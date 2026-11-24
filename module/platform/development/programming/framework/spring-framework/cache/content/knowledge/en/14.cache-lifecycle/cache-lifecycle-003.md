# Choosing DTOs or Immutable Data to Store in Spring Cache

> **Spring Framework – Cache Abstraction · Group: Data and Lifecycle.** This lesson explains why cached values should be **DTOs/snapshots that cannot be mutated unintentionally**, when not to directly cache entities with mutable state, how to design immutable objects in Java 17+, and how to keep the cache accurate when source data is updated.

## 1. The problem: caching does not automatically make a value a safe copy

A `@Cacheable` call can return a Java object containing multiple fields. The Spring Cache Abstraction coordinates key lookup and result storage, yet **does not guarantee that every cache backend deep-copies or freezes objects**. With a local reference-based cache, the object placed into the cache can be the very same object that application code still holds.

Suppose:

1. `getBook("BK-1")` loads a `Book` object titled `"Java Basics"`.
2. Spring puts that object into the `books` cache under key `"BK-1"`.
3. Other code receives the object and directly calls `book.setTitle("Changed")`.
4. If the cache holds **the same object reference**, the next read may receive `"Changed"` even though the data source was never updated accordingly.

Possible consequences include: data modified outside the official write path; the cache becoming inconsistent with the database; state shared across requests; hard-to-reproduce concurrency bugs; and accidentally returning request-specific information to another request.

Diagram:

~~~text
DAO / Service
    |
    | @Cacheable returns MutableBook
    v
Local reference-based cache
    |
    +----> Request A receives object ----> mutates title/tags
    |
    +----> Request B reads same key ----> sees state mutated by A
~~~

**Design principle:** cache **values representing state at a point in time** rather than sharing objects that can be mutated arbitrarily. Immutable DTOs, defensively copied records, and value types like `String` or `BigDecimal` are generally preferable to entities tied to an ORM lifecycle and state.

This does not eliminate the need for TTL, updates, and eviction. **Immutability prevents unintended mutation; it does not automatically make cached data fresh when the source changes.**

## 2. What are DTOs and immutable snapshots?

A **DTO (Data Transfer Object)** is an object carrying data for exchange between layers or for returning to clients. A DTO typically holds a curated set of fields rather than all entity relationships and behaviors.

An **immutable object** is an object whose observable state cannot change after creation. Returning a `BookView` represents a snapshot at read time; if the source is updated, rather than mutating the cached object, the application creates a new snapshot and handles invalidation.

Business data example:

~~~java
public record BookView(
        String isbn,
        String title,
        java.util.List<String> tags
) {
    public BookView {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

`BookView` here is a **syntactically standalone record declaration** that should be placed in `BookView.java` or as a nested record inside an appropriate class. In Java 17:

- Record components generate `final` fields and accessors such as `isbn()`, `title()`, and `tags()`.
- `String` is immutable, so `isbn` and `title` cannot be mutated internally.
- `List.copyOf(tags)` creates a list that **forbids mutation through the list API** and avoids sharing a mutable source list, provided the elements inside are also immutable.
- `BookView` provides no setters; representing a new version requires creating a new `BookView` object.

**Important:** the `record` keyword only guarantees that component references are `final`; it **does not automatically create deep immutability** for nested objects. If `tags` is an `ArrayList` and no copy is made, callers can still call `bookView.tags().add("unexpected")` and alter the observable content. That is why the example places `List.copyOf` in the compact constructor.

### A DTO is not immutable by default

Here is a **mutable** DTO:

~~~java
public class MutableBookDto {
    private String title;

    public MutableBookDto(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

If this object is cached with a reference-storing backend, callers can change `title`. Simply renaming an entity to DTO is **not enough**; you must inspect its field structure, mutating APIs, and how the cache provider stores values.

## 3. Why is caching JPA entities directly usually avoided?

A JPA entity is not always dangerous, but placing it directly into Spring Cache requires carefully evaluating the following points:

| Risk | When caching a mutable entity/proxy | When caching an appropriate DTO snapshot |
| --- | --- | --- |
| Mutation outside the update workflow | Entity setters can mutate the cached in-memory object | No setters; a new snapshot is created on changes |
| Lazy associations | Lazy proxies/collections may require an active session to read | Includes only materialized and genuinely needed fields |
| Persistence context | Entity has managed/detached state and an ORM-bound lifecycle | DTO is independent of any session or persistence context |
| JSON representation | Circular references, lazy initialization, or redundant data | Flat structure with a clear schema |
| Serializability | Distributed providers may fail to serialize proxies/associations | DTO is specifically designed and tested for the codec |
| Cache size | Relationship graphs can retain large amounts of unnecessary data | Retains only the fields needed for the use case |
| Data sensitivity | Entities may contain internal fields that should not be cached or exposed | Fields selected according to least-privilege principles |

For instance, an `OrderEntity` might hold payment details, addresses, lazy relationships to hundreds of order items, and dirty-checking state. If a screen only needs `orderId`, `total`, and `status`, build an `OrderSummary` from the loaded data. That snapshot is far easier to size, schema-version, and manage across its lifecycle.

**Distinguish the two cache layers:** Spring Cache (`@Cacheable`) is an application-level cache coordinated by Spring; JPA/Hibernate's **second-level cache** and first-level persistence context are separate ORM mechanisms. This guidance on choosing DTOs addresses **values stored in Spring Cache**, not enabling or disabling JPA's second-level cache.

### Are there cases where entities can be cached?

Not every entity is strictly forbidden. A genuinely immutable object free of hard-to-control lazy proxies, with a clear lifecycle and backend compatibility, can be considered. Yet when teams need an easy-to-review policy across codebases, **a simple DTO snapshot with an explicit contract is usually the safer default**. Do not cache an object attached to a DB session and assume the entity can be used as-is across arbitrary requests.

## 4. Immutability must consider the entire object graph

### 4.1. `final` does not make inner elements immutable

~~~java
import java.util.List;

public record UnsafeBookView(String isbn, List<String> tags) {
}
~~~

`UnsafeBookView` only has a `final` reference field `tags`. If a caller passes an `ArrayList`, its contents can be altered via `view.tags().add("new")` or an external reference kept by the caller.

A safe version for data composed of `String` values:

~~~java
import java.util.List;

public record SafeBookView(String isbn, List<String> tags) {
    public SafeBookView {
        tags = List.copyOf(tags);
    }
}
~~~

This example is a **record definition for use in an appropriate Java file**, not a program with `main`. For a list containing `String` elements:

- Mutating the source list after creating the record does not affect the snapshot.
- Callers cannot `add`, `remove`, or `set` elements through `tags()`.
- Decide explicitly how to handle `null`: `List.copyOf` rejects null collections and null elements.

`Collections.unmodifiableList(sourceList)` **differs in meaning**: it may be an unmodifiable view *through that reference*, yet if the underlying `sourceList` is mutated elsewhere, the view still reflects those changes. `List.copyOf` takes an unmodifiable copy per contract; if the source is already an immutable list, the JDK may reuse the instance while still honoring the immutability contract.

### 4.2. `List.copyOf` only copies the list structure

If the list holds mutable objects:

~~~java
import java.util.List;

public record Address(String street) {
}

public record CustomerView(String customerId, List<Address> addresses) {
    public CustomerView {
        addresses = List.copyOf(addresses);
    }
}
~~~

In the example above, `Address` is a record containing only a `String`, so each element is also immutable by design. If `Address` were a class with mutable setters, `List.copyOf` would only keep the element references **without deep-copying each `Address`**. In that case, you must convert each element into an immutable value object before building the list.

A transformation pattern, assuming `MutableAddress` has a `getStreet()` method:

~~~java
List<Address> snapshots = addressesFromSource.stream()
        .map(address -> new Address(address.getStreet()))
        .toList();
CustomerView view = new CustomerView("C-1", snapshots);
~~~

This is an **illustrative mapping snippet inside a method**, requiring `addressesFromSource` and `MutableAddress` from a real application. The `toList()` method (Java 16+) produces an unmodifiable list, and the `CustomerView` constructor applies `List.copyOf` to enforce the snapshot rule right at the DTO boundary.

### 4.3. Date/time, numeric, and collection fields

Prefer inherently immutable value types whenever possible:

- `String`, `BigDecimal`, `UUID`, `LocalDate`, `Instant`: easier to reason about than their mutable counterparts.
- `LocalDateTime`/`Instant` in `java.time` are immutable; for distributed timestamps, be explicit about timezone/UTC and representation.
- If source data uses mutable `java.util.Date`, convert to `Instant` or defensively copy when entering the DTO.
- `List.copyOf`, `Set.copyOf`, and `Map.copyOf` are useful for collections when **the keys and values inside are also safe**; these methods do not deep-copy nested objects.
- Never put `InputStream`, `EntityManager`, `Session`, `Connection`, `HttpServletRequest`, or thread-bound contexts directly into cached values. They carry live resources or lifecycles rather than a pure data snapshot.

Do not turn immutability into a mechanical rule that causes excessive copying. For large collections, evaluate memory and copy cost; when a value is genuinely immutable from creation, a dedicated immutable type can be reused safely.

## 5. Complete Java 17+ example: caching an immutable DTO instead of a mutable source object

This example uses **Spring Framework 6.2.14**, `ConcurrentMapCacheManager`, and Java 17. Source data is simulated using a mutable class containing `title` and `ArrayList<String> tags`. The `@Cacheable` method builds an **immutable `BookView` record** before caching; `@CacheEvict` deletes the key when the source changes.

What to observe:

1. Two reads of the same ISBN through the proxy share one cache entry.
2. Attempting to mutate `tags` through the DTO is rejected.
3. When the source changes, the old DTO is **not mutated along with it**.
4. Eviction removes the old entry; the next read creates a new DTO matching the source.

Create the two files below.

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ImmutableCacheValueDemo'
}
~~~

**File `src/main/java/demo/ImmutableCacheValueDemo.java`:**

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ImmutableCacheValueDemo {

    // Cached value: snapshot keyed by ISBN, does not share a mutable list.
    public record BookView(String isbn, String title, List<String> tags) {
        public BookView {
            Objects.requireNonNull(isbn, "isbn");
            Objects.requireNonNull(title, "title");
            tags = List.copyOf(tags);
        }
    }

    // Only used to simulate an updatable source entity/record.
    static final class MutableBook {
        String title;
        final List<String> tags;

        MutableBook(String title, List<String> tags) {
            this.title = title;
            this.tags = new ArrayList<>(tags);
        }
    }

    public static class BookService {
        private final Map<String, MutableBook> source =
                new ConcurrentHashMap<>(Map.of(
                        "BK-1",
                        new MutableBook("Effective Java", List.of("java", "books"))
                ));
        private int sourceReads;

        @Cacheable(cacheNames = "books", key = "#p0")
        public BookView getBook(String isbn) {
            sourceReads++;
            MutableBook book = source.get(isbn);
            if (book == null) {
                return null;
            }
            return new BookView(isbn, book.title, book.tags);
        }

        @CacheEvict(cacheNames = "books", key = "#p0")
        public void renameBook(String isbn, String newTitle) {
            if (newTitle == null || newTitle.isBlank()) {
                throw new IllegalArgumentException("new title is blank");
            }
            MutableBook book = Objects.requireNonNull(
                    source.get(isbn), "unknown isbn"
            );
            book.title = newTitle;
            book.tags.add("revised");
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache books = Objects.requireNonNull(manager.getCache("books"));

            BookView first = service.getBook("BK-1");
            BookView second = service.getBook("BK-1");

            System.out.println("first: " + first);
            System.out.println("same object on hit: " + (first == second));
            System.out.println("source reads before update: " +
                    service.sourceReads());

            boolean blocked = false;
            try {
                first.tags().add("injected");
            } catch (UnsupportedOperationException ex) {
                blocked = true;
            }
            System.out.println("mutation blocked: " + blocked);

            service.renameBook("BK-1", "Effective Java 4");
            System.out.println("cache entry after update: " +
                    (books.get("BK-1") != null));
            System.out.println("old snapshot title: " + first.title());

            BookView fresh = service.getBook("BK-1");
            System.out.println("fresh: " + fresh);
            System.out.println("source reads after update: " +
                    service.sourceReads());
        }
    }
}
~~~

Run in the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout of the program** (excluding Gradle or external environment logs):

~~~text
first: BookView[isbn=BK-1, title=Effective Java, tags=[java, books]]
same object on hit: true
source reads before update: 1
mutation blocked: true
cache entry after update: false
old snapshot title: Effective Java
fresh: BookView[isbn=BK-1, title=Effective Java 4, tags=[java, books, revised]]
source reads after update: 2
~~~

### Explaining each result

1. The first call to `getBook("BK-1")` executes the method body and builds a `BookView` containing a copy of the list. The second call with the same key hits `books`, so the method body does not run; `sourceReads = 1`.
2. `same object on hit: true` holds **in this example using the default `ConcurrentMapCacheManager` with store-by-reference**. Do not assert that object identity is true across all distributed backends or store-by-value/serializing backends.
3. `first.tags().add("injected")` throws `UnsupportedOperationException` because the list comes from `List.copyOf`, so the program prints `mutation blocked: true`. Had a mutable DTO been chosen, the mutation could affect the shared cached object.
4. `renameBook` modifies the **source** and adds the `"revised"` tag, and Spring's `@CacheEvict` deletes the entry with the matching key by default after the method succeeds. Hence `books.get("BK-1")` returns `null` (no entry).
5. The `first` variable still references the old snapshot with title `"Effective Java"`. It **does not change automatically** after the source is modified.
6. `getBook("BK-1")` after eviction executes the method body again, creating a new snapshot with `"Effective Java 4"` and the added `"revised"` tag; `sourceReads` increments to 2.

This example is intentionally single-threaded to focus on cache value selection. In real applications, source updates and eviction must account for transactions, concurrency, and concrete invalidation rules. `@EnableCaching` and retrieving the bean via `AnnotationConfigApplicationContext` ensure calls pass through the caching proxy. Calling `getBook` internally via `this.getBook("BK-1")` within the same bean in default proxy mode can bypass the annotation.

## 6. Immutable snapshots do not replace a cache lifecycle strategy

An immutable `BookView` prevents callers from mutating cached objects, yet if the DB renames a book from `"Effective Java"` to a new title, the old snapshot remains **accurate as of the old point in time**, and does not automatically become fresh data.

Essential considerations:

### 6.1. Keys must be stable and uniquely identify the data

In the example, `key = "#p0"` is the ISBN. If the returned data also depends on tenant, language, access permissions, or other parameters, the key must reflect **every** factor affecting the result. For instance, if the same `bookId` has tenant-specific state while the cache keys only on `bookId`, data could be returned to the wrong tenant.

Do not cache using a mutable input object directly as a key if `equals()`/`hashCode()` depend on mutable state. Prefer `String`/stable IDs or well-defined immutable value objects.

### 6.2. Evicting or updating entries after the source changes

`@CacheEvict(cacheNames = "books", key = "#p0")` fits when a successful update invalidates the old snapshot. `@CachePut` can serve as an alternative if the update method always returns the exact new DTO and the cache layout matches, though do not force it just to avoid evicting when there is no corresponding return value.

With `@Transactional`, eviction after a method completes **does not by default** guarantee the DB has committed. Designs requiring high consistency should control post-commit invalidation and reader/writer races. `TransactionAwareCacheManagerProxy` or post-commit callbacks are approaches to verify against your provider and transaction boundaries.

### 6.3. TTL and stale-data tolerance

TTL/TTI, capacity-based eviction, and cache persistence are **provider-dependent** policies. An immutable DTO can still go stale if the TTL is too long or the application forgets invalidation.

- Frequently updated data: requires shorter TTLs or event-driven invalidation.
- Read-heavy, rarely changed data: longer TTLs can reduce source load costs.
- Sensitive data: do not retain it longer than permitted, and do not cache information that unauthorized callers could mistakenly read.

The Spring Cache abstraction does not provide a uniform TTL across all backends through `@Cacheable` alone; you must configure the cache provider.

### 6.4. DTO schema and serialization

With distributed caches like Redis, data is typically serialized to JSON or binary. When changing a DTO schema between deployments, old cached entries may fail to deserialize or lack important fields.

Consider cache name/key versioning, tested codecs, migration/eviction on deployment, and compatibility between producers and consumers. Immutable records make schemas clearer, though they do not automatically solve every serializer concern.

### 6.5. Size, depth, and security

A DTO should hold **just enough** data for the method, rather than copying an entire entity graph. Caching too many fields increases memory footprint, network payload, and serialization time. Conversely, a DTO missing fields promised by the method's contract causes functional bugs.

In particular, avoid placing passwords, tokens, session-bound objects, or user-private data into cache regions whose keys lack tenant/user context. Immutability **does not replace** access control and proper cache partitioning.

## 7. Comparing cache value choices

| Choice | Advantages | Limitations / caveats | When to consider |
| --- | --- | --- | --- |
| Mutable JPA entity | Minimal initial mapping | Has setters, lazy proxies, ORM state, excess data | Only with an explicit policy for lifecycle and provider |
| Mutable DTO class | Easy integration with legacy libraries | Callers can mutate fields/lists; does not solve reference sharing | When boundaries enforce defensive copying and mutation control |
| Java `record` with immutable fields | Concise, clear constructor/accessors, readable values | A record is only shallowly immutable if it nests mutable objects | Preferred for pure-data cache snapshots |
| `record` + copied collections / elements | Restricts mutation on both collections and elements | Copying/mapping cost; requires null handling | Good default for data with nested collections |
| Serialized value (Redis or store-by-value) | Separates identity across read/write operations | Codec, schema, latency; copying/serialization does not replace invalidation | Multi-instance caches requiring shared state |
| Cache IDs, load entities at another layer | Lightweight cached values | May not sufficiently reduce queries and latency | Complex data needing lookup separated from the object graph |

**Practical recommendation:** start with an immutable DTO containing **only the fields required by the read path**, constructed in the read layer after materializing related data; expand only when measurements show more must be stored.

## 8. Designing mapping at the cache boundary

A clear pipeline:

~~~text
Repository / source API
         |
         | Load data per business logic
         v
  Mutable entity / model
         |
         | Map + materialize required lazy fields
         | Copy mutable collections / elements
         v
    Immutable DTO
         |
         | @Cacheable stores in cache by key
         v
 Cache holds snapshot
         |
         | Multiple callers read same DTO
         v
  Cannot mutate snapshot unintentionally
~~~

If mapping is expensive, deciding **where to place `@Cacheable`** matters too. Place the annotation on the method returning the immutable DTO so the cache holds the post-mapping result, rather than caching the entity and having to re-map on every request or accidentally exposing mutable cached objects.

**Note on ownership:** the DTO instance may be shared across requests if the cache stores by reference. The design should assume callers will read it but are not permitted to mutate it. Records with copied collections and immutable elements satisfy this far better than relying on a convention like “nobody call the setters.”

Do not put a lazy entity into the cache and then work around lazy-load errors by extending the session to the request or switching every relationship to eager loading unnecessarily. Identify the exact data the DTO requires, query just that data, and build the snapshot within the proper transaction boundary.

## 9. Common pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Returned from cache, yet title/tags get mutated by another request | Cache stores mutable object by reference | Immutable DTO; defensively copy lists and nested values |
| Using a record, yet the list still changes | Record is shallowly immutable and holds the original mutable list | `List.copyOf` in the constructor; inspect element types |
| Using `Collections.unmodifiableList`, yet data still changes | The view wraps the original list, which gets mutated elsewhere | Create an independent snapshot with `List.copyOf` or an equivalent copy |
| Caching entities directly causes serialization errors | Lazy proxies, bidirectional relationships, or incompatible serializer | Map to a clear-schema DTO; test the codec |
| Cached data differs from the DB after an update | Immutability does not equal freshness | `@CacheEvict`/`@CachePut`, TTL, post-commit handling |
| Two tenants see the same value | Cache key lacks a tenant/user discriminator | Add key components and enforce access checks |
| `List.copyOf` throws `NullPointerException` | Input collection contains nulls or the list itself is null | Normalize or reject nulls per the DTO contract |
| Cache memory grows rapidly | DTO holds an overly large data graph or TTL is too long | Retain only necessary fields, bound size, configure eviction |
| Old records fail to deserialize after deployment | Incompatible schema/codec | Schema versioning strategy, test migration/eviction |
| Annotation does not work on same-bean calls | Self-invocation bypasses the Spring proxy | Invoke through another proxy bean or redesign the service layer |

### Checks before putting a data type into the cache

Answer these questions:

1. **Are there setters or mutable collections?** If so, can callers or other threads mutate the cached state?
2. **Are there lazy associations, DB sessions, or live resources?** If so, map the needed data out of that lifecycle.
3. **Is there data that should not be shared?** If so, strip it from the DTO or ensure proper partitioning/keys and access controls.
4. **What are the key and lifecycle?** When the source changes, which write path will evict/update? When does the cache expire?
5. **Is it serializable?** If using a remote backend, test reads/writes and cross-version deployments.
6. **Is the whole object worth caching?** Measure memory, hit rate, and mapping/source-load time.

You do not need to turn every value into a massive deep-copied tree. What you need is a **clear immutability contract at the boundary where objects are shared**, balanced against cost and the corresponding lifecycle model.

## 10. Self-check exercises

**Exercise 1.** Does `record ProductView(String id, List<String> tags)` automatically guarantee that `tags()` cannot be mutated?

**Answer:** No. A record holds a final reference, yet the list itself may be mutable. Copy it with `List.copyOf(tags)` in the constructor or require an immutable collection by contract.

**Exercise 2.** Why can directly caching a managed JPA entity cause problems even when the key is right?

**Answer:** An entity has mutable state, lazy relationships, and a lifecycle tied to the persistence context. An object shared through the cache can be mutated unintentionally or fail outside an active session. A DTO snapshot reduces those coupling constraints.

**Exercise 3.** Given `List.copyOf` on a list containing `MutableAddress` objects with setters, is the DTO deeply immutable?

**Answer:** Not yet. The list is structurally unmodifiable, yet its elements can still be mutated. Convert elements into immutable value objects or perform a deeper defensive copy.

**Exercise 4.** After a successful update, will an immutable `BookView` held in the cache automatically update its title to match the DB?

**Answer:** No. You still need to evict/update the entry and configure an appropriate TTL/invalidation policy. Immutability only prevents unintended mutation; it does not keep data fresh.

**Exercise 5.** In the example using the default `ConcurrentMapCacheManager`, why can `first == second` be true?

**Answer:** The default `ConcurrentMapCache` stores by reference within the same JVM; a cache hit can return the same instance. With backends using serialization or store-by-value, object identity is not necessarily preserved.

## 11. Summary and official sources

**Key points to remember:**

- **Spring Cache does not by default guarantee deep copying or make cached values immutable.**
- DTO is just a name; **mutable DTOs still carry risk** if the backend keeps the same reference.
- In Java 17+, `record` is a readable choice for snapshots; protect collections and nested objects with appropriate copies.
- Avoid storing lazy/managed entities directly if cached values must be independent of ORM lifecycles and work across multiple requests or instances.
- **Immutability ≠ freshness**: you still need proper cache keys, `@CacheEvict`/`@CachePut`, TTLs, and post-commit strategies.
- Cache only the fields truly needed, and verify serialization, security, and size.

**References:**

- [Spring Framework 6.2 – Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html)
- [Spring Framework 6.2 – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework – ConcurrentMapCache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Java 17 – List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java 17 – Records](https://docs.oracle.com/en/java/javase/17/language/records.html)
