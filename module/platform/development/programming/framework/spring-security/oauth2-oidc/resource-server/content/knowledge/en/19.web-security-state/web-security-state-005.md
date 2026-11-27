# CSRF Based on How the Browser Sends Credentials

In **Spring Security OAuth 2.0/OIDC Resource Server**, whether an API needs CSRF protection **cannot be decided merely by saying "the API uses JWT," "stateless," or "CORS is enabled."** The more important question is:

> **Does the browser automatically attach a credential that the server accepts when another site causes it to send a request?**

If the browser has a session cookie, a JWT cookie, cached HTTP Basic credentials, or another credential automatically sent by the browser, an attacker can exploit an unintended user request. If the Resource Server only accepts access tokens in **Authorization: Bearer** **explicitly** attached by trusted JavaScript code or a non-browser client, and the browser does not automatically send any other credential accepted by the API, the traditional CSRF model generally does not apply in the same way.

**CSRF is an issue of credential-sending behavior and trust boundaries**, not merely whether a token is JWT or opaque. This lesson analyzes browser/sessions, cookies, SPAs, BFFs, OAuth2 Login, Spring Security's CSRF filter, configuration, and testing to choose the right policy for each architecture.

## 1. What does CSRF exploit?

**Cross-Site Request Forgery (CSRF)** occurs when an untrusted site causes a user's browser to send a request to a system where the user is logged in, and the server processes that request under the user's identity even though the action was not intended by the user.

Suppose a user is logged into **https://shop.example.com**, and the server issued a cookie:

~~~http
Set-Cookie: JSESSIONID=session-abc; Path=/; Secure; HttpOnly; SameSite=None
~~~

Another site can contain a form:

~~~html
<form action="https://shop.example.com/account/email"
      method="POST">
  <input name="newEmail" value="example@attacker.example">
  <button type="submit">Continue</button>
</form>
~~~

This HTML illustrates the mechanism in a learning environment. When the user submits the form, the browser may send the request to Shop and **automatically attach JSESSIONID** if cookie policy permits. If the server relies solely on the session cookie for authentication, checks neither origin nor CSRF token, and accepts the form data, the action can execute under the victim's identity.

The attacker **does not need to know the cookie value**. The browser itself automatically sent the credential.

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant S as Shop API
    participant X as Untrusted Site
    U->>B: Log into Shop
    B->>S: Valid POST login
    S-->>B: Set-Cookie session
    U->>B: Open external site
    B->>X: Load content
    X-->>B: Form/action targeting Shop
    B->>S: POST + session cookie if policy permits
    Note over S: No CSRF protection
    S-->>B: Updates data with user's privileges
~~~

A CSRF attack requires both conditions: the browser sending the credential and the server accepting the state-changing request. **SameSite**, token requirements, and request origin checks can block these links in the chain. However, do not assume the browser always sends cookies: consider **SameSite**, cookie domain/path, navigation type, credentials mode, and browser policies.

### 1.1. Same-Origin Policy does not automatically block all CSRF

The Same-Origin Policy normally prevents scripts on another site from **reading the response** from Shop. Yet **not being able to read the response differs from not being able to send the request**. The browser can still perform cross-origin form submissions or other requests under certain conditions.

Therefore, a request can alter server state **even when the attacker cannot read the JSON response**.

## 2. Why how the browser sends credentials matters more than token format?

Distinguish two types of credential transmission:

**Automatic credentials (ambient credentials):** the browser manages a cookie or authentication mechanism and sends it automatically when a request matches the criteria. The attacker's page does not need access to the credential value to make the browser send the request.

**Client-explicitly-attached credentials:** application JavaScript code, a native client, a CLI, or a backend explicitly sets a header containing a token. A browser does not automatically grab a token stored in a JavaScript variable on one origin and inject it into a cross-site form on another origin.

| Architecture | Does browser auto-send credential on matching requests? | Must evaluate CSRF? |
|---|---|---|
| Web app logged in with **JSESSIONID** | Yes, depending on cookie policy | **Yes** |
| JWT stored in **HttpOnly cookie**, API reads cookie | Yes | **Yes** |
| BFF using session cookie, holding OAuth tokens server-side | Yes | **Yes**, at browser → BFF |
| OAuth2 Login then using session cookie for business ops | Yes | **Yes** |
| Refresh token cookie and refresh endpoint using cookie | Yes | **Yes**, for that endpoint |
| HTTP Basic credentials cached and auto-sent by browser | Possibly | Must evaluate |
| Browser-managed TLS client certificate | Possibly | Must evaluate |
| SPA explicitly adding **Authorization: Bearer** from in-memory token | Not in the cookie/form manner | Usually no CSRF token needed if **no** ambient authentication exists |
| CLI/mobile explicitly setting Bearer header | Unrelated to browser auto-sending | Outside browser CSRF model |
| JWT Resource Server with custom resolver reading JWT from cookie | Yes | **Yes** |
| API supporting both Bearer header and session cookie | Cookie can be used | **Yes** on cookie-accepting endpoints |

**JwtDecoder** and **OpaqueTokenIntrospector** resolve **access token validity**. They do not by themselves prove **the user intentionally initiated the request from the browser**.

## 3. Explicit Bearer headers and JWT cookies are not the same

### 3.1. Bearer token in header placed by frontend

Example of an SPA holding an access token in state/memory and explicitly calling the API:

~~~javascript
async function createOrder(accessToken, order) {
  return fetch("/api/orders", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + accessToken,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(order)
  });
}
~~~

Application code **explicitly** adds the Authorization header. An HTML form from another website does not know `accessToken` and cannot make the browser insert that JavaScript variable into a request.

**The safety condition must be stated completely:** the server **only** accepts tokens in the Authorization header and does not accept browser session cookies/Basic/certificates as substitute authentication. If a cookie authentication fallback remains, CSRF risk returns.

Nor should you conclude this SPA is immune to XSS: malicious JavaScript running in the real origin can use the token or submit actions itself. CSRF tokens do not replace XSS defenses.

### 3.2. JWT in a cookie is still sent like a cookie

~~~http
Set-Cookie: ACCESS_TOKEN=jwt-value; Path=/; Secure; HttpOnly; SameSite=None
~~~

If a custom filter or **BearerTokenResolver** extracts the JWT from a cookie, the browser can send the credential automatically. The fact that the JWT is validly signed with RS256 **does not prove the user intended to make the request**.

**JWT + stateless + HttpOnly cookie can still require CSRF protection.**

### 3.3. HttpOnly and Secure solve different problems

- **HttpOnly** helps prevent JavaScript from accessing the cookie via `document.cookie`; it does not stop the browser from sending the cookie.
- **Secure** restricts sending the cookie over secure channels.
- **SameSite** restricts sending the cookie in certain cross-site contexts.
- **CSRF token** requires a value explicitly sent by the client in a form/header, which does not appear automatically just because the browser holds a session cookie.

A session cookie should be protected with Secure/HttpOnly and appropriate cookie scoping, yet these attributes do not by themselves replace CSRF tokens on sensitive endpoints.

## 4. SameSite: important, but does not replace CSRF policy

Example session cookie:

~~~http
Set-Cookie: JSESSIONID=example; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| SameSite | General effect | Limitations |
|---|---|---|
| **Strict** | Sends cookie in same-site contexts | Can break navigation flows arriving from external sites |
| **Lax** | Sends in same-site and some cross-site top-level navigations using safe methods | Does not protect if GET performs dangerous actions |
| **None** | Allows cross-site cookies where browser conditions permit | Modern browsers require **Secure** |

Many browsers apply default behavior similar to Lax when a cookie omits SameSite, though you must not depend on default nuances across every browser/version. Some default Lax implementations have a brief exception for POSTs on newly set cookies.

### 4.1. Same-site differs from same-origin

Example:

~~~text
https://app.example.com
https://api.example.com
https://untrusted.example.com
~~~

These are different origins yet may belong to the same **site** under schemeful site rules. If one subdomain is controlled by an untrusted party, **SameSite** is no longer a tight enough boundary to block all requests from that subdomain.

Therefore evaluate the cookie **Domain** and subdomain scope. Host-only cookies or prefixes like **__Host-** can help restrict cookie scope where appropriate.

### 4.2. Never use GET to change state

Spring Security by default does not require a CSRF token for **GET, HEAD, TRACE, OPTIONS**, because HTTP semantics consider them safe methods.

If an application writes:

~~~text
GET /orders/42/cancel
GET /account/delete
GET /logout
~~~

and GET directly performs state-changing actions, CSRF can occur via multiple paths. Replace them with appropriate POST/DELETE methods, combined with authorization checks and CSRF policy. **SameSite=Lax** still sends cookies on certain top-level navigations using GET.

## 5. CORS does not by itself solve CSRF

**CORS** primarily governs whether browser JavaScript from another origin can make certain cross-origin requests and **read the response**. It does not replace verifying request intent.

An HTML form POST with a simple content type can be sent cross-origin by the browser without reading the response. When the server uses cookie authentication and accepts form requests, **blocking reading the JSON response does not stop server state from being modified**.

### 5.1. Preflight and custom headers

Cross-origin JavaScript requests containing **Authorization**, **X-CSRF-TOKEN**, or non-simple content types typically trigger a CORS preflight. If the server does not allow that origin, the browser blocks the request per the CORS model.

This is a useful defense layer, yet has limitations:

- Form submissions can send requests without preflight.
- The server might accept additional content types or method overrides.
- CORS configuration might allow untrusted origins.
- A same-site subdomain can still be a different origin.
- CORS is not a session/CSRF token verification mechanism.

### 5.2. credentials in fetch

~~~javascript
fetch("https://api.example.com/orders", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ item: "book" })
});
~~~

**credentials: "include"** allows the browser to attach matching credentials if cookie policies and browser constraints permit. It does not guarantee every cookie is sent, but serves as a reminder that an SPA can use **cookie authentication** even when requests originate from JavaScript.

**Never open Access-Control-Allow-Origin broadly alongside credentials.** Verify the origin allowlist and preflight according to your real frontend architecture.

## 6. CsrfFilter in Spring Security Servlet

Spring Security provides **CsrfFilter** to check CSRF tokens on HTTP methods considered unsafe. CSRF protection is enabled by default in common web `SecurityFilterChain` configurations.

Processing flow:

~~~mermaid
flowchart TD
    R[HTTP request] --> C[CsrfFilter]
    C --> M{Method needs CSRF validation?}
    M -->|No| P[Continue SecurityFilterChain]
    M -->|Yes| L[Load expected CsrfToken]
    L --> T[Read token from header/form parameter]
    T --> V{Token matches expected token?}
    V -->|No or missing| D[AccessDenied / typically 403]
    V -->|Yes| P
    P --> A[Authentication and Authorization]
    A --> H[Controller / Domain policy]
~~~

This is a logical diagram; actual filter ordering and exception handling depend on configuration.

### 6.1. Related components

| Component | Function |
|---|---|
| **CsrfFilter** | Selects requests to check, compares tokens, rejects missing/invalid ones |
| **CsrfToken** | Header/parameter name and token value |
| **CsrfTokenRepository** | Generates/saves/loads expected tokens |
| **HttpSessionCsrfTokenRepository** | Stores CSRF token in HttpSession; common default |
| **CookieCsrfTokenRepository** | Stores expected token in a cookie to support SPAs |
| **CsrfTokenRequestHandler** | Exposes token to views and reads token submitted in requests |
| **XorCsrfTokenRequestAttributeHandler** | Masks tokens to mitigate BREACH; modern Spring Security default |
| **AccessDeniedHandler** | Handles missing/invalid CSRF tokens |

**CsrfFilter does not verify JWT signatures.** JWT/opaque tokens must be processed independently by a trusted `JwtDecoder` or `OpaqueTokenIntrospector`.

### 6.2. Unsafe HTTP methods

With the default matcher, `CsrfFilter` typically ignores **GET, HEAD, TRACE, OPTIONS** and requires tokens for **POST, PUT, PATCH, DELETE** and other unsafe methods.

Although TRACE is considered safe for the CSRF matcher, applications should usually disable TRACE for other security reasons. Most importantly, **never mutate business state via GET**.

### 6.3. Deferred tokens and BREACH

In Spring Security 6+, CSRF token loading is deferred until needed; tokens exposed by the default request handler may be **masked with randomness** to reduce BREACH risk.

Consequently, an SPA reading a raw CSRF token from a cookie must use an appropriate handler rather than blindly copying server-rendered form patterns into an SPA without accounting for token masking differences.

## 7. Synchronizer Token Pattern

The standard principle is that **the server requires an unpredictable value not automatically attached by the browser just because a cookie exists**.

Process:

1. Server generates a token bound to the session/protection context.
2. Token is delivered to the real application's form or UI securely.
3. Browser sends the session cookie automatically, **but the form/JS must explicitly send the CSRF token as well**.
4. Server compares the submitted CSRF token with the expected token; missing or mismatched → reject.

~~~mermaid
sequenceDiagram
    participant B as Legitimate App Browser
    participant S as Spring Security
    B->>S: GET /profile + session cookie
    S-->>B: Page containing token in form
    B->>S: POST /profile + session cookie + hidden _csrf
    S->>S: Verify token matches session
    S-->>B: Continue if other policies pass
~~~

### 7.1. Hidden form field

~~~html
<form action="/profile" method="post">
  <input name="displayName" value="Example">
  <input type="hidden"
         name="_csrf"
         value="token-created-by-the-server">
  <button type="submit">Save</button>
</form>
~~~

The value must be generated/injected into the view by the server, never hardcoded. View integrations like Thymeleaf and Spring form tags can add the token automatically when configured properly.

### 7.2. A CSRF cookie alone is not enough

The browser also sends CSRF cookies automatically. If the server only checks that the cookie **exists**, an attacker benefits from the browser sending that cookie automatically.

The server must verify the submitted token in the **hidden field or header** via the repository/handler. With a custom double-submit cookie pattern, guard against cookie injection and bind tokens to the session—such as signed session-bound tokens when the design calls for it.

## 8. Websites with session/form login: keep CSRF enabled

For web apps using **JSESSIONID** and form login, Spring Security normally enables CSRF protection by default.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**csrf(Customizer.withDefaults())** states the policy explicitly; in many Servlet configurations you do not need to write it since CSRF is enabled by default.

If a form POST gets 403 due to a missing CSRF token, **do not fix it by disabling CSRF globally**. Ensure the form includes the token and the session/token remains valid.

### 8.1. Login and logout also involve CSRF

- **Login CSRF** can log a victim's browser into an unintended account or corrupt the identity flow.
- **Logout CSRF** can let an attacker force a victim to log out. When CSRF protection is on, Spring Security normally uses **POST /logout** with a CSRF token instead of GET logout.
- Account linking, email change, password reset, and other sensitive endpoints must be evaluated against the browser credential/threat model.

A public URL marked **permitAll** does not mean POST requests to that URL bypass `CsrfFilter`.

## 9. SPAs and BFFs using cookies: CSRF tokens are still needed

An SPA may call an API using a session cookie or a BFF cookie:

~~~text
Browser holds HttpOnly session cookie
  -> JavaScript sends POST /api/orders
  -> Browser automatically attaches cookie
  -> JavaScript also sends X-CSRF-TOKEN or X-XSRF-TOKEN
  -> Server verifies token
~~~

### 9.1. CookieCsrfTokenRepository

Spring Security supports:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Common names:

~~~text
Cookie: XSRF-TOKEN
Header: X-XSRF-TOKEN
Form parameter: _csrf
~~~

**withHttpOnlyFalse()** is used when the frontend truly needs JavaScript to read the CSRF cookie. **Never do this for session cookies or access token cookies** just because CSRF is needed. If the frontend receives the CSRF token via server-rendered HTML or another mechanism, a JavaScript-readable CSRF cookie may not be necessary.

### 9.2. Raw tokens and BREACH masking must match the version

Spring Security 6 uses **XorCsrfTokenRequestAttributeHandler** by default. When a server-rendered form submits a masked token, the handler decodes it; whereas an SPA reads the raw token from the cookie and sends **X-XSRF-TOKEN**.

Therefore Spring Security documents an **SPA-specific request handler**, distinguishing raw headers from masked form parameters and refreshing the CSRF cookie after authentication/logout. Setting `CookieCsrfTokenRepository` alone is not necessarily sufficient across all versions/integrations.

In **Spring Security 7.0+**, configuration can use:

~~~java
http.csrf(csrf -> csrf.spa());
~~~

**spa()** configures the appropriate SPA components per Spring Security 7 documentation. **Do not copy it to Spring Security 6 if the method does not yet exist.** With Boot 3/Security 6, follow the manual recipe in the matching version's documentation.

### 9.3. JavaScript sending the CSRF header

~~~javascript
async function updateProfile(csrfToken, profile) {
  return fetch("/api/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(profile)
  });
}
~~~

This example assumes the frontend already obtained a valid CSRF token. Cross-origin requests need credentials and CORS configured appropriately for the architecture rather than opened arbitrarily. **The token value sent in the header** is what differs from the auto-sent session cookie.

## 10. OAuth2/OIDC Login: state, nonce, and PKCE do not replace post-login CSRF

In Authorization Code/OIDC Login:

- **state** binds authorization requests/responses and helps prevent login CSRF/response mix-up per design.
- **nonce** binds the ID Token to the authentication request when OIDC is used.
- **PKCE** binds the authorization code to the client's code verifier.
- **redirect_uri** and issuer/client validation protect other boundaries.

These mechanisms do not automatically protect:

~~~text
POST /account/change-email
POST /orders/approve
POST /logout
POST /auth/refresh
~~~

if the browser accesses them using a session cookie or ambient credentials.

For example, a user logs in via OAuth2 Login, and the application retains **JSESSIONID** for business operations. After login, **POST /account/change-email** can still need a CSRF token, even though the earlier authorization code flow had state/nonce/PKCE.

### 10.1. Refresh token cookies

If the browser stores a refresh token in an HttpOnly cookie, the **/auth/refresh** endpoint is invoked with an auto-attached cookie. Evaluate CSRF for this endpoint based on the effects of refreshing/rotating sessions/tokens, alongside CORS, caching, token rotation, and replay protection.

Do not exclude all **/auth/** URLs from CSRF under a broad rule merely because they are "authentication endpoints."

## 11. BFF: examine the two legs separately

A Backend for Frontend keeps OAuth2 access tokens/refresh tokens on the server while the browser only holds a session cookie.

~~~mermaid
flowchart LR
    B[Browser] -->|Auto-sent session cookie| F[BFF]
    F -->|Explicitly attached Bearer header| R[Resource Server]
    F <-->|Server-side OAuth protocol/tokens| A[Authorization Server]
~~~

**Browser → BFF leg:** cookies are auto-sent; POST/PUT/DELETE actions carry CSRF risk and normally need CSRF protection.

**BFF → Resource Server leg:** the BFF explicitly attaches Authorization Bearer. If the Resource Server accepts no ambient browser credentials, its CSRF threat model differs.

A flawed argument is **"the BFF does not give access tokens to the browser, so there is no CSRF."** The browser still holds a login cookie for the BFF, requiring proper protection at the browser-facing boundary.

## 12. Pure Bearer-header Resource Server: when can CSRF be disabled?

Disabling `CsrfFilter` on an API-only chain can be considered if **all relevant conditions are verified**:

1. The API authenticates solely via Bearer tokens in the **Authorization header** explicitly sent by clients.
2. The API does not use **JSESSIONID** or any cookie as a login credential.
3. The API does not read JWT/opaque tokens from cookies via a custom resolver/filter.
4. The API accepts no browser-managed HTTP Basic or client-certificate authentication as a substitute.
5. The API has no fallback session authentication when the Authorization header is missing.
6. Login/refresh/logout/BFF endpoints using ambient credentials live in another chain and remain protected.
7. Requests with only a cookie and no Bearer header **are rejected**.
8. JWT/opaque token checks and authorization remain active.
9. CORS, XSS, token storage, TLS, and security headers are evaluated independently.

Example **Bearer-only** Servlet JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerOnlySecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Only after confirming the chain has no ambient credentials.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Do not copy this snippet into a cookie-authenticated app.** It only illustrates the policy of **one API chain** after analyzing the proper threat model.

### 12.1. STATELESS does not by itself protect against CSRF

**SessionCreationPolicy.STATELESS** tells Spring Security not to use `HttpSession` to save/retrieve `SecurityContext` under that policy. It **does not stop browsers from sending cookies** and **does not stop a custom filter from reading a JWT from a cookie**.

A backend that saves no session yet accepts a JWT cookie still has an ambient credential. CSRF protection must be decided from actual authentication behavior.

### 12.2. Opaque tokens follow the same principle

With:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

if tokens are always explicitly placed in the Authorization header by clients, the CSRF conclusion matches Bearer-only JWT. **JwtDecoder** and **OpaqueTokenIntrospector** differ in verification method, not in whether browsers auto-send credentials.

### 12.3. Disabling CSRF does not mean disabling authentication

When disabling CSRF on a Bearer-only chain, the Resource Server must still:

- Check trusted issuer, key/signature, or introspection endpoint.
- Check audience, exp/nbf, token type/profile per policy.
- Check scope/authority and tenant/ownership permissions.
- Reject missing, forged, expired, or under-privileged tokens.
- Protect credentials with HTTPS and never log raw tokens.

Never use `csrf.disable()` to "fix" `401 invalid_token` or `403 insufficient_scope`.

## 13. Hybrid systems: SecurityFilterChains along credential boundaries

An application may serve both a Bearer-only API and a session-cookie UI. In that case, separate the security chains.

Principle example:

~~~text
@Order(1) /api/**:
  JWT Bearer header only
  stateless
  CSRF disabled per verified threat model
  Scope/authority authorization

@Order(2) /web/**:
  Form login/OAuth2 Login
  HttpSession and session cookie
  CSRF enabled

@Order(3) fallback:
  Deny unhandled requests or apply designed policy
~~~

Configuration pattern:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/web/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Example limitation:** the **/web/** chain only illustrates matchers and policy, and does not fully configure login pages, OIDC callbacks, logout, or error/static routes. When using default `formLogin`, login/logout URLs must fall inside the right chain or be reconfigured; do not copy this template straight into production.

**FilterChainProxy selects the first matching chain**, rather than merging policies. If the same endpoint accepts both cookie sessions and Bearer headers, never drop CSRF merely because the endpoint can handle Bearer tokens.

## 14. Selectively ignoring CSRF differs from bypassing all of Spring Security

Spring Security allows skipping CSRF checks for specific requests:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/integration/webhook/**"));
~~~

However, verify that endpoint **does not authenticate using browser-ambient credentials**, while having other appropriate protections (such as HMAC signatures and replay protection for webhooks). Excluding from CSRF **does not authenticate the endpoint**.

Distinguish:

- **csrf.ignoringRequestMatchers**: skips only CSRF validation on matching requests; other filters/authorization still run.
- **web.ignoring().requestMatchers**: bypasses the Spring Security filter chain far more broadly, potentially skipping authentication/authorization altogether.
- **permitAll()**: skips authorization without requiring authentication, yet **CsrfFilter can still require a token for POST**.

Never use **web.ignoring** to fix CSRF errors on business endpoints.

## 15. Token repositories: Session vs. Cookie

### 15.1. HttpSessionCsrfTokenRepository

~~~java
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository()));
~~~

The expected value lives in `HttpSession`, fitting server-rendered forms. If the session expires, the CSRF token from an older page becomes invalid, causing 403; the application should handle session-timeout UX properly rather than disabling validation.

### 15.2. CookieCsrfTokenRepository

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

This snippet covers **only the repository**, not a complete SPA recipe for Spring Security 6. With raw tokens from cookies and masked tokens from the BREACH handler, configure an appropriate request handler and refresh the token after authentication/logout.

Never put CSRF tokens in URLs, query strings, or referer-prone locations. Avoid logging raw session cookies, access tokens, and CSRF tokens.

## 16. Origin, Referer, and Fetch Metadata as defense-in-depth

Additional layers can help mitigate CSRF:

| Mechanism | Effect | Limitations |
|---|---|---|
| **Origin validation** | Compares request origin against an allowlist | Origin may be missing/null depending on request; needs fallback policy |
| **Referer validation** | Can help when Origin is absent | Can be stripped by browser/privacy policies |
| **Sec-Fetch-Site** | Distinguishes same-origin, same-site, cross-site | Not always sent by clients; same-site subdomains may not be trusted |
| **SameSite=Lax/Strict** | Reduces cross-site cookie-sending scenarios | Does not protect every path, especially misused GET semantics |
| **Strict Content-Type** | Reduces ability of simple forms to hit JSON-only handlers | Insufficient if server supports other content types, method overrides, or flawed CORS |
| **CSRF token** | Requires an unpredictable value sent explicitly | Must be protected from XSS/leaks with proper lifecycle handling |

Never compare origins using naive string suffix checks, never trust forwarded proxy headers from arbitrary clients, and never assume every browser sends Fetch Metadata.

## 17. CSRF and XSS are two different problems

**CSRF:** attacker cannot read the credential yet causes the browser to send it automatically.

**XSS:** attacker executes JavaScript inside the application's origin. That script can:

- Read CSRF tokens exposed in the DOM or JavaScript-readable cookies.
- Send requests with valid CSRF headers.
- Read access tokens stored anywhere JavaScript can reach.
- Perform actions under the victim's session.

Therefore, CSRF tokens **do not fully protect when XSS exists**, and HttpOnly cookies **do not by themselves prevent CSRF**. Combine template escaping/output encoding, CSP, dependency hygiene, proper cookie policies, and Bearer token protection.

## 18. Testing CSRF with Spring Security MockMvc

Spring Security Test provides the **csrf() request post-processor** for Servlet MockMvc.

Assume controller **POST /web/profile** exists and returns **204 No Content** upon successful update:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

// In a test class with real MockMvc and SecurityFilterChain.
@Test
void postWithoutCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
}

@Test
void postWithValidCsrfPassesFilter() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isNoContent());
}

@Test
void postWithInvalidCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
}
~~~

This is an illustrative CSRF/authorization test, not a complete test class. Returning **204** depends on the controller, auth policy, and fixtures. The core value is distinguishing **missing/invalid CSRF tokens** from **valid tokens**.

### 18.1. MockMvc jwt() does not automatically disable CsrfFilter

Spring Security Test supports **jwt()** to build a mock Authentication. If you call:

~~~java
mockMvc.perform(post("/api/orders").with(jwt()));
~~~

on a chain **where CSRF is still enabled**, the request may return **403 due to a missing CSRF token**. That does not prove JWTs always require CSRF; it simply reflects **that chain's policy in the test**.

When testing a Bearer-only API with CSRF disabled per threat model, use that exact security configuration to test scopes/authorities, and add integration tests with a real Authorization header to test `JwtDecoder`.

### 18.2. Testing real browser scenarios

Beyond MockMvc, test:

1. Cookie-authenticated POST missing CSRF → rejected.
2. CSRF token belonging to wrong session → rejected.
3. Valid cookie and CSRF token → passes `CsrfFilter`.
4. Bearer-only API without token → rejected.
5. Bearer-only API with `JSESSIONID`/cookie only → **does not authenticate**.
6. Forged JWT signature or wrong issuer/audience → rejected.
7. Valid JWT missing scope → rejected by authorization.
8. SameSite/CORS behavior on real origins/public URLs.
9. OIDC Login, logout, refresh cookies, BFF endpoints.
10. Exact `SecurityFilterChain` `@Order` and matchers.

**Do not use `MockMvcBuilders.standaloneSetup`** without Spring Security filters or **`@AutoConfigureMockMvc(addFilters=false)`** to draw conclusions about production CSRF.

## 19. Distinguishing 401, 403 from CSRF, and 403 from scope

| Request | Decision source | Typical result |
|---|---|---|
| POST with session cookie but missing CSRF | **CsrfFilter** | **403** |
| POST with session cookie, invalid CSRF | **CsrfFilter** | **403** |
| GET protected API without Bearer token | Authentication | **401** |
| POST Bearer-only chain with CSRF disabled, no token | Authentication | **401** |
| Invalid JWT signature | JwtDecoder | Commonly **401 invalid_token** |
| Valid token lacking scope | Authorization | **403**, possibly `insufficient_scope` |
| Token has scope but lacks tenant access | Domain policy | **403/404** per design |
| POST with valid Bearer token on chain with CSRF enabled | CsrfFilter | Can be **403 due to missing CSRF** |

**Not every 403 means a missing OAuth2 scope.** If `CsrfFilter` rejects the request, do not rush to return **WWW-Authenticate: Bearer error="insufficient_scope"** or tweak `JwtAuthenticationConverter`.

When debugging, identify the selected filter chain, CSRF request matcher, and exception type such as **MissingCsrfTokenException/InvalidCsrfTokenException** before inspecting `JwtDecoder`/scopes.

## 20. Common mistakes

**"REST APIs do not render HTML, so there is no CSRF."** False if the API uses cookies or browser-managed authentication.

**"Stateless and JWT, so there is no CSRF."** False when the browser automatically sends a JWT cookie.

**"HttpOnly prevents CSRF."** False: HttpOnly reduces JavaScript's ability to read a cookie, yet does not stop the browser from sending the cookie.

**"CORS blocks other origins, so that's enough."** No, cross-site forms can send requests without reading responses.

**"SameSite=Lax replaces CSRF tokens."** Not in all cases, especially if GET changes state or untrusted same-site subdomains exist.

**"OIDC Login already has state/nonce/PKCE."** Those mechanisms protect the authorization/login flow, not business POSTs using session cookies afterward.

**"The BFF stores tokens on the server, so there is no CSRF."** The browser still sends the BFF session cookie.

**"permitAll means no CSRF is needed."** No, `permitAll` is an authorization rule; `CsrfFilter` can still inspect unsafe methods.

**"Just having the XSRF-TOKEN cookie present is enough."** No, the server must verify the token explicitly submitted in the header/form per repository/handler.

**"Disabling CSRF is the fix for every POST 403."** Dangerous. Determine whether 403 came from CSRF, scope, role, or domain policy.

**"Disabling CSRF on one chain keeps other chains safe."** Each chain/matcher has its own authentication mechanisms and policy; evaluate all URLs.

## 21. Project policy decision workflow

**Step 1 — Inventory endpoints and authentication methods.** Record URLs, methods, `SecurityFilterChain`, token types, session cookies, Basic, mTLS, and BFF/refresh cookies.

**Step 2 — Identify which credentials browsers send automatically.** Check cookie Domain/Path/SameSite, browser auth caches, certificates, credentials mode, and fallback paths.

**Step 3 — Identify state-changing endpoints.** Include not only CRUD, but also login, logout, refresh, approve, transfer, billing, account linking, and token rotation.

**Step 4 — Choose the CSRF mechanism.** With cookie/session authentication, keep token validation alongside SameSite/Origin/Fetch Metadata. For Bearer-only chains verified to have no ambient credentials, CSRF may be disabled for that specific chain.

**Step 5 — Verify Spring Security configuration.** `SecurityFilterChain` selection, `@Order`, `securityMatcher`, `csrf.ignoringRequestMatchers`, `CsrfTokenRepository`, request handlers, fallbacks, and servlet filter registration.

**Step 6 — Test negative scenarios.** Missing token, cookie-only, forged token, missing scope, missing/invalid CSRF, cross-tenant, and real browser/proxy behavior.

**Step 7 — Re-evaluate when architecture changes.** Moving a JWT from the Authorization header into a cookie, adding `OAuth2Login`, BFF, or refresh cookies can render an earlier decision to disable CSRF **invalid**.

## 22. Scenario exercises

### A. Pure Bearer-header SPA

The frontend explicitly attaches Authorization Bearer; the API trusts only this header and uses no sessions/cookies/Basic. **Traditional CSRF lacks ambient credentials; disabling CSRF on the API chain can be considered**, though XSS defense, token theft protection, issuer/audience/scope validation, and CORS remain mandatory.

### B. JWT in an HttpOnly cookie, stateless backend

The browser sends the JWT cookie automatically. **CSRF risk can still exist**, even though the server stores no session and the JWT is validly signed.

### C. OAuth2 Login then using JSESSIONID

OIDC state/nonce/PKCE protect the login flow, yet a profile-update POST using the session cookie **still requires CSRF protection** under the browser model.

### D. BFF holding access tokens server-side

Browser → BFF over session cookies has CSRF risk; BFF → Resource Server explicitly attaching Bearer has a different threat model.

### E. GET /orders/42/cancel

Using GET to cancel an order is an unsafe design. `CsrfFilter` skips GET by default; switch to an appropriate method and apply CSRF/authorization.

### F. MockMvc POST with jwt() returns 403

If `CsrfFilter` is still enabled, 403 may come from a missing CSRF token rather than scope. Check the chain and exception before changing policies.

## Conclusion

**CSRF depends on whether the browser automatically sends credentials the server accepts**, not simply on JWT, opaque tokens, REST, or statelessness. Cookie sessions, JWT cookies, BFF sessions, session-backed OAuth2 Login, and other browser-managed mechanisms all require CSRF evaluation for state-changing operations.

**Spring Security Servlet** provides `CsrfFilter`, `CsrfTokenRepository`, and `CsrfTokenRequestHandler` to validate anti-forgery values sent **explicitly** via forms/headers. SameSite, Origin/Fetch Metadata, CORS, and cookie flags are important supporting layers, not automatic substitutes for token validation across all architectures.

A **pure Authorization: Bearer Resource Server** may not need CSRF tokens once verified to accept no ambient credentials and backed by tests. **`SessionCreationPolicy.STATELESS`, `HttpOnly`, JWT signatures, and OIDC state/PKCE are not switches that automatically eliminate CSRF.**

### References

- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF Concepts and Synchronizer Token Pattern](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Servlet CSRF Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security API — CsrfConfigurer.spa()](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Set-Cookie and SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
