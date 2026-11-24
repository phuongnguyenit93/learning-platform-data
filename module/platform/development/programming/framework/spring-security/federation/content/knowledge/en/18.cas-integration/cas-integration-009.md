# Distinguishing Stateful Application Sessions from Stateless Ticket Authentication Mode

> **Module:** Spring Security – Federation · **Parent Topic:** CAS Integration. This lesson distinguishes **stateful CAS web login (stateful application session)** from **CAS ticket authentication without `HttpSession` (stateless client/service)**, focusing specifically on Spring Security's `CasAuthenticationFilter`, `CasAuthenticationProvider`, and `StatelessTicketCache`. "Stateless" in HTTP/Spring **does not automatically mean** the entire system holds no state, nor does it **permit reusing a CAS ticket at the CAS server after it has been validated**.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Identify **CAS server SSO session**, **service ticket (ST)**, **proxy ticket (PT)**, **application `HttpSession`**, and **`SecurityContext`** as distinct constructs.
2. Describe how a browser receives an ST, the application calls CAS to validate the ST **once**, and then persists `Authentication` in the application session for subsequent requests.
3. Explain why API/remoting clients without session cookies must normally present a credential **on every request** instead of relying on `JSESSIONID`.
4. Distinguish `CasServiceTicketAuthenticationToken.CAS_STATEFUL_IDENTIFIER` from `CAS_STATELESS_IDENTIFIER` in the Spring Security CAS 6.x API.
5. Understand the roles of `ServiceProperties.authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource`, `Cas20ProxyTicketValidator`, and `StatelessTicketCache`.
6. Resolve the apparent paradox: **a CAS ST/PT is validated only once**, yet Spring can **reuse a cached authentication keyed by ticket** in stateless mode.
7. Compare `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository`, and `SessionCreationPolicy.STATELESS`, without confusing Spring's session policy with CAS ticket-processing configuration.
8. Recognize the risks of a **ticket cache acting as a bearer credential**: token leakage, replay during TTL, service/tenant scoping, stale roles, logout/revocation, multi-node consistency, and availability.
9. Design both deployment styles—a stateful web portal and a stateless backend API—choosing the right auth mechanism rather than forcing CAS tickets to act like JWTs or permanent API keys.
10. Run a standalone Java 17 program clearly illustrating CAS validation timing, local session reads, cache hits, and post-expiration behavior.
11. Build a test matrix covering session fixation, TTLs, service mismatches, PT/PGT trust, CAS outages, logout, and per-request authorization data.

**Version scope:** Java 17, Spring Boot 3.3.x / Spring Security 6.3.x using the **CAS** protocol; newer/older Spring Security APIs and configuration patterns must be verified against your actual dependencies. Conditional Spring examples require a real CAS server and proper service registration; the standalone Java code makes no real CAS calls.

## 2. The Deciding Question: After Authentication, How Do Subsequent Requests Prove Identity?

An Orders Portal application has both a browser UI and a backend reporting API:

- The browser visits `/orders` and is redirected to CAS. Once CAS validates the ST, Portal creates a `JSESSIONID` session. The browser continues making requests with the **Portal session cookie**; Portal **does not re-validate the ST** on every request.
- A service-to-service client calls `/api/reports` **without an `HttpSession` cookie**. If using CAS proxy tickets under Spring's stateless mechanism, each request must carry the **corresponding ticket**, and the API must authenticate that request—either by validating a **fresh ticket** at CAS every time, or by using a **`StatelessTicketCache`** to reuse a prior validation result within a managed window.

From the outside, both have "logged in via CAS"; the difference lies in **where proof of login is held between requests**.

| Criterion | Stateful Web Portal | CAS Stateless Remoting / API |
| --- | --- | --- |
| Typical caller | Browser with cookies, multi-request UI. | Backend/remote client not using Portal session cookies. |
| Typical CAS ticket | ST from `/login?service=...`. | PT issued via PGT, scoped to `targetService`. |
| Ticket arrival point | `CasAuthenticationFilter.filterProcessesUrl`, defaulting to `/login/cas`. | URLs other than login callback when `authenticateAllArtifacts` is enabled with dynamic service URLs. |
| Internal signal | `CAS_STATEFUL_IDENTIFIER`. | `CAS_STATELESS_IDENTIFIER`. |
| Identifier on subsequent requests | Session ID cookie `JSESSIONID` and server-side `SecurityContext`. | Credential on the request, typically a PT; optionally looked up in `StatelessTicketCache`. |
| Direct CAS validation | Upon initial ST receipt for login. | On first PT cache miss, or on every fresh ticket if uncached. |
| Where auth lives | `HttpSession` / session store. | No `HttpSession` needed, though a **server-side ticket cache** may exist. |
| Primary TTL / revocation | Session timeout, logout, session store, local account policy. | Ticket cache TTL/eviction, ticket exposure, and local permissions; single-use CAS ticket does not auto-purge cache. |
| If state is lost | User may have to re-SSO/re-login. | If cache is lost, the same PT already consumed at CAS cannot be re-validated. |
| Major risk | Session cookie hijacking, fixation/CSRF/session mismatch. | Token/PT leakage, replay within cache window, improper service/tenant isolation. |

**Core conclusion:** Stateful vs. stateless describes **how the application continues authenticating subsequent requests**, not whether the CAS server maintains an SSO session. CAS always manages its own ticket/SSO lifecycle separately.

## 3. Five Distinct State Types to Keep Separate

### 3.1. CAS TGT / TGC: Identity Provider SSO State

- The CAS server issues a **Ticket-Granting Ticket (TGT)** upon user authentication, managing the SSO session within CAS's boundary.
- The browser typically holds a **Ticket-Granting Cookie (TGC)** scoped to the CAS domain; Portal does **not** own that cookie.
- TGT/TGC lifetimes may be longer than, shorter than, or independent of Portal's HTTP session.
- One CAS SSO session can issue **multiple STs** for different applications.
- Local logout at Portal **does not guarantee** logging out TGT/TGC at CAS; CAS logout / Single Sign-Out must be implemented if required.

### 3.2. Service Ticket (ST): Single-Service Transfer Credential

- CAS issues an ST for **one service URL** after the browser authenticates.
- The browser returns to `https://portal.example/login/cas?ticket=ST-...`.
- The **Portal server** calls CAS `/serviceValidate?service=...&ticket=...` over HTTPS.
- CAS checks that the ST matches the service, is unused, and is unexpired; validation **consumes** the ST regardless of success or failure per the CAS protocol.
- An ST is **not** a local session ID, username, or business permission.

### 3.3. Proxy-Granting Ticket and Proxy Ticket

An already-authenticated application may need to call a backend service **on behalf of the user**:

- It uses a trusted `pgtUrl` callback during CAS validation to receive and correlate a **Proxy-Granting Ticket (PGT)** via `PGTIOU`.
- The app uses the PGT to ask CAS for a **Proxy Ticket (PT)** scoped to a specific `targetService` via `/proxy`.
- The backend receives the PT and calls `/proxyValidate`, not `/serviceValidate` for PTs.
- A PT is likewise **opaque, service-bound, and valid for a single validation attempt** at CAS.
- The `cas:proxies` chain reflects intermediary services; the backend must accept only approved proxies.

**Never use a PGT as a PT**, and never pass a PGT or TGT to the browser or backends outside the trust boundary. A PGT can mint many PTs; leaking a PGT is far more severe than leaking a single narrowly scoped PT.

### 3.4. Application `HttpSession`: Portal State

`JSESSIONID` normally references an `HttpSession` managed by Portal or its session store. That session can hold `SPRING_SECURITY_CONTEXT` containing the CAS-authenticated `Authentication`.

~~~text
Browser cookie JSESSIONID=abc
       |
       v
Portal HttpSession abc
       |
       +-- SecurityContext
       |     Authentication principal=alice
       |     GrantedAuthorities=[APP_ORDER_READ]
       |
       +-- SavedRequest, CSRF token, or other session data
~~~

The browser does not resend the ST after login. Every request through Spring Security restores `SecurityContext` from the repository/session (while valid) and then checks business authorization.

### 3.5. `StatelessTicketCache`: State Outside `HttpSession`

Spring Security's `StatelessTicketCache` is **not** a browser session store; it maps **ticket -> verified `CasAuthenticationToken`**.

~~~text
Client request PT-abc
    |
    v
API CAS filter / provider
    |
    +-- Cache MISS -> HTTPS CAS /proxyValidate
    |                 -> verified user + authorities
    |                 -> put CasAuthenticationToken in cache
    |
    +-- Cache HIT  -> reuse cached CasAuthenticationToken
    |
    v
Request SecurityContext (this request only)
    |
    v
Authorization / business handler
~~~

With a 2-minute cache TTL, CAS has already consumed the PT on the first call, yet the API continues accepting **that same PT string** for two minutes via its **local cache**—not because CAS relaxed its single-use rule. Treat this mechanism as **turning a ticket into a temporary bearer credential inside the API** and govern it strictly.

## 4. Stateful Browser Login: Complete Timeline

~~~text
Browser             Portal (Spring Security)             CAS Server
   |                         |                              |
   | GET /orders             |                              |
   |------------------------>| no local Authentication      |
   |<-- 302 CAS /login ------| service=Portal/login/cas     |
   |------------------------------------------------------->|
   |                         |                              | TGC/TGT or credentials
   |<-- 302 Portal?ticket=ST-|------------------------------|
   | GET /login/cas?ticket=ST                              |
   |------------------------>| CasAuthenticationFilter      |
   |                         |-- CAS /serviceValidate ----->|
   |                         |<-- CAS XML Success ----------|
   |                         | load UserDetails/roles       |
   |                         | save SecurityContext in      |
   |                         | HttpSession, rotate ID       |
   |<-- redirect clean URL --|                              |
   | GET /orders + JSESSIONID                               |
   |------------------------>| restore SecurityContext      |
   |<-- 200 or 403 ----------| authorization check          |
~~~

### 4.1. Concrete Steps in Spring

1. `ExceptionTranslationFilter` invokes `CasAuthenticationEntryPoint` when a protected request is unauthenticated.
2. `CasAuthenticationEntryPoint` constructs the CAS login URL using `ServiceProperties.service` as the canonical callback URL.
3. CAS issues an ST and redirects the browser to the `/login/cas` callback.
4. `CasAuthenticationFilter` intercepts the ticket at `filterProcessesUrl` and creates a `CasServiceTicketAuthenticationToken` with a principal indicating **stateful** mode.
5. `AuthenticationManager` forwards the token to `CasAuthenticationProvider`.
6. The provider uses `Cas20ServiceTicketValidator` and `ServiceProperties` to call CAS `/serviceValidate` over TLS.
7. CAS returns `cas:authenticationSuccess`; the provider loads local authorities and builds `CasAuthenticationToken`.
8. The authentication filter / `SecurityContextRepository` saves the result to the session; Spring handles session fixation as configured.
9. Subsequent requests use the session cookie without **reusing the ticket**; backend authorization still enforces permissions/tenant/resource checks.

### 4.2. Why Not Call CAS on Every HTTP Request?

Because an ST is single-use. If the browser resubmitted the same `ST-...` on the next page view, CAS would return `INVALID_TICKET`. A stateful web app must rely on a **different** post-login credential, typically the Portal session cookie.

**Do not confuse**:
- "ST is single-use" = **CAS validation** rule.
- "Portal session spans many requests" = **Portal session management** rule.
- "CAS TGT is still alive" = reason a user can re-SSO quickly if the Portal session expires.

### 4.3. Session Fixation and Cookies

After CAS login, enforce:
- Session ID rotation on successful authentication; in modern Servlets Spring normally uses `changeSessionId()`, though custom CAS filters/session strategies must be configured and tested explicitly.
- `Secure`, `HttpOnly`, and `SameSite` cookie flags suited to the app and cross-site flows.
- CSRF protection for cookie-backed browser actions; the login callback is a GET handling tickets separately.
- Idle session timeout, absolute timeout if policy requires, logout invalidation, concurrent session limits, and account revocation.
- Never put `JSESSIONID` in URLs, and never treat a browser-supplied `HttpSession` as proof of authorization outside Spring Security.
- Use a shared session store or tested session affinity if Portal runs across multiple instances.

### 4.4. After Local Logout

Local logout at Portal destroys `HttpSession` and its `SecurityContext`. **CAS's TGC/TGT may remain active**, so revisiting a protected page can redirect to CAS and obtain a **fresh ST** without re-entering a password. That is a new SSO round-trip, not reuse of the old ST.

## 5. Stateless CAS: Authenticating Every Request Without `HttpSession`

### 5.1. Differing From the Entry Point

The Spring Security reference defines a **stateful CAS client** as a request carrying a ticket sent to `CasAuthenticationFilter.filterProcessesUrl`. A **stateless CAS client** is a request carrying a ticket to a URL **other than** that callback, when the filter is configured to accept tickets on permitted URLs.

Key pieces enabled per the Spring Security CAS pattern:

- `ServiceProperties.setAuthenticateAllArtifacts(true)`: allows processing CAS tickets on URLs beyond the login callback (must be bounded by security filter chain and route trust).
- `ServiceAuthenticationDetailsSource`: supplies the **service URL of the currently protected request** to the provider, rather than blindly using the fixed web callback `ServiceProperties.service`.
- `CasServiceTicketAuthenticationToken.CAS_STATELESS_IDENTIFIER`: signals to the provider that authentication is stateless and must not rely on a prior session-stored auth.
- `Cas20ProxyTicketValidator`: validates **proxy tickets** via CAS `/proxyValidate`, distinct from `Cas20ServiceTicketValidator` for STs.
- `StatelessTicketCache`: optionally caches a verified `CasAuthenticationToken` per policy, enabling cache hits when the caller presents the same ticket again.
- `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository`: ensure **no `SecurityContext` is saved into `HttpSession`** across requests.

**No single property configures this entire design automatically.** `SessionCreationPolicy.STATELESS` affects only Spring's session/security context; it does not enable CAS PT processing across APIs, configure the ticket validator, select target services, or enforce proxy trust.

### 5.2. Standard Proxy Ticket Flow

~~~text
User/browser -> Front-end App (already CAS-logged-in)
                  |
                  | holds PGT from CAS via verified callback
                  v
           CAS /proxy?pgt=PGT-...&targetService=API
                  |
                  +-> returns PT-xyz strictly for API
                  |
Front-end server -- HTTPS, PT-xyz --> Back-end API
                                      |
                                      | no JSESSIONID
                                      | CasAuthenticationFilter
                                      | ticket cache lookup
                                      |
                          MISS ------+------ HIT
                           |                  |
                     CAS /proxyValidate      cached CasAuthenticationToken
                     service=API            (must still have TTL/trust)
                     ticket=PT-xyz           |
                           |                  |
                      validated user -------+
                                      |
                                      v
                              Request-only SecurityContext
                                      |
                                      v
                              local authorization
~~~

**Important:** once the backend API validates a PT and caches the token while valid, subsequent requests carrying the same PT succeed **via the cache**, not because CAS allows re-validating the PT. The CAS protocol still enforces **one validation attempt** per PT and binds it to the issued `targetService`.

### 5.3. "Not Saving Sessions" Does Not Mean "Holding Zero State"

Even when no `HttpSession` is created, the system can still maintain:

- TGT/TGC and ticket state on the CAS server.
- PGT storage in the front-end service (when proxying).
- `StatelessTicketCache` in the API (if enabled).
- Revocation blocklists, permission caches, and identity links.
- Load balancer affinity, rate limiting, audits, and request tracing.

Thus "stateless" in the application typically means only **not using per-browser `HttpSession` for authentication persistence**. Nothing in the architecture forces the CAS server to be stateless or eliminates caches.

### 5.4. Consequences of Omitting a Ticket Cache

If every API request must carry a **fresh** PT, the API calls CAS `/proxyValidate` for that PT, CAS consumes it, and the authentication result lives only for that single request.

Advantages:
- No window of **cached reusable tickets**.
- Revocation and ticket validity are checked at CAS on every **new ticket**.
- No need to share a ticket cache across API nodes.

Disadvantages:
- The front-end must mint a new PT via its PGT on every call.
- More CAS and HTTPS round-trips, impacting latency and availability.
- A CAS outage blocks new requests from authenticating unless another valid credential exists.
- Requires securing PGT storage, managing proxy chains, and avoiding retries of already-consumed PTs.

`NullStatelessTicketCache` is the no-op cache implementation in Spring's API; it ensures **zero cache hits**, yet **never turns an old PT into a credential CAS will validate multiple times**.

## 6. One-Time CAS Tickets and Caching: Two Rules That Only Look Contradictory

### 6.1. CAS Protocol

For ST/PT:

1. CAS issues a ticket for one specific `service`.
2. The ticket is valid for a short window.
3. On the **first** validation call, CAS consumes the ticket—even on wrong service or failed validation.
4. Subsequent validation attempts with that same ticket are rejected by CAS.

~~~text
CAS:
validate(PT-1, API) -> SUCCESS, mark PT-1 consumed
validate(PT-1, API) -> INVALID_TICKET
~~~

### 6.2. Spring CAS Stateless Ticket Cache

With `SpringCacheBasedTicketCache` configured:

~~~text
API:
Request #1, PT-1 -> cache MISS -> CAS validates SUCCESS
                -> cache[PT-1]=CasAuthenticationToken(user=alice), TTL 2m

Request #2, PT-1 -> cache HIT  -> accepts cached authentication
                -> DOES NOT call CAS validate a second time

Request #3, PT-1 after TTL -> cache MISS
                -> CAS validate -> INVALID_TICKET because PT-1 was consumed
~~~

There is zero contradiction: **CAS refuses re-validation**, while the API **skips calling CAS again** on a cache hit.

### 6.3. Security: This Is Effectively an API-Created Bearer Credential

If the same PT string can be replayed to retrieve a cached `CasAuthenticationToken`, anyone who obtains that PT string within the TTL **can replay it** against the API. Hence caching is not merely a CPU optimization; it **changes the API's ticket threat model**.

Mandatory questions before enabling it:

- What TLS/mTLS protects the PT in transit? Could it leak into URL queries, browser history, `Referer`, access logs, or telemetry?
- How long is the cache TTL? Are size caps and eviction on user disable/logout enforced?
- Does the cache key scope by CAS realm, target service, tenant, and route/method if policy requires? Spring's default cache is documented as keyed by ticket ID; **do not assume every business constraint is re-checked on a cache hit**.
- Is the cache shared across multiple security chains or tenants without partitioning?
- Are local roles and account status re-verified before sensitive actions?
- During a CAS backend outage, does the cache keep permitting requests? If so, is that an approved risk-policy decision?
- After cache eviction, will the system request a fresh PT or unexpectedly hit CAS with an old ticket and fail?
- Does auditing capture cache hits, misses, expirations, and revocations?

**Safe default for sensitive APIs:** prefer a fresh PT / fresh validation per request, or a purpose-built access token mechanism with explicit audience, scope, expiration, and revocation. Enable caching only after reviewing the threat model and TTL limits—never just to cut CAS call counts.

## 7. What Is State in Spring Security, and Where Does It Live?

### 7.1. `SecurityContextHolder` != `SecurityContextRepository`

- `SecurityContextHolder` normally holds `SecurityContext` at **thread/request** scope so filters and services can read `Authentication`.
- `SecurityContextRepository` decides whether context is **saved and restored** across requests.
- `HttpSessionSecurityContextRepository` reads/writes the security context in `HttpSession`.
- `NullSecurityContextRepository` never persists context across requests.
- `SessionCreationPolicy.STATELESS` instructs Spring Security not to create or use `HttpSession` for `SecurityContext`; that is a **Spring session** policy, not a proxy-ticket policy.

Thus a stateless API still populates `SecurityContextHolder.getContext().getAuthentication()` **while processing an authenticated request**. The difference is that **the next request has no cookie/session context to restore**.

### 7.2. `SessionCreationPolicy` in Context

| Policy | Approximate Meaning | Is It CAS Stateless Auth? |
| --- | --- | --- |
| `ALWAYS` | Spring creates a session. | No; still requires separate CAS wiring. |
| `IF_REQUIRED` | Creates a session when the framework needs one. | Fits most stateful web flows. |
| `NEVER` | Spring never creates a new session proactively, though it may use an existing one. | Does not guarantee zero session usage. |
| `STATELESS` | Neither creates nor uses `HttpSession` for `SecurityContext`. | **Insufficient** on its own to accept/validate CAS tickets statelessly. |

A redirect-based CAS web portal normally needs a request cache/`SavedRequest`, CSRF tokens, and a callback session. Forcing `STATELESS` onto that same filter chain without redesigning those components causes redirect loops or lost `Authentication` after redirect.

### 7.3. Multiple `SecurityFilterChain` Configurations

You can separate them:

~~~text
@Order(1) /api/**  -> CAS PT or bearer API; STATELESS;
                      NullSecurityContextRepository; no web redirects

@Order(2) /**      -> CAS web ST callback, HttpSession session;
                      CasAuthenticationEntryPoint, CSRF, session fixation
~~~

Chains must define **exact `requestMatcher` rules** so a `CasAuthenticationFilter` configured with `authenticateAllArtifacts=true` does not accidentally intercept tickets on unintended URLs. Each chain should have its own trust configuration, never sharing caches across incompatible scopes.

## 8. Comparing Architectural Choices

| Context | Suitable Model | Why |
| --- | --- | --- |
| Browser-based MVC web app, many pages | Stateful CAS login + local `HttpSession`. | CAS ticket validates once; sessions fit browsers. |
| SPA calling same-origin backend with cookies | Can use web session + CSRF/session policy. | "SPA" does not mandate statelessness. |
| Service-to-service API calls on user's behalf via CAS proxy | CAS PT + stateless processing per trusted target service. | Every request carries credentials without browser cookies. |
| High-traffic API wanting PT caching | Only with an explicit cache threat model, TTL, and revocation. | Cache reduces CAS calls while opening a replay window. |
| Multi-client public API needing no CAS delegation | Consider OAuth2/OIDC JWT or opaque access tokens by design. | CAS PT does not replace a standard API token system. |
| Sensitive service requiring per-call identity verification | Fresh PT/validation per request or dedicated step-up design. | Avoids long-lived cached authentication. |
| Web portal with multi-app logout | CAS SLO + local session invalidation per contract. | TGT/TGC and Portal `HttpSession` are two distinct session systems. |
| Multi-tenant using distinct CAS realms | Scope realm/service/tenant and isolate caches. | Usernames and ticket IDs are not globally meaningful. |

**Do not pick stateless simply because it sounds more modern.** Operational overhead and security risk depend on callers, client capabilities, credential management, latency, and revocation requirements.

## 9. Standalone Java 17: Local Session vs. PT Cache

This example has **no real CAS server** and **no real `HttpSession`**. It simulates only the rules: CAS tickets are single-use, Portal retains a local session after web login, and the API caches PT validation results for a short TTL. Because it uses fixed maps and synthetic timestamps, stdout is **independent of wall-clock time**.

### 9.1. File `CasSessionModesDemo.java`

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CasSessionModesDemo {

    private static final String WEB =
        "https://portal.example/login/cas";
    private static final String API =
        "https://api.example/reports";
    private static final String OTHER =
        "https://other.example/reports";

    record Ticket(String service, String username) { }
    record CachedAuth(String username, long expiresAt) { }

    // Simulates the CAS side: ST/PT consumed on first attempt.
    static final class CasServer {
        private final Map<String, Ticket> issued = new HashMap<>();
        private final Set<String> consumed = new HashSet<>();

        void issue(String ticketId, String service, String user) {
            issued.put(ticketId, new Ticket(service, user));
        }

        String validate(String ticketId, String service) {
            Ticket issuedTicket = issued.get(ticketId);
            if (issuedTicket == null || !consumed.add(ticketId)) {
                return "INVALID_TICKET";
            }
            if (!issuedTicket.service().equals(service)) {
                return "INVALID_SERVICE";
            }
            return "SUCCESS:" + issuedTicket.username();
        }
    }

    // Simulates Web Portal: remembers username by session ID.
    static final class StatefulPortal {
        private final CasServer cas;
        private final Map<String, String> sessions = new HashMap<>();

        StatefulPortal(CasServer cas) {
            this.cas = cas;
        }

        String login(String ticket, String sessionId) {
            String result = cas.validate(ticket, WEB);
            if (!result.startsWith("SUCCESS:")) {
                return "DENY:" + result;
            }
            String username = result.substring("SUCCESS:".length());
            sessions.put(sessionId, username);
            return "AUTH:" + username;
        }

        String nextRequest(String sessionId) {
            String user = sessions.get(sessionId);
            return user == null ? "ANONYMOUS" : "AUTH:" + user;
        }

        void logout(String sessionId) {
            sessions.remove(sessionId);
        }
    }

    // Simulates API without HttpSession:
    // On cache hit, CAS is not called again.
    static final class StatelessApi {
        private final CasServer cas;
        private final Map<String, CachedAuth> cache = new HashMap<>();
        private final long ttlSeconds;

        StatelessApi(CasServer cas, long ttlSeconds) {
            this.cas = cas;
            this.ttlSeconds = ttlSeconds;
        }

        String request(String ticket, String service, long now) {
            // Scoped by target service, unlike ticket-only keys
            // in some built-in Spring caches.
            String key = service + "#" + ticket;
            CachedAuth entry = cache.get(key);

            if (entry != null && now < entry.expiresAt()) {
                return "AUTH:" + entry.username() + " (CACHE)";
            }
            cache.remove(key);

            String result = cas.validate(ticket, service);
            if (!result.startsWith("SUCCESS:")) {
                return "DENY:" + result;
            }

            String username = result.substring("SUCCESS:".length());
            cache.put(key, new CachedAuth(username, now + ttlSeconds));
            return "AUTH:" + username + " (CAS)";
        }
    }

    public static void main(String[] args) {
        CasServer cas = new CasServer();
        StatefulPortal web = new StatefulPortal(cas);
        StatelessApi api = new StatelessApi(cas, 30);

        cas.issue("ST-WEB", WEB, "alice");
        System.out.println("webLogin=" +
            web.login("ST-WEB", "session-1"));
        System.out.println("webNext=" +
            web.nextRequest("session-1"));
        System.out.println("webReplay=" +
            web.login("ST-WEB", "session-2"));
        web.logout("session-1");
        System.out.println("webAfterLogout=" +
            web.nextRequest("session-1"));

        cas.issue("PT-API", API, "bob");
        System.out.println("apiFirst=" +
            api.request("PT-API", API, 100));
        System.out.println("apiCached=" +
            api.request("PT-API", API, 110));
        System.out.println("apiExpired=" +
            api.request("PT-API", API, 131));

        cas.issue("PT-WRONG", API, "charlie");
        System.out.println("apiWrongService=" +
            api.request("PT-WRONG", OTHER, 200));
        System.out.println("apiAfterWrongService=" +
            api.request("PT-WRONG", API, 201));
    }
}
~~~

### 9.2. Compile and Run

Requires **JDK 17 or newer**:

~~~bash
javac --release 17 CasSessionModesDemo.java
java CasSessionModesDemo
~~~

**Exact stdout:**

~~~text
webLogin=AUTH:alice
webNext=AUTH:alice
webReplay=DENY:INVALID_TICKET
webAfterLogout=ANONYMOUS
apiFirst=AUTH:bob (CAS)
apiCached=AUTH:bob (CACHE)
apiExpired=DENY:INVALID_TICKET
apiWrongService=DENY:INVALID_SERVICE
apiAfterWrongService=DENY:INVALID_TICKET
~~~

**Reading the results:**

- `webLogin` validates the ST once and populates the local session map.
- `webNext` skips calling CAS because the Portal session exists.
- `webReplay` shows the old ST cannot be reused.
- `webAfterLogout` clears the local session, returning to anonymous.
- `apiFirst` validates the PT successfully and caches authentication for 30 seconds.
- `apiCached` reuses the local cache entry without making CAS allow a second PT validation.
- `apiExpired`: cache TTL elapsed; CAS already consumed the PT so re-validation fails, requiring a **fresh PT**.
- `apiWrongService` consumes the PT when validating against the wrong service.
- `apiAfterWrongService`: fixing the URL still fails because the old PT was already consumed; a new ticket is required.

**Limitations:** This code lacks HTTP, TLS, proxy chains, cryptography, account authorization, and real CAS internals. Keying cache by `service#ticket` illustrates scoping; verify Spring's actual cache key structure against its Javadoc/version and design partitioning with approved controls rather than assuming defaults match this demo.

## 10. Spring Boot 3.3: Stateful CAS Web Configured in Java

Below is an **integration sample project** for a web portal using CAS service tickets and `HttpSession`. It requires a real CAS server; login cannot be verified merely by running code without CAS metadata and a service registry. The goal is illustrating **where `SecurityContext` is saved** and the CAS provider's responsibilities, rather than writing a `TicketValidator` that blindly accepts every ticket.

### 10.1. Structure

~~~text
cas-stateful-web/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/casstate/
    │   ├── CasStatefulApplication.java
    │   ├── CasWebSecurityConfig.java
    │   └── MeController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cas-stateful-web'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'
}
~~~

**Use `spring-security-cas`**, not `spring-security-saml2-service-provider`, for CAS ST/PT. The pinned versions here are for learning; in production use actively maintained, security-patched Spring/CAS client versions.

### 10.2. Application and Configuration

`src/main/java/com/example/casstate/CasStatefulApplication.java`:

~~~java
package com.example.casstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasStatefulApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasStatefulApplication.class, args);
    }
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  cas:
    base-url: "${CAS_BASE_URL}"
    login-url: "${CAS_LOGIN_URL}"
    web-service: "${CAS_WEB_SERVICE}"

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Example environment variables set by an administrator:

~~~text
CAS_BASE_URL=https://cas.partner.example/cas
CAS_LOGIN_URL=https://cas.partner.example/cas/login
CAS_WEB_SERVICE=https://portal.example/login/cas
~~~

**`CAS_WEB_SERVICE` must match the exact canonical service URL** registered in CAS and handled by the CAS filter receiving `ticket`. If a reverse proxy places the app under a different scheme/host/port, fix the URL config upfront—never disable service matching at CAS.

### 10.3. `CasWebSecurityConfig.java`

~~~java
package com.example.casstate;

import java.util.List;
import java.util.Map;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {

    @Bean
    ServiceProperties casWebServiceProperties(
            @Value("${app.cas.web-service}") String serviceUrl) {
        if (!serviceUrl.startsWith("https://")
                || !serviceUrl.endsWith("/login/cas")) {
            throw new IllegalArgumentException(
                "Expected canonical HTTPS CAS callback /login/cas");
        }
        ServiceProperties result = new ServiceProperties();
        result.setService(serviceUrl);
        result.setAuthenticateAllArtifacts(false);
        return result;
    }

    @Bean
    UserDetailsService localUsers() {
        // Learning only: permit only known subjects.
        UserDetails alice = User.withUsername("alice")
            .password("{noop}unused-for-CAS-auth")
            .authorities("APP_REPORT_READ")
            .build();
        Map<String, UserDetails> allowed = Map.of("alice", alice);
        return username -> {
            UserDetails account = allowed.get(username);
            if (account == null) {
                throw new UsernameNotFoundException(
                    "CAS user not linked to an enabled local account");
            }
            return account;
        };
    }

    @Bean
    CasAuthenticationProvider casWebProvider(
            ServiceProperties casWebServiceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.base-url}") String baseUrl) {

        if (!baseUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                "CAS validation server must be HTTPS");
        }

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(casWebServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(baseUrl));
        provider.setUserDetailsService(localUsers);
        provider.setKey("cas-stateful-portal");
        return provider;
    }

    @Bean
    CasAuthenticationEntryPoint casWebEntryPoint(
            ServiceProperties casWebServiceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {

        if (!loginUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                "CAS login server must be HTTPS");
        }

        CasAuthenticationEntryPoint point =
            new CasAuthenticationEntryPoint();
        point.setLoginUrl(loginUrl);
        point.setServiceProperties(casWebServiceProperties);
        return point;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            CasAuthenticationProvider casWebProvider,
            CasAuthenticationEntryPoint casWebEntryPoint,
            ServiceProperties casWebServiceProperties) throws Exception {

        AuthenticationManager manager =
            new ProviderManager(List.of(casWebProvider));
        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        // Instantiate filter inside the chain to prevent Spring Boot from
        // auto-registering a @Bean Filter a second time in the Servlet container.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setAuthenticationManager(manager);
        casFilter.setServiceProperties(casWebServiceProperties);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setSecurityContextRepository(repository);
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(casWebEntryPoint)
            )
            .securityContext(ctx -> ctx
                .securityContextRepository(repository)
            )
            .addFilterAt(casFilter, CasAuthenticationFilter.class)
            .build();
    }
}
~~~

**Configuration explanation:**

- `ServiceProperties.service` pins the callback URL, and `authenticateAllArtifacts=false` restricts ST handling to the callback rather than arbitrary URLs.
- `CasAuthenticationEntryPoint` redirects the browser to CAS.
- `CasAuthenticationFilter` handles `/login/cas`; the CAS request principal is the stateful identifier.
- `CasAuthenticationProvider` calls `Cas20ServiceTicketValidator`: the CAS server performs real ST validation.
- `HttpSessionSecurityContextRepository` saves and restores `Authentication` across Portal requests.
- `ChangeSessionIdAuthenticationStrategy` demonstrates session fixation protection upon successful CAS authentication; test with your actual Servlet container/session setup.
- `UserDetailsService` supplies local authorities for linked users. `{noop}` in the demo **is not used for CAS authentication** and is not a secure choice for production password logins.
- **Do not declare `CasAuthenticationFilter` as a `@Bean`** while also adding it to the chain, as Spring Boot auto-registers `Filter` beans in the Servlet container outside `SecurityFilterChain`.
- Do not configure `SessionCreationPolicy.STATELESS` in this cookie/session web chain.
- Local logout and CAS SLO are distinct. Add CAS Single Sign-Out configuration only when the partner actually supports it and it has been tested.

### 10.4. Controller

`src/main/java/com/example/casstate/MeController.java`:

~~~java
package com.example.casstate;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/")
    public String home() {
        return "Open /me to sign in with CAS";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(a -> a.getAuthority()).toList()
        );
    }
}
~~~

With CAS user `alice` and the local allowlist, `GET /me` returns:

~~~json
{
  "user": "alice",
  "authorities": ["APP_REPORT_READ"]
}
~~~

This **does not** mean CAS granted `APP_REPORT_READ`. That authority came from the local `UserDetailsService`. If CAS authenticates a subject with no local account, the app does not invent permissions automatically.

### 10.5. Run and Verify

~~~bash
./gradlew bootRun
~~~

Prepare a compatible JDK 17/Gradle wrapper, public HTTPS host, real CAS server, service registry, and proper CA/certificate configuration. Without real URLs/keys/service registration, startup or login will not complete; this guide **does not supply a fake IdP**.

Verification procedure:

1. Browser accesses `/me` and receives a redirect to CAS login.
2. CAS authenticates and issues an ST pointing to exact `CAS_WEB_SERVICE`.
3. Portal server calls `/serviceValidate` over TLS; never perform this from the browser.
4. Spring persists the authenticated `SecurityContext` in `HttpSession`.
5. A second request with the same `JSESSIONID` returns the same principal **without resending the ST**.
6. After local logout, `JSESSIONID` holds no authentication; CAS TGC may issue a fresh ST to re-SSO.
7. Replaying the old ST to the callback must be rejected by CAS rather than creating a new authentication.
8. Verify session ID rotation on login, timeouts, cookies, and disabled accounts.

## 11. Stateless Spring CAS: Configuring Core Components

**This is an integration recipe to wire into a dedicated API `SecurityFilterChain`, not a standalone runnable project:** it requires the CAS proxy protocol, a PGT/PT issuer, a backend service registry, proxy trust policies, role mapping, and a ticket cache implementation. Its purpose is highlighting mandatory components and audit points, rather than claiming adding `sessionCreationPolicy(STATELESS)` suffices.

### 11.1. Decide Endpoints and Target Services First

Suppose the backend API accepts tickets via URL:

~~~text
https://api.example/internal/reports?ticket=PT-...
~~~

The IdP issued the PT for that exact `targetService`, and Spring's `ServiceAuthenticationDetailsSource` must construct the identical service URL for `/proxyValidate`. Example URLs **must not leak tickets into access logs** and require HTTPS and masking. Never let clients alter hostnames, tenants, or proxy trust via `service`/`casServer` parameters.

If the API serves `/internal/reports?page=2` and `/internal/reports?page=3`, align with CAS on how **canonical service URLs**/queries are matched. Do not assume a PT for reports automatically validates on arbitrary paths/queries. Fixed CAS-registered service IDs may work if supported by your profile and client library; test thoroughly.

### 11.2. Enabling `authenticateAllArtifacts` and `ServiceAuthenticationDetailsSource`

~~~java
// API BEAN / WIRING FRAGMENT, not a standalone class.
ServiceProperties apiService = new ServiceProperties();
apiService.setService("https://api.example/internal/reports");
apiService.setAuthenticateAllArtifacts(true);

CasAuthenticationFilter apiFilter = new CasAuthenticationFilter();
apiFilter.setServiceProperties(apiService);
apiFilter.setAuthenticationDetailsSource(
    new org.springframework.security.cas.web.authentication
        .ServiceAuthenticationDetailsSource(apiService)
);
apiFilter.setAuthenticationManager(apiAuthManager);
apiFilter.setSecurityContextRepository(
    new org.springframework.security.web.context
        .NullSecurityContextRepository()
);
~~~

**To complete:** `apiAuthManager` is a manager containing the API's `CasAuthenticationProvider`; configure the filter chain to match `/internal/**` with an entry point returning 401 instead of a browser redirect. This is a **wiring fragment**, not a Java class with all imports and a `main` method.

**Trust boundary:** `ServiceAuthenticationDetailsSource` inspects the incoming request URL; if reverse proxy / `Host` headers are unguarded, the computed service URL can be wrong or spoofed. Use canonical public URLs / allowlisted routes and trust forwarded headers **only from trusted reverse proxies**.

### 11.3. Provider Using a Proxy Ticket Validator

~~~java
// BEAN FRAGMENT: backend API validates PT via /proxyValidate.
// These settings come from trusted configuration, never from the request.
CasAuthenticationProvider apiProvider =
    new CasAuthenticationProvider();

apiProvider.setServiceProperties(apiService);
apiProvider.setTicketValidator(
    new org.apereo.cas.client.validation
        .Cas20ProxyTicketValidator("https://cas.example/cas")
);
apiProvider.setUserDetailsService(localUsers);
apiProvider.setKey("cas-stateless-api");
~~~

In production, configure **`CasProxyDecider`** or an appropriate proxy trust policy so unauthorized intermediary chains are rejected. CAS docs sometimes show `acceptAnyProxy=true` for illustration; **never enable it by default in sensitive environments**. If deploying proxying, configure the PGT callback/PGTIOU and verify source/target service policies at CAS.

### 11.4. Choosing a Ticket Cache

**No cache:**

~~~java
// Creates no window for re-accepting the same PT in a local cache.
// Requires a FRESH PT on the next API request.
apiProvider.setStatelessTicketCache(
    new org.springframework.security.cas.authentication
        .NullStatelessTicketCache()
);
~~~

**With cache:** Spring Security provides `SpringCacheBasedTicketCache` wrapping a Spring `Cache`. Example with TTL and size cap (this snippet requires Caffeine and `spring-context-support` dependencies):

~~~java
// CACHE CONFIGURATION FRAGMENT, not a complete SecurityConfig.
org.springframework.cache.Cache localCache =
    new org.springframework.cache.caffeine.CaffeineCache(
        "cas-pt-auth",
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(5000)
            .expireAfterWrite(java.time.Duration.ofSeconds(60))
            .build()
    );

apiProvider.setStatelessTicketCache(
    new org.springframework.security.cas.authentication
        .SpringCacheBasedTicketCache(localCache)
);
~~~

With a 60-second cache, `CasAuthenticationProvider` can reuse `CasAuthenticationToken` from cache when the PT is resubmitted. **60 seconds is not a CAS/Spring default.** Check:
- Does it enforce realm/service/tenant scoping? If the default cache key is solely the ticket ID, avoid sharing caches across trust contexts; consider namespaced wrappers or route isolation.
- Eviction when an account is locked/revoked or logged out per policy.
- Bounded TTL, max size, metrics, and fault handling. Avoid unbounded permanent caches.
- In multi-node deployments, Node A's local cache differs from Node B's; a PT already consumed at CAS on Node A will fail on Node B. Do not adopt a "distributed cache" while ignoring key scoping, expiration, and eviction requirements.

**Never call a cached setup "truly stateless":** there is no browser `HttpSession`, yet server-side cache state still exists with risks comparable to bearer tokens.

### 11.5. `SecurityFilterChain` for the API

~~~java
// DSL FRAGMENT: filter, manager, and service properties already initialized.
// Do not share with the web chain handling CAS browser login.
http
    .securityMatcher("/internal/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(
            org.springframework.security.config.http
                .SessionCreationPolicy.STATELESS
        )
    )
    .securityContext(context -> context
        .securityContextRepository(
            new org.springframework.security.web.context
                .NullSecurityContextRepository()
        )
    )
    .requestCache(cache -> cache.disable())
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .addFilterAt(apiFilter, CasAuthenticationFilter.class);
~~~

In a **two-chain** application, use explicit `@Order` and matchers; only `/internal/**` uses this session policy. The API needs an entry point returning **401 JSON** instead of redirecting to CAS login when a machine client lacks a PT; align security/CSRF config with the credential type (non-cookie) and HTTP methods without **disabling CSRF application-wide**. Account for state-mutating endpoints under `/internal/**`, CORS/mTLS/gateway, and replay controls.

### 11.6. Why Not Reuse One Provider/Web Filter and Flip `authenticateAllArtifacts` to `true`?

Because `authenticateAllArtifacts=true` lets the CAS filter accept tickets on **every URL matched by the chain**. If the web chain covers many endpoints, an attacker can try submitting a ticket to an unintended path and trick the app into validating under a different service URL.

Separating security chains and bean configs ensures:
- Browser callbacks use **stateful ST** with fixed `ServiceProperties.service`.
- APIs use **stateless PT** with approved target services and proxy validation.
- `HttpSessionSecurityContextRepository` and `NullSecurityContextRepository` are never mixed ambiguously.
- Ticket caches are never shared across tenants/IdPs with distinct trust anchors.
- Separate logs/metrics and distinct HTTP error responses remain clean.

## 12. Can a Cache Hit Affect Authorization?

Yes. When the cache holds `CasAuthenticationToken` with `GrantedAuthority` values and a local user's permissions change **after the first validation** while the cache entry is still live, a cache hit can return **stale** authorities unless the app reloads or re-checks them.

Example:

~~~text
T0  API validates PT-123 with CAS -> alice, APP_EXPORT_READ
T1  Cache stores authentication for PT-123, TTL 60s
T2  Admin disables alice or revokes APP_EXPORT_READ
T3  Client resends PT-123 (within TTL) -> cache hit
T4  If code inspects only cached authority -> risk of still ALLOWing
~~~

**Mitigation:**
- For sensitive permissions, perform **resource-level authorization** against current local user status and policies at request time.
- Implement cache invalidation when local accounts are revoked, switch tenants, unlink CAS identities, or change permissions.
- Use short TTLs and tight scoping; never treat TTL as a substitute for near-real-time revocation requirements.
- Never cache administrative privileges unboundedly; evaluate step-up re-authentication for sensitive actions.
- On a cache miss during a CAS outage, fail closed; never return stale user data from another request's session.

### 12.1. Ticket Cache Differs from User Profile Cache

- `StatelessTicketCache` stores **Authentication derived from a CAS ticket**.
- A user profile cache stores name/email/department and can refresh independently.
- A permission cache stores local permissions and needs dedicated invalidation/revalidation.
- The CAS ticket registry tracks issued/consumed ST/PTs on the CAS server.
- Clearing one cache does not automatically clear all related state stores.

### 12.2. Local Sessions Can Also Hold Stale Permissions

A stateful portal can likewise hold `Authentication`/authorities inside `HttpSession`. When an admin revokes permissions, the app must decide whether to invalidate sessions, reload permissions, or check the backend per request. Never claim stateful is bad and stateless is good: **both require revocation and authorization policies**, differing only in where the authentication artifact is stored.

## 13. CAS Outages, Caching, and Availability

| Situation | Stateful Portal | Stateless PT Without Cache | Stateless PT With Cache |
| --- | --- | --- | --- |
| CAS healthy, fresh credential | ST login succeeds. | Fresh PT validates. | Miss validates; hit uses verified auth. |
| CAS briefly unreachable after Portal login | Valid Portal session may continue per policy. | Cannot validate fresh PTs. | Cache hits may continue until TTL, if risk policy allows. |
| CAS outage before initial authentication | No new session created. | Cannot authenticate. | Cache miss cannot authenticate. |
| Ticket already consumed at CAS | Portal uses session cookie; never resends ST. | Old PT rejected. | Cached PT hit may still be accepted. |
| Another node lacks local state | Session store needs shared/sticky store or re-login. | Fresh PT validates; old PT fails. | Local cache miss fails for a PT already consumed on another node. |
| User just revoked | Session needs invalidation / authz recheck. | Fresh PT validation and local perms must check. | Cached auth must be evicted / permissions revalidated. |
| CAS SLO / logout occurs | Local session must receive logout/invalidation properly. | PGT/PT issuance/validation affected per CAS policy. | Cached PT is **not automatically cleared** without eviction integration. |

**Never claim a cache hit guarantees safety during a CAS outage.** It is purely a deliberate trade-off: the API accepts a previously verified token for its TTL even when the issuer is unreachable. Sensitive systems may demand failing closed immediately.

## 14. Service Scope, Realm, Proxy Chain, and Tenant

### 14.1. Service Binding in CAS

CAS issues an ST/PT for a specific `service`/`targetService`. On initial validation, CAS verifies that the service matches. With a stateless API cache, **cache hits skip calling CAS again**, so the service itself must prevent cached authentication from being accepted outside the approved service/route/tenant.

For example, the same PT could be copied to `/admin/export`; if the API keys its cache solely by ticket and skips resource authorization, privilege escalation occurs. Controls:
- Give the API clear service identifiers / canonical routes and isolate sensitive apps into distinct service scopes.
- Check local permissions, actions, resource ownership, and tenant **on every request**.
- Avoid a single global ticket cache across multiple target services or trust contexts.
- Never let browser/client-supplied URLs pick the CAS endpoint or `service` parameter.
- Consider mTLS/gateway identity for service-to-service traffic and modern audience/scope tokens where appropriate.

### 14.2. Multiple CAS Realms

~~~text
CAS realm A -> service portal-A -> alice -> local-user-A
CAS realm B -> service portal-B -> alice -> local-user-B
~~~

Identical usernames are not automatically the same account. With a stateless cache, enforce explicit scoping:

~~~text
IdentityKey = (trustedCasRealm, serviceScope, validatedUser)
CacheKey policy = (trustedCasRealm, serviceScope, ticketId)
~~~

This is a **design recommendation**, not a claim that `SpringCacheBasedTicketCache` creates this composite key by default. If your version cannot customize keys, deploy **separate cache instances/repositories per realm and service** to prevent collisions.

### 14.3. Permissions Do Not Come From a Ticket String

CAS tickets, usernames, and attributes verify **identity**. Permissions like `APP_REPORT_READ`, `APP_ORDER_APPROVE`, or tenant ownership must originate from an SP-managed store or an approved trust-mapping contract. Never let a `PT-ADMIN` ticket prefix or `groups=admin` attribute turn directly into Portal admin privileges.

### 14.4. Proxy Trust Chain

A backend may receive a PT used by an authorized intermediary proxy. CAS responses can include `cas:proxies`. The backend must enforce policies specifying allowed proxies, hop counts, and services—never letting an untrusted intermediary join the chain. CAS `/proxyValidate` and proxy-chain verification are distinct authentication requirements that must never be skipped just to cut latency.

## 15. Protecting Credentials and Reducing Replay Risk

### 15.1. Tickets Usually Travel in URLs

In classic CAS flows, browsers/clients send `?ticket=ST-...` or `?ticket=PT-...`. They risk leaking via:
- HTTP access logs, ingress, and reverse proxies.
- Application Performance Monitoring, traces, and dashboards.
- Browser history and `Referer` headers to external sites.
- Screenshots, bug reports, and chats containing URLs.
- HTTP caches/analytics capturing unsanitized queries.

**Mitigations:**
- Enforce HTTPS between CAS <-> Portal and mTLS/TLS for service-to-service when required by contract.
- Mask the `ticket` query parameter in logs; never put tickets into metric labels.
- Apply `Referrer-Policy: no-referrer` or a strict policy on callbacks, and load no third-party assets before redirecting cleanly.
- Never store ST/PT in `localStorage` or outbound redirect query parameters.
- Never accept tickets from user-controlled redirects lacking a service allowlist.
- Enforce input length/payload limits, rate limiting, and CSRF protection on cookie-backed browser actions.
- If using a ticket cache, enforce short TTLs, eviction, strict access control, and never write raw tickets to audit logs.

### 15.2. Replay: Distinguishing Two Windows

**CAS window:** an unvalidated PT can be stolen and used ahead of the intended recipient. CAS validates only once, so an attacker can consume the PT before the victim does.

**Local cache window:** once the API has validated a PT and cached the token, an attacker holding that same PT can replay it during the TTL to receive cached authentication. This is a **separate** risk not mitigated by CAS's single-use rule alone.

### 15.3. What Not to Do

- Enable `acceptAnyProxy=true` by default on sensitive backends.
- Disable TLS hostname/certificate verification to "reduce latency."
- Run a cache with no TTL/max size and no eviction on logout.
- Use raw tickets as audit identifiers in shared observability systems.
- Use `SessionCreationPolicy.STATELESS` to accidentally drop CSRF on a cookie-based web chain.
- Let clients pass arbitrary `casServer=...` or `service=...` parameters for validation, causing SSRF/trust confusion.
- Accept HTTP 200 from CAS without checking `cas:authenticationSuccess` vs. `cas:authenticationFailure`.
- Parse `PT-...` strings directly into usernames or permissions.
- Use one tenant's ST/PT to establish a session in another tenant.
- Let a cache hit bypass local authorization checks.
- Treat a PT cache like an OAuth access token with standardized scopes and revocation without designing for it.

## 16. Logout, Session Expiry, and Permission Revocation

### 16.1. Stateful Portal

~~~text
Browser -- POST /logout --> Portal invalidates HttpSession
                                 |
                                 +-- clear local SecurityContext
                                 +-- remove local session cookie
                                 +-- optional CAS Single Sign Out
~~~

If CAS Single Sign-Out is not implemented, the TGT/TGC at CAS may remain active, allowing the user to SSO back in with a fresh ST upon returning to a protected page.

### 16.2. Stateless API

There is no `HttpSession` to invalidate. You must:
1. Block/evict cache entries by ticket/identity/tenant when required.
2. Stop accepting compromised PTs or revoked users even before cache TTL expires when immediate revocation is mandated.
3. Track PGT/PT issuance and delegation at the front-end; when CAS logs out, understand whether cached PTs on the backend are automatically invalidated **or not**.
4. Enforce session and permission checks on every resource/request; never rely solely on unverified SLO notifications.
5. Never return `200 logout success` across an API cluster if another node's local cache still holds the ticket.

### 16.3. Absolute Session Lifetime vs. Cache Lifetime

- `HttpSession` has an idle timeout, plus optional absolute max age / forced re-authentication per policy.
- `StatelessTicketCache` has its own TTL, max size, and invalidation semantics.
- CAS TGT/TGC has its own lifetime.
- CAS ST/PTs are short-lived before validation and consumed immediately upon validation.
- Never take one TTL (e.g., a 20-minute session) and assume it governs all of the above.

## 17. Monitoring and Failure Analysis

| Symptom | Possible Cause | Investigation Path |
| --- | --- | --- |
| Web login succeeds then next request is anonymous | `SecurityContext` not persisted, session cookie lost, or `STATELESS` misconfigured. | Check `SecurityContextRepository`, CAS filter success path, cookies, and `SessionCreationPolicy`. |
| Browser redirected to CAS in a loop | Wrong service URL, filter callback mismatch, unsaved session, or CAS error. | Match canonical callback, masked access logs, and authentication traces. |
| First API PT call succeeds, second fails | Expected CAS single-use behavior, uncached, routed to another node, or TTL expired. | Check whether policy expects fresh PTs or caching + routing. |
| Old API PT accepted for 1 minute | Stateless authentication cache is active. | Assess bearer/replay risk and verify TTL matches policy. |
| One node allows, another node rejects | Unsynced local caches without shared store. | Use scoped shared cache or fresh PT per call. |
| CAS returns 200 yet login fails | XML `authenticationFailure` or unlinked user. | Check failure code, local `UserDetails`, and service. |
| API accepts a PT issued for a different service | Wrong dynamic service URL or cache scoping. | Inspect `ServiceAuthenticationDetailsSource` and `targetService` binding. |
| Admin revokes user yet API still accepts | Cached authorities not evicted/reloaded. | Enforce policy invalidation and local permission revalidation. |
| API returns 302 HTML to machine client | Web CAS entry point applied to wrong chain. | APIs should return 401/403 per protocol; separate entry points. |
| Web login saves session despite `STATELESS` on API | Two separate security chains—expected behavior. | Verify actual matchers and `@Order`. |
| API creates `JSESSIONID` despite `STATELESS` | Another filter, request cache, CSRF, or session config creates state. | Audit the entire filter chain, not just one annotation. |
| CAS server timeout hangs web/API | CAS validation client lacks timeouts / circuit breaker. | Set connect/read timeouts, fail closed, track latency metrics. |

### 17.1. Suggested Metrics

~~~text
cas_web_login_total{result,realm}
cas_web_session_created_total{realm}
cas_web_session_invalidated_total{reason}
cas_stateless_ticket_validation_total{result,realm}
cas_stateless_cache_hit_total{service}
cas_stateless_cache_miss_total{service}
cas_stateless_cache_eviction_total{reason}
cas_proxy_ticket_failure_total{reason}
cas_user_revocation_enforcement_total{mode}
cas_api_auth_latency_seconds{route_group}
~~~

These are **suggested metrics**, not built-in Spring Security defaults. Never put ST/PT, user IDs, emails, TGT/PGT, or session cookies into labels. If correlating audits, generate a random internal ID and never log raw credentials.

### 17.2. What Logs Should Record

- The **approved** CAS realm/service registration, never client-supplied URLs.
- Authentication mode: stateful web, stateless cache hit, or stateless CAS validation.
- Generic CAS validation result code; never log raw CAS XML or tickets.
- Local account status / permission decision **anonymized or encrypted** per audit policy.
- Cache age/TTL bucket and session store health.
- Consistent HTTP error classes (401 unauthenticated / 403 authenticated lacking permission / 5xx dependency failure).
- Retry behavior and ticket-reuse failure counts (count only, never log the ticket).

## 18. Integration Test Matrix

| ID | Test | Expected Outcome |
| --- | --- | --- |
| T01 | Unauthenticated browser GET on protected page. | Redirects to CAS login with canonical service URL. |
| T02 | CAS issues ST for exact service. | Callback receives ticket and calls `/serviceValidate` once. |
| T03 | CAS validation succeeds, local user active. | Portal establishes `Authentication` and session. |
| T04 | Subsequent web request with valid `JSESSIONID`. | Restores `Authentication`; never resends ST to CAS. |
| T05 | Replay old ST at callback. | CAS rejects; no new session created. |
| T06 | Web session expires. | Request loses local auth; may SSO for a fresh ST. |
| T07 | Local Portal logout while CAS TGC remains. | Local session destroyed; does not claim CAS logout. |
| T08 | Web session ID before vs. after CAS login. | Proper session fixation protection active. |
| T09 | Misconfigured cookie `Secure`/`HttpOnly`/`SameSite`. | Test catches it and verifies right settings. |
| T10 | Fresh stateless PT for matching target service. | API CAS validation succeeds; request-only `SecurityContext`. |
| T11 | Uncached stateless PT reused. | CAS returns `INVALID_TICKET` on second attempt. |
| T12 | Cached stateless PT within TTL. | Cache hit; CAS validate not called a second time. |
| T13 | Cache entry expires past TTL. | Old PT no longer authenticates; requires fresh ticket. |
| T14 | PT presented at different service URL than initial validation. | CAS rejects service mismatch. |
| T15 | Cached PT replayed to another endpoint/tenant. | Backend enforces scope/permissions; rejects cross-tenant. |
| T16 | PT leaked in URL/logs. | Redaction, incident response, and cache eviction triggered. |
| T17 | CAS outage prior to ticket validation. | Fails closed; does not authenticate. |
| T18 | CAS outage after API cache hit. | Behaves per documented cache policy and TTL. |
| T19 | API Node B lacks Node A's cache. | Old PT fails / requires fresh PT; no false success. |
| T20 | API with distributed cache. | TTL, namespace, atomic eviction, and tenant isolation hold. |
| T21 | User disabled while web session alive. | Session invalidated or current policy denies access. |
| T22 | User revoked while stateless cache entry alive. | Eviction/revalidation blocks sensitive permissions. |
| T23 | Proxy chain includes unauthorized proxy. | Backend rejects; `acceptAnyProxy` never enabled. |
| T24 | Client sends `casServer=attacker`. | Input ignored; calls only trusted CAS host. |
| T25 | Client sends `service` differing from contract. | Trusted service URL cannot be overridden. |
| T26 | API chain configured with web CAS redirect entry point. | Test catches 302 and enforces 401. |
| T27 | API chain `STATELESS` yet another filter creates a session. | Per-chain audit catches it and disables session features. |
| T28 | Web chain configured as `STATELESS`. | Test catches lost persistence / login loop. |
| T29 | CAS returns HTTP 200 with `authenticationFailure`. | Does not authenticate. |
| T30 | Proxy Ticket sent to `/serviceValidate`. | Rejected as an ST. |
| T31 | Service Ticket sent to API with PT-only policy. | Wrong ticket type rejected. |
| T32 | CAS proxy ticket expired before validation. | CAS rejects; API never bypasses. |
| T33 | CAS validation network timeout. | Never fabricates local `Authentication`; retries only with fresh PT. |
| T34 | Multi-realm sharing username `alice`. | No cross-mapping of local users/tenants. |
| T35 | API configures unbounded cache TTL. | QA policy fails, enforcing max TTL/size. |
| T36 | Same user holds web local session and API ticket cache. | Revocation clears both stores explicitly without assuming one-sided logout clears the other. |

### 18.1. Suggested Labs

**Lab A — Stateful Web:**
1. Run test CAS and Portal Servlet with `HttpSessionSecurityContextRepository`.
2. Log in and verify callback carries a fresh ST and CAS validation runs once.
3. Call `GET /me` repeatedly with the cookie, confirming CAS is not called again.
4. Perform local logout, verify `JSESSIONID` is invalidated, and revisit a protected page to observe SSO via a new ST.
5. Stop/disconnect the session store and observe the impact across nodes.

**Lab B — API Without `HttpSession`:**
1. Configure CAS proxy PGT/PT in an authorized test environment.
2. Expose a backend service with registered `targetService` using `Cas20ProxyTicketValidator`.
3. Disable caching: fresh PT succeeds, old PT fails.
4. Enable a short-TTL cache: fresh PT validates once, repeated requests within TTL hit cache.
5. Run across two API instances and inspect cache consistency and replay behavior.
6. Revoke the user or role and verify access is denied despite a cache hit.
7. Capture redacted metrics without ever capturing or logging raw tickets.

**Lab C — Threat Model:**
1. Simulate presenting a PT to another URL, service, tenant, and CAS realm.
2. Analyze where binding is checked by CAS (first call) vs. enforced by the API itself (on cache hits).
3. Shut down CAS and measure behavior of web sessions, fresh/miss PTs, and cached/hit PTs.
4. Choose TTL/eviction policies and evaluate whether a dedicated API access token should replace PT caching.

## 19. Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "CAS tickets are single-use so every web request must re-validate." | Replays rejected by CAS. | Stateful web stores local session; never reuse STs. |
| "`STATELESS` means the server holds zero state." | Overlooks CAS/PGT/identity caches and revocation. | Separate CAS, Portal session, and ticket cache states. |
| "Setting `STATELESS` automatically enables PT support." | API fails to validate CAS tickets or breaks authorization. | Wire CAS artifact processing, details source, proxy validator, and right chain. |
| "A cache hit proves CAS just verified the ticket." | Misunderstands freshness and revocation. | Log/bound cache TTL and treat as cached authentication. |
| "Caching PTs has no risk because PTs are one-time." | Token can be replayed throughout cache TTL. | Treat as bearer, use short TTL, TLS, and eviction. |
| "One cache shared by all tenants because tickets are unique." | Cross-realm/trust-scope mix-ups. | Namespaced/trust-isolated caches and authorization. |
| "Change service URL per request and validate." | Service confusion, SSRF, mismatches. | Trusted service config, route allowlists, and canonical hosts. |
| "Use `/serviceValidate` for proxy tickets." | CAS rejects or breaks profile behavior. | Use proxy validator and proxy trust policy. |
| "Enable `acceptAnyProxy` to avoid errors." | Accepts untrusted intermediary chains. | Named/trusted proxy policy. |
| "Once a user is authenticated, permissions stay valid forever." | Cache/session retains stale roles after revocation. | Per-request policy/revocation checks and invalidation. |
| "API has no `JSESSIONID` so there is no CSRF or browser risk." | API may still be called from browsers or leak URL credentials. | Threat-model actual credentials and cookies. |
| "Disable HTTPS checks because CAS is internal." | Credential/token exposure or spoofed servers. | Proper TLS truststore/mTLS. |
| "No response from CAS—grant role temporarily." | Authentication bypass. | Fail closed; retry only with a fresh ticket. |
| "Portal logout already cleared the API cache." | Cached PT stays alive. | Explicitly revoke both sessions and caches within scope. |
| "Declare `CasAuthenticationFilter` as `@Bean` and also call `addFilterAt`." | Filter can register twice. | Register only in `SecurityFilterChain` or disable servlet auto-registration. |

## 20. Pre-Production Checklist

- [ ] Classified browser vs. backend remoting callers and chose stateful vs. stateless per requirement.
- [ ] Web ST callback and CAS validation URLs are allowlisted, HTTPS, and strictly canonical.
- [ ] Web filter uses `CAS_STATEFUL_IDENTIFIER` on callback and persists `SecurityContext` in session.
- [ ] Stateful sessions enforce rotation, TTL, cookie attributes, CSRF, logout, and shared-store policies.
- [ ] API accepts CAS PTs only on approved routes and `targetService` values.
- [ ] `authenticateAllArtifacts` and `ServiceAuthenticationDetailsSource` are properly configured and scoped.
- [ ] API proxy validator calls `/proxyValidate` and enforces an allowed proxy-chain policy.
- [ ] `SessionCreationPolicy.STATELESS` / `NullSecurityContextRepository` applied strictly to the API filter chain.
- [ ] `NullStatelessTicketCache` is never mistaken for allowing CAS to re-validate consumed tickets.
- [ ] If `SpringCacheBasedTicketCache` is enabled, TTL, max size, eviction, multi-node, and realm scoping are proven.
- [ ] Cache hits are treated as reusing a cached credential rather than fresh CAS verification.
- [ ] Ticket leakage is controlled across URLs, logs, `Referer`, analytics, and tracing.
- [ ] CAS validation URL, service URL, and tenant are never taken from untrusted request parameters.
- [ ] Local account, permissions, and tenant resource authorization are checked per policy on every request.
- [ ] Session and ticket cache revocation plans cover disabled local accounts, CAS SLO, and incidents.
- [ ] CAS outage behavior is documented across web sessions, cache hits, cache misses, and fresh tickets.
- [ ] Web and API chains define proper matchers, ordering, and entry points; API machine clients receive 401/403.
- [ ] Proxy PGT/PTs are stored via secret management and never exposed to browsers.
- [ ] Tests T01–T36 or an equivalent suite pass in staging.
- [ ] All Spring examples reviewed against actual versions and dependencies upgraded for security fixes.

## Key Takeaways

> **Stateful CAS:** validate **ST once** -> store `Authentication` in **Portal `HttpSession`** -> subsequent requests use the session cookie. **Stateless CAS:** do not restore `Authentication` from `HttpSession`; clients present a **ticket/credential on every request**; Spring may use `StatelessTicketCache` to remember the **initial PT validation result**. That cache never makes a CAS ticket reusable at CAS, yet it turns the PT into a **bearer credential valid for the API cache's TTL**. Decisions around caching, scoping, TTL, eviction, and authorization are therefore security decisions, not merely performance tuning.

### Official Documentation

- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): stateful service tickets, stateless proxy tickets, `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource`, and `StatelessTicketCache`.
- [Spring Security 6.3.5 — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): stateful `/login/cas` callback, stateless ticket paths, principal identifiers, and filter semantics.
- [Spring Security 6.3.5 — CasAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): ticket validator, user details, cache, and provider key.
- [Spring Security 6.3.x — StatelessTicketCache Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/cas/authentication/StatelessTicketCache.html): cache storing `CasAuthenticationToken` by ticket for callers without `HttpSession`.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, `NullSecurityContextRepository`, `SessionCreationPolicy.STATELESS`, and session fixation.
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service-bound ST/PT valid for a single validation attempt, PGT, and `/proxyValidate`.
- [Apereo CAS — Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): TGT/TGC/ST and CAS protocol versions.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session fixation, and revocation.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential handling, throttling, and reauthentication.
