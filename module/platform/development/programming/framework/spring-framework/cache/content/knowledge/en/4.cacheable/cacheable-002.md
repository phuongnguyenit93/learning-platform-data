# Applying @Cacheable at the Class Level and Method Level in Spring Framework

## 1. At Which Two Scopes Does @Cacheable Operate?

In Spring Cache, `@Cacheable` describes a policy for storing **method invocation results** by key. The first call with a key that is not yet stored is typically a **cache miss**: Spring executes the method and stores the value if conditions permit. Subsequent calls where the cache holds the corresponding value are a **cache hit**: the interceptor returns the cached data without normally executing the method body.

The `org.springframework.cache.annotation.Cacheable` annotation can be placed on `METHOD` **or** `TYPE` (class). The difference lies in the scope of methods that receive this policy:

| Declaration style | Methods that are cached | Suitable use case |
| --- | --- | --- |
| **Method-level**: place `@Cacheable` before `findById` | Only the annotated method; other methods in the same class do not automatically inherit the policy. | Services mixing reads and writes; each query has different caching needs. |
| **Class-level**: place `@Cacheable` before `class` | Methods of the class are handled by the Spring cache interceptor; in common proxy mode, attention focuses on `public` methods invoked **through the Spring proxy**. | A class dedicated solely to cacheable read operations using a consistent key rule. |

**Key point to remember:** `@Cacheable` placed on a class *can actually cache the class's methods even if those methods do not carry individual annotations*. Meanwhile, `@CacheConfig` placed on a class **does not activate caching**: it only supplies shared configuration for declared cache operations.

Placing the annotation does not mean every call is cached: `@EnableCaching` must be enabled, an appropriate `CacheManager` must exist, the call must go through an eligible bean/proxy, and `condition`, `unless`, and provider policies must be satisfied.

## 2. Method-Level @Cacheable: Selecting the Right Read Operations

A service with multiple responsibilities should declare caching only on methods that genuinely need optimization:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productNames", key = "#p0")
    public String findName(String productId) {
        return repository.findName(productId);
    }

    public String findCategory(String productId) {
        return repository.findCategory(productId);
    }

    public void updateName(String productId, String newName) {
        repository.updateName(productId, newName);
    }
}
~~~

*The snippet above illustrates the declaration style; it assumes the project defines `ProductRepository`, enables caching, and has a cache named `productNames`. It is not a standalone Java program.*

Suppose a client using the Spring bean calls `findName("p1")` twice:

1. The first time, key `p1` is not in `productNames` → **miss**, the repository is called and the value can be cached.
2. The second time, if the key is still valid → **hit**, Spring returns the result without running `findName`.
3. Calling `findCategory("p1")` twice still executes the repository **twice** because that method has no `@Cacheable` and the class has no `@Cacheable` either.
4. `updateName(...)` still executes normally, but **does not automatically remove** `findName`'s value from the cache. When source data changes, invalidation or cache updates must be applied (such as an appropriate `@CacheEvict` policy).

`cacheNames` chooses where the value is stored; `key` determines the entry identifier. The expression `#p0` refers to the **first parameter**, useful when Java does not retain parameter names in bytecode. If `key` is omitted, Spring uses the default key generator based on the parameter list.

Method-level declarations make it clear right at the call site when reading code that `findName` is cached while `findCategory` is not. They also allow defining separate caches, keys, conditions, and update strategies when methods have differing characteristics.

## 3. Class-Level @Cacheable: A Broader Scope

If a class consists exclusively of cacheable read operations, `@Cacheable` can be placed on the class:

~~~java
@Service
@Cacheable(
    cacheNames = "productReadModels",
    key = "#root.methodName + ':' + #p0"
)
public class ProductReadService {
    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    public String findName(String productId) {
        return repository.findName(productId);
    }

    public String findCategory(String productId) {
        return repository.findCategory(productId);
    }
}
~~~

*This is an illustrative snippet, not a standalone runnable file.*

Both `findName("p1")` and `findCategory("p1")` receive the class's cache policy. The expression `#root.methodName` is the name of the method currently being invoked in Spring Cache's SpEL context:

- `findName("p1")` produces the key `findName:p1`.
- `findCategory("p1")` produces the key `findCategory:p1`.

### Why is the key so important at the class level?

The default key generator `SimpleKeyGenerator` normally relies only on **the parameters**, without automatically adding the method name. For two methods that both accept `"p1"` and share the `productReadModels` cache, both could end up using the single key `p1`. In that case, a `findName` result stored earlier could be mistakenly returned by `findCategory`, even though the two methods should return different types/contents.

The solution is to choose separate cache namespaces per result type or build keys that incorporate the method identity, such as `#root.methodName + ':' + #p0`. If a specific method needs a more complex key, an appropriate `key` or `keyGenerator` can be used at the method level.

**Do not place `@Cacheable` on an entire class just to "optimize everything at once."** If a method with side effects—such as `update`, `sendEmail`, `incrementCounter`, or `charge`—is added later, a cache hit could cause its method body to be skipped. Placing the annotation at the class level is only safe when the scope of cached methods is clearly understood and aligned with business requirements.

## 4. Complete Example: Observing Both Approaches with Java 17+ and Spring Boot 3.x

The example uses `spring-boot-starter-cache`, `@EnableCaching`, and `ConcurrentMapCacheManager`. Two independent cache regions (`byClass` and `byMethod`) make the behavior of each declaration style clear. `ConcurrentMapCacheManager` stores entries in the process's RAM; the demo focuses on annotation scope, with no TTL or Redis requirements.

In a **Spring Boot 3.x project already configured with the Java/Spring Boot plugins**, add the dependency to `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Create **`src/main/java/com/example/cacheplacement/CachePlacementApplication.java`** with the complete Java code:

~~~java
package com.example.cacheplacement;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CachePlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(CachePlacementApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("byClass", "byMethod");
    }

    @Bean
    ProductSource productSource() {
        return new ProductSource();
    }

    @Bean
    ClassLevelService classLevelService(ProductSource source) {
        return new ClassLevelService(source);
    }

    @Bean
    MethodLevelService methodLevelService(ProductSource source) {
        return new MethodLevelService(source);
    }

    @Bean
    CommandLineRunner compare(ClassLevelService byClass,
                              MethodLevelService byMethod) {
        return args -> {
            System.out.println("C1=" + byClass.findName("p1"));
            System.out.println("C2=" + byClass.findName("p1"));
            System.out.println("C3=" + byClass.findCategory("p1"));
            System.out.println("C4=" + byClass.findCategory("p1"));

            System.out.println("M1=" + byMethod.findName("p1"));
            System.out.println("M2=" + byMethod.findName("p1"));
            System.out.println("M3=" + byMethod.findCategory("p1"));
            System.out.println("M4=" + byMethod.findCategory("p1"));
        };
    }

    public static class ProductSource {
        public String loadName(String id) {
            System.out.println("DB name " + id);
            return "Keyboard " + id;
        }

        public String loadCategory(String id) {
            System.out.println("DB category " + id);
            return "Accessories " + id;
        }
    }

    // Both methods share a common class-level cache policy.
    @Cacheable(
        cacheNames = "byClass",
        key = "#root.methodName + ':' + #p0"
    )
    public static class ClassLevelService {
        private final ProductSource source;

        public ClassLevelService(ProductSource source) {
            this.source = source;
        }

        public String findName(String id) {
            return source.loadName(id);
        }

        public String findCategory(String id) {
            return source.loadCategory(id);
        }
    }

    // Only findName is cached.
    public static class MethodLevelService {
        private final ProductSource source;

        public MethodLevelService(ProductSource source) {
            this.source = source;
        }

        @Cacheable(cacheNames = "byMethod", key = "#p0")
        public String findName(String id) {
            return source.loadName(id);
        }

        public String findCategory(String id) {
            return source.loadCategory(id);
        }
    }
}
~~~

Run from the root directory of a project configured with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
gradlew.bat bootRun
~~~

Ignoring Gradle/Spring Boot startup logs, **the lines explicitly printed by the demo** are:

~~~text
DB name p1
C1=Keyboard p1
C2=Keyboard p1
DB category p1
C3=Accessories p1
C4=Accessories p1
DB name p1
M1=Keyboard p1
M2=Keyboard p1
DB category p1
M3=Accessories p1
DB category p1
M4=Accessories p1
~~~

| Call | Calls `ProductSource`? | Explanation |
| --- | --- | --- |
| `C1` | Yes | `findName:p1` misses for the first time in `byClass`. |
| `C2` | No | Second call hits for `findName:p1`. |
| `C3` | Yes | `findCategory:p1` is a different key, so it misses. |
| `C4` | No | Second call hits for `findCategory:p1`; this is the effect of the **class-level** annotation. |
| `M1` | Yes | `findName` has method-level `@Cacheable`; first call misses in `byMethod`. |
| `M2` | No | Second call hits for the annotated method. |
| `M3`, `M4` | **Yes on both calls** | `findCategory` carries no annotation and the class does not carry `@Cacheable` either. |

Both services are registered in the Spring context via `@Bean`; `CommandLineRunner` receives them via dependency injection. As a result, calls go through Spring proxies, allowing the cache interceptor to operate. If you create them with `new` outside Spring and call them directly, the annotations will not automatically take effect.

**Distinguishing compilation methods:** The Java file above is complete code inside a **Spring Boot** project, relying on Spring dependencies and Spring context startup. It is not a plain JDK-only file to run with `javac`/`java` without a classpath. The `bootRun` command provides the appropriate runtime environment.

## 5. How Does Class-Level @CacheConfig Differ from Class-Level @Cacheable?

`@CacheConfig` is used to share default attributes such as `cacheNames`, `keyGenerator`, `cacheManager`, or `cacheResolver`. By itself, `@CacheConfig` **does not create a cache operation** for any method.

Illustrative example:

~~~java
@CacheConfig(cacheNames = "products")
@Service
public class SelectiveProductService {

    @Cacheable(key = "#p0")
    public String findName(String id) {
        return loadNameFromSource(id);
    }

    public String findCategory(String id) {
        return loadCategoryFromSource(id);
    }
}
~~~

*This snippet only illustrates the annotation; the two helper functions `loadNameFromSource` and `loadCategoryFromSource` must be implemented by the application author, so it does not compile standalone.*

Here:

- `findName` is cached because it **has `@Cacheable`**; the cache name `products` is inherited from `@CacheConfig`.
- `findCategory` remains uncached, even though it is in the same class as `@CacheConfig`.
- Cache operation parameters declared at the method level can override the defaults from `@CacheConfig`.
- When a method has its own cache annotation while the class has `@Cacheable`, Spring prioritizes the cache metadata applied directly on the method. Individual methods can be customized, but overlapping designs that make it hard for readers to tell which cache is used should be avoided.

In most services that mix reads and writes, the easiest approach to control is `@CacheConfig` for shared settings combined with `@Cacheable` placed only on the specific methods that need caching.

## 6. Conditions Required for the Annotation to Take Effect

`@EnableCaching` lets Spring apply caching annotations via AOP. The default mode is **proxy**, so pay attention to the following points:

1. **Spring-managed bean:** Objects created with `new` are not automatically wrapped by a caching proxy. Use a Spring-managed bean injected into the caller.
2. **External call:** A method inside a bean calling `this.findName(id)` will not pass through the proxy in normal mode. This is *self-invocation*; the annotation may appear in the source code yet not trigger caching for that internal call.
3. **Visibility:** With proxy mode, prefer `public` methods. Do not assume `private`, `protected`, or package-private methods are cached like `public` ones under every configuration.
4. **Class/interface placement:** Spring recommends placing cache annotations on concrete implementation classes and their methods, as annotations on interfaces can depend on the proxy creation mechanism or AspectJ.
5. **Bean lifecycle:** Do not rely on calls inside `@PostConstruct` to verify caching; the proxy may not yet be active as you expect.
6. **Cache names and keys:** Different methods sharing a cache and the same parameter set can collide on the default key. Be extra careful when applying class-level caching.
7. **Storage conditions:** `condition` decides whether caching applies before the call; `unless` can veto caching after the method runs. Each cache provider also has its own policies regarding `null` storage, eviction, capacity limits, and expiration.

### Interaction with write methods

`@Cacheable` is suited for reusable **read results**. It does not automatically track database changes. At both the class and method levels, whenever a write path exists, you must design invalidation with `@CacheEvict`, cache updates with `@CachePut`, TTL, or event coordination according to consistency requirements.

It is especially dangerous when a class has `@Cacheable` at the top and later gains methods with side effects such as `placeOrder`, `charge`, `incrementCounter`, or `sendNotification`. If the call is handled by the cache interceptor and results in a hit, **the method body may not run**. That behavior is wrong for write operations that must execute. Isolate methods with side effects into a separate bean or place `@Cacheable` only on individual read methods.

## 7. Choosing Annotation Placement Based on Service Design

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Service with `findById`, `save`, `delete` | `@Cacheable` only on `findById` | Avoids the risk of skipping methods with side effects. |
| Read-only class where every eligible method is cached | Class-level `@Cacheable` can be used | Less annotation repetition, but requires managing keys and auditing new methods. |
| Multiple methods share `cacheNames`, only a few need caching | `@CacheConfig` + `@Cacheable` on methods | Shares configuration while keeping scope selective. |
| Methods have different keys, conditions, or invalidation strategies | `@Cacheable` on each method | Clear and easy to maintain. |
| Data must always reflect the latest update | Re-evaluate caching and design consistency | Annotation placement alone does not determine data freshness. |

Before moving from method-level to class-level, review all eligible methods in the class as well as methods expected to be added later. This is a functional scope change, not merely a shorthand syntax choice.

## 8. Self-Check Exercises

**Question 1.** A class has `@Cacheable("catalog")`; `findName("p1")` and `findCategory("p1")` are both `public` and both called through a Spring proxy. Can both use the cache?

**Answer:** Yes. Placing the annotation at the class level applies the cache policy to eligible methods. However, if using the default key and the same cache, two methods receiving `"p1"` can collide on keys; you must design keys that distinguish the results.

**Question 2.** Replace `@Cacheable("catalog")` with `@CacheConfig(cacheNames = "catalog")` without adding annotations on the methods. Will there be cache hits?

**Answer:** No cache operations are declared to activate caching for calls. `@CacheConfig` only holds default configuration.

**Question 3.** `@Cacheable` is on the method, yet `this.findName("p1")` is called from another method of the same bean. Why are no cache hits observed?

**Answer:** Self-invocation bypasses the Spring caching proxy in default proxy mode. You must call through a valid bean/proxy or use an appropriate weaving mechanism if required.

**Question 4.** A service has a `charge(id)` method that performs payment processing. Should `@Cacheable` be placed on the whole class to make this method faster?

**Answer:** No. A cache hit could skip the method body, violating business execution requirements. Idempotency in payments must be solved with business mechanisms, not `@Cacheable`.

**Question 5.** Why did demo call `C4` not print `DB category p1` while `M4` did?

**Answer:** `C4` hit thanks to `@Cacheable` on the `ClassLevelService` class; `M4` called `findCategory` on `MethodLevelService`, which is not cached.

## 9. References

- [Javadoc `@Cacheable` — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html): `TYPE`/`METHOD` scope and annotation attributes.
- [Declarative Annotation-based Caching — Spring Framework](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): SpEL keys, `@CacheConfig`, proxies, `@EnableCaching`, and execution constraints.

**Takeaway:** **Method-level** `@Cacheable` affects only the annotated method; **class-level** `@Cacheable` extends the policy to eligible methods of the class. `@CacheConfig` helps share configuration when you still want to select precisely which methods are cached.