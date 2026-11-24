# `CacheControl` and HTTP caching strategies in Spring WebFlux

## 1. What problem does HTTP caching solve?

An API often returns the same resource many times: images, JavaScript files, public configuration, product catalogs, or article data. If clients have to download the full content on every request, the system wastes bandwidth, increases latency, and puts repeated load on the server.

**HTTP caching** lets browsers, proxies, or CDNs store a response and reuse it according to the policy advertised by the server. When the stored copy becomes stale, the cache can ask the server whether the content has changed. If it has not changed, the server returns `304 Not Modified` without resending the body.

In Spring Framework, `org.springframework.http.CacheControl` is a builder for creating the `Cache-Control` response header. Spring WebFlux can attach this policy to `ResponseEntity`, `ServerResponse`, or static resource handlers.

Three concepts need to be distinguished:

1. **HTTP cache policy:** instructs browsers, proxies, and CDNs whether they may store the response, for how long, and when they must revalidate.
2. **HTTP validator:** `ETag` or `Last-Modified` helps caches verify whether a stored copy still represents the current resource.
3. **Application cache:** caching data inside the application, such as Caffeine, Redis, or Spring Cache. This is a separate mechanism and is not created merely by `CacheControl`.

`CacheControl` does not store objects in RAM, Redis, or a database. It builds HTTP directives for client-side or intermediary caches to follow.

## 2. Lifecycle of a cached response

```text
Client sends GET /products/42
          |
          v
Spring WebFlux builds response
          |
          | Cache-Control: private, max-age=60
          | ETag: "product-v3"
          v
Browser receives 200 OK and body
          |
          v
Browser stores response by cache key
          |
          | Within freshness lifetime: can use stored copy
          |
          v
When revalidation is needed, send If-None-Match
          |
          v
Server compares validator
          |
          +---- Unchanged ---> 304 Not Modified, no body
          |
          +---- Changed -----> 200 OK, new ETag and new body
```

- **Fresh:** the response is within its freshness lifetime; the cache can reuse it without asking the origin if no other directive requires otherwise.
- **Stale:** the freshness lifetime has expired; the cache usually must revalidate before reusing.
- **Revalidation:** the cache sends a conditional request with `If-None-Match` or `If-Modified-Since`.
- **304 Not Modified:** the server confirms the stored representation is still suitable; the cache can continue using the old body.
- **200 OK:** a new representation is sent when the resource changes or there is no matching validator.

HTTP caching is most useful with `GET` and `HEAD`. Caching other methods has specific conditions; do not assume every request can be cached.

## 3. What header is `Cache-Control`?

`Cache-Control` is a response header containing one or more directives, separated by commas:

```http
Cache-Control: private, max-age=60, must-revalidate
```

Example:

```http
Cache-Control: max-age=3600
```

allows caches to treat the response as fresh for 3,600 seconds under the HTTP caching model.

Spring provides the builder:

```java
CacheControl oneHour =
        CacheControl.maxAge(Duration.ofHours(1));

CacheControl noStore =
        CacheControl.noStore();

CacheControl privateCache =
        CacheControl.maxAge(Duration.ofMinutes(5))
                .cachePrivate();

CacheControl publicAsset =
        CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic()
                .immutable();
```

`CacheControl` is a builder for response directives. It is not a general parser for the request `Cache-Control` header; if you need to read request directives, read the request headers and handle them per application policy.

## 4. Important directives

### 4.1. `max-age`

```http
Cache-Control: max-age=300
```

The response has a freshness lifetime of 300 seconds. During that time, caches can use the stored copy without sending a request to the server, unless revalidation or another policy requires it.

Spring:

```java
CacheControl.maxAge(Duration.ofMinutes(5));
```

Set `max-age` only when the application accepts that clients may see stale data during that interval.

### 4.2. `no-cache` and `no-store`

```http
Cache-Control: no-cache
```

`no-cache` **does not mean forbidding storage**. A cache may store the response, but must revalidate with the origin before using the stored copy.

```java
CacheControl.noCache();
```

Conversely:

```http
Cache-Control: no-store
```

instructs caches not to store the response. Use this when content is sensitive or the response must not be stored in an HTTP cache.

```java
CacheControl.noStore();
```

`no-store` does not replace TLS, authentication, authorization, log protection, or sensitive-data management at the application layer.

### 4.3. `private` and `public`

```http
Cache-Control: private, max-age=60
```

`private` indicates the response is intended for a single user; shared caches such as proxies/CDNs must not store the response under this directive. The user's private browser cache can still store it.

```http
Cache-Control: public, max-age=3600
```

`public` allows public caches to store the response in cases where, without this directive, storing in shared caches might be restricted.

Spring:

```java
CacheControl.maxAge(Duration.ofMinutes(1)).cachePrivate();

CacheControl.maxAge(Duration.ofHours(1)).cachePublic();
```

Do not attach `public` to endpoints personalized by user, tenant, role, or cookie without proving that a shared cache cannot return the wrong data.

### 4.4. `s-maxage`

```http
Cache-Control: public, max-age=60, s-maxage=300
```

`s-maxage` applies to shared caches and overrides the `max-age` freshness lifetime in shared caches. Browser/private caches still use `max-age`.

```java
CacheControl.maxAge(Duration.ofMinutes(1))
        .cachePublic()
        .sMaxAge(Duration.ofMinutes(5));
```

Use this when you want CDNs/proxies to have a different freshness than browsers, but only when the data is suitable for a shared cache.

### 4.5. `must-revalidate` and `proxy-revalidate`

- `must-revalidate`: once a response is stale, the cache must revalidate before using it.
- `proxy-revalidate`: applies the same rule to shared caches, not private caches.

```java
CacheControl.maxAge(Duration.ofMinutes(2))
        .mustRevalidate();

CacheControl.maxAge(Duration.ofMinutes(2))
        .proxyRevalidate();
```

They do not replace validators; for effective revalidation, provide `ETag` or `Last-Modified`.

### 4.6. `immutable`

```http
Cache-Control: public, max-age=31536000, immutable
```

`immutable` signals that the representation will not change during its freshness lifetime. It suits static assets whose names contain a hash/version, such as `app.8d91a2.js`.

```java
CacheControl.maxAge(Duration.ofDays(365))
        .cachePublic()
        .immutable();
```

Use only with versioned URLs or resources that are genuinely immutable during the cache duration. If you overwrite the content while keeping the same URL, clients may keep using the old version for a very long time.

### 4.7. `no-transform`

`no-transform` asks intermediaries not to alter the representation in ways that transform its content.

```java
CacheControl.maxAge(Duration.ofHours(1))
        .cachePublic()
        .noTransform();
```

### 4.8. `stale-while-revalidate` and `stale-if-error`

```java
CacheControl policy = CacheControl.maxAge(Duration.ofMinutes(1))
        .staleWhileRevalidate(Duration.ofSeconds(30))
        .staleIfError(Duration.ofMinutes(10));
```

- `stale-while-revalidate=30`: a cache may serve a stale copy for up to 30 seconds while trying to revalidate in the background.
- `stale-if-error=600`: when the origin errors, a cache may use a stale copy for the allowed time.

The behavior depends on whether the cache/CDN supports these extension directives. Do not assume every browser or proxy implements them the same way. This is not Reactor retry or Spring Cache.

## 5. Choosing a policy by data type

| Response type | Commonly considered policy | Reason |
|---|---|---|
| JavaScript/CSS/images with a hash in the URL | `public`, long `max-age`, `immutable` | New URL when content changes |
| Public catalog that changes periodically | `public`, short `max-age`, ETag | Cacheable yet updates relatively quickly |
| API depending on a logged-in user | `private`, short freshness or `no-cache` | Avoid shared caches storing personal data |
| Response containing secrets | `no-store` | Do not want HTTP caches to store the response |
| Data that must be checked on every use while keeping the body | `no-cache` with ETag | Cache revalidates and can receive 304 |
| Public API via CDN | `public`, `s-maxage`, validator | Separate freshness for shared caches |
| Real-time stream/SSE | Specific policy, usually no caching | Content changes continuously |

This is a starting point, not a mandatory formula. Decide based on data sensitivity, change frequency, stale tolerance, cache keys, and CDN deployment.

## 6. `CacheControl` API in Spring Framework

Class `org.springframework.http.CacheControl` is a fluent builder. Commonly used methods in Spring Framework 6.1:

| Method | Directive |
|---|---|
| `maxAge(Duration)` | `max-age` |
| `noCache()` | `no-cache` |
| `noStore()` | `no-store` |
| `cachePrivate()` | `private` |
| `cachePublic()` | `public` |
| `mustRevalidate()` | `must-revalidate` |
| `proxyRevalidate()` | `proxy-revalidate` |
| `sMaxAge(Duration)` | `s-maxage` |
| `staleWhileRevalidate(Duration)` | `stale-while-revalidate` |
| `staleIfError(Duration)` | `stale-if-error` |
| `noTransform()` | `no-transform` |
| `immutable()` | `immutable` |
| `getHeaderValue()` | Gets the generated header string |

Example:

```java
CacheControl policy = CacheControl.maxAge(Duration.ofMinutes(10))
        .cachePublic()
        .mustRevalidate()
        .noTransform();

String headerValue = policy.getHeaderValue();
System.out.println(headerValue);
```

The header value is generated by the builder in the corresponding directive order:

```text
max-age=600, must-revalidate, no-transform, public
```

Do not rely on directive order to express priority; meaning is defined by HTTP semantics. If you need a directive without a corresponding method, you can set the header manually after checking compatibility and avoiding conflicting directives.

## 7. Attaching `CacheControl` to a WebFlux response

### 7.1. Annotated controller returning `ResponseEntity`

```java
@GetMapping("/catalog/{id}")
Mono<ResponseEntity<ProductView>> getProduct(@PathVariable long id) {
    return productService.findById(id)
            .map(product -> ResponseEntity.ok()
                    .cacheControl(
                            CacheControl.maxAge(Duration.ofMinutes(5))
                                    .cachePrivate()
                    )
                    .eTag(product.etag())
                    .lastModified(product.updatedAt())
                    .body(toView(product))
            );
}
```

`ResponseEntity` builder supports `cacheControl`, `eTag`, and `lastModified`. WebFlux supports methods returning `Mono<ResponseEntity<T>>`; the service returns a Publisher and the controller does not need to call `.block()`.

When a matching conditional request arrives, Spring WebFlux can compare `ETag`/`Last-Modified` against the request headers and return `304 Not Modified` with an empty body if the resource has not changed. When content changes, the normal response returns `200` along with the new validator.

### 7.2. Functional endpoint with `ServerResponse`

```java
Mono<ServerResponse> response =
        ServerResponse.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic()
                )
                .eTag("\"catalog-v4\"")
                .varyBy("Accept-Language")
                .bodyValue(catalog);
```

`cacheControl(...)` sets `Cache-Control`; `eTag(...)` sets the validator; `varyBy(...)` announces headers involved in selecting the representation.

### 7.3. Using `ServerHttpResponse` directly

```java
CacheControl policy = CacheControl.noStore();

response.getHeaders().set(
        HttpHeaders.CACHE_CONTROL,
        policy.getHeaderValue()
);
```

This snippet only prepares headers. If the response has already committed, changing headers may no longer take effect. Set the cache policy before starting to write the body.

## 8. `ETag`: validator by representation version

`ETag` is an entity tag identifying a version of a representation:

```http
ETag: "product-42-v7"
```

The client sends it back in the request:

```http
If-None-Match: "product-42-v7"
```

- If it matches in a conditional GET/HEAD, the server can return `304 Not Modified` and skip resending the body.
- If it differs, the server returns `200 OK`, the new body, and the new ETag.

### 8.1. Strong and weak ETag

Strong ETag:

```http
ETag: "v7"
```

Weak ETag:

```http
ETag: W/"v7"
```

- A strong validator indicates byte-level equivalence of the representation per HTTP semantics.
- A weak validator indicates semantic equivalence of content without promising byte-for-byte identity.

With `If-None-Match` for GET/HEAD, HTTP uses weak comparison. With preconditions such as `If-Match`, strong comparison matters.

An ETag can be generated from a version number, a hash of the serialized representation, a revision ID, or a stable checksum. Do not generate a random ETag on every request; if the ETag always differs, the client cannot revalidate successfully.

### 8.2. The ETag must represent the exact representation

If the same URL has multiple representations depending on `Accept`, `Accept-Language`, `Accept-Encoding`, or user permissions, the ETag and cache key must reflect those differences. Sharing one ETag across two different representations can cause caches to reuse the wrong body.

`Vary` helps caches distinguish cache keys; `ETag` helps validate the version of the chosen representation.

## 9. `Last-Modified`: timestamp-based validator

`Last-Modified` indicates when the resource was last modified:

```http
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
```

The client can send:

```http
If-Modified-Since: Sat, 15 Mar 2025 10:00:00 GMT
```

If the resource has not changed since that point in time, the server returns `304 Not Modified`.

Spring:

```java
ResponseEntity.ok()
        .lastModified(updatedAt)
        .body(resource);
```

HTTP dates have one-second resolution; if a resource changes several times within the same second, the timestamp may not distinguish the versions. ETag is usually more accurate, and both can be combined.

## 10. Conditional requests with `ServerWebExchange`

Spring WebFlux provides:

```java
boolean unchanged = exchange.checkNotModified(etag);

boolean unchangedByDate =
        exchange.checkNotModified(lastModified);

boolean unchangedByBoth =
        exchange.checkNotModified(etag, lastModified);
```

`checkNotModified(...)` compares the validator computed by the application against the conditional request headers and prepares the response status/headers automatically when appropriate. If it returns `true`, the request does not need to continue processing content. If it returns `false`, the application continues building the representation.

| Request precondition | Outcome when condition is met |
|---|---|
| GET/HEAD with matching `If-None-Match` | `304 Not Modified` |
| GET/HEAD with matching `If-Modified-Since` | `304 Not Modified` |
| POST/PUT/DELETE with unmet precondition | `412 Precondition Failed` |
| Validator does not match or no precondition | Continue processing |

Skeleton handler example in an annotated controller:

```java
@GetMapping("/documents/{id}/manual")
Mono<DocumentView> getDocument(
        @PathVariable long id,
        ServerWebExchange exchange) {

    return documentService.findById(id)
            .flatMap(document -> {
                String etag = document.etag();
                Instant modified = document.updatedAt();

                if (exchange.checkNotModified(etag, modified)) {
                    return Mono.empty();
                }

                return Mono.just(toView(document));
            });
}
```

This is an illustrative pattern for a controller returning a reactive body. `checkNotModified` prepares the status and headers; when it returns `true`, do not create a new body. Test how the response finishes with the specific return type and Spring version you are using. With `ResponseEntity`, declaring ETag and Last-Modified on the builder is usually simpler.

Computing ETag/Last-Modified requires reliable metadata. If you have to read an entire large file just to compute a hash before deciding 304, the benefit may diminish. You can store a version/checksum alongside the resource for fast checking.

## 11. `304 Not Modified` is not an error response

A 304 response:

- Carries no response body.
- Tells the cache the stored representation can still be used.
- Can update cache metadata according to headers sent by the server.
- Does not mean the resource is empty or the request failed.

Example:

```http
HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: private, max-age=300
```

The client takes the body from its stored cache copy. The server saves bandwidth because it does not have to resend the representation.

Do not return `200 OK` with an empty body to simulate 304. The two responses have different semantics.

## 12. `Vary`: cache key depending on request headers

Suppose an API returns content by language:

```text
GET /help
Accept-Language: vi
```

and:

```text
GET /help
Accept-Language: en
```

Same URL, different bodies. If the cache distinguishes only by URL, a Vietnamese response could be mistakenly served to an English client. The server should send:

```http
Vary: Accept-Language
```

In a WebFlux functional response:

```java
return ServerResponse.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
        .varyBy("Accept-Language")
        .bodyValue(translatedContent);
```

Headers commonly included in `Vary`:

- `Accept-Language` when content depends on language.
- `Accept-Encoding` when the representation differs by compression.
- `Accept` when returning JSON, XML, or different representations.

List only the request headers that genuinely alter the representation. `Vary` and authorization must be designed together; do not use cache keys in place of permission checks.

## 13. Safe caching with authentication and personal data

Shared caches can serve the same response copy to many users. Therefore, the cache policy must account for authentication and authorization.

- For user-dependent responses, consider `private` or `no-store`.
- `private` prevents shared caches from storing the response, though private browser caches can still store it.
- If content must not be stored in any HTTP cache, use `no-store`.
- Responses with an `Authorization` header are subject to specific HTTP caching rules. Do not assume a CDN will or will not cache based solely on the URL.
- If a response depends on cookies/sessions, avoid sharing the body across sessions. For personalized content, `private` or `no-store` is usually clearer.

Do not use `public` just to increase the cache hit ratio. A cache policy does not replace authentication, authorization, tenant isolation, or server-side access control.

## 14. Caching static resources in WebFlux

Static resources such as CSS, JavaScript, and images usually have a different caching strategy from dynamic APIs:

```java
@Configuration
class StaticResourceConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable()
                );
    }
}
```

This is an illustrative configuration for a WebFlux application. This usage fits when asset URLs contain a version/hash and content is not overwritten under the same URL.

Common frontend strategies:

- Versioned/hashed files: cache long and `immutable`.
- HTML entry point: cache short or revalidate to pick up new manifest/asset versions.
- Dynamic API: policy by access permissions and stale tolerance.

If static resources are served through a CDN, synchronize cache headers at the origin and CDN configuration; check whether the CDN overrides the policy.

## 15. How HTTP cache differs from Spring Cache, Caffeine, and Redis

| Mechanism | Where is it cached? | Stored item | Controlled by |
|---|---|---|---|
| HTTP browser cache | Client device | HTTP response | `Cache-Control`, ETag, Last-Modified, Vary |
| Reverse proxy/CDN | Intermediary infrastructure | HTTP response | HTTP headers and CDN configuration |
| Spring Cache | Inside the application or provider | Method result | `@Cacheable`, `@CacheEvict`, `CacheManager` |
| Caffeine | JVM memory | Object/value | TTL, size, eviction |
| Redis | External cache | Key/value | TTL, key policy, eviction |

`@Cacheable("products")` can avoid repeated database queries in a service. `CacheControl.maxAge(...)` instructs browsers/proxies to store the response. The two mechanisms can be combined, but need a consistent invalidation strategy.

HTTP caching does not automatically create an application cache. Nor does a good application cache automatically make browsers receive 304.

## 16. Cache invalidation when data changes

A caching strategy needs to answer: when a resource is updated, how is the stale cache detected and removed?

1. **Short TTL:** the cache expires its freshness automatically after a fixed period. Easy to implement, but accepts staleness during the TTL.
2. **Validators:** ETag/Last-Modified let caches ask the origin when stale.
3. **Versioned URLs:** when content changes, the URL changes; suits static assets.
4. **CDN purge:** the application/deployment sends a cache-deletion command by URL or tag per CDN features.
5. **Versioned cache keys:** a new version creates a new key; old copies expire naturally.

HTTP caching has invalidation rules after certain successful unsafe request methods for the target URI, but you should not rely on that to clear every cached copy across every URL or CDN. If the same data appears at multiple endpoints, a clear purge/versioning strategy is needed.

Example of a product changing its name:

- Old ETag: `"product-42-v7"`.
- New ETag: `"product-42-v8"`.
- Client sends `If-None-Match: "product-42-v7"`.
- Server sees it does not match and returns `200` with the new ETag and body.

## 17. Complete Java 17+ example with Spring Boot WebFlux

The example creates the `GET /assets/{id}` endpoint. The demo resource has a fixed version so it is easy to observe:

- The first response returns `200 OK`, `Cache-Control`, `ETag`, and `Last-Modified`.
- The next request sends `If-None-Match` with the old ETag.
- Spring WebFlux recognizes that the resource has not changed and returns `304 Not Modified` with no body.

### Directory structure

```text
http-cache-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/assets")
class AssetController {

    private static final Asset ASSET = new Asset(
            42L,
            "Spring WebFlux Guide",
            "\"asset-v3\"",
            Instant.parse("2025-03-15T10:00:00Z")
    );

    @GetMapping("/{id}")
    Mono<ResponseEntity<AssetView>> get(@PathVariable long id) {
        if (id != ASSET.id()) {
            return Mono.just(notFound());
        }

        AssetView view = new AssetView(
                ASSET.id(),
                ASSET.name(),
                "v3"
        );

        return Mono.just(
                ResponseEntity.ok()
                        .cacheControl(
                                CacheControl.maxAge(Duration.ofMinutes(1))
                                        .cachePrivate()
                        )
                        .eTag(ASSET.etag())
                        .lastModified(ASSET.updatedAt())
                        .body(view)
        );
    }

    private ResponseEntity<AssetView> notFound() {
        return ResponseEntity.status(404).build();
    }

    record Asset(
            long id,
            String name,
            String etag,
            Instant updatedAt
    ) {}

    record AssetView(long id, String name, String version) {}
}
```

From the project directory, JDK 17+ and Maven are required:

```bash
mvn spring-boot:run
```

### First request

```bash
curl -i http://localhost:8080/assets/42
```

Important parts of the response:

```http
HTTP/1.1 200 OK
Cache-Control: max-age=60, private
ETag: "asset-v3"
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
Content-Type: application/json

{"id":42,"name":"Spring WebFlux Guide","version":"v3"}
```

Secondary headers such as `Date` or `Content-Length` may vary by runtime/server.

### Request with validator

```bash
curl -i \
  -H 'If-None-Match: "asset-v3"' \
  http://localhost:8080/assets/42
```

Expected response:

```http
HTTP/1.1 304 Not Modified
Cache-Control: max-age=60, private
ETag: "asset-v3"
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
```

The 304 response has no JSON body. The client uses the body stored from the previous 200 response.

**Reading the program:**

1. `Asset` holds the ID, content, ETag, and update timestamp.
2. `ResponseEntity.ok()` chooses status 200 for the current representation.
3. `.cacheControl(...)` sets a private policy with 60-second freshness.
4. `.eTag(...)` and `.lastModified(...)` publish the two validators.
5. When the request carries a matching `If-None-Match`, WebFlux can return 304 and skip the body.
6. The method returns `Mono<ResponseEntity<AssetView>>`; do not call `.block()` or `.subscribe()` in the controller.

The example fixes the version so the response is predictable. In a real application, ETag and `updatedAt` must come from a reliable version/timestamp of the data.

## 18. Testing conditional caching with `WebTestClient`

You can test status and validators without opening a TCP port:

```java
WebTestClient client = WebTestClient
        .bindToController(new AssetController())
        .build();

client.get()
        .uri("/assets/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                "Cache-Control", "max-age=60, private"
        )
        .expectHeader().valueEquals("ETag", "\"asset-v3\"")
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

client.get()
        .uri("/assets/42")
        .header("If-None-Match", "\"asset-v3\"")
        .exchange()
        .expectStatus().isNotModified()
        .expectBody().isEmpty();
```

This test snippet requires `spring-test` (usually available via `spring-boot-starter-test`) and the `WebTestClient` import. If testing with `bindToController`, make sure the controller has the required dependencies or use an appropriate fixture.

Tests to add:

- A non-matching old ETag receives `200` with the new ETag.
- A matching `If-Modified-Since` receives `304`.
- A request without a validator still receives the representation.
- A non-existent resource returns `404`.
- A personal response is not configured as `public`.
- `Vary` distinguishes representations by the relevant headers.

## 19. Common mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Using `no-cache` thinking it forbids storing completely | The cache can still store the body and revalidate | Use `no-store` when you do not want caches to store |
| Using `public` for personalized responses | Shared caches risk serving the wrong data | Use `private` or `no-store` |
| Setting `max-age` too long for unversioned URLs | Clients keep stale content after deployment | Use versioned URLs or a short TTL |
| Setting only `Cache-Control` without a validator | When stale, the server usually has to resend the full body | Add ETag/Last-Modified when appropriate |
| ETag changes on every request | No opportunity to return 304 effectively | Use a stable version/hash |
| ETag does not reflect the representation | The cache may reuse the wrong body | Compute the validator for the exact representation |
| Omitting `Vary` when the body depends on `Accept-Language` | The cache may serve the wrong language | Send `Vary: Accept-Language` |
| Treating `CacheControl` like Redis/Caffeine | Data is not cached in the JVM as expected | Use Spring Cache or a cache provider |
| Thinking `304` must have an empty JSON body | Wrong HTTP semantics | 304 has no representation body; client uses cached copy |
| Using `Last-Modified` for data that changes multiple times in one second | Timestamp may not distinguish versions | Use ETag or combine validators |
| Using `immutable` for a fixed URL that gets overwritten | Clients may keep the old copy for a long time | Use only with versioned URLs |
| Ignoring cache keys and access permissions | Data leakage across users/tenants | Design `private`, `Vary`, and authorization properly |
| Using cache headers in place of authentication | Unauthorized callers can still call the origin | Always check authorization on the server |
| Testing an endpoint with only a single 200 request | Fails to catch conditional request bugs | Test `If-None-Match`, `If-Modified-Since`, and 304 |
| Assuming the CDN always obeys the origin | The CDN may have override rules or its own cache key | Verify CDN configuration and actual responses |

## 20. Cache strategy design checklist

1. Is the response public or dependent on user, tenant, role, or cookie?
2. How long can data stay stale while remaining acceptable?
3. Should caches be allowed to store the body, or is `no-store` needed?
4. Should you use `max-age`, `no-cache`, or `no-store`?
5. Are shared caches allowed to store it? Are `private`, `public`, or `s-maxage` needed?
6. Is there a stable ETag or Last-Modified?
7. Does the representation vary by `Accept`, `Accept-Language`, or `Accept-Encoding`? Is `Vary` needed?
8. Does the URL have a version/hash to use `immutable`?
9. When data changes, will TTL, validators, versioned URLs, or CDN purge update the cache?
10. Do conditional requests return the right 304/412 without sending unnecessary bodies?
11. Does the response contain tokens, sensitive data, or personal information?
12. Are there integration tests verifying headers and cache behavior through an actual proxy/CDN?

## 21. Self-check exercises

**Question 1.** What directive does `CacheControl.maxAge(Duration.ofMinutes(5))` produce?

**Answer:** `max-age=300`. Caches can treat the response as fresh for 300 seconds under HTTP caching rules.

**Question 2.** How do `no-cache` and `no-store` differ?

**Answer:** `no-cache` allows storing but requires revalidation before reuse; `no-store` instructs caches not to store the response.

**Question 3.** Does `private` prevent browsers from storing the response?

**Answer:** No. It prevents shared caches from storing the response; a user's private cache can still store it.

**Question 4.** Why does a response that varies by `Accept-Language` need `Vary: Accept-Language`?

**Answer:** So caches distinguish representations by the request header and do not serve one language's content to a request for another language.

**Question 5.** When `If-None-Match` matches the current ETag on GET, what can the server return?

**Answer:** `304 Not Modified` with no body; the client uses its cached representation.

**Question 6.** Can an ETag be derived from a record's version?

**Answer:** Yes, if the version changes whenever the relevant representation changes and is stable enough to accurately identify versions.

**Question 7.** Is `immutable` suitable for `/app.js` that gets overwritten on every deploy?

**Answer:** No. Use URLs containing a content hash/version so new content gets a new URL.

**Question 8.** Does `CacheControl` automatically store the response in Redis?

**Answer:** No. It builds an HTTP response header; Redis/Spring Cache is separate application caching.

**Question 9.** If an endpoint returns personal data for a logged-in user, should `public` be used?

**Answer:** Not by default. Use private or no-store depending on sensitivity and security policy.

**Question 10.** Does `304 Not Modified` mean the resource does not exist?

**Answer:** No. It means the representation the client already stored is still valid; 304 carries no new body.

## 22. Rules to apply

- Use `CacheControl` to build the `Cache-Control` response header; do not confuse it with application caching.
- Choose `no-store` when the response must not be stored; choose `no-cache` when it can be stored but must revalidate.
- Use `private` for per-user responses; use `public` only when shared caches are allowed to store it.
- Set `max-age` according to stale tolerance; use `s-maxage` when shared caches need separate freshness.
- Combine with `ETag` or `Last-Modified` so conditional requests can return 304.
- Use `Vary` when the representation depends on request headers.
- Use `immutable` only with versioned/hashed URLs.
- Test status, headers, body, and cache behavior via `WebTestClient` and real CDN infrastructure.

**Key takeaway:** `Cache-Control` decides how caches store and reuse responses; ETag/Last-Modified help validate representations; `Vary` helps caches distinguish variants. `CacheControl` in Spring WebFlux is a builder for HTTP response policy, not an application data store.

## 23. Official references

- [Spring Framework — HTTP Caching in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html)
- [Spring Framework 6.1 — `CacheControl` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework 6.1 — `ServerWebExchange` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — `ServerResponse.HeadersBuilder` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.HeadersBuilder.html)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 8246 — Immutable HTTP Responses](https://www.rfc-editor.org/rfc/rfc8246)
