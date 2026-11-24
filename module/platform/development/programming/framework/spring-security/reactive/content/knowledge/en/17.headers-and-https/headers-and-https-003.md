# X-Content-Type-Options and Preventing Content-Type Sniffing

## Objectives and Context

This lesson belongs to the **Headers and HTTPS** group in the **Spring Security - reactive** module. When a browser loads a JavaScript, CSS, JSON, HTML, or user-uploaded document, the server must declare its **content type** using the `Content-Type` header. Historically, some browsers tried to *guess* the content type from the response's first bytes, even when the server sent no type or the wrong type. This **MIME sniffing** behavior can cause a document meant to be stored purely as data to be treated as **script or HTML**, creating cross-site scripting (XSS) and data exposure risks.

Protective header:

```http
X-Content-Type-Options: nosniff
```

instructs the browser to respect the declared MIME type instead of guessing under the rules governed by `nosniff`. **Spring Security WebFlux adds this header by default** on responses passing through a typical security chain, but the header is only effective when the application **also returns the correct `Content-Type`** for each resource.

After this lesson, you can:

1. Distinguish **MIME type**, `Content-Type`, and **content sniffing**.
2. Explain the effect of `X-Content-Type-Options: nosniff` when a browser loads `<script>` and `<link rel="stylesheet">`.
3. Explain why `nosniff` reduces MIME confusion/XSS risks but is **not** a malware filter, file validator, CSP, or complete XSS defense.
4. Distinguish `text/javascript`, `text/css`, `application/json`, `text/plain`, `text/html`, and `application/octet-stream` responses.
5. Use the proper Spring Security **reactive** `ServerHttpSecurity`/`SecurityWebFilterChain` APIs, understand default security headers, and verify them over HTTP.
6. Build a **Java 17+, Spring Boot 3.3.13, Spring WebFlux** app serving JS/CSS resources with accurate MIME types and intentionally wrong MIME types to observe browser blocking.
7. Test with `WebTestClient`: status, `Content-Type`, `X-Content-Type-Options`, response body, and security behavior.
8. Safely handle document/file uploads, downloads, static resources, reverse proxies, 401/403/500 responses, and cache/CDNs.
9. Distinguish `nosniff` from CSP, CORS, CSRF, HSTS, `Content-Disposition`, and intentionally executable HTML content.
10. Diagnose **"Refused to execute script ... MIME type ... strict MIME type checking"** messages in DevTools.

**Core takeaway:** `nosniff` **does not automatically fix an incorrect `Content-Type`**. If a script is served as `text/plain`, the browser will block the script rather than guessing it is JavaScript. The right fix is sending the proper MIME type while keeping `nosniff` enabled.

## 1. What Are MIME Type and Content-Type?

A **MIME type** (media type) classifies the returned data. The `Content-Type` header tells the client what kind of content the response body contains:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=UTF-8
X-Content-Type-Options: nosniff

document.title = "Demo";
```

In this example, `Content-Type` announces that this is JavaScript; `nosniff` tells the browser not to reinterpret those bytes as another type under restricted sniffing rules.

Common pairs:

| Actual content | Common Content-Type | Notes |
| --- | --- | --- |
| HTML page | `text/html; charset=UTF-8` | HTML can execute scripts when permitted by other policies |
| JavaScript | `text/javascript` | Standard MIME type for scripts; several other JavaScript MIME types remain accepted for compatibility |
| CSS | `text/css` | The type browsers require for stylesheets |
| JSON | `application/json` | Will not turn into an executable script via `<script>` when `nosniff` is present |
| Plain text | `text/plain; charset=UTF-8` | Browser will not treat it as HTML/JS purely from content |
| Undefined binary file | `application/octet-stream` | Often paired with `Content-Disposition: attachment` when downloading is intended |
| SVG | `image/svg+xml` | XML-based content that can have active behavior depending on context; uploads require special handling |
| PNG | `image/png` | Do not treat a `.png` extension as proof of actual content |
| JPEG | `image/jpeg` | Do not confuse with non-standard `image/jpg` |
| PDF | `application/pdf` | PDFs carry distinct risks; preview/download policies must be designed |
| CSV | `text/csv; charset=UTF-8` | Downloaded CSV data also requires attention to formula injection when opened in spreadsheets |

**A file extension is not a Content-Type.** A URL ending in `.js` can be returned by a server with `Content-Type: text/plain` due to misconfigured CDN/nginx rules; the browser decides handling based on response headers, request destination, mode, and policy. Conversely, a client can upload a file named `image.png` whose content is HTML/script. The server must verify the file itself, rather than trusting only the filename or multipart upload `Content-Type`.

**Content-Type differs from Content-Encoding.** `Content-Encoding: gzip` describes how the body is compressed. After decompression, a JavaScript file still has MIME type `text/javascript`; do not set `Content-Type: application/gzip` just because gzipped JavaScript is transferred over HTTP.

## 2. Content Sniffing: Why Is Guessing MIME Types Dangerous?

When a server omits MIME information or declares the wrong type, older browsers might inspect the leading bytes:

```text
Server declares: Content-Type: text/plain
Actual body:     <script>/* code controlling the page */</script>

Browser sniffs: "Looks like HTML/JS, maybe handle as active content?"
                         |
                         v
                 XSS / MIME confusion risk
```

A classic scenario:

1. An application lets users upload a file and stores it on the same hostname as the authenticated app.
2. The file is served by the server without a Content-Type or with an untrusted Content-Type.
3. The payload is a **polyglot** or syntax the browser can interpret as JavaScript/HTML.
4. The document is embedded into a page via `<script>` or opened directly in a browsing context, depending on MIME and browser policy.
5. If the browser treats the file as active content in a privileged origin, attacker code can access data accessible to that origin.

`nosniff` mitigates one class of this confusion by forbidding the browser from upgrading a file declared as non-script/non-style into script/style via disallowed sniffing.

However, if a server **intentionally returns untrusted content with `Content-Type: text/html`** on the same origin, the `nosniff` header does not render that HTML harmless. The browser is explicitly told it is HTML. Thus, **for untrusted uploads**, domain isolation, forced downloads, content sanitization, and proper CSP/HTML policies are still required.

## 3. Which Requests Does nosniff Actually Affect?

### 3.1. Script Destination

Given `<script src="...">`:

```html
<script src="/assets/good.js" defer></script>
<script src="/assets/bad.js" defer></script>
```

If the first response has:

```http
Content-Type: text/javascript
X-Content-Type-Options: nosniff
```

the browser may execute the JavaScript after satisfying other script-loading checks such as CSP, CORS for modules, and network state.

If the second response has:

```http
Content-Type: text/plain
X-Content-Type-Options: nosniff
```

the browser must refuse to execute it in the **script request destination** rather than sniffing the body into JavaScript.

**Important distinction:** The body of `bad.js` may contain valid JavaScript; **it is the mismatched response MIME type** that causes browser blocking. Renaming the URL to `good.js` will not fix it; you must fix the response Content-Type.

Modern browsers also enforce strict MIME checks for **JavaScript modules** (`type="module"`) and certain other loading mechanisms. Never assume classic script behavior without `nosniff` generalizes to every script type.

### 3.2. Stylesheet Destination

When HTML contains:

```html
<link rel="stylesheet" href="/assets/good.css">
<link rel="stylesheet" href="/assets/bad.css">
```

the browser expects responses for a `style` destination to have `Content-Type: text/css`. If `bad.css` is served as `text/plain` with `nosniff`, the browser blocks the mismatched stylesheet. This can strip colors/fonts from a layout because **the server declared the wrong type**, not because Spring Security denied authorization.

### 3.3. Navigation/Document and Other Responses

According to MDN/Fetch documentation, `nosniff` also instructs non-script/style contexts to respect Content-Type instead of guessing. For example, a response declared as `text/plain` containing `<h1>...` or `<script>...` will not be turned into a `text/html` page by the browser just because the bytes look like HTML.

Yet **do not overgeneralize to "nosniff blocks every wrong-MIME resource across the entire Web"**:

- At **script/style destinations**, strict MIME **blocking** applies.
- For **navigation/document**, browsers use the provided MIME type; display/download behavior can vary by browser and other headers.
- For **`fetch()`**, receiving bytes and calling `response.text()` or `response.json()` depends on CORS, body parsing, and JS code; `nosniff` **is not a JSON schema validator**. `response.json()` can still parse or fail based on content and does not perform authorization.
- For images, PDFs, fonts, media, and downloads, dedicated MIME, CORS/CORP/CSP, and security rules apply; `nosniff` does not replace them.
- For **cross-origin** data, browsers may apply other read-restriction mechanisms such as CORB where implemented. Do not rely on CORB as a substitute for missing API authorization.

### 3.4. The Only Valid Value Is nosniff

Syntax:

```http
X-Content-Type-Options: nosniff
```

Do not use `sniff`, `deny`, `sameorigin`, or `1` as replacement values. `DENY` and `SAMEORIGIN` belong to different policies such as `X-Frame-Options`.

**Do not confuse it with `X-XSS-Protection`.** That header is a legacy, deprecated mechanism that could even introduce unwanted behavior; `nosniff` serves its own specific purpose, though it does not replace CSP or source-level XSS prevention.

## 4. Related Protection Layers: None Replaces Another

| Mechanism | What does it protect? | Does it replace nosniff? |
| --- | --- | --- |
| `Content-Type` | Declares accurate content type | Must be paired with nosniff |
| `X-Content-Type-Options: nosniff` | Prevents improper MIME sniffing; blocks mismatched script/style | Central control here |
| `Content-Security-Policy` | Controls script/style origins, inline code, other destinations | Does not replace sending proper MIME |
| `Content-Disposition: attachment` | Directs browser to download instead of inline rendering | Useful for untrusted files; does not replace validation |
| `Strict-Transport-Security` | Encourages browser to use HTTPS for host when eligible | Unrelated to MIME directly |
| `X-Frame-Options` / `frame-ancestors` | Restricts framing the page | Does not classify scripts/styles |
| `CORS` | Conditionally lets JS from another origin read responses | Not MIME validation |
| `CSRF protection` | Protects against certain forged state-changing browser requests | Does not address MIME confusion |
| `Authentication`/`Authorization` | Verifies who may access a resource | Does not replace nosniff |
| File scanning/sanitization | Detects and sanitizes malicious upload content | Still needed, especially for HTML/SVG/PDF |
| Separate upload domain | Isolates active content from privileged origin | Crucial when users upload untrusted files |

A single request may simultaneously require **HTTPS, authorization, accurate Content-Type, nosniff, and CSP**, depending on the resource. Having `nosniff` alone does not make an endpoint returning arbitrary `text/html` safe.

## 5. What Does Spring Security WebFlux Do by Default?

### 5.1. Default Header

When reactive Spring Security is enabled via `SecurityWebFilterChain` and defaults are not disabled, Spring Security adds several security response headers, including:

```http
X-Content-Type-Options: nosniff
```

Other default headers may include cache-control, `X-Frame-Options`, `X-XSS-Protection: 0`, and `Strict-Transport-Security` **only under appropriate HTTPS conditions**. Always verify the exact header set and values against your Spring Security version.

In WebFlux, the DSL is `ServerHttpSecurity`, **not Servlet `HttpSecurity`**:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Even though the code does not call `headers(...)`, **Content-Type Options remains enabled by default**. Calling `permitAll()` only allows requests to reach the handler; it does not mean security headers should be omitted on public responses.

### 5.2. When Expressing the Header Explicitly

If you want explicit configuration visible in the codebase, Spring Security supports:

```java
// Illustrative snippet added to ServerHttpSecurity before build().
.headers(headers -> headers
    .contentTypeOptions(Customizer.withDefaults()))
```

This method belongs to reactive `ServerHttpSecurity.HeaderSpec`. In Spring Security WebFlux, security header handling is integrated into the security filter chain. **You do not need to write a custom WebFilter just to set `X-Content-Type-Options` when using the default**, nor should you emit duplicate headers if a gateway already enforces a unified policy.

### 5.3. How to Disable (for Understanding, Not Recommended)

```java
// Illustrative snippet — do not apply to the runnable demo in this lesson.
.headers(headers -> headers
    .contentTypeOptions(contentTypeOptions ->
        contentTypeOptions.disable()))
```

Disabling it strips browsers of a protective layer when handling scripts/styles and other MIME contexts. If static JS/CSS fails to load after enabling `nosniff`, **fix the MIME type at the source** (WebFlux controller, resource handler, object storage, nginx/CDN) instead of disabling the header.

**Never disable nosniff to serve JSON, CSV, images, or PDFs**. Each type should carry an appropriate `Content-Type` and explicit download/render rules.

### 5.4. Does the Header Appear on Every URL?

Headers are applied by the **security chain**. In applications with multiple `SecurityWebFilterChain` beans, a request may hit another chain with different header settings; if no chain matches, do not assume the header was added.

Additionally:

- Responses generated by a proxy/CDN **before reaching the app** may lack headers added by Spring Security.
- Exceptions thrown inside a WebFilter running before the security chain may be handled by a global error handler without passing through the header writer.
- Static resources may be served by a resource handler or another domain/CDN.
- Once a response is committed, downstream filters cannot freely modify response headers.

Thus, **practical testing** of 200, 401/403, 404, 500, file downloads, static assets, and responses through a reverse proxy matters more than simply reading a configuration bean.

## 6. Runnable Example: Java 17+, Spring Boot WebFlux, and Browser

The demo app intentionally serves two JS files and two CSS files:

- `/assets/good.js`: JavaScript body, `Content-Type: text/javascript`.
- `/assets/bad.js`: JavaScript body **but** `Content-Type: text/plain`.
- `/assets/good.css`: CSS body, `Content-Type: text/css`.
- `/assets/bad.css`: CSS body **but** `Content-Type: text/plain`.

All include `X-Content-Type-Options: nosniff` when passing through the security chain.

The page `/demo.html` embeds `<script>` and `<link>` pointing to all four resources for verification in Chrome/Firefox. It also exposes JSON endpoint `/api/public`, Basic-auth-protected `/api/private`, and `/download/untrusted` served as an attachment.

> The `bad.js`/`bad.css` endpoints are intentionally misconfigured **only for this lab**. In real applications, fix the MIME types and never serve script/style sources with wrong types; the goal here is observing browser rejection.

### 6.1. Directory Tree

```text
webflux-nosniff-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/NosniffApplication.java
      resources/static/demo.html
    test/
      java/example/NosniffApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'webflux-nosniff-lab'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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

Spring Boot's BOM manages compatible Spring Security, Spring WebFlux, and Reactor versions. This sample excludes `spring-boot-starter-web` (MVC/Servlet). In real products, choose a supported Boot release per your security/maintenance policy; 3.3.13 is pinned here to reproduce the lesson environment.

### 6.4. NosniffApplication.java

Create `src/main/java/example/NosniffApplication.java`:

```java
package example;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class NosniffApplication {

    private static final MediaType JAVASCRIPT =
            MediaType.parseMediaType("text/javascript");

    private static final MediaType CSS =
            MediaType.parseMediaType("text/css");

    public static void main(String[] args) {
        SpringApplication.run(NosniffApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicJson() {
        return Map.of("message", "PUBLIC_OK");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateJson() {
        return Map.of("message", "PRIVATE_OK");
    }

    @GetMapping("/assets/good.js")
    public ResponseEntity<String> goodScript() {
        return ResponseEntity.ok()
                .contentType(JAVASCRIPT)
                .body("document.getElementById('good-script')"
                        + ".textContent = 'GOOD SCRIPT EXECUTED';");
    }

    @GetMapping("/assets/bad.js")
    public ResponseEntity<String> badScript() {
        // Demo only: browser blocks script with wrong MIME.
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("document.getElementById('bad-script')"
                        + ".textContent = 'BAD SCRIPT EXECUTED';");
    }

    @GetMapping("/assets/good.css")
    public ResponseEntity<String> goodCss() {
        return ResponseEntity.ok()
                .contentType(CSS)
                .body("#good-style { color: green; "
                        + "font-weight: bold; }");
    }

    @GetMapping("/assets/bad.css")
    public ResponseEntity<String> badCss() {
        // Demo only: browser blocks CSS with wrong MIME.
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("#bad-style { color: crimson; "
                        + "font-weight: bold; }");
    }

    @GetMapping("/download/untrusted")
    public ResponseEntity<byte[]> downloadUntrusted() {
        // Simulated payload, not read from a real upload.
        byte[] bytes = "<script>alert('not executed')</script>"
                .getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"untrusted.txt\"")
                .body(bytes);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/demo.html", "/assets/**",
                                "/api/public", "/download/untrusted")
                        .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // No headers(...) customization: keep default nosniff.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Important details to understand in the Java code:**

1. `@EnableWebFluxSecurity` and `SecurityWebFilterChain` enable reactive Spring Security; the default header writer adds `X-Content-Type-Options: nosniff`.
2. `ResponseEntity.contentType(...)` sends an explicit MIME type for the four resources rather than relying on the framework to infer it from `.js/.css` controller URL extensions.
3. `goodScript` uses `text/javascript`; `goodCss` uses `text/css`. When the browser fetches them for script/style destinations, the MIME types match.
4. `badScript`/`badCss` return syntactically valid JavaScript/CSS while declaring `text/plain`. With `nosniff`, the browser refuses to execute/apply them in those contexts.
5. `/api/public` returns a `Map` object, which Spring WebFlux/Jackson serializes to JSON with the proper Content-Type rather than `text/plain`.
6. `/api/private` is protected by `anyExchange().authenticated()`, while still receiving security headers on authenticated responses and certain error responses.
7. `/download/untrusted` sets `Content-Type: application/octet-stream` and `Content-Disposition: attachment` so the browser downloads it rather than rendering it as HTML. This is **not** a virus/file scanner; production must also restrict and isolate upload sources.
8. `{noop}learn` is a local demo password only; never use it in production. HTTP Basic requires real HTTPS, strong password hashing, rate limiting, and credential-stuffing protection.
9. `formLogin(...disable())` makes unauthenticated requests receive a 401 Basic challenge rather than a login page redirect.
10. The sample omits `@CrossOrigin`; the demo page and backend share the **same origin `localhost:8080`**. Thus, observed MIME errors are not mixed with CORS errors.

### 6.5. Demo HTML Page

Create `src/main/resources/static/demo.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux X-Content-Type-Options demo</title>
  <link rel="stylesheet" href="/assets/good.css">
  <link rel="stylesheet" href="/assets/bad.css">
</head>
<body>
  <h1>Demo nosniff and MIME types</h1>

  <h2>JavaScript</h2>
  <p id="good-script">GOOD SCRIPT NOT YET LOADED</p>
  <p id="bad-script">BAD SCRIPT DID NOT RUN</p>

  <h2>Stylesheet</h2>
  <p id="good-style">GOOD CSS SHOULD BE GREEN</p>
  <p id="bad-style">BAD CSS SHOULD STAY DEFAULT</p>

  <p>Inspect DevTools Network and Console to verify.</p>

  <script defer src="/assets/good.js"></script>
  <script defer src="/assets/bad.js"></script>
</body>
</html>
```

This HTML shares the backend's origin. Both scripts have `defer` so they run after document parsing. When the browser obeys `nosniff`, the good script changes `good-script`'s text, while the bad script is blocked so `BAD SCRIPT DID NOT RUN` remains unchanged.

For CSS, `good-style` turns green, while `bad-style` does not receive `color: crimson` from the wrong-MIME stylesheet. Other factors besides MIME (CSP, extensions, DevTools cache, proxies) can also affect rendering, so check response headers rather than drawing conclusions from colors alone.

### 6.6. Running the Application

Requires JDK 17+ and Gradle compatible with Spring Boot 3.3.13. In the project directory:

```bash
gradle bootRun
```

If using the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. Without a wrapper, `gradle bootRun` uses your installed Gradle. The example requires no Redis, database, or external services.

Open a browser:

```text
http://localhost:8080/demo.html
```

After loading, observe:

| Resource | Content-Type from backend | nosniff | Result in script/style context |
| --- | --- | --- | --- |
| `/assets/good.js` | `text/javascript` | Yes | Script runs; text "GOOD SCRIPT EXECUTED" |
| `/assets/bad.js` | `text/plain` | Yes | Browser blocks; text "BAD SCRIPT DID NOT RUN" |
| `/assets/good.css` | `text/css` | Yes | Style applies; green text |
| `/assets/bad.css` | `text/plain` | Yes | Browser blocks; mismatched style ignored |
| `/api/public` | `application/json` | Yes | Normal JSON API response |
| `/download/untrusted` | `application/octet-stream` | Yes | Browser prompted to download file |
| `/api/private` (unauthenticated) | Depends on error response | Usually present in chain | 401 Basic challenge, not a MIME error |

These are **expected results** under modern browser behavior; not a live execution record on your machine. Do not write tests asserting exact DevTools error wording, as Chrome/Firefox messages can change.

### 6.7. Where to Look in DevTools?

Open DevTools → **Network** and reload `/demo.html` with appropriate cache settings:

1. Select the `good.js` request. Check Response Headers: `Content-Type: text/javascript`, `X-Content-Type-Options: nosniff`.
2. Select `bad.js`. `Content-Type: text/plain` and `nosniff`. The Console tab should show a refusal to execute the script because its MIME type is not JavaScript.
3. Select `good.css` and `bad.css`. Check both MIME types, then inspect `Computed styles` on the good/bad elements.
4. If neither JS runs, check **Console for CSP/mixed content/CORS** alongside MIME. Do not rush to disable nosniff.
5. If bad JS runs anyway, check browser/DevTools cache, actual response headers, and whether a proxy stripped `nosniff` or rewrote `Content-Type` to JavaScript.
6. If the HTML fails to load, confirm `/demo.html` has `permitAll` and static resource mapping works; routing/401 errors differ from MIME errors.

## 7. Inspecting Response Headers Directly with curl

`curl` displays HTTP headers and bodies, but **does not enforce browser MIME sniffing rules**. Use curl to verify the server configuration, then use a browser to confirm whether scripts/styles actually execute.

### 7.1. Correct vs. Incorrect JS MIME

```bash
curl -i http://localhost:8080/assets/good.js
curl -i http://localhost:8080/assets/bad.js
```

Expected output (abbreviated):

```http
HTTP/1.1 200 OK
Content-Type: text/javascript
X-Content-Type-Options: nosniff

document.getElementById('good-script').textContent = 'GOOD SCRIPT EXECUTED';
```

and:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
X-Content-Type-Options: nosniff

document.getElementById('bad-script').textContent = 'BAD SCRIPT EXECUTED';
```

This shows only the relevant headers/body **with other headers omitted**; actual responses may include `charset` and different header ordering. Seeing JavaScript in the body does not mean a browser will run it: the browser also checks MIME in the `<script>` context.

### 7.2. Correct vs. Incorrect CSS MIME

```bash
curl -i http://localhost:8080/assets/good.css
curl -i http://localhost:8080/assets/bad.css
```

Key difference:

```http
Content-Type: text/css
X-Content-Type-Options: nosniff
```

versus:

```http
Content-Type: text/plain
X-Content-Type-Options: nosniff
```

Stylesheet behavior depends on the actual response. Both URLs may return HTTP 200, yet only the proper MIME allows the browser to apply the styles.

### 7.3. JSON, Private Endpoint, and Download

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/private
curl -I http://localhost:8080/download/untrusted
```

The last command `curl -I` sends **HEAD**; if a route only declares `@GetMapping`, Spring WebFlux typically supports the matching HEAD automatically, though behavior/headers can vary by handler. To inspect the full GET attachment response, run:

```bash
curl -i http://localhost:8080/download/untrusted
```

Expected GET response contains:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="untrusted.txt"
X-Content-Type-Options: nosniff
```

`nosniff` **does not sanitize the body**; it merely stops browsers from guessing the wrong MIME; `Content-Disposition: attachment` directs a download. If a user downloads and opens the file in another application, that application has its own trust boundaries and risks.

## 8. Automated Testing with WebTestClient

Create `src/test/java/example/NosniffApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class NosniffApplicationTests {

    private static final String NOSNIFF = "X-Content-Type-Options";

    @Autowired
    WebTestClient client;

    @Test
    void publicJsonHasCorrectTypeAndNosniff() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        value -> assertTrue(
                                value.startsWith("application/json")))
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }

    @Test
    void correctJavaScriptMimeKeepsNosniff() {
        client.get().uri("/assets/good.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("text/javascript")))
                .expectBody(String.class)
                .isEqualTo(
                    "document.getElementById('good-script')"
                    + ".textContent = 'GOOD SCRIPT EXECUTED';");
    }

    @Test
    void mislabeledJavaScriptStillHasNosniff() {
        client.get().uri("/assets/bad.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("text/plain")))
                .expectBody(String.class)
                .isEqualTo(
                    "document.getElementById('bad-script')"
                    + ".textContent = 'BAD SCRIPT EXECUTED';");
    }

    @Test
    void correctCssIsTextCss() {
        client.get().uri("/assets/good.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/css")));
    }

    @Test
    void mislabeledCssIsPlainTextAndNosniff() {
        client.get().uri("/assets/bad.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/plain")));
    }

    @Test
    void demoHtmlIsServedThroughSecurityChain() {
        client.get().uri("/demo.html")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/html")));
    }

    @Test
    void privateApiNeedsBasicCredentials() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void authorizedPrivateJsonStillHasNosniff() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectBody()
                .jsonPath("$.message").isEqualTo("PRIVATE_OK");
    }

    @Test
    void untrustedDataDownloadUsesAttachment() {
        client.get().uri("/download/untrusted")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("application/octet-stream")))
                .expectHeader().value(
                        HttpHeaders.CONTENT_DISPOSITION,
                        value -> assertTrue(
                                value.startsWith("attachment;")));
    }
}
```

Run:

```bash
gradle test
```

**What these tests verify:**

- Spring Security WebFlux emits `X-Content-Type-Options: nosniff` through the security chain on public, private, static, and download resources.
- The **correct** and **incorrect** MIME types for JS/CSS are returned exactly as intended by the demo, without Spring rewriting them by sniffing.
- The JSON API returns the right type and authentication is verified independently.
- Downloads include `Content-Disposition: attachment`, not merely nosniff.

**Limitation:** `WebTestClient` **is not a browser**. It does not execute `<script>`, render CSS, or apply browser MIME sniffing algorithms. Passing header tests **does not prove by itself** that a script is blocked in Chrome/Firefox. Combine WebTestClient with real browser or browser-automation testing for script/style scenarios.

**Do not assert exact timestamps or DevTools messages.** Console warnings depend on browser/version; what needs verification are the resource destination, server MIME type, nosniff header, and whether scripts/styles executed.

## 9. Behavior Matrix: Same Body, Different Headers

Assume the body contains valid JavaScript.

| Response Content-Type | X-Content-Type-Options | Browser context | Key outcome |
| --- | --- | --- | --- |
| `text/javascript` | `nosniff` | `<script src>` | May execute if CSP/network/auth allow |
| `application/javascript` | `nosniff` | `<script src>` | Also an accepted JavaScript MIME type; modern standards recommend `text/javascript` |
| `text/plain` | `nosniff` | `<script src>` | Blocked due to wrong MIME |
| `application/json` | `nosniff` | `<script src>` | Blocked because not a JavaScript MIME |
| Missing Content-Type header | `nosniff` | `<script src>` | Must not rely on browser guessing to run scripts |
| `text/javascript` | no `nosniff` | `<script src>` | May execute; lacks protection for other resources |
| `text/plain` | no `nosniff` | Classic script | Behavior can vary by browser; never rely on sniffing to run scripts |
| `text/plain` | `nosniff` | Direct navigation | Browser should not sniff bytes as HTML |
| `text/html` containing user-authored content | `nosniff` | Direct navigation | Still active HTML content; nosniff **does not neutralize properly typed HTML** |
| `application/octet-stream` + attachment | `nosniff` | Direct navigation | Encourages download; depends on browser and other policies |

Do not treat this table as an absolute test engine for every browser and resource type. **Request destination, CSP, crossorigin mode, browser version, and media type parsers** all matter. The most important rule to remember is **script/style destination with mismatched MIME + nosniff → browser refuses**.

## 10. File Uploads: Where nosniff Helps, Yet Remains Insufficient

Systems allowing uploads of images, documents, PDFs, logs, CSVs, or HTML fragments are common places where MIME confusion arises.

### 10.1. Dangerous Data Flow

```text
Client upload:
  filename: contract.png
  Content-Type: image/png      (client-supplied)
  bytes: <html><script>...</script></html>

Server:
  stores raw bytes
  serves at https://app.example.test/files/contract.png
  trusts client-supplied extension/Content-Type

Browser:
  if resource is treated as HTML/JS under the app origin,
  can cause XSS or unintended active content
```

**Client Content-Type and file extensions are untrusted input.** If a server echoes those values directly as response headers, an attacker can make the server send `text/html` or `text/javascript` for an unvetted file. Once the header declares an active MIME type, `nosniff` cannot make it harmless.

### 10.2. Minimum Policy for Handling Uploads

1. **Allowlist formats** matching business requirements; reject unsupported types.
2. **Inspect actual content** with a reputable parser/decoder; never rely solely on filename or client MIME.
3. **Limit size**, file count, nesting/decompression bombs, request rate, and quotas.
4. **Rename stored files** with server-generated IDs to avoid path traversal; never use user-supplied names directly in filesystem paths.
5. **Host on a separate domain without main-app session cookies** when users can download or view untrusted content; consider a domain with a restrictive CSP.
6. **Set standard Content-Type** for verified data; never reflect multipart `Content-Type` blindly.
7. For files not needing inline preview, set **`Content-Disposition: attachment`**; use `application/octet-stream` or an appropriate verified type.
8. **Set `X-Content-Type-Options: nosniff`** on responses so browsers do not guess improperly.
9. For HTML/SVG that genuinely must be displayed, consider sanitization, CSP sandboxing, separate domains, and signed/authorized URLs.
10. **Scan for malware** per your threat model on PDF/Office/archives, and enforce access/TTL controls for private files.
11. Enforce per-user/resource access control; nosniff does not decide who may download a file.
12. Do not assume a one-time check suffices if files can be modified in object storage after approval.

### 10.3. When to Use attachment?

Example server response for an untrusted text file:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="review.txt"
X-Content-Type-Options: nosniff
```

The browser is instructed to download it rather than render it as an HTML page under the application's origin. For business cases requiring preview, generate a **sanitized preview** and serve it from an appropriate trust boundary. A safe policy never relies solely on "the extension looks like .txt".

### 10.4. Limitation of nosniff on Valid HTML

If a server serves:

```http
Content-Type: text/html
X-Content-Type-Options: nosniff
```

and the body is HTML containing attacker-supplied `<script>`, it is still HTML, and the browser can execute scripts subject to other policies. Thus the claim **"nosniff is enabled so HTML uploads are safe"** is false. You also need sanitization, CSP, sandboxing, or origin isolation—or forbid HTML uploads if business requirements don't need them.

### 10.5. SVG, PDF, and Other Active Formats

`image/svg+xml` is an XML vector format capable of active content depending on how it is used; do not equate it with static PNG/JPEG. PDFs and Office files can embed complex or active structures. `nosniff` does not perform safe parsing for them. Design uploads/downloads around true file types and properly sandboxed viewers.

## 11. When the Browser Reports "Refused to execute script"

The message may look like:

```text
Refused to execute script from ... because its MIME type
('text/plain') is not executable, and strict MIME type
checking is enabled.
```

**Diagnostic steps:**

1. Open DevTools **Network** and select the exact rejected request.
2. Confirm whether the status is **200/304** or **404/302/401/500**. Many SPAs return `index.html` with `Content-Type: text/html` for a non-existent `.js` URL; the browser blocks it because HTML is not JavaScript.
3. Check **Response Headers → Content-Type**. Scripts require a JavaScript MIME type; stylesheets require `text/css`.
4. Check whether **X-Content-Type-Options** is `nosniff`. If so, that proves the browser was instructed not to sniff. Do not "fix" it by deleting the header.
5. Check the **Response body**: if the body is login HTML, a JSON error, or an nginx 404 page, the issue is routing/security/rewrites, not JS content.
6. Inspect the **Request URL** across reverse proxies and deployment base paths. The app may request `/assets/app.js` while the actual file lives at `/app/assets/app.js`.
7. Check **object storage/CDN Content-Type metadata**. `.js` files must be uploaded with accurate metadata or mapped properly by the gateway.
8. If using JS modules, check strict MIME and module CORS/CSP rules rather than assuming classic-script behavior.
9. For CSS, check whether the response is an HTML error page. A CSS URL redirected to login can appear with MIME `text/html`.
10. Reload after fixing CDN/cache, using versioned asset URLs if necessary to avoid receiving stale wrong headers from cache.
11. Check Console CSP errors **separately from MIME errors**. If CSP blocks a script from another source, fix CSP/loading sources instead of disabling nosniff.
12. Use `curl -I`/`curl -i` to inspect responses at each hop; final browser testing confirms script/style execution.

### 11.1. When Content-Type Is text/html for a JS URL

A very common SPA scenario:

```text
Browser requests:
  GET /static/app-123.js

Server fallback route:
  returns index.html
  Content-Type: text/html

Result:
  browser blocks JS; Console MIME type ('text/html') error
```

Fix the **static asset mapping or rewrite rule**; do not change `index.html`'s `Content-Type: text/html` to `text/javascript` to "fool" the browser. Nor should you disable security headers. Ensure missing assets return 404 rather than HTML bodies under JS URLs when serving JS.

### 11.2. Proxy Sending application/octet-stream for JS

Some servers fall back to `application/octet-stream`. For scripts/styles, that is not a type browsers expect when `nosniff` is enabled. Fix the proxy/static server's MIME mapping, e.g., `.js → text/javascript`, `.css → text/css`. Never write a global WebFilter converting **every** octet-stream into JavaScript; that could turn arbitrary binaries/uploads into dangerous active content.

### 11.3. MIME Errors Caused by 401/403/404 Responses

A `<script src>` may receive 401 JSON or a 302 redirect to an HTML login page. The browser refuses to run the error body as JavaScript. That is good behavior. What needs fixing is the **asset route, authentication policy, or proper asset loading path**, not nosniff.

### 11.4. 304 Cache and Headers

With `304 Not Modified`, browsers combine metadata/headers from the earlier cached response. Debugging may show that not every header appears on a 304 identically to a 200, so inspect the original 200 response, cache metadata, and CDN. If an asset was cached with a wrong MIME type, refresh metadata/URLs properly; do not conclude from a single 304 trace that the browser ignores nosniff.

## 12. Spring WebFlux: Where to Set Content-Type

### 12.1. Controller Returning JSON

```java
@GetMapping(value = "/api/report",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<ReportResponse> report() {
    return service.loadReport();
}
```

This is a **code snippet** requiring `ReportResponse` and `service`; it can return DTOs/Maps via Jackson when the appropriate codec is configured. `produces` lets WebFlux content negotiation apply the proper JSON media type.

Never return a JSON body with `Content-Type: text/javascript` just so a client can embed it with `<script>`. JSONP/cross-origin script inclusion is a legacy pattern with distinct risks; use CORS and proper authentication for JSON APIs.

### 12.2. Controller Returning Text

```java
@GetMapping(value = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> plain() {
    return Mono.just("<h1>This is just text</h1>");
}
```

With `nosniff` and `text/plain`, standard browser behavior will not treat `<h1>` as HTML during navigation. When real HTML rendering is required, send `text/html` only for **trusted or sanitized** content.

### 12.3. Static Assets on the Classpath

Spring Boot WebFlux can serve static resources from `classpath:/static/`. It normally infers MIME types via resource filenames/`MediaTypeFactory`. Yet do not assume every new file extension or CDN proxy has the right mapping.

Example:

```text
src/main/resources/static/
  demo.html
  css/app.css
  js/app.js
  images/logo.png
```

Each asset needs an accurate response Content-Type. For uncommon extensions or binary downloads, configure resource handlers/metadata properly instead of disabling nosniff. When static content lives on a separate CDN, **the component actually serving the response** must emit the proper headers.

### 12.4. WebFilter Writing Responses Directly

A `WebFilter` can write a body directly:

```java
// Illustrative snippet — not a standalone WebFilter.
ServerHttpResponse response = exchange.getResponse();
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
response.getHeaders().set(
        "X-Content-Type-Options", "nosniff");
response.setStatusCode(HttpStatus.BAD_REQUEST);
return response.writeWith(
        Mono.just(response.bufferFactory().wrap(
                "Bad request".getBytes(StandardCharsets.UTF_8))));
```

This snippet requires the corresponding WebFlux imports/variables; it illustrates a filter that *owns the response*. When the default security header writer is already active, **you do not need to manually inject nosniff in every handler**, except when a custom filter sits outside the chain and writes its own response. Never write the body and then continue calling `chain.filter(exchange)`; that can cause double writes or committed-response errors.

### 12.5. Responses When Errors Occur After Commit

If the server has already started streaming a 200 response and an error occurs, status/headers cannot always be changed after commit. `nosniff` must be set **before the response commits**, via an appropriate writer/filter. Security headers should therefore be applied early in the response lifecycle rather than waiting until after body data is sent.

## 13. Security Chains, Error Responses, and HTTPS

### 13.1. PermitAll Does Not Omit Headers

`.pathMatchers("/assets/**").permitAll()` lets clients fetch static assets without logging in. Spring Security can still add security headers to those requests. If public endpoints lack `nosniff` while private ones have it, check **`securityMatcher`/chain selection**, not just controller annotations.

### 13.2. Multiple SecurityWebFilterChain Beans

Suppose:

```text
Order 1: /api/**      -> Resource Server/Bearer
Order 2: /assets/**   -> public/static
Order 3: /**          -> form login
```

Each chain can configure headers independently. `WebFilterChainProxy` selects the first matching chain; a chain dedicated to static assets might accidentally call `headers(...disable())` or be bypassed. Then JS/CSS receive different headers from the API.

**Test each URL group**, including:
- JS/CSS from the static security chain;
- public/private JSON APIs;
- HTTP 401/403 error responses;
- file downloads;
- unmatched paths;
- responses generated or blocked by a gateway/CDN.

If requests hit a **separate domain** not running Spring Security, configure the headers directly at that origin/proxy. Never assume Spring Security headers automatically apply across every hop.

### 13.3. nosniff and HSTS Do Two Different Jobs

**HTTPS** encrypts traffic. `Strict-Transport-Security` (HSTS) instructs the browser to return over HTTPS for that host after receiving the policy on a valid connection. `X-Content-Type-Options: nosniff` governs how the browser handles media types. The two mechanisms complement rather than replace each other.

In Spring Security, HSTS is sent based on HTTPS conditions and security config. Observing no HSTS when curling local HTTP `localhost:8080` **does not prove nosniff is missing**; verify each header individually. Production requires TLS, domain-appropriate HSTS, valid HTTP→HTTPS redirects, certificate trust, and accurate reverse-proxy forwarded headers.

### 13.4. CORS Is Not a Fix for MIME Errors

A script may be blocked by CORS (especially cross-origin module scripts) or by MIME, CSP, network, or authorization. Enabling `@CrossOrigin("*")` will not turn `text/plain` into JavaScript. Check Console/Network to identify **which layer failed** before applying a fix.

### 13.5. CSRF Does Not Solve MIME Confusion

CSRF protection prevents certain forged state-changing requests when browsers attach credentials automatically. It does not replace nosniff. Conversely, nosniff does not protect POST endpoints from CSRF. Both should be present where the threat model requires them.

## 14. Operations and Change Control

### 14.1. Checklist for APIs and Assets

1. **Security defaults:** Is Spring Security WebFlux active with `contentTypeOptions` enabled?
2. **Accurate MIME:** `.js → text/javascript`, `.css → text/css`, JSON → `application/json`, trusted HTML → `text/html`.
3. **Static resources:** Do not redirect unauthenticated JS/CSS to login HTML; do not return `index.html` for missing JS files.
4. **Uploads:** Validate bytes, MIME, extensions, size, allowed formats, and storage path; never reflect client MIME directly.
5. **Previews:** Never render untrusted HTML/SVG on a high-privilege origin without sandboxing/sanitization.
6. **Downloads:** Include `Content-Disposition: attachment` when downloading is intended; use an appropriate MIME type.
7. **Authorization:** Private files and APIs still enforce user/resource checks; nosniff is not an ACL.
8. **Proxy/CDN:** Preserve or add `X-Content-Type-Options: nosniff` consistently without overwriting Content-Type incorrectly.
9. **Caching:** After fixing MIME types, purge/invalidate caches or bump versioned asset names; verify 200/304.
10. **Error responses:** Check 401/403/404/500 for required headers along real code paths; avoid leaking login HTML into JS URLs.
11. **Browser tests:** Verify Chrome/Firefox actually block `bad.js`/`bad.css` and execute `good.js`/`good.css`.
12. **Automated tests:** `WebTestClient` verifies headers/status; never assume it simulates a browser.
13. **Content-Security-Policy:** Review `script-src`/`style-src` and related rules whenever active content exists.
14. **HTTPS/HSTS:** Verify transport security and MIME policy separately; nosniff does not replace TLS.
15. **Monitoring:** Track static/script load failures, Content-Type drift, 404 assets, browser errors, and scanner findings.

### 14.2. Regression Testing on Upgrades

Whenever upgrading Spring Boot/Spring Security, changing CDNs/static servers, or migrating to WebFlux functional endpoints, re-run:

- Default `X-Content-Type-Options` tests;
- JS/CSS MIME tests on 200 and error responses;
- Static resource mapping / `index.html` fallback tests;
- Multiple security chain tests;
- Uploaded file download/sandbox policy tests;
- Proxy/canonical hostname response tests;
- Browser behavior tests for module scripts, CSP, and MIME handling.

**Do not rely solely on a single-header scanner PASS.** A scanner seeing `nosniff` may still miss a server returning `text/html` for dangerous uploads or allowing unauthorized file downloads.

### 14.3. Safe CDN/Reverse Proxy Configuration

For CDN-served assets, ensure:

```http
Content-Type: text/javascript
X-Content-Type-Options: nosniff
Cache-Control: public, max-age=...
```

The `...` only illustrates a cache policy; do not copy it verbatim into a real header. Hash-named static files can use long caches on versioned URLs. Still, **Content-Type and nosniff are mandatory accurate metadata**, independent of cache TTL.

If a CDN returns an HTML 404 for a JS URL, fix routing/status and content type; never force every response under `/js/**` to JavaScript when the actual body is an HTML error page.

### 14.4. Establishing a Security Header Baseline

Define a control contract:

```text
Every protected app/proxy response must:
  - include X-Content-Type-Options: nosniff
  - declare a Content-Type matching the body (or no body when appropriate)
  - avoid leaking stack traces/secrets in error pages
  - include appropriate Content-Disposition for downloads
  - adhere to resource-specific CSP, HSTS, CORS, and cache policies
```

This is a general baseline; exceptions like `204 No Content`, `304 Not Modified`, or out-of-chain components can occur and should be evaluated per HTTP semantics. Avoid forcing `Content-Type: application/json` onto every body just to appease a scanner.

## 15. Common Mistakes and Fixes

| Mistake | Why is it wrong? | How to handle it |
| --- | --- | --- |
| Disabling `nosniff` so wrong-MIME JS runs | Removes protection | Fix `Content-Type` on JS and static server |
| Treating `nosniff` as a virus scanner | Does not inspect malicious payloads | Validate, scan, sanitize, restrict uploads |
| Returning untrusted HTML as `text/html` assuming nosniff suffices | Browser is explicitly told it is HTML | Isolate domain/sandbox/sanitize/attachment |
| Using `application/json` for `<script src>` | Not a JavaScript MIME type | Serve proper JS or fetch JSON via `fetch` |
| Using `text/plain` for CSS | Style destination requires `text/css` | Fix CSS MIME type |
| Trusting file extensions or upload Content-Type | Clients can spoof them | Inspect actual file contents on the server |
| Using `application/octet-stream` for all responses | JS/CSS/browsers cannot handle properly | Choose media type per resource |
| Replacing every 404 with `index.html` | Missing JS assets fail as HTML MIME errors | Restrict SPA fallback to navigation routes |
| Assuming status 200 = script executed | Browsers still check MIME/CSP/CORS | Inspect browser Console/Network |
| Assuming WebTestClient simulates nosniff | HTTP client has no browser enforcement | Test in Chrome/Firefox/browser automation |
| Mistaking CORS errors for nosniff errors | Two distinct mechanisms | Identify the exact failing layer in DevTools |
| Adding headers manually in every controller | Easy to miss static/error responses | Use security defaults or unified proxy policy |
| Header appears on API but not CDN | Different origin/response owner | Configure CDN/proxy properly |
| Dropping `nosniff` on 401/403/500 | Can expose how browsers handle error bodies | Check security chains and global error handling |
| Relying on browser sniffing to "fix" asset loading | Unreliable behavior, higher risk | Set accurate MIME headers and versioned assets |

## 16. Self-Check Questions

**1. What does X-Content-Type-Options: nosniff tell the browser to do?**  
Respect the declared Content-Type rather than guessing under restricted cases; notably, it **blocks scripts/styles** with mismatched MIME types.

**2. If the body is valid JavaScript but the server returns Content-Type: text/plain with nosniff, will `<script src>` execute?**  
No, modern browsers refuse execution in a script destination due to the wrong MIME type.

**3. If the body is CSS but the server returns text/plain with nosniff, will the browser apply the styles?**  
No; stylesheet destinations require `text/css`.

**4. Does enabling nosniff help browsers automatically determine the right MIME when the server omits it?**  
No. The header **does not fix Content-Type**; it only restricts sniffing. The server must declare the right type.

**5. Why might `/assets/app.js` return 200 yet leave the page blank?**  
The response might be an HTML fallback/login page, JSON error, or `text/plain` instead of JavaScript, so the browser blocks the script despite HTTP 200.

**6. Does nosniff prevent XSS if a server returns user-uploaded HTML with Content-Type: text/html?**  
No. That HTML remains active content under the declared MIME; isolation, sanitization, CSP/sandboxing, or attachment handling is still required.

**7. Does nosniff replace authentication/authorization for private files?**  
No. It knows nothing about users, roles, or owners; the backend must still enforce access controls.

**8. Does Content-Disposition: attachment do the same job as nosniff?**  
No. Attachment encourages downloading; nosniff restricts browser MIME inference. Both may be needed.

**9. In Spring Security WebFlux, must you configure headers(...) manually to get nosniff?**  
No. Spring Security enables Content-Type Options by default; no extra configuration is needed unless disabled.

**10. Is switching from ServerHttpSecurity to HttpSecurity the way to customize nosniff in WebFlux?**  
No. `ServerHttpSecurity` is the reactive WebFlux DSL; `HttpSecurity` belongs to Servlet.

**11. Why use text/javascript rather than application/octet-stream for JS?**  
Script destinations require a JavaScript MIME type. `application/octet-stream` is not a script type browsers will execute when nosniff is enabled.

**12. Why doesn't a passing WebTestClient header test prove the browser blocks bad.js?**  
Because WebTestClient inspects HTTP responses without executing scripts/styles or browser sniffing rules. Separate browser testing is required.

**13. How do CSP and nosniff differ?**  
CSP restricts origins and usage of active resources; nosniff restricts MIME interpretation. They are complementary layers.

**14. Does HSTS turn text/plain JS into JavaScript?**  
No. HSTS governs HTTPS; MIME types must still be accurate.

**15. Can we set Content-Type: text/html on every endpoint so browsers always display it?**  
No. That is wrong for JSON/JS/CSS/downloads and can increase XSS risk. Choose the proper type per resource.

**16. If an uploaded file is named avatar.png yet its bytes are HTML, what should you do?**  
Never trust the filename or client MIME; validate actual contents, reject invalid formats, isolate upload domains, and apply proper headers/policies.

**17. When JavaScript is served from a separate CDN domain, does backend Spring Security set headers on the CDN response?**  
No. Headers must be configured on the component **actually serving the response**, such as the CDN/object storage/reverse proxy.

**18. Why can Content-Type text/plain + nosniff be useful for untrusted text data?**  
Because browsers will not automatically infer bytes containing HTML tags into an active HTML page in contexts controlled by the header.

**19. Should you disable nosniff when the browser reports a MIME error?**  
No. Inspect the exact request URL, actual response body, and asset Content-Type.

**20. Does a JSON fetch API response with nosniff guarantee valid JSON and no data leaks?**  
No. JSON parsing, CORS, authentication, authorization, and data protection remain separate responsibilities.

**Remember:** In Spring Security reactive, **keep `X-Content-Type-Options: nosniff` enabled**, serve every resource with an **accurate `Content-Type`**, use `Content-Disposition`/separate domains/sanitization for untrusted uploads, and test with **browsers + WebTestClient**. If a script/style is blocked, fix **the MIME type at the source**, never weaken security policies to hide configuration bugs.

## References

- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): `nosniff` syntax, script/style blocking, and other MIME contexts.
- [MDN — MIME Type Verification](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/MIME_types): protecting scripts/styles, MIME sniffing, and proper Content-Type recommendations.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media types, charset, and differences between Content-Type and Content-Encoding.
- [WHATWG — MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/): MIME determination from responses and interaction with browser rules.
- [WHATWG — Fetch Standard](https://fetch.spec.whatwg.org/): request destinations, `nosniff`, CORS, and fetch behavior.
- [Spring Security — Default Security HTTP Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): default security headers and `X-Content-Type-Options: nosniff`.
- [Spring Security — HTTP Response Headers in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html): `ServerHttpSecurity.headers(...)`, default Content-Type Options, and disabling.
- [Spring Security — ServerHttpSecurity.HeaderSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html): reactive `contentTypeOptions(...)`.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [Spring Framework — WebFlux Static Resources](https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-static-resources): resource handling, caching, and MIME mappings.
- [MDN — Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition): download vs. inline semantics.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): allowlisting, validation, storage isolation, and safe upload handling.
