# Deferred CSRF Tokens and Token Masking to Mitigate BREACH Risk

> **Scope:** Spring Security on the Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x; Java 17+). This lesson explains two CSRF-related mechanisms that solve different problems: **deferred CSRF tokens** avoid loading/generating tokens when not yet needed, while **XOR masking** alters the token value emitted in responses to mitigate leaks via HTTP compression side channels (BREACH). Both still operate alongside `CsrfFilter` and `CsrfTokenRepository`.

## 1. Understand the Problem Before Configuring

CSRF (Cross-Site Request Forgery) arises when the browser automatically attaches credentials (especially session cookies) to a request triggered by another page. If the server checks only the cookie, an attacker can try to cause a logged-in user to send a state-changing request. A CSRF token is an unpredictable value that a legitimate page must include in the request; the server compares this value against the token bound to the user's context.

BREACH is a different kind of side-channel attack: when an HTTPS response **is compressed**, and the response simultaneously contains a stable secret alongside attacker-influenced data, compressed response sizes across multiple queries can gradually reveal parts of the secret. TLS does not automatically hide response sizes. If an HTML form always embeds the exact same session CSRF token verbatim, that token can become a target for compression side channels under suitable conditions.

| Mechanism | Question to solve | Primary effect |
| --- | --- | --- |
| **Deferred loading** (`deferred token`) | Does this request actually need to read/generate a token from the repository? | Avoids unnecessary session access or token creation on read-only requests that do not use tokens. |
| **XOR masking** (`XorCsrfTokenRequestAttributeHandler`) | How to avoid consecutive responses containing the exact same secret token string? | Each time the token is placed in a response, produces a different randomized representation; on incoming requests, unmasks to verify the raw token. |

**Do not confuse them:** deferred loading optimizes token lifecycle; XOR masking mitigates token exposure through compression. Disabling one mechanism is not how you enable the other. Masking does not replace CSRF verification, authentication, XSS controls, or cookie policies.

## 2. How Does the Token Move Through the Servlet Filter Chain?

In the normal flow:

1. `CsrfFilter` receives the request and obtains a **deferred token** object from `CsrfTokenRepository`. The repository typically stores the raw token in the HTTP session (`HttpSessionCsrfTokenRepository`), or in a cookie if the application chooses `CookieCsrfTokenRepository`.
2. `CsrfTokenRequestHandler` exposes the token to the rest of the request (such as the `_csrf` attribute used in templates). With an XOR request handler, the value exposed for rendering is the **masked value**, not the raw value.
3. For safe methods (e.g., GET/HEAD/OPTIONS/TRACE), the filter does not require CSRF token comparison by default. If the controller/view does not read the token, the supplier may never be triggered.
4. If the template accesses `_csrf.token`, or an endpoint intentionally returns the token, the token is loaded/generated and formatted to send to the client. If the request belongs to the protected group (typically POST/PUT/PATCH/DELETE), `CsrfFilter` must fetch the expected token and the client-submitted value to compare.
5. For tokens sent from forms/headers in **masked form**, the request handler recovers the original value before comparing against the repository token. Missing or wrong tokens typically result in HTTP **403 Forbidden**.

You can visualize it as:

~~~text
GET page not using CSRF
  -> CsrfFilter -> deferred token -> view does not read token
  -> may avoid loading/generating token

GET form page
  -> CsrfFilter -> deferred token -> view reads _csrf.token
  -> repository loads/creates raw token S
  -> XorCsrfTokenRequestAttributeHandler creates masked representation M
  -> HTML contains M

POST form (session cookie + M)
  -> CsrfFilter -> reads raw token S from repository
  -> request handler unmasks M into S'
  -> compares S' with S -> valid, so processing continues
~~~

The goal is not to have a different token in the repository after every GET: **the raw token can stay the same within the same session**, while the masked value embedded into HTML changes across renders.

## 3. Deferred Loading: When Is the Token Actually Loaded?

### Mechanism

The relevant APIs use `Supplier<CsrfToken>` or an equivalent deferred mechanism to postpone loading/generating. `CsrfTokenRepository` decides how tokens are stored; the request handler decides how token values are exposed and read back. In Spring Security 6, deferred token loading is the default behavior in the standard CSRF pipeline.

**Examples by scenario:**

- `GET /health` does not need a token and no other component forces session loading: no need to read/generate a CSRF token merely because the CSRF filter ran.
- `GET /account/edit` renders a form containing `_csrf.token`: the token is materialized; if absent, the repository can generate and save it.
- `POST /account` requires CSRF verification: must read the expected token; deferral does not mean skipping verification.
- `GET /csrf` returns the token to the frontend: the endpoint intentionally accesses the token, forcing materialization.

Do not treat **whether a request has a session** or **has a Set-Cookie header** as the sole indicator of CSRF. Other components (login, SecurityContext persistence, application code) can also create sessions/cookies. To confirm lazy loading, observe the specific repository and request.

### Benefits and Trade-offs

For applications with many read requests or APIs that do not render forms, deferred loading can reduce session store operations, avoid creating sessions solely to hold a CSRF token, and prevent unnecessary cookies. The actual savings depend on how the application uses sessions and how handlers access the token.

If the application actively calls `getToken()` or `Supplier.get()` on **every** request, deferred-loading benefits are lost on those requests. When JavaScript needs a token, it is usually cleaner to provide a dedicated token-issuing endpoint instead of forcing token generation on every GET.

## 4. XOR Masking: What Is Masked and How Is It Unmasked?

Suppose the raw token stored in the repository is the string `S`. Each time the token needs to be output to a response, the handler generates a fresh random byte sequence `R` of appropriate length, and produces a representation (conceptual illustration):

~~~text
S_bytes = UTF-8(S)
R       = fresh random bytes
X       = R XOR S_bytes
M       = Base64URL(R || X)
~~~

When the client sends back `M`, the handler separates `R` and `X`, computes `R XOR X` to recover `S_bytes`, and matches it against the raw token in the repository. The actual representation is managed by the library; applications should not implement their own decoder from this conceptual description.

Key points:

- **The same `S` can produce countless different `M` values** because a new mask `R` is used each time. This keeps the reflected value in compressed responses from remaining static like the raw token.
- **`M` is not cryptographic encryption:** a party that can directly read the entire `M` also has enough data to recover `S`. Protecting token secrecy still relies on same-origin isolation, XSS prevention, response access control, and session controls.
- XOR masking **does not modify the stored token** in the session/cookie and does not automatically rotate the raw token after each GET.
- Masking reduces one BREACH exploitation vector targeting the CSRF token; it **does not prove all secrets in the response are safe** against compression attacks. Other stably reflected secrets still require separate evaluation.

In Spring Security 6, `XorCsrfTokenRequestAttributeHandler` is the default choice for BREACH protection on CSRF token values exposed in requests. If an application replaces it with a plain `CsrfTokenRequestAttributeHandler`, note that exposed values are no longer XOR-masked as before.

## 5. Typical Servlet Configuration

The following example uses Spring Boot 3.x + Spring Security 6.x and Java 17+. This is a **configuration class in an application with Spring Web/Security dependencies**, not a standalone Java program runnable with a single `javac` command without libraries. The configuration explicitly names the repository and handler for clarity; in standard Spring Security 6 configurations, both the session repository and XOR handler are already the defaults.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/csrf").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
                .csrfTokenRequestHandler(new XorCsrfTokenRequestAttributeHandler()));

        return http.build();
    }
}
~~~

Explanation:

- `HttpSessionCsrfTokenRepository` holds the **raw token** bound to the session; the session cookie links requests to that session.
- `XorCsrfTokenRequestAttributeHandler` manages the **masked** representation when the token appears in request attributes and when the client sends the masked token back.
- Deferred loading is handled through `CsrfFilter`/repository pathways; the snippet above **does not need to manually create a Supplier** or toggle an extra flag.
- `authorizeHttpRequests` controls **authentication/authorization**; it does not imply disabling CSRF. `permitAll()` on `/login` or `/csrf` also does not automatically disable CSRF checking for POST.

### Rendering HTML Forms Server-Side

With Spring MVC + Thymeleaf, the token from the request attribute can be put into a hidden field:

~~~html
<form action="/profile" method="post">
    <label>
        Display name
        <input name="displayName" type="text">
    </label>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Save</button>
</form>
~~~

When the template reads `_csrf.token`, the token is materialized and the rendered value is the **masked value**. The browser sends the hidden field with the session cookie; the server unmasks and compares. In certain Spring MVC/Thymeleaf integrations, automatic hidden CSRF field insertion is already active: **do not insert a duplicate** if the current template already generates that field automatically. When the application runs under a non-`/` context path, generate the action URL using the template/router mechanism instead of hardcoding it as in the example.

Manual test example: load the same form twice using **the same session**. The hidden token may differ between the two responses even though the session's raw token has not changed; both representations remain valid while the session and raw token are active. Do not write logic assuming `_csrf.token` must stay identical across GET requests.

## 6. JavaScript / SPA: Choosing the Right Token Issuance Approach

SPA applications using **session cookies sent automatically with requests** still need a CSRF solution. A common mistake is that SPAs often read raw tokens from a cookie, whereas the default XOR handler expects a **masked value** when parsing tokens from requests.

### Approach A — Endpoint Returning the Token to JavaScript (Preserving the XOR Path)

A same-origin controller can return `CsrfToken` to the frontend:

~~~java
package example.web;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

On the default path with the XOR handler, the token exposed to the controller is in a form suitable for the client to send back via a request parameter/header. Reading the token at this endpoint triggers deferred loading. The frontend must preserve the session cookie and use the returned **header name** (do not guess):

~~~javascript
const csrfResponse = await fetch("/csrf", {
  credentials: "same-origin",
  cache: "no-store"
});
if (!csrfResponse.ok) throw new Error("Cannot obtain CSRF token");

const csrf = await csrfResponse.json();

const saveResponse = await fetch("/api/profile", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ displayName: "Lan" })
});
if (!saveResponse.ok) throw new Error("Save failed");
~~~

This is an illustrative JavaScript snippet **integrating with an existing endpoint**, not a standalone runnable example. The actual endpoint must be same-origin, use HTTPS, and apply appropriate cache policies (prefer `Cache-Control: no-store` for token responses). `csrf.token` is bound to the current session context; after session/authentication changes, re-fetch as needed.

**Advantage:** JavaScript does not need to read a raw CSRF cookie; the default XOR handler still decodes the token; other GET requests are not forced to load CSRF tokens merely to set a cookie for the SPA.

### Approach B — SPA Reads the `XSRF-TOKEN` Cookie and Sends a Raw Header

`CookieCsrfTokenRepository.withHttpOnlyFalse()` lets JavaScript read the CSRF cookie (usually `XSRF-TOKEN`) to send back in a header (usually `X-XSRF-TOKEN`). The value in the cookie is the **raw token**, differing from the XOR representation from the request attribute. If an SPA directly sends the raw token in a header while the server uses the XOR decoder for all sources, requests may receive **403**.

A compatible approach is using a request handler that chooses resolution strategy based on where the token was sent: headers from the SPA are read **plain**, while tokens from forms/request parameters are **XOR-unmasked**. The following class example is for Spring Security 6.x:

~~~java
package example.security;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

public final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        csrfToken.get(); // Cookie needs to be generated/written so the SPA can read it.
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler resolver =
                headerValue != null && !headerValue.isBlank() ? plain : xor;
        return resolver.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Register it in the CSRF configuration:

~~~java
// Replace the csrf(...) configuration of SecurityFilterChain in the example above:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

This registration snippet requires importing `org.springframework.security.web.csrf.CookieCsrfTokenRepository` and is only a **replacement fragment** inside a complete configuration, not a standalone Java statement.

**Trade-off to remember:** calling `csrfToken.get()` in `handle` intentionally materializes the token on every request passing through the handler, to ensure the cookie is present for the SPA. Therefore, this raw-cookie solution trades away part of the **deferred loading** benefit. If the frontend is not required to read a token cookie, Approach A is usually simpler and preserves on-demand loading. Regardless of which approach you choose, ensure the application uses matching token formats where it **issues** and where it **receives** them.

After successful login or logout, authentication-related CSRF components may clear the old token; the SPA should fetch a new token (call `/csrf` or trigger the corresponding cookie-creation path). Do not reuse a token obtained before a session change indefinitely.

## 7. Proper Conditions and Protection Limits

- **CSRF protection is needed when the browser automatically sends credentials:** session cookies, and depending on architecture, HTTP Basic or other auto-attached credentials. APIs returning JSON can still suffer CSRF if authentication relies on cookies.
- **Requests using only Bearer tokens attached manually by JavaScript in the Authorization header** have a different threat model; decide whether to apply CSRF based on the entire authentication flow, not based on the "REST API" label or JSON responses.
- **SameSite cookies** help reduce certain attack paths yet are a supplementary layer; they do not automatically guarantee safety in all cases. CORS, origin, and HTTPS controls must still be configured properly.
- **XSS can invalidate CSRF token security assumptions:** a malicious script running in the same origin can read form/endpoint tokens or send legitimate requests. Address XSS independently.
- **XOR masking only reduces BREACH risk for the masked token**. When compressed responses also reflect other secrets or the application prints raw tokens into HTML/JSON itself, re-evaluate compression exposure. Compression can be restricted on responses containing sensitive secrets depending on the threat model.
- **Never write tokens to URLs/query strings or logs**, because URLs easily leak into history/referrers/logs and token values can appear in unintended places. Prefer hidden form fields or headers.
- **Tokens must match the right session/cookie:** having a well-formed token while using another session's cookie still results in rejection. Avoid caching token-containing responses across users.

## 8. Verifying Behavior and Troubleshooting

### Integration Checklist

1. **GET not needing a token:** send a request to a read-only endpoint that does not render CSRF; verify whether the CSRF path itself avoids loading/creating a token. Do not attribute every new session to CSRF.
2. **GET form twice in the same session:** observe that the two hidden fields receive different masked values; with the valid session, each value can still be submitted to the server.
3. **POST without a token or with a wrong token:** expect rejection at the CSRF layer, typically HTTP 403; distinguish this from authentication/authorization errors that may occur before or after.
4. **POST with a valid token:** with the matching session cookie, the request passes CSRF verification; final outcome still depends on validation, controller logic, and access permissions.
5. **SPA sending headers:** confirm the header name, token retrieval method (masked from endpoint vs. raw from cookie), `credentials`, and repository/handler match.
6. **Login, logout, session expiration:** re-fetch tokens under the new session; test a request with the old token to ensure the rejection path works properly.
7. **Compression and caching:** ensure raw tokens or stable secrets are not accidentally placed in compressed responses susceptible to size measurement; do not cache token endpoints shared across users.

With Spring Security Test/MockMvc, `spring-security-test` provides `.with(csrf())` and `.with(csrf().asHeader())` to test token-bearing branches in controller tests. Those post-processors are convenient for 403/application-path tests, yet **do not replace** integration tests observing masked tokens in HTML or how real clients send headers/cookies.

### Misleading Symptoms

| Symptom | Cause to examine | Resolution |
| --- | --- | --- |
| GET does not generate CSRF cookie/session | Deferred token has not been accessed yet; this may be completely intended. | Only trigger token access on forms or the `/csrf` endpoint when the client needs it. |
| Hidden token changes on every render | Fresh XOR mask on the same raw token. | Do not compare hidden values across GETs expecting a static value. |
| SPA puts cookie token in header and POST gets 403 | Header token is **raw**, while handler expects **masked**. | Use an endpoint returning masked tokens or the raw-header/masked-form handler shown above. |
| POST with right token still gets 403 | Mismatched session cookie, rotated token, different origin endpoint, or separate authorization error. | Inspect session, request header/parameter, handler, cookie flags, and logs. |
| Next request after login/logout gets 403 | Old token was cleared/rotated on authentication transition. | Fetch a fresh token before the next write operation. |
| Thought lazy loading was enabled yet every GET creates a token | Handler/controller/template always calls `get()`/`getToken()`. | Locate what forces materialization; do it only on requests needing a token. |
| Enabled XOR and assumed zero BREACH risk | Response still contains other secrets, or raw token is reflected elsewhere. | Audit all sensitive responses and compression/caching policies. |

## 9. Choosing an Implementation Approach

- **Server-rendered forms, session cookies:** keep Spring Security 6 defaults, using deferred tokens + `XorCsrfTokenRequestAttributeHandler`; views access `_csrf` when needed. This is the simplest flow.
- **SPA with session cookies that can call a token-issuing endpoint:** use `GET /csrf`, receive a masked token, and send it back in the matching header; retains on-demand loading benefits for GETs that do not use tokens.
- **SPA forced to read a raw CSRF cookie:** use `CookieCsrfTokenRepository` with a request handler supporting raw-header/masked-form; understand that forcing cookie materialization on every request increases token overhead.
- **Applications with BREACH security requirements:** avoid emitting stable raw tokens in compressed responses; evaluate other secrets and response-size measurement models as well, rather than viewing XOR as a universal cure-all.

**Remember:** the repository preserves the **raw token**, deferred loading decides **when to load/create the token**, and the XOR handler decides **which representation is sent to the client and how that representation is read back**. All three must align to protect POSTs against CSRF, reduce overhead on token-free requests, and limit BREACH side channels involving rendered tokens.