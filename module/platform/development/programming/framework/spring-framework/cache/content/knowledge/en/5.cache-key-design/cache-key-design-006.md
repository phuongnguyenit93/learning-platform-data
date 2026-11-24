# Including All Parameters That Actually Affect the Result — Spring Cache Key Design

## Learning Objectives

After this lesson, you will know how to identify **which inputs truly affect the result** of a method, represent them as a cache key, detect hidden parameters outside the method signature, avoid mixing up data across tenants/users, and verify correctness with a Java 17+ Spring Boot example.

Principle of **Key Design**: **if two invocations can return two different business results while the cache entry is still valid, they must have two different keys in the same cache**. If they only differ in information used for logging or request tracing and the result remains equivalent, they should share the same key.

## 1. What Does "Parameters That Affect the Result" Mean?

Suppose an application displays a product using the method:

```text
getProductView(productId, tenantId, languageTag, currency,
               membershipTier, traceId) → ProductView
```

The system has multiple stores, multiple languages, currency-based pricing, and membership tiers. We need to ask: **if we keep everything else the same and change only one parameter, can the result change?**

| Parameter | Can it change the result? | Decision |
| --- | --- | --- |
| `productId` | Yes: different product. | Must be in the key. |
| `tenantId` | Yes: each store may have different products, prices, or visibility rules. | Must be included when data is partitioned by tenant. |
| `languageTag` | Yes: translations or presentation change. | Must be included when the method returns localized content. |
| `currency` | Yes: currency unit/converted price changes. | Must be included if it affects the returned value. |
| `membershipTier` | Yes: tier-based pricing or discounts. | Must be included if tier-based pricing applies. |
| `traceId` | No, if only for logging/correlation. | Exclude from the key. |

Thus, a semantically accurate representation could be:

```text
ProductViewKey(tenantId, productId, languageTag, currency, membershipTier)
```

Do not assume "the key is all parameters" or "the key is only the ID". Decide based on the method's **output contract** and the contexts that influence it.

In general, we can write `result = f(businessInputs, context, sourceState)`. The key represents the inputs/context that must be distinguished; changes in `sourceState` (database, price table, configuration) also require TTL, invalidation, or versioning strategies.

## 2. Correctness Condition: Never Merge Two Different Results

Let `K(x)` denote the cache key for invocation `x` and `R(x)` denote the business result. Within one cache and the timeframe during which an entry may be reused, we require:

```text
K(x) == K(y)  ⇒  R(x) is equivalent to R(y) per the business contract.
```

"Equivalent" does not just mean product names look the same: price, access permissions, currency unit, data ordering, pagination, language, and returned fields are also part of the contract if the API exposes them.

Two common mistakes:

- **Under-keying (missing key components):** two calls that should have different results share the same key, returning wrong information; when data is user/tenant-specific, this can be a data leak bug.
- **Over-keying (excess key components):** two calls that could share an entry generate different keys, for example merely because of a random `requestId`. Cache hits drop, while entries, memory usage, and source load increase.

**Prioritize data correctness over hit rate.** A high hit rate has no value if entries come from the wrong context.

## 3. How to Find Every Input Affecting the Result

Do not inspect only the method parameters. Across service code, repositories, policies, and external calls, list every factor that can influence the **content or visibility** of the result:

1. **Data identifiers:** product ID, category ID, warehouse ID, organization/tenant.
2. **Query criteria:** filters, search query, sort, page, size, field selection, include/exclude flags. For example, the same category with `includeOutOfStock=true` must differ from false.
3. **User context:** identity, role, permission scope, customer segment. User ID is not always required; only when the output depends on the user or their scope.
4. **Localization:** language, region, timezone, currency, tax region if they affect the output.
5. **Policy/version:** experiment cohort, feature flag, pricing rule, schema/API version if the same cache holds multiple incompatible output versions.
6. **Time-varying source data:** prices, exchange rates, inventory, order status, promotions. Decide whether to add a snapshot/version to the key or control freshness via invalidation/TTL.
7. **Infrastructure parameters:** traceId, spanId, correlationId, logging tags are normally unnecessary if they do not affect the output. For timeout/retry, check whether they alter fallback behavior or the returned value.

Also verify the **data flow path**. For example, a controller passes a user ID, the service reads the tenant from a ThreadLocal, and the repository adds a tenant filter. If the key contains only product ID, a cache hit skips the method body so the tenant filter is no longer executed for that request.

### Hidden Context Is a Dangerous Source of Bugs

Anti-pattern example:

```java
// Incorrect illustration; Product and TenantContext are hypothetical types.
@Cacheable(cacheNames = "visibleProducts", key = "#p0")
public List<Product> getVisibleProducts(String categoryId) {
    String tenantId = TenantContext.currentTenant();
    // Query data by categoryId AND tenantId...
}
```

The same category across two tenants can share a key and return the previous tenant's data. The same happens when a method reads `SecurityContextHolder`, `LocaleContextHolder`, the clock, feature flags, current currency, or a policy from configuration.

**Prefer turning genuinely important dependencies into explicit inputs**, such as `VisibleProductsKey(tenantId, categoryId, languageTag, scope)`, constructed after validation and normalization. When output is random or changes too rapidly, that method may not be suitable for caching.

**Security note:** having tenant/user scope in the key does not replace authorization checks. If an authorization check sits *inside* a `@Cacheable` method, a cache hit can skip that check entirely. Place authorization checks on a call path that always executes before the cached method, and only return data matching the authenticated scope. Avoid using raw access tokens, passwords, or session secrets as keys or logging them.

## 4. How Does Spring Cache Generate Default Keys?

Spring Cache uses `SimpleKeyGenerator` by default with these rules:

- Zero parameters: `SimpleKey.EMPTY`.
- One parameter: uses that parameter object itself as the key.
- Multiple parameters: creates a `SimpleKey` containing all arguments.

This works well if every parameter must be distinguished and has stable `equals/hashCode`. However, if the signature has `traceId` or `requestId` solely for observability, a default key including them causes unnecessary misses. And the framework does not automatically detect tenant/locale/role variables read from context inside the method.

Spring lets you specify a key via **SpEL**:

```java
@Cacheable(cacheNames = "catalogViews", key = "#p0")
public String describe(CacheKey businessKey, String requestId) {
    // ...
}
```

`#p0` (or `#a0`) is the first argument. Use positional indices when you do not want to depend on whether the compiler retains parameter names. If multiple methods need the same complex rule, you can use a custom `KeyGenerator` bean; `key` and `keyGenerator` must not be specified simultaneously on the same cache operation.

A clean way to avoid collision-prone string concatenation is wrapping business components in a Java `record`. An immutable record derives `equals/hashCode` from each component, making it well-suited as an in-memory cache key when components are also stable.

## 5. Java 17+ Spring Boot Example — Capturing Full Context, Ignoring Trace

This example can run in an **existing Spring Boot Gradle project** with Java 17+ and the cache starter dependency. Return data is built from the key's fields for clear observation without needing a database.

Add to `build.gradle` (keeping your existing plugin versions and other dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/keys/CacheKey.java`:**

```java
package example.keys;

import java.util.Objects;

public record CacheKey(
        String tenantId,
        String productId,
        String languageTag,
        String priceTier
) {
    public CacheKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(languageTag, "languageTag");
        Objects.requireNonNull(priceTier, "priceTier");
    }
}
```

All fields in `CacheKey` change the demo's output. `record` ensures two instances with the same four components are treated as equal under `equals/hashCode`.

**File `src/main/java/example/keys/CacheConfiguration.java`:**

```java
package example.keys;

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
        return new ConcurrentMapCacheManager("catalogViews");
    }
}
```

`ConcurrentMapCacheManager` is a simple single-JVM backend for observing behavior and does not provide default TTL or size limits.

**File `src/main/java/example/keys/CatalogService.java`:**

```java
package example.keys;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "catalogViews", key = "#p0")
    public String describe(CacheKey key, String requestId) {
        System.out.println("SOURCE_READ #" + sourceReads.incrementAndGet());
        return key.tenantId() + "/" + key.productId() + "/"
                + key.languageTag() + "/" + key.priceTier();
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

`requestId` is only a request metadata parameter and does not affect the return value, so `key="#p0"` excludes it from the cache key. The counter increments only when the `describe` body actually executes.

**File `src/main/java/example/keys/KeyDemoApplication.java`:**

```java
package example.keys;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class KeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(CatalogService service) {
        return args -> {
            CacheKey vietnamese = new CacheKey("shopA", "P42", "vi-VN", "standard");
            CacheKey english = new CacheKey("shopA", "P42", "en-US", "standard");
            CacheKey premium = new CacheKey("shopA", "P42", "vi-VN", "premium");
            CacheKey secondTenant = new CacheKey("shopB", "P42", "vi-VN", "standard");

            System.out.println("1: " + service.describe(vietnamese, "req-1"));
            System.out.println("2: " + service.describe(
                    new CacheKey("shopA", "P42", "vi-VN", "standard"), "req-2"));
            System.out.println("3: " + service.describe(english, "req-3"));
            System.out.println("4: " + service.describe(premium, "req-4"));
            System.out.println("5: " + service.describe(secondTenant, "req-5"));
        };
    }
}
```

Run in the project:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

The demo's `System.out` lines appear in order (excluding Spring startup logs):

```text
SOURCE_READ #1
1: shopA/P42/vi-VN/standard
2: shopA/P42/vi-VN/standard
SOURCE_READ #2
3: shopA/P42/en-US/standard
SOURCE_READ #3
4: shopA/P42/vi-VN/premium
SOURCE_READ #4
5: shopB/P42/vi-VN/standard
```

| Call | What changed | Behavior |
| --- | --- | --- |
| 1 | New key, first time | Miss, method body runs (`#1`). |
| 2 | New record with the same four fields; different requestId | Hit, method body does not re-run. |
| 3 | Language changed `vi-VN` → `en-US` | Miss (`#2`), content differs. |
| 4 | Tier changed `standard` → `premium` | Miss (`#3`), content differs. |
| 5 | Tenant changed `shopA` → `shopB` | Miss (`#4`), does not reuse previous tenant's cache. |

If `key = "#p0"` is removed in this example, the default key of the two-parameter method will include `requestId`. Call 2 will therefore miss despite having the same business result.

**Demo scope:** does not simulate transactions, access control, TTL, or real data updates. `@EnableCaching` only takes effect when calling the method through a Spring-managed bean proxy; self-invoking `this.describe(...)` inside the same service can bypass the interceptor in default proxy mode. The example consists of multiple Java files in a Spring Boot project, not a single standalone file to run with `javac`.

## 6. Counter-Example: ID-Only Key Returns Wrong Data Across Tenants

```java
// WRONG when the result depends on tenant, locale, and tier as well!
@Cacheable(cacheNames = "catalogViews", key = "#productId")
public ProductView get(String productId, String tenantId,
                       String languageTag, String priceTier) {
    // Logic returning product based on all four parameters...
}
```

`ProductView` is an illustrative type only. Once `get("P42", "shopA", "vi-VN", "standard")` writes an entry under key `P42`, a request `get("P42", "shopB", "en-US", "premium")` can hit that key and receive shopA's data. The method body does not run, so logic based on the other three parameters is bypassed.

**Under-keying** cannot be fixed with `unless` or merely shortening TTL. You must change the key contract first: use a record with the exact required fields, or a `KeyGenerator` with an unambiguous key structure, while ensuring authorization is still checked before the cached method. If the result is proven to be a public catalog identical across all tenants/locales, the key can be simplified, but that must be an evidence-backed business decision.

## 7. Normalization and Stability of Cache Keys

Choosing the right fields is a necessary condition; how fields are represented also matters greatly.

- **Normalize data before building keys:** `usd`/`USD`, `vi-vn`/`vi-VN`, default filter/sort values, extra whitespace. Normalize only per domain rules; do not arbitrarily lowercase case-sensitive IDs.
- **Immutable keys:** use `record` or immutable value objects. If a key is a mutable object, changing a field after placing it into a hash-based map can cause lookups to fail.
- **Meaningful `equals/hashCode`:** two inputs are considered the same key when they genuinely carry the same meaning. Creating a new object per request with default identity equality can cause misses even when fields match.
- **No naive string concatenation:** tuples `("a:b","c")` and `("a","b:c")` can both produce `a:b:c` when merely joined with `:`. Use a record/tuple or an unambiguously delimited encoding.
- **Cache names are namespaces:** two methods sharing a cache/key while returning different types or meanings can collide. Use appropriate cache names or separate key domains/versions.
- **Backends must be verified:** records as keys are convenient for `ConcurrentMapCacheManager`. With Redis/distributed caches, inspect serializers/conversion/prefixes/key schemas and compatibility requirements across instances.
- **Never put secrets in keys/logs:** tokens, passwords, and sensitive session details are not safe key choices. Use minimal business identifiers/scopes after authentication.

## 8. Difference Between a Complete Key and Fresh Data

Even with a perfect key, the data source can still change. For example, the same `CacheKey("shopA","P42","vi-VN","standard")` may have a different price list today than yesterday.

- Use `@CacheEvict` after a successful update/delete so the next call re-reads, matching **the exact cache name and key definition**.
- Use `@CachePut` when a method updates the source and returns a result matching the cached entry; verify key semantics between read and write.
- Set TTL/expiry via the cache provider when bounded staleness is acceptable.
- Use `catalogVersion` or a snapshot ID as a key component **if** the query contract is versioned and requires reading per snapshot.
- If data requires real-time accuracy or results change continuously, consider not caching it.

Do not add `Instant.now()` to the key on every read to "avoid staleness": doing so constantly generates new keys and renders the cache nearly useless. For business-date-dependent data, a date-based key can be used *when business rules allow*, while handling timezones, expiry, and intraday updates.

When updating inside a transaction, evicting too early can let another request reload stale data before commit. Design invalidation to align with transactions and check for race conditions when strong consistency is required; annotations do not handle every case automatically.

## 9. Test Plan for Complete and Minimal Keys

Structure tests around **pairs of calls changing exactly one variable**, resetting the cache appropriately to measure source access counts accurately:

| Case | Action | Expectation |
| --- | --- | --- |
| Same key called twice | Use two records with equal fields. | First misses, second hits; source executes once. |
| Change tenant | Same product/lang/tier; different tenant. | Independent miss; does not return previous tenant's data. |
| Change locale | Same product/tenant/tier; different lang. | Misses and returns the right translation. |
| Change currency or tier | Only one pricing component changes. | Different key; returns the right price. |
| Change request ID | All business inputs stay the same. | Hits; source read count does not increase. |
| Change filter/sort/page | One query criterion changes. | If the result can differ, the key must differ. |
| Change hidden user/scope/flag | Change context affecting results or permissions. | Does not reuse wrong entry; authorization check still runs. |
| Source data update | Price/name/stock changes. | Evict/put/TTL behaves per contract, no out-of-bounds staleness. |
| Equivalent inputs | Two representations normalized under a shared rule. | Use the same key and return the same result. |

Useful metrics once data correctness is established: cache hit/miss rates, source query counts, latency, entry counts, memory usage, and stale data duration. **Never trade correctness or authorization to increase hit rate.**

## 10. Pre-Production Service Caching Checklist

1. Explicitly document what determines the return value; audit both parameters and hidden context.
2. Vary each input one by one to prove when the output can differ or require access restrictions.
3. Put all impactful factors into the key; exclude parameters used solely for logging/tracing.
4. Normalize equivalent values; keep keys immutable with stable equality/hashing.
5. Verify SpEL/`KeyGenerator` key generation, cache names, and collision risks across methods.
6. Verify provider, serializer, TTL, updates/eviction, source mutations, and transactions.
7. Ensure authorization runs even on cache hits; never use secrets as keys.
8. Add tests covering key equivalence, tenant/locale/tier isolation, traceId exclusion, data changes, and post-invalidation behavior.

## Official Documentation

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
