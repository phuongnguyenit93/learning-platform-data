# Diagnosing CAS INVALID_SERVICE, INVALID_TICKET, and Redirect Loops in Spring Security

## 1. Why Do These Three Symptoms Usually Appear Together?

An application using **Spring Security – federation** to log in via **Apereo CAS** normally works like this: when a user visits a resource requiring authentication, the app redirects the browser to the CAS Server; CAS authenticates the user and issues a **Service Ticket (ST)**; the browser returns to the application's callback; the app uses the ST to call CAS **/serviceValidate** (or the appropriate validation endpoint); after CAS verifies it, Spring Security creates `Authentication` and maintains a local session.

If the service misconfigures one of these steps, you may observe:

- **`INVALID_SERVICE`**: CAS determines that the `service` supplied when validating the ticket does not match the `service` for which the ticket was issued.
- **`INVALID_TICKET`**: the ticket is invalidated, nonexistent, expired, previously used, or fails validation requirements such as `renew` per the protocol.
- **"Too many redirects" / ERR_TOO_MANY_REDIRECTS**: the browser continuously bounces from the app to CAS and back without **ever establishing a usable application session**. The loop can occur because validation fails, or because validation **succeeds** yet the session cookie / SecurityContext is lost.

**Crucial point in the CAS protocol:** **A Service Ticket is validated once and only once**, regardless of whether the check succeeds or fails. Specifically, **`INVALID_SERVICE` consumes the ticket**. When you fix the service URL configuration and retry **the exact same old ticket**, the next result is usually **`INVALID_TICKET`**. If operators overlook this, they mistakenly assume "we fixed the URL yet CAS still rejects the ticket".

This lesson belongs to **Observability and debugging**. Goals:

1. Read error codes accurately per the **CAS protocol**, distinguishing them from **service registry denials**.
2. Compare the three places `service` is used: redirect to `/login`, callback receiving ST, and back-channel `/serviceValidate`.
3. Identify mismatches in scheme/host/port/path/query/trailing slash, external URL vs. internal URL behind a load balancer/proxy, double URL-encoding, and dynamic parameters.
4. Understand the ST lifecycle, retry/replay, expiration, `renew=true`, ST vs. PT, and CAS SSO session/TGC vs. Spring `JSESSIONID`.
5. Read **Spring Security `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `Cas20ServiceTicketValidator`**, and related configuration.
6. Collect redirect traces and safe logs/correlation without **logging raw tickets or cookies**.
7. Distinguish a loop caused by **validation failure** from a loop caused by **session non-persistence** despite validation success.
8. Follow a runbook: reproduce → branch by root cause → fix the right place → test a **fresh ST** → confirm a working app session → regression tests.
9. Run a **Java 17** demo simulating error codes and both types of redirect loops, with verified stdout.
10. Build a test checklist and production error-monitoring metrics.

**Scope limit:** CAS is its own SSO protocol. Never project semantics from Kerberos service tickets, SAML Assertions, OIDC ID Tokens, or OAuth Authorization Codes onto CAS Service Tickets. A CAS ST is neither a JWT nor a browser cookie.

## 2. Standard CAS Flow: Distinguishing CAS SSO Session and Application Session

~~~text
Browser                 Spring Security Web App              Apereo CAS
   |                             |                                |
   | GET /private                |                                |
   |---------------------------->|                                |
   |                             | No Authentication yet          |
   |<----------------------------| 302 /cas/login?service=S        |
   |------------------------------------------------------------->|
   |                             |                                | Has SSO/TGC?
   |                             |                                | Login if needed
   |<-------------------------------------------------------------|
   | 302 S?ticket=ST-NEW-1       |                                |
   |                             |                                |
   | GET /login/cas?ticket=ST-NEW-1                              |
   |---------------------------->|                                |
   |                             | CasAuthenticationFilter        |
   |                             | -> CasAuthenticationProvider   |
   |                             | -> TicketValidator             |
   |                             |                                |
   |                             | GET /cas/serviceValidate       |
   |                             | ?service=S&ticket=ST-NEW-1     |
   |                             |------------------------------->|
   |                             | <cas:authenticationSuccess>    |
   |                             |<-------------------------------|
   |                             |                                |
   |                             | Load UserDetails/roles         |
   |                             | Save SecurityContext/session   |
   |<----------------------------| Set-Cookie: JSESSIONID=...     |
   | 302 /private                |                                |
   |---------------------------->|                                |
   | Cookie: JSESSIONID=...      |                                |
   |<----------------------------| 200 /private                   |
~~~

In this example:

~~~text
CAS base URL:  https://sso.example.test/cas
CAS login:     https://sso.example.test/cas/login
CAS validate:  https://sso.example.test/cas/serviceValidate

Public service / CAS callback:
  https://portal.example.test/login/cas

Protected business endpoint:
  https://portal.example.test/private
~~~

**Service callback** and **business URL** do not have to be identical. In a typical stateful Spring Security CAS configuration, `ServiceProperties.service` must point to the URL monitored by **`CasAuthenticationFilter`**, `/login/cas` by default. Redirecting back to `/private` is the job of the success handler/saved request after authentication, **not by validating ST against `/private`**.

### 2.1. Terms to Distinguish

| Term | Meaning |
| --- | --- |
| **CAS `service`** | URL identifying the service that CAS redirects back to with a service ticket upon issuance; reused during validation |
| **Service registry** | Catalog/pattern/policy of services the CAS Server is permitted to serve |
| **ST — Service Ticket** | Opaque credential issued for one service, **single-use validation** |
| **TGC — Ticket Granting Cookie** | SSO login cookie of the **CAS Server**, enabling issuance of new STs per policy |
| **TGT — CAS Ticket Granting Ticket** | Server-side SSO proof linked to TGC; not a Kerberos TGT and never sent as an ST to the Spring callback |
| **`JSESSIONID`** | Session cookie **of the Spring application**, independent of TGC |
| **`CasAuthenticationEntryPoint`** | Initiates SSO by redirecting the browser to CAS login |
| **`CasAuthenticationFilter`** | Intercepts the ticket artifact at the callback matching `filterProcessesUrl` |
| **`CasAuthenticationProvider`** | Uses `TicketValidator` to verify the ticket and load `UserDetails`/authorities |
| **`Cas20ServiceTicketValidator`** | Client calling the CAS ticket validation endpoint; never trusts an ST merely because a string starts with `ST-` |

If the user still holds a **valid CAS TGC** while the app fails to keep `JSESSIONID`, every time the app redirects to CAS, CAS can issue a **new ST** almost immediately. That produces an ultra-fast redirect loop even though the user is already logged into CAS.

## 3. Reading CAS Protocol Error Codes Accurately

CAS 2.0/3.x `/serviceValidate` returns XML with one of two branches:

**Success** (abbreviated):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Failure** (example):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service identifier does not match ticket
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

These XML snippets illustrate structure only, not actual output from a specific CAS Server. **Detailed message bodies vary by version/config**; do not parse by checking substrings for the word "invalid". Parse the proper XML namespace/element/error code and **disallow XXE** if writing a custom client (prefer the CAS client library).

### 3.1. Specification Meaning Table

| Error Code | Meaning per CAS Protocol | What to Investigate |
| --- | --- | --- |
| **`INVALID_REQUEST`** | Missing required request parameters | `service`, `ticket`, encoding, parameter names |
| **`INVALID_TICKET_SPEC`** | Ticket/validation does not satisfy required type/spec | PT sent to `/serviceValidate`, wrong validation profile |
| **`INVALID_TICKET`** | Ticket invalid, expired, already used/unrecognized; also occurs with `renew=true` if ticket was not issued from primary authentication | ST lifecycle, retry, expiry, `renew`, CAS ticket store |
| **`INVALID_SERVICE`** | Ticket **validly existed**, yet the `service` at validation **did not match** the service bound to the ticket; ticket is destroyed | `service` URL at CAS login vs. validation, scheme/host/port/path/query |
| **`UNAUTHORIZED_SERVICE_PROXY`** | Service not authorized for proxy authentication | PGT/proxy policy; do not confuse with ST service mismatch |
| **`INVALID_PROXY_CALLBACK`** | Proxy callback/credentials fail security requirements | HTTPS PGT callback, cert trust, routing |
| **`INTERNAL_ERROR`** | CAS hit an internal error during validation | CAS logs, ticket registry, storage/cluster, dependency failures |

CAS Server/versions may add extra error codes; this table lists the **minimum protocol codes**. Never rely solely on the code name to assert a root cause without checking **CAS logs and service/ticket correlation**.

**Distinction:** the CAS login message **"Application Not Authorized"** normally occurs because the **service URL is rejected by the service registry**, which is distinct from **`INVALID_SERVICE`** at ticket validation: a ticket may have been validly issued, yet the service passed at validation was wrong.

### 3.2. Where Does the Error Code Appear?

In the browser, you typically see redirects/cookies/HTTP 302; **`INVALID_SERVICE` and `INVALID_TICKET` normally appear in the back-channel XML response** between the application and CAS. The browser client may only see an error login page or a loop.

Evidence to collect:

- Browser HAR: 302 chain and **redacted** URLs.
- CAS Server logs: validation failure code, registration/service ID, timestamp, request correlation.
- Spring app logs: exceptions from `TicketValidator`/`CasAuthenticationProvider`; service URL used for validation, callback path, session persistence.
- Gateway/ingress logs: public host/scheme, trusted forwarded headers, cookies/SameSite/Path.
- Metrics: number of CAS redirects per browser/session, validation failure rates, successful validations followed by lost sessions.

**Never log raw `ticket` / TGC / `JSESSIONID`**, even when debugging.

## 4. INVALID_SERVICE: At Which Step Is the Service URL Wrong?

### 4.1. Nature of Ticket Substitution Protection

When CAS issues an ST for:

~~~text
https://portal.example.test/login/cas
~~~

that ticket **cannot be used as a credential for**:

~~~text
https://reports.example.test/login/cas
~~~

even when both apps share the same CAS Server. Service binding prevents a ticket for service A from being carried over to service B.

In standard Spring Security CAS:

~~~text
ServiceProperties.service:
  https://portal.example.test/login/cas

CasAuthenticationEntryPoint:
  redirects to
  https://sso.example.test/cas/login
      ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas

CAS issues ST for:
  https://portal.example.test/login/cas

Browser callback:
  https://portal.example.test/login/cas?ticket=ST-NEW-1

CasAuthenticationProvider / TicketValidator:
  GET https://sso.example.test/cas/serviceValidate
      ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
      &ticket=ST-NEW-1
~~~

Spring uses the same **`ServiceProperties`** across the entrypoint/provider and the matching callback filter. If CAS issued the ST for a different `service` string than the one the validator sends, **`INVALID_SERVICE`** can occur.

### 4.2. One Service Mismatch Can Turn Into Two Consecutive Error Codes

~~~text
T1  CAS issues ST-1 for service=https://portal.example.test/login/cas
T2  App validates ST-1 with service=http://app:8080/login/cas
T3  CAS: INVALID_SERVICE
    ST-1 is CONSUMED per CAS protocol
T4  Operator fixes service=http://... to https://portal...
T5  Operator retries validating ST-1 AGAIN
T6  CAS: INVALID_TICKET, because ST-1 is no longer valid
T7  Browser initiates a NEW CAS login, CAS issues ST-2
T8  App validates ST-2 with service=https://portal... -> SUCCESS
~~~

Therefore, the proper test procedure after fixing **`INVALID_SERVICE`** is to **initiate a fresh CAS login round to get a new ST**. Never retry the same ST or add network retries "waiting for sync".

### 4.3. URL Differences That Commonly Cause INVALID_SERVICE

| Service Used at Ticket Issuance | Service at Validation | Result in Strict Matching Profile |
| --- | --- | --- |
| `https://portal.example.test/login/cas` | Identical string | PASS if ST is still valid |
| `https://portal.example.test/login/cas` | `http://portal.example.test/login/cas` | FAIL: scheme |
| `https://portal.example.test/login/cas` | `http://app:8080/login/cas` | FAIL: internal vs. public |
| `https://portal.example.test/login/cas` | `https://portal-internal.example.test/login/cas` | FAIL: host |
| `https://portal.example.test/login/cas` | `https://portal.example.test:8443/login/cas` | FAIL: port |
| `https://portal.example.test/login/cas` | `https://portal.example.test/app/login/cas` | FAIL: context path |
| `https://portal.example.test/login/cas` | `https://portal.example.test/login/cas/` | FAIL: trailing slash |
| `https://portal.example.test/login/cas` | `https://portal.example.test/login/cas?lang=vi` | FAIL: query |
| `https://portal.example.test/login/cas` | `https://portal.example.test/private` | FAIL: callback vs. protected page |
| `https://portal.example.test/login/cas` | `https://evil.example.test/login/cas` | FAIL: cross-service substitution |
| `https://portal.example.test/login/cas?x=1&y=2` | Same parameters but different canonical form | Must compare against CAS's actual service matching strategy |

**Exact precision note:** The CAS protocol binds a ticket to a **service identifier**, and the CAS Server has configurable **service matching strategies/normalization rules**. The table applies **strict identity matching** to illustrate errors; there is no arbitrary URI canonicalization rule that clients may assume always equates. Never "fix" by checking `startsWith("https://portal")` or broad regexes in ticket validation.

### 4.4. Registry Match and Ticket Match Are Two Separate Checks

The **service registry** may allow a **pattern** like `^https://portal\.example\.test/login/cas$` or an approved set of URLs. The registry decides **whether a service is permitted to use CAS**.

**Ticket validation** requires the exact **service identifier to which the ST was issued**, per matching policy. Registering a pattern matching two URLs does not mean an ST issued for URL A is automatically valid for URL B.

Example of a bad registry entry:

~~~text
^https://.*       # Allows any HTTPS host - TOO BROAD
~~~

Such a configuration can cause CAS to accept unintended applications. **Never open the registry to the entire Internet** to fix `INVALID_SERVICE`. Fix the exact service identifier and register the right application.

### 4.5. URL Encoding: Distinguishing HTTP Representation from Service Value

In CAS login/validation requests, `service` is a **URL-encoded query parameter**. Example:

~~~text
Original service value:
  https://portal.example.test/login/cas

When passed in CAS URL:
  service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
~~~

The CAS server **decodes the parameter** and then evaluates the service identifier. If a gateway/client accidentally **double-encodes**, the value after one decode round remains `https%3A%2F%2F...` instead of the original URL, causing mismatch/registry errors.

Check:

- Who is responsible for encoding the query parameter? Spring CAS client or custom app redirect?
- Is anyone concatenating query strings directly and calling `URLEncoder` over the **entire CAS URL**?
- Is `?ticket=...` being appended inside `service` before validation?
- Are dynamic tracking parameters, localization queries, `;jsessionid`, fragments, or extra slashes added?
- Does a proxy rewrite/normalize query/path or redirect `http→https`?

**Never compare raw URL-encoded strings as if they were canonical service values**; decode exactly one layer in test traces and compare **logical values** per the CAS service matcher.

## 5. INVALID_TICKET: The Ticket Can Truly No Longer Be Used

### 5.1. Causes per Protocol

A CAS Service Ticket:

- Is an opaque string; **never parse or guess users from the ticket**.
- Is bound exclusively to the **service** attached at issuance.
- **Can be validated only once**. The CAS protocol specifies that a ticket is invalidated after **a single validation attempt**, **even if that attempt fails**.
- Has a **short lifetime** per the CAS ticket expiration policy; once expired, validation fails.
- Depends on the CAS ticket registry/store holding its record.
- May be subject to `renew=true` on validation.

Common causes of `INVALID_TICKET`:

1. **Replay:** callback was refreshed/navigated back, or browser/proxy resent the same `ticket`.
2. **Double validation:** two servlet filters, two authentication managers, or duplicate requests both called `/serviceValidate` for one ST.
3. **Ticket was already consumed by a prior `INVALID_SERVICE`**.
4. **Ticket expired** because the user lingered in the browser, network delay, queue, or clock/policy mismatch.
5. **Ticket absent in registry**: altered characters/bad URI parsing, lost CAS store/cache, or cluster deployment with inconsistent stores.
6. **`renew=true`** while the ticket was issued from an existing SSO session (without primary credentials login for that issuance).
7. **Wrong ticket/endpoint type** (PT sent to `/serviceValidate`, or ST used where a proxy ticket is required)—the exact error may be `INVALID_TICKET_SPEC` or another code depending on implementation.
8. **Forged ticket/not issued by this CAS Server**, or staging/prod CAS environments mixed up.
9. **Load balancer/ticket registry replication failure**: ticket issued on one node yet validation lands somewhere it is not visible.
10. **Client reuses the ticket across stateless API requests** even though an ST is single-use.

### 5.2. Signals to Record

| Evidence | Hypothesis |
| --- | --- |
| First validation SUCCESS, second INVALID_TICKET | Single-use works properly |
| First validation INVALID_SERVICE, second INVALID_TICKET | Mismatch consumed the ticket |
| First validation INVALID_TICKET even with right service | Unknown/expired/already-used ST or renew mismatch |
| Two app nodes simultaneously validate one ticket | Race/double-validation |
| Fails only when user hits browser Back/Refresh | Callback replay |
| Fails after very slow redirects | Ticket expired / time policy |
| Fails only when `sendRenew=true` | Primary-auth requirement not met |
| Fails only after CAS Server rollout | Ticket registry keys/cache/store/cluster issue |
| Fails when sending PT to `/serviceValidate` | Wrong validation endpoint/ticket type |
| Every newly minted ST returns INVALID_TICKET | CAS server issuer/registry, expiration, renew, client config |
| App uses ST like a long-lived cookie | Anti-pattern: ST is not a reusable session token |

**Do not increase ticket TTL or disable replay protection as a first-aid fix.** Find the root cause. When security policy requires short-lived/single-use STs, altering TTL/ticket policies does not fix client logic bugs.

### 5.3. Renew = Require Primary Authentication, Not Auto-Retry

In Spring Security, `ServiceProperties#setSendRenew(true)` tells CAS not to rely solely on an existing SSO session when issuing an ST; validating with `renew` also requires the ticket to prove primary-credential authentication per the CAS contract.

Scenario:

~~~text
Browser already has TGC / SSO login
App/CAS client validation uses renew=true
Ticket was not issued from a corresponding primary login
=> CAS may return INVALID_TICKET per CAS spec
~~~

Do not reflexively flip `renew=true` to false if the app requires **fresh authentication/step-up**. Verify that CAS `/login` receives the same `renew` policy, that the browser actually prompts for fresh credentials, and that the CAS validator uses the same `ServiceProperties`.

### 5.4. ST and PT Are Different

- **ST** is issued by CAS for a browser to access an application; `/serviceValidate` verifies STs.
- **PT** is a **Proxy Ticket** for service-to-service delegation; it uses `/proxyValidate` and proxy authorization policy.
- **PGT** is a Proxy Granting Ticket, issued via a separate callback/delegation mechanism, not an ST.

If a `PT-...` is sent to `/serviceValidate`, the CAS protocol mandates **it must not be treated as a successful ST**; the specific error may fall under ticket specification errors. Never "fix" by replacing `PT-` with `ST-` or skipping verification.

Spring Security CAS also offers **`authenticateAllArtifacts` and `ServiceAuthenticationDetailsSource`** for specific proxy/stateless use cases. Do not enable them casually on a stateful web app just to accept tickets on arbitrary paths.

## 6. Redirect Loop: Three Branches to Distinguish Immediately

"Too many redirects" is an **HTTP/browser symptom**, not a CAS protocol error code. To find the root cause, first ask **whether CAS ticket validation has ever succeeded**.

### Branch A: Validation Fails on Every Cycle

~~~text
GET /private
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS issues ST-1
  -> 302 /login/cas?ticket=ST-1
App validates ST-1 with WRONG_SERVICE
  <- CAS INVALID_SERVICE
App remains anonymous
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS issues ST-2
  -> 302 /login/cas?ticket=ST-2
App validates ST-2 with WRONG_SERVICE
  <- CAS INVALID_SERVICE
... repeats continuously ...
~~~

Characteristics:

- Each cycle gets a **new ST**, not the same ST.
- CAS SSO/TGC may still be valid, so CAS login redirects very quickly.
- CAS validation fails repeatedly: `INVALID_SERVICE`, `INVALID_TICKET`, TLS, certificate/trust errors, or network failures.
- The app never creates Authentication/session because validation never succeeded.

**Priority:** inspect the **very first validation failure**, the `service` when CAS issued the ticket, and the `service` when the validator sent it. Do not start by clearing all cookies or raising session timeouts.

### Branch B: Validation Succeeds Yet the Application Session Does Not Persist

~~~text
GET /private
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS issues ST-1
  -> /login/cas?ticket=ST-1
App /serviceValidate ST-1 -> authenticationSuccess
App creates SecurityContext = alice
App returns Set-Cookie: JSESSIONID=S1
Browser GET /private yet DOES NOT send JSESSIONID=S1
  -> App remains anonymous
  -> CAS /login?service=PUBLIC_SERVICE
CAS issues ST-2
  -> /login/cas?ticket=ST-2
App validation SUCCESS
  -> Set-Cookie: JSESSIONID=S2
Browser again omits the cookie ...
~~~

Characteristics:

- CAS validation **SUCCEEDS** on every cycle.
- The Spring app keeps redirecting to CAS because it **cannot restore `SecurityContext`** on the subsequent request.
- Common causes: **Cookie Path/Domain/SameSite/Secure**, hostname mismatch, HTTP/HTTPS, reverse proxy, browser-blocked session cookie, or **`SecurityContextRepository` not saving**.
- Application is accidentally **stateless** or uses `SessionCreationPolicy.STATELESS` even though browser CAS requires stateful sessions.
- Session saved on node A while next request lands on node B, Redis/Spring Session is not shared, or sticky sessions are broken.

**Priority:** inspect `Set-Cookie` and the **subsequent request's `Cookie` header**, opaque hashed session IDs, SecurityContext save/load, and the shared store.

### Branch C: CAS/Login/Entrypoint or URL Routing Self-Redirects

~~~text
GET /login/cas?ticket=ST-1
  -> route does not match CasAuthenticationFilter
  -> anyRequest().authenticated() keeps treating as anonymous
  -> CasAuthenticationEntryPoint redirects back to CAS login
  -> CAS redirects again to /login/cas?ticket=ST-2
  -> callback is still bypassed
... repeats ...
~~~

Causes:

- Spring Security `FilterChain` matcher does not cover `/login/cas`, or `filterProcessesUrl` does not match.
- Application context path is doubled: `/app/login/cas` vs. `/login/cas`.
- Reverse proxy rewrites callback path/host wrongly, so another route handles the ticket.
- CAS filter sits in the wrong `SecurityFilterChain`/order; a custom redirect filter fires before the CAS filter runs.
- Redirecting to app's `/login` itself requires authentication and bounces back to CAS, looping even without an ST.
- Login success handler redirects to a protected URL in a different cookie scope/HTTP/host alias.
- Forced HTTPS redirects/proxy TLS termination cause an `http→https→http` loop.
- `gateway=true` orchestration or saved-request loop, if used.
- CAS Server itself has a redirect loop because TGC/SSO cookie is blocked on the CAS domain; the trace shows the loop on the **CAS login host**, not just the app host.

**Priority:** group `Location` headers by hostname/path/status/`Set-Cookie` and confirm **the callback actually hits the CAS filter**.

## 7. Explaining Relevant Spring Security CAS Configurations

Spring Security CAS documentation defines these core components:

~~~text
ExceptionTranslationFilter
      |
      +-> CasAuthenticationEntryPoint
      |     - CAS login URL
      |     - ServiceProperties.service
      |
      v
Browser CAS login + ST redirect
      |
      v
CasAuthenticationFilter (default /login/cas)
      - extracts ?ticket
      - submits CAS service ticket Authentication
      |
      v
ProviderManager
      |
      v
CasAuthenticationProvider
      - ServiceProperties
      - Cas20ServiceTicketValidator
      - UserDetailsService / authorities
      |
      v
SecurityContextRepository
      - HttpSession / Spring Session
      |
      v
SavedRequest / success redirect / authorization
~~~

**`ServiceProperties.service` is the starting point for investigation.** `CasAuthenticationFilter` Javadoc explains that when the filter monitors `/login/cas`, `ServiceProperties.getService()` is used as the `service` when validating the ST. It must stay consistent with the actual callback URL.

This is the CAS client for Spring Security, not Spring Security SAML2/OIDC; never add `saml2Login` or `oauth2Login` to "fix" a CAS callback when the app uses CAS.

### 7.1. Dependencies and Version Alignment

Gradle example (in a project with Boot/Spring dependency management):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The CAS client library `org.apereo.cas.client:cas-client-core` is a module dependency in corresponding branches. Use BOM/plugin alignment matching your Java/Jakarta Servlet version; **never mix** Spring Security CAS 5.x/6.x/7.x with incompatible CAS client packages. While older Spring Security CAS docs show legacy XML examples, **7.x Javadoc** still documents `ServiceProperties`, `CasAuthenticationFilter`, `CasAuthenticationEntryPoint`, and `CasAuthenticationProvider`.

**Never hardcode a "latest" version in examples**; check the project's actual release/BOM. Spring Boot 3.x and 4.x differ in dependencies/Jakarta APIs; illustrative code must compile against your chosen stack.

### 7.2. Sample Spring Java Config: One Consistent Service URL

Example bean config for a web app receiving callbacks at `https://portal.example.test/login/cas`:

~~~java
package com.example.portal.security;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {
    private static final String SERVICE =
        "https://portal.example.test/login/cas";
    private static final String CAS_BASE =
        "https://sso.example.test/cas";

    @Bean
    ServiceProperties casServiceProperties() {
        ServiceProperties props = new ServiceProperties();
        props.setService(SERVICE);
        props.setSendRenew(false);
        return props;
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties casServiceProperties,
            UserDetailsService userDetailsService) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setServiceProperties(casServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setKey("portal-cas-provider-identity");
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain casFilterChain(
            HttpSecurity http,
            ServiceProperties casServiceProperties,
            CasAuthenticationProvider casProvider) throws Exception {

        CasAuthenticationEntryPoint entry = new CasAuthenticationEntryPoint();
        entry.setLoginUrl(CAS_BASE + "/login");
        entry.setServiceProperties(casServiceProperties);

        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(casServiceProperties);
        filter.setAuthenticationManager(new ProviderManager(casProvider));
        filter.setSecurityContextRepository(repository);
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(casProvider)
            .securityContext(context -> context
                .securityContextRepository(repository))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entry))
            .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

This is a **Spring integration configuration**, not standalone Java 17. It requires a real CAS Server or protocol-compliant mock server, certificate chain, secure `UserDetailsService`, session persistence, HTTPS ingress, CSRF/logout policy, and integration tests for your chosen Spring version.

Key points to check:

- `ServiceProperties.service` is a fixed, accurate **public callback URL**.
- `CasAuthenticationEntryPoint` and `CasAuthenticationProvider` share the **same `ServiceProperties` bean**.
- `CasAuthenticationFilter.filterProcessesUrl` matches the exact `/login/cas` callback path after context path.
- `Cas20ServiceTicketValidator(CAS_BASE)` uses the **CAS Server's** base URL, not the application's URL.
- `CasAuthenticationProvider` loads local `UserDetailsService`/roles **after CAS validates the ticket**.
- `HttpSessionSecurityContextRepository` fits stateful browser sessions; note `filter.setSecurityContextRepository(...)` specifically on custom filters in Spring Security 6/7.
- `ChangeSessionIdAuthenticationStrategy` mitigates session fixation after login.
- If multiple `SecurityFilterChain`s exist, verify the callback and protected resources sit under the right policy and the filter is not auto-registered/executed twice.
- If choosing dynamic service URLs or `authenticateAllArtifacts=true` for proxy/stateless use cases, configure `ServiceAuthenticationDetailsSource` and ticket URL binding per Spring docs; **never enable them as a patch for `INVALID_SERVICE`**.
- Never add `formLogin`/`httpBasic` fallbacks to a CAS-only chain unless required by policy; an unintended fallback provider can create an authentication downgrade.

### 7.3. Redirect Loop Caused by Filter URL Mismatch

Example:

~~~text
ServiceProperties.service = https://portal.example.test/app/login/cas
CasAuthenticationFilter.filterProcessesUrl = /login/cas
Servlet context path = /app
Reverse proxy strips /app before app

Observed callback at backend:
  /login/cas?ticket=ST-...

If route/context path or SecurityFilterChain matchers are inconsistent:
  CAS filter may fail to intercept the ticket.
  Browser is redirected back to CAS by entrypoint.
~~~

This example **requires checking actual request paths and servlet context**, not an automatic rule that "having `/app` is wrong". Spring resolves servlet context paths and filter paths per framework semantics; measure with traces/integration tests rather than **guessing**.

## 8. Reverse Proxy/TLS Breaking `service`

A common topology:

~~~text
Browser:
  https://portal.example.test/login/cas

Load balancer:
  terminates TLS, rewrites Host/Path
  X-Forwarded-Proto: https
  X-Forwarded-Host: portal.example.test

Spring app:
  http://portal-pod:8080/login/cas
~~~

If the CAS entrypoint constructs `service` from the **public URL** while the validator/filter computes it from the **internal URL**, the ticket can be rejected. If both use a wrong internal URL, the CAS Server may reject the service in the service registry, or the browser may fail to reach the callback.

### 8.1. Proper Checklist

- Establish **one single source of truth** for the public service callback.
- Have a service registry entry for the approved **public service identifier**, never an open `.*` regex.
- Set `ServiceProperties.service` explicitly when Spring CAS components rely on a static service.
- If the app uses dynamic URLs, verify every component derives the exact same **trusted external URL**.
- Reverse proxy sets `Forwarded`/`X-Forwarded-*` **only from trusted proxies**; strip/block spoofed headers from the Internet.
- In Spring Boot, configure the appropriate Servlet/proxy forwarding strategy; **verify with real requests**, not just by reading a YAML property.
- Ensure HTTPS scheme, host, port, context path, and path casing/trailing slash are consistent.
- Verify single-layer URL-encoding; service query parameters must not mutate unexpectedly.
- Never encode `JSESSIONID`/tickets into the service identifier without an approved contract.
- Never disable TLS validation to fix handshake errors. CAS back-channel ticket validation must use HTTPS with a trusted CA.
- Never accept Host-header injection to construct login redirects or attacker-controlled service URLs.

### 8.2. Why Can an HTTP→HTTPS 302 Also Be Involved?

If the gateway and app disagree on the public scheme:

~~~text
Browser -> https://portal.example.test
Proxy -> http://app:8080
Spring sees http and redirects to https://app:8080
Proxy redirects back to public https://portal...
... scheme/host loop ...
~~~

In this branch, **no ticket validation may have happened at all**. Use a HAR to see whether the redirect happens before CAS login, at the CAS Server, or after callback.

## 9. Session Issues Where CAS Validation Succeeds Yet Still Loops

### 9.1. Two Cookies on Two Hosts

| Cookie | Default Domain | Purpose | When Lost |
| --- | --- | --- | --- |
| **CAS TGC** | `sso.example.test` | Maintains CAS SSO; lets CAS mint new STs | CAS may require re-login |
| **Application `JSESSIONID`** | `portal.example.test` | Maintains Spring local authentication | App is anonymous after callback, redirects back to CAS |
| **Session store key** | Backend Redis/JDBC/container | Maps Session ID → `SecurityContext` | Session cookie exists yet app cannot load state |

**Never delete TGC and assume app `JSESSIONID` was destroyed**, and never delete `JSESSIONID` and assume the user is completely logged out of CAS. CAS Single Logout (SLO) has its own mechanism; local logout and central logout have separate lifecycles.

### 9.2. Browser Fails to Store/Send `JSESSIONID`

Common mistakes:

- `Set-Cookie` has a `Domain` differing from the hostname the user visits.
- `Path` does not cover `/private` or the callback/saved request.
- `SameSite` is blocked by the browser in a particular cross-site/embedded flow; incompatible cookie policy.
- `Secure` cookie is only sent over HTTPS; app/redirect drops back to HTTP.
- Browser privacy settings, third-party cookie blocking, or sandboxed iframes.
- Multiple apps share cookie name/domain/path, causing session collisions.
- Session ID is regenerated yet the `Set-Cookie` on the success response is stripped by a proxy.
- Browser switches between `www.portal` and `portal`, breaking host-only cookies.
- Cookie size/headers exceed gateway limits or are rejected by the browser.
- Proxy rewrites `Set-Cookie: Path/Domain/SameSite` wrongly.

**Verify whether the next request carries a `Cookie` header with the right opaque session ID.** You do not need to read raw cookie values; in browser DevTools you can inspect existence/attributes during authorized debugging.

### 9.3. Spring Fails to Save or Restore `SecurityContext`

For stateful Spring Security Servlet apps, ensure:

- `CasAuthenticationFilter`/custom filter saves the successful Authentication into `SecurityContextRepository`.
- `SecurityContextHolderFilter`/repository loads it on the next request by session.
- `SessionCreationPolicy.STATELESS` or `NullSecurityContextRepository` is not unintentionally active on the CAS browser chain.
- The login success handler does not invalidate the session or clear SecurityContext right after validation.
- A valid session fixation strategy is used without invalidating the session after saving and losing state.
- Multiple filter chains do not let callback succeed on chain A while `/private` runs on chain B with a different repository.
- Spring Session/Redis/JDBC has compatible serializers/versions and a shared session store.
- Account status/roles/business authorization are not confused with CAS validation failure: **CAS success followed by HTTP 403** can be local authorization, not a CAS ticket error.

In Spring Security 6/7, custom authentication filters may require an **explicit save**. `CasAuthenticationFilter` Javadoc provides `setSecurityContextRepository`. Verify behavior for your exact version rather than copying old Spring Security 5 config without checking session persistence.

### 9.4. Why Should You Not Retry ST When Session Is Lost?

If CAS validation **succeeded** yet the app failed to save `JSESSIONID`, reusing ST-1 in the browser causes CAS to return `INVALID_TICKET` because ST-1 is single-use. **Fix the local session**, then initiate a **new login flow with a new ST**. Never replace sessions by caching STs in the browser.

Spring includes `StatelessTicketCache` for certain **proxy ticket/stateless** integrations, yet that is a specialized pattern and **does not replace `HttpSession` for browser CAS login**. Do not enable ticket caching broadly to work around validation failures.

## 10. Observability Method: Capturing Traces Without Leaking Tickets

### 10.1. Minimal Trace of One Login Attempt

Record under one **`traceId`**:

~~~text
01 CLIENT GET /private
   app-authenticated=false
   app-session-present=false

02 APP 302 Location: https://sso.example.test/cas/login?service=<redacted>
   serviceFingerprint=svc-a3b2

03 CAS 302 Location: https://portal.example.test/login/cas?ticket=<REDACTED>
   issuedServiceFingerprint=svc-a3b2

04 CLIENT GET /login/cas?ticket=<REDACTED>
   callbackMatchedCasFilter=true
   appSessionPresent=true/false

05 APP -> CAS /serviceValidate
   validationServiceFingerprint=svc-c7d9
   ticketRef=opaque-hmac-ref

06 CAS -> APP authenticationFailure code=INVALID_SERVICE

07 APP failureHandler -> 302 CAS login
   loginRedirectCount=2
~~~

**Service fingerprint** and **ticketRef** here are illustrative formats, not real SHA-256 outputs from logs. In production, if ST correlation is needed, use an **HMAC with a dedicated observability-only key** over the ticket ID and keep a very short TTL; avoid raw tickets or unsalted hashes that allow unintended correlation. For `service`, log an **approved configuration alias** or non-sensitive canonical service ID per policy.

### 10.2. Three `service` Values Needed for Comparison

| Point | Value Needed |
| --- | --- |
| `/cas/login?service=...` | **`S_issue`**: `service` CAS receives to issue the ticket |
| Browser callback URL | **`S_callback`**: where ST is actually delivered; compare against `filterProcessesUrl` |
| `/cas/serviceValidate?service=...` | **`S_validate`**: `service` the app sends to CAS to validate |

**If `S_issue != S_validate`** → investigate **`INVALID_SERVICE`**.  
**If `S_callback` is not handled by the CAS filter** → investigate **routing/filter/entrypoint loop**.  
**If `service` + validation succeed yet session fails to persist** → investigate **Cookie/SecurityContext/session store**.

Do not look only at the browser's `Location` and assume that is the `service` the validator uses; validation is a **server-to-server call** and can use a different value.

### 10.3. HTTP 302 Chain: Browser/Network Trace or Test Tools

In a **test environment without real credentials**, you can observe:

~~~bash
curl --head --max-redirs 0 \
  "https://portal.example.test/private"
~~~

`curl -I` sends HEAD, so filter behavior may differ from GET in some apps. This is useful to inspect the entrypoint `Location`, yet **does not reproduce full browser cookie/SSO loops**. Browser DevTools HAR captures it better; **redact `ticket`, cookies, and auth params** before sharing.

You can run:

~~~bash
curl --location --max-redirs 6 \
  --output /dev/null \
  --write-out 'redirects=%{num_redirects} final=%{http_code}\n' \
  "https://portal.example.test/private"
~~~

Run only against **test environments/URLs** or authorized targets, and avoid verbose logging so authentication tickets in `Location` are not recorded. Redirect count alone does not identify the CAS fault; correlate with CAS logs/app logs.

### 10.4. Extreme Caution When Calling CAS Validation Manually

Protocol-level example (contains no real ticket):

~~~text
GET /cas/serviceValidate
    ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
    &ticket=ST-FRESH-TEST-TICKET
~~~

This is a request template, not a valid ST. Because validation **consumes the ticket**, running `curl`/Postman directly with an **ST from a browser currently logging in** will cause that browser login to fail immediately afterward. Use only **fresh STs in an authorized test fixture/realm**, and fetch a **fresh ST** for every test.

Avoid:

- Saving raw tickets in shell history, CI logs, proxy access logs, screenshots, or bug trackers.
- Copying an ST from a production HAR into a shared terminal.
- Sending `ticket` to an APM platform outside data-privacy boundaries.
- Testing batches of tickets; STs are sensitive credentials.
- Calling `/serviceValidate` twice with the same ST and treating the second failure as the original root cause.

## 11. Hypothesis-Driven Diagnosis: Rapid Branching

| First Signal | Hypothesis | Next Check | Remediation |
| --- | --- | --- | --- |
| **`INVALID_SERVICE`** on first try | `S_issue != S_validate` | Compare decoded service strings, public URL, path | Align `ServiceProperties.service` and callback |
| **`INVALID_TICKET`** after `INVALID_SERVICE` | Ticket already consumed | CAS timeline by `ticketRef` | Mint a fresh ST after fixing `service` |
| **`INVALID_TICKET`** on first try | Replay/expired/renew/unknown | CAS ticket store/expiry/client logs | Isolate the exact root cause |
| **`INVALID_TICKET`** when `renew=true` | Ticket from SSO rather than primary login | `sendRenew` at login and validation | Align fresh-auth flow per policy |
| **`INVALID_TICKET_SPEC`** with PT | Wrong ticket type/validation endpoint | Check PT/ST and `/proxyValidate` | Use the right protocol endpoint |
| "Application Not Authorized" at CAS login | Service registry mismatch | CAS registered services/regex | Fix registry for public callback |
| CAS validation SUCCEEDS yet loops | Session/cookie/SecurityContext fails to persist | `Set-Cookie` vs. next `Cookie`; repository | Fix session store/cookie attributes |
| No call to `/serviceValidate` | CAS filter missed ticket | Callback route/matcher/filter chain | Fix `filterProcessesUrl`/ordering |
| `/login/cas` returns 302 to CAS before validate | Callback intercepted by auth/redirect | Chain matcher, route, saved request | Let CAS filter handle callback properly |
| Browser stays on CAS login, no callback | CAS SSO/TGC/cookie/login policy | CAS auth logs/cookie domain, MFA/renew | Fix CAS-side cookie/webflow |
| 302 http↔https | Forwarding TLS config | `Location` URLs / trusted proxy headers | Fix trusted external URL scheme |
| One node works, another fails | Config/session/ticket registry inconsistency | Compare node versions/keys/caches | Sync configuration/shared store |
| Fails after logout | CAS SSO vs. app session lifecycle | SLO events, logout redirect | Design logout to match expectations |
| 403 after CAS success | Local user/role issue | `UserDetailsService` / authorities | Fix business authorization; do not alter ST |
| Stateless API reuses ST | No session, ST is single-use | `TicketValidator` usage/caching | Use an auth scheme suited for APIs |

**One 302 chain can involve multiple concurrent causes.** Prioritize evidence from the **first validation attempt**; downstream errors like "ticket unknown" after consumption are secondary symptoms.

## 12. Standalone Java 17: Simulating CAS Error Codes and Redirect Loops

The code below is a **Java 17 program runnable via `javac`/`java`**, needing no Spring, CAS Server, network, or certificates. It models CAS rules:

- The registry holds two **permitted services**.
- Every minted ST binds to its **exact service**.
- `validate` removes the ticket from the store **immediately on any validation attempt**.
- When `service` differs, it returns **`INVALID_SERVICE`** and the ticket is still consumed.
- Repeating the same ticket returns **`INVALID_TICKET`**.
- Expired, unknown tickets, `renew=true` without primary login, and missing parameters are rejected.
- A proxy ticket sent to `/serviceValidate` is not accepted as an ST.
- Two separate redirect loop simulations: repeated service mismatch, and **CAS success while the app fails to keep the session cookie**.
- Properly configured cases complete login in one redirect cycle.

**Warning:** this is a **mock protocol state machine**; it does not mint real STs, connect to CAS, or perform real authentication. Exact `service` checking illustrates **strict matching**, whereas a real CAS Server may have configurable service matching strategies. `sessionCookiePersists` simulates browser/session outcomes, not a cookie parser. This code is **not a production CAS client and must not be used as an `AuthenticationProvider`**.

File **`CasFailureDiagnosticsDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CasFailureDiagnosticsDemo {
    static final String PUBLIC_SERVICE =
        "https://portal.example.test/login/cas";
    static final String ALTERNATE_SERVICE =
        "https://reports.example.test/login/cas";
    static final Instant NOW = Instant.parse("2026-11-07T10:00:00Z");
    static final Duration TICKET_TTL = Duration.ofMinutes(5);

    record Ticket(String issuedService, Instant createdAt,
                  boolean primaryLogin, boolean proxyTicket) {}
    record Check(String code, boolean accepted) {
        static Check error(String code) {
            return new Check(code, false);
        }
        static Check success() {
            return new Check("AUTHENTICATION_SUCCESS", true);
        }
    }

    static final class MockCas {
        final Set<String> registeredServices =
            new HashSet<>(Set.of(PUBLIC_SERVICE, ALTERNATE_SERVICE));
        final Map<String, Ticket> tickets = new HashMap<>();
        int sequence;

        String issue(String service, boolean primary, Instant now) {
            if (!registeredServices.contains(service)) return null;
            String id = "ST-LAB-" + (++sequence);
            tickets.put(id, new Ticket(service, now, primary, false));
            return id;
        }
        String issueProxy(String service, Instant now) {
            if (!registeredServices.contains(service)) return null;
            String id = "PT-LAB-" + (++sequence);
            tickets.put(id, new Ticket(service, now, true, true));
            return id;
        }
        Check validate(String ticketId, String validationService,
                       boolean renew, Instant now, String endpoint) {
            if (ticketId == null || ticketId.isBlank()
                    || validationService == null
                    || validationService.isBlank()) {
                return Check.error("INVALID_REQUEST");
            }
            // CAS service tickets have single-use validation semantics.
            Ticket ticket = tickets.remove(ticketId);
            if (ticket == null) return Check.error("INVALID_TICKET");
            if (now.isBefore(ticket.createdAt())
                    || !now.isBefore(ticket.createdAt().plus(TICKET_TTL))) {
                return Check.error("INVALID_TICKET");
            }
            if (!ticket.issuedService().equals(validationService)) {
                return Check.error("INVALID_SERVICE");
            }
            if (ticket.proxyTicket()
                    && "/serviceValidate".equals(endpoint)) {
                return Check.error("INVALID_TICKET_SPEC");
            }
            if (renew && !ticket.primaryLogin()) {
                return Check.error("INVALID_TICKET");
            }
            return Check.success();
        }
    }

    static final class LocalApp {
        final MockCas cas;
        final String validationService;
        int serviceValidationFailures;
        int casRedirects;
        boolean sessionCookiePersists;
        boolean authenticatedSession;

        LocalApp(MockCas cas, String validationService,
                 boolean sessionCookiePersists) {
            this.cas = cas;
            this.validationService = validationService;
            this.sessionCookiePersists = sessionCookiePersists;
        }

        boolean visitProtectedResource(int maxCycles) {
            for (int i = 0; i < maxCycles; i++) {
                if (authenticatedSession) return true;
                casRedirects++;
                String newTicket = cas.issue(PUBLIC_SERVICE, false, NOW);
                Check check = cas.validate(newTicket, validationService,
                    false, NOW.plusSeconds(i + 1), "/serviceValidate");
                if (!check.accepted()) {
                    serviceValidationFailures++;
                    continue;
                }
                // A successful CAS validation is not enough if the
                // local SecurityContext/session cookie never persists.
                if (sessionCookiePersists) {
                    authenticatedSession = true;
                }
            }
            return authenticatedSession;
        }
    }

    static void expect(String label, boolean value) {
        System.out.println(label + "=" + value);
    }

    public static void main(String[] args) {
        MockCas cas = new MockCas();
        String valid = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("validTicketAndServiceAccepted",
            cas.validate(valid, PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").accepted());
        expect("sameTicketReplayIsInvalidTicket",
            "INVALID_TICKET".equals(
                cas.validate(valid, PUBLIC_SERVICE, false, NOW,
                    "/serviceValidate").code()));

        String mismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("wrongServiceFirstInvalidService",
            "INVALID_SERVICE".equals(
                cas.validate(mismatch, ALTERNATE_SERVICE, false, NOW,
                    "/serviceValidate").code()));
        expect("mismatchConsumesTicket",
            "INVALID_TICKET".equals(
                cas.validate(mismatch, PUBLIC_SERVICE, false, NOW,
                    "/serviceValidate").code()));

        String wrongScheme = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("httpHttpsMismatch",
            "INVALID_SERVICE".equals(cas.validate(wrongScheme,
                "http://portal.example.test/login/cas", false, NOW,
                "/serviceValidate").code()));

        String wrongPath = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("pathMismatch",
            "INVALID_SERVICE".equals(cas.validate(wrongPath,
                "https://portal.example.test/app/login/cas",
                false, NOW, "/serviceValidate").code()));

        String trailingSlash = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("trailingSlashMismatch",
            "INVALID_SERVICE".equals(cas.validate(trailingSlash,
                PUBLIC_SERVICE + "/", false, NOW,
                "/serviceValidate").code()));

        String queryMismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("queryMismatch",
            "INVALID_SERVICE".equals(cas.validate(queryMismatch,
                PUBLIC_SERVICE + "?lang=vi", false, NOW,
                "/serviceValidate").code()));

        String hostMismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("hostMismatch",
            "INVALID_SERVICE".equals(cas.validate(hostMismatch,
                "https://portal-internal.example.test/login/cas",
                false, NOW, "/serviceValidate").code()));

        String expired = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("expiredTicketRejected",
            "INVALID_TICKET".equals(cas.validate(expired,
                PUBLIC_SERVICE, false, NOW.plusSeconds(301),
                "/serviceValidate").code()));

        String refreshed = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("freshTicketAfterConfigRepairAccepted",
            cas.validate(refreshed, PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").accepted());

        String notRenewed = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("renewRequiresPrimaryAuthentication",
            "INVALID_TICKET".equals(cas.validate(notRenewed,
                PUBLIC_SERVICE, true, NOW,
                "/serviceValidate").code()));

        String renewed = cas.issue(PUBLIC_SERVICE, true, NOW);
        expect("renewWithPrimaryAuthenticationAccepted",
            cas.validate(renewed, PUBLIC_SERVICE, true, NOW,
                "/serviceValidate").accepted());

        String proxy = cas.issueProxy(PUBLIC_SERVICE, NOW);
        expect("proxyTicketRejectedByServiceValidate",
            "INVALID_TICKET_SPEC".equals(cas.validate(proxy,
                PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").code()));

        expect("missingTicketInvalidRequest",
            "INVALID_REQUEST".equals(cas.validate(null, PUBLIC_SERVICE,
                false, NOW, "/serviceValidate").code()));
        expect("missingServiceInvalidRequest",
            "INVALID_REQUEST".equals(cas.validate("ST-any", null,
                false, NOW, "/serviceValidate").code()));
        expect("unknownTicketInvalidTicket",
            "INVALID_TICKET".equals(cas.validate("ST-unknown",
                PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").code()));
        expect("unregisteredServiceRejectedAtIssuance",
            cas.issue("https://evil.example.test/callback",
                false, NOW) == null);

        LocalApp wrongApp = new LocalApp(new MockCas(),
            "http://portal.example.test/login/cas", true);
        expect("serviceMismatchCausesLoginLoop",
            !wrongApp.visitProtectedResource(3));
        expect("loopRepeatedCASRedirects",
            wrongApp.casRedirects == 3);
        expect("loopRepeatedValidationFailures",
            wrongApp.serviceValidationFailures == 3);

        LocalApp noCookie = new LocalApp(new MockCas(),
            PUBLIC_SERVICE, false);
        expect("lostApplicationSessionCausesLoop",
            !noCookie.visitProtectedResource(3));
        expect("ticketValidationMaySucceedDuringLoop",
            noCookie.serviceValidationFailures == 0);
        expect("missingCookieRepeatedRedirects",
            noCookie.casRedirects == 3);

        LocalApp healthy = new LocalApp(new MockCas(),
            PUBLIC_SERVICE, true);
        expect("healthySessionStopsRedirects",
            healthy.visitProtectedResource(3));
        expect("healthyLoginUsesOneRedirect",
            healthy.casRedirects == 1);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CasFailureDiagnosticsDemo.java
java CasFailureDiagnosticsDemo
~~~

**Exact stdout** verified with JDK 17:

~~~text
validTicketAndServiceAccepted=true
sameTicketReplayIsInvalidTicket=true
wrongServiceFirstInvalidService=true
mismatchConsumesTicket=true
httpHttpsMismatch=true
pathMismatch=true
trailingSlashMismatch=true
queryMismatch=true
hostMismatch=true
expiredTicketRejected=true
freshTicketAfterConfigRepairAccepted=true
renewRequiresPrimaryAuthentication=true
renewWithPrimaryAuthenticationAccepted=true
proxyTicketRejectedByServiceValidate=true
missingTicketInvalidRequest=true
missingServiceInvalidRequest=true
unknownTicketInvalidTicket=true
unregisteredServiceRejectedAtIssuance=true
serviceMismatchCausesLoginLoop=true
loopRepeatedCASRedirects=true
loopRepeatedValidationFailures=true
lostApplicationSessionCausesLoop=true
ticketValidationMaySucceedDuringLoop=true
missingCookieRepeatedRedirects=true
healthySessionStopsRedirects=true
healthyLoginUsesOneRedirect=true
~~~

### 12.1. Interpreting the Results

- `validTicketAndServiceAccepted=true`: fresh, valid ST for the right service is accepted.
- `sameTicketReplayIsInvalidTicket=true`: second validation of a used ST is rejected.
- `wrongServiceFirstInvalidService=true`: first validation with wrong service returns `INVALID_SERVICE`.
- `mismatchConsumesTicket=true`: after `INVALID_SERVICE`, the same ticket becomes `INVALID_TICKET`.
- `httpHttpsMismatch`, `pathMismatch`, `trailingSlashMismatch`, `queryMismatch`, `hostMismatch`: each service URI variant is rejected by the strict matcher.
- `expiredTicketRejected=true`: ST past TTL is rejected.
- `freshTicketAfterConfigRepairAccepted=true`: fixing `service` requires a **new ticket**.
- `renewRequiresPrimaryAuthentication=true`: an SSO-issued ST does not satisfy `renew` validation in the mock.
- `renewWithPrimaryAuthenticationAccepted=true`: a fresh ST issued after primary auth satisfies `renew`.
- `proxyTicketRejectedByServiceValidate=true`: proxy tickets cannot substitute for STs.
- `missingTicketInvalidRequest`, `missingServiceInvalidRequest`, and `unknownTicketInvalidTicket`: distinguish missing-parameter requests from unknown tickets.
- `unregisteredServiceRejectedAtIssuance=true`: the service registry blocks unknown services **before issuing an ST**.
- `serviceMismatchCausesLoginLoop=true` and `loopRepeatedValidationFailures=true`: loops due to CAS validation failures.
- `lostApplicationSessionCausesLoop=true` and `ticketValidationMaySucceedDuringLoop=true`: loops **even when CAS validation succeeds**, because the local session is not kept.
- `healthySessionStopsRedirects=true`: when both CAS validation and Spring session persistence work, the loop stops.

**Do not treat this output as a test against a real CAS Server.** The demo only models protocol logic to check understanding; integration testing requires a real test server/IdP and the Spring CAS filter/provider.

## 13. Test Matrix: Negative and Positive Controls

| Test | Setup | Expectation |
| --- | --- | --- |
| Baseline fresh ST | CAS login+validation with same service, working app cookie | PASS, Authentication and session persist |
| Wrong scheme | Ticket for HTTPS, validate HTTP | `INVALID_SERVICE` under strict matching |
| Wrong host | Public hostname vs. internal app hostname | `INVALID_SERVICE` |
| Wrong port | 443 vs. 8443 | `INVALID_SERVICE` if identifier mismatches |
| Wrong path | `/login/cas` vs. `/app/login/cas` | `INVALID_SERVICE` |
| Wrong trailing slash | `/login/cas` vs. `/login/cas/` | `INVALID_SERVICE` |
| Query parameter drift | `?lang=vi` added on one side | Mismatch per service matcher |
| Double-encoded service | Browser/validator decode different identifiers | Registry/mismatch error |
| Ticket for another application | CAS ST for service B, validate as service A | `INVALID_SERVICE`; ticket consumed |
| Revalidate same ST | Reuse an already-SUCCEEDED ST | `INVALID_TICKET` |
| Retry ST after `INVALID_SERVICE` | Reuse old ST after fixing URL | `INVALID_TICKET` |
| Fresh ST after fix | Start a new login using the right URL | PASS |
| Expired ST | Wait beyond TTL | `INVALID_TICKET` |
| Unknown ST | Fake/not in registry | `INVALID_TICKET` |
| Missing ticket | `/serviceValidate` without `ticket` | `INVALID_REQUEST` |
| Missing service | `/serviceValidate` without `service` | `INVALID_REQUEST` |
| Renew mismatch | CAS issued from SSO, validation `renew=true` | `INVALID_TICKET` or policy-specific failure |
| Renew primary login | Fresh primary auth + renew policy | PASS if all other conditions hold |
| PT sent to `/serviceValidate` | Wrong ticket type | FAIL, code depends on implementation/spec |
| Service not registered | CAS login receives service outside allowlist | CAS "not authorized"; **do not** call it `INVALID_SERVICE` |
| Duplicate callback | Two filters or two requests validate the same ST | Only one attempt succeeds; subsequent attempt FAILS |
| Two replicas, nonshared CAS ticket store | Ticket minted on node A, validated on node B | FAIL/unknown ticket; fix cluster store |
| CAS TLS trust failed | App fails to verify CAS cert | Fail closed; never disable TLS |
| Filter URL mismatch | Callback misses `CasAuthenticationFilter` | Loop; no validation call |
| Wrong `SecurityFilterChain` | Callback hits another chain | Loop or 404 |
| CAS validation SUCCEEDS, no app cookie | Browser omits `JSESSIONID` | Loop despite valid ST |
| CAS validation SUCCEEDS, context not saved | `NullSecurityContextRepository` | Loop/anonymous subsequent request |
| Wrong cookie `Path` | Session sent on callback, not `/private` | Loop |
| Wrong cookie `Domain` | Host differs across redirects | Loop |
| Spring Session missing across replicas | Cookie exists yet node B cannot restore | Loop |
| CAS TGC blocked | CAS cannot keep SSO state | CAS login/cookie errors; possible loop in CAS |
| http↔https bounce | Incorrect proxy forwarding | Redirect loop before CAS validation |
| Callback URL redirects again | Success handler points back to protected login page | Loop |
| Browser refreshes ticket callback | ST already used | `INVALID_TICKET`, not treated as new login |
| CAS succeeds yet local user disabled | `UserDetailsService`/account status denies | App auth fails; do not weaken policy |
| CAS succeeds yet local 403 | Missing authorities | 403; do not mistake for CAS ticket validation |
| CAS logout yet app keeps session | No SLO/invalidation | May stay locally authenticated |
| App logout yet CAS keeps TGC | App auto-SSO logs in again | Expected per session lifecycles without central logout |
| Request with spoofed credential | Client sends `ticket=ST-fake` | No user created; CAS validation mandatory |

**Every negative test needs an independent fresh ST.** A suite reusing tickets across tests easily produces misleading results because STs get consumed. **Always keep a positive baseline** with the same CAS config so tests do not "pass" merely because every request fails due to SSL/ticket store bugs.

## 14. Spring Integration Testing: Verifying True End-to-End

A proper CAS client test should wire:

1. **Test CAS Server** or an HTTP test server faithfully implementing the CAS protocol with ticket issuance/consumption.
2. Real Spring `CasAuthenticationEntryPoint` and `CasAuthenticationFilter`.
3. `CasAuthenticationProvider` with `Cas20ServiceTicketValidator` pointing to the test CAS endpoint.
4. Browser/HTTP client supporting cookies and redirects, with bounded max redirects.
5. Valid test `service` property, valid callback URL, and a `UserDetailsService` with test users.
6. Tests changing **one variable at a time**: public HTTPS vs. internal HTTP, path/port/query, renew, ticket expiry, duplicate callback, cookie loss.
7. Verification that CAS success genuinely leads to `SecurityContext`/`HttpSession` persisting on the next request.
8. Verification that error handlers route back per policy without unbounded loops.
9. If proxy/ingress exists, test forwarded headers/host reconstruction in a production-like setup.
10. Test CAS SLO/logout separately: app session vs. CAS TGC.

Example **MockMvc skeleton illustrating a callback request**, **not a complete CAS validation test**:

~~~java
// Requires @SpringBootTest, @AutoConfigureMockMvc, and a real test CAS server.
// ticket is a freshly issued ST for the right service; NEVER use a production ST.
MvcResult callback = mockMvc.perform(
    get("/login/cas")
        .param("ticket", freshTestServiceTicket)
        .session(browserSession))
    .andReturn();

// After callback, verify Authentication/session and /private request:
// - ticket validation success -> right user authenticated, right local roles
// - session/cookie persisted
// - protected request does not redirect back to CAS
// - negative ticket creates no new auth
~~~

Never simply use `SecurityMockMvcRequestPostProcessors.user("alice")` to claim the CAS ticket validator works; that bypasses the CAS protocol. And never validate one ST twice across two assertions/calls.

### 14.1. Testing Login Loops with Max Redirects

For HTTP integration clients, set a small **redirect limit**, e.g., 6–10, and assert:

- Normal login stays below the threshold for the environment.
- With wrong service/missing cookie, the test catches the loop instead of hanging.
- Traces distinguish: `validationFailureCount > 0` vs. `validationSuccessCount > 0 but sessionMissing`.
- Browser receives no user authentication when validation fails.
- No tickets/cookies are written into test logs.
- After fixing, a **new login** establishes a persistent session and subsequent requests do not redirect.

**Never increase max redirects unboundedly** to "fix" the error. That is a symptom, not a missing limit.

## 15. Logs/Metrics for Operational Observability

### 15.1. Recommended Events

**CAS ticket validation failure:**

~~~text
event=CAS_TICKET_VALIDATION_FAILED
traceId=trace-73ae
serviceConfigId=portal-public
serviceFingerprint=svc-9fb4
casErrorCode=INVALID_SERVICE
httpCallbackPath=/login/cas
localSessionPresent=false
authPath=CAS_ST
~~~

**Validation succeeded yet session did not persist:**

~~~text
event=CAS_LOGIN_SUCCESS_BUT_SESSION_NOT_RESTORED
traceId=trace-744c
serviceConfigId=portal-public
casValidated=true
sessionCookieObserved=false
securityContextRestored=false
nextRequestPath=/private
~~~

**Redirect loop threshold:**

~~~text
event=CAS_REDIRECT_LOOP_SUSPECTED
traceId=trace-818a
appRedirectToCasCount=5
validationFailureCount=5
validationSuccessCount=0
reason=SERVICE_URL_MISMATCH
~~~

The event/reason names above are **illustrative log designs**, not built-in CAS/Spring log codes.

### 15.2. Metrics to Have

| Metric | Sensible Dimensions | Alert |
| --- | --- | --- |
| `cas_login_redirect_total` | `serviceConfigId`, `environment` | Redirects spike without matching logins |
| `cas_ticket_validate_total{result}` | `success`/`fail`, `protocolErrorCategory` | Spike in `INVALID_SERVICE`/`INVALID_TICKET` rate |
| `cas_ticket_validate_duration` | `casEndpointGroup`, `environment` | Timeout/latency spike |
| `cas_redirects_per_login_flow` | histogram, not ticket ID | Redirect chains too long |
| `cas_success_session_missing_total` | `serviceConfigId`, `node` | CAS succeeds yet no context on next request |
| `cas_ticket_replay_suspected_total` | `environment`/`reason` | Replays/duplicate filters |
| `spring_session_restore_failure_total` | `node`, `storeBackend` | Session cookie present yet auth lost |
| `cas_unauthorized_service_total` | `registeredServiceId` | Service registry mismatch or attack |
| `cas_validation_http_error_total` | `statusGroup`, `tls`/`network` | CAS endpoint/TLS failures |
| `cas_slo_session_invalidate_total` | `integrationType` | Track central logout propagation |

**Never put `ticket`, username/email/`JSESSIONID`, raw service query, or tokens into metric labels**: high cardinality plus privacy/credential leakage risks. Use service config IDs, HTTP error classes, deployment env, and CAS protocol codes.

### 15.3. Controlled Debug Enabling

In staging/test, you can time-box enabling log categories for Spring Security CAS/CAS client/Apereo CAS and the reverse proxy **for your exact version**. `DEBUG` log level never authorizes logging credentials; if a library inadvertently logs full URLs with `ticket=...`, configure redaction at the source/proxy/appender.

Production should log reason codes and correlation references, not leave `TRACE` enabled across all of `org.springframework.security` or all HTTP headers for long periods just to catch one mismatch.

## 16. Real-Incident Resolution Runbook

### Phase A — Isolate Within One Flow

1. Choose an authorized browser/test account; start a **clean session**.
2. Confirm whether the URL sits on the **app or CAS Server**, and which hosts bounce continuously.
3. Capture a **redacted** 302 chain with trace ID, status, `Location` host/path, and `Set-Cookie`/`Cookie` presence.
4. Grab the **first CAS Server validation error** and the Spring client validation outcome for the **first ST**.
5. If no validation call occurs, check **callback path/chain/filter** before digging into CAS tickets.
6. If validation succeeds, jump immediately to the session persistence branch.
7. If a failure code appears, classify via the table in section 3; never assume everything means "wrong password".

### Phase B — If `INVALID_SERVICE`

1. Grab the **service when CAS issued the ST** (`S_issue`) from the CAS login request/log.
2. Grab the **service when `TicketValidator` validated the ST** (`S_validate`) from server-side logs/redacted traces.
3. Compare scheme, public/internal host, port, context path, case, slash, query, and encoding.
4. Check Spring `ServiceProperties.service`, CAS entrypoint, CAS filter URL, and `TicketValidator`.
5. Check CAS registered services: public callback is allowed and matches expectations.
6. Fix app/proxy/metadata at **one source of truth**; never widen regexes indiscriminately.
7. **Mint a new ST** and retest; never reuse an ST that already got `INVALID_SERVICE`.
8. Confirm success + persisted Spring session + protected resource 200/authorized per policy.

### Phase C — If `INVALID_TICKET`

1. Check whether the same ticket was already validated earlier, or if duplicate requests/filters exist.
2. If `INVALID_SERVICE` preceded it, treat the subsequent `INVALID_TICKET` as a secondary effect.
3. Check CAS ticket registry lookup/expiration policy and timestamps.
4. Check `renew=true` on login/validation and primary-auth expectations.
5. Check ST/PT and `/serviceValidate`/`/proxyValidate`.
6. Check CAS Server cluster registry storage/replication/keys; check staging/prod mix-ups.
7. Check browser back/refresh or retries from load balancer/APM/proxy resending the ST.
8. Use a **fresh ST per test**; never extend TTL or disable replay protection.
9. Confirm CAS validation truly succeeds after the fix and local auth is granted.

### Phase D — If Redirect Loop Yet CAS Validation SUCCEEDS

1. Verify the callback filter created `Authentication` and the success handler ran.
2. Verify server `Set-Cookie: JSESSIONID` after success.
3. Verify the browser sends the Cookie with proper `Domain`/`Path`/`SameSite`/`Secure` on the next request.
4. Verify `SecurityContextRepository` saved/restored context.
5. Verify session store/Spring Session/Redis across replicas; check if the request hit a different node.
6. Verify the success redirect did not switch host/HTTP/port and invalidate the cookie.
7. Verify session fixation handler/logout/CSRF filters did not invalidate the session right after login.
8. Verify business authorization: missing local roles can cause 403, not a CAS issue.
9. If cookies/repository are sound yet it still loops, check `SecurityFilterChain` matchers/order and redirect target.
10. Repeat with a fresh browser and fresh ST; a healthy flow redirects to CAS **once** and continues using the app session.

### Phase E — Deployment Check

- Did public hostname, TLS termination, context path, or ingress headers change?
- Did CAS registered service regex/version/priority change?
- Were Spring Boot/Spring Security/CAS client upgraded, changing filter/token classes or behavior?
- Is the CAS Server ticket registry store/cluster/shared cache failing?
- Is the new deployment version rolled out uniformly across all nodes?
- Did cookie `SameSite`/`Domain`/`Path` change due to proxy or app server updates?
- Any session serializer/schema incompatibility during a rolling deploy?
- Did CAS logout/SLO policy change?
- Did `renew` policy or MFA/step-up flow change?
- Does monitoring clearly separate validation failures from session loss?

## 17. Dangerous Anti-Patterns

1. **"On `INVALID_SERVICE`, change all service URLs to regex `.*`."** Wrong: widens the CAS service registry and increases service-spoofing risk.
2. **"Retry the old ticket after fixing config."** Wrong: STs are single-use; mismatches also consume them.
3. **"CAS returning `INVALID_TICKET` means wrong user password."** Wrong: can be replay/expiry/renew/unknown.
4. **"CAS TGC exists, so Spring app must have a session."** Wrong: two cookies with separate lifecycles/domains.
5. **"CAS validation SUCCEEDS yet loops, so restart CAS."** Incorrect: inspect local cookies/repository/proxy.
6. **"Skip TLS verification for CAS URLs to test faster."** Wrong: sends STs/identities over untrusted connections.
7. **"Enable `authenticateAllArtifacts` for all URLs to stop errors."** Unsuitable for stateful browsers and introduces ticket-handling risks.
8. **"Take an ST from a production HAR and curl it repeatedly."** Wrong: exposes credentials and consumes the ST.
9. **"Check only status 302 without checking `Location` and back-channel."** Insufficient to classify loops.
10. **"Any HTTP 200 from `/serviceValidate` means `authenticationSuccess`."** Wrong: CAS `/serviceValidate` can return HTTP 200 with an `authenticationFailure` body.
11. **"CAS login allows a wildcard service, so `INVALID_SERVICE` cannot happen."** Wrong: registry authorization and ticket binding are separate checks.
12. **"If it fails once, let the proxy auto-retry `/serviceValidate`."** Wrong: the ticket is already consumed; retrying fails or skews diagnosis.
13. **"Keep cookie `Secure` while bouncing back to HTTP due to LB path."** Wrong: browsers omit Secure cookies over HTTP; fix the public TLS route.
14. **"Just `permitAll` `/login/cas` to handle the callback."** Insufficient: `CasAuthenticationFilter` must intercept the ticket and validate it, not just `permitAll`.
15. **"On redirect loop, raise `maxRedirects`."** Does not solve the root cause, only prolongs the loop.
16. **"Cache ST like a refresh token."** Wrong: an ST is a single-use service credential.
17. **"Drop `sendRenew` even though business requires primary auth."** Lowers assurance; fix the flow and policy instead of bypassing.
18. **"Saw `/private` 200 after callback so validation succeeded."** Browser might still hold an old `SecurityContext`; tests must verify a fresh user/flow.
19. **"Message 'Application Not Authorized' is the same as `INVALID_SERVICE`."** Wrong: distinguish registry rejection from ticket validation mismatch.
20. **"Put the same CAS filter in two `SecurityFilterChain`s or auto-register twice."** Causes double validation/replay; audit filter registration.
21. **"Use client-supplied `Host`/`X-Forwarded-Proto` to build service URLs."** Opens Host-header spoofing/open redirects; trust proxy only.
22. **"Store full tickets in the observability platform."** Unconsumed tickets are bearer credentials; always redact.

## 18. Operations and Code Review Checklist

- [ ] Confirmed CAS login URL, CAS validation URL, and public Spring callback URL.
- [ ] `ServiceProperties.service` aligns with `CasAuthenticationFilter.filterProcessesUrl` and CAS registered service.
- [ ] EntryPoint and AuthenticationProvider share the same `ServiceProperties` or identical equivalent config.
- [ ] `S_issue`, `S_callback`, and `S_validate` compared within the same flow.
- [ ] `service` URL-encoded once at HTTP layer; no query/slash/port drift.
- [ ] Public scheme/host/port/context path accurate even behind ingress/LB.
- [ ] `Forwarded`/`Host` headers trusted only from verified reverse proxies.
- [ ] CAS service registry allows exact services, not broad wildcards.
- [ ] CAS TLS server certificate verified and transport uses HTTPS.
- [ ] Fresh ST used for **every validation attempt**, never retrying a consumed ST.
- [ ] `INVALID_SERVICE` understood as invalidating the ticket.
- [ ] `INVALID_TICKET` branched into replay/expired/renew/unknown/type/registry.
- [ ] `sendRenew` and fresh-auth policy checked across both CAS login and validation.
- [ ] ST/PT/PGT and `/serviceValidate` vs. `/proxyValidate` kept distinct.
- [ ] CAS filter handles callbacks on the right route and `SecurityFilterChain` without double registration.
- [ ] CAS validation success/failure parsed from XML body, not just HTTP status code.
- [ ] App creates `Authentication` only after CAS validation succeeds, loading local roles/tenant.
- [ ] CAS success paired with `SecurityContextRepository` saving to a stateful session.
- [ ] Spring session cookie exists and is sent back by the browser on protected requests.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` and public host tested.
- [ ] Spring Session/Redis/JDBC/replica configs are consistent.
- [ ] Session fixation/logout/SLO do not prematurely wipe sessions.
- [ ] Runbook covers redirect loops before CAS, at CAS, at callback, and after CAS success.
- [ ] E2E tests enforce a max-redirect cap instead of hanging infinitely.
- [ ] Tests cover wrong service, mismatch→invalid_ticket, expired, renew, replay, and unknown ticket.
- [ ] Tests cover CAS success with missing cookie/SecurityContext to distinguish from validation failure.
- [ ] Positive baseline and fresh ST verified when retesting after fixes.
- [ ] Logs/metrics include CAS protocol error category and service config ID.
- [ ] Never log raw tickets, TGC, `JSESSIONID`, user credentials, or full validation URLs.
- [ ] Registry, public URL, and session cookie changes reviewed and regression-tested.

## 19. Self-Check Questions

**1. Are CAS `INVALID_SERVICE` and "Application Not Authorized" the same?**

No. `INVALID_SERVICE` means **the service bound to the ticket does not match the service used at validation**; "Application Not Authorized" usually means the CAS service registry rejected the service URL at login.

**2. Can an ST that just received `INVALID_SERVICE` be re-validated with the right URL?**

No. The CAS protocol requires **invalidating the ticket after any validation attempt**, including mismatches. The next attempt normally returns `INVALID_TICKET`.

**3. Why can a browser bounce endlessly between the app and CAS even after CAS authenticated the user?**

Because the app may fail to intercept the ticket, fail validation, or **fail to preserve local `SecurityContext`/`JSESSIONID`**, while the CAS TGC remains active and rapidly mints new STs.

**4. If CAS validation returns `authenticationSuccess` XML yet the browser lands back on `/login/cas`, what do you check first?**

Check **session cookies, `SecurityContextRepository`, success handler/redirect target, and filter chains**. Do not default to blaming CAS.

**5. Should `ServiceProperties.service` point to `/private`?**

Usually no. For default stateful Spring CAS, it should be the **callback URL monitored by `CasAuthenticationFilter`**, e.g., `https://portal.example.test/login/cas`.

**6. Which URI differences easily trigger `INVALID_SERVICE`?**

HTTP/HTTPS scheme, public/internal hostname, port, context path, trailing slash, query parameters, and encoding.

**7. Why does a URL registry regex matching multiple hosts not mean an ST can be used across those hosts?**

The registry governs who **is allowed to use CAS**; each ST is still **bound to a specific service identifier** and must match it during validation.

**8. Does `INVALID_TICKET` always mean a forged ticket?**

No. The ticket may be already used, expired, consumed by a mismatch, missing from the store, or failing `renew`.

**9. Is HTTP 200 from `/serviceValidate` enough to prove login succeeded?**

No. You must read `<cas:authenticationSuccess>` or `<cas:authenticationFailure code=...>` in the body.

**10. How does CAS `renew=true` differ from login retries?**

It demands **primary authentication freshness** rather than reusing a CAS SSO session; validation may reject an ST that fails this check.

**11. Can a proxy ticket be used with `/serviceValidate`?**

Not as an ordinary ST. CAS proxy validation has its own endpoint/rules, and `/serviceValidate` must not return success for a PT.

**12. How do you tell whether a redirect loop is caused by cookies or the CAS protocol?**

If CAS repeatedly returns `authenticationFailure`, fix ticket/service; if CAS repeatedly returns `authenticationSuccess` yet the app stays anonymous on the next request, fix cookies/`SecurityContext`.

**13. Can refreshing the callback URL in a browser cause `INVALID_TICKET`?**

Yes. The ST was already validated once, so refreshing `?ticket=ST-...` is a replay.

**14. Should you raise TTL when tickets frequently expire?**

Only after investigating the root cause and completing a security review. Never use TTL to mask double validation, slow callbacks, or proxy misrouting.

**15. Does local CAS app logout mean the user is logged out of central SSO?**

No. CAS TGC and Spring `JSESSIONID` have separate lifecycles; coordinate Single Logout if required.

**16. Is `http.authorizeHttpRequests(...).permitAll("/login/cas")` alone enough for CAS callbacks to work?**

No. The callback must also be intercepted by **`CasAuthenticationFilter`**, which passes the ST to `TicketValidator` and saves auth/session.

**17. Why do multiple replicas cause `INVALID_TICKET` or redirect loops?**

The CAS ticket registry and Spring session store are two separate layers; an unshared ticket registry causes unknown STs, while an unshared app session causes loops after validation succeeds.

**18. Should Service Tickets be placed into metric labels for debugging?**

No. An ST is a credential and has high cardinality; use redacted/correlation refs with strict retention/authorization.

## 20. Official References

- **Apereo CAS 2.0 Protocol Specification** — `/login`, `/serviceValidate`, `INVALID_SERVICE`, `INVALID_TICKET`, single-use ST, `renew`, and proxy tickets: https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html
- **Apereo CAS Protocol Specification (development docs)** — error codes, CAS ST lifecycle, and endpoints: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- **Apereo CAS Troubleshooting Guide** — "Too many redirects", `INVALID_TICKET`, registered service mismatch, tickets/SSL: https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html
- **Apereo CAS Ticket Validation** — service matching strategy and ticket service binding: https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html
- **Apereo CAS Single Logout** — local application sessions vs. CAS session/TGC, SLO: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
- **Spring Security CAS Authentication** — `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `Cas20ServiceTicketValidator`, proxy/static: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- **Spring Security Javadoc: CasAuthenticationFilter** — `/login/cas` default, service URL, ticket request parameter, and `SecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html
- **Spring Security Javadoc: ServiceProperties** — `service`, `sendRenew`, `artifactParameter`, `authenticateAllArtifacts`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- **Spring Security Javadoc: CasAuthenticationProvider** — `TicketValidator`, `ServiceProperties`, `UserDetailsService`, `userDetailsChecker`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- **Spring Security Javadoc: CasAuthenticationEntryPoint** — CAS login URL, service URL, redirect behavior: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html
- **Spring Security Session Management** — `HttpSession`, `SecurityContextRepository`, fixation, explicit save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- **OWASP Session Management Cheat Sheet** — cookie flags, session fixation, expiration/logout: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- **OWASP Logging Cheat Sheet** — redaction of tokens/secrets and incident-ready logs: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

**Summary:** When seeing **CAS `INVALID_SERVICE`**, compare **the `service` at ST issuance and the `service` at validation**, keeping in mind that a mismatch **already consumed the ticket**. When seeing **`INVALID_TICKET`**, check **single-use/replay, expiration, `renew`, unknown ticket, ticket type, and CAS cluster**, rather than jumping to "wrong password". When seeing a **redirect loop**, first ask **whether CAS ticket validation succeeded**; if not, follow the ticket/service branch; if it succeeded yet Spring remains anonymous, follow the **`JSESSIONID`/`SecurityContextRepository`/session store/filter chain** branch. Always use a **fresh ST when retesting**, keep HTTPS/service allowlists intact, never log credentials, and verify the endpoint is **an app session accessing authorized resources without infinite redirects**.