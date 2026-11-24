# Sending CSRF Tokens in Forms or Headers

> **Spring Security fundamentals → CSRF.** An application using login sessions/cookies must send a **CSRF token** in a form field (commonly named `_csrf`) or in an HTTP header (commonly `X-CSRF-TOKEN` or `X-XSRF-TOKEN`) when issuing state-changing requests. This lesson covers principles, Servlet flow, Spring Boot 3.x / Spring Security 6.x / Java 17+ code, practical testing with MockMvc, and notes for JavaScript/SPAs, BREACH, cookies, logout, session timeouts, and WebFlux.

## 1. Why Must a CSRF Token Accompany the Request?

When a user is logged into a website via a cookie, the browser can automatically attach qualifying cookies to requests. A page on another website can cause the browser to send a request to the legitimate website via forms, navigations, or other triggers. If the backend only sees the login cookie and accepts every operation, a forged request can make changes under the victim's identity.

For example, the following HTML snippet comes from **another website**, not a trusted form:

```html
<form action="https://accounts.example.org/profile/email" method="post">
  <input type="hidden" name="newEmail" value="other@example.net">
  <button type="submit">Continue</button>
</form>
```

Depending on `SameSite`, browser policy, and environment, the request can carry the user's login cookie. The foreign site does not need to know the password to trigger the request.

**Synchronizer token pattern idea:** The server creates a token bound to a session or trusted context. The legitimate UI reads the server-provided token and sends it **via a body field or dedicated header**. The browser **does not auto-create/send that field/header merely because a cookie exists**. The server compares the token against the expected value in `CsrfTokenRepository` and blocks requests with missing or wrong tokens **before performing any mutation**.

```text
Browser with session cookie                 Spring Security
    |                                           |
    | GET /form or GET /csrf                    |
    |------------------------------------------>|
    | page/JSON containing valid CSRF token     |
    |<------------------------------------------|
    |                                           |
    | POST /api/preference                      |
    | Cookie: JSESSIONID=...                    |
    | _csrf=<token>  OR                         |
    | X-CSRF-TOKEN: <token>                     |
    |------------------------------------------>|
    |                                           |
    |             CsrfFilter checks token       |
    |                    |                      |
    |          +---------+---------+            |
    |          |                   |            |
    |        valid           missing/wrong      |
    |          |                   |            |
    |  authentication/        reject,           |
    |  authorization/         usually 403       |
    |  controller                               |
```

**CSRF tokens do not replace authentication or authorization.** A request carrying a valid token must still verify whether the user is logged in and permitted to modify the resource. Conversely, a logged-in user who fails to submit a valid CSRF token is still rejected on protected requests.

### 1.1. Threat Model and Scope

CSRF primarily involves credentials that browsers **automatically send** by context, such as session cookies and sometimes HTTP Basic or cookie-stored tokens. If a purely stateless API accepts only Bearer access tokens **actively placed in `Authorization`** by clients, with no auto-attached credentials, the cookie-style CSRF threat differs. However, cookie-based refresh/logout endpoints, session-backed SPAs, or hybrid systems still need CSRF evaluation. Never conclude "REST APIs always disable CSRF".

`SameSite` cookies, Origin/Referer validation, CORS, and CSRF tokens serve complementary rather than fully equivalent roles. Same-origin XSS can read or abuse tokens issued to the UI; therefore XSS must be mitigated separately.

## 2. Which Requests Need a Token and Where Should It Go?

Per HTTP semantics, `GET`, `HEAD`, `OPTIONS`, and `TRACE` are considered safe methods; Spring Security Servlet skips CSRF for them by default. `POST`, `PUT`, `PATCH`, and `DELETE` requests are protected when CSRF is enabled.

**Critical condition:** GET must truly not mutate data. Designing `GET /remove-account` to delete accounts breaks the safe-method assumption; browser link prefetching or an external site embedding a link/image can trigger side effects.

| Client / content | Typical token transport | Notes |
|---|---|---|
| HTML form using POST | Hidden input `_csrf` in form body | Value obtained from server for the right session |
| Server-rendered Thymeleaf/JSP | Auto-inserted or manually rendered hidden input | Template engine must integrate CSRF |
| Fetch/AJAX sending JSON | `X-CSRF-TOKEN` header | Client must actively read token and send header |
| Spring SPA using CSRF cookie | `XSRF-TOKEN` cookie read by JS and sent in `X-XSRF-TOKEN` | Must handle Spring Security 6 raw vs. masked tokens |
| Multipart upload | Prefer header if appropriate | Avoids parsing upload body before CSRF filter |
| Stateless Bearer backend | Decide based on credential transport | Never toggle CSRF by guesswork |
| Read-only GET request | Normally no CSRF needed | Still requires authorization if private |

**Do not put CSRF tokens in URL query strings.** URLs easily end up in access logs, browser history, analytics, link previews, or `Referer` headers. Use body parameters or headers.

## 3. Spring Security Components

| Component | Function |
|---|---|
| `CsrfFilter` | Checks token on protected requests before continuing down the filter chain |
| `CsrfToken` | Provides `getToken()`, `getParameterName()`, `getHeaderName()` |
| `CsrfTokenRepository` | Generates, stores, and retrieves expected tokens |
| `HttpSessionCsrfTokenRepository` | Stores expected token in Servlet `HttpSession`; common default mechanism |
| `CookieCsrfTokenRepository` | Uses a cookie holding the token, typically `XSRF-TOKEN` |
| `CsrfTokenRequestHandler` | Exposes token to views and resolves submitted token from parameter/header |
| `XorCsrfTokenRequestAttributeHandler` | Common default in Spring Security 6, adding masking to mitigate BREACH |
| `CsrfTokenRequestAttributeHandler` | Does not use XOR masking; useful when handling raw tokens from SPA headers |
| `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` | Can clear old tokens upon successful authentication/logout |
| `AccessDeniedHandler` | Chooses how rejections are returned, including CSRF failures |

An unsafe request follows logic like:

```text
POST /api/preference
    |
    v
CsrfFilter
    |
    +--> Is CSRF required?
    |      |
    |      +--> No: continue
    |      |
    |      +--> Yes: load/create expected token from repository
    |               |
    |               v
    |          Request handler reads token
    |          from _csrf parameter or header
    |               |
    |               v
    |          Compare with expected token
    |            |               |
    |          match       mismatch/missing
    |            |               |
    |         continue       403 (usually)
    |
    v
Authentication + HTTP/Method/Object authorization
    |
    v
Controller and service
```

Spring Security 6 uses **deferred CSRF tokens** to avoid unnecessary session creation/reads. Calling `getToken()` from a view/controller causes the required token to be loaded/generated when actually used.

## 4. Method 1 — CSRF Token in an HTML Form

### 4.1. Hidden Input

A valid HTML form must include the server's token in the form submitting the request:

```html
<form method="post" action="/api/preference">
  <label for="theme">Theme</label>
  <select id="theme" name="theme">
    <option value="light">Light</option>
    <option value="dark">Dark</option>
  </select>
  <input type="hidden" name="_csrf" value="SERVER_RENDERED_TOKEN">
  <button type="submit">Save</button>
</form>
```

`SERVER_RENDERED_TOKEN` in this doc is **illustrative**, not a usable token. The real value must be replaced with `CsrfToken.getToken()` supplied by Spring Security for the session/view. The form submits data as:

```http
POST /api/preference HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

theme=dark&_csrf=<server-issued-token>
```

The browser attaches the cookie automatically; the token is sent because it lives inside the legitimate form the user interacts with. Another form on a foreign site does not know the token bound to the victim's session.

**Do not hardcode the field name if customized:** `CsrfToken.getParameterName()` returns the active name; `getToken()` returns the value for the field per request handler. Token values must not be cached as public shared HTML.

### 4.2. Thymeleaf and Template Engines

With template engines integrating `RequestDataValueProcessor`, like Thymeleaf in standard Spring MVC setups, hidden CSRF inputs can be inserted automatically for unsafe-method forms. With JSP or manual HTML rendering, access the `_csrf` request attribute and render the field.

When writing it manually, ensure:
- The hidden input actually sits **inside the submitted form**.
- There are not two fields with the same name and differing tokens.
- The value comes from the current request/session, not hardcoded or from another user's token.
- If submitted after session expiration/login/logout, the UI fetches a new token.
- HTML escaping fits the template, and responses have proper cache policies for session-specific content.

A JSP-style example:

```html
<input type="hidden"
       name="CSRF_PARAMETER_NAME_FROM_REQUEST"
       value="CSRF_TOKEN_VALUE_FROM_REQUEST">
```

Here the two uppercase values simply illustrate dynamic placeholders; replace them with your view engine's expressions rather than copying them literally into an app.

### 4.3. A CSRF Token Is Not a Secret Hidden from the User

Users can view `_csrf` in DevTools. This is not a bug: the token prevents another origin from reading legitimate page contents, rather than hiding it from the session owner. If a user has UI access yet lacks permission to edit another record, the server must still check ownership/tenant/permissions.

## 5. Method 2 — CSRF Token in an HTTP Header

Apps using `fetch` or AJAX can read the token from an HTML meta tag or a `GET /csrf` endpoint, then attach a header on POST/PUT/PATCH/DELETE.

```http
POST /api/preference HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>
X-CSRF-TOKEN: <server-issued-token>

theme=dark
```

There is no need to send both `_csrf` and the header simultaneously; pick one approach consistent with your repository/request handler. The header does not replace the login cookie in session-based apps; **each serves a distinct purpose**.

### 5.1. Header Name Depends on the Repository

| Common setup | Field name | Header name |
|---|---|---|
| `HttpSessionCsrfTokenRepository` | `_csrf` | `X-CSRF-TOKEN` |
| `CookieCsrfTokenRepository` | `_csrf` | `X-XSRF-TOKEN` |
| Custom repository/handler | Per configuration | Per configuration |

Preferably read `CsrfToken.getHeaderName()` from the server instead of assuming every app uses `X-CSRF-TOKEN`.

### 5.2. Same-Origin Fetch

In the runnable example in section 6, `GET /csrf` returns JSON containing field name, header name, and token; JS can use:

```javascript
async function updateTheme(theme) {
  const bootstrap = await fetch("/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!bootstrap.ok) {
    throw new Error("Failed to load CSRF token");
  }
  const csrf = await bootstrap.json();

  const response = await fetch("/api/preference", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrf.headerName]: csrf.token,
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: new URLSearchParams({ theme })
  });
  if (!response.ok) {
    throw new Error("POST rejected or failed");
  }
  return response.json();
}
```

Here JavaScript **does not generate the token itself**, does not use the session ID as a token, and does not put the token in the URL. When sending JSON requests, the JSON body works normally; the header token is handled by `CsrfFilter` before the controller, without requiring a form-urlencoded body.

## 6. Runnable Spring Boot 3.x / Java 17+ Example

Create a project with Spring Initializr, Java 17+, selecting **Spring Web** and **Spring Security**. Use the project's Gradle Wrapper.

### 6.1. Dependencies

In the `build.gradle` of a project that already includes Boot plugins/repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is **only the dependencies block**, not the entire `build.gradle`. `spring-security-test` provides `csrf()`, `csrf().asHeader()`, and `user()`.

### 6.2. Complete Java File

Create `src/main/java/example/csrf/CsrfFormHeaderApplication.java`:

```java
package example.csrf;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfFormHeaderApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormHeaderApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/form", "/csrf", "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/preference")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/preference")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            // CSRF enabled by default. Do not call csrf.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {
    private final Map<String, String> themes =
        new ConcurrentHashMap<>();

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping(value="/form", produces=MediaType.TEXT_HTML_VALUE)
    String form(CsrfToken csrf) {
        return """
            <!doctype html>
            <html lang="en">
              <head><meta charset="UTF-8"></head>
              <body>
                <form action="/api/preference" method="post">
                  <select name="theme">
                    <option value="dark">Dark</option>
                    <option value="light">Light</option>
                  </select>
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Save</button>
                </form>
              </body>
            </html>
            """.formatted(
                csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        // Expose only to same-origin JS; avoid shared caches.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "parameterName", token.getParameterName(),
                "headerName", token.getHeaderName(),
                "token", token.getToken()));
    }

    @PostMapping("/api/preference")
    Map<String, String> update(
            @RequestParam String theme, Authentication auth) {
        if (!"dark".equals(theme) && !"light".equals(theme)) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "Unsupported theme");
        }
        themes.put(auth.getName(), theme);
        return Map.of("user", auth.getName(), "theme", theme);
    }

    @GetMapping("/api/preference")
    Map<String, String> read(Authentication auth) {
        return Map.of(
            "user", auth.getName(),
            "theme", themes.getOrDefault(auth.getName(), "unset"));
    }
}
```

### 6.3. Breakdown of Each Part

1. `/form` and `/csrf` are open to anonymous users to learn token loading, while the controller prevents anonymous users from mutating data. In production, design origin/CORS/caching so tokens are not leaked via cross-origin reads.
2. `/api/preference` GET and POST require `authenticated()`. `anyRequest().denyAll()` denies undeclared endpoints.
3. Spring Security's `formLogin` provides a default login page; login POST is also covered by CSRF protection.
4. `GET /form` injects `CsrfToken`, invokes `getToken()` to materialize the token, and renders the hidden field. In Spring Security 6, the rendered value may be **masked** to mitigate BREACH.
5. `GET /csrf` returns the token alongside the `headerName` the client must attach on POSTs. `Cache-Control: no-store` reduces the risk of caching responses containing session tokens.
6. `POST /api/preference` is never invoked if `CsrfFilter` rejects the request; after passing the filter, authentication and theme validation still apply.
7. The in-memory map is illustrative only; not multi-node storage, with no database or tenant separation. To enforce owner/role rules, add policies at the service/repository layer.
8. `{noop}` **does not hash passwords**. Use only for local demos; production requires proper password hashing/identity providers, HTTPS, session cookie hardening, and auditing.

### 6.4. Running with Gradle

```bash
./gradlew bootRun
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
.\gradlew.bat test
```

Run each command per purpose: `bootRun` keeps the server process running, `test` runs tests in a separate Gradle task.

Steps to try in a browser:

1. Visit `http://localhost:8080/login`, log in as `alice/demo123` using the default form.
2. Open `http://localhost:8080/form` after login to fetch the latest CSRF token. Pre-login tokens may be cleared upon successful authentication.
3. Inspect the actual HTML in DevTools: a hidden input named `_csrf` must contain a server-provided value.
4. Submit the form and receive JSON like `{"user":"alice","theme":"dark"}` if dark was selected.
5. Remove the hidden field and submit while still logged in: Spring Security must reject the request (typically 403).
6. Try `GET /api/preference` while logged in: GET needs no token, yet still requires authentication.

When the app runs under a non-root context path, the form action `/api/preference` must be adjusted via your template engine/router's URL builder. Never copy real session cookies or CSRF tokens into screenshots, issues, or logs.

### 6.5. Sending Headers with curl Keeping the Same Session

On a local machine with `curl` and `jq`, while the server is running:

```bash
csrf="$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')"

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=alice" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$csrf" \
  http://localhost:8080/login

# Refresh token after login, as the old token may be cleared.
csrf="$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')"

curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "theme=dark" \
  http://localhost:8080/api/preference
```

`cookies.txt` preserves the session between fetching the CSRF token and sending the request; tokens do not work across different sessions. With real accounts, never expose cookie jars or tokens in shell history/logs. In browsers, the cookie jar is managed by browser policy rather than this file.

## 7. MockMvc Testing: Forms, Headers, Missing Tokens, Invalid Tokens

Create `src/test/java/example/csrf/CsrfFormHeaderApplicationTest.java`:

```java
package example.csrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormHeaderApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void htmlFormContainsTokenField() throws Exception {
        MvcResult page = mvc.perform(get("/form"))
            .andExpect(status().isOk())
            .andReturn();
        String html = page.getResponse().getContentAsString();
        assertThat(html).contains("name=\"_csrf\"");
        assertThat(html).contains("method=\"post\"");
        assertThat(page.getRequest().getSession(false))
            .isNotNull();
    }

    @Test
    void missingTokenRejectsAuthenticatedPost() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenRejectsAuthenticatedPost() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validFormParameterWorks() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf())
                .param("theme", "dark"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void validHeaderWorks() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "light"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void endpointTokenAndSameSessionWork() throws Exception {
        MvcResult getToken = mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName")
                .value("X-CSRF-TOKEN"))
            .andReturn();

        JsonNode tokenJson = mapper.readTree(
            getToken.getResponse().getContentAsString());
        String token = tokenJson.path("token").asText();
        assertThat(token).isNotBlank();

        MockHttpSession session =
            (MockHttpSession) getToken.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/preference")
                .session(session)
                .with(user("alice"))
                .header("X-CSRF-TOKEN", token)
                .param("theme", "dark"))
            .andExpect(status().isOk());
    }

    @Test
    void anotherSessionCannotReuseToken() throws Exception {
        MvcResult first = mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andReturn();
        String token = mapper.readTree(
            first.getResponse().getContentAsString())
            .path("token").asText();

        mvc.perform(post("/api/preference")
                .session(new MockHttpSession())
                .with(user("alice"))
                .header("X-CSRF-TOKEN", token)
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginPostNeedsCsrfAsWell() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedGetNeedsNoCsrf() throws Exception {
        mvc.perform(get("/api/preference")
                .with(user("alice")))
            .andExpect(status().isOk());
    }
}
```

`MockMvc` here invokes the Spring app context with the real filter chain. `spring-security-test`'s `csrf()` helper supplies valid tokens in tests, `csrf().asHeader()` places the token in the header, and `useInvalidToken()` intentionally passes a bad token. `endpointTokenAndSameSessionWork` also reads a real value from `GET /csrf` and sends it with the same `MockHttpSession`, testing frontend integration more realistically.

| Test case | Expected | Meaning |
|---|---|---|
| Form has hidden `_csrf` | 200 HTML | UI outputs token |
| Logged-in POST missing token | 403 | Authentication does not replace CSRF |
| Logged-in POST with wrong token | 403 | Server verifies validity |
| POST with `csrf()` | 200 | Valid form parameter |
| POST with `csrf().asHeader()` | 200 | Valid header |
| JSON token + matching session | 200 | Bootstrap token API works |
| Session A token + session B | 403 | Not shared system-wide |
| `POST /login` missing token | 403 | Login POST also needs protection |
| `POST /login` with valid token | 3xx | Executes form login |
| Logged-in GET | 200 | No CSRF required for safe GET |

**Limitations:** `with(user("alice"))` fabricates authentication for the test request to isolate CSRF, rather than testing password policies. `MockMvc` does not replace browser/network tests for cookie Domain/Secure/SameSite, CORS, reverse proxies, or distributed session stores. Tests may require updates for your actual dependency versions.

## 8. Spring Security 6: Masked Tokens, BREACH, and Deferred Tokens

Spring Security 6 introduces nuances that often surprise developers:

**(1) BREACH masking.** `XorCsrfTokenRequestAttributeHandler` is typically the default. When tokens appear in compressed HTML/responses, the handler applies random masking. Two renders can emit **two different strings** even though the expected token in the session did not change. Never assert that two rendered strings are identical, and never swap handlers just to make tokens "static".

**(2) Request handler resolves fields/headers.** The handler reads `_csrf` from request parameters or `X-CSRF-TOKEN` / `X-XSRF-TOKEN` per config, decodes the masked representation if needed, and compares against the real token. Thus, a value copied directly from a raw repository may not match the representation exposed in views.

**(3) Deferred tokens.** Tokens may only be loaded/generated when accessed. If an SPA relies on a token cookie appearing after a GET, ensure a component requiring the token actually loads it; declaring the repository alone does not guarantee cookies are sent on every response.

**(4) Auth transitions.** On successful login/logout, old tokens may be cleared by `CsrfAuthenticationStrategy`/`CsrfLogoutHandler`. Clients must fetch a new token before sending subsequent unsafe requests.

Distinguish the pieces:

```text
Expected token in HttpSession or CookieCsrfTokenRepository
    |
    +--> Exposed to render HTML: may be XOR-masked per handler
    |
    +--> Form _csrf: sends rendered token, handler decodes
    |
    +--> SPA reads XSRF-TOKEN cookie: usually sees raw token
          and needs a handler accepting raw headers properly
```

## 9. SPAs Using the `XSRF-TOKEN` Cookie / `X-XSRF-TOKEN` Header

For some SPAs (Angular or configured JS frontends), the backend can issue an `XSRF-TOKEN` cookie for the frontend to read and send back in the `X-XSRF-TOKEN` header. That is **not** a session cookie. Login cookies like `JSESSIONID` should stay properly `HttpOnly`; only the **CSRF** cookie may be configured as JS-readable when genuinely needed.

### 9.1. Cookie Repository

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
```

**This is not yet a complete SPA configuration for Spring Security 6.** `CookieCsrfTokenRepository` puts a raw token in the cookie, whereas the default `XorCsrfTokenRequestAttributeHandler` may expect a masked token. You need a request handler bridging this difference.

### 9.2. Sample Handler: Raw Header, Masked Form

The snippet below is an **illustrative class** (must be wired into the app's Servlet config, not a standalone program):

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler masked =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> tokenSupplier) {
        masked.handle(request, response, tokenSupplier);
        tokenSupplier.get(); // load deferred token when cookie is needed
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken expected) {
        String header = request.getHeader(expected.getHeaderName());
        return (StringUtils.hasText(header) ? plain : masked)
            .resolveCsrfTokenValue(request, expected);
    }
}
```

Wire it into the **same security chain protecting the SPA**:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(
        new SpaCsrfTokenRequestHandler()));
```

Requires importing `CookieCsrfTokenRepository`. For the `X-XSRF-TOKEN` header, the request handler reads the raw token; for form `_csrf`, it uses the masked representation. The code mirrors the Spring Security reference idea; verify compatibility against your project's framework/config versions.

### 9.3. SPA Sequence

```text
GET /csrf or bootstrap API
  → server loads/generates CSRF token
  → Set-Cookie: XSRF-TOKEN=<raw-token> if configured

Same-origin frontend:
  → reads XSRF-TOKEN from document.cookie
  → fetch POST with appropriate credentials
  → X-XSRF-TOKEN: <raw-token>
  → CsrfFilter validates via SPA handler
```

Cases where the token cannot be read:
- `HttpOnly` is enabled on the CSRF cookie the frontend needs to read (unlike auth cookies).
- Cookie Path/Domain/SameSite/Secure prevent the browser from storing/sending it.
- Deferred token was never loaded, so no cookie was issued.
- Token was cleared on login/logout and the SPA failed to refresh.
- Misconfigured CORS/credential origins, or frontend framework doesn't auto-attach the header as assumed.
- API matches a different `SecurityFilterChain` lacking the matching repository/handler.

Never open CORS with credentials to every website just to "get the token working". Prefer same-origin whenever possible; if cross-origin is mandatory, design strict allowlists and CSRF policies.

## 10. Why Do CSRF and CORS Not Replace Each Other?

CSRF controls whether a state-changing request carries proof of originating from a legitimate flow, whereas CORS governs browser JS rights to read responses and make certain cross-origin requests.

A cross-site HTML form can normally be sent without the sender reading the response; therefore relying solely on CORS cannot block state-changing requests. Conversely, custom headers can trigger preflight, yet overly permissive CORS still leaves risk. You need simultaneously:
- CSRF tokens aligned with auto-sent credential threat models;
- Accurate CORS origins, methods, headers, and credentials;
- SameSite, Secure, and HttpOnly cookie policies;
- HTTPS, trusted reverse proxies, and XSS defenses;
- Resource-level authentication and authorization.

## 11. Handling 403 Systematically

**A 403 does not automatically mean CSRF.** It can stem from permissions, CSRF, expired sessions, or other policies. Diagnose step by step:

1. Confirm the request method and whether `CsrfFilter` requires a token.
2. Check the active user/session cookie, verifying it matches the session used to obtain the token.
3. Verify the live form has `_csrf` and live JS sends the exact header name.
4. If using SPA cookies, distinguish raw tokens from XOR-masked tokens.
5. After login/logout, fetch a fresh token; do not reuse the prior session's token.
6. Check cookie Path/Domain/SameSite/Secure and proxy forwarded headers.
7. If a valid token still returns 403, inspect `@PreAuthorize`, roles/authorities, tenant, and ownership.
8. When logging, record error types/request IDs rather than raw CSRF tokens, session IDs, or `Authorization` headers.
9. Write negative tests with an authenticated user plus missing and bad tokens to isolate CSRF errors.
10. Never disable CSRF or change every method to GET just to turn tests green.

| Symptom | Possible cause | Fix direction |
|---|---|---|
| Form POST always 403 | Missing/expired hidden input | Render current session's CSRF token |
| Fetch POST 403 yet form works | Wrong or missing header | Use `getHeaderName()`, check Network tab |
| SPA cookie/header match yet 403 | Raw cookie vs. XOR handler mismatch | Dedicated SPA handler |
| First POST after login gets 403 | Token cleared on login | Fetch new token after login |
| Session A token sent from session B gets 403 | Wrong session binding | Never reuse tokens across sessions |
| `POST /login` gets 403 | Missing token in login form | Include hidden token or test helper |
| GET still returns 200 | Safe GET needs no token by default | Never put mutations on GET |
| Valid CSRF yet still 403 | Missing business permissions | Check authorization, do not disable CSRF |
| Browser reports CORS error | Wrong cross-origin config/cookies | Configure trusted origins and credentials |
| Multipart upload 403 | Body token unread per filter order | Check multipart chain, consider header |

## 12. Form Login, Logout, Session Timeout, and Multipart

- **Login:** `POST /login` typically requires a CSRF token. Spring Security's built-in form-login page supplies the token; custom login pages must ensure the token is included.
- **Logout:** POST logout prevents a GET link from accidentally logging out users. Successful logout can clear tokens, so clients must re-bootstrap if continuing to use the app.
- **Session timeout:** UI holding a hidden token in a long-idle tab may submit after session expiration. Requests should handle 403/redirects gracefully instead of disabling protection.
- **Session fixation:** After authentication succeeds, the session ID often changes. Data/tokens across authentication boundaries must be tested rather than assuming old tokens remain valid.
- **Multi-tab:** Tab A logging in/out alters token/session state, so tab B may need to reload its token. Handle UX so users do not lose form drafts.
- **Multipart:** Putting the token in a header lets the CSRF filter read it without waiting to parse the multipart body first. Avoid query tokens unless justified by a clear threat-model review.
- **Method override:** `HiddenHttpMethodFilter` can turn a form POST into PUT/DELETE server-side. Filter ordering and CSRF policies for the effective HTTP method must be tested.
- **WebFlux:** `ServerHttpSecurity`, `ServerCsrfTokenRepository`, and `WebSessionServerCsrfTokenRepository` belong to the reactive stack; never copy `HttpServletRequest`/`HttpSessionCsrfTokenRepository` straight into WebFlux.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Disabling CSRF to stop POST 403s | Loses browser session protection | Fix token transport |
| Hardcoding same CSRF token for all users | Not bound to session | Use server repository |
| Keeping token only in cookie without field/header | Browser auto-sends cookies in CSRF | Send via separate channel |
| Putting token in URL query | Easily leaked in logs/history | Hidden field or header |
| Generating tokens with `Math.random()` on frontend | Server has no trusted expected token | Server-issued tokens |
| Disabling `HttpOnly` on **session cookie** for JS CSRF | Session credential readable by JS | Only CSRF cookie readable if needed |
| Raw SPA cookie with handler expecting masked | Confusing 403s | Use hybrid raw/header handler |
| Not refreshing token after login/logout | Old token becomes invalid | Re-bootstrap |
| Testing only with `csrf()` helper, ignoring frontend | Misses cookie/CORS/JS bugs | Real browser/integration tests |
| Treating CSRF token as role/owner check | Valid token still accesses wrong object | Service/DB authorization |
| Mutating on GET to dodge CSRF | Links or prefetch trigger side effects | Use proper unsafe methods |
| Logging all request headers | Leaks tokens/cookies/bearer creds | Redaction and minimal logging |
| Allowing all cross-origin credentials | Expands attack surface | Trusted CORS allowlist |
| Reusing same token after session expiration | 403 or broken navigation | Reauthenticate/reload token |

## 14. Pre-Release Checklist

- [ ] Clearly identify session-cookie, SPA-cookie, or stateless Bearer auth; know whether credentials auto-send.
- [ ] All mutations use unsafe HTTP methods; zero state-changing GETs exist.
- [ ] Server-rendered forms include tokens from `CsrfToken` in properly named hidden fields.
- [ ] Fetch/AJAX APIs attach the properly named header with the current session's token.
- [ ] With `CookieCsrfTokenRepository`, handle raw/masked and deferred tokens per Spring Security version.
- [ ] Login and logout POSTs are protected; SPAs refresh tokens after authentication transitions.
- [ ] Sessions/cookies, SameSite, Secure, HttpOnly, and proxies behave properly.
- [ ] CORS does not let untrusted origins read tokens or send arbitrary credentialed requests.
- [ ] Tokens never appear in URLs, analytics, shared caches, or logs.
- [ ] Test POST with valid token (form), valid token (header), missing token, and invalid token.
- [ ] Test session A/B isolation, login/logout, session timeout, multipart, and multi-tab where applicable.
- [ ] Test authorization separately (missing role or wrong owner still denied even with valid token).
- [ ] In operations, distinguish CSRF vs. authorization errors without logging secrets.

## 15. Exercises and Answers

**Q1.** Logged in, a POST request carries a valid `JSESSIONID` yet lacks `_csrf`/header. Is that enough?

**Answer:** No. Cookies can be auto-sent by browsers when requests are triggered from another site; the CSRF token must arrive via a separate field/header channel.

**Q2.** Are `X-XSRF-TOKEN` and `X-CSRF-TOKEN` identical everywhere?

**Answer:** No. Different repositories/handlers expect different header names. Use `CsrfToken.getHeaderName()` and network testing.

**Q3.** Why can an SPA's `XSRF-TOKEN` cookie cause 403 in Spring Security 6 even when JavaScript sends a header matching the cookie?

**Answer:** The cookie usually holds the raw token, whereas the default XOR handler expects a masked representation. Use a handler that resolves raw headers properly.

**Q4.** Can a token become stale after login?

**Answer:** Yes. `CsrfAuthenticationStrategy` can clear tokens. Clients should fetch a new token after successful login.

**Q5.** If `MockMvc` uses `csrf().asHeader()`, does that guarantee the frontend is right?

**Answer:** No. The test helper only simulates a request with a valid token; the frontend still needs real cookies, CORS, header names, and session lifecycle handling.

**Q6.** Does a valid CSRF token allow a user to edit someone else's document?

**Answer:** No. CSRF only stops forged requests; document permissions must be checked via HTTP/method/service/query scoping.

**Q7.** Which token transport is more convenient for multipart uploads via JS?

**Answer:** Headers are usually more suitable because the filter can validate the token without parsing the multipart body first, depending on middleware setup.

**Q8.** When using an `Authorization: Bearer` token in a JS client with no auth cookies, is a CSRF token automatically required?

**Answer:** Depends on the threat model. If browsers do not auto-send credentials, cookie-based CSRF differs; still inspect refresh cookies, hybrid auth, XSS, and CORS.

## 16. Official References

- [Spring Security — CSRF (Servlet, Spring Security 6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): forms, headers, repositories, deferred tokens, BREACH, SPAs, and logout.
- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().asHeader()`, `csrf().useInvalidToken()`.
- [Spring Security — CSRF (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): WebFlux and `ServerCsrfTokenRepository`.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, double-submit cookie, and defense-in-depth.
- [OWASP — XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): why XSS must be defended alongside CSRF.

**Conclusion:** In browser-session apps, CSRF tokens must be sent via **hidden form inputs** or **HTTP headers** on state-changing requests; browser auto-sent login cookies **are not enough**. In Spring Security MVC, use real tokens provided by the repository/request handler; in cookie-based SPAs, mind raw/masked tokens and post-login/logout refreshes. CSRF protection, authentication, and authorization must always work together.
