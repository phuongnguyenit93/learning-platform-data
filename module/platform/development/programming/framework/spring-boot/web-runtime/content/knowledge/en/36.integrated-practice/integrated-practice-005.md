# Serving UI Views, Versioned Static Assets, and Cache Policies in Spring Boot

## 1. Integrated Practice and Required Output

Suppose a Spring Boot service serves **HTML pages** for users as well as **CSS, JavaScript, images**, and a few **JSON APIs**. Across deployments, CSS and JS content can change. Browsers may cache a file for minutes, months, or a year; CDNs and reverse proxies maintain caches of their own. Applying the exact same cache policy to every URL invites two opposite failures:

- **Caching too weakly:** on every page load, the browser re-fetches unchanged CSS/JS, increasing latency and bandwidth.
- **Caching too aggressively on unversioned URLs:** after deploying new HTML, the browser keeps stale CSS; the UI breaks, client JavaScript mismatches the API, or clients get stuck after a rollback.

An even worse bug: a **personalized** HTML or API response gets cached by a shared CDN because `Cache-Control: public` was applied carelessly.

This lesson belongs to **Integrated Practice** in the **Spring Boot - web-runtime** module. The goal is to build a mini Spring Boot website using **Java 17+, Spring Boot 3.3.13, Spring MVC + Thymeleaf** with concrete contracts:

1. `GET /` returns HTML with `Cache-Control: no-cache` (a shared demo HTML page containing no personal data).
2. The HTML references CSS/JS using **content-hashed paths**, e.g. `/assets/css/site-<md5>.css`, without hardcoding hashes.
3. Valid hashed asset URLs return `Cache-Control: public, max-age=31536000, immutable`.
4. **Unversioned** asset URLs (if still reachable) return `Cache-Control: no-cache` to prevent stale version caching.
5. `GET /api/catalog` returns JSON with an `ETag` validator and revalidation policy; sending a matching `If-None-Match` returns `304 Not Modified` with an empty body.
6. `GET /api/account-preview` demonstrates responses that must not be stored by shared or private caches using `Cache-Control: private, no-store`.
7. Includes **real embedded-server integration tests** (`@SpringBootTest(RANDOM_PORT)` and JDK `HttpClient`), not just controller unit tests.
8. Includes a CDN/NGINX/SPA deployment checklist and a **multi-build asset change test** to catch stale caching.

**Important:** this example is a demo focused on headers and the resource chain; it omits authentication, CSRF, production CSP, and user-specific business state. Never expose `/api/account-preview` with real user data without Spring Security and authorization. The tests are designed to run cleanly; this document does not claim Gradle/HTTP was executed in the authoring environment.

## 2. Four Easily Confused Cache Layers

```text
                    GET /
Browser
 ├── HTTP cache: HTML/JS/CSS, ETag, max-age
 └── Service worker Cache Storage (if the app has one)
           │
           ▼
CDN / reverse proxy
 └── Shared HTTP cache: s-maxage, public/private, Vary, cache key
           │
           ▼
Spring Boot embedded server
 ├── ResourceHttpRequestHandler serving static files
 ├── Resource chain resolver/cache (in JVM)
 ├── Thymeleaf template cache (compiled template)
 └── @Cacheable/application data cache (if present)
           │
           ▼
DB / Object storage
```

| Cache Layer | Example | Directly Controlled by HTTP Cache-Control? |
|---|---|---|
| Browser HTTP cache | Stores CSS/JS/HTML responses | **Yes**, per HTTP caching semantics |
| CDN / reverse proxy cache | Caches shared responses at the edge | **Yes**, combined with CDN-specific rules |
| Service Worker Cache Storage | `caches.open("v5")` | **Not automatically**; controlled by service worker JS code |
| Spring MVC resource chain cache | `spring.web.resources.chain.cache=true` | **Not directly**; internal resolution/metadata cache |
| Thymeleaf template cache | `spring.thymeleaf.cache=true` | **No**; caches parsed templates, not browser responses |
| Spring Cache abstraction | `@Cacheable` for services/data | **Not automatically**; completely separate from HTTP response caching |

Any strategy to prevent stale UIs must know **which layer it is controlling**. `spring.thymeleaf.cache=false` lets developers see template edits faster, yet **does not make browsers drop cached JavaScript**. `@CacheEvict` clearing a Redis key does not evict CSS cached in a browser. `spring.web.resources.chain.cache` speeds up internal resolution, not `Cache-Control`.

## 3. Why URLs Need Versions

Suppose a file has a fixed path:

```text
/assets/css/site.css
```

On day 1 the CSS is blue; on day 2 it turns purple. If a browser cached `/assets/css/site.css` with `max-age=31536000`, it may keep using the blue stylesheet until freshness expires; deploying new code **does not force browsers to reload** a URL that is still fresh.

A better strategy:

```text
Day 1: /assets/css/site-a1b2...c3d4.css
Day 2: /assets/css/site-9f8e...7a6b.css
```

These names **illustrate the format only**, not the actual hash of the demo file. When content changes, the URL changes; browsers treat it as a brand-new resource and download the new version. Old hashed files remain safe to cache long-term because each URL maps to immutable bytes.

Two distinct approaches exist:

- **Content-based version:** a hash computed from file bytes, e.g. Spring Framework's `ContentVersionStrategy` uses a 32-character hex **MD5** in the URL. Unchanged bytes → unchanged hash; changing one byte → different hash.
- **Fixed version:** prepending a release label, e.g. `/v2026-11-08/js/app.js`, rotated per release. This fits some JavaScript module loaders or build pipelines generating release-scoped URLs/manifests.

**Content hashes exist for cache invalidation**, not security integrity or authentication against tampering: MD5 URL versioning is not equivalent to signature verification or `Subresource Integrity` (SRI). For assets from third-party CDNs, consider `integrity="sha384-..."`, `crossorigin`, and an appropriate CSP.

### 3.1. Critical Contract

For long-lived immutable caching, **a hashed URL must never serve altered bytes**. Never reuse the same `site-a1...css` path for modified content. Treat hashed assets as immutable artifacts in object storage or a CDN.

After deployment, new HTML points to the new URLs; previously cached HTML in browsers can still point to old hashed assets. Therefore, **retain assets from prior releases during a rollout/rollback window** or serve them via CDN/object storage. If a new deployment drops old assets immediately, clients holding older HTML can hit 404s when fetching old hashed URLs.

## 4. Cache-Control: no-cache, no-store, private, public, and immutable

A response may carry:

```http
Cache-Control: public, max-age=31536000, immutable
```

Practical meaning of the directives:

| Directive | Practical Meaning |
|---|---|
| `max-age=600` | Response stays fresh for up to 600 seconds per HTTP caching rules |
| `public` | Shared caches may store it when other conditions permit; **use only for truly shared data** |
| `private` | Only a single user agent's private cache may store it; shared CDNs must not |
| `no-cache` | **May be stored**, but must not be reused without revalidating with the origin |
| `no-store` | Compliant caches must not store the response; fits sensitive content |
| `must-revalidate` | Once stale, do not serve again without successful revalidation per RFC rules |
| `immutable` | While fresh, supporting clients skip conditional revalidation because the URL denotes immutable content |
| `s-maxage=...` | Freshness lifetime for shared caches, overriding browser max-age |
| `stale-while-revalidate=...` | Allows caches to serve stale content briefly while revalidating asynchronously |
| `Vary: Accept-Encoding` | Incorporates request headers into the cache key to separate gzip/br/identity variants |

**`no-cache` is not `no-store`.** That is the most common misconception: `no-cache` permits storage with mandatory revalidation before reuse, whereas `no-store` forbids storing altogether. Shared catalog HTML can use `no-cache`; an admin page carrying tokens/PII calls for `private, no-store`. Note that newly adding `no-store` **does not purge data already cached under an earlier policy**; handle migration/cache purges carefully.

**Never slap `public` onto responses with `Set-Cookie`, Authorization, user IDs, shopping carts, or private documents.** Shared caches can leak user A's response to user B if cache keys and policies are wrong.

### 4.1. Recommended Policy Matrix

| Resource Kind | URL | Suggested Policy | Reason |
|---|---|---|---|
| Public website HTML | `/` | `no-cache` | Revalidate on every navigation so stale UIs aren't kept |
| Personal HTML / account page | `/me` | `private, no-store` | Never store sensitive data |
| Fingerprinted CSS/JS/images | `/assets/site-<hash>.css` | `public, max-age=31536000, immutable` | URL changes whenever bytes change |
| Unfingerprinted CSS/JS | `/assets/site.css` | `no-cache` or very short freshness | Avoid stale assets across deploys |
| Shared JSON catalog | `/api/catalog` | `public, max-age=0, must-revalidate` + ETag | Revalidation saves response bodies |
| Token / profile JSON | `/api/profile` | `private, no-store` | Protect privacy |
| Health / readiness | `/actuator/health/readiness` | Typically uncached or infra-defined | Avoid stale health status |
| Permanent redirects `301/308` | Canonical URL | Strictly controlled | Browsers/proxies cache permanent redirects long-term |
| Errors 404/5xx | Varies | Avoid accidental caching | CDNs may apply negative caching/overrides |

This is an **illustrative policy**. High-traffic public APIs might use `s-maxage=60` with browser revalidation; real-time pages may need `no-store`; unversioned assets should never receive long immutable caching unless the path truly never changes.

## 5. How Spring Boot 3.3 Serves Static Resources

With Spring Boot MVC auto-configuration, static resources are looked up from:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

In this demo project we use `src/main/resources/static/`. Placing:

```text
src/main/resources/static/assets/css/site.css
src/main/resources/static/assets/js/app.js
```

exposes the unversioned URLs (with default resource mappings enabled):

```text
/assets/css/site.css
/assets/js/app.js
```

Important properties:

```properties
# Enable resolver chain; may also auto-enable when a strategy is enabled.
spring.web.resources.chain.enabled=true

# Generate paths with MD5 content hash:
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**

# Optimize internal JVM resolver cache; NOT an HTTP TTL:
spring.web.resources.chain.cache=true
```

Per Spring Boot **3.3 Servlet Web Applications**, Thymeleaf and FreeMarker auto-configure `ResourceUrlEncodingFilter` so URLs generated by templates are rewritten through the resource chain. JSP requires explicit filter registration per docs; other template engines need dedicated helpers/macros or `ResourceUrlProvider`.

**Never hardcode MD5 hashes into HTML templates.** In Thymeleaf:

```html
<link rel="stylesheet" th:href="@{/assets/css/site.css}">
<script defer th:src="@{/assets/js/app.js}"></script>
```

At runtime, resources pass through the content strategy and rewrite to `/assets/css/site-<32-hex>.css`. Requests to those rewritten paths are resolved back to the original file by `ResourceHttpRequestHandler`/`VersionResourceResolver`. If a template outputs `href="/assets/css/site.css"` directly (bypassing URL rewriting), browsers fetch the unfingerprinted path and long-term caching will cause bugs.

**Note on CSS/ES modules:** CSS `url(...)` references and JavaScript dynamic imports/module loaders can require separate transformation pipelines. Spring docs note exceptions in `ContentVersionStrategy` for JavaScript module loaders; use build manifests or a fixed version strategy and test deep imports where needed. This demo intentionally uses one plain CSS file and one JS file without claiming every nested reference is rewritten automatically.

### 5.1. Spring Boot's HTTP Cache Properties Apply Globally to the Static Resource Handler

For example:

```properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
```

These properties apply to the **Boot-configured static resource handler**, which usually **includes unhashed URLs too** if served by the same handler. Only enable 365 days globally if all unversioned paths are blocked or their risks are accepted.

In the demo below, we **do not** set global `spring.web.resources.cache.cachecontrol.max-age=365d`. Instead, a **filter checks whether the URL matches the exact content fingerprint computed by the resource chain**; only matching fingerprinted URLs receive long cache lifetimes. This cleanly teaches the two-tier policy. For large production apps with hundreds of assets, prefer a build manifest + CDN rules or dedicated ResourceHandlers to avoid per-request hash lookups.

## 6. Practice Project Architecture

We create a Spring Boot MVC + Thymeleaf project with:
- `HomeController` returning the view with `Cache-Control: no-cache`.
- `CatalogController` (`ApiController`) returning JSON with `ETag` and revalidation.
- `AccountPreviewController` (`ApiController`) returning `no-store` with demo-only data.
- `AssetCachePolicyFilter` distinguishing resolver-verified hashed URLs from plain URLs.
- `src/main/resources/static/assets/css/site.css` and `js/app.js`.
- `src/main/resources/templates/home.html` using Thymeleaf URL expressions.
- Real HTTP tests verifying rendering, hashes, cache policies, and 304 responses.

```text
spring-cache-site-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sitecache/
    │   │   └── SiteCacheApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── templates/home.html
    │       └── static/assets/
    │           ├── css/site.css
    │           └── js/app.js
    └── test/
        └── java/com/example/sitecache/
            └── SiteCacheHttpTest.java
```

### 6.1. Gradle and Java 17

**`settings.gradle`:**

```groovy
rootProject.name = 'spring-cache-site-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-webflux` to this MVC demo. `WebClient` can be used in MVC when needed, but this lesson focuses on serving views + static assets with Servlet MVC and practicing conditional HTTP caching.

### 6.2. application.properties

**`src/main/resources/application.properties`:**

```properties
spring.application.name=spring-cache-site-demo
server.port=8080

# Let Boot MVC map default static resources.
spring.web.resources.add-mappings=true

# Content-hashed URLs for CSS/JS.
spring.web.resources.chain.enabled=true
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
spring.web.resources.chain.cache=true

# Do not apply a global one-year HTTP cache:
# spring.web.resources.cache.cachecontrol.max-age=365d

# Production can cache parsed templates.
# During development this can be set to false:
spring.thymeleaf.cache=true

# Demo does not expose internal error details.
server.error.include-message=never
server.error.include-stacktrace=never
```

**Keep distinct:** `spring.web.resources.chain.cache=true` **caches resource resolver results in the JVM**, not browser `Cache-Control`. During development, editing files directly on disk inside a running JVM can be hidden by resolver caching and Thymeleaf template caching; rebuild/restart or set dev properties properly rather than assuming the content strategy is broken.

## 7. Complete Java Code for the Application

**`src/main/java/com/example/sitecache/SiteCacheApplication.java`:**

```java
package com.example.sitecache;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.resource.ResourceUrlProvider;

@SpringBootApplication
public class SiteCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(SiteCacheApplication.class, args);
    }
}

@Controller
class HomeController {

    @GetMapping("/")
    String home(Model model, HttpServletResponse response) {
        // Shared demo HTML; no-cache allows storage
        // but forces revalidation before every reuse.
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        model.addAttribute("pageTitle", "Versioned UI");
        return "home";
    }
}

@RestController
class ApiController {

    @GetMapping("/api/catalog")
    ResponseEntity<List<String>> catalog() {
        // Fixed demo catalog. When data changes in
        // production, ETag MUST change with the representation.
        return ResponseEntity.ok()
                .eTag("\"catalog-rev-1\"")
                .header(HttpHeaders.CACHE_CONTROL,
                        "public, max-age=0, must-revalidate")
                .body(List.of("book", "pen"));
    }

    @GetMapping("/api/account-preview")
    ResponseEntity<Map<String, String>> accountPreview() {
        // Returns demo data only, no auth yet.
        // Production: protect route before returning user data.
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL,
                        "private, no-store")
                .body(Map.of("state", "demo-only"));
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
class AssetCachePolicyFilter extends OncePerRequestFilter {

    private static final String CSS =
            "/assets/css/site.css";
    private static final String JS =
            "/assets/js/app.js";

    private final ResourceUrlProvider urlProvider;

    AssetCachePolicyFilter(ResourceUrlProvider urlProvider) {
        this.urlProvider = urlProvider;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String contextPath = request.getContextPath();
        String requestUri = request.getRequestURI();
        String path = requestUri.substring(contextPath.length());

        if (path.startsWith("/assets/")) {
            String cssVersioned =
                    urlProvider.getForLookupPath(CSS);
            String jsVersioned =
                    urlProvider.getForLookupPath(JS);

            boolean fingerprintMatches =
                    path.equals(cssVersioned)
                    || path.equals(jsVersioned);

            if (fingerprintMatches) {
                // Only URLs generated by the resource resolver
                // for CURRENT content get long-lived caching.
                response.setHeader(
                        HttpHeaders.CACHE_CONTROL,
                        "public, max-age=31536000, immutable");
            } else {
                // Unhashed URLs or invalid hashes
                // never get a long cache TTL from this filter.
                response.setHeader(
                        HttpHeaders.CACHE_CONTROL, "no-cache");
            }
        }

        filterChain.doFilter(request, response);
    }
}
```

**Guarantees and limitations of the code:**

1. One Java file contains a single `public class SiteCacheApplication` matching its filename; `HomeController`, `ApiController`, and `AssetCachePolicyFilter` are package-private in the same package and discovered by Spring component scanning.
2. The filter touches only paths starting with `/assets/`. HTML and JSON endpoints set their own cache policies in their controllers.
3. `ResourceUrlProvider` resolves the versioned URL actually generated by the Spring resource chain; the filter checks **exact full-path equality**, rather than trusting an arbitrary `-<32 hex>` regex from the client.
4. Any fake hash not matching a canonical demo asset will **not** be marked immutable; the resource handler typically returns 404 for bad hashes. This lowers the risk of caching 404s forever during experiments.
5. The demo lists only **two assets**. With hundreds of files, never list them manually in a filter: move to a build asset manifest, verified hash registry/CDN policy, or separate resource handlers. This is an **explicitly stated design limit**, not a full production asset pipeline.
6. `requestUri.substring(contextPath.length())` strips the context path when running at the root context path. Under servlet path mappings or complex proxy prefixes, compute canonical URLs cleanly and test `server.servlet.context-path` alongside trusted forwarded headers. Never trust client-supplied `X-Forwarded-Prefix`.
7. The header is set before the servlet resource handler writes bytes. The demo omits a global static handler `CacheControl` so it does not overwrite our filter; integration tests verify the transmitted values.
8. On 404 errors, handlers or the container may emit their own cache headers. Production must test CDN negative caching policies; never assume one app filter governs all CDN 404s.
9. Resource paths must **never serve modified content at an existing hashed URL**. `ContentVersionStrategy` uses MD5 for versioning, not content integrity/SRI.
10. `catalog` uses `ResponseEntity.eTag(...)`. Spring MVC evaluates conditional headers via `HttpEntityMethodProcessor` and returns 304 when `If-None-Match` matches; JDK HTTP tests verify this over real networking.
11. `/api/account-preview` is unauthenticated and holds no PII. `private,no-store` does not replace Spring Security or authorization.

**Important note on filter ordering:** Spring Boot auto-configures `ResourceUrlEncodingFilter` for Thymeleaf in MVC. Our demo cache filter does not generate fingerprints; it sets policies based on the URLs produced by `ResourceUrlProvider`. In practice, always verify template rewriting succeeded via an HTTP test before enabling long cache TTLs.

## 8. Thymeleaf View: HTML References Source Paths, Browser Receives Hashed URLs

**`src/main/resources/templates/home.html`:**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">
    <title th:text="${pageTitle}">Demo page</title>

    <!-- Thymeleaf + ResourceUrlEncodingFilter rewrite URLs -->
    <link rel="stylesheet"
          th:href="@{/assets/css/site.css}">
    <script defer th:src="@{/assets/js/app.js}"></script>
</head>
<body>
<main>
    <h1 th:text="${pageTitle}">Versioned UI</h1>
    <p>HTML is revalidated; CSS and JS use fingerprinted URLs.</p>
    <p id="status">JavaScript has not run yet.</p>
    <a href="/api/catalog">View JSON catalog</a>
</main>
</body>
</html>
```

Note Thymeleaf syntax: `th:text="${pageTitle}"` is an attribute expression, `th:href="@{/assets/css/site.css}"` is a URL expression. When rendered through Thymeleaf and the URL encoding filter, the link becomes:

```html
<link rel="stylesheet"
      href="/assets/css/site-<content-md5>.css">
```

The path above **describes the format**, not literal HTML to copy; the rendered HTML contains **32 hexadecimal characters** in place of the placeholder when the resource chain works. You never edit the template manually when CSS changes.

**If a test sees `href="/assets/css/site.css"` unchanged**, check:
- Did Boot load `spring-boot-starter-thymeleaf` and render the template with Thymeleaf?
- Is the app really Spring MVC rather than WebFlux?
- Is content version strategy enabled and do its paths match?
- Does the link use `th:href`/a URL helper routed through `encodeURL`?
- Is `ResourceUrlEncodingFilter` registered in the filter chain?
- Does the resource actually exist at the classpath static location?
- Did a context path or proxy path rewrite alter the resource lookup path?
- Did a custom `WebMvcConfigurer`/resource handler accidentally override Boot's resource chain?

## 9. Actual CSS and JavaScript Files

**`src/main/resources/static/assets/css/site.css`:**

```css
:root {
    --brand: #2351a4;
    color-scheme: light;
}
body {
    font-family: system-ui, Arial, sans-serif;
    margin: 2rem auto;
    max-width: 52rem;
    line-height: 1.6;
}
main {
    border-top: 0.35rem solid var(--brand);
    padding-top: 1rem;
}
h1 {
    color: var(--brand);
}
```

**`src/main/resources/static/assets/js/app.js`:**

```javascript
"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const target = document.querySelector("#status");
    if (target) {
        target.textContent = "JavaScript loaded from versioned resource.";
    }
});
```

No external libraries or dynamic imports are used in the demo; two static files suffice to observe:
- CSS contains `--brand` so bytes and hash changes can be verified when changing the color.
- JS updates `#status` on DOM load; browser JS execution can be tested with an E2E browser test, while HTTP tests should not pretend to be a browser.
- Neither file holds personal data, so `public, immutable` is safe on **verified hashed** URLs.
- Adding fonts or images requires checking cross-origin rules, content types, CORS, and dedicated caching policies.

## 10. Starting Up and Manual Verification with curl

Requires JDK 17+ and Gradle compatible with Boot 3.3.13:

```bash
gradle bootRun
```

If a Gradle Wrapper exists, use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows PowerShell.

### 10.1. HTML

```bash
curl -sS -i http://localhost:8080/
```

Expected:
- HTTP 200.
- `Content-Type` HTML (possibly with charset).
- `Cache-Control: no-cache`.
- HTML contains `/assets/css/site-<32hex>.css` and `/assets/js/app-<32hex>.js`.

Do not hardcode a "true" hash in documentation because it depends byte-for-byte on file contents. The hash shifts on newline or encoding edits, or if build tools minify/transform assets.

### 10.2. Extract the Server-Rendered CSS URL and Fetch It

On Linux/macOS with `grep -E`:

```bash
curl -sS http://localhost:8080/ -o home.html

ASSET=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' home.html \
  | head -n 1)

echo "$ASSET"
curl -i "http://localhost:8080$ASSET"
```

If `ASSET` is empty, **do not blame curl**; inspect template auto URL rewriting and the resource chain.

Expected for the valid hashed URL:
- HTTP 200.
- CSS bytes contain `--brand`.
- `Cache-Control: public, max-age=31536000, immutable`.

### 10.3. Unhashed URL

```bash
curl -i http://localhost:8080/assets/css/site.css
```

Expect HTTP 200 and `Cache-Control: no-cache`. Never let a reusable URL like `site.css` carry `max-age=31536000` if its contents can change in the next release.

### 10.4. API with ETag

```bash
curl -i http://localhost:8080/api/catalog

curl -i \
  -H 'If-None-Match: "catalog-rev-1"' \
  http://localhost:8080/api/catalog
```

Expected:
- First request: HTTP 200 + JSON `["book","pen"]`, header `ETag: "catalog-rev-1"`, and policy `public, max-age=0, must-revalidate`.
- Second request with matching `If-None-Match` → HTTP **304 Not Modified** with empty body. 304 tells a caching client to reuse its stored representation; raw `curl` simply shows 304 and **does not reassemble a cached body like a browser**.
- Changing `If-None-Match` to `"catalog-rev-other"` → HTTP 200 with full body.

### 10.5. Cache-Sensitive API

```bash
curl -i http://localhost:8080/api/account-preview
```

Expect HTTP 200, JSON `{"state":"demo-only"}`, and `Cache-Control: private, no-store`. This is an anonymous preview; in production it **must have authentication/authorization** before holding real account data.

## 11. Integration Tests Against a Real Web Server

Calling `HomeController.home(...)` directly in a unit test will not prove Thymeleaf renders versioned asset URLs. `MockMvc` can verify the MVC layer, yet we also want to prove the embedded server, resource handler, HTTP headers, conditional requests, and static bytes end to end.

Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` to start a real Tomcat on a random port. `@LocalServerPort` injects the bound port; `java.net.http.HttpClient` sends real localhost HTTP requests.

**`src/test/java/com/example/sitecache/SiteCacheHttpTest.java`:**

```java
package com.example.sitecache;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SiteCacheHttpTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private HttpRequest.Builder get(String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET();
    }

    private HttpResponse<String> send(String path)
            throws Exception {
        return client.send(
                get(path).build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private String header(
            HttpResponse<?> response, String name) {
        return response.headers()
                .firstValue(name).orElse("");
    }

    @Test
    void homeIsRevalidatedAndLinksAreContentVersioned()
            throws Exception {

        HttpResponse<String> response = send("/");
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Content-Type"))
                .contains("text/html");
        assertThat(header(response, "Cache-Control"))
                .isEqualTo("no-cache");

        assertThat(response.body()).contains(
                "Versioned UI");
        assertThat(response.body())
                .containsPattern(
                        "/assets/css/site-[0-9a-f]{32}\\.css");
        assertThat(response.body())
                .containsPattern(
                        "/assets/js/app-[0-9a-f]{32}\\.js");
    }

    private String versionedCssFromHtml(String html) {
        Matcher matcher = Pattern.compile(
                "/assets/css/site-[0-9a-f]{32}\\.css")
                .matcher(html);
        assertThat(matcher.find()).isTrue();
        return matcher.group();
    }

    @Test
    void fingerprintedAssetIsPublicAndImmutable()
            throws Exception {

        String cssUrl = versionedCssFromHtml(
                send("/").body());

        HttpResponse<String> response = send(cssUrl);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Content-Type"))
                .contains("text/css");
        assertThat(response.body()).contains("--brand");
        assertThat(header(response, "Cache-Control"))
                .contains("public")
                .contains("max-age=31536000")
                .contains("immutable");
    }

    @Test
    void unversionedAssetMustRevalidate()
            throws Exception {

        HttpResponse<String> response =
                send("/assets/css/site.css");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("--brand");
        assertThat(header(response, "Cache-Control"))
                .isEqualTo("no-cache");
    }

    @Test
    void falseHashIsNotCachedAsImmutable()
            throws Exception {

        String wrong =
                "/assets/css/site-00000000000000000000000000000000.css";

        HttpResponse<String> response = send(wrong);

        assertThat(response.statusCode()).isEqualTo(404);
        assertThat(header(response, "Cache-Control"))
                .doesNotContain("immutable");
    }

    @Test
    void matchingETagReturns304WithEmptyBody()
            throws Exception {

        HttpResponse<String> original =
                send("/api/catalog");

        assertThat(original.statusCode()).isEqualTo(200);
        assertThat(original.body())
                .contains("\"book\"", "\"pen\"");
        String etag = header(original, "ETag");
        assertThat(etag).isEqualTo("\"catalog-rev-1\"");

        HttpRequest conditional =
                get("/api/catalog")
                        .header("If-None-Match", etag)
                        .build();

        HttpResponse<String> notModified = client.send(
                conditional,
                HttpResponse.BodyHandlers.ofString());

        assertThat(notModified.statusCode()).isEqualTo(304);
        assertThat(notModified.body()).isEmpty();
    }

    @Test
    void differentETagReturnsCurrentRepresentation()
            throws Exception {

        HttpRequest request = get("/api/catalog")
                .header("If-None-Match", "\"some-old-revision\"")
                .build();

        HttpResponse<String> result = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(result.statusCode()).isEqualTo(200);
        assertThat(result.body()).contains("book");
    }

    @Test
    void previewMustNeverBeStoredBySharedCache()
            throws Exception {

        HttpResponse<String> response =
                send("/api/account-preview");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Cache-Control"))
                .contains("private")
                .contains("no-store");
        assertThat(response.body())
                .contains("\"demo-only\"");
    }

    @Test
    void javaScriptIsVersionedAndImmutable()
            throws Exception {

        HttpResponse<String> home = send("/");
        Matcher match = Pattern.compile(
                "/assets/js/app-[0-9a-f]{32}\\.js")
                .matcher(home.body());

        assertThat(match.find()).isTrue();

        HttpResponse<String> js = send(match.group());
        assertThat(js.statusCode()).isEqualTo(200);
        assertThat(js.body()).contains("DOMContentLoaded");
        assertThat(header(js, "Cache-Control"))
                .contains("immutable");
    }
}
```

Run:

```bash
gradle test
```

Expected: **8 tests** pass when Boot 3.3.13, Java 17, Thymeleaf URL rewriting, and the resource chain are wired properly. This is an **expected outcome, not a claim that Gradle was run here**.

### 11.1. What Do the Assertions Actually Prove?

- `homeIsRevalidatedAndLinksAreContentVersioned`: HTML passes through Thymeleaf and URLs carry hashes; checking the CSS file's existence alone is insufficient.
- `fingerprintedAssetIsPublicAndImmutable`: the rendered URL is resolved by the HTTP server with the right cache policy.
- `unversionedAssetMustRevalidate`: the bare path is not given a one-year immutable TTL.
- `falseHashIsNotCachedAsImmutable`: a client cannot fake an arbitrary hash and receive the demo's immutable policy.
- `matchingETagReturns304WithEmptyBody`: `If-None-Match` conditional handling works via `ResponseEntity`; 304 carries no body.
- `differentETagReturnsCurrentRepresentation`: stale validators do not accidentally return empty bodies.
- `previewMustNeverBeStoredBySharedCache`: demo response carries `private, no-store`; does not by itself prove every CDN obeys headers.
- `javaScriptIsVersionedAndImmutable`: JS wasn't forgotten when enabling CSS content versioning.

**Limitations:** these tests do not execute real browser JavaScript, nor test CDN, compression, CSP, auth/cookies, TLS, or rolling deployments with two asset generations. Those require the checks in sections 15–21.

## 12. Testing Asset Changes Across Two Builds

A single build test does not prove the hash **changes when bytes change**. To verify cache busting end-to-end, produce two independent artifacts:

**Release R1**
1. Build JAR with `site.css` having `--brand: #2351a4;`.
2. Start app and fetch `/` HTML.
3. Extract CSS URL into `CSS_R1`.
4. Fetch that URL, record byte checksum and cache policy.

**Release R2**
1. Edit CSS to `--brand: #6138a5;`.
2. Clean-build R2 JAR (ensuring updated resources are packaged).
3. Run R2 on another port.
4. Fetch `/` HTML and extract CSS URL as `CSS_R2`.
5. Assert `CSS_R1 != CSS_R2` and `CSS_R2` contains the new color.
6. Both R1/R2 HTML keep `Cache-Control: no-cache`.
7. `/assets/css/site.css` on R2 has no long cache lifetime.
8. Fetch `CSS_R1` via **CDN/asset origin** after R1 is replaced across the app fleet. If users still hold old HTML, R1's URL must still be served from retained immutable storage.

**Crucial point:** when running a new R2 JAR, Spring Boot's classpath resource handler **no longer serves R1's hash** because the R2 JAR only contains the new `site.css`. Content versioning does not automatically preserve history across releases! CDNs/object storage need retention policies or multi-version asset buckets to serve prior hashed assets intentionally.

### 12.1. Illustrative Shell Smoke Test

```bash
# Run R1 on 8080 and R2 on 8081 using two separate artifacts.
curl -sS http://localhost:8080/ > r1.html
curl -sS http://localhost:8081/ > r2.html

CSS_R1=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' r1.html | head -n 1)
CSS_R2=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' r2.html | head -n 1)

printf "R1: %s\nR2: %s\n" "$CSS_R1" "$CSS_R2"

test -n "$CSS_R1"
test -n "$CSS_R2"
test "$CSS_R1" != "$CSS_R2"
```

**No fixed output digest is printed** because hashes depend on exact bytes. This script verifies URL divergence, not that R1 assets remain available at R2's origin. If both URLs match, check whether the file was actually rebuilt, Gradle incremental caching, and content version strategy config.

### 12.2. Rollbacks Must Be Tested Too

Once R2 has served HTML, a client may still have R2 assets cached when you roll back to R1:
- If rolled-back R1 HTML points to R1's hash, browsers may already have R1 cached or fetch it cleanly.
- If a client keeps an open R2 tab, it may still request R2's asset. If R2 was wiped from every origin/CDN and the browser hadn't cached it, the UI hits 404.
- If R2 JavaScript calls an API endpoint introduced only in R2, keeping the asset alone isn't enough. You need backward-compatible APIs or app-level reload/version negotiation.
- A service worker can hold R2 HTML/JS independently of the HTTP cache; manage its lifecycle and upgrade policy separately.

**Practical takeaway:** versioned assets, HTML cache policy, and API compatibility belong together. Never inspect CSS `Cache-Control` alone and assume rollouts are safe.

## 13. ETags and Conditional Requests: Saving Bodies While Staying Fresh

HTTP cache validators allow clients to revalidate:

```text
Client                              Server
  │ GET /api/catalog                 │
  ├─────────────────────────────────►│
  │◄──── 200 ETag: "catalog-rev-1" ───┤
  │      body = ["book","pen"]        │
  │                                   │
  │ GET /api/catalog                  │
  │ If-None-Match: "catalog-rev-1"     │
  ├─────────────────────────────────►│
  │◄──── 304 Not Modified ────────────┤
  │      NO response body             │
  │                                   │
  │ client reuses cached body         │
```

**An ETag is not a timestamp**; it is an opaque validator for the selected representation. Options include:
- Strong ETag: `"revision-7"`, valid only when representations are strictly byte-equivalent.
- Weak ETag: `W/"revision-7"`, used when representations are semantically equivalent though not byte-identical per HTTP policy.
- Database revisions, response byte checksums, content hashes, or storage object versions.

In the demo, the catalog is **static**, so `"catalog-rev-1"` is valid within that scope. In production, if a response varies by locale, account, query params, role, DB contents, or feature flags, **the ETag must change for every varying dimension**. Keeping a constant `"catalog-rev-1"` for mutable data is a bug: clients will get 304 even after the payload changed.

### 13.1. What Status 304 Includes and Excludes

- 304 is typically returned on conditional GET/HEAD when the selected representation is unchanged.
- **No response message body** is sent for the resource.
- The response can include metadata headers needed to refresh the cache entry such as `ETag` and `Cache-Control`.
- A raw JDK `HttpClient` does not act as a browser cache when sending `If-None-Match`; tests must retain the prior body if simulating reuse.
- `If-None-Match` takes precedence over `If-Modified-Since` per the HTTP spec when both are sent.
- 304 **does not mean the app did zero work**; the server may still query the DB or compute the ETag unless backed by cheap revision metadata.
- If a client lacks the old body yet sends `If-None-Match`, 304 supplies no body; consumers must handle that cleanly.
- For state-changing methods, `If-Match` and 412 Precondition Failed handle optimistic concurrency—a separate problem from GET caching with `If-None-Match`.

### 13.2. Do Static Resources Automatically Get ETags?

Spring MVC's `ResourceHttpRequestHandler` supports `Last-Modified` and conditional requests from resource metadata. **Do not assume every static resource automatically gets an ETag from Spring Boot** just because content-hashed URLs are enabled. Versioned paths and HTTP ETags are distinct mechanisms:
- Content-hashed URLs produce a **new cache key** when bytes change.
- ETags **revalidate the same URL** once stale.
- `Last-Modified` enables revalidation, subject to second-level timestamp precision and resource source quirks.
- `ShallowEtagHeaderFilter` computes ETags by buffering response bodies, **not recommended for large streams/downloads** due to buffering CPU/memory; generating ETags from metadata/revisions is much cheaper.

In practice, browsers rarely need to revalidate hashed immutable assets while fresh. For unhashed HTML and APIs, ETags/`Last-Modified` deliver far greater value.

## 14. Cache Policies for HTML, Private JSON, and Redirects

### 14.1. Shared HTML

`Cache-Control: no-cache` is a simple default letting browsers store HTML while forcing revalidation before reuse. Without an ETag/`Last-Modified` on HTML, revalidation yields 200 and re-downloads the body. That is acceptable: HTML is far smaller than JS bundles, and picking up updated asset URLs quickly matters most.

If HTML contains personal data, CSRF tokens, secrets, or privacy constraints forbidding storage, use `Cache-Control: private, no-store` and stay out of public CDNs. Not all HTML is safe to store.

### 14.2. Public JSON

Public catalog responses use `ETag` with `max-age=0, must-revalidate`. Tune by domain needs:
- Rarely changing catalog: short freshness and CDN `s-maxage`.
- Fast-moving pricing/inventory: disable caching or revalidate strictly, prioritizing data correctness.
- User-specific fields in API: `private` or `no-store`, never shared public cache.
- HTTP `Vary` when content depends on `Accept-Language`, `Accept-Encoding`, etc.; avoid broad `Vary: Cookie` which explodes cache keys.

### 14.3. Redirects Can Be Cached

`301 Moved Permanently` and `308 Permanent Redirect` carry caching semantics unlike `302`/`307`. If you redirect `/old` to `/new` permanently and later roll back, browsers may remember the permanent redirect. Across multi-version rollouts:
- Test `Location`, scheme/host, and query preservation.
- Behind TLS-terminating proxies, configure trusted forwarded headers; never trust client-supplied headers.
- Never accidentally cache user-specific or OAuth callback redirects.
- Choose redirect statuses and expiries intentionally—avoid 301 for experimental routes that may change soon.

## 15. NGINX/CDN: Long Cache Only on Verified Asset Paths

In production, a clean setup has the **build pipeline emit fingerprinted assets** into a dedicated URL namespace (such as `/assets/v/`), allowing CDN rules to apply `immutable` strictly to that guaranteed-immutable namespace. In this Spring `ResourceVersionResolver` demo, the hash sits in the filename; the CDN must know that URL genuinely exists and never mutates.

Illustrative NGINX config placing browser caching at the **edge**:

```nginx
# Fragment; TLS, upstreams, and ACLs still require full configuration.
server {
    listen 443 ssl;
    server_name site.example.test;

    # ssl_certificate /...;
    # ssl_certificate_key /...;

    location /assets/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # DO NOT add_header immutable for ALL of /assets/
        # if unhashed /assets/site.css is still reachable.
        # Let the origin filter control it or match
        # strictly on hashed paths/build manifests.
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Do not configure proxy caching for HTML/account
        # without reviewing Cache-Control, Authorization, and cookies.
    }
}
```

**This is not a complete production NGINX config**; it omits TLS keys/CAs, forwarded-header trust boundaries, body/header limits, auth/rate limits, logging, timeouts, and network controls. Never copy directly to production.

On a CDN:
- Check whether it **honors origin `Cache-Control`** or overrides TTLs and error caching.
- Never cache `Set-Cookie`/`Authorization`-dependent HTML as public merely because it shares a hostname.
- Cache keys must include necessary path/query/header variations without unbounded cardinality.
- If the CDN caches immutable assets, retain old hashes long enough for open tabs and rollbacks.
- For gzip/br compressed variants, support `Vary: Accept-Encoding` and check per-representation ETag semantics.
- Maintain a purge plan for incidents (**wrong bytes under a hashed URL, leaked secret in a JS bundle, stale HTML**), without relying on purges for routine deploys.

**Security:** never trust `X-Forwarded-*` directly from clients. Reverse proxies must strip/overwrite headers at the trust boundary, and backends must accept traffic only from trusted proxies. Wrong scheme/host values corrupt template URLs, redirects, Secure cookies, and cache keys.

## 16. Compression, Range/HEAD, Images, and Fonts

HTTP variants add complexity to caching:

### 16.1. Compression

- Browsers may send `Accept-Encoding: br, gzip`; servers or CDNs respond with matching `Content-Encoding`.
- When the same URL serves multiple encodings, caches must honor `Vary: Accept-Encoding`.
- For precompressed static resources, Spring's resource chain offers `EncodedResourceResolver` and `VersionResourceResolver`. Spring Framework docs state to **register `EncodedResourceResolver` before `VersionResourceResolver`** when configuring manually so the content hash is computed from the uncompressed asset.
- `server.compression.enabled=true` alters transmitted response bytes, so ETag/hash contracts must account for representations. Never assume raw and compressed representations share strong ETag equivalence.
- Prevent CDNs from caching a compressed body and serving it to a client that did not advertise that `Accept-Encoding`.

### 16.2. Range / Partial Content

Video/large-file downloads use `Range: bytes=...` and HTTP 206 Partial Content with `Content-Range` and `Accept-Ranges`. Server and resource handler support varies; test on your exact runtime.

Never put a full-body buffering ETag filter in front of large/streaming files without measuring memory. Use CDN/object storage optimized for byte-range requests on large media; a content-hashed URL does not replace byte-range semantics.

### 16.3. Images and Fonts

- Immutable images (AVIF/WebP/PNG) can be fingerprinted just like CSS/JS.
- Cross-origin fonts may need CORS (`Access-Control-Allow-Origin` and `Cross-Origin-Resource-Policy` depending on architecture).
- Responsive images with `srcset` must version **every** variant (width/format), not just the fallback image.
- CSS `url(...)` references to fonts/images must stay consistent in rewriting/manifests; a newly hashed CSS referencing a missing image still breaks the UI.
- For personal images like private avatars, use signed URLs with short TTLs rather than `public, immutable` if access permissions can revoke.

## 17. Service Workers and SPAs: HTTP Cache-Control Doesn't Control Everything

When a frontend uses a service worker:
- `CacheStorage` can still serve cached HTML/JS even when HTTP returned `no-cache`, depending on service worker logic.
- A `cache-first` strategy on an unhashed app shell can lock clients onto stale versions indefinitely.
- `network-first` for HTML fits better, paired with offline fallbacks and timeouts.
- Upgrading service workers (activate/claim/skipWaiting) needs a UX and API-compatibility plan.
- Never let service workers cache `/api/account`, token responses, or CSRF-sensitive HTML without explicit privacy design.
- `service-worker.js` itself needs short freshness/revalidation so browsers detect updates—never mark it immutable at a fixed URL.

**SPA fallback with Spring Boot:**
- Static assets must be served cleanly; never forward **all** asset 404s to `index.html` with status 200, or browsers receive HTML for `.js` URLs, triggering MIME errors and poisoned CDN caches.
- Client-side SPA routes like `/dashboard` can forward `index.html` when `Accept` includes HTML and the path does not collide with API/static prefixes.
- Missing hashed assets must return **404** so deployment bugs surface immediately instead of serving an HTML fallback.
- Test SEO/prerendering, history routing, base paths, Content-Security-Policy, and `index.html` caching across actual proxy paths.

Conceptual routing (not standalone code):

```text
GET /dashboard     + Accept: text/html  -> index.html
GET /assets/x.js   + Accept: */*        -> resource or 404
GET /api/users     + Accept: */*        -> API or 404
```

Path/Accept branching must be guarded carefully—never use a blanket catch-all controller that swallows missing-resource 404s.

## 18. WebFlux and Static Resource Handling: Similarities and Differences

Spring Boot WebFlux supports static resources and content-versioned resource handlers, yet **does not use Servlet `Filter` or MVC's `ResourceUrlEncodingFilter`**. In WebFlux:
- The pipeline uses `WebFilter` and `ServerWebExchange`.
- Cache headers are set on `ServerHttpResponse.getHeaders()` inside a `WebFilter` before commit.
- Template integration and URL rewriting follow the reactive stack—do not copy MVC's `ResourceUrlProvider`/`HttpServletResponse.encodeURL`.
- `spring.web.resources.*` shares common properties, but verify behavior with `@SpringBootTest(RANDOM_PORT)` on Reactor Netty.
- In WebFlux, `WebSession` replaces Servlet `HttpSession`; cache policies never substitute for sessions/authorization.
- If both `starter-web` and `starter-webflux` are present, Boot normally defaults to MVC; never guess runtime stack just from importing `Mono`.

Illustrative WebFlux fragment (**not a standalone runnable app**):

```java
// Inside a Spring WebFlux WebFilter:
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String path = exchange.getRequest()
            .getPath().value();

    if (path.equals("/api/account")) {
        exchange.getResponse().getHeaders().set(
                HttpHeaders.CACHE_CONTROL,
                "private, no-store");
    }

    return chain.filter(exchange);
}
```

Real use requires imports, bean registration, auth policies, and reverse proxy verification. If using a frontend build tool (Vite/Webpack/Angular/React) that outputs fingerprinted asset manifests, letting NGINX/CDN serve static bundles while Spring Boot serves APIs is also valid—just keep **HTML, API, and cache key contracts consistent**.

## 19. Cache Busting Does Not Guarantee UI and API Compatibility

Suppose:
1. R1 JavaScript calls `GET /api/orders` and reads `totalCents`.
2. R2 JavaScript calls the same endpoint expecting `totalAmount`.
3. A browser tab still runs cached R1 HTML/JS while the R2 backend removed `totalCents`.
4. Even with perfect hashed asset URLs, R1 JS breaks because the **API contract broke**.

Solutions:
- Keep backward-compatible API fields while older active clients are still live.
- Delay removing legacy endpoints/schemas until after the rollout window.
- Provide version negotiation or a gentle app-version banner if needed, without force-reloading while a user is editing a form.
- For WebSocket/SSE, design protocol compatibility and reconnect semantics.
- Test R1 client against R2 API and vice versa during mixed deployments.
- Session/cookie/serializer schemas must also stay compatible between R1 and R2; asset hashing does not fix incompatible deserialization or auth.
- If a forced reload is unavoidable, prompt clearly and preserve unsaved user state.

**False check:** "R2 HTML references CSS_R2, so every user is running JS R2." An open tab that has not reloaded can execute R1 JS in memory for hours. Zero-downtime deployments must tolerate mixed frontend/backend versions.

## 20. Dynamic API ETags and Data-Driven Invalidation

A catalog API backed by a database should:
- Increment a catalog revision or compute a hash of the canonical representation.
- Include every dimension that alters the response body (tenant, locale, currency, permissions) in the ETag or cache key.
- Avoid `updatedAt` alone if multiple edits can share a timestamp unit, suffer clock skew, or happen via backfills.
- When using `Last-Modified`, account for 1-second precision and clock sync.
- Remember GET `If-None-Match` saves response bandwidth yet may still query the DB to read the revision.
- Keep internal `@Cacheable` service keys/evictions independent from HTTP-layer ETags.

Safe revision-based ETag pattern:

```java
// Illustrative controller method fragment, not standalone:
@GetMapping("/api/catalog")
ResponseEntity<CatalogDto> readCatalog() {
    CatalogSnapshot snapshot = catalogService.current();

    String etag = "\"catalog-" + snapshot.revision() + "\"";

    return ResponseEntity.ok()
            .eTag(etag)
            .header(HttpHeaders.CACHE_CONTROL,
                    "public, max-age=0, must-revalidate")
            .body(snapshot.payload());
}
```

`CatalogDto`, `CatalogSnapshot`, and `catalogService` must be implemented by the app. **Revisions must be unique per varying representation** and never shared blindly across tenants. If catalog entries vary by user permissions, **never mark them `public`**; use `private` or `no-store` with proper authorization.

### 20.1. Can HTTP 304 Be Used on Authenticated Requests?

HTTP caching defines intricate rules when `Authorization` is present. Shared caches must not arbitrarily reuse responses lacking explicit permission directives; private caches follow separate rules. Still, **never rely on accidental CDN behavior** to protect secrets. For personal APIs, set `Cache-Control: private, no-store` when appropriate and verify through the gateway; never embed secrets or guessable user IDs in ETags.

An ETag is not an access token and never replaces authorization. If user B replays user A's ETag, the server must still authenticate, authorize, select user B's representation, and only then evaluate the conditional header.

## 21. Security: Where Caching Becomes a Vulnerability

### 21.1. Shared Cache Keys Missing User Identity

If `/api/me` returns logged-in user data while the origin mistakenly emits `Cache-Control: public, max-age=600`, a CDN keying solely on URL can serve one user's data to another. Risk spikes when CDNs ignore cookies or `Authorization` in cache keys.

Mitigations:
- Never enable shared caching for private data without airtight key/authorization design.
- Return `Cache-Control: private, no-store` for sensitive responses per policy.
- Configure CDN cache bypass rules whenever auth headers/cookies are present—do not rely only on browsers.
- Audit `Set-Cookie` handling so login/logout responses are never cached.
- Test with **two synthetic users A and B** through the proxy: A's response must never leak to B.

### 21.2. Public Assets Containing Secrets

JavaScript bundles can leak:
- API keys mistaken for secrets (client-side JS can never keep a secret).
- Internal URLs, feature flags, debug metadata.
- Source maps exposing original source code or tokens if accidentally deployed.
- Sensitive build-time environment configuration.

**Content hashes do not secure files.** Once a secret ships in a JS bundle, browser and CDN caches can hold copies long after deletion at the origin. Rotate compromised secrets and execute incident response rather than just changing the URL.

### 21.3. Cache Poisoning and Path Normalization

Proxies can differ in how they normalize:
- Query strings and parameter order.
- URL encoding, percent-decoding, and semicolon parameters.
- `Host`, `Forwarded`, and `X-Forwarded-*` headers.
- HTTP `Vary` and `Content-Encoding`.
- Redirects and path case sensitivity.

Never treat a regex that "looks like a hash" as proof an asset exists or is authentic. In the demo, the filter matches **the canonical URL generated by the resource chain**. Production apps with many files need build manifests/verified storage and strict cache keys. CDNs must never cache a 200 HTML SPA fallback under a missing hashed `.js` URL.

### 21.4. CSP and SRI

- CSP rules like `script-src 'self'`/nonces restrict script origins (mind inline scripts).
- SRI verifies fetched subresource bytes for scripts/stylesheets, especially from third-party CDNs.
- Spring's MD5 resource URL versioning is for cache invalidation, not cryptographic subresource integrity.
- Never pair wildcard CORS `*` with credentials on cookie-authenticated APIs.
- Never trust client-supplied SSL/TLS termination headers; test proxy trust configs.

## 22. Observability and Layer-by-Layer Debugging

A post-deploy 404 on an asset URL can stem from:
- Cached HTML referencing an old release's hash deleted from the origin.
- Thymeleaf failing to rewrite the URL, leaving the bare path.
- A CDN rule rewriting all 404s to 200 HTML.
- Modified `spring.web.resources.static-locations`.
- App running under a different context path.
- Build tool failing to copy `static/assets` into the JAR.
- CDN overriding `Cache-Control`.
- Resource chain mismatch between fixed vs content version strategies.
- CDN caching a 404 before the new asset finished uploading.

**Signals to collect:**

| Signal | Meaning |
|---|---|
| HTTP 200/304/404/5xx on `/assets/**` | Cache hits/misses, missing assets, origin errors |
| CDN cache status: HIT/MISS/BYPASS | Whether the right URL groups are cached |
| HTML response/cache headers | Whether HTML revalidates after deploy |
| Distinct fingerprinted asset paths | Which build versions are actively served |
| 304 ratio on public APIs | Body bandwidth savings, paired with latency |
| Post-rollout JS error rate | Old clients vs API incompatibility |
| Resource handler exceptions | Lookup/version/static path mismatches |
| Response bytes + TTFB | Bandwidth and latency impact of caching |
| Frontend version vs API version | Detecting mixed-version failures |
| Security header compliance | CSP/CORS/Cache-Control leak prevention |

Never put raw `Cookie`, `Authorization`, session IDs, arbitrary user IDs, or full URLs containing secrets into metric labels. For HTTP APIs, use route templates and bounded reason enums. Redact/expire CDN logs that may contain query tokens.

### 22.1. Shortest-Path Debugging

1. `curl -I /`: are HTML `Cache-Control` and `Content-Type` right?
2. `curl -s /`: do rendered asset URLs contain hashes?
3. `curl -I <hashed-url>`: status 200 and `immutable`?
4. `curl -I <bare-url>`: is it mistakenly cached for a year?
5. `curl -H 'If-None-Match: ...' /api/catalog`: 304 or 200?
6. Test through domain/CDN: were response headers overridden?
7. Test R1→R2: did the hash change, and are old assets retained?
8. Test in a real browser toggling Disable Cache to separate resource chain bugs from HTTP cache bugs.
9. If an offline service worker is active, inspect/clear Cache Storage **in a test environment** to isolate that source of staleness.
10. Inspect packaged resource bytes inside the JAR/image and proxy rewrite rules.

Never shrug off bugs with "just hit Ctrl+F5": hard refreshes mask stale-cache root causes and do nothing for production users.

## 23. Complete QA Matrix

| Check | Input | Expected |
|---|---|---|
| HTML freshness | GET `/` | 200 text/html + `no-cache` |
| HTML versioned links | GET `/` | CSS/JS URLs contain 32-hex content MD5 |
| Hashed CSS | GET URL from HTML | 200 CSS + `public, max-age=31536000, immutable` |
| Hashed JS | GET URL from HTML | 200 JS + `immutable` |
| Bare CSS | GET `/assets/css/site.css` | 200 + `no-cache` |
| Fake hash | GET `site-0000...css` | 404, never marked `immutable` |
| API ETag | GET `/api/catalog` | 200, ETag matching selected representation |
| Conditional GET | Matching `If-None-Match` | 304 empty body |
| Stale ETag | Non-matching `If-None-Match` | 200 fresh body |
| Sensitive API | GET `/api/account-preview` | `private, no-store` |
| CSS content deploy | Change CSS color in R2 | R2 URL differs from R1; bytes match |
| Old asset retention | GET R1 URL after R2 deploy | Asset still served if historical hashes retained |
| HTML rollback | R2→R1 | R1 HTML points to R1 assets; old tabs don't 404 |
| API compatibility | R1 JS calling R2 API | No broken business contract |
| Browser cache | Two navigations with cache on | HTML revalidates; hashed assets HIT while fresh |
| CDN policy | GET `/assets/`, `/api/me` | Assets public, account never shared |
| Compression | `Accept-Encoding: gzip/br` | Valid `Vary`/`Content-Encoding` and valid bytes |
| HTTP/2 / TLS | Request through ingress | Valid cert, `h2` negotiated as configured |
| SPA fallback | Missing asset | 404, not fake 200 `index.html` |
| Service worker | Upgrade with cache-first | Does not pin old app shell forever |
| Authentication | Users A and B via CDN | No private cross-user leak |
| Error caching | 404/5xx/redirects | No unintended caching |
| Observability | R2 rollout | Healthy CDN HIT/MISS, client errors, asset 404s |

**Do not cram every case into one unit-test class.** The demo's 8 HTTP tests form the core suite; browser/CDN/staging suites belong at the infrastructure layers. For browser Playwright/Selenium tests, run against the real frontend build and assert DOM updates after JS executes. For CDN checks, test in a staging environment mirroring production caching rules.

## 24. Common Pitfalls and Fixes

| Symptom | Cause | Resolution |
|---|---|---|
| HTML still links `site.css` | Bypassed Thymeleaf URL rewrite or content strategy disabled | Use `th:href` + Boot chain; test rendered HTML over HTTP |
| CSS stays stale after deploy | Bare URL cached for 1 year | Use fingerprinted URLs; shorten/remove bare path TTL |
| CSS hash unchanged after edit | Build/resource cache or edited file outside artifact | Inspect resource bytes in JAR, rebuild and restart |
| Hashed URL returns 404 | Missing static file or lookup strategy mismatch | Check classpath, resource chain, and deployment |
| Old tabs hit 404 on assets after rollout | Old release assets deleted too soon | Retain immutable historical assets on CDN/object storage |
| Old HTML/JS incompatible with API | Open tab still runs R1 JS | Keep backward-compatible APIs, reload/version policy |
| Long `Cache-Control` on bare CSS | Global Boot 1-year static cache enabled | Scope long policy strictly to verified hashed URLs |
| `no-cache` assumed to mean "do not store" | Confused HTTP directives | Use `no-store` when storage must be prohibited |
| User A sees User B's data | CDN cached personalized response as public | `private`/`no-store`, auth-aware CDN bypass |
| API always returns 304 despite data edits | Static hardcoded ETag | Compute ETag from real revision/hash |
| API always returns 200 despite matching ETag | Bypassed `ResponseEntity` conditional path or mismatched validator | Check ETag quotes/`If-None-Match`/handler |
| Static assets lack ETag | Resource handler doesn't auto-generate expected ETag | Rely on `Last-Modified`/hashed URLs, or add explicit ETag if needed |
| CDN returns HTML for `.js` | SPA fallback catches missing assets | Keep 404 for asset prefixes |
| Service worker shows stale UI | Cache Storage controlled by SW JS separately from HTTP cache | Manage SW lifecycle/versioning |
| Dev HTML edits not visible | Thymeleaf template cache enabled | Set `spring.thymeleaf.cache=false` in dev profile, restart properly |
| Static asset edits not reloaded | Internal resource chain cache / JAR packaging | Dev profile, rebuild resources, verify runtime |
| CSS paths break under context-path | Hardcoded root-relative URLs | Use Thymeleaf `@{...}`, test under context path |
| 32-hex URL hash mistaken for SRI | ContentVersionStrategy MD5 is only versioning | Add cryptographic SRI SHA-384 and CSP |
| CDN gzip variants break | Missing/broken `Vary` | Test `Accept-Encoding` and compressed variants |
| Browser caches old 301 forever | Permanent redirect cached | Choose redirect status/TTL intentionally |
| JS asset leaks a secret | Secrets bundled into frontend | Rotate secret, purge/run incident response |
| Profile page uses `no-cache` despite privacy rules | `no-cache` still permits storage | Switch to `private, no-store` |
| New asset hash paired with old API | Mixed frontend/backend rollout | Test compatibility and rollout ordering |
| Filter hash lookup costs CPU with many assets | Per-request `ResourceUrlProvider` calls | Use build manifest or CDN object storage/rules |
| Login cookie breaks behind proxy | Wrong SameSite/Secure/forwarded headers | Fix proxy trust boundary, run auth integration tests |
| HTML cached by proxy against origin header | CDN overrides `Cache-Control` | Inspect CDN rules/headers and bypass routes |

## 25. Production Deployment Checklist

- [ ] Classify public HTML, private HTML, public JSON, private JSON, and static assets.
- [ ] HTML uses fast-updating policy: `no-cache`, or `private, no-store` if personalized.
- [ ] CSS/JS/fonts/images use verified content-hashed or build-versioned URLs.
- [ ] Zero hardcoded hashes; templates/helpers/manifests generate URLs from build/resource chain.
- [ ] Valid hashed assets get long `public, max-age=..., immutable`.
- [ ] Unhashed URLs are not cached long-term, or are safely closed/redirected.
- [ ] CDN/object storage retains old assets across rollout and rollback windows.
- [ ] Spring resource chain and Thymeleaf URL rewriting verified by real HTTP tests.
- [ ] Internal JVM resolver/template caches not confused with browser/CDN HTTP caches.
- [ ] API ETags change whenever representations change; conditional GET returns 304 properly.
- [ ] Dynamic private content enforces auth and `private, no-store` per policy.
- [ ] Tokens, CSRF, account data, and `Set-Cookie` are never cached in shared CDNs.
- [ ] `Vary` and compression variants verified.
- [ ] Browser service worker Cache Storage has explicit versioning/purge/lifecycle handling.
- [ ] Missing JS/CSS assets return 404 instead of falling back to 200 `index.html`.
- [ ] API maintains backward compatibility for open tabs running prior release JS.
- [ ] R1→R2→rollback tested in browser/CDN staging, not just one JUnit test.
- [ ] HTTP `RANDOM_PORT` integration tests verify headers, 304, and hashed URLs.
- [ ] Security includes CSP, SRI, TLS, and trusted proxy headers.
- [ ] Metrics track CDN HIT/MISS, asset 404s, JS errors, and cache policy violations.
- [ ] No secrets or PII in bundles, logs, snapshots, or metrics.
- [ ] Rollback, purge, and incident response plans exist for bad assets.

## 26. Self-Check Questions

**1. Why put a hash in the CSS filename instead of just using a tiny max-age?**  
Because a hashed URL becomes a brand-new cache key whenever content changes, allowing long immutable caching while clients still load new releases immediately after deploy.

**2. Does `Cache-Control: no-cache` forbid browsers from storing the response?**  
No. It allows storage while requiring revalidation before reuse. `no-store` is the directive that forbids storage.

**3. Should `spring.web.resources.cache.cachecontrol.max-age=365d` be set for all static files?**  
Only if every served path is truly immutable or unversioned paths are blocked. If mutable `site.css` shares the handler, clients risk getting stale files.

**4. Will Thymeleaf automatically rewrite `href="/assets/css/site.css"` into a hashed URL?**  
Never assume that. Use `th:href="@{/assets/css/site.css}"` with the content resource chain and `ResourceUrlEncodingFilter`, then verify with real rendered HTML.

**5. Is `spring.web.resources.chain.cache` the browser `Cache-Control`?**  
No. It caches internal resource-chain resolution inside the JVM.

**6. How does an ETag help when HTML or APIs lack hashed URLs?**  
It enables conditional requests; when the selected representation has not changed, the server returns 304 with an empty body and the client reuses its cached body.

**7. Does Spring's static handler automatically generate strong ETags for every file?**  
Do not rely on that assumption. Static handlers commonly support `Last-Modified`; content-versioned URLs are a separate mechanism from ETags.

**8. If HTML already points to JS_R2 while the backend API rolls back to R1, is the app guaranteed to work?**  
No. Cached HTML/JS tabs may call APIs that R1 lacks. API compatibility or controlled reload handling is required.

**9. Why retain old hashed assets after a deploy?**  
Clients may still hold cached HTML pointing to R1's hashed URLs and either never fetched them or evicted them from browser cache.

**10. Is Spring's MD5 content hash the same as SRI?**  
No. The MD5 URL strategy is for versioning/cache busting; SRI uses separate cryptographic hashes for subresource integrity.

**11. Can a CDN safely cache a personalized response just because the URL is identical?**  
No, that is unsafe. Use auth-aware caching policies, `private, no-store`, or strict partitioning so shared user data never leaks.

**12. Why is a 304 response useful even though it has no JSON body?**  
Because the browser/cache already holds the body from an earlier 200; 304 confirms it is still valid and updates cache metadata without re-transmitting the payload.

**13. When files are gzip-compressed, what must ETag/URL hashing consider?**  
The selected representation, `Content-Encoding`/`Vary`, and whether hashes are computed before or after compression—never mix variants together.

**14. Must a service worker automatically obey HTTP `Cache-Control` when using the Cache Storage API?**  
No. Service workers execute custom JS caching logic and have their own lifecycle that must be designed and tested.

**15. Does a Java controller unit test prove rendered asset URLs actually contain hashes?**  
Not yet. You must render Thymeleaf through a real web runtime and HTTP GET the generated URL.

## 27. Official References

1. **Spring Boot 3.3 — Servlet Web Applications / Static Content**: default static locations, versioned resource URLs, and `ResourceUrlEncodingFilter` auto-config for Thymeleaf/FreeMarker. https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
2. **Spring Boot 3.3 — Common Application Properties**: `spring.web.resources.chain.*`, `spring.web.resources.cache.cachecontrol.*`, `spring.thymeleaf.cache`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. **Spring Framework — Static Resources (Spring MVC)**: `ResourceHttpRequestHandler`, `VersionResourceResolver`, `ContentVersionStrategy`, `ResourceUrlProvider`, and `ResourceUrlEncodingFilter`. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
4. **Spring Framework — HTTP Caching (MVC)**: `Cache-Control`, `ETag`, and conditional request behavior. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
5. **Spring Framework — Resource Handling (WebFlux)**: equivalent reactive resource handling and cache policies. https://docs.spring.io/spring-framework/reference/web/webflux/config.html
6. **Spring Boot 3.3 — Testing Spring Boot Applications**: `@SpringBootTest(RANDOM_PORT)` and `@LocalServerPort`. https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
7. **Thymeleaf + Spring Integration**: `th:href` URL expressions and Spring MVC link rewriting. https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
8. **RFC 9111 — HTTP Caching**: `Cache-Control`, validators, `Vary`, freshness, shared/private caches, and conditional requests. https://www.rfc-editor.org/rfc/rfc9111.html
9. **RFC 9110 — HTTP Semantics**: 304 Not Modified, `If-None-Match`, `ETag`, `Last-Modified`, and conditional requests. https://www.rfc-editor.org/rfc/rfc9110.html
10. **MDN — Cache-Control** (browser compatibility and `immutable` semantics): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
11. **MDN — Service Worker Cache API**: Cache Storage and how it differs from the HTTP cache. https://developer.mozilla.org/en-US/docs/Web/API/Cache
12. **NGINX — Proxy Module**: proxy caching, cache keys, revalidation, and header handling. https://nginx.org/en/docs/http/ngx_http_proxy_module.html

**Practical conclusion:** To serve UI assets efficiently while keeping deployments and rollbacks safe, **revalidate HTML**, use **content-hashed URLs for CSS/JS**, apply **immutable caching strictly to truly immutable resources**, never share-cache personal data, and use **ETag/304 for revalidatable public APIs**. Clearly distinguish caches in the browser, CDN, service worker, Spring resource chain, and template engine. Verify with real HTTP tests via Spring Boot `RANDOM_PORT`, then extend with R1→R2/rollback checks and CDN/browser staging tests across the entire delivery path.