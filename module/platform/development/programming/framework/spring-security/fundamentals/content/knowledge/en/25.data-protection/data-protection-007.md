# Never Put Credentials, Cookies, or Tokens in URLs or Error Messages

## 1. Why Must Authentication Data Never Travel in URLs?

Credentials are data that lets a party prove identity or exercise an access grant. Examples include passwords, session IDs, API keys, OAuth access tokens, refresh tokens, one-time codes, and secret keys. **Anyone who obtains certain types of this data can act on behalf of the user or application**, at least while that data remains valid.

Two common ways authentication data leaks accidentally are:

1. **Placing secrets in URLs:** `/account?token=...`, `/users/password/abc...`, `https://user:password@example.com`, `/page#access_token=...`.
2. **Exposing secrets in public errors:** returning raw `Exception.getMessage()`, the request URL, query string, `Authorization` header, cookies, SQL statements, or stack traces to the browser or client app.

HTTPS encrypts data in transit between TLS endpoints; **HTTPS does not erase URLs from browser history, reverse proxy logs, monitoring systems, analytics tools, or screenshots**. Likewise, hiding an error message in the UI is not enough if the API still sends secrets inside JSON, headers, or redirects.

Goals of this lesson within **Spring Security Servlet, Spring Boot 3.x, and Java 17+**:

- Understand exactly what URLs, headers, cookies, bodies, and error responses can leak.
- Place credentials and tokens in the right channels; never turn a resource address into a "password".
- Handle errors with stable status/error codes without reflecting caller secrets or internal details.
- Properly evaluate protocol exceptions such as OAuth 2.0 authorization codes and account recovery links.
- Write positive and negative tests proving URLs and responses do not inadvertently contain secrets.

## 2. Through Which Paths Do URLs Leak Information?

Consider a URL you **should never build**:

```text
https://app.example.com/api/orders?access_token=FAKE_TOKEN_ONLY_FOR_DEMO
```

Even over HTTPS, this string can be copied into many places:

| Storage / sharing location | Why is it risky? | What must be controlled? |
| --- | --- | --- |
| Browser history, bookmarks, and address bar | Users can save, share, or screenshot the full URL. | Never put credentials in URLs by design. |
| Access logs of web servers, load balancers, gateways, proxies | The request target may be logged with path and query. | Configure logs not to capture queries with secret data; review every tier. |
| APM, tracing, metrics, error-reporting systems | "Full URL", trace attributes, or exception messages may be collected automatically. | Record only route templates and permitted data; redact at collection time. |
| `Referer` header when navigating or loading resources | Source URLs may be sent per referrer policy; granularity depends on same-origin/cross-origin and headers. | Set an appropriate `Referrer-Policy`, yet still never put secrets in URLs. |
| Page JavaScript and browser extensions | Scripts with access can read `location.href`, `location.search`, or `location.hash`. | Restrict third-party scripts, enforce CSP, and keep secrets out of URLs. |
| Chat, email, support tickets, and screenshots | Users may paste URLs into external channels. | Use a public correlation ID instead of a token-bearing URL for support. |
| Redirects and error pages | `Location`, `next`, `returnUrl`, or errors echoing the full input URL can re-broadcast tokens. | Validate redirect targets and never embed secrets in URLs/headers/bodies. |

Distinguish the parts of a URL:

```text
https://user:pass@host.example.com/orders/SECRET_PATH?token=SECRET_QUERY#SECRET_FRAGMENT
        └user info┘                        └path─────┘ └query─────┘ └fragment────┘
```

- **Userinfo (`user:pass@`):** legacy URI syntax for username/password; never use it to transmit login credentials.
- **Path:** `/reset/TOKEN` still appears in history, access logs, analytics, and shared links. Moving a token from the query string into the path **does not solve the problem**.
- **Query:** `?token=...`, `?password=...` appear in the HTTP request URL and risk being logged/collected. Values may be encoded, yet encoding is **not encryption**.
- **Fragment (`#...`):** per HTTP semantics, browsers **do not send the fragment to the server in the HTTP request target**; `Referer` must not include the fragment either. However, fragments still appear in history/address bars and can be read by JavaScript/extensions, so they are **not a safe place to store access tokens**. The legacy OAuth implicit flow used fragments for tokens; modern recommendations prefer Authorization Code with PKCE.

Rule of thumb: if a URL can be bookmarked, pasted into chat, or recorded by logging systems, assume **it can be shared unintentionally**. Never use URLs as credential storage.

## 3. Placing Each Type of Information in the Right Channel

| Data type | Appropriate channel in web apps/APIs | What to avoid |
| --- | --- | --- |
| Username, password on login | `POST` with form/body over HTTPS; server authenticates and applies rate limiting. | `GET /login?password=...`, logging request bodies, putting passwords in redirects. |
| Bearer OAuth access token | `Authorization: Bearer <token>` header over HTTPS. | `?access_token=...`, tokens in paths, sending tokens to the wrong origin. |
| Refresh token | Protocol-defined token-endpoint channel with secure storage; for browsers prefer architectures avoiding exposing tokens to untrusted scripts. | URLs/fragments, unassessed `localStorage`, logs/token analytics. |
| Server-managed session ID | Cookie with `Secure`, `HttpOnly`, appropriate `SameSite`, and narrowest `Path`/`Domain`. | `?jsessionid=...`, `;jsessionid=...` in path, cookies in error messages. |
| Service API key | API-defined header (e.g., `X-API-Key` or `Authorization`) over HTTPS, scoped permissions and rotation. | Query parameters, committing in source code, logging raw headers. |
| CSRF token | Hidden form field or framework/application-defined header. | Putting the token in URLs; mistaking a CSRF token for authentication. |
| Error/correlation ID | Random secret-free identifier in response header or body. | Using access tokens, session IDs, or full URLs as "support codes". |

**Note:** headers and bodies are not "absolutely safe containers". Proxies, debug logs, APMs, or frontend scripts can still leak `Authorization`, `Cookie`, `Set-Cookie`, and bodies. Moving secrets out of URLs is a mandatory design step; beyond that, you still need TLS, log filtering, authorization, token lifecycle management, and script restrictions.

### 3.1. Logging In with a Session Cookie

Example of proper placement during authentication:

```http
POST /login HTTP/1.1
Host: app.example.com
Content-Type: application/x-www-form-urlencoded

username=demo-user&password=FAKE_PASSWORD_FOR_EXAMPLE
```

After authentication, the server may issue a session cookie:

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=DEMO_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /dashboard
Cache-Control: no-store
```

The values above are **for protocol illustration only**—never use them as real credentials. Session cookies are sent by browsers via the `Cookie` header per cookie rules; the server should never generate redirects like `/dashboard?sid=...`. `Secure` restricts cookie transmission to secure channels per browser rules; `HttpOnly` blocks JavaScript from reading the cookie; `SameSite` helps reduce cross-site cookie sending, though it **does not replace CSRF protection** in every scenario. Some applications may need `SameSite=None; Secure` for genuine cross-site flows after risk assessment.

With Servlet-container-managed sessions, avoid **URL rewriting** that appends `;jsessionid=...` to links. Use cookie-based session tracking when browsers support cookies, and inspect actual URLs after login and navigation. Moving a token from a query parameter into a path segment or matrix parameter does not protect it.

### 3.2. APIs Using Bearer Tokens

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer FAKE_ACCESS_TOKEN_FOR_EXAMPLE
Accept: application/json
```

The token is placed in the header specified by OAuth 2.0 Bearer Token Usage; the URL identifies only the resource. With Spring Security Resource Server, prefer `oauth2ResourceServer(...).jwt(...)` or corresponding opaque-token config rather than writing a naive custom JWT filter. The server must validate signature or introspection, expiration, issuer, audience, and scopes/authorities per token type. **All sample tokens are fake**; never print real tokens to consoles, logs, or documentation.

When a client sends a bad token, never return an error like:

```json
{
  "message": "Bearer eyJhbGciOi... rejected",
  "requestUrl": "/api/orders?access_token=eyJhbGciOi..."
}
```

Instead, use status codes and public error codes while preserving the `WWW-Authenticate` challenge when required by the auth scheme. For OAuth Bearer, returning standard error codes/info in challenges must follow the protocol and information-disclosure policy; never embed token values in challenges.

### 3.3. Sending Secrets in the Body Does Not Mean You Can Log the Body

A `POST` request over HTTPS with passwords in the body avoids many URL leak surfaces. Still, middleware configured with `logRequestBody=true` or exception handlers printing request bodies can leak passwords. Especially avoid logging raw payloads on `/login`, `/token`, `/reset-password`, or requests carrying personal data.

On the frontend, avoid `window.location = "/api/pay?token=" + accessToken`; when sending a bearer token to an API, use `fetch` with the proper header and verify the target is a trusted origin:

```javascript
// accessToken obtained from a securely designed session/token mechanism.
// This is a frontend snippet, not a recommendation to store tokens in localStorage.
const response = await fetch("https://api.example.com/orders", {
  method: "GET",
  headers: { Authorization: "Bearer " + accessToken }
});

if (response.status === 401) {
  // UI handles expired session according to the API contract.
}
```

The code above only illustrates **where the token is transmitted**; token storage, XSS, CORS, expiration, refresh, and network errors must still be handled by the real architecture.

## 4. Protocol Cases Where Token-Like Data Appears in URLs

The rule "never put access/refresh/session tokens in URLs" does not mean arbitrarily changing protocols that use **short-lived transaction codes** in URLs. Distinguish these cases:

### 4.1. OAuth 2.0 Authorization Code with PKCE

The Authorization Code flow typically redirects the browser back to:

```text
https://client.example.com/login/oauth2/code/provider?code=ONE_TIME_CODE&state=RANDOM_STATE
```

In OAuth 2.0, `code` is a short-lived, single-use **authorization code** exchanged for tokens at the appropriate token endpoint channel; it is **not an access token** for calling resource APIs. This is a controlled protocol element, not permission to put access tokens, refresh tokens, passwords, or session IDs in query strings.

Protection requirements include:

- Use **Authorization Code + PKCE** (prefer `S256`), verifying `state` and login-initiation session context against CSRF.
- Accept only exact registered redirect URIs and use HTTPS on public endpoints as appropriate.
- Keep authorization codes short-lived, single-use, and bound to the client and redirect URI per protocol; never log raw `code` or `state` values in operations.
- After processing the callback, redirect the user to a clean URL so `code` does not linger on workspace screens, shared links, or analytics.
- Never use the implicit flow returning `access_token` in the fragment as a default for new SPAs.

Although PKCE reduces the risk of intercepted codes being used, `code` remains contextually sensitive. Handling callbacks with the Spring Security OAuth2 Client library avoids subtle custom verification mistakes. Never break `/login/oauth2/code/...` just to ensure "no code ever appears in any URL".

### 4.2. Password Reset and Email Verification Links

Account recovery emails often must carry a **temporary recovery code** in a link so the recipient can open the page:

```text
https://app.example.com/reset?code=ONE_TIME_RESET_CODE
```

This is a business exception that must be strictly protected, because anyone holding the link within its validity window can perform a sensitive action. The design should include:

1. A sufficiently unpredictable random code, narrow usage scope, **short lifetime**, and **single-use** semantics; store a hashed/verifiable form server-side where appropriate and invalidate upon use.
2. HTTPS, rate limiting, auditing, and not disclosing whether an account exists when recovery is requested.
3. The landing page must not load unnecessary analytics, third-party scripts, or external resources; set `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
4. Avoid logging the URL/code in CDNs, proxies, gateways, APMs, JavaScript error trackers, or support tickets. A filter at the end of a request cannot erase logs a gateway already wrote earlier.
5. Exchange the code for a short-lived workflow session and redirect to a clean URL; use `POST` for changing the password and validate the code properly.
6. If a link is detected as leaked, treat the code as compromised: revoke, reissue, and check for unauthorized use.

**Never** turn a reset code into a long-lived access token. `history.replaceState` only removes the URL from the address bar after the page loads; it **cannot recall** copies already captured in history, network logs, or proxies.

### 4.3. Signed URLs (Presigned URLs)

A signed URL for downloading a file for a limited time is a **bearer-style capability**. It may be required by object storage or file delivery systems, but must restrict lifetime, allowed methods/permissions, target resource, sharing, and logging; avoid sending it to unrelated parties. It is **not** a general mechanism for passing a user's login bearer token.

## 5. Principles for Designing Non-Leaking Error Messages

A good error message answers: did the request succeed, what should the user do next, and what can operations look up? It **never needs** to return SQL queries, hostnames, Java class names, access tokens, or passwords.

| Error | Should NOT return | Appropriate public message |
| --- | --- | --- |
| Invalid login | "No user `alice@example.com`" or "password `123456` is wrong" | "Invalid username or password." |
| Expired session / unauthenticated | "Cookie `JSESSIONID=...` expired" | 401 + `AUTHENTICATION_REQUIRED`; client re-authenticates. |
| Unauthorized | "You lack role `FINANCE_ROOT` in ACL table `internal_roles`" | 403 + `ACCESS_DENIED` or designed 404 policy. |
| Token error | "JWT `eyJ...` invalid signature at line ..." | 401 + protocol-valid error code without echoing token value. |
| Invalid input | Echoing full body containing password/API key | 400 + **publicly safe** field names and validation rules. |
| 500 error | `Exception.getMessage()`, stack trace, DB connection, raw URL | 500 + `INTERNAL_ERROR` and correlation ID if supported. |
| Route not found | `request.getRequestURL() + "?" + request.getQueryString()` | 404 + neutral message without reflecting query string. |

Simple contract example:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Unable to process request at this time."
}
```

If a correlation ID is included, it should be random, free of credentials or user data, and searchable only in access-restricted logs. Never reuse a token, cookie, session ID, or raw URL as a correlation ID. Some APIs use RFC 9457 `ProblemDetail`, adding public error codes as extension properties; contract consistency matters more than the exact field names in this example.

### 5.1. Commonly Overlooked Error Leak Sources

- `exception.getMessage()` and `ex.toString()` can contain connection strings, file paths, query contents, or third-party service payloads.
- `request.getQueryString()` and `request.getRequestURI()` can contain secrets in query/path; never reflect them directly into JSON/HTML, redirects, `Location`, or `WWW-Authenticate`.
- `BindingResult`/validation messages and echoed request bodies can contain passwords/API keys; expose only vetted field names and rule identifiers.
- `ResponseStatusException` with client-controlled reasons or exceptions from external APIs can leak details if default error handling returns raw messages.
- Default/debug error pages, stack traces, and `server.error.include-*` in production must be checked; never let clients trigger stack-trace output.
- Internal logs are not automatically immune either: redact `Authorization`, `Cookie`, `Set-Cookie`, passwords, refresh tokens, secret keys, and request/response bodies at collection points.
- Never print tokens to the browser console or send tokens to analytics when rendering error pages.

**Do not mix security errors with application errors:** 401 errors are typically handled by `AuthenticationEntryPoint` and 403 errors by `AccessDeniedHandler` or equivalent mechanisms; `@RestControllerAdvice` handles MVC exceptions and does not automatically catch exceptions thrown earlier in filters. When customizing 401/Bearer JSON, preserve standard `WWW-Authenticate` headers; never break authentication protocols just for "prettier messages".

## 6. Spring Boot 3.x Example: Blocking Sensitive URL Parameters and Returning Non-Reflecting Errors

This example **illustrates an additional defense layer**: the demo API rejects query parameter names such as `access_token`, `refresh_token`, `id_token`, `password`, and `api_key`, and omits request values and exception details from error responses.

**Important limitation:** the filter below detects a known list of query parameter names. It **cannot prove every URL is clean**: secrets could appear under `q`, in the path, multiple-encoded, or at a gateway before reaching the app. The primary defense remains designing clients not to put secrets in URLs, configuring logging across all tiers, and real testing. Never rely on a filter as a "silver bullet" replacing sound design.

Written for **Java 17+, Spring Boot 3.x, and Spring Security 6.x**. Create a Boot project with Gradle wrapper, plugins, and main class; add dependencies:

```groovy
// Fragment in build.gradle (Groovy DSL), not a complete build file.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

All Java classes use package `demo.safeurl`.

### 6.1. Startup Application

File `src/main/java/demo/safeurl/SafeUrlApplication.java`:

```java
package demo.safeurl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUrlApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUrlApplication.class, args);
    }
}
```

### 6.2. Filter Blocking Sensitive Query Parameter Names

File `src/main/java/demo/safeurl/SensitiveQueryGuardFilter.java`:

```java
package demo.safeurl;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;

public final class SensitiveQueryGuardFilter extends OncePerRequestFilter {

    private static final Set<String> BLOCKED_NAMES = Set.of(
        "access_token", "refresh_token", "id_token", "password",
        "passwd", "client_secret", "api_key", "apikey",
        "authorization", "cookie", "session_id", "jsessionid"
    );

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Use request path without context path, checking only the demo API.
        String uri = request.getRequestURI();
        String contextPath = request.getContextPath();
        String path = uri.substring(contextPath.length());
        return !path.startsWith("/api/public/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String query = request.getQueryString();

        if (query != null) {
            for (String part : query.split("&")) {
                int equalSign = part.indexOf('=');
                String encodedName = equalSign < 0
                        ? part
                        : part.substring(0, equalSign);

                final String decodedName;
                try {
                    decodedName = URLDecoder.decode(
                            encodedName, StandardCharsets.UTF_8
                    ).toLowerCase(Locale.ROOT);
                } catch (IllegalArgumentException malformedEncoding) {
                    // Do not include URL or exception in response/log.
                    writeSafeBadRequest(response);
                    return;
                }

                if (BLOCKED_NAMES.contains(decodedName)) {
                    writeSafeBadRequest(response);
                    return;
                }
            }
        }

        chain.doFilter(request, response);
    }

    private static void writeSafeBadRequest(HttpServletResponse response)
            throws IOException {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.getWriter().write(
            "{\"code\":\"SENSITIVE_URL_PARAMETER\","
            + "\"message\":\"Invalid data in URL.\"}"
        );
    }
}
```

Design notes:

1. `getQueryString()` is only used to **inspect parameter names**. The filter never appends `query`, `URI`, or exceptions to logs or responses.
2. `URLDecoder` handles percent-encoded names such as `access%5Ftoken`; it still cannot guarantee detecting every encoding or unusual parameter naming scheme. Malformed percent-encoding returns 400 with a neutral body.
3. Active only under `/api/public/**` for this exercise; do not copy this parameter list and path into production without inventorying your endpoints.
4. `OncePerRequestFilter` is registered inside the **Spring Security filter chain**, not as an auto-registered Servlet filter bean; avoid `@Component` on this class when also using `addFilterBefore`.
5. Blocking sensitive query parameter names is a supplemental measure; if a gateway already logged the full URL before the request reached the JVM, this filter cannot erase that log line.
6. A static 400 response with `Cache-Control: no-store` gives clients a consistent error without leaking secrets. In real systems, consider a shared error writer ensuring every error branch includes protective headers.

### 6.3. Adding the Filter to the Chain While Keeping Protective Defaults

File `src/main/java/demo/safeurl/SecurityConfig.java`:

```java
package demo.safeurl;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Endpoints are for demo purposes only, not a production API pattern.
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().denyAll()
            )
            .addFilterBefore(
                new SensitiveQueryGuardFilter(), AuthorizationFilter.class
            );

        return http.build();
    }
}
```

`AuthorizationFilter` is added when configuring `authorizeHttpRequests`. Placing the custom filter before it rejects requests with sensitive query parameters on the demo API; other endpoints still follow authorization rules. When a request matches `shouldNotFilter`, the filter skips its own logic while the rest of the Spring Security filter chain continues running.

The code does not disable CSRF, CORS, security headers, or relax `anyRequest` system-wide. Because the example uses public `GET` requests to test URL leakage, it does not illustrate CSRF-protected mutations. If a real app has cookie-authenticated `POST` endpoints, test CSRF independently.

### 6.4. Controller Simulating an Internal Error and MVC Advice Hiding Details

File `src/main/java/demo/safeurl/DemoController.java`:

```java
package demo.safeurl;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/public")
public class DemoController {

    @GetMapping("/search")
    public Map<String, Object> search(
            @RequestParam(defaultValue = "") String q
    ) {
        // Do not reflect the raw query string or q content into the response.
        return Map.of("accepted", !q.isBlank(), "resultCount", 0);
    }

    @GetMapping("/fail")
    public String fail() {
        // Technical string solely to prove it does not appear in public errors.
        throw new IllegalStateException(
            "internal-db=private-node; token=INTERNAL_ONLY"
        );
    }
}
```

File `src/main/java/demo/safeurl/PublicErrorAdvice.java`:

```java
package demo.safeurl;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class PublicErrorAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> handleUnexpectedError() {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .body(Map.of(
                "code", "INTERNAL_ERROR",
                "message", "Unable to process request at this time."
            ));
    }
}
```

Here `@RestControllerAdvice` handles only the example's `IllegalStateException`; **you cannot assume every error from controllers, filters, Spring Security, or reverse proxies is now hidden**. Production systems need a comprehensive policy for 400, 401, 403, 404, 500, and real exceptions, along with scrubbing sensitive details from logs, APMs, and default error pages.

## 7. MockMvc Tests: Valid Input Accepted, Secrets Blocked, Errors Not Reflected

File `src/test/java/demo/safeurl/SensitiveUrlTests.java`:

```java
package demo.safeurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SensitiveUrlTests {

    private static final String FAKE_SECRET = "FAKE_SECRET_TEST_ONLY_123";

    @Autowired
    MockMvc mvc;

    @Test
    void ordinaryQueryIsAccepted() throws Exception {
        mvc.perform(get("/api/public/search?q=java"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.resultCount").value(0));
    }

    @Test
    void accessTokenInQueryIsRejectedWithoutReflection()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/search?access_token=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("SENSITIVE_URL_PARAMETER"))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains(FAKE_SECRET));
        assertFalse(body.contains("access_token"));
    }

    @Test
    void percentEncodedSensitiveParameterNameIsRejected()
            throws Exception {
        mvc.perform(
                get("/api/public/search?access%5Ftoken=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("SENSITIVE_URL_PARAMETER"));
    }

    @Test
    void passwordInQueryIsRejectedWithoutReflection()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/search?password=" + FAKE_SECRET)
            )
            .andExpect(status().isBadRequest())
            .andReturn();

        assertFalse(result.getResponse().getContentAsString()
                .contains(FAKE_SECRET));
    }

    @Test
    void exceptionDetailsAndQueryAreNotReturnedToClient()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/public/fail?note=harmless")
            )
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("INTERNAL_ONLY"));
        assertFalse(body.contains("private-node"));
        assertFalse(body.contains("IllegalStateException"));
        assertFalse(body.contains("note=harmless"));
    }
}
```

Run inside the Boot project configured with Gradle wrapper:

```bash
./gradlew test --tests demo.safeurl.SensitiveUrlTests
```

When implemented with the classes and dependencies above, **these five tests are designed to PASS**. That is the expected outcome of the example, not a claim that the suite was executed in this document. With `@AutoConfigureMockMvc` and `spring-security-test`, MockMvc runs through the application's configured filter chain.

| Test | Expected result | What it proves |
| --- | --- | --- |
| `q=java` | 200, valid JSON | Ordinary queries work; legitimate parameters are not mistakenly blocked. |
| `access_token=FAKE_SECRET` | 400, code `SENSITIVE_URL_PARAMETER` | Token-named query is blocked; response does not echo sensitive value/name. |
| `access%5Ftoken=...` | 400 | Common URL-encoded parameter names are still detected. |
| `password=FAKE_SECRET` | 400, clean body | Credentials are not reflected back to the client. |
| `/fail?note=...` with internal error | 500, `INTERNAL_ERROR`, clean body | Exception message, internal hostnames, and query never appear in the response. |

These tests **only verify application behavior at the MockMvc entry point**. They do not prove that reverse proxies, CDNs, browser history, URL paths, log files, or APMs avoid recording tokens. End-to-end verification requires testing real infrastructure and checking log/trace collection settings across every layer.

You can run the program with `./gradlew bootRun` and issue valid GET calls over HTTPS in the target environment. Never put real tokens in curl commands, browsers, or tests; even a command line with a URL can be saved in shell history.

## 8. Protecting Spring Security and Spring MVC Error Responses in Production

The example above mainly illustrates **400 errors from a filter and 500 errors from MVC**. For applications with real authentication, 401/403 flows must be tested separately.

### 8.1. Handling 401 and 403 at Their Source

- **401 Unauthorized:** request requires authentication that is absent or invalid. In Spring Security Servlet, many cases are handled via `AuthenticationEntryPoint`. Use neutral messages; never say which token was wrong or echo the token back.
- **403 Forbidden:** request is authenticated but lacks sufficient permissions, typically via `AccessDeniedHandler` or equivalent handlers. Never reveal internal role/ACL names or details about resources the caller is not permitted to know exist.
- **401 Bearer/Basic:** the `WWW-Authenticate` header is an essential part of the protocol and must retain a valid challenge. Never place the original `Authorization` header, session cookies, or stack traces in challenge headers.

If there are multiple `SecurityFilterChain` beans, test each chain. MVC error handlers like `@RestControllerAdvice` do not automatically intercept errors raised before `DispatcherServlet`.

### 8.2. Controlling Default and Debug Errors

In production, review Spring Boot's policies for `server.error.include-message`, `server.error.include-stacktrace`, `server.error.include-exception`, validation errors, and the default error page. Never provide a mechanism letting clients request stack traces for troubleshooting.

Example properties to configure explicitly in `application-prod.yml`:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
    include-binding-errors: never
```

This is a safeguard for Boot's default error controller; custom handlers can still leak data if they return raw exceptions, URLs, or bodies. Debug and Actuator endpoints must also be secured and data-restricted. Never assume error responses are safe solely because these properties are set.

### 8.3. Protecting URLs in Logs, Traces, and Alerts

Avoid logging:

```java
// DO NOT: may log credentials in the query string.
log.warn("Request failed: url={}, reason={}",
         request.getRequestURL() + "?" + request.getQueryString(),
         exception.getMessage());
```

Replace with vetted values such as route templates, error codes, and an independent correlation ID:

```java
// Illustrative at a place where routeName, publicCode, and correlationId
// are already verified not to contain sensitive input data.
log.warn("Request rejected: route={}, code={}, correlationId={}",
         routeName, publicCode, correlationId);
```

This is a fragment, not a standalone Java class: variables and loggers must be declared in your app. If `routeName` is populated by copying the raw URL, you lose the protection. If `exception.getMessage()` contains a secret, logging it uncontrolled remains risky even if not shown to the client.

At gateways and APMs, prefer **route templates** (such as `/api/orders/{id}`) over full URLs or query strings. If operational needs still require a few query parameters, allowlist only vetted non-sensitive parameters; never rely solely on "regex-replacing `token=...`" because parameter names and encodings vary widely.

## 9. `Referrer-Policy`, `Cache-Control`, and Their Limits

Pages handling sensitive data typically need:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

- `Referrer-Policy: no-referrer` instructs browsers not to send the `Referer` header from that page. It reduces one URL leak vector, **yet does not clear browser history, access logs, or scripts that already read the URL**.
- `Cache-Control: no-store` instructs compliant caches not to store the response; it **does not guarantee** the app refrains from logging URLs or users refrain from copying URLs.
- `nosniff` helps control browser MIME sniffing; it is **not** a token-hiding mechanism.
- Content Security Policy (CSP) and restricting third-party scripts shrink the script surface that can read page data; CSP does not replace clean URL design.
- `Secure` and `HttpOnly` apply to cookies; they do not protect tokens placed in queries, paths, or fragments.

Changing response headers while still generating links like `?access_token=...` leaves the root vulnerability unsolved.

## 10. Acceptance Testing Matrix for Real Applications

| Item | Scenario to test | Passing signal |
| --- | --- | --- |
| Login | Form login, success/failure redirects | URLs carry no password, session ID, or refresh/access token; failed-login messages are neutral. |
| Session cookie | `Set-Cookie` response and subsequent requests | Cookie has proper flags and is never reflected in URLs, error JSON, or logs. |
| Bearer API | Resource calls with valid/invalid `Authorization` | Protocol-compliant headers; 401/403 do not echo tokens; no access tokens in queries. |
| Internal links | Navigation, emails, shared URLs | No tokens/cookies/credentials in `href`, `Location`, canonical URLs, or appended queries. |
| OAuth callback | Authorization Code + PKCE | Code/state validated and short-lived; never used as bearer access token; raw code not logged. |
| Account recovery | Valid/expired/used/replayed links | Single-use, short-lived, free of log/analytics/third-party leaks; safe referrer and cache headers on page. |
| 400 errors | Invalid inputs or sensitive URL params | Proper status/public codes; never echoes passwords, tokens, cookies, or sensitive bodies. |
| 401 and 403 errors | Unauthenticated or unauthorized calls | Neutral messages and standard challenges; no internal role names or raw tokens leaked. |
| 500 errors | Technical exception holding internal data | Body and headers free of stack traces, queries, secrets, or class/infra names; safe log lookup. |
| Proxy/APM/logs | Requests carrying fake sentinels in sensitive params | Test sentinel absent from access logs, traces, analytics, tickets, and alerts outside controlled bounds. |
| Browser history/referrer | Opening, navigating, and sharing pages | No token-bearing URLs propagated; browser obeys configured policies. |
| Code review | Inspecting URL/redirect builders and exception catches | No credential concatenation into URLs; never returns raw `ex.getMessage()` or `request.getQueryString()`. |

**Testing log leaks with safe dummy markers:** use a sentinel like `FAKE_SECRET_TEST_ONLY_123`, verify the request is blocked or handled as designed, then search **staging/test environment** logs and traces for that sentinel. Never use real passwords or tokens for this test. If the sentinel appears in proxy logs before the filter blocks it, fix the proxy's logging configuration; controller advice alone cannot fix upstream logs.

## 11. Common Mistakes and Fixes

1. **"We use HTTPS, so tokens in URLs are fine."** HTTPS covers transit only; history, logs, referrers per policy, analytics, and user link-sharing remain exposed.
2. **Moving `?token=...` to `/token/...`.** The path is still part of the URL and gets logged/copied. Use headers, cookies, or bodies according to data type.
3. **Putting tokens in `#fragment` so "the server never sees them".** JavaScript, extensions, and history can still see them; never use fragments as default storage for access tokens.
4. **Base64- or URL-encoding access tokens before putting them in links.** Encoding is trivially reversible and adds zero secrecy.
5. **Sending passwords over GET.** Switch to POST body over HTTPS, suppress sensitive body logging, and protect login flows properly.
6. **Reading cookies from JavaScript for convenience.** Session cookies should be `HttpOnly` whenever JS does not need them; never put session IDs in URLs or consoles.
7. **Returning `ex.getMessage()` to help users report bugs.** Use error codes/correlation IDs and public messages; restrict internal logs by role.
8. **Returning the full validation payload.** Error lists should contain only permitted field names and rule codes; never echo passwords, API keys, or refresh tokens.
9. **Relying solely on regex masking in logs.** Parameter names, encodings, nested JSON, paths, and headers vary too much; use log field allowlists and avoid capturing sensitive data.
10. **Fixing only Spring MVC errors.** Security filters, proxies, gateways, error pages, and OAuth callbacks can have separate handlers and logs.
11. **Confusing OAuth authorization codes with bearer access tokens.** Redirect codes are PKCE-protected, short-lived, single-use protocol artifacts; access/refresh tokens must never be put arbitrarily in queries.
12. **Creating permanent reset links.** Recovery codes must expire quickly, be single-use, and be shielded from logs, referrers, scripts, and sharing.
13. **Thinking 5 MockMvc tests prove the entire system is safe.** You still must inspect browsers, proxies, APMs, and logs outside the JVM.
14. **Using real secrets in leak tests.** Use fake tokens/sentinels only to keep real secrets out of test output and CI logs.

## 12. Practice Exercise

An API has these three URLs:

```text
GET  /api/orders?access_token=REAL_VALUE
POST /login?password=REAL_VALUE
GET  /reset?code=ONE_TIME_VALUE
```

Analyze each case:

- `/api/orders`: move the access token to the `Authorization: Bearer ...` header over HTTPS, verify client origin and token scope/expiry; never construct URLs containing tokens.
- `/login`: use a POST form/body over HTTPS; keep passwords out of queries, paths, and redirects; suppress body logging and handle session cookies/CSRF.
- `/reset`: a one-time code in the link may be required by the recovery flow, yet it must be short-lived and tightly scoped, unlogged, script-restricted, served with no-referrer/no-store, consumed promptly, and redirected to a clean URL.

Then write tests verifying: a valid request succeeds; a request with a fake token in the URL is rejected; an exception containing `INTERNAL_ONLY` still returns a 500 response without that string; and an environment check confirms gateways/APMs do not store the sentinel.

**Self-assessment:** can a user copy a URL, send an error screenshot, and ask support for help without accidentally sharing an active credential? Can the server diagnose errors without writing tokens or passwords to logs? If not, both design and testing still need work.

## References

- OWASP — [Information exposure through query strings in URL](https://community.owasp.org/vulnerabilities/Information_exposure_through_query_strings_in_url).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- OAuth 2.0 Bearer Token Usage — [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750).
- OAuth 2.0 Authorization Code — [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749).
- PKCE — [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636).
- HTTP Semantics (fragments and `Referer`) — [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110).
- Spring Security — [Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html).
- Spring Security — [Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Boot — [Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).