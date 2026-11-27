# Designing Cache Names and Key Expressions with SpEL

In Spring Boot, **Spring Cache** allows applications to declare storage and reuse of method results using annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`. When using **Spring Data Redis**, `RedisCacheManager` can back those caches with Redis, allowing multiple application instances to share cached data.

A proper cache configuration requires more than just a working Redis instance. The application must answer two questions:

1. **What dataset does the cache name represent?** For instance, product profiles by ID, calculated prices by currency, or search results.
2. **Which outputs does the cache key distinguish?** If the same method can return different results depending on tenant, language, currency, or permissions, those factors must be accounted for in the key.

Choosing overly generic cache names or writing SpEL expressions missing parameters can cause the application to return **wrong data**, or even data belonging to another tenant. Conversely, packing unstable information into keys lowers cache hit rates, complicates accurate eviction, and proliferates keys in Redis.

This lesson explains how **`cacheNames`, `key`, and Redis key prefix configuration** work together, how to write **Spring Expression Language (SpEL)** expressions, and how to design caches so reads, updates, evictions, partitioning, and data upgrades remain consistent.

## 1. A cached result is identified by cache name and key

Consider a product lookup service:

~~~java
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView findProduct(String productId) {
    return repository.findProduct(productId);
}
~~~

Here:

- `cacheNames = "catalog.productById.v1"` selects the **logical cache region** managed by Spring Cache.
- `key = "#productId"` is a SpEL expression; Spring evaluates it against the method call's arguments and uses the result as the cache key.
- If the cache already holds a valid value for the pair *(cache name, key)*, Spring normally returns the stored result without invoking the method body.
- If absent, Spring invokes the method and stores the result according to cache policy and annotation attributes.

Model:

~~~text
   Call findProduct("p-42")
                 |
                 v
        Cache Interceptor
                 |
                 +--> cacheNames = catalog.productById.v1
                 |
                 +--> SpEL key = "p-42"
                 |
                 v
           RedisCacheManager
                 |
                 v
    Redis key: catalog.productById.v1::p-42
                 |
         +-------+--------+
         |                |
      Cache hit        Cache miss
         |                |
         v                v
    Return value     Call repository
                          |
                          v
                      Write cache
                          |
                          v
                      Return value
~~~

With the default `RedisCacheConfiguration` using the cache name as a prefix, the Redis key typically has the form:

~~~text
<cacheName>::<cacheKey>
~~~

For example, `catalog.productById.v1::p-42`. This is how Spring Data Redis constructs a keyspace in typical configurations, not a mandatory Redis syntax. Applications can customize prefixes, string conversion, and serializers.

**The cache name is not the complete Redis key.** The cache name is a logical identifier in Spring; the cache key is the output of the SpEL expression or `KeyGenerator`; `RedisCacheManager` combines both with the serializer/prefix to determine the physical key.

## 2. Naming caches by meaning and data lifecycle

Cache names should describe the **type of stored result** and follow a consistent convention across services. For example:

| Cache name | Expected data | Semantics |
| --- | --- | --- |
| `catalog.productById.v1` | One product by ID | Product detail object |
| `catalog.productPrice.v1` | Calculated price per product and currency | May have a shorter TTL than product info |
| `catalog.categoryTree.v1` | Category tree per language | Frequently read, rarely modified data |
| `account.profileById.v1` | Account profile | Has specific authorization and invalidation rules |
| `catalog.searchPage.v1` | Search results with filter/page/sort | Many key variants, prone to key growth |

One useful convention is:

~~~text
<boundedContext>.<resultType>.v<schemaVersion>
~~~

Where:

- **Bounded context**: the business area owning the data, such as `catalog` or `account`.
- **Result type**: the type of result cached, such as `productById`, `categoryTree`, or `searchPage`.
- **Version**: version bumped when data structure or cache semantics change incompatibly.

You do not need to bump the version for every code change; versioning is valuable when older cached entries might be misread by a newer application version. For example, if values used to be custom JSON strings and the new version uses objects with a different structure, switching the cache name to `catalog.productById.v2` establishes a fresh namespace and prevents collisions during rolling deployments.

### What problems do overly generic cache names cause?

Example:

~~~java
@Cacheable(cacheNames = "data", key = "#id")
public ProductView product(String id) { ... }

@Cacheable(cacheNames = "data", key = "#id")
public CustomerView customer(String id) { ... }
~~~

Both methods share **the same cache name and key expression**. If both receive `"42"`, they can share the same cache entry even though the underlying data is completely different. This can cause cast errors, deserialization failures, or returning wrong data.

Splitting into `catalog.productById.v1` and `account.customerById.v1` gives each result type its own space. Do not rely on Java class names or method names to distinguish entries automatically when the same `cacheNames` and `key` are specified.

### Avoid putting high-cardinality values into cache names

Normally, do not create cache names such as `catalog.product.p-42` and `catalog.product.p-43` per individual product. Values varying per record belong in the **key**, whereas the cache name represents a group of data sharing the same policy.

This keeps TTLs, prefixes, metrics, and cache-name evictions clear. For multi-tenant data, tenant separation can be designed in the prefix or key; creating thousands of dynamic cache names requires a clear operational justification.

## 3. SpEL expressions in `@Cacheable`

Spring uses SpEL to compute keys at method invocation time. Common expressions:

~~~java
// Key from a single parameter.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView findById(String productId) { ... }

// Key combining parameters.
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "#tenantId + ':' + #productId"
)
public ProductView findByTenantAndId(
        String tenantId, String productId) { ... }

// Extract a single property from a parameter object.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#request.productId")
public ProductView find(ProductRequest request) { ... }

// Use parameter index, independent of Java parameter name metadata.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#p0")
public ProductView findByIdWithIndex(String productId) { ... }
~~~

SpEL references:

| Expression | Meaning |
| --- | --- |
| `#productId` | Method parameter named `productId`, if parameter names are available |
| `#p0` or `#a0` | First parameter, zero-based index |
| `#p1` or `#a1` | Second parameter |
| `#root.args[0]` | First argument via the root object |
| `#root.methodName` | Name of the cached method |
| `#root.targetClass` | Target class of the invocation |
| `#request.productId` | `productId` property of parameter object `request` |
| `#request?.productId` | Null-safe property access when `request` may be `null` |
| `T(java.util.Locale).ROOT` | Reference to constant `Locale.ROOT` via SpEL type operator |

To use `#productId` by name, Java must retain parameter name metadata for Spring to read, typically via the `-parameters` compiler flag. If the project does not guarantee this, aliases `#p0`, `#a0`, and `#root.args[0]` prevent SpEL from failing to resolve variable names.

Groovy Gradle example if explicit enabling is required:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

With Spring Boot, inspect the actual build configuration since plugins/toolchains may already apply this flag. Do not enable it redundantly just because of a snippet.

### What happens if `key` is omitted?

Spring Cache uses the default `KeyGenerator`, typically `SimpleKeyGenerator`:

- No arguments: a special `SimpleKey.EMPTY` key.
- Exactly one argument: uses that argument itself as the key.
- Two or more arguments: constructs a `SimpleKey` from all arguments.

Example:

~~~java
@Cacheable("catalog.productById.v1")
public ProductView findById(String id) { ... }
~~~

For a single `String id`, the default key may be completely fine. However, when a method accepts mutable objects, `Pageable`, a request DTO containing fields that do not affect the output, or parameters lacking stable equality, the default key can be unclear. For critical business APIs, explicit SpEL expressions help maintainers understand cache identity directly on the method.

## 4. Core principle: identical meaningful inputs must yield the same key

A good cache key satisfies two criteria:

1. **Deterministic**: two business-equivalent calls produce the same key.
2. **Sufficiently distinct**: two calls that can return different outputs never accidentally produce the same key.

Consider a price calculation method:

~~~java
public PriceView calculatePrice(
    String tenantId,
    String productId,
    String currency,
    String membershipTier
) { ... }
~~~

If pricing depends on all four factors, keying solely on `#productId` is wrong. Two customers in different tiers or two currencies could receive each other's prices.

An explicit expression:

~~~java
@Cacheable(
    cacheNames = "catalog.productPrice.v1",
    key = "'tenant=' + #tenantId"
        + " + ';product=' + #productId"
        + " + ';currency=' + #currency"
        + " + ';tier=' + #membershipTier"
)
public PriceView calculatePrice(
        String tenantId,
        String productId,
        String currency,
        String membershipTier) { ... }
~~~

Java string concatenation inside the annotation above produces a single SpEL expression. A simpler style writes it on one line:

~~~java
@Cacheable(cacheNames = "catalog.productPrice.v1",
    key = "'t=' + #tenantId + ';p=' + #productId + ';c=' + #currency + ';tier=' + #membershipTier")
public PriceView calculatePrice(
    String tenantId, String productId, String currency, String membershipTier
) { ... }
~~~

Example generated keys:

~~~text
t=shop-a;p=p-42;c=VND;tier=GOLD
t=shop-a;p=p-42;c=USD;tier=GOLD
t=shop-a;p=p-42;c=VND;tier=BASIC
~~~

These three results have distinct cache identities.

**Note on delimiters:** If free-form input values can contain `;` or `=`, simple string concatenation can introduce ambiguity. In real systems, validate/normalize IDs to strict formats or use a `KeyGenerator` that encodes components unambiguously. Never assume arbitrary string concatenation is collision-free.

### Things frequently forgotten in keys

| Factor affecting output | Risk if omitted from key |
| --- | --- |
| Tenant / organization | Could read another tenant's data |
| Language / locale | Serves translations in the wrong language |
| Currency | Returns prices in the wrong currency |
| Customer segment / permissions | Serves unauthorized data |
| Search filters | One filter's results served for another filter |
| Page number and page size | Page 2 reuses Page 1 results |
| Sort field and sort direction | Returns list in wrong order |
| Calculation rule version | Uses results computed under old rules |

Not every factor belongs verbatim in a Redis key string. For example, multi-dimensional permissions can explode key counts; for sensitive data, sometimes **not caching per user** is the safer and simpler choice. First identify the exact set of inputs that truly affect output.

## 5. Multi-tenant cache design with cache names and SpEL

Suppose a system serves products for multiple stores. Two tenants may both have `productId = "p-42"` with different product details.

Incorrect design:

~~~java
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView getProduct(String tenantId, String productId) {
    return store.findByTenantAndId(tenantId, productId)
        .orElse(null);
}
~~~

Because `tenantId` is omitted from the key, two calls:

~~~text
getProduct("shop-a", "p-42")
getProduct("shop-b", "p-42")
~~~

both check cache entry `catalog.productById.v1::p-42`. If the two tenants have different data, the application can return wrong data.

Better design:

~~~java
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId",
    unless = "#result == null"
)
public ProductView getProduct(String tenantId, String productId) {
    return store.findByTenantAndId(tenantId, productId)
        .orElse(null);
}
~~~

Logical keys:

~~~text
tenant=shop-a;product=p-42
tenant=shop-b;product=p-42
~~~

For this to be secure, `tenantId` must be an **authenticated** and **authorized** identifier from the request context; never assume users have permission to query a tenant simply because they sent a tenant ID in a URL. Cache keys prevent data collisions across tenants, but do not replace authorization checks.

To prevent sensitive information from leaking via Redis keys, use normalized internal identifiers or one-way hashing per system policy. Do not place access tokens, card numbers, personal information, or sensitive queries verbatim into key names solely for debugging convenience.

## 6. Writing keys for filters, pagination, and sorting

For a product search endpoint:

~~~java
public SearchPage search(
    String tenantId,
    String category,
    String locale,
    int page,
    int size,
    String sortBy,
    String sortDirection
) { ... }
~~~

If output depends on all these parameters, the key should reflect them:

~~~java
@Cacheable(
    cacheNames = "catalog.searchPage.v1",
    key = "'t=' + #tenantId"
        + " + ';cat=' + #category"
        + " + ';lang=' + #locale"
        + " + ';page=' + #page"
        + " + ';size=' + #size"
        + " + ';sort=' + #sortBy"
        + " + ';dir=' + #sortDirection"
)
public SearchPage search(
        String tenantId, String category, String locale,
        int page, int size, String sortBy, String sortDirection) {
    // ...
}
~~~

Expressions like `#page` and `#size` hold numeric values, and SpEL concatenates them via the string `+` operator. Validate inputs and canonicalize `sortBy` and `sortDirection` before invoking the cached method.

However, caching every search combination is not always beneficial: too many filters, pages, and sort orders drive **key cardinality** very high. When nearly every query runs only once, hit rates stay low while consuming Redis memory. For search results, usually:

- Cache only popular filters, first pages, or frequently repeated queries.
- Set shorter TTLs than product detail caches if data changes often.
- Bound allowed page/size values and sort variants to avoid unbounded key growth from arbitrary inputs.
- Canonicalize equivalent values, such as `"vi-VN"` and `"vi-vn"`, under one consistent rule.

### Do not put an entire mutable request object in the key unnecessarily

Example:

~~~java
@Cacheable(cacheNames = "catalog.searchPage.v1", key = "#request")
public SearchPage search(SearchRequest request) { ... }
~~~

If `SearchRequest` is a mutable class without content-based `equals` and `hashCode`, or if the serializer produces an unstable string, two equivalent requests may fail to produce the same cache key. Even with a record providing field-based equality, the request might still hold `traceId`, `timestamp`, or fields unrelated to output, lowering hit rates.

The solution is writing an expression selecting only the output-affecting properties or creating an immutable key type and dedicated `KeyGenerator`.

## 7. Canonicalizing values before generating cache keys

If two business-equivalent inputs differ in formatting, the cache becomes fragmented:

~~~text
getBySku(" abc-42 ")
getBySku("ABC-42")
getBySku("abc-42")
~~~

If the system defines SKUs as case-insensitive and trims leading/trailing whitespace, canonicalize consistently **before checking the cache**:

~~~java
import java.util.Locale;

public String canonicalSku(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("sku must not be blank");
    }
    return raw.trim().toUpperCase(Locale.ROOT);
}
~~~

Simple canonicalization can be expressed directly in SpEL:

~~~java
@Cacheable(
    cacheNames = "catalog.productBySku.v1",
    key = "#sku.trim().toUpperCase(T(java.util.Locale).ROOT)"
)
public ProductView getBySku(String sku) {
    // Method body must still apply the same canonicalization rule.
    return store.findBySku(canonicalSku(sku)).orElse(null);
}
~~~

There is a design pitfall here: if SpEL canonicalizes one way while business logic processes differently, cache keys and source queries drift out of sync. Therefore, for complex rules, canonicalize data **at the system boundary or orchestrating service** and invoke the cached method with the canonical value.

Example:

~~~java
public ProductView lookupSku(String rawSku) {
    String canonical = canonicalSku(rawSku);
    return cachedCatalog.getByCanonicalSku(canonical);
}
~~~

`cachedCatalog` is **a different Spring bean** so the call passes through the Spring Cache proxy. This also avoids the self-invocation bug explained later.

Do not arbitrarily canonicalize case-sensitive identifiers such as tokens, hashes, or IDs where casing carries meaning. Every canonicalization rule must originate from the business contract.

## 8. Customizing Redis key prefixes with `RedisCacheManager`

In a Redis instance shared across environments or applications, using just the cache name `catalog.productById.v1` may not sufficiently separate operational scopes.

You can add application and environment prefixes:

~~~text
shop:prod:catalog.productById.v1::tenant=shop-a;product=p-42
shop:staging:catalog.productById.v1::tenant=shop-a;product=p-42
~~~

Example Spring Boot / Spring Data Redis configuration:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(
                    cacheName -> "shop:prod:" + cacheName + "::"
                )
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withCacheConfiguration(
                "catalog.productById.v1",
                defaults.entryTtl(Duration.ofMinutes(5))
            )
            .withCacheConfiguration(
                "catalog.searchPage.v1",
                defaults.entryTtl(Duration.ofSeconds(30))
            )
            .build();
    }
}
~~~

The example hardcodes `shop:prod:` for clarity. In production applications, load prefixes from reliable environment configuration rather than hardcoding `prod` and accidentally running against staging. Some systems dedicate separate Redis instances/databases per environment; prefixes still help operators distinguish data types, though they are **not a standalone security isolation boundary**.

With the configuration above, `@Cacheable(cacheNames = "catalog.productById.v1", key = "'tenant=' + #tenantId + ';product=' + #productId")` produces a physical key equivalent to:

~~~text
shop:prod:catalog.productById.v1::tenant=shop-a;product=p-42
~~~

**Cache names must match** across annotations, `withCacheConfiguration(...)`, metrics, and invalidation calls. If an annotation targets `catalog.productsById.v1` while the TTL configuration targets `catalog.productById.v1`, Spring may create a different cache or apply default configuration, yielding an unexpected TTL.

### Do not disable prefixes casually

Spring Data Redis lets you customize or disable key prefixes. If disabled, two distinct logical caches generating the same key can overwrite each other in Redis, and per-cache clear operations can have hard-to-control effects depending on configuration. Keeping explicit prefixes is right for most applications.

### Prefixes, keys, and serializers are separate layers

Cache names and SpEL define *identity*; serializers determine how keys/values become Redis data. Changing the serializer or object format can render old data unreadable even when cache names and keys remain unchanged. During incompatible schema/serializer changes, consider bumping the cache name version or executing a controlled migration/clear strategy.

## 9. `@Cacheable`, `@CachePut`, and `@CacheEvict` must share the same key contract

A common bug: reads key by tenant and product, while updates evict only by product.

~~~java
// Read:
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId"
)
public ProductView get(String tenantId, String productId) { ... }

// Wrong: evicts only by productId, mismatching the read key.
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    key = "#productId"
)
public void update(String tenantId, String productId,
                   UpdateProductRequest request) { ... }
~~~

After the update, the old cache entry remains at `tenant=shop-a;product=p-42`. Users keep receiving stale data until TTL expires or another mechanism deletes the entry.

Consistent design:

~~~java
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId"
)
public void update(String tenantId, String productId,
                   UpdateProductRequest request) {
    store.update(tenantId, productId, request);
}
~~~

By default `@CacheEvict` performs invalidation after the method completes successfully. For critical data writes, verify source commit ordering and invalidation timing. If a database transaction has not yet committed when the cache is evicted, another request could read stale data and repopulate the cache. Coordinating cache operations with transactions must reflect business staleness tolerance.

### `@CachePut` must match the read key exactly

`@CachePut` always executes the method body and writes the result to the cache by key:

~~~java
@CachePut(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #result.id"
)
public ProductView save(String tenantId, ProductDraft draft) {
    return store.save(tenantId, draft);
}
~~~

With `@CachePut`, the method return value can be referenced in the `key` expression after the method runs. This example only works if `store.save(...)` returns a non-`null` `ProductView` with an `id` property matching the ID used by `get`.

Do not use `#result` in `@Cacheable.key` for initial cache lookups: when checking the cache before calling the method, no result exists yet. In `@Cacheable`, `#result` can be used in `unless` after execution to decide whether to cache.

### When a single change affects multiple caches

Updating a product may affect both product detail and search pages:

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId"
    ),
    @CacheEvict(
        cacheNames = "catalog.searchPage.v1",
        allEntries = true
    )
})
public void updateProduct(
        String tenantId, String productId,
        UpdateProductRequest request) {
    store.update(tenantId, productId, request);
}
~~~

`allEntries = true` clears **the entire logical cache region** `catalog.searchPage.v1`, which can affect every tenant in that region. This may be acceptable for small caches, short TTLs, or infrequent updates, but is expensive for caches with many keys. Nor does it mean deleting only the current tenant's search results.

If invalidation per tenant or per specific query list is required, design a dedicated key-mapping/grouping mechanism or avoid caching result sets that cannot be cleanly invalidated. Do not expect `@CacheEvict` to deduce all search filters containing the modified product.

## 10. `condition` and `unless` conditions

Caching is not always suitable for every invocation. SpEL conditions can be used:

~~~java
@Cacheable(
    cacheNames = "catalog.searchPage.v1",
    key = "'tenant=' + #tenantId + ';page=' + #page",
    condition = "#page == 0",
    unless = "#result == null"
)
public SearchPage firstPageOrOtherPage(String tenantId, int page) {
    return store.search(tenantId, page);
}
~~~

In this example:

- `condition = "#page == 0"` is evaluated before using the cache; only page 0 passes through cache logic.
- `unless = "#result == null"` is evaluated after the method returns a result, preventing `null` storage.
- If `page != 0`, the method still executes without using the cache for that call.

Do not rely on `#result` inside `condition` because at the moment cache participation is decided, the method has not run yet. With `unless`, remember it does not undo earlier actions; it solely governs whether the result is stored in the cache.

If you want to cache the absence of data to avoid repeating expensive queries (negative caching), design a representation for missing results and an appropriate TTL. For example, `unless = "#result == null"` will **not** cache not-found cases, causing every lookup to hit the data source.

## 11. Unstable data sources that distort cache keys

### 11.1. Clock dependencies

Example:

~~~java
@Cacheable(
    cacheNames = "catalog.discount.v1",
    key = "#productId + ':' + T(java.lang.System).currentTimeMillis()"
)
public DiscountView discount(String productId) { ... }
~~~

This expression generates a virtually new key on every call; the cache is almost never reused. If discount pricing depends on a promotion campaign version, use an explicit **promotion ID/version** or business period as a key component combined with TTL.

### 11.2. Using `toString()` on objects without a stable contract

If an object relies on the default `Object.toString()`, the string typically reflects the JVM instance identity. Equal data in two different instances can yield two different keys. When encoding multi-field structures, use an immutable key type with a clear canonical contract or a `KeyGenerator`.

### 11.3. Using `hashCode()` as a unique identifier

~~~java
@Cacheable(cacheNames = "catalog.searchPage.v1",
           key = "#request.hashCode()")
public SearchPage search(SearchRequest request) { ... }
~~~

`hashCode()` is not a unique identifier and can collide. Some hash implementations even depend on mutable state. Only use hashes in cache keys when the design explicitly addresses collision risks; a canonical representation of input data is usually clearer.

### 11.4. Mixing hidden parameters inside the method body

Consider a `getCurrentUserDashboard()` method taking no parameters that reads the current user from `SecurityContextHolder`:

~~~java
@Cacheable(cacheNames = "dashboard.v1")
public DashboardView getCurrentUserDashboard() { ... }
~~~

Because the method takes no arguments, the default key is identical for all users. If results vary per account, this causes data leaks. A clean design passes the authenticated user identifier into a **cached service bean**:

~~~java
@Cacheable(
    cacheNames = "account.dashboard.v1",
    key = "#userId"
)
public DashboardView getDashboard(String userId) { ... }
~~~

Permissions must still be checked at the business boundary; including `userId` in the key merely partitions cached data.

## 12. When SpEL becomes too complex: use `KeyGenerator`

Long SpEL expressions easily introduce delimiter ambiguities or missed parameters. When multiple methods share a key rule, create a dedicated `KeyGenerator`.

Example rule for **two String parameters** consisting of tenant ID and product ID. To avoid collisions when IDs contain delimiters, encode each component with URL-safe Base64:

~~~java
package com.example.redis.cache;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.stereotype.Component;

@Component("tenantProductKeyGenerator")
public class TenantProductKeyGenerator implements KeyGenerator {

    private static String encode(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Cache key component is blank");
        }
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public Object generate(Object target, Method method, Object... params) {
        if (params.length != 2
                || !(params[0] instanceof String tenantId)
                || !(params[1] instanceof String productId)) {
            throw new IllegalArgumentException(
                "Expected (String tenantId, String productId)"
            );
        }

        return "t:" + encode(tenantId) + ":p:" + encode(productId);
    }
}
~~~

Usage:

~~~java
@Cacheable(
    cacheNames = "catalog.productById.v1",
    keyGenerator = "tenantProductKeyGenerator"
)
public ProductView getProduct(String tenantId, String productId) {
    // ...
}
~~~

Likewise, `@CacheEvict` methods for the same parameter pair must use **that exact same KeyGenerator**, otherwise they will not delete the matching cache entry:

~~~java
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    keyGenerator = "tenantProductKeyGenerator"
)
public void invalidate(String tenantId, String productId) {
    // Business operation or explicit invalidation.
}
~~~

A single cache annotation should not specify both `key` and `keyGenerator`; pick one mechanism per operation. Base64 in this example is an **ambiguity-avoiding encoding**, not security encryption: anyone with read access to Redis keys can decode it. If IDs are sensitive, apply an appropriate protection strategy.

A `KeyGenerator` should enforce a clear contract on parameter order and types. Swapping method parameters from `(tenantId, productId)` to `(productId, tenantId)` without updating the generator produces wrong keys even though both are `String`s. When sharing a generator across methods, consider an explicit request ID type or test the input contract.

## 13. Service example with consistent cache reads and invalidation

The example below separates read and update services to highlight the Spring Cache proxy mechanism.

~~~java
package com.example.redis.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final ProductStore store;

    public CatalogQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId",
        unless = "#result == null"
    )
    public ProductView getById(String tenantId, String productId) {
        return store.findByTenantAndId(tenantId, productId).orElse(null);
    }
}
~~~

~~~java
package com.example.redis.catalog;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class CatalogCommandService {

    private final ProductStore store;

    public CatalogCommandService(ProductStore store) {
        this.store = store;
    }

    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId"
    )
    public void update(
            String tenantId,
            String productId,
            UpdateProductRequest request) {
        store.update(tenantId, productId, request);
    }
}
~~~

Assuming `ProductStore` is the primary data-access abstraction:

~~~java
import java.util.Optional;

public interface ProductStore {
    Optional<ProductView> findByTenantAndId(
        String tenantId, String productId
    );

    void update(
        String tenantId, String productId,
        UpdateProductRequest request
    );
}
~~~

`ProductView` and `UpdateProductRequest` are application DTO/domain types. With Redis Cache using default Java serialization, value types must be compatible with the configured serializer; many systems proactively choose a JSON serializer and manage schemas/versions so instances can read each other's entries.

Flow:

~~~text
          HTTP Controller / Application Service
                         |
                  +------+------+
                  |             |
                  v             v
         CatalogQueryService  CatalogCommandService
            getById(...)         update(...)
                  |                  |
                  v                  v
          @Cacheable          Write data source
                  |                  |
              Cache hit?             v
              /       \         @CacheEvict
            Yes       No             |
             |         |             |
         Use cache  ProductStore     |
                         |           |
                         v           v
                    Save cache  Delete exact cache key
~~~

**Spring AOP proxy note:** In standard proxy mode, a method calling another `@Cacheable` method **on the same instance via `this.method()`** will not pass through the cache interceptor. Ensure cached call sites invoke a Spring bean/proxy or structure services accordingly. Having an annotation on a method is insufficient if the runtime call bypasses the proxy.

## 14. Testing cache keys against real Redis

Cache tests should prove three properties:

1. Calling again with the same parameters uses the cached result without calling the data source a second time.
2. Same `productId` with a different `tenantId` produces two separate cache entries.
3. Evicting the cache for one tenant/product pair does not remove the other tenant's entry.

You can build an integration test with Spring Boot, Testcontainers, and a service counting executions. The service below returns strings so the example does not depend on a custom DTO serializer.

~~~java
package com.example.redis.cachetest;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;

public class CountingCatalogService {

    private final AtomicInteger databaseCalls = new AtomicInteger();

    @Cacheable(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #p0 + ';product=' + #p1"
    )
    public String load(String tenantId, String productId) {
        databaseCalls.incrementAndGet();
        return tenantId + "/" + productId;
    }

    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #p0 + ';product=' + #p1"
    )
    public void invalidate(String tenantId, String productId) {
        // Actively delete cache for the specified identifier pair.
    }

    public int databaseCalls() {
        return databaseCalls.get();
    }
}
~~~

In the test example, aliases `#p0` and `#p1` are used to avoid depending on parameter name metadata.

~~~java
package com.example.redis.cachetest;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = CacheKeyIntegrationTest.TestApp.class)
class CacheKeyIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableCaching(proxyTargetClass = true)
    static class TestApp {
        @Bean
        CountingCatalogService countingCatalogService() {
            return new CountingCatalogService();
        }
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port", () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CountingCatalogService service;

    @Test
    void keysMustSeparateTenantsAndMatchEviction() {
        String suffix = UUID.randomUUID().toString();
        String id = "product-" + suffix;
        String tenantA = "a-" + suffix;
        String tenantB = "b-" + suffix;

        int before = service.databaseCalls();

        assertThat(service.load(tenantA, id))
            .isEqualTo(tenantA + "/" + id);
        assertThat(service.load(tenantA, id))
            .isEqualTo(tenantA + "/" + id);

        // Same product ID but different tenant must hit the source again.
        assertThat(service.load(tenantB, id))
            .isEqualTo(tenantB + "/" + id);
        assertThat(service.databaseCalls() - before).isEqualTo(2);

        service.invalidate(tenantA, id);

        // Tenant B remains cached.
        service.load(tenantB, id);
        assertThat(service.databaseCalls() - before).isEqualTo(2);

        // Tenant A must reload after invalidation.
        service.load(tenantA, id);
        assertThat(service.databaseCalls() - before).isEqualTo(3);

        // Actively clean up test keys without waiting for default TTL.
        service.invalidate(tenantA, id);
        service.invalidate(tenantB, id);
    }
}
~~~

To run, the project needs appropriate dependencies, such as:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Here `@EnableCaching` activates cache interception; `RedisCacheManager` is auto-configured by Spring Boot when Redis Cache is chosen as the cache provider per application settings. If the project has multiple cache providers on the classpath, configure/specify Redis Cache explicitly so integration tests do not accidentally test another provider. Redis Testcontainers requires Docker or a compatible container runtime.

For tests needing to verify exact **physical Redis key names**, read keys by prefix in the test Redis instance using `StringRedisTemplate` or inspect the configured `CacheManager`, avoiding assertions tied to an implicit key format when the project customizes prefixes/serializers.

## 15. Common mistakes when naming caches and writing SpEL

| Symptom | Common cause | Remediation |
| --- | --- | --- |
| Two tenants receive the same cached product | Key only uses `productId` | Include authenticated tenant ID in key or separate namespaces appropriately |
| Data changes yet old copy is still returned | `@CacheEvict` uses different cache name or key formula | Use identical cache name and key contract for reads/writes/evictions |
| `#productId` expression fails to resolve | Missing Java parameter name metadata | Enable `-parameters` or use `#p0` / `#a0` |
| Very low cache hit rate despite static data | Key contains timestamp, trace ID, or mutable object | Include only output-affecting inputs and canonicalize |
| Empty cache key used for all users | Parameterless method reads user from context | Pass controlled user/tenant identifier into the cached method |
| Clearing search cache wipes cache for all tenants | `allEntries = true` used on shared cache name | Review invalidation policy and separate read cache models |
| SpEL fails accessing property on null | Missing validation or unsafe property access | Validate inputs, use `?.`, or use meaningful defaults |
| Concatenated parameters cause collisions | Delimiter appears in input data | Enforce format constraints or use a KeyGenerator with component encoding |
| `@Cacheable` skips when called from same class | Self-invocation bypasses Spring AOP proxy | Extract bean or call through proxy per chosen architecture |
| One instance fails to deserialize another's cache | Schema/serializer changed under same key namespace | Version caches and manage deployment/migration |
| Cache key leaks sensitive information | Raw tokens, emails, or sensitive filters placed in key | Use internal IDs or an appropriate key-hashing strategy |
| Null results cached/uncached unexpectedly | `unless`, cache configuration, or null-value policy | Define negative caching and TTL explicitly |
| Wrong TTL despite declaring per-cache config | Cache name in config differs from `cacheNames` | Keep name constants/conventions consistent and test TTL |
| SpEL relies on `#result` in lookup key | Result is only available after method runs | Use parameters for `@Cacheable.key`; `#result` only where post-invocation is supported |
| Search cache grows unboundedly | Filters/pages/sorts generate too many key combinations | Bound cardinality, lower TTL, or cache only popular queries |

## 16. Design workflow before adding a new cache

A systematic approach:

**Step 1 — Identify the exact cached result.** Is it an entity by ID, a localized DTO, a pricing table, a list, or permission-dependent data? Never share a cache name across two result types with differing semantics or serializers.

**Step 2 — List every input that alters the result.** Include explicit parameters and implicit factors like tenant, user, locale, currency, rule version, permissions, and active status. Cache only when a safe, stable identity can be defined.

**Step 3 — Choose a cache name with clear ownership.** For example, `catalog.productById.v1`. Design application/environment prefixes if Redis is shared, and set a TTL matching the data lifecycle.

**Step 4 — Choose the key expression or KeyGenerator.** Prefer canonical, immutable, sufficiently distinct IDs. Guard against delimiters, null inputs, and exposing sensitive data in Redis key names.

**Step 5 — Design invalidation alongside cache reads.** Determine which operations update data and which cache names/keys must be evicted or rewritten. If one update affects many filtered result sets, consider short TTLs or an indexing/invalidation mechanism instead of assuming a single key can be evicted.

**Step 6 — Test correctness before optimizing hit rate.** Identical inputs must hit; differing tenant, language, or currency must miss when outputs differ; updates must cause subsequent reads to see fresh data within the chosen consistency window.

**Step 7 — Observe in production.** Track key counts, Redis memory, hits/misses, eviction rates, serialization errors, TTLs, and cardinality per cache name. If a cache generates excessive variants with low hit rates, narrow its scope or adjust the caching strategy.

### Integrated decision example

Suppose an API returns product information by tenant and language:

~~~text
GET /tenants/shop-a/products/p-42?lang=vi-VN
~~~

A cache contract might be:

~~~text
Cache name:
    catalog.localizedProduct.v1

Key:
    tenant=shop-a;product=p-42;lang=vi-VN

Redis prefix:
    shop:prod:

Physical Redis key:
    shop:prod:catalog.localizedProduct.v1::tenant=shop-a;product=p-42;lang=vi-VN

TTL:
    5 minutes (illustrative, determined by business requirements)

Invalidate:
    When display content changes, delete affected language
    variants or apply an appropriate version/TTL policy.
~~~

This contract is valid only when locale values are canonicalized, tenant access is authorized, and invalidation handles all language variants. If new language translations are added or the product DTO changes schema, you may need to update the cache name/version and old-data cleanup mechanism.

## 17. Conclusion

In Spring Cache combined with Spring Data Redis, **the cache name defines a group of results, the cache key identifies a specific result within that group, and the Redis prefix/serializer defines how the group and key are represented in Redis**. A reliable design requires all three layers to align.

SpEL enables writing clear keys from parameters like `#productId`, `#tenantId`, `#p0`, or request properties. What matters is not expression length, but the **identity contract**: two equivalent calls must share a key, two calls that can return different data must be distinguished, and `@CacheEvict`/`@CachePut` operations must follow the exact same rule.

In systems with multiple tenants, languages, and pricing policies, a wrong cache key causes far worse consequences than a cache miss. Canonicalize inputs, isolate namespaces clearly, bound variants, test reads and invalidations together, and combine TTLs with versioning so cached data never becomes an uncontrolled source of inaccuracy.
