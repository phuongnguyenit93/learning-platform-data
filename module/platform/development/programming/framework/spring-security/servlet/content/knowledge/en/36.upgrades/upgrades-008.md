# Deferred CSRF Token Loading, Token Masking, and SPA Integration in Spring Security Servlet

## 1. Upgrade context: Spring Security 6 and puzzling 403 errors

When migrating a **Spring Security Servlet** application from 5.x to **Spring Security 6.x** (typically with Spring Boot 3 and Jakarta Servlet), many teams run into a puzzling symptom: GET page requests succeed, yet POST requests fail with 403, the CSRF cookie is absent on the initial GET, or an SPA sends `X-XSRF-TOKEN` and the server still rejects the token.

This does not mean Spring Security dropped CSRF protection. Two major changes explain it:

1. **Deferred CSRF tokens**: loading or generating the token **on demand**, instead of eagerly hitting the repository on every incoming request.
2. **BREACH-mitigating CSRF token masking**: the token exposed to HTML/request attributes can be **masked with randomness**, making it distinct from the **raw token** stored in the repository or SPA cookie.

An SPA reading the `XSRF-TOKEN` cookie and sending it in the `X-XSRF-TOKEN` header normally sends the **raw token**, not the masked token. If the server's handler expects a masked form value, the raw header is misparsed and POST fails. Conversely, disabling CSRF protection simply to “stop 403s” removes a critical defense whenever browsers send **session cookies** or automatic credentials.

**Lesson objectives:** explain deferred loading and XOR masking, choose the right repository/request handler for SPAs, maintain compatibility with server-rendered forms, handle token lifecycles across login/logout, and write HTTP tests sending real cookies/headers. Examples target **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**; URLs and API names are learning examples. Check exact versions when applying to real applications.

## 2. What is CSRF, and when does an app actually need protection?

CSRF (Cross-Site Request Forgery) happens when a malicious site tricks a user's browser into sending an unwanted request to an application to which the browser attaches credentials automatically—most commonly authentication cookies. If the server accepts state changes solely from that session cookie, an attacker can abuse the victim's privileges without knowing their password.

Example valid request in a session-backed system:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-cookie>; XSRF-TOKEN=<raw-csrf-token>
Content-Type: application/json
X-XSRF-TOKEN: <raw-csrf-token>

{"theme":"dark"}
~~~

Angle-bracket values are **illustrative placeholders**, not real secrets. The browser sends the `JSESSIONID` authentication cookie automatically. The `XSRF-TOKEN` CSRF cookie can also be sent automatically; having the SPA **read the token and place it in a header** per the server contract provides the independent proof distinguishing legitimate same-origin requests.

**A CSRF cookie alone is not enough**: if the server only checks a cookie browsers attach automatically, CSRF protection collapses. The expected token must be compared against an **independently submitted token** in a form parameter or request header per framework mechanics.

### CSRF is not XSS, CORS, or authorization

- **CSRF**: a browser automatically attaches credentials to a request the user never intended to authorize.
- **XSS**: malicious JavaScript executing in the same origin; if an SPA can read the CSRF cookie, XSS can read it and issue requests too. CSRF tokens do not replace XSS defenses.
- **CORS**: restricts cross-origin browser access. CORS does not automatically replace CSRF tokens, especially with simple requests or misconfigured origins.
- **Authorization**: checks who may perform what action. Holding a valid CSRF token does not authorize a user to modify someone else's account.
- **SameSite cookies**: reduce certain cross-site cookie transmissions, yet do not fully replace CSRF defenses across all architectures.

A truly **stateless API that accepts only client-attached Bearer tokens in `Authorization` headers and never receives automatic credentials** has a different threat model. However, **JWTs stored in cookies** or browser-cached HTTP Basic credentials still face CSRF risk; never use the word “REST” or “JWT” as an excuse to disable CSRF globally.

## 3. Distinguishing raw, masked, and submitted tokens

| Concept | Where it lives | How it is used |
| --- | --- | --- |
| **Expected/raw token** | `CsrfTokenRepository` (session or cookie) | Ground-truth value the server validates against |
| **Masked token** | Request attribute such as `_csrf.token` when rendering HTML | Transformed with a random mask to mitigate BREACH; forms submit this value |
| **Submitted token** | Request header or form parameter | Resolved/decoded by `CsrfTokenRequestHandler` before `CsrfFilter` compares |

Suppose the raw token in the repository is `T`. On the first form render, the XOR handler emits `M1`; on the next render, it emits `M2`. Both `M1` and `M2` can represent **the same raw token `T`** without the repository having rotated the token. Having a fresh random mask per render is completely normal.

In an SPA using `CookieCsrfTokenRepository`, the cookie normally holds **`T`**. JavaScript sends `X-XSRF-TOKEN: T`. The server must treat this header as **plain/raw** instead of applying XOR un-masking meant for masked form tokens.

**BREACH masking is neither encryption nor a token signature.** It randomizes the response representation to mitigate a compression side channel; it does not replace randomness, entropy, constant-time comparison, TLS, cookie flags, or CSRF policy.

### Why can the token inside a hidden HTML input change on every GET?

`XorCsrfTokenRequestAttributeHandler` applies a fresh random mask so the raw CSRF token does not appear statically in compressed responses containing attacker-influenced data. The hidden input value can differ across two renders within the same session even when the underlying token is unchanged.

Never compare the raw cookie token against a masked hidden form value and conclude the cookie is broken. Never send the masked HTML token in a header where a custom SPA handler expects the raw cookie value. The resolution path must match how the value was produced.

## 4. Deferred CSRF tokens: lazy loading

**`CsrfTokenRepository`** handles `generateToken`, `saveToken`, and `loadToken`. Spring Security 6 uses deferred tokens via a supplier to avoid loading or creating tokens on requests that never touch them.

Conceptual GET flow:

~~~text
GET /api/public
     │
     ▼
SecurityFilterChain → CsrfFilter
     │
     ├─ Obtain deferred CSRF supplier
     ├─ CsrfTokenRequestHandler.handle(...) sets request attribute
     ├─ Controller returns JSON without reading _csrf
     └─ No CSRF validation needed since GET is a safe method
                   │
                   ▼
      Repository may NOT be called to load/generate
      And Set-Cookie: XSRF-TOKEN may NOT be emitted
~~~

POST flow requiring CSRF:

~~~text
POST /api/update
     │
     ▼
CsrfFilter detects unsafe method
     │
     ├─ Load/generate expected token from repository
     ├─ Handler resolves submitted token from header/form
     ├─ Compare both values
     │
     ├─ Match → proceed to authorization/controller
     └─ Missing/mismatch → AccessDeniedHandler → HTTP 403
~~~

Spring Security's default matcher normally protects methods outside the safe group (GET, HEAD, OPTIONS, TRACE). **GET must genuinely be side-effect-free**; if a developer uses GET to transfer money or change permissions, CSRF matchers cannot fix that flawed design.

### 4.1. Benefits and upgrade impact

Deferred loading reduces session store/repository writes when users only read content, especially under heavy GET traffic. However, if a frontend **needs the token cookie immediately on an initial bootstrap GET**, the server must materialize the token explicitly. Otherwise, an SPA opening the page and immediately issuing a POST may lack the cookie.

This explains why a server-rendered form page receives a token normally (the template accesses `_csrf.token`, triggering loading), whereas a JSON GET endpoint that never touches the token may omit `Set-Cookie`.

Never promise “every GET is always lazy”: view rendering, handler configuration, a CSRF token endpoint, or invoking the supplier's `get()` can trigger loading. Measure real requests rather than guessing from URLs.

### 4.2. Plain Java 17 example of lazy loading

Example file `DeferredTokenDemo.java` **runs on JDK 17+ with no Spring dependencies**. It illustrates a lazy-loading supplier, **not a real CSRF security implementation**.

~~~java
import java.util.function.Supplier;

public class DeferredTokenDemo {
    static final class LazyToken implements Supplier<String> {
        private String cached;
        private int loads;

        @Override
        public String get() {
            if (cached == null) {
                cached = "example-raw-token";
                loads++;
            }
            return cached;
        }

        int loadCount() {
            return loads;
        }
    }

    public static void main(String[] args) {
        LazyToken token = new LazyToken();

        System.out.println("before=" + token.loadCount());
        System.out.println("first=" + token.get());
        System.out.println("after=" + token.loadCount());
        System.out.println("second=" + token.get());
        System.out.println("loads=" + token.loadCount());
    }
}
~~~

Run:

~~~bash
javac DeferredTokenDemo.java
java DeferredTokenDemo
~~~

**Exact** stdout:

~~~text
before=0
first=example-raw-token
after=1
second=example-raw-token
loads=1
~~~

How the real supplier caches in Spring Security depends on the request/repository lifecycle; this example only explains the term “deferred,” never use it to generate tokens or make authorization decisions.

## 5. XorCsrfTokenRequestAttributeHandler: BREACH-masked tokens

**BREACH** is a side-channel attack exploiting compressed response size variations when a stable secret appears in output alongside attacker-controlled reflected input. Emitting a static raw CSRF token repeatedly in HTML forms is a classic risk under the right conditions.

Spring Security Servlet uses `XorCsrfTokenRequestAttributeHandler` to expose a **masked representation** via the request attribute during rendering, then resolves the submitted form value back to compare against the raw token. Example template output:

~~~html
<form action="/profile" method="post">
  <input type="hidden"
         name="_csrf"
         value="masked-value-produced-by-server">
  <button type="submit">Save</button>
</form>
~~~

This is a simplified HTML example; the masked value is a **placeholder**, not a real format. Never hand-roll XOR/encoding logic on the frontend; leave it to Spring Security's handler.

Because a fresh mask can be generated per render, `_csrf.token` can vary even while the repository's raw token remains fixed. Conversely, when login/logout clears the raw token, the expected token itself changes and an older form becomes invalid.

### 5.1. Is switching the whole app to the plain handler safe?

The plain `CsrfTokenRequestAttributeHandler` accepts raw tokens in headers, yet using it in place of the XOR handler **across all server-rendered responses** forfeits BREACH masking on HTML forms. A cleaner SPA integration keeps XOR for attributes/forms and uses the plain resolver solely for **raw headers** from the SPA.

Note: in the design below, **the `X-XSRF-TOKEN` header is always treated as raw**. If a client extracts the masked hidden form token and sends it in this header, the request can fail. Forms send masked tokens via `_csrf`; SPAs send raw tokens via the header.

## 6. Repositories: Session CSRF vs Cookie CSRF differences

| Criterion | `HttpSessionCsrfTokenRepository` | `CookieCsrfTokenRepository` |
| --- | --- | --- |
| Stores expected token | Server-managed HTTP session | Browser-held and browser-sent cookie |
| Typical integration | MVC server-rendered forms and session login | SPAs reading the raw token from a cookie |
| Must JS read the token? | Not necessarily; views read attributes | Usually yes; use `withHttpOnlyFalse()` when required |
| Depends on session store | Yes | Separate token cookie with its own lifecycle; auth may still use a session |
| Risks to evaluate | Session persistence, expiry, fixation, multi-node | XSS, cookie injection, Domain/Path/SameSite/Secure, trusted subdomains |
| How submitted token is sent | Hidden form parameter/header per handler | SPA's raw header or form value per handler |

By default, `CookieCsrfTokenRepository` typically uses cookie **`XSRF-TOKEN`**, header **`X-XSRF-TOKEN`**, and form parameter **`_csrf`**; check if your app customized those names. The CSRF cookie **is not a session authentication cookie**. Possessing the token does not prove the user is logged in.

`CookieCsrfTokenRepository.withHttpOnlyFalse()` makes the cookie readable by JavaScript. That is a **deliberate tradeoff** for SPAs. Never apply it to session cookies; authentication cookies must keep `HttpOnly`, `Secure`, and flags/paths/SameSite appropriate to your architecture.

### Cookie missing because the token is deferred

With deferred loading, a public GET that never reads the token may emit no cookie. An SPA needs a bootstrap request that generates the token. The pattern in Section 7 calls `csrfToken.get()` inside a custom handler to materialize the supplier on requests, ensuring the cookie is ready before mutations.

In return, this loads the token even on GETs that do not need a CSRF form—**trading away lazy optimization across the whole chain**. That tradeoff is reasonable for same-origin SPAs; to preserve laziness on most GETs, bootstrap tokens only at a narrow endpoint and test repository/attribute mechanics thoroughly on your version.

## 7. Spring Security 6 configuration for a session-cookie SPA

The following example runs in a **Spring Boot 3.x project with Java 17+, Spring Web MVC, and Spring Security 6.x**. These classes compile and run via Gradle or Maven with dependencies, **not** as standalone JDK files.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example file layout:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  security/SpaCsrfTokenRequestHandler.java
  security/SecurityConfig.java
  web/DemoApiController.java
src/test/java/com/example/demo/
  SpaCsrfIntegrationTest.java
~~~

### 7.2. Handler supporting both XOR forms and raw SPA headers

File `SpaCsrfTokenRequestHandler.java` in package `com.example.demo.security`:

~~~java
package com.example.demo.security;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        // Token rendered in HTML attribute stays XOR-masked.
        xor.handle(request, response, csrfToken);

        // Force loading/generating the token so the SPA receives the raw cookie.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String value = request.getHeader(
            csrfToken.getHeaderName());

        // SPA header carries raw token. Form parameter carries masked token.
        return (StringUtils.hasText(value) ? plain : xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

This is a real `CsrfTokenRequestHandler` implementation using the Spring Security 6 API. **Do not add a second `CsrfFilter` manually.** Logic:

1. `xor.handle(...)` sets the request attribute for server-rendered forms with a masked value.
2. `csrfToken.get()` forces the supplier to load/generate the token, causing the repository to emit `Set-Cookie: XSRF-TOKEN=...` if absent.
3. If the request carries a non-empty header named `csrfToken.getHeaderName()`, the handler uses the plain resolver. The client-sent token **must be the raw value** from the cookie.
4. If the header is absent, the handler uses the XOR resolver for masked form parameters.
5. `CsrfFilter` still compares expected vs submitted tokens. This code does not “allow through because a header exists,” nor does it disable CSRF checks.

**Limitation:** if a frontend library grabs a masked form token and puts it into `X-XSRF-TOKEN`, this handler treats it as raw and can reject it. The SPA contract must stay consistent: **raw cookie → raw header**, masked SSR form → masked parameter.

### 7.3. SecurityFilterChain

File `SecurityConfig.java` in package `com.example.demo.security`:

~~~java
package com.example.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/bootstrap")
                    .permitAll()
                .requestMatchers("/api/preferences").authenticated()
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(
                    new SpaCsrfTokenRequestHandler()));

        return http.build();
    }
}
~~~

**Note:** `anyRequest().permitAll()` is solely to keep this small demo easy to follow, **not a production policy**. Real APIs must enforce role/authority/tenant/resource authorization and restrict routes. Form login uses session cookies, so CSRF remains enabled. A CSRF token does not prove the caller is logged in.

If the browser uses another session cookie, explicitly define `Secure`, `HttpOnly`, `SameSite`, session fixation protection, logout lifecycle, and cookie path/context path. Never configure `withHttpOnlyFalse()` on session cookies.

### 7.4. Application class

File `DemoApplication.java` in package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.5. Sample controller

File `DemoApiController.java` in package `com.example.demo.web`:

~~~java
package com.example.demo.web;

import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoApiController {
    public record PreferenceInput(String theme) {}

    @GetMapping("/api/bootstrap")
    public Map<String, String> bootstrap() {
        return Map.of("status", "ready");
    }

    @PostMapping("/api/preferences")
    public Map<String, String> save(
            @RequestBody PreferenceInput input) {
        if (input == null
            || !Set.of("dark", "light").contains(input.theme())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Unsupported theme");
        }
        // Demo only echoes theme; does not write to a database.
        return Map.of("theme", input.theme());
    }
}
~~~

`GET /api/bootstrap` is a safe GET allowing the browser to trigger the handler. `POST /api/preferences` must satisfy both **CSRF validation** and `authenticated()` before reaching the controller. The Java tests in Section 10 use a mock authenticated user so they do not depend on real accounts or passwords.

## 8. SPA JavaScript: the right GET-cookie, POST-header sequence

This example targets a **same-origin SPA and backend**, not cross-origin. The SPA first GETs the bootstrap endpoint so the server issues the token cookie. Then JavaScript reads `XSRF-TOKEN` and attaches the raw token in the `X-XSRF-TOKEN` header of the POST request.

~~~javascript
function readCookie(name) {
  const prefix = name + "=";
  const pair = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));

  return pair
    ? decodeURIComponent(pair.slice(prefix.length))
    : null;
}

async function getCsrfToken() {
  const response = await fetch("/api/bootstrap", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed");
  }

  const rawToken = readCookie("XSRF-TOKEN");
  if (!rawToken) {
    throw new Error("Missing XSRF-TOKEN cookie");
  }
  return rawToken;
}

async function saveTheme() {
  const csrf = await getCsrfToken();
  const response = await fetch("/api/preferences", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrf
    },
    body: JSON.stringify({ theme: "dark" })
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  return response.json();
}
~~~

**The client must never put the token in URLs/query strings**, send the token to third-party endpoints, or log token values. Browsers attach cookies per origin/credentials rules; the raw CSRF header is attached explicitly by script.

Having a CSRF token does not imply the user is logged in. While unauthenticated, a POST with a valid token can still receive a 302 login redirect or 401 (depending on entry point). Do not confuse that with a CSRF 403.

### 8.1. What to do after login/logout?

Spring Security provides components such as `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` to clear old CSRF tokens during appropriate authentication/logout flows. With deferred tokens, a new token will not necessarily appear on that same response. Therefore, the SPA should:

1. Log in with a valid token per policy.
2. Once authentication completes, **issue a fresh bootstrap GET**.
3. Read the new cookie and use the new token for POST/PUT/PATCH/DELETE.
4. After logout, clear any cached raw token on the frontend and re-bootstrap before the next mutation.

**Never reuse a pre-login token (`T1`) after login if the server cleared or rotated it to `T2`.** Multi-tab apps can hit stale tokens when another tab logs in, switches sessions, or logs out. Upon receiving 403, the frontend must distinguish CSRF failure from permission denied and never infinitely retry non-idempotent mutations.

### 8.2. Why is same-origin different from cross-origin?

If the SPA lives at `https://app.example.test` and the API lives at `https://api.example.test`, that is cross-origin. A host-only cookie from `api.example.test` **cannot be read via `document.cookie` on `app.example.test`** merely by passing `credentials: "include"`.

Redesign the bootstrap protocol, cookie `Domain`/`Path`/`Secure`/`SameSite`, exact CORS allowlist, credentials policy, and threat model. Never enable `Access-Control-Allow-Origin: *` with credentials. If a dedicated API endpoint must deliver the token to the frontend, ensure proper origin/authorization controls, prevent public caching of the response, and never let JS log tokens to analytics.

In real cross-site setups, `SameSite=None; Secure` and browser third-party cookie policies affect cookie delivery. It is never just tweaking one header: test in real browsers behind realistic HTTPS/proxies.

## 9. SSR forms still use XOR-masked tokens

An application combining Thymeleaf/JSP and an SPA should support **both representations** without turning off masking globally.

Thymeleaf form example:

~~~html
<form th:action="@{/profile}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Save</button>
</form>
~~~

`${_csrf.token}` is read from the request attribute by the template engine and can be the **masked representation** produced by the XOR handler. On POST, the form submits `_csrf`, and the handler uses the XOR resolver to un-mask the token. Some Spring/Thymeleaf integrations emit the hidden CSRF input automatically; this example writes it explicitly for clarity.

**Never copy the hidden form field's string and send it as a raw `X-XSRF-TOKEN` header.** In the Section 7 request handler, only the form parameter path runs the XOR resolver; the header is always treated as raw.

For **SSR-only** apps where JS never needs to read cookies, the simplest choice is usually keeping the default session repository + XOR handler. There is no reason to configure `CookieCsrfTokenRepository.withHttpOnlyFalse()` merely because you are on Spring Security 6.

## 10. MockMvc testing with real HTTP cookies and headers

`spring-security-test` offers `.with(csrf())`, which is handy for unit/authorization tests. Yet tests relying only on that helper can pass even when an actual SPA cannot obtain a cookie or a raw header hits the wrong handler. Write tests covering:

**GET bootstrap → inspect cookie → POST with that cookie + raw header**.

File `SpaCsrfIntegrationTest.java` in package `com.example.demo`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SpaCsrfIntegrationTest {

    @Autowired
    MockMvc mvc;

    private Cookie bootstrapCookie() throws Exception {
        MvcResult result = mvc.perform(get("/api/bootstrap"))
            .andExpect(status().isOk())
            .andReturn();

        Cookie cookie = result.getResponse()
            .getCookie("XSRF-TOKEN");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void bootstrapIssuesCsrfCookie() throws Exception {
        bootstrapCookie();
    }

    @Test
    void cookieAloneDoesNotSatisfyCsrf() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rawCookieHeaderIsAccepted() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .header("X-XSRF-TOKEN", token.getValue())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void invalidHeaderIsRejected() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .header("X-XSRF-TOKEN", "invalid-value")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**What each test verifies:**

- `bootstrapIssuesCsrfCookie`: even a public GET that ignores tokens emits the cookie because the custom SPA handler calls the deferred supplier's `get()`.
- `cookieAloneDoesNotSatisfyCsrf`: sending only the browser cookie without the submitted header → 403.
- `rawCookieHeaderIsAccepted`: traverses the filter chain, cookie repository, and raw-header resolver; CSRF passes and the mock authenticated principal accesses the endpoint.
- `invalidHeaderIsRejected`: valid cookie with wrong header → 403.
- `.with(user("alice"))` only injects a test user; **it does not test real password/login verification**. With Spring Boot Test and `SecurityFilterChain`, it isolates CSRF behavior.
- These tests do not yet prove rotation across login/logout, CORS, or real browser/proxy cookie behavior; add environment-matching integration tests as well.

Run command in a project with the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.demo.SpaCsrfIntegrationTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests com.example.demo.SpaCsrfIntegrationTest
~~~

**Do not fabricate Gradle stdout or claim tests ran** when no project environment is set up. Run them in practice to verify Spring Security versions/dependencies, the filter chain, cookie paths, and the app context.

### 10.1. Extended test matrix

| Case | Expected outcome |
| --- | --- |
| GET/bootstrap with no cookie yet | Receives `XSRF-TOKEN` when handler materializes |
| POST with cookie only | 403 |
| POST with raw header matching cookie | Passes CSRF, proceeds to authentication/authorization |
| POST with wrong header or missing cookie | 403 |
| SSR form with masked `_csrf` | Passes CSRF with matching repository/session |
| Masked form token placed in raw header | Rejected per sample handler |
| POST with pre-login token after login | May return 403 when token cleared/rotated |
| Re-bootstrap after login | Receives fresh token for subsequent mutations |
| Logout POST without token | 403 when logout is protected |
| User lacks authority yet has valid token | Authorization 403, not CSRF |
| GET with business side effects | Must fix design; safe methods skip CSRF by default |
| Cross-origin SPA lacking cookie visibility | Bootstrap/header handshake fails |
| Cookie/path behind reverse proxy differs from local | Test exact path, HTTPS, SameSite, context path |
| Browser with two tabs and one logs out | Other tab must handle stale token safely |

Never assert status 403 alone and conclude CSRF works. Requests can return 403 due to missing permissions, wrong tenant, CORS, or business policy. Identify **which filter/handler** rejected it via safe logs without logging raw CSRF tokens.

## 11. Migration pitfalls: picking the right fix instead of disabling CSRF

### 11.1. Switching the whole app to the plain handler?

Some older guides suggest switching to plain `CsrfTokenRequestAttributeHandler` or setting `setCsrfRequestAttributeName(null)` to force eager loading. That is **not the default fix** for all SPAs: plain handlers on server-rendered HTML drop BREACH masking, and request-attribute/lazy setters alone do not resolve the raw-header vs masked-form mismatch.

Separate cleanly:
- SPA raw cookie/header uses the plain resolver.
- Masked form values use the XOR resolver.
- Tokens are bootstrapped when browsers need them, balancing performance.

### 11.2. Should you call csrf.disable()?

**Not** just because POST returns 403 after upgrading. In session/cookie-backed SPAs, disabling CSRF creates vulnerabilities. If an app is genuinely pure stateless Bearer-header auth, you can configure a dedicated `SecurityFilterChain`/API matcher per its threat model, provided you verify no automatic credentials arrive via cookies/Basic or browser side-effect routes.

Use targeted matchers for genuinely public or justified non-browser endpoints rather than applying global `csrf.disable()` without investigation.

### 11.3. Do not register a duplicate CsrfFilter

Spring Security automatically installs `CsrfFilter` when `http.csrf(...)` is configured. Registering another filter manually in the servlet container or a custom chain can run CSRF checks twice or break lifecycle ordering. Always configure repository, handler, and matchers via official APIs.

### 11.4. Cookies, domains, and subdomains

If `XSRF-TOKEN` can be read by untrusted scripts or overwritten by a compromised subdomain, the protection model degrades. Avoid overly broad cookie `Domain` attributes, consider host-only cookies, enforce `Secure` flags, and lock down CORS allowlists. Some architectures require additional `Origin`/`Referer` validation or token-binding policies; never assume double-submit cookies alone solve all cookie-injection risks.

### 11.5. When the first POST after login still returns 403

Check:

1. Did login success clear the old token via the CSRF authentication strategy?
2. Did the frontend re-bootstrap after login/redirect?
3. Did the browser receive the new `Set-Cookie` and use the right `Path`/`Domain`/`SameSite`/`Secure`?
4. Does the POST carry both the updated cookie and updated raw header?
5. Does the handler pick plain resolution for headers rather than trying to XOR-decode them?
6. Do multiple security filter chains apply differently to GET vs POST?
7. Did the 403 come from CSRF or authorization?

Answering these seven questions is far safer than adding a single line to disable CSRF.

## 12. Practical troubleshooting table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| GET 200 yet no CSRF cookie | Token not materialized due to lazy loading | Bootstrap/force supplier `get()`; check repository |
| Cookie has token yet raw header rejected | XOR handler treats raw header as masked | Use SPA request handler with plain-header resolution |
| SSR form previously worked, now POST 403 | Server swapped XOR/plain inconsistently | Keep forms masked and resolve via XOR |
| Hidden `_csrf.token` differs on every GET | Random masking; raw token may stay unchanged | Never compare masked strings as raw tokens |
| Login succeeds, then first mutation returns 403 | Old token invalidated | Issue fresh bootstrap GET and send new token |
| Logout returns 403 | Missing or stale CSRF on logout POST | Send valid token before logout |
| Subdomain SPA cannot read token | Host-only cookie on another origin | Redesign bootstrap/cookie/CORS architecture |
| Postman works, browser fails | Browser cookies, CORS, SameSite, and CSRF differ | Inspect requests in controlled browser session |
| `X-XSRF-TOKEN` header blocked | CORS preflight/proxy disallows header | Tighten allowlist properly and test real requests |
| Token in cookie yet missing on POST | Incorrect `Path`/`Domain`/`SameSite`/`Secure`/`credentials` | Inspect `Set-Cookie`/`Cookie` over HTTPS/proxy |
| Cookie and header match, still 403 | Missing role, expired session, or another filter | Separate CSRF from authentication/authorization |
| Custom handler makes every GET costly | `csrfToken.get()` forces loading | Narrow bootstrap endpoint or evaluate session store |
| Tab A logs out, Tab B POST returns 403 | Session/token rotated or revoked | Re-bootstrap and handle stale tokens safely |
| Tests using `with(csrf())` all pass | Cookie-header handshake never tested | Add GET-cookie → POST-raw-header tests |
| API uses cookie JWT with CSRF disabled | Confused stateless token with auto-sent cookie | Re-evaluate CSRF threat model |
| HTML form leaks raw token in compressed output | Entire handler switched to plain | Re-enable XOR masking |
| One node succeeds, another returns 403 | Inconsistent session persistence/cookie routing | Check cluster session store, proxy, sticky sessions |

### Safe observability

Never log `Authorization`, `JSESSIONID`, `XSRF-TOKEN`, `X-XSRF-TOKEN`, or full `CsrfToken` objects in logs or traces. Log error categories such as `csrf.missing`/`csrf.invalid`, route templates, HTTP methods, status codes, correlation IDs, and the selected chain/handler instead. Keep public error messages minimal; never echo expected or raw submitted tokens back to clients.

A 403 from `CsrfFilter` and a 403 from missing authority have completely different remedies. Never base retry logic solely on HTTP status codes.

## 13. Production upgrade checklist

- [ ] Confirm exact Spring Boot/Security/Framework versions and Servlet stack rather than WebFlux.
- [ ] Map requests carrying automatic credentials (session cookies, JWT cookies, browser Basic) and unsafe HTTP methods.
- [ ] Know when deferred tokens load and when GETs return content without emitting cookies.
- [ ] Understand how raw expected tokens differ from masked tokens rendered in SSR views.
- [ ] Preserve XOR masking on HTML forms needing BREACH defense.
- [ ] For same-origin SPAs, ensure `XSRF-TOKEN` is issued via bootstrap and `X-XSRF-TOKEN` sends the **raw** cookie value.
- [ ] Use `CookieCsrfTokenRepository.withHttpOnlyFalse()` only when JavaScript must read the CSRF cookie.
- [ ] Never strip `HttpOnly` from session auth cookies; configure `Secure`/`SameSite`/`Domain`/`Path` properly.
- [ ] Custom request handlers select plain for raw headers and XOR for masked form parameters without skipping token comparison.
- [ ] Re-bootstrap tokens after login/logout/rotation; old tabs must not infinitely retry unsafe mutations.
- [ ] Never place tokens in URLs/queries or logs, and never reflect secrets in error responses.
- [ ] Never disable CSRF globally solely because the app uses an SPA or JWT.
- [ ] Verify authentication/authorization, CSRF, CORS, and object-level permissions together.
- [ ] Include MockMvc tests for cookie-only fail, raw-header pass, bad-header fail, masked-form pass, and token rotation.
- [ ] Test browsers behind HTTPS/reverse proxies, session clusters, cookie flags, CORS, multiple tabs, and caching.
- [ ] Prepare a versioned rollout/rollback plan and measure overhead if materializing tokens on all GETs.

**Conclusion:** Spring Security Servlet 6.x separates **deferred token loading**, **BREACH-mitigating masked token rendering**, and **resolving client-submitted tokens**. SSR forms normally submit masked `_csrf`, whereas cookie-based SPAs must send the **raw `XSRF-TOKEN` in the `X-XSRF-TOKEN` header** backed by a matching request handler. To upgrade safely, verify the repository, handler, login/logout lifecycles, and real HTTP cookies/headers rather than removing CSRF defenses just to silence 403s.
