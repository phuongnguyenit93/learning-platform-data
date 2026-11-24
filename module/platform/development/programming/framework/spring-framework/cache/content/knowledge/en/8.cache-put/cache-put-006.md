# Behavior When a Method Throws an Exception with `@CachePut`

## 1. Key Takeaway

In the Spring Framework, `@CachePut` marks a method whose **return value after successful execution** will be placed into the cache, subject to `condition` and `unless`. Unlike `@Cacheable`, `@CachePut` **does not use a cache hit to skip the method body**: every call intercepted by Spring under normal caching mechanics still invokes the target method.

If **the method body throws an exception instead of returning normally**, Spring **does not perform a cache put for the result of that failed call**. The exception propagates to the caller according to standard exception mechanics, unless another layer catches/handles it.

Do not conflate three distinct points:

1. **No new cache put:** because the method did not return a normal result to store.
2. **No automatic deletion of the old entry:** `@CachePut` is not `@CacheEvict`; an existing entry may remain and continue being read.
3. **No guaranteed rollback of non-cache data:** if the method already mutated the database, called an API, wrote a file, or emitted an event *before throwing the exception*, those side effects may persist without an appropriate transaction/compensation mechanism.

Short example:

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product updateProduct(String id, String title) {
    repository.save(id, title);
    throw new IllegalStateException("Cannot finish update");
}
```

*This illustrates behavior, not a standalone program: `Product` and `repository` are not defined.*

When the `throw` statement executes, the method does not return a `Product`; therefore, **there is no result for `@CachePut` to write to the cache**. However, `repository.save(...)` was already called; whether that mutation rolls back depends on the transaction, repository, and infrastructure in use, **not on `@CachePut` itself**.

## 2. Normal execution flow vs. exception-throwing flow

In a synchronous scenario, the call comes from another bean through the Spring proxy:

```text
Caller
  |
  v
@CachePut Spring cache advice
  |
  |  (may evaluate condition based on input data)
  v
Execute target method
  |
  +-- Completes normally, has return value
  |      |
  |      +-- unless or cache condition rejects store? -> skip put
  |      |
  |      '-- allowed to store -> compute appropriate key -> cache.put(key, result)
  |                                      |
  |                                      '-- return result to caller
  |
  '-- Throws exception
         |
         +-- DO NOT run @CachePut's cache put for the failed call
         |
         '-- exception propagates to caller (if no other catch layer)
```

In some configurations, Spring may resolve the cache or evaluate `condition` **before** calling the method; therefore, you should not state that the interceptor does nothing at all when the method fails. What is guaranteed in the default model is **no `@CachePut` write of a successful result after a call that throws an exception**.

| Case | Does the method run? | `@CachePut` outcome | What the caller observes |
| --- | --- | --- | --- |
| Completes normally, caching allowed | Yes | Writes/replaces entry by key | Receives return value |
| Completes normally, `condition=false` | Yes | No cache write from operation | Receives return value |
| Completes normally, `unless=true` | Yes | No cache write | Receives return value |
| Throws `IllegalArgumentException` before mutating data | Yes | No cache write from failed call | Receives exception |
| Throws exception after mutating non-cache data | Yes | No cache write from failed call | Receives exception; side effects may remain |
| `cache.put` or key expression fails **after method returns** | Yes, may have already completed | Write may fail | Cache-layer exception (distinct from method-body exception) |

The last row is critical when diagnosing issues: **“caller receives an exception” does not always mean “the target method threw an exception”**. An error can come from a Redis connection, serializer, key expression, or cache adapter after the method has already finished.

## 3. What happens to the old cache entry?

`@CachePut` **updates** the cache with the method's new result, but only when annotation processing has sufficient data and conditions to write. Consider a cache that already holds an entry:

```text
products["P1"] = Product("P1", "Old Name", revision=1)
```

A call to `updateProduct("P1", "New Name")` throws an exception. If no other cache operation occurs, a failed `@CachePut` **does not replace** the old entry with `"New Name"` and **does not delete** the entry either:

```text
Before: cache["P1"] = Old Name
Call update -> method throws
After:  cache["P1"] = Old Name   (unless another operation modifies it)
```

Consequences:

- A read method with `@Cacheable(cacheNames="products", key="#p0")` can still **cache hit** and return the old data.
- If the cache did not have key `"P1"` initially, a failing `@CachePut` call does not create that key.
- This is the behavior of the **failed `@CachePut` operation**, not a promise that all cache state is immutable. If another thread concurrently writes or evicts the same key, the final state still depends on contention between operations.

Therefore, distinguish two questions: **Is new data written?** and **Is old data deleted?** When `@CachePut` throws an exception, the default answers are **no new result is written** and **the old entry is not automatically evicted**.

## 4. Exceptions before and after mutating the database

Two cases have the same outcome at the `@CachePut` layer (no new cache write) but very different consequences for source data.

### 4.1. Throwing an exception before mutating data

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product rename(String id, String newTitle) {
    if (newTitle.isBlank()) {
        throw new IllegalArgumentException("Title is required");
    }
    return repository.rename(id, newTitle);
}
```

If `newTitle` is blank and the method throws immediately on input validation, the repository is not called. Assuming no other side effects, both the database and the cache remain unchanged.

### 4.2. Throwing an exception after mutating data

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product rename(String id, String newTitle) {
    Product saved = repository.rename(id, newTitle);
    externalNotifier.send(saved);  // may fail
    return saved;
}
```

*Both examples above are illustrative only. `Product`, `repository`, and `externalNotifier` must be defined to compile.*

If the repository write succeeded and `externalNotifier.send(...)` throws an exception, `rename` **does not return `saved`**, even though the local variable `saved` held a value internally. `@CachePut` does not write to the cache from that local variable; Spring can only observe either a normal completion or an exception. If the data write is not rolled back, the database may contain `"New Name"` while the cache still holds `"Old Name"`.

**Common misconception:** thinking `@CachePut` is responsible for synchronizing the database and cache on an all-or-nothing basis. It provides neither distributed transactions nor automatic rollback for method side effects.

If the method runs inside a transaction and the exception triggers a rollback, database changes can be undone per the transaction manager's rules. By default, Spring transactions typically roll back on `RuntimeException` and `Error`, whereas checked exceptions require explicit configuration (such as `rollbackFor`), depending on version/configuration. Do not infer rollback behavior solely from the presence of `@CachePut`.

## 5. `#result`, `key`, `condition`, `unless` when an exception occurs

Spring Cache uses SpEL for keys and conditions, but expressions referencing the **return value** only have data if the method produced a result:

```java
@CachePut(
    cacheNames = "products",
    key = "#result.id()",
    unless = "#result == null"
)
public Product saveProduct(ProductDraft draft) {
    return repository.save(draft);
}
```

*Illustrative snippet: types and repository are not declared.*

If `repository.save(draft)` returns a `Product` normally, Spring can extract `#result.id()` as the key and evaluate `unless` to decide whether to store. If `saveProduct` throws an exception:

- There is no successful method `#result` to build a new write key.
- The `unless` expression is not a `catch` block or error handler; it cannot be used to turn an exception into a valid result.
- No cache put is executed for the exception-throwing call.
- The exception still propagates; handle it at the appropriate business/API layer.

Distinction table:

| Component | Role when method **returns normally** | Role when method **throws** |
| --- | --- | --- |
| `condition` | Decides whether to apply cache operation, usually from input data | Does not catch exceptions; if false, method still runs and can still throw |
| `key = "#p0"` | Computes key from argument | Does not cause a cache put when there is no return value |
| `key = "#result.id()"` | Computes key from result when result exists | No successful result to compute put key |
| `unless = "#result == null"` | Rejects write when method returns `null` | **Not** an exception check or rollback |
| `@CachePut` | Calls method and may put | Does not put result of exception-throwing call |

Note: even when choosing a key from an argument instead of `#result`, a failing call still has no successful return value to store. The issue is not key syntax, but **the method's execution outcome**.

## 6. Runnable Java 17+ example: comparing three scenarios

The example uses **Java 17**, **Spring Boot 3.3.5**, Maven, and `ConcurrentMapCacheManager` in a single JVM. A map acts as the “database” to intentionally illustrate **mutating data and then throwing**, without automatic transactions.

We have:

- `find` using `@Cacheable` to observe cache hits.
- `rename` using `@CachePut(key="#result.id()")` to update the entry after the method returns normally.
- Three modes: **BEFORE** error (before mutating data), **AFTER** error (data mutated, then throws), and **SUCCESS** (returns normally).

### 6.1. Project structure

```text
cacheput-exception-demo/
├── pom.xml
└── src/main/java/example/cacheputerrors/
    ├── Application.java
    ├── Product.java
    └── ProductService.java
```

### 6.2. `pom.xml`

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
    <artifactId>cacheput-exception-demo</artifactId>
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

### 6.3. `src/main/java/example/cacheputerrors/Product.java`

```java
package example.cacheputerrors;

public record Product(String id, String title, int revision) {}
```

### 6.4. `src/main/java/example/cacheputerrors/ProductService.java`

```java
package example.cacheputerrors;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public enum Mode {
        BEFORE, AFTER, SUCCESS
    }

    private final Map<String, Product> database = new ConcurrentHashMap<>();

    public ProductService() {
        database.put("P1", new Product("P1", "Original", 1));
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        System.out.println("DB_READ " + id);
        return database.get(id);
    }

    @CachePut(cacheNames = "products", key = "#result.id()")
    public Product rename(String id, String title, Mode mode) {
        System.out.println("METHOD_" + mode + " " + id);

        if (mode == Mode.BEFORE) {
            throw new IllegalStateException("before mutation");
        }

        Product current = database.get(id);
        if (current == null) {
            throw new IllegalArgumentException("Unknown product: " + id);
        }

        Product changed = new Product(id, title, current.revision() + 1);
        database.put(id, changed);

        if (mode == Mode.AFTER) {
            throw new IllegalStateException("after mutation");
        }

        return changed;
    }
}
```

### 6.5. `src/main/java/example/cacheputerrors/Application.java`

```java
package example.cacheputerrors;

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
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(ProductService products) {
        return args -> {
            System.out.println("READ1 -> " + products.find("P1"));
            System.out.println("READ2 -> " + products.find("P1"));

            try {
                products.rename("P1", "Rejected", ProductService.Mode.BEFORE);
            } catch (IllegalStateException ex) {
                System.out.println("ERROR1 -> " + ex.getMessage());
            }

            System.out.println("READ3 -> " + products.find("P1"));

            try {
                products.rename("P1", "DatabaseOnly", ProductService.Mode.AFTER);
            } catch (IllegalStateException ex) {
                System.out.println("ERROR2 -> " + ex.getMessage());
            }

            System.out.println("READ4 -> " + products.find("P1"));

            System.out.println(
                "PUT -> " +
                products.rename("P1", "Committed", ProductService.Mode.SUCCESS)
            );
            System.out.println("READ5 -> " + products.find("P1"));
        };
    }
}
```

### 6.6. Run command and stdout

In the `cacheput-exception-demo` directory, using JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Lines emitted by the example program in **exact order** (Spring Boot also emits startup logs):

```text
DB_READ P1
READ1 -> Product[id=P1, title=Original, revision=1]
READ2 -> Product[id=P1, title=Original, revision=1]
METHOD_BEFORE P1
ERROR1 -> before mutation
READ3 -> Product[id=P1, title=Original, revision=1]
METHOD_AFTER P1
ERROR2 -> after mutation
READ4 -> Product[id=P1, title=Original, revision=1]
METHOD_SUCCESS P1
PUT -> Product[id=P1, title=Committed, revision=3]
READ5 -> Product[id=P1, title=Committed, revision=3]
```

### 6.7. Step-by-step output explanation

**Step 1 — READ1 and READ2.** The first read misses, so `find` prints `DB_READ P1`, returns `Product(... Original, revision=1)`, and stores it in `products["P1"]`. The second read hits, skipping the body of `find`, so no additional `DB_READ` prints.

**Step 2 — BEFORE.** `rename(..., BEFORE)` still enters the method body even though the cache holds key `P1`: `@CachePut` does not skip a method on a hit. After printing `METHOD_BEFORE P1`, the method throws `IllegalStateException` before writing to the map. Spring does not write a new cache entry; the caller catches the error and prints `ERROR1`. `READ3` still hits the `Original, revision=1` entry.

**Step 3 — AFTER.** `rename(..., AFTER)` creates `Product(... DatabaseOnly, revision=2)` and updates the map **before** throwing. Since there is no transaction in the demo, the map mutation persists. However, `@CachePut` does not run the put step for the failing call because the method never returned. Thus `READ4` still hits the **stale cache** `Original, revision=1`. This is an intentional example of **simulated database updated while cache stays stale**.

**Step 4 — SUCCESS.** `rename(..., SUCCESS)` reads the current revision in the map as **2**, increments it to **3**, sets title to `Committed`, and returns `Product` normally. `@CachePut(key="#result.id()")` reads ID `"P1"` from the result and overwrites cache key `P1` with `revision=3`. `READ5` hits the new result with no new `DB_READ` line.

**Note on runnability:** the three Java files have packages matching their file locations; Spring Boot scans the `ProductService` bean; `@EnableCaching` enables the interceptor; the bean is invoked via a Spring-managed bean injected into `CommandLineRunner`, avoiding self-invocation. Expected output has been verified against Java execution order and cache operations; the Maven configuration is complete to run in an environment with JDK/Maven and dependency access. This sample does not simulate real transactions; `ConcurrentHashMap` is used specifically to demonstrate that side effects persist after an exception.

## 7. What if an exception is caught inside the method?

The `@CachePut` contract inspects whether the method **completes with a normal return value**, not how many `catch` blocks occurred internally.

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product updateWithFallback(String id, String title) {
    try {
        return repository.update(id, title);
    } catch (TemporaryServiceException ex) {
        return new Product(id, "Fallback", 0);
    }
}
```

*Illustrative snippet above; `repository` and `TemporaryServiceException` must be declared.*

If the exception is caught inside the method and the method **returns `Product(..., "Fallback", 0)`**, Spring sees a **normal** completion. Without an excluding `condition`/`unless`, `@CachePut` may **write the fallback value into the cache**. This can be either an intentional business decision or a severe bug if fallback data must not replace real data.

If you do not want to cache fallbacks, establish a contract clearly indicating which results may be stored, such as:

- Returning an object with a `success` flag and using `unless = "!#result.success()"` when the method returns normally.
- Using `unless` to veto `null`/placeholder results when appropriate.
- Or letting the exception propagate when the operation genuinely fails and handling it in the caller layer.

Conceptual example with a flagged result:

```java
public record UpdateOutcome(String id, boolean success, String message) {}

@CachePut(cacheNames = "outcomes", key = "#result.id()",
          unless = "!#result.success()")
public UpdateOutcome tryUpdate(String id) {
    return new UpdateOutcome(id, false, "Cannot update");
}
```

*This is illustrative code inside a Spring class/service, not a standalone Java file.*

Because the method above **returns normally** with `success=false`, `unless` decides not to write; this mechanism differs from **throwing an exception**. Design keys/return objects so expressions do not dereference `null`.

## 8. `@Transactional` and cache update timing

Suppose an update operation runs inside a transaction:

```java
@Transactional
@CachePut(cacheNames = "products", key = "#result.id()")
public Product updateProduct(String id, String title) {
    Product saved = repository.rename(id, title);
    validateAfterWrite(saved);  // may throw an exception
    return saved;
}
```

*This snippet is illustrative, not standalone runnable.*

If `validateAfterWrite` throws a runtime exception, the transaction manager can normally mark it for rollback and not commit the database change. Meanwhile, `@CachePut`'s cache put will not run because the method threw an exception.

However, distinguish between **method completion** and **transaction commit**:

- `@CachePut` is handled by cache advice; `@Transactional` by transaction advice. Advice ordering and how the cache manager integrates with transactions **affect put timing relative to commit**.
- Do not assume that merely stacking both annotations creates an atomic transaction spanning both the database and Redis.
- If the method returns normally but the commit subsequently fails, a cache put executed too early may already hold values from an uncommitted transaction.
- When the cache must update only **after commit**, consider a transaction-aware cache manager (such as `TransactionAwareCacheManagerProxy` or an appropriate provider option), registering post-commit actions, or a coordinated outbox/invalidation model. You must also test concurrency, retries, and system failure modes.

**Rollback rules are not uniform either:** by default `@Transactional` typically rolls back on unchecked exceptions (`RuntimeException`) and `Error`, while checked exceptions usually need `rollbackFor` configured to roll back. If a method catches the error and returns normally, the transaction may commit (unless marked rollback-only). Thus database and cache behavior must be verified against the actual transaction policy, not guessed from the `throw` keyword alone.

## 9. Distinguishing business errors from cache-layer errors

Errors can arise in at least three places:

| Where does the error occur? | Did the target method run? | Cache entry and outcome |
| --- | --- | --- |
| Inside the method, **before returning** | Yes, but failed | `@CachePut` does not write a result from that call |
| In key/expression or in `Cache.put` **after method returns** | Method may have already finished | Put may fail; entry state depends on provider progress/error |
| In other advice/logic before or after method | Depends on ordering | Inspect stack trace and failure point to conclude |

Spring Cache has error-handling mechanisms for cache providers, such as `CacheErrorHandler` where applicable. Default configuration usually propagates errors from cache operations, though an application can supply a custom handler to ignore or log errors. **Do not confuse a cache-store error with a method business exception.**

For example, the method updates the database and returns `Product` successfully, but Redis encounters a network error during `put`:

- The cache may remain un-updated even though the database changed.
- The caller may receive an exception from the cache layer, depending on error-handling setup.
- Blindly retrying the entire operation can cause duplicate side effects (such as creating orders, incrementing versions, or emitting events).

The system needs idempotency handling, controlled retries, and telemetry observability. Do not conclude “the method did not run” solely from an exception type; monitor logs at method entry/exit, database transactions, and cache operations.

## 10. Should you evict the cache when an update fails?

There is no single answer applicable to every system. Evicting the cache depends on **whether the source data actually changed or not**.

**Case A — transaction rolled back completely:** source data is still the old version. The old cache may still be valid; there is no need to delete it just because an exception occurred.

**Case B — data mutation already committed or side effects persist despite method failure:** the old cache may now be wrong. You need a mechanism to determine the true state and invalidate/update accordingly—for example, an orchestrating service that updates and evicts the right key once commit success is known, or reliable event-based synchronization.

**Case C — update outcome is indeterminate (external service timeout):** do not assume failure means “no change happened”. You may need to re-query the source, use idempotent request keys, or refresh the cache under a safe policy.

Quick comparison with `@CacheEvict`:

- `@CachePut`: goal is to **write a new result**; when the method throws, there is no normal result to put.
- `@CacheEvict(beforeInvocation = false)`: defaults to deleting **after the method completes successfully**; if the method throws, no post-invocation eviction runs.
- `@CacheEvict(beforeInvocation = true)`: deletes **before running the method**, so it can still delete even if the method subsequently throws an exception.

Do not arbitrarily use `beforeInvocation=true` as a “cure-all”: it can wipe the cache even when source data did not change at all, increasing misses or causing unintended behavior. Choose a policy based on your consistency requirements.

## 11. Common mistakes when using `@CachePut`

1. **Assuming a cache hit prevents an update.** `@CachePut` always executes the intercepted method; it is not like `@Cacheable`.
2. **Expecting an exception to automatically delete the old cache.** No; `@CachePut` does not auto-evict an entry just because the method failed.
3. **Expecting an exception to automatically roll back the database.** Rollback is the responsibility of transactions/databases, not `@CachePut`.
4. **Catching exceptions and returning a placeholder that gets cached.** With a normal return, `@CachePut` may cache the placeholder; use `unless` or an explicit error contract.
5. **Setting `key="#result.id()"` and thinking the key still evaluates after the method throws.** There is no successful result to write.
6. **Using incompatible read/write cache keys.** If reading by `"P1"` while putting with a different object type, the read method may hit an old entry under another key or miss.
7. **Placing `@CachePut` on a method not intercepted by the Spring proxy.** Self-invocation (`this.rename(...)`) or instantiating with `new` in default proxy mode can bypass cache advice; even successful results will not be put.
8. **Relying on `condition`/`unless` to catch exceptions.** They control cache operations, not Java exception handlers.
9. **Assuming that if the cache was written, the transaction committed.** Advice ordering and transaction awareness must be verified.
10. **Retrying non-idempotent updates when seeing a cache exception.** The method may have already executed side effects successfully before the cache write failed.
11. **Treating every return type as synchronous.** For `CompletableFuture` or reactive return types, Spring Framework 6.1+ supports updating the cache when the value is produced; check your framework version, adapter, and completion/failure representation before mechanically applying this lesson's synchronous diagram.

## 12. Diagnosing issues in real projects

When an update API with `@CachePut` throws an error yet read data remains stale, check in order:

1. **Does the call go through a Spring bean proxy?** Confirm `@EnableCaching` (or equivalent cache config), a Spring-managed bean, and no self-invocation.
2. **Was the method actually invoked?** Place logs at entry, before/after repository calls, before return, and before throw.
3. **Where did the exception originate?** Distinguish an exception inside the method from SpEL key, serialization, cache backend, or other advice errors.
4. **Did the transaction commit or roll back?** Do not look only at the HTTP response; check transaction logs and database state.
5. **Does the old entry still exist?** Use metrics/cache provider tools to inspect the specific cache name and key, avoiding clearing the entire cache arbitrarily.
6. **Were cache conditions satisfied?** `condition` and `unless` can prevent puts **even when the method returns normally**.
7. **Do keys match between read and update?** Compare SpEL and data types, including tenant/locale/version where relevant.
8. **Are there concurrent writers or TTL/eviction?** Avoid drawing conclusions from a single request in multi-instance setups.
9. **Is there a post-failure recovery mechanism?** Decide when to evict/refresh only after knowing what state the actual data is in.

### Design checklist

- **Operations that can throw:** clearly document which changes roll back and which need compensation.
- **Stable cache put key:** write and read keys share the same semantics and namespace.
- **Do not cache normal error results:** use `unless` / explicit result types.
- **Update after commit if needed:** choose reliable transaction-aware caching/invalidation.
- **Observable:** maintain metrics for method invocations, cache puts/hits, transaction outcomes, and provider errors.
- **Test both success and failure paths:** verify cache state and source data, not only HTTP responses.

## 13. Self-check questions

**Question 1.** Cache has `products["P1"] = "Old"`. A `@CachePut` method intends to update it to `"New"` but throws `IllegalStateException` before returning. Will the cache automatically hold `"New"`?

**Answer:** No. `@CachePut` does not put a result for an exception-throwing call. The `"Old"` entry is not automatically deleted by that annotation.

**Question 2.** The method writes to the database successfully, then an external service call throws an exception. Is the database guaranteed to roll back?

**Answer:** You cannot conclude that from `@CachePut` alone. Check whether a transaction wraps the mutation, whether the exception triggers rollback, whether data already committed, and what external side effects occurred.

**Question 3.** A method catches an exception internally and returns `Product("P1", "Fallback", 0)`. Can `@CachePut` store `Fallback`?

**Answer:** Yes. From the interceptor's perspective, the method **returned normally**; if cache `condition`/`unless` allow, the fallback may be put.

**Question 4.** The caller receives an exception after an update. Can you state for certain that `@CachePut` wrote nothing because the method definitely threw?

**Answer:** No. The exception could have occurred **after the method finished**, such as from the cache provider or key expression. Identify the error source using logs/stack traces.

**Question 5.** Does `@CachePut(key="#result.id()")` evaluate `#result.id()` successfully after the method throws an exception?

**Answer:** There is no normal return value to compute the cache put key in that case. Switching to `key="#p0"` will not turn a failing method into a successful put either.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@CachePut`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Javadoc — `TransactionAwareCacheManagerProxy`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
