# Cache-Control, Expires, and Policies for Static or Private Data

> **Module:** Spring Boot - web-runtime · **Group:** HTTP Caching and Compression. This lesson explains HTTP caching per RFC 9111, compares browser caches and shared caches (proxy/CDN), and builds policies for static resources, HTML, public APIs, and personal content. Examples use Java **17+**, Maven, and **Spring Boot 4.1.2** with Spring MVC. Spring WebFlux applies the same HTTP protocol but has its own runtime configuration APIs.

## Learning Outcomes

After this lesson, you will be able to:

1. Read and accurately choose `Cache-Control`, `Expires`, `Date`, `Age`, `ETag`, `Last-Modified`, and `Vary`.
2. Distinguish `no-cache`, `no-store`, `private`, `public`, `max-age`, `s-maxage`, `must-revalidate`, and `immutable`, and know when to use each directive.
3. Design long caching for **immutable** versioned/hashed CSS/JS/images, short TTLs or revalidation for mutable files/HTML, and strict policies for personal/sensitive data.
4. Understand when an HTTP cache returns data without querying the server, when it must validate, and how 200/304 works with conditional requests.
5. Write Spring MVC `WebMvcConfigurer` configuration for two static asset groups and use `ResponseEntity.cacheControl(...)` for APIs with different sensitivity levels.
6. Analyze risks of data leakage via CDN, cache keys/Vary, `Authorization` responses, Spring Security, Service Workers, and release deployment errors.
7. Distinguish HTTP caching from Spring `@Cacheable` and `gzip/br` compression.

## 1. What Does an HTTP Cache Store and at Which Layer?

An HTTP cache stores **response representations** (headers, body, and related metadata) to avoid resending bytes or calling the origin when a stored copy is still permitted for reuse. Not every response is cached; the policy depends on HTTP method, status, headers, authorization, and the cache's own rules.

~~~text
Browser / mobile HTTP client
   |
   +-- Private HTTP cache (dedicated to that client/browser only)
   |      fresh hit -> may not send a network request
   |
   v
Proxy / CDN / reverse proxy: shared cache
   |      a single response copy can serve multiple clients
   |
   v
Gateway / Load Balancer
   |
   v
Spring Boot application
   |
   +-- static resource handler: CSS / JS / font / image
   +-- @Controller / @RestController: HTML / JSON
   |
   v
Service -> database
~~~

- **Private HTTP cache**: browser cache, HTTP client. The `private` header allows this type of cache to store the response when other conditions are met.
- **Shared HTTP cache**: proxy/CDN that can serve the same response copy to multiple users. This is why special care is needed with account data.
- **Spring method/data cache**: `@Cacheable`, Caffeine, Redis, ORM cache reside inside the server; they do **not** automatically follow HTTP response `Cache-Control`.
- **Service Worker Cache Storage**: managed separately by browser-side code and can exist outside the standard HTTP cache; `no-store` does not clear data in other storages.

**Caching vs. compression:** Cache-Control determines whether a response can be stored/reused; `Content-Encoding: gzip`/`br` only indicates the body was compressed in transit. Both techniques can be used together and require `Vary: Accept-Encoding` if multiple encoding variants exist.

## 2. Freshness: Is the Response Still Fresh or Stale?

A cache can reuse a **fresh** response without asking the server if policy allows. Once the freshness lifetime is exceeded, the response becomes **stale**, at which point revalidation or a full reload may be needed.

For example, the origin returns:

~~~http
HTTP/1.1 200 OK
Date: Sun, 08 Nov 2026 01:00:00 GMT
Cache-Control: public, max-age=300
Content-Type: text/css

body { color: navy; }
~~~

`max-age=300` indicates a maximum freshness lifetime of 300 seconds based on response age. It is **not** a guarantee that the browser keeps the file for exactly 300 seconds: caches may evict early, requests may force validation, or other conditions may apply.

If a CDN caches the response and serves it after some time, it may send:

~~~http
Age: 120
Cache-Control: public, max-age=300
~~~

`Age` is the estimated age of the response per HTTP rules, usually indicating a copy served from an upstream cache. The client must not assume a full 300 seconds remain: the age has already elapsed.

### Precedence Order for Determining Freshness Lifetime

According to RFC 9111, for a storable response:

1. A **shared cache** prioritizes `s-maxage` if the response contains that directive.
2. Otherwise, the cache uses `max-age`.
3. If neither directive is present, `Expires` provides an absolute expiration time, compared against `Date`/receipt time.
4. If explicit freshness is missing, some responses may use **heuristic freshness** depending on status and cache rules; missing headers **do not mean** caching is guaranteed not to happen.

Example:

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 01:10:00 GMT
Cache-Control: public, max-age=60, s-maxage=120
~~~

Browsers/private caches apply `max-age=60`; shared caches prioritize `s-maxage=120`. The 10-minute `Expires` timestamp **does not override** the two modern directives.

## 3. Meaning of Cache-Control Directives

| Response directive | Standard meaning | When to use |
| --- | --- | --- |
| `public` | Shared caches may store the response if other conditions are met | Public static assets, public APIs with verified cache keys |
| `private` | Shared caches **must not store**; private caches may store | Personal data that is low-sensitivity and allowed in browser cache |
| `no-store` | Compliant caches must not store request/response within directive scope | Sensitive profiles, tokens, orders, payment info |
| `no-cache` | May store, but **must revalidate successfully** before reuse | HTML entry pages, resources needing version verification |
| `max-age=300` | Response can stay fresh for up to 300 seconds (if other policies allow) | Explicit browser/API TTL |
| `s-maxage=60` | Shared caches use a 60-second TTL instead of max-age/Expires | CDN caching public content |
| `must-revalidate` | Once stale, must validate successfully; must not serve stale automatically | Data that must not be served past expiration |
| `proxy-revalidate` | Similar revalidation semantics, applied to shared caches | Rules for proxies |
| `immutable` | Representation will not change during freshness lifetime | URLs with **truly immutable** hashes/versions |
| `no-transform` | Intermediaries must not automatically transform content per directive | When transferred representation must remain intact |
| `stale-while-revalidate=30` | Some caches may serve stale for an extra 30 seconds while revalidating | Public content tolerating update delay |
| `stale-if-error=300` | Some caches may serve stale when upstream fails | Public content tolerating errors/staleness |

### 3.1. `no-cache` Does NOT Forbid Storage

~~~http
Cache-Control: no-cache
ETag: "home-v5"
~~~

The browser is allowed to keep the response copy. However, every time it wants to reuse it, it must verify with the origin. When an ETag is present, the request can include:

~~~http
GET / HTTP/1.1
If-None-Match: "home-v5"
~~~

If the content has not changed, the server can return **304 Not Modified** without resending the body. Here is the benefit: **it does not save a round-trip**, but it saves response bytes.

### 3.2. `no-store` Is the Directive That Forbids Storage

~~~http
Cache-Control: no-store
~~~

According to the standard, caches must not store the request/response for reuse. This is the cautious choice for data containing sensitive personal information. However, the header does not encrypt transport, does not protect against malicious clients, and does not erase files or data already in localStorage, Service Workers, the DOM, browser history, or screenshots. HTTPS, auth, and dedicated data deletion policies remain mandatory.

### 3.3. `max-age=0` Is Not Equivalent to `no-store`

`max-age=0` makes the response immediately stale by freshness rules, but caches can still **store** it and use conditional requests to revalidate. `no-cache` also allows storage while requiring revalidation. Do not use `max-age=0` or `no-cache` instead of `no-store` on tokens, account data, or private documents where storage must be restricted.

### 3.4. `private` Is Not Equivalent to `no-store`

~~~http
Cache-Control: private, max-age=60
~~~

Shared caches must not store it, but the user's browser can hold this copy for 60 seconds. If someone else uses the same device/browser profile after the account owner logs out, cached responses can still pose a risk. Only use it when **the business genuinely accepts** browser-side storage.

### 3.5. `public` and Authorization Require Special Evaluation

Under RFC 9111, shared caches are normally restricted when a request carries `Authorization`, **however** certain explicit response directives such as `public` or `s-maxage` can permit shared caching under standard conditions. Never conclude “because Authorization is present, the CDN definitely won't cache it”. For responses containing PII or identity-dependent results, **do not** casually add `public`/`s-maxage`.

A response with `Set-Cookie` is also not automatically shielded from all shared-cache scenarios solely by that header. Always set explicit cache policies and configure the CDN properly.

## 4. Expires: Absolute Expiration in HTTP-date

`Expires` specifies a **date and time** after which the response is considered stale:

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 01:05:00 GMT
~~~

Here, the response expires at 01:05 UTC; this does not mean the resource is deleted from the server at that time. The value is an HTTP-date (typically IMF-fixdate in GMT), not a relative number of seconds.

### When Both Expires and max-age Appear

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 02:00:00 GMT
Cache-Control: max-age=60
~~~

Compliant caches prioritize `max-age=60`, **ignoring Expires** when computing freshness. If `s-maxage` is present, shared caches prioritize `s-maxage`. Therefore, you cannot set Expires to one hour and expect it to override a one-minute TTL.

With `Expires: 0` or an invalid date format, caches must treat it as already expired. This is a legacy compatibility technique and **does not carry the anti-storage force** of `Cache-Control: no-store`.

### When Should Expires Be Used?

- There is a legacy system that genuinely relies on Expires and needs compatibility.
- You want to demonstrate or operate an absolute deadline mechanism for a representation, with properly managed clocks.
- You need to account for its relationship with `Date`, `Age`, and clock skew across systems.

In modern Spring Boot, **prefer Cache-Control** by default. Do not generate HTTP-dates using local time without GMT or rely on untrusted clocks.

## 5. ETag, Last-Modified, Conditional Requests, and 304

**Freshness** answers “can the stored copy be used without asking the server?”. **Validation** answers “after asking the server, is the stored copy still suitable?”.

### 5.1. ETag

Origin returns:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
ETag: "catalog-v2"
Content-Type: application/json

{"version":2,"name":"Catalog"}
~~~

After the TTL expires, the client can send:

~~~http
GET /api/catalog HTTP/1.1
If-None-Match: "catalog-v2"
~~~

If the current representation is still that version, the server returns:

~~~http
HTTP/1.1 304 Not Modified
ETag: "catalog-v2"
Cache-Control: public, max-age=300
~~~

304 contains no new representation body; the HTTP client uses the appropriate cached body per rules. If the content changed, the origin should return 200 and a different ETag.

**ETag must change when the representation changes.** Hardcoding a constant ETag for mutable database content will cause caches to reuse stale data incorrectly. Strong `"..."` and weak `W/"..."` ETags have different comparison semantics; do not use ETags as proof of user authentication or to embed tokens/sensitive identifiers.

### 5.2. Last-Modified

Static responses can send:

~~~http
Last-Modified: Sun, 08 Nov 2026 00:00:00 GMT
~~~

Clients revalidate via `If-Modified-Since`. This is modification-time metadata, which may not distinguish two changes within the same second or when storage systems lose timestamps. ETag can provide a better validator for many cases.

If a client sends both `If-None-Match` and `If-Modified-Since`, HTTP preconditions define precedence rules; do not arbitrarily return 304 just because one of them looks “old”.

### 5.3. 304 Must Still Enforce Authorization

For per-user resources, the server **must still verify current authentication and authorization** before considering returning 304. A matching ETag does not grant user B permission to use user A's cached representation. HTTP cache keys and data partitioning must be designed before enabling caching.

Spring MVC supports `ResponseEntity.eTag(...)`/`lastModified(...)` and `WebRequest.checkNotModified(...)`. `ShallowEtagHeaderFilter` can hash the body after rendering, usually saving bandwidth without necessarily avoiding the CPU cost of building the response; for expensive representations, computing validators early from version/metadata is more efficient.

## 6. Vary and Cache Keys: Why the Same URL May Not Mean the Same Data

Basic cache keys may rely on method and target URI, but responses can also vary by request headers. `Vary` indicates which headers must match when reusing a stored copy.

For example, an API responding by language:

~~~http
Cache-Control: public, max-age=60
Vary: Accept-Language
~~~

Without Vary (or an equivalent CDN cache key), the CDN could return a Vietnamese response to someone requesting English because the URL is identical.

Other scenarios:

- `Vary: Accept-Encoding` for `gzip`/`br`/uncompressed variants. When compressing, remember caching and compression are two separate mechanisms.
- `Vary: Origin` may be needed when CORS responses vary by Origin.
- `Vary: Cookie` or `Vary: Authorization` can make keys hard to manage and multiply variants; **they do not replace private/no-store or authorization**.
- Custom cache rules at a CDN may strip query params, cookies, or headers from the key; that is a major risk for user-dependent responses.

If the same URL `/api/me` returns profiles by session/cookie, **do not** use `public` just because a CDN advertises “cache key by cookie”. Prefer no-store for profiles/PII, unless the system is thoroughly designed and evaluated.

## 7. Practical Policy Matrix

| Target | Starting Cache-Control | Explanation |
| --- | --- | --- |
| Public CSS/JS/fonts/images with **content hash in URL** | `public, max-age=31536000, immutable` | Can be cached long-term, provided the URL changes when bytes change |
| Static assets with immutable release path like `/v7/site.css` | `public, max-age=31536000, immutable` | Only valid if v7 is never modified at the same URL |
| Static files at the same URL that can change | `no-cache` or `public, max-age=60` + validator | Need timely updates; do not hold stale code for a year |
| Non-personalized HTML entry page | `no-cache` + ETag/Last-Modified when helpful | Revalidate before reuse to pick up links to new assets |
| Logged-in user HTML | `no-store` if sensitive; occasionally `private, no-cache` if acceptable | Keep out of shared cache; consider logout/account switching |
| Slowly changing public catalog/news API | `public, max-age=300` + ETag; optional separate CDN policy | Trade staleness tolerance for performance |
| **Non-sensitive** user preferences | `private, max-age=60` if appropriate | Browser may store; CDN must not store |
| Profiles, tokens, balances, health, orders | `no-store` | Avoid storing sensitive HTTP responses per standard |
| Login/logout/password reset/session | `no-store` | Avoid caching session/auth-dependent responses |
| File downloads containing private documents | `no-store`; check auth; appropriate download headers | Avoid public cache and restrict browser cache |
| 404/301 errors that may change over time | Explicit policy, do not cache long-term if mutable | Some statuses can be heuristically cached |
| Public content allowed to serve stale during outages | TTL + controlled stale extensions | Only use when business accepts outdated information |

There is no single policy that fits an entire site. Classify based on **sensitivity, URL immutability, update frequency, SLA, staleness tolerance, and cache key**.

### 7.1. Versioned/Hashed Assets: Why Must the URL Change?

Example:

~~~text
Release 1: /assets/app.83caef2.css
Release 2: /assets/app.26b197a.css
~~~

If you edit CSS while keeping the URL `/assets/app.css` with a one-year TTL, browsers may continue using the old copy. `immutable` is only a directive; it **does not change the URL automatically** when a file changes. Version by content or release, update the HTML, and keep old assets around until HTML/browser tabs referencing older versions won't break.

HTML should have a short TTL or `no-cache` so browsers quickly pick up new asset URLs. Service workers, CDNs, and SPA shell caches also have their own rules that must be checked.

### 7.2. Personal Data: When private, When no-store?

`private, max-age=60` is for **low-sensitivity** content that you accept storing in the browser. `no-store` is better suited for account data / high exposure risk, or when logout must prevent reusing cached bodies.

Do not mistake `private` for encryption or access control. Another user sharing the same browser profile could see stale data; cache policies do not replace HTTPS, session invalidation, Secure/HttpOnly/SameSite cookies, and endpoint authorization.

## 8. Spring Boot Configuration: Static Resources and HTTP Responses

Spring Boot MVC typically uses static locations:

~~~text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
~~~

For example, `src/main/resources/static/assets/site.css` can be served at `/assets/site.css` by default, depending on `spring.mvc.static-path-pattern` and resource handler configuration.

### 8.1. Using Properties to Set a Global Policy for Default Static Resource Handlers

~~~properties
# Applies only to Boot's default static resource handling.
spring.web.resources.cache.cachecontrol.cache-public=true
spring.web.resources.cache.cachecontrol.max-age=10m

# Example simple duration-based policy:
# spring.web.resources.cache.period=600

# Allow using Last-Modified if supported by the resource.
spring.web.resources.cache.use-last-modified=true

# Configure content-based versioning strategy when needed:
# spring.web.resources.chain.strategy.content.enabled=true
# spring.web.resources.chain.strategy.content.paths=/**
~~~

The `spring.web.resources.cache.*` properties **do not automatically apply TTLs** to JSON responses produced by `@RestController`. Do not set a long global cache for static resources that mix mutable and versioned files. To separate policies by URL, use `WebMvcConfigurer` or verified CDN rules.

Spring provides `VersionResourceResolver` and `ResourceUrlProvider` to support content-hash-based URL versioning. Enabling the resolver while still hardcoding unversioned URLs in HTML **does not guarantee cache busting**; URLs must be generated/rewritten appropriately or your build pipeline must emit hashed filenames.

### 8.2. Using CacheControl in Controllers

For dynamic responses, Spring MVC can set policies per method:

~~~java
// Illustrative controller snippet with ResponseEntity and CacheControl imported:
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(privateResult);
~~~

For public resources:

~~~java
// Illustrative, public representation with 5-minute TTL:
return ResponseEntity.ok()
        .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic())
        .eTag("\"version-123\"")
        .body(publicResult);
~~~

ETags must come from real versions/representations, not hardcoded when data can change.

## 9. Runnable Java 17 Example: Versioned Static, Mutable Static, and Private API

The Spring Boot project below provides these endpoints:

- `GET /assets/versioned/v1/site.css`: versioned CSS, public, 365-day TTL, immutable.
- `GET /assets/live/site.css`: mutable CSS at the same URL, no-cache.
- `GET /page`: HTML entry page, no-cache.
- `GET /api/catalog`: public JSON, max-age=300 and fixed ETag since the demo content is fixed.
- `GET /api/demo/preference?theme=blue`: illustrates low-sensitivity personal data, private/max-age=60. **No auth**, header example only.
- `GET /api/demo/account`: simulated sensitive response, no-store. **Returns no real account data**.
- `GET /api/legacy/notice`: server-generated Expires relative to UTC time (no max-age set).

### 9.1. Project Structure

~~~text
http-cache-demo/
  pom.xml
  src/main/java/com/example/cachepolicy/
    CachePolicyApplication.java
    StaticCacheConfig.java
    CachePolicyController.java
  src/main/resources/
    application.properties
    static/assets/versioned/v1/site.css
    static/assets/live/site.css
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

`spring-boot-starter-webmvc` is the MVC starter for Spring Boot 4.x; Spring Boot 3.x applications typically use `spring-boot-starter-web`. The demo omits Spring Security so headers from code are clearly visible, though that **does not mean** the illustrative endpoints are safe for real data.

### 9.3. CachePolicyApplication.java

~~~java
package com.example.cachepolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CachePolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CachePolicyApplication.class, args);
    }
}
~~~

### 9.4. StaticCacheConfig.java

~~~java
package com.example.cachepolicy;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class StaticCacheConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/versioned/**")
                .addResourceLocations("classpath:/static/assets/versioned/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable());

        registry.addResourceHandler("/assets/live/**")
                .addResourceLocations("classpath:/static/assets/live/")
                .setCacheControl(CacheControl.noCache());
    }
}
~~~

- URL `/assets/versioned/v1/site.css` maps to classpath `/static/assets/versioned/v1/site.css`.
- `CacheControl.maxAge(Duration.ofDays(365))` equals 31,536,000 seconds; `cachePublic()` allows shared caches; `immutable()` is only valid if bytes under `/v1` never change.
- `CacheControl.noCache()` for `live` requires caches to revalidate before reuse. Revalidation can use the resource file's `Last-Modified`.
- The two URL patterns do not overlap, avoiding policy conflicts.
- Do not place personal files in `static/`: static resource handlers are not the place to enforce per-file auth.

### 9.5. CachePolicyController.java

~~~java
package com.example.cachepolicy;

import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CachePolicyController {

    @GetMapping("/api/catalog")
    public ResponseEntity<Map<String, String>> catalog() {
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic())
                .eTag("\"catalog-v1\"")
                .body(Map.of(
                        "version", "1",
                        "name", "HTTP cache demo"));
    }

    @GetMapping("/api/demo/preference")
    public ResponseEntity<Map<String, String>> preference(
            @RequestParam(defaultValue = "dark") String theme) {
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePrivate())
                .body(Map.of("theme", theme));
    }

    @GetMapping("/api/demo/account")
    public ResponseEntity<Map<String, String>> account() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "notice", "No real account data is exposed"));
    }

    @GetMapping("/page")
    public ResponseEntity<String> page() {
        String html = """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="utf-8">
                  <title>HTTP Cache</title>
                  <link rel="stylesheet" href="/assets/versioned/v1/site.css">
                </head>
                <body>
                  <h1>Cache policy demo</h1>
                  <p>HTML revalidates; versioned CSS is cached long-term.</p>
                </body>
                </html>
                """;

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_HTML)
                .cacheControl(CacheControl.noCache())
                .body(html);
    }

    @GetMapping("/api/legacy/notice")
    public ResponseEntity<Map<String, String>> legacyNotice() {
        String expires = DateTimeFormatter.RFC_1123_DATE_TIME.format(
                ZonedDateTime.now(ZoneOffset.UTC).plusMinutes(2));

        return ResponseEntity.ok()
                .header(HttpHeaders.EXPIRES, expires)
                .body(Map.of("notice", "Expires-only example"));
    }
}
~~~

**Important points:**

- The catalog data is constant, so ETag `"catalog-v1"` demonstrates the validator; if content changes, the ETag must be updated. Spring MVC handles conditional requests matching the `ResponseEntity` ETag and can return 304 when the client sends a matching `If-None-Match`.
- `preference()` and `account()` have no authentication **solely to simulate the two cache policies**. Do not copy the demo as an endpoint for real sensitive data without adding login and permission checks.
- `page()` returns an HTML body directly because no template engine is needed to demonstrate headers. In a Thymeleaf-rendered application, policies still need to be set on controller/handler responses.
- `legacyNotice()` generates a GMT/UTC HTTP-date via standard Java APIs, adding Expires without automatically adding Cache-Control. Actual headers also depend on proxies/filters/runtime configuration.

### 9.6. Resource Files

**src/main/resources/application.properties**

~~~properties
server.port=8080

# Static policies by URL are configured in StaticCacheConfig.
# Avoid setting a long public TTL uniformly for all resources.
~~~

**src/main/resources/static/assets/versioned/v1/site.css**

~~~css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem;
}
h1 {
    color: #1769aa;
}
~~~

**src/main/resources/static/assets/live/site.css**

~~~css
body {
    background-color: #f3f5f7;
}
~~~

When editing versioned CSS in production, add a new URL such as `/assets/versioned/v2/site.css`; do not overwrite version 1. In practice, using content hashes in the build pipeline eliminates manual versioning mistakes.

### 9.7. Run and Verify

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal (cURL to show status and headers):

~~~bash
curl -i http://localhost:8080/assets/versioned/v1/site.css
~~~

Expect 200, CSS Content-Type, and Cache-Control containing the directives:

~~~http
Cache-Control: max-age=31536000, public, immutable
~~~

The print order of other headers is not fixed in this lesson.

~~~bash
curl -i http://localhost:8080/assets/live/site.css
~~~

Expect 200, with the response containing:

~~~http
Cache-Control: no-cache
~~~

~~~bash
curl -i http://localhost:8080/page
~~~

Expect 200 with HTML `Content-Type` and `Cache-Control: no-cache`; the HTML references `/assets/versioned/v1/site.css`.

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Expect 200 with the headers:

~~~http
Cache-Control: max-age=300, public
ETag: "catalog-v1"
Content-Type: application/json
~~~

The JSON body has two fields `version` and `name`; key order may vary. To test revalidation:

~~~bash
curl -i -H 'If-None-Match: "catalog-v1"' \
  http://localhost:8080/api/catalog
~~~

Expect **304 Not Modified** and no representation body when Spring MVC receives the matching ETag and content is unchanged. If additional proxies/filters exist, test directly against the origin first.

~~~bash
curl -i "http://localhost:8080/api/demo/preference?theme=blue"
curl -i http://localhost:8080/api/demo/account
~~~

The preference response contains `private, max-age=60`; account contains `no-store`. This illustrates cache headers, **not** a complete account protection model.

~~~bash
curl -i http://localhost:8080/api/legacy/notice
~~~

Expect `Expires` as an HTTP-date roughly **two minutes after the request was processed**. Format example:

~~~http
Expires: Sun, 08 Nov 2026 01:02:00 GMT
~~~

The timestamp illustrates syntax and is **not** fixed; the program generates the value dynamically from the server's clock.

On Windows PowerShell, use `curl.exe` to invoke cURL directly, for example:

~~~powershell
curl.exe -i http://localhost:8080/api/catalog
curl.exe -i -H 'If-None-Match: "catalog-v1"' http://localhost:8080/api/catalog
~~~

Package the application:

~~~bash
mvn package
java -jar target/http-cache-demo-0.0.1-SNAPSHOT.jar
~~~

Because of Spring Boot dependencies, plain `javac` lacks the required classpath; build with Maven.

## 10. Common Confusions in Real-World Environments

### 10.1. Request Directives and Response Directives Differ

A client can send:

~~~http
GET /api/catalog HTTP/1.1
Cache-Control: no-cache
~~~

This asks caches not to reuse a stored response without revalidating. It **does not instruct** the server to purge content from all caches. Conversely, a response `Cache-Control: no-cache` is the origin's instruction regarding future reuse.

Reload/hard reload buttons or “Disable cache” in DevTools can cause the browser to send special headers or bypass caches; do not treat that behavior as sole proof of production configuration.

### 10.2. 304 Is a Bandwidth Optimization Without a New Body

304 can carry metadata such as ETag and Cache-Control and carries no new representation body. The browser keeps the old body if cache validation succeeds. If an endpoint serves personal data, the server must still verify the current user before deciding on 304. Do not use a shared version ETag to bypass authorization checks.

### 10.3. no-cache + must-revalidate Does Not Become no-store

`must-revalidate` means **once stale**, the cache must not serve stale content without verification. `no-cache` requires revalidation before reuse from the start. Neither is equivalent to `no-store`, so neither is appropriate if the goal is “do not store sensitive content”.

### 10.4. Use Stale Extensions for Public Content, Not Balances

`stale-while-revalidate` and `stale-if-error` can help a CDN serve public responses while the origin is slow or failing. They are not suitable for all data: if financial data, permissions, or order status notifications must be fresh, uncontrolled stale serving must be forbidden. Avoid combining directives with conflicting semantics without understanding how the specific cache implements them.

### 10.5. 404/Redirects Can Also Be Cached

Some status codes are eligible for heuristic caching under the HTTP standard. If `/product/123` does not exist today and is created tomorrow, a CDN may continue returning a cached 404 if the policy is unclear. Permanent redirects can also be cached; changing mappings later requires accounting for both caches and browser history. Set explicit cache policies for errors/redirects and purge when needed.

### 10.6. HTML Containing Old Links Breaks Cache Busting

Changing a CSS URL by hash while caching HTML for a year can cause browsers to keep loading the previous CSS. Use long caching for immutable assets **and short caching/no-cache for entry HTML**, while retaining old asset versions during an appropriate deployment/rollback window.

## 11. Spring Security, CDN, and Service Workers

### Spring Security Adds Default Anti-Cache Headers

When integrating Spring Security, the default typically includes:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

The goal is to prevent storing user content in HTTP caches by default. Spring Security can defer to the application's policy if the response already sets its own Cache-Control. Do not disable default security headers **site-wide** just to make CSS/JS cache quickly. Configure public assets separately and verify headers after the entire filter chain.

### CDN/Gateway Can Override TTL

In production:

~~~text
Spring Boot -> Nginx/Envoy/Gateway -> CDN -> Browser
~~~

The CDN may have Edge TTLs, custom cache keys, purge policies, rules stripping query params, or other headers like Surrogate-Control. Inspect differences between the **origin response**, **gateway response**, **CDN response**, and **browser network traces**; do not assume Spring Boot properties are always the final policy the client receives.

In particular, never let a CDN cache responses with `Authorization`/cookies without proper classification. Personal data must be isolated per user/tenant and authorization-checked; use no-store when shared caching is not deliberately designed.

### Service Workers/Browser History

An application-authored Service Worker can store responses in Cache Storage, IndexedDB, or other storage APIs. `no-store` is solely an HTTP cache policy and does not automatically clear application-managed storage. On logout or account switch, the application must clear sensitive state/caches per its own lifecycle and recheck the session on back-navigation. Browser back-forward cache (bfcache) is not the same as HTTP caching and varies by browser/version; do not treat no-store as an absolute DOM-erasure measure.

## 12. Relationship to HTTP Compression

| Aspect | HTTP caching | HTTP compression |
| --- | --- | --- |
| Goal | Avoid resending/recomputing a representation | Reduce transferred bytes of a representation |
| Headers | Cache-Control, Expires, ETag, Last-Modified, Age, Vary | Accept-Encoding, Content-Encoding, Vary |
| Can work together? | Yes | Yes |
| Common mistake | Shared cache mistakenly stores a private response | Sending gzip to a client that does not accept it |
| Connection | Cache key must select the right variant | Vary: Accept-Encoding distinguishes variants |

Example:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=600
Content-Type: text/css
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

A CSS response can be both gzip-compressed and cached. `Cache-Control: no-transform` is not a toggle to enable/disable compression in Spring Boot; it restricts intermediaries from altering content per the directive's definition. When using precompressed assets, coordinate the resource resolver and versioning strategy rather than just flipping one property and assuming caching is right.

## 13. How to Test and Monitor Policies

Verification steps during deployment:

1. Use `curl -i` or the Network panel to inspect **response** Cache-Control/Expires/ETag/Vary.
2. Call the endpoint again with a valid `If-None-Match` to verify 304; modify the actual content and confirm the ETag changes.
3. Test public/anonymous, authenticated user A, and authenticated user B against the same URL. Never let A's private response be served by the CDN to B.
4. Check cache headers across logout, login, session timeout, permission changes, 404, redirects, and 500.
5. Test traffic through the proxy/CDN; compare cache HIT/MISS, Age, X-Cache (if present), cache key, and edge TTL.
6. For versioned assets, test a new release changing URLs while ensuring older versions still load for users/browsers that still need them.
7. When compression is enabled, check Vary and Content-Encoding per Accept-Encoding; do not let caches return mismatched bytes.
8. Test browsers holding stale HTML, service worker offline caches, and customers using multiple accounts on one device.

Suggested test commands:

~~~bash
curl -i http://localhost:8080/api/catalog
curl -i -H 'If-None-Match: "catalog-v1"' http://localhost:8080/api/catalog
curl -i http://localhost:8080/api/demo/account
curl -i http://localhost:8080/assets/versioned/v1/site.css
~~~

In integration tests with MockMvc, you can assert `no-store`/`private` headers and status 304; test code will need Spring MVC Test/JUnit dependencies compatible with your Boot version, outside the minimal Maven example above. When middleware alters response headers, test in a full environment rather than relying solely on controller unit tests.

### Useful Metrics

- Cache HIT/MISS and 304 ratio; bandwidth savings ratio.
- `Age`/remaining TTL; count of stale responses served per policy.
- Origin and CDN p95/p99 latency; request volume from CDN to origin.
- 4xx/5xx rate, repeated cached 404s, mis-cached redirects.
- Rate of responses tagged with an incorrect public/private/no-store classification.
- Incidents of cross-tenant/cross-user data leakage or stale data after logout (requires zero tolerance).

## 14. Common Mistakes and Fixes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Updated CSS, yet users still see old version | Long cache on unchanged URL, misapplied immutable | New version/hash URL; update HTML |
| New HTML is not picked up | Entry HTML also cached long-term, service worker retains old copy | no-cache/short TTL; audit SW/CDN |
| User B sees User A's data | Shared cache key missing auth or wrong public policy | Proper layer no-store/private, configure CDN, cross-user tests |
| `no-cache`, yet browser still holds body | `no-cache` allows storage and forces revalidation | If storage must be forbidden, use `no-store` |
| `max-age=0`, yet 304 requests still appear | `max-age=0` does not forbid storage | Valid behavior; use `no-store` if needed |
| `Expires` 1 hour, yet TTL is 60 seconds | `max-age` overrides `Expires` | Define clear policy and inspect headers |
| 304 even though new data changed | ETag kept unchanged or validator computed wrongly | Tie ETag to real representation/version |
| Static files don't cache when Spring Security is enabled | Default response headers/filter chain interferes | Set explicit cache policy for assets and verify response |
| Content languages get mixed up at proxy | Vary/cache key missing `Accept-Language` | Proper Vary or separate URLs |
| CDN serves wrong gzip variant | Incorrect key and `Vary: Accept-Encoding` | Configure variants and test clients |
| 404 persists after resource exists | Negative caching/heuristic caching | Short TTL/no-cache for 404, proper purge |
| Profile still visible after logout | HTTP cache or app storage/bfcache unhandled | no-store, clear state, recheck session |
| Using `private` for sensitive tokens | Browser still stores body | Use `no-store` |
| Enabling `public` on auth responses | Can open shared caching per RFC | Never `public` for private data, check CDN key |
| Confusing `@Cacheable` with HTTP caching | Server cache works, but clients see no `Cache-Control` | Design the two caches independently |

## 15. Pre-Deployment Design Checklist

- [ ] What category is the resource: public immutable, public mutable, public API, personalized, sensitive, or auth/session?
- [ ] Does the response contain tokens, PII, role/tenant-specific data, or strictly public content?
- [ ] For private content, is there a clear business reason to allow browser caching instead of `no-store`?
- [ ] For long static TTLs, **does the URL change when bytes change**, without overwriting older versions?
- [ ] Can the HTML entry page revalidate to link to new assets?
- [ ] Does every response have a clear policy that is not unintentionally altered by security filters/proxies/CDNs?
- [ ] Do ETag/Last-Modified accurately reflect the representation, and is 304 only returned after checking permissions?
- [ ] Do Vary/cache keys distinguish language, encoding, and conditions that alter the body?
- [ ] Have cross-user, logout, role change, 404, redirect, CDN hit, and static deploy scenarios been tested?
- [ ] Have response caching, `@Cacheable`, server-side data caching, Service Workers, and gzip been clearly separated?
- [ ] Are CDN purge plans, asset version rollback, observability, and response header contracts in place?

### Quick Decision Flow

~~~text
Contains sensitive data, session/tokens/PII?
   -> no-store + HTTPS + authorization.

Non-sensitive, yet per-user response?
   -> private + short TTL only if browser storage is acceptable;
      when unsure, no-store.

Public resource with immutable hashed/versioned URL?
   -> public, max-age=31536000, immutable.

Public resource whose same URL can change?
   -> no-cache + validator or short max-age.

Public API tolerating at most X seconds of staleness?
   -> public, max-age=X + ETag; design s-maxage if CDN is permitted.

Uncertain about cache key or sensitivity?
   -> Do not enable public/long TTL before verifying.
~~~

## 16. Self-Check Questions with Answers

**Question 1.** Does `no-cache` prevent the browser from storing HTML?

**Answer:** No; caches may store it, but must revalidate before reuse. An ETag can allow the server to return 304 without a body.

**Question 2.** Is `private, max-age=300` appropriate for a page containing tokens or account balances?

**Answer:** Not recommended. A private browser cache can still store it; for sensitive content, prioritize `no-store` and secure auth/session design.

**Question 3.** A response has `Expires` 30 minutes in the future and `max-age=60`. Which TTL wins?

**Answer:** `max-age` 60 seconds wins; shared caches will use `s-maxage` if sent.

**Question 4.** Why is enabling `immutable` on `/app.js` alone insufficient?

**Answer:** If the URL does not change when bytes change, the browser may keep the old JS. Hashed/versioned URLs and HTML updates are required.

**Question 5.** If an `Authorization` header is in the request, is the CDN guaranteed not to cache?

**Answer:** Not unconditionally: the RFC has cases where response directives allow shared caching, and CDNs have their own configurations. Never use `public`/`s-maxage` for account-specific data.

**Question 6.** Is `max-age=0` the same as `no-store`?

**Answer:** No; the response can still be stored, it is just immediately stale. Revalidation with ETag/304 remains meaningful.

**Question 7.** If JSON changes while ETag stays the same, what happens?

**Answer:** Clients may receive 304 and reuse the old body; ETag must change with the actual version/representation.

**Question 8.** Why does a multi-language API need Vary?

**Answer:** So caches do not mistakenly serve a body generated for a different `Accept-Language` at the same URL.

**Question 9.** Are gzip and caching the same mechanism?

**Answer:** No; gzip reduces transferred bytes, caching reuses responses; `Vary: Accept-Encoding` may be needed for variants.

**Question 10.** Does using `no-store` guarantee data is erased everywhere after logout?

**Answer:** No. It governs compliant HTTP caches; it does not clear browser storage/app state or replace authentication/HTTPS.

## 17. References

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html) — Cache-Control, Expires, freshness, shared caches, conditional responses.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — HTTP-date, validators, conditional requests, status codes.
- [Spring Framework — HTTP Caching in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html) — CacheControl, ETag, Last-Modified.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html) — ResourceHandlerRegistry, VersionResourceResolver, CacheControl.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — spring.web.resources.cache.*.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html) — static resources and MVC.
- [Spring Framework — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html) — noCache, noStore, cachePrivate, immutable.
- [Spring Security — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) — default cache headers and customization.
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/) — Spring Boot version used in the example.

**Remember:** Classify your data **before** choosing a TTL. For immutable versioned/hashed static assets, cache very long-term; for HTML and mutable resources, use short TTLs or revalidation; for low-sensitivity personal data, use `private` only when browser storage is acceptable; for sensitive data, prefer `no-store`. `max-age`/`s-maxage` take precedence over `Expires`; validators enable 304; every configuration must be verified at the origin, proxy/CDN, and browser.