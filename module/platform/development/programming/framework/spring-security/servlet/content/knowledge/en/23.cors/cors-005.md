# allowCredentials and the Limits of Wildcard Origins in CORS

**Scope:** Spring Security on **Servlet/Spring MVC**, Spring Boot 3.x / Spring Security 6.x applications; Java 17+ examples. This lesson explains exactly when to use `allowCredentials(true)`, why it cannot be paired with `allowedOrigins("*")`, how to configure a safe allowlist, and how to observe preflight/responses from the browser.

## 1. Grasp Three Concepts Accurately: Origin, CORS, and Credentials

An **origin** has three components: **scheme + host + port**. If even one component differs, it is **cross-origin**.

| URL A | URL B | Same origin? | Reason |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/profile` | Yes | Path is not part of the origin. |
| `https://app.example.com` | `https://api.example.com` | No | Different host. |
| `http://localhost:5173` | `http://localhost:8080` | No | Different port. |
| `http://example.com` | `https://example.com` | No | Different scheme. |

**CORS (Cross-Origin Resource Sharing)** is the mechanism a browser uses to decide whether JavaScript at origin A may read an HTTP response from origin B. The server declares policy via `Access-Control-Allow-*` headers. The Same-Origin Policy remains the default; the server only relaxes access for approved origins.

**Credentials** in the Fetch/CORS context can include cookies, HTTP authentication, and TLS client certificates. For session-based applications, authentication cookies like `JSESSIONID` are the common case. Note that there are **two distinct decisions**:

1. **Client** chooses whether to send/receive credentials (`fetch(..., { credentials: "include" })` for cross-origin).
2. **Server** decides whether to allow exposing responses to a cross-origin request carrying credentials (`Access-Control-Allow-Credentials: true` together with a valid origin).

The `Access-Control-Allow-Credentials: true` header **does not by itself force the browser to send cookies**, **does not make cookies bypass SameSite/Secure rules**, and **does not mean all origins are allowed**.

## 2. Core Rule: Credentials Do Not Pair with Wildcard Origin "*"

Suppose JavaScript at `https://app.example.com` calls `https://api.example.com/api/profile` with `credentials: "include"`. **Invalid** response configuration:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

For requests with credentials, the browser **does not accept** `Access-Control-Allow-Origin: *` to expose responses to JavaScript. This is a CORS specification rule, not specific to Spring. Developer Tools may report an error similar to: *The value of the 'Access-Control-Allow-Origin' header must not be '*' when the request's credentials mode is 'include'.*

**Correct configuration** for a permitted frontend:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

`Access-Control-Allow-Origin` specifies **one concrete permitted origin** (without a path); if there are multiple origins in the allowlist, the server selects/echoes the exact request origin when permitted, rather than returning a comma-separated list of origins. `Vary: Origin` helps caches distinguish responses that may differ by origin; for preflight, Spring may also add `Access-Control-Request-Method` and `Access-Control-Request-Headers` to `Vary`.

For **public** resources not needing credentials, `Access-Control-Allow-Origin: *` may be appropriate. When the frontend sends `credentials: "include"`, a wildcard is still invalid even if the endpoint is public; the client may consider `credentials: "omit"` if credentials are genuinely not needed.

| Scenario | `Access-Control-Allow-Origin` | `Access-Control-Allow-Credentials` | Browser outcome |
| --- | --- | --- | --- |
| Request without credentials, public API | `*` | Not required to be `true` | Can read response if other CORS rules also pass. |
| Request `credentials: "include"`, valid frontend | `https://app.example.com` | `true` | Response exposed if other CORS, cookie, and auth conditions pass. |
| Request `credentials: "include"` | `*` | `true` | **Blocked by CORS** when JavaScript reads response. |
| Request `credentials: "include"`, specific origin | `https://app.example.com` | Missing/not `true` | **Blocked by CORS** for credentialed request. |
| Untrusted origin not in allowlist | No matching origin returned | Not permitted | Browser prevents JavaScript of untrusted origin from reading response. |

**Important:** CORS is a **browser** policy, not a server authentication or authorization system. `curl`, Postman, and other backends can still call the API; `Origin` can be spoofed by non-browser clients. Endpoints must still verify session/token, access permissions, and input data. A *simple request* may already have been sent to the server before the browser blocks JavaScript from reading the response; therefore CORS **does not replace CSRF protection**.

## 3. Spring Framework: allowedOrigins vs. allowedOriginPatterns

In Spring MVC/Security, `CorsConfiguration` has two common ways to configure origins:

**Option A — list exact trusted origins (preferred):**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
    "https://app.example.com",
    "http://localhost:5173"
));
cors.setAllowCredentials(true);
```

Each `allowedOrigins` entry is an origin consisting of scheme, host, and port if any; no path, query, `*` in host, or trailing `/`. Only include `localhost` in a development environment profile, and do not leave it open unnecessarily in production.

**Option B — use patterns when there are genuinely many valid subdomains:**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.example.com"
));
cors.setAllowCredentials(true);
```

For an actual origin matched by the pattern, Spring writes the **specific matched origin** into `Access-Control-Allow-Origin`, for example `https://portal.example.com`; the response header **does not contain the pattern** `https://*.example.com`. This enables `allowCredentials(true)` to work at the protocol level. However, every subdomain matching the pattern is trusted: a subdomain managed by a third party or compromised can create risk. The pattern above also does not automatically include the apex origin `https://example.com`; if needed, add it separately.

**Configuration to avoid:**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true); // Invalid when combined with "*".
```

Spring checks this combination via `validateAllowCredentials()` and may throw `IllegalArgumentException` when processing CORS: `*` cannot be placed in `Access-Control-Allow-Origin` for a credentialed response. Similarly, `@CrossOrigin(origins = "*", allowCredentials = "true")` is a conflicting configuration.

**Do not mechanically "fix" it with `allowedOriginPatterns("*")`.** Although Spring can echo the concrete origin and allow credentials with a global pattern, its effect is trusting **every** website to read credentialed responses (if cookies are actually sent and the endpoint permits). That is far too broad a policy for an API carrying private data.

## 4. Complete Configuration for Spring Security Servlet

Example Spring Boot 3.x application with a development frontend at `http://localhost:5173` and production frontend at `https://app.example.com`. The backend registers CORS for `/api/**` and keeps Spring Security protecting endpoints that require login.

The Java files below share package `com.example.corsdemo`, placed in `src/main/java/com/example/corsdemo/`. The example requires `spring-boot-starter-web` and `spring-boot-starter-security` dependencies on the classpath; they are **not** standalone plain `javac` programs.

**`CorsConfig.java`:**

```java
package com.example.corsdemo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Explicit origins, DO NOT use "*" when credentials are enabled.
        config.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));
        config.setAllowCredentials(true);

        // Restrict actions and request headers to what is actually needed.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
        ));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"
        ));
        config.setExposedHeaders(List.of("X-Request-ID"));
        config.setMaxAge(1800L); // Browser may cache preflight.

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
```

**`SecurityConfig.java`:**

```java
package com.example.corsdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource) throws Exception {

        http
            // Apply CORS in the Security filter chain,
            // so OPTIONS preflight runs before authentication.
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Keep default CSRF protection for unsafe methods.
        return http.build();
    }
}
```

**`ApiController.java`:**

```java
package com.example.corsdemo;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public ResponseEntity<Map<String, String>> publicData() {
        return ResponseEntity.ok()
            .header("X-Request-ID", "demo-001")
            .body(Map.of("message", "public"));
    }

    @GetMapping("/api/account")
    public Map<String, String> account(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/api/items")
    public Map<String, String> receive(
            @RequestBody Map<String, String> input) {
        // Echo only for illustration; not persisted to a database.
        return Map.of("received", input.getOrDefault("name", ""));
    }
}
```

**`CorsDemoApplication.java`:**

```java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

If creating a new project, choose **Spring Initializr → Gradle, Java 17+, Spring Boot 3.x, Spring Web, Spring Security**, add the four files above, and run the wrapper command:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `.\gradlew.bat bootRun`. The default URL when `server.port` is unchanged is `http://localhost:8080`; the frontend runs at `http://localhost:5173`. Spring Security's default demo password (if using the generated user) appears in the startup log; it is for testing only, not for production use.

**What happens?**

- `GET /api/public` is allowed when not logged in. Browsers from an allowed origin receive the matching `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials: true`. The `X-Request-ID` header is readable by JavaScript because of `exposedHeaders`.
- `GET /api/account` requires a login session. Valid CORS only helps the browser read the response **when authentication is also valid**.
- `POST /api/items` is also subject to CSRF protection. A cross-origin request with a session cookie and valid CORS **can still get 403** if the CSRF token is missing. To call the real POST, you must integrate a suitable CSRF token issuance/reading flow (e.g. cookie + `X-XSRF-TOKEN` header) and ensure the client can access the token under the chosen origin/cookie architecture. Do not disable CSRF to "fix" CORS errors.
- With a source configured for `/api/**`, the CORS policy does not automatically apply to other paths (like `/login`). If the frontend must log in via cross-origin XHR, you need to design an appropriate login/session/cookie flow; this code only illustrates public GET, authenticated GET, and API preflight.

In a Spring Security application, processing CORS **before authentication checks** is crucial because `OPTIONS` preflight requests normally **do not carry session cookies**. Configuring `http.cors(...)` so Spring Security uses `CorsConfigurationSource` ensures preflight requests are handled in the right place. Do not simply write a manual filter returning `Access-Control-Allow-Origin` for all requests, which easily creates duplicate headers or missing policies.

## 5. Frontend: Credentials Must Be Enabled on the Fetch Side

Example JavaScript running on frontend `http://localhost:5173` calling API `http://localhost:8080`:

```javascript
const apiBase = "http://localhost:8080";

async function readPublicData() {
  const response = await fetch(apiBase + "/api/public", {
    method: "GET",
    credentials: "include"
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const data = await response.json();
  const requestId = response.headers.get("X-Request-ID");

  console.log(data, requestId);
}

readPublicData();
```

When the server runs properly and the origin is in the allowlist, example log output is:

```text
{message: 'public'} 'demo-001'
```

Object formatting in DevTools may vary by browser, yet the JSON payload is `{"message":"public"}` and the header read is `demo-001`.

Fetch credential modes:

- `omit`: do not send credentials and do not process receiving credentials in this mode; suitable for genuinely public APIs.
- `same-origin`: Fetch's default; sends credentials for same-origin requests, **does not send cookies on cross-origin requests**.
- `include`: allows sending/receiving credentials even cross-origin, **subject to cookie limits and browser policies**. The server must return appropriate CORS headers for JavaScript to read the response.

Cross-origin **does not equal** cross-site. Two ports on `localhost` are cross-origin yet may be same-site; `app.example.com` and `api.example.com` are cross-origin yet usually same-site. Conversely, `other-domain.test` to `api.example.com` is cross-site. `SameSite=Lax` or `Strict` cookies, `Secure`, third-party cookie restrictions, and partitioning can prevent cookies in certain cross-site requests **even when CORS is valid**. For cookies that must be sent in a cross-site context, `SameSite=None; Secure` usually must be considered and remains subject to browser cookie-blocking policies. Never treat relaxing `SameSite` as a default solution for every system.

**If JS needs to POST with a CSRF token:** CORS must allow the `X-XSRF-TOKEN` request header and appropriate preflight. Putting a token in a header is a **CSRF** concern, separate from `allowCredentials`. A frontend at `app.example.com` cannot read a **host-only** cookie of `api.example.com` via `document.cookie`; a specifically designed bootstrap/token/BFF mechanism is needed, rather than assuming `credentials: "include"` automatically makes cookies appear in the frontend's `document.cookie`.

## 6. Preflight: The Browser Asks Permission Before Conditional Requests

When making a cross-origin request with a non-safelisted method or header (for example a JSON POST with `Content-Type: application/json` or header `X-XSRF-TOKEN`), the browser normally sends an `OPTIONS` **preflight**:

```http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
```

A valid response from Spring may look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: content-type,x-xsrf-token
Access-Control-Max-Age: 1800
Vary: Origin
```

Specific headers/formatting may vary by version and request, as long as CORS policy is satisfied. A successful preflight only allows the browser to **attempt sending the actual request**; the `POST` request may still be blocked by authentication, CSRF, or validation. Do not use the preflight's status as proof that the business POST succeeded.

Per the CORS specification, **preflight normally does not send credentials** like session cookies; therefore if the Security filter chain forces `OPTIONS` to be authenticated, preflight may return 401/302 before CORS is evaluated. Some implementations have special TLS client certificate behaviors; do not rely on them to authenticate preflight.

**Do not use `*` indiscriminately with credentialed preflight:** beyond origin, wildcards in `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, or `Access-Control-Expose-Headers` also have special semantics when requests carry credentials; the safest and easiest-to-verify approach is listing required methods/headers as in the configuration above.

## 7. Practical Testing with curl and DevTools

Assume the backend is at `http://localhost:8080`.

**A. Test preflight for a permitted origin:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-xsrf-token"
```

On Windows PowerShell, you can use `curl.exe` to invoke real curl. A valid response needs `Access-Control-Allow-Origin: http://localhost:5173` and `Access-Control-Allow-Credentials: true`, plus methods/headers for preflight.

**B. Test an origin not in the allowlist:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"
```

Must not receive a CORS response authorizing `https://untrusted.example`. Spring may return 403 for a rejected preflight. Do not use `curl` to conclude whether a browser allows reading the response, because `curl` does not enforce the same-origin policy.

**C. Test GET from frontend JavaScript:**

In Chrome/Edge DevTools → **Network**, open the request to `/api/public`:

1. **Request Headers** must have `Origin: http://localhost:5173`.
2. **Response Headers** must have `Access-Control-Allow-Origin: http://localhost:5173` and `Access-Control-Allow-Credentials: true` if using `credentials: "include"`.
3. The **Console** tab receives the JSON and `X-Request-ID` as in the JS snippet. If you switch the frontend to an unpermitted origin, the browser will report a CORS error.
4. If you see a server response in Network yet `fetch` fails due to CORS, there is no contradiction: the server may have processed the request, while the **browser refuses to expose the response to JS**.
5. If authenticated GET returns 302/401, verify login/session and cookie rules. If POST returns 403, also check CSRF. Do not lump everything into CORS errors.

**D. Test misconfiguration in dev (do not deploy):**

If you change it to `setAllowedOrigins(List.of("*"))` while keeping `setAllowCredentials(true)`, Spring rejects that configuration when validating CORS config; typically you see an `IllegalArgumentException` regarding `allowCredentials` and wildcard. Restore the explicit origin allowlist to fix it.

## 8. Configuration Errors and How to Pinpoint the Real Cause

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Console says wildcard cannot be used with credentials | Response has `Access-Control-Allow-Origin: *`, Fetch uses `include`. | Use explicit origin allowlist + `allowCredentials(true)`; or drop credentials if API is truly public. |
| Spring throws `IllegalArgumentException` about `allowCredentials` | `allowedOrigins` contains `*` together with `allowCredentials=true`. | Switch to explicit `allowedOrigins`; only use `allowedOriginPatterns` after evaluating trust scope. |
| `Access-Control-Allow-Origin` is right yet JS still gets CORS error | Missing `Access-Control-Allow-Credentials: true` for `include` request; preflight missing method/header. | Inspect **both request and response** in Network, check credentials mode and headers. |
| Preflight returns 401/302 | `OPTIONS` handled by security/login filter before CORS. | Connect `CorsConfigurationSource` with `http.cors(...)`, verify CORS filter runs before authentication. |
| CORS is right yet no cookie is sent | Wrong Fetch `credentials`; blocked by SameSite/Secure/domain/path/third-party cookie policy. | Check Cookies tab, Network → Request Cookies, origin/site, and cookie attributes. |
| GET profile returns 401/302 | No valid session. | Verify session/login; valid CORS does not grant login authorization. |
| POST returns 403 even though preflight is green | Missing/wrong CSRF token or insufficient permissions. | Check `CsrfFilter` and `X-XSRF-TOKEN`; do not disable CSRF just to test CORS. |
| Works on localhost, fails in production | Scheme, host, or port mismatches allowlist; different HTTPS/cookie policy. | Allow exact production origin and audit domain/path/SameSite/Secure. |
| Responses sometimes serve wrong origin from cache | Proxy/CDN does not vary by `Origin`. | Ensure `Vary: Origin` is respected and caches do not leak private responses. |
| Duplicate `Access-Control-Allow-Origin` headers | Both Spring CORS configured and another header added via proxy/filter/controller. | Pick one configuration owner; avoid emitting duplicate/conflicting values. |

**Security notes:**

- **Do not reflect every `Origin`** without checking an allowlist; setting `allowedOriginPatterns("*")` when credentials are enabled creates the same effect.
- **Do not use `Access-Control-Allow-Origin: null` as a shortcut.** The `null` origin can arise from sandboxed iframes or `file:`; it is not trusted by default.
- CORS does not reduce the need for **CSRF tokens** when authenticating via cookies. Origin/Referer checking and SameSite can assist defense, yet do not automatically replace full CSRF protection.
- Allow only frontends that genuinely need to read credentialed responses; restrict methods/headers and exposed headers. Separate development and production configurations.
- Check **data access permissions** on the backend: a request with valid CORS is still subject to authentication, authorization, and object-level checks (IDOR/BOLA).

## 9. Self-Assessment Checklist

Answer these four questions yourself before enabling `allowCredentials`:

1. Which frontends need to read responses carrying cookies or HTTP credentials? Can you list their **exact** scheme/host/port?
2. Does the frontend use `credentials: "include"` for cross-origin, and are cookies actually sent under SameSite/Secure/domain/path?
3. Does the response return **one concrete origin** along with `Access-Control-Allow-Credentials: true`, required methods/headers, and `Vary: Origin`?
4. Have preflight, authentication, authorization, and CSRF been tested **separately**?

**Key Takeaways:** `allowCredentials(true)` lets the browser expose responses of credentialed requests **only to permitted origins**, yet does not itself send cookies or bypass authentication. With Spring Security Servlet, **`allowedOrigins("*")` + `allowCredentials(true)` is a conflict**. Use an explicit origin allowlist; if using `allowedOriginPatterns`, Spring echoes the actual origin, yet you must still tightly govern the pattern. Test CORS together with preflight, cookie policy, authentication, and CSRF to avoid misdiagnosing errors and over-granting access.
