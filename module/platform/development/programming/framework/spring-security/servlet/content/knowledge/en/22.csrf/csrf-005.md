# CookieCsrfTokenRepository and Sending CSRF Tokens Back via Headers

**Scope:** Spring Security for **Servlet/Spring MVC** applications (Spring Security 6.x, Java 17+), specifically JavaScript/SPA frontends communicating with a backend using session cookies. This lesson focuses on issuing tokens with `CookieCsrfTokenRepository`, reading the cookie, and sending the token back in an HTTP header; WebFlux uses a different mechanism and API.

## 1. Why Send the Token via a Header?

In an application authenticated with sessions, the browser automatically attaches the session cookie (e.g., `JSESSIONID`) to same-site requests, and in some cases even to requests initiated from other sites. An attacker can exploit this automatic cookie-sending behavior to make a victim's browser perform state-changing actions such as a money-transfer POST or data DELETE. That is **Cross-Site Request Forgery (CSRF)**.

CSRF protection requires state-changing requests to carry an additional value that an attacker's page cannot arbitrarily obtain. In Spring Security Servlet, `CsrfFilter` looks up the stored token using `CsrfTokenRepository` and compares it with the token sent by the client. A missing or wrong token usually results in **HTTP 403** before the request reaches the controller.

- The session authentication cookie proves **the browser has an active logged-in session**; it does not by itself prove the user intentionally initiated the request.
- The CSRF token is additional proof for state-changing requests. The `X-XSRF-TOKEN` header must contain **the token value**, not the cookie name and not the session cookie.
- CSRF protection **does not replace authentication, authorization, XSS defense, or business validation**. If the application has XSS, a malicious script on the same origin can read the token when the cookie is not `HttpOnly`.

By default, Spring Security checks CSRF for **unsafe** methods (typically `POST`, `PUT`, `PATCH`, `DELETE`); `GET`, `HEAD`, `OPTIONS`, and `TRACE` are considered safe by default. GET endpoints must truly not alter state.

## 2. What Does CookieCsrfTokenRepository Store, and What Does the Client Send?

`CookieCsrfTokenRepository` stores the token value in a browser cookie; every protected request must send **that same value** via a header or form parameter for the backend to compare.

| Component | Common default | Role |
| --- | --- | --- |
| CSRF cookie | `XSRF-TOKEN` | Where the token is stored for the client to receive after a response. |
| CSRF header | `X-XSRF-TOKEN` | Where JavaScript sends the token back when calling POST/PUT/PATCH/DELETE. |
| Form parameter | `_csrf` | How traditional HTML forms send the token. |
| Session cookie | `JSESSIONID` (if sessions are used) | Session authentication; **distinct** from the CSRF token. |

Cookie, header, and parameter names can be customized on the repository; the frontend must use the exact agreed names. `withHttpOnlyFalse()` creates a repository that allows JavaScript to read the `XSRF-TOKEN` cookie via `document.cookie`. When the backend renders forms and inserts the CSRF token into HTML itself, enabling JavaScript to read the cookie is generally unnecessary.

**Same-origin flow:**

1. The client calls `GET /api/csrf`. The token handler tells Spring Security to generate/read the token, and the response includes `Set-Cookie: XSRF-TOKEN=...` if needed.
2. The browser stores the cookie within the appropriate domain/path scope. Same-origin JavaScript reads `XSRF-TOKEN`; scripts cannot read cookies with the `HttpOnly` flag.
3. When calling `POST /api/notes`, the client sends the session cookie via normal cookie mechanics, while also setting `X-XSRF-TOKEN: <value read from XSRF-TOKEN>`.
4. `CsrfFilter` fetches the token managed by the repository, reads the token from the request via `CsrfTokenRequestHandler`, compares them, and lets the request proceed only when valid.

**Illustrative** HTTP example (token value is hypothetical):

```http
GET /api/csrf HTTP/1.1
Host: app.example.com

HTTP/1.1 204 No Content
Set-Cookie: XSRF-TOKEN=token-123; Path=/

POST /api/notes HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=session-abc; XSRF-TOKEN=token-123
X-XSRF-TOKEN: token-123
Content-Type: application/json

{"text":"hello"}
```

The header is added **explicitly by frontend code** (or the framework's XSRF mechanism); the browser does not automatically copy the token from the `XSRF-TOKEN` cookie into `X-XSRF-TOKEN`.

## 3. Common Pitfalls in Spring Security 6: Deferred Tokens and BREACH

Configuring only `csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())` may **not be enough for an SPA** in Spring Security 6:

- **Deferred loading:** tokens are loaded/generated only when actually accessed. A GET request that does not touch the token may not create the cookie as the frontend expects. An SPA should have a bootstrap endpoint and a request handler that actively accesses the token.
- **BREACH protection:** the default handler `XorCsrfTokenRequestAttributeHandler` may expose a **masked token value** to HTML/request attributes. That masked string differs from the raw token stored in the `XSRF-TOKEN` cookie. If the default handler is used to decode all inputs, a header containing the **raw** value read from the cookie may be rejected.
- **SPA handling approach:** when the token comes from the `X-XSRF-TOKEN` header, use `CsrfTokenRequestAttributeHandler` to read the raw value; when the token comes from a parameter/form, keep `XorCsrfTokenRequestAttributeHandler` to handle the masked representation. When handling requests, actively call `csrfToken.get()` to trigger cookie creation/writing.

Do not arbitrarily drop BREACH protection or assume the token in the cookie always equals the `_csrf.token` string rendered to HTML. The two usage paths can have different representations.

## 4. Servlet Configuration Example with Spring Security 6

The following files belong to **a Spring Boot 3.x Servlet application** using `spring-boot-starter-web` and `spring-boot-starter-security`. They are not standalone `javac` programs because they require Spring libraries on the classpath. Place them together in the `com.example.csrf` package and run as a Spring Boot application; Java 17 or higher satisfies the syntax.

**`SpaCsrfTokenRequestHandler.java`** — handles raw tokens from headers and masked tokens from forms:

```java
package com.example.csrf;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;
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
        // Use the masked token for HTML/forms (BREACH protection).
        xor.handle(request, response, csrfToken);
        // Force the deferred token to load/generate so the SPA gets the cookie.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler handler =
                StringUtils.hasText(header) ? plain : xor;
        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
```

**`SecurityConfig.java`** — uses cookie CSRF; permits calling the bootstrap endpoint before login, while business APIs require login:

```java
package com.example.csrf;

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
        CookieCsrfTokenRepository repository =
                CookieCsrfTokenRepository.withHttpOnlyFalse();

        http
            .csrf(csrf -> csrf
                .csrfTokenRepository(repository)
                .csrfTokenRequestHandler(
                    new SpaCsrfTokenRequestHandler()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

**`DemoController.java`** — state-preserving GET endpoint, illustrative POST returning data:

```java
package com.example.csrf;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/csrf")
    public ResponseEntity<Void> csrf() {
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/notes")
    public Map<String, String> createNote(
            @RequestBody Map<String, String> body) {
        return Map.of("saved", body.getOrDefault("text", ""));
    }
}
```

**`DemoApplication.java`** — Spring Boot entry point:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

With a Gradle project that already has `org.springframework.boot` and the two starters above, run `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). For a standalone project example, a minimal `build.gradle` can use:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

The Gradle wrapper (`gradlew`) must already exist; if creating a project with Spring Initializr, select Spring Web, Spring Security, Java 17+, and use the generated wrapper. In the example, Spring Security creates a demo account `user` with a password printed to the startup log if no custom account is configured. The default login form at `/login` already integrates a CSRF token for the form. **Do not deploy default demo accounts in production.**

## 5. JavaScript: Reading the Cookie and Setting the Right Header

Frontend example on the **same origin** as the backend (such as `https://app.example.com` calling `/api/...`):

```javascript
async function bootstrapCsrf() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot initialize CSRF: " + response.status);
  }
}

function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

async function createNote(text) {
  const token = readCookie("XSRF-TOKEN");
  if (!token) {
    throw new Error("XSRF-TOKEN missing; call bootstrapCsrf first");
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    throw new Error("Request failed: " + response.status);
  }
  return response.json();
}

// Call bootstrapCsrf() after page load and after login;
// once an authenticated session exists, call createNote("hello").
```

Explanation of key parts:

- `bootstrapCsrf()` triggers the server to return the token cookie (via `csrfToken.get()` in the handler); do not take the token from a JSON body or a custom response header.
- `readCookie("XSRF-TOKEN")` only reads cookies with matching domain/path scope and `HttpOnly=false`. If the token contains percent-encoded characters, `decodeURIComponent` restores the value.
- `credentials: "same-origin"` ensures the session cookie and CSRF cookie are sent on same-origin requests. The token is also copied into a **separate header**, because sending the `XSRF-TOKEN` cookie alone is not enough.
- The `Content-Type: application/json` header only describes the body; it is not itself a token. The backend extracts the token from `X-XSRF-TOKEN` via the handler.
- After login/logout, Spring Security may clear the old token to guard against session fixation/CSRF. When the session changes, **call the bootstrap endpoint again** before state-changing requests; do not hold tokens in variables/application state for too long.

Note: If the SPA is on a different origin (`app.example.com`) while the API is on `api.example.com`, SPA JavaScript **cannot read host-only cookies of the API** via `document.cookie`. This is a separate issue from enabling `credentials: "include"`: you must also design same-site/same-origin or a BFF, cookie scope, exact CORS, and secure token issuance. Never open `Access-Control-Allow-Origin: *` with credentials or widen the cookie domain indiscriminately.

## 6. Verifying in the Browser and with an HTTP Client

1. Visit `GET /api/csrf`; observe in DevTools **Network → Response Headers** (`Set-Cookie` present when the server issues/rotates the token) and **Application/Storage → Cookies** (named `XSRF-TOKEN`). This call normally returns **204 No Content** in the sample controller; the token lives in the cookie, not in the body.
2. Log in via `/login` to obtain a valid session; after logging in, call `GET /api/csrf` again because the token may have been cleared on successful authentication.
3. Call `POST /api/notes` with the session cookie and the right `X-XSRF-TOKEN` header: e.g., returns **200 OK**, body `{"saved":"hello"}`. Verify in the Network tab that **Request Headers** includes `X-XSRF-TOKEN` matching the cookie value.
4. Try the same request while omitting the header or altering the token: while the session remains valid, expect **403 Forbidden**, without running the controller. Sending a valid token without being logged in may still receive **302 redirect to login** or an authentication response; CSRF and authentication are two distinct verification layers.
5. Call `GET /api/csrf` multiple times: the token may be reused according to the repository's lifecycle; do not assume every GET issues a new token. After logout/login, re-check and re-bootstrap.

Example initial verification command (run while the application is running locally):

```bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
```

Expect `HTTP/1.1 204` in the response and, if a token was just created, `Set-Cookie: XSRF-TOKEN=...`. This output **depends on cookie state and server configuration**, not a static string. The `cookies.txt` file holds only test cookies; do not store or share real session cookies/tokens.

## 7. Security and Common Pitfalls

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| `403` despite having `XSRF-TOKEN` cookie | Frontend did not set the header, used the wrong name, or sent only the cookie. | Send `X-XSRF-TOKEN` containing the cookie's **value** on unsafe methods. |
| `403` when header equals the exact cookie value on Spring Security 6 | Default XOR handler expects a masked representation, whereas the header from the cookie is raw. | Use the SPA handler shown above; keep XOR for forms, plain for headers. |
| `XSRF-TOKEN` missing after GET | Token is still deferred or endpoint did not trigger token access; possibly wrong cookie path/domain. | Call the bootstrap endpoint and invoke `csrfToken.get()` in the handler; check cookie scope. |
| JavaScript reads token as `null` | Cookie has `HttpOnly`, mismatched domain/path, or browser blocked it. | Only for SPAs that must read the cookie: `withHttpOnlyFalse()`; audit cookie scope and policy. |
| Works briefly after login then `403` | Token was rotated or cleared after authentication, logout, or session change. | Re-fetch the CSRF cookie after auth state transitions. |
| API from another origin fails | CORS/credentials, SameSite, Secure, or frontend cannot access host-only cookies. | Design cookie and CORS policies per origin; prefer same-origin/BFF. |
| POST gets `302` to `/login` or `401` | No valid authenticated session yet, even if the CSRF token is valid. | Check login and session before concluding a CSRF error. |

**Rules that should not be ignored:**

- Use HTTPS in production and appropriate `Secure` cookies; configure `SameSite` per architecture (typically `Lax` or `Strict` when feasible). Cookies can be customized via `CookieCsrfTokenRepository#setCookieCustomizer` in Spring Security 6.1+. `SameSite` helps reduce CSRF risk but **does not replace tokens**.
- Set the minimum necessary cookie path/domain. Avoid letting untrusted subdomains set or read the application's CSRF cookie; strictly control CORS and origins allowed to send credentials.
- `HttpOnly=false` is an intentional decision so the SPA can read the token; this means same-origin scripts (including XSS) can read it. Maintain HTML escaping, CSP, and XSS defenses; do not log or place tokens in URLs/query strings.
- If the backend accepts only Bearer tokens sent **explicitly** via `Authorization`, with no auto-attached cookies/HTTP credentials, the CSRF threat model may differ; evaluate the real authentication mechanism before altering filters. **Do not disable CSRF just to bypass 403 errors** in cookie-authenticated apps.
- For traditional HTML forms, Spring can use `_csrf` as a hidden input with a masked token; do not force forms to use the SPA's cookie/header reading mechanism.

## 8. Remember the Mechanism

`CookieCsrfTokenRepository` issues/stores the token in the `XSRF-TOKEN` cookie; for SPAs reading the cookie with JavaScript, state-changing requests must send back the **raw token in the `X-XSRF-TOKEN` header** alongside the session cookie. In Spring Security 6, pay attention to **deferred tokens** and **XOR/BREACH masking**: the SPA handler must trigger cookie issuance and read raw headers properly. Only when the token matches does the request pass `CsrfFilter`; endpoint access rights are still decided separately by authentication and authorization.
