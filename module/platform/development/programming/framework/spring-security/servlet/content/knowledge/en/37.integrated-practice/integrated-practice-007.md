# Practice Lab: CSRF, CORS, and Security Headers with Browser Testing

> **Lab environment:** Spring Boot 3.5.x, Spring Security 6.x (Servlet / Spring MVC), Java 17+, Maven; Chromium browser and Playwright. The backend runs at `http://localhost:8080`; a separate frontend runs at `http://localhost:5173`. Examples are for **localhost** development, not production security settings. The steps keep default CSRF, an exact CORS allowlist, and Spring Security's HTTP security headers. The goal is not merely making HTTP requests "succeed", but **triggering intentional failures, observing exact browser behavior, and proving the defenses work**.

## 1. Expected Outcomes

After this lab, you should be able to execute all four testing areas:

1. **CSRF:** form login / session cookie works; tokenless POST returns 403; a pre-login token becomes invalid after login; the fresh token works; a USER role cannot invoke an EDITOR action even with a valid CSRF token.
2. **CORS:** a page at `http://localhost:5173` calls the API at `http://localhost:8080` via `fetch` with `credentials: "include"`, preflight, and proper response headers. Origin `http://127.0.0.1:5173` is outside the allowlist and the browser blocks reading the cross-origin response.
3. **Security headers:** backend HTTP responses carry `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, and `Referrer-Policy` as configured; an inline script injected into the **backend HTML document** is blocked by CSP, while the same-origin external script still runs.
4. **Accurate boundary analysis:** explain why a 200 preflight does not grant operation permission, why a CORS error is not proof an API is protected by authorization, why an HTTP 403 is not necessarily CSRF, and why HSTS does not appear on plain HTTP localhost responses.

**Core principle:** CSRF, CORS, and security headers are **three distinct mechanisms** that can appear together in one request without replacing one another.

## 2. Defense Model: Do Not Confuse These Mechanisms

| Mechanism | Protection Purpose | Enforcement Boundary | What It Does **Not** Replace |
| --- | --- | --- | --- |
| **CSRF token** | Prevents state-changing requests triggered from another site while the browser auto-attaches credentials. | Server-side `CsrfFilter` validates tokens on unsafe HTTP requests. | Authentication, authorization, XSS defense. |
| **CORS** | Controls which origins allow **browser JavaScript** to read cross-origin responses, plus cross-origin request conditions. | Browser enforces CORS; server emits `Access-Control-Allow-*` headers. | Authentication, authorization, or blocking curl/server-to-server requests. |
| **CSP** | Reduces risk of unwanted script execution, content injection, and loading resources from untrusted sources. | Browser applies the policy of the **HTML document receiving the CSP**. | XSS output escaping, backend permission checks. |
| **X-Frame-Options / frame-ancestors** | Prevents unauthorized UI framing / clickjacking. | Browser on documents carrying that header. | CSRF tokens / POST validation. |
| **X-Content-Type-Options: nosniff** | Restricts MIME sniffing for certain resources. | Browser checking response MIME type and context. | Proper MIME configuration or input validation. |
| **HSTS** | Instructs browsers to use HTTPS for a host after receiving the policy over valid HTTPS. | Browser per host's HSTS state. | TLS/mTLS, reverse proxy, and authorization. |
| **Referrer-Policy** | Controls URL details sent in `Referer` during navigation/resource loads. | Browser. | Preventing sensitive request logging or other data leaks. |
| **Authorization** | Allows only authorized users/roles/permissions to invoke backend operations. | `SecurityFilterChain`, method security, domain policy, and data layer. | None of the first three mechanisms can replace this. |

**Why test with a real browser?** MockMvc can verify response headers, the CSRF filter, and URL authorization, but it does not fully reproduce browsers enforcing CORS, CSP, cookie jars, origin rules, preflight caches, or multi-tab session transitions. For conditions testing *actual browser enforcement*, use Playwright or an equivalent browser tool.

## 3. Project Structure for the Lab

Create the project directories:

~~~text
security-browser-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/securitylab/
│   │   │   ├── SecurityBrowserLabApplication.java
│   │   │   ├── SecurityConfig.java
│   │   │   └── ApiController.java
│   │   └── resources/static/
│   │       ├── index.html
│   │       └── app.js
│   └── test/java/com/example/securitylab/
│       └── HttpSecurityIntegrationTest.java
├── cors-client/
│   ├── index.html
│   └── client.js
└── browser-tests/
    └── tests/
        └── security.spec.js
~~~

**Two-origin setup:**

~~~text
Origin A - Backend:
  http://localhost:8080
  Spring Boot: /, /app.js, /csrf, /api/public,
               /api/profile, /api/notes, /login

Origin B - Frontend:
  http://localhost:5173
  Python static server: /, /client.js

Comparison:
  scheme (http)  : same
  hostname       : same localhost
  port           : DIFFERENT 8080 vs 5173
  -> DIFFERENT ORIGINS per browser rules
  -> same-site under localhost same-scheme rules
~~~

Two origins on different ports are **cross-origin**, so cross-origin `fetch` calls are governed by CORS. Yet they are **same-site** under schemeful same-site rules when both hostname and scheme match `localhost`; that matters for `SameSite` cookies. **Cross-origin does not mean cross-site.** Thus the demo uses `localhost` on both ports; **do not switch the frontend to `127.0.0.1`** and expect cookies to behave identically. They are different hosts and do not share a cookie jar.

## 4. Preparing Java, Maven, Node, and the Browser

Verify tools:

~~~bash
java -version
mvn -version
node --version
npm --version
~~~

Requires Java 17 or newer compatible with Boot 3.x; Maven 3.6.3+, and a Node.js version currently supported by Playwright. Python 3 can serve as the static dev server; on Windows, use `py` if `python3` is unavailable.

Create the Maven project in `pom.xml`; this is the **complete demo POM**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-browser-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version 3.5.0 in the POM is a **specific baseline for the demo**, not a claim about the latest Boot release. Real projects should use supported, security-patched Boot/Security versions and re-test DSL compatibility. Never mix Spring Security 5/`javax.servlet` dependencies into Boot 3/`jakarta.servlet`.

## 5. Starting the Spring Boot Application

File `src/main/java/com/example/securitylab/SecurityBrowserLabApplication.java`:

~~~java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityBrowserLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityBrowserLabApplication.class, args);
    }
}
~~~

This app serves the backend on port 8080 unless another `server.port` is set. If your environment already sets a port, configure `server.port=8080` in a demo profile rather than modifying production config.

## 6. SecurityConfig: CSRF Enabled, CORS Allowlist, Security Headers

File `src/main/java/com/example/securitylab/SecurityConfig.java`:

~~~java
package com.example.securitylab;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/", "/index.html", "/app.js",
                    "/csrf", "/api/public", "/error"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/api/profile", true)
                .permitAll()
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "style-src 'self'; " +
                        "connect-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "form-action 'self'; " +
                        "frame-ancestors 'none'"
                    )
                )
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
            );

        return http.build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-test-password"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-test-password"))
                .roles("USER", "EDITOR")
                .build()
        );
    }
}
~~~

### 6.1 Read Every Configuration Block Carefully

- `cors(Customizer.withDefaults())` enables Spring Security to pick up the `UrlBasedCorsConfigurationSource` bean. CORS must run **before authorization** so preflight requests are not rejected simply for lacking a session cookie.
- `csrf(Customizer.withDefaults())` preserves CSRF protection. `CsrfFilter` checks unsafe requests, including form-login POSTs and business POSTs in a cookie-based setup.
- `GET /csrf` is permitted for anonymous users so the frontend can fetch a token for POST login. The token belongs only to the current session; the response must avoid caching and never be exposed via CORS to untrusted origins.
- `POST /api/notes` requires `ROLE_EDITOR`. Even with a valid CSRF token, a user holding only `ROLE_USER` still gets 403.
- `.formLogin(...permitAll())` provides the generated login page and handles `POST /login` with CSRF; after login succeeds, it redirects to `/api/profile`.
- `anyRequest().denyAll()` is a fail-closed fallback for undeclared routes; production must list additional real routes per policy.
- `cors.setAllowedOrigins` lists **specifically** `http://localhost:5173`, never `"*"`. With `allowCredentials(true)`, never use `*` as an arbitrary wildcard for all origins.
- `allowedMethods` and `allowedHeaders` define which preflights are accepted, **not** endpoint authorization. A browser may pass preflight while the actual POST is blocked by authentication/authorization/CSRF.
- `headers.contentSecurityPolicy(...)` sets an explicit CSP for backend documents: same-origin scripts only; no inline scripts (since `'unsafe-inline'` is absent); no objects, frame ancestors, or external base URLs.
- `referrerPolicy(NO_REFERRER)` minimizes URL data sent in Referer; still never put secrets in URLs.

### 6.2 What Other Default Security Headers Are Sent?

Spring Security Servlet writes several default safe headers, such as `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, cache headers, and `Strict-Transport-Security` **when the request uses HTTPS**. Exact headers still depend on version/config and response handling.

**Important:** CSP **is not enabled by default** for all apps; this lab adds it explicitly. HSTS **should not be expected on HTTP localhost**; production needs proper HTTPS from clients through reverse proxies/apps and a domain-appropriate HSTS policy. Never add `includeSubDomains` or `preload` mechanically: every subdomain must genuinely support HTTPS.

### 6.3 Why Not Enable allowCredentials for Every Origin?

If an app uses session cookies, allowing a malicious origin to read credentialed API responses can expose user data. Rules:

- Never return `Access-Control-Allow-Origin: *` alongside `Access-Control-Allow-Credentials: true`.
- Never reflect arbitrary request `Origin` headers with credentials enabled.
- Do not allowlist the `null` origin unless explicitly needed with dedicated safeguards; `null` origins appear in special browser contexts.
- Match exact hostname, scheme, and port; `localhost:5173` differs from `127.0.0.1:5173` and `https://localhost:5173`.
- For deployments that are both cross-origin and **cross-site**, carefully design `SameSite=None; Secure`, HTTPS, CSRF, and browser third-party-cookie behavior. The demo picks same-site localhost to reduce those variables.

## 7. API Controller for Token Issuance, Profile, and Mutations

File `src/main/java/com/example/securitylab/ApiController.java`:

~~~java
package com.example.securitylab;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    public record CsrfInfo(
            String headerName, String parameterName, String token) {
    }

    public record NoteRequest(String text) {
    }

    @GetMapping("/csrf")
    public ResponseEntity<CsrfInfo> csrf(CsrfToken token) {
        CsrfInfo info = new CsrfInfo(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(info);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @PostMapping("/api/notes")
    public ResponseEntity<Map<String, String>> createNote(
            @RequestBody NoteRequest note) {

        if (note == null ||
                note.text() == null ||
                note.text().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "text-required"));
        }

        // Demo: does not write to a database, no real side effects.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "saved"));
    }
}
~~~

**Security notes:**

- `GET /csrf` exposes `headerName` and `token` for the current request. Calling `getToken()` materializes a deferred token when needed; in Spring Security 6 the returned value may be **XOR-masked**. The client must send back the exact string returned by the server in the matching header.
- The token endpoint neither accepts nor returns credentials and sets `Cache-Control: no-store`; never cache it in CDNs or expose tokens to disallowed origins.
- `GET /api/profile` requires authentication in `SecurityFilterChain`; the method simply reads the `Authentication` supplied by Spring Security.
- `POST /api/notes` requires **both role EDITOR and a valid CSRF token**. The demo controller stores nothing; status 201 merely confirms the request cleared the security chain.
- Production needs validation, owner/tenant checks, request size limits, error handling, and real persistence. **Never** rely on role fields sent by the client in JSON to make authorization decisions.
- A CSRF token **does not replace authentication**. An anonymous user holding a token still cannot call `/api/notes`.

## 8. Backend HTML Document to Observe Real CSP Enforcement

Create `src/main/resources/static/index.html`:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Security Headers Lab</title>
</head>
<body>
  <h1>Backend Page with CSP</h1>
  <p id="loaded">Script has not run yet.</p>
  <p>Inspect Response Headers and Console in DevTools.</p>
  <script src="/app.js" defer></script>
</body>
</html>
~~~

Create `src/main/resources/static/app.js`:

~~~javascript
"use strict";

document.getElementById("loaded").textContent =
  "Same-origin external script ran.";
~~~

Because this HTML is **served from the backend on port 8080**, it receives the `Content-Security-Policy` written by Spring Security on the HTTP response. The same-origin script `/app.js` is permitted to run by `script-src 'self'`.

Do not place an inline `<script> ... </script>` in this file: the configured CSP **disallows inline scripts**, so the browser must block them. To test the policy, we will **inject** an inline script from Playwright and verify it does not execute. Never let a reverse proxy strip the CSP header before reaching production browsers.

**Distinction:** the API returning a CSP header does not mean it governs scripts inside a page **served from port 5173**. Browsers bind CSP to the **document that received the policy**. Thus the lab intentionally uses **two pages**: backend HTML to test CSP, and the port 5173 frontend to test CORS.

## 9. Cross-Origin Frontend on localhost:5173

File `cors-client/index.html`:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CORS + CSRF Lab</title>
</head>
<body>
  <h1>Cross-Origin Frontend</h1>
  <button id="get-token" type="button">Get CSRF token</button>
  <button id="login" type="button">Sign in as editor</button>
  <button id="save" type="button">Save note</button>
  <button id="logout" type="button">Sign out</button>
  <p id="status" role="status">No action yet</p>
  <script src="/client.js" defer></script>
</body>
</html>
~~~

File `cors-client/client.js`:

~~~javascript
"use strict";

const API = "http://localhost:8080";
const statusNode = document.getElementById("status");
let csrfState = null;

function show(text) {
  statusNode.textContent = text;
}

async function request(path, options = {}) {
  return fetch(API + path, {
    ...options,
    credentials: "include",
    cache: "no-store"
  });
}

async function fetchCsrf() {
  const response = await request("/csrf");
  if (!response.ok) {
    throw new Error("Could not fetch CSRF token");
  }

  const data = await response.json();
  if (!data.headerName || !data.token) {
    throw new Error("Invalid CSRF JSON");
  }

  // Keep token in tab memory; never write to URL or localStorage.
  csrfState = data;
  return data;
}

async function loginEditor() {
  const csrf = await fetchCsrf();

  const response = await request("/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body: new URLSearchParams({
      username: "editor",
      password: "editor-test-password"
    })
  });

  // Browser fetch follows formLogin redirects by default.
  // Never infer login success just from a 200 HTML login page.
  const profile = await request("/api/profile", {
    headers: { "Accept": "application/json" }
  });

  const type = profile.headers.get("content-type") || "";
  if (!profile.ok || !type.includes("application/json")) {
    throw new Error("Login did not establish an authenticated session");
  }

  const body = await profile.json();
  if (body.user !== "editor") {
    throw new Error("Unexpected authenticated principal");
  }

  // Login success clears the previous CSRF token per default lifecycle.
  // Always refresh after session/authentication changes.
  await fetchCsrf();
  show("Signed in as editor");
}

async function saveNote() {
  if (!csrfState) {
    await fetchCsrf();
  }

  const result = await request("/api/notes", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      [csrfState.headerName]: csrfState.token
    },
    body: JSON.stringify({ text: "Browser lab" })
  });

  if (result.status !== 201) {
    throw new Error("POST rejected: HTTP " + result.status);
  }

  const body = await result.json();
  if (body.status !== "saved") {
    throw new Error("Unexpected response");
  }
  show("Note saved: 201 Created");
}

async function logout() {
  if (!csrfState) {
    await fetchCsrf();
  }

  await request("/logout", {
    method: "POST",
    headers: { [csrfState.headerName]: csrfState.token }
  });

  csrfState = null;
  await fetchCsrf();
  show("Signed out and fetched new token");
}

function bind(id, action) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await action();
    } catch (error) {
      show("Error: " + error.message);
    }
  });
}

bind("get-token", async () => {
  await fetchCsrf();
  show("CSRF token fetched for current session");
});
bind("login", loginEditor);
bind("save", saveNote);
bind("logout", logout);
~~~

### 9.1 Why Does Every Request Use credentials: include?

The frontend runs on `5173` and the API on `8080`. Because they are **different origins**, `fetch`'s default `credentials: "same-origin"` will not automatically send the session cookie to the backend. With `credentials: "include"`, the browser can attach cookies matching the backend's domain/path/SameSite on cross-origin requests, if cookie policies permit.

On the backend, CORS responses with `Access-Control-Allow-Origin: http://localhost:5173` and `Access-Control-Allow-Credentials: true` tell the browser this origin may read credentialed responses. **Both sides must be configured properly.** If cookies are blocked by SameSite, Secure, or third-party cookie policies, enabling CORS alone will not cause cookies to be sent.

### 9.2 CSRF Header Triggers Preflight

The demo POST sends a custom `X-CSRF-TOKEN` header and `Content-Type: application/json`. These cause the browser to send an **OPTIONS preflight** before the cross-origin POST. The server responds to the preflight with allowed origin/methods/headers; only then does the browser issue the real POST if CORS checks pass.

**Critical point:** an allowed preflight **does not** mean the user is logged in, holds role EDITOR, or has a valid CSRF token. Preflight checks *whether this kind of cross-origin request may be sent*; the actual POST still passes through `CsrfFilter` and authorization.

### 9.3 Demo JavaScript Is Not a Secret Store

`editor-test-password` in the frontend is **strictly for the local lab**. Never embed real passwords in production JavaScript; users must enter credentials through a secure login flow or appropriate SSO/OIDC. In deployed apps, all user data must be protected against XSS and stored safely. Keeping the CSRF token in memory limits persistence, yet **same-origin XSS can still read the token**: CSP, output encoding, and XSS defenses remain mandatory.

## 10. Running the App in Two Terminals

From `security-browser-lab`, terminal 1 runs the backend:

~~~bash
mvn spring-boot:run
~~~

Once started, check in a browser:

~~~text
http://localhost:8080/
http://localhost:8080/api/public
http://localhost:8080/csrf
~~~

Terminal 2 starts the static frontend server; with Python 3:

~~~bash
python3 -m http.server 5173 --directory cors-client
~~~

On Windows, if `python3` does not exist, try:

~~~powershell
py -m http.server 5173 --directory cors-client
~~~

Open:

~~~text
http://localhost:5173/
~~~

**Do not open `file:///.../cors-client/index.html` to test CORS.** `file:` pages can have an opaque/`null` origin that does not match the configured `http://localhost:5173`. Always serve over an actual HTTP server so the browser sees the right origin.

### 10.1 Manual Walkthrough

1. Open `http://localhost:5173/` in Chromium; open DevTools → Network.
2. Click **Get CSRF token**; inspect `GET http://localhost:8080/csrf` and its JSON response. Avoid pasting raw tokens/cookies into tickets.
3. Click **Sign in as editor**; observe an OPTIONS preflight if sent by the browser, POST `/login`, and the redirect/profile check. The `localhost` session cookie may rotate after login (session fixation protection).
4. Click **Save note**; POST `/api/notes` must return **201 Created** and `{"status":"saved"}`.
5. Try omitting the CSRF header via DevTools JavaScript (Section 12): POST will return 403.
6. Try sending the pre-login token after login: rejected per the default lifecycle.
7. Open `http://localhost:8080/` and inspect security response headers; try injecting an inline script via Playwright to observe CSP enforcement.
8. Sign out on the frontend, then retry with the new token/session; POST requests requiring EDITOR must continue to be blocked when anonymous.

Never treat "Network shows OPTIONS 200" as proof the test passed. Always inspect the **actual POST** and its final status.

## 11. HTTP CORS Preflight: Exact Expectations

A sample preflight sent by the browser for a JSON POST carrying a CSRF header:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

The semantically important response headers:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin
~~~

**This is an illustrative response**, not a guarantee of exact ordering, casing, or that every Spring Boot/Servlet version emits identical headers. `Vary` may also list `Access-Control-Request-Method` and `Access-Control-Request-Headers`. What matters in testing is **the allowed origin, credentials flag, methods, and headers** matching the request.

For disallowed origins, no `Access-Control-Allow-Origin` header permitting that origin may be returned. Spring's `CorsFilter` can return 403 for invalid CORS requests; the browser may log a **CORS error** and JavaScript receives a rejected Promise/TypeError instead of reading the blocked status/body.

### 11.1 CORS Does Not Stop curl from Sending Requests

Command-line tools can issue requests even when browsers block foreign-origin JavaScript from reading responses. For example:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Command-line HTTP clients **do not enforce browser same-origin policy**. Thus CORS **is not a firewall**, not an authorization mechanism, and does not protect APIs from attackers sending HTTP directly. Sensitive endpoints still need authentication, authorization, and CSRF aligned with the threat model.

### 11.2 Never Use CORS to "Fix" 401/403 Errors

If browser Network shows a 403 POST carrying valid CORS allow-origin headers, the request likely passed CORS and was rejected by CSRF or authorization. Never set `allowedOrigins("*")` just to make 403s disappear. Check instead:

- Did the browser attach the session cookie?
- Is the CSRF token in the right header and still tied to the current session?
- Does the user hold the EDITOR role?
- Did the real request get 401/302 to login and hit a browser redirect/CORS failure?
- Is the frontend using the right scheme/hostname/port without mixing `localhost` and `127.0.0.1`?

## 12. Triggering CSRF and Role Failures from Browser DevTools

After signing in as editor and receiving a fresh token, run this snippet **without the CSRF header** in the Console on `http://localhost:5173`:

~~~javascript
const missingCsrf = await fetch(
  "http://localhost:8080/api/notes",
  {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: "missing token" })
  }
);
console.log(missingCsrf.status);
~~~

With an active session, allowed CORS origin, and JSON POST body, expect status **403** due to the missing token. The Console may also show an OPTIONS preflight; the OPTIONS request can succeed while the subsequent POST still gets 403.

To test an **invalid token**:

~~~javascript
const invalidCsrf = await fetch(
  "http://localhost:8080/api/notes",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": "deliberately-invalid-token"
    },
    body: JSON.stringify({ text: "bad token" })
  }
);
console.log(invalidCsrf.status);
~~~

Expect 403. This snippet **does not disable CSRF** and never steals anyone else's secret token. Run tests only against your own controlled local demo.

### 12.1 USER Role with Valid CSRF Is Still Denied

You can sign in with user `reader` and `reader-test-password` in an isolated session (e.g., a fresh browser context or after signing out). When POST `/api/notes` carries a valid token, `CsrfFilter` allows it through, yet `hasRole("EDITOR")` still returns 403.

Looking at status 403 alone cannot distinguish the two causes. To prove **authorization**, always include a **valid CSRF token** in the test. To prove **CSRF**, use a principal that holds **EDITOR**. The isolated tests below are structured exactly this way.

### 12.2 Stale Token After Login

Fetch a token before login from `GET /csrf`, complete login, then try sending that **old token** to `POST /api/notes` under the new session. In default Spring Security form login, the old CSRF token is cleared on authentication success, so the POST with the old token gets 403. Fetching a new token after login and retrying succeeds.

Do not assume every GET mints a brand-new raw token: Spring Security 6 may **XOR-mask** the emitted token, making the string look different across GETs while the underlying expected token stays the same. Failure after login is caused by the **authentication/lifecycle transition**, not merely because two tabs show different masked strings.

## 13. Testing the Backend with MockMvc: CSRF, CORS, Headers, Roles

The first test suite runs Spring Security's filter chain inside the Spring Boot context **without a browser**. This is ideal for isolating backend behavior before running Playwright.

File `src/test/java/com/example/securitylab/HttpSecurityIntegrationTest.java`:

~~~java
package com.example.securitylab;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanFetchCsrfAndItMustNotBeCached()
            throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty())
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithValidCsrfCreatesNote() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("saved"));
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerIsDeniedEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginPreflightReturnsCredentialHeaders()
            throws Exception {
        mvc.perform(options("/api/notes")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void deniedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header("Origin", "http://127.0.0.1:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void appDocumentHasCspAndDefaultSecurityHeaders()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                    "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                    "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                    "Content-Security-Policy",
                    org.hamcrest.Matchers.containsString(
                        "script-src 'self'")));
    }

    @Test
    void publicApiWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }
}
~~~

**Why use `@WithMockUser` in these tests?** Here we want to isolate **CSRF vs. authorization**, not test real password login. The reader test with valid CSRF still gets 403 due to the missing role; the editor test without CSRF gets 403 despite the right role. Those are independent, more precise checks than an unclassified "POST returns 403" test.

### 13.1 Limitations to Document in Test Reports

- `@WithMockUser` places a mock Authentication in TestContext. It **does not verify passwords** or browser cookies.
- Spring Security Test's `csrf()` synthesizes a valid token in the test request. It **does not test** whether the browser fetched the token via GET, refreshed it after login, or sent `credentials: "include"`.
- MockMvc runs Spring MVC + security filters in-process, **without reproducing real browser CORS/CSP enforcement**.
- Testing the CSP header only proves **the server emitted the policy string**, not that a browser blocks inline scripts. The Playwright suite below supplies that proof.
- On HTTP MockMvc, never assert HSTS is always present because Spring Security sends HSTS only on appropriate HTTPS requests. That expectation must be tested on an HTTPS deployment.
- Test outcomes depend on Boot/Security versions and active context. Never use a `permitAll` test profile or `@AutoConfigureMockMvc(addFilters=false)` as a "fix" in a security practice lab.

Run:

~~~bash
mvn test
~~~

With the demo code intact, the nine tests in `HttpSecurityIntegrationTest` behave as written. There is no fixed Maven stdout; if any test fails, investigate each cause rather than editing code to always return 200.

## 14. Browser Testing with Playwright

### 14.1 Installing Playwright

From `browser-tests` (a separate directory alongside `pom.xml`):

~~~bash
npm init -y
npm install --save-dev @playwright/test
npx playwright install chromium
~~~

**Before running Playwright**, keep both server terminals running:

~~~text
backend  http://localhost:8080
frontend http://localhost:5173
~~~

On Windows/CI, install Chromium OS dependencies per Playwright's platform instructions. Browser automation uses **real Chromium**, not Playwright's Node HTTP `APIRequestContext`, so real CORS and CSP enforcement are exercised.

### 14.2 Test File security.spec.js

Create `browser-tests/tests/security.spec.js`:

~~~javascript
import { test, expect } from "@playwright/test";

const FRONTEND = "http://localhost:5173";
const BACKEND = "http://localhost:8080";

test("frontend is allowed by CORS and gets valid CSRF",
    async ({ page }) => {

  await page.goto(FRONTEND);

  await page.getByRole("button", { name: "Get CSRF token" })
    .click();

  await expect(page.locator("#status"))
    .toHaveText("CSRF token fetched for current session");

  // Fetch runs in browser origin 5173 (not Node HTTP).
  const body = await page.evaluate(async () => {
    const response = await fetch(
      "http://localhost:8080/api/public",
      { credentials: "include" }
    );
    return response.json();
  });

  expect(body.message).toBe("public");
});

test("after login, stale token is rejected while fresh token succeeds",
    async ({ page }) => {

  await page.goto(FRONTEND);

  const oldCsrf = await page.evaluate(async () => {
    const res = await fetch("http://localhost:8080/csrf", {
      credentials: "include",
      cache: "no-store"
    });
    return res.json();
  });

  await page.getByRole("button", { name: "Sign in as editor" })
    .click();
  await expect(page.locator("#status"))
    .toHaveText("Signed in as editor");

  // Form login changes authentication and CSRF lifecycle.
  const oldStatus = await page.evaluate(async old => {
    const res = await fetch(
      "http://localhost:8080/api/notes",
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          [old.headerName]: old.token
        },
        body: JSON.stringify({ text: "stale token" })
      }
    );
    return res.status;
  }, oldCsrf);

  expect(oldStatus).toBe(403);

  // Frontend automatically fetched a fresh token after login.
  await page.getByRole("button", { name: "Save note" })
    .click();
  await expect(page.locator("#status"))
    .toHaveText("Note saved: 201 Created");

  // Has EDITOR role, yet missing CSRF is still denied.
  const missingStatus = await page.evaluate(async () => {
    const res = await fetch(
      "http://localhost:8080/api/notes",
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "without csrf" })
      }
    );
    return res.status;
  });

  expect(missingStatus).toBe(403);
});

test("origin outside allowlist is blocked from reading CORS response",
    async ({ page }) => {

  // Python http.server binds both localhost and 127.0.0.1 by default.
  await page.goto("http://127.0.0.1:5173/");

  const blocked = await page.evaluate(async () => {
    try {
      await fetch("http://localhost:8080/api/public", {
        mode: "cors",
        credentials: "include"
      });
      return false;
    } catch {
      return true;
    }
  });

  expect(blocked).toBe(true);
});

test("backend CSP allows external script but blocks inline script",
    async ({ page }) => {

  await page.goto(BACKEND + "/");

  await expect(page.locator("#loaded"))
    .toHaveText("Same-origin external script ran.");

  const inlineExecuted = await page.evaluate(() => {
    window.__labInlineExecuted = false;

    const script = document.createElement("script");
    script.textContent = "window.__labInlineExecuted = true";
    document.body.appendChild(script);

    return window.__labInlineExecuted;
  });

  expect(inlineExecuted).toBe(false);

  const headers = await page.evaluate(async () => {
    // Server header inspection was also verified via MockMvc.
    return document.location.origin;
  });
  expect(headers).toBe(BACKEND);
});
~~~

These tests execute **JavaScript inside the browser context** via `page.evaluate`. When testing a disallowed CORS origin, the browser must prevent scripts from reading the response and may log a CORS error to the Console. Do not expect JavaScript to catch an HTTP 403 status from a disallowed CORS response: browser policy rejects `fetch` with a network-style error.

**On stale tokens after login:** the test grabs a token from the anonymous session **before** login; after login, the default authentication strategy invalidates the old token. That tests a common post-login UX pitfall. If you customize the CSRF repository/handler or authentication filter in a real project, align the test scenario with the actual lifecycle and verify the cause instead of guessing.

### 14.3 Running Browser Tests

Inside `browser-tests`:

~~~bash
npx playwright test tests/security.spec.js
~~~

To watch the real browser run:

~~~bash
npx playwright test tests/security.spec.js --headed
~~~

To debug a failing test:

~~~bash
npx playwright test tests/security.spec.js --debug
~~~

By default, Playwright runs tests in **isolated browser contexts** in parallel. That helps isolation because each test gets separate cookies/CSRF state; however, if a real app uses a shared database/user state, design fixtures to avoid contention.

**Never fabricate results:** test outputs, durations, and pass/fail counts can only be reported after actually running the project and Playwright in an environment with Java, Node, browsers, ports, and dependencies ready. These files are **lab templates**, not recorded execution logs.

## 15. Extra Observations in DevTools to Pinpoint Root Causes

While running browser tests or manual checks, open Chromium DevTools → **Network**, filter by `Fetch/XHR`, and inspect:

### For GET /csrf

- Request origin `http://localhost:5173`.
- Response `Access-Control-Allow-Origin: http://localhost:5173` and `Access-Control-Allow-Credentials: true` when the Origin header is present.
- Response JSON containing the header name and token for the current session.
- `Cache-Control` preventing token caching.
- If a session cookie is set: inspect Path, Domain, SameSite, and Secure, while **never copying raw values** into reports.

### For OPTIONS /api/notes

- `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` generated automatically by the browser.
- Response permitting matching origin/method/headers.
- OPTIONS does not need a CSRF token like a business POST; it is a CORS probe, not a state-changing action.

### For POST /api/notes

- Matching credentials/session cookie attached.
- CSRF header carrying the value from the **current session**, not the pre-login token.
- 201 response with EDITOR + valid CSRF; 403 if token or role is missing.
- Never log raw tokens/cookies in CI, tickets, or public screenshots.

### For GET / (backend HTML)

- `Content-Security-Policy` containing `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY`.
- `Referrer-Policy: no-referrer`.
- External script `/app.js` loads and executes.
- Inline script injected by Playwright is blocked; the browser Console may log a CSP violation.
- HTTP localhost lacks the HSTS header seen over valid HTTPS. That is not proof HSTS is disabled in production.

## 16. Security Headers: What This Lab Proves and Does Not Prove

### 16.1 A Proper CSP Does Not Solve All XSS

A strict `script-src` CSP blocks many script injection vectors, yet does not replace:

- Context-aware output encoding for HTML/attribute/URL/JavaScript contexts.
- Avoiding `innerHTML` with untrusted data.
- Proper sanitization for rich HTML.
- Server-side validation and authorization.
- Subresource Integrity (SRI) for third-party scripts and supply-chain review.
- Nonce/hash policies when safe inline bootstrap scripts are needed; never enable `unsafe-inline` just to "make the site work".

CSP can first be rolled out with `Content-Security-Policy-Report-Only` to measure violations during migration, though **Report-Only does not block** like an enforcing header. This lab uses the enforcing header so the browser test proves inline scripts are stopped.

### 16.2 API Response Headers Do Not Protect a Cross-Origin Frontend Document

Suppose the backend returns CSP on `GET /api/public`, while frontend HTML is served by the Python server on 5173. The JSON response's CSP **does not govern** which scripts execute inside the 5173 document. If a real frontend is hosted on a CDN/reverse proxy, that CDN/proxy/frontend server must emit the CSP for the **HTML document** itself.

That is why Playwright tests CSP on `http://localhost:8080/` rather than the 5173 frontend. Mixing those up is a common mistake when deploying separated backends and SPAs.

### 16.3 X-Frame-Options and frame-ancestors

Spring Security defaults to emitting `X-Frame-Options: DENY`, preventing compliant browsers from framing the page. CSP `frame-ancestors 'none'` is the modern document-level equivalent with greater flexibility.

When framing is genuinely needed between enterprise-managed origins, define an explicit allowlist and test browsers on the actual deployment domains. Never strip all frame protections just to get a temporary embed working.

### 16.4 X-Content-Type-Options, Cache, Referrer

- `X-Content-Type-Options: nosniff` helps when browsers classify resources; always return accurate Content-Types for JS/CSS/JSON.
- Spring Security cache headers prevent caching certain sensitive responses, yet **cannot** replace proper CDN/API cache design. The demo `/csrf` endpoint sets `no-store` explicitly.
- `Referrer-Policy: no-referrer` curtails URL leakage via Referer; if analytics require referrers, pick an appropriate policy while still keeping credentials/tokens out of URLs.
- Headers like `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy`, and `Cross-Origin-Resource-Policy` are useful for stricter browser isolation models, but **do not enable them blindly**: COEP/CORP can break legitimate cross-origin resource loads. This lab omits them instead of bundling an unanalyzed preset.

### 16.5 HSTS Must Only Be Tested Over Real HTTPS

`Strict-Transport-Security` is emitted by Spring Security when the request is recognized as HTTPS per proper configuration. On HTTP localhost, never fail an audit simply because the HSTS header is absent.

In production, verify:
1. Clients reach the production hostname over real **HTTPS**.
2. Responses include HSTS with an appropriate `max-age`, without confusing HTTP vs. HTTPS.
3. Reverse proxies/ingress forward the true scheme without trusting arbitrary client `X-Forwarded-Proto` headers.
4. HTTPS certificates and redirects are valid with zero mixed content.
5. Only enable `includeSubDomains`/preload after auditing all subdomains and rollback plans.

**Never enable HSTS preload on localhost or demo domains**; preloading has long-lasting effects on real domains.

## 17. Cookies, SameSite, and CSRF in the Two-Port Model

A `fetch("http://localhost:8080/api/notes", {credentials:"include"})` from `http://localhost:5173` is **cross-origin**, yet both URLs share the same scheme and hostname, making them **same-site**. A session cookie with `SameSite=Lax` can be sent on same-site requests if Path/Domain and other policies match.

Why didn't the lab use `https://evil.example` as the demo frontend? The goal is to isolate **CORS origin checks** first without mixing in cross-site cookie restrictions. If a real frontend runs on a different registrable domain:

- Browsers may withhold cookies under `SameSite=Lax/Strict`.
- `SameSite=None; Secure` is typically required for cross-site cookies, alongside HTTPS.
- Browser privacy controls may still block third-party cookies even with valid server CORS headers.
- CSRF protection remains necessary whenever browsers can attach cookies in cross-site scenarios.
- CORS `allowCredentials` does not override SameSite or third-party cookie policies.
- Refresh, logout, CSRF tokens, and CSRF handlers must fit the credential model.

**Rule:** CORS, Cookie SameSite, and CSRF guard different boundaries. Never assume a single setting covers all three.

## 18. When Are 401, 302, 403, and 201 Expected?

| Scenario | Under Demo Config | How to Read It |
| --- | --- | --- |
| GET public, anonymous | 200 | No authentication required. |
| GET profile, anonymous | Usually 302 to login page due to formLogin. | Authentication entry point behavior, not a CORS decision. |
| POST notes, editor, valid CSRF | 201 | Authentication/authorization/CSRF all passed; controller ran. |
| POST notes, editor, missing CSRF | 403 | CsrfFilter blocked the request. |
| POST notes, editor, invalid CSRF token | 403 | Invalid token, not a role failure. |
| POST notes, reader, valid CSRF | 403 | Missing `ROLE_EDITOR`. |
| OPTIONS from allowed 5173 origin | 200 or configured preflight success. | CORS permits this cross-origin request shape; does not grant user permissions. |
| OPTIONS from 127.0.0.1:5173 | Rejected by CorsFilter; browser blocks JS from reading response. | Origin is not in the allowlist. |
| CSP blocks inline script | Script does not execute; browser logs violation. | Proves browser enforcement on backend HTML. |

**You cannot diagnose the root cause from a status code alone.** Inspect the HTTP method, Origin, cookies, CSRF header, principal, authorities, filter chain, and logs in an appropriate dev/test environment.

## 19. Common Mistakes in the Lab

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| GET /csrf returns 200 but POST returns 403 | Token omitted, stale after login, or session cookie missing. | Fetch a fresh token after login; verify headerName, credentials, and cookies. |
| OPTIONS 200 yet POST 403 | CORS passed preflight, but CSRF or role failed. | Inspect the real POST; separate CSRF tests from role tests. |
| Frontend hits `TypeError: Failed to fetch` | Blocked by browser CORS, server down, HTTP/HTTPS mismatch, cookie/privacy policy, or network error. | Inspect DevTools Network/Console, Origin, and Response Headers rather than guessing from TypeError. |
| Origin 127.0.0.1 rejected | Allowlist contains only localhost. | Keep the two hostnames distinct as a negative test; allowlist real production origins. |
| CORS fails with allowCredentials=true and "*" | Wildcard is invalid for credentialed CORS or rejected by the framework. | Specify exact `allowedOrigins`. |
| Cookie not sent despite valid ACAO | `fetch` lacks credentials include; SameSite/Secure/Path/Domain or third-party policy. | Check cookie and site/origin settings before loosening CORS. |
| POST login redirects yet frontend says not logged in | Wrong credentials, failure redirect to HTML, session cookie not stored, or bad CSRF. | GET /api/profile after login and verify JSON principal; don't trust a 200 redirect alone. |
| Editor POST without CSRF gets 403 | CSRF protection is working properly. | Fetch token and send the right header; never disable CsrfFilter. |
| Reader POST with valid CSRF gets 403 | Server requires ROLE_EDITOR. | That is authorization; never grant roles carelessly or switch to permitAll. |
| CSP stops inline script in HTML | Policy intentionally omits unsafe-inline. | Move JS to external scripts, or consider nonces/hashes if inline is truly needed. |
| CSP test on 5173 frontend sees no block | Port 5173 HTML comes from Python server and **lacks backend CSP**. | Test the backend HTML document or configure CSP on the frontend server. |
| Playwright fails while MockMvc passes | Real browser CORS/CSP/cookie behavior differs from mock HTTP. | Distinguish server header tests from browser enforcement; inspect traces/Console. |
| HSTS absent on localhost HTTP | HSTS applies to HTTPS and is normally emitted only on secure requests. | Test on HTTPS deployment; don't fake HSTS conclusions over HTTP. |
| Browser test times out | Backend/frontend not running or port busy. | Check ports 8080/5173, test origins, and server logs. |
| CORS preflight disappears on second call | Browser may cache preflight per `Access-Control-Max-Age`. | Clear cache / use fresh context, alter request, or inspect Network appropriately. |
| Frontend works locally but breaks in prod | Hardcoded credentials, different session/cookie topology, different CSP/proxy. | Design production auth, TLS, secrets, allowed origins, and browser policies properly. |

## 20. Lab Acceptance Checklist

Check off each item **only after verifying** via tests/Network:

- [ ] Backend runs on `localhost:8080`, frontend on `localhost:5173` via HTTP server.
- [ ] CORS allowlist avoids credentialed wildcards; 5173 is permitted and 127.0.0.1:5173 is blocked.
- [ ] OPTIONS preflight returns expected `Access-Control-Allow-*` headers; actual POSTs still go through authorization/CSRF.
- [ ] `GET /csrf` returns the current session's token with `Cache-Control: no-store`.
- [ ] Editor login succeeds via the form login filter and the browser retains the right session cookie.
- [ ] Pre-login token is rejected after authentication change; the fresh token succeeds on POST.
- [ ] Editor POST with missing/invalid CSRF returns 403.
- [ ] User lacking EDITOR role with valid CSRF still gets 403.
- [ ] Editor with valid CSRF succeeds on POST and receives 201/expected JSON.
- [ ] GET backend HTML carries proper CSP, same-origin external script runs, and inline scripts are blocked in the browser.
- [ ] Backend responses include `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy` as configured.
- [ ] HSTS is not reported as failing merely on local HTTP; a separate HTTPS deployment check is planned.
- [ ] `@WithMockUser` is never used to claim browser cookie/session/login lifecycle behavior.
- [ ] CORS is not treated as authorization; every sensitive endpoint keeps server-side permission checks.
- [ ] Hardcoded demo credentials and raw CSRF tokens/cookies are never used or logged in production.
- [ ] When sharing DevTools/CI traces, cookies, Authorization headers, CSRF tokens, and PII are masked/filtered.

## 21. Self-Check Questions

**Q1.** A browser sends OPTIONS `/api/notes` and gets 200. Can an unauthenticated user send a valid POST?

**A:** An allowed preflight only shows origin/method/headers satisfy CORS. The actual POST still requires authentication, role EDITOR, and a valid CSRF token. OPTIONS 200 **grants zero permissions**.

**Q2.** Does a CORS error mean an attacker cannot call the endpoint with curl?

**A:** No. CORS is a JavaScript/browser policy. Server-to-server and command-line clients are not governed by browser same-origin policy; the backend must enforce its own authorization.

**Q3.** Why does the 5173 frontend calling the 8080 API need CORS when both are on localhost?

**A:** An origin consists of **scheme + hostname + port**. Different ports mean different origins. Two addresses can be same-site while still being cross-origin.

**Q4.** After login, the pre-login token gets 403 while a fresh token succeeds. Should we disable CSRF for POST login?

**A:** No. Spring Security can clear/rotate the token on authentication success; the frontend should fetch a fresh token for the new session. Login CSRF is an important defense in cookie/session architectures.

**Q5.** Does a JSON API's CSP header automatically protect a React/HTML page served from a cross-origin CDN?

**A:** No. Browsers enforce CSP on the **document** that received the CSP header. The CDN/frontend server must emit the policy for the frontend document if you want CSP enforced there.

**Q6.** Why doesn't Spring Security send HSTS on `http://localhost:8080`?

**A:** HSTS must be learned by browsers over valid HTTPS; an HTTP demo cannot prove an HSTS deployment. Test directly against the production HTTPS endpoint.

**Q7.** Does a `@WithMockUser` test with `.with(csrf())` returning 201 prove browsers send cookies and tokens properly?

**A:** No. That tests server rules with test-supplied Authentication/tokens. Playwright/browser flows are needed to verify CORS, cookies, login rotation, and real fetch requests.

## 22. Summary

This lab connects **three browser defense layers** with server-side authorization:

~~~text
Frontend page 5173
  -> browser checks origin + CORS preflight
  -> fetch with credentials include (matching cookie)
  -> request reaches backend 8080
       -> CorsFilter: valid origin/method/headers?
       -> CsrfFilter: token matches current session?
       -> Authentication/Authorization: user has ROLE_EDITOR?
       -> Controller: executes action and returns response
  <- browser receives response with CORS headers
  <- browser decides whether frontend JS may read response

Backend HTML page 8080
  <- backend sends security headers (CSP, nosniff, frame, referrer...)
  -> browser enforces CSP on that exact document
~~~

**CSRF protects against forged actions under auto-sent credentials; CORS governs cross-origin JavaScript access to responses; security headers mitigate specific browser-side attack classes.** They are effective only when combined with authentication, authorization, proper cookie/session policies, and production HTTPS.

**Closing rule:** *Security testing must cover both allowed and denied cases, and both backend assertions and browser enforcement. Never "fix" a lab by disabling CSRF, opening CORS to every origin, or stripping CSP just to make tests pass.*

## References

- Spring Security Reference — Servlet CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security Reference — Servlet CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security Reference — Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security Reference — Spring MVC MockMvc testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security Reference — MockMvc CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- MDN — SameSite cookie attribute: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
- Playwright Test — Getting Started: https://playwright.dev/docs/intro
