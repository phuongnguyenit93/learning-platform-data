# JDK Proxies, Class-Based Proxies, and `proxyTargetClass` in Spring Cache

## 1. Objectives and Big Picture

Spring Cache relies on **Spring AOP** to apply the behavior of `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@Caching` when a method call passes **through a Spring proxy**. Consequently, the same annotation can work or be skipped depending on the call path, the bean's interfaces, the proxy type, `final` modifiers, method visibility, and the `proxyTargetClass` configuration.

Three core concepts:

- **JDK dynamic proxy (interface-based proxy):** the proxy object is created via the standard JDK proxy mechanism and **implements the interfaces** that Spring chooses to expose. It is not a subclass of the implementation class.
- **Class-based proxy (CGLIB):** Spring generates a runtime subclass of the implementation class. The proxy is an instance of the target class type, able to intercept overridable methods while respecting AOP constraints.
- **`proxyTargetClass`:** an option selecting the proxy strategy. In caching proxy mode, `@EnableCaching(proxyTargetClass = true)` requests class-based proxies; `false` is the **Spring Framework** default and generally prefers JDK proxies when the target has interfaces.

Do not equate **proxy mode** with **proxy type**. Proxy mode (`AdviceMode.PROXY`) means advice runs at the proxy boundary; within that mode, JDK or CGLIB is how the proxy object is created. By contrast, `AdviceMode.ASPECTJ` uses weaving (a separate configuration), and is **not** a "stronger" version of CGLIB.

### Practical Question

Suppose `ProductServiceImpl` implements `ProductService`:

~~~java
public interface ProductService {
    Product get(long id);
}

public class ProductServiceImpl implements ProductService {
    @Override
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product get(long id) {
        return repository.find(id);
    }

    @Cacheable(cacheNames = "stats", key = "#p0")
    public String internalStats(long id) {
        return repository.stats(id);
    }
}
~~~

This is an **illustrative snippet**: it requires `Product`, `repository`, Spring beans, and `@EnableCaching`. With a JDK proxy, callers normally can only invoke APIs belonging to the `ProductService` interface through the proxy; `internalStats` is not on the interface, so it is not exposed on a JDK proxy. With a class-based proxy, callers can use the `ProductServiceImpl` type and call the public `internalStats` method through the proxy, provided it is eligible for advice.

What matters is not "whether the annotation appears in source code," but **whether the method call is intercepted by the Spring interceptor**.

## 2. What Rules Does Spring Use to Choose the Proxy Type?

In standard Spring AOP proxying, the general selection is:

| Target bean | `proxyTargetClass=false` | `proxyTargetClass=true` |
| --- | --- | --- |
| Has at least one eligible interface to proxy | Typically creates a JDK dynamic proxy | Creates a class-based proxy via CGLIB |
| Has no interface to proxy | Still creates a class-based proxy (cannot use JDK interface proxy) | Creates a class-based proxy |
| `final` class with interface | Can use JDK proxy for supported interface methods | Cannot subclass a `final` class with CGLIB |
| `final` method on non-`final` class | Interface methods can be intercepted at the JDK proxy layer | Cannot override `final` method to advise with CGLIB |
| No applicable cache/advisors | Not necessarily proxied | Not necessarily proxied; `true` does not turn every bean into a proxied bean |

**The rule "false = JDK proxy" is not absolute.** If a bean has no interface for Spring to expose, a class-based proxy is still the viable choice when caching proxy mode is enabled. Other auto-proxy components, global configuration, Spring Boot, and framework versions can also affect the final outcome. **Inspect the actual proxy object** rather than concluding from a single annotation.

## 3. JDK Dynamic Proxy: Interface-Based

A JDK dynamic proxy is created by the JVM to implement one or more interfaces. A call:

~~~text
Caller
  |
  v
JDK proxy implements ProductService
  |
  v
Spring CacheInterceptor / AOP advice
  |
  +--> cache hit: return result
  |
  +--> cache miss: call target ProductServiceImpl.get(id)
~~~

Because a JDK proxy **does not extend `ProductServiceImpl`**, the following characteristics are important:

1. You can inject and call via the **interface type** (`ProductService`), which minimizes coupling to the implementation.
2. You cannot cast a JDK proxy to `ProductServiceImpl` even though the underlying target is of that class. `proxy instanceof ProductServiceImpl` is `false`.
3. A public method existing **only on the implementation** and not in the proxy interface is not part of the callable API on a JDK proxy. If you need to expose that method, consider adding it to the interface or choosing a class-based proxy.
4. Placing `@Cacheable` on the **implementation method** is the stable choice when the proxy strategy might change; Spring can look up the cache operation from the target method. Do not put annotations exclusively on interfaces and assume every mode/weaving/version behaves identically.
5. A JDK proxy can work with a `final` implementation class because it **does not subclass** that class. However, interception is still limited to methods exposed via the interface.
6. The **self-invocation** issue still exists: a method on the target calling `this.get(id)` does not go back through the JDK proxy.

Dependency injection example:

~~~java
@Service
class ReportService {
    private final ProductService productService; // fine with JDK proxy

    ReportService(ProductService productService) {
        this.productService = productService;
    }
}
~~~

The snippet above needs the interface, annotation imports, and a Spring context. If you change the constructor parameter to `ProductServiceImpl` while the actual bean is a JDK proxy, injecting by concrete class can fail because the proxy is not a subtype of that class.

### Do Not Rely on Runtime Class Names

Names such as `jdk.proxy2.$Proxy...` or generated class suffixes vary across JDKs, runtimes, and Spring versions. Use:

~~~java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
~~~

The `org.springframework.aop.support.AopUtils` class provides these helpers. Appropriate boolean/type checks are far more robust than regex matching on class names.

## 4. Class-Based Proxy: CGLIB Subclass

When a class-based proxy is selected, Spring generates a subclass of the target class (CGLIB is repackaged inside `spring-core`). The proxy can override inheritable and overridable methods, insert advice, and delegate to the target when needed:

~~~text
Caller invokes ProductServiceImpl
          |
          v
ProductServiceImpl$$SpringCGLIB$$... (subclass)
          |
          v
Spring CacheInterceptor
          |
          v
ProductServiceImpl target method (if execution is needed)
~~~

Advantages:

- The proxy **is a subtype** of the implementation, so callers can inject/cast to the concrete type (absent other configuration issues).
- Can expose public methods on the class that are not part of a business interface.
- Can be used for beans **not implementing any interface**.

Limitations to keep in mind:

- **A `final class` cannot be subclassed**; therefore class-based proxies cannot apply to it. Java `record` types are final by default and should not be chosen to hold cache-advised business methods requiring subclass proxies.
- **A `final method` cannot be overridden**, so CGLIB cannot advise it via subclass interception.
- **A `private method` cannot be overridden**, so it cannot be advised by CGLIB. Methods invisible to the subclass (such as package-private methods on a superclass in another package) may also not be advised.
- With the Java Platform Module System module path, subclass proxies can hit package/module access restrictions and require proper module configuration. Do not use `--add-opens` indiscriminately as a default workaround.
- CGLIB proxies can be instantiated via Objenesis to avoid invoking the target constructor a second time; do not write business logic depending on how many times a constructor runs due to proxy implementation details.
- In Kotlin, classes and methods are final by default; Spring "open" compiler plugins may be necessary. Even then, turning on `proxyTargetClass=true` alone does not automatically make every Kotlin class a valid proxy target.

**CGLIB is not a solution for self-invocation.** Once a call enters the target object, `this.someCacheableMethod()` is still an internal call and can bypass proxy advice. This is a property of the **proxy boundary**, not of the proxy generation technology.

### Public vs. Non-Public in Caching

To keep source code portable between JDK/CGLIB and across Spring versions, **prefer cache annotations on public methods** of Spring-managed beans. Some subclass-based AOP mechanisms can intercept `protected` or package-visible methods at the bytecode level, but that does not automatically guarantee cache annotations are processed across all configurations. Private and final methods have clear restrictions; if non-public interception is truly needed, verify annotation policy and test it in practice.

## 5. What Does `@EnableCaching(proxyTargetClass = ...)` Mean?

Plain Spring Framework configuration (no Spring Boot dependency):

~~~java
@Configuration
@EnableCaching(proxyTargetClass = false)
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

This is an illustrative configuration needing corresponding imports. With `false`, when a bean has suitable interfaces, Spring typically uses a JDK dynamic proxy; when there is no interface, Spring can still create a CGLIB proxy.

To **force class-based proxies** in proxy mode:

~~~java
@Configuration
@EnableCaching(proxyTargetClass = true)
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

The configuration snippets above share the same class name only to compare **two independent choices**; in an application you pick the appropriate configuration rather than declaring two classes with the same name.

### Similar-Looking Flags That Do Completely Different Things

| Configuration | Effect |
| --- | --- |
| `@EnableCaching(proxyTargetClass=true)` | Selects class-based proxies for **caching advice** in proxy mode |
| `@EnableCaching(mode=AdviceMode.PROXY)` | Selects proxy-based caching (default) |
| `@EnableCaching(mode=AdviceMode.ASPECTJ)` | Selects AspectJ weaving, requiring weaving setup and `spring-aspects`; `proxyTargetClass` is no longer meaningful in this mode |
| `@Configuration(proxyBeanMethods=false)` | Disables proxying of **`@Bean` method calls inside the configuration class**; not a flag for choosing JDK/CGLIB for service caching |
| Spring Boot `spring.aop.proxy-target-class=false` | Affects Spring AOP auto-configuration in Boot, potentially yielding interface-based proxies unless overridden elsewhere |

**Global effect:** `proxyTargetClass=true` does not necessarily affect only one bean. Spring can merge settings across multiple auto-proxy creators; forcing class-based proxies in one place can affect beans using `@Transactional` or other Spring AOP advisors in the same context. Changing this flag can therefore change proxy types and bean injection behavior elsewhere.

**Spring Boot vs. plain Spring Framework:** Spring Boot AOP documentation notes that Boot auto-configuration defaults to CGLIB and can be switched back to JDK proxies via `spring.aop.proxy-target-class=false`. Conversely, the default `proxyTargetClass` attribute on `@EnableCaching` in core Spring Framework is `false`. Do not deduce the final proxy type from a single default alone; check properties, configured advisors, and the actual object obtained from the context.

**Version note:** Spring Framework 7.0 introduces `@Proxyable` to select interface/class proxying at the bean level in supported configurations; this is a version-specific feature, not a universal equivalent to `@EnableCaching(proxyTargetClass=true)` across all Spring versions.

## 6. Which Methods Can Receive Cache Advice?

| Case | JDK interface proxy | Class-based proxy |
| --- | --- | --- |
| Public method on interface and cache-annotated on implementation | Can be advised if called through proxy | Can be advised if method is non-final and configuration permits |
| Public method only on implementation | Not present on the JDK proxy interface | Can be advised if overridable |
| Private method | Not exposed on interface to invoke via proxy as business method | Cannot be overridden/advised by subclass |
| Final method on implementation | Can be advised through interface proxy call, since advice runs outside target | Cannot be overridden to advise |
| Final class with interface | Interface can be proxied | Final class cannot be subclassed |
| Self-invocation via `this` | Bypasses proxy advice | Bypasses proxy advice |
| Object created with `new` instead of retrieved from context | Not wrapped by a Spring proxy | Not wrapped by a Spring proxy |
| Internal call inside `@PostConstruct` | Should not rely on an incompletely initialized proxy | Should not rely on an incompletely initialized proxy |

"Can be" differs from "guaranteed": the annotation must still be detected, the bean eligible for the advisor, the proxy present, the right cache manager/resolver configured, and the call must actually go through the proxy.

**Specifically regarding `final`:** saying "`final` always stops `@Cacheable` from working" is overly broad. The `final` limitation is a CGLIB subclass-overriding issue. A JDK proxy can intercept calls through the interface before delegating to a target with a `final` method. However, that is not a reason to build a caching design around `final` implementations; always verify the actual proxy.

## 7. Standalone Runnable Java 17+ Example: Two Contexts, Two Proxy Types

The example below uses the same interface and implementation but runs them in **two independent `AnnotationConfigApplicationContext` instances**. Each context has its own `CacheManager` to avoid global configuration interference. `GreetingServiceImpl` has:

- `greet(name)`: present on the interface, annotated with `@Cacheable`.
- `extra(name)`: a public method **only on the implementation**, also annotated with `@Cacheable`.

With the JDK proxy, the caller invokes `greet` via the interface; the proxy cannot be cast to the implementation to call `extra`. With the CGLIB proxy, the caller casts to the implementation and can call both methods; two calls with the same key run the target only once.

### 7.1. Maven `pom.xml`

Uses JDK 17+ and Spring Framework 7.0.9; no Spring Boot or database needed.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-proxy-types</artifactId>
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

### 7.2. File `src/main/java/demo/CacheProxyTypesDemo.java`

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CacheProxyTypesDemo {

    private CacheProxyTypesDemo() {}

    public interface GreetingService {
        String greet(String name);
    }

    public static class GreetingServiceImpl implements GreetingService {
        private int greetLoads;
        private int extraLoads;

        @Override
        @Cacheable(cacheNames = "greetings", key = "#p0")
        public String greet(String name) {
            System.out.println("load greet " + (++greetLoads));
            return "Hello, " + name;
        }

        // Method not present on the GreetingService interface.
        @Cacheable(cacheNames = "extras", key = "#p0")
        public String extra(String name) {
            System.out.println("load extra " + (++extraLoads));
            return "Extra, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(proxyTargetClass = false)
    public static class JdkConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("greetings", "extras");
        }

        @Bean
        GreetingService greetingService() {
            return new GreetingServiceImpl();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(proxyTargetClass = true)
    public static class ClassConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("greetings", "extras");
        }

        @Bean
        GreetingService greetingService() {
            return new GreetingServiceImpl();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {
            Object bean = context.getBean("greetingService");
            System.out.println(
                    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
            System.out.println(
                    "JDK instanceof impl: "
                    + (bean instanceof GreetingServiceImpl));

            GreetingService service = (GreetingService) bean;
            System.out.println("JDK call 1: " + service.greet("Linh"));
            System.out.println("JDK call 2: " + service.greet("Linh"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(ClassConfig.class)) {
            Object bean = context.getBean("greetingService");
            System.out.println(
                    "CGLIB proxy: " + AopUtils.isCglibProxy(bean));
            System.out.println(
                    "CGLIB instanceof impl: "
                    + (bean instanceof GreetingServiceImpl));

            GreetingServiceImpl service = (GreetingServiceImpl) bean;
            System.out.println("CGLIB call 1: " + service.greet("Linh"));
            System.out.println("CGLIB call 2: " + service.greet("Linh"));
            System.out.println("Extra call 1: " + service.extra("Linh"));
            System.out.println("Extra call 2: " + service.extra("Linh"));
        }
    }
}
~~~

Both configuration classes set `proxyBeanMethods=false` so `@Bean` method calls do not use separate configuration-class proxying; the **cache proxy** choice is controlled solely by `@EnableCaching(proxyTargetClass=...)` in each context.

### 7.3. Run and Output

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheProxyTypesDemo
~~~

Lines printed by the program in exact order (excluding Maven/framework logs):

~~~text
JDK proxy: true
JDK instanceof impl: false
load greet 1
JDK call 1: Hello, Linh
JDK call 2: Hello, Linh
CGLIB proxy: true
CGLIB instanceof impl: true
load greet 1
CGLIB call 1: Hello, Linh
CGLIB call 2: Hello, Linh
load extra 1
Extra call 1: Extra, Linh
Extra call 2: Extra, Linh
~~~

**Why is the output like this?**

1. The JDK config has `proxyTargetClass=false`, and the target implements `GreetingService`. The bean is a JDK proxy implementing the interface, not a `GreetingServiceImpl`.
2. `greet("Linh")` misses on the first call and prints `load greet 1`, then hits on the second call without incrementing the counter.
3. Closing the JDK context and opening the class-based context creates a new cache/bean; the new target's counters start from 0 again.
4. The CGLIB config requests a subclass proxy; the object is an instance of `GreetingServiceImpl`, so casting to the implementation succeeds.
5. `extra("Linh")` is a public, non-final annotated method; the CGLIB proxy exposes it and hits the cache on the second call.

If you tried calling `((GreetingServiceImpl) bean).extra("Linh")` in the JDK block, the program would throw `ClassCastException`. The example deliberately avoids throwing this error to keep output clean, though you can test it intentionally.

The example is a self-contained Maven project in terms of **source**. The output above is reasoned from the cache operations and call flow; when integrating into a real system, run it to verify dependency/plugin versions and runtime settings.

## 8. Self-Invocation: Switching to CGLIB Still Cannot Save It

Consider:

~~~java
@Service
public class ProductServiceImpl {
    public Product fetchViaHelper(long id) {
        return get(id); // implicit this.get(id)
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product get(long id) {
        return repository.find(id);
    }
}
~~~

This snippet requires `Product` and a repository. If a caller invokes `fetchViaHelper` **through the proxy**, the outer call can go through the proxy, but the internal call `this.get(id)` executed by the target will not loop back through the proxy. Thus `@Cacheable` on `get` is not applied for that internal call; `get` runs directly even if the cache already holds an entry. This is inherently true for both JDK and CGLIB proxy modes.

Ways to handle it:

- **Prefer extracting a bean:** put the cached `get` method into a `CachedProductReader`, inject that bean into the orchestrating service, and invoke via the Spring-managed reference. No proxy-internals tricks needed.
- **Restructure the public API:** external callers invoke the cached method directly through the proxy.
- **Self-injection or `AopContext.currentProxy()`:** can work under specific conditions but creates coupling to AOP/proxy exposure and can be confusing; not the default choice.
- **AspectJ weaving:** can handle internal invocations via bytecode weaving, but requires `spring-aspects` and load-time or compile-time weaving configuration; this is a completely different strategy from `proxyTargetClass`.

Similarly, an object created with `new ProductServiceImpl()` instead of retrieved from `ApplicationContext` does not automatically get Spring caching advice.

## 9. Annotations on Interface vs. Implementation?

Spring recommends placing `@Cacheable`, `@CacheEvict`, and `@CachePut` on the **concrete implementation class/method** to avoid differences in Java annotation inheritance and discovery mechanics across interface proxies, class proxies, and AspectJ.

Preferred example:

~~~java
public interface CatalogService {
    Item find(String sku);
}

@Service
public class CatalogServiceImpl implements CatalogService {
    @Override
    @Cacheable(cacheNames = "items", key = "#p0")
    public Item find(String sku) {
        return repository.find(sku);
    }
}
~~~

This is a snippet lacking `Item`/repository. The interface describes the business contract; caching is an implementation policy. Annotations placed only on the interface may work in certain setups, but should not be assumed intact when changing proxy types/AspectJ or upgrading versions. If you must annotate an interface, write integration tests for that exact mode.

## 10. Configuration and Versions: Subtle Traps

### 10.1. Global Configuration Flags

Spring can merge multiple auto-proxy creators; a configuration requesting class-based proxies can cause beans with `@Transactional` or other advisors to also be wrapped in subclass proxies, not just cache-annotated beans. When enabling `proxyTargetClass=true`, audit class-based injection sites, test mocks, generic interfaces, and `final` classes before treating it as a local tweak.

### 10.2. Spring Boot May Pick a Different Default

Spring Boot auto-configures Spring AOP with its own defaults, and Boot documentation states that class-based proxies (CGLIB) are the default for AOP auto-configuration; the property `spring.aop.proxy-target-class=false` can switch back to JDK proxies. If an app combines `@EnableCaching`, `@EnableAspectJAutoProxy`, transaction advice, or other configurations, the outcome depends on how they merge. **Measure the proxy type with `AopUtils` rather than guessing from starter names.**

### 10.3. Spring Framework 7 and @Proxyable

Spring Framework 7 introduces `@Proxyable` to select proxy strategies at the bean level in supported scenarios. This is a version-specific capability and does not apply retroactively to all Framework 6 apps. Do not recommend `@Proxyable` by default without confirming the running framework version and involved auto-proxy processors.

### 10.4. Native Image and Module Path

Class-based proxies require dynamic subclassing or properly prepared proxy metadata during AOT/native image builds. Java module access rules can restrict subclass generation. Starting cleanly on a standard JVM is not enough to prove native-packaging compatibility; test under the actual build/deploy mode.

### 10.5. Avoid Premature Optimization Based on Proxy Speed

Performance differences between JDK proxies and CGLIB should not be the sole deciding factor. For caching, cache hit/miss ratios, serializers, backend/network latency, transactions, and method cost usually matter far more. Choose the proxy type primarily based on **method contract, injection capabilities, class constraints, and AOP configuration**.

## 11. Debugging When @Cacheable Does Not Work

A systematic diagnostic sequence:

1. **Is `@EnableCaching` present in the right application context?** The annotation on a method alone does not enable caching infrastructure.
2. **Is the bean managed by Spring?** If created with `new`, there is no auto-proxying.
3. **Is the bean actually a proxy?** Check `AopUtils.isAopProxy(bean)`, then classify with `isJdkDynamicProxy`/`isCglibProxy`.
4. **Does the call path go through the proxy?** If self-invocation/`this.method()`, refactor.
5. **For JDK proxies, is the method on the proxy interface?** If only on the implementation, clients calling via the JDK proxy cannot invoke it.
6. **For CGLIB, is the class/method `final` or `private`?** Cannot subclass final classes or override private/final methods.
7. **Is the annotation detected on the target implementation?** Do not rely solely on annotations on interfaces or ineligible methods.
8. **Are `cacheNames`, key, `condition`, `unless`, and manager/resolver right?** A valid proxy does not guarantee a second call hits if keys differ or conditions fail.
9. **Are other advisors interfering?** `@Transactional`, `@Async`, security, retry, and auto-proxy settings can alter proxy type, ordering, or call paths.
10. **Test with a counter.** Call the same method twice through the Spring bean with the same key and check how many times the target method executes.

Runtime inspection example (snippet requires Spring AOP on the classpath):

~~~java
Object bean = context.getBean("greetingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
~~~

Do not parse generated proxy class names to branch behavior; testing against the **API contract and business method execution counts** is more reliable.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `proxyTargetClass=false` always yields JDK | Beans without interfaces still become CGLIB, causing confusion | Check interfaces and runtime proxy type |
| Injecting implementation type when bean is a JDK proxy | Type mismatch; injection/cast fails | Inject via interface or use class proxy intentionally |
| Assuming CGLIB proxies run on every method | Final/private methods cannot be advised | Use public non-final methods through proxy |
| Assuming `final` classes always work with CGLIB | Subclass proxy cannot be created | Design interface + JDK proxy or remove final if appropriate |
| Assuming CGLIB handles self-invocation | Cache annotation on self-called method is bypassed | Extract bean and call through proxy |
| Putting cache annotations only on interfaces | Less consistent across modes/versions | Prefer annotations on the implementation |
| Testing only with `new ServiceImpl()` | No advice even with valid annotations | Retrieve bean from Spring context |
| Confusing `@Configuration(proxyBeanMethods=false)` with `proxyTargetClass=false` | Misreading configuration | Distinguish configuration proxying from service AOP |
| Enabling `proxyTargetClass=true` without checking other advisors | Other transactional/AOP beans may change proxy type | Check merged config and run integration tests |
| Ignoring Spring Boot auto-AOP | Wrong default proxy type assumptions | Inspect properties, context, and `AopUtils` |
| Blaming cache misses on proxy type | Keys, TTL, condition, unless, self-invocation also cause misses | Measure counters and trace cache operations |

## 13. Design Checklist

When deciding between JDK proxies and class-based proxies for Spring Cache:

- Does the business API have an interface? Can callers depend on the interface instead of the concrete class?
- Are there public methods needing advice that are not on the interface? Is it worth adding them to the interface rather than forcing class proxies?
- Are there `final`, `private`, or module access restrictions on classes or methods?
- Are `@EnableCaching(proxyTargetClass=...)`, Spring Boot AOP properties, or other advisors forcing a stronger proxy type configuration?
- Do all cacheable calls pass through the Spring-managed proxy? Are `this.method()` or `new` bypassing it?
- Are `@Cacheable`/`@CacheEvict` placed on the implementation with valid cache names, keys, and conditions?
- Does code/tests cast or inject implementation classes or assume generated proxy names?
- Do you have integration tests in the **exact runtime mode** of your app verifying `AopUtils`, hit/miss, method visibility, and self-invocation?

## 14. Official References

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK dynamic proxies, CGLIB, `final`/`private` limits, self-invocation, and proxy type configuration.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, `proxyTargetClass`, proxy vs. AspectJ, annotation discovery, and enabling caching.
- [Spring Framework — EnableCaching Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/EnableCaching.html): contract for `proxyTargetClass`, `mode`, `order`.
- [Spring Framework — AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): APIs for inspecting proxy types.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): class-based proxy default in Boot and the `spring.aop.proxy-target-class` property.

**Conclusion:** JDK proxies represent **interfaces**, CGLIB creates **subclasses of the implementation**, and `proxyTargetClass` controls proxy strategy preference in the corresponding configuration. Neither automatically solves self-invocation; for caching to work properly, calls must go through the proxy, target eligible methods, and be verified by runtime behavior.