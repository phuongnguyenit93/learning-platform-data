# CsrfToken, CsrfTokenRepository, and CsrfTokenRequestHandler in Spring Security Servlet

> **Scope:** Spring MVC/Servlet applications using Spring Security 6.x, Java 17+ (typically with Spring Boot 3.x). This lesson focuses on the **Servlet filter chain** CSRF mechanism and does not apply verbatim to Spring WebFlux. The configuration and examples assume the application authenticates users with session cookies.

## 1. Why is a CSRF token needed?

**Cross-Site Request Forgery (CSRF)** occurs when a victim's browser is logged into one website, and another website causes the browser to send a state-changing request to that website. The browser may automatically attach the login cookie; if the server only checks the cookie, it is difficult to distinguish an intentional user request from a tricked one.

For example: a user logs into `https://app.example`, then visits a malicious page containing a form that sends `POST /profile/change-email`. If the backend relies solely on the session cookie, the forged request may be processed. When CSRF protection is enabled, the backend requires an **unpredictable token bound to a valid context** alongside state-modifying requests. A cross-origin page cannot arbitrarily read the token from the target website under the standard browser model.

- Methods considered safe in HTTP semantics (`GET`, `HEAD`, `OPTIONS`, `TRACE`) do not normally require a CSRF token under the default configuration. `POST`, `PUT`, `PATCH`, and `DELETE` are subject to verification. Therefore, **GET must not perform state-changing actions**.
- CSRF is especially important when **the browser automatically sends credentials**, such as session cookies. An API that only accepts a Bearer token actively attached by JavaScript in `Authorization` may have a different risk model, but you must evaluate the entire actual authentication mechanism before excluding CSRF.
- `SameSite` cookies, CORS, `Origin`/`Referer` checks, and CSRF tokens address different aspects. CORS does not prevent all types of requests from another website; `SameSite` has limitations depending on deployment. Do not replace CSRF evaluation with the assumption "the API only accepts JSON".
- A CSRF token is **not an XSS countermeasure**. If an attacker can run JavaScript on the trusted origin itself, they can usually use the legitimate request-sending flow.

## 2. Three Components: Who Holds the Token, Who Stores It, Who Reads the Request?

| Component | Primary responsibility | Not responsible for |
| --- | --- | --- |
| `CsrfToken` | Describes the token to send: header name, request parameter name, token value. | Does not read requests itself or manage storage. |
| `CsrfTokenRepository` | Generates, saves, and loads tokens from storage; supports deferred retrieval. | Does not decide whether the client's submitted token is in a header or form, nor how the rendered value is masked. |
| `CsrfTokenRequestHandler` | Exposes the token as a request attribute for the view layer and resolves **the token value sent by the client** (header/parameter, possibly needing unmasking). | Does not decide token validity by directly querying storage. |
| `CsrfFilter` | Coordinates the repository and handler, checks the token on protected requests, and rejects invalid requests. | Does not replace the above components with a single object. |

Relationship within a Servlet request:

~~~text
HTTP request
    |
    v
Spring Security filter chain
    |
    v
CsrfFilter
    |--- CsrfTokenRepository: obtain DeferredCsrfToken
    |--- CsrfTokenRequestHandler.handle(...): prepare request attribute
    |
    +--- Safe request (typically GET) --> continue processing;
    |        if view/controller accesses the token, the token is loaded/generated
    |
    +--- Protected request (typically POST/PUT/PATCH/DELETE)
             |--- load expected token via repository
             |--- requestHandler.resolveCsrfTokenValue(...): read submitted token
             |--- compare submitted token with expected token
                     |--- valid --> filter chain continues
                     +--- missing/wrong --> AccessDeniedHandler (typically HTTP 403)
~~~

Core point: the repository answers **"which token is the server expecting?"**; the request handler answers **"which token did the client actually send, and in what form?"**; `CsrfFilter` compares the two results.

## 3. `CsrfToken`: A Small Yet Crucial Data Contract

`org.springframework.security.web.csrf.CsrfToken` is an interface with three methods:

~~~java
public interface CsrfToken {
    String getHeaderName();
    String getParameterName();
    String getToken();
}
~~~

- `getHeaderName()`: HTTP header name where the client can send the token, e.g., `X-CSRF-TOKEN` or `X-XSRF-TOKEN`.
- `getParameterName()`: form parameter name, usually `_csrf` by default.
- `getToken()`: the value to present/send according to the request handler mechanism. Distinguish the **stored raw token** from the **masked value used in forms** in section 5.

`DefaultCsrfToken` is an implementation carrying these three properties. Never create tokens with hardcoded strings or embed tokens in source code. Tokens must be generated and managed with an appropriate lifecycle by the repository.

Example of a valid server-rendered form request:

~~~html
<form method="post" action="/profile">
  <input type="hidden" name="_csrf" value="SERVER_RENDERED_TOKEN">
  <button type="submit">Save changes</button>
</form>
~~~

`SERVER_RENDERED_TOKEN` is an **illustrative placeholder**, not a real value or a command to copy verbatim. The template layer must insert the proper token for the current request. With Thymeleaf and Spring Security, the token can be read from the `_csrf` request attribute:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Spring Security can automatically add the hidden field in forms properly integrated with Spring MVC/Thymeleaf rendering; if building forms manually, inspect the actual HTML to ensure the token is sent. With an XOR handler, the value rendered into the form may **differ from the raw token string** stored by the repository; this is intentional.

## 4. `CsrfTokenRepository`: Generating, Saving, Loading, and Deferring Token Loading

Core contract:

~~~java
public interface CsrfTokenRepository {
    CsrfToken generateToken(HttpServletRequest request);

    void saveToken(
        CsrfToken token,
        HttpServletRequest request,
        HttpServletResponse response
    );

    CsrfToken loadToken(HttpServletRequest request);
}
~~~

Modern Spring Security versions also support `loadDeferredToken(request, response)`, returning a `DeferredCsrfToken` to defer loading/generating the token until needed. Deferral avoids creating a session or accessing session data on requests that never use a CSRF token. Only when handling code actually accesses the token does loading/generation/saving occur.

### Two Common Repositories

**`HttpSessionCsrfTokenRepository`**

- Stores the token in the server-side `HttpSession`; suitable for MVC applications authenticating with sessions and server-rendered forms.
- The token is verified against data belonging to the browser's session. The browser typically only needs the session cookie; forms/JS receive the separate token to send back.
- This is the common default storage in Spring Security Servlet. There is no need to switch to a cookie repository if the application only uses forms and sessions.

**`CookieCsrfTokenRepository`**

- Stores the token in a cookie; the default cookie name is usually `XSRF-TOKEN`, the default HTTP header is `X-XSRF-TOKEN`, and the parameter is `_csrf`. This model is often used when an SPA needs to read the token from a cookie and attach it to a header.
- The cookie holding the CSRF token is **distinct from the authentication cookie**. The client must still send the token via the corresponding header/parameter; having the cookie sent automatically alone is not sufficient as active proof of the request.
- `CookieCsrfTokenRepository.withHttpOnlyFalse()` allows JavaScript to read the CSRF cookie to set the header. Use this only when the client flow requires it; `HttpOnly=false` makes this value readable by scripts on the origin. XSS protection and cookie policies remain vital.
- You must configure `Secure`, `SameSite`, `Path`, cookie domain, and reverse proxy settings per deployment environment. Do not assume every SPA or cross-origin deployment works with default settings.

### Generating and Clearing Tokens

- `generateToken` creates a new `CsrfToken`; `saveToken` is responsible for storing it. `loadToken` returns the saved token or `null` if none exists.
- `saveToken(null, request, response)` is used to delete/invalidate the saved token; how deletion works depends on the repository. Authentication-success/logout mechanisms may clear old tokens to prevent continuing to use a token from before a security event.
- When a token is cleared and creating a new token is deferred, an SPA may have to make a CSRF initialization request again before the next `POST`. This explains the case "logged in, then the first POST gets 403" even though the login session is valid.

Do not store tokens in logs, analytics, or URL query strings. Do not embed a shared token for all users into publicly cached static HTML.

## 5. `CsrfTokenRequestHandler`: Request Attributes and How Submitted Tokens Are Read

Two key methods of `CsrfTokenRequestHandler`:

~~~java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    Supplier<CsrfToken> deferredCsrfToken
);

String resolveCsrfTokenValue(
    HttpServletRequest request,
    CsrfToken csrfToken
);
~~~

`handle` receives a supplier to prepare how the token is exposed to the current request, such as the `_csrf` attribute in MVC. It does not necessarily have to call `get()` immediately, so it can preserve the deferred mechanism. `resolveCsrfTokenValue` receives the request and expected token to locate or transform **the value submitted by the client**; `CsrfFilter` is what checks whether the two values match.

### `CsrfTokenRequestAttributeHandler`: Plain Values

This handler exposes the token in a request attribute and reads the value sent via header or parameter. In unmasked flows, the exposed value directly corresponds to the raw token. It is suitable when you want "plain" token handling, but **does not automatically provide BREACH-mitigating masking** for tokens embedded in HTML.

### `XorCsrfTokenRequestAttributeHandler`: Masking to Mitigate BREACH Risk

Spring Security 6 uses `XorCsrfTokenRequestAttributeHandler` by default in standard Servlet CSRF configurations. When a token appears in a compressed response (e.g., an HTML form), repeating the raw token can create a signal for **BREACH**-style attacks. The XOR handler applies random noise/masking to the exposed value on each render, then unmasks the form-submitted value to compare against the raw token.

Distinguish:

- **Raw token**: the value stored by the repository; does not mean it changes on every GET.
- **Masked token value**: may differ across renders, yet still represents the same raw token.
- **Client-submitted value**: a server-rendered form may submit a masked value; an SPA reading the token from a cookie holds the **raw value**. Therefore, using the wrong handler to read that value type can result in HTTP 403.

Do not misinterpret "the token changes on every render" as "the repository generated a new token each time". That may simply be the difference in BREACH-protective representation.

### Choosing the Right Handler for the Token Submission Path

| Client flow | Where the token is obtained | How it is sent | Requirement for the request handler |
| --- | --- | --- | --- |
| MVC/Thymeleaf form | Request attribute exposed by Spring Security | Hidden parameter `_csrf` | Handler compatible with rendered tokens; default XOR meets this. |
| JavaScript reading token from cookie | `XSRF-TOKEN` cookie readable by JS | Header `X-XSRF-TOKEN` | Must accept the raw token from the header. |
| App both rendering forms and using an SPA | Form: masked; JS: raw cookie | Parameter and header | Handler must properly handle **both formats**, not equate them automatically. |

## 6. Standard MVC Application Configuration: Keep Defaults

For server-rendered applications authenticating via sessions, you typically only need to configure authentication and authorization, leaving CSRF at its defaults. The following snippet is a Spring Boot configuration class with `spring-boot-starter-security` and `spring-boot-starter-web` dependencies; it will not compile standalone with `javac` without Spring libraries:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

When a GET page displays a data-modifying form, the template reads the token from `_csrf` and puts it into the POST form. The browser sends the session cookie alongside the hidden parameter; `CsrfFilter` looks up the expected token via the session repository, delegates to the handler to decode the masked token (if any), and compares them. If the token is missing/wrong, the response is usually 403 right at the filter, before the controller runs business logic.

**Note:** use either this configuration **or** the SPA configuration in section 7 for a corresponding filter chain. Do not copy both `SecurityFilterChain` beans matching all requests into the same application.

## 7. SPA Reading Cookies Case: Coordinating Repository and Handler

This example targets an SPA on the **same origin** as the backend, authenticating with session cookies, needing to read `XSRF-TOKEN` to send a header. It preserves XOR for forms/server-rendered views, while accepting raw tokens when a request includes the header. This is a deliberate configuration choice; it is not a universal default suitable for every architecture.

**File `SpaCsrfTokenRequestHandler.java`:**

~~~java
package demo.security;

import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> deferredCsrfToken) {
        // Keep the masked value for HTML forms.
        xor.handle(request, response, deferredCsrfToken);

        // Force loading/generating the token so the repository can send the cookie.
        deferredCsrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());

        // SPA header: raw token; form parameter: masked token.
        CsrfTokenRequestHandler handler =
                headerValue != null && !headerValue.isBlank()
                        ? plain
                        : xor;

        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

**File `SpaSecurityConfig.java`:**

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
@EnableWebSecurity
public class SpaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()));

        return http.build();
    }
}
~~~

**File `CsrfBootstrapController.java`:**

~~~java
package demo.security;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    public ResponseEntity<Void> bootstrap() {
        // The CSRF filter already triggered token loading before the controller.
        return ResponseEntity.noContent().build();
    }
}
~~~

Here, `GET /csrf` is simply an initialization request so the response has a chance to issue the cookie; the controller does not return the token in the body. With `SpaCsrfTokenRequestHandler`, `deferredCsrfToken.get()` guarantees the token is loaded or generated, rather than relying on whether an MVC view reads the token.

**JavaScript client (illustrative for a same-origin browser):**

~~~javascript
// Re-initialize the token on app startup and after auth state changes.
await fetch("/csrf", { credentials: "same-origin" });

const pair = document.cookie
    .split("; ")
    .find(value => value.startsWith("XSRF-TOKEN="));

if (!pair) {
    throw new Error("Missing XSRF-TOKEN cookie; check GET /csrf and cookie policy");
}

const csrfToken = decodeURIComponent(pair.slice("XSRF-TOKEN=".length));

const response = await fetch("/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ displayName: "Lan" })
});

if (!response.ok) {
    throw new Error("Failed to save profile: HTTP " + response.status);
}
~~~

A `POST /profile` endpoint and a properly logged-in user are required; the JavaScript snippet does not create those components. `GET /csrf` may still need to be called again after login/logout because the old token has been invalidated. If the application operates across multiple origins, separate cookie/CORS/credentials/CSRF analysis must be added; do not reuse the same-origin example verbatim.

### Why Setting Only `CookieCsrfTokenRepository.withHttpOnlyFalse()` May Not Be Enough

The repository determines the token in the cookie and the expected header; the default **request handler** may still expect an XOR-masked token. If JavaScript reads the **raw token** from the cookie and sends the header while the handler decodes it as an XOR token, the request can receive a 403. The coordinating handler in the example branches based on the header to choose how to resolve it, while continuing to expose a masked value for forms.

Do not use an unmasked `CsrfTokenRequestAttributeHandler` on every request merely to fix 403 errors without evaluating the BREACH impact on responses containing tokens in HTML.

## 8. Concrete Lifecycle: Read, Generate, Use, Refresh

### 8.1 Server-Rendered MVC Pages

1. Browser sends `GET /profile` with the session cookie.
2. `CsrfFilter` obtains the deferred token from the repository. The handler prepares the `_csrf` request attribute.
3. When the view accesses `_csrf.token`, the token is loaded/generated. If using the XOR handler, the token exposed to the form is a masked version.
4. The view renders a hidden field with the exact parameter name and token value.
5. Browser sends `POST /profile` with the session cookie and `_csrf` parameter.
6. The filter fetches the server-expected token, the handler decodes/reads the token from the request; only if valid does the controller run.

### 8.2 SPA Using a CSRF Cookie

1. The SPA calls `GET /csrf` so the browser receives or updates the `XSRF-TOKEN` cookie.
2. The client reads the cookie and sends the raw token in `X-XSRF-TOKEN` on state-changing requests.
3. The filter loads the expected token via `CookieCsrfTokenRepository`; the branching handler uses the plain header-reading path.
4. After login/logout or upon session change, the client performs the token re-initialization step if the old token was cleared.

### 8.3 Missing or Invalid Token

- No expected token in the repository: protected request is rejected, typically 403.
- Token exists server-side but client does not send parameter/header: typically 403.
- Client sends token from another session, stale token, wrong header name, or raw token hits a handler expecting masked: typically 403.
- A 403 **does not by itself prove** the error is CSRF; authentication, authorization, exception handling, or the controller can also cause errors. Identify the actual filter/exception before fixing.

## 9. Testing CSRF with MockMvc

For Spring MVC, the test dependency `org.springframework.security:spring-security-test` provides `csrf()`. The following example assumes the application in section 6 has a `POST /profile` controller returning HTTP 200 after passing security:

~~~java
package demo.security;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @PostMapping("/profile")
    public String saveProfile() {
        return "saved";
    }
}
~~~

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectPostWithoutCsrf() throws Exception {
        mvc.perform(post("/profile").with(user("alice")))
           .andExpect(status().isForbidden());
    }

    @Test
    void acceptPostWithCsrf() throws Exception {
        mvc.perform(post("/profile")
                .with(user("alice"))
                .with(csrf()))
           .andExpect(status().isOk());
    }

    @Test
    void rejectInvalidToken() throws Exception {
        mvc.perform(post("/profile")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
           .andExpect(status().isForbidden());
    }
}
~~~

The example requires a Spring Boot project with MVC, Security, `spring-security-test`, JUnit 5, and a bootable application. Place the configuration, controller, and tests in a package scanned by Spring Boot component-scan. Run via the project's Gradle/Maven (e.g., `./gradlew test`); do **not** expect standalone compilation with only `javac`. This test demonstrates the CSRF contract of the MVC configuration in section 6; when testing an SPA, include integration tests using the cookie repository, `X-XSRF-TOKEN` header, and actual token-loading flow.

Test both passing **and** failing cases. An endpoint returning 403 because the user is not logged in does not prove CSRF works; that is why the test grants a user before checking the token.

## 10. Common Errors and How to Diagnose Them

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Form POST returns 403 even when logged in | Form missing `_csrf`, rendered wrong name/value, lost session, token invalidated. | Inspect HTML form, request payload, and session; use the current request's token. |
| First SPA POST after login returns 403 | Token cookie cleared on auth state change; new token not yet initialized due to deferred loading. | Call bootstrap GET to issue token/cookie after login before POSTing. |
| `XSRF-TOKEN` cookie exists yet header is still invalid | Client did not send `X-XSRF-TOKEN`; sent wrong value; handler tried to XOR-decode a raw value. | Inspect actual headers and the request handler strategy. |
| Token in HTML changes on every reload | XOR handler generates a new masked representation. | Distinguish masked representation from raw token before concluding the repository is rotating. |
| `csrf().disable()` makes 403 disappear | CSRF policy was blocking the request, likely because the client passed the wrong token. | Fix token issuance/sending/resolution; only disable CSRF if the threat model permits and on the right filter chain. |
| Same POST works in MockMvc but fails in browser | Browser also enforces cookie path/domain, SameSite, Secure, credentials, Origin. | Inspect Network request/response headers and reverse proxy environment. |
| GET form has side effects | Endpoint design violates safe-method semantics; GET usually requires no CSRF token. | Move data-modifying operation to a protected method and add the token. |

When diagnosing:

1. Identify which `SecurityFilterChain` the request enters; with multiple chains, CSRF configs may differ.
2. Identify whether the repository stores in session or cookie, and whether the real request carries the right session/cookie.
3. Identify whether the handler expects a **plain header** or **masked parameter**; verify header/parameter names instead of assuming.
4. Compare token presence and lifecycle **without logging secret values**. Enable controlled security debug logging, avoiding logging request bodies/headers containing tokens in real environments.
5. Check login, logout, session expiration, cookie domain/path, proxies, and browsers. Only afterward adjust matchers or CSRF configuration.

## 11. When Should You Customize?

- **Standard form/session applications:** prefer default `HttpSessionCsrfTokenRepository` and XOR handler. Most applications do not need custom repository/handler implementations.
- **SPAs using session cookies and adding CSRF headers themselves:** consider `CookieCsrfTokenRepository` and a handler that properly understands raw headers; clearly decide whether `HttpOnly=false` is needed and how tokens are initialized.
- **Specialized integrations:** only write a custom `CsrfTokenRepository` when a genuinely different store/token cycle is required (e.g., distributed storage with explicit constraints); test generation/saving/loading/deletion, concurrent requests, and session boundaries.
- **Webhooks/APIs not using authentication cookies:** consider separate chain/matcher configuration if requests cannot be exploited via browser auto-authentication mechanisms. Webhooks still need their own authentication mechanism (signature/HMAC or equivalent), not merely CSRF exclusion.
- **Multi-chain applications:** use `securityMatcher`/chain ordering intentionally; one chain's CSRF config does not automatically apply to requests handled by another chain.

## 12. Self-Check Knowledge Questions

1. When `POST /transfer` lacks a CSRF token, which component reads the expected token, which resolves the client-submitted token, and which rejects the request? **Answer:** repository, request handler, then `CsrfFilter`.
2. Why can `_csrf.token` in HTML differ on every render while the session token stays unchanged? **Answer:** the XOR handler creates different masked representations, without necessarily generating a new raw token.
3. Why can switching from a session repository to a cookie repository cause an SPA to get 403? **Answer:** token name/source, JS ability to read the cookie, header submission, and how the handler resolves plain/masked tokens must be compatible.
4. When is calling `GET /csrf` needed after login? **Answer:** when the old token was cleared and a new token is loaded/generated on demand; the SPA needs to receive the token before state-changing requests.
5. Why is `with(csrf())` in tests insufficient to conclude all authorization is correct? **Answer:** the helper only provides a valid CSRF token; authentication/authorization and business logic are still verified separately.

**Remember:** `CsrfToken` carries token data; `CsrfTokenRepository` manages tokens server-side; `CsrfTokenRequestHandler` formats/exposes tokens and reads client-submitted values; `CsrfFilter` coordinates and decides whether to block requests lacking a valid token.