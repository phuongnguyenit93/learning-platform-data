# Managing Sessions, AuthnRequest, and Logout Mapping in a Multi-Node Cluster

> **Module:** Spring Security – federation · **Group:** Deployment and Operations. This Knowledge article focuses on operating a Java/Spring Security SAML 2.0 Service Provider (SP) when an application runs across **multiple JVMs/pods/nodes** behind a load balancer. Three distinct states must be managed separately yet consistently: **(1) the browser's HttpSession / Spring SecurityContext; (2) pending AuthnRequests awaiting a SAMLResponse and correlation data; (3) pending LogoutRequests awaiting a LogoutResponse along with the mapping from IdP identity/SessionIndex to local sessions that must be revoked**. Topics include Redis/Spring Session, browser cookies/SameSite, login CSRF, SAML Single Logout (SLO), replay protection, public ACS/SLO names behind a proxy, failover/rolling deploys, secret governance, and chaos testing. The Java 17 example at the end runs standalone yet **only simulates state**—it does not implement a real SAML signature verifier. Domains, identifiers, and endpoints in this article are illustrative.

## 1. A Typical Production Failure: Request Hits Node A, Callback Lands on Node B

Suppose a reporting application runs three pods `sp-a`, `sp-b`, and `sp-c` behind the public URL `https://reports.example.org`. At login initiation:

```text
Browser                    Ingress / LB                  SAML SP Cluster
   |                           |                                |
   | GET /saml2/authenticate/corp                            |
   |-------------------------->|---------------------> sp-a     |
   |                           |                      creates  |
   |                           |                 AuthnRequest R |
   |                           |                 saves in A's   |
   |                           |                 local session  |
   |<--------------------------|<--------------------- redirect |
   |                           |                                |
   | Browser visits IdP; IdP authenticates and sends Response   |
   |                           |                                |
   | POST /login/saml2/sso/corp with InResponseTo=R              |
   |-------------------------->|---------------------> sp-b     |
   |                           |                      tries to  |
   |                           |                      load R    |
   |                           |                 R not in B's   |
   |                           |                 local session  |
   |<--------------------------|<-------------------- SSO error |
```

The IdP signature may be valid and clocks accurate, yet Spring Security cannot find the `AuthnRequest` needed to correlate `InResponseTo` and `RelayState`. Switching backends between two HTTP requests is normal; a properly designed system must not depend on node A's local memory.

Another failure: a user has two browser sessions `S1` on node A and `S2` on node C. The IdP sends a `LogoutRequest` containing `SessionIndex=IX-123` to node B. If the handler merely calls `request.getSession(false).invalidate()`, it may **fail to terminate S1/S2**, because an IdP SLO callback can arrive **without a browser cookie**. When the app replies `LogoutResponse Success` while sessions remain active, SLO gives the illusion of completion while the user retains data access.

**Lesson goal:** Preserve state/correlation across multiple nodes **without dropping browser binding**; log out the exact set of sessions, and only after the `LogoutRequest` has been trusted and fully profile-checked.

## 2. Four Lifecycles That Must Not Be Merged into One

| Object | Primary identifier key | Where created? | When used? | When terminated? |
| --- | --- | --- | --- | --- |
| **Browser HttpSession** | Random server-generated session ID via `SESSION`/`JSESSIONID` cookie | Before/after login at SP | Session authentication and app state | Timeout, local logout, revocation, user disabled |
| **Pending AuthnRequest** | SAML request ID + unguessable `RelayState` + browser-flow binding | SP initiates login | Correlating SAMLResponse `InResponseTo` | One-time consume, TTL, cancel/expiry |
| **Pending RP LogoutRequest** | SAML LogoutRequest ID, optional RelayState + browser/logout transaction binding | SP initiates SLO | Checking `LogoutResponse@InResponseTo` and status | One-time consume, TTL, failure/timeout |
| **SAML session association** | Trusted IdP registration + NameID context + `SessionIndex` → local session IDs | After assertion authentication | IdP-initiated SLO/targeted revocation | Local session expiry, unlink, logout, deprovision |

**Fifth:** `SecurityContext` holds the authenticated principal/authorities, usually stored in HttpSession or an appropriate repository. It is **post-authentication state**, not a substitute for pending AuthnRequest or the logout index table.

### 2.1. Identifiers That Cannot Be Used Interchangeably

- **Browser session ID** is an application-managed secret (bearer session credential), **not** the SAML `SessionIndex`.
- **SAML SessionIndex** appears in `AuthnStatement` and `LogoutRequest`, issued by the IdP; it is not the local Redis session ID.
- **AuthnRequest ID** is the ID of the outbound SP request; `Response@InResponseTo` references this ID.
- **LogoutRequest ID** is the ID of the SLO request; `LogoutResponse@InResponseTo` references that ID.
- **RelayState** is opaque state passed through the browser, usable as a correlation hint. Never treat a browser-sent value as proof of HttpSession ownership.
- **NameID** has meaning only alongside its trusted IdP, format, and qualifiers; it may be transient or persistent per the IdP profile.
- **Registration ID / Entity ID** binds an SP integration to a specific IdP; never mix sessions across IdPs or tenants.

### 2.2. Invariants That Must Be Preserved

1. **Confidentiality:** session IDs, auth tokens, SAML assertions, credentials, and mappings never appear in logs.
2. **Integrity:** only a verified principal from a registered IdP may create a mapping.
3. **Correct association:** callbacks must never attach to a different browser or different request.
4. **One-time use:** AuthnRequests, LogoutRequests, and replay-sensitive response IDs are never accepted more than once.
5. **Bounded lifetime:** every pending request and mapping has a TTL/cleanup; never an unbounded cache.
6. **Multi-node visibility:** node B can reliably read state created by node A.
7. **Atomicity:** consuming state and creating/revoking sessions must avoid races.
8. **Revocation completeness:** SLO returns Success only when SP-side responsibilities have executed per policy.
9. **Failure behavior:** if cache/session store fails, fail closed for dependent functionality—never drop `InResponseTo` to "rescue" SSO.
10. **Isolation:** trusted issuers, tenants, NameID formats, SessionIndexes, and browser sessions never leak across RPs.

## 3. Recommended Overall Architecture

```text
                          Internet / Browser
                                 |
                                 v
                 TLS Ingress / Reverse Proxy
                 canonical https://reports.example.org
                                 |
                 +---------------+---------------+
                 |               |               |
               sp-a            sp-b            sp-c
           Spring Boot      Spring Boot      Spring Boot
           Security SAML2   Security SAML2   Security SAML2
                 |               |               |
                 +---------------+---------------+
                                 |
                 Centralized, protected state stores
                 +-------------------------------+
                 | Spring Session Redis / DB     |
                 |   HTTP session + SecurityCtx  |
                 |   pending AuthnRequest        |
                 |   pending LogoutRequest       |
                 +-------------------------------+
                                 |
                 +-------------------------------+
                 | SAML application indexes      |
                 |   (IdP, NameID, SessionIndex) |
                 |          -> sessionId set     |
                 |   sessionId -> association    |
                 |   replay IDs / completed SLO  |
                 +-------------------------------+
                                 |
                        SAML IdP / metadata
```

**Note:** the application indexes table is a **design you must actively implement if you want to log out multiple sessions by SessionIndex**; it does not appear automatically simply by enabling Spring Session Redis. Spring Security SAML2 provides SLO capabilities, but locating and terminating **all** sessions across devices/nodes must be **tested in practice** and may require custom validated mapping/revocation.

### 3.1. Sticky Sessions Are Not Equivalent to Distributed State

A load balancer can use affinity so the browser returns to node A. However:
- If node A restarts or is evicted before callback ⇒ request mapping is lost.
- Cross-site callbacks can lose the affinity cookie.
- Scale-in, failover, and rolling upgrades switch nodes.
- IdP-initiated SLO may arrive with no affinity cookie.
- Sessions on other devices live on other nodes and cannot all be terminated via the current browser session.

Sticky sessions are an **optimization/temporary mitigation**, not a guarantee for SAML correlation and global logout. Full HA/SLO requirements need shared state or a stateless design **with equivalent security binding** and distributed revocation.

### 3.2. Separate or Shared Redis?

A single Redis cluster can store Spring Session and domain SAML indexes with **separate namespaces and permissions**. You do not need a separate Redis per state type, but you do need least-privilege permissions, TTLs, replica/failover, eviction policies, monitoring, and redaction. Never run Redis `KEYS *` to "clear stuck sessions" in production.

## 4. SP-Initiated SSO: AuthnRequest Lifecycle in a Cluster

### 4.1. Normal Sequence

1. Browser hits `/saml2/authenticate/corp`.
2. `Saml2WebSsoAuthenticationRequestFilter` resolves the trusted `RelyingPartyRegistration`.
3. SP creates a `samlp:AuthnRequest` with a **unique unguessable ID**, `IssueInstant`, destination, and ACS details.
4. `Saml2AuthenticationRequestRepository` stores `AbstractSaml2AuthenticationRequest` along with correlation information.
5. Browser redirects/POSTs to the IdP via Redirect/POST binding with `SAMLRequest`/`RelayState` as configured.
6. IdP authenticates and issues a `SAMLResponse` whose `InResponseTo` references the AuthnRequest ID.
7. Browser POSTs the response to ACS `/login/saml2/sso/corp`.
8. `Saml2WebSsoAuthenticationFilter` / `Saml2AuthenticationTokenConverter` loads the pending AuthnRequest from the repository.
9. OpenSAML provider verifies trusted IdP signature, issuer, audience, recipient/destination, Conditions, bearer SubjectConfirmation, `InResponseTo`, replay, and profile checks.
10. On success, the pending request is consumed per policy; an authenticated SecurityContext and local session are created.
11. The SAML identity/sessionIndex→new session ID mapping is recorded after session fixation protection completes.
12. On failure, neither an authenticated SecurityContext nor a logout index link is created.

The APIs/filters above are Spring Security Servlet SAML2 components; for Spring Security 6.x/7.x, check release notes/Javadoc for exact methods.

### 4.2. Spring Default: Request in HttpSession

Spring Security documentation confirms the default is `HttpSessionSaml2AuthenticationRequestRepository`. If `HttpSession` is **per-node in-memory Tomcat**, node B cannot read an AuthnRequest saved on node A. But if Spring Session **replaces HttpSession with a Redis-backed session** properly, request state travels with the cookie and is shared across nodes.

```text
Browser cookie: SESSION = opaque-123
   |
   +--> sp-a stores AuthnRequest R in HttpSession
   |      Spring Session persists opaque-123 -> R in Redis
   |
   +--> IdP completes authentication
   |
   +--> sp-b receives browser cookie opaque-123
          Spring Session resolves opaque-123 from Redis
          AuthnRequest R found, then validates InResponseTo
```

This approach is usually preferred because it preserves **browser-session binding** inside the request repository rather than merely keeping a global map keyed by caller-supplied ID.

### 4.3. Spring Boot + Redis-Backed HttpSession

Dependency example with Spring Boot dependency management:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
  </dependency>
</dependencies>
```

Spring Boot configuration fragment example:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: none

spring:
  session:
    redis:
      namespace: reports:sessions
      flush-mode: on_save
  data:
    redis:
      host: redis.internal.example
      port: 6379
      ssl:
        enabled: true
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
```

**This is an operational fragment, not a ready-to-run configuration for all versions.** You must supply Redis credentials from a secret manager, TLS truststores for Redis/IdP, trusted metadata/signing credentials, network policy, complete `RelyingPartyRegistration`, service-provider entityID/ACS/SLO, and CSRF/session policies. Verify Spring Boot property names and dependencies for your exact version. `same-site: none` should only be selected after verifying browser callback binding and privacy policy; it requires `Secure` cookies and does not replace CSRF protection.

Spring Session replaces `HttpSession` with a Redis-backed repository via `springSessionRepositoryFilter`. It does **not** automatically turn every custom singleton map, local Caffeine cache, or application logout index into distributed state.

### 4.4. Validate Session Cookies in a Real Browser

Spring Session typically uses the `SESSION` cookie; other servlet/session configs may use `JSESSIONID`. **Do not hardcode** the cookie name in business logic. Using the Network tab in a **test environment**, verify the cookie is sent when the browser POSTs from the IdP to the ACS, including:

- Top-level cross-site POST from the IdP.
- Browser privacy restrictions and third-party-cookie policies.
- SameSite=Lax, Strict, and None.
- Cookie `Secure`/`HttpOnly`/Domain/Path.
- Cross-subdomain vs cross-origin deployment.
- Existing browser session vs new session.
- HTTPS offload at ingress and public Host/Proto.

For cross-site POSTs, `SameSite=Lax` **typically omits the cookie** in that context; browser defaults may have nuances. `SameSite=Strict` drops the cookie even more readily when returning from the IdP. `SameSite=None;Secure` supports cross-site use cases but introduces other CSRF considerations, so retain SAML response correlation, state, and browser/session safeguards.

## 5. Do Not "Fix" Missing AuthnRequests by Dropping Correlation

### 5.1. A Dangerous Approach

```text
Response arrives on node B
  AuthnRequest R not found
      |
      v
Developer disables InResponseTo check
  / accepts IdP-initiated style regardless of flow
      |
      v
Attacker can exploit unsolicited assertions / login CSRF
```

**Wrong in principle:** A SAMLResponse with a valid signature can still be a response that **this browser never requested**. Skipping pending-request validation lets an attacker try to inject an assertion from the attacker's account into a victim's session or perform unsolicited login if other controls are weak.

### 5.2. Looking Up by RelayState Alone Also Has Trade-Offs

Spring Security provides `CacheSaml2AuthenticationRequestRepository`, which caches AuthnRequests by `RelayState` instead of session in some setups. Spring Security docs **explicitly warn**: looking up by `RelayState` or `InResponseTo` without browser-session binding can lose a layer of defense against login fixation/CSRF. An attacker could initiate a valid SAML flow and trick the victim's browser into receiving that flow's callback.

If an architecture uses a distributed AuthnRequest cache outside HttpSession:

- `RelayState` must be strong random, opaque, and free of PII, arbitrary redirect URLs, or session IDs.
- Bind the state to the **browser/login transaction** via a session cookie or an independent mechanism with equivalent assurance.
- Correlate request ID, trusted registration/issuer, destination, browser binding, TTL, and one-time usage.
- Never load a request from an arbitrary browser-supplied `RelayState` without browser binding to create an authenticated session.
- Keep TTL short and consume atomically (non-atomic GET+DELETE is insufficient under races).
- Check target URLs for open redirects after login; never trust `RelayState` as an absolute redirect URI.
- When browsers block cookies, explore safe cookie deployment/flow changes rather than treating cache-only as a "magic fix."

### 5.3. Single AuthnRequest or Multiple Pending Requests per Session?

A user may open two tabs, start two logins concurrently, or switch registrations. If a repository/model holds only one pending AuthnRequest per session, the second flow can overwrite the first. Test actual Spring Security release and repository behavior. To support multiple flows, use a server-side map keyed by request ID **bound to the browser-session context**, cap pending flows/TTL, and consume atomically—never allow unbounded growth.

Never treat a request ID from a URL as authentication; it is solely a **correlation identifier** inside a validated message. An IdP-initiated SSO flow without a pending request is a separate profile requiring explicit allowlisting and replay/recipient controls, not a bypass for SP-initiated checks.

## 6. RelayState, InResponseTo, and Session Fixation

### 6.1. Constraints to Enforce

For request `R`:

```text
Pending:
  expectedRegistration = corp
  expectedIdP          = https://idp.example.org
  requestId            = _req-7432
  relayState           = opaque-strong-random
  originalBrowserFlow  = bound-to-session-S0
  expiresAt            = T+3min

Inbound Response:
  registration         = corp
  issuer               = expected trusted IdP
  inResponseTo         = _req-7432
  relayState           = opaque-strong-random
  browser session      = S0
  signature/audience/time/replay validated
```

**Matching `InResponseTo` does not replace validating signature, issuer, audience, bearer Recipient, and Conditions.** Conversely, a valid signature does not replace browser-flow correlation.

### 6.2. Session ID Changes After Login

Spring Security typically applies session fixation defense that changes the session ID upon login (Servlet `changeSessionId` or another strategy). Consequently:

```text
Before auth:
  SESSION = S0
  Pending AuthnRequest refers to flow S0

After successful auth:
  SESSION = S1
  SAML session index mapping MUST point to S1
  and should no longer point to obsolete S0
```

**Do not record the SAML logout index before the new session ID is finalized and leave it pointing to S0 forever.** Use `HttpSessionIdListener` or `SessionFixationProtectionEvent` to update mappings atomically and test across node switches. Never disable session fixation protection because the session index mapping lags behind.

### 6.3. Invalid Cookies or Session Expiry Mid-Flow

If the browser loses `SESSION` on callback or the session expires, the SP may not find the pending AuthnRequest. Under strict SP-initiated flow, **fail safely and start a fresh login**, rather than trusting a `RelayState` still sitting in shared cache as proof the user owned the original session. Avoid infinite auto-retry loops; the UI can prompt to log in again while logs record only safe correlation reason codes.

### 6.4. Races and One-Time Consumption

Two POSTs of the same SAMLResponse to nodes B/C can occur nearly simultaneously due to reloads, proxy retries, or replay attacks. The repository must ensure only one transaction consumes the AuthnRequest. Replay detection for signed Response/Assertion IDs is a separate layer; **do not rely solely on deleting pending state** if IdP-initiated flows could be permitted.

In Redis, use Lua scripts/transactions or suitable atomic operations to verify expected values and remove exactly once. Never use non-atomic `GET` followed by `DEL` to simulate a one-time guarantee. Eventual consistency/replica reads can cause duplicate acceptance.

## 7. Spring Security SAML2: Components and Where to Swap the Repository

### 7.1. AuthnRequest Repository

Components from Spring Security docs:

| Component | Role |
| --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Generates AuthnRequest before redirecting to IdP |
| `Saml2AuthenticationRequestRepository` | Saves and loads pending `AbstractSaml2AuthenticationRequest` |
| `HttpSessionSaml2AuthenticationRequestRepository` | Default: saves request in HttpSession |
| `CacheSaml2AuthenticationRequestRepository` | RelayState/cache repository in supported versions, with browser-binding caveat |
| `Saml2WebSsoAuthenticationFilter` | Processes ACS SAMLResponse |
| `Saml2AuthenticationTokenConverter` | Resolves registration, loads pending request context |
| `OpenSaml5AuthenticationProvider` | Verifies signed SAML/protocol in current release |
| `RelyingPartyRegistrationRepository` | Trusted IdP/SP entityID, keys, endpoints |

Example bean for Spring Security versions offering `CacheSaml2AuthenticationRequestRepository`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.saml2.provider.service.web
        .Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web
        .CacheSaml2AuthenticationRequestRepository;

@Bean
Saml2AuthenticationRequestRepository<?> authnRequestRepository() {
    // Fragment: ensure browser/session binding policy before choosing this!
    return new CacheSaml2AuthenticationRequestRepository();
}
```

**Warning:** this is a Spring configuration fragment, not a standalone compilable program. Class/method names may differ across Spring Security 6.x/7.x; check exact version docs. **Do not assume the cache repo's default factory provides Redis clustering and proven browser binding.** If you use Spring Session Redis and the default HttpSession, you usually **do not need** to switch to a RelayState cache.

### 7.2. A Minimal Conceptual SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .saml2Login(saml -> {})
        .saml2Logout(saml -> {})
        .build();
}
```

This fragment illustrates **enabling SAML login and SLO**; it omits full SAML registrations, trusted IdP signing certs, private signing keys for logout, Spring Session Redis, SLO SessionIndex indexing, CSRF policies, and real authorization. `saml2Logout` works properly only when IdP metadata/registration defines SingleLogoutService and required SP signing credentials. Do not call this a complete HA/SLO configuration.

### 7.3. Never Drop Trusted Verification to Diagnose Cluster Issues

When `InResponseTo` fails after deployment, check the session repository/cookies/Redis first. Never resolve it by:
- Disabling signature verification.
- Accepting `Response`s from any IdP.
- Promoting an untrusted certificate from `KeyInfo` as a verification credential.
- Dropping `InResponseTo`/Audience/Recipient/replay checks.
- Accepting browser-supplied `RelayState` as a trust anchor.
- Letting callbacks select issuer/registration/JWKS URLs dynamically.

Those are independent security controls and must stay intact even when one node cannot read state.

## 8. Single Logout in SAML: Two Independent Directions

### 8.1. RP-Initiated Logout

Example when a user clicks logout at the SP:

```text
Browser -> SP POST /logout (CSRF protected)
      |
      v
Saml2RelyingPartyInitiatedLogoutSuccessHandler
      |
      +-- invalidate local session / clear SecurityContext
      +-- resolve trusted IdP SLO endpoint
      +-- create/sign LogoutRequest with ID L1
      +-- persist pending LogoutRequest correlation
      |
      v
Browser / IdP receives SAML LogoutRequest
      |
      v
IdP returns signed LogoutResponse InResponseTo=L1
      |
      v
SP verifies signature, status, destination, issuer,
  InResponseTo & RelayState against L1
      |
      v
Complete / show logout result
```

Per the docs, Spring Security local logout handlers may invalidate the session **before** processing the outbound SAML LogoutRequest. The library provides `Saml2LogoutRequestRepository` to retain `Saml2LogoutRequest` for correlation when the IdP returns `LogoutResponse`. **If implementing a custom repository**, ensure the record persists with appropriate binding **after local session invalidation**, or use tested standard semantics; never assume storing in the old session and deleting that session keeps the correlation alive.

### 8.2. IdP-Initiated Logout (AP-Initiated)

The IdP sends `samlp:LogoutRequest` to the SP at an endpoint such as `/logout/saml2/slo`:

```xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_logout-request-18"
  Version="2.0"
  IssueInstant="2026-11-07T10:00:00Z"
  Destination="https://reports.example.org/logout/saml2/slo">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-person-9
  </saml:NameID>
  <samlp:SessionIndex>IX-123</samlp:SessionIndex>
</samlp:LogoutRequest>
```

This is **illustrative unsigned XML**, not for production or logout proof. Real messages must be processed per binding/signature/profile and trusted IdP metadata; Spring Security provides `Saml2LogoutRequestFilter` and `Saml2LogoutRequestValidator`. After verification, the SP locates local sessions matching `NameID` + `SessionIndex`, terminates them per policy, and returns a `samlp:LogoutResponse` with `InResponseTo` matching the request ID.

**Never** read a raw `SessionIndex` and immediately delete sessions. Query the mapping only after signature, issuer, destination, profile-appropriate audience/recipient, timing, and replay are verified. The SLO callback may arrive without a browser session cookie.

### 8.3. Spring Security Components

| Component | Purpose |
| --- | --- |
| `Saml2LogoutRequestFilter` | Receives/validates LogoutRequest from IdP |
| `Saml2LogoutRequestValidator` | Verifies request per SAML profile/trusted registration |
| `Saml2LogoutResponseResolver` | Creates/signs LogoutResponse when SP handles IdP request |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Initiates RP SLO after local logout |
| `Saml2LogoutRequestResolver` | Creates outbound SAML LogoutRequest |
| `Saml2LogoutRequestRepository` | Stores pending RP LogoutRequest to match inbound LogoutResponse |
| `HttpSessionLogoutRequestRepository` | Stores pending request in HttpSession per implementation/docs |
| `Saml2LogoutResponseFilter` | Receives IdP LogoutResponse |
| `Saml2LogoutResponseValidator` | Verifies response and InResponseTo/status |
| `RelyingPartyRegistration` | Trusted IdP SLO endpoint, verification/signing credentials |

In Servlet SAML2, defaults in docs use `POST /logout` for RP-initiated SLO and `/logout/saml2/slo` for IdP request/response, though routes are customizable. Never use an endpoint from unverified SAML XML to auto-configure a trusted IdP.

## 9. Pending LogoutRequest: Local Session Ended Yet Correlation Must Survive

### 9.1. Two Distinct Problems

**Issue A:** The SP deleted the browser session, so when the IdP sends `LogoutResponse` with `InResponseTo=L1`, the repository cannot find `L1`. This happens if custom state is misplaced or the browser cookie does not return.

**Issue B:** The SP finds a pending LogoutRequest in a global cache by `L1` but does not know which **browser/logout flow** the callback belongs to, leading to wrong redirects, results, or CSRF.

The solution requires **transactional correlation** rather than a bare map keyed by request ID.

### 9.2. Suggested Pending Record

```text
LogoutTransaction {
  requestId:          _logout-L1
  registrationId:     corp
  expectedIssuer:     https://idp.example.org/saml
  expectedDestination:https://reports.example.org/logout/saml2/slo
  opaqueRelayState:   highEntropyRandom
  browserBinding:     independent short-lived transaction secret
  localAccountRef:    RP-internal opaque ID (optional; minimized)
  createdAt:          UTC
  expiresAt:          UTC + short approved TTL
  consumedAt:         absent
}
```

Never store private signing keys in the pending record. Once the old HttpSession is invalidated, `browserBinding` must use a control with an independent lifecycle or server-protected/cryptographically bound state—never assume a deleted session cookie still exists. Every implementation must evaluate UX/threat models to prevent login/logout CSRF, open redirects, and information leaks.

### 9.3. Custom Repository Extension

Spring Security docs allow:

```java
http.saml2Logout(saml -> saml
    .logoutRequest(request -> request
        .logoutRequestRepository(
            myCustomLogoutRequestRepository)));
```

This fragment requires `HttpSecurity` and a `myCustomLogoutRequestRepository` bean implementing `Saml2LogoutRequestRepository` for your release. The repository must support **load/save/remove** per the filters' contract, TTLs, validator signed-issuer checks, one-time matching, and multi-node reads. Replacing this repository alone **does not** implement "IdP SessionIndex → all browser sessions"; that is a separate layer.

### 9.4. Repeated LogoutResponse

The IdP may retry the same LogoutResponse or an attacker may replay it. An already consumed LogoutRequest record must never approve a second response. Under concurrency, use atomic compare-and-delete or a consumed marker. On timeout, clean up the pending record; **never recreate an authenticated local session** just because SLO failed—local logout has already occurred.

### 9.5. SLO Can Fail Partially

RP-initiated SLO does not guarantee the IdP or other RPs logged out successfully. The IdP might omit LogoutResponse, return `PartialLogout`, or hit a network failure. A terminated local session must stay terminated; UI/auditing should distinguish **local logout success** from **federated SLO pending/partial/failure**. Never claim "logged out of all applications" without protocol outcome and operational evidence.

## 10. Mapping NameID/SessionIndex → Local Sessions

### 10.1. Why Redis-Backed HttpSession Alone Is Not Enough

Spring Session Redis lets any node read a session if it has the **session ID**. Yet IdP-initiated SLO usually provides only:

```text
Verified IdP entityID = https://idp.example.org/saml
Verified NameID        = opaque-person-9
Verified SessionIndex  = IX-123
SAML LogoutRequest ID  = _logout-X
```

It **does not send the app's Redis session ID** and may send no cookie. The SP needs a **secondary index** from trusted SAML identity/session identifiers to local sessions. This is application-specific data requiring controlled storage.

### 10.2. The Mapping Key Is Not Just SessionIndex

Do not write:

```text
index["IX-123"] -> sessionId
```

`SessionIndex` can collide across IdPs/tenants or across two different SAML sessions; an IdP may also reuse the same SessionIndex for multiple app sessions. The key should include:

```text
SamlSessionKey(
  rpRegistrationId,
  trustedIdpEntityId,
  nameIdFormat,
  nameQualifier,
  spNameQualifier,
  nameIdValue,
  sessionIndex
) -> Set<localHttpSessionIds>
```

Use exact IDP/NameID semantics confirmed by the IdP contract. If stable NameID or SessionIndex is unavailable, policy must define an explicit fallback. **Never** key by email/username/substring, which risks logging out the wrong user.

### 10.3. One SessionIndex Can Map to Multiple Local Sessions

A user can sign into the same IdP SSO session across:
- Browser A on a laptop.
- Browser B in a separate profile.
- Different tabs/sessions of the same browser per application.
- Mobile clients using front-channel browser SAML if the architecture supports it.

When the IdP sends a LogoutRequest specifying `SessionIndex=IX-123`, a complete SLO implementation may need to terminate **all local session IDs matching this index**, not only the request-scoped `HttpSession`. Conversely, never terminate other sessions like `IX-456` when logout targets IX-123 unless policy/profile permits a broader scope.

### 10.4. Association Cardinality and Reverse Mapping

```text
Forward:
  key(corp, IdP-A, opaque-person-9, IX-123)
      -> {S1, S2}

Reverse:
  S1 -> key(corp, IdP-A, opaque-person-9, IX-123)
  S2 -> key(corp, IdP-A, opaque-person-9, IX-123)

After S1 expires:
  forward -> {S2}
  reverse[S1] removed

After verified IdP SLO for IX-123:
  revoke S2
  forward key removed
  reverse[S2] removed
```

The reverse index enables cleanup when sessions expire, rotate, or are invalidated. With only a forward set, stale entries linger, increasing collisions or risking invalidating reused session IDs (session IDs must be random and non-reused).

### 10.5. Securing the Index Key

`NameID`, `SessionIndex`, and session IDs link identities to sessions. Avoid raw PII in Redis key names, metrics, and logs. Consider a **keyed HMAC index** using a server-controlled secret:

```text
indexKey = HMAC-SHA256(
  index-secret,
  registration + issuer + NameID qualifiers
  + NameID + SessionIndex
)
```

Do not use public `SHA-256(email)`; keyed HMAC limits dictionary attacks. Still, the HMAC output can remain pseudonymous personal data. Plan key lifecycle/migration during secret rotation so rotating the HMAC secret does not abruptly lose the ability to log out existing sessions.

### 10.6. Missing SessionIndex and Multiple SessionIndexes

A SAML `LogoutRequest` may contain multiple `SessionIndex` elements or none. When absent, the request can carry broader meaning under the SAML profile/IdP contract: logging out all sessions for that NameID from that issuer, or requiring a different policy. To prevent accidental mass logout:

1. Verify trusted IdP signature/issuer/NameID context.
2. Determine the semantics of the active SLO profile.
3. If indexes are present, target **only the valid declared indexes**.
4. If no index is present, perform broad logout only when contract/security policy allows; otherwise reject or return the appropriate status.
5. Never use a raw browser-supplied email to infer "logout all."
6. Cap max indexes/sessions to mitigate abuse and stale records; report partial failure if incomplete.

### 10.7. SessionIndex May Not Be Exposed Directly

Spring Security `Saml2AuthenticatedPrincipal` exposes NameID/attributes; whether `SessionIndex` is exposed directly depends on release/provider. If you must store SessionIndex, extract it from the **Assertion/AuthnStatement already verified by OpenSAML**, via an authentication converter/hook after validation—never parse raw `SAMLResponse` with regex/DOM and trust a `SessionIndex` inside an unsigned subtree.

When no SessionIndex exists in the assertion, never invent an arbitrary value and treat it as an IdP SessionIndex. Use a dedicated fallback/logout policy.

## 11. Spring Session Indexing vs SAML SessionIndex

Spring Session provides `FindByIndexNameSessionRepository` and `findByPrincipalName(...)` when supported by the repository/version. It looks up **HTTP sessions by Spring principal name** and is useful for whole-account revocation.

However, **principal name index ≠ SAML SessionIndex**. If a user holds two distinct IdP sessions:

```text
principal = "opaque-user-9"
SessionIndex X -> S1, S2
SessionIndex Y -> S3
```

`findByPrincipalName("opaque-user-9")` may return **S1, S2, S3** (if indexed), which cannot target X alone. If IdP SLO asks only for X and you delete all 3, that is **over-logout**; if you delete only the request-cookie session, that is **under-logout**.

### 11.1. Java Fragment Finding Sessions by Principal

```java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

// Fragment: repository is an indexed Spring Session repository.
Map<String, ? extends Session> sessions =
        repository.findByPrincipalName(
            "trusted-and-normalized-local-principal");
```

Do not use this code blindly for every IdP SLO. Verify the principal index is populated and maintained properly; docs note population may be the application's responsibility and differs by implementation. For targeted SAML logout, use the **NameID/SessionIndex** association and revoke only matched HTTP session IDs.

### 11.2. SessionRepository.deleteById and Caveats

```java
// Fragment: SAML LogoutRequest already verified and IDs found
// authorized for revocation for the specific IdP/NameID/SessionIndex.
for (String localSessionId : verifiedTargets) {
    springSessionRepository.deleteById(localSessionId);
}
```

This is a dangerous operation if `verifiedTargets` comes from an unverified token. Even after verification, confirm target sessions still exist and match the right identity/index, and handle concurrent session rotation, error/retry/idempotency, and auditing. In distributed caches, deletion propagation has latency; security-sensitive endpoints may need a revocation marker/epoch check.

### 11.3. Session Fixation and the Reverse Index

When a session ID changes `S0→S1` after authentication, you must:
- Move the reverse index from S0 to S1.
- Update the forward set removing S0 and adding S1 atomically.
- Avoid accidentally deleting S1 during a race with logout.
- If using Spring Session principal indexing, confirm the new index is updated.
- Test `changeSessionId`/`migrateSession` per servlet container/release.

Never place a raw session ID in an IdP-visible field such as `RelayState` or SAML `SessionIndex`. The mapping exists solely on the SP side.

## 12. Session/Store TTL, Eviction, and Cleanup Mechanisms

### 12.1. Different States Do Not Share One TTL

| State | Operational TTL to choose | After TTL expires |
| --- | --- | --- |
| Pending AuthnRequest | Short, sufficient for redirect/MFA per policy | Callbacks missing correlation are rejected |
| Pending LogoutRequest | Short yet sufficient for IdP SLO round-trip | Reject stale LogoutResponse; local logout remains complete |
| Authenticated HttpSession | Per app session security policy | Session invalid; indexes must be cleaned up |
| SAML mapping key | At least the active local session lifecycle, not infinite | Remove when session ends; reaper cleanup |
| Replay ledger | Covers full validity window/replay risk plus skew | Reject reused IDs within the risk window |
| SSO SessionIndex material | Only while serving logout/incident policy | Delete when no active references remain |
| Audit events | Per separate retention policy | Purge/aggregate, never retain raw PII |

**Never set "everything to 30 minutes"** leaving pending AuthnRequests alive for half an hour or expiring SessionIndex mappings after 3 minutes while HttpSessions live 8 hours. Do not pick one static number for all cases; align with IdP assertion TTL, SLO timing, and business policy.

### 12.2. Cleanup via Events and Reaper

- On local logout, delete the reverse entry and forward-set membership.
- On session timeout, listen to session destroyed/expired events if the backend emits them reliably.
- Run a **reconciliation/reaper job** for missed events, Redis failovers, and partial failures.
- On `changeSessionId`, transfer associations.
- When IdP SLO invalidates multiple sessions, delete sessions and index entries idempotently.
- Do not retain index memberships for nonexistent session IDs.
- Manage forward-set TTL while active members remain; never expire the key earlier than the longest-lived session.
- Never rely 100% on Redis keyspace notifications as a security guarantee; events can be disabled, lost, or delayed.

### 12.3. Eviction and Redis Failure

If Redis evicts keys under memory pressure, pending correlation can vanish and logins fail. This is an **availability issue**, never a reason to drop checks. Size Redis memory limits and eviction policies to prevent losing security state; monitor:
- evicted keys,
- pending request misses,
- session lookup latency,
- Redis replication lag,
- timeouts,
- connection saturation,
- stale SLO indexes,
- failed atomic operations.

If Redis is unavailable, the application should **reject callbacks requiring correlation** and fail safely, showing a retry message. Never fall back to a single-node in-memory request map without designing cluster security/consistency.

## 13. Race Conditions: Login, Logout, Locking, and Expiry

### 13.1. Duplicate Login Callbacks

```text
T1 sp-b reads pending AuthnRequest R
T2 sp-c reads same R
T1 verifies and creates session S1
T2 verifies and creates session S2

Unsafe result: same signed SAMLResponse accepted twice.

Expected:
  only one atomic consume of R succeeds,
  replay ledger rejects duplicate signed IDs,
  second request cannot create new authenticated session.
```

Atomic consume must be guarded by request ID, trusted registration, and expected browser-flow binding. A plain `GET` then `DEL` race is insufficient.

### 13.2. Concurrent Login and IdP SLO

```text
T1 login callback authenticated, prepares S1 mapping IX-X
T2 IdP LogoutRequest for IX-X arrives, revokes all known sessions
T1 commits S1 after logout -> user appears logged in again
```

To prevent a **session resurrection race**, consider a short-lived revocation marker/generation for the (trusted IdP, NameID, SessionIndex) association. The login commit checks the current generation or forced reauthentication policy before publishing S1. Logout increments the generation atomically, invalidates existing sessions, and stale login commits are rejected or revalidated. This behavior is **application architecture**, not an automatic Spring Session Redis feature.

### 13.3. Logout and Session ID Rotation

T1 creates authenticated session `S1`; T2 still sees old `S0`. If the mapping update is non-atomic, SLO might revoke S0 only while S1 survives. Use a transaction/Lua script to update forward/reverse mappings in one logical operation, or store a stable local session entity with generation-aware ID mapping.

### 13.4. Repeated IdP LogoutRequest

Replaying SLO request ID `L1` must not revoke a new session created later for the same account. Maintain a replay ledger keyed by verified IdP/LogoutRequest ID with TTL and processing status. For a duplicate request, return a protocol-appropriate result or reject per policy, but **never reinterpret an old L1 as a fresh instruction to terminate future sessions**.

### 13.5. Partial DB/Redis Failures

If session deletion succeeds while the index update fails, the reaper should repair it. If the index update succeeds while deletion fails, the session may remain live: **do not respond with unconditional Success** when security policy mandates revocation. Use idempotent jobs/retries, metrics, and documented SLO status semantics. For sensitive apps, a revocation epoch checked on every protected request closes the window even before physical deletion finishes.

## 14. Load Balancer, Cookies, and Public URL Consistency

### 14.1. Public URLs Must Match Across All Nodes

Suppose the IdP receives an AuthnRequest containing:

```text
AssertionConsumerServiceURL:
  https://reports.example.org/login/saml2/sso/corp

SP entityID:
  https://reports.example.org/saml2/service-provider-metadata/corp

SingleLogoutService:
  https://reports.example.org/logout/saml2/slo
```

Never let `sp-a` advertise `http://10.1.1.11:8080/...` and `sp-b` advertise `http://10.1.1.12:8080/...` due to proxy TLS termination or forwarded-header misconfiguration. The IdP will sign/redirect to inconsistent endpoints and Spring `Destination`/`Recipient` validators may reject.

### 14.2. Forwarded Headers

Spring Boot provides `server.forward-headers-strategy` to process reverse proxy headers depending on deployment. Trust `X-Forwarded-Proto`/`X-Forwarded-Host`/`Forwarded` **only from an authenticated ingress**, and strip malicious client-supplied headers. If the app trusts HTTP headers sent by an Internet user, an attacker can corrupt recipient, ACS URL, and redirect checks.

### 14.3. Cookie Domain/Path

If the app's public path is `/reports` while its internal context path is `/`, a cookie path mismatch can prevent the browser from sending the session cookie to `/login/saml2/sso/corp`. Inspect actual browser requests/cookie attributes rather than looking only at server config. Cookie names may also change (`SESSION` vs `JSESSIONID`) after Spring Session integration.

### 14.4. IdP Callbacks Do Not Always Carry Browser Cookies

In particular, IdP-initiated SLO can be delivered via iframe/front-channel where browser privacy policies and SameSite rules block cookies. **Do not design IdP SLO around `request.getSession()`** to find all logged-in users. Validate the IdP request, query the server-side SAML session index, and revoke the targeted sessions.

## 15. Signatures, Certificates, and Metadata in a Cluster

### 15.1. Every Node Must Share the Same Trust Model

- Same `RelyingPartyRegistration` (entityID, IdP entityID, ACS/SLO endpoints, bindings).
- Same trusted IdP signing verification keys, with controlled old+new overlap during rollovers.
- Same SP private signing key or key service to sign AuthnRequest/LogoutRequest per registration, unless the profile supports multiple keys and matching metadata.
- Same SP decryption credentials when encrypted assertions are used; no node should be able to decrypt while another cannot.
- Same accepted clock skew policy, replay semantics, and authn request repository configuration.
- Versioned configuration with a rollout/rollback plan so node A does not accept issuer B while node C rejects it.
- Secret keys and certificates kept in a secret manager, never in Git, images, logs, or exceptions.

### 15.2. Signing Certificate Rollover During Rolling Deploys

A request emitted by node A using SP signing key v1 whose callback hits node B configured solely with v2 can cause verification/trust or logout flow mismatches depending on IdP metadata and SP profile. Maintain explicit overlap/vintage tagging, verify signing credential versions on every node, and coordinate IdP metadata publication. Never trust a certificate inside SAMLResponse `KeyInfo` to "patch over" stale trusted keys.

### 15.3. IdP Metadata Refresh

If each node refreshes metadata independently without sharing a snapshot, trusted keys/endpoints can drift. Choose a controlled config versioning/cache refresh strategy. Changing an SLO endpoint can break pending logout transactions; retain outbound request contexts long enough to validate inbound old responses under the right issuer/destination policy during transitions.

## 16. Java 17: Simulating Shared State Between Two Nodes and Targeted SLO

This example creates a **shared in-memory state object** to simulate a Redis cluster. Two logical nodes A/B share the **same store instance**, so node A can create a pending AuthnRequest and node B processes the callback. The program also verifies:
- Rejecting callbacks with the wrong browser cookie or wrong RelayState.
- Rejecting reuse of an already consumed AuthnRequest.
- Rejecting expired pending AuthnRequests.
- Mapping (registration, issuer, NameID, SessionIndex) → **set of local session IDs**.
- **Verified** IdP SLO terminates only sessions with the matching SessionIndex, keeping other session indexes alive.
- RP SLO deletes the local session immediately, yet keeps the **pending LogoutRequest transaction independently** so an IdP callback hitting another node still matches and consumes once.
- Rejecting wrong browser-logout bindings and replayed LogoutResponses.

**Crucial limitation:** the boolean `verifiedBySamlProvider` is **test-supplied data simulating a trusted framework**; it is never a value clients may send. The code does not parse XML, verify IdP signatures, check assertion Audience/Recipient/InResponseTo/time/replay, issue cookies, connect to Redis, or use TLS or atomic Redis Lua scripts. `HashMap` is not thread-safe and does not replace a production cluster repository.

Save as `SamlClusterStateDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SamlClusterStateDemo {

    enum Decision {
        ACCEPT, REJECT_MISSING,
        REJECT_BINDING, REJECT_EXPIRED, REJECT_UNVERIFIED
    }

    record Identity(
            String registration, String issuer,
            String nameId, String sessionIndex) {}

    record PendingLogin(
            String requestId, String relayState,
            String browserSession, String registration,
            Instant expiresAt) {}

    record PendingLogout(
            String requestId, String relayState,
            String browserBinding, Instant expiresAt) {}

    static final class SharedStore {
        private final Map<String, PendingLogin> logins =
                new HashMap<>();
        private final Map<String, PendingLogout> logouts =
                new HashMap<>();
        private final Map<String, Identity> sessions =
                new HashMap<>();
        private final Map<Identity, Set<String>> index =
                new HashMap<>();

        void beginLogin(String requestId, String relayState,
                String browserSession, String registration,
                Instant expiresAt) {
            logins.put(requestId, new PendingLogin(
                requestId, relayState, browserSession,
                registration, expiresAt));
        }

        Decision completeLogin(
                String requestId, String relayState,
                String browserSession, Identity identity,
                Instant now, boolean verifiedBySamlProvider) {

            if (!verifiedBySamlProvider) {
                return Decision.REJECT_UNVERIFIED;
            }
            PendingLogin p = logins.get(requestId);
            if (p == null) {
                return Decision.REJECT_MISSING;
            }
            if (!now.isBefore(p.expiresAt())) {
                logins.remove(requestId);
                return Decision.REJECT_EXPIRED;
            }
            if (!p.relayState().equals(relayState)
                    || !p.browserSession().equals(browserSession)
                    || !p.registration().equals(
                        identity.registration())) {
                return Decision.REJECT_BINDING;
            }
            logins.remove(requestId);
            sessions.put(browserSession, identity);
            index.computeIfAbsent(identity,
                    ignored -> new HashSet<>())
                    .add(browserSession);
            return Decision.ACCEPT;
        }

        boolean sessionAlive(String localId) {
            return sessions.containsKey(localId);
        }

        void deleteSession(String localId) {
            Identity key = sessions.remove(localId);
            if (key == null) {
                return;
            }
            Set<String> ids = index.get(key);
            if (ids != null) {
                ids.remove(localId);
                if (ids.isEmpty()) {
                    index.remove(key);
                }
            }
        }

        int idpInitiatedLogout(
                Identity verifiedIdentity,
                boolean verifiedBySamlProvider) {
            if (!verifiedBySamlProvider) {
                return 0;
            }
            List<String> targets = new ArrayList<>(
                index.getOrDefault(
                    verifiedIdentity, Set.of()));
            for (String id : targets) {
                deleteSession(id);
            }
            return targets.size();
        }

        void beginRpLogout(
                String localSession, String requestId,
                String relayState, String browserBinding,
                Instant expiresAt) {
            if (!sessionAlive(localSession)) {
                throw new IllegalStateException(
                    "Active session required");
            }
            deleteSession(localSession);
            logouts.put(requestId, new PendingLogout(
                requestId, relayState,
                browserBinding, expiresAt));
        }

        Decision completeRpLogoutResponse(
                String responseInResponseTo,
                String relayState, String browserBinding,
                Instant now, boolean verifiedBySamlProvider) {
            if (!verifiedBySamlProvider) {
                return Decision.REJECT_UNVERIFIED;
            }
            PendingLogout p = logouts.get(responseInResponseTo);
            if (p == null) {
                return Decision.REJECT_MISSING;
            }
            if (!now.isBefore(p.expiresAt())) {
                logouts.remove(responseInResponseTo);
                return Decision.REJECT_EXPIRED;
            }
            if (!p.relayState().equals(relayState)
                    || !p.browserBinding().equals(browserBinding)) {
                return Decision.REJECT_BINDING;
            }
            logouts.remove(responseInResponseTo);
            return Decision.ACCEPT;
        }
    }

    static final class Node {
        final String name;
        final SharedStore store;

        Node(String name, SharedStore store) {
            this.name = name;
            this.store = store;
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        SharedStore shared = new SharedStore();
        Node nodeA = new Node("sp-a", shared);
        Node nodeB = new Node("sp-b", shared);

        Identity ix1 = new Identity("corp",
            "https://idp.example.org", "name-9", "IX-1");
        Identity ix2 = new Identity("corp",
            "https://idp.example.org", "name-9", "IX-2");

        nodeA.store.beginLogin(
            "R1", "relay-1", "browser-A",
            "corp", now.plusSeconds(120));
        System.out.println("Cross-node AuthnRequest: " +
            nodeB.store.completeLogin(
                "R1", "relay-1", "browser-A",
                ix1, now.plusSeconds(5), true));
        System.out.println("Replay AuthnRequest: " +
            nodeA.store.completeLogin(
                "R1", "relay-1", "browser-A",
                ix1, now.plusSeconds(6), true));

        nodeA.store.beginLogin(
            "R2", "relay-2", "browser-B",
            "corp", now.plusSeconds(120));
        System.out.println("Wrong browser binding: " +
            nodeB.store.completeLogin(
                "R2", "relay-2", "browser-X",
                ix1, now.plusSeconds(5), true));
        System.out.println("Wrong RelayState: " +
            nodeB.store.completeLogin(
                "R2", "wrong-relay", "browser-B",
                ix1, now.plusSeconds(6), true));
        System.out.println("Correct callback still works: " +
            nodeB.store.completeLogin(
                "R2", "relay-2", "browser-B",
                ix1, now.plusSeconds(7), true));

        nodeA.store.beginLogin(
            "OLD", "relay-old", "browser-X",
            "corp", now.plusSeconds(3));
        System.out.println("Expired pending request: " +
            nodeB.store.completeLogin(
                "OLD", "relay-old", "browser-X",
                ix1, now.plusSeconds(4), true));

        nodeA.store.beginLogin(
            "R3", "relay-3", "browser-C",
            "corp", now.plusSeconds(120));
        if (nodeB.store.completeLogin(
                "R3", "relay-3", "browser-C",
                ix2, now.plusSeconds(7), true)
                != Decision.ACCEPT) {
            throw new IllegalStateException(
                "Test login setup failed");
        }

        System.out.println("Unverified IdP SLO revoked: " +
            nodeB.store.idpInitiatedLogout(ix1, false));
        System.out.println("Verified SLO IX-1 revoked: " +
            nodeB.store.idpInitiatedLogout(ix1, true));
        System.out.println("Different SessionIndex remains: " +
            nodeA.store.sessionAlive("browser-C"));

        Identity foreign = new Identity("corp",
            "https://other-idp.example.org", "name-9", "IX-2");
        System.out.println("Foreign issuer revokes: " +
            nodeB.store.idpInitiatedLogout(foreign, true));

        nodeA.store.beginRpLogout(
            "browser-C", "L1", "logout-relay",
            "browser-transaction", now.plusSeconds(120));
        System.out.println("RP logout removed local session: " +
            !nodeB.store.sessionAlive("browser-C"));
        System.out.println("Wrong LogoutResponse binding: " +
            nodeB.store.completeRpLogoutResponse(
                "L1", "logout-relay", "other-browser",
                now.plusSeconds(10), true));
        System.out.println("Cross-node LogoutResponse: " +
            nodeB.store.completeRpLogoutResponse(
                "L1", "logout-relay", "browser-transaction",
                now.plusSeconds(11), true));
        System.out.println("Replay LogoutResponse: " +
            nodeA.store.completeRpLogoutResponse(
                "L1", "logout-relay", "browser-transaction",
                now.plusSeconds(12), true));
    }
}
```

Run with JDK 17+:

```bash
javac SamlClusterStateDemo.java
java SamlClusterStateDemo
```

**Exact** stdout:

```text
Cross-node AuthnRequest: ACCEPT
Replay AuthnRequest: REJECT_MISSING
Wrong browser binding: REJECT_BINDING
Wrong RelayState: REJECT_BINDING
Correct callback still works: ACCEPT
Expired pending request: REJECT_EXPIRED
Unverified IdP SLO revoked: 0
Verified SLO IX-1 revoked: 2
Different SessionIndex remains: true
Foreign issuer revokes: 0
RP logout removed local session: true
Wrong LogoutResponse binding: REJECT_BINDING
Cross-node LogoutResponse: ACCEPT
Replay LogoutResponse: REJECT_MISSING
```

### 16.1. Explaining the Results

- `sp-a` stores pending `R1`, `sp-b` reads the same shared store and accepts the valid callback → `ACCEPT`. With two separate local HashMaps, this case fails.
- `R1` is removed after acceptance → next attempt yields `REJECT_MISSING`. Production also requires a replay ledger on SAML Response/Assertion IDs.
- Browser `X` cannot use browser `B`'s pending request even knowing `R2`/`RelayState`; `REJECT_BINDING`.
- Wrong RelayState also rejects, without consuming pending `R2`, so the legitimate callback can still succeed. Production needs rate limiting to deter probing.
- `OLD` has a short expiry and is rejected; never extend TTLs indefinitely.
- `IX-1` has **two local sessions** A/B; verified IdP SLO targets both sessions accurately without terminating IX-2.
- A forged LogoutRequest cannot revoke sessions; the demo uses a simulated trusted boolean to represent this gate.
- An SLO request from another issuer, even with the same NameID, does not revoke the real issuer's session.
- RP logout deleted local session C; pending `L1` remains in a **separate state map**, allowing node B to validate the subsequent LogoutResponse.
- Wrong browser binding does not consume `L1`; the valid callback succeeds; replaying the callback rejects.

### 16.2. Sample Code Limitations

1. Test-supplied `verifiedBySamlProvider` is not real crypto; production **never accepts that boolean over HTTP**. It must come from a trusted, successfully validated SAML response/request.
2. `SharedStore` is a single-JVM HashMap—not thread-safe, lacking atomic Redis operations or background TTL cleanup.
3. The SAML identity key contains only registration/issuer/NameID/SessionIndex; production needs NameID format/qualifiers, tenant, and trusted subject context.
4. Browser binding in the demo is a plain string; production uses a cookie/session-bound high-entropy secret or another approved strong mechanism.
5. Demo session IDs do not rotate after login; production must handle session fixation/ID rotation.
6. No verification of XML signatures, timestamps, Destination, AudienceRestriction, Recipient, InResponseTo, or LogoutResponse status/replay.
7. `completeLogin` assumes the verified IdP already matched Response `InResponseTo` against `requestId`; production must **actually verify this** inside the OpenSAML provider.
8. No transactions/locks, unique keys, or generation-based revocation guards.
9. No distributed session storage, real Redis `SessionRepository`, encryption at rest, or secret management.
10. Do not adopt demo code as a SAML login/logout implementation; use Spring Security providers/filters with mapping code behind the trust boundary.
11. Does not prove full global logout across all devices; that must be tested with a live IdP, browsers, and Spring Session Redis.
12. Does not handle IdP LogoutRequests lacking `SessionIndex` or containing multiple SessionIndexes; production requires dedicated policies.

## 17. Multi-Node AuthnRequest Test Suite

| ID | Scenario | Expected |
| --- | --- | --- |
| AUTH-01 | Start login on node A, ACS hits node B with same browser cookie | Pending request found, SSO passes |
| AUTH-02 | Start on A, node A restarts, ACS hits C | Passes if shared state has not expired |
| AUTH-03 | Redis session state unreadable | Reject callback, never skip InResponseTo |
| AUTH-04 | `SESSION` cookie omitted on cross-site POST | Reject per strict correlation or apply approved browser-binding policy |
| AUTH-05 | Client sends valid InResponseTo but different browser session | Reject |
| AUTH-06 | Same RelayState but altered InResponseTo | Reject |
| AUTH-07 | Same InResponseTo but wrong registration/issuer | Reject |
| AUTH-08 | Pending request expired | Reject, create no SecurityContext |
| AUTH-09 | Duplicate valid SAMLResponse sent to B and C | Only first accepted; replay rejected |
| AUTH-10 | Two tabs start two logins in the same browser session | Behavior matches repository policy, no dangerous silent overwrite |
| AUTH-11 | Browser times out before callback | Restart login, never fail-open |
| AUTH-12 | Valid signature but wrong Audience | Reject |
| AUTH-13 | Valid signature but wrong ACS Recipient | Reject |
| AUTH-14 | Valid response from untrusted IdP | Reject |
| AUTH-15 | IdP-initiated unsolicited response when SP allows SP-initiated only | Reject |
| AUTH-16 | SameSite=Strict drops cookie | Test cross-site callback, never drop binding |
| AUTH-17 | SameSite=None;Secure + CSRF/correlation | Browser flow passes without creating login CSRF |
| AUTH-18 | Session fixation rotates ID after login | New session indexed, old association removed |
| AUTH-19 | Nodes A/B hold differing RelyingPartyRegistration versions | Canary fails, rollout gated |
| AUTH-20 | Redis eviction drops pending request | Fail closed, monitor evictions |
| AUTH-21 | Callback on wrong public hostname/proto | Reject wrong recipient/destination, fix proxy |
| AUTH-22 | User clicks login twice rapidly | No duplicate unexpected accounts/sessions |
| AUTH-23 | Redis replica lag when reading request | Never accept stale/replayed requests |
| AUTH-24 | RelayState holds attacker redirect URL | Never perform arbitrary redirect |
| AUTH-25 | Signature altered after signing | Rejected for signature, does not count as correlation test |
| AUTH-26 | Protocol verification fails | Do not record logout index/session association |
| AUTH-27 | Pending request created with unbounded TTL | Security QA FAIL |
| AUTH-28 | Request cache keyed only by RelayState with no browser binding | Security QA FAIL for strict SP-initiated flow |
| AUTH-29 | Old-version node parses newly serialized session object | Version compatibility test, never silently bypass |
| AUTH-30 | Browser persistent cookie while backend session expired | Reject, no ghost session |

### 17.1. Standard Test Fixture

Every integration test needs a trusted test IdP signing key, fresh signed SAMLResponse, valid `Conditions`/bearer `SubjectConfirmationData`, matching `InResponseTo`, and real browser cookies when testing strict session repositories. Modifying timestamps, NameID, or request IDs in XML after signing produces signature errors rather than testing the request repository.

### 17.2. Verify Destinations Rather Than HTTP Codes Alone

SAML login may 302-redirect to success or a login error; verify:
- Authenticated `SecurityContext` / principal is accurate after callback.
- New session ID if session fixation protection is active.
- Pending request consumed exactly once.
- Right local session is indexed to the IdP session.
- No session created on failed callback.
- Protected endpoint access succeeds with the browser cookie.
- No raw SAMLResponse/NameID/SessionIndex leaked in logs.

## 18. Multi-Node Single Logout Test Suite

| ID | Scenario | Expected |
| --- | --- | --- |
| SLO-01 | RP POST logout on node A, IdP LogoutResponse hits B | Correlation and status handled across nodes |
| SLO-02 | RP local session invalidated before LogoutResponse | Pending logout transaction still resolvable per design |
| SLO-03 | LogoutResponse InResponseTo mismatches pending LogoutRequest | Reject |
| SLO-04 | LogoutResponse RelayState wrong/missing against required binding | Reject per profile |
| SLO-05 | Duplicate LogoutResponse after successful processing | Reject/idempotent response, never resurrect login |
| SLO-06 | LogoutResponse signature from unknown IdP | Reject |
| SLO-07 | Signed IdP SLO, NameID/SessionIndex match two sessions on nodes A/C | Both sessions revoked |
| SLO-08 | IdP SLO targets IX-A while IX-B exists | IX-B remains unless policy is broader |
| SLO-09 | Identical SessionIndex string from another IdP | No cross-issuer revocation |
| SLO-10 | Identical NameID string from tenant B | No cross-tenant revocation |
| SLO-11 | IdP SLO callback with no browser cookie | Server-side mapping handles it |
| SLO-12 | IdP request has no SessionIndex | Apply reviewed broad/strict policy, never guess |
| SLO-13 | IdP request has multiple SessionIndex entries | Validate then revoke only associated indexes |
| SLO-14 | IdP request has unverified signature | Zero sessions deleted |
| SLO-15 | IdP request has duplicate Request ID | Replay rejected; no future session deletion |
| SLO-16 | Session S1 expired while forward index stale | Reaper/reconciliation removes stale refs |
| SLO-17 | Session ID S0 rotated to S1 at login | Index targets S1, not S0 |
| SLO-18 | SLO races fresh login for the same IX | Revocation marker prevents session resurrection |
| SLO-19 | Redis partial deletion failure | Retry/idempotency and honest status, no false Success |
| SLO-20 | Logout request expires without IdP response | Local logout remains effective, pending cleaned |
| SLO-21 | IdP returns PartialLogout status | Show/audit partial, do not claim global SLO |
| SLO-22 | Browser blocks third-party cookies | IdP-initiated SLO does not rely on browser cookies |
| SLO-23 | Session in another browser/device shares IX | Scoped per verified SAML IX mapping |
| SLO-24 | Session shares username but has different IdP session | No accidental blanket deletion |
| SLO-25 | Mapped HttpSession missing from store | Safe cleanup, no extra deletions |
| SLO-26 | `sessionRepository.deleteById` hits stale ID | Idempotent, verify state/generation |
| SLO-27 | Account disabled/locked during SLO | Status/revocation applies, no re-login via race |
| SLO-28 | SAML NameID is transient, mapping changed | Only verified current association can be revoked |
| SLO-29 | Signing key rotates during pending LogoutRequest | Trusted old/new rollover policy tested |
| SLO-30 | IdP LogoutResponse shows success while SP session remains live | QA FAIL |
| SLO-31 | Local logout without SLO | Only local session ended; do not claim IdP logout |
| SLO-32 | User reauthenticates after SLO | New session established only after fresh trusted login |
| SLO-33 | IdP LogoutRequest sent simultaneously from different regions | Idempotent distributed revocation |
| SLO-34 | Health checks show Redis up while SAML index unavailable | SLO readiness fails |
| SLO-35 | Logs include raw SAMLResponse/NameID/SESSION cookie | Security QA FAIL |

### 18.1. Validate SLO Messages Before Deleting

You cannot grab `SessionIndex` from a raw LogoutRequest and delete HTTP sessions, because any requester could send forged XML. Order of operations:

```text
Parse hardened XML / binding
  -> resolve server-trusted registration/issuer
  -> verify IdP signature/certificate/algorithm
  -> verify destination, time, name ID, session index rules
  -> replay detect request ID
  -> derive authorized SAML session key
  -> resolve targeted local sessions
  -> revoke idempotently (and audit)
  -> sign/send LogoutResponse with correct Status/InResponseTo
```

When customizing handlers, never omit Spring Security's default validators. For IdP-initiated SLO, test whether the current library terminates only the **request-associated session** or satisfies your app's cross-browser expectations; if global mapping is absent, add an authorized module behind the verified gate.

## 19. Chaos Engineering / Rolling Deployment

### 19.1. Simulating Node Failure

1. Browser starts SSO on A; pending AuthnRequest persists to Redis.
2. Kill pod A before the callback arrives.
3. IdP POSTs callback to B; assert login succeeds with the same session cookie.
4. Kill B immediately after session creation; a protected request hitting C remains authenticated.
5. IdP sends LogoutRequest to C; assert sessions from A/B/other devices are revoked by SessionIndex.
6. Reuse old cookie after logout on B; assert protected data is denied.
7. Repost the same Response/LogoutRequest: replay is rejected.
8. Keep PII/credentials out of chaos test artifacts.

### 19.2. Rolling Deploy with Schema/Version Mismatch

If `AbstractSaml2AuthenticationRequest` or custom session attributes use Java object serialization, app v1 may fail to deserialize objects written by v2. Zero-downtime rollouts need:
- Backward/forward-compatible serialization (never rely on default Java serialization of arbitrary classes without governance).
- Versioned DTOs, schema migrations, and cross-version canary logins.
- Namespace prefixes and TTLs that do not break pending transactions.
- Testing v1 initiates / v2 completes and vice versa.
- Controlled draining of old pending requests if an intentional protocol-breaking change occurs.
- Never flush all of Redis during deploy—it disrupts all sessions and can mask replay tests.

### 19.3. Redis Failover

Verify availability and consistency: a login request write acknowledged by primary and then read on another node can race with replica lag in asynchronous setups. For one-time consumption/replay, prefer atomic operations on the authoritative consistency domain; stale cache replicas can allow double acceptance. Test failover when:
- a pending login was just written,
- SLO revocation is in progress,
- the session index updates after session ID rotation,
- an IdP SLO request is replayed.

Never fall back to `permitAll`, unsigned SAML, no `InResponseTo`, or sessionless login just to preserve UX during a Redis outage.

## 20. Security and Privacy of Distributed State

### 20.1. Redis Is Not a Public Session Cache

- Place Redis on a private network with TLS and server auth/ACLs.
- Supply secret credentials via a secret manager; rotate without losing state.
- Never expose Redis directly to the Internet or use weak default passwords.
- Encrypt backups/snapshots, limit retention, and test restores.
- Use namespaces and ACLs so one application cannot read another app's sessions.
- Never log `SESSION` cookies, SAMLResponse, NameID, raw RelayState, or raw SessionIndex.
- Bound serialized `SecurityContext` size and minimize stored SAML attributes.
- Avoid Redis keys containing plaintext email/NameID when opaque/HMAC keys work.
- Separate SAML signing/decryption keys from Redis encryption/auth keys.

### 20.2. Session IDs Are Bearer Secrets

Anyone holding a valid session ID can hijack the session. Never place this value in:
- SAML `RelayState`.
- URL query parameters.
- Metric labels.
- HTTP referrers or browser analytics.
- Error messages/tickets/chat.
- Application debug logs.

When log correlation is needed, use independent opaque event IDs with TTLs or scoped keyed hashing; never expose the mapping table to unauthorized support staff.

### 20.3. Session Data Minimization

A SAML Assertion carries NameID, attributes, groups, and SessionIndex. Spring Security SAML2 Authentication may keep serialized SAMLResponse/principal inside SecurityContext/session depending on release. Store only data strictly required for authorization and SLO; audit session serialization, Redis memory dumps, and backups. **Do not strip signed Assertions recklessly and break framework semantics**, yet minimize attribute release at the IdP and store minimal mappings in application indexes.

### 20.4. Authorizing Session Revocation

An admin action to "log out all sessions for user X" is also security-sensitive. Never expose an unauthenticated API taking `sessionIndex`/`NameID` and deleting from Redis. Separate:
- Signed, validated IdP-initiated SLO.
- Authenticated user-initiated local logout.
- Admin-initiated revocation with RBAC/MFA/auditing.
- Security-incident bulk revocation with approvals and job tracking.

Each source carries different trust and authorization even though all end in `SessionRepository.deleteById`.

## 21. Observability and Runbooks

### 21.1. Permitted Event Log

```json
{
  "event": "saml_callback_rejected",
  "registration": "corp",
  "node": "sp-b",
  "reason": "AUTHN_REQUEST_NOT_FOUND",
  "request_correlation": "opaque-event-8",
  "session_store": "redis",
  "result": "rejected"
}
```

Never log full SAMLResponse XML, private keys, encoded tokens, raw SessionIndex/NameID, cookie IDs, or user attributes. Logging should retain only safe reason codes and aggregate counters.

### 21.2. Key Metrics

| Metric | Meaning |
| --- | --- |
| `saml_authn_request_missing_total` | Callback could not find pending request; browser cookie/Redis/TTL issue |
| `saml_inresponseto_mismatch_total` | Correlation failure, potential attack or misconfiguration |
| `saml_login_replay_rejected_total` | Repeated response rejection |
| `saml_logout_request_pending` | Outstanding RP logout transactions |
| `saml_logout_response_mismatch_total` | InResponseTo/RelayState validation failure |
| `saml_slo_target_sessions_count` | Sessions targeted per verified SLO |
| `saml_slo_partial_failure_total` | Partial delete/index/revocation failures |
| `saml_session_index_stale_total` | Stale forward/reverse mappings |
| `spring_session_redis_latency_ms` | Session lookup latency |
| `spring_session_redis_evicted_keys` | Capacity pressure |
| `saml_slo_replay_rejected_total` | Replay detected |
| `saml_same_site_cookie_missing_total` | Test-only/safe aggregate callback cookie absence |

**Never** attach user email/NameID/sessionId as metric labels due to cardinality and information leakage.

### 21.3. Runbook for SSO Failures After Scale-Out

1. Trace the flow: which node emitted the initial login redirect, which node received the callback.
2. Check whether the browser **actually sends the right cookie to the ACS** after cross-site POST; never log cookie values.
3. Verify the Spring Session Redis filter is truly active rather than Tomcat in-memory HttpSession.
4. Check Redis namespace/credentials/TTL/evictions/config across pods.
5. Verify pending `AuthnRequest` retention per release and session fixation lifecycle.
6. Check `InResponseTo` and `RelayState` mismatches via safe internal reason codes.
7. Verify proxy public ACS entityID/Recipient/Destination and forwarded headers.
8. Verify IdP trusted certs/keys/config versions and clocks.
9. If only one pod fails, drain/canary that pod and compare serialization/repository versions.
10. If Redis is unavailable, fail closed safely and show retry—never bypass correlation.
11. Test node A initiation → node B callback to confirm the fix.
12. Monitor replay failures and unexpected login successes after changes.

### 21.4. Runbook for SLO Failures Leaving Sessions Active

1. Verify the IdP **actually sent a signed LogoutRequest** and the SP received it at the right endpoint.
2. Verify signature/issuer/destination/timing/replay validators executed cleanly.
3. Determine whether SessionIndex is present, multiple, or absent; apply scope per contract.
4. Use trusted registration + NameID context + SessionIndex to look up the forward index.
5. For each target session ID, verify reverse association and current `SessionRepository` state.
6. Delete sessions cleanly and update mappings idempotently.
7. If using a distributed revocation marker, update it to block login/old-cookie races.
8. Return SAML `LogoutResponse` with status matching actual results—never report false Success.
9. Test whether old cookies from **two different browsers/nodes** still retain access.
10. Audit cleanup/partial failures, reaper stale entries, and Redis failover events.
11. Check whether custom SLO handlers execute when no browser session cookie is present.
12. Re-run RP-initiated SLO and IdP-initiated SLO separately; one passing does not prove the other.

## 22. Production Checklist

- [ ] Public SP entityID, ACS, and SLO URLs are consistent across all nodes/proxies.
- [ ] Trusted IdP metadata/verification keys and SP signing/decryption keys are synced and versioned.
- [ ] Spring Session Redis genuinely replaces local HttpSession with TLS/ACL/HA/TTL.
- [ ] Pending AuthnRequests are stored under a security-binding policy, not a bare local map.
- [ ] Callbacks landing on another node load the request with valid browser-flow binding.
- [ ] `InResponseTo`/`RelayState`, signed assertions, issuer, audience, bearer, and replay checks all operate.
- [ ] `InResponseTo` is never bypassed when Redis/cache fails.
- [ ] SameSite, Secure, HttpOnly, Cookie Domain/Path, and cross-site POSTs are tested in real browsers.
- [ ] Pending requests have short TTLs and atomic consume, handling multiple tabs per policy.
- [ ] RP LogoutRequest repository preserves required state after local session invalidation.
- [ ] LogoutResponse verifies trusted IdP, `InResponseTo`/RelayState, and consumes exactly once.
- [ ] IdP LogoutRequest is verified **before** querying SessionIndex and deleting sessions.
- [ ] SAML key includes trusted registration, IdP issuer, NameID context, and SessionIndex.
- [ ] Index maps to a **set of local HTTP session IDs**, not merely the current session.
- [ ] Reverse mapping cleans up properly on session expiry, logout, and session ID rotation.
- [ ] IdP SLO does not depend on a browser cookie being present.
- [ ] When SessionIndex is absent/multiple, policy defines clear scope and failure behavior.
- [ ] SessionIndex-targeted SLO never terminates sessions from another IdP/tenant.
- [ ] Spring Session principal-name index is never confused with SAML SessionIndex.
- [ ] One-time replay/expired request checks have atomic shared-store semantics.
- [ ] Login-vs-logout races have proper revocation/generation handling.
- [ ] Redis failures cause login/logout to fail safely without dropping trust/correlation.
- [ ] Local logout and federated logout are reported distinctly when SLO is partial.
- [ ] Rolling deploy serialization and config version compatibility are tested.
- [ ] Chaotic node restarts/Redis failovers do not break auth/session binding.
- [ ] No logging of session cookies, raw SAML assertions, NameID, RelayState, or keys.
- [ ] Multi-browser/multi-pod SLO acceptance tests verify old cookies are denied.
- [ ] Cleanup/reaper and index reconciliation have metrics/alerts.
- [ ] High-risk actions check local account disabled/locked/session revocation state.
- [ ] SLO security incident runbooks, change approvals, and rollback plans are ready.

## 23. Review Questions

**1. Why can login on node A fail when the callback lands on node B?**  
Because pending `AuthnRequest`/`HttpSession` resides in A's memory, which B cannot read. Share state via Spring Session Redis or a distributed repository with browser binding.

**2. Do sticky sessions guarantee SSO high availability?**  
No. Failover, affinity-cookie loss on callback, pod restarts, and cookieless IdP SLO break sticky assumptions.

**3. Where does Spring Security store AuthnRequest by default?**  
In `HttpSessionSaml2AuthenticationRequestRepository` per docs; when HttpSession uses Spring Session Redis, state is shared if the callback carries the right cookie.

**4. Should `InResponseTo` be skipped when the repository misses?**  
No. That bypasses correlation/security; fix cookies/Redis/TTL or safely restart login instead.

**5. What risk comes from looking up AuthnRequest solely by RelayState?**  
Browser-session binding can be lost, enabling login fixation/CSRF; an additional flow binding is needed when using a global cache.

**6. Why must pending AuthnRequests be consumed once?**  
So a response/IdP assertion cannot be reused to authenticate repeatedly, complementing replay controls.

**7. Are an HttpSession ID and a SAML SessionIndex the same?**  
No. HttpSession belongs to the app/browser cookie; SessionIndex is the IdP's SAML session identifier.

**8. Why must IdP-initiated SLO not rely on cookies?**  
The callback may lack the current browser cookie; terminating sessions across devices requires a server-side trusted SessionIndex→sessions mapping.

**9. Is it safe to map a bare SessionIndex without the issuer?**  
Unsafe; it must be namespaced by trusted registration/IdP and NameID context.

**10. Can one SessionIndex map to multiple local HttpSessions?**  
Yes. Targeted SLO must revoke the full set of active sessions per contract.

**11. Is Spring Session `findByPrincipalName` automatically a SAML SessionIndex index?**  
No. It indexes by principal name without distinguishing IdP sessions or SessionIndexes.

**12. Should an IdP-initiated LogoutRequest delete sessions before signature checks?**  
No. Verify issuer/signature/profile/replay before using NameID/SessionIndex.

**13. What if RP-initiated logout already deleted the local session before LogoutResponse arrives?**  
Pending LogoutRequest correlation must survive long enough in the proper repository/flow binding to validate the IdP's response.

**14. Does a LogoutResponse saying Success guarantee every other app logged out?**  
Not necessarily; partial/failed/async outcomes occur. The SP should report only the local/federated status it actually verified.

**15. When session ID changes S0→S1 after login, where should the logout mapping point?**  
To S1, by updating forward/reverse mappings rather than keeping S0.

**16. If Redis loses an AuthnRequest, should the app fall back to a local HashMap?**  
Never automatically; that breaks consistency and browser binding. Fail safely and retry the flow.

**17. If the IdP sends SLO with no SessionIndex, what does the SP do?**  
Follow the approved SAML profile/trust contract: either broad logout for that NameID or reject; never guess deleting only one session or everyone with the same email.

**18. If a user logs in concurrently with an IdP logout, what can happen?**  
A session resurrection race; prevent it with an atomic generation/revocation marker or equivalent protection.

**19. Why can an app session stay alive even after the SAML Assertion expires?**  
Assertion validity governs using the assertion; the local session has its own lifetime. Logout must terminate the local session per policy.

**20. Why check SameSite/Path/Host when debugging missing AuthnRequests?**  
The cookie might not return to the ACS, leaving the node unable to locate the browser HttpSession even when Redis is healthy.

**21. Can `RelayState` be set to the local session ID?**  
No. Session IDs are bearer secrets and must never appear in browser-visible SAML parameters/URLs or logs.

**22. Can you assume enabling `saml2Logout` logs out all devices automatically?**  
No. Verify how the library/app maps IdP SessionIndex to local sessions and test across real browsers.

**23. If a valid signed IdP LogoutRequest arrives from IdP B with the same NameID as IdP A, should it delete A's session?**  
No. Lookups must be namespaced by trusted IdP registration/issuer.

**24. After a rolling deploy switches nodes, what happens if Spring Session fails to deserialize an object?**  
Login/logout fails due to state incompatibility; use versioned serialization and cross-version integration tests rather than skipping validation.

## 24. Official Documentation and References

- [Spring Security — Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `Saml2AuthenticationRequestRepository`, `HttpSessionSaml2AuthenticationRequestRepository`, and `CacheSaml2AuthenticationRequestRepository` with the RelayState/session-binding warning.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, and verified response processing.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): AuthnRequest flow, ACS, verifying IdP assertions.
- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/IdP-initiated SLO, LogoutRequest/LogoutResponse filters, `Saml2LogoutRequestRepository`, and customization.
- [Spring Security — SAML2 Logout Request Repository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html): save/load/remove pending SLO requests.
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): Spring Session Redis-backed HttpSession, `springSessionRepositoryFilter`, namespaces/cookies.
- [Spring Session — API Indexing](https://docs.spring.io/spring-session/reference/api.html): `FindByIndexNameSessionRepository` and `findByPrincipalName`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext persistence, session fixation protection, session expiry/logout.
- [OASIS SAML2 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnStatement/SessionIndex, LogoutRequest/LogoutResponse, InResponseTo, NameID.
- [OASIS SAML2 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, Single Logout, bearer requirements.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, InResponseTo, replay, XML parsing.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie security, session IDs, lifecycle.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): fail-closed auth, login CSRF, session behavior.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): protecting session IDs/claims in logs.

**Remember:** A Spring Security SAML2 cluster needs more than nodes sharing visibility into `HttpSession`. It requires **browser-correlated, single-use AuthnRequests**, **RP LogoutRequests that remain lookup-capable after local logout**, and **controlled mapping from IdP SessionIndex/NameID to all relevant local sessions**. Spring Session Redis solves shared HttpSession yet **does not build a global SLO index automatically**; sticky sessions do not guarantee failover, and a RelayState-only cache can lose browser binding. Always verify signature/issuer/audience/recipient/time/replay before creating or revoking sessions, bound TTLs, govern Redis/keys, and test multi-browser multi-node SSO/SLO. If the store or correlation fails, **fail closed** rather than dropping validation.