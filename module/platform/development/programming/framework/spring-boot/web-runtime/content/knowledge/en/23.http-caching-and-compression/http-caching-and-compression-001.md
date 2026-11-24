# Distinguishing HTTP Caching from Spring Cache at the Business Layer

> **Context:** Spring Boot web-runtime, under the topic “HTTP Caching and Compression”. This lesson explains two types of caching that are easily confused in Java applications: **HTTP caching** at the browser/proxy/CDN and **Spring Cache** at the service/repository layer. Examples use Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+ with Spring MVC; the final section highlights the differences when implementing with Spring WebFlux. TTL values in the examples are for practice only.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify **where the cache resides**, **what object it stores**, and **when the application layer can be bypassed** in a request.
2. Explain HTTP `Cache-Control` directives: `max-age`, `s-maxage`, `public`, `private`, `no-cache`, `no-store`, `must-revalidate`, and `Vary` according to RFC 9111.
3. Distinguish between a **fresh response** reused immediately and a **conditional GET** using `If-None-Match` / `ETag` or `If-Modified-Since` / `Last-Modified` that can receive `304 Not Modified`.
4. Use Spring Cache with `@EnableCaching`, `@Cacheable`, `@CacheEvict`, `@CachePut`, and a `CacheManager`, understanding cache keys, TTL, invalidation, cache stampede, and proxy limitations.
5. Understand why a business cache hit **is not equivalent to** an HTTP cache hit, and why evicting Spring Cache **does not automatically clear** the browser/CDN cache.
6. Run a Java 17+ Spring MVC application with both cache layers; inspect service load count, ETag, and data changes via `curl`.
7. Design appropriate caching for public content, personal content, frequently changing data, and gzip/br-compressed static resources, while measuring effectiveness and avoiding stale data responses.

## 2. Two Caches at Two Different Locations

Imagine a client accessing `GET /products/1`. There may be **caching outside the app** and **caching inside the app**:

~~~text
Browser
  |  (1) browser HTTP cache: is there a fresh response?
  |
  v
CDN / reverse proxy / shared HTTP cache
  |  (2) CDN cache: is there a valid representation?
  |
  v
Spring Boot HTTP server / Controller
  |  (3) controller handles HTTP request
  v
@Service / @Cacheable
  |  (4) business cache: is Product(id=1) present?
  |
  v
Database / downstream API
~~~

- **HTTP cache** holds one or more *HTTP response representations* along with their metadata (status, response headers, validators, and body depending on the implementation). The client/CDN decides whether it can be reused or must query the origin, based on HTTP semantics and policy.
- **Spring Cache** holds *the result of a method invocation* in a `Cache` managed by a `CacheManager`, typically keyed by cache name + key. This can be a `Product`, DTO, list, or computed result; it does not by default preserve HTTP status, ETag, Content-Type, and body representation.
- A **valid HTTP cache hit** can prevent the request from reaching Spring Boot, so controller/service/database **none of them run** for that request.
- A **Spring Cache hit** only occurs **when the request has already reached the application** and a call passes through Spring's caching proxy. Controller, authorization, serialization, response filters, and network transfer may still execute.

For example: the browser holds a `200 OK` for `/products/1` that remains fresh for 30 seconds. The next GET can reuse the body directly in the browser without calling the server. Once freshness expires, the browser can send a GET with `If-None-Match`. This request reaches the server, the controller reads the Product from Spring Cache to compute the validator; if unchanged, the server returns `304` and the browser reuses the stored body. The two cache layers work together but **have no automatic mechanism to synchronize expiration or invalidation**.

### Quick Comparison Table

| Criterion | HTTP cache | Spring Cache at the business layer |
|---|---|---|
| Where it executes | Browser, CDN, reverse proxy, HTTP client, or other HTTP cache | Inside the application via Spring cache abstraction and provider |
| Unit of storage | HTTP response/representation with protocol metadata | Method invocation result, by cache name and key |
| Key | URI/method, plus dimensions considered by `Vary` and cache implementation | Cache name + key from `KeyGenerator`/SpEL |
| Control | `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, RFC rules | `@Cacheable`, `@CacheEvict`, `@CachePut`, `CacheManager`, provider TTL |
| What work does it avoid? | Can avoid origin requests, body transfer, and all server processing | Can avoid DB/downstream HTTP queries or computation inside the method |
| Expiration | HTTP freshness such as `max-age`, `s-maxage`, revalidation | TTL/TTI/size/eviction via Redis/Caffeine/provider or application logic |
| Cache eviction/update | Per HTTP rules, CDN purge, URL change, revalidation, or other policy | Evict/update key, TTL expiration, or invalidation event |
| Typical risks | Serving stale responses, caching personal data in shared cache, missing `Vary` | Key missing tenant/user, stale data, cache stampede, memory exhaustion |
| Relationship to compression | Representation may differ by `Accept-Encoding` and `Vary` | Domain object results are usually not compressed HTTP bytes yet |

**Key takeaway:** Both mechanisms are called “cache” but optimize different segments of the request journey. They can be enabled independently or combined.

## 3. What Does an HTTP Cache Store, and Who Can Reuse It?

RFC 9111 describes an HTTP cache as a local store of responses and the rules for reusing them. It is necessary to distinguish:

- **Private cache:** dedicated to a single user, such as a browser's cache.
- **Shared cache:** serves multiple users, such as a CDN or proxy cache.
- **Origin server:** the source server generating the response (Spring Boot or a system behind a gateway).

A response should only be considered cacheable when it meets the conditions of the RFC, not merely because the app returned `200`. Request method, status, directives, Authorization, metadata, and cache policy all have an impact. For example, a public GET response with `Cache-Control: public, max-age=60` can typically be stored by an HTTP cache, though this does not promise every browser/proxy must store it: caches have their own rights and implementation conditions.

### When the response is still fresh

~~~http
GET /products/1 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: W/"product-1-v4"

{"id":1,"name":"Notebook","version":4}
~~~

During those 60 seconds per freshness semantics (which may factor in `Age`, storage time, policy, and other factors), an eligible HTTP cache can reuse the representation **without contacting the origin**. The internal Spring Cache layer does not receive a corresponding invocation.

### When the representation is stale and needs revalidation

~~~http
GET /products/1 HTTP/1.1
Host: api.example.test
If-None-Match: W/"product-1-v4"

HTTP/1.1 304 Not Modified
ETag: W/"product-1-v4"
Cache-Control: public, max-age=60
~~~

`304 Not Modified` contains no replacement representation body; the client keeps the old content and updates metadata according to HTTP rules. **304 is not a Spring Cache hit.** 304 is a protocol result returned from the origin or an intermediate cache when the validator matches; Spring Cache may help the server determine the version without querying the DB.

If the resource has changed, the server typically returns `200 OK` with a new body and new ETag, rather than returning 304.

### Vary changes how representations are reused

If the response varies by language:

~~~http
Vary: Accept-Language
~~~

the cache must inspect that request header when selecting a stored representation. If the response differs by gzip or Brotli:

~~~http
Vary: Accept-Encoding
~~~

the cache must distinguish the client's encoding capabilities according to Vary. Omitting `Vary` can cause a cache to send the wrong language or encoding to a client. `Vary` **does not replace** protecting personal data: user-specific responses should generally use `private` or `no-store` depending on sensitivity.

## 4. Reading Cache-Control and Validators Accurately

| Directive/header | Practical meaning | Common misconception |
|---|---|---|
| `max-age=60` | Response is fresh for up to a 60-second freshness lifetime (subject to Age and cache policy rules). | Assuming the origin locks data for 60 seconds or the DB cache has a 60-second TTL. |
| `s-maxage=120` | Freshness specifically for **shared caches**, taking precedence over max-age for shared caches per RFC. | Assuming private browser caches are also forced to use 120 seconds. |
| `public` | Allows shared caches to store the response in RFC-permitted cases; commonly used for public content. | Attaching it to responses containing user data/tokens to “speed up the CDN”. |
| `private` | Shared caches must not store the response in the sense of the parameterless directive; private caches may store it if other conditions are met. | Thinking private means encryption or a data security mechanism. |
| `no-cache` | Caches may store the response but **must revalidate successfully** before reusing it. | Thinking no-cache always equals “do not store” (incorrect). |
| `no-store` | Compliant caches must not store the request/response per directive rules; suitable for very sensitive data. | Thinking it guarantees erasing every old copy across all systems (not guaranteed). |
| `must-revalidate` | Once stale, caches must not reuse it in ineligible cases; must revalidate per RFC. | Thinking the server must always be called even while the response is fresh. |
| `ETag` | Validator for a representation (strong/weak), commonly used with If-None-Match. | Treating ETag as a TTL or always a strong byte checksum. |
| `Last-Modified` | Modification time determined by the origin, usable with If-Modified-Since. | Treating the timestamp as exact for multiple changes within the same second. |
| `Vary` | Indicates request headers that a cache must consider when selecting a representation. | Using Vary as an automatic, safe way to isolate tenants/users. |
| `Age` | Age information of the response in a cache, affecting freshness calculation. | Subtracting client clock time from max-age while ignoring Age. |

Beyond the directives above, HTTP caching also involves heuristic freshness, status/method-specific rules, `immutable`, stale controls, and proxy-specific policies. For important business data, **set an explicit policy** rather than relying on heuristics.

### Strong ETag vs. Weak ETag

- **Strong ETag**, e.g. `"abc123"`, has strong semantics regarding representation bytes per validator rules. If a gzip-compressed representation differs from the identity version, the same strong validator must not be arbitrarily reused as if the bytes were completely identical.
- **Weak ETag**, e.g. `W/"product-1-v4"`, indicates that content can be considered semantically equivalent for revalidation, but is not strong enough for operations requiring byte-range consistency or optimistic concurrency based on strong comparisons.
- HTTP `If-None-Match` with GET uses matching suitable for conditional retrieval, so a weak ETag is a reasonable choice when the validator is tied to a **business version** rather than an exact hash of response bytes.
- HTTP `If-Match` is for update preconditions with strong comparison semantics; if using true optimistic concurrency, design a dedicated strong validator/version contract.

`ETag` and `Last-Modified` can appear together; when a request includes `If-None-Match`, HTTP defines precedence rules over `If-Modified-Since`. Do not write custom logic such as “if either one matches then return 304” while ignoring protocol rules.

## 5. Generating Cache-Control, ETag, and 304 in Spring MVC

Spring Framework provides `CacheControl`, `ResponseEntity`, and `WebRequest.checkNotModified(...)` to help applications work with HTTP validators. For example, an endpoint building a response:

~~~java
CacheControl policy =
        CacheControl.maxAge(java.time.Duration.ofSeconds(30))
                    .cachePublic();

return ResponseEntity.ok()
        .cacheControl(policy)
        .eTag("W/\"product-1-v4\"")
        .body(product);
~~~

The snippet above is only a **controller fragment**, with `product` already created beforehand. `CacheControl` sets the response header; `eTag` sets the validator; when the framework processes the corresponding conditional request, the response can be converted to 304 per HTTP conditions. For code that needs explicit control over building and returning the body, the controller can also use `WebRequest.checkNotModified(etag)` to stop before rendering.

Several HTTP caching APIs do not require `@EnableCaching`. `@EnableCaching` enables **Spring method caching**, which is completely different from configuring HTTP responses.

### ShallowEtagHeaderFilter Is Not a Business Cache

`ShallowEtagHeaderFilter` can generate a “shallow” ETag based on the response content after it has been rendered, allowing clients to revalidate and save **bandwidth** when the body has not changed. It does not by itself guarantee avoiding controller/service/DB work or eliminating response rendering/serialization costs, and it may buffer content to compute the ETag. For large or streaming bodies, evaluate buffer overhead and compatibility before adding the filter.

If the app already has a reliable **version/updatedAt**, checking conditional requests early can avoid unnecessary processing/serialization. However, if a DB call is needed to fetch the version, there may still be origin overhead; that is where Spring Cache or lightweight metadata helps.

## 6. Spring Cache Is an Abstraction Over Method Invocations

Spring Framework defines a cache abstraction based on cache name/key and `CacheManager`. It **does not mandate** a specific provider and does not automatically determine TTL or distributed behavior. The main annotations:

| Annotation | Behavior | When to use |
|---|---|---|
| `@Cacheable` | Looks up the cache first; on a hit it can return the stored value without running the method; on a miss it executes and caches the result per rules. | Reading products, configuration, catalogs, or expensive computations. |
| `@CacheEvict` | Removes an entry or all entries by key/cache; by default after the method executes successfully. | Updating/deleting data that invalidates previously cached read results. |
| `@CachePut` | Always executes the method and puts the new result into the cache, without skipping the method. | Updating the cache alongside a mutation when key and result are consistent. |
| `@Caching` | Groups multiple cache operations on a method. | A mutation affecting multiple caches/keys. |
| `@CacheConfig` | Sets shared cache configuration at the class level. | Multiple methods sharing the same cache name/key generator. |
| `@EnableCaching` | Enables the infrastructure that interprets caching annotations. | Application configuration. |

`@Cacheable` does not mean “cache every HTTP GET”. The cache is only consulted when **that exact annotated method** is invoked through a Spring-supported mechanism. One HTTP request might invoke multiple cached methods, or none at all.

### Cache Providers and CacheManager

Spring Cache supports various backends. Common examples:

- **Simple/ConcurrentMapCacheManager:** stores entries in an internal JVM memory map. Easy to learn with, but lacks built-in TTL/size caps like Caffeine, is not shared across replicas, and is lost on restart.
- **Caffeine:** an in-process cache with configurable size limits, expiration, and statistics. Suitable for read-heavy data that does not require immediate synchronization across replicas; requires an invalidation mechanism if running multiple instances.
- **Redis:** an external cache store shareable across service instances, with TTL, network cost, and consistency/invalidation by design.
- **JCache or other providers:** supported depending on classpath/configuration; do not assume identical TTL semantics across all providers.

Spring Boot provides cache auto-configuration when the required infrastructure is present. In a project with `spring-boot-starter-cache` and `@EnableCaching`, if no specialized provider or user-defined `CacheManager` exists, Boot may choose the simple cache manager for demos. When Caffeine or Redis is added, Boot applies provider detection rules and specific configuration. **Do not assume `@Cacheable` automatically has a 60-second TTL.**

### Cache Keys Are Business Data, Not HTTP URLs

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long id) { ... }
~~~

`#p0` is the first parameter (id). The actual key here is the `products` cache + product id. For user-scoped data:

~~~java
@Cacheable(cacheNames = "accountPreferences",
           key = "#p0 + ':' + #p1")
public Preferences preferences(String tenantId, String userId) {
    // Illustrative only; Preferences and repository are application-defined.
    return repository.loadPreferences(tenantId, userId);
}
~~~

If the key only contains `userId` in a multi-tenant system with overlapping IDs, there is a risk of returning another tenant's data. If the result depends on currency, locale, pricing group, permissions, or version, those dimensions must also be accounted for. Do not use a full authentication token as a cache key or in logs.

## 7. Runnable Example: Spring Cache and HTTP Cache in One Spring Boot App

The following lab application provides:

- `GET /products/1`: public response with `Cache-Control: public, max-age=30` and a weak `ETag` based on version; calls a `@Cacheable` service.
- `GET /debug/load-count`: views how many times the method actually read the simulated “database”, response sets `no-store`.
- `PUT /products/1?name=TenMoi`: updates the data, increments the version, and performs `@CacheEvict` on the Spring Cache entry.
- No real DB needed: `ConcurrentHashMap` serves as storage for demonstration. In a real system, slow queries are the reason to cache method results.

### 7.1. Dependencies and Project

You need a **Spring Boot 3.3, Java 17+** project, already configured with the Gradle Spring Boot plugin, repositories, and dependency management. Add to `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

This is a dependencies snippet, **not the complete build script**. Do not add another cache provider in this lab so that simple cache behavior is preserved. In a project that already includes Redis or Caffeine, auto-configuration may pick a different provider, so create an isolated test project if you want the exact results.

### 7.2. Create a Complete Java File

Place at `src/main/java/example/twocaches/TwoCachesApplication.java`:

~~~java
package example.twocaches;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableCaching
public class TwoCachesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TwoCachesApplication.class, args);
    }

    public record Product(long id, String name, long version) { }

    @Service
    public static class CatalogService {
        // Simulated storage: not Spring's cache.
        private final Map<Long, Product> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public CatalogService() {
            database.put(1L, new Product(1L, "Notebook", 1L));
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(long id) {
            Product result = database.get(id);
            if (result == null) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Unknown product");
            }
            loads.incrementAndGet();
            return result;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public Product rename(long id, String newName) {
            return database.compute(id, (key, previous) -> {
                if (previous == null) {
                    throw new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Unknown product");
                }
                return new Product(
                        previous.id(), newName,
                        previous.version() + 1);
            });
        }

        public int loadCount() {
            return loads.get();
        }
    }

    @RestController
    public static class CatalogController {
        private final CatalogService service;

        public CatalogController(CatalogService service) {
            this.service = service;
        }

        @GetMapping("/products/{id}")
        public ResponseEntity<Product> get(
                @PathVariable long id,
                WebRequest request) {

            Product product = service.find(id);

            // Weak ETag reflects business version; does not assert
            // every JSON byte after content negotiation is immutable.
            String etag = "W/\"product-" + product.id()
                    + "-v" + product.version() + "\"";

            CacheControl policy = CacheControl
                    .maxAge(Duration.ofSeconds(30))
                    .cachePublic();

            if (request.checkNotModified(etag)) {
                return ResponseEntity
                        .status(HttpStatus.NOT_MODIFIED)
                        .cacheControl(policy)
                        .eTag(etag)
                        .build();
            }
            return ResponseEntity.ok()
                    .cacheControl(policy)
                    .eTag(etag)
                    .body(product);
        }

        @GetMapping("/debug/load-count")
        public ResponseEntity<Map<String, Integer>> count() {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(Map.of("loads", service.loadCount()));
        }

        @PutMapping("/products/{id}")
        public ResponseEntity<Product> rename(
                @PathVariable long id,
                @RequestParam String name) {

            if (name.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Blank name");
            }
            Product updated = service.rename(id, name);
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(updated);
        }
    }
}
~~~

**Why can this class run on Java 17?** The code uses Java records, `Map.of`, `ConcurrentHashMap`, `AtomicInteger`, `Duration`, and the corresponding Spring Boot APIs. Nested classes are `static`; `CatalogService` is a Spring `@Service` constructor-injected into the controller, ensuring calls to `service.find(...)` and `service.rename(...)` go through Spring's caching proxy. Do not call cached methods from within the `CatalogService` instance itself via `this.find(...)`.

`@EnableCaching` on the application class activates cache interception. Without a custom CacheManager or another cache provider, Boot can provide the simple cache. This cache **does not expire automatically** and only exists in the process's memory.

### 7.3. Run and Verify with curl

Run at the project root directory:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`; with the Maven wrapper in a Maven-configured Boot project use `./mvnw spring-boot:run`. Verify with the following commands, calling each command in order.

**Step A – First GET:**

~~~bash
curl -i http://localhost:8080/products/1
curl -s http://localhost:8080/debug/load-count
~~~

Expect status `200 OK` for the product, JSON equivalent to `{"id":1,"name":"Notebook","version":1}`, a public `Cache-Control` with max-age 30 seconds, and `ETag: W/"product-1-v1"`. The count endpoint returns:

~~~json
{"loads":1}
~~~

**Step B – call the same URL again with curl:**

~~~bash
curl -i http://localhost:8080/products/1
curl -s http://localhost:8080/debug/load-count
~~~

Expect `{"loads":1}` unchanged: the controller ran, but `@Cacheable` returned the Product from **Spring Cache** so the `find` method did not run again. **Plain curl does not retain an HTTP cache across invocations**; do not treat this as proof of a browser/CDN HTTP cache hit.

**Step C – send a conditional GET:**

~~~bash
curl -i -H 'If-None-Match: W/"product-1-v1"' \
  http://localhost:8080/products/1

curl -s http://localhost:8080/debug/load-count
~~~

In shells that support single quotes (Linux/macOS), the GET result should be `304 Not Modified`, empty body, ETag still corresponding to version 1, and `loads` still 1. On Windows PowerShell, quote according to the shell or use `curl.exe`; if quoting is uncertain, put it on one line and inspect the request with `curl -v`.

**Step D – update data:**

~~~bash
curl -i -X PUT "http://localhost:8080/products/1?name=So%20moi"
curl -s http://localhost:8080/debug/load-count
~~~

The update response returns Product version 2. `@CacheEvict` removes key 1's entry from Spring Cache **after the mutation succeeds**. However, count can still be 1 right after the PUT, because the mutation does not call `find`.

**Step E – GET again with the old ETag:**

~~~bash
curl -i -H 'If-None-Match: W/"product-1-v1"' \
  http://localhost:8080/products/1

curl -s http://localhost:8080/debug/load-count
~~~

Because the service cache was evicted, this GET reads the new storage state and builds a version 2 ETag, so expect `200 OK`, body with `"version":2`, ETag `W/"product-1-v2"`, and count incremented to:

~~~json
{"loads":2}
~~~

**An easily missed point:** A browser or CDN holding the v1 response **still fresh for 30 seconds** can reuse v1 for normal GETs even after PUT changed the backend/Spring Cache. The demo uses curl to actively query the origin; it does not prove the browser cache automatically vanishes after a mutation. If the product requires immediate fresh reads, you need to adjust the cache policy, cache key/versioned URL, purge/invalidation, or revalidation per the system contract.

### 7.4. Verifying Status and Response Headers

In practice, header order, JSON whitespace, charset style, Date, and connection headers are determined by Spring/the container. Do not rely on raw responses matching the example byte-for-byte; check **semantics**: status, ETag, Cache-Control, body, and method load count.

On a system with a proxy/CDN, `Age`, `Via`, `X-Cache` (if configured), and server access logs can help distinguish HTTP cache hits. Do not assume every CDN uses `X-Cache` or identical hit/miss syntax. In a browser, DevTools Network may display `from memory cache`, `from disk cache`, conditional revalidation, or a network response depending on the browser.

## 8. The Nature of Invalidation: Each Cache Has Its Own Clock

Consider a hypothetical timeline:

| Time | HTTP cache | Spring Cache | Database | Consequence |
|---|---|---|---|---|
| t = 0 | Browser stores response v1, fresh for 60 seconds | Service caches Product v1 | v1 | First GET returns v1 |
| t = 10 | Browser still holds fresh v1 | A mutation evicts Product v1 | v2 | Backend is new, but browser can still see v1 |
| t = 20 | Browser reuses v1 without asking origin | Business cache is not called | v2 | Evicting Spring Cache alone cannot clear the HTTP copy |
| t = 61 | Browser freshness expires, revalidates ETag v1 | Service loads/caches Product v2 | v2 | Origin returns 200 v2 instead of 304 |

**The reverse direction is also dangerous:** if the HTTP response has `no-cache` (forcing revalidation) while Spring Cache still holds Product v1 after the DB changed to v2 without eviction/expiration, the origin may keep sending weak ETag v1 and returning an incorrect `304` relative to the source data. HTTP revalidation **does not clean** a stale business cache. A consistent invalidation/TTL strategy is required.

There is no default formula linking the two TTLs. Business cache TTL must reflect the staleness tolerance of the domain and mutation mechanisms; HTTP TTL depends on staleness tolerance at the client/shared cache. Even if both TTLs are set to the same value, different entry creation times and revalidation conditions mean **there is no guarantee** they expire simultaneously.

### Common Update Strategies

- **Cache-aside:** the service reads via `@Cacheable`; after a successful mutation, it evicts the related key. Fits when updates are centrally managed and a small concurrency staleness window is acceptable.
- **Write-through/update cache:** after a mutation, updates the cache with the new record (possibly via `@CachePut`), but must ensure the cached value matches committed data and avoid races across requests.
- **TTL + eviction:** TTL acts as a safety net for mutations from external sources; TTL does not replace invalidation if immediate updates are required.
- **Event-driven invalidation:** when multiple services/replicas mutate data, publish invalidation/version-change events, paying attention to event ordering, retries, idempotency, and eventual consistency.
- **HTTP versioned URLs:** static resources with hash/version filenames are served with long freshness; when content changes, use a new URL.
- **CDN purge/invalidation:** use the CDN's official mechanism when you need to remove/refresh shared cache entries; a Spring `@CacheEvict` event does not trigger a CDN purge by itself.

## 9. When to Use no-store, private, public, or no-cache?

Classify by **sensitivity** and **allowed staleness**, not mechanically by whether an endpoint is GET or POST.

| Response | Usually appropriate HTTP policy | Business-layer Spring Cache |
|---|---|---|
| JS/CSS/images with content hash in filename | Long `public, max-age` and possibly `immutable`, depending on infrastructure | Usually no `@Cacheable` needed for binary static resources |
| Public product catalog, tens of seconds of staleness acceptable | `public, max-age=30` or explicit CDN policy | `@Cacheable` for products; evict on update |
| Fast-updating public news | Short `max-age`, `ETag`/Last-Modified for revalidation | TTL/invalidation matching update rate |
| Personal profile | `private` if browser storage is allowed; `no-store` if sensitive | If cached in service, key must include user/tenant/permission context and protect data |
| Access tokens, payment info, secrets | Usually `Cache-Control: no-store` alongside appropriate safeguards | Avoid storing such sensitive data in cache unless truly needed; apply encryption/access policy/TTL |
| Response varies by language | `Vary: Accept-Language`, plus freshness policy | Service cache key may need to include locale |
| Response varies by gzip/br | `Vary: Accept-Encoding` when representations depend on request encoding | Domain Product object can use a single cache entry independent of encoding |
| Near real-time data / quota | `no-store` or `no-cache` + reliable validator as required | Limit stale caching; strict invalidation/versioning |

`private` does not mean the data is encrypted or readable only by an authorized user. `no-store` also does not automatically purge copies already stored elsewhere or prevent logging; security requires authentication, authorization, TLS, and data retention policies.

### Authorization and Shared Caches

RFC 9111 places special restrictions on requests with `Authorization`: a shared cache must not arbitrarily reuse a response unless the response includes directives permitting it under specific rules. Therefore, **do not unconditionally attach `public`** to endpoints using Authorization just because it might increase cache hits. If representations are per-user, avoid shared caching by default and test with multiple accounts to catch cache leakage.

If a response depends on a session cookie, tenant, role, or feature flag, those dimensions can also affect the representation, yet merely adding `Vary: Cookie` is not an automatically safe solution and can cause massive cache fragmentation. Prefer no-store/private or properly scoped URLs/keys and explicit policies.

## 10. Spring Cache: Choosing a Provider, TTL, and Memory Budget

### 10.1. Simple Cache for Labs

With the default simple `ConcurrentMapCacheManager`, the cache can retain entries indefinitely until evicted, cleared, or the JVM restarts; memory usage grows with the number of keys/values if no suitable limit exists. **Do not use simple cache as a default production strategy for an unbounded key set.**

### 10.2. Caffeine: TTL and Capacity Limits Within One JVM

If you want an in-process cache with size caps and TTL in Spring Boot, add the Caffeine dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

In `application.properties` of **a project that already has starter-web**:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=60s
~~~

This is provider configuration, without modifying Spring `@Cacheable`. Once an entry's TTL expires, the next call can recompute it. Caffeine is a **per-instance** cache: if running three replicas, each replica has its own contents/timing. TTL does not guarantee data refreshes immediately without a request, and does not automatically notify browsers/CDNs when a mutation occurs.

### 10.3. Redis: Shared Cache and Load Limits

In a multi-instance environment, Redis can serve as a shared cache provider, with TTL configured via provider/Boot settings and connection pooling. Common properties example:

~~~properties
spring.cache.type=redis
spring.cache.redis.time-to-live=60s
~~~

This is **not** a standalone runnable Redis setup: the project must also have the Redis starter/driver, a Redis server, connectivity, and appropriate serialization. The TTL value applies to provider cache entries, not HTTP `Cache-Control`.

Using Redis cache for Java objects requires checking the serializer, schema/DTO versioning, key namespace, tenant isolation, backend durability, and failure modes. If Redis goes down, the application may slow down or fail due to cache dependency; do not assume caching is always “free”.

### 10.4. Cache Stampede and Concurrency

When a hot entry expires, many concurrent requests can miss simultaneously and query the DB together. Some providers support `@Cacheable(sync = true)` to synchronize value computation for the same key **within the scope the provider supports**, though you cannot assume this always synchronizes across multiple JVMs or resolves every refresh race. Measure DB load and cache miss spikes; for very hot data, consider TTL jitter, refresh-ahead, per-key coordination, or single-flight at an appropriate layer.

Too long a TTL causes staleness; too short a TTL causes frequent misses and increases backend load. Choose based on DB query cost, update frequency, freshness requirements, hot keys, and traffic patterns. Do not “optimize” by bumping all TTLs to several hours.

## 11. Proxy Limitations: Why Does @Cacheable Sometimes Not Run?

In Spring's default mode, cache annotations are typically applied through a **Spring AOP proxy**.

~~~java
@Service
public class CatalogService {
    @Cacheable("products")
    public Product find(long id) {
        return repository.load(id);
    }

    public Product anotherMethod(long id) {
        return this.find(id); // Call within same instance -> may bypass proxy
    }
}
~~~

This is an **illustrative code snippet**: `Product` and `repository` are application-defined, not a standalone runnable Java file. When another method calls `this.find(id)` on the same object, the call does not pass through the outer Spring proxy, so the caching annotation may not be applied. Other situations to check: objects created with `new` instead of container-managed beans, method visibility/proxy type, final methods/classes, cache infrastructure not enabled, or methods not invoked on the bean/proxy as intended.

The full example in section 7 uses a **controller calling a separate service bean** to avoid self-invocation. Do not try to fix this by making every method static or invoking the proxy from inside the object itself; clean service boundaries are easier to test and maintain.

### @Cacheable, @CachePut, and @CacheEvict Are Not Interchangeable

- `@Cacheable`: can skip method execution on a hit.
- `@CachePut`: **always runs** the method and uses the result to update the entry. If a method returns a response DTO different from the cached entity, misusing `@CachePut` can put the wrong type into the cache.
- `@CacheEvict`: deletes the entry, usually after the method completes successfully. If the database transaction has not committed yet or an event publishes late, races can happen; design invalidation order around transactions.
- `allEntries=true`: clears the entire cache, which can trigger a large cache stampede; only use when a change truly affects all keys.
- `beforeInvocation=true`: has different business semantics from default (evicts even if the method throws); do not enable carelessly.

A mutation may also affect list, category, and search caches. Evicting `products[id]` does not automatically delete `productSearch[query]`. Map cache key dependencies according to domain logic.

## 12. HTTP Conditional Requests and Consistent Validators

### Version-Based ETag

In the demo app, the weak ETag is `W/"product-1-v1"` for version 1. When a mutation bumps the version to 2, the validator changes. This approach is fast, but only accurate if every change affecting the **served representation** updates the version. If the JSON reflects inventory from another source without updating the version, the server may return 304 when the actual content has changed.

### Last-Modified

`Last-Modified` reflects the resource's modification time in HTTP time format. A reliable source timestamp is needed; header resolution may be coarser than multiple updates within the same second. Spring's `WebRequest.checkNotModified(lastModifiedMillis)` or `ResponseEntity.lastModified(...)` can support conditional requests. If two changes happen back-to-back within the same second, relying solely on Last-Modified can lack precision; a reliable version ETag is usually more suitable.

### 304 and Other HTTP Statuses

- `304 Not Modified` is used for conditional GET/HEAD when validators show the old representation can be reused; the response **has no body**.
- `412 Precondition Failed` typically relates to unmet update preconditions like `If-Match`, not a way to express a “cache miss”.
- `200 OK` with a new body is normal when validators do not match or the request lacks conditional headers.
- `206 Partial Content` is the response for valid range requests; strong ETags and exact byte representations matter when assembling multiple ranges.

Do not change a status to 304 just because of a business cache hit: a cache hit does not prove the browser already holds the previous body. Only return 304 when an **HTTP conditional request** and its validators genuinely satisfy the semantics.

## 13. HTTP Caching and gzip/br Compression

Because the parent topic is “HTTP Caching and Compression”, it is important to understand the relationship between **representation caching** and **content encoding**.

A client can send:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: gzip, br
~~~

The origin or CDN may choose a gzip/br-encoded representation or identity, depending on capabilities/config. If compressed responses differ by `Accept-Encoding`, the policy usually needs `Vary: Accept-Encoding` so caches select the right variant for each client. **Each encoded representation can have a different byte sequence.** This relates to generating strong ETags; do not assign the same strong validator to two representations with different bytes and assume it works across range/validator semantics.

In Spring Boot MVC, server-side response compression can be configured using the relevant properties:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=text/html,text/css,application/javascript,application/json
~~~

This is an **illustrative configuration snippet**; engine/container, MIME types, HTTP negotiation, proxies, and compression levels can vary by deployment. Do not enable compression for all content types when files are already compressed (JPEG/PNG images, video, archives), as it may save no bandwidth and increase CPU usage.

**Compression is not caching.** Compression makes the body transferred over the network smaller; HTTP caching can eliminate origin hits/transfers altogether if the representation is fresh; Spring Cache avoids work inside methods. The three mechanisms optimize different resources: bandwidth/compression CPU, network + origin requests, and DB/compute.

A useful byte-count/correlation test: measure response headers `Content-Encoding`, `Vary`, `ETag`, `Cache-Control`, and body size from the client; then compare the same endpoint when sending `Accept-Encoding: identity` versus allowing gzip/br. If representations differ, check validators and cache keys at the proxy layer. Do not use the `Content-Length` of uncompressed JSON as the byte count of a compressed response.

## 14. Spring Boot Static Resources: HTTP Caching Is Often More Useful Than @Cacheable

JS, CSS, icons, and static images are typically served by Spring Boot's static resource handling from the classpath, e.g. `src/main/resources/static`. When filenames include a content hash/version (e.g. `app.8f0a21.js`), you can set long freshness for those immutable URLs: when content changes, the build produces a new URL. This is controlled “cache busting”.

With Spring Boot 3.3, static resource caching properties include:

~~~properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
~~~

This configuration is only appropriate **when resource URLs are truly immutable/versioned** and deployment guarantees new bytes are never served under an old URL. If you overwrite `/app.js` while keeping it fresh for one year, clients may continue using the old JS for a very long time.

At the Spring MVC level, `ResourceHandlerRegistry` and `CacheControl` can configure individual resource mappings. This is HTTP response caching; you do not need `@Cacheable` on a Java service just to cache JavaScript files.

## 15. Does Spring WebFlux Have HTTP Caching and Spring Cache?

Yes. Spring WebFlux supports HTTP caching via `CacheControl`, ETag/Last-Modified, conditional requests, and `ServerWebExchange.checkNotModified(...)`. Spring's Cache abstraction can also be used in the service layer of a WebFlux application, though the **non-blocking execution path** must be evaluated based on cache provider and Spring Framework version.

A logic example (code **illustrative inside a WebFlux controller**, does not compile standalone):

~~~java
@GetMapping("/reactive-products/{id}")
public Mono<ResponseEntity<Product>> get(@PathVariable long id,
                                          ServerWebExchange exchange) {
    return productService.findReactive(id)
            .map(product -> {
                String etag = "W/\"product-" + id
                        + "-v" + product.version() + "\"";
                CacheControl policy =
                        CacheControl.maxAge(Duration.ofSeconds(15))
                                    .cachePublic();

                if (exchange.checkNotModified(etag)) {
                    return ResponseEntity
                            .status(HttpStatus.NOT_MODIFIED)
                            .cacheControl(policy)
                            .eTag(etag)
                            .build();
                }
                return ResponseEntity.ok()
                        .cacheControl(policy)
                        .eTag(etag)
                        .body(product);
            });
}
~~~

Requires the corresponding controller class/imports, reactive service, and Product type. This example illustrates HTTP conditional handling, not how to implement a cache provider. Spring Framework 6.1 has dedicated handling for reactive return types in the cache abstraction; `Mono`/`Flux` behavior, asynchronous cache retrieval, and compatibility depend on version/provider. Do not assume “wrapping a blocking `RedisTemplate` in `Mono`” makes cache I/O non-blocking.

In WebFlux, blocking cache clients, database calls, or heavy serialization running on the Netty event loop can slow down many requests. If using a blocking cache provider, offload work appropriately or choose a genuinely reactive API/adapter. HTTP cache policies still follow the same client/proxy semantics as in MVC.

## 16. Measuring Effectiveness at Each Layer Separately

Do not look at a single “cache hit ratio” number and conclude the entire system is efficient. Measure **each layer**.

| Observation | How to measure | Valid conclusion |
|---|---|---|
| Browser HTTP cache | DevTools Network, transfer size, conditional GET | Can reduce origin requests or client bandwidth |
| CDN shared cache | CDN analytics/response metadata, origin logs | Whether the shared cache serves requests per policy |
| Spring Cache hit/miss | Provider metrics, method invocation count, traces | Whether expensive methods are skipped on hits |
| DB query rate | DB/query metrics, downstream spans | Whether caching reduces backend work |
| Serialization/CPU | Profiling/traces on the server | A business cache hit can still re-serialize DTOs |
| HTTP `304` | Access logs, client traces, response status | Revalidation saves body bandwidth; does not prove methods did not run |
| p95/p99 latency | Client/proxy/server metrics by path | Real impact on experience; separate cache hits/misses |
| Cache memory usage | Caffeine/Redis/JVM metrics | Whether key cardinality/entry size/TTL fit the budget |

### Key Measurement Formulas

Business cache hit ratio:

~~~text
hit_ratio = cache_hits / (cache_hits + cache_misses)
~~~

Where hits/misses must come from the provider under a consistent definition, not inferred from HTTP 200/304. HTTP cache hit ratio is calculated over requests/representations served from browser/proxy; the two ratios have **different denominators**.

To measure impact on the database:

~~~text
DB queries per second (before) = 1000
DB queries per second (after)  = 150
Reduction = (1000 - 150) / 1000 = 85%
~~~

This is only an example formula, not measured metrics from the demo application. Control for traffic mix, read/write ratio, cache warm-up, TTL, CDN hit rate, and replica count before comparing.

### A Short Controlled Benchmark Process

1. Define the workload: e.g., 90% public product GETs, 10% PUT updates; hot/cold key ratio, JSON payload size, and unique user count.
2. Run a baseline with Spring Cache off (or without annotations) and HTTP cache forced to revalidate, recording DB load, CPU, network bytes, and p95/p99.
3. Enable **Spring Cache alone**; measure cache hits, DB load, and p95/p99 at the origin. To keep HTTP caching from hiding requests, use a test client that intentionally sends requests to the origin.
4. Enable **HTTP caching** at the browser/CDN per policy; measure origin request rate, transfer bytes, Age, and 304 count, verifying no data leaks between users.
5. Run mutations, TTL expirations, cache purges, concurrent misses, and failovers; confirm data freshness meets SLOs.
6. Test compression on/off under the same traffic profile; measure bandwidth and CPU changes, and check Vary/ETag correctness.

Do not compare run 1 with a cold cache against run 2 with a warm cache and claim one cache is better; record conditions and repeat tests.

## 17. Common Pitfalls and Root Causes

| Symptom | Common cause | How to fix |
|---|---|---|
| Calling GET twice with curl returns 200 both times, yet DB is not queried again | Curl does not reuse HTTP cache; Spring Cache hit | Check load count/metrics; test If-None-Match separately |
| Browser still sees old product after `@CacheEvict` | Browser/CDN still holds a fresh response | Reduce max-age, use revalidation, or purge/version URLs as needed |
| HTTP 304 even though backend data changed | ETag/version computed from stale business cache, not invalidated | Check validator source and service eviction/TTL |
| With `no-cache`, responses are still stored | `no-cache` allows storage but requires revalidation | Use `no-store` when storage must be prohibited per protocol |
| `@Cacheable` is present but method still runs every time | Self-invocation, unproxied bean, different key, missing `@EnableCaching`/provider | Check proxy, key, bean wiring, and instrumentation |
| `@CachePut` updates DB, but GET stays stale | Inconsistent keys, uncommitted mutation, different cache | Standardize key namespace, evict/update after commit |
| CPU/heap grows despite high cache hit rate | Cache stores large objects, high key cardinality, missing TTL/size cap | Cap size/TTL, measure memory and object graphs |
| Caffeine cache hits differ across replicas | Cache lives inside each JVM | Accept eventual consistency or use distributed invalidation/cache |
| CDN serves user A's content to user B | Wrong `public`/shared policy, key missing context, cacheable auth response | Use `no-store`/`private`, access tests, and safe shared-cache design |
| Vietnamese/English responses get mixed up | Missing `Vary: Accept-Language` or key dimension | Add proper Vary and verify cache variants |
| Client receives gzip when unsupported | Incorrect `Vary: Accept-Encoding`/cache config | Fix representation variants, proxy, and compression negotiation |
| Same strong ETag shared between byte-different gzip and identity | Validator violates representation semantics | Use strong per representation or weak when appropriate |
| Increasing `s-maxage` does not make browsers hold longer | `s-maxage` controls shared caches | Configure `max-age` separately for private browsers |
| Configured Redis TTL, yet HTTP still caches for many minutes | Redis TTL does not change `Cache-Control` | Design TTL per layer; HTTP headers are independent |
| Enabled `ShallowEtagHeaderFilter`, yet CPU did not drop | Filter usually needs the rendered body to hash it | Use version-based conditional handling / business cache |
| Caching everywhere makes p99 worse | Overloaded cache server, miss stampede, Redis latency, large serialization | Measure each layer, concurrency, backend, and cache provider |

## 18. Designing a Testable Cache Policy

Before enabling caching for an endpoint, answer these questions thoroughly:

1. **Who owns the data?** Public, per-user, tenant, role, or authorization scope?
2. **How fresh must it be?** Is 30 seconds or 1 minute of staleness acceptable, or is immediate “read-your-writes” required?
3. **What changes the representation?** Version, locale, currency, feature flag, personalized pricing, content encoding?
4. **Which layer needs optimizing?** Reducing bandwidth/CDN origin requests, or reducing DB/CPU inside the service?
5. **What is the complete cache key?** HTTP variants via Vary, Spring keys via domain identity + context.
6. **Are there external mutations?** Do admin consoles, batch jobs, events, or downstream systems modify the same data?
7. **How is invalidation performed?** Evict, `@CachePut`, TTL, events, CDN purge, versioned URLs, or a combination?
8. **What if the cache fails or is unavailable?** DB fallback, timeouts, overload control, consistency, and error observability.
9. **What are the resource limits?** Cache entry count/size, network round trips, Redis memory, serialization, max stale.
10. **What test evidence is sufficient?** HTTP headers, conditional GET 304, no-store on sensitive endpoints, cache provider metrics, mutation correctness, and multi-user isolation.

Whenever possible, encode these conditions as **integration tests**: after mutating, the product version must change; the new ETag must differ; GET with the old ETag must return 200; GET with the new ETag returns 304; sensitive endpoints must have proper policies; cache keys must not leak across tenants. When using a real CDN, test both the origin and shared cache in an authorized environment, because controller tests do not fully simulate RFC caching behavior.

## 19. Self-Check

**Question 1.** A Spring service returns from `@Cacheable`; does the browser automatically receive HTTP 304?  
**Answer:** No. 304 only happens when an HTTP request is conditional and validators match; a Spring Cache hit only indicates method result reuse inside the application.

**Question 2.** The server returns `Cache-Control: public, max-age=60`, and the browser still has a fresh response. Will the controller definitely run on the next GET?  
**Answer:** No. An HTTP cache can serve the response without sending a request to the origin.

**Question 3.** Does `no-cache` mean storage of the response is forbidden?  
**Answer:** No. Caches may store it, but must revalidate successfully before reusing it. `no-store` is the directive that forbids storage per HTTP semantics.

**Question 4.** After `@CacheEvict`, does the CDN automatically purge its cached response?  
**Answer:** No. You need HTTP policies/TTL/revalidation, versioned URLs, or a separate CDN invalidation mechanism.

**Question 5.** Can you use Spring Cache TTL = 5 minutes and HTTP max-age = 10 seconds?  
**Answer:** Yes, but you must evaluate stale consistency: after 10 seconds when the browser revalidates, the origin could still serve 5-minute-old data from Spring Cache without reliable invalidation.

**Question 6.** How does `@CachePut` differ from `@Cacheable`?  
**Answer:** `@CachePut` always executes the method and updates the cache with its result; `@Cacheable` can skip the method on a hit.

**Question 7.** If a `@Cacheable` method is called via `this.method()` inside the same bean, is it guaranteed to go through the proxy?  
**Answer:** Not in default proxy mode. Self-invocation can bypass caching advice.

**Question 8.** Is it safe to mark a user-specific response `public` just because it has an authorization token?  
**Answer:** No. You must design shared cache policy around content and Authorization rules to prevent personal data leaks; `no-store`/`private` is usually more appropriate.

**Question 9.** What does `Vary: Accept-Encoding` control?  
**Answer:** It tells HTTP caches to distinguish response variants by request `Accept-Encoding`, avoiding serving mismatched gzip/br/identity copies.

**Question 10.** Is a version-based weak ETag suitable for revalidating JSON?  
**Answer:** It can be suitable if the version changes on every semantic change to the representation. It does not replace strong validators for operations requiring byte identity.

**Question 11.** Does `ShallowEtagHeaderFilter` automatically eliminate DB query and rendering costs?  
**Answer:** No. The filter typically computes the ETag from the rendered body, saving bandwidth while the service/serialization may still execute.

**Question 12.** Does measuring a high Spring Cache hit ratio prove the CDN is working well?  
**Answer:** No. HTTP cache hit/miss is an independent metric at the browser/proxy, with its own denominator and network behavior.

## 20. Official References

- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): private/shared caches, freshness, storage, and Cache-Control directives.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ETag, Last-Modified, conditional requests, and representation semantics.
- [Spring Framework – HTTP Caching in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): CacheControl, ResponseEntity, conditional requests, and ShallowEtagHeaderFilter.
- [Spring Framework – HTTP Caching in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): HTTP validators and CacheControl in the reactive stack.
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): cache name, key, CacheManager, semantics, and provider integration.
- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): @Cacheable, @CacheEvict, @CachePut, sync, and proxy-related behavior.
- [Spring Boot 3.3 – Caching](https://docs.spring.io/spring-boot/3.3/reference/io/caching.html): cache auto-configuration and providers in Spring Boot.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): properties for cache providers, static resources, and response compression.
