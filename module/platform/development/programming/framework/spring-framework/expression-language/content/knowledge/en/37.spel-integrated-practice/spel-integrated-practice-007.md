# Integrating SpEL into @Value or Cache Annotations

## 1. Overview

Spring allows using Spring Expression Language (SpEL) in many annotations to retrieve configuration, compute values, or control runtime behavior. Two common places are:

- `@Value`: injects external properties or SpEL-computed values into fields, constructor parameters, or method parameters.
- Cache annotations such as `@Cacheable`, `@CachePut`, `@CacheEvict`: use SpEL to generate cache keys, decide whether to cache, and inspect results before storing.

Although both use SpEL, these two places have different EvaluationContexts:

| Location | Purpose | Data SpEL can access |
|---|---|---|
| `@Value` | Compute a value to inject into a bean. | Property placeholders, system properties, bean references, and SpEL expressions configured in the ApplicationContext. |
| Cache annotation | Generate a key or condition for a method call. | Method arguments, method/target metadata, list of caches, and in some phases `#result`. |

Do not copy an expression from one annotation to another without reviewing the context. For example, `#isbn` in `@Cacheable` is a method parameter; it does not automatically exist in a regular `@Value`.

## 2. Requirements for annotations to be processed

Annotations must be processed by Spring inside an ApplicationContext. For `@Value`, the bean must be created and processed by the container. For cache annotations, caching must be enabled:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
```

`@EnableCaching` registers the infrastructure that processes cache annotations. Placing `@Cacheable` on a method without enabling caching will not automatically cache the method.

Service example:

```java
@Service
public class BookService {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findBook(ISBN isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

CacheManager determines the cache provider and the caches used by the annotations. In real-world applications, Caffeine, Redis, or another provider can be used; annotation SpEL syntax does not replace cache provider configuration.

## 3. Distinguishing property placeholders and SpEL in @Value

Two common syntaxes:

| Syntax | Meaning | Example |
|---|---|---|
| `${...}` | Retrieve value from Environment/PropertySource. | `${catalog.name}` |
| `#{...}` | Evaluate SpEL expression. | `#{systemProperties['user.region']}` |

Use a placeholder when you only need to retrieve configuration:

```properties
catalog.name=MovieCatalog
catalog.page-size=24
```

```java
@Component
public class MovieRecommender {

    private final String catalog;

    public MovieRecommender(
            @Value("${catalog.name}") String catalog) {
        this.catalog = catalog;
    }
}
```

Spring resolves the placeholder and converts the value to the target type if needed. If the property is `Integer`, `Boolean`, `Duration`, or a type with a matching converter, you do not necessarily have to parse the string manually in the constructor.

Use SpEL when calculations or data structure access are needed:

```java
@Component
public class CatalogSettings {

    private final String catalog;

    public CatalogSettings(
            @Value("#{systemProperties['user.catalog'] + 'Catalog'}")
            String catalog) {
        this.catalog = catalog;
    }
}
```

Here SpEL reads the system property `user.catalog`, appends the suffix `Catalog`, and injects the result.

## 4. Default values and type conversion in @Value

Placeholders support default values using `:`:

```java
@Value("${catalog.page-size:20}")
private int pageSize;
```

If `catalog.page-size` is not declared, Spring uses the default value 20. The String value is converted into `int` through ConversionService.

Collections or arrays can be injected from configuration:

```properties
catalog.supported-languages=en,vi,ja
```

```java
@Value("${catalog.supported-languages}")
private String[] supportedLanguages;
```

For configurations with many related fields, `@ConfigurationProperties` is usually easier to organize and validate than many scattered `@Value` annotations. `@Value` fits a few standalone values or short computation expressions.

### 4.1. Unresolvable placeholders

In standard Spring configuration, the default embedded value resolver may handle placeholders in lenient mode. If you need to fail fast when a required property is missing, register `PropertySourcesPlaceholderConfigurer`:

```java
@Configuration
public class PropertyConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer
            propertyPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

With Java configuration, the `@Bean` method creating the configurer needs to be `static`. Spring Boot configures `PropertySourcesPlaceholderConfigurer` by default to read `application.properties` and `application.yml`.

Do not set a default for a required property just so the application can start. For critical configuration, failing fast usually helps detect deployment errors earlier.

## 5. Using SpEL to access beans, static methods, and collections in @Value

SpEL can reference beans in the ApplicationContext using the `@beanName` syntax:

```java
@Component
public class DisplaySettings {

    private final String welcomeMessage;

    public DisplaySettings(
            @Value("#{@messageSettings.welcomeMessage}")
            String welcomeMessage) {
        this.welcomeMessage = welcomeMessage;
    }
}
```

You can call methods or read properties on a bean if the bean and method are accessible in the expression context:

```java
@Value("#{ @regionSettings.defaultRegion().toUpperCase() }")
private String region;
```

Static methods can be called via type references:

```java
@Value("#{T(java.lang.Math).max(10, 25)}")
private int minimumPageSize;
```

SpEL also supports collection literals:

```java
@Value("#{{'en': 'English', 'vi': 'Vietnamese'}}")
private Map<String, String> languageNames;
```

These expressions are evaluated while Spring processes bean injection. Field/constructor parameter values are not automatically recomputed whenever external properties change. If dynamically changing configuration is needed, use a configuration bean with an explicit refresh mechanism or query Environment/ConfigurationProperties according to an appropriate design.

## 6. Combining placeholders and SpEL

In `@Value`, placeholders can be resolved before the remainder is evaluated as SpEL. This is useful when you want to fetch a configuration value and then use it in a calculation:

```properties
catalog.page-size=24
```

```java
@Value("#{T(java.lang.Math).max(${catalog.page-size:20}, 10)}")
private int effectivePageSize;
```

If the property is 24, the expression computes `max(24, 10)` and injects 24. If the property is absent, the placeholder supplies 20.

Keep expressions short and readable. If the formula is long or contains multiple conditions, move the logic into a clearly named configuration bean instead of nesting multiple placeholders and SpEL expressions inside one annotation.

## 7. SpEL in @Cacheable: creating cache keys

The cache key determines how a result is stored and looked up. If the key does not fully reflect the parameters affecting the result, the application may return stale data or data belonging to another request.

Example method taking an ISBN along with two flags:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn.rawNumber"
)
public Book findBook(
        ISBN isbn,
        boolean checkWarehouse,
        boolean includeUsed) {
    return repository.findBook(
            isbn, checkWarehouse, includeUsed);
}
```

The expression `#isbn.rawNumber` uses only the ISBN code as the key. This approach is only correct if `checkWarehouse` and `includeUsed` do not change the result. If the two flags affect the result, they must be included in the key:

```java
@Cacheable(
    cacheNames = "books",
    key = "{#isbn.rawNumber, #checkWarehouse, #includeUsed}"
)
public Book findBook(
        ISBN isbn,
        boolean checkWarehouse,
        boolean includeUsed) {
    // ...
}
```

You can access nested properties, call methods, or use static methods:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn) {
    // ...
}

@Cacheable(cacheNames = "books", key = "T(com.example.Keys).normalize(#isbn)")
public Book findBookByNormalizedIsbn(ISBN isbn) {
    // ...
}
```

Static helpers should be pure, deterministic, and free of side effects. Keys need to remain consistent across calls and distinguish every input that can change the result.

## 8. Default keys and when SpEL is needed

If neither `key` nor `keyGenerator` is declared, Spring uses `SimpleKeyGenerator` with these rules:

- Method with no parameters: uses `SimpleKey.EMPTY`.
- Method with one parameter: uses that parameter itself.
- Method with multiple parameters: uses a `SimpleKey` containing all parameters.

The default key works well if parameters have stable `equals()` and `hashCode()` implementations and all parameters affect the result. Use SpEL when only some parameters need to participate in the key or when a nested property needs to be extracted.

The `key` and `keyGenerator` attributes are mutually exclusive. Do not declare both on the same cache operation.

Custom KeyGenerator example:

```java
@Cacheable(
    cacheNames = "books",
    keyGenerator = "bookKeyGenerator"
)
public Book findBook(ISBN isbn, boolean includeUsed) {
    // ...
}
```

If key generation logic can be reused across multiple methods or is too complex for a short expression, a custom KeyGenerator is usually easier to test.

## 9. Cache annotations have their own EvaluationContext

SpEL in cache annotations is evaluated on a context created by Spring Cache. The root object provides metadata about the method being called:

| Expression | Meaning |
|---|---|
| `#root.methodName` | Method name. |
| `#root.method` | Method being invoked. |
| `#root.target` | Target object. |
| `#root.targetClass` | Class of the target. |
| `#root.args` | Array of arguments passed to the method. |
| `#root.args[0]` | First argument. |
| `#root.caches` | Caches used for the current operation. |
| `#root.caches[0].name` | Name of the first cache. |
| `#isbn` | Method parameter named isbn, if parameter names are discovered. |
| `#a0`, `#p0` | Aliases to access the first parameter by index. |
| `#result` | Method result, only available in supported expression phases. |

Example using index to avoid depending on parameter names:

```java
@Cacheable(cacheNames = "books", key = "#a0.rawNumber")
public Book findBook(ISBN isbn) {
    // ...
}
```

If you want to use parameter names like `#isbn`, ensure parameter name metadata is retained in bytecode (typically by enabling the `-parameters` compiler option). When unsure whether names are available, use `#a0` or `#p0`.

The root object of a cache expression is not the root domain object that SpEL normally receives in a standalone expression. For example, `#root.target` is the bean being invoked; `#root.args[0]` is a method argument.

## 10. Differences between condition and unless

`@Cacheable` has two attributes to control storing results:

- `condition` is evaluated before the method runs. If false, Spring skips caching for that invocation and the method is still called.
- `unless` is evaluated after the method runs. If true, the result is not put into the cache.

Example caching only short names:

```java
@Cacheable(
    cacheNames = "books",
    condition = "#name.length() < 32"
)
public Book findBook(String name) {
    // ...
}
```

Example not caching hardcover books:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result.hardback"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

Do not use `#result` in `@Cacheable`'s `condition`, because condition is evaluated before the method is called. Use `#result` in `unless`, when the result is already available.

With return type `Optional<Book>`, the cache abstraction unwraps the business object value for `#result`. Because the result can be null, use safe navigation:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result?.hardback"
)
public Optional<Book> findBook(ISBN isbn) {
    // ...
}
```

## 11. @CachePut: always invokes the method and updates the cache

Unlike `@Cacheable`, `@CachePut` does not skip the method when data is already in the cache. The method is always executed and the result is placed into the cache under the computed key:

```java
@CachePut(cacheNames = "books", key = "#isbn")
public Book updateBook(ISBN isbn, BookDescriptor descriptor) {
    return repository.update(isbn, descriptor);
}
```

SpEL can be used in `key`, `condition`, and `unless` similarly to other cache operations. `#result` can be used in phases where the result is already available.

Do not place `@Cacheable` and `@CachePut` on the same method arbitrarily. One annotation wants to skip the method on a cache hit, while the other forces the method to run. The two behaviors can conflict. If coordination is needed, their conditions must be clearly mutually exclusive and tested.

## 12. @CacheEvict: removing cache entries by key or clearing an entire cache region

`@CacheEvict` removes an entry by key:

```java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void deleteBook(ISBN isbn) {
    repository.delete(isbn);
}
```

An entire cache region can be cleared:

```java
@CacheEvict(cacheNames = "books", allEntries = true)
public void importBooks(InputStream batch) {
    repository.importBooks(batch);
}
```

The `beforeInvocation` attribute determines when eviction occurs:

- Default `false`: evicts after the method finishes successfully.
- `true`: evicts before the method is invoked, regardless of whether the method later succeeds or throws an exception.

For example, evicting the cache before performing an operation can prevent stale data from being read during an update:

```java
@CacheEvict(
    cacheNames = "books",
    key = "#isbn",
    beforeInvocation = true
)
public void rebuildBookIndex(ISBN isbn) {
    // ...
}
```

When `beforeInvocation=true`, `#result` cannot be used in key/condition expressions because the method has not been executed yet. `allEntries=true` clears the entire cache; an individual key has no meaning in this case.

## 13. @Caching and @CacheConfig

Use `@Caching` when a method requires multiple cache operations or multiple different keys/conditions:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", key = "#isbn"),
    @CacheEvict(cacheNames = "book-search", allEntries = true)
})
public void updateBook(ISBN isbn, BookDescriptor descriptor) {
    // ...
}
```

Use `@CacheConfig` to share cache configuration at the class level:

```java
@Service
@CacheConfig(cacheNames = "books")
public class BookService {

    @Cacheable(key = "#isbn")
    public Book findBook(ISBN isbn) {
        // ...
    }

    @CacheEvict(key = "#isbn")
    public void deleteBook(ISBN isbn) {
        // ...
    }
}
```

`@CacheConfig` only supplies shared configuration; this annotation itself does not enable caching. Operation-level configuration overrides shared configuration when declared.

## 14. Enabling caching and proxy limitations

In default mode, Spring applies cache annotations through an AOP proxy. Therefore:

- Only external calls passing through the proxy are intercepted.
- Self-invocation (a method in the same class calling another method on the same object) does not go through the proxy and does not trigger cache advice.
- With proxy mode, place cache annotations on public methods of concrete classes.
- Do not rely on the cache proxy inside `@PostConstruct` or before the bean has finished initializing.

Example of self-invocation not triggering caching as expected:

```java
@Service
public class BookService {

    public Book load(String isbn) {
        return findCached(isbn); // Internal call on this.
    }

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findCached(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

You can extract the cached method into another bean so calls go through the proxy:

```java
@Service
public class CachedBookLookup {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findCached(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

Or consider AspectJ weaving if the application needs to intercept self-invocation/non-public methods and accepts the corresponding weaving configuration.

## 15. Choosing a correct and safe cache key

The cache key is part of data correctness and security. If a key omits parameters that affect the result, the cache may return wrong data.

Principles:

- Include every parameter that changes the result.
- Include tenant, locale, user scope, or version if they affect the result.
- Do not put tokens, passwords, or secret data into keys/logs.
- Prefer immutable keys with stable `equals()`/`hashCode()`.
- Avoid calling methods with side effects or I/O in key expressions.
- Do not use `#root.target` as a key if the target object does not have stable identity semantics.
- Do not share the same cache region for two data types with different structures/meanings if keys could collide.

Example of a key with tenant and ISBN:

```java
@Cacheable(
    cacheNames = "tenant-books",
    key = "{#tenantId, #isbn.rawNumber}"
)
public Book findBook(String tenantId, ISBN isbn) {
    // ...
}
```

If tenant is omitted from the key when the result depends on tenant, one tenant's data may be returned to another tenant. This is a correctness bug and can become a data leak.

## 16. Common errors and how to handle them

| Symptom | Cause | Resolution |
|---|---|---|
| `@Value` injects literal `${...}` string | Placeholder not configured/resolved or resolver is lenient. | Check PropertySource and PropertySourcesPlaceholderConfigurer. |
| `@Value` SpEL cannot find bean | Wrong bean name or bean is not in ApplicationContext. | Check bean name and the context containing the bean. |
| `#isbn` is not recognized in cache key | Parameter name metadata is missing. | Use `#a0`/`#p0` or compile with `-parameters`. |
| Cache key collision or returns wrong data | Key omits a parameter affecting the result. | Add the necessary parameters to the key. |
| `#result` cannot be used in condition | Condition runs before method invocation. | Use `#result` in unless or a supported post-invocation phase. |
| `@CachePut` and `@Cacheable` cause confusing behavior | One skips the method, the other forces execution. | Split methods or design clearly mutually exclusive conditions. |
| Cache annotation has no effect | `@EnableCaching` not enabled or bean is not proxied. | Check cache configuration and ApplicationContext. |
| Internal call does not cache | Self-invocation bypasses the proxy. | Move the method to another bean or use AspectJ. |
| `@CacheEvict` does not evict when method fails | Default eviction occurs after the method succeeds. | Use `beforeInvocation=true` if business logic requires it. |
| Both `key` and `keyGenerator` declared | The two attributes are mutually exclusive. | Choose one key generation approach. |
| Both `cacheManager` and `cacheResolver` declared | The two cache resolution mechanisms are mutually exclusive. | Choose CacheManager or CacheResolver. |
| SpEL in @Value does not update when property changes | Value is injected during bean initialization lifecycle. | Use an appropriate dynamic refresh/configuration mechanism. |

## 17. Workflow for integrating SpEL into annotations

1. Determine whether the annotation needed is `@Value` or a cache annotation.
2. For `@Value`, use placeholders for simple configuration and SpEL for calculations/bean references.
3. Declare default values intentionally; configure strict placeholders if properties are required.
4. Determine target types and ConversionService if custom converters are needed.
5. For caching, enable `@EnableCaching` and configure CacheManager/CacheResolver.
6. Define keys that fully reflect every input affecting the result.
7. Use `#a0`/`#p0` if parameter names are not retained in bytecode.
8. Distinguish `condition` (before invocation) from `unless` (after invocation).
9. Only use `#result` in phases where the cache abstraction provides the result.
10. Choose the right annotation: `@Cacheable` to read/populate cache, `@CachePut` to always run the method and update cache, `@CacheEvict` to remove entries.
11. Check proxy semantics, public methods, and self-invocation.
12. Test cache hit/miss, key, condition, unless, eviction, property resolution, and conversion.

## 18. Key takeaways

- `@Value` uses `${...}` to retrieve properties and `#{...}` to evaluate SpEL.
- `@Value` can read system properties, beans, static members, and collection literals.
- `@Value` values are injected during bean processing; they do not auto-refresh when configuration changes.
- Cache annotations have their own EvaluationContext with `#root.method`, `#root.target`, `#root.args`, argument variables, and `#result` per phase.
- Use SpEL `key` to select parameters or nested properties for building cache keys.
- `condition` is evaluated before the method; `unless` is evaluated after the method.
- `#result` is only available in supported expression phases, not in `@Cacheable` condition.
- `@Cacheable` can skip the method on cache hit; `@CachePut` always runs the method; `@CacheEvict` removes cache entries.
- `@EnableCaching` enables annotation-driven caching; proxy mode does not intercept self-invocation.
- Cache keys must include every factor that changes the result, including tenant/locale if applicable.

## References

- [Spring Framework Reference — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework Reference — SpEL Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Javadoc — Cacheable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework Javadoc — CachePut](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html)
- [Spring Framework Javadoc — CacheEvict](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
