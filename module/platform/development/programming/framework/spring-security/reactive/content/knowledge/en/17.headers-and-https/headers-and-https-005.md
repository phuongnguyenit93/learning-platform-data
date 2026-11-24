# Content-Security-Policy, Nonces, and XSS Protection Limits

## 1. Context and Objectives

Within the **Headers and HTTPS** section of **Spring Security reactive / WebFlux**, Content-Security-Policy (**CSP**) is a key response header for reducing the risk of **Cross-Site Scripting (XSS)**. CSP tells the browser which sources of scripts, styles, images, iframes, API connections, etc. are permitted inside an HTML document. One strong CSP style uses a **nonce**—a fresh random value per response—to allow specific trusted scripts to run without opening `'unsafe-inline'`.

However, **CSP does not fix all XSS**. Applications must still escape data when building HTML, use safe DOM APIs, sanitize rich HTML when required, protect sessions, and authenticate users. If a valid nonce-bearing script itself uses `innerHTML` with untrusted data, it can still become an XSS gadget.

Lesson objectives:

1. Understand that CSP is a **browser-enforced** policy, not a server-side HTML sanitizer or authentication mechanism.
2. Read `Content-Security-Policy` and distinguish it from `Content-Security-Policy-Report-Only`.
3. Properly use `default-src`, `script-src`, `script-src-attr`, `style-src`, `connect-src`, `object-src`, `base-uri`, `form-action`, and `frame-ancestors`.
4. Explain what a nonce is, why at least 128 bits of entropy from `SecureRandom` is needed, why it must be regenerated **on every HTML response**, and why header and HTML must match.
5. Configure **static** CSP using the `ServerHttpSecurity.headers().contentSecurityPolicy(...)` DSL; distinguish it from **dynamic CSP with a nonce**.
6. Run a **Java 17+, Spring Boot 3.3.5, Spring Security reactive** example with dynamic HTML and a trusted script carrying a nonce.
7. Test with `WebTestClient`: random nonces across responses, HTML nonce matching the header, user data escaped, response uncached, and authentication remaining separate.
8. Understand protection limits against XSS, how `'strict-dynamic'` works, Trusted Types, caching/CDNs, reverse proxies, CSP reports, and HTTPS.
9. Have a security review checklist and troubleshooting steps when the browser blocks legitimate scripts.

**Scope:** CSP response headers and HTML in a WebFlux application. Static/SSR SPAs, CDNs, template engines, or systems with multiple security chains may require different implementations, yet the nonce/CSP principles remain the same.

## 2. Recap: XSS and Primary Defenses

### 2.1. XSS Starts by Mistaking Data for Code

The following Java snippet is **unsafe** if `name` comes from a user:

```java
// ANTI-PATTERN: solely for illustrating an injection flaw.
String html = "<p>Hello " + name + "</p>";
```

If `name` contains:

```html
<img src=x onerror="alert('XSS demo')">
```

the browser may interpret it as real HTML, and the inline `onerror` event handler can execute JavaScript. This is an educational payload for recognizing the risk, not to be used on systems without authorization to test.

In an HTML **text context**, encode before inserting data:

```java
String escaped = HtmlUtils.htmlEscape(name);
String html = "<p>Hello " + escaped + "</p>";
```

`HtmlUtils` belongs to `org.springframework.web.util`. When data contains `<`, `>`, and special characters, the output uses HTML entities so the browser displays **plain text**. However, escaping rules also depend on context: HTML attributes, URLs, CSS, and JavaScript strings require context-appropriate encoding; **never reuse a single HTML escaping function for every context**.

### 2.2. CSP Adds an Execution-Restriction Layer

If another rendering point still lets `<script>` or `onclick` slip through, a strict CSP can stop the browser from executing content outside the allowed set. This is **defense-in-depth**.

Defense has multiple layers:

```text
Untrusted data
        |
        v
Business-appropriate input validation
        |
        v
Template / DOM-safe API / context-aware output encoding
        |
        v
HTML response + CSP response header
        |
        v
Browser checks permitted sources and behaviors
        |
        v
User interface
```

Never skip output encoding on the excuse that "we already have CSP." CSP is not a filter that cleans HTML source on the server and does not guarantee every browser/WebView enforces identically.

## 3. What Is the CSP Response Header?

CSP is delivered primarily via an HTTP response header:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'none'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
```

A policy consists of **directives**, separated by `;`:

- `'self'`: sources matching the document's own origin in CSP semantics.
- `'none'`: allows no sources in that source list.
- `https://cdn.example.test`: a specific host source, written without quotes around the URL.
- `'nonce-abc...'`: permits script/style elements bearing the matching `nonce` attribute.
- `'sha256-...'`: permits inline script/style content matching the hash.
- `'strict-dynamic'`: a trust-delegation mechanism for scripts permitted by nonce/hash, requiring careful evaluation.

### Key Directives Table

| Directive | Behavior | Guidance |
| --- | --- | --- |
| `default-src` | Fallback for many resource fetch directives | Start with `'none'` and open only what is needed |
| `script-src` | Script execution and certain JS behaviors | Prefer nonce/hash; minimize unsafe-inline/eval |
| `script-src-elem` | Sources for script elements | Customize when needing to distinguish `<script>` sources |
| `script-src-attr` | Inline event-handler attributes | `'none'` explicitly blocks `onclick`, `onerror` |
| `style-src` | CSS sources and inline styles per policy | Allow legitimate stylesheets; nonce/hash if needed |
| `img-src` | Image sources | Allow only exact required origins/data schemes |
| `font-src` | Web fonts | Restrict to application CDNs/hosts |
| `connect-src` | Fetch/XHR/WebSocket/EventSource, etc. | Only the API/WSS endpoints actually needed |
| `object-src` | Object/embed plugins | Usually `'none'` |
| `base-uri` | `<base>` changing the base URL | Usually `'none'` |
| `form-action` | HTML form submission targets | Only required origins, e.g., `'self'` |
| `frame-ancestors` | Who may embed this document | `'none'` to forbid embedding |
| `frame-src` | Iframes this document may embed | Opposite direction of `frame-ancestors` |
| `upgrade-insecure-requests` | Asks browser to upgrade HTTP subresources to HTTPS | Only when backend/site is fully HTTPS-ready |
| `report-uri` / `report-to` | Sends CSP violation reports | Needs endpoint, privacy controls, and rate limiting |

**Important note:** `base-uri`, `form-action`, and `frame-ancestors` **do not fall back to `default-src`**. A "`default-src 'none'`" policy alone does not define these boundaries.

### `'unsafe-inline'` and `'unsafe-eval'`

`'unsafe-inline'` can permit inline scripts and event handlers far more broadly than intended; `'unsafe-eval'` enables eval-like behaviors. Do not add them simply to keep a legacy frontend running. Convert inline event handlers to `addEventListener` inside a trusted script, move JavaScript into external files, or give controlled scripts a nonce/hash.

When browsers support nonce/hash in `script-src`, combining them with `'unsafe-inline'` has specific compatibility behavior; do not rely on mixed fallbacks without understanding your target browsers' CSP behavior.

## 4. Enforce vs. Report-Only

### Enforcing CSP

```http
Content-Security-Policy: default-src 'none'; script-src 'self'; object-src 'none'
```

The browser enforces the policy, blocks content violating supported directives, and can log violations in DevTools.

### Report-Only CSP

```http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'
```

This policy is for **observation** only and does not block content solely due to report-only violations. To receive reports on a server, configure the corresponding report endpoint and a policy for handling data sent there.

### Phased Rollout

1. Inventory HTML documents, inline scripts, stylesheets, CDNs, analytics, API connections, WebSockets, and iframes.
2. Build a candidate policy with explicit sources, avoiding `*` or `'unsafe-inline'`.
3. Use Report-Only to discover affected pages/features; control report volume and privacy.
4. Update frontend code, add nonces/hashes to app-controlled scripts, and remove inline event handlers/eval.
5. Enforce the tested policy across target browsers.
6. Maintain monitoring and regression tests when changing libraries or frontend build pipelines.
7. If adding a second CSP at a gateway, **check the intersection effect** with the existing policy.

Multiple enforced CSP headers must typically be satisfied **simultaneously**. They do not form an OR allowlist. If Spring Security applies a static `script-src 'self'` CSP and a controller adds a nonce CSP, inline scripts with the nonce may still be blocked by the static policy.

## 5. Static CSP in Spring Security Reactive

Per Spring Security documentation, the framework **does not add CSP by default**, because CSP must reflect each application's specific needs. Example **static** WebFlux configuration:

```java
// FRAGMENT inside a @Bean SecurityWebFilterChain.
return http
        .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated())
        .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                        .policyDirectives(
                                "default-src 'none'; "
                              + "script-src 'self'; "
                              + "style-src 'self'; "
                              + "img-src 'self'; "
                              + "connect-src 'self'; "
                              + "object-src 'none'; "
                              + "base-uri 'none'; "
                              + "frame-ancestors 'none'")))
        .build();
```

In a complete configuration, `http` is `ServerHttpSecurity` and the bean returns `SecurityWebFilterChain`. This is the **reactive** API, not Servlet's `HttpSecurity` / `SecurityFilterChain`.

For **Report-Only**:

```java
// ALTERNATIVE FRAGMENT; do not stack on top of the dynamic demo policy.
.headers(headers -> headers
        .contentSecurityPolicy(policy -> policy
                .policyDirectives(
                        "default-src 'none'; "
                      + "script-src 'self'; "
                      + "object-src 'none'; "
                      + "base-uri 'none'")
                .reportOnly()))
```

Both fragments represent standalone options. If an app uses no inline scripts, a static CSP may fit well. However, **a nonce must change on every response**; a static `policyDirectives(...)` evaluated once when building the filter chain cannot supply a per-response nonce matching dynamically rendered HTML.

**The full runnable example below will not enable a static CSP writer**, because the controller generates dynamic CSP nonces on `/page` responses. Never combine both snippets in the same chain without designing a unified policy.

## 6. What Is a Nonce and How Must It Be Generated?

A **nonce** is a random value authorizing a specific script/style element. The server emits the nonce in the **CSP header** while placing it in the `nonce` attribute of **trusted tags generated by the application**:

```http
Content-Security-Policy: default-src 'none'; script-src 'nonce-ExampleRandomValueOnly'; object-src 'none'; base-uri 'none'
```

```html
<script nonce="ExampleRandomValueOnly">
  document.getElementById("message").textContent = "Trusted script";
</script>
```

The string above only illustrates syntax—it **lacks sufficient entropy and must not be copied to production**. For real nonces, use a CSPRNG and a fresh value per response.

### Technical Requirements

- **At least 128 bits of entropy**. For example, 24 random bytes = **192 bits**, Base64-encoded.
- Generate with `java.security.SecureRandom`, never `Math.random()`, timestamps, or incrementing counters.
- Every **HTML response** gets a fresh nonce; never store one in `application.properties`, static constants, or sessions for reuse.
- Within the **same response**, header and HTML must use the **exact same nonce**.
- Assign nonces only to script/style tags **controlled by the server/template**. Never auto-attach nonces to all `<script>` tags after concatenating user-supplied HTML.
- A nonce need not remain secret forever: it appears in the response and DOM. The crucial property is being **unpredictable before a new response is generated**.
- When HTML is cached or proxy-rewritten, keep **header and HTML synchronized**; never pair a cached body carrying nonce A with a header carrying nonce B.
- Never treat a nonce as an authentication token, password, or CSRF token.

### Nonces, Hashes, and SRI

| Mechanism | Purpose | Best suited when |
| --- | --- | --- |
| CSP nonce | Permits trusted script/style elements in a response | Dynamically rendered HTML |
| CSP hash `'sha256-...'` | Permits inline script/style blocks matching the hash | Static, rarely changing content |
| SRI `integrity="sha384-..."` | Verifies fetched resource bytes by hash | External scripts/styles from CDNs |
| CSP host allowlist | Permits sources by origin/host | Watch for XSS leveraging same-origin sources |
| `'strict-dynamic'` | Trusts nonce/hash-allowed scripts and scripts they load dynamically | Loaders audited against script gadgets |

Never treat a nonce as a "content-integrity signature": a nonce authorizes the **script tag** and does not prove the logic inside is safe. For external resources, SRI serves a distinct purpose and should be considered alongside CSP.

## 7. Complete Example: Spring Boot WebFlux Generating a Nonce per HTML Response

The demo uses **Java 17+**, **Spring Boot 3.3.5**, Spring Security managed by the Boot BOM, and compatible Gradle (e.g., 8.5).

Behavior:

- `GET /page?name=An`: server generates a fresh nonce, sets the CSP header, and returns HTML with a matching script nonce.
- The `name` parameter is **HTML-escaped** before insertion into the text node.
- The trusted script registers its event via `addEventListener`, avoiding `onclick`.
- `Cache-Control: no-store` is set on nonce-bearing pages; no conflicting static CSP is enabled.
- `GET /health` is public.
- `GET /api/profile` requires HTTP Basic, demonstrating CSP does not replace authentication.

### 7.1. Project Structure

```text
reactive-csp-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/csp/
    │   ├── CspApplication.java
    │   ├── SecurityConfig.java
    │   ├── CspNonceGenerator.java
    │   └── CspController.java
    └── test/java/dev/example/csp/
        └── CspSecurityTests.java
```

### 7.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-csp-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not simultaneously add `spring-boot-starter-web` to a pure WebFlux demo: Spring Boot typically favors Servlet/MVC when both web starters are present.

### 7.3. Application Entry Point

`src/main/java/dev/example/csp/CspApplication.java`:

```java
package dev.example.csp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CspApplication {
    public static void main(String[] args) {
        SpringApplication.run(CspApplication.class, args);
    }
}
```

### 7.4. Security Config

`src/main/java/dev/example/csp/SecurityConfig.java`:

```java
package dev.example.csp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/page", "/health")
                            .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Explanation:
- `@EnableWebFluxSecurity` and `ServerHttpSecurity` belong to the reactive stack.
- The HTML page is public for the demo; `/api/profile` requires an authenticated principal.
- Sample user `reader` and password `reader-pass` are for localhost only, BCrypt-encoded in memory.
- No static `.contentSecurityPolicy(...)` writer is in the chain; the `/page` controller generates the nonce header, avoiding two overlapping CSP policies.
- Spring Security still applies other default headers, such as `X-Content-Type-Options: nosniff`.
- `formLogin` is disabled so 401 HTTP Basic challenges are observed cleanly.
- Production must use HTTPS/TLS if transmitting HTTP Basic credentials, and must never hardcode demo credentials.

### 7.5. Nonce Generator Using SecureRandom

`src/main/java/dev/example/csp/CspNonceGenerator.java`:

```java
package dev.example.csp;

import java.security.SecureRandom;
import java.util.Base64;

import org.springframework.stereotype.Component;

@Component
public class CspNonceGenerator {

    private final SecureRandom random = new SecureRandom();

    public String nextNonce() {
        byte[] bytes = new byte[24]; // 24 bytes = 192 bits
        random.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
```

Each `nextNonce()` call allocates a fresh byte array and fills it using the CSPRNG. A single shared generator bean is fine; **never store a generated nonce in a field and reuse it**. 24 bytes provide 192 bits of entropy, yielding a Base64 string of roughly 32 characters. Base64 is not encryption; here it simply encodes the nonce using valid CSP header characters.

### 7.6. WebFlux Controller Generating Synchronized CSP and HTML

`src/main/java/dev/example/csp/CspController.java`:

```java
package dev.example.csp;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

import reactor.core.publisher.Mono;

@RestController
public class CspController {

    private final CspNonceGenerator nonceGenerator;

    public CspController(CspNonceGenerator nonceGenerator) {
        this.nonceGenerator = nonceGenerator;
    }

    @GetMapping(value = "/page", produces = MediaType.TEXT_HTML_VALUE)
    public Mono<ResponseEntity<String>> page(
            @RequestParam(defaultValue = "guest") String name) {

        return Mono.fromSupplier(() -> {
            String nonce = nonceGenerator.nextNonce();
            String safeName = HtmlUtils.htmlEscape(name);

            String policy = "default-src 'none'; "
                    + "script-src 'nonce-" + nonce + "'; "
                    + "script-src-attr 'none'; "
                    + "style-src 'none'; "
                    + "img-src 'self'; "
                    + "connect-src 'self'; "
                    + "object-src 'none'; "
                    + "base-uri 'none'; "
                    + "form-action 'self'; "
                    + "frame-ancestors 'none'";

            String html = """
                    <!doctype html>
                    <html lang="en">
                    <head>
                      <meta charset="utf-8">
                      <title>Spring WebFlux CSP demo</title>
                    </head>
                    <body>
                      <h1>Nonce CSP demo</h1>
                      <p id="message">Hello %s</p>
                      <button id="change" type="button">Change greeting</button>
                      <script nonce="%s">
                        document.getElementById("change")
                          .addEventListener("click", () => {
                            document.getElementById("message")
                              .textContent = "Trusted script executed";
                          });
                      </script>
                    </body>
                    </html>
                    """.formatted(safeName, nonce);

            return ResponseEntity.ok()
                    .contentType(new MediaType(
                            MediaType.TEXT_HTML, StandardCharsets.UTF_8))
                    .cacheControl(CacheControl.noStore())
                    .header("Content-Security-Policy", policy)
                    .body(html);
        });
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(Principal principal) {
        return Mono.just(Map.of("user", principal.getName()));
    }
}
```

#### Why Does This Approach Satisfy the Policy?

1. `Mono.fromSupplier(...)` executes logic when the subscriber handles the request. Every `/page` response generates a new nonce.
2. The `SecureRandom` nonce has sufficient entropy; **the same `nonce` variable** builds both `script-src` and `<script nonce="...">`.
3. `script-src 'nonce-...'` permits the server-owned script tag while disallowing arbitrary inline scripts.
4. `script-src-attr 'none'` and omitting `'unsafe-inline'` block inline event-handler attributes.
5. The script uses `addEventListener` rather than `onclick="..."`.
6. `HtmlUtils.htmlEscape(name)` sanitizes user input **before inserting into an HTML text context**. Never insert user input into script source, unescaped HTML attributes, or `javascript:` URLs.
7. `object-src 'none'`, `base-uri 'none'`, and `frame-ancestors 'none'` reduce additional attack surfaces.
8. `CacheControl.noStore()` prevents reuse of a document containing a nonce; CDNs/proxies must still be configured accordingly.
9. `ResponseEntity` sets proper `Content-Type: text/html; charset=UTF-8` and the CSP header.
10. Although `/page` is public, `/api/profile` still requires authentication. CSP does not replace authorization.
11. No second global CSP writer is added. If a gateway also adds CSP, check policy intersection.
12. `Mono<ResponseEntity<String>>` is an appropriate reactive controller return type; never call `block()` or `subscribe()`.

This is a small **server-rendered HTML** demo without a template engine. With Thymeleaf/real SSR, the equivalent pattern generates a single per-request nonce, passes it to the model/template, and uses it in both the header and template-authored script tags. **Never automatically attach nonces to all script tags after user data has been interpolated.**

## 8. Running and Observing Headers

From the `reactive-csp-demo` directory:

```bash
gradle bootRun
```

If using a Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). The server defaults to `http://localhost:8080`.

### 8.1. Using curl to Inspect the Response

```bash
curl -i "http://localhost:8080/page?name=An"
```

You will see parts like:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
Cache-Control: no-store
Content-Security-Policy: default-src 'none'; script-src 'nonce-<NEW_NONCE>'; script-src-attr 'none'; style-src 'none'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

`<NEW_NONCE>` is only an **output placeholder**, not a real value. The HTML body contains:

```html
<p id="message">Hello An</p>
<script nonce="<EXACT_NONCE_VALUE_FROM_HEADER>">
  // Application-authored script using addEventListener.
</script>
```

This is **abbreviated output**, not a byte-for-byte full response. What must be verified is that **the header and script attribute match in the same response**, and **the nonce changes across two responses**.

`curl` does not enforce CSP like a browser. Use it to inspect headers/bodies, not to conclude XSS is blocked in browsers.

### 8.2. Testing Dangerous HTML Input in a Learning Environment

```bash
curl -i "http://localhost:8080/page?name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E"
```

After HTML escaping, the page contains text like:

```html
<p id="message">Hello &lt;img src=x onerror=alert(1)&gt;</p>
```

The browser renders those characters as plain text rather than creating an `<img>` from the input. This is the direct benefit of **output encoding**. If another rendering context fails to encode, CSP can block an un-nonced event handler, yet you must fix the injection source rather than relying solely on CSP.

### 8.3. Using DevTools

1. Open `http://localhost:8080/page?name=An`.
2. Go to **Network → Document /page** and inspect `Content-Security-Policy`, `Content-Type`, and `Cache-Control`.
3. Verify the application's `<script nonce="...">` in the DOM.
4. Click the "Change greeting" button; the script with a valid nonce executes.
5. Reload and check for a new nonce. If identical across multiple responses, inspect the generator/cache.
6. Try URL-encoded HTML input; confirm it renders as text.
7. Check **Console** for CSP violations.
8. If DevTools `getAttribute("nonce")` returns an empty string, that may be the browser's **nonce hiding** behavior; the `element.nonce` property can still be read. Never treat the nonce as a permanent secret.

**Do not treat JavaScript typed directly into the DevTools Console as sole proof of CSP**: DevTools runs with special privileges and behaves differently from scripts delivered in HTML. Use test pages/E2E tests and inspect actual script elements and violations.

### 8.4. Authentication Remains Independent

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/profile

# Curl prompts for demo password when only username is provided.
curl -i --user reader http://localhost:8080/api/profile
```

Expected:
- `GET /health` → 200, body `ok`.
- `GET /api/profile` without credentials → 401.
- `GET /api/profile` as `reader` with correct password → 200, JSON containing `user=reader`.

In production, always use HTTPS/TLS with server verification; never send plaintext HTTP Basic credentials over unencrypted HTTP.

## 9. Testing with WebTestClient

`WebTestClient` verifies WebFlux response headers/bodies. It **is not a browser JavaScript engine**: passing tests do not prove browsers block all XSS. Browser E2E tests are needed when deploying security policies.

File `src/test/java/dev/example/csp/CspSecurityTests.java`:

```java
package dev.example.csp;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CspSecurityTests {

    private static final Pattern NONCE_PATTERN =
            Pattern.compile("script-src 'nonce-([^']+)'");

    @Autowired
    WebTestClient client;

    private EntityExchangeResult<String> page(String url) {
        return client.get().uri(url)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .returnResult();
    }

    private String nonceInHeader(EntityExchangeResult<String> result) {
        String policy = result.getResponseHeaders()
                .getFirst("Content-Security-Policy");
        assertNotNull(policy);

        Matcher matcher = NONCE_PATTERN.matcher(policy);
        assertTrue(matcher.find());
        return matcher.group(1);
    }

    @Test
    void trustedScriptHasTheNonceDeclaredInCsp() {
        EntityExchangeResult<String> result = page("/page?name=An");
        String nonce = nonceInHeader(result);
        String html = result.getResponseBody();

        assertNotNull(html);
        assertTrue(nonce.length() >= 22);
        assertTrue(html.contains("<script nonce=\"" + nonce + "\">"));
    }

    @Test
    void twoResponsesHaveDifferentNonces() {
        String first = nonceInHeader(page("/page"));
        String second = nonceInHeader(page("/page"));

        assertNotEquals(first, second);
    }

    @Test
    void scriptPolicyDoesNotUseUnsafeInlineOrUnsafeEval() {
        EntityExchangeResult<String> result = page("/page");
        String policy = result.getResponseHeaders()
                .getFirst("Content-Security-Policy");

        assertNotNull(policy);
        assertFalse(policy.contains("'unsafe-inline'"));
        assertFalse(policy.contains("'unsafe-eval'"));
        assertTrue(policy.contains("object-src 'none'"));
        assertTrue(policy.contains("base-uri 'none'"));
        assertTrue(policy.contains("frame-ancestors 'none'"));
        assertTrue(policy.contains("script-src-attr 'none'"));
    }

    @Test
    void userInputIsHtmlEscaped() {
        EntityExchangeResult<String> result = page(
                "/page?name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E");
        String html = result.getResponseBody();

        assertNotNull(html);
        assertTrue(html.contains("&lt;img"));
        assertTrue(html.contains("&gt;"));
        assertFalse(html.contains("<img src=x"));
    }

    @Test
    void dynamicHtmlIsMarkedNoStore() {
        EntityExchangeResult<String> result = page("/page");
        String header = result.getResponseHeaders()
                .getFirst(HttpHeaders.CACHE_CONTROL);

        assertNotNull(header);
        assertTrue(header.contains("no-store"));
    }

    @Test
    void springSecurityStillSetsNosniff() {
        EntityExchangeResult<String> result = page("/page");
        assertEquals("nosniff", result.getResponseHeaders()
                .getFirst("X-Content-Type-Options"));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void profileNeedsAuthentication() {
        client.get().uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCanViewProfile() {
        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.user").isEqualTo("reader");
    }
}
```

Run:

```bash
gradle test
```

**Expected result:** 9 tests pass when files and dependencies match the example. This is an **expected outcome based on code**, not a claim that Gradle was executed in your environment.

### Scope of the Tests

| Test | Verifies | Does not prove |
| --- | --- | --- |
| CSP nonce matches script tag | Header and HTML are generated synchronously | Browser is free of XSS |
| Fresh nonce across 2 responses | Nonces are not reused between requests | Every CDN/proxy node is configured properly |
| No unsafe-inline/eval | Strict script policy on tested directives | Absence of script gadgets |
| HTML escaping | Input in **text context** does not become a tag | Every HTML/JS/CSS context is safe |
| Cache-Control no-store | Demo page requests no caching | All proxy caches comply |
| Nosniff present | Spring Security default header is active | HTTPS/HSTS is configured |
| 401/200 profile | Authentication works independently of CSP | All endpoints have complete authorization |

**Critical check:** If filter A generates nonce A in the header while view B generates nonce B in the script, both might look like "a nonce is present" yet the browser will still block it. Tests must compare **values within the same response**, not merely assert that `nonce-` appears.

## 10. Nonce Design in Multi-Page Applications

### 10.1. WebFilter and Template Engines

Across many HTML controllers, establishing a **request-scoped nonce** is easiest to manage:

```text
HTTP request
     |
     v
WebFilter / request context generates nonce once
     |
     +--> Store nonce in ServerWebExchange attribute
     |
     +--> Build CSP response header with that nonce
     |
     +--> Pass nonce to view/template
     |
     v
Render HTML: only trusted script/style tags carry nonce
     |
     v
Synchronized response header + body
```

This is a design diagram, **not standalone filter code**. If using `ServerHttpResponse.beforeCommit(...)`, remember to write the header **before the response commits**. Never call `block()` to unwrap a nonce from a `Mono`, and never generate distinct nonces across different components of the same document.

### 10.2. Template Engines and User-Provided HTML

Templates must attach nonces only to `<script>`/`<style>` tags controlled by your team. **Never** run a regex replacing every `<script>` in the final HTML to add a nonce: an attacker could submit an HTML fragment containing a script, and that logic would accidentally grant it a nonce.

If your template engine auto-escapes text, keep that behavior; never use raw/unescaped HTML directives unless the value has been sanitized under your application's policy.

### 10.3. Static SPAs, SSR, and Hash-Based Policies

With static HTML behind a CDN, generating a fresh nonce **per response** is not straightforward if the CDN serves cached raw bytes. Options:
- Move inline scripts into external files and use a suitable CSP.
- Use hash-based CSP for static inline snippets.
- Dynamically render the nonce in both header and HTML at the server/edge before returning.
- Never reuse a build-time nonce across all users.
- Audit scripts injected by framework builds into the document, hydration scripts, third-party SDKs, and CSS runtimes.

If a CDN updates only the CSP header without updating the script nonce in the cached body, the browser blocks trusted scripts. If it swaps the body without updating the header, it breaks too. Maintain a consistent caching strategy and test the final response reaching the browser.

### 10.4. Multiple Spring Security Filter Chains

With `@Order`/`securityMatcher`, separate chains may handle HTML, APIs, admin, etc. A CSP writer on chain A does not automatically apply to documents handled by chain B. Inspect every path, redirect, and error page. You can apply HTML policies at the controller/renderer layer and static policies via security header writers on other responses, while avoiding duplicate or mismatched headers.

### 10.5. Proxies, Gateways, and Multiple CSP Headers

If a proxy adds a fixed CSP while the app adds a nonce CSP, browsers must satisfy **all enforced policies**. For example:
- Policy A: `script-src 'self'`.
- Policy B: `script-src 'nonce-abc'`.

An inline script carrying nonce `abc` satisfies B, yet may still violate A because `'self'` does not allow that inline script. Do not solve this by switching both to `'unsafe-inline'`. Establish unified ownership and test the final CSP response.

## 11. XSS Protection Limits

### 11.1. CSP Does Not Replace Output Encoding

OWASP treats context-aware output encoding and sanitization (when needed) as the primary defense. An injected script may be blocked by CSP, yet untrusted markup can still alter the UI, create phishing forms, or exploit browsers/libraries with differing behaviors. Never pass raw user input into:
- HTML text without HTML escaping.
- HTML attributes without context-appropriate encoding.
- JS strings or source code.
- CSS strings or URLs.
- `href=javascript:...` or dangerous URLs.
- DOM `innerHTML` and dangerous sinks.

To display text, use `textContent` in JavaScript rather than `innerHTML`. When rich HTML is required, use a reputable sanitizer (e.g., DOMPurify in the appropriate context), keep it updated, and avoid mutating output after sanitization in ways that undo protection.

### 11.2. A Nonced Script Can Still Be an XSS Gadget

The following JavaScript fragment is **unsafe even inside a nonce-authorized script**:

```javascript
// ANTI-PATTERN: trusted code still handles input dangerously.
const query = new URLSearchParams(location.search).get("html");
document.getElementById("target").innerHTML = query;
```

Valid scripts have DOM access. CSP might block some subsequent injected script execution, yet does not guarantee neutralizing all exploitation paths. Fix it with `textContent` or a sanitizer for rich HTML, and eliminate the dangerous data flow.

### 11.3. `'strict-dynamic'` Has Both Benefits and Risks

When CSP includes a nonce/hash plus `'strict-dynamic'`, supporting browsers can trust scripts dynamically created/loaded by an already-trusted script. This helps script loaders work, yet if a loader builds `<script src=...>` from query parameters or untrusted data, an attacker can steer script sources under the allowed policy.

In browsers supporting `'strict-dynamic'`, host sources, scheme sources, or `'self'` in `script-src` may be ignored in that model. Never treat `'strict-dynamic'` as simply "adding an origin to an allowlist."

### 11.4. A Nonce Is Not an Access Token

Nonces appear in the document and can be read via DOM APIs. They do not replace CSRF tokens or session identifiers. If an attacker can already execute trusted JavaScript within the origin, a nonce will not stop access to data reachable by legitimate scripts. A nonce primarily prevents **an untrusted script from becoming an executed script**.

### 11.5. CSP Does Not Fix Backend Vulnerabilities

IDOR/BOLA, broken authorization, SSRF, SQL injection, insecure deserialization, leaked JWTs, missing tenant isolation, CSRF, and business-logic flaws are never solved by CSP alone. The server must still authenticate, authorize, and validate requests.

Nor does CSP encrypt HTTP, revoke tokens, or stop bots/curl from sending requests: **HTTPS, HSTS, security filters, authn/authz, CSRF, and rate limiting** are separate controls.

### 11.6. Browser Compatibility

CSP is enforced by supporting browsers, not all HTTP clients. Newer directives such as `script-src-attr`, `'strict-dynamic'`, or Trusted Types vary in support and behavior. Test across your product's supported browser list, and keep output encoding active even if a policy is not enforced.

## 12. Trusted Types and Complementary Layers

**Trusted Types** (where supported by browsers) can require certain DOM injection sinks to accept typed values produced through an appropriate policy rather than arbitrary strings. The `require-trusted-types-for 'script'` directive can help reduce DOM XSS in DOM-heavy applications.

However:
- Trusted Types **do not automatically sanitize data**. A policy producing `TrustedHTML`/`TrustedScriptURL` must still validate/sanitize properly.
- Browser support varies; feature detection and suitable fallbacks are required.
- Overly permissive policies—such as returning unchecked input verbatim—reduce protective value.
- Use safe DOM APIs from the start, then layer on Trusted Types in complex apps.
- Never enable a new directive in production without auditing libraries that rely on `innerHTML` or controlled sinks.

A layered defense system:
- Context-aware encoding + safe rendering.
- HTML sanitization when user-authored markup is allowed.
- Nonce/hash-based CSP.
- Trusted Types where browser/framework support exists.
- Auditing dependencies/third-party scripts and using SRI where appropriate.
- Separate HTTPS/HSTS, cookie attributes, and authentication/authorization.

## 13. CSP Report-Only and Violation Reports

An example Report-Only policy:

```http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'; report-uri /csp-report
```

It does not block scripts itself; it instructs the browser to log/report violations. `report-uri`/`report-to` and `Reporting-Endpoints` depend on browser support and configuration, so verify target browsers.

**Do not merely declare `report-uri` and expect the server to collect reports automatically.** You need a dedicated endpoint, safe handling of untrusted report payloads, and flood protection.

Violation reports may contain:
- The document URL or blocked resource URL.
- Violated directive and file/line details.
- Samples of blocked content if `'report-sample'` is enabled in supporting browsers.

Those fields can expose PII or tokens if sensitive data ever appeared in URLs or source. Therefore:
1. Never put secrets in queries or paths.
2. Scrub sensitive data in the report receiver and log collector.
3. Enforce size limits, rate limiting, and sampling.
4. Apply RBAC/auditing, retention, and privacy policies.
5. Do not enable `'report-sample'` by default everywhere.
6. Distinguish browser-extension noise from real application regressions.

An application can keep an **active enforcing policy** alongside a **new report-only policy** to test further tightening, provided you track which policy blocks and which only observes.

## 14. CSP Alongside Other HTTP Security Headers

| Mechanism | Purpose | Does not replace |
| --- | --- | --- |
| CSP | Restricts content/script sources and behaviors inside documents | Output encoding, authn/authz, CSRF |
| HTTPS/TLS | Protects HTTP data in transit | CSP, server authorization |
| HSTS | Helps browsers prefer HTTPS after learning policy | Certificate validation, CSP |
| `X-Content-Type-Options: nosniff` | Restricts MIME sniffing | CSP script policy |
| `X-Frame-Options` | Reduces clickjacking in older browsers | All CSP capabilities |
| `frame-ancestors` | Chooses which origins may embed the page | `frame-src` (the reverse direction) |
| `Referrer-Policy` | Reduces data sent via `Referer` | Authentication |
| Cookie `Secure`/`HttpOnly`/`SameSite` | Mitigates certain cookie risks | CSP and all CSRF cases |
| CSRF token | Protects state-changing actions with browser credentials | CSP and CORS |
| SRI | Verifies bytes of externally loaded resources | Nonce freshness |
| Trusted Types | Restricts supported DOM injection sinks | Sanitization/validation |

Spring Security provides several default headers, yet **does not generate an application-specific CSP**. HSTS must apply over HTTPS; never enable `upgrade-insecure-requests` in a localhost HTTP demo as a substitute for TLS configuration.

## 15. Common CSP Misconfigurations

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Script with nonce still fails to run | Header nonce differs from HTML | Generate one nonce and reuse it within a single response |
| Nonce is always identical | Generated at startup or cached | Use CSPRNG on every HTML response |
| Arbitrary script runs without a nonce | Policy has `'unsafe-inline'` or broad sources | Tighten `script-src`, remove unsafe-inline |
| All inline scripts are blocked | `default-src 'none'` without `script-src` | Authorize trusted script nonces/hashes |
| Styles are missing | `style-src 'none'` blocks CSS | Allow valid stylesheets/style nonces |
| Same-origin external JS fails to load | Nonce policy does not imply `'self'` | Add nonce to trusted script tags or adjust policy |
| Report-only does not block anything | Working as designed: observation only | Switch to enforcing after QA |
| Two different CSP values emitted | Proxy and app both add the header | Establish single ownership or check intersection |
| Nonced JS still suffers DOM-XSS | Trusted script uses `innerHTML` | Replace dangerous sinks with safe DOM APIs |
| CDN causes mismatch | Body has nonce A, header has nonce B | Synchronize caching and rendering |
| One page lacks CSP | Hits a different filter chain/route | Audit all HTML documents |
| Browser reports CSP violation | Policy blocks an unpermitted resource | Classify valid vs. invalid scripts before relaxing |
| `frame-ancestors 'none'` blocks needed iframe | Embed requirements not accounted for | Intentionally allowlist required origins |
| AJAX/WebSocket blocked | `connect-src` missing valid URLs | List actual API/WSS endpoints |
| CSP report spam | Missing rate limiting/filtering | Add sampling and endpoint controls |
| Servlet CSP API used in WebFlux app | Confused `HttpSecurity` with `ServerHttpSecurity` | Use the reactive DSL |
| HTTP tests pass while browser fails | Tests do not execute JS | Add browser E2E and DevTools checks |

## 16. Review Checklist and Self-Check

### Pre-Production Checklist

- [ ] Application uses **WebFlux** properly with the matching security chain.
- [ ] CSP is explicitly designed; never assume Spring Security adds it automatically.
- [ ] Single owner for each document's CSP header, with no unintended duplicate policies.
- [ ] `script-src` is not overly broad; avoid `'unsafe-inline'` and `'unsafe-eval'`.
- [ ] CSPRNG nonce has **≥128 bits of entropy**, regenerated for every HTML response.
- [ ] Header nonce and HTML `nonce` attributes match within the same response.
- [ ] Nonces are never automatically attached to user-controlled scripts.
- [ ] Context-appropriate output encoding exists for HTML text/attributes/JS/URL/CSS.
- [ ] Never pass untrusted input to `innerHTML`; sanitize rich HTML if permitted.
- [ ] `object-src`, `base-uri`, `frame-ancestors`, `form-action`, and `connect-src` are reviewed.
- [ ] Nonce-bearing scripts are reviewed against dynamic-loader gadgets.
- [ ] HTML caches/CDNs/proxies do not cause nonce mismatches.
- [ ] CSP Report-Only rollout and report endpoints enforce access control, retention, and rate limits.
- [ ] HTTPS/TLS, HSTS, nosniff, cookies, CSRF, CORS, and authentication are reviewed separately.
- [ ] Response headers/bodies and browser E2E behavior are tested across supported browsers.
- [ ] Login/error pages, multiple chains, SSR, and SPA documents are all tested for CSP.

### Review Questions

**1. Who enforces CSP?**  
The browser enforces the policy sent by the server via response headers; CSP does not enforce server-side API permissions.

**2. Does Spring Security reactive include a default CSP?**  
No. Each application must supply an appropriate policy.

**3. How does Enforce differ from Report-Only?**  
Enforce blocks violations; Report-Only logs/reports them without blocking under that policy.

**4. What minimum entropy does a nonce require?**  
At least 128 bits; the demo uses 192 bits from `SecureRandom`.

**5. Can a single nonce be reused across all responses?**  
No. Generate a fresh one per HTML response, using that same nonce in the header and all trusted scripts within that response.

**6. What HTML does `script-src 'nonce-abc'` require?**  
A script tag with attribute `nonce="abc"`, not blocked by another policy.

**7. Why isn't a nonce a password?**  
It is present in the HTML/DOM and is designed to be unpredictable **before the response is built**, not a permanent secret.

**8. Why shouldn't you automatically add a nonce to every script tag?**  
It could grant a nonce to an attacker-injected script after untrusted input was interpolated into HTML.

**9. Does CSP replace `HtmlUtils.htmlEscape`?**  
No. Context-aware output encoding is the primary line of defense.

**10. Is `innerHTML=userInput` safe inside a nonced script?**  
No. A trusted script can still cause DOM XSS; use `textContent` or a sanitizer.

**11. What does `'strict-dynamic'` do?**  
It lets nonce/hash-trusted scripts propagate trust to scripts they load dynamically; dangerous if a loader builds URLs from untrusted input.

**12. Are `frame-ancestors` and `frame-src` the same?**  
No. One controls who may embed your page; the other controls which resources your page may embed.

**13. Why aren't WebTestClient CSP tests sufficient?**  
WebTestClient does not execute JavaScript or browser CSP semantics; browser E2E testing is required.

**14. Does CSP stop unauthenticated users from calling APIs?**  
No. Spring Security authentication and authorization are required.

**15. Should you enable `'unsafe-inline'` when a legitimate script gets blocked?**  
Not as a default quick fix. Check for nonce/header mismatches or refactor the script.

**16. Can a proxy CSP and an app CSP conflict?**  
Yes. All enforced policies must be satisfied; one policy can block a source allowed by the other.

**17. Can CSP violation reports contain sensitive data?**  
Yes—URLs, resource info, and source samples; redact and restrict access to the receiver.

**18. Does CSP replace HTTPS?**  
No. TLS protects transit; CSP governs certain content behaviors in the browser.

### Practice Exercises

1. Run the demo, fetch `/page` twice; confirm a fresh nonce each time and header/body parity per response.
2. Alter the `nonce` attribute in HTML to a wrong value **only in a local learning copy** and confirm the browser blocks the script.
3. Pass HTML in the `name` query param, observe `&lt;`/`&gt;`, and explain output encoding.
4. Change the CSP to `script-src 'self'` and observe the inline trusted script no longer runs.
5. Add a local stylesheet; design an explicit `style-src` so the page works without wildcards.
6. Write a test ensuring the policy contains neither `'unsafe-inline'` nor `'unsafe-eval'`.
7. Use browser E2E to verify valid scripts run while inline event handlers are disallowed.
8. Compare hash-based CSP for static inline bootstrap scripts against nonce-based CSP for dynamic HTML behind a CDN.
9. Design a Report-Only policy, a report-receiving endpoint, and rate-limiting/redaction controls.
10. Diagram a request-scoped nonce flow across WebFilter → template → header and identify where duplicate nonces could happen.
11. Review a `'strict-dynamic'` script loader reading URLs from query params; identify the risk and fix.
12. Add a role-restricted API demonstrating that CSP does not replace method/route security.
13. Check whether a proxy injects another CSP that blocks scripts.
14. Build a CSP checklist covering login and error pages, not only main pages.

## 17. References

- [Spring Security — WebFlux HTTP response headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): no default CSP; configuring `contentSecurityPolicy` and Report-Only.
- [Spring Security — WebFlux configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, security filters.
- [Spring Security 6.3 API — ServerHttpSecurity.HeaderSpec](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html): CSP header DSL API.
- [MDN — CSP guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): nonce/hash, strict CSP, `'strict-dynamic'`, Report-Only.
- [MDN — HTML nonce attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/nonce): minimum 128-bit nonce, single-use, header/script match.
- [MDN — Content-Security-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): directives and source expressions.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): context-aware encoding, sanitization, dangerous sinks, and CSP defense-in-depth.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): practical CSP strategies.
- [W3C — CSP Level 3](https://www.w3.org/TR/CSP3/): CSP specification.
- [Spring Framework — HtmlUtils](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/util/HtmlUtils.html): HTML text escaping.

**Remember:** For **Content-Security-Policy** in Spring Security reactive, use CSP to **reduce XSS risk**, never to replace **output encoding/sanitization**. When using nonces, the server must generate a fresh nonce with a **CSPRNG on every HTML response** and use that exact value in both the **CSP header and trusted scripts**; avoid `'unsafe-inline'`, never grant nonces to user-supplied data, and manage caching/CDNs carefully. Still enforce **HTTPS, authentication, authorization, CSRF, and safe DOM APIs**.