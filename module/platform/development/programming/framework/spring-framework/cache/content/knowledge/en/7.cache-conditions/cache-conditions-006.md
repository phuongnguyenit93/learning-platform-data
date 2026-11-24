# `#result` of `Optional` and the Safe Navigation Operator in Spring Cache

## 1. Lesson Objectives

When a Spring Cache method returns `Optional<T>`, caching conditions must account not only for what the method returns, but also for **how Spring represents that result in SpEL**. A common mistake is writing `unless = "#result.isEmpty()"` assuming `#result` is an `Optional`. In cache annotations, that is incorrect: for Spring-supported wrapper types like `Optional`, **`#result` points to the business value inside the wrapper**. `Optional.empty()` is represented as **`null`** when evaluating `#result` in cache expressions that have access to the result.

This lesson explains three points related to **Caching Conditions**:

1. `condition` and `unless` are evaluated at different times; `#result` is only available where a result exists.
2. For `Optional<T>`, checks on `#result` must target `T` or `null`, not `Optional.isPresent()`/`isEmpty()`.
3. SpEL `?.` (safe navigation) prevents errors when dereferencing `null`; however, it only guards the operation it is attached to and does not decide on its own whether empty results should be cached.

By the end of this lesson, you will be able to predict cache hits/misses with `Optional.of(...)` and `Optional.empty()`, write safe `unless` expressions, accurately test how many times the real method is called, and avoid confusing Spring Cache's unwrapping rule with SpEL's `Optional` safe-navigation support across Spring versions.

## 2. Where `#result` Fits in the Cache Processing Flow

`@Cacheable` typically runs: evaluate condition on arguments → find entry by key → if hit, immediately return cached value → if miss, invoke method → evaluate `unless` on the **newly computed result** → store if not vetoed. Method invocation may not happen on a cache hit, so there is no "new method result" on which to evaluate `unless` on a normal hit path.

~~~mermaid
flowchart TD
  A[Caller invokes bean via proxy] --> B{Is condition true?}
  B -- No --> C[Invoke method and return result]
  B -- Yes --> D[Resolve cache and key]
  D --> E{Cache hit?}
  E -- Yes --> F[Return result from cache]
  E -- No --> G[Invoke real method]
  G --> H[Unwrap supported wrapper for result context]
  H --> I{Does unless evaluate to true?}
  I -- Yes --> J[Do not put; still return method result]
  I -- No --> K[Put result per provider policy]
  K --> L[Return method result]
  J --> L
~~~

The diagram illustrates a standard synchronous `@Cacheable` flow. Real cases also include `sync=true`, multiple operations, cache errors, `CompletableFuture`/reactive return types, and conditions across multiple caches. The diagram focuses on when `#result` is evaluated.

| Expression location | When evaluated? | Is `#result` available? | Purpose |
| --- | --- | --- | --- |
| `@Cacheable(condition = "...")` | Before lookup/method call, based on inputs | **No** | Decide whether to apply caching for this invocation |
| `@Cacheable(key = "...")` | When determining the key for lookup | **No** | Select the entry to read; usually uses arguments |
| `@Cacheable(unless = "...")` | After the method completes on the entry-creation branch | **Yes** | Veto writing the new result to the cache |
| `@CachePut(key = "...")` | For writing the result after invocation | **Available** | Select key based on result or inputs |
| `@CachePut(unless = "...")` | After invocation | **Yes** | Veto writing the result |
| `@CacheEvict(key = "...", beforeInvocation = false)` | After invocation | **Yes** | Select entry to evict based on result if appropriate |
| `@CacheEvict(beforeInvocation = true)` | Before method | **No** | No result to reference |

`@CacheEvict` **does not have an `unless` attribute**. Expressions like `condition` control the operation at the appropriate point; do not use `#result` in `@Cacheable`'s `condition` or expect it to exist before the method runs.

## 3. `#result` with `Optional<T>`: Value `T` or `null`

Consider this declaration (snippet must live inside a Spring bean with matching `Book` and `repository`):

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.archived() == true"
)
public Optional<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Suppose `Book` has a method `archived()` returning `boolean`. Three important cases:

| Java value returned by method | `#result` value in `unless` | `#result == null` | `#result?.archived() == true` | Outcome |
| --- | --- | --- | --- | --- |
| `Optional.of(bookActive)` | `bookActive` (type `Book`) | false | false | Put allowed |
| `Optional.of(bookArchived)` | `bookArchived` (type `Book`) | false | true | Put vetoed |
| `Optional.empty()` | `null` | true | false (safe navigation returns `null`; compared with `true` is false) | Put vetoed |

Note: `#result` is **not `Optional<Book>`** in the context above. Therefore:

~~~java
// Semantically wrong when declared to return Optional<Book>:
@Cacheable(cacheNames = "books", unless = "#result.isEmpty()")

// Correct when you want not to store Optional.empty() results:
@Cacheable(cacheNames = "books", unless = "#result == null")

// Correct when you want to skip both empty results and archived books:
@Cacheable(
    cacheNames = "books",
    unless = "#result == null || #result?.archived() == true"
)
~~~

The lines above are **illustrative annotation snippets**, not standalone Java source. The first expression can throw a SpEL error when `#result` is `null` or when `Book` has no `isEmpty()` method. You cannot infer `#result`'s methods directly from the API of the method's declared wrapper return type.

**When the result is not `Optional`:** for a method returning `Book`, `#result` is `Book` or `null` depending on the actual return value. If a method returns a custom wrapper for which Spring Cache has no unwrapping rule, do not assume `#result` is the inner element. Verify behavior against the actual framework and wrapper type.

### Is `Optional.empty()` Cached or Not?

Spring Cache supports `Optional`: when present, the cache handles the inner value; when empty, it handles a `null` result so the cache provider can store it if configured to support null. **Without an `unless` veto, a not-found lookup can be cached** (negative caching). For example, the default `ConcurrentMapCacheManager` can store null values via an internal mechanism; subsequent calls can still hit and be adapted back to `Optional.empty()` by Spring. Do not assume all providers cache null identically: null storage, serialization, and TTL depend on the backend.

Both policies are valid depending on needs:

- **Do not cache misses:** `unless = "#result == null"`. Suitable when new data may appear soon and you want the next call to retry immediately.
- **Allow caching misses:** omit the null veto if the provider supports it. Reduces repeated queries for non-existent IDs, but can preserve a "no data" state until TTL expiration or eviction. Design invalidation when new records are created.

`unless` decides **whether to write or not write** after invocation; it does not turn an `Optional.empty()` into an exception and does not alter the value returned to the caller.

## 4. How Does the SpEL `?.` Operator Work?

`?.` is the **null-safe navigation** operator in Spring Expression Language. When the object on the left is null, the operator returns `null` for that specific property/method access instead of attempting to invoke on null.

Expression examples:

~~~text
#result.name             // normal access; errors if #result == null
#result?.name            // null when #result == null
#result?.isArchived()    // null when #result == null
#result?.price           // gets price if object exists; null otherwise
~~~

These are **illustrative SpEL expressions**, not Java syntax. When `Book` is a Java record, the reliable approach is calling the accessor `#result?.archived()`; for a Java bean with a `getName()` getter, property style `#result?.name` works.

### 4.1. Safe Navigation Protects Each Individual Link

Expression:

~~~text
#result?.owner.address.city
~~~

**Not completely safe.** If `#result` is null, `#result?.owner` yields `null`, yet the remaining `.address.city` is still evaluated, which can cause an error. If `owner` is null, `.address` also fails.

Use instead:

~~~text
#result?.owner?.address?.city
~~~

Or with methods on records:

~~~text
#result?.owner()?.address()?.city()
~~~

Whenever any link marked with `?.` encounters null, that step returns null; subsequent links must also use safe navigation when needed. **`?.` does not automatically short-circuit the entire compound expression.**

### 4.2. A `null` Result Is Not Equal to Boolean `false`

When an expression makes caching decisions, state the policy for null values explicitly.

Examples:

~~~java
// Veto only when archived() is true; empty results are NOT vetoed:
@Cacheable(cacheNames = "books",
           unless = "#result?.archived() == true")

// Veto both empty results and archived books:
@Cacheable(cacheNames = "books",
           unless = "#result == null || #result?.archived() == true")

// Only cache Books with status = ACTIVE and non-null:
@Cacheable(cacheNames = "books",
           unless = "#result == null || #result?.status() != 'ACTIVE'")
~~~

In the last example, assume `status()` returns a `String`. `#result?.status() != 'ACTIVE'` is true if status differs from ACTIVE (including null); the `#result == null` clause makes the intent to exclude `Optional.empty()` explicit. For nested nulls or enum types, adjust the comparison accordingly.

Writing `unless = "#result?.archived()"` appears in Spring docs as a short example, but for complex policies you should explicitly verify how the expression converts to boolean, its nullability, and business data. The `== true` or `== false` style paired with explicit null rules is usually easier to test.

### 4.3. Other Operators Commonly Confused

| SpEL syntax | Meaning | Example |
| --- | --- | --- |
| `?.` | Null-safe property/method access | `#result?.archived()` |
| `?:` | Elvis: choose fallback value when null (per SpEL semantics) | `#result?.nickname ?: 'N/A'` |
| `?.[]` | Null-safe indexing in SpEL versions that support it | `#result?.[0]` |
| `?.?`, `?.!`, `?.^`, `?.$` | Null-safe collection selection/projection, where version-supported | See Spring SpEL docs |

**Do not confuse SpEL's `?.` with Java's `Optional.map(...)` or operators from other languages.** Java 17 has no `obj?.member` syntax; it is valid only **inside SpEL expression strings** parsed by Spring.

## 5. Version Note: SpEL 7.0 and `Optional` in Expressions

There are **two distinct unwrapping mechanisms** that learners often conflate.

**Mechanism A — Spring Cache `#result`:** In result-capable caching expressions, Spring converts supported wrappers like `Optional<Book>` to `Book` or `null` before letting the expression reference `#result`. Thus `#result?.archived()` operates on the `Book` value or null itself; this is Spring Cache's contract and requires no manual `Optional.get()`.

**Mechanism B — SpEL null-safe operator on an actual `Optional`-typed variable:** Spring Framework 7.0 documentation introduces **transparent unwrapping for `Optional` when using null-safe operators**. For example, a SpEL variable `#candidate` literally holding `Optional<Book>`:

~~~text
#candidate?.title
~~~

In Spring Framework 7.0+, if `#candidate = Optional.of(book)`, the null-safe operator can access `title` on the `book` object; if `Optional.empty()`, it returns null. That behavior **differs from Spring Cache preparing `#result`**, which is already unwrapped beforehand. Do not apply that syntax to arbitrary `Optional` variables on Spring 6.x without verifying support; null-safe handling on `Optional` changes across versions.

Also per SpEL 7.0 documentation, methods on the `Optional` API itself, such as `#candidate?.orElse('Unknown')`, remain usable. However, when working with `unless` and `#result` in Spring Cache, **do not try calling `#result.orElse(...)`**: `#result` is already the business value or null.

## 6. Writing `condition`/`unless` Patterns to Match Requirements

Suppose `findBook(String id)` returns `Optional<Book>`, where `Book` has accessors `archived()`, `price()`, and `owner()`. The following patterns are **Spring annotation snippets only**, not standalone programs.

### 6.1. Cache Only When ID Is Non-Blank and Result Is Valid

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null || #result?.archived() == true"
)
~~~

`condition` checks **inputs** before cache lookup. If false, the method runs normally and no cache operation is applied. `unless` runs only when there is a new result to decide whether to store. If `Optional.empty()`, `#result == null` is true so the miss is not cached; if the book is archived, it is not cached either.

### 6.2. Store Result Only When Price Is Within Threshold

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.price() > 1000000"
)
~~~

This example assumes `price()` returns a numeric type comparable with an integer literal as supported by SpEL, and business policy excludes values above the threshold. For `BigDecimal` and real currency, use type-appropriate comparisons and financial rules; do not treat the literal above as complete business encoding.

### 6.3. Based on Potentially Null Nested Properties

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.owner()?.suspended() == true"
)
~~~

If `Book.owner()` returns null, `?.suspended()` continues to guard safely. If business policy requires **not caching books missing an owner**, write the rule explicitly, for example:

~~~text
#result == null || #result?.owner() == null
    || #result?.owner()?.suspended() == true
~~~

A long expression can be placed on a single line in the annotation attribute; line wrapping above is only for readability. Null-safe navigation **prevents errors**, rather than inventing a business policy for missing data.

### 6.4. Checking Enum Status

With `BookStatus` as an enum:

~~~java
@Cacheable(
    cacheNames = "books",
    unless = "#result == null || #result?.status() != T(com.example.BookStatus).ACTIVE"
)
~~~

This snippet requires the real `com.example.BookStatus` enum on the classpath. When adding to a project, substitute the actual class name. You can use `T(package.Enum)` to reference an enum in SpEL instead of comparing arbitrarily against strings. If `status()` is null, being unequal to `ACTIVE` evaluates to true, matching the exclusion policy.

## 7. Runnable Java 17+ Example with Spring Framework: Observing `Optional.empty()`

This example includes two policies to distinguish **veto miss** and **cache miss**. It uses Spring Framework 7.0.9, JDK 17+, and Maven. Create the files at the exact paths below.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>optional-cache-conditions</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>7.0.9</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/demo/OptionalCacheDemo.java`**

~~~java
package demo;

import java.util.Optional;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class OptionalCacheDemo {
    @Bean
    CacheManager cacheManager() {
        // Local cache; allows cached nulls by default.
        return new ConcurrentMapCacheManager("profiles", "negative");
    }

    @Bean
    ProfileService profileService() {
        return new ProfileService();
    }

    public record Profile(String id, boolean hidden) { }

    public static class ProfileService {
        private int loads;
        private int negativeLoads;

        @Cacheable(
            cacheNames = "profiles",
            key = "#p0",
            unless = "#result?.hidden() == true || #result == null"
        )
        public Optional<Profile> find(String id) {
            System.out.println("DB find #" + (++loads) + " " + id);
            return switch (id) {
                case "public" -> Optional.of(new Profile(id, false));
                case "private" -> Optional.of(new Profile(id, true));
                default -> Optional.empty();
            };
        }

        @Cacheable(cacheNames = "negative", key = "#p0")
        public Optional<Profile> findAllowMissing(String id) {
            System.out.println("DB negative #" + (++negativeLoads));
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             OptionalCacheDemo.class)) {
            var service = context.getBean(ProfileService.class);

            System.out.println(service.find("public"));
            System.out.println(service.find("public"));

            System.out.println(service.find("private"));
            System.out.println(service.find("private"));

            System.out.println(service.find("unknown"));
            System.out.println(service.find("unknown"));

            System.out.println(service.findAllowMissing("unknown"));
            System.out.println(service.findAllowMissing("unknown"));
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.OptionalCacheDemo
~~~

Lines printed by the program itself (excluding Maven/framework logs):

~~~text
DB find #1 public
Optional[Profile[id=public, hidden=false]]
Optional[Profile[id=public, hidden=false]]
DB find #2 private
Optional[Profile[id=private, hidden=true]]
DB find #3 private
Optional[Profile[id=private, hidden=true]]
DB find #4 unknown
Optional.empty
DB find #5 unknown
Optional.empty
DB negative #1
Optional.empty
Optional.empty
~~~

**Exact interpretation:**

1. First `find("public")`: miss, method runs, `#result` is `Profile(hidden=false)`. `unless` is false, cache is written. Second call hits without incrementing `loads`.
2. `find("private")`: `#result?.hidden() == true`, result is vetoed. Both calls run the method, producing DB find #2 and #3.
3. `find("unknown")`: returns `Optional.empty()`, `#result` in `unless` is null. The `?.` operator returns null, `#result == null` is true, so it is **not** cached; every call runs the method again (#4 and #5).
4. `findAllowMissing("unknown")`: has no `unless`, so the cache allows storing "not found" via `ConcurrentMapCacheManager`'s null support. The second call receives `Optional.empty()` from the cache and does **not** print DB negative #2.

The example configures `@EnableCaching` and retrieves `ProfileService` from the Spring context so calls go through the proxy. Calling `new ProfileService().find(...)` directly or invoking the cacheable method via `this` inside the same bean in default proxy mode can bypass advice and produce different measurements.

## 8. Interaction with `@CachePut`, `@CacheEvict`, and Key SpEL

Although the focus is `@Cacheable` caching conditions, it is important to understand other places where `#result` can appear.

**`@CachePut`** always invokes the business method, then puts the result per the appropriate key/condition. If the method returns `Optional<Book>`, result expressions in supported positions also see the business value inside the wrapper. Example:

~~~java
@CachePut(
    cacheNames = "books",
    key = "#result?.isbn()",
    unless = "#result == null"
)
public Optional<Book> save(BookDraft draft) {
    // Write data and return Optional<Book>
}
~~~

This is a **snippet**; if `#result` is null, the key expression `#result?.isbn()` yields null. Some cache pipelines or expression modes can reject null keys or fail even when you expect `unless` to veto. **Prefer a stable key derived from inputs** (for example `key="#p0.isbn()"`) whenever possible, or test the null branch on your actual Spring version; do not rely on `unless` as a guarantee that every null-producing key expression is valid.

**`@CacheEvict`** runs after the method by default, so it can reference `#result` in its key expression. If `beforeInvocation=true`, no result exists yet; arguments must be used to compute the key. It has no `unless` attribute.

**`@Caching`** can declare multiple operations on one method; each operation has its own evaluation timing. Avoid combining `@Cacheable` and `@CachePut` on the same method unless you understand the exclusion conditions, because one operation tries to skip the method while the other requires running it.

## 9. Common Mistakes When Writing `unless` for `Optional`

| Mistake | Why is it wrong or dangerous? | Better phrasing |
| --- | --- | --- |
| `unless="#result.isEmpty()"` | `#result` is not `Optional` and may be null | `unless="#result == null"` |
| `unless="#result.get().archived()"` | `#result` is already unwrapped; `get()` is invalid on `Book` | `unless="#result?.archived() == true"` |
| `condition="#result != null"` | `@Cacheable` `condition` has no result | Move result rules to `unless` |
| `unless="#result.archived()"` | Null dereference error on `Optional.empty()` | Use `?.` and an explicit null policy |
| `unless="#result?.owner.address.city == 'X'"` | Safe navigation only protects `result` at `owner` | `#result?.owner?.address?.city` if the property chain fits |
| `unless="#result?.archived() == true"` when **wanting to skip null too** | Null does not equal true; empty can still be cached | Add `#result == null || ...` |
| `#result.orElse(null)` | `#result` is no longer an `Optional` | Access `#result` directly |
| Assuming all providers store null | Some backends forbid/differ in representing null | Check the `Cache` implementation and configuration |
| Treating `?.` as access control | Only prevents null errors, does not check authorization | Separate authorization and cache key/scope |
| Confusing `Optional.empty()` with exceptions | Exceptions do not produce a successful result for `unless` | Handle errors/negative caching under separate policies |

Additionally, `@Cacheable(sync=true)` **does not support `unless`**: the synchronized branch coordinates computation according to provider capabilities and has its own configuration restrictions. Do not try adding `unless` to a synchronized operation assuming it will execute like the normal branch.

## 10. Testing Caching Conditions Instead of Just Reading Annotations

A real Spring test suite should prove:

1. **Valid hit:** first call returns `Optional.of(active)`, second call does not run the real method; returned value is still `Optional<...>`.
2. **Attribute veto:** `Optional.of(hidden)` is rejected by `unless`; method runs on every call.
3. **Empty veto:** `Optional.empty()` is rejected by `#result == null`; method runs on every call.
4. **Negative caching:** remove `unless` on a null-supporting provider; second call returns `Optional.empty()` without running the method.
5. **Safe null chain:** result has a null nested property and expression uses `?.` throughout; no SpEL exception occurs.
6. **Version transitions:** test expressions with actual `Optional` variables separately if using Spring 7's specific null-safe syntax; keep them separate from unwrapped `#result` tests.
7. **Invalidation:** when an entity that previously returned `Optional.empty()` is created, the "not found" entry must be evicted or expire per policy.
8. **Proxy:** verify tests invoke the bean retrieved from `ApplicationContext` and do not accidentally bypass advice via self-invocation.

To unit-test expressions without a cache provider, you can use `SpelExpressionParser` and `StandardEvaluationContext`; however, this only tests **pure SpEL**, without reproducing the cache context or `#result` unwrapping rules. To verify real `Optional` `#result` behavior, invoke the annotated method through the caching infrastructure.

Condensed example of a standalone SpEL test (snippet requiring the `spring-expression` dependency):

~~~java
var parser = new org.springframework.expression.spel.standard.SpelExpressionParser();
var context = new org.springframework.expression.spel.support.StandardEvaluationContext();
context.setVariable("result", null);
Object value = parser.parseExpression("#result?.toString()").getValue(context);
System.out.println(value == null); // true
~~~

In that test, if you replace `#result` with an intact Java `Optional`, you are testing the semantics of SpEL operators on `Optional` in the running library version, **not** simulating the `#result` prepared by Spring Cache.

## 11. When Should You Cache `Optional.empty()`?

This ties directly into `unless`:

- For lookups of an invalid ID repeated continuously, negative caching can cut load on databases and upstream services. Use a sufficiently short TTL and invalidation if the record can be created afterward.
- For data that can appear immediately, not caching `Optional.empty()` lets the next request query again, at the cost of higher load.
- For authorized/tenant-scoped data, a "not found" might mean **no permission to see**, not necessarily non-existence. Include the proper scope in the key and never let a negative cache entry from one tenant/role apply to another.
- If the provider does not support null or handles null inconsistently, do not rely on `Optional.empty()` without testing. You can use an explicit domain-specific representation for negative results or choose to skip caching them.
- Monitor hit/miss rates, lifetimes, and repeated query counts instead of defaulting to "always cache empty" or "never cache empty" across every endpoint.

**Especially note:** `unless = "#result == null"` only checks whether the **business value** is null; do not expect this condition to filter other "unhelpful" data such as `INVALID`-status objects, empty collections, negative numbers, or locked entities. If policy requires excluding those, write explicit rules and test each branch.

## 12. Practical Checklist

Before merging a cache annotation on a method returning `Optional<T>`, answer:

- Is `#result` `T` or null? Does any expression call `Optional.isPresent()`, `isEmpty()`, or `get()` out of context?
- Does `condition` rely solely on arguments and pre-invocation context? Does `unless` take full responsibility for the post-result policy?
- Does every nullable place use `?.` properly, including links after the first step in a chain?
- Does the expression clearly state whether empty is **cached** or **vetoed**? `?.` alone does not define that policy.
- Does the provider support caching null? If so, are TTL and invalidation for negative entries reasonable?
- Does the key include all parameters, tenant, and business scope to prevent wrong results or cross-user leakage?
- Is there a Spring context test measuring target method executions across valid `Optional.of`, vetoed `Optional.of`, and `Optional.empty()` branches?
- If using SpEL safe navigation directly on an `Optional` variable (distinct from cache `#result`), does the Spring version support those semantics?

## 13. Official References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `condition`, `unless`, `#result`, `Optional` unwrapping rules, caching SpEL context, and limitations.
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html): `?.`, compound expressions, null-safe method/property access, and changes related to `Optional` starting in Spring 7.0.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): syntax, operators, and evaluation context.
- [Spring Framework — Cacheable Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html): `condition`/`unless` contract and annotation attributes.

Key takeaway when reading code: `@Cacheable` returns `Optional<Book>`, yet inside `unless`, `#result` is **`Book` or `null`**; `#result?.property` guards null access; and the decision of **whether to cache `Optional.empty()`** must be stated via an explicit `unless` policy and tested against the real cache provider.