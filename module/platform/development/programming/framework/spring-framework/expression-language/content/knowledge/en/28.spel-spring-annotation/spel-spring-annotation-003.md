# SpEL in `@Cacheable`, `@CachePut`, and `@CacheEvict`

## Objectives

Spring Cache annotations allow using the Spring Expression Language (SpEL) to determine cache keys, caching conditions, and whether to store the result. Each annotation has a specific purpose:

- `@Cacheable` checks the cache first; if a matching value exists, it returns that value and skips calling the method.
- `@CachePut` always calls the method and then updates the cache with the returned result.
- `@CacheEvict` removes an entry or the entire cache to discard stale data.

SpEL lets these decisions depend on parameters, nested properties, method metadata, or return values. To write expressions accurately, it is necessary to understand when expressions are evaluated and which variables are available at that time.

## 1. Enabling annotation-based caching

Place `@EnableCaching` on a configuration class to enable processing of cache annotations:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

The example above creates a simple cache manager with a cache named `books`. In real applications, Caffeine, Redis, or another implementation can be used depending on requirements. `@Cacheable`, `@CachePut`, and `@CacheEvict` are only processed when the caching infrastructure is enabled and the method is invoked through the corresponding interception mechanism.

## 2. SpEL evaluation context specific to cache

Spring creates a dedicated evaluation context for each cache operation. In addition to method arguments, the context has a root object containing metadata about the invocation and the caches used.

| Reference | Meaning | Example |
| --- | --- | --- |
| `#root.methodName` | Name of the method being invoked. | `#root.methodName == 'findBook'` |
| `#root.method` | The `Method` object being invoked. | `#root.method.name` |
| `#root.target` | The target object receiving the invocation. | `#root.target` |
| `#root.targetClass` | The actual class of the target. | `#root.targetClass` |
| `#root.args` | Array of method arguments. | `#root.args[0]` |
| `#root.caches` | The caches selected for the operation. | `#root.caches[0].name` |
| `#result` | Method result, only available in certain post-invocation expressions. | `#result?.id` |

The root object can be referenced with `#root`; arguments can also be accessed by name if Spring can discover the parameter names.

## 3. Accessing method arguments

Suppose a method has the signature:

```java
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

In cache expressions, parameters can be accessed by name:

```java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

Or access nested properties:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

If parameter names are unavailable in metadata that Spring can use, use positional aliases:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    // ...
}
```

`#p0` and `#a0` both refer to the first parameter; `#p1` and `#a1` refer to the second parameter. `#root.args[0]` can also be used to reference the same argument. Parameter names typically need to be retained in bytecode, for example by compiling with the `-parameters` option; positional aliases are a reliable choice when you are unsure whether parameter names are available.

## 4. `@Cacheable`: using SpEL for keys and conditions

`@Cacheable` checks the cache before running the method. If the cache has an entry for the computed key, Spring returns the cached value and the method is not invoked. If no entry exists, the method runs and the result may be stored.

### Generating keys with SpEL

```java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    return repository.findByIsbn(isbn);
}
```

The key expression can select an argument, a property of an argument, or compute a value from multiple parameters:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn, boolean includeUsed) {
    // ...
}
```

```java
@Cacheable(cacheNames = "bookSearch", key = "#p0 + ':' + #p1")
public List<Book> search(String category, String language) {
    // ...
}
```

The `key` expression can return an object as the cache key; it does not have to be a String. Keys need stable semantics and `equals()`/`hashCode()` suitable for the cache provider. For complex keys or keys used across multiple methods, consider a custom `KeyGenerator` instead of building strings manually.

If `key` is omitted, Spring uses `SimpleKeyGenerator`: with no parameters it uses `SimpleKey.EMPTY`; with one parameter it uses that parameter itself; with multiple parameters it uses a `SimpleKey` containing the parameters. If only some parameters affect the result, a `key` expression helps ignore parameters that only serve other logic.

`key` and `keyGenerator` are mutually exclusive ways of selecting keys within the same cache operation; do not declare both.

### The `condition` condition

`condition` is evaluated before the method runs. If the expression returns true, the cache operation is applied; if false, the method still runs, but the operation's caching behavior is skipped.

```java
@Cacheable(cacheNames = "books", condition = "#name.length() < 32")
public Book findBook(String name) {
    // ...
}
```

The example only caches names shorter than 32 characters. `condition` can use arguments, properties, and metadata of the root object.

### The `unless` exclusion condition

`unless` is evaluated after the method has run. If the expression returns true, the result is not added to the cache:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result == null"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

In this example, null results are not cached. `unless` is suitable when decisions need to be based on the actual result, such as only caching verified objects or not caching temporary data.

## 5. `condition` and `unless` differ in timing

This is the most important difference when writing cache expressions:

| Attribute | Evaluation timing | Can use `#result`? | If the expression returns true |
| --- | --- | --- | --- |
| `condition` | Before the method is called. | No. | Allows the cache operation to proceed. |
| `unless` | After the method has run. | Yes. | Vetoes storing the result in the cache. |

Do not use `#result` in `condition`, because the method has not run yet and there is no result yet. If the caching decision depends on the result, use `unless` when the annotation supports this attribute.

Example with an `Optional<Book>` result:

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

For wrappers supported by Spring Cache such as `Optional`, `#result` refers to the inner business object rather than the wrapper. When there is no value, `#result` can be null; use safe navigation `?.` if needed.

## 6. `@CachePut`: always runs the method then updates the cache

`@CachePut` is used when the method must execute every time, yet the result still needs to be written to the cache. Unlike `@Cacheable`, it does not skip the method just because the cache already has an entry.

```java
@CachePut(cacheNames = "books", key = "#isbn")
public Book updateBook(ISBN isbn, BookDescriptor descriptor) {
    return repository.update(isbn, descriptor);
}
```

The method runs, returns a `Book`, and then Spring uses the key expression to update the corresponding entry in the cache.

Because the method has already been invoked, `#result` can be used in the key expression of `@CachePut`:

```java
@CachePut(cacheNames = "books", key = "#result.isbn")
public Book updateBook(BookUpdate update) {
    return repository.update(update);
}
```

In this case the key is taken from the returned object. Use `#result` only when the method is guaranteed to return an appropriate object and the expression handles null cases properly.

`@CachePut` also supports `condition` and `unless`: `condition` is evaluated before invocation; `unless` is evaluated after invocation so it can veto writing the result. Do not place `@Cacheable` and `@CachePut` on the same method without clearly designed mutually exclusive conditions, because one annotation wants to skip the method while the other requires the method to run.

## 7. `@CacheEvict`: delete an entry by key or clear the entire cache

`@CacheEvict` removes stale cached data. Use `key` to remove a specific entry:

```java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void deleteBook(ISBN isbn) {
    repository.delete(isbn);
}
```

By default, `beforeInvocation` is false, meaning eviction occurs after the method completes successfully. If the method throws an exception, post-invocation eviction is not performed.

To remove all entries in the cache, use `allEntries = true`:

```java
@CacheEvict(cacheNames = "books", allEntries = true)
public void reloadBookCatalog() {
    repository.reloadCatalog();
}
```

When `allEntries = true`, Spring clears the entire cache; a specific key no longer applies to that operation. Use `allEntries` when data changes affect the entire cache region.

### Evicting before the method runs

```java
@CacheEvict(cacheNames = "books", key = "#isbn", beforeInvocation = true)
public void refreshBook(ISBN isbn) {
    repository.refresh(isbn);
}
```

With `beforeInvocation = true`, the cache entry is removed before the method runs, even if the method later throws an exception. Use this mode when cache removal must happen regardless of the method outcome.

When eviction happens after invocation (`beforeInvocation = false`), `#result` can be used in cache-evict expressions. When eviction happens before invocation, there is no result yet, so `#result` cannot be relied upon.

`@CacheEvict` does not have an `unless` attribute; if a condition is needed to perform eviction, use `condition`.

## 8. Where is `#result` available?

`#result` is the business value returned by the method, but it is only available in expressions that run after invocation:

| Expression location | `#result` available? | Reason |
| --- | --- | --- |
| `@Cacheable(key = ...)` | No. | Key is computed before the method runs to look up the cache. |
| `@Cacheable(condition = ...)` | No. | Condition is evaluated before invocation. |
| `@Cacheable(unless = ...)` | Yes. | Unless runs after the method returns. |
| `@CachePut(key = ...)` | Yes. | Method always runs before the cache is updated. |
| `@CachePut(condition = ...)` | No. | Condition is evaluated before invocation. |
| `@CachePut(unless = ...)` | Yes. | Unless runs after invocation. |
| `@CacheEvict(key/condition)` with `beforeInvocation = true` | No. | Cache eviction is performed before the method. |
| `@CacheEvict(key/condition)` with `beforeInvocation = false` | Yes, in post-invocation cache-evict expressions. | Result is already available when the operation runs. |

For `Optional` and supported wrappers, `#result` is the business object inside the wrapper. `#result?.property` can be used to avoid errors when there is no value.

## 9. Cache metadata in expressions

In addition to method arguments and `#result`, metadata of the cache operation can be used:

```java
@Cacheable(
    cacheNames = "books",
    key = "#root.methodName + ':' + #p0",
    condition = "#root.targetClass.simpleName == 'BookService'"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

Examples of using cache metadata:

```spel
#root.methodName
#root.method.name
#root.targetClass
#root.args[0]
#root.caches[0].name
```

`#root.caches` are the caches resolved for the operation. Only use index `[0]` when the operation actually has a corresponding cache at that position; if there are multiple caches, clearly understand the application's resolution order and configuration.

## 10. Using `@Caching` and `@CacheConfig`

`@Caching` groups multiple cache operations onto the same method, for example evicting multiple caches with different key expressions:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", key = "#p0"),
    @CacheEvict(cacheNames = "bookSearch", allEntries = true)
})
public void deleteBook(ISBN isbn) {
    // ...
}
```

`@CacheConfig` sets shared configuration at the class level, such as cache names, `KeyGenerator`, `CacheManager`, or `CacheResolver`:

```java
@CacheConfig(cacheNames = "books")
public class BookService {

    @Cacheable(key = "#isbn")
    public Book findBook(ISBN isbn) {
        // ...
    }
}
```

`@CacheConfig` only shares configuration; it does not enable caching by itself. Operation-level configuration can override class-level shared configuration.

## 11. Proxies, self-invocation, and intercepted methods

In the default configuration, Spring processes cache annotations using AOP proxies. Only calls that go through the proxy are intercepted. If a method in the same class directly calls another method that also has `@Cacheable`, that internal call usually bypasses the proxy, so the caching annotation on the called method has no effect.

Example:

```java
public Book loadForPage(ISBN isbn) {
    return findBook(isbn); // self-invocation: does not go through proxy
}

@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    // ...
}
```

For caching to work, call the method through a Spring-managed proxy from another bean or extract the cacheable logic into a separate bean. AspectJ mode is another option when the application needs interception beyond proxy semantics, though it requires weaving configuration.

In proxy mode, cache annotations should be placed on public methods of concrete classes as recommended by Spring. Do not rely on annotations on private methods or self-invocation.

## 12. Key design and things to avoid

A cache key must represent all inputs that affect the result. If an important parameter is omitted, two different calls might share a cache entry and return wrong data.

Example method:

```java
public Book findBook(ISBN isbn, String language) {
    // The result depends on both ISBN and language.
}
```

A key using only `#isbn` may not suffice if the same ISBN has multiple translations. You can use:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber + ':' + #language")
```

Avoid keys that:

- Depend on mutable objects whose `equals()`/`hashCode()` change after being placed in the cache.
- Use `System.currentTimeMillis()`, random values, or unstable state that causes every call to generate a different key.
- Concatenate strings without a clear delimiter or encoding, causing collisions between value pairs.
- Omit tenant, locale, user scope, or version if they affect the returned data.
- Call expensive methods or methods with side effects inside key expressions.

If key logic is complex, use a dedicated `KeyGenerator` for easier testing and maintenance. Key expressions should be short, readable, and perform no I/O.

## 13. Common errors and how to handle them

| Symptom | Causes to check | How to handle |
| --- | --- | --- |
| `#isbn` is not resolved | Parameter name is missing from metadata. | Use `#p0`, `#a0`, or `#root.args[0]`; enable `-parameters` if names are needed. |
| `#result` is null or unavailable in expression | Expression runs before method invocation. | Only use `#result` in `unless`, `@CachePut` key, or post-invocation `@CacheEvict`. |
| `@Cacheable` still runs the method every time | Cache miss, different key, false condition, or annotation is not intercepted. | Check key, cache name, condition, cache provider, and proxy invocation. |
| `unless` caches or excludes the wrong result | Veto condition logic is inverted. | Remember `unless = true` means do not cache the result; verify with concrete result examples. |
| `@CachePut` does not skip the method when cache has an entry | This is the intended behavior of `@CachePut`. | Use `@Cacheable` if the goal is to skip the method on cache hit. |
| Cache is not evicted when method throws an error | `beforeInvocation` defaults to false and method did not complete successfully. | Use `beforeInvocation = true` if removal before execution is needed regardless of outcome. |
| Entire cache is not cleared | Using key eviction instead of `allEntries = true`. | Enable `allEntries = true` for cache-wide eviction. |
| Same method has both cacheable and cache put with unpredictable behavior | Two operations have opposing purposes. | Split methods or use clear mutually exclusive conditions; do not rely on `#result` in conditions checked beforehand. |
| Caching annotation does not work on internal calls | Self-invocation bypasses the default proxy. | Call through a Spring proxy or move the method to another bean. |
| Data from another tenant/language is shared | Cache key omits part of the input affecting the result. | Add tenant, locale, or required parameters to the key. |

## Key takeaways

- `@Cacheable` checks the cache first and can skip the method; `@CachePut` always runs the method then updates the cache; `@CacheEvict` removes an entry or the entire cache.
- Cache annotations must be enabled with `@EnableCaching` or the equivalent XML configuration.
- `key`, `condition`, and `unless` are SpEL expressions in cache annotations; they do not need to be wrapped in `#{...}`.
- Use `#p0`, `#a0`, or `#root.args[0]` when parameter names are unavailable.
- `condition` runs before invocation; `unless` runs after invocation and true vetoes caching.
- `#result` is only available in post-invocation expressions: `unless`, `@CachePut` key, and `@CacheEvict` when `beforeInvocation=false`.
- `@CacheEvict` by default evicts after the method succeeds; `beforeInvocation=true` evicts before the method; `allEntries=true` clears the entire cache.
- `@CachePut` does not skip the method on cache hit; avoid combining it arbitrarily with `@Cacheable` on the same method.
- `@CacheConfig` shares class-level configuration; `@Caching` groups multiple cache operations; neither enables caching by itself.
- Proxy mode does not intercept self-invocation; call through a proxy or use an appropriate bean design.
- Cache keys must include every input affecting the result and have stable equals/hashCode semantics.

## References

- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework Reference — Cache SpEL Evaluation Context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-spel-context)
- [Spring Framework API — Cacheable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework API — CachePut](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html)
- [Spring Framework API — CacheEvict](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework API — CacheConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html)