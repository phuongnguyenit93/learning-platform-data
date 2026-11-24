# Accessing `#root.methodName`, `targetClass`, `args`, and `caches` in Spring Cache

## 1. The Spring Cache SpEL Root Object

Spring Cache supports Spring Expression Language (SpEL) in `@Cacheable`'s `key` and `condition` attributes, as well as several attributes of `@CachePut` and `@CacheEvict`. Whenever a method is processed through the Spring Cache interceptor, the framework creates a dedicated *evaluation context* so SpEL knows which method is being called, which arguments were passed, and which caches were selected.

In that context, **`#root` is the root object of the current cache operation**. The four attributes to learn:

| Expression | Value and Type | Meaning |
| --- | --- | --- |
| `#root.methodName` | `String`, e.g. `"find"` | Name of the Java method being invoked. |
| `#root.targetClass` | `Class<?>`, e.g. `CatalogService.class` | Class of the target object. |
| `#root.args` | `Object[]` array, e.g. `["B-7", "vi"]` | Actual arguments in call order, 0-based index. |
| `#root.caches` | Collection of `org.springframework.cache.Cache` | Caches resolved for the current operation. |

Suppose `CatalogService.find("B-7")` is annotated with `@Cacheable(cacheNames = "catalog")`. When called **through a Spring-managed proxy**, you can picture the context like this:

~~~text
service.find("B-7")
       |
       v
Spring Cache interceptor
       +-- #root.methodName  = "find"
       +-- #root.targetClass = CatalogService.class
       +-- #root.args        = ["B-7"]
       +-- #root.caches      = [Cache("catalog")]
       |
       v
Evaluate SpEL for key / condition
       |
       +-- cache hit  -> use cached data
       +-- cache miss -> run method then store result if permitted
~~~

`#root` describes **the invocation**, not the contents of a cache entry or a list of every cache in the system. This context is created by Spring Cache; if you use `SpelExpressionParser` directly outside the cache interceptor, these values will not be present automatically.

## 2. Using Each Attribute

### 2.1. `#root.methodName` — Method Name

`#root.methodName` returns the method name, such as `"find"`. Spring also provides `#root.method`, which is the method metadata; `#root.method.name` is another way to get the name.

Common use case: adding a prefix so different methods sharing one cache do not overwrite each other's keys.

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.methodName + ':' + #p0")
~~~

This is an annotation snippet placed on an appropriate method. For `find("B-7")`, the key is `find:B-7`; for `findSummary("B-7")`, the key is `findSummary:B-7`.

However, `methodName` is **not the full signature**. Two overloads `find(String)` and `find(long)` still have the same name. If different parameter values can convert to the same string, design an unambiguous key encoding or use a `KeyGenerator`.

### 2.2. `#root.targetClass` — Target Class

`#root.targetClass` is a `Class<?>` object, **not** a class name string by default. On Java 17+, you can access the name via SpEL:

~~~text
#root.targetClass
#root.targetClass.simpleName
#root.targetClass.name
#root.targetClass.packageName
~~~

For class `demo.CatalogService`, `simpleName` typically gives `"CatalogService"` and `name` gives `"demo.CatalogService"`. `simpleName` can collide across packages. If a shared key needs to distinguish class names, `name` is usually clearer.

Distinction: `#root.target` is the **target object instance being invoked**, whereas `#root.targetClass` is the **class of that object**. Including class metadata in keys can help namespace entries, but it also means keys change when renaming or refactoring packages. Do not add class names to every key out of habit.

### 2.3. `#root.args` — Argument Array

Suppose a method has signature `find(String code, String locale)` and is called with `find("B-7", "vi")`:

| Access Form | Value |
| --- | --- |
| `#root.args[0]` | `"B-7"` |
| `#root.args[1]` | `"vi"` |
| `#p0` or `#a0` | `"B-7"` |
| `#p1` or `#a1` | `"vi"` |
| `#code` | `"B-7"` if parameter names are discovered by Spring. |

`#root.args[0]`, `#p0`, and `#a0` all access the first parameter by **position**. `#code` depends on bytecode containing discoverable parameter names, such as compiling with the `-parameters` flag.

Example of a localized result depending on both code and language:

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.args[0] + ':' + #root.args[1]")
~~~

With `find("B-7", "vi")`, the key is `B-7:vi`. Taking only `args[0]` would cause `find("B-7", "vi")` and `find("B-7", "en")` to share the same key even though their results must differ.

**Constraints and choices:**

- Indexing starts at **0**. `args[1]` on a single-parameter method will fail during evaluation.
- On a no-argument method, do not use `args[0]`.
- For complex arguments, pick a stable identifier field (such as `#p0.id` if accessible) rather than relying on `toString()` or object identity.
- Joining arguments into a string with a delimiter can cause key collisions when the data itself contains that delimiter. For complex keys, design a dedicated encoding or a `KeyGenerator`.
- Do not put sensitive secrets into keys if the backend, logs, or metrics might record keys.

### 2.4. `#root.caches` — Caches for the Current Operation

`#root.caches` is the collection of `Cache` objects resolved through `CacheResolver` for this operation. It is neither the list of all caches known to `CacheManager` nor the collection of entries inside a cache.

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.caches[0].name + ':' + #p0")
~~~

Here `#root.caches[0]` is the first `Cache` object, and `.name` reads the name via `Cache#getName()`. If the cache is named `catalog` and the argument is `B-7`, the key will be `catalog:B-7`.

When an annotation declares multiple caches, such as `cacheNames = {"catalog", "catalogBackup"}`, the cache list in context can contain multiple elements. **Do not** assume each cache gets a completely separate key just by using `#root.caches[0].name`; the operation's computed key is used when interacting with the resolved caches.

If a custom `CacheResolver` supplies no caches, indexing `[0]` is unsafe. In most cases, cache names already separate namespaces, so repeating the cache name inside the key is unnecessary. This example mainly demonstrates how to access metadata.

## 3. Runnable Demo with Spring Boot 3, Java 17+

We build a key using all four attributes:

~~~text
#root.methodName + '|' +
#root.targetClass.simpleName + '|' +
#root.args[0] + '|' +
#root.caches[0].name
~~~

When calling `CatalogService.find("B-7")` on a cache named `catalog`, the expected key is: `find|CatalogService|B-7|catalog`.

Use a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Create `src/main/java/demo/CacheSpelApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheSpelApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheSpelApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    CommandLineRunner demo(CatalogService service, CacheManager manager) {
        return args -> {
            System.out.println("1 = " + service.find("B-7"));
            System.out.println("2 = " + service.find("B-7"));

            String key = "find|CatalogService|B-7|catalog";
            Cache cache = manager.getCache("catalog");
            if (cache == null) {
                throw new IllegalStateException("Missing catalog cache");
            }
            System.out.println("key = " + key);
            System.out.println("from cache = " + cache.get(key, String.class));
        };
    }
}

class CatalogService {
    @Cacheable(
            cacheNames = "catalog",
            key = "#root.methodName + '|' + "
                    + "#root.targetClass.simpleName + '|' + "
                    + "#root.args[0] + '|' + "
                    + "#root.caches[0].name"
    )
    public String find(String code) {
        System.out.println("LOAD " + code);
        return "title:" + code;
    }
}
~~~

Run `./gradlew bootRun` if the project has a Gradle Wrapper (Windows: `gradlew.bat bootRun`), or `gradle bootRun` if a compatible Gradle version is installed. Alongside Spring Boot's banner and startup logs, the program prints these demo lines in order:

~~~text
LOAD B-7
1 = title:B-7
2 = title:B-7
key = find|CatalogService|B-7|catalog
from cache = title:B-7
~~~

**Step-by-step explanation:**

1. `@EnableCaching` enables annotation processing. `CatalogService` is registered via `@Bean`; calls from `CommandLineRunner` go through the Spring-managed object.
2. The first `find("B-7")` call is a **cache miss**, so the method body runs and prints `LOAD B-7`; then `title:B-7` is stored.
3. The second call has the same metadata and argument, so the key is unchanged. This is a **cache hit** and skips executing the `find` body, which is why only one `LOAD` line appears.
4. `Cache#get(key, String.class)` confirms that the corresponding key holds the stored value.

Key parts:

| Attribute | Demo Value |
| --- | --- |
| `#root.methodName` | `find` |
| `#root.targetClass.simpleName` | `CatalogService` |
| `#root.args[0]` | `B-7` |
| `#root.caches[0].name` | `catalog` |

The complete key is `find|CatalogService|B-7|catalog`. In Java, annotation string literals concatenated with `+` are joined at compile time, so Spring receives a single SpEL string.

`ConcurrentMapCacheManager` is a local in-memory cache with no default TTL and no automatic synchronization across multiple instances. It was chosen to illustrate expressions; other providers have their own storage policies.

## 4. Writing Conditions and Avoiding Wrong Keys

### 4.1. `condition` Is Evaluated Before Using the Cache

An example for a method with a `String` first parameter:

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.args[0]",
           condition = "#root.args[0] != null and !#root.args[0].isBlank()")
~~~

When `condition` is `false`, this annotation's cache operation is skipped, while the method body still executes. The expression above only fits the stated signature; it cannot be applied verbatim to a non-`String` parameter.

`#root` represents invocation metadata, whereas `#result` represents the return value after the method runs and is **not available** in `@Cacheable`'s `key` or `condition`. `#result` can be used in `@Cacheable`'s `unless`, `@CachePut`'s `key`, or post-invocation `@CacheEvict` expressions (`beforeInvocation = false`), depending on context.

### 4.2. Aligning Key Rules on Update/Evict

If `@Cacheable` on `find` uses `key = "#root.methodName + ':' + #p0"`, it produces `find:B-7`. Copying that exact expression onto `@CacheEvict` on `update` produces `update:B-7`. The two keys are **not equal**, so eviction will not delete the entry that `find` stored.

The solution is to align key rules between read and write paths: for simple cases, use `key = "#p0"` on both `@Cacheable` and `@CacheEvict`; for complex cases, build a well-tested key generator or helper. Including method/class names in a key only makes sense when invalidation paths are accounted for.

### 4.3. `#root` Does Not Solve Every Consistency Problem

SpEL identifies a specific key; it does not automatically remove entries when the database is modified by another service. If data is read by tenant, locale, or version, those factors must appear in the key appropriately. TTL, invalidation events, and cache backend selection are separate decisions regarding freshness and data consistency.

## 5. Common Mistakes

| Mistake / Misconception | Cause | Fix |
| --- | --- | --- |
| Writing `#methodName` and treating it like `#root.methodName`. | `methodName` is a property on the root object, not a standalone variable by default. | Use `#root.methodName`. |
| Treating `#root.targetClass` as a `String` class name. | It is a `Class<?>`. | Use `.name` or `.simpleName` when a name string is needed. |
| Reading `#root.args[1]` on a single-parameter method. | Index exceeds array bounds. | Check the signature; indexing starts at 0. |
| Expression `#code` is not resolved. | Parameter names may not be stored in bytecode. | Use `#p0`, `#a0`, or `#root.args[0]`. |
| Confusing `#root.caches` with all caches in the app. | It only holds caches resolved for the operation. | Check `cacheNames` or `CacheResolver`. |
| `#root.caches[0].name` fails. | Resolver returned no first element or configuration is wrong. | Verify resolved caches before indexing `[0]`. |
| Calling twice still runs the method twice. | Caching not enabled, key changes, entry expired, or self-invocation bypasses proxy. | Check `@EnableCaching`, proxy, key, and provider policies. |
| `@CacheEvict` fails to remove the right entry. | Key expressions differ between read and write methods. | Compare actual keys and unify the rule. |

In particular, calling `this.find(...)` inside `CatalogService` itself normally bypasses the Spring proxy in default proxy mode. As a result, `@Cacheable` may not execute. Call through a Spring-managed bean and inspect the provider or logs to separate proxy issues from SpEL issues.

## 6. Self-Check

**Question 1.** With `find("B-7", "vi")`, which expressions retrieve the second argument?

Answer: `#root.args[1]`, `#p1`, or `#a1`.

**Question 2.** How do `#root.caches[0]` and `#root.caches[0].name` differ?

Answer: the first gets the `Cache` object, while the second gets that cache's name.

**Question 3.** Does `#root.targetClass` mean the same thing as `#root.target`?

Answer: no. The first is the `Class<?>` of the target object; the second is the target object itself.

**Question 4.** Why should you not copy `#root.methodName + ':' + #p0` verbatim from `find` to `update` for eviction?

Answer: the method prefix changes from `find` to `update`, producing two different keys. Eviction must target the exact cached key.

**Question 5.** When should you use `#p0` instead of `#code`?

Answer: when you want positional access without depending on Spring's ability to read parameter names from bytecode.

**Key takeaway:** `#root.methodName`, `#root.targetClass`, `#root.args`, and `#root.caches` expose metadata of the current cache invocation. Include all parameters affecting the result, keep keys stable, and align keys across read, update, and delete operations.

Reference: [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html).
