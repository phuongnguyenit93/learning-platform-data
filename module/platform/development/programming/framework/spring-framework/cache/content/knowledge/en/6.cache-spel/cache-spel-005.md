# Using the Return Value via `#result` in Permitted Contexts

## 1. What Is `#result` and Why Is It Not Available Everywhere?

In Spring Framework cache annotations, Spring Expression Language (**SpEL**) lets you reference arguments via `#p0`, `#p1`, or parameter names, and reference the **method return value** via the special variable `#result` during **certain stages**.

`#result` is **not a Java variable** inside the method body. It is a variable in the **evaluation context provided by Spring Cache** when evaluating annotation expressions. To know whether it can be used, determine accurately: **is the expression evaluated before or after the method produces a result?**

```text
Invocation -> Spring Cache interceptor
             |
             | Before invoking the method:
             |  - knows arguments (#p0, #p1, ...)
             |  - can select cache, compute lookup key, check pre-call condition
             |  - NO method result YET => #result is unavailable
             |
             | If needed: invoke method, obtain return value
             |  - #result is now available
             |
             '-- Evaluate post-call expressions: e.g., @Cacheable unless,
                 @CachePut key, post-invocation @CacheEvict key
```

**Core rule:** An expression that must run **before** the method produces a result cannot reference `#result`. Only expressions running **after** the invocation, in contexts where Spring provides this variable, can use `#result` to inspect the return value or read its properties.

For example, if a method returns a `Book` object, the expression `#result.id()` invokes the `id()` method on the result; `#result == null` checks whether the result is `null`. These two expressions are only meaningful if Spring is providing `#result`.

## 2. Decision Table: When Is `#result` Available?

| Annotation / Attribute | Typical Timing | Can Use `#result`? | Reason |
| --- | --- | --- | --- |
| `@Cacheable(key = "...")` | Before cache lookup / method call | **No** | Must know the key to search the cache before having a result |
| `@Cacheable(condition = "...")` | Before deciding whether to check cache | **No** | Condition gates applying caching before the call |
| `@Cacheable(unless = "...")` | After method executes on a miss | **Yes** | Result is available to decide whether to store it |
| `@CachePut(key = "...")` | After method executes | **Yes** | Spring always runs the method and can derive the key from the result |
| `@CachePut(unless = "...")` | After method executes | **Yes** | Can veto placing the result into the cache |
| `@CacheEvict(key = "...", beforeInvocation = false)` | After method completes successfully | **Yes** | Can choose the key to evict based on the return value |
| `@CacheEvict(key = "...", beforeInvocation = true)` | Before method executes | **No** | Eviction happens before any return value exists |

With `@CachePut`, expressions evaluated after the invocation can reference the result according to the annotation's contract; distinguish this from `@Cacheable(condition=...)`, which is checked before looking up the cache. With `@CacheEvict`, using `#result` in post-processing conditions or keys depends on `beforeInvocation = false`. Identify the specific evaluation context rather than assuming every attribute has the same variables.

**Do not use `#result` inside `cacheNames` as if it were a SpEL expression:** cache names on annotations are cache-name configuration, not an attribute routinely evaluated by Spring as SpEL.

## 3. `@Cacheable(unless = ...)`: Vetoing Storage Based on Return Value

`@Cacheable` checks the cache **before** needing to run the method. On a hit, Spring returns the stored data and skips the method body. On a miss, the method runs and produces a result. At that point, `unless` is allowed to use `#result` to **decide not to cache** the newly produced result.

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.findById(id);
}
```

*This is an illustrative snippet; `Book` and `repository` must be defined. A full runnable example is in Section 7.*

- If `findBook("B-1")` returns a `Book`, `unless` is `false` and Spring can store the object.
- If the method returns `null`, `unless` is `true` and Spring does not cache that `null` return.
- On a cache hit, the method body does not run and `unless` is **not a filter that re-evaluates** already-cached data.
- If the method throws an exception, there is no normal return value for `unless` to inspect; by default `@Cacheable` does not cache exceptions.

Example of choosing not to cache unpublished data:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || !#result.published()"
)
public Book findBook(String id) {
    return repository.findById(id);
}
```

The expression uses a short-circuit **OR** operator: if `#result == null` is true, `!#result.published()` is not evaluated on `null`. If the result is a Java record with a `published()` accessor, method-call syntax works in SpEL.

Understand the exact role of `unless`: it **does not re-run the method**, **does not delete an old entry by default**, and **does not apply to existing cache hits**. It only vetoes the operation of **storing the new value** once the method has produced a result.

## 4. Why Is `@Cacheable(key = "#result.id()")` Wrong?

Consider the following code:

```java
// WRONG: @Cacheable must compute the key before a result exists
@Cacheable(cacheNames = "books", key = "#result.id()")
public Book findBook(String id) {
    return repository.findById(id);
}
```

At the cache lookup step, no `Book` has been produced yet. Spring cannot read `#result.id()` to find an entry before calling the method. Accessing a property on a nonexistent value will fail when the expression evaluates; this is not a valid way to generate a key for `@Cacheable`.

Fix when the method receives an ID:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.findById(id);
}
```

Similarly, you cannot use `@Cacheable(condition = "#result != null")` to decide whether to check the cache: no result exists yet at that stage. If you want **not to store `null` values after execution**, use:

```java
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result == null")
public Book findBook(String id) {
    return repository.findById(id);
}
```

**Do not confuse `condition` with `unless`:**

| Question | Appropriate Tool |
| --- | --- |
| Decide whether to use caching based on *input arguments*? | `condition` (e.g., `#p0.length() < 30`) |
| Decide whether to store a miss result based on *return value*? | `unless` (e.g., `#result == null`) |
| Build a cache lookup key from *input arguments*? | `key` on `@Cacheable` |
| Build a cache write key from the *return value*? | `key` on `@CachePut` |

## 5. `@CachePut(key = "#result.id()")`: Key Computed After Obtaining the Result

Unlike `@Cacheable`, `@CachePut` **always executes the target method** (when the call goes through cache advice), and then updates the cache with the result. Therefore, the method can return an object carrying the ID you want to use as the key:

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book saveBook(String title) {
    return repository.saveNewBook(title);
}
```

*This is an illustrative snippet: `saveNewBook` must return a `Book` with a valid `id()`; `repository` must be implemented.*

In this example, the ID may be generated by the database, so at the start of the call no ID exists yet. Once `repository.saveNewBook(title)` returns `Book`, Spring can evaluate `#result.id()` and write to the cache under that key.

**Points to verify:**

- `@CachePut` **does not skip** the method when an entry already exists; its main purpose is updating the cache with the newly produced result.
- If `#result == null` while the expression accesses `#result.id()`, key computation can fail. For nullable results, design a compatible guard/condition or return a valid object before caching.
- A read method `@Cacheable(cacheNames = "books", key = "#p0")` must be called with the **same key/ID type** to see the entry written by `@CachePut`.
- Do not casually combine `@Cacheable` and `@CachePut` on the same method: the two annotations target conflicting execution behaviors.

## 6. `@CacheEvict`: Using `#result` When Evicting After Invocation

`@CacheEvict` removes entries from a cache. By default `beforeInvocation = false`: Spring evicts the cache **after the method completes successfully**, so it can use the result to determine which key to delete:

```java
@CacheEvict(
    cacheNames = "books",
    key = "#result.id()",
    beforeInvocation = false
)
public Book archiveBook(String id) {
    return repository.archive(id);
}
```

*This is an illustrative snippet; `repository.archive(id)` must return a `Book` with an ID and related classes must be defined.*

Sequence: `archiveBook` runs → returns `Book` → Spring evaluates `#result.id()` → evicts the entry. This is useful when the exact key is only known from the processing result.

If `archiveBook` returns `null`, `#result.id()` is unsafe; ensure a valid result or apply an appropriate post-processing condition. If the method throws an exception and eviction happens after invocation, the operation does not evict the cache by default.

**Invalid case:**

```java
// WRONG: evicting beforehand means #result does not exist yet
@CacheEvict(
    cacheNames = "books",
    key = "#result.id()",
    beforeInvocation = true
)
public Book archiveBook(String id) {
    return repository.archive(id);
}
```

With `beforeInvocation = true`, eviction runs **before the method executes**, regardless of the method's outcome or whether it throws an exception. Thus, keys can only be built from data **known beforehand**, such as `key = "#p0"`.

`@CacheEvict(allEntries = true)` clears the entire cache, so it is not combined with selecting an individual key for that operation.

## 7. Runnable Java 17+ Example: Observing Three Ways to Use `#result`

The example below uses Spring Boot **3.3.5**, Java **17+**, Maven, and an in-memory cache. It demonstrates three goals:

1. `@Cacheable(unless = "#result == null || !#result.published()")`: do not cache missing or unpublished results.
2. `@CachePut(key = "#result.id()")`: use the ID **from the return object** to write the cache after updating.
3. `@CacheEvict(key = "#result.id()")`: use the ID **from the return object** to evict the cache after deleting data.

Structure:

```text
result-spel-demo/
├── pom.xml
└── src/main/java/example/resultspel/
    ├── Application.java
    ├── Book.java
    └── BookService.java
```

**`pom.xml`**

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
    <artifactId>result-spel-demo</artifactId>
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

**`src/main/java/example/resultspel/Book.java`**

```java
package example.resultspel;

public record Book(String id, String title, boolean published) {}
```

**`src/main/java/example/resultspel/BookService.java`**

```java
package example.resultspel;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final Map<String, Book> database = new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public BookService() {
        database.put("A", new Book("A", "Alpha", true));
        database.put("D", new Book("D", "Draft", false));
    }

    @Cacheable(
        cacheNames = "books",
        key = "#p0",
        unless = "#result == null || !#result.published()"
    )
    public Book find(String id) {
        int count = reads.incrementAndGet();
        System.out.println("DB READ " + id + " #" + count);
        return database.get(id);
    }

    @CachePut(cacheNames = "books", key = "#result.id()")
    public Book update(String id, String title) {
        Book book = new Book(id, title, true);
        database.put(id, book);
        System.out.println("DB WRITE " + id + "=" + title);
        return book;
    }

    @CacheEvict(
        cacheNames = "books",
        key = "#result.id()",
        beforeInvocation = false
    )
    public Book remove(String id) {
        Book removed = database.remove(id);
        if (removed == null) {
            throw new IllegalArgumentException("Unknown book: " + id);
        }
        System.out.println("DB REMOVE " + id);
        return removed;
    }
}
```

**`src/main/java/example/resultspel/Application.java`**

```java
package example.resultspel;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            System.out.println("READ A1 => " + books.find("A"));
            System.out.println("READ A2 => " + books.find("A"));
            System.out.println("READ D1 => " + books.find("D"));
            System.out.println("READ D2 => " + books.find("D"));
            System.out.println("PUT => " + books.update("A", "Beta"));
            System.out.println("READ A3 => " + books.find("A"));
            System.out.println("REMOVE => " + books.remove("A"));
            System.out.println("READ A4 => " + books.find("A"));
            System.out.println("READ A5 => " + books.find("A"));
        };
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Program output lines appear in this exact order (excluding Spring Boot startup logs):

```text
DB READ A #1
READ A1 => Book[id=A, title=Alpha, published=true]
READ A2 => Book[id=A, title=Alpha, published=true]
DB READ D #2
READ D1 => Book[id=D, title=Draft, published=false]
DB READ D #3
READ D2 => Book[id=D, title=Draft, published=false]
DB WRITE A=Beta
PUT => Book[id=A, title=Beta, published=true]
READ A3 => Book[id=A, title=Beta, published=true]
DB REMOVE A
REMOVE => Book[id=A, title=Beta, published=true]
DB READ A #4
READ A4 => null
DB READ A #5
READ A5 => null
```

Explanation:

- **READ A1:** first call misses. Method runs and returns `Book("A", "Alpha", true)`, `unless` evaluates to `false` so the value is stored.
- **READ A2:** hit. Method `find` does not run again; no `DB READ` log.
- **READ D1/D2:** runs every time because the result has `published() == false`; `unless` is `true` and vetoes caching.
- **PUT:** `update` always runs, writes to the simulated database, and returns `Book("A", "Beta", true)`. `#result.id()` equals `"A"` so it overwrites entry `books["A"]`. **READ A3** hits and returns `Beta` without querying the database.
- **REMOVE:** `remove` returns the object with ID `"A"` and `@CacheEvict` uses `#result.id()` to remove entry `books["A"]`.
- **READ A4/A5:** `A` is no longer in the database, so the method returns `null`; `unless = "#result == null ..."` vetoes caching, so both calls run the method and increment the counter.

The program uses `ConcurrentMapCacheManager` and therefore only simulates caching within a single JVM; it does not verify TTL, distributed caching, transactions, or serialization strategies. The read counter is printed to prove **whether the method executed or not**. Running the example requires JDK 17+ and Maven; you cannot run `javac` alone on files with Spring dependencies without configuring the classpath.

## 8. `Optional<T>`: `#result` Is the Value Inside the Wrapper

Spring Cache supports recognized wrapper types, notably `java.util.Optional`. When a method returns `Optional<Book>`, the SpEL expression `#result` in post-processing contexts **represents the inner `Book` object** rather than the `Optional<Book>` wrapper itself; for `Optional.empty()`, that value is `null`.

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || !#result.published()"
)
public java.util.Optional<Book> findOptional(String id) {
    return repository.findOptionalById(id);
}
```

*This is an illustrative snippet and will not run standalone because `repository` is not declared.*

If `Optional.of(new Book("A", "Alpha", true))`, `#result` in `unless` represents `Book`. If `Optional.empty()`, the condition `#result == null` is `true`. Do not write `#result.isPresent()` when the context has already unwrapped it: that is an `Optional` method, not a `Book` method.

The safe navigation operator in SpEL helps access properties when the result may be null:

```java
// SpEL safe navigation operator: avoids dereferencing null
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result?.published() == false || #result == null")
public java.util.Optional<Book> findOptional(String id) {
    return repository.findOptionalById(id);
}
```

Choose a concise, readable phrasing for the condition; in this example, `#result == null || !#result.published()` is already clear enough. Verify unwrapping semantics for each async/reactive type and framework version rather than generalizing `Optional`'s rule to every wrapper.

## 9. Practical Pitfalls: Key Choice, Nulls, and Shared Results

**Pitfall 1 — Return value does not share identity with the read key.** Suppose `@CachePut(key="#result.id()")` writes by `String id`, while the read method `@Cacheable(key="#p0")` accepts a `BookRequest` object. The two keys may differ despite having the same business ID. Explicitly enforce a consistent key type, e.g., `#p0.id()` on the read method.

**Pitfall 2 — Result can be null.** With `@CachePut(key="#result.id()")` or `@CacheEvict(key="#result.id()")`, verify the return contract. If null is valid, guard the expression with an appropriate post-processing condition or derive the key from arguments instead of reading a property on null.

**Pitfall 3 — Unstable value.** A method returning a mutable object and using `#result.id` can cause issues if the ID is mutated after the cache operation. Use an immutable ID or a stable snapshot.

**Pitfall 4 — Using `#result` before a result exists.** `@Cacheable(key="#result.id")` and `@Cacheable(condition="#result != null")` fail due to timing. Changing brackets or `#root` syntax cannot make `#result` available earlier.

**Pitfall 5 — Assuming using `unless` re-checks cache hits.** `unless` is only evaluated after the method executes on a call that needed computation; it does not re-read the data source and does not replace invalidation/TTL mechanisms.

**Pitfall 6 — Assuming `#result` belongs to a universal SpEL context.** `#root.args`, `#p0`, and `#result` serve different roles. Parameter names may be unavailable when compiled without `-parameters` metadata; positional syntax `#p0`/`#a0` avoids depending on parameter names.

**Pitfall 7 — Method does not complete normally.** If a method throws an exception, cache actions that run after a successful invocation have no normal return value. Handling cache errors or domain exceptions requires separate logic, not relying on `#result` to “catch” exceptions.

## 10. Workflow for Choosing SpEL Expressions

When writing cache annotations, follow this sequence:

1. **Identify the goal:** look up cache before method, veto storage after method, write after update, or evict after mutation?
2. **Determine the timing:** will the expression run before or after the method? This determines whether `#result` is available.
3. **Select available data:** if running before, use only arguments and corresponding metadata; if running after, `#result` can be used on supported attributes.
4. **Design for null-safety:** can the result be null/empty/throw an exception? Are `unless`, post-processing conditions, or consistent return types needed?
5. **Verify keys across read, put, and evict:** same cache name, same key type, same business meaning.
6. **Verify calls pass through the Spring proxy:** cache annotations are only intercepted when the corresponding Spring configuration is actually active.
7. **Observe empirically:** print counters inside the method body, check hit/miss behavior, and read back the key to confirm behavior.

## 11. Self-Check Questions

**Question 1.** Why is `@Cacheable(key = "#result.id()")` invalid whereas `@CachePut(key = "#result.id()")` can be valid?

Answer: `@Cacheable` must compute the key to search the cache **before** calling the method; at that moment no result exists. `@CachePut` calls the method first and then uses the result to write to the cache.

**Question 2.** Does `@Cacheable(unless = "#result == null")` force a cache hit returning `null` to re-run the method?

Answer: No. `unless` checks the newly produced result after a miss. Whether the provider caches `null` depends on configuration, but `unless` is not a filter that re-runs on hits.

**Question 3.** Can `#result.id()` be used in `@CacheEvict(beforeInvocation = true)`?

Answer: No. Eviction runs before the method, so no result exists yet. Use a key based on arguments, or switch to post-invocation eviction if the business contract allows.

**Question 4.** A method returns `Optional<Book>`; inside `unless`, is `#result` an `Optional<Book>` or a `Book`?

Answer: With `Optional` supported by Spring Cache, it is the inner `Book` when present; `Optional.empty()` is represented as `null`.

**Question 5.** An update method returns `Book(id="A")`, and `@CachePut(key="#result.id()")` writes `books["A"]`. A read method uses `@Cacheable(key="#p0")` and receives `"A"`. Can it hit the newly updated entry?

Answer: Yes, provided `cacheNames="books"` matches, the key has the same type/value, and the cache provider retains the entry. This illustrates that read and write keys must align.

## References

- Spring Framework Reference, *Declarative Annotation-based Caching*, sections *Conditional Caching* and *Available Caching SpEL Evaluation Context*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc, `@Cacheable`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc, `@CachePut`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc, `@CacheEvict`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
