# Building a Minimal Example Proving Caching Works in Spring Framework

## Target Outcome

This lesson guides you through building **a standalone Java 17 application with Spring Framework Cache** to verify that `@Cacheable` actually prevents a business method from running again when the same key is already in the cache.

Upon completion, you will be able to:
- Create a small Maven project requiring no database, Docker, Redis, or Spring Boot.
- Register a `CacheManager`, enable `@EnableCaching`, declare `@Cacheable`, and invoke a bean through the Spring container.
- Use **an execution counter on the real method** to distinguish a cache miss from a cache hit.
- Re-run the command and compare stdout step by step; know what constitutes proof and what is insufficient to conclude caching works.
- Recognize common setup mistakes such as forgetting `@EnableCaching` or self-invoking a method within the same object.

> **Direct task:** build **the minimal example proving caching works**. Therefore, we use Spring's built-in in-memory cache (`ConcurrentMapCacheManager`), one cached method, and deterministic output measurement. TTL, Redis, distributed caching, and performance tuning are subsequent topics, not prerequisites for this exercise.

## 1. What Counts as "Caching Is Working"?

You cannot conclude caching works simply because `@Cacheable` was added or because two calls returned the same string. An uncached method can also return the same result.

We must observe **whether the real business code is skipped**. Suppose a book-lookup method takes `bookId`; each time it genuinely executes, it increments `realLoads` and prints a line starting with `LOAD`.

Verification scenario:

| Call | Argument | Expectation | Real method executions after call |
| --- | --- | --- | ---: |
| 1 | `find("A")` | Cache miss: load data and write entry for key A | 1 |
| 2 | `find("A")` | Cache hit: return stored result, **do not re-run** method body | 1 |
| 3 | `find("B")` | Cache miss: key B differs from key A | 2 |
| 4 | `find("A")` | Cache hit again for key A | 2 |

Thus the decisive signal is **four calls from `main` yet only two real method executions**. We also add an automated check: if the execution count is not 2 or the results for A differ, the program throws an error.

### Participating Components

~~~text
main()
  |
  | calls Spring-managed bean
  v
Spring proxy (CacheInterceptor)
  |
  | @Cacheable(cacheNames = "books")
  | builds key from bookId parameter
  v
CacheManager -> "books" cache (ConcurrentMapCache)
  |
  +-- key exists (HIT)   -> return cached value
  |
  +-- key missing (MISS) -> run find(bookId) method
                           -> increment realLoads, print LOAD
                           -> store result, return
~~~

`@EnableCaching` enables cache annotation processing; `CacheManager` provides the `books` store; `@Cacheable` declares the method and target store name. Under the default proxy configuration, only calls passing **through the Spring proxy** are intercepted. <https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html>

## 2. Environment Requirements and Project Structure

- **JDK 17+** (e.g., JDK 17 or 21).
- **Apache Maven** working in the terminal.
- Network access on the first Maven run to fetch dependencies not yet in the local repository.

Verify:

~~~bash
java -version
mvn -version
~~~

Create the directory and two files as follows:

~~~text
spring-cache-proof/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheProof.java
~~~

The class name `CacheProof` must match the file name `CacheProof.java`; `package demo;` corresponds to the `demo/` directory.

The example uses **Spring Framework 6.2.16** (running on Java 17+) with only the Spring dependency `spring-context`. Caching via `ConcurrentMapCacheManager` is built into Spring Framework, so this lesson needs no third-party cache library.

## 3. The `pom.xml` File

Create `pom.xml` directly inside `spring-cache-proof/`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-proof</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

`spring-context` brings along the required Spring dependencies, including the AOP infrastructure used by cache annotations. `maven.compiler.release=17` targets Java 17 compilation. `exec-maven-plugin` runs `main` with a single Maven command without manually assembling the classpath.

## 4. Complete Java Source: `CacheProof.java`

Create `src/main/java/demo/CacheProof.java` with the **entire** following content:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheProof {

    @Configuration
    @EnableCaching
    public static class CacheConfig {

        @Bean
        public CacheManager cacheManager() {
            // Create a cache named "books" in JVM memory.
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookCatalog bookCatalog() {
            // Let Spring manage and create a proxy for this bean.
            return new BookCatalog();
        }
    }

    public static class BookCatalog {
        private int realLoads = 0;

        @Cacheable(cacheNames = "books")
        public String find(String bookId) {
            realLoads++;
            System.out.println("LOAD bookId=" + bookId
                    + " count=" + realLoads);
            return "book-" + bookId + "-version-" + realLoads;
        }

        public int realLoads() {
            return realLoads;
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            // Important: get the bean from the Spring container, do not new BookCatalog().
            BookCatalog catalog = context.getBean(BookCatalog.class);

            String first = catalog.find("A");
            System.out.println("first=" + first);

            String second = catalog.find("A");
            System.out.println("second=" + second);

            String other = catalog.find("B");
            System.out.println("other=" + other);

            String again = catalog.find("A");
            System.out.println("again=" + again);

            System.out.println("realLoads=" + catalog.realLoads());

            if (!first.equals(second)
                    || !first.equals(again)
                    || catalog.realLoads() != 2) {
                throw new IllegalStateException("Cache verification FAILED");
            }

            System.out.println("CACHE_OK");
        }
    }
}
~~~

This code is a **complete program** that compiles and runs with no real database dependency. The `realLoads` variable represents the number of data-source queries—enough to prove the cache skips work on hits. In a real system, the `return` logic of `find` can be replaced with a DB query or an observable HTTP call.

### Explaining the Four Configuration Points

1. **`@Configuration`** marks `CacheConfig` as a class declaring Spring beans.
2. **`@EnableCaching`** activates the infrastructure that intercepts methods with cache annotations. Adding `@Cacheable` without this activation produces no annotation-based caching effect.
3. **`@Bean CacheManager`** returns `ConcurrentMapCacheManager("books")`: a manager providing a cache store named `books`, storing data in the current process's memory.
4. **`@Cacheable(cacheNames = "books")`** tells Spring: on each `find` call, look up the result by key in `books`; on hit return it directly, on miss run the method body and store the result.

For a method with a single **non-null parameter** `String bookId`, the default key is the `bookId` string itself. Thus `"A"` and `"B"` are two distinct entries.

`BookCatalog` is a `public`, non-`final` class; `find` is also `public`, non-`final`. This shape is compatible with class-based proxies when a bean does not declare an interface. **Do not call `new BookCatalog()` from `main`**: manually instantiating the object means calls will not go through Spring's proxy.

## 5. Run and Verify the Exact Output

Open a terminal in the directory containing `pom.xml` and run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheProof
~~~

The **stdout written by the program** must consist of exactly these eight lines (excluding separate Java/Maven notices if your environment prints extra logs):

~~~text
LOAD bookId=A count=1
first=book-A-version-1
second=book-A-version-1
LOAD bookId=B count=2
other=book-B-version-2
again=book-A-version-1
realLoads=2
CACHE_OK
~~~

Interpretation of each call:

| Call | What does Spring do? | Direct evidence |
| --- | --- | --- |
| `find("A")` 1st time | Miss; runs `find` body, caches `book-A-version-1` | `LOAD bookId=A count=1` appears |
| `find("A")` 2nd time | Hit; returns stored value | `second=book-A-version-1`; **no second LOAD line for A** |
| `find("B")` | Miss because key B does not exist yet | `LOAD bookId=B count=2` appears |
| `find("A")` 3rd time | Hit for A; still the value from the first call | `again=book-A-version-1`; **no third LOAD line for A** |

Two independent pieces of evidence reinforce each other:

- **Execution trace:** only two `LOAD` lines appear even though `find` was called four times.
- **Counter and assertion:** `realLoads=2`, ending with `CACHE_OK`. If the check fails, the program throws `IllegalStateException` instead of printing `CACHE_OK`.

`CACHE_OK` means **caching worked inside one ApplicationContext, for sequential calls and the two keys in this example**. By itself it does not prove performance under heavy load, TTL, synchronization across multiple machines, or consistency with a database.

### Why Is a Counter Needed?

If the business code always returned `"book-A"`, two calls would return the same result even without a cache. In this example, `realLoads` increments only when **the real method body executes**. The gap between four calls and two increments is observable proof, not merely an inference from the annotation being present.

To make the evidence even clearer, you can record all three details: the input key, each `LOAD` line, and the real method execution count. When replacing the mock source with a database, a query counter or SQL logs can serve the same role.

## 6. Control Check: Disable Caching to See the Test Catch Failures

The goal of the control check is to answer: **If caching stops working, does the test above catch it?**

In `CacheConfig`, temporarily **remove or comment out `@EnableCaching`**, then run the same command again. Now `@Cacheable` is not activated through the annotation infrastructure; every `find` call runs the method body. You will see four `LOAD` lines, `realLoads=4`, and the error:

~~~text
java.lang.IllegalStateException: Cache verification FAILED
~~~

The four calls increment `realLoads` to 1, 2, 3, and 4 in turn. Because `realLoads() != 2` evaluates to true, the program throws an exception and **does not print `CACHE_OK`**. This control check catches when annotations are inactive.

Restore `@EnableCaching` after the experiment to return to the original program. Simply restarting the process gives a fresh ApplicationContext and cache store, so no manual data cleanup is needed for this lesson.

> **Note:** `@Cacheable` declares intent, whereas `@EnableCaching` and the proxy provide the execution mechanism. A `CacheManager` bean existing in the context is not enough to conclude annotation caching is enabled.

## 7. Verifying the Cache Holds the Entry (Optional)

The counter in Section 5 already proves caching behavior. If you want to inspect the entry directly, you can add the following snippet **inside `main`'s `try` block after the `find` calls**:

~~~java
CacheManager manager = context.getBean(CacheManager.class);
org.springframework.cache.Cache books = manager.getCache("books");

if (books == null) {
    throw new IllegalStateException("Missing cache: books");
}

System.out.println("cachedA="
        + books.get("A", String.class));
~~~

With the generated data, the extra line is:

~~~text
cachedA=book-A-version-1
~~~

This snippet is an extension, **not part of the standard eight-line stdout in Section 5**. It uses `CacheManager` to access `books` and fetch key `"A"`. Seeing the entry confirms the result was stored; confirming the real method was skipped should still rely on `realLoads`.

`getCache("books")` can return `null` if the manager does not know the store name; therefore the check handles that case explicitly.

## 8. Why Does This Example Run Without Spring Boot or Redis?

Spring Framework provides the **Cache Abstraction** (`Cache`, `CacheManager`, `@Cacheable`, `@EnableCaching`) and the basic `ConcurrentMapCacheManager` implementation. We manually register the two beans `CacheManager` and `BookCatalog` in `CacheConfig`, then create an `AnnotationConfigApplicationContext`.

This suffices to verify caching in a single JVM. **Spring Boot is not required**. Using Spring Boot, starters, auto-configuration, and `spring.cache.*` properties can reduce configuration boilerplate, but that is a different setup path. To keep a minimal verification example easy to analyze, we declare every key component explicitly.

Intentional limitations of `ConcurrentMapCacheManager` in this example:

- Stores entries in the RAM of **one JVM**; restarting the process loses cached data.
- Does not natively provide TTL/time-based expiration or capacity limits; do not interpret stale data persisting as a bug.
- Does not automatically synchronize entries across multiple application instances.
- Suitable for understanding mechanics or basic verification. For TTL, eviction policies, observability, and cross-instance sharing, choose an appropriate provider such as Caffeine/Redis and configure it separately.

`@Cacheable(cacheNames = "books")` only chooses the logical store and how results are used. **A cache name does not set TTL, entry limits, or distributed caching strategies.**

## 9. Mistakes That Easily Skew Experiment Results

| Symptom | Common cause | Correct fix |
| --- | --- | --- |
| Every call for A prints `LOAD` | Missing `@EnableCaching` or method is not intercepted by a proxy | Check the annotation on `@Configuration`; always call the bean obtained from the Spring context |
| `new BookCatalog().find("A")` does not cache | Object instantiated manually, bypassing the Spring proxy | Use `context.getBean(BookCatalog.class)` |
| Calling `this.find("A")` from another method in the same class misses cache | **Self-invocation** bypasses the proxy in default mode | Move the call to another bean or redesign service boundaries |
| `@Cacheable("books")` yet Spring cannot find the cache | Store name on annotation does not match cache manager configuration | Match `books` in `ConcurrentMapCacheManager("books")` |
| Two runs with the same input re-execute after every restart | Cache exists only in the current process | Execute consecutive calls within **the same** ApplicationContext |
| Using two different keys and expecting shared results | Default key is based on parameters | Use the same string `"A"` when testing hits; `"B"` is only to illustrate a miss |
| Concluding a hit merely from two equal return strings | The underlying function might return deterministic values | Use a counter, logging in the method body, or real query counts |
| Placing annotation on a private or unproxyable method | Proxy mechanism limits (visibility/`final`/self-invocation) | Use a public method, non-final class, called through the proxy bean |
| Expecting an entry to expire automatically after a few seconds | Example configures no TTL | To test TTL, switch to a TTL-capable provider and configure an explicit policy |

Also avoid relying on `Thread.sleep` or random execution timing as the sole proof. A deterministic counter makes results faster and more reliable to reproduce. When benchmarking performance, run multiple iterations with warm-up, steady load, and proper metrics; this minimal lesson focuses on verifying **cache hit/miss semantics**.

## 10. Self-Check Exercises

### Exercise 1 — Change Key to Trigger a New Miss

In `main`, try adding a `catalog.find("C")` call **before printing `realLoads`**. Predict that real method executions will increase from 2 to 3. Also update the assertion condition accordingly if you want the program to finish with `CACHE_OK`. Reason: C does not yet have an entry in `books`.

### Exercise 2 — Call B Again

Add `catalog.find("B")` after B has already been called once in the same context. Because entry B already exists, the counter **does not increment**. Thus the cache stores results per key rather than merely remembering the last call's value.

### Exercise 3 — Compare Running via Spring vs. Directly

Keep the baseline code as a control. Then, in a separate experiment, replace the bean from `context.getBean` with `new BookCatalog()`. Every call will run the real method; the counter will no longer be 2. This illustrates the role of the Spring proxy.

### Exercise 4 — Answer Yourself

1. Why can't you conclude caching works just from `@Cacheable` being present?
2. In the code above, which component provides the `books` cache and which activates annotation processing?
3. Why isn't calling `find("A")` then `find("B")` considered a cache hit?
4. If `@EnableCaching` is removed, what is the result of the check at the end of the program?
5. Why does this test not prove a multi-instance system has a shared cache?

**Core answers:** (1) Proof that the real method is skipped is required; (2) `ConcurrentMapCacheManager` and `@EnableCaching`; (3) two different keys; (4) `realLoads=4`, verification fails; (5) data is stored in each JVM's RAM.

## 11. Completion Checklist

- [ ] Able to run `java -version` and `mvn -version`.
- [ ] Created `pom.xml` and `src/main/java/demo/CacheProof.java` accurately.
- [ ] Program has `@Configuration`, `@EnableCaching`, a `CacheManager` bean, and a `BookCatalog` bean.
- [ ] Method `find` has `@Cacheable(cacheNames = "books")`; `main` obtains the bean via `context.getBean`.
- [ ] Running in the same context: four `find` calls produce **two** `LOAD` lines.
- [ ] Stdout shows `realLoads=2` and `CACHE_OK`.
- [ ] Understand why removing `@EnableCaching` or bypassing the proxy causes verification to fail.

Once these criteria are met, you have **runnable, observable, and controlled proof** that Spring Cache Abstraction works in a minimal setup.

### Official Documentation

- [Spring Framework — Declarative annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring cache storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Cache abstraction overview](https://docs.spring.io/spring-framework/reference/integration/cache.html)