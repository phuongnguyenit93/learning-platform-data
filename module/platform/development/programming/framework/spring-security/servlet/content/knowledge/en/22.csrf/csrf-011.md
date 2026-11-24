# CSRF Analysis for APIs Using Cookies, HTTP Basic, or Bearer Headers

## 1. What Does CSRF Actually Depend On?

**Cross-Site Request Forgery (CSRF)** is a situation where an attacker-controlled page causes a victim's browser to send a request to an application the victim is logged into. The server sees valid authentication credentials yet cannot confirm whether the operation was genuinely initiated by the user in a trusted interface.

The key condition is not whether the application is called a "REST API", "stateless", or whether tokens use the JWT format. The question to ask is: **does the browser automatically attach credentials when an untrusted source triggers a request?**

A typical CSRF requires all of the following simultaneously:

1. The user has a login state or credentials that the browser can automatically send to the target.
2. The attacker can craft a request that the browser will send (for example, an HTML form).
3. The endpoint mutates data or state, and does not verify independent proof of the user's intent.
4. Cookies or credentials are actually attached by the browser under current rules; if blocked by SameSite or another mechanism, that specific scenario fails.

For example, a malicious page might submit a form:

~~~html
<form action="https://shop.example/api/address" method="post">
  <input type="hidden" name="address" value="Attacker address">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

This is an example of **how a request is generated**, not a guaranteed successful exploit: the endpoint must accept form data and credentials must be sent. The attacker usually **does not need to read the response**. Therefore, the *same-origin policy* preventing data reads and not enabling CORS do not automatically block CSRF from a valid form.

**Distinction:** CSRF exploits the browser's automatic authentication authority. XSS is unauthorized JavaScript execution within a trusted origin; XSS can read or use CSRF tokens accessible to JavaScript, so CSRF defense does not replace XSS defense.

## 2. Decision Matrix by Credential Submission Mechanism

| How the API authenticates | Does the browser auto-send credentials on a request triggered by another page? | Conclusion regarding CSRF |
| --- | --- | --- |
| Session cookie (e.g., `JSESSIONID`) | **Yes**, if cookie rules, SameSite, and browser policies allow | **At risk**; requires CSRF defense for state-changing operations |
| JWT/access token placed in a cookie | **Yes**, under similar cookie conditions | **At risk**, even though the token is a JWT and the backend stores no session |
| Browser-managed/cached HTTP Basic | **Possibly**: the browser may auto-send `Authorization: Basic ...` within the remembered authentication scope | **At risk** when accessed via browser; do not disable CSRF by default just for "stateless Basic" |
| Bearer token actively fetched by JavaScript and placed in `Authorization: Bearer ...` | **Not automatically**: forms, images, or navigations to the target cannot know the token to populate the header | **Normally no classic CSRF risk** if the endpoint accepts only Bearer headers and has no other auto-auth path |
| Bearer token existing only in a native app, CLI, or server-to-server calls | No browser ambient credentials mechanism | Browser-based CSRF is not a direct threat for that client |
| Bearer token stored in a cookie then used by a gateway/BFF to authenticate | **Yes** for the cookie sent by the browser | Evaluate as a **cookie**, not based on the word "Bearer" on the server side |

The rule of thumb is to **inspect each endpoint and every way it accepts credentials**. An API accepting both a Bearer header and a session cookie can still be vulnerable to CSRF via the cookie path, even though legitimate SPA requests typically use Bearer.

### 2.1. Cookies: Both Sessions and JWTs Need CSRF Evaluation

An external page can cause the browser to send a request to the application. When the authentication cookie accompanies it, the server side only sees an authenticated user. The `HttpOnly` attribute prevents JavaScript from reading the cookie, yet **does not stop the browser from auto-sending the cookie**, so it does not solve CSRF. The same holds for a cookie containing a JWT: token format does not alter the transport mechanism.

Risk-reducing factors:

- **Synchronizer-style CSRF tokens**: the server binds the token to the session, renders or provides the token to legitimate clients, and verifies it on state-changing requests. Tokens must be unpredictable, bound to the session, and not rely solely on auto-sent credentials.
- **Double-submit cookie**: the client sends the same token via both a cookie and a separate header/field. For stateless variants without server-side storage, use signed or session-bound tokens; naively comparing two cookie-sourced values can be tampered with, especially when untrusted subdomains exist.
- **SameSite cookies**: help reduce cross-site requests yet have limitations. `Strict` blocks sending cookies in many cross-site contexts; `Lax` generally allows top-level navigations using safe methods like GET, not standard cross-site POSTs; `None; Secure` permits cross-site sending subject to current cookie policies. Some browsers have an exception for newly set cookies when the app **omits** the SameSite attribute, so configure it explicitly.
- **Origin/Referer or Fetch Metadata checks** as an additional layer, especially for sensitive endpoints. Do not overlook host, proxy, and allowlist misconfigurations.
- **Do not turn GET/HEAD into write operations.** Simply switching a method to GET to avoid CSRF tokens is a design flaw.

Note: **same-site does not mean same-origin**. Two subdomains can be on the same "site" yet have different origins; applications must also consider compromised or untrusted subdomains. A cookie with `SameSite=Lax` or `Strict` is not a license to skip intent verification for sensitive operations.

### 2.2. HTTP Basic: Depends on Who Attaches Authorization

In browser-managed Basic auth, after the user authenticates, the browser can cache the credentials and automatically apply them to requests within the corresponding protection space. A malicious page does not need to know the password; if the browser automatically adds the Basic header to API requests, CSRF conditions mirror cookies. SameSite governs only cookies, **not Basic Authorization**.

Conversely, when a script or CLI **actively** attaches `Authorization: Basic ...` each time and no browser has cached credentials for automatic reuse, requests from a malicious website do not carry that header. Do not conclude solely from the scheme name; inspect actual browser flows, how Basic is cached/remembered, and authentication fallbacks.

APIs using Basic are often described as "stateless", yet **stateless does not mean immune to CSRF**. If browsers are supported and Basic is auto-sent, protect state-changing methods with CSRF or redesign how credentials are accepted.

### 2.3. Bearer in the Authorization Header: When Is a CSRF Token Typically Unnecessary?

Example of an SPA fetching an access token and actively sending it:

~~~http
POST /api/orders HTTP/1.1
Host: api.example
Authorization: Bearer eyJ...
Content-Type: application/json

{"productId":42}
~~~

An HTML form from another website cannot populate `Authorization: Bearer ...` itself. A malicious website's JavaScript cannot read variables, memory, or localStorage of the application's origin either. If it tries a cross-origin fetch with an `Authorization` header, the request typically requires a CORS preflight; and even if the server enables CORS, the attacker still needs a **valid token** to authenticate.

Therefore, you can **omit CSRF tokens** on a route that genuinely accepts only access tokens from client-attached Bearer headers, provided it accepts no session cookies, automatic HTTP Basic, or cookie-based fallbacks on that same route. This does **not** mean Bearer is "completely safe": storing tokens in localStorage risks theft via XSS; using cookies to hold refresh tokens brings CSRF concerns to cookie-handling endpoints; misconfigured CORS can increase data exposure. You must address XSS, token storage, authorization, TLS, and CORS configuration independently.

A BFF model might use Bearer **between the BFF and the API**, while the browser authenticates to the BFF with cookies. In that case, BFF endpoints receiving requests from the browser still fall under the **cookie CSRF model**.

## 3. Why Do CORS, Content-Type, and SameSite Not Replace CSRF Defense?

**CORS** primarily governs whether scripts from another origin may access responses or send cross-origin requests requiring preflight. An HTML form submitting `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain` typically needs no CORS preflight. The server may have already performed the state change even though the browser blocks the attacker from reading the response.

An API accepting only `application/json` and requiring a custom header forces certain cross-origin requests to preflight. This is a **supplementary barrier**, yet you must enforce the actual Content-Type, avoid parsing other content types, avoid allowing preflights from arbitrary origins with credentials, and avoid assuming every request preflights. The `Origin` header and Fetch Metadata (e.g., `Sec-Fetch-Site`) can strengthen blocking unwanted requests; missing/legacy values need an explicit handling policy.

**SameSite** is a cookie attribute; it does not stop browser auto-sent HTTP Basic, does not fix write endpoints exposed via GET, and does not guarantee distinguishing requests from a same-site yet cross-origin subdomain.

**CSRF tokens** must be verified by the server, typically located in a header or body of state-changing requests. Never place tokens in URLs because they easily leak into logs, history, or Referer headers. If serving tokens via a JSON endpoint, allow only trusted clients to read it, avoid CORS credentials for unknown origins, and avoid shared caching.

## 4. Applying to Spring Security Servlet

In a Servlet application using Spring Security, `CsrfFilter` checks CSRF when the CSRF mechanism is enabled; the default configuration protects HTTP methods outside the safe group `GET`, `HEAD`, `OPTIONS`, and `TRACE`. State-changing methods such as `POST`, `PUT`, `PATCH`, and `DELETE` require a valid token unless intentionally excluded. When missing or invalid, the response is typically **HTTP 403** before reaching the business handler.

For applications using sessions/cookies, Spring Security provides `HttpSessionCsrfTokenRepository` to store tokens per session; browsers can still keep authentication cookies in `HttpOnly` mode. There is no need to disable CSRF simply because the frontend is an SPA or paths begin with `/api/`.

The following configuration sample **is an integration snippet inside a Spring Boot 3 / Spring Security 6+, Java 17+ project** with Spring Web, Spring Security, and OAuth2 Resource Server. Route `/api/token/**` accepts only Bearer JWTs, while browser/session/Basic routes keep CSRF. The project must configure `JwtDecoder` (issuer/JWK) and real users itself; this is not a standalone Java file runnable via `javac`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/token/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserApi(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf").permitAll()
                .anyRequest().authenticated())
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Boundary explanation:

- `@Order(1)` selects the Bearer chain **first** for `/api/token/**`; this chain registers neither form login nor Basic and is intended not to authenticate via cookies. Disabling CSRF on this chain is **appropriate only if that assumption holds**. Audit other filters/entry points, reverse proxies, and any fallback mechanisms.
- `@Order(2)` is the remaining chain; it allows session login and browser HTTP Basic, so it **keeps CSRF**. Do not disable CSRF globally just because the system has some Bearer APIs.
- `SessionCreationPolicy.STATELESS` applies to the Bearer chain; stateless policy alone does not prove an API is immune to CSRF.
- For endpoints like webhooks that must skip CSRF because they receive direct requests from external systems, narrow the exclusion to the exact endpoint and enforce separate signature/authentication verification. Never use `/api/**` as a blanket exclusion when cookies/Basic still exist underneath.

### 4.1. Issuing CSRF Tokens for Frontends Using Sessions/Cookies

With the default session-backed repository, a GET endpoint can let an SPA retrieve the header name and token. The illustrative controller below belongs to a project with Spring MVC; `CsrfFilter` must run on `/api/csrf`:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {
    @GetMapping("/api/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
            request.getAttribute(CsrfToken.class.getName());
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
~~~

Calling `getToken()` also materializes the deferred token when needed (modern Spring Security behavior). After authenticating, a same-origin frontend fetches the token and sends it with write operations:

~~~javascript
const csrfResponse = await fetch("/api/csrf", {
  credentials: "same-origin"
});
if (!csrfResponse.ok) throw new Error("Cannot obtain CSRF token");
const { headerName, token } = await csrfResponse.json();

const response = await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ productId: 42 })
});
if (!response.ok) throw new Error("Order request rejected");
~~~

The JavaScript snippet only illustrates a request to the `/api/orders` business endpoint; the application must have the matching controller, data, and permissions. Since sessions/tokens can change after login/logout or rotation, clients should **re-fetch the CSRF token after logging in or changing sessions**, handle 403s cleanly, and avoid logging tokens.

If choosing `CookieCsrfTokenRepository.withHttpOnlyFalse()` so an SPA reads the `XSRF-TOKEN` cookie and sends the `X-XSRF-TOKEN` header, note:

1. The **CSRF token** cookie may need to be JavaScript-readable; that **does not mean** removing `HttpOnly` from authentication cookies.
2. Spring Security 6 includes token masking to mitigate BREACH risk, alongside deferred token loading. Reading a **raw** token from a cookie and sending it in a header requires a compatible `CsrfTokenRequestHandler` (the SPA pattern documented by Spring Security); merely swapping the repository is not always sufficient.
3. CSRF cookies require proper `Secure`, `Path`, `Domain`, and SameSite configuration. Do not trust subdomains with permission to write cookies for a parent domain; consider binding tokens to sessions and host-only cookies.

### 4.2. When Only Bearer Headers Exist in a Separate API

A pure Bearer resource server API with no cookie/automatic Basic login can disable CSRF on that exact security chain, like `bearerApi` in the example. Access token validation, permission scopes/authorities, expiration, signatures, issuer/audience, and XSS/token-leak prevention must still be enforced.

**Do not confuse them:** a JWT sent in a `Cookie` is evaluated as a cookie; an OAuth2 token in `Authorization: Bearer` manually attached by the client is evaluated as a header. The statement "the API uses JWT so disable CSRF" omits information about the transport channel and browser behavior.

## 5. Testing Scenarios and Interpreting Results

Use a state-changing endpoint with real authentication. In integration tests, send the same request with each credential group and check whether server-side data was modified, rather than inspecting only status codes.

| Test case | Expected when configured properly |
| --- | --- |
| Valid cookie/session, POST missing CSRF token | Blocked, typically `403 Forbidden`; data unchanged |
| Valid cookie/session, wrong CSRF token or token from another session | Blocked; data unchanged |
| Valid cookie/session, valid CSRF token sent in supported header/field | Passes CSRF check; subsequent outcome depends on permissions and business logic |
| Browser cached Basic credentials, POST triggered from foreign origin, missing CSRF token | Blocked if browser actually auto-sends Basic and route has CSRF enabled |
| Bearer-only endpoint, POST without Bearer header | Rejected at authentication step, typically `401`; outcome may depend on entry point |
| Bearer-only endpoint, valid Bearer, no CSRF token | May pass CSRF layer since chain does not require token; still checks authz and business logic |
| Hybrid endpoint accepting both cookie and Bearer, POST from foreign page with only cookie | Must be protected along the cookie path; must not rely on Bearer mode being used by other requests |
| Login/logout or sensitive operation via GET | Design must be fixed; never use side-effecting GETs to evade CSRF checks |

When testing with `curl`/Postman, remember they **do not automatically replicate** browser cookie-sending rules, Basic caching, SameSite, and CORS. Use DevTools/automated browser tests to confirm cookies/headers are actually sent in cross-site scenarios. A POST failing due to missing credentials or SameSite blocking does not prove the entire CSRF configuration is safe.

Distinguish in logs and tests: `401` usually relates to missing/invalid authentication; `403` can stem from CSRF **or** insufficient permissions. Inspect the filter chain, exception, SecurityContext, and presence/absence of data changes to determine the true cause.

## 6. Decision Workflow for a Specific Endpoint

1. **List every authentication method** the route accepts: session cookie, JWT cookie, cached Basic, Bearer header, proxy/BFF, or fallbacks. Do not look only at the "JWT/REST/stateless" label.
2. **Identify which client initiates requests:** browser, SPA, mobile, CLI, or server-to-server. If browsers are involved, check whether credentials are auto-attached when the initiator is another page.
3. **Flag state-changing requests**, including login/logout, password changes, transactions, configuration, and side effects hidden in GET.
4. **If an ambient credential path from browsers exists**, require a CSRF token or sufficiently strong intent verification for unsafe methods; apply SameSite and Origin/Fetch Metadata as supplementary layers.
5. **If the route accepts only client-attached Bearer headers**, you may intentionally exclude CSRF on that chain; verify configuration to ensure no cookie/Basic fallback exists.
6. **Test with both legitimate and coerced requests**, including untrusted origins/subdomains. Verify no data writes occur in blocked cases.

### Common Mistakes

- "Using JWT means no CSRF": wrong if the JWT resides in an auto-sent cookie.
- "HTTP Basic is stateless so disable CSRF": wrong when browsers remember and auto-send Basic.
- "It's `HttpOnly` so CSRF is impossible": `HttpOnly` only restricts reading cookies from JavaScript.
- "Without CORS, malicious forms cannot send POST": untrue for simple forms.
- "Allowing only JSON makes it safe by default": still depends on Content-Type enforcement, CORS/preflight, other endpoints, and input methods.
- "`SameSite=Lax` protects every request": side-effecting top-level GETs, cross-origin same-site requests, and browser policies still apply.
- "Disable CSRF for all `/api/**`": may strip protection from APIs using sessions or Basic.
- "As long as the token is valid, all other attacks are stopped": CSRF tokens do not stop XSS, token theft, broken authorization, or clickjacking.

**Rule to remember:** The decisive question is not "does cookie, Basic, or Bearer sound secure?", but **can the browser automatically send credentials trusted by the server when an attacker triggers a request?** For browser-managed cookies and Basic, evaluate CSRF by default. For application-attached Bearer headers, CSRF tokens are typically unnecessary on routes accepting strictly Bearer, yet always verify the endpoint's actual authentication paths.
