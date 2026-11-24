# Placing Spring Cache Configuration in the Right ApplicationContext

## Lesson Objectives

A Spring application can have **one or multiple `ApplicationContext` instances**. Declaring `@Cacheable` on a service is not enough: the mechanism that detects annotations and builds caching proxies must be enabled in **the context that owns the service bean**. This is a classic reason why code still runs and always returns results, yet a `@Cacheable` method keeps executing on every call.

After this lesson, you will be able to:
- Distinguish the root context from a `DispatcherServlet` child context and understand the scope of `@EnableCaching`.
- Place `@EnableCaching`, `CacheManager`, and services in the right place in Spring Framework or Spring Boot.
- Verify proxies and caching behavior yourself with a Java 17+ example.
- Diagnose cases where caching does not work because configuration lives in the wrong context.

## 1. Principle: Cache Configuration Is Scoped to an ApplicationContext

Spring Cache processes `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@Caching` via advice/AOP. In typical configurations, `@EnableCaching` registers infrastructure so Spring inspects beans **created and processed within that same `ApplicationContext`** and applies proxies to eligible methods.

Not every application has a context hierarchy. A typical Spring Boot web application usually uses a single application context containing controllers, services, and infrastructure. However, a traditional Spring MVC application can have two tiers:

```text
Root WebApplicationContext (PARENT)
  ├─ CatalogService       <-- @Cacheable on method
  ├─ CatalogRepository
  ├─ CacheConfiguration   <-- @EnableCaching here
  └─ CacheManager
          |
          | Child can look up Parent's beans
          v
DispatcherServlet WebApplicationContext (CHILD)
  ├─ CatalogController
  ├─ HandlerMapping
  └─ WebMvcConfig
```

**Key point:** A bean in the parent can be used by the child via inherited lookup. However, the fact that the child sees parent beans **does not mean** the child's proxy-creation infrastructure re-runs on beans already created in the parent. A `BeanPostProcessor`/advisor registered in the child does not automatically turn a parent service into a cached proxy.

Placing `@EnableCaching` in the `DispatcherServlet` **child** while the service lives in **root** causes the child to process only the child's own beans (typically controllers), while the root service may remain an un-advised object with no caching.

Placement rules:

| Bean / element | Context that should own it in a two-tier MVC model | Why |
| --- | --- | --- |
| Service with `@Cacheable` | Root | Business logic shared across servlets. |
| `@EnableCaching` / caching configuration | Root | Enables proxy processing for root services. |
| `CacheManager`, `CacheResolver` serving root services | Root, or a context accessible to the service infrastructure | Root does not look up beans that exist only in a child. |
| Controllers, MVC mappings, view resolvers | Child `DispatcherServlet` | Per-servlet web infrastructure. |
| Service registered only in child | Child | If a service truly lives in the child, caching must be enabled in that child. |

This is guidance for the **typical root/child model**, not a rule forcing all caches into root. Identify **the context that actually creates the annotated bean**, then enable caching within that context.

## 2. What Is Required for Caching to Work

1. **Dependencies:** Spring Cache API/AOP must be on the classpath. With Spring Boot, `spring-boot-starter-cache` provides the baseline setup.
2. **Enable annotation processing:** Have `@EnableCaching` on a `@Configuration` loaded into the right context, or XML `<cache:annotation-driven/>` in the corresponding context.
3. **Cache storage:** Have a suitable `CacheManager` or `CacheResolver` usable by that context's cache advice. Spring Boot can auto-configure a provider if caching is enabled; plain Spring Framework typically requires explicit declaration.
4. **Spring-managed bean:** The service must be instantiated/registered by Spring and processed by that context's infrastructure.
5. **Call passes through the proxy:** In `proxy` mode (default), only calls from other beans passing through the Spring proxy are intercepted. Internal `this.find(...)` calls within the same object do not trigger caching.

Having a `CacheManager` in the application **does not automatically enable** `@Cacheable`. Conversely, enabling `@EnableCaching` in one context while placing the only cache manager in a **child** context can prevent the parent from finding the manager when creating or executing the cache advisor.

## 3. Wrong in Child, Right in Root: Self-Contained Java 17+ Example

The example below manually creates a parent and child using `AnnotationConfigApplicationContext`. No web server is needed, because the goal is to reproduce **the same context-scoping rule** encountered in multi-context Spring MVC applications.

Uses Java 17+ and Gradle 8.x. Create a project with this structure:

```text
context-cache-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ContextPlacementDemo.java
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'context-cache-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ContextPlacementDemo'
}
```

File `src/main/java/demo/cache/ContextPlacementDemo.java` (complete single-file source):

```java
package demo.cache;

import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class ContextPlacementDemo {

    public static void main(String[] args) {
        run("WRONG", RootWithoutCaching.class, ChildCachingOnly.class);
        run("RIGHT", RootWithCaching.class, ChildWebOnly.class);
    }

    private static void run(String label,
                            Class<?> rootConfig,
                            Class<?> childConfig) {
        try (AnnotationConfigApplicationContext root =
                     new AnnotationConfigApplicationContext(rootConfig);
             AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

            child.setParent(root);
            child.register(childConfig);
            child.refresh();

            DataService service = child.getBean(DataService.class);
            String first = service.find("A");
            String second = service.find("A");

            System.out.printf("%s | proxy=%s | %s | %s | executions=%d%n",
                    label, AopUtils.isAopProxy(service),
                    first, second, service.executions());
        }
    }

    // This bean will be created in the root context in both scenarios.
    public static class DataService {
        private int executions;

        @Cacheable(cacheNames = "records")
        public String find(String id) {
            return id + "-load-" + ++executions;
        }

        public int executions() {
            return executions;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ServiceBeans {
        @Bean
        DataService dataService() {
            return new DataService();
        }
    }

    // Wrong scenario: root creates the service but caching is not enabled yet.
    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    public static class RootWithoutCaching {
    }

    // Cache infrastructure in child does not re-process root beans.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class ChildCachingOnly {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("records");
        }
    }

    // Right scenario: root has both the service and caching infrastructure.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    @Import(ServiceBeans.class)
    public static class RootWithCaching {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("records");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildWebOnly {
    }
}
```

Run in the project directory with `gradle run --quiet`, or `./gradlew run --quiet` if using Gradle Wrapper (Windows: `.\gradlew.bat run --quiet`). Lines printed by the program:

```text
WRONG | proxy=false | A-load-1 | A-load-2 | executions=2
RIGHT | proxy=true | A-load-1 | A-load-1 | executions=1
```

Analysis:
- In the `WRONG` run: `ServiceBeans` is imported into root so `DataService` is created by root. `@EnableCaching` exists only in child. Child retrieves the parent bean via `getBean()`, yet that bean **is not cache-proxied**; two actual calls produce two different strings.
- In the `RIGHT` run: `@EnableCaching` shares the same scope as the service bean in root, so the bean is cache-proxied. The second call reuses the cache entry for key `"A"`, and the method executes only once.
- Each scenario creates a fresh context and a fresh `ConcurrentMapCacheManager`; therefore counters and cache entries do not leak between the two runs.
- `AopUtils.isAopProxy()` helps detect a proxy, but **`proxy=true` alone is not enough to prove caching works** (a bean could be proxied by another advice). You must verify execution count and return values as shown.

This is a minimal model of the ApplicationContext problem; `RootWithoutCaching` and `ChildCachingOnly` are **intentionally misconfigured classes for comparison** and should not be copied into real systems.

## 4. Applying This to Spring MVC with Root + Child DispatcherServlet

In a Spring MVC application using `AbstractAnnotationConfigDispatcherServletInitializer`, root config and servlet config are typically declared separately:

```java
public class ShopInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return new Class<?>[] { RootConfig.class, CacheConfig.class };
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebMvcConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}

@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan("demo.shop.service")
class RootConfig {
}

@Configuration(proxyBeanMethods = false)
@EnableWebMvc
@ComponentScan("demo.shop.web")
class WebMvcConfig {
}
```

This is an **illustrative configuration snippet** to place inside a Spring MVC project with the corresponding dependencies/imports and actual classes; it is not a standalone program. `demo.shop.service` contains service beans annotated with `@Cacheable("catalog")`. `CacheConfig` is loaded via `getRootConfigClasses()`, so it shares the same context as the services. `WebMvcConfig` handles MVC concerns in the child.

Moving `CacheConfig.class` from root to `getServletConfigClasses()` without changing where services are created will produce the exact scoping error from the previous example. When there are multiple `DispatcherServlet`s, placing shared services and caching infrastructure in root avoids accidentally creating multiple independent beans/caches.

For XML equivalence, load the following in the **root context** configuration file if services live in root:

```xml
<cache:annotation-driven cache-manager="cacheManager"/>
<bean id="cacheManager"
      class="org.springframework.cache.concurrent.ConcurrentMapCacheManager">
    <constructor-arg>
        <list><value>catalog</value></list>
    </constructor-arg>
</bean>
```

This illustrative XML snippet is only part of a configuration file declaring the proper `cache` and `beans` namespaces/schemas; it must be added to the root configuration in use. In Spring Framework, `@EnableCaching` and `<cache:annotation-driven/>` are two declaration styles for the same goal of enabling cache annotations.

## 5. Applying This to Spring Boot: Usually One Context, Scope Still Matters

In a typical Spring Boot servlet application, `@SpringBootApplication` opens the main context and runs component scanning. When controllers, services, and `CacheManager` configuration all reside in this context, root/child issues usually do not arise.

A controllable layout:

```java
// demo/shop/ShopApplication.java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}

// demo/shop/config/CacheConfiguration.java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}

// demo/shop/service/CatalogService.java
@Service
public class CatalogService {
    @Cacheable("catalog")
    public String getTitle(long id) {
        return "Item #" + id;
    }
}
```

These are **three illustrative files** (each with appropriate packages/imports), not a single Java file to copy verbatim. Because both `config` and `service` sit under the root package `demo.shop`, they are scanned into the main application context. Boot auto-configures a `CacheManager` if no manager/resolver exists and a suitable provider is present; here, the bean we declare replaces that auto-configuration need.

Spring Boot recommends separating `@EnableCaching` into its own configuration class rather than hard-attaching it to the main application class: doing so makes scope easier to control when using slice tests or wanting to disable caching in a test.

**Package scanning note:** The `CacheConfiguration` bean will not appear automatically if its package sits outside the component scan area and is not `@Import`ed. Verify that the configuration is actually loaded rather than merely checking whether the annotation exists in a file.

When a Boot system uses `SpringApplicationBuilder.parent(...).child(...)`, multiple separate contexts, or initializes a `DispatcherServlet` with a self-configured child context, apply the rule from Section 1 again: identify the context creating the service and configure caching there.

## 6. Distinguishing "Wrong Context Placement" from Other Configuration Errors

| Symptom | Cause to check | How to verify |
| --- | --- | --- |
| `@Cacheable` always runs body even for identical keys | `@EnableCaching` in child, service in parent; or caching not enabled | Inspect context tree, bean owner, `AopUtils.isAopProxy()`, execution count |
| Service cannot find `CacheManager` | Manager declared only in child, or missing compatible bean | Check manager beans in the same context and parent visible to the advisor |
| Proxy exists but cache never hits | Different key, `condition`, `unless`, TTL, provider, or wrong bean called | Log key/cache name and verify body execution count |
| `this.method()` does not cache | Self-invocation bypasses default proxy | Call from another bean through the Spring proxy |
| Only controllers are cached, services are not | Annotation processing enabled in servlet child | Move cache configuration into the service context |
| Some endpoints see stale values, others do not | Contexts have distinct services/caches, duplicated caches, or flawed invalidation | Check service/manager identity, keys, and cache regions |
| Tests behave differently from runtime | Tests build a different context/slice from production | Verify loaded context, `@Import`, and cache-enabling config |
| Multiple `CacheManager`s cause ambiguity | No default bean defined or missing resolver | Use clear default config or specify `cacheManager` on the operation |

**Root and child have asymmetric lookup directions.** Child can reference parent beans, but parent does not automatically see beans that exist only in child. If multiple cache managers are unavoidable, deliberately determine which context owns each one and how they resolve (e.g., `@Cacheable(cacheManager="...")` or `CachingConfigurer`).

**Do not scatter `@EnableCaching` across every config class.** That does not fix scope mismatches if a bean was already created in another context; it also complicates infrastructure/proxy control when multiple contexts hold duplicate configuration copies. Declare it in the context that owns the annotated beans; enable it in multiple contexts only when you genuinely want to process each context's own beans.

**Do not confuse the proxy with the cache store.** A proxy is a wrapper intercepting calls; `CacheManager` manages `Cache` instances. Placing the manager in the right scope is necessary, yet a manager does not replace enabling cache advice in the context creating the beans. With Redis, different contexts can point to the same Redis server while still differing in whether the proxy exists.

**Do not confuse context scope with transactions/TTL.** Placing `@EnableCaching` in the right context only solves whether annotations are processed. TTL, consistency, eviction timing, and backend policies are separate decisions.

## 7. Implementation and Verification Checklist

Before concluding caching works, verify in sequence:

1. **Diagram or log the context tree**: how many contexts are created? Which is root and which is a `DispatcherServlet` child?
2. **Identify service ownership**: in which context is the service bean registered via `@Service`, `@Bean`, or `@Import`? If bean names/types overlap between parent and child, verify the actual instance used by the controller.
3. **Check where `@EnableCaching` is loaded**: the configuration must be registered and processed in the right service context. For XML, check which context loads the file containing `<cache:annotation-driven/>`.
4. **Check cache manager/resolver**: the cache name exists; the bean is resolvable by the caching infrastructure in the relevant context.
5. **Check the call path**: the service is obtained via Spring dependency injection; the method is public and invoked through the proxy, not via `this.method()`.
6. **Measure cache hits/misses**: call twice with the same key and compare body execution counts; test key changes and eviction operations.
7. **Test with the proper context structure**: a unit test calling the method directly or a `@WebMvcTest` loading only the MVC slice cannot replace an integration test of service + caching. Use a real test context with the required configuration.

You can add logging while debugging:

```properties
logging.level.org.springframework.cache=TRACE
logging.level.org.springframework.cache.interceptor=TRACE
```

These log levels help observe cache handling depending on version/configuration. Do not treat logs as the sole proof: tests observing outputs, call counts, and actual proxies remain more authoritative.

A short check in a Spring test (illustrative; requires your project's context and assertions framework):

```java
DataService service = applicationContext.getBean(DataService.class);
assertThat(AopUtils.isAopProxy(service)).isTrue();

String a = service.find("A");
String b = service.find("A");
assertThat(b).isEqualTo(a);
assertThat(service.executions()).isEqualTo(1);
```

All checks must use **the exact bean obtained from the context under test**, and each test should start with an empty/controlled cache before measuring call counts.

## 8. Self-Check Questions

**Q1.** A `@Cacheable` service sits in root; `@EnableCaching` is placed in `WebMvcConfig` of the child `DispatcherServlet`. Even though the child can inject the service, why might caching fail to run?

**Answer:** Child sees parent beans through lookup, but child's AOP/cache processing infrastructure does not retroactively post-process beans already initialized in parent. Caching must be enabled in the context that owns the service.

**Q2.** There is a `CacheManager` in root, yet a service in the same context always executes. Will adding another manager definitely solve it?

**Answer:** No. You must verify `@EnableCaching` is loaded and the method is called through a caching proxy, and only then examine cache names/keys/providers.

**Q3.** A service exists only in the child, while root has `@EnableCaching` enabled. Will a caching proxy be created automatically for the child service?

**Answer:** Not by default: root infrastructure does not automatically post-process beans initialized in the child. Cache processing must be enabled in the child if that is truly where the service lives.

**Q4.** Spring Boot typically has no explicit root/child hierarchy; do we still need to care about context scope?

**Answer:** Yes. Most single-context Boot apps only need one caching configuration scanned in the right scope. However, custom parent/child contexts, test slices, multiple contexts, and misconfigured package scans still cause the same symptom.

## 9. Takeaways

- `@EnableCaching` is a **per-ApplicationContext configuration**, not a global switch applying automatically across every context in the JVM.
- Place caching infrastructure in **the context that creates the beans bearing cache annotations**; in a typical root/child Spring MVC setup, if services are in root, enable caching in root.
- Parent beans can be used by a child, but **child post-processors/advisors do not retroactively process parent beans**.
- A properly placed `CacheManager`, a properly created proxy, and a call going through the proxy are **three conditions that must be verified separately**.
- For single-context Spring Boot apps, use a dedicated `@Configuration @EnableCaching` class within the application's component-scan scope.

### Official References

- [Spring Framework – Enabling Caching Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-enable)
- [Spring Framework – Context Hierarchy in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/context-hierarchy.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)