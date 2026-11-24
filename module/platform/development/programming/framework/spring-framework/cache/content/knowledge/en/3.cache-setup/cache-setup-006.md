# Verifying Spring-Managed Business Beans So Spring Cache Works

## 1. Objectives

In Spring Framework, a method annotated with `@Cacheable` is not guaranteed to be cached. The annotation only expresses intent; Spring must **manage the business object as a bean**, enable the caching infrastructure, and route calls through the corresponding advice mechanism. When encountering "I added `@Cacheable` yet it queries the data every single time," the first crucial setup step is verifying **where the object being called actually comes from**.

After this lesson, you will be able to:

1. Verify that a service/repository/business bean is actually present in the running `ApplicationContext`.
2. Distinguish **managed by Spring** from **proxied for caching** and **actually producing cache hits**.
3. Inspect beans by name, type, proxy status, and cache advice using Spring APIs.
4. Diagnose configuration errors such as wrong package scanning, multiple contexts, manually instantiating objects with `new`, `self-invocation`, unproxyable methods, or missing `@EnableCaching`.
5. Run a Java 17+ example contrasting a Spring-returned bean with an ordinary object.

**Key criterion:** Calls must go through a bean reference provided by Spring—typically an **AOP proxy**—not merely through any class annotated with `@Service` and `@Cacheable`.

## 2. What Is a Spring-Managed Bean?

`ApplicationContext` is the container holding `BeanDefinition`s, responsible for instantiating, configuring, dependency-injecting, and managing bean lifecycles. A *business bean* can be a service executing business logic, a repository, a client adapter, or a data-access component. With default Spring AOP caching, Spring typically creates a **proxy** representing an eligible bean; callers must invoke through the proxy for caching advice to get a chance to run.

Common ways to register a business bean:

| Registration method | Example | Condition to exist in context |
| --- | --- | --- |
| Component scanning | `@Service`, `@Component`, `@Repository` | Class falls within `@ComponentScan` or Spring Boot's default scan; not excluded by filters/profiles/conditions. |
| Java configuration | `@Bean PriceService priceService()` | The `@Configuration` class containing the `@Bean` method must be registered/imported into the context. |
| Other imports/config | `@Import`, XML, programmatic bean registration | Bean definition is actually loaded into the current context. |

`@Service` is a specialization of `@Component`, so the component scanner can detect it. However, **merely putting `@Service` on a class does not make it appear automatically in every context**.

Example configuration code for an application using component scanning:

~~~java
@Configuration
@ComponentScan(basePackages = "com.example.catalog")
@EnableCaching
public class CatalogConfig {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

~~~java
package com.example.catalog.service;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String sku) {
        return "product-" + sku;
    }
}
~~~

**Note:** The two snippets above illustrate configuration in a project with appropriate Spring dependencies, not a full standalone program. The scan scope `com.example.catalog` includes its subpackage `com.example.catalog.service`. If `ProductService` sits in a different package outside the scan, the bean will not be registered automatically.

With Spring Boot, `@SpringBootApplication` includes default component scanning from the application class's package downward into subpackages. `@EnableCaching` is still the step that activates caching annotation processing and can be placed on an appropriate configuration class.

### "Spring-Managed" Does Not Mean "Cached"

Three assertions that must be verified separately:

- **Bean is managed:** The container finds the corresponding bean and returns a reference on `getBean(...)`/dependency injection.
- **Bean is AOP-proxied:** The reference may be a proxy created by Spring AOP, yet that proxy might hold only transaction/security advice and not necessarily caching advice.
- **Caching works:** Calls pass through the proxy to a method with `@Cacheable`, key/condition/cache backend are valid, and repeated calls can return from cache without executing the business method.

Relationship diagram:

~~~mermaid
flowchart TD
    A[Business class] --> B{Registered in ApplicationContext?}
    B -->|No| C[Fix scan, Bean config, profile, or context]
    B -->|Yes| D{Caching enabled and cache operation present?}
    D -->|No| E[Check EnableCaching and annotation]
    D -->|Yes| F{Call goes through cache AOP proxy?}
    F -->|No| G[Check new, self-invocation, proxy limits]
    F -->|Yes| H[Check key, cache, condition, and hit/miss]
~~~

## 3. Step 1 — Verify the Business Bean Exists in the Right Context

Suppose we need to check a `ProductService` inside `ApplicationContext context`. The following statements are **illustrative snippets inside code that already has `context` and class `ProductService`**:

~~~java
// Check by bean name (default name for @Service is usually productService):
boolean existsByName = context.containsBean("productService");

// Check by type; succeeds when only one matching bean exists:
ProductService service = context.getBean(ProductService.class);

// List bean names matching the type:
String[] names = context.getBeanNamesForType(ProductService.class);
System.out.println(Arrays.toString(names));
~~~

### How to Interpret Results

- `context.containsBean("productService") == true`: the container recognizes a bean under **that name** (potentially including beans in a parent context). **Does not prove caching advice is present on the bean**.
- `context.containsBean("productService") == false`: that name does not exist; **you cannot yet conclude this bean type is unmanaged**, because the name might have been overridden, aliased, or the proxy registered under a different type.
- `getBean(ProductService.class)` succeeds: the container can supply a bean of the requested type. If none exists, Spring typically throws `NoSuchBeanDefinitionException`; if multiple unresolvable candidates exist, it throws `NoUniqueBeanDefinitionException`.
- `getBeanNamesForType(...)` returns candidate names by type and helps spot duplicate registrations. In systems using JDK dynamic proxies, **the concrete implementation class** may not be the type exposed by the proxy; prefer checking by the interface that clients inject.
- `context.getBean("productService")` returns the reference the application should use. Compare this reference with the object actually being called to detect code creating instances manually.

Bean name and type APIs have limits worth knowing. `containsBeanDefinition(name)` (on an appropriate `BeanFactory`) checks definitions registered **locally** in that factory, unlike `containsBean(name)` which can search up into parents. Some type-query operations can trigger bean or `FactoryBean` initialization during diagnostics; avoid overusing full bean scans on request paths.

### Quick Spring Boot Check

In a Boot environment with an injected `ApplicationContext`, you can write a startup check or integration test:

~~~java
@Component
public class BeanPresenceCheck {
    private final ApplicationContext context;

    public BeanPresenceCheck(ApplicationContext context) {
        this.context = context;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {
        System.out.println(
            "service present = " + context.containsBean("productService")
        );
    }
}
~~~

This is an **illustrative snippet for a Spring Boot application**, requiring the corresponding imports for `ApplicationContext`, `Component`, `EventListener`, `ApplicationReadyEvent`, and an actual `productService` bean. `ApplicationReadyEvent` lets you inspect after Boot finishes starting; do not put cache checks in a constructor or `@PostConstruct` and assume proxies are already active.

## 4. Step 2 — Verify the Proxy and Cache Advice

Spring Cache in default `@EnableCaching(mode = AdviceMode.PROXY)` mode uses Spring AOP proxies. If code invokes the bean via the exact reference returned by the context, you can inspect several signals:

~~~java
Object bean = context.getBean("productService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

These statements are **illustrative snippets**, requiring `org.springframework.aop.support.AopUtils` and an appropriate context.

| Result | Meaning |
| --- | --- |
| `AopUtils.isAopProxy(bean) == false` | The reference is not a Spring AOP proxy; possibly because no advisor applies, caching is not enabled, or the object was obtained/created differently. |
| `isJdkDynamicProxy(bean) == true` | Interface-based proxy; code should inject/call through the interface and avoid casting to the implementation class. |
| `isCglibProxy(bean) == true` | Subclass-based proxy of the target class; `final` classes or `final` methods have proxy limitations. |
| `getTargetClass(bean)` | Reveals the target business class when the proxy's class name carries a runtime-generated suffix. |

**Important:** A proxy may exist because of `@Transactional`, logging, or another advice. Therefore `isAopProxy == true` **is not enough to prove a caching interceptor is attached**.

### Checking for `CacheInterceptor` Among Advisors

For a Spring AOP proxy accessible via the `Advised` interface:

~~~java
Object bean = context.getBean("productService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getAdvice().getClass().getName());
    }
}
~~~

Illustrative imports: `org.springframework.aop.framework.Advised` and `org.springframework.aop.Advisor`. A typical annotation-based caching advisor uses advice `org.springframework.cache.interceptor.CacheInterceptor`.

You can check specifically with:

~~~java
boolean hasCacheAdvice =
    bean instanceof Advised advised &&
    Arrays.stream(advised.getAdvisors())
          .anyMatch(advisor ->
              advisor.getAdvice() instanceof CacheInterceptor);
~~~

This is a **diagnostic check**, not an API guarantee across every advice mechanism: a proxy can be configured as opaque or methods can be advised via AspectJ weaving. Having `CacheInterceptor` on the proxy still does not prove **the called method** matches the pointcut/cache operation; you must test actual behavior.

### Desired Call Path

~~~text
Controller / job / message listener
    -> Spring-injected reference of ProductService
    -> Spring AOP proxy
    -> CacheInterceptor (if method has an applicable cache operation)
    -> Cache / business method per hit-miss
~~~

In `proxy mode`, direct calls via `this.method()` from the same object enter the target without going back through the proxy. Conversely, calling a public method on a container-supplied bean from another bean is the most predictable path.

## 5. Step 3 — Confirm Cache Infrastructure and Actual Behavior

Once bean presence and proxy status are verified, check the caching configuration:

1. Is `@EnableCaching` present in the exact `ApplicationContext` containing the business bean?
2. Is there at least one suitable `CacheManager` (or custom `CacheResolver`), and does the cache name resolve properly?
3. Does the called method have a cache operation, such as `@Cacheable("products")`, with an appropriate key, condition, and visibility?
4. Does the caller obtain the reference from dependency injection/`getBean` rather than `new ProductService()` or `this.find()`?
5. When called twice with **the same key**, does the business method execution count drop from two to one?

Example cache-name check (illustrative with `context`):

~~~java
CacheManager manager = context.getBean(CacheManager.class);
Cache products = manager.getCache("products");

System.out.println("cache resolved = " + (products != null));
~~~

Imports: `org.springframework.cache.CacheManager` and `org.springframework.cache.Cache`. `getCache("products") != null` only proves the cache can be resolved; it **does not confirm the method was advised or that the cache holds entries**. Some managers create caches lazily on demand, whereas managers configured with fixed names reject other names.

A more reliable way to test caching is counting how many times the business method executes. If calling twice with the same argument executes the method once, and adding an evict causes the method to run again, you have evidence of the advice's behavior. Control for factors that skew conclusions: `condition`, `unless`, TTL, eviction, concurrent calls, self-memoizing targets, and previously cached data.

## 6. Standalone Runnable Java 17+ Example with Maven

This example registers `PriceService` via `@Bean`, so it does not rely on package scanning; it then verifies **the bean is managed**, **the proxy contains `CacheInterceptor`**, **the cache name resolves**, and **two calls with the same key compute only once**. Finally, it contrasts this with an instance created directly via `new`.

Uses Java 17+, Maven, and Spring Framework **7.0.9** (a release available on Maven repositories). Create the structure:

~~~text
managed-bean-cache/
├── pom.xml
└── src/main/java/demo/ManagedBeanCacheDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>managed-bean-cache</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/demo/ManagedBeanCacheDemo.java`:**

~~~java
package demo;

import java.util.Arrays;

import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheInterceptor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ManagedBeanCacheDemo {

    @Configuration
    @EnableCaching(proxyTargetClass = true)
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    // Business object. The @Bean above is managed and proxied by Spring.
    public static class PriceService {
        private int invocations;

        @Cacheable(cacheNames = "prices", key = "#p0")
        public String price(String sku) {
            invocations++;
            System.out.println("compute " + sku + " #" + invocations);
            return "price-" + sku + "-" + invocations;
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Object bean = context.getBean("priceService");
            PriceService service = context.getBean(PriceService.class);

            System.out.println("registered = " +
                context.containsBean("priceService"));
            System.out.println("same bean by type = " + (bean == service));
            System.out.println("is AOP proxy = " + AopUtils.isAopProxy(bean));
            System.out.println("is CGLIB proxy = " + AopUtils.isCglibProxy(bean));

            boolean hasCacheAdvice =
                bean instanceof Advised advised &&
                Arrays.stream(advised.getAdvisors())
                      .anyMatch(advisor ->
                          advisor.getAdvice() instanceof CacheInterceptor);

            System.out.println("cache advice = " + hasCacheAdvice);
            System.out.println("cache exists = " +
                (context.getBean(CacheManager.class)
                        .getCache("prices") != null));

            System.out.println("first = " + service.price("SKU-1"));
            System.out.println("second = " + service.price("SKU-1"));

            PriceService plain = new PriceService();
            System.out.println("plain first = " + plain.price("SKU-1"));
            System.out.println("plain second = " + plain.price("SKU-1"));
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.ManagedBeanCacheDemo"
~~~

**Lines printed by the program, ignoring Maven/environment logs:**

~~~text
registered = true
same bean by type = true
is AOP proxy = true
is CGLIB proxy = true
cache advice = true
cache exists = true
compute SKU-1 #1
first = price-SKU-1-1
second = price-SKU-1-1
compute SKU-1 #1
plain first = price-SKU-1-1
compute SKU-1 #2
plain second = price-SKU-1-2
~~~

Explanation:

- `Config` is a Spring configuration with `@EnableCaching` providing `CacheManager` and the `priceService` bean. Even though the factory method contains `new PriceService()`, **the instance returned from `@Bean` is still managed by the Spring container** and can be wrapped in a proxy after initialization.
- `getBean("priceService")` and `getBean(PriceService.class)` return the same **proxy reference** of the bean (the example intentionally uses a class-based proxy).
- `isAopProxy`, `isCglibProxy`, and inspecting advisors prove the bean has a caching proxy under this configuration.
- The first `service.price("SKU-1")` call misses the cache: the business method prints `compute ... #1`. The second call with the same key hits, so no extra `compute` line prints.
- The `plain` instance was invoked directly without ever going through the Spring container: both calls execute the method body and the counter increments.
- `ConcurrentMapCacheManager` is only an in-memory cache suitable for demos. It does not provide cross-process sharing or persistence after the application shuts down.

**Scope of runnability:** This is a complete Spring Core program (requiring no Spring Boot or database). When moving to a real application, so dependency injection obtains the right service proxy, preserve the "bean in context + call through proxy" principle and swap in a manager suited to your environment.

## 7. Variant with `@Service` and Component Scanning

In real projects, the more common registration style is:

~~~java
// File: src/main/java/com/example/catalog/service/PriceService.java
package com.example.catalog.service;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return "price-" + sku;
    }
}
~~~

~~~java
// File: src/main/java/com/example/catalog/CatalogConfig.java
package com.example.catalog;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "com.example.catalog")
@EnableCaching
public class CatalogConfig {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
~~~

This is an **illustrative pair of classes** for a package-based configuration application, without `main()`. `@ComponentScan` scans `com.example.catalog` and its subpackages; `PriceService` is registered with default name `priceService`. If config lives in `com.example.app` and scans only that package, a service in `com.example.catalog.service` can be missed. When needed, adjust base packages or use explicit `@Import`/`@Bean`.

To detect duplicate beans by type, inspect `context.getBeanNamesForType(PriceService.class)` and configure `@Primary`/`@Qualifier` when multiple candidates exist. However, if runtime uses interface-based JDK proxies, query by the injected **interface** rather than assuming the implementation class is always lookupable.

## 8. Why Might `@Cacheable` Still Not Run When the Bean Exists?

### 8.1. Instantiating the Object Outside the Container

~~~java
PriceService unmanaged = new PriceService();
unmanaged.price("SKU-1"); // Direct call; no caching proxy
~~~

This object is unregistered and has no cache advice. The conceptual exception is `new` inside a `@Bean` factory method where **the instance is returned to the container**, as in the main example; Spring management depends on **the reference used at the call site**.

**How to fix:** Inject `PriceService` into other beans via constructor injection or obtain the bean from `ApplicationContext`. Do not use `new` to call a service designed for Spring AOP.

### 8.2. Self-Invocation

~~~java
@Service
public class ProductService {
    public String loadSummary(String sku) {
        return find(sku); // this.find(sku), does not go through proxy
    }

    @Cacheable("products")
    public String find(String sku) {
        // ...
        return "product-" + sku;
    }
}
~~~

This is an illustrative snippet in an application with `@EnableCaching` and a cache manager. If a client calls `loadSummary` on the proxy, the body of `loadSummary` runs on the target object; the subsequent call to `find` via `this` does not go through the caching proxy. The bean exists, even the cache advisor exists, yet this path still skips `@Cacheable`.

**How to fix:** Extract the cacheable method into a dedicated Spring bean and inject that bean into the caller, or redesign the call path to go through the proxy. Do not treat `AopUtils.isAopProxy(service)` as proof that all internal calls will be intercepted.

### 8.3. Missing or Misplaced Annotations

- `@Service` is present, but `@Cacheable` is forgotten on the method to cache: the bean is managed, with no cache operation on that method.
- `@Cacheable` is present, but `@EnableCaching` is not enabled in the context holding the service: Spring does not set up the required advice.
- Annotating a `private` or `final` method, or a `final` class when using class-based proxies: proxy restrictions prevent advice from applying as expected.
- Putting annotations on an interface while using a weaving setup different from proxy mode: review placement. The least surprising approach is placing annotations on public methods of the concrete class.

### 8.4. Wrong Context

In systems with **parent/child `ApplicationContext`s**, or Spring MVC/Boot test slice setups, the service bean may live in a different context from the `@EnableCaching` configuration. A caching processor applies only to beans within the scope of the context it processes. A request entering the web context does not necessarily imply the root context's cache setup just because a controller is visible.

Verify: which config classes are loaded, which tier's context holds the service, where `@EnableCaching` is placed, and which bean reference is actually injected into the controller/job. `@WebMvcTest` typically loads only a slice of the application; to prove real service caching, use an integration test loading all relevant beans or explicit `@Import`s.

### 8.5. Proxy Exists Yet Cache Still Misses

Additional reasons to inspect:

- Arguments or keys differ across calls; an unstable custom `KeyGenerator`.
- `condition` evaluates to false, `unless` vetoes storing the result; null values or provider policies cause differences.
- Cache cleared by `@CacheEvict`, replaced by `@CachePut`, or expired by provider TTL.
- Wrong cache name, wrong manager/resolver, or multiple backend instances not sharing data.
- Two concurrent requests both miss before either finishes populating the cache.
- Method invoked via a direct reference to the target object even though a proxy exists in the context.

Once you confirm the bean is managed, shift inspection to **the call path, cache keys, and cache backend**, rather than adding `@Service` again.

## 9. Practical Debugging Flow in Order

| Observation | Check first | How to resolve |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Package scanning, `@Bean`/`@Import`, profiles, conditions, parent/child context | Register the bean properly in the context; avoid manual instantiation as a "workaround." |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type | Use `@Qualifier`/`@Primary` or remove unintended duplicate registrations. |
| `containsBean` is false yet code runs | Bean name may differ, or a `new` object exists outside the container | Check name/type and the actual injected reference. |
| Bean exists, `isAopProxy` is false | `@EnableCaching`, operation annotations, whether advice matches | Verify config is in the right context and the method is eligible. |
| `isAopProxy` is true, no `CacheInterceptor` | Only other AOP advice may be present | Check caching/annotation infrastructure and inspect advisors. |
| `CacheInterceptor` present, business method still runs every time | self-invocation, different keys, `condition`/`unless`, TTL/evict | Count invocations, print keys, and verify active cache entries. |
| Cache works when running app, fails in unit test | Test instantiates object directly or slice does not enable caching | Test with an appropriate context and inject beans from Spring. |
| Only some methods get cached | Method visibility/`final`, proxy interface, call path | Design eligible public methods and invoke via proxy. |

### Quick Verification Checklist

1. **Right bean?** `getBean(...)` succeeds, and the reference matches the instance the caller uses.
2. **Right context?** `@EnableCaching` is loaded within the business bean's scope.
3. **Right advisor?** `AopUtils.isAopProxy`, then inspect cache advice if needed.
4. **Right method?** Matching `@Cacheable`/operation on a public method invoked via proxy.
5. **Right cache/key?** `CacheManager` resolves the cache name, and keys across two calls are equal.
6. **Right behavior?** Second call with the same key skips the method body; after clear/evict, the next call runs again.

If the first five checks pass yet tests still fail, add an integration test mirroring the production call path; observe business method execution counts and provider hit/miss statistics before tuning or changing configuration.

## 10. Operational and Testing Notes

- **Avoid asserting on the proxy's class name:** `bean.getClass() == ProductService.class` can be false even for a completely valid bean because proxies have dynamically generated classes. `AopUtils.getTargetClass(...)` is more useful for diagnostics.
- **Do not place cache probes in a bean's own constructor or `@PostConstruct`:** proxies may not be ready there. Test from a caller bean or after context startup completes.
- **Verify business outcomes:** Seeing `CacheInterceptor` in the advisor list alone does not prove caching works accurately for the method and key being tested.
- **Do not treat `isAopProxy == false` as an absolute conclusion in every mode:** `mode = ASPECTJ` uses weaving instead of proxies; the checks here target the common proxy mode.
- **Manage scopes and concurrency:** Singleton, prototype, or scoped proxies have different lifecycles; do not confuse instance counts with cache hit counts. TTL and cache distribution belong to the provider, not to "being a managed bean."
- **Do not enable class-based proxies indiscriminately:** `proxyTargetClass = true` is handy for implementation-based inspection examples, but for interface-based apps JDK proxies are often appropriate. `final` classes/methods and Java module boundaries also affect proxying.
- **Keep test configuration realistic:** `Mockito.mock(...)` or `new` does not automatically receive advice; for tests requiring real caching, obtain beans from a Spring context. If a test focuses purely on business logic, there is no need to enable caching for a plain unit test.

## 11. Official Documentation

- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `@Service`, `@ComponentScan`, bean registration.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, method cache annotations, self-invocation, and context scope.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxies, CGLIB, `final` methods, and calls via `this`.
- [AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): API for inspecting Spring AOP proxies and target classes.
- [ApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContext.html): looking up beans by name and type.

A complete verification confirms three independent layers: **the bean exists in the right `ApplicationContext` → the bean receives caching advice per the configured mechanism → business calls traverse the advice and produce the expected cache hits/misses**.