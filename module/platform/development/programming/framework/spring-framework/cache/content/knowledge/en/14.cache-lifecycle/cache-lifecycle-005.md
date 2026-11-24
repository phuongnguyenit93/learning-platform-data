# Caching Non-Existent Results and What Happens When Data Is Created Later

## 1. Scenario: “not found” yesterday, created today

Suppose an API looks up books by `bookId`. The first time `B42` is queried, the database returns “does not exist.” Shortly afterward, an administrator creates book `B42`. Yet the search API keeps reporting “not found” even though the database already has the record. Why?

A common cause is **negative caching**: the system remembered not only found results, but also **not-found results**. The next time the `@Cacheable` method receives the same key, Spring may return “does not exist” from the cache **without running the database query method**.

```text
T0: database does not have B42
    getById("B42") -> cache MISS -> DB: not found
    cache["B42"] = <value representing "not found">

T1: another thread creates B42 in the database
    database["B42"] = Book("B42", "New Book")
    cache["B42"] remains <not found> if not invalidated

T2: getById("B42") -> cache HIT
    returns "not found" from cache, DOES NOT read the new database state

T3: evict/expire/re-put the right key
    getById("B42") -> cache MISS or HIT with new value
    callers now see Book("B42", "New Book")
```

**Conclusion:** the cache does not automatically observe database changes. A “does not exist” observation at T0 is **not an eternal truth**. If the cache holds onto that observation for too long, the application suffers from “the record was created yet still returns 404.”

This is a **data lifecycle and consistency** issue, not a bug in `@Cacheable` itself.

## 2. “Cache miss” differs from “cache holds a null value”

Keep the two states clearly separated in your mental model:

- **Cache miss:** no mapping exists for the key. Spring must invoke the target method to retrieve data per the operation's configuration.
- **Cache hit containing a non-existent result:** a mapping exists, yet the stored business value represents “no record.” Spring may **skip invoking the target method** and return the empty representation.

A simple method:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String bookId) {
    return repository.find(bookId); // returns null if not found
}
```

*This is an illustrative snippet, not a standalone program; `Book` and `repository` are not defined.*

If the cache provider allows storing `null` through the Spring abstraction, the first call returning `null` can cause the cache to store **an entry representing `null`**. Next time, with the same key, Spring sees the entry and returns `null` without entering `repository.find`.

**Not all cache providers handle `null` the same way.** Some support it or convert `null` into an internal sentinel; some configurations disallow storing `null`; some adapters reject put-null operations. Therefore, never conclude “Spring always caches `null`” without knowing your application's `CacheManager` and provider.

### 2.1. How Spring distinguishes them with `Cache.ValueWrapper`

When using the `Cache` API directly:

```java
Cache.ValueWrapper wrapper = cache.get("B42");

if (wrapper == null) {
    System.out.println("MISS: entry does not exist");
} else if (wrapper.get() == null) {
    System.out.println("HIT: entry represents a null result");
} else {
    System.out.println("HIT: actual object present");
}
```

*This example belongs inside a method where `Cache cache` is already available; corresponding imports must be added.*

With caches that can hold `null` such as the default `ConcurrentMapCache`, these two expressions have **different** meanings:

- `cache.get(key) == null`: no entry exists.
- `cache.get(key) != null && cache.get(key).get() == null`: an entry exists, and **the user value is `null`**.

Do not use `cache.get(key, Book.class) == null` to assert a miss, because the retrieval path returning an unwrapped value cannot distinguish “no mapping” from “a mapping containing `null`.”

### 2.2. `ConcurrentMapCacheManager` and `null` values

Spring Framework's `ConcurrentMapCacheManager` **allows `null` by default** by converting `null` into an internal placeholder object, even though Java's `ConcurrentHashMap` does not support storing `null` directly. Related configuration:

```java
@Bean
CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
    manager.setAllowNullValues(true);
    return manager;
}
```

*This is only a bean in a configuration class, not a standalone Java file.*

If changed to `manager.setAllowNullValues(false)`, this provider is not permitted to store `null`. However, **disabling `allowNullValues` does not automatically activate a valid fallback or reload policy**: if the method actually returns `null` and the operation still attempts to put, an error can occur. When the goal is “return `null` to callers without caching `null`,” configuring `unless` explicitly is the clearer option.

## 3. `Optional.empty()` can become a cached negative result

It is not only methods returning `null` that encounter this issue. Spring Cache supports `java.util.Optional<T>`:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Optional<Book> find(String bookId) {
    return repository.findOptional(bookId);
}
```

*This is an illustrative snippet; `Book` and `repository` must be defined.*

In Spring Framework versions supporting `Optional` in the cache abstraction:

- `Optional.of(book)` is **unwrapped** to store the `book` value.
- `Optional.empty()` is treated as a **`null`** result at the cache layer.
- On a cache hit containing data, Spring reconstructs the method's expected return type, such as `Optional.of(book)` or `Optional.empty()`.

Therefore, do not assume “using `Optional` means non-existent results are never cached.” `Optional` clarifies the method's Java contract; it **does not automatically define the policy on whether empty results are cached**.

With `unless = "#result == null"`, Spring treats `#result` as **the business object after unwrapping `Optional`**, not the `Optional` wrapper itself. When the method returns `Optional.empty()`, this expression can veto the cache put.

If a method throws `NoSuchElementException`, `ResponseStatusException`, or a custom exception instead of returning `Optional.empty()`, that is a different scenario: **standard `@Cacheable` does not cache exceptions via the return-value storage mechanism**, because the method did not complete normally. An HTTP gateway or web-tier cache may cache HTTP 404 according to its own policy; do not equate that with Spring method caching.

## 4. Two policies: cache negatives or cache only positive results?

### 4.1. Policy A — Negative caching

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.find(id);  // may return null
}
```

If the provider allows `null`, the “not found” entry is remembered. The benefit is that non-existent IDs queried repeatedly will **not keep hitting the database**. However, when an ID is created later, the cache can continue reporting non-existence until the entry expires or is deleted/updated.

Better suited when:

- most negative keys genuinely stay non-existent for a long time;
- requests for non-existent IDs happen very frequently and database load must be reduced;
- there is a **short negative TTL**, invalidation on creation, or a reliable versioning mechanism;
- the business tolerates a controlled staleness window.

For example, a system checking an unallocated code may cache “does not exist” for a **short duration**. Never pick a long negative TTL merely because the positive TTL is long.

### 4.2. Policy B — Do not cache empty results

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

`unless` is a SpEL expression evaluated **after the method runs** on a miss. When the result is `null`, the expression evaluates to `true` and Spring **does not write an entry**. Subsequent calls continue querying the database; thus if the record is created, the very next read can see it immediately (assuming database consistency and no other cache underneath).

This policy fits when new data is frequently created right after a not-found lookup, or when detecting newly created existence quickly outweighs reducing miss load.

**Trade-off:** a non-existent ID queried 10,000 times can trigger up to 10,000 database loads (unless other protective layers exist). Skipping negative caching prevents stale negative entries, **not for free**.

### 4.3. Comparison

| Case | Cache `null` as well | `unless="#result == null"` |
| --- | --- | --- |
| First lookup for a missing ID | Queries DB, may store a null entry | Queries DB, does not store |
| Second lookup for the same missing ID | Can hit without querying DB | Misses and queries DB again |
| After the ID is created externally | May keep returning stale `null` | Next read has a chance to see the record |
| DB load from repeated missing IDs | Lower on cache hits | Higher under heavy request volume |
| Need for TTL/invalidation on negative data | **Critical** | No negative entry created by this operation |
| Guarantee new data is always visible immediately | No, unless invalidated | Still depends on data source, other caches, and races |
| Cache provider does not support `null` | Must configure an appropriate policy | Vetoes put-null, avoiding null-storage calls |

**Note on `condition`:** `@Cacheable(condition = "...")` is evaluated before the method, based on inputs; `#result` is not available to know whether data exists. `unless` is the right place to inspect **the return value**.

## 5. Data created later: ways to keep the cache up to date

All approaches require **the right cache name, right key, and right timing**.

### 5.1. Approach 1 — Do not cache negative values

```java
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result == null")
public Book findBook(String id) {
    return repository.find(id);
}
```

This is straightforward when seeing newly created data takes priority. However, it can still serve stale data for **already-cached positive entries** when a record is modified, so it does not replace a general invalidation mechanism.

### 5.2. Approach 2 — Evict the negative entry on successful creation

```java
@CacheEvict(cacheNames = "books", key = "#p0")
public Book createBook(String id, String title) {
    return repository.insert(id, title);
}
```

*Illustrative snippet, repository omitted.*

By default, `@CacheEvict` has `beforeInvocation=false`, meaning eviction runs **after the method completes normally**. If creation throws an exception, standard post-invocation eviction does not happen. Once the entry is removed, the next `@Cacheable` call misses, queries the new data, and can cache the positive result.

Do not blindly switch to `beforeInvocation=true` without careful thought: eviction would occur **before the creation method runs**, even if creation fails. In transactional systems, verify eviction timing relative to database commit; “method returns normally” does not always mean an outer transaction has committed.

### 5.3. Approach 3 — Write the new object directly with `@CachePut`

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book createBook(String id, String title) {
    return repository.insert(id, title);
}
```

When the method returns the new `Book` normally, `@CachePut` can overwrite the negative entry at key `book.id()` with the positive object. The next read on the same cache/key hits immediately. This reduces reload round-trips, yet requires a matching result type, consistent keys, and safe cache-update timing.

**Do not use `@CachePut` to delete an entry if returning `null` makes no sense:** putting `null` can preserve a negative entry instead. For successful creation, return the confirmed object and store it under the right key.

### 5.4. Approach 4 — Short negative TTL and resource bounds

When you cannot guarantee that every writer emits an invalidation event (because multiple external services or batch jobs create data), a short negative TTL acts as a guardrail so stale “does not exist” errors do not persist indefinitely.

For example, a business requirement: “Not-found book results may be stale for at most 10 seconds”; in that case, set a negative TTL of around 10 seconds if the provider supports positive/negative separation and matching consistency guarantees. **There is no `ttl` attribute on `@Cacheable` or `@CacheConfig`** to handle this automatically; configuration must live in the provider, a dedicated cache, or application logic.

TTL only sets an approximate time bound assuming the provider behaves as expected; it does not eliminate races, clock skew, replication lag, or strict read-your-writes requirements. Combine TTL with event-driven invalidation where needed.

## 6. Runnable example: cached null, subsequent creation causing staleness, and recovery

The following example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and `ConcurrentMapCacheManager`, with no Redis or external database required. A `ConcurrentHashMap` simulates the books table. Complex transactions are omitted for clear observation.

The demo illustrates three scenarios:

- **A: negative cache + data created outside the cache** → keeps returning stale `null` until evicted.
- **B: `unless` refuses to cache `null`** → re-queries the DB and sees the object after creation, at the cost of extra queries while absent.
- **C: negative cache + `@CachePut` on creation** → the `null` entry is replaced with the new object without waiting for a miss.

### 6.1. Structure

```text
negative-cache-demo/
├── pom.xml
└── src/main/java/example/negativecache/
    ├── NegativeCacheApplication.java
    ├── Book.java
    ├── BookStore.java
    └── BookService.java
```

### 6.2. File `pom.xml`

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

    <groupId>example</groupId>
    <artifactId>negative-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
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

### 6.3. File `src/main/java/example/negativecache/Book.java`

```java
package example.negativecache;

public record Book(String id, String title) {}
```

Java 17 records automatically generate a `toString()` formatted like `Book[id=A, title=Alpha]`, making stdout easy to match.

### 6.4. File `src/main/java/example/negativecache/BookStore.java`

```java
package example.negativecache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class BookStore {
    private final ConcurrentMap<String, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public Book find(String id) {
        Book book = books.get(id);
        int n = reads.incrementAndGet();
        System.out.println(
            "DB_READ #" + n + " " + id + " -> " +
            (book == null ? "ABSENT" : book.title())
        );
        return book;
    }

    public Book create(String id, String title) {
        Book created = new Book(id, title);
        Book previous = books.putIfAbsent(id, created);
        if (previous != null) {
            throw new IllegalStateException("Book exists: " + id);
        }
        System.out.println("DB_CREATE " + id + " -> " + title);
        return created;
    }
}
```

This is a simulated data store backed by `ConcurrentHashMap` in a single JVM. `create` uses `putIfAbsent` to avoid overwriting an existing book in the demo, though it is not a real database or transaction.

### 6.5. File `src/main/java/example/negativecache/BookService.java`

```java
package example.negativecache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookStore store;

    public BookService(BookStore store) {
        this.store = store;
    }

    // Can cache null: negative caching when the provider allows it.
    @Cacheable(cacheNames = "negative", key = "#p0")
    public Book cachedEvenWhenAbsent(String id) {
        return store.find(id);
    }

    // Only cache positive results, do not cache null.
    @Cacheable(
        cacheNames = "positiveOnly",
        key = "#p0",
        unless = "#result == null"
    )
    public Book skipAbsent(String id) {
        return store.find(id);
    }

    // Remove either negative or positive entry for the same key after the method returns.
    @CacheEvict(cacheNames = "negative", key = "#p0")
    public void invalidateNegative(String id) {
        System.out.println("CACHE_EVICT " + id);
    }

    // Create the book and put the positive result into the same cache/key as the read method.
    @CachePut(cacheNames = "negative", key = "#result.id()")
    public Book createAndRefresh(String id, String title) {
        return store.create(id, title);
    }
}
```

All cache operations sit on public methods of a Spring-managed bean. `CommandLineRunner` invokes through the injected bean (not via `this.`), giving the cache proxy a chance to intercept.

### 6.6. File `src/main/java/example/negativecache/NegativeCacheApplication.java`

```java
package example.negativecache;

import java.util.Objects;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class NegativeCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(NegativeCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("negative", "positiveOnly");
        // Make configuration explicit so the negative caching demo is consistent.
        manager.setAllowNullValues(true);
        return manager;
    }

    @Bean
    CommandLineRunner demo(
        BookStore store, BookService service, CacheManager manager
    ) {
        return args -> {
            Cache negative = Objects.requireNonNull(
                manager.getCache("negative")
            );
            Cache positiveOnly = Objects.requireNonNull(
                manager.getCache("positiveOnly")
            );

            // A: cache null, create in store without automatic invalidation.
            System.out.println("A1 => " + service.cachedEvenWhenAbsent("A"));
            System.out.println("A2 => " + service.cachedEvenWhenAbsent("A"));
            Cache.ValueWrapper aEntry = negative.get("A");
            System.out.println(
                "A_CACHED_NULL => " +
                (aEntry != null && aEntry.get() == null)
            );

            store.create("A", "Alpha"); // simulate a writer outside the cache
            System.out.println(
                "A_STALE => " + service.cachedEvenWhenAbsent("A")
            );
            service.invalidateNegative("A");
            System.out.println(
                "A_REFRESHED => " + service.cachedEvenWhenAbsent("A")
            );

            // B: do not store null; after create, it will re-query the store.
            System.out.println("B1 => " + service.skipAbsent("B"));
            System.out.println("B2 => " + service.skipAbsent("B"));
            System.out.println(
                "B_CACHE_PRESENT => " + (positiveOnly.get("B") != null)
            );
            store.create("B", "Bravo");
            System.out.println("B3 => " + service.skipAbsent("B"));
            System.out.println("B4 => " + service.skipAbsent("B"));

            // C: negative entry is replaced via @CachePut when creating the book.
            System.out.println("C0 => " + service.cachedEvenWhenAbsent("C"));
            System.out.println(
                "C_PUT => " + service.createAndRefresh("C", "Charlie")
            );
            System.out.println("C1 => " + service.cachedEvenWhenAbsent("C"));
        };
    }
}
```

### 6.7. Running the program

In the `negative-cache-demo` directory, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

The demo application prints the following lines in **this exact order** (Spring Boot also prints startup logs, omitted here):

```text
DB_READ #1 A -> ABSENT
A1 => null
A2 => null
A_CACHED_NULL => true
DB_CREATE A -> Alpha
A_STALE => null
CACHE_EVICT A
DB_READ #2 A -> Alpha
A_REFRESHED => Book[id=A, title=Alpha]
DB_READ #3 B -> ABSENT
B1 => null
DB_READ #4 B -> ABSENT
B2 => null
B_CACHE_PRESENT => false
DB_CREATE B -> Bravo
DB_READ #5 B -> Bravo
B3 => Book[id=B, title=Bravo]
B4 => Book[id=B, title=Bravo]
DB_READ #6 C -> ABSENT
C0 => null
DB_CREATE C -> Charlie
C_PUT => Book[id=C, title=Charlie]
C1 => Book[id=C, title=Charlie]
```

### 6.8. Interpreting each group of results

**Group A — Caching `null` creates a stale negative result:**

1. `A1`: the `negative` cache does not yet have key `A`. Spring invokes `BookStore.find`, prints `DB_READ #1 A -> ABSENT`, and the method returns `null`. Because the manager allows null values, it stores an entry representing `null`.
2. `A2`: cache hit on `null`; the method does not run. No `DB_READ #2` appears at this point.
3. `A_CACHED_NULL => true`: `Cache.get("A")` returns a `ValueWrapper` whose `get() == null`. This is a **negative hit**, not a miss.
4. `store.create("A", "Alpha")`: the map now contains book A, yet no cache annotation or event automatically updates the cache entry.
5. `A_STALE => null`: the cache still holds the negative entry. Even though the store has Alpha, Spring still returns the stale `null`.
6. `invalidateNegative("A")`: Spring executes `@CacheEvict` to delete key A after the method finishes normally; the next read misses, prints `DB_READ #2 A -> Alpha`, and the cache receives the new object.

**Group B — `unless` does not cache `null`:**

1. `B1`: on the first call, book B is absent, queries the simulated database (#3), returns `null`, and `unless` evaluates to `true`, so nothing is stored.
2. `B2`: with no negative entry, it queries again (#4), still gets `null`, and does not cache.
3. `B_CACHE_PRESENT => false`: there is no mapping for key B in the `positiveOnly` cache.
4. `store.create("B", "Bravo")`: creates book B.
5. `B3`: the next call queries (#5) and finds Bravo; since the result is non-null, it is cached.
6. `B4`: the same key hits, with no additional `DB_READ`.

**Group C — `@CachePut` overwrites the negative entry:**

1. `C0`: query (#6) does not find C; `negative["C"]` holds the negative value.
2. `createAndRefresh("C", "Charlie")`: the creation method returns `Book`; `@CachePut` extracts `#result.id()` as `"C"` and writes the object into **the same `negative` cache, under the same key C**.
3. `C1`: the subsequent read hits the new object without calling `BookStore.find`, so there is no `DB_READ #7`.

**Why the output is deterministic:** the code runs sequentially inside `CommandLineRunner`; the two caches are separate local caches where each new key starts absent; the cache manager is explicitly configured with `allowNullValues=true`; there are no other threads or automatic TTLs; and every call to `BookService` from `CommandLineRunner` goes through the Spring-managed proxy. Java record output follows `Book[id=..., title=...]`.

This is a behavioral demo, not a production system: `BookStore` is an in-memory map without transactions or multiple nodes. Code, annotations, keys, and stdout ordering were reviewed manually; to confirm at runtime, run Maven in an environment with a JDK and dependencies.

## 7. If an API returns 404, did it cache the error?

Suppose a controller has:

```java
@GetMapping("/books/{id}")
public BookDto read(@PathVariable String id) {
    Book book = bookService.find(id);
    if (book == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    return BookDto.from(book);
}
```

*The snippet above illustrates the web layer; corresponding imports and `BookDto`/service types are required.*

If `bookService.find(id)` **cached `null`**, the controller may throw `ResponseStatusException` every time without the service re-querying the database. From the outside, users observe repeated HTTP 404s and may think Spring “cached the 404 exception.” In reality, **the method cache may simply be holding a `null` result**, while the controller constructs a fresh 404 response from that `null`.

Conversely, if the `@Cacheable` method itself throws `ResponseStatusException` before returning a value, `@Cacheable` by default **does not store exceptions as normal return values**. HTTP caches in CDNs, reverse proxies, browsers, or API gateways have their own 404 caching rules; inspect the right layer.

**How to diagnose:** log entries into the data-reading method, inspect the cache entry with `Cache.get`, distinguish a cached-null hit from a cache miss, and check where the status code is produced.

## 8. `@Cacheable(unless="#result == null")` and `Optional<Book>`

When a method returns `Optional<Book>`:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Book> findOptional(String id) {
    return repository.findOptional(id);
}
```

*Illustrative snippet; `repository` is not defined.*

In caching SpEL, Spring unwraps `Optional`: `#result` refers to `Book` when present, or `null` when empty. Therefore, `unless="#result == null"` is the proper expression for “do not store when absent,” even when the method API uses `Optional`.

Do not naively write `unless="#result.isEmpty()"` assuming `#result` is an `Optional`. With supported `Optional` wrappers, `#result` is **the inner value**, not the wrapper; calling `isEmpty()` like that can fail type checks or dereference `null`.

When using a custom `Result` type containing a `NOT_FOUND` status, Spring does not automatically know it represents a negative outcome:

```java
record LookupResult(boolean found, Book book) {}

@Cacheable(cacheNames = "books", key = "#p0",
           unless = "!#result.found()")
public LookupResult findResult(String id) {
    // Return a LookupResult matching the actual data.
    return new LookupResult(false, null);
}
```

*Illustrative snippet, not advice to return a hardcoded result in a real application.*

With this kind of result, `unless` must explicitly encode the rule “do not store when `found=false`.” That is a **business contract defined by you**, not a Spring default.

## 9. Negative TTL, cache stampede, and performance cost

### 9.1. When should “does not exist” be cached?

Negative caching is helpful when the system handles many queries for keys that frequently do not exist:

- Bots repeatedly querying unallocated product codes.
- Services checking non-existent IDs at high frequency.
- Lookups to a high-latency external service that frequently returns not-found.

If every miss hits the database, load can spike sharply. A short-lived negative entry reduces load at the cost of freshness.

Define an **acceptable staleness budget** per business requirements. If newly created data must be visible immediately in the same session, a short negative TTL alone may still be insufficient; you need invalidation/refresh or a direct-to-source read path after writes.

### 9.2. Positive and negative TTLs should be evaluated separately

An existing book may be relatively stable and cached longer; yet “no book exists” can change mere seconds after creation. Therefore, many systems choose a **shorter negative TTL than positive TTL**.

Implementation depends on the cache provider:

- Separate `booksPositive` and `booksNegative` caches with different TTL configurations.
- Use a stateful wrapper and storage logic that classifies results if the backend supports it.
- Use a cache provider supporting per-entry expiry policies, if available.
- Combine event-based invalidation with a bounded TTL.

There is no standard `@Cacheable(ttl=...)` annotation attribute; lifetimes are configured via the provider/cache manager or a custom abstraction.

### 9.3. The “thousands of concurrent misses” problem

When skipping `null` caching with `unless`, thousands of concurrent requests asking for a non-existent ID can all hit the database. Possible mitigations include:

- rate limiting, batching, or request coalescing;
- short-TTL negative caching with proper invalidation rules;
- distributed locks/single-flight at the appropriate layer when needed;
- another caching layer with stampede protection.

Spring supports `@Cacheable(sync=true)` as a backend-dependent hint to synchronize loads for the same key, yet it has an important limitation: **combining `sync=true` with `unless` in the same `@Cacheable` is not supported**, nor multiple caches or combining other cache operations. Never present `@Cacheable(sync=true, unless="#result == null")` as a valid configuration.

Even when using `sync=true`, do not assume it solves all concurrency across multiple nodes: synchronization scope and failure behavior depend on the provider.

## 10. Data creation, transactions, and negative entry consistency

“Evict upon successful creation” sounds simple, yet database commit timing must be considered.

For example:

```java
@Transactional
@CacheEvict(cacheNames = "books", key = "#result.id()")
public Book createBook(CreateBookCommand command) {
    return repository.insert(command);
}
```

*Illustrative snippet; requires an appropriate transaction manager and repository.*

`@CacheEvict(beforeInvocation=false)` runs after the method completes successfully **from the cache advice's perspective**, yet if transaction advice wraps outside cache advice, an eviction can happen **before the database commits**. A concurrent read can miss, query stale DB state that does not yet see the new record, and **re-cache `null`**; then the transaction commits, leaving the negative entry alive.

This is a particularly dangerous race:

```text
Writer creates B42 in a transaction (not yet committed)
  -> evicts cache["B42"]
Reader immediately:
  -> cache miss
  -> database still cannot see B42
  -> cache stores "does not exist"
Writer commits B42
  -> cache["B42"] remains "does not exist" without further invalidation
```

Ways to reduce the risk:

1. Ensure cache invalidation/put operations are coordinated **after commit** when consistency requires it.
2. Consider `TransactionAwareCacheManagerProxy` or a cache decorator/transaction synchronization appropriate for your backend and transaction scope.
3. In distributed systems, use reliable post-commit events (transactional outbox, idempotent consumers) to invalidate/refresh all relevant nodes.
4. Keep a sufficiently short negative TTL to bound the blast radius of lost events.
5. Test under real concurrency and rollback conditions, not solely with sequential calls.

**Do not assume cache and database share one atomic transaction:** `@Transactional` does not turn Redis and the database into a single commit unit. Nor is `@CachePut` a transactional write-through in every environment.

## 11. The race between miss and create even with eviction

Even when creation evicts **after commit**, a race still exists:

```text
Reader R1: starts find("B42"), cache miss
Reader R1: queries DB -> does not see B42 yet, prepares to return null

Writer W: creates B42, commits successfully
Writer W: evicts key B42

Reader R1: completes @Cacheable and writes null into cache AFTER eviction
Reader R2: sees the stale negative entry, returns "not found"
```

Thus, a single eviction is not a strong guarantee under every concurrent schedule. To achieve higher consistency, design deliberately:

- Read/write under a shared lock or an appropriate serialization mechanism.
- Versioned keys or generation tokens so stale miss results cannot overwrite a newer cache generation.
- Very short negative TTLs to limit impact when races occur.
- Re-invalidation or refresh mechanisms when create events are detected, considering event ordering and retries.
- Accounting for writers that bypass the application using the annotations.

If critical data requires strict **read-your-writes**, you may need to read directly from the source after creation or use a different read/write invariant rather than hoping the cache becomes consistent instantaneously.

## 12. Cache keys, tenants, and context-dependent data

Consider this method:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String bookId, String tenantId) {
    return repository.find(tenantId, bookId);
}
```

*Illustrative snippet; repository omitted.*

If the cache key is only `bookId` while data existence varies by `tenantId`, one tenant lacking the book can cache `null` under key `B42`, causing another tenant **that already has the book** to also receive `null`. This is a form of **cross-tenant cache poisoning** leading to wrong results and even security risks.

The key must include **every dimension affecting the output**, for example:

```java
@Cacheable(cacheNames = "books", key = "#p1 + ':' + #p0")
public Book findBook(String bookId, String tenantId) {
    return repository.find(tenantId, bookId);
}
```

In this example, `#p1` is the tenant and `#p0` is `bookId`. When creating a record, `@CacheEvict` or `@CachePut` must **use the exact same key construction and the same cache name/manager**. You can choose a composite key object or `KeyGenerator` instead of string concatenation if input formatting is complex and prone to collisions.

Cache keys do not replace **authorization checks**. Never trust a client-supplied tenant ID without verifying it against the authenticated security context.

## 13. Symptoms and diagnostics

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Record exists in DB, API still returns 404 | Method caches `null`/`Optional.empty` | Check `Cache.get(key)`, method invocation counts, cache name/key |
| Takes several seconds for a new record to appear | Negative TTL | Inspect expiration, provider metrics, creation timestamps |
| Created via API A appears immediately; via batch B appears slowly | API A has `@CacheEvict`/`@CachePut`, batch B emits no invalidation | Trace all writers and producer events |
| Cache evicted yet `null` reappears | Race: reader missed before commit and wrote `null` after evict | Check transaction timing and concurrent traces |
| `@CacheEvict` annotation present yet does not run | Self-invocation, wrong bean/proxy, or mismatched key | Log method calls, inspect proxy, cache name, and key |
| Not caching `null`, yet database load spikes | `unless` makes every negative result a miss | Measure negative-lookup QPS and DB read counts |
| One tenant gets “not found” even though another tenant has it | Key does not distinguish tenants | Compare cache keys across tenants and auth contexts |
| Cache `get` has `wrapper != null` yet `get()==null` | A negative entry is genuinely stored | Distinguish wrapper hit from miss; check `allowNullValues` |
| Method throws an exception and next request still reloads | Exceptions are not cached as return values | Check exception source and any outer HTTP/gateway caches |

The practical approach is to **measure at both ends**: logs/metrics when the method actually queries the database, and cache hit/miss state at the provider. Looking solely at HTTP responses is not enough to distinguish a negative cache hit from a fresh query returning absent.

### 13.1. Minimum tests to have

1. **First missing lookup:** ID absent, read returns `null`/empty or 404.
2. **Repeated missing lookup:** verify whether the method runs again or is skipped by the cache per policy.
3. **Create after missing:** create the same ID, read again; result must meet freshness requirements.
4. **Failed creation:** do not insert a bogus object into the cache; verify eviction does not happen unintentionally.
5. **Create via external writer:** verify events, TTL, or invalidation.
6. **Concurrent miss/create:** force interleaving between database reads and cache puts/evictions to catch races.
7. **Multi-tenant:** the same ID in another tenant does not share negative entries.
8. **Provider null support:** test real `allowNullValues`/serializer/null sentinel behavior in the production-like environment.
9. **Multi-node:** verify invalidation/TTL across all relevant nodes or cache partitions.
10. **Transaction rollback:** confirm data and cache recover cleanly after rollback or commit failure.

Never test only “first call returns null”: negative caching bugs usually **surface only on calls after data has been created**.

## 14. Common mistakes

1. **Confusing `null` with a cache miss.** If the provider stores `null` via a sentinel, `Cache.get(key)` can return a wrapper even when the inner value is `null`.
2. **Assuming `Optional.empty()` is never cached.** Spring Cache can unwrap `Optional` to `null` and store it if allowed.
3. **Using `condition="#result == null"` to avoid negative caching.** `condition` is evaluated before the method; to inspect the result, use `unless`.
4. **Assuming `unless=true` throws or returns an error.** It only declines storing the new result; the caller still receives the current call's `null`/empty.
5. **Disabling null support without designing how `null`-returning methods are handled.** Depending on the provider, cache puts can fail; `unless` usually expresses intent more clearly.
6. **Creating a new record while evicting a different cache namespace.** Key, cache name, and cache manager/resolver must match between reads and writes/evictions.
7. **Evicting too early, before database commit.** Readers can miss, read uncommitted database state, and cache `null` again.
8. **Believing post-commit eviction eliminates all races.** A reader that started before creation can write `null` after eviction; guard against races if strong consistency is required.
9. **Using a long positive TTL for negative results too.** Negative entries can keep newly created data “invisible” for too long.
10. **Replacing negative results with a fake error object in the same cache as valid objects.** Risks type/logic bugs and blurs business states; use an explicit contract.
11. **Placing `@CacheEvict` on a private method or calling from the same bean and expecting proxy interception.** In default proxy mode, self-invocation bypasses advice.
12. **Combining `sync=true` and `unless` in `@Cacheable`.** Spring does not support that combination.
13. **Assuming HTTP 404 exceptions are cached by Spring method caching by default.** It may be a cached `null` in the service or an HTTP response cache at another layer.
14. **Using keys that do not distinguish tenant/user/locale.** One group's negative result can cause wrong answers for another group.
15. **Assuming caching handles authorization or data validation.** Permission checks and business rules must run at the appropriate point on every request.

## 15. Self-check questions

**Question 1.** `@Cacheable` returns `null`, and `ConcurrentMapCacheManager` allows nulls. Will the next call with the same key definitely run the database query method?

**Answer:** No. The cache may have stored a negative entry representing `null`; the next call hits and skips the method body.

**Question 2.** `Cache.get("B42") != null`, yet `Cache.get("B42").get() == null`. What can you conclude?

**Answer:** The cache holds an entry for `B42`, and the user value is `null`. This is a “null hit,” distinct from `Cache.get("B42") == null` indicating a miss.

**Question 3.** Record `B42` is created after a lookup already cached `null`. Does `@Cacheable` automatically detect that the database changed?

**Answer:** No. You need invalidation, `@CachePut`, TTL/expiry, versioned keys, or another appropriate policy.

**Question 4.** `@Cacheable(unless="#result == null")` returns `null`. What does the caller receive? Is `null` stored in the cache?

**Answer:** The caller still receives `null` from that invocation; Spring declines to put the `null` result due to the `unless` condition.

**Question 5.** For a method returning `Optional.empty()`, does `unless="#result == null"` take effect?

**Answer:** Yes, for Spring Cache's supported `Optional` wrapper, `#result` refers to the unwrapped inner value; empty is treated as `null` when evaluating the condition.

**Question 6.** What if creation has committed, yet an older in-flight reader that missed writes `null` after eviction?

**Answer:** The cache can become re-poisoned with a negative result. A single eviction does not guarantee strong consistency across every interleaving; race-mitigation design or bounded negative lifetimes are needed.

**Question 7.** Can `@Cacheable(sync=true, unless="#result == null")` be used for both single-flight and vetoing `null`?

**Answer:** No. `sync=true` has the restriction that `unless` cannot be used. Choose another concurrency or negative-caching technique.

**Question 8.** `BookService.find(id, tenantId)` uses a key containing only `id`. Can a “not found” result affect another tenant?

**Answer:** Yes. If two tenants share the same ID with different underlying data, one tenant's negative entry can be served to the other tenant. Keys or cache scopes must isolate tenants and preserve proper authorization checks.

## 16. Quick takeaways

- **Negative caching** is caching a “does not exist” outcome, commonly represented by `null`, `Optional.empty`, or a business sentinel.
- **Cache miss ≠ cache null hit.** Distinguish `Cache.get(key) == null` from an existing wrapper whose `get() == null`.
- **Data created later does not automatically clear negative entries.** Stale 404s can appear even after the record exists in the database.
- **`unless="#result == null"`** avoids storing empty results, in exchange for higher DB load when keys remain non-existent.
- **`@CacheEvict`** removes entries; **`@CachePut`** writes new data. Both must use the exact cache/key and timing.
- **Negative TTLs and invalidation** should derive from freshness requirements, not be mechanically copied from positive TTLs.
- **Concurrency and transactions** can cause `null` to be written back after eviction; test races when consistent read-after-create is required.
- **Methods throwing exceptions differ from methods returning `null`.** Spring Cache does not automatically cache exceptions as normal return values.

## Official references

- Spring Framework Reference — Declarative Annotation-based Caching, `@Cacheable`, `unless`, `Optional`, and `@CacheEvict`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@Cacheable`, `sync` and `unless` constraints: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc — `Cache` and `Cache.ValueWrapper`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework Javadoc — `ConcurrentMapCacheManager` and `setAllowNullValues`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Proxying Mechanisms/self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
