# REST APIs or Stateless Configurations Do Not Automatically Eliminate All CSRF Risks

A fairly common line of reasoning when securing APIs is: "This is a REST API, it does not use server-side sessions, and `SessionCreationPolicy.STATELESS` is set, so there is definitely no CSRF." **That conclusion is wrong if browsers still automatically send authentication credentials on requests that external websites can trigger.** Switching from a session ID to a JWT stored in a cookie does not change this nature: the browser can still attach the cookie automatically.

To evaluate Cross-Site Request Forgery (CSRF) risk, the central question is: **"On a request triggered by another site, can the browser automatically attach credentials sufficient for the server to accept the action?"**—not whether the API path starts with `/api`, returns JSON, or avoids server-side state.

This lesson belongs to the **CSRF** group in Spring Security fundamentals, focusing on how to assess risks in REST APIs, stateless applications, and Spring Security Servlet configurations. After completing it, you should be able to explain why cookie-based JWTs and HTTP Basic can still face CSRF, when a Bearer-only API carries low classic CSRF risk, the roles of SameSite/CORS/CSRF tokens, and how to choose an appropriate `SecurityFilterChain`.

## 1. The CSRF Mechanism Does Not Depend on Whether the Server Has Sessions

**CSRF (Cross-Site Request Forgery)** occurs when an attacker causes an authenticated user's browser to **send a request executing an unwanted action** to a target website/API. Attackers usually do not need to know the password or read the credential; they exploit the browser automatically attaching credentials to valid requests according to browser rules.

Hypothetical example:

1. The user is logged into `https://bank.example.test`, holding an authentication cookie valid for that site.
2. The user opens `https://attacker.example.org`, which contains a form submitting data to `https://bank.example.test/account/change-email`.
3. The browser may send the request triggered by the foreign page. **Whether the cookie is attached depends on `SameSite`, domain, path, scheme, and other browser policies**.
4. If a valid cookie is sent and the server checks only authentication without **checking anti-CSRF proof**, the email-change request may be accepted as if initiated intentionally by the user.
5. The attacker may not read the response due to the Same-Origin Policy (SOP), yet the state change has already occurred.

Diagram describing the risk condition:

```text
User logged into bank.example.test
     |
     | browser holds auth cookie belonging to bank.example.test
     v
Opens attacker.example.org
     |
     | page triggers POST to bank.example.test
     v
Browser checks cookie policies (SameSite/Domain/Path/Secure)
     |
     | if cookie is sent automatically
     v
Target API receives request + auth cookie
     |
     | API checks only credential, no CSRF proof checked
     v
State-changing action may be executed
```

**Root principle:** CSRF exploits **privileges that the browser automatically carries into requests**. Whether the server stores an `HttpSession` is merely an implementation detail of the authentication method, not the sole decisive factor.

### Illustrative HTML Form of an Exploited Request

The following example is for understanding the threat on an authorized test site; `example.test` is not a real website:

```html
<form method="post"
      action="https://bank.example.test/account/change-email">
  <input type="hidden" name="email" value="unwanted@example.test">
  <button type="submit">Submit</button>
</form>
```

If the browser allows sending the auth cookie and the endpoint accepts `application/x-www-form-urlencoded` **without CSRF protection**, the operation can succeed when the user clicks the button. An external page can also auto-submit the form via JavaScript subject to browser restrictions; merely using `POST` on the server does not stop this scenario.

This pattern **does not guarantee every endpoint is exploitable**: `SameSite` may block the cookie, the endpoint may only accept other media types, and the CSRF filter may reject the request. It illustrates **the condition that must be evaluated**, rather than concluding all cross-site forms succeed.

## 2. What Does "Stateless" Actually Mean?

In Spring Security Servlet, the common configuration for a stateless API is:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
```

Meaning: **Spring Security will not create or use an `HttpSession` to obtain `SecurityContext`** for requests matched by that chain. It steers the API toward per-request authentication, such as JWT Bearer tokens. It **does not** dictate how browsers store credentials, disable cookies issued by the app itself, or prevent other components from calling Servlet APIs to create sessions.

Example of a self-contained JWT auth cookie service:

```http
Set-Cookie: AUTH=eyJ...; Secure; HttpOnly; SameSite=None; Path=/
```

On subsequent requests, the browser may auto-send:

```http
POST /api/orders/confirm HTTP/1.1
Host: shop.example.test
Cookie: AUTH=eyJ...
Content-Type: application/x-www-form-urlencoded

orderId=42
```

Even if the API decodes the JWT **without querying a session in RAM/Redis**, the cookie remains an **ambient credential**: the browser attaches it automatically per cookie policy. If another page triggers a request and the cookie is sent, CSRF risk can still arise.

Do not equate three distinct claims:

- `STATELESS` → does not use HTTP sessions to restore Spring Security context in that chain.
- JWT → a token format verifiable via signature/claims; **JWTs do not eliminate CSRF on their own**.
- `Authorization: Bearer` actively attached only by first-party JavaScript → a credential delivery model that can reduce classic CSRF conditions, **provided no other automatic auth path exists**.

**Even with a validly signed JWT, the server must still verify issuer, audience, expiry, and permissions.** Yet a valid signature only proves the token is trusted under those rules; it does not prove **the user intentionally initiated the current request**.

## 3. REST APIs and JSON Do Not Block CSRF by Themselves

**REST** is an architectural style for resource communication; it does not define "browsers have no cookies", "all clients send only Bearer headers", or "every browser action is intentionally confirmed".

The following labels **are not standalone anti-CSRF measures**:

- URLs starting with `/api/`.
- JSON-formatted HTTP bodies.
- Splitting frontend and backend onto two hostnames.
- Accepting only `POST`/`PUT`/`PATCH`/`DELETE` instead of GET to mutate data.
- Avoiding `JSESSIONID` while using a JWT in a cookie.
- Not creating server sessions and setting `SessionCreationPolicy.STATELESS`.
- Enabling CORS with some origin allowlist.

**Proper HTTP method design still matters greatly:** `GET`, `HEAD`, and `OPTIONS` must be designed as semantically "safe" methods that cause no business-significant state changes. If `GET /delete?id=42` deletes data, a navigation or resource load can trigger damage without needing a `POST` form. `POST` must not be treated as "safe because it is POST"; it needs proper authentication, authorization, and anti-CSRF checks.

### "What If the API Accepts Only `application/json`?"

A standard cross-site HTML form sends simple content types like `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`. It cannot arbitrarily construct a request with `Content-Type: application/json` and custom headers bypassing browser constraints.

If the server **strictly validates content types, refuses to parse `text/plain` as JSON, exposes no alternate form-accepting endpoints, and avoids unsafe CORS configurations**, several classic CSRF vectors become difficult or blocked. However, this is only **one control layer**. Loose body parsing, multi-format endpoints, bad CORS, state-changing GETs, and client-side CSRF patterns make the rule "JSON = no CSRF" unreliable.

Spring Security specifically notes that JSON requests **can still face CSRF** in particular setups. Disabling CSRF solely because of a `.json` suffix or a REST label ignores how browsers and servers actually interact.

## 4. Comparing Credential Delivery: Where CSRF Appears

| Authentication method | Does browser auto-send credentials? | CSRF considerations |
|---|---|---|
| **Session cookie (`JSESSIONID`)** | Yes, when cookie matches scope/policy | Vulnerable if state-changing requests lack CSRF defense |
| **JWT access token in `AUTH` cookie** | Yes, if cookie is permitted | **Risk remains** even without backend HTTP sessions |
| **Cached HTTP Basic in browser** | Browser may re-send credentials per auth scope and client behavior | Can be vulnerable to CSRF; do not treat Basic as immune |
| **Client certificate / browser auto-credentials** | May be used automatically by browser per connection/policy | Must evaluate CSRF based on browser path and actual identity |
| **Bearer token strictly in Authorization header added by app JS** | Foreign pages do not hold Bearer value; cross-origin JS bounded by SOP/CORS | Low classic CSRF risk **if the API strictly accepts only this mechanism** |
| **API key in custom header set by first-party app** | Browser does not fabricate keys for foreign pages | Control key leakage/XSS/CORS; CSRF risk depends on alternate auth paths |
| **Cookie auth + CSRF token header** | Auth cookie auto-sends; CSRF header is not auto-attached by browser | Protected against CSRF when server verifies token/header properly |

Distinguish the last row carefully: browsers can auto-send **a cookie containing a CSRF token**, so **requiring only the CSRF cookie's presence is insufficient**. You must extract the token out of the automatic channel and send it in a header or form parameter controlled by the legitimate app; the server verifies it properly.

### How Do a JWT in a Cookie and a JWT in a Header Differ?

The exact same JWT value can travel two ways:

```http
Cookie: AUTH=EXAMPLE_JWT
```

or:

```http
Authorization: Bearer EXAMPLE_JWT
```

**An identical JWT does not mean identical risk.** The decisive difference is who attaches the credential to the request.

- Browser-managed cookies are sent automatically when cookie rules match.
- Bearer headers are normally added explicitly by app JavaScript or another HTTP client. An attacking page from another origin does not know the token value to set the header.
- If a Bearer token is instead automatically copied from a cookie into a header by a framework for every triggerable request, or if the API has a cookie fallback, re-evaluate the actual flow.
- When tokens live in `localStorage` or JavaScript variables, classic CSRF may be less applicable, yet **XSS token theft** or forcing same-origin code to send requests remains a threat. Never declare `localStorage` automatically "safer".

Also consider the Backend-for-Frontend (BFF) pattern: the backend holds access/refresh tokens server-side while the browser uses only a session cookie to call the BFF. With a BFF, browser → BFF requests still require CSRF protection, even if BFF → downstream API uses Bearer tokens in headers.

## 5. Practical Example: A Stateless API Still Vulnerable to CSRF

Suppose `orders.example.test` uses:

- Spring MVC `@RestController` with JSON bodies.
- Self-contained JWT in an `AUTH` cookie, signature verified by the backend.
- `SessionCreationPolicy.STATELESS` in Spring Security.
- Endpoint `POST /api/orders/42/approve` changing order state.
- Cookies allowed in a context that external requests can trigger.
- No CSRF tokens, Origin/Fetch Metadata verification, or equivalent anti-forgery safeguards.

While a user is logged in, an appropriate cross-site or cross-origin request can make the browser send `AUTH`; if the endpoint accepts that request type, the server has enough authentication data to execute the command. **No step of the attack requires reading a server session.**

Risk drops or is blocked when cookies use appropriate `SameSite` settings, APIs strictly require media types/headers unforgeable by external pages, servers verify Origin/CSRF tokens, or no auto-sent credentials exist. Yet **"being stateless" is not itself the safeguard**.

### Nearly the Opposite Case: Bearer-Only API

An API called by a mobile app or backend:

```http
POST /api/orders/42/approve HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Content-Type: application/json

{"approved":true}
```

If the API **only accepts tokens in the `Authorization` header**, never accepts sessions/cookies/Basic/integrated auth as fallbacks, permits no other auto-sent credentials, and external pages do not know the token, then a foreign page crafting a form or navigation will **lack a valid Bearer token**. Under that model, classic CSRF is unlikely to succeed, so disabling Spring Security CSRF for the Bearer-only scope can be considered after verifying assumptions.

**Limitation:** This does not make the API safe against XSS, token leaks, misconfigured CORS, broken authorization, request replay, or client-side CSRF. If cookie auth is later added "for convenience", the decision to disable CSRF must be revisited.

## 6. What Do SameSite, HttpOnly, and Secure Actually Help With?

Cookies have multiple security attributes; each addresses a different problem:

| Attribute | Meaning | What it does NOT guarantee |
|---|---|---|
| `HttpOnly` | Restricts JavaScript from reading cookies via `document.cookie` | **Does not stop browsers from auto-sending cookies**; does not prevent CSRF |
| `Secure` | Requires sending cookies over HTTPS per browser policy | Does not prevent CSRF if cookies travel over HTTPS in forged requests |
| `SameSite=Strict` | Restricts sending cookies in cross-site scenarios | Does not solve **same-site yet cross-origin** requests, XSS, or client-side CSRF |
| `SameSite=Lax` | Blocks many unsafe cross-site requests while allowing certain top-level safe navigations | Not proof of user intent for every action; does not fix unsafe GETs |
| `SameSite=None; Secure` | Allows cookies in eligible cross-site contexts, subject to browser policy | Can enable cookie transmission on CSRF-prone requests |
| `Domain`, `Path` | Limits host/path scope receiving cookies | Does not distinguish user clicks from external page triggers |

**Same-site differs from same-origin.** For instance, `https://shop.example.test` and `https://promo.example.test` are **different origins** due to differing hosts, yet usually the same *site* under schemeful site/registrable domain rules. An untrusted subdomain can trigger same-site requests where `SameSite=Strict` or `Lax` does not necessarily block cookies. Be cautious whenever subdomains have differing trust levels.

Practical detail: modern browsers apply different SameSite defaults/exceptions depending on context, version, and cookie creation time. Therefore **verify behavior on supported browsers**, rather than assuming a cookie omitting `SameSite` gets one fixed uniform policy everywhere.

`HttpOnly` is the right choice for **authentication cookies** whenever possible. When using the **SPA CSRF token cookie** pattern, sometimes a **separate** cookie named `XSRF-TOKEN` is intentionally readable by JavaScript to echo back in a header. Do not confuse the readable CSRF cookie with the login cookie that must stay secret; the two cookies serve different roles.

## 7. CORS and Same-Origin Policy Are Not General CSRF Shields

**Same-Origin Policy (SOP)** primarily prevents scripts of one origin from reading/accessing data of another origin. **CORS** lets servers permit certain cross-origin interactions under browser enforcement. CSRF, however, can rely solely on **sending a request and triggering side effects** without needing to read the response.

A cross-site HTML form can be submitted by the browser without the API allowing response reads via CORS. If credentials auto-send and the server executes the action, the user still suffers impact even if the foreign script never sees the returned JSON.

**Preflight helps restrict certain request types**—for instance, JavaScript trying to send `Authorization` or a custom `X-CSRF-TOKEN` header cross-origin generally triggers CORS preflight. However:

- Simple-content-type form POSTs do not require that kind of preflight.
- APIs might allow credentialed CORS for overly broad or untrusted origins; blindly reflecting `Origin` alongside `Access-Control-Allow-Credentials: true` is dangerous.
- Lacking `Access-Control-Allow-Origin` in the response **does not mean the server refused to execute the request**.
- `Origin`/`Referer` and Fetch Metadata (`Sec-Fetch-Site`, `Sec-Fetch-Mode`, etc.) can support anti-forgery policies, though missing headers, proxies, and non-browser clients must be handled.

**Technical conclusion:** CORS is a cross-origin sharing policy; CSRF must be assessed by auto-sent credentials, state-changing requests, and request-origin proof. Strictly configured CORS is a supporting layer, never a full replacement for CSRF protection on cookie-authenticated apps.

## 8. Spring Security Servlet: Default CSRF Configuration

Spring Security Servlet **enables CSRF protection by default** for unsafe HTTP methods (typically `POST`, `PUT`, `PATCH`, `DELETE`). It can be stated explicitly in a `SecurityFilterChain`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BrowserSecurityConfig {

    @Bean
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

This is a configuration example **within a Spring Boot 3 / Spring Security 6 project containing Spring MVC, Security dependencies, and necessary authentication components**; not a standalone Java class runnable with `javac`. `csrf(Customizer.withDefaults())` makes the default explicit. With the default `HttpSessionCsrfTokenRepository`, expected tokens are typically managed in `HttpSession`. HTML forms must submit `_csrf` or JavaScript clients must send the token via the configured header.

A POST lacking a valid CSRF token to a protected endpoint is typically rejected with **403 Forbidden** before business logic runs. Depending on filter order and authentication state, observed errors can vary; never rely solely on a 403 status as proof that CSRF works properly.

### How Does a CSRF Token Protect?

**Synchronizer Token Pattern**:

1. The server issues an unpredictable CSRF token for an appropriate authentication/session context.
2. The trusted app puts the token in a hidden form field or dedicated header when sending state-changing requests.
3. The browser may auto-send auth cookies, yet an attacking page lacks the **valid CSRF token in the server-required location**.
4. The server matches the submitted value against the expected token; if wrong or missing, it rejects before executing the action.

Illustrative valid request example:

```http
POST /account/change-email HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=EXAMPLE_SESSION
Content-Type: application/x-www-form-urlencoded

email=new%40example.test&_csrf=EXAMPLE_CSRF_TOKEN
```

These are dummy values; the server must actually issue and verify tokens rather than using a constant string `EXAMPLE_CSRF_TOKEN`. With HTML templates like Thymeleaf properly integrated with Spring Security, CSRF tokens can be injected into forms automatically. With SPAs, design token retrieval and submission via `X-CSRF-TOKEN` or `X-XSRF-TOKEN` per config.

An **auto-sent** CSRF cookie is not sufficient "proof" if the server only checks that cookie. The **double-submit cookie** model requires reading the token and sending it over a non-automatic channel (e.g., custom header) for comparison; implementations should cryptographically bind signed tokens to session/identity per architecture to prevent cookie injection/fixation. Do not roll your own naive random token or signing scheme when the framework provides trusted components.

## 9. When Can CSRF Be Disabled for Bearer-Only APIs?

A REST API using OAuth2 Resource Server that accepts only `Authorization: Bearer` from clients can apply a dedicated chain. Spring Security Servlet example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerOnlyApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

**Exact explanation of the safety conditions here:** On `/api/**`, the API **trusts only Bearer tokens actively sent in headers by clients**, rejects cookies as credentials, has no HTTP Basic/browser-managed authentication, uses no session as an authentication fallback, and has no state-changing endpoints accepting unintended anonymous requests. JWTs are properly verified for issuer, audience, expiry, signature, and scopes/permissions. Under those conditions, no credential exists that a third-party browser page can automatically attach to a form request to satisfy Bearer authentication.

`csrf(AbstractHttpConfigurer::disable)` disables `CsrfFilter` **for this filter chain**, not proving unconditionally that "stateless means no CSRF needed". If browser cookie login is later enabled on `/api/**`, `AUTH` cookies containing JWTs are accepted, or HTTP Basic is enabled for browsers, you must **re-evaluate and restore CSRF defenses** before deploying.

Using `@Order(1)` and `securityMatcher("/api/**")` merely illustrates scoping. Real applications need **remaining chains** or fallback policies so every request is protected. This section does not assume a browser chain already exists when showing only the API snippet.

### Same API Yet JWT Comes from a Cookie: Is Disabling CSRF Appropriate?

**No, if that cookie is an automatic credential used by the browser to authenticate and state-changing requests can be triggered unintentionally.** Even though the API builds authentication from a JWT without sessions, the browser still auto-sends the cookie. Choose protections per threat model, such as:

- Keep CSRF protection for cookie-authenticated requests.
- Use synchronizer CSRF tokens if suitable session state exists, or **signed double-submit tokens**/sessionless token mechanisms when truly stateless.
- Send CSRF tokens via dedicated headers not auto-added by browsers, and verify them server-side.
- Configure SameSite/Secure/HttpOnly, verify Origin or Fetch Metadata appropriately, and keep CORS tight.
- Restrict state-changing requests; never use GET to execute dangerous actions.

If using `CookieCsrfTokenRepository` for a Spring Security SPA, note that **Spring Security 6 uses deferred token loading and default BREACH protection**. JavaScript normally reads the raw token from the cookie while the default handler expects XOR-masked representations on certain paths; official docs provide the SPA `CsrfTokenRequestHandler` setup and how to reissue cookie tokens after login/logout. Do not merely call `CookieCsrfTokenRepository.withHttpOnlyFalse()` and assume complete SPA integration across versions/frameworks. Auth cookies should keep `HttpOnly` where appropriate, whereas CSRF token cookies readable by JS have a separate design and purpose.

## 10. Applications Having Both Browser Sessions and REST APIs

Suppose one application serves `/profile` for browsers and `/api/**` for mobile/backend clients with two independent auth flows:

- `/profile`: form login, browsers use session cookies; requires CSRF protection.
- `/api/**`: Bearer headers **only**, rejects cookies/sessions; may disable CSRF specifically after verifying assumptions.

One way to configure multiple chains (Spring Boot code, not standalone):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedCsrfSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

This pattern requires Spring Security starters, OAuth2 Resource Server, and a valid issuer/JWT decoder. It does not configure users or issuers itself; that belongs to your app. If already using `apiChain` from section 9, **choose only one appropriate configuration** rather than declaring two overlapping `apiChain` beans.

Notes:

1. Spring Security evaluates `SecurityFilterChain` beans in order and uses the first matching chain.
2. The API chain must truly accept only Bearer headers. If cookie auth is added for `/api/**`, change the design.
3. The browser chain must still handle login/logout endpoints and cookie-authenticated requests; never disable CSRF app-wide just because some APIs are stateless.
4. For a same-origin SPA using cookies to call REST endpoints, that API **is a browser cookie API**, not a "CSRF-exempt" Bearer-only API under this pattern.
5. `SessionCreationPolicy.STATELESS` governs Spring Security's session management for that chain; it does not automatically control custom cookies issued by the app.

### Comparing Similar-Looking Requests

| Request | Authentication method | CSRF condition to evaluate |
|---|---|---|
| `GET /api/orders`, Bearer header set by mobile app | Client-controlled token | Normally non-mutating, still needs authn/authz |
| `POST /api/orders`, Bearer header from backend service | Backend-attached token | Classic CSRF may not apply if zero auto-sent credentials exist |
| `POST /api/orders`, `AUTH` cookie sent by browser | Automatic cookie | **Requires appropriate CSRF protection** |
| `POST /account/email`, browser session cookie | Automatic cookie | **Requires appropriate CSRF protection** |
| `POST /admin/action`, cached browser HTTP Basic | Browser may auto-send credentials | Must evaluate CSRF; do not skip just because no session exists |
| `GET /logout` that actually destroys sessions | Unsafe behavior via GET | Fix endpoint/method and evaluate CSRF |

## 11. Login CSRF, Logout CSRF, and State-Change Impact

CSRF is not limited to "transferring money" or "deleting data". **Login CSRF** forces a browser into an unwanted session/account; **logout CSRF** forces a user out, causing disruption or state confusion. For cookie/session apps, protecting login and logout against CSRF is part of secure design.

In Spring Security Servlet, CSRF protects unsafe requests by default. With CSRF enabled, `LogoutFilter` requires a matching `POST` request to log out; browser forms can carry the `_csrf` hidden input. Never replace it with a state-changing `GET /logout` without a security analysis.

In OAuth2/OIDC logins, the `state` parameter in Authorization Code Flow binds redirect responses to initial requests and prevents redirect/login CSRF attacks. It **is not a general CSRF token** for all REST endpoints after login. Likewise, PKCE protects authorization codes from certain interception/theft attacks; it does not make cookie-based APIs immune to CSRF.

An API exposing `GET /admin/delete` or `GET /payment/confirm` that mutates business state is a bug to fix, because browsers can load/navigate GET URLs in many cookie-permitting contexts. CSRF tokens on unsafe methods cannot fix state mutation placed on safe methods.

## 12. XSS, Client-Side CSRF, and Classic CSRF: Three Related Yet Distinct Issues

**Classic CSRF:** A page on another origin tries sending a request while the browser automatically attaches cookies/auth. Appropriate defenses are CSRF tokens, cookie policies, Origin/Fetch Metadata, and trust boundaries per threat model.

**XSS (Cross-Site Scripting):** Attacker script executes inside the app's own origin. It can directly send requests using the page's privileges, read tokens accessible to JavaScript, or manipulate the UI. `HttpOnly` restricts reading auth cookies, yet same-origin scripts can still make the browser send authenticated requests and `HttpOnly` does not eliminate XSS impact. Use output encoding, proper CSP, and dedicated XSS defenses.

**Client-side CSRF:** Legitimate application JavaScript can be steered by untrusted data (URLs, query params, postMessages, fragments...) into issuing state-changing requests complete with credentials and CSRF headers that the script itself is allowed to send. Here the attacker exploits **client logic**, and SameSite or standard CSRF tokens may not suffice if same-origin code sends valid tokens itself. Validate inputs and restrict frontend actions controllable by external data.

Never claim "we have CSRF tokens so XSS isn't dangerous" or "we use Bearer headers so client-side CSRF is impossible". These layers defend against different vectors.

## 13. Security Testing: Proving Assumptions Before Disabling CSRF

To evaluate a specific API, answer these questions in order:

1. **Who calls the endpoint?** Browser, mobile app, backend, third-party service?
2. **Where do credentials come from?** Cookie/session, JWT cookie, browser-cached HTTP Basic, client cert, or client-attached Bearer header?
3. **Does the request mutate state?** `POST/PUT/PATCH/DELETE` or any poorly designed `GET` endpoint?
4. **Can an external page trigger the request?** HTML form, navigation, image/link, cross-origin JS within SOP/CORS, URL, or frontend-controlling data?
5. **Does the browser auto-attach credentials when that request happens?** Check cookie SameSite/Domain/Path/Secure, HTTP Basic caching, cookie auth fallbacks, and client-specific behavior.
6. **How does the server validate CSRF?** CSRF token/header, Origin/Referer, Fetch Metadata, media type, cross-site policies, and binding tokens to user/context?
7. **When the token is invalid or missing, does the server reject before side effects?** Check actual results in an authorized test environment, not just HTTP status codes.
8. **Do filter chains match the right paths?** Bearer-only APIs must apply exact `securityMatcher`s; browser chains must preserve CSRF.
9. **Do clients/frontends refresh tokens after login/logout?** SPAs using CSRF tokens may need new tokens as Spring Security updates corresponding state.
10. **If config changes later, could risk return?** Adding JWT cookies, Basic auth, browser-facing endpoints, or credentialed CORS must trigger a CSRF review.

### Minimum Test Matrix

| Test environment | Request | Expected outcome |
|---|---|---|
| Browser cookie app with CSRF enabled | Unsafe method + valid cookie + **missing CSRF token** | Rejected, zero side effects |
| Browser cookie app with CSRF enabled | Unsafe method + valid cookie + **valid** CSRF token | Allowed to proceed if authorized |
| Browser cookie app with CSRF enabled | Unsafe method + **invalid** token | Rejected, zero side effects |
| Bearer-only API | Unsafe method without Authorization | Typically 401, zero side effects |
| Bearer-only API | Valid Bearer yet insufficient permissions | Typically 403, zero side effects |
| Bearer-only API | Valid Bearer, authorized | Permitted if payload and business rules also valid |
| Stateless JWT cookie app | Request from external site where cookie is sent | Must have suitable protection; stateless alone is insufficient |
| API with side-effecting `GET` | Cross-site navigation/link | Must fix design; do not rely on CSRF filter for GET |

**Meaningful testing must observe whether business data actually changed.** For example, a 403 status can come from authorization rules, so missing CSRF tokens must be distinguished from missing permissions. In Spring Security tests, `spring-security-test` provides the `csrf()` request post-processor for MockMvc to test both with/without CSRF token branches on the active chain.

### Limited `curl` Example

In an authorized test environment using dummy data, you can send a request with a test cookie:

```bash
curl --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --cookie "JSESSIONID=EXAMPLE_SESSION" \
  --data "email=demo%40example.test" \
  https://portal.example.test/account/change-email
```

This command is only a structural sample, **not a test result**; `EXAMPLE_SESSION` is an intentionally invalid placeholder. `curl` does not enforce browser SameSite/CORS policies, so it **does not prove cross-site browser requests include cookies**. Run corresponding real browser/automation tests to verify cookie and Origin policies. Never disable TLS verification with `-k` just to make requests succeed.

## 14. Standalone Java 17 Example: Classifying CSRF Conditions

The Java snippet below only trains reasoning on **initial condition checks**; it performs no real network/browser analysis, generates no CSRF tokens, and does not replace Spring Security. Each output expresses an **assumption about a credential model**, not proof that an API is secure in practice.

Create `CsrfRiskChecklistDemo.java`:

```java
public class CsrfRiskChecklistDemo {
    enum CredentialMode {
        SESSION_COOKIE,
        JWT_COOKIE,
        BROWSER_BASIC,
        EXPLICIT_BEARER_HEADER
    }

    static String assess(CredentialMode mode, boolean changesState) {
        if (!changesState) {
            return "No state change assumed; verify endpoint behavior";
        }
        return switch (mode) {
            case SESSION_COOKIE, JWT_COOKIE, BROWSER_BASIC ->
                    "Check CSRF: browser may auto-send credentials";
            case EXPLICIT_BEARER_HEADER ->
                    "Classic CSRF condition not established; audit other paths";
        };
    }

    public static void main(String[] args) {
        System.out.println("Session: " +
                assess(CredentialMode.SESSION_COOKIE, true));
        System.out.println("JWT cookie: " +
                assess(CredentialMode.JWT_COOKIE, true));
        System.out.println("Bearer: " +
                assess(CredentialMode.EXPLICIT_BEARER_HEADER, true));
        System.out.println("GET: " +
                assess(CredentialMode.JWT_COOKIE, false));
    }
}
```

Run with JDK 17 or later:

```bash
javac CsrfRiskChecklistDemo.java
java CsrfRiskChecklistDemo
```

Exact output:

```text
Session: Check CSRF: browser may auto-send credentials
JWT cookie: Check CSRF: browser may auto-send credentials
Bearer: Classic CSRF condition not established; audit other paths
GET: No state change assumed; verify endpoint behavior
```

Key takeaway: both session cookies and JWT cookies fall under **browsers may auto-send credentials**, whereas client-attached Bearer headers still require checking whether the API accepts any other cookies/Basic auth. The GET line assumes **no state change**; if a GET endpoint mutates data, that output does not hold.

## 15. Ten Common Mistakes and Fixes

| Claim / mistake | Why it is wrong | How to handle |
|---|---|---|
| "`STATELESS`, so disable CSRF everywhere" | Browsers may still auto-send cookies/Basic | Classify credentials and requests per filter chain |
| "Signed JWT prevents CSRF" | Signatures prove token origin, not request intent | If JWT sits in a cookie, apply proper CSRF defense |
| "REST APIs cannot have CSRF" | REST does not govern credential/browser policies | Analyze clients and credential delivery |
| "JSON cannot suffer CSRF" | Endpoints may accept other formats or exploitable flows | Enforce strict media types, keep CSRF when cookie-authenticated |
| "Disabling CORS blocks form submissions" | CORS does not stop all forms/navigations from sending requests | Use CSRF tokens and supplemental origin policies |
| "`HttpOnly` stops CSRF" | It stops scripts from reading cookies, not browsers from attaching them | Keep `HttpOnly` and add CSRF protection |
| "`SameSite=Lax` stops all CSRF" | Same-site cross-origin and poorly designed GETs remain risky | Combine tokens, Origin checks, and endpoint audits |
| "Auto-sent CSRF cookie is enough" | Attackers can make browsers send cookies without knowing tokens | Require separate server-verified header/form token |
| "Disabling CSRF on one API means the whole app is safe" | Browser chains, cookie fallbacks, or other endpoints may exist | Restrict `securityMatcher`, audit every chain |
| "401/403 proves no CSRF" | May come from missing auth/permissions rather than CSRF | Check side effects and isolate failure causes |

### Final Key Takeaway

**CSRF happens when browsers can send state-changing requests with automatic credentials and the server lacks verification of active/legitimate request intent.** `REST`, `JSON`, `JWT`, or `SessionCreationPolicy.STATELESS` do not eliminate this condition by themselves.

**Practical rule:** Keep CSRF protection for browser flows using cookies or auto-sent credentials; consider scoped disabling only for genuinely **Bearer-only APIs with zero browser-managed authentication**, after auditing the request model and protecting remaining endpoints. At the same time, maintain HTTPS, authorization, XSS defense, SameSite/CORS policies, and real-world testing.

## References

- [Spring Security — Cross-Site Request Forgery (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF configuration, session/cookie token repositories, SPAs, and login/logout considerations.
- [Spring Security — CSRF and Stateless Browser Applications](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): explains why custom JWT cookies and HTTP Basic still carry CSRF risk despite being stateless.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token patterns, Signed Double-Submit Cookie, SameSite, Origin/Fetch Metadata, and risks.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): SOP, credentialed requests, and preflight.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): meaning of safe HTTP methods and why state-changing actions must not use GET.
