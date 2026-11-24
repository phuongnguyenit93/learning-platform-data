# @CacheEvict: Evicting related data copies across multiple keys

## Lesson objectives

When a record changes, an application usually does not cache that data under just **one key**. The same product can appear in a detail cache, a summary, category listings, search results, or statistics. If only one entry is removed, the remaining copies can continue returning **stale data**.

This lesson explains how to use **`@CacheEvict`** in Spring Framework to invalidate related copies at **multiple keys**, within **one or more cache names**, and how to choose a solution when the key set is not known in advance.

After this lesson, you will be able to:

- Distinguish between **single-key**, **multi-key**, and **full cache region** eviction.
- Use `@Caching(evict = {...})` to declare multiple `@CacheEvict` operations with different key expressions.
- Ensure eviction keys **match exactly** the keys used by `@Cacheable`.
- Identify dependencies such as *detail → summary → category list* and pick the appropriate eviction scope.
- Handle category changes, dynamic key sets, transaction rollbacks, concurrent contention, and multi-instance systems.
- Run a Java 17 + Spring Cache example to verify multiple entries are evicted while unrelated entries remain intact.

> **Principle:** To avoid stale data, you must find all cache entries **that depend on the data just changed**. A single key-based `@CacheEvict` only deletes the resolved key in the specified cache name; Spring does not automatically hunt down logical copies living under other keys.

## 1. Problem: One product, multiple copies in the cache

Suppose an e-commerce system has product ID = 42, old name "Book A", category "books". Different read methods store the following results:

| Cache name | Key | Cached value | Depends on product 42? |
| --- | --- | --- | --- |
| `productViews` | `detail:42` | Detail info containing "Book A" | Yes |
| `productViews` | `summary:42` | Summary containing "Book A" | Yes |
| `categoryLists` | `category:books` | List containing "Book A" | Yes |
| `categoryLists` | `category:games` | Game product list | No |
| `productViews` | `detail:77` | Product 77 details | No |

When renaming product 42 to "Book B":

- Evicting only `productViews[detail:42]` is **not enough**. A call to view the summary can still see "Book A".
- If only the detail and summary keys are evicted, the `category:books` list can still contain "Book A".
- Clearing `category:games` or all other products causes unnecessary cache misses and extra load.

The exact eviction scope in this example is **the three affected entries**: `detail:42`, `summary:42`, `category:books`.

### Data dependency model

~~~text
Record Product(id=42, category=books)
          |
          +----> productViews[detail:42]
          |
          +----> productViews[summary:42]
          |
          +----> categoryLists[category:books]

Record Product(id=77, category=games)
          |
          +----> categoryLists[category:games]
                  (unrelated to renaming Product 42)
~~~

An update operation needs to know this **dependency graph**; cache annotations do not infer it automatically from the database or queries.

## 2. What does a basic @CacheEvict remove?

A simple example:

~~~java
@CacheEvict(cacheNames = "productViews", key = "'detail:' + #p0")
public void renameProduct(long productId, String newName) {
    repository.rename(productId, newName);
}
~~~

This is an illustrative snippet requiring `repository` to exist in a real service.

With `renameProduct(42, "Book B")`, when the method completes normally, Spring can request removing the entry corresponding to:

~~~text
cache name = productViews
key        = detail:42
~~~

**It does not automatically remove** `productViews[summary:42]` or `categoryLists[category:books]`.

### Cache region name and key are two separate components

`productViews[detail:42]` and `categoryLists[detail:42]` are two distinct entries because their cache names differ. Conversely, within the same `productViews`, `detail:42` and `summary:42` are two distinct keys.

Therefore, to clean up multiple copies, you must specify the exact **set of `(cache name, key)` pairs**. Knowing only the source object's ID is not sufficient.

## 3. Evicting multiple keys with @Caching(evict = {...})

Spring provides `@Caching` to group multiple cache operations on a single method. This is a convenient declarative approach when **the keys to evict are known and few in number**.

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "productViews",
        key = "'detail:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'summary:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #p2"
    )
})
public void renameProduct(
        long productId,
        String newName,
        String category) {
    repository.rename(productId, newName, category);
}
~~~

This is illustrative code for a service with a repository and the constraint that **the passed-in `category` reflects the product's current category**. If the category is wrong or has changed, do not assume the `categoryLists` eviction was sufficient.

All three SpEL expressions are evaluated in the context of **`renameProduct`'s parameters**, not the read methods' parameters:

- `#p0` is the first parameter `productId`: produces `detail:42` and `summary:42`.
- `#p2` is the third parameter `category`: produces `category:books`.
- `#p1` is `newName`, omitted from keys because the caches identify by product/category rather than name.

Using `#p0`, `#p1`, `#p2` does not depend on whether Java compilation retains parameter names. In real projects, `#productId` and `#category` can be used when parameter names are available.

**Important:** `@Caching` only **groups multiple operations**; it does not create an atomic transaction across keys or caches. If one evict operation fails, the Spring Cache abstraction does not guarantee all other operations roll back together.

### One annotation can specify multiple cache names when the key is identical

If two cache regions use **the exact same key**, you can write:

~~~java
@CacheEvict(
    cacheNames = {"productById", "productSnapshot"},
    key = "#p0"
)
public void update(long productId) {
    repository.update(productId);
}
~~~

However, with `detail:42`, `summary:42`, and `category:books`, the keys differ. Use multiple `@CacheEvict` entries via `@Caching` (or choose an appropriate programmatic approach); **do not** expect a single `key` to expand into multiple keys automatically.

## 4. Runnable Java 17 example: evicting three copies, keeping an unrelated copy

The following example is a console program runnable with Java 17+, Maven, and **Spring Framework 6.2.10**. It uses `ConcurrentMapCacheManager` to inspect entries in memory. Three cache entries related to product ID 42 are evicted after renaming, while the "games" category list stays intact.

### 4.1. Project structure

~~~text
multi-key-eviction/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultiKeyEvictionDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>multi-key-eviction</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 4.3. src/main/java/demo/MultiKeyEvictionDemo.java

~~~java
package demo;

import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MultiKeyEvictionDemo {

    // Immutable value object; used as fake database row.
    public record Product(long id, String category, String name) {}

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "productViews", "categoryLists");
        }

        @Bean
        public ProductRepository productRepository() {
            return new ProductRepository();
        }

        @Bean
        public ProductService productService(ProductRepository repository) {
            return new ProductService(repository);
        }
    }

    public static class ProductRepository {
        private final Map<Long, Product> products =
                new ConcurrentHashMap<>();

        public ProductRepository() {
            products.put(42L, new Product(42L, "books", "Book A"));
            products.put(77L, new Product(77L, "games", "Game A"));
        }

        public Product get(long id) {
            return Objects.requireNonNull(
                products.get(id), "Unknown product");
        }

        public String namesByCategory(String category) {
            return products.values().stream()
                .filter(p -> p.category().equals(category))
                .sorted(Comparator.comparingLong(Product::id))
                .map(Product::name)
                .collect(Collectors.joining(", "));
        }

        public void rename(
                long id, String newName, String expectedCategory) {
            Product old = get(id);
            if (!old.category().equals(expectedCategory)) {
                throw new IllegalArgumentException(
                    "Category does not match");
            }
            products.put(id, new Product(
                id, old.category(), newName));
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger detailReads = new AtomicInteger();
        private final AtomicInteger summaryReads = new AtomicInteger();
        private final AtomicInteger listReads = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "productViews",
            key = "'detail:' + #p0"
        )
        public String detail(long id) {
            detailReads.incrementAndGet();
            Product p = repository.get(id);
            return "Detail " + p.id() + ": " + p.name();
        }

        @Cacheable(
            cacheNames = "productViews",
            key = "'summary:' + #p0"
        )
        public String summary(long id) {
            summaryReads.incrementAndGet();
            Product p = repository.get(id);
            return "Summary " + p.id() + ": " + p.name();
        }

        @Cacheable(
            cacheNames = "categoryLists",
            key = "'category:' + #p0"
        )
        public String categoryList(String category) {
            listReads.incrementAndGet();
            return "Category " + category + ": " +
                    repository.namesByCategory(category);
        }

        @Caching(evict = {
            @CacheEvict(
                cacheNames = "productViews",
                key = "'detail:' + #p0"
            ),
            @CacheEvict(
                cacheNames = "productViews",
                key = "'summary:' + #p0"
            ),
            @CacheEvict(
                cacheNames = "categoryLists",
                key = "'category:' + #p2"
            )
        })
        public void rename(
                long id, String newName, String category) {
            repository.rename(id, newName, category);
        }

        public String counters() {
            return "detail=" + detailReads.get()
                + ", summary=" + summaryReads.get()
                + ", list=" + listReads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service =
                context.getBean(ProductService.class);
            CacheManager cacheManager =
                context.getBean(CacheManager.class);

            Cache views = Objects.requireNonNull(
                cacheManager.getCache("productViews"));
            Cache lists = Objects.requireNonNull(
                cacheManager.getCache("categoryLists"));

            System.out.println(service.detail(42L));
            System.out.println(service.summary(42L));
            System.out.println(service.categoryList("books"));
            System.out.println(service.categoryList("games"));
            System.out.println("Counts before hit: " +
                service.counters());

            service.detail(42L);
            service.summary(42L);
            service.categoryList("books");
            service.categoryList("games");
            System.out.println("Counts after hit: " +
                service.counters());

            service.rename(42L, "Book B", "books");

            System.out.println("Detail evicted: " +
                (views.get("detail:42") == null));
            System.out.println("Summary evicted: " +
                (views.get("summary:42") == null));
            System.out.println("Books list evicted: " +
                (lists.get("category:books") == null));
            System.out.println("Games list still cached: " +
                (lists.get("category:games") != null));

            System.out.println(service.detail(42L));
            System.out.println(service.summary(42L));
            System.out.println(service.categoryList("books"));
            System.out.println(service.categoryList("games"));
            System.out.println("Counts after reread: " +
                service.counters());
        }
    }
}
~~~

### 4.4. Running the program

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MultiKeyEvictionDemo
~~~

Lines printed by the program (excluding Maven logs):

~~~text
Detail 42: Book A
Summary 42: Book A
Category books: Book A
Category games: Game A
Counts before hit: detail=1, summary=1, list=2
Counts after hit: detail=1, summary=1, list=2
Detail evicted: true
Summary evicted: true
Books list evicted: true
Games list still cached: true
Detail 42: Book B
Summary 42: Book B
Category books: Book B
Category games: Game A
Counts after reread: detail=2, summary=2, list=3
~~~

### 4.5. Analyzing the results

1. The first four calls populate `detail:42`, `summary:42`, `category:books`, and `category:games` in turn. The counters are `detail=1, summary=1, list=2`.
2. Calling all four methods again with the same keys produces **cache hits**. Counters do not rise, proving Spring skipped the `@Cacheable` method bodies.
3. `rename` actually changes the source from "Book A" to "Book B", and then `@Caching(evict = {...})` evicts the three dependent entries.
4. Checking directly via `CacheManager` shows the three entries were removed. `category:games` still exists because the games category is unrelated.
5. Upon re-reading, the three removed entries cause misses and reload the new data "Book B". The games list still hits; the `list` counter only increases from 2 to 3.

**Why use `@EnableCaching`?** This configuration enables Spring's cache advice. `detail`, `summary`, `categoryList`, and `rename` are all called through the `ProductService` retrieved from `ApplicationContext`, so the proxy has a chance to process the annotations.

**Example limitations:** `ConcurrentMapCacheManager` is merely an in-process RAM cache. This is an example to observe behavior; there are no database transactions, Redis, TTLs, distributed locks, or multi-instance coordination mechanisms. Output lines are derived directly from the program's logic and assume dependencies function normally.

## 5. When to use a single @CacheEvict, @Caching, or allEntries?

| Need | Approach | Scope |
| --- | --- | --- |
| One known key in one cache | `@CacheEvict(cacheNames = "...", key = "...")` | One entry |
| Same key must be evicted across multiple caches | One `@CacheEvict` with multiple `cacheNames` | One key per listed cache |
| Multiple distinct keys, finite count known from params/result | `@Caching(evict = { ... })` | Multiple known entries |
| All entries in a cache region become invalid | `@CacheEvict(allEntries = true)` | Entire cache region |
| Dynamic key set, count varies each time | `CacheManager`/`Cache.evict(key)` with a resolved key list, or redesign cache model | Per runtime key set |
| Dependencies of many queries hard to determine | Separate caches by query type, versioning, TTL, or clear appropriate region | Decided by application policy |

### 5.1. allEntries = true is not a prefix wildcard

Example:

~~~java
@CacheEvict(cacheNames = "categoryLists", allEntries = true)
public void bulkUpdateProducts() {
    repository.bulkUpdate();
}
~~~

This **illustrative code** clears all entries in `categoryLists` after `bulkUpdateProducts` succeeds, not just `category:books`. This is useful when a change affects too many lists and exact keys cannot be determined. However, it causes many cache misses and increases reload traffic.

Spring does not by default support an expression like `key = "'category:*'"` to remove every key starting with `category:`. That is only **a single literal key** when produced by a SpEL expression, not pattern matching.

When using `allEntries = true`, Spring ignores `key` because it is clearing the entire region; do not write `key` alongside it expecting to narrow the scope. Consider separating regions by dependency scope so `allEntries` does not affect unrelated data.

### 5.2. Comparing precision and cost

- **Exact multi-key eviction:** minimal impact on hit ratio, but requires a reliable dependency model and a complete key list.
- **Full-region clear:** simpler when impact is broad, but can cause cache stampedes or sudden load spikes.
- **Short TTL:** bounds staleness duration, yet does not replace invalidation when business logic requires seeing new data immediately.
- **Key versioning:** useful for groups of results that can switch versions together, though version keys must be managed to prevent unbounded memory growth and handle expired old entries.

## 6. What if a product moves from an old category to a new category?

Renaming differs from **changing category**. When product 42 moves from "books" to "games", you must refresh:

- Detail and summary of product 42.
- The **old books** list (because the product is no longer there).
- The **new games** list (because the product was just added).

If only `category:games` is evicted, the books list may still contain product 42. If only `category:books` is evicted, the games list may lack product 42.

When the old category is only known after reading/updating data, you can return a result describing the change and use `#result` in `@CacheEvict` **post-invocation**. The snippet below is **illustrative code**, assuming the repository and update method are already defined; it is not part of the standalone program in section 4:

~~~java
public record MoveResult(
    long productId, String oldCategory, String newCategory) {}

@Caching(evict = {
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #result.oldCategory()"
    ),
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #result.newCategory()"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'detail:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'summary:' + #p0"
    )
})
public MoveResult moveProduct(long productId, String newCategory) {
    return repository.moveAndDescribe(productId, newCategory);
}
~~~

With `@CacheEvict`'s default `beforeInvocation = false`, Spring allows `#result` when computing keys after the method completes successfully. In the code above, `#result.oldCategory()` and `#result.newCategory()` are Java record accessor methods.

**Do not use `#result` when `beforeInvocation = true`**, because before the method runs there is no result yet. At the same time, establish clear conventions for `MoveResult` being null, failed operations, or when the old and new categories are identical.

If an update affects many categories, filters, or paginated lists, the return value may not list every affected cache key. In that case, adjust the invalidation model: a dependent-key index, sensible full-region clearing, cache region splitting, or version management.

## 7. What if the number of related keys is unknown in advance?

`@Caching(evict = {...})` is great for **a small, statically declarable list**. But suppose product 42 appears across 1,000 combinations of `search:q=...`, `page:...`, `sort:...`, and `filter:...`. You cannot write a `@CacheEvict` annotation for every future combination.

### 7.1. Resolve the key set first, then evict via API

Spring's `CacheManager` gives access to `Cache`; the cache provides `evict(key)`. When the application **has a reliable set of keys**, it can evict each entry individually.

~~~java
import java.util.Collection;
import java.util.Objects;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

public class DependentKeyInvalidator {
    private final CacheManager cacheManager;

    public DependentKeyInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void invalidateSearchKeys(Collection<String> affectedKeys) {
        Cache search = Objects.requireNonNull(
            cacheManager.getCache("searchResults"));

        for (String key : affectedKeys) {
            search.evict(key);
        }
    }
}
~~~

This is **a reusable code snippet for a Spring project**, not a standalone `main` program; the class must be registered as a bean with `CacheManager` supplied.

To implement this properly, you must know how to discover `affectedKeys`. For instance, an index tracking "which search keys productId 42 currently affects" must be updated whenever entries are created/deleted. If the index is incomplete or stale, related copies can be missed.

**Do not treat `CacheManager` as a key-enumeration API across all providers.** Spring's Cache abstraction does not provide a standard API to scan keys by prefix. Key iteration in Caffeine/Redis or Redis `SCAN` is provider-specific and requires evaluating cost, safety, clustering, and production operations.

### 7.2. Split cache regions to limit eviction scope

If `productDetail` can be evicted accurately by ID while every search list depends too broadly, put detail and search results in **two separate cache names**. When a product changes:

- Evict `productDetail[id]` by key.
- Clear `searchResults` with `allEntries = true` if business rules genuinely allow it and all search entries risk being stale.

That is a trade-off decision: trading cache warm-up cost for simplified correctness. Do not clear a wide region for convenience without observing hit ratio, load speed, traffic, and freshness requirements.

### 7.3. Versioning or generation tokens

Another approach is embedding a **generation/version** in the key of a cache group, such as `search:v18:filter=books`. When the dataset changes, increment the generation; reads construct keys for the new generation and do not use old results.

You need a consistent version source across instances, an expiration/cleanup mechanism for old-version entries, and testing for races when a writer increments the version concurrently with a reader. This is **system design**, not built-in functionality provided by `@CacheEvict`.

## 8. Evict after method success or before invocation?

By default `@CacheEvict` uses `beforeInvocation = false`. This means eviction is triggered **after the target method completes successfully**. If the method throws an exception outward, that call does not trigger post-invocation eviction.

~~~java
@CacheEvict(
    cacheNames = "productViews",
    key = "'detail:' + #p0"
)
public void updateProduct(long id) {
    repository.update(id);
}
~~~

The **illustrative code** above is only one post-invocation eviction; other copies still need separate handling.

When using:

~~~java
@CacheEvict(
    cacheNames = "productViews",
    key = "'detail:' + #p0",
    beforeInvocation = true
)
public void refreshProduct(long id) {
    repository.refreshFromRemote(id);
}
~~~

Spring performs eviction **before calling** the method. If the method fails, the already-removed entry is not automatically restored. This suits certain refresh operations or invalidations that must happen regardless of outcome, but it is not a safe default for all updates.

With `@Caching` containing multiple evictions, `beforeInvocation` can be configured per annotation, though you should avoid splitting related operations into two unintended time points.

### Caught exceptions and business failure results

If a method **catches an exception and returns normally** (for example `UpdateResult(success=false)`), under default settings Spring can still treat the invocation as successful and run eviction. You can consider an appropriate `condition` based on the post-invocation result or let business logic throw an exception at the right time; design according to the method's contract.

## 9. Transactions, concurrency, and multiple instances

### 9.1. @Transactional does not by default turn multiple evicts into an atomic transaction

Suppose a database update and multiple `@CacheEvict` operations run within a `@Transactional` operation. The Spring Cache advice and transaction advice mechanisms may wrap the method in different orders; **do not assume cache entries are only evicted after the database commits**.

If eviction happens before the transaction commits and another reader refills the cache from the old state, a stale entry can be recreated. If the update rolls back, entries may already have been evicted even though actual data did not change.

For domains requiring stronger consistency, consider caches equipped with **transaction-aware behavior**, an `afterCommit` mechanism, or post-commit event publication; test the specific provider and actual timing. Even so, multiple evictions across independent caches do not automatically become a distributed transaction.

### 9.2. Race condition after eviction

A tricky scenario:

~~~text
Reader A: miss -> starts reading old record
Writer B: updates source -> evicts keys
Reader A: finishes old query -> puts old version into cache
~~~

Without proper coordination, stale data can **be written back into the cache after eviction**. Risk mitigations include versioning, appropriate locking/synchronization, version checking at cache-put time, consistent serialization, and read/write path design. `@CacheEvict` alone does not solve all race conditions.

### 9.3. Multiple instances

With a **local in-memory** cache, instance A evicts its own entry while instance B still holds a stale copy. If system-wide invalidation is needed, consider:

- Using a shared cache like Redis (with consistent key, region, and serializer configuration).
- Using an event/broadcast mechanism for each instance to evict its corresponding local cache.
- Combining versioning, TTL, and metrics when the system has eventual consistency.

If using queues/events for invalidation, account for duplicate events, out-of-order delivery, retries, idempotency, and integrity of the `(cacheName, key)` pair.

## 10. Common mistakes

1. **Evicting only detail, forgetting summary/list.** Stale data still appears on other screens. Build a dependency matrix between source records and cache keys.
2. **Different key generation rules between read and evict.** Reads use `detail:42` yet eviction uses key `42`; syntactically valid eviction targeting the wrong entry. Directly compare `@Cacheable` and `@CacheEvict` expressions.
3. **Using one key to represent multiple copies.** A single `@CacheEvict(key = "'detail:' + #p0")` does not evict `summary:42`. Use `@Caching` when key count is finite.
4. **Assuming `allEntries` evicts by prefix.** `allEntries=true` clears the entire region, not keys matching a pattern.
5. **Changing category yet only evicting the new category.** The old category still holds the moved record. Both old and new categories are needed.
6. **Pagination and filters create countless keys with no invalidation plan.** Consider region design, a dependent-key index, or versioning.
7. **Calling a method via `this.update(...)` inside the same bean.** Under default proxy mode, self-invocation bypasses cache advice; `@Caching` is not applied.
8. **Assuming multiple evictions are atomic.** Provider failures can leave only a subset of keys evicted. Add observability and retry/recovery if business rules require it.
9. **Assuming DB transaction commit and cache evict are always synchronized.** Test advice ordering, rollbacks, and after-commit behavior.
10. **Clearing every region to avoid computing dependencies.** Simple, yet can trigger cache stampedes, drop hit ratios, and cause database load spikes.
11. **Forgetting version/tenant/locale in keys.** Can evict the wrong entry or miss copies of the same resource across variants.
12. **Overlooking multi-node setups.** Evicting local cache on one instance does not clean other instances automatically.
13. **Using `#result` with `beforeInvocation=true`.** Before the method runs, there is no result to reference.
14. **Believing a TTL policy completely replaces eviction.** TTL only bounds staleness duration; for business flows needing immediate accuracy after updates, an appropriate invalidation strategy is required.

## 11. Pre-deployment checklist

- [ ] Identify every type of cached result copy depending on the source record (detail, summary, list, aggregate, search).
- [ ] List all `(cacheName, key)` pairs requiring eviction for each kind of change.
- [ ] Confirm keys in `@CacheEvict` match the keys produced by `@Cacheable` or `@CachePut`.
- [ ] If moving groups/categories, evict both old and new categories.
- [ ] Use `@Caching(evict = {...})` for finite, determinable keys.
- [ ] Use `allEntries` only when cost and scope trade-offs are accepted.
- [ ] For dynamic keys, maintain a reliable dependency index, versioning mechanism, or other verifiable strategy.
- [ ] Define pre/post-invocation eviction policy, including when methods throw exceptions.
- [ ] Test transaction rollbacks, cache provider failures, concurrent reads/writes, and multiple instances.
- [ ] Ensure methods are invoked through Spring proxies with `@EnableCaching`, without unintended self-invocation.
- [ ] Collect metrics on hit/miss, evictions, detected staleness rates, and reload costs.

## 12. Self-check exercises

**Question 1.** Product 42 has two entries `detail:42` and `summary:42` in the same cache. Does a single `@CacheEvict(key="'detail:' + #p0")` evict both?  
**Answer:** No. It only targets `detail:42`. An eviction for `summary:42` must be added.

**Question 2.** Three keys to evict are known from method parameters across two cache names. Which annotation groups these operations?  
**Answer:** `@Caching(evict = { @CacheEvict(...), ... })`.

**Question 3.** What does `allEntries=true` with `cacheNames="categoryLists"` mean?  
**Answer:** Clears all entries in the `categoryLists` region, not just one category or prefix.

**Question 4.** A product moves from "books" to "games". Why must both lists be evicted?  
**Answer:** The old books list must drop the product, while the new games list must include it.

**Question 5.** An update method throws an exception with `beforeInvocation=false`. Does post-invocation eviction run?  
**Answer:** No, under the default mechanism when the exception escapes outward.

**Question 6.** Why does evicting three cache keys not guarantee all three caches are consistent at every instant?  
**Answer:** Eviction is not atomic across multiple keys/providers; concurrency, transaction boundaries, and multiple nodes also play a role.

**Question 7.** Can you ask Spring to delete all keys with prefix `category:` using `key="'category:*'"`?  
**Answer:** No. The cache abstraction does not provide universal wildcard key eviction.

**Question 8.** When the number of search keys changes constantly, what is better than writing a thousand annotations?  
**Answer:** Depending on the system: track the affected key set and evict programmatically; or redesign cache regions, use versioning/TTL, or clear an appropriate region.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Javadoc — CacheEvict: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework Javadoc — Caching: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
