# @CachePut: Choosing Keys from Arguments or Return Values

## Objectives

After this lesson, you will know when `@CachePut` should compute the cache key from **input arguments** and when it must take it from the **return value**. You will understand when Spring evaluates SpEL expressions, know how to keep the same key between `@CachePut` and `@Cacheable`, run a Java 17+ example yourself, and spot common errors with post-save generated IDs, `null` results, key types, and transactions.

This is a lesson in the **`@CachePut`** group, focusing on key selection for an operation that **always runs the method and then updates the cache**. Do not confuse `@CachePut` with `@Cacheable`: `@Cacheable` can skip the method body on a hit, whereas `@CachePut` always executes the method and writes the return value if caching conditions are satisfied.

## 1. Why must you choose the right key source?

Suppose a service has two operations:

- `updateBook(42, "Spring Cache")` edits the book with ID 42. The ID is known **before** running the method.
- `createBook("Spring Cache")` creates a new book; the repository/database assigns ID 101 **during** execution. Before calling, the official ID is unknown.

Both operations can return a `Book` and need to update the `books` cache, where `findById(42)` uses ID 42 itself as the key. If we want the record created by `createBook` to be immediately found by `findById(101)`, we must write to the cache under **key 101**, not the title string `"Spring Cache"`.

Quick selection rule:

| Data to identify the entry | Where to take the key from? | Example |
| --- | --- | --- |
| Argument already contains the stable identifier of the cached entry | **Argument** | `key = "#p0"` with `updateBook(Long id, ...)` |
| Argument is an object with an already-determined, immutable ID | **Argument property** | `key = "#p0.id()"` with `save(Book book)` |
| Official ID is generated or normalized during processing | **Return value** | `key = "#result.id()"` with `createBook(String title)` |
| Result may not exist, or may not contain a valid key | Redesign the put rule; handle empty/error results | Avoid accessing `#result.id()` when `#result == null` |
| Read and write use different identifiers | Align the key schema or proactively update the corresponding caches | Do not write by name and read by ID under the same contract |

The deciding point is **not** “which way is shorter”. Ask: *which exact key will the read method we want to update use to look up the cache?*

## 2. When Spring evaluates keys in @CachePut

For a synchronous method returning a normal result, the typical flow is:

```text
Call via Spring proxy
    │
    ├── Check cache applicability condition if present (condition)
    │
    ├── Execute real method (ALWAYS runs with @CachePut)
    │        └── May save to database, generate ID, normalize data...
    │
    ├── Receive result and evaluate unless if present
    │
    ├── Compute cache key from expression (can use #result)
    │
    └── Write return value into cache under that key
```

`@CachePut` can use `#result` in its `key` expression **because the return data is already available when performing the cache put**. This is an important characteristic of the annotation.

Example choosing from an argument:

```java
@CachePut(cacheNames = "books", key = "#p0")
public Book rename(Long id, String newTitle) {
    return repository.updateTitle(id, newTitle);
}
```

Example choosing from the result:

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book create(String title) {
    return repository.insertAndReturnBook(title);
}
```

The two snippets above are **illustrative patterns**, requiring `Book` and `repository` in a real application. The SpEL `key` expressions are understood as follows:

- `#p0` / `#a0`: parameter at index 0; `#p1` is the next parameter.
- `#root.args[0]`: another way to access the first argument.
- `#result`: the method's return value (the business object after Spring handles supported wrappers).
- `#result.id()`: invokes the accessor of the returned object, e.g., the accessor of a Java `record Book`.

**Be careful with `@Cacheable`:** do not use `key = "#result.id()"` to look up the cache in `@Cacheable`, because the lookup key must be known *before* deciding whether to invoke the method. `#result` is valid for `@Cacheable(unless = "...")` after execution, but not for `@Cacheable`'s `key` expression.

## 3. Consistency principles between @CachePut and @Cacheable

Suppose:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findById(Long id) { /* read source */ }
```

That cache distinguishes entries by `Long id`. Every cache write path intended to serve `findById` must produce **the same cache name, the same key value, and the same backend-compatible key type**.

Correct example:

```text
findById(101L)                   → books[Long(101)]
rename(101L, "New")              → books[Long(101)]
create(...) returns Book(id=101) → books[Long(101)]
```

Some error-prone combinations:

| Cache write path | Cache read path | Problem |
| --- | --- | --- |
| `@CachePut(key="#p0")` on `create(String title)` | `@Cacheable(key="#p0")` on `findById(Long id)` | Writes by title but reads by ID; the created entry is not used for ID reads. |
| `key="#result.id()"` where result returns ID as `String "101"` | Read with `Long 101L` | Different key type; many backends treat them as two distinct keys. |
| Write `cacheNames="bookDetails"` | Read `cacheNames="books"` | Different cache namespace. |
| Write with old ID even when operation changes identifier | Read with new ID | Entry may be stale/wrong; must migrate key and evict old entry if contract allows ID changes. |
| Default all parameters `(id, title)` for update | Read has only `id` | Update produces `SimpleKey(id,title)`, mismatching the `id`-only key. |

Every method should have a clear **key contract**, for example `books: Book.id (Long)`. Changing the contract requires reviewing read, put, evict methods, serialization, and all instances sharing the cache.

## 4. Runnable demo: return-value ID for create, input ID for rename

The example uses Java 17+, Spring Boot with Gradle, and an in-memory cache. It demonstrates both key calculation styles and confirms that reads after `@CachePut` are cache hits. The `ConcurrentMapCacheManager` backend has no default TTL or size limit; the purpose here is solely to observe key selection.

In an existing Spring Boot Gradle project (configured with plugins and a Spring Boot version compatible with Java 17+), add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

Create **`src/main/java/example/cacheput/Book.java`**:

```java
package example.cacheput;

public record Book(Long id, String title) {
}
```

`record` keeps results immutable; the `id()` and `title()` accessors can be invoked in Java or SpEL.

Create **`src/main/java/example/cacheput/CacheConfiguration.java`**:

```java
package example.cacheput;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

Create **`src/main/java/example/cacheput/BookService.java`**:

```java
package example.cacheput;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    // Simulates a database and ID generator, for lesson purposes only.
    private final Map<Long, Book> database = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(100);
    private final AtomicInteger sourceReads = new AtomicInteger();

    // Input ID is not yet known. After create() returns,
    // Spring reads the ID from the returned Book to populate the cache.
    @CachePut(cacheNames = "books", key = "#result.id()")
    public Book create(String title) {
        Long id = nextId.incrementAndGet();
        Book book = new Book(id, title);
        database.put(id, book);
        return book;
    }

    // Exact entry ID is known before the method runs.
    // Neither the new title nor call count belongs in the books key.
    @CachePut(cacheNames = "books", key = "#p0")
    public Book rename(Long id, String newTitle) {
        Book updated = new Book(id, newTitle);
        if (database.replace(id, updated) == null) {
            throw new IllegalArgumentException("Unknown book: " + id);
        }
        return updated;
    }

    // Read path uses the exact key schema that both put paths use.
    @Cacheable(cacheNames = "books", key = "#p0")
    public Book findById(Long id) {
        System.out.println("SOURCE_READ " + sourceReads.incrementAndGet());
        return database.get(id);
    }

    // Only to prove the next read is a miss after eviction.
    @CacheEvict(cacheNames = "books", key = "#p0")
    public void evictCachedBook(Long id) {
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

Create **`src/main/java/example/cacheput/CachePutKeyDemoApplication.java`**:

```java
package example.cacheput;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CachePutKeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CachePutKeyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runExample(BookService books) {
        return args -> {
            Book created = books.create("Java 17");
            System.out.println("created = " + created);
            System.out.println("read1 = " + books.findById(created.id()));

            Book updated = books.rename(created.id(), "Spring Cache");
            System.out.println("renamed = " + updated);
            System.out.println("read2 = " + books.findById(created.id()));

            books.evictCachedBook(created.id());
            System.out.println("read3 = " + books.findById(created.id()));
            System.out.println("sourceReads = " + books.sourceReadCount());
        };
    }
}
```

Run from the project directory:

```bash
./gradlew bootRun
# On Windows PowerShell: .\gradlew.bat bootRun
```

**`System.out` lines produced by this program**, in exact order, excluding Spring Boot logs:

```text
created = Book[id=101, title=Java 17]
read1 = Book[id=101, title=Java 17]
renamed = Book[id=101, title=Spring Cache]
read2 = Book[id=101, title=Spring Cache]
SOURCE_READ 1
read3 = Book[id=101, title=Spring Cache]
sourceReads = 1
```

Matching each action:

1. `create("Java 17")` generates ID 101 and returns `Book`. `@CachePut(key="#result.id()")` writes `books[101L]`.
2. `findById(101L)` gets a cache hit; does not print `SOURCE_READ`.
3. `rename(101L, "Spring Cache")` **still runs** and updates the database, then `@CachePut(key="#p0")` replaces `books[101L]` with the new result.
4. `findById(101L)` hits again, seeing the new title without reading the database.
5. `evictCachedBook(101L)` deletes the entry, so the subsequent `findById(101L)` prints `SOURCE_READ 1` and returns the content from the database.
6. The source counter equaling 1 proves: the first two reads did not execute the body of `findById`, and only the read after eviction ran it.

**Why is stdout predictable?** A fresh single process starts, `nextId` initializes at 100 with no concurrent requests; the `Book` record has Java's standard `toString()`; `CommandLineRunner` invokes each operation sequentially. The demo does not depend on a real database.

These are **four classes in a Spring Boot project**, not a single standalone file run directly with `javac`: Spring and build dependencies are required. If a project has other runners or a different cache manager, logs/behavior outside the example may differ.

## 5. When should the key be taken from an argument?

Use an **argument** when a parameter already describes the exact cache key used by the read paths.

Example editing a user with a known identifier:

```java
@CachePut(cacheNames = "usersById", key = "#p0")
public User updateProfile(Long userId, UpdateProfileCommand command) {
    return repository.updateAndFetch(userId, command);
}
```

Here `User`, `UpdateProfileCommand`, and `repository` are illustrative types/variables. `userId` is always the ID of the updated entry, so there is no need to wait for the result to determine the key. With default keys, both `userId` and `command` would participate in the key; that could diverge from `getById(userId)`.

Reasonable variations:

- `key = "#p0"`: first parameter is the ID, e.g., `Long id`.
- `key = "#p0.id()"`: first parameter is an object with a stable ID.
- `key = "#p0.tenantId() + ':' + #p0.bookId()"`: just an example of string concatenation when components are normalized and properly escaped. With multiple components, prefer a value object/key generator to avoid string collisions.
- `key = "#p1"`: the ID is in the second parameter, provided it is genuinely the read path's key.

**Point to self-check:** if the ID is altered/normalized inside the method body or multiple tenants share the same ID, picking a single argument may not suffice. The key must reflect all components that alter the result and access rights.

## 6. When should the key be taken from the return value?

Use **`#result`** when the final identifier only appears after running the method or when the system wants the normalized/persisted value from the returned object.

Example creating a product with a database-assigned ID:

```java
@CachePut(cacheNames = "productsById", key = "#result.id()")
public Product createProduct(CreateProductRequest request) {
    return repository.insertAndFetch(request);
}
```

In this example, `Product`, `CreateProductRequest`, and `repository` are illustrative types. The method must return **an object with a stable final ID**; if the repository only returns a success boolean or `void`, Spring cannot deduce the ID via `#result.id()`. In that case, change the return contract, obtain the ID via another mechanism, or evict/re-read under a known key.

Real-world cases:

- The database auto-generates an ID after `INSERT`.
- The server assigns a public ID/slug different from what the client sent.
- The service converts a temporary ID to an official ID.
- Post-save data is normalized, and the read path uses the normalized identifier.

**Mandatory condition:** the value pointed to by `#result` must be present on put, and the key-forming component must be valid. If the method can return `null` or `Optional.empty()`, do not assume `#result.id()` is safe. Choose a fail-fast contract when creation fails, or configure vetoing empty results (such as `unless = "#result == null"`) and test on your Spring/provider version.

With Spring-supported wrapper return types like `Optional<Book>`, `#result` in caching SpEL refers to the **actual `Book`**, not `Optional<Book>`; the empty case can resolve to `null`. With future/reactive return types, asynchronous completion timing and cache behavior depend on the Spring version and backend; verify separately rather than extrapolating from synchronous demos.

## 7. Expressions that must not be misused

| Scenario | Right approach | Why |
| --- | --- | --- |
| Put after method generates ID | `@CachePut(key="#result.id()")` | At put time, the result is already available. |
| Put updating a record with existing ID | `@CachePut(key="#p0")` | Same key as read-by-ID. |
| Lookup before running method | `@Cacheable(key="#p0")` | Key must be known before deciding hit/miss. |
| Avoid caching unsuitable results | `@CachePut(unless="#result == null")` if contract allows | `unless` is evaluated after invocation. |
| Cache only when input meets condition | `@CachePut(condition="#p0 != null")` when matching signature | `condition` relies on information available before invocation. |
| Evict entry on success using return value | Can use `@CacheEvict(key="#result.id()")` when `beforeInvocation=false` | Result is only available after invocation; requires a matching return contract. |

Do not arbitrarily put `@Cacheable` and `@CachePut` on the same method: one annotation aims to skip execution on a hit, while the other always needs execution to update the cache. Avoid mutually exclusive conditions between them based on `#result` because selecting cache operations includes a pre-invocation evaluation step.

## 8. Hard-to-spot bugs in production environments

### 8.1. Write key differs from read key

`@CachePut(key="#result.id()")` will not help `getByCode(String code)` if the read method caches by code. The solution is to unify on one ID-based cache, or maintain a separate cache by code and update/evict each cache properly. Do not assume two caches stay in sync automatically.

### 8.2. Same ID but different tenant or permissions

If `books` contains tenant-specific data, `key="#result.id()"` may still lack the tenant. For instance, if tenant A and B both have book ID 101, entries can overwrite each other. The key must have sufficient scope, such as a `(tenantId, bookId)` value object, or tenant-separated cache namespaces. Authorization checks must happen *before the cached method* because on a hit, the `@Cacheable` body may not execute.

### 8.3. Argument and result have mismatched IDs

`updateBook(requestedId, ...)` might return an entity whose `canonicalId` differs from the requested ID. Choosing `#p0` or `#result.id()` must be based on the identifier that the **read path** looks up. If an ID change is valid, also handle the old entry (evict/migrate key) and update related index caches. A single put by itself does not delete all old aliases.

### 8.4. Error results, null, or side effects

`@CachePut` always calls the method, so repository errors still occur. When the method throws an exception, the put normally does not run along the success path. When the method returns `null` or a type without an ID, `#result.id()` cannot be considered valid. Explicitly define failure behavior, return the needed entity/ID, and define a policy for skipping empty values.

### 8.5. Commit timing and concurrent requests

`@CachePut` updates the cache based on the method result; that **does not automatically guarantee** cache and database data committed atomically. If a transaction rolls back after a cache put, or another request writes concurrently, the cache may be wrong or stale. For strict consistency requirements, consider transaction boundaries, post-commit cache updates, TTL/invalidation, and concurrency testing.

### 8.6. Self-invocation and backends

Annotations work through Spring proxies under default configuration. Calling `this.rename(...)` within the same bean or instantiating with `new BookService()` bypasses advice. Also, `Long(101)`, string `"101"`, and Redis key serialization can differ; tests should use the actual backend/key generator used in deployment.

## 9. Testing to prove you chose right

Building on the demo, add tests or run observations for these cases:

1. **New create:** call `create` returning a new ID, then immediately call `findById(id)`. If cached properly via `#result.id()`, no source read happens.
2. **Update with ID:** call `rename(id, newTitle)`, then `findById(id)` must hit and return the new title. The title value is not part of the key.
3. **Evict:** remove the entry for the same ID, call `findById(id)` again, and verify it reads the source once.
4. **Intentional wrong key:** try `@CachePut(key="#p0")` on `create(String title)`; reading by `Long` ID will miss. Only do this in a test environment—do not keep the wrong configuration.
5. **Two tenants with the same ID:** simulate two records with the same numeric ID but different tenants. If the cache is shared, ensure the key includes the tenant so wrong data is not returned.
6. **Null/exception:** test failed creation / no entity returned. Confirm no erroneous put or invalid entry occurs.
7. **Transaction boundaries:** with a real service, test successful updates, rollbacks, and concurrent requests.
8. **Type and namespace:** compare `Long` ID vs. `String` ID; verify cache names and key generators across read/put/evict.

Only conclude “the key is right” with evidence of **both correct returned content and correct hit/miss behavior**. Returning the right value by reading the database every time does not prove `@CachePut` updated the cache properly.

## 10. Code review decision checklist

- [ ] Identified the **read method** and its key before choosing the key for `@CachePut`.
- [ ] Clear on whether the ID/key value exists before invocation or only after the method returns.
- [ ] If taken from arguments, using `#p0`/`#p1` or corresponding property properly, without accidentally creating a `SimpleKey` including unrelated data.
- [ ] If taken from the result, the return type always has a valid identifier or an empty-result policy is in place.
- [ ] Cache name, key type, namespace, tenant/scope, and serializer are compatible across read/put/evict.
- [ ] `#result` is not used to compute a `@Cacheable` lookup key.
- [ ] Database updates, cache, and transactions have a consistent strategy; old entries are handled when IDs/aliases change.
- [ ] Tested via source access counts and returned data, including failure and concurrency cases where applicable.

## References

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `@CachePut` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
