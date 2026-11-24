# Cache-Control, Expires, and Browser Cache vs. Shared Cache in Spring MVC

## 1. Why Does HTTP Caching Matter?

A client calls `GET /api/products` and receives 100 KB of JSON. If every time a user reopens the page the full response has to be downloaded from the origin server, the network and backend do extra work. **HTTP caching** lets a client or intermediary reuse an HTTP response while it is still valid, or **revalidate** with the server to avoid transferring an unchanged body.

However, not all data is suitable for a shared cache. If the response to `GET /api/me` contains a name, email, or balance and gets served by a CDN/proxy to another user, a caching bug can become a data leak vulnerability. Therefore, understanding `Cache-Control` and `Expires` is part of **HTTP protocol design and security**, not just a speedup trick.

After this lesson, you will be able to:

1. Distinguish between a **private cache** (typically a browser) and a **shared cache** (reverse proxy, CDN, forward proxy).
2. Explain why **storage**, **freshness** lifetime, and **revalidation** conditions are three separate decisions.
3. Properly use `max-age`, `s-maxage`, `private`, `public`, `no-cache`, `no-store`, `must-revalidate`, `immutable`, and `Expires`.
4. Know why requests with `Authorization`, responses with `Set-Cookie`, or session usage require strict cache policy review.
5. Design caching for public resources, dynamic HTML, personalized APIs, and sensitive data.
6. Use `org.springframework.http.CacheControl`, `ResponseEntity`, `ETag`, and Spring static resource handling.
7. Write contract tests with MockMvc, inspect headers with curl, and avoid cache leakage risks.

**Scope:** Spring Web MVC (Servlet stack), **Java 17, Spring Boot 3.3.5 / Spring Framework 6.1.x**, HTTP caching per **RFC 9111 (HTTP Caching)** and conditional requests per RFC 9110. This lesson does not replace vendor-specific CDN policies, nor is it about Spring `@Cacheable` for caching method results in the JVM/Redis.

## 2. Where Do HTTP Caches Live?

```text
┌──────────────────┐
│ User A's Browser │
│ private HTTP     │
│ cache            │
└────────┬─────────┘
         │ HTTP request
         ▼
┌──────────────────┐
│ Shared cache /   │
│ CDN / proxy      │
│ (many clients)   │
└────────┬─────────┘
         │ may forward to origin
         ▼
┌──────────────────┐
│ Spring MVC       │
│ origin server    │
└──────────────────┘
         ▲
         │
┌────────┴─────────┐
│ User B's Browser │
│ private cache    │
└──────────────────┘
```

This diagram is conceptual, not a mandatory topology. Some systems have multiple CDNs/proxies, while others have no shared cache.

### 2.1. Private Cache

A **private cache** is tied to a single user/client, typically the browser HTTP cache. A response with personal data **can be cached in that user's browser** if policy allows and it is beneficial, but it must not appear in a shared cache.

Example:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60

{"displayName":"Lan"}
```

Basic meaning:

- `private`: a **shared cache must not store the response** (in its unqualified directive form).
- `max-age=60`: under normal conditions, a private cache may consider the response fresh for up to 60 seconds, taking `Age`/`Date` and age calculation rules into account.
- It does not mean the data is encrypted or only readable by the right user. Browser history, disk storage, local access, sessions, or how the browser isolates its cache still need consideration.
- If sensitive data must not be stored on the device at all, use `no-store` instead of `private`.

### 2.2. Shared Cache

A **shared cache** reuses responses across multiple clients. A CDN sitting in front of the origin is a common example. When receiving public data with the right policy, a CDN can serve the body directly without calling Spring MVC on every request.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=120, s-maxage=600

{"siteName":"Java Learning","theme":"light"}
```

- The browser can consider the response fresh for about **120 seconds**.
- A shared cache can consider the response fresh for about **600 seconds** thanks to `s-maxage` (if other storage/reuse conditions are also met).
- `public` allows shared caches to store responses that would normally be restricted, even responses to requests carrying `Authorization`; therefore, only use it when you are sure the representation is safe to share.
- Directives do not guarantee a CDN will actually store it: the CDN might have caching disabled, be capacity-limited, or enforce its own rules.

### 2.3. Shared Cache Is Not the Same as a Database Cache

An HTTP cache stores and reuses **HTTP responses** keyed by URL, method, selected request headers, response headers, and HTTP rules.

Spring `@Cacheable` typically caches **method return values** inside the application/Redis/Ehcache. It does not automatically generate `Cache-Control`, honor `Vary` or `Authorization`, or return HTTP `304`. Conversely, adding `Cache-Control` does not make `@Cacheable` work. Both layers can complement each other, but they must be designed independently.

## 3. Three Questions a Cache Must Answer

A cache cannot just see `200 OK` and decide to store it forever. It must answer:

1. **Is the response allowed to be stored?** Depends on method, status, `Cache-Control`, `Authorization`, private/shared restrictions, and RFC rules.
2. **If stored, is it still fresh?** Depends on `max-age`, `s-maxage`, `Expires`, `Date`, `Age`, and elapsed time; heuristic freshness may apply when an explicit policy is absent.
3. **If stale, can it still be reused?** It may be revalidated successfully via `ETag`/`Last-Modified`, or in certain cases served stale if permitted. `no-cache`/`must-revalidate` impose strict conditions.

```text
Client GET /public/config
         |
         v
   Cache has entry?
      /       \
     No       Yes
     |         |
     v         v
  Forward    Entry still fresh?
  origin       /         \
             Yes          No
              |            |
              v            v
            Reuse      Validate with origin?
            body        /               \
                     304             200 changed
                      |                   |
                      v                   v
                 Reuse stored       Store new response
                 representation     if permitted
```

This is a simplified flow. A cache may bypass an entry, decline to store, evict entries, or need to honor `Vary`, `Authorization`, and additional cache directives. HTTP `304 Not Modified` **is not a new JSON body**; it updates certain metadata/validators of the cached response and enables reusing the stored representation.

## 4. Core Cache-Control Directives

`Cache-Control` can appear in both **requests** and **responses**; its meaning depends on position. The following primarily covers **response Cache-Control**, as Spring MVC controllers manage the policy for data they return.

| Response directive | Primary meaning | Key takeaway |
| --- | --- | --- |
| `max-age=N` | Freshness lifetime of N seconds for affected caches | Not "store for N seconds then delete"; stale entries can remain for revalidation |
| `s-maxage=N` | Freshness for **shared caches**, overriding `max-age` and `Expires` | Browsers/private caches ignore `s-maxage` |
| `public` | Allows shared caching in cases that would normally be restricted | Be extremely cautious with personalized/authenticated responses |
| `private` | Prohibits **shared caches** from storing the response; private caches still may | Not equivalent to `no-store` |
| `no-cache` | May be stored, but **must be validated before every reuse** | Does not mean "do not cache" |
| `no-store` | Caches must not store the request/response per directive | Use for confidential data, though it does not guarantee purging old caches |
| `must-revalidate` | Once stale, must not be reused before successful validation | Does not mean "always revalidate" while still fresh |
| `proxy-revalidate` | Same idea as `must-revalidate` but for shared caches | Requires other storage/freshness policies as well |
| `no-transform` | Intermediaries must not transform the response content | Useful for format-sensitive bytes and media |
| `immutable` | Representation is not expected to change during its freshness lifetime | Use for hashed/versioned assets, not dynamic data |
| `stale-while-revalidate=N` | Allows serving stale briefly while revalidating asynchronously | Cache must support it; do not use for strictly current data |
| `stale-if-error=N` | Allows serving stale for a window when encountering specific errors | Not unconditionally suitable for update-sensitive data/prices |

### 4.1. no-cache vs. no-store

Two responses:

```http
Cache-Control: no-cache
```

and

```http
Cache-Control: no-store
```

**are not equivalent**.

- `no-cache` **allows storing** the response, but before **every reuse**, the cache must validate it with the origin (usually via a conditional request and `304`). It saves body transfer when the response has not changed.
- `no-store` instructs caches **not to store** the response per the RFC, reducing the risk of sensitive data lingering in browsers/proxies. However, it cannot delete an earlier cached copy just by sending a new header, because an old cache might not contact the origin.
- Use `private, no-cache` for personal content that can be kept temporarily in the browser but needs revalidation on every reuse.
- Use `no-store` when no cache should retain the data—for example, responses containing access tokens, secret reset links, sensitive reports, or financial information requiring storage restrictions.

**Security note:** HTTP caching directives do not replace TLS, authentication, authorization, encryption at rest, or true cache eviction across every environment. A non-compliant or malicious cache may ignore them.

### 4.2. max-age Is Not an Absolute Retention Timer

`Cache-Control: max-age=120` does not mean "delete the response exactly 120 seconds after the browser clicks GET." It indicates the maximum freshness lifetime of the response, measured against its **current age**. A shared cache might have already held the response for 30 seconds before sending it to the browser; an `Age: 30` header indicates the browser only has about 90 seconds of freshness left if no other details apply.

The full RFC calculation considers `Date`, `Age`, apparent age, response delay, and resident time. For fundamentals, remember: **Age consumes part of max-age**; you do not get a fresh N seconds added at every cache tier.

### 4.3. s-maxage vs. max-age

```http
Cache-Control: public, max-age=60, s-maxage=300
```

For a public response eligible for storage, browsers/private caches use up to **60s**, while shared caches use up to **300s** as the freshness lifetime. `s-maxage` also carries shared-cache revalidation semantics when stale. Do not assume that after 60s the browser will always get brand-new data from the origin: the browser may ask the CDN, and the CDN can still serve its own fresh response.

If you need rapid updates for users while reducing origin requests, you must design CDN cache lifetimes and invalidation appropriately, because a long `s-maxage` can delay visibility of new content.

### 4.4. public and private Do Not Express Access Permissions

`public` means the response **may be stored in shared caches** under HTTP rules, not that any user is authorized to read the API. `private` means it must not be stored in a shared cache, and **does not guarantee** server-side ACLs/authentication. A private API must still verify user/tenant permissions on every request reaching the origin.

A dangerous mistake is adding `public`/`s-maxage` to an API with `Authorization` to "boost hit rate" without proving the data is strictly a public representation. Accidentally specifying `public` can cause shared caches to reuse an authenticated response for another user under RFC rules.

## 5. Expires: Clock-Based Freshness Expiration

`Expires` is an HTTP response header containing an absolute **HTTP-date**:

```http
Date: Wed, 21 Oct 2026 10:00:00 GMT
Expires: Wed, 21 Oct 2026 10:02:00 GMT
```

Without higher-precedence cache directives, this example declares a freshness lifetime of roughly 120 seconds from `Date`. `Expires` is a **GMT timestamp**, not a number of seconds. `Expires: 120` is invalid per the standard.

Compare:

```http
Cache-Control: max-age=120
```

and

```http
Expires: Wed, 21 Oct 2026 10:02:00 GMT
```

- `max-age` expresses a duration, avoiding many risks from unsynchronized origin/client clocks.
- `Expires` is an absolute date, easily misinterpreted if `Date` is inaccurate or server/CDN time handling is off.
- Both can be sent for legacy client compatibility, but **`Cache-Control: max-age` takes precedence over `Expires`**.
- In shared caches, `s-maxage` also overrides both `Expires` and `max-age` for shared freshness.
- An `Expires` date in the past indicates the response is already stale; it does not necessarily forbid storage (unlike `no-store`).
- Never use client-supplied time to decide server data validity; HTTP-date is protocol metadata.

### 5.1. Common Precedence Rules

Given a response:

```http
Cache-Control: public, max-age=60, s-maxage=300
Expires: Thu, 22 Oct 2026 10:00:00 GMT
```

- Shared caches follow `s-maxage=300`.
- Private caches/browsers follow `max-age=60`.
- `Expires` is ignored whenever the corresponding cache lifetime directive is specified.

This is the **precedence model**. Cache storage/reuse remains subject to other RFC 9111 conditions, such as method/status, authorization, `Vary`, and directive details.

### 5.2. Expires Does Not Force Storage

`Expires` or `max-age` primarily controls freshness if the response is **eligible to be stored**. Having a future `Expires` does not bypass `Cache-Control: no-store` or `private` on a shared cache. The "may it be stored?" step comes before "how long is it fresh?".

## 6. Browser Cache, CDN, Proxy: Practical Behavior Examples

Suppose browser A requests `GET /assets/app.81d31a.js` and the CDN returns:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript
Cache-Control: public, max-age=31536000, immutable
ETag: "sha256-81d31a"
```

Because the URL contains a content hash, the same URL always maps to the same content. Browsers and shared caches can keep the response for a long time (if capacity/policy permit), saving bandwidth. When deploying a new version, the HTML references a **new URL**; bytes at the old hashed URL are never overwritten.

Conversely:

```http
GET /dashboard
Cookie: SESSION=...
```

A personal dashboard response might return:

```http
HTTP/1.1 200 OK
Cache-Control: private, no-cache
ETag: "account-42-v7"
Vary: Accept-Language

[HTML for the logged-in account]
```

The browser can retain a copy and revalidate it, while shared caches must not store it. If the dashboard displays sensitive secrets, consider `no-store`.

### Policy Selection Table by Scenario

| Content | Example policy | Notes |
| --- | --- | --- |
| Fingerprinted JS/CSS in URL | `public, max-age=31536000, immutable` | Only when bytes are truly immutable for the same URL |
| Public announcements updated hourly | `public, max-age=60, s-maxage=300` | CDN may lag up to policy lifetime without purging |
| HTML shell changing on each deploy | `no-cache` | Allows storing and validating before reuse |
| Standard account info API | `private, no-cache` | Browser may store; revalidate on each use |
| Private report API allowing 30s staleness | `private, max-age=30` | Only when business logic accepts 30s-old data |
| API returning tokens/credentials/secrets | `no-store` | Do not rely on private cache being completely safe |
| Public resource with ETag | `public, max-age=120` + ETag | Can return 304 once stale |
| Login/error page with personal content | `no-store` or `private, no-cache` depending on sensitivity | Consider session, bfcache, and security |
| Rapidly changing price/inventory GET | `no-cache` or very short freshness | Never use cache as source of truth for checkout |
| Explicitly versioned public docs | `public, max-age=600` | Change URL or purge when republishing |

These policies are **design examples**; no single value fits every API.

## 7. Authorization and Set-Cookie: Shared Cache Risk Areas

### 7.1. The Authorization Header

RFC 9111 restricts **shared caches** by default from reusing responses to requests containing an `Authorization` header. However, certain directives **allow** shared caching under specific conditions:

- `public`;
- `s-maxage`;
- `must-revalidate` (subject to specific rules; does not mean always fresh or cacheable by default).

**Therefore, never say "having Authorization means CDNs absolutely never cache."** If a controller or gateway adds `Cache-Control: public`, authenticated data can become shared-cacheable when other conditions hold. Review policies endpoint by endpoint.

Dangerous example:

```http
GET /api/me HTTP/1.1
Authorization: Bearer user-A-token

HTTP/1.1 200 OK
Cache-Control: public, s-maxage=600

{"email":"user-a@example.com"}
```

This is a **risk anti-pattern**, not a recommended policy. If the shared cache key does not safely isolate by user or bypass caching, personal data can reach the wrong client.

### 7.2. Cookie/Set-Cookie Does Not Automatically Block Caching

A request containing `Cookie` or a response containing `Set-Cookie` **does not automatically mean HTTP forbids all shared caches from storing it**. Many CDNs have vendor rules like bypassing on cookies or not caching `Set-Cookie` responses, but those are **product/CDN configurations**, not a substitute for `Cache-Control`.

For content personalized via a session cookie:

```http
Cache-Control: private, no-cache
```

or if sensitive:

```http
Cache-Control: no-store
```

must be set **explicitly** and tested through the real CDN/ingress path. Do not use `Vary: Cookie` as a "silver bullet" instead of `private`: `Vary` can create massive variant counts, configuration risks, and cache key pitfalls. For private APIs, shared caching should be disallowed by policy rather than trying to cache per session cookie.

### 7.3. Limits of Cache Isolation

Even `private` or `no-store` does not replace authn/authz, TLS, and local browser controls. A system used on shared computers still needs timeouts, logout, cookie controls, and device access permissions. `no-store` does not erase an old unrefreshed entry merely by sending a new response if the cache never calls the origin; you must combine versioned URLs, invalidation, auth, and actual cache policies.

## 8. ETag, Last-Modified, and HTTP 304

`Cache-Control` governs how a cache may reuse a response. **ETag** and **Last-Modified** are validators that let a cache ask the server whether its stored copy is still valid:

```text
1. GET /api/public/config
   -> 200 OK
      Cache-Control: no-cache
      ETag: "config-v3"
      Body: {"theme":"light"}

2. GET /api/public/config
   If-None-Match: "config-v3"
   -> 304 Not Modified
      ETag: "config-v3"
      [no response body]

3. Client/cache reuses body of the stored copy
```

- `no-cache` still allows step 3 if validation succeeds.
- `304 Not Modified` saves body bandwidth and updates certain entry metadata; it **does not synthesize** data for a client that has no cached representation.
- `Last-Modified` and `If-Modified-Since` are an alternative mechanism using HTTP-dates. Timestamps have resolution and precision limitations, so `ETag` is usually more flexible when representations change frequently.
- When both `If-None-Match` and `If-Modified-Since` are present, HTTP defines validator precedence rules; do not check the two headers independently and wrongly return 304.
- `ETag` must reflect the actual version/representation, not be randomized on every request (which destroys cache hits); if content is user-specific, the validator must also be tied to the right user and ACL.

### no-cache with ETag vs. no-store

`Cache-Control: no-cache` + `ETag` is a useful pattern for frequently changing public JSON/HTML: cached bytes can stay in the browser, but every reuse requires origin confirmation. `no-store` tells caches not to store the response at all, rendering cached-body revalidation inapplicable in the usual sense.

### Caching with Age and Request Cache-Control

A client can send:

```http
Cache-Control: no-cache
```

in a **request** to ask caches not to use a stored entry without validating it. It **cannot force the origin to produce fresh data** if the origin itself is stale, and request directives differ from response directives in who they govern. `Cache-Control: max-age=0` in a request typically asks for an entry with very low/non-stale age, which is not strictly identical to purging caches.

## 9. Vary: Caching Multiple Representations Properly

One URL can return different data depending on a request header:

```http
GET /help
Accept-Language: vi
```

and:

```http
GET /help
Accept-Language: en
```

If the server uses `Accept-Language` to choose the language, the response should include:

```http
Vary: Accept-Language
Cache-Control: public, max-age=300
```

A shared cache must account for `Vary` when selecting a stored response, avoiding serving the Vietnamese version to an English request. Similarly, for compressed vs. uncompressed content:

```http
Vary: Accept-Encoding
```

Key distinctions:

- `Vary` is **cache selection metadata**, not authorization or secret protection.
- `Vary: Cookie` or `Vary: Authorization` is often unsafe or impractical due to huge numbers of variants; user-specific content should generally use `private` or `no-store` with CDN bypass configured.
- APIs with query parameters must also be distinguished accurately by cache keys; some CDNs can be configured to ignore queries or normalize URLs. Query parameters containing secrets must never appear in URLs or logs.
- Returning different languages based on a session cookie while sending `Vary: Accept-Language` is broken, because the source determining the representation is not the `Accept-Language` request header.

## 10. Spring MVC: CacheControl API

Spring Framework provides `org.springframework.http.CacheControl` to build syntactically valid response headers. Key APIs:

```java
CacheControl.maxAge(Duration.ofSeconds(120));
CacheControl.noCache();
CacheControl.noStore();
CacheControl.maxAge(Duration.ofSeconds(120)).cachePublic();
CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate();
CacheControl.maxAge(Duration.ofSeconds(120))
        .sMaxAge(Duration.ofSeconds(600)).cachePublic();
CacheControl.maxAge(Duration.ofDays(365))
        .cachePublic().immutable();
```

These are **Java snippets** requiring `CacheControl` and `Duration` imports; they are not a standalone `main` program. The `cachePublic()`, `cachePrivate()`, `sMaxAge(Duration)`, and `immutable()` methods are present in Spring 6.1.

You can combine them with `ResponseEntity`:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(responseDto);
```

This example needs a `responseDto` variable and a matching return type; a complete controller is in section 11. `ResponseEntity.cacheControl(...)` sets the HTTP `Cache-Control` response header—it does not cache a Java object inside a Spring Service.

### Expires in ResponseEntity

Spring does not restrict you to `CacheControl`; you can set `Expires` with `ResponseEntity.header(...)`:

```java
String expires = ZonedDateTime.now(ZoneOffset.UTC)
        .plusSeconds(120)
        .format(DateTimeFormatter.RFC_1123_DATE_TIME);

return ResponseEntity.ok()
        .header(HttpHeaders.EXPIRES, expires)
        .body(responseDto);
```

This requires imports for `ZonedDateTime`, `ZoneOffset`, `DateTimeFormatter`, `HttpHeaders`, `ResponseEntity`, and a valid DTO. This is a **snippet**. To avoid generating an overly distant timestamp or an ambiguous local timezone, UTC + HTTP-date is the right choice. If adding `max-age` alongside `Expires`, remember **`max-age` wins** when caches support it.

## 11. Runnable Java 17 / Spring Boot 3.3.5 Project

We will build a REST API with five policy endpoints:

1. `GET /api/cache/public` — public data: browser fresh for 120 seconds, shared cache fresh for 600 seconds.
2. `GET /api/cache/revalidate` — public data, but **every reuse requires revalidation**, with a fixed ETag and `304` support.
3. `GET /api/cache/private-demo` — sample personal data with `private, max-age=60`.
4. `GET /api/cache/secret-demo` — sensitive demo data with `no-store`.
5. `GET /api/cache/expires` — `Expires`-only example demonstrating an absolute HTTP-date.

All endpoints return **static data with no authentication** so we can focus on HTTP caching. The names `private-demo` and `secret-demo` only illustrate header policies; these **are not real authenticated APIs** and do not generate or expose real secrets. Production code must obtain the principal from Spring Security and verify permissions before building a response.

### 11.1. Project Tree

```text
http-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/httpcache/
    │   ├── HttpCacheApplication.java
    │   └── CacheDemoController.java
    └── test/java/demo/httpcache/
        └── CacheDemoControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
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
```

**`src/main/java/demo/httpcache/HttpCacheApplication.java`**

```java
package demo.httpcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}
```

### 11.2. Controller with Explicit Policies

**`src/main/java/demo/httpcache/CacheDemoController.java`**

```java
package demo.httpcache;

import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cache")
public class CacheDemoController {

    public record Catalog(String siteName, String release) {}

    @GetMapping("/public")
    public ResponseEntity<Catalog> publicCatalog() {
        Catalog data = new Catalog("Java Learning", "2026.10");

        CacheControl cache = CacheControl
                .maxAge(Duration.ofSeconds(120))
                .cachePublic()
                .sMaxAge(Duration.ofSeconds(600));

        return ResponseEntity.ok()
                .cacheControl(cache)
                .body(data);
    }

    @GetMapping("/revalidate")
    public ResponseEntity<Map<String, String>> revalidate() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag("config-v1")
                .body(Map.of("theme", "light"));
    }

    @GetMapping("/private-demo")
    public ResponseEntity<Map<String, String>> privateDemo() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofSeconds(60))
                        .cachePrivate())
                .body(Map.of("displayName", "Example User"));
    }

    @GetMapping("/secret-demo")
    public ResponseEntity<Map<String, String>> secretDemo() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("notice", "Do not store this response"));
    }

    @GetMapping("/expires")
    public ResponseEntity<Map<String, String>> withExpires() {
        String expires = ZonedDateTime.now(ZoneOffset.UTC)
                .plusSeconds(120)
                .format(DateTimeFormatter.RFC_1123_DATE_TIME);

        return ResponseEntity.ok()
                .header(HttpHeaders.EXPIRES, expires)
                .body(Map.of("policy", "expires-only"));
    }
}
```

**Code explanation:**

- `@RestController` serializes DTOs/Maps to JSON via Jackson and `ResponseEntity` sets status/headers.
- The `public` endpoint deliberately sets `max-age=120` and `s-maxage=600` to illustrate the difference between browsers and CDNs. Only do this because the body is **public, non-user-specific** data.
- `revalidate` has `no-cache` + `ETag`. In Spring MVC, when a client sends `If-None-Match: "config-v1"`, the framework can turn `ResponseEntity` into `304 Not Modified` with an empty body.
- `private-demo` lets private caches retain the response for up to 60s; shared caches are barred from storing it via `private`.
- `secret-demo` instructs all caches not to store; the JSON here is just a **dummy string**, with no real secret.
- `expires` builds an HTTP-date at request time plus 120s; it **omits Cache-Control max-age** so you can study `Expires` precedence and syntax separately.
- None of the endpoints use `@Cacheable` because the focus here is HTTP response caching, not method-level caching.
- `ETag` `config-v1` is only valid as long as the actual representation's bytes/semantics do not change within that version. If you change the JSON body without updating the ETag, the server may wrongly return `304` for a stale cached body.

### 11.3. Running and Testing with curl

From the `http-cache-demo` directory containing `pom.xml`, with Java 17+ and Maven installed:

```bash
mvn test
mvn spring-boot:run
```

These are **two sequential commands**. With the server on `localhost:8080`, try:

```bash
curl -i http://localhost:8080/api/cache/public
```

Key headers and body (JSON field ordering is not guaranteed):

```http
HTTP/1.1 200
Content-Type: application/json
Cache-Control: max-age=120, public, s-maxage=600

{"siteName":"Java Learning","release":"2026.10"}
```

Next:

```bash
curl -i http://localhost:8080/api/cache/private-demo
```

Expected:

```http
HTTP/1.1 200
Cache-Control: max-age=60, private

{"displayName":"Example User"}
```

The `secret-demo` response includes:

```http
HTTP/1.1 200
Cache-Control: no-store
```

First fetch the response with an ETag:

```bash
curl -i http://localhost:8080/api/cache/revalidate
```

Expected:

```http
HTTP/1.1 200
Cache-Control: no-cache
ETag: "config-v1"

{"theme":"light"}
```

Send a conditional GET:

```bash
curl -i \
  -H 'If-None-Match: "config-v1"' \
  http://localhost:8080/api/cache/revalidate
```

Spring MVC should return status `304 Not Modified` with no response body when the ETag matches. `curl` is not a default browser cache; the command merely simulates a client sending a conditional header and does not prove the response was actually cached by a browser or CDN.

Try `Expires`:

```bash
curl -i http://localhost:8080/api/cache/expires
```

Expect `Expires: <HTTP-date>` roughly two minutes after the response is created. **Do not hardcode the date/time** since it depends on the server clock. A `Date` header added by the container or proxy may also appear depending on the runtime.

## 12. MockMvc Contract Tests

**`src/test/java/demo/httpcache/CacheDemoControllerTest.java`**

```java
package demo.httpcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResponseHasBrowserAndSharedTtls() throws Exception {
        mvc.perform(get("/api/cache/public"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL,
                    "max-age=120, public, s-maxage=600"))
           .andExpect(jsonPath("$.siteName").value("Java Learning"));
    }

    @Test
    void privateResponseCannotBeStoredBySharedCache()
            throws Exception {
        mvc.perform(get("/api/cache/private-demo"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "max-age=60, private"));
    }

    @Test
    void secretResponseRequestsNoStorage() throws Exception {
        mvc.perform(get("/api/cache/secret-demo"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"));
    }

    @Test
    void unchangedETagGets304WithoutBody() throws Exception {
        mvc.perform(get("/api/cache/revalidate")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"config-v1\""))
           .andExpect(status().isNotModified())
           .andExpect(content().string(""));
    }

    @Test
    void withoutConditionRevalidationEndpointReturnsBody()
            throws Exception {
        mvc.perform(get("/api/cache/revalidate"))
           .andExpect(status().isOk())
           .andExpect(header().string(HttpHeaders.ETAG,
                    "\"config-v1\""))
           .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                    "no-cache"))
           .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void expiresIsValidHttpDate() throws Exception {
        var result = mvc.perform(get("/api/cache/expires"))
                .andExpect(status().isOk())
                .andExpect(header().exists(HttpHeaders.EXPIRES))
                .andReturn();
        String expires = result.getResponse()
                .getHeader(HttpHeaders.EXPIRES);
        assertTrue(expires != null && expires.contains("GMT"));
    }
}
```

The test suite contains **6 test methods**. Run:

```bash
mvn test
```

If run and all tests pass, Maven exits with code `0` and displays a summary like `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`. The code here is designed for Spring MVC 6.1 / Java 17 APIs; this lesson does not claim to have actually executed Maven while authoring the Sheet.

**Limitations of the tests:**

- MockMvc verifies headers and MVC conditional responses; it **does not prove** that a CDN stored and reused responses across multiple users.
- Testing shared caches requires a staging environment with a real proxy/CDN, checking hit/miss/`Age`/`Vary` and requests carrying cookies/`Authorization`.
- Do not rely solely on `response.getHeader("Expires")` containing `GMT` in production: parse the HTTP-date per standard and assert expected policy/freshness in thorough tests.
- When adding Spring Security, tests must properly simulate principals/authn; these demo endpoints have no real security.

## 13. Static Resources: Long-Lived Caching Only When URLs Change with Content

Spring Boot can serve files from `classpath:/static/`. For CSS/JS/images, long-lived caching reduces origin traffic, but easily leaves clients holding **stale versions** after a deploy if URLs do not change.

### Good Design: Fingerprinted URLs

```text
/assets/site.abc123.css   -> bytes of version A
/assets/site.def456.css   -> bytes of version B
```

When an immutable URL never changes its bytes, you can set:

```http
Cache-Control: public, max-age=31536000, immutable
```

During deployment, HTML must reference the new URL while the old URL must continue serving its original bytes as needed. Never use `immutable` for `/index.html` or `/config.json` that can change at the same URL.

### Illustrative Spring MVC Resource Handler

**`AssetsCacheConfig.java`** (**optional** configuration, not needed for the runnable API in section 11):

```java
package demo.httpcache;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetsCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(CacheControl
                        .maxAge(Duration.ofDays(365))
                        .cachePublic()
                        .immutable());
    }
}
```

If you add this class, place files under `src/main/resources/static/assets/`. This policy is **only safe if every file served under /assets/** has an immutable/fingerprinted URL**; if you put `/assets/logo.png` there and overwrite the logo daily, browsers may keep the old logo for a very long time.

### Spring Boot Resource Configuration

These properties exist in Boot 3.3:

```properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
```

**This is an example of globally configuring default static resource handlers, not a required part of the runnable project.** Global configuration can also affect unversioned static HTML. When you have both `index.html` and fingerprinted assets, it is usually better to choose a **dedicated resource handler** like above or path-specific config rather than applying a 1-year `max-age` to everything.

### Static Resource Handling Is Not @Cacheable

- `Cache-Control` and `ETag`/`Last-Modified` help browsers/proxies cache HTTP responses.
- `spring.web.resources.chain.cache` optimizes resource chain lookup **on the server side**, not browser cache lifetime.
- `@Cacheable` optimizes Spring bean return values; by default it has nothing to do with URL hashes, `Vary`, CDNs, or HTTP status codes.

## 14. How to Verify Browser and CDN Caching

### 14.1. Using DevTools

In browser DevTools → Network:

1. Open the page and record the request URL, status, `Cache-Control`, `Expires`, `ETag`, and `Last-Modified`.
2. Perform a normal reload: responses may use memory/disk cache or revalidate per policy.
3. Try disabling cache in DevTools when comparing (behavior depends on whether DevTools is open).
4. With `no-cache`, watch for conditional requests carrying `If-None-Match` and `304` responses when an ETag/cached representation exists.
5. With hashed static assets, you should see resources served from memory/disk cache without contacting the origin.
6. Verify responses carry the right `Vary` header when changing language or `Accept-Encoding`.

**Do not use the browser Back/Forward Cache (bfcache)** as proof that HTTP caching is working. `bfcache` can snapshot an entire page/DOM for instant navigation, which is a different mechanism from HTTP response caching with its own rules.

### 14.2. Checking a Real CDN

With a staging CDN/proxy:

- Request a public URL the first time and observe a miss or small `Age`; subsequent requests may hit. Specific headers like `X-Cache`/`CF-Cache-Status` are **provider-specific**, not universal HTTP standards.
- Compare unauthenticated requests from two browsers to a public asset sharing the same cache key.
- For private URLs, test two different principals/cookies and ensure user A's response **cannot be reused for user B** via the shared cache.
- Send requests with `Authorization` to public vs. private endpoints and verify behavior against CDN config and `Cache-Control`.
- Verify query parameters, `Vary: Accept-Encoding`, `Vary: Accept-Language`, cookies, and redirects.
- When purging the CDN or deploying a new version, test URL/ETag consistency and freshness across edge locations.

Without a CDN/proxy in front of the server, inspecting headers with `curl` alone does not prove shared caching occurs. `Cache-Control` is a policy caches obey, not a command saying "save to CDN immediately."

## 15. Common Pitfalls and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `no-cache` set, yet browser still has a response copy | Confusing `no-cache` with `no-store` | `no-cache` allows storage, requiring revalidation before reuse |
| `private` set, yet data remains on browser disk | `private` only forbids shared caches | Use `no-store` when storage must be disallowed |
| CDN serves wrong user's data across users | Accidental `public`/`s-maxage` on personal response or wrong cache key | Disallow shared caching, audit `Authorization`/Cookie/`Vary`, and purge properly |
| Added `Set-Cookie`, yet CDN still gets cache hits | Cookies do not automatically forbid caching per RFC | Set explicit `Cache-Control` and CDN bypass rules |
| `Expires` has passed, yet body is still reused | Stale serving, validators, heuristics, or overriding policy | Check `Cache-Control` precedence, `Age`, and revalidation |
| `max-age` is 120s, yet browser only has 40s left | CDN already held it for 80s (`Age`/`Date`) | Account for current age instead of resetting TTL at every layer |
| CSS updated, yet clients see the old version | Long TTL on the same URL, incorrect `immutable` | Use URL fingerprinting/versioning and purge if needed |
| No 304 despite having an ETag | Client didn't send `If-None-Match`, or ETag changes per request | Inspect request headers and ETag lifecycle |
| 304 returned, yet actual content changed | ETag did not advance with representation | Use a stable version/hash reflecting the bytes |
| Response has differing `Expires` and `max-age` | Misunderstanding precedence | `max-age` overrides `Expires`; `s-maxage` targets shared caches |
| Wrong language served through CDN | Missing `Vary: Accept-Language` or cache key mismatch | Set `Vary` when representation depends on a request header |
| Authenticated JSON API still cached publicly | Looking only at `200`/`GET` without considering identity | Separate public vs. personalized contracts; use `private`/`no-store` |
| Using `@Cacheable`, yet DevTools still downloads the body | Method cache differs from HTTP cache | Add appropriate headers/ETag and measure both layers separately |
| CDN doesn't cache despite `public, max-age` | CDN policy, bypass, `Set-Cookie` handling, or method/status | Check CDN config instead of assuming Spring triggers CDN storage |
| Browser doesn't store despite large `max-age` | Capacity eviction, private mode, browser policy | Cache headers do not guarantee retention |
| 304 has different `Cache-Control` than 200 | Validation response updates metadata | Verify response policies in both 200 and 304 responses |
| Using `immutable` for dynamic data | Same URL changes bytes, yet cache never revalidates | Remove `immutable` or change URLs when content changes |

Systematic debugging steps:

1. Determine whether the response is **public or user-specific** before discussing TTLs.
2. Inspect response **`Cache-Control`, `Expires`, `Date`, `Age`, `ETag`, `Last-Modified`, and `Vary`**.
3. Inspect request method, URL/query, **`Authorization`, `Cookie`, `Accept-Language`, and `Accept-Encoding`**.
4. Identify which cache is hitting: browser, service worker, reverse proxy, CDN, or server method cache.
5. If seeing `304`, confirm the validator is accurate and the cached body belongs to the same representation/user.
6. Test two real users through the shared cache to check for leakage, not just headers.
7. If inconsistencies appear, separate origin responses from CDN-transformed responses.
8. Review post-deploy invalidation/versioning, not just single-request lifetimes.

## 16. Security and Data Policies

### 16.1. no-store Does Not Make Data Completely Safe

`no-store` does not recall copies that already left the server, nor does it protect against screenshots, malicious browser extensions, non-compliant proxies, or logs/observability. Truly sensitive data still requires:

- Proper HTTPS and HSTS.
- Sound authentication, authorization, and tenant isolation.
- Session expiration, cookie flags, and logout.
- Never logging or putting secrets in URLs/queries, logs, tracing, or unnecessary responses.
- CDN/reverse proxy configs forbidding caching of private endpoints and responses carrying tokens.
- Data retention/erasure policies and auditing.

### 16.2. Stale Content Can Cause Business Bugs

A stale cached `GET /cart` can show users outdated quantities or coupons; meanwhile, `POST /checkout` must **always validate prices, inventory, and permissions** against authoritative data. Never trust a price displayed from a CDN to calculate charges. For rapidly changing content, `no-cache` or short TTLs make sense; for public read-only content, higher TTLs are beneficial.

### 16.3. Vary and Cache Keys Are Part of Security Review

If two users receive different representations at the same URL, merely setting `max-age` and hoping caches "tell users apart automatically" is wrong. You must forbid shared caching or carefully architect cache keys and authorization; `private` or `no-store` is the proper starting point. Also review error responses, redirects, `304`s, preflights, and gateway-generated responses.

## 17. Self-Check Exercises

1. Does `Cache-Control: no-cache` allow a cache to store a response? When may it be reused?
2. How do `no-store` and `private` differ?
3. With `public, max-age=60, s-maxage=300`, what TTL do browsers and CDNs each use?
4. How does `Expires` interact with `max-age` and `s-maxage`?
5. Why does `Authorization` not guarantee that shared caches will never store data?
6. Why is `Set-Cookie` not a caching shield for personal information?
7. What is the benefit of `ETag` and `304 Not Modified` when a response uses `no-cache`?
8. How does `Age: 40` affect a `max-age=120` response?
9. When should `immutable` be used for CSS/JS, and how must it be paired with URL versioning?
10. What problem does `Vary: Accept-Language` solve? Can it replace authorization?
11. Are `@Cacheable` and HTTP `Cache-Control` the same cache layer?
12. Why does testing response headers with MockMvc not prove a real CDN won't leak data?

**Suggested answers:** (1) It may store, but must validate before reuse. (2) `no-store` forbids all caches from storing; `private` forbids shared caches. (3) Browser 60s, shared cache 300s if other conditions hold. (4) The corresponding `Cache-Control` TTL overrides `Expires`. (5) `public`/`s-maxage`/`must-revalidate` can permit it under the RFC. (6) Cookies do not automatically forbid shared caching per spec. (7) Avoids retransferring the body when the representation hasn't changed. (8) Roughly 80s remaining in the simple model. (9) When the URL includes a fingerprint and bytes never change. (10) Distinguishes representations by language; it is not auth. (11) No; one is method-level caching, the other is HTTP response caching. (12) Real shared caches have their own policies and cache keys unlike MockMvc.

## 18. References

- [RFC 9111 — HTTP Caching, cache storage/freshness/revalidation](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9110 — HTTP Semantics, conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Framework 6.1 — HTTP Caching (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-caching.html)
- [Spring Framework 6.1 — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework 6.1 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Boot 3.3 — Common Application Properties, static resources](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- [MDN — Cache-Control header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [RFC 8246 — immutable response directive](https://www.rfc-editor.org/rfc/rfc8246.html)

**Conclusion:** `Cache-Control` governs storage limits, freshness lifetimes, and revalidation; `Expires` is an absolute expiration date with lower precedence than `max-age`/`s-maxage`. Browser caches serve a single client; shared caches/CDNs serve many clients and therefore demand strict privacy and cache-key design. Spring MVC uses `CacheControl`, `ResponseEntity`, `ETag`, and resource handling to implement HTTP policies, but **does not automatically make a CDN safe or replace permission checks**. Before enabling caching, always ask: *Who is allowed to read this representation? Which caches may keep it? For how long, and how is it updated?*.
