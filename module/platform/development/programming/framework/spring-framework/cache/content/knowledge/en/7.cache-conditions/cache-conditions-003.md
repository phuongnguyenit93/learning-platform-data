# Distinguishing Cache-Bypass Conditions from Business Conditions

## 1. Two Different Questions

In Spring Framework, the `condition` attribute of `@Cacheable` answers the question:

> **Should this invocation participate in cache read/write operations?**

A business rule answers a different question:

> **Is this invocation valid, permitted to execute, and which rules should process it?**

Both types of conditions can appear in the same application, but they do not replace each other. For example, a promotional product whose price changes continuously should **not use the cache**; that is a performance and freshness decision. A user who is not allowed to view partner-only pricing must be **denied access**; that is a business or authorization rule.

```text
Request
  |
  v
Business / access-control checks required for every request
  |-- Invalid: reject or return a business error
  '-- Valid
       |
       v
    Call through Spring cache proxy
       |-- @Cacheable.condition = false
       |      -> skip cache read and write -> run method
       '-- @Cacheable.condition = true
              |-- cache HIT -> return cached data, skip method body
              '-- cache MISS -> run method -> evaluate unless -> may store
```

**Key point:** `condition = false` does **not** mean "refuse to call the method." It means **do not use the cache for this call**. The target method still executes (in normal synchronous flow).

If a business condition lives inside the body of a `@Cacheable` method, a **cache hit can skip that condition entirely**. Therefore, checks that must run on **every request** (such as dynamic authentication/authorization) must sit at a boundary executed before returning any cached result.

## 2. When Does `@Cacheable(condition = ...)` Execute?

An example:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != 'FLASH'"
)
public Integer loadPrice(String sku) {
    return repository.loadPrice(sku);
}
```

*This snippet illustrates the annotation; `repository` must be implemented. A complete runnable example is in section 6.*

The `condition` expression is SpEL and is evaluated **before** the `@Cacheable` cache lookup. `#p0` is the first argument, which is `sku` here.

- `loadPrice("FLASH")`: `condition` returns `false`. Spring **skips both cache lookup and cache put** for this operation, then invokes the real `loadPrice`. Subsequent calls with `"FLASH"` also run the method.
- `loadPrice("STANDARD")`: `condition` returns `true`. Spring checks the `prices` cache with key `"STANDARD"`. On a hit, the method body **does not run**; on a miss, the method runs and the result may be stored.
- `condition` only decides whether to use caching for this operation. It **does not check permissions**, **does not validate business rules**, and **does not prevent database calls** when the expression returns `false`.

This is typically an intentional caching policy: do not cache rapidly changing prices, requests requiring fresh data, test queries, or calls with inputs unsuitable for caching.

Note: `condition` is evaluated using data **available before the method returns**, such as parameters `#p0`, `#p1`, or Spring-supported metadata. Do not use `#result` in `@Cacheable(condition = ...)` because no method result exists yet at that time.

## 3. Where Do Business Conditions Live and What Do They Do?

Business conditions can be:

- **Preconditions:** order quantity must be greater than 0, item code must exist, request must be in the proper state.
- **Calculation rules:** orders of 10 or more items receive a different price tier; user group determines which policy applies.
- **Access control:** whether the caller is allowed to view data for this tenant, account, or customer.
- **Invariants and postconditions:** do not oversell inventory; updated data must satisfy consistency constraints.

There are cases where the result after applying business rules **can be safely cached**. For example, the list price of a standard SKU does not change for 10 minutes and does not depend on the caller. In that case, computing once and reusing makes sense.

However, a rule that **must be re-evaluated on every request** cannot reside only inside a `@Cacheable` method body:

```java
// Dangerous example: permission check can be skipped on a cache hit
@Cacheable(cacheNames = "documents", key = "#p0")
public Document getDocument(String documentId, User caller) {
    permissionService.assertCanRead(caller, documentId);
    return repository.find(documentId);
}
```

*This snippet illustrates a design flaw; `Document`, `User`, `permissionService`, and `repository` are not defined.*

Suppose authorized user A calls `getDocument("DOC-1", A)`, causing the cache to store an entry under key `"DOC-1"`. Later, unauthorized user B calls `getDocument("DOC-1", B)`: on a hit, the method **does not run**, so `permissionService.assertCanRead` **does not run either**. That is a latent access-control vulnerability.

A cleaner design: check permissions in a service or guard layer executed before calling the cacheable bean. If results are user- or tenant-specific, the cache key and storage scope must also distinguish every context factor affecting the data. Including user ID in the key can prevent data mixing, but **does not replace request-time permission checks**.

## 4. Exact Comparison of `condition`, `unless`, and Business `if`

| Mechanism | Question answered | Timing | When condition is not met / triggers |
| --- | --- | --- | --- |
| `@Cacheable(condition = "...")` | Should this call participate in cache lookup/write? | Before cache lookup | Skips cache, **still calls method** |
| `@Cacheable(unless = "...")` | Should we **refuse to store this new result**? | After method runs on a miss | When `unless = true`, **does not write cache**; result is still returned |
| `if (...)` inside method body | How should business logic run or reject input? | When method body actually runs | Per code: may throw, return, or switch branches |
| Policy check in facade/filter before cacheable bean | Is this request allowed to proceed? | Before calling cacheable bean | Can reject immediately, even if cache holds data |
| `@CacheEvict` after data-modifying operations | Should previously stored results be removed? | Usually after method succeeds | Deletes entry so next read loads fresh data |

Combined example:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != 'FLASH'",
    unless = "#result == null"
)
public Integer loadPrice(String sku) {
    if (sku.isBlank()) {
        throw new IllegalArgumentException("SKU required");
    }
    return repository.findPrice(sku);
}
```

*Standalone snippet illustrating syntax; `repository` is undefined.*

Interpretation:

1. `sku == "FLASH"`: cache is bypassed; the method runs and executes `if`.
2. `sku == "STANDARD"`, cache miss: the method runs, may throw due to the rule or return a price; then `unless` is evaluated.
3. `sku == "STANDARD"`, cache hit: the method does not run, so the `if` **inside the method** is also skipped. Thus, if `if` is a permission check required on every request, that placement is inappropriate.
4. If the method returns `null` on a miss: `unless` is `true`, so Spring does not store null; this does not automatically turn into a business error response.
5. If the method throws an exception: there is no normal return value to store under default `@Cacheable`.

**Do not confuse expression semantics:** `condition = false` is "cache bypass"; `unless = true` is "veto cache put"; `throw new ...` is "business rejection." These are three distinct behaviors, easily observed from program output.

## 5. Choosing the Right Execution Layer for Each Rule Type

A service design often has two layers:

```text
HTTP / caller
    |
    v
PriceFacade.getPrice(sku, caller)
    |-- validate request
    |-- authorize caller
    '-- PriceLookupService.loadPrice(sku)
            |-- Spring @Cacheable interceptor
            |     condition / key / hit / miss / unless
            '-- method body if cache miss or bypass
                  -> database / expensive computation
```

The **outer layer** handles preconditions and permissions that must be checked on every call. The **cacheable layer** handles queries/computations whose results can be reused for the same key. This is an easy-to-follow organization, not a strict rule requiring exactly two classes.

Watch out for two boundaries:

- If pricing **actually depends** on customer tier or tenant, include every variable affecting output in the cache key (or use a separate cache name/scope) to avoid serving the wrong price. If data is highly sensitive, consider not caching it in a shared layer.
- Actions with **mandatory per-call side effects** (recording transactions, updating inventory, emitting events) are not suitable to be skipped by `@Cacheable`. Caches should hold repeatable reads/computations with a proper business refresh strategy.

Do not believe that setting `condition = "#caller.isAdmin()"` implements authorization. It only decides caching for admins; calls from non-admins still enter the method. A cache condition expression is not a security barrier.

## 6. Runnable Java 17+ Example: Independent Cache Bypass and Business Rules

The following Spring Boot program has two beans:

- `PriceFacade` validates input and permissions **every time** a caller invokes it.
- `PriceLookupService` uses `@Cacheable` to decide which SKUs are cached. `FLASH` always bypasses the cache, while `UNKNOWN` returns `null` and is vetoed from storage by `unless`.

A counter inside the lookup method shows **when the method body actually runs**. The whole example runs with Java 17+, Maven, and Spring Boot 3.3.5 using an in-memory local cache.

Structure:

```text
business-vs-cache/
├── pom.xml
└── src/main/java/example/cachepolicy/
    ├── Application.java
    ├── PriceFacade.java
    └── PriceLookupService.java
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
    <artifactId>business-vs-cache</artifactId>
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

**`src/main/java/example/cachepolicy/PriceLookupService.java`**

```java
package example.cachepolicy;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceLookupService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(
        cacheNames = "prices",
        key = "#p0",
        condition = "#p0 != 'FLASH'",
        unless = "#result == null"
    )
    public Integer loadPrice(String sku) {
        int callNumber = loads.incrementAndGet();
        System.out.println("LOAD #" + callNumber + " " + sku);

        return switch (sku) {
            case "STANDARD" -> 100;
            case "FLASH" -> 80;
            default -> null;
        };
    }
}
```

**`src/main/java/example/cachepolicy/PriceFacade.java`**

```java
package example.cachepolicy;

import org.springframework.stereotype.Service;

@Service
public class PriceFacade {
    private final PriceLookupService lookup;

    public PriceFacade(PriceLookupService lookup) {
        this.lookup = lookup;
    }

    public Integer getPrice(String sku, boolean allowedToView) {
        // Business rule: must be checked on every request.
        if (!allowedToView) {
            throw new SecurityException("Access denied");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU required");
        }

        // This call goes through another bean's proxy so @Cacheable takes effect.
        return lookup.loadPrice(sku);
    }
}
```

**`src/main/java/example/cachepolicy/Application.java`**

```java
package example.cachepolicy;

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
        return new ConcurrentMapCacheManager("prices");
    }

    @Bean
    CommandLineRunner demo(PriceFacade prices) {
        return args -> {
            System.out.println("S1 -> " + prices.getPrice("STANDARD", true));
            System.out.println("S2 -> " + prices.getPrice("STANDARD", true));

            try {
                prices.getPrice("STANDARD", false);
            } catch (SecurityException ex) {
                System.out.println("DENY -> " + ex.getMessage());
            }

            System.out.println("F1 -> " + prices.getPrice("FLASH", true));
            System.out.println("F2 -> " + prices.getPrice("FLASH", true));
            System.out.println("U1 -> " + prices.getPrice("UNKNOWN", true));
            System.out.println("U2 -> " + prices.getPrice("UNKNOWN", true));
        };
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

The example's output lines appear in the **exact order** below; the console will also include Spring Boot startup logs:

```text
LOAD #1 STANDARD
S1 -> 100
S2 -> 100
DENY -> Access denied
LOAD #2 FLASH
F1 -> 80
LOAD #3 FLASH
F2 -> 80
LOAD #4 UNKNOWN
U1 -> null
LOAD #5 UNKNOWN
U2 -> null
```

Why does this output occur?

| Call | Business rule in `PriceFacade` | Cache decision | Did `loadPrice` body run? |
| --- | --- | --- | --- |
| S1, STANDARD | Allowed | `condition=true`, miss | Yes: prints `LOAD #1`, caches `100` |
| S2, STANDARD | Allowed | `condition=true`, hit | No; returns `100` from cache |
| DENY, STANDARD | **Rejected** before calling lookup | No cache lookup | No; throws `SecurityException` |
| F1 and F2, FLASH | Allowed | `condition=false` every time | Yes both times; prints `LOAD #2` and `LOAD #3` |
| U1 and U2, UNKNOWN | Allowed | Miss; `unless=true` because result is null | Yes both times; prints `LOAD #4` and `LOAD #5` |

This is visual proof of three distinct behaviors:

- **Business reject:** `DENY` triggers even though `STANDARD` is already in the cache. The permission check layer runs before calling the cacheable bean.
- **Cache bypass:** `FLASH` is not rejected. Each call returns `80`, but the method must re-run because `condition=false`.
- **Skip cache put:** `UNKNOWN` is allowed to execute, but the `null` result is not stored due to `unless=true`. Thus call U2 still runs the method.

This program demonstrates with fixed data and `ConcurrentMapCacheManager`, not a real authentication application. The boolean `allowedToView` only simulates an authorization decision; in a real system, permissions must be verified from a trusted security context (such as Spring Security), never blindly trusting a client-supplied boolean flag. This cache lives in a single JVM with no automatic TTL or cross-node synchronization.

## 7. Impact of Cache Hits on `if` Logic Inside the Method

A developer might place the following steps inside a cacheable method:

```java
@Cacheable(cacheNames = "report", key = "#p0")
public Report getReport(String reportId, User caller) {
    ensurePermission(caller, reportId);
    validateRequest(reportId);
    Report data = loadFromDatabase(reportId);
    return data;
}
```

*This snippet is illustrative only: helper types and methods are not implemented.*

On a **miss**, the entire method body runs, so `ensurePermission` and `validateRequest` execute. On a **hit**, the interceptor returns the stored entry without executing those two functions. This is a major reason to separate permission checks from cacheable methods whenever permissions can vary by user or time.

However, not every `if` inside a method is a mistake. For example:

```java
@Cacheable(cacheNames = "shipping", key = "#p0 + ':' + #p1")
public int shippingFee(String zone, int weightKg) {
    if (weightKg >= 10) {
        return 50;
    }
    return 20;
}
```

The condition `weightKg >= 10` is a **result calculation rule**, and if the result truly depends only on `zone` and `weightKg`, that result can be cached. A hit does not need to re-evaluate the `if` because Spring reuses the **result already computed for the same inputs**.

Business rules must be evaluated by their semantics, not merely by the `if` syntax: a condition that **must be re-checked on every call** differs from a calculation **stable for a given key** whose result can be reused.

## 8. Key Design and Invalidation to Prevent Wrong Results

Even with external permission checks, cached results are only accurate if the key distinguishes all variables affecting the output.

For example, personalized pricing:

```java
@Cacheable(cacheNames = "customerPrices", key = "#p0 + ':' + #p1")
public int loadCustomerPrice(String productId, String customerTier) {
    return calculatePrice(productId, customerTier);
}
```

Here both `productId` and `customerTier` can affect the result. If you only chose `key="#p0"`, the `VIP` tier could receive `STANDARD` tier pricing or vice versa. In multi-tenant systems, the tenant ID usually must participate in the cache scope/key if data differs by tenant; permission checks are still needed at a guaranteed execution point.

When source data changes, cache hits can return stale data. Appropriate refresh mechanisms must be used: `@CacheEvict` after successful updates, `@CachePut` when writing new results directly, TTL, versioned keys, or cross-node invalidation. You must also consider transaction commit timing and read/write races when strong consistency is required.

Do not put a criterion like "do not cache if data changed" in `condition` based on unread state, because the condition expression runs before the method. If deciding whether to store depends on the **newly loaded result itself**, use `unless`; if you need to know whether the cache is still fresh, you need a versioning/expiry/invalidation strategy at the appropriate layer.

## 9. Common Pitfalls

1. **Using `condition=false` to reject users.** Spring only skips the cache and still invokes the method. If the method does not block it itself, the business action still runs.
2. **Putting dynamic permission checks only inside the cacheable method.** Cache hits skip the method, potentially skipping permission checks.
3. **Assuming `unless=true` means returning an error or re-running the method.** It only vetoes caching the result of the invocation that just ran; the result is still returned to the caller.
4. **Mixing different users'/tenants' results under one key.** Keys must reflect all context affecting the output; highly sensitive data should avoid shared caching.
5. **Forgetting to check for self-invocation.** In default proxy mode, internal `this.loadPrice(...)` calls within the same bean bypass the cache interceptor, so `condition`/`unless` rules are not applied either.
6. **Assuming every hit is up to date.** The cache does not automatically watch the database; an expiration or cache eviction/update policy is required.
7. **Placing side effects in a cacheable method and expecting them to always run.** Hits can skip emitting events, writing business audit logs, or updating state.
8. **Evaluating a business rule using the return value in `@Cacheable(condition="#result...")`.** Pre-lookup conditions do not have `#result` yet; use input data or `unless` if the question is whether to store the newly produced result.
9. **Confusing the cache provider with business policy.** The provider manages storage/retrieval/TTL/eviction per configuration; it does not understand application authorization conditions or validity rules.

## 10. Knowledge Self-Check

**Question 1.** `@Cacheable(condition = "#p0 != 'FLASH'")` receives `sku="FLASH"`. Will Spring prevent the method from running?

**Answer:** No. Spring skips caching for this operation; the actual method is still invoked and runs per business logic.

**Question 2.** A `@Cacheable` method has `if (!allowed) throw ...` in its body; the cache already holds the matching key. Is the permission check guaranteed to run?

**Answer:** No. A cache hit can return the entry directly at the interceptor and skip the entire method body. Permission checks must live at a layer enforced on every request.

**Question 3.** `condition=true`, cache miss, method returns `null`, `unless="#result == null"`. What happens?

**Answer:** The method ran; `unless` evaluates to `true`, so Spring does not write the new result to the cache. The current call still receives `null`.

**Question 4.** A method calculates shipping fees based on `zone` and `weightKg`. Can the weight-threshold calculation stay inside the cacheable method?

**Answer:** Yes, if the fee calculation is deterministic for those factors, the key includes all factors, and related data is refreshed when needed. Hits return the already-computed fee for the same key.

**Question 5.** Can all authorization logic be replaced with `@Cacheable(condition="#caller.isAuthorized()")`?

**Answer:** No. When the condition is false, Spring skips caching yet still executes the method. Access control must be enforced by an authorization layer that blocks unauthorized actions.

## References

- Spring Framework Reference — *Declarative Annotation-based Caching*, section *Conditional Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — *Proxying Mechanisms*, self-invocation section: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
