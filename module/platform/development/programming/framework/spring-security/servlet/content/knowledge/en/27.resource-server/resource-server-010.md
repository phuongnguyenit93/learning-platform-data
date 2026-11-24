# STATELESS, SecurityContextRepository, and CSRF Control by Token Transport

> **Scope:** Spring Security **Servlet** (Spring Boot 3, Spring Security 6, Java 17+), focusing on OAuth2 Resource Servers receiving access tokens. Most importantly: **not creating a session** and **not needing CSRF protection** are two *distinct* claims. Whether CSRF protection is needed depends on **how the browser sends credentials** and which other authentication mechanisms are active—not merely on the keyword `STATELESS` or whether tokens are formatted as JWTs.

## 1. Three Questions You Must Separate

When securing an API, answer these in order:

1. **Credential source:** Is the access token explicitly sent by the client via `Authorization: Bearer ...`, or automatically attached by the browser in cookies / HTTP Basic / client certificates? Does the API accept multiple authentication mechanisms at once?
2. **SecurityContext lifecycle:** After authenticating the current request, where is `Authentication` held for authorization checks? Must it be persisted so the **next** request inherits the identity?
3. **CSRF exposure:** Can a page on another origin cause the victim's browser to automatically send a **currently valid credential** to a state-changing endpoint, even though the attacker does not know the credential?

For example, two systems may both say “we use JWT,” yet differ on CSRF:

| Architecture | How Credentials Travel with Requests | Session / SecurityContext | Browser CSRF Risk |
| --- | --- | --- | --- |
| Mobile or API client sending bearer | `Authorization: Bearer TOKEN` header explicitly attached by client | Per-request authentication; no HTTP session needed | Does not rely on auto-sent browser credentials; usually no CSRF token needed on this pure API chain |
| SPA sending bearer manually | JavaScript adds the `Authorization` header from a held token | Usually stateless server-side | Same as above *if* the API truly accepts bearer headers only; still must guard against XSS, CORS, token leakage |
| Browser holds JWT in a cookie and backend reads the cookie | `Cookie: access_token=...` auto-attached by the browser | May be stateless without an `HttpSession` | **Must evaluate and handle CSRF**; JWTs do not prevent CSRF |
| BFF holds OAuth tokens server-side, browser holds session cookie | Session cookie travels automatically; BFF calls Resource Server with Bearer | BFF typically uses sessions; Resource Server can be stateless | BFF needs appropriate CSRF protection; pure-bearer Resource Server typically does not |
| App combining web login and Resource Server | May receive both `JSESSIONID` and bearer | Depends on chains/filters | Never disable CSRF globally merely because part of the API uses bearer |
| Browser auto-sends cached HTTP Basic or client certificate | Credentials auto-sent by the browser per context | May not use HttpSession | CSRF can still exist even when the server is stateless |

**Initial takeaway:** `SessionCreationPolicy.STATELESS` controls **how Spring Security uses HttpSession** for the SecurityContext; `SecurityContextRepository` controls **where context is loaded/saved**; `CsrfFilter` controls **request forgery protection**. Three tools solve three separate problems.

## 2. Distinguishing JWT, Session, and SecurityContext

### 2.1. A JWT or Opaque Token Is Not a SecurityContext

In an OAuth2 Resource Server, a valid request typically carries the header:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

`BearerTokenAuthenticationFilter` extracts the token, then authenticates via a JWT decoder or opaque token introspector. If valid, Spring Security creates the corresponding `Authentication` and places it in `SecurityContext` for authorization of the **current request**.

- A JWT can self-contain claims and be verified by signature, issuer, expiry, and audience; a JWT **is not** a Servlet `HttpSession`.
- An opaque token is checked via introspection (or a configured mechanism), and likewise needs no `HttpSession` to remember logins.
- `Authentication` in `SecurityContextHolder` is data for security filters and controllers to read permissions for the **current request**; it does not automatically become a persistent session.

A subsequent request must send its own valid token if the API is built stateless. That does not mean access tokens have no “state” on the issuer side: tokens have lifetimes, can be revoked, have signing keys, and relate to permissions/users.

### 2.2. SecurityContextHolder Differs from SecurityContextRepository

- **`SecurityContextHolder`:** API to access the active `SecurityContext` during processing; the default strategy in Servlet apps is typically thread-bound. Spring Security manages setting and clearing the context across the filter lifecycle.
- **`SecurityContextRepository`:** where `SecurityContext` is **loaded** and/or **saved** across processing stages. Depending on implementation, it may store in request attributes, `HttpSession`, or nowhere.
- **`SessionCreationPolicy`:** Spring Security's policy on creating/using `HttpSession`, not a blanket prohibition preventing any application component from calling `request.getSession()`.

Never confuse “context present while processing a request” with “context persisted into `HttpSession`.” A Resource Server needs `Authentication` for the controller, authorization, and auditing of the **in-flight call**; it does not necessarily persist it for the next request.

## 3. What Does SessionCreationPolicy.STATELESS Actually Do?

Familiar configuration:

```java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

Each `SessionCreationPolicy` value means something different:

| Policy | Primary Meaning in Spring Security |
| --- | --- |
| `ALWAYS` | Spring Security actively creates an `HttpSession` |
| `IF_REQUIRED` | Creates an `HttpSession` only when a security mechanism needs one |
| `NEVER` | Never creates an `HttpSession` itself, yet may use an **already existing** session |
| **`STATELESS`** | Spring Security does not create an `HttpSession` and does not use sessions to obtain `SecurityContext` |

**`NEVER` is not `STATELESS`.** For instance, if other servlet code creates a session first, `NEVER` can let Spring Security reuse that session; `STATELESS` aims to authenticate requests without depending on an existing session.

### 3.1. STATELESS Does Not Guarantee “No Cookies”

Seeing `JSESSIONID` in the browser despite `STATELESS` is not proof that Spring Security ignored the policy. A session can be created by MVC, JSP, another servlet, a library, a custom filter, session-backed CSRF mechanisms, or application code. Investigate **which component triggers session creation**, rather than blaming every cookie on the Resource Server.

At the same time, **never rely on one `STATELESS` line to assume session authentication is eliminated from every filter**. When an app enables web-style authentication, custom filters, or multiple filter chains, audit all active mechanisms.

### 3.2. STATELESS Does Not Automatically Disable CSRF

A request may use no `HttpSession` at all while the browser still auto-attaches a **cookie holding a JWT**, letting attackers exploit cross-site requests. Thus:

```text
JWT + no HttpSession + credential in cookie
                      !=
                 CSRF immunity
```

Conversely, a Resource Server requiring client-attached bearer headers may not need CSRF tokens, **while still needing** JWT validation, scope/permission checks, proper CORS, HTTPS, and token leakage protections.

### 3.3. STATELESS Does Not Make Logout Revoke Tokens

With per-request bearer authentication:
- Deleting a session cookie or invalidating an `HttpSession` **does not** revoke an issued JWT.
- A client can delete its local access token on logout, yet a stolen token remains usable until expiration, revocation, or blocking via token-state controls.
- Choose short TTLs, refresh-token rotation, revocation/introspection, key management, audience, and scopes per your threat model.

## 4. SecurityContextRepository: Where Is Context Loaded/Saved?

Important Spring Security Servlet implementations:

| Implementation | Where Stored / Looked Up | When Appropriate | Limitations |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession` | Web logins needing Authentication preserved across requests | Unsuitable for remembering tokens in stateless bearer APIs |
| `RequestAttributeSecurityContextRepository` | Attributes of **one HTTP request** | Preserves context across dispatch phases of the same request (e.g., error dispatch) | Does not persist identity to the next HTTP request |
| `NullSecurityContextRepository` | Neither persists nor returns saved context | When you never want Authentication loaded/saved via a repository | Does not persist context across requests or dispatches |
| `DelegatingSecurityContextRepository` | Combines multiple repositories | Servlet setups using both request attributes and sessions per config | Must understand which child repository is actually used |

In standard Spring Security 6 web configurations, the repository may be a `DelegatingSecurityContextRepository` combining request attributes and sessions; Resource Server mechanisms may store context for the **current request**. **Never assume a single default repository across all filters and all versions/configs.** Verify against the actual running chain.

### 4.1. SecurityContext Lifecycle in a Stateless Resource Server

```text
Request #1
Authorization: Bearer TOKEN
    |
    v
BearerTokenAuthenticationFilter
  -> resolver reads token
  -> AuthenticationManager / JWT decoder authenticates
  -> SecurityContextHolder holds Authentication
  -> authorization -> controller
  -> security filter cleanup
    |
    v
Response #1

Request #2
(no Authorization sent)
    |
    v
Does NOT inherit Request #1's bearer Authentication
    |
    v
Route requiring authenticated -> typically HTTP 401
```

Authentication working in Request #1 does not require creating an `HttpSession`. For a Resource Server, each request must be verified from the token sent on that request.

### 4.2. SecurityContextHolderFilter and Explicit Save

Spring Security 6 favors `SecurityContextHolderFilter`, which reads context from `SecurityContextRepository`. Under the explicit-save model, this filter **does not automatically save** `SecurityContext` when a request finishes; if you write a custom stateful login flow, your custom authentication code must call the repository's `saveContext(...)` when context should persist to subsequent requests.

**Illustrative API snippet for custom stateful login** (not a configuration for pure Bearer APIs):

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

Here `authenticated` must be a genuinely authenticated `Authentication` object, and `securityContextRepository` must be the repository configured for the filter chain. The snippet above belongs **inside an authentication handler that has request/response**; it cannot run standalone since variables must be supplied. Never save a bearer token's context into a session just to process subsequent requests “faster”—doing so turns the architecture stateful and can introduce cookie-based ambient credentials.

### 4.3. Should You Force NullSecurityContextRepository?

Only with a clear requirement and verified filter lifecycle behavior. Example configuration expression:

```java
http.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository())
);
```

This is an **illustrative snippet**, using `org.springframework.security.web.context.NullSecurityContextRepository`. Not every application needs to declare it: `STATELESS` already expresses the intent not to rely on `HttpSession` for context, and request-attribute storage can be useful for internal dispatches without making the API stateful. Forcing a null repository can affect error dispatches or custom filters. **Prefer minimal, tested configuration** rather than replacing every security context component solely to feel “more stateless.”

## 5. CSRF Depends on Token Transport, Not Token Type

### 5.1. How Does CSRF Work?

A victim is logged in to `bank.example.test`. An attacker-controlled page tricks the browser into sending a request to `bank.example.test`. If **the browser automatically attaches credentials** (such as a session cookie) and the endpoint accepts state-changing actions without proper CSRF checks, the request can execute as the victim. The attacker does not even need to read the response; causing the side effect is enough.

```text
User is logged in to the app
  -> browser holds auto-sent cookie/credential
  -> user opens attacker page
  -> attacker triggers cross-site POST to the app
  -> browser may auto-send credential (per cookie policy/SameSite)
  -> server authenticates as victim
  -> without CSRF protection, action may be executed
```

The crux is **ambient authority**: credentials automatically travel with requests. `SameSite` rules, `Origin`/`Referer`, CORS, CSRF tokens, and endpoint structure all contribute to defense; no single factor replaces all other security requirements.

### 5.2. Client-Attached Bearer Headers

When an API authenticates access tokens exclusively from:

```http
Authorization: Bearer ACCESS_TOKEN
```

An attacker page on another origin cannot guess the access token to fill the header; browsers do not automatically grab JavaScript-held tokens from the victim's app to attach to arbitrary requests. Therefore, **cookie-style CSRF normally does not apply in the same way** to chains accepting only bearer headers.

However, all of these conditions must hold:
- The server **does not** accept session cookies or JWT cookies to authenticate the **same endpoints**.
- No other browser auto-sent mechanism is accepted by the server, such as browser-cached HTTP Basic or client certificates.
- CORS is not treated as an authorization system; the API must still validate bearer tokens, scopes, and issuer/audience.
- Client-side tokens are protected against XSS and risky extensions; if an attacker steals the token, that is **token theft**, needing no CSRF.
- Tokens are not placed in URL/query/form fallbacks that inadvertently expose credentials.

**CSRF can still be disabled specifically for a bearer-only API** once these conditions are verified, instead of disabling it across the entire application.

### 5.3. JWT in a Cookie: CSRF Can Still Happen

An API can decode JWTs from `Cookie: access_token=...` without creating any `HttpSession`. Yet cookies are automatically sent by browsers whenever cookie rules match. Hence attackers can abuse the browser to send credentialed requests. `HttpOnly` prevents JavaScript from reading the cookie via `document.cookie`, **not** the browser from attaching the cookie to requests. `Secure` requires HTTPS, **not** CSRF prevention. `SameSite` mitigates some cross-site requests, yet depends on browser context and site/origin boundaries—it does not replace evaluating state-changing endpoints.

If choosing cookies for credentials:
- Design proper CSRF defenses (synchronizer tokens, properly implemented double-submit, architectural origin validation).
- Carefully configure `Secure`, `HttpOnly`, `SameSite`, and domain/path.
- Never perform state-changing side effects on `GET`.
- Mitigate XSS because XSS can issue valid same-origin requests even without reading `HttpOnly` cookies.

### 5.4. BFF and Session Cookies

With a **Backend-for-Frontend**, the browser sends a session cookie to the BFF; the BFF stores access tokens server-side and calls downstream Resource Servers with bearer headers. The two tiers have different policies:

```text
Browser --(session cookie; CSRF protection)--> BFF
BFF     --(Authorization: Bearer; token validation)--> Resource Server
```

- **BFF:** receives auto-sent browser credentials; typically keeps CSRF protection for state-changing actions and manages session cookies.
- **Resource Server:** if it authenticates only bearer headers from the BFF and supports no cookie authentication, it can use STATELESS and disable CSRF **on the pure-bearer chain**.
- That **does not** mean the BFF or external-facing APIs may disable CSRF.

### 5.5. Hybrid Environments: Multiple Mechanisms in One Application

An app has web login at `/account/**` and a bearer API at `/api/**`. If a single configuration applies `csrf(csrf -> csrf.disable())` globally, profile-update forms using session cookies lose CSRF protection. Instead, split **SecurityFilterChains by matcher** or apply conditional CSRF protection based on **the exact endpoints and active authentication mechanisms**.

**Principle:** identify every authentication mechanism accepted by a chain; never use “endpoint is REST/JSON” or “token is a JWT” as the sole criterion to disable CSRF.

## 6. Spring Security 6 Servlet Configuration: Separating Bearer API and Web Session

Example using Spring Boot 3, Java 17+, with dependencies `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-boot-starter-oauth2-resource-server`. The classes below must sit inside a package scanned by the application's `@SpringBootApplication`. They are **not** single-file classes compilable with bare `javac`; Spring Boot and dependencies supply the container and filter chain.

**Critical security assumption:** every `/api/**` path **accepts bearer tokens from `Authorization` only**, using no cookies/sessions/HTTP Basic/client certificates for authentication. If your real API accepts any auto-sent credentials, **do not copy `csrf.disable()` verbatim**.

### 6.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .csrf(csrf -> csrf.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // DO NOT disable CSRF on webChain.
        // Spring Security keeps default CSRF protection for web.
        return http.build();
    }
}
```

Meaning of each decision:

1. `@Order(1)` + `securityMatcher("/api/**")` gives the API chain an explicit scope running ahead of the fallback web chain. `@Order(2)` handles remaining requests. Leave no sensitive route outside both chains.
2. `STATELESS` avoids using `HttpSession` to obtain `SecurityContext` for the API. Each API request requires a valid bearer token or a `permitAll` route.
3. `NullRequestCache` avoids storing “pre-login requests” for the API flow using a request cache meant for web sessions, reducing unintended session creation.
4. `csrf(csrf -> csrf.disable())` **appears only in the API chain** under the bearer-header-only assumption. It is not automatically implied by `STATELESS`.
5. `formLogin(...disable())` and `httpBasic(...disable())` turn off two common authentication mechanisms outside the API's bearer-only contract. If the app has custom filters, continue auditing them.
6. `oauth2ResourceServer(...jwt(...))` enables the bearer token filter and JWT validation. A valid JWT does not guarantee permission; matchers require `SCOPE_orders.read`/`SCOPE_orders.write`.
7. `webChain` retains form login and default CSRF protection; web POST requests must include a valid CSRF token.
8. Scope rules in this example are illustrative. Default Spring Security Resource Server typically maps JWT `scope`/`scp` values to authorities prefixed with `SCOPE_`; if your Authorization Server uses another claim schema, configure a converter and test it.

**No magic from stateless:** cookies sent by a browser to `/api/**` may still appear on the wire, yet if the API chain accepts only bearer headers as assumed, those cookies **are not used to authenticate**. Verify this with integration tests in your real application.

### 6.2. JWT Issuer and JWK Configuration

File `application.yml` (illustrative values; replace with real issuer/JWK):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/protocol/openid-connect/certs
```

Declaring `jwk-set-uri` directly can avoid querying issuer metadata at startup; token and issuer verification per configuration is still required. In real products use trusted URLs and validate signature, timestamps, issuer, audience, and appropriate scopes. **Audience validation** for an API does not automatically come from knowing `issuer-uri`; implement a dedicated validator when required.

This configuration does not govern CSRF. CSRF decisions follow from **the credential mechanisms accepted by each chain**.

### 6.3. Illustrative Controller for Testing

File `DemoController.java`:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders";
    }

    @PostMapping("/api/orders")
    public String createOrder() {
        return "created";
    }

    @PostMapping("/account/update")
    public String updateAccount() {
        return "updated";
    }
}
```

These endpoints return static text solely to highlight differences in **security policy**; they mutate no real data. Because `/account/update` belongs to `webChain`, POST requires both authentication **and** a CSRF token. Because `/api/orders` belongs to `apiChain`, POST requires a valid bearer token and authority `SCOPE_orders.write`, without requiring a CSRF token under the bearer-only assumption.

### 6.4. If the Application Truly Has Only One Bearer API

You can use a single `SecurityFilterChain` instead of two: enable `STATELESS`, bearer Resource Server, an appropriate request cache, and disable CSRF when the entire application is genuinely **bearer-header-only**. Conversely, if HTML logins or session cookies exist, keep a separate web chain or design tailored rules. Never apply one template blindly to every system.

## 7. CSRF Protection in the Web Session Chain

In applications using session cookies, Spring Security Servlet uses `CsrfFilter` to check tokens on unsafe HTTP methods (typically POST/PUT/PATCH/DELETE). By default, safe methods such as GET, HEAD, TRACE, and OPTIONS are not blocked by the CSRF filter; **that does not permit GET to cause side effects** and does not replace other method controls.

Example Thymeleaf form using Spring Security CSRF support:

```html
<form action="/account/update" method="post">
  <input type="hidden"
         th:name="\${_csrf.parameterName}"
         th:value="\${_csrf.token}" />
  <button type="submit">Update</button>
</form>
```

This is a **Thymeleaf template**, not already-rendered static HTML. Spring Security must supply the CSRF token to the request and the app must configure MVC/Thymeleaf accordingly. The template engine substitutes the token's parameter name and value; the browser submits it in the form body. Without Thymeleaf, the application must explicitly supply the matching token in a hidden field or header.

Spring Security 6 uses lazy CSRF tokens and request handlers to mitigate BREACH in certain setups; never simply assume “opening a GET page always guarantees a session and visible cookie token.” For SPAs using cookies and AJAX, examine `CookieCsrfTokenRepository` along with the appropriate request handler and token delivery, especially when using `X-XSRF-TOKEN`. Never disable token masking/XOR or `HttpOnly` just to “fix” an AJAX error without understanding the risks.

### 7.1. A CSRF Token Is Not an Access Token

- An access token authenticates an API caller and its granted scopes.
- A CSRF token proves a state-changing request originated from an approved context per the app's CSRF defense.
- Never put an access token into a hidden `_csrf` field or URL.
- Never treat a “signed JWT” as a CSRF token; they solve two different security problems.

When browsers use sessions/BFFs, CSRF defense remains essential even when the BFF uses OAuth access tokens server-side.

## 8. Testing with MockMvc and Spring Security Test

Add the appropriate test dependencies, such as `spring-boot-starter-test` and `spring-security-test`. File `SecurityPolicyTests.java` (in the same package as the Spring Boot application or a test-scanned package):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPolicyTests {
    @Autowired
    MockMvc mvc;

    @Test
    void noBearerOnProtectedApiReturns401() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedApiPostDoesNotNeedCsrfToken() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void authenticatedButInsufficientScopeReturns403() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionPostWithoutCsrfReturns403() throws Exception {
        mvc.perform(post("/account/update").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/account/update")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }
}
```

Meaning:
- Test 1 verifies the protected API rejects anonymous requests.
- Test 2 proves the **API chain** does not require CSRF when given a simulated JWT authentication with the needed authority.
- Test 3 proves stateless does not mean every valid JWT may perform every action; authorization can return 403.
- Tests 4–5 verify the **web chain** is unaffected by disabling CSRF on the API: session POSTs require a CSRF token.

**Important limitation:** `jwt()` in Spring Security Test is a request post-processor simulating JWT authentication; it tests authorization and filter chain interaction, **not whether the JWT decoder verified a real signature, whether BearerTokenResolver extracted a token from `Authorization`, or whether the issuer is reachable**. To test real tokens, write integration tests with a decoder/test key or test Authorization Server and test through the HTTP Bearer header.

If the test class and config sit in the proper package, `DemoController` endpoints exist, and auth chains match properly, the five tests above produce the expected results. There is no separate business stdout. Run in a Maven/Gradle project with the corresponding dependencies, e.g.:

```bash
mvn -Dtest=SecurityPolicyTests test
# Or:
./gradlew test --tests SecurityPolicyTests
```

### 8.1. Testing That Cookies/Sessions Do Not Authenticate the API by Mistake

To confirm `csrf.disable()` is truly safe, add end-to-end tests on the real system:
1. Log in through the web chain and retain a valid session cookie.
2. Call `POST /api/orders` **with only the session cookie**, sending no bearer token.
3. Expect the API chain **not to use that session cookie to authenticate**; the request must be rejected (typically 401 in this example).
4. Call the same endpoint with a valid bearer token carrying scope `orders.write` and confirm it succeeds.
5. If the cookie-only request succeeds, the bearer-only assumption is broken: **never disable CSRF** on that endpoint until the authentication source is fixed.

Likewise, test other auto-sent credentials such as browser-cached HTTP Basic, client certificates, or custom authentication filters if supported by the system.

### 8.2. Testing SecurityContextRepository and Real Sessions

For a stateless API, verify:
- Request A sends a valid token → authentication is established within Request A.
- Request B sends no token → **does not inherit** authentication from A, even if the browser holds cookies created by another component.
- No session is created **by the API security mechanism** to remember auth; use dev logging/instrumentation to track down whichever component creates `HttpSession` if `JSESSIONID` unexpectedly appears.
- Requests going through error dispatch/forward are tested with an appropriate repository if the application needs the principal during error flows.

Note: tests themselves may create sessions due to test post-processors or web-chain mechanics, so do not declare “stateless API FAILED” solely because an `HttpSession` appears in the test harness. Trace the actual code path and session creation source.

## 9. Manual HTTP: Distinguishing 401, 403, and CSRF Errors

Assuming the app runs at `http://localhost:8080` with the mappings above:

```bash
# Protected API without Authorization => typically 401.
curl -i http://localhost:8080/api/orders

# Invalid test token: resolver may extract the string,
# yet JWT validator typically rejects => 401.
curl -i http://localhost:8080/api/orders \
  -H 'Authorization: Bearer invalid-token'

# No valid credential: POST cannot succeed;
# API chain does not require CSRF, yet still requires authentication.
curl -i -X POST http://localhost:8080/api/orders

# Web endpoint requiring login session and CSRF token.
# Sending an anonymous POST is typically blocked, without proving
# specifically whether it was a CSRF or authentication error.
curl -i -X POST http://localhost:8080/account/update
```

When tested with `jwt()` or real tokens, you can distinguish clearly: **no token → 401**, **valid token lacking scope → 403**, **web session POST missing CSRF token → 403**. The last two can both be 403 yet originate from **two completely different mechanisms**.

**Never put real tokens in URLs or shell history.** When testing bearer tokens, prefer CI/test secret handling, avoid shared logs, and restrict access to request-header logs.

## 10. API Design Decision Table

| Condition | Suggested Session Policy | SecurityContextRepository / Persistence | CSRF |
| --- | --- | --- | --- |
| Resource Server accepts bearer header only, no auto-auth | `STATELESS` | Do not persist context in `HttpSession`; auth every request | Can be disabled on the **bearer-only chain** |
| Browser session form login | `IF_REQUIRED` or suitable web policy | `HttpSessionSecurityContextRepository`/appropriate delegate | **Keep** CSRF protection on unsafe methods |
| BFF receives session cookie, downstream bearer | BFF stateful by design; downstream usually `STATELESS` | BFF stores auth/server-side tokens safely; downstream auths every call | **BFF needs CSRF**; downstream bearer-only evaluated separately |
| JWT read from cookie in sessionless API | Can be `STATELESS` | Does not necessarily use `HttpSession` | **Still needs** CSRF defenses suited to cookies |
| API accepts both cookie login and bearer | Depends on specific chain | Must inspect where both sources load/persist | Do not disable globally; split chains or enforce exact CSRF rules |
| Service-to-service via bearer header | Usually `STATELESS` | Do not persist context across requests | Browser CSRF normally inapplicable, yet TLS, token validation, and authorization still needed |
| App uses HTTP Basic in browsers | May not use sessions | Context usually does not need session persistence | Still evaluate CSRF since browsers auto-send cached Basic credentials |

**How to choose:** ask “which credentials are accepted by the server on this endpoint and can a browser attach them automatically?” before choosing `csrf.disable()`. Then ask “must authentication be preserved for the next request?” to pick the session policy and repository.

## 11. Common Mistakes and Fixes

1. **“We use JWT so CSRF is impossible.”** False if the JWT sits in an auto-sent cookie. Evaluate token transport and browser auto-auth.
2. **“Setting STATELESS makes Spring Security disable CSRF automatically.”** False: session policy and the CSRF filter are separate configurations.
3. **“Disable CSRF app-wide because /api uses Bearer.”** False when form/session pages still exist. Split matchers/chains and keep CSRF for web routes.
4. **“NullSecurityContextRepository means controllers won't see Authentication.”** False: the current request's authentication can still reside in `SecurityContextHolder`; the repository governs loading/saving across stages/requests.
5. **“RequestAttributeSecurityContextRepository is a session.”** False: request attributes are scoped to a single request/dispatch, not persisted across independent requests.
6. **“STATELESS guarantees the server never emits JSESSIONID.”** False if another library/app/filter creates a session; trace the source instead of blaming one config line.
7. **“HttpOnly cookies prevent CSRF.”** False: `HttpOnly` prevents scripts from reading cookies, not browsers from auto-sending cookies when conditions match.
8. **“SameSite eliminates all risk.”** False: inspect site boundaries, browser behavior, state-changing endpoints, and actual CSRF policy.
9. **“CORS replaces CSRF tokens.”** False: CORS governs response readability and certain browser cross-origin requests; it is neither an authorization system nor a universal CSRF replacement.
10. **“A valid Bearer token grants access to every API.”** False: you need scopes/authorities, audience, ownership checks, and business authorization.
11. **“Logging out of a session revokes the JWT.”** False: stateless bearer tokens need short TTLs, revocation/introspection, and dedicated token lifecycles.
12. **“MockMvc .with(jwt()) tests JWT signature verification.”** False: that mocks authentication; test the JWT decoder / real tokens independently.

## 12. Implementation and Review Checklist

- [ ] Document every authentication source accepted by each `SecurityFilterChain`: Authorization Bearer, session cookie, cookie JWT, Basic, client certificate, custom filters.
- [ ] Use `STATELESS` only where identity need not persist via `HttpSession`; verify subsequent requests do not inherit previous Authentication.
- [ ] Understand where `SecurityContext` is loaded/saved; never confuse `SecurityContextHolder` with `SecurityContextRepository`.
- [ ] For bearer-only APIs, ensure form login, HTTP Basic, and session auth are not accidentally active on the same chain.
- [ ] Disable CSRF only on endpoints whose credentials **are never auto-sent by browsers** and after auditing all other auth mechanisms.
- [ ] For web/BFF/cookie authentication, retain proper CSRF protection, `Secure`/`HttpOnly`/`SameSite` cookies, and no unsafe GETs.
- [ ] Never rely solely on CORS or JWT signing to mitigate CSRF.
- [ ] Ensure issuer, signature, expiry, audience, and scopes/ownership are properly validated.
- [ ] Use an appropriate request cache for APIs; avoid accidentally storing saved requests or login state in sessions.
- [ ] Maintain unit/integration tests separating 401 missing token, 403 insufficient scope, 403 CSRF, CORS preflight, and cookie-only requests.
- [ ] Verify session creation, error dispatches, and context persistence with any custom filters.
- [ ] Have a logout/revocation/rotation strategy; never assume stateless automatically revokes credentials.

**Final takeaway:** `STATELESS` is a decision about **using HttpSession**, `SecurityContextRepository` is a decision about **saving/loading SecurityContext**, while CSRF depends on **whether the browser automatically attaches credentials to requests**. A pure `Authorization: Bearer` Resource Server typically runs stateless and may omit CSRF tokens; however, JWTs in cookies or BFF/session cookies **still require** proper CSRF protection.
