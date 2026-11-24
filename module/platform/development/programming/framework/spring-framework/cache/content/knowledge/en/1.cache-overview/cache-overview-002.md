# Distinguishing Cache, Buffer, Database, and HTTP Cache in Spring Framework

## 1. Four Concepts Solving Four Different Needs

In a Spring application, the same data may pass through a **database**, an **application cache**, a **buffer**, and an **HTTP cache**. They can coexist, yet they serve different purposes:

- **Cache (result cache):** holds copies or reproducible computation results so subsequent accesses are faster, reducing work on the origin data source/processing stage.
- **Buffer (stream buffer):** temporarily holds data being transferred or processed to batch I/O operations, smooth out speed differences between producer and consumer, or process data in chunks.
- **Database:** manages data with schemas, queries, and consistency constraints; usually the **authoritative data source** (source of truth) for the business domain.
- **HTTP cache:** **a type of cache at the HTTP protocol layer**. Browsers, proxies, or CDNs store representations of HTTP responses and decide when they may be reused or must be revalidated according to HTTP headers.

The core distinction: **cache** is about *reusing results*, **buffer** is about *data streams in motion*, **database** is about *managing business state*, and **HTTP cache** is about *reusing HTTP responses*. HTTP cache belongs to the cache family, but has different rules and operating locations than Spring method caching.

| Criterion | Application Cache | Buffer | Database | HTTP Cache |
|---|---|---|---|---|
| Primary goal | Reduce repeated queries or computations | Reduce I/O overhead, regulate flow | Store, query, and enforce data rules | Reduce network load, latency, and requests to origin |
| Typical unit | Key → value/result | Bytes, characters, pending elements | Records, rows, documents, relations | HTTP response/representation tied to request and cache rules |
| Usage pattern | Lookup by key; hit/miss | Sequential or chunked read/write | Query, transaction, CRUD | Serve fresh response or revalidate |
| When stale/full | TTL, eviction, update/delete | Flush, consumption, backpressure | Write/update/delete per business logic | Freshness lifetime, validator, invalidation/purge |
| Role in correctness | Usually discardable and reproducible | Does not replace the data source | Usually the authoritative source | Depends on origin response and HTTP cache policy |
| Examples | Spring `@Cacheable`, Caffeine, Redis | `BufferedInputStream`, `ByteBuffer` | PostgreSQL, MySQL, MongoDB | Browser cache, CDN, `Cache-Control`, `ETag` |

**Note:** a database may also use an internal buffer pool/cache; a cache may also be stored on disk or in Redis. Classification is based on **the role and guarantees of the data**, not merely where it resides (RAM or disk).

## 2. How Does Application Caching Work in Spring?

Suppose an API fetches a product by ID. A read without caching follows this flow:

~~~text
HTTP request → Controller → Service → Repository → Database → Response
~~~

When caching is applied at the service layer:

~~~text
HTTP request → Controller → Service → [Cache by productId]
                                         │
                       hit: return result ─┤
                                         └─ miss: Repository → Database
                                                    │
                                              write to cache
                                                    │
                                                return result
~~~

- **Cache hit:** the key already has a valid value, so the service can return the result without running the origin query.
- **Cache miss:** the key is absent (or the entry expired/was deleted), so it must read from the source and may then populate the cache.
- **Cache key:** unique identifier for the query conditions. Using only `productId` is wrong if the result also depends on tenant, locale, access permissions, regional pricing, or data version.
- **Invalidation/eviction:** after the source changes, the cached value must be prevented from being wrongly reused; entries can be deleted, updated, or left to wait for TTL if the business allows slightly stale data.
- **TTL (time to live):** how long an entry is considered valid per the cache provider's policy; TTL does not by itself solve all consistency or sensitive-data issues.

### Using Spring's Cache Abstraction

Spring provides an abstraction to declare cache operations on methods. The snippet below is **illustrative integration code**, requiring Spring Framework, corresponding domain/repository classes, and application configuration; **it is not a standalone Java program**.

~~~java
@Configuration
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}

@Service
class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Product findById(long id) {
        return repository.findById(id).orElseThrow();
    }

    @CacheEvict(cacheNames = "products", key = "#id")
    public void rename(long id, String newName) {
        repository.rename(id, newName);
    }
}
~~~

Here, `Product` and `ProductRepository` are assumed business types. `@EnableCaching` enables cache annotation processing; `CacheManager` selects where caches are stored. `@Cacheable` allows reusing a stored result keyed by `id` and skipping the method body on a hit. `@CacheEvict` by default deletes the entry **after the method completes successfully**, so the next read fetches fresh data. `@CachePut` is another option when you want to **always execute the method** and put its return value into the cache.

`ConcurrentMapCacheManager` is an in-memory implementation convenient for learning or simple cases; it does not provide TTL out of the box like a cache provider with expiration policies. When the application runs multiple instances, in-RAM caches on each instance do not synchronize automatically. You can use Caffeine for local memory/TTL management or Redis and an appropriate provider for a shared cache; configuring timeouts, serialization, versioning, and invalidation depends on the actual system.

**Commonly overlooked limitations:**

1. Proxy-based cache annotations usually take effect only when calls go **through the Spring proxy**; calling `this.findById(id)` from another method in the same object can bypass interception.
2. Updating the database and modifying the cache do not naturally form an atomic transaction. For transactional operations, you must consider commit timing, rollback, and invalidation; do not assume `@CacheEvict` solves every race condition.
3. Do not blindly cache user- or permission-dependent results if the key does not distinguish context. Revoking or changing permissions must also invalidate cached data.
4. A high hit ratio does not mean data is correct. Monitor stale reads, memory usage, reload time, provider errors, and origin hits on cache misses.

## 3. Buffer: Holding Data in Transit, Not a Query Result Store

A buffer serves **streaming or transfer** processes. For example, when reading a file byte by byte, `BufferedInputStream` can read many bytes from the source into a memory region and then serve many small `read()` calls. This reduces calls to the more expensive I/O source. `BufferedWriter` typically batches writes and flushes them to the destination when full, when `flush()` is called, or when properly closed.

~~~text
I/O Source → [buffer holding a block of bytes] → reader consumes sequentially
Writer     → [buffer batching multiple writes] → I/O destination
~~~

Unlike a key-based cache, a buffer usually has no concept of **hit/miss for the same business query**. Data is consumed, written out, or replaced as the stream progresses. In asynchronous pipelines, a bounded buffer/queue can absorb temporary rate mismatches; when the consumer is persistently slow, backpressure, size limits, or overload-handling policies are needed. A buffer **does not make a database more durable**, nor does it guarantee that a user's response is saved for the next request.

Examples to tell them apart:

- Reading a large file with `BufferedInputStream`: the buffer saves small read operations; a call to load a different file does not receive old results from the buffer.
- Caching file contents by path/version: subsequent requests can reuse the stored result, but you must check for file changes.
- Spring MVC/Servlet has mechanisms to buffer response writes or request reads; the fact that an HTTP response is *streamed through a buffer* does not mean browsers or CDNs are allowed to *cache* that response.

## 4. Database: Where Business Truth Lives

In a sales system, the database is typically where product names, orders, inventory, confirmed changes, and constraints are stored. It supports capabilities a cache cannot replace: transactional business updates, flexible querying, locks/constraints, transactions, and typically crash recovery.

A cache entry `products:42 → "Java"` does not imply the database changed if the cache is edited. If the cache is cleared and the system is properly designed, the application must still be able to fetch or reconstruct the information from the authoritative source. Conversely, accidentally deleting a database record is a business-state change requiring backups or recovery mechanisms.

Not every database persists to disk, and not every cache loses data on restart: there are in-memory databases and distributed caches with persistence. The criterion is the **data contract**. A system can use Redis as its primary data store if designed that way; in that case, calling it a "cache you can freely wipe" would be wrong.

**Typical update flow:**

~~~text
Write change → Database commits per business rules
             → update/evict corresponding application cache
             → HTTP cache expires, revalidates, or is purged per policy
~~~

These are separate responsibilities. A database change **does not automatically** clear browser caches or every service instance's cache. If inventory requires high freshness, choose an appropriate policy and handle transactions/concurrency carefully; do not rely on an arbitrary TTL.

## 5. HTTP Cache: Caching Responses by HTTP Rules

In web architecture, responses can be reused **before the request even reaches the Spring Controller**:

~~~text
Browser → [browser HTTP cache] → [CDN/proxy cache] → Spring Controller
                                                        ↓
                                                  Spring service cache
                                                        ↓
                                                     Database
~~~

HTTP caches evaluate responses based on request details and HTTP directives; they do not directly read `@Cacheable` annotations or know internal `CacheManager` keys.

Common directives/validators:

| HTTP Header | Practical Meaning |
|---|---|
| `Cache-Control: max-age=60` | Response can be considered fresh for 60 seconds according to HTTP cache age calculation rules. |
| `Cache-Control: private` | Response is intended for a private cache, such as a browser cache; shared caches must not store it. |
| `Cache-Control: public` | Allows shared caches to store the response when other conditions are valid; must consider authorized/private data. |
| `Cache-Control: no-cache` | Response may be stored, **but must be revalidated before reuse**. |
| `Cache-Control: no-store` | Instructs caches not to store the response; it is not a command to purge previously cached copies. |
| `ETag` and request `If-None-Match` | Validator comparing representation versions; if unchanged, origin may return `304 Not Modified`. |
| `Last-Modified` and `If-Modified-Since` | Revalidation method based on modification timestamp; requires a reliable timestamp source. |
| `Vary` | Declares request headers affecting the representation so caches distinguish variants properly. |

Example endpoint returning data not intended for shared caches:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60
ETag: "product-42-v7"

{"id":42,"name":"Java"}
~~~

While the response is still fresh, the browser can reuse its stored copy without sending a new request. When revalidation is needed, the browser can send:

~~~http
GET /products/42 HTTP/1.1
Host: example.test
If-None-Match: "product-42-v7"
~~~

If the representation on the server **has not changed**, a valid response can be:

~~~http
HTTP/1.1 304 Not Modified
Cache-Control: private, max-age=60
ETag: "product-42-v7"
~~~

A `304` **carries no response body**; the client continues using the stored body with updated metadata. If the resource has changed, the server typically returns `200 OK` with the new body and validator. This is **HTTP revalidation**, different from `@Cacheable` hit/miss. An API handling conditional requests must have a mechanism to set validators and evaluate conditions; merely adding `ETag` as a text string does not automatically implement the full protocol.

**Safety and correctness issues:** responses carrying user-specific data must not accidentally enter a shared cache. Use appropriate policies such as `private` or `no-store`, along with proper authorization, cookie/Authorization handling, and `Vary`. `max-age=60` can allow users to see old data while fresh; evicting the server's application cache does not make browsers immediately forget their stored HTTP copy.

## 6. Standalone Java 17 Demonstration: Key-Based Cache and Stream Buffer

This example uses only JDK 17+, without Spring. `Map database` simulates an **in-program authoritative source**, **not a real database or durable storage**. `Map cache` simulates a key-based read cache. `BufferedInputStream` illustrates reading a byte stream through a buffer; `ByteArrayInputStream` is used only to keep the example self-contained, not for measuring I/O performance.

Save the file `CacheBufferDemo.java`:

~~~java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class CacheBufferDemo {
    private static final Map<Long, String> database = new HashMap<>();
    private static final Map<Long, String> cache = new HashMap<>();

    private static String findProduct(long id) {
        if (cache.containsKey(id)) {
            System.out.println("CACHE HIT");
            return cache.get(id);
        }
        System.out.println("CACHE MISS -> DATABASE");
        String result = database.get(id);
        if (result == null) {
            throw new IllegalArgumentException("Unknown product: " + id);
        }
        cache.put(id, result);
        return result;
    }

    private static void renameProduct(long id, String newName) {
        database.put(id, newName);
        cache.remove(id);
    }

    public static void main(String[] args) throws IOException {
        database.put(1L, "Java");

        System.out.println(findProduct(1L));
        System.out.println(findProduct(1L));

        renameProduct(1L, "Java 21");
        System.out.println(findProduct(1L));

        byte[] bytes = "AB".getBytes(StandardCharsets.US_ASCII);
        try (BufferedInputStream buffer =
                 new BufferedInputStream(new ByteArrayInputStream(bytes))) {
            System.out.println("BUFFER READ: " + (char) buffer.read());
            System.out.println("BUFFER READ: " + (char) buffer.read());
        }
    }
}
~~~

Compile and run:

~~~bash
javac CacheBufferDemo.java
java CacheBufferDemo
~~~

Exact stdout:

~~~text
CACHE MISS -> DATABASE
Java
CACHE HIT
Java
CACHE MISS -> DATABASE
Java 21
BUFFER READ: A
BUFFER READ: B
~~~

Explanation: the first `findProduct(1L)` call misses, the second hits; `renameProduct` updates the source and removes the cache entry so the next call must read from the source again. The two `read()` calls fetch two consecutive bytes from the stream, not two keyed queries. The demo is single-threaded and ignores concurrent contention; real applications need thread-safe cache mechanisms, expiration/synchronization policies, and source error handling.

## 7. Choosing the Right Tool for the Situation

| Business/Technical Question | What to Consider | Why |
|---|---|---|
| Same product catalog read repeatedly; DB query is expensive? | Application cache (`@Cacheable` + suitable provider) | Avoids recomputing/re-querying; needs keys, TTL, and invalidation. |
| Reading a network/disk file in many small reads? | Buffer | Batches I/O and manages data streams. |
| Orders must be confirmed, audited, and queried with exact state? | Database/transaction | Source of business state; caching only optimizes reads when appropriate. |
| Users reload the same image or identical GET response? | HTTP cache | Reduces round trips and can avoid hitting the backend; uses validators/cache policy. |
| Authenticated API data can differ per user? | Design cache keys and HTTP policy by permissions | Prevents cross-user data leaks; avoids inappropriate shared caching. |
| Backend evicted, yet the page still shows an old version? | Also check HTTP cache and frontend state | Layers store independent copies and do not automatically cascade invalidation. |

### When Multiple Cache Layers Exist

A `GET /products/42` request may:
1. Be served by the browser from its HTTP cache: **no HTTP request reaches the backend**.
2. Bypass browser cache but be served by a CDN: **Spring does not receive the request**.
3. Reach Spring and hit `@Cacheable`: **repository is not queried**.
4. Reach Spring and miss the application cache: **reads database then populates cache**.

Therefore, observing "the DB was not queried" is **not enough to determine** which cache layer acted. When debugging, inspect network/request headers and status (`200`/`304`), Controller/Service logs, cache hit/miss stats, and corresponding database queries. Avoid confusing a "buffered response" on the server with a "browser-cached response".

## 8. Common Mistakes and Principles to Remember

- **Using cache instead of a database:** caches can be evicted, expire, or lose data; the authoritative source and transactional responsibilities must be clear.
- **Confusing a buffer with a query cache:** a buffer serves stream reading/writing; it does not automatically reuse keyed business results across requests.
- **Assuming HTTP cache and `@Cacheable` are the same:** they operate at two different layers with separate keys and invalidation.
- **Thinking `no-cache` forbids storing:** it actually requires revalidation before reuse; `no-store` is the directive not to store.
- **Forgetting invalidation:** the DB has been updated, yet the application cache or HTTP cache may still hold old copies.
- **Omitting factors that affect the key:** same ID with different tenant, permissions, locale, or parameters may require distinct entries.
- **Ignoring resources and concurrency:** overly large caches cause memory pressure; hot keys/cache stampedes can send many requests straight to the DB on a miss; unbounded buffers can exhaust RAM.
- **Assuming annotations guarantee hits:** caching must be enabled, a suitable `CacheManager` must exist, calls must go through the proxy in proxy mode, and real metrics must be measured.

**Self-check:** (1) During a file upload operation, do bytes waiting to be written belong to a buffer or a query cache? (2) If a response is served by the browser without the Spring Controller running, which layer may be responsible? (3) When a product price changes, is evicting the `@Cacheable` entry enough to purge copies stored in a CDN? (4) Why should a tenant-scoped permissioned result not use a cache key containing only the ID?

**Suggested answers:** (1) Buffer. (2) Browser-side HTTP cache or an intermediate cache. (3) No; HTTP caches have separate policies and management mechanisms. (4) It risks serving the wrong tenant's data because the key lacks context.

## 9. References

- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework Reference — Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- MDN — HTTP Caching: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control

**Final takeaway:** the **database** holds authoritative business state; a **buffer** moves streaming data efficiently; an **application cache** makes processing/query results reusable; an **HTTP cache** makes web responses reusable per HTTP rules. Pick the right layer and design **keys, freshness, invalidation, and access control** before optimizing speed.