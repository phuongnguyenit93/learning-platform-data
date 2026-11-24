# Unifying Configuration When Multiple Spring Mechanisms Require Proxies

## 1. Why Does Auto-Proxy Need Unification in Spring?

A single Spring bean can simultaneously be subject to multiple AOP-proxy-based capabilities:
- `@Aspect` with `@Before` or `@Around` to observe method calls.
- `@Transactional`, which Spring associates with `TransactionInterceptor` when transaction management is enabled in `AdviceMode.PROXY`.
- `@Cacheable`, `@CacheEvict`, or `@CachePut`, which Spring handles with a cache interceptor when caching is enabled in proxy mode.
- Certain other proxy capabilities, such as `@Async`, have their own infrastructure registration path depending on the version.

For example, a `placeOrder()` method both has `@Transactional` and matches a logging aspect. If Spring created proxies without coordinating these features, each configuration might compete over how to wrap the bean, which proxy type to use, or where advice runs.

**In Spring Framework 6.x, standard proxy configurations such as `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, and `@EnableCaching` in `AdviceMode.PROXY` share a unifiable auto-proxy creator infrastructure within the same `ApplicationContext`.** The mechanisms still retain their own advisors, yet can be applied together to the bean's Spring proxy. In particular, a `proxyTargetClass=true` requirement from one configuration can determine the shared proxy type, even when another configuration specifies `false`.

The scope of this lesson is **proxy-based Spring AOP and Spring IoC**. We will walk from the auto-proxy creator infrastructure, option-precedence rules, advisor chains, and a runnable example, to how to inspect Spring AOP working alongside caching, transactions, and async.

## 2. Three Components to Distinguish Clearly

### 2.1. Auto-Proxy Creator: The Component Creating Proxies During Bean Initialization

The auto-proxy creator is a kind of `BeanPostProcessor`. When the container creates a Spring bean, it checks matching advisors and returns a proxy if the bean needs to be advised. In the standard infrastructure, Spring uses the internal bean name `org.springframework.aop.config.internalAutoProxyCreator` to coordinate auto-proxy registrations.

Common implementations:
- `InfrastructureAdvisorAutoProxyCreator` handles infrastructure advisors.
- `AspectJAwareAdvisorAutoProxyCreator` adds rules related to AspectJ advisors.
- `AnnotationAwareAspectJAutoProxyCreator` can recognize beans annotated with `@Aspect` and create advisors.

When another feature requires a more capable auto-proxy creator, Spring performs **escalation**: using the implementation that satisfies the higher requirement for the shared infrastructure. Thus, a single auto-proxy creator can handle both Spring transaction/cache advisors and advisors generated from `@Aspect`.

**The auto-proxy creator is an infrastructure bean**, not a proxy for `ProductService`. Whether an auto-proxy creator exists in the context and how many Spring beans need a proxy are two different questions.

### 2.2. Advisor and Interceptor: Per-Feature Logic

An advisor typically pairs an applicability condition (pointcut/method matching) with an advice/interceptor. Features still have independent behavior:

| Mechanism | Activation | Typical AOP component | Meaning when a method is called |
| --- | --- | --- | --- |
| Spring `@AspectJ` | `@EnableAspectJAutoProxy` or corresponding AOP auto-configuration | Advisor/advice created from `@Aspect` | Advice runs when method matches pointcut and goes through proxy |
| Transaction | `@EnableTransactionManagement` in `PROXY` | Transaction advisor + `TransactionInterceptor` | Opens/joins/ends transaction according to configuration |
| Caching | `@EnableCaching` in `PROXY` | Cache advisor + `CacheInterceptor` | Cache miss continues to target; cache hit can return result immediately |
| Async in Spring 6.1 | `@EnableAsync` in `PROXY` | `AsyncAnnotationBeanPostProcessor` + `AsyncAnnotationAdvisor` | Executes method via task executor when called through proxy |

One cannot infer from **one shared auto-proxy creator** that caching, transactions, and logging are all executed by the exact same interceptor. They are separate advisors/advice, selected when appropriate for a specific method.

### 2.3. Actual Proxy: Where Clients Invoke Methods

```text
One ApplicationContext
   |
   +-- @EnableAspectJAutoProxy --> Spring @Aspect advisors
   +-- @EnableCaching ----------> cache advisor/interceptor
   +-- @EnableTransactionManagement --> transaction advisor/interceptor
   |
   +-- Shared Spring auto-proxy infrastructure
          |
          +-- create OrderService bean
          +-- find advisors matching the bean/method
          +-- create proxy when appropriate advisors exist
                           |
Client ----> Spring AOP proxy
                 |
                 +-- advice A (if matched)
                 +-- advice B (if matched)
                 +-- advice C (if matched)
                 |
                 +-- target method (if chain continues)
```

One proxy can hold multiple advisors, but **not every advisor runs for every method**. Spring computes the interceptor chain based on the method currently called, the target class, and runtime conditions when needed.

Conversely, if a bean matches no advisor, `proxyTargetClass=true` alone is not a reason for Spring to create an AOP proxy for that bean.

## 3. Why Does `proxyTargetClass=true` Affect Multiple Mechanisms?

### 3.1. Annotations Jointly Determining Configuration

Suppose a context registers:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(proxyTargetClass = true)
@EnableTransactionManagement(proxyTargetClass = false)
public class InfrastructureConfig {
    // This is only an illustrative snippet for proxy type selection.
    // For caching/transactions to actually work, register an appropriate
    // CacheManager and TransactionManager.
}
```

Even though AspectJ AOP and transactions specify `false`, caching specifies `true`. Spring applies **the stronger proxy requirement**, namely class-based proxying, for auto-proxying in the context. `false` means do not force class-based proxying, not an absolute demand to "forbid class-based proxying".

| `@EnableAspectJAutoProxy` | `@EnableCaching` | `@EnableTransactionManagement` | Resulting general proxy tendency |
| --- | --- | --- | --- |
| `false` | `false` | `false` | JDK proxy when the bean has suitable interfaces; class proxy may still be needed if no interface exists |
| `true` | `false` | `false` | Class-based proxy when the bean needs to be proxied |
| `false` | `true` | `false` | Class-based proxy, even for beans advised by an aspect |
| `false` | `false` | `true` | Class-based proxy, even for beans that only have caching or aspect advisors |
| `true` | `true` | `false` | Class-based proxy |
| `false` | `true` | `true` | Class-based proxy |

This table applies when the above configurations operate together in **proxy mode and within the same context**, in Spring Framework 6.x. If custom proxy infrastructure or a different framework version is present, verify at runtime.

### 3.2. Class-Based Proxy and Interface-Based Proxy Are Not Equivalent

- **JDK dynamic proxy** implements the target's interfaces. When clients obtain the bean by interface, this makes sense; when obtaining by implementation class, it can fail because a JDK proxy is not a subclass of that class.
- **Class-based proxy (CGLIB)** subclasses the target class, so it can usually be retrieved by class type. However, a `final` class cannot be subclassed for proxying, a `final` method cannot be overridden, and a `private` method cannot be advised via this proxy mechanism.
- **Self-invocation** `this.otherMethod()` on the target still bypasses the Spring AOP proxy, regardless of JDK or CGLIB.

Do not enable class-based proxying globally just to fix an internal method call: self-invocation by nature is not automatically fixed by proxying.

### 3.3. `exposeProxy` Also Pertains to Infrastructure, With a Different Purpose

`@EnableAspectJAutoProxy` also has:

```java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
```

When `exposeProxy=true`, code executing inside a call through an AOP proxy can access the current proxy via `AopContext.currentProxy()`. That is a special supporting mechanism, typically via `ThreadLocal`. It **does not make self-invocation go through the proxy automatically**; the developer must explicitly change how the call is made and accept a dependency on Spring AOP.

Options enabling additional capabilities such as class-based proxying/exposeProxy can be integrated into the shared auto-proxy configuration in the context. Do not confuse `exposeProxy` with an option that changes the number of aspect beans, transaction boundaries, or cache types.

## 4. A Unified Auto-Proxy Creator Does Not Mean Advice Ordering Resolves Automatically

A call to `OrderService.place(...)` can match logging, transaction, and cache advisors simultaneously.

```text
Caller
  |
  v
proxy.place(...)
  |
  +-- logging @Around?           (order depends on @Order)
  +-- TransactionInterceptor?    (order depends on transaction order)
  +-- CacheInterceptor?          (order depends on caching order)
  |
  +-- target.place(...)          (only runs if chain continues)
```

If `CacheInterceptor` sits **outside** `TransactionInterceptor` and hits the cache, it can return the result before reaching the transaction interceptor. If the transaction interceptor sits **outside** caching, a transaction may still be started even on a cache hit.

Similarly, an aspect using `@Before` placed outside the cache interceptor can log every call, including cache hits. If the advice sits after the cache interceptor in the chain, a cache hit can return the result before the advice executes.

**Annotation order on `@Configuration` does not determine advice order.** You need to use `@Order`/`Ordered` for aspects and the `order` attribute on each feature.

Precedence configuration example:

```java
@Aspect
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceAspect {

    @Before("execution(* com.example.service..*.*(..))")
    public void beforeCall() {
        // High priority, can sit outside lower-priority advisors.
    }
}
```

```java
@EnableCaching(order = Ordered.LOWEST_PRECEDENCE)
```

The code above is an illustrative snippet (requiring imports, bean registration, and a real service if placed in a project). An advisor with a **smaller** `order` number generally has higher precedence; outer advice is entered earlier and exited later when the chain proceeds normally. When multiple advisors share the same precedence or special configurations exist, verify the actual order with an integration test.

### Three Distinct Facts

1. **The auto-proxy creator is unified:** Spring coordinates the infrastructure to create proxies.
2. **Advisors are combined:** One proxy can hold multiple advisors corresponding to different features.
3. **Invocation outcome depends on order:** Which advice runs, whether the target is called, and how exceptions propagate still depend on pointcuts, ordering, and how interceptors continue the chain.

Do not use seeing `AopUtils.isAopProxy(bean) == true` to conclude that all three features executed properly.

## 5. Runnable Example: Combining `@Aspect` and `@Cacheable`

This example isolates two Spring mechanisms that commonly create proxies together, using **Java 17, Spring Framework 6.1.14, and Gradle**. Without Spring Boot, we explicitly specify the exact `proxyTargetClass` options.

Verification goals:
- `@EnableAspectJAutoProxy(proxyTargetClass=false)` does not override `@EnableCaching(proxyTargetClass=true)`.
- A bean implementing an interface still becomes a **class-based AOP proxy**.
- A high-precedence logging aspect can observe both calls, while caching makes the target run only once.

### 5.1. Creating the Project

```text
spring-aop-combined/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/combined/
    ├── CatalogApi.java
    ├── CatalogService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-combined'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.combined.DemoApp'
}
```

Here `spring-context` provides `ApplicationContext`, the cache API, and `ConcurrentMapCacheManager`; `spring-aop` provides proxying; `aspectjweaver` provides the components needed to process expressions in `@Aspect`.

### 5.2. Interface and Target

`src/main/java/demo/combined/CatalogApi.java`:

```java
package demo.combined;

public interface CatalogApi {
    String find(String sku);
}
```

`src/main/java/demo/combined/CatalogService.java`:

```java
package demo.combined;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;

public class CatalogService implements CatalogApi {
    private final AtomicInteger calls = new AtomicInteger();

    @Override
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        int count = calls.incrementAndGet();
        System.out.println("target#" + count);
        return "item:" + sku;
    }

    public int targetCallCount() {
        return calls.get();
    }
}
```

`find(...)` returns a fixed result by SKU. The cache manager can store `"item:sku-7"` after the first call. `targetCallCount()` only measures how many times the method logic inside the target actually ran.

### 5.3. High-Precedence Aspect

`src/main/java/demo/combined/TraceAspect.java`:

```java
package demo.combined;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@Aspect
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceAspect {

    @Before("execution(public * demo.combined.CatalogService.find(..))")
    public void beforeFind() {
        System.out.println("aspect:before");
    }
}
```

`@Aspect` declares a Spring AOP aspect; `@Before` has a pointcut matching only `CatalogService.find(..)`. `@Order` is fixed so the advice sits outside the cache advice in the example; on a cache hit, logging can still run even though the target is not called.

### 5.4. One Context Enabling Two Mechanisms

`src/main/java/demo/combined/AppConfig.java`:

```java
package demo.combined;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(
    proxyTargetClass = true,
    order = Ordered.LOWEST_PRECEDENCE
)
public class AppConfig {

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

All three beans are registered explicitly so they are not affected by component scanning. `TraceAspect` does not need `@Component` because it is already an `@Bean`; a class annotated only with `@Aspect` will not automatically become a Spring bean if it is not registered.

`@EnableCaching` operates in default proxy mode, requests a class proxy, and registers the cache advisor. `@EnableAspectJAutoProxy` enables aspect detection. Caching's `true` option overrides the aspect's `false` option in the shared auto-proxy infrastructure.

### 5.5. Running the Program

`src/main/java/demo/combined/DemoApp.java`:

```java
package demo.combined;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogApi byInterface = context.getBean(CatalogApi.class);
            CatalogService byClass = context.getBean(CatalogService.class);

            System.out.println("sameBean=" + (byInterface == byClass));
            System.out.println("isAopProxy=" +
                               AopUtils.isAopProxy(byInterface));
            System.out.println("isClassProxy=" +
                               AopUtils.isCglibProxy(byInterface));

            System.out.println("first=" + byInterface.find("sku-7"));
            System.out.println("second=" + byInterface.find("sku-7"));
            System.out.println("targetCalls=" + byClass.targetCallCount());
        }
    }
}
```

Using a Gradle installation that can run the project, in the directory containing `build.gradle`:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

Lines **printed by the Java program** (ignoring build/logging output from tools):

```text
sameBean=true
isAopProxy=true
isClassProxy=true
aspect:before
target#1
first=item:sku-7
aspect:before
second=item:sku-7
targetCalls=1
```

Meaning:
1. `sameBean=true`: retrieving by interface or by class returns the exact same Spring-managed singleton/proxy.
2. `isAopProxy=true`: the bean was wrapped with a Spring AOP proxy.
3. `isClassProxy=true`: even though the aspect declared `proxyTargetClass=false`, caching requested `true`.
4. `aspect:before` appears **twice** because the aspect has higher precedence than the cache advisor, observing the cache hit as well.
5. `target#1` appears **once**: caching returns the result for the second call from `ConcurrentMapCacheManager` without calling the target method again.
6. `targetCalls=1` confirms this. Checking the target counter is different from merely checking that the two returned strings are equal.

This is an example verifying how Spring coordinates two mechanisms. It does not imply that every manually created proxy is merged.

## 6. Trying Variants to See Which Configuration Determines the Proxy

Based on the example code, you can change **one configuration at a time**.

### Variant A: Removing the Class-Based Request from Caching

Change:

```java
@EnableCaching(proxyTargetClass = false)
```

If no other configuration requests class-based proxying, `CatalogService` implementing `CatalogApi` is typically wrapped by a **JDK dynamic proxy**. Then:
- `context.getBean(CatalogApi.class)` remains valid.
- `context.getBean(CatalogService.class)` may fail to retrieve the JDK proxy because the proxy does not extend `CatalogService`.
- `AopUtils.isJdkDynamicProxy(bean)` is the right check, after updating `DemoApp` not to look up by class type.

Do not reuse the unmodified original program to conclude that JDK proxy "is broken" when looking up by class.

### Variant B: Enabling Only `@EnableCaching`

Keep the cache manager and beans, but remove `@EnableAspectJAutoProxy`. The caching infrastructure still processes `@Cacheable`; it does not automatically ensure `@Aspect` beans are interpreted into aspect advisors. Do not expect `aspect:before` logs to remain if no other `@AspectJ` processing infrastructure is present.

### Variant C: Enabling Only `@EnableAspectJAutoProxy`

Remove `@EnableCaching`. The aspect can still advise `find` through the proxy, but `@Cacheable` on the target does not automatically activate caching. Two calls to the target will increment the counter to two.

### Variant D: Reordering Advice

If the cache interceptor sits outside and a cache hit occurs, the inner aspect's advice **may not run** the second time because the cache returns the result before continuing the chain. Hence interceptor ordering is behavior to design and verify, not an accident of how Spring merges infrastructure.

## 7. Inspecting the Auto-Proxy Creator and Advisors at Runtime

If you have the `context` variable as an `AnnotationConfigApplicationContext` in the example above, you can read the infrastructure bean (supplementary inspection snippet, not a standalone program):

```java
import org.springframework.aop.config.AopConfigUtils;

String autoProxyCreatorName =
    AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME;
Object creator = context.getBean(autoProxyCreatorName);
System.out.println(creator.getClass().getName());
```

In a configuration with `@AspectJ`, you may see `AnnotationAwareAspectJAutoProxyCreator` because it supports discovering advisors declared from `@Aspect` in addition to infrastructure advisors. This is an infrastructure detail for diagnostics, not a class to depend on in business code.

To view advisors on the proxy, given the `byInterface` variable:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

if (byInterface instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

You can see advisors related to caching and the aspect. The printed order reflects the actual proxy configuration; the list is not an immutable API contract across versions. An advisor on a proxy does not necessarily run on every method; pointcuts and method matchers still determine invocation behavior.

**Note on double-proxying:** In standard Spring infrastructure, unifying the auto-proxy creator helps prevent each declaration from creating a new proxy layer. However, separate `BeanPostProcessor`s or manually written proxy factories can still add another proxy layer. Do not take `AopUtils.isAopProxy` as proof there are no nested proxies; inspect `Advised`/target source when diagnosing that situation.

## 8. Adding `@Transactional`: Shared Advisor, Independent Transaction Logic

When `@EnableTransactionManagement(mode=AdviceMode.PROXY)` is enabled, Spring registers an advisor for `@Transactional`.

Illustrative configuration example, **not a standalone runnable program** as it lacks an appropriate `TransactionManager` and datasource:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(proxyTargetClass = false)
@EnableTransactionManagement(
    mode = AdviceMode.PROXY,
    proxyTargetClass = true,
    order = 200
)
class ServiceAopConfig {
    // Requires a real CacheManager and TransactionManager.
}
```

`proxyTargetClass=true` on transactions applies the class-based proxy requirement in the same infrastructure, even for beans advised by aspects or caching. However:
- **Without a transaction manager**, the proxy/advisor cannot execute a valid database transaction on its own.
- `order=200` controls the ordering of the transaction advisor, not arbitrary Spring bean creation order.
- Transaction/cache ordering matters: if the cache interceptor sits outside and returns on a cache hit, the inner part of the chain may not open a transaction. If the transaction interceptor sits outside caching, a transaction can start before caching decides the result.
- Cache invalidation after successful commit is a separate business requirement; it is not guaranteed merely by sharing a Spring proxy.

**AspectJ mode differs from PROXY mode:** `@EnableTransactionManagement(mode=AdviceMode.ASPECTJ)` uses a transaction aspect with weaving when the corresponding infrastructure is configured; in that case `proxyTargetClass` on this transaction branch has no effect. Do not apply `PROXY`'s auto-proxy unification rules to infer that weaving goes through the same proxy.

Similarly, `@EnableCaching(mode=AdviceMode.ASPECTJ)` is a different model requiring `spring-aspects` and weaving configuration. The example above uses proxy mode only.

## 9. `@Async` and Changes Across Spring Versions

In **Spring Framework 6.1**, `@EnableAsync` does not follow the exact same auto-proxy creator registration path as `@EnableAspectJAutoProxy`/caching/transactions.

- `@EnableAsync` commonly uses `AsyncAnnotationBeanPostProcessor`.
- This processor can add `AsyncAnnotationAdvisor` to an **existing AOP proxy**, or create a new proxy when needed.
- The processor's default `order` aims to process after other post-processors so it can add its advisor to the proxy rather than wrapping another layer.
- `@EnableAsync(proxyTargetClass=true)` still influences class-based proxy selection for other beans needing proxies in the context per Spring 6.1 Javadoc, but do not conclude from that that **every BeanPostProcessor is itself an auto-proxy creator instance**.

**According to Spring Framework 7.0 documentation**, the mechanism unifying global default proxy settings has been extended to individual proxy processors, such as `@EnableAsync`. Therefore, if an application uses Spring 7.0, read the reference/Javadoc for **that exact release** before assuming identical detailed behavior to Spring 6.1.

`@EnableScheduling` instead focuses on registering scheduled methods and does not automatically imply creating an AOP auto-proxy creator for every scheduled method. Likewise, security configurations or user-written interceptors may use their own integration paths; verify empirically before concluding proxy counts.

## 10. In Spring Boot, What Decides the Proxy Type?

Spring Boot has Spring AOP auto-configuration when the appropriate dependency is loaded (commonly via `spring-boot-starter-aop`). In **Spring Boot 3.3**, class-based proxying is typically the default for AOP auto-configuration when properties are unchanged:

```properties
spring.aop.proxy-target-class=true
```

You can change direction with:

```properties
spring.aop.proxy-target-class=false
```

However, if the application in the same context also has `@EnableCaching(proxyTargetClass=true)` or `@EnableTransactionManagement(proxyTargetClass=true)`, the stronger class-proxy requirement can still govern auto-proxying. Therefore, looking at one Boot property alone is not enough to conclude whether the final proxy is JDK or CGLIB.

Additionally, a Boot application can have extra auto-configured advisors (transaction, cache, security...). To understand a method, inspect dependencies, auto-configurations, the context owning the bean, advisors, and the method actually called. When explaining behavior, specify the running Boot/Spring version.

## 11. Common Errors and How to Verify

| Symptom | Common cause | How to fix/verify |
| --- | --- | --- |
| `@EnableAspectJAutoProxy(proxyTargetClass=false)` yet result is still CGLIB | Caching, transactions, or Boot requested `true` | Collect all proxy configs in the same context; use `AopUtils.isCglibProxy`. |
| Bean has proxy, yet `@Before` does not run | Aspect is not a bean, AOP not enabled, pointcut does not match, or call bypasses proxy | Check aspect bean, advisors, pointcut, and call path. |
| Aspect runs twice, target runs only once | Aspect sits outside caching; cache hit skips target | This can be expected behavior, depending on logging needs. |
| Aspect only runs the first time a cached method is called | Cache interceptor sits outside aspect and returns on cache hit | Check `@Order` and the cache advisor's `order`. |
| Retrieving bean by class fails | Bean has a JDK dynamic proxy | Inject the interface or configure class-based proxying when genuinely needed. |
| Transaction does not work despite `@Transactional` | Missing/wrong `TransactionManager`, method mismatch, or self-invocation | Check manager, advisor, transaction mode, and proxy call path. |
| Caching has no effect | `@EnableCaching` not enabled, missing `CacheManager`, self-invocation, or ineligible method | Verify cache config, keys, and target call count. |
| After enabling CGLIB, a `final` bean errors | Cannot create subclass proxy | Design the class to be proxyable or keep appropriate interface-based proxying. |
| AOP config in parent, yet bean in child receives no proxy | Auto-proxy creator is **per-context** infrastructure | Enable mechanism in the right context creating the bean; check bean ownership. |
| Multiple nested proxies exist | Custom post-processors or special mechanisms wrap the proxy again | Inspect `Advised`, target source, and BeanPostProcessor order. |
| Async behavior differs from docs | Comparing wrong version or confusing async processor with standard auto-proxy creator | Cross-check Spring Framework 6.x/7.0 and `AsyncAnnotationBeanPostProcessor`. |

### Concise Yet Evidence-Backed Debugging Workflow

1. **Context:** Identify which `ApplicationContext` creates the bean and receives the `@Enable...` annotations.
2. **Infrastructure:** Is `internalAutoProxyCreator` present? Are `AsyncAnnotationBeanPostProcessor` or other custom processors present?
3. **Proxy:** Does Spring provide a JDK proxy or CGLIB? `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`.
4. **Advisors:** Are the expected advisors from `@Aspect`, caching, and transactions present on the proxy?
5. **Order:** Which advice is outer/inner? Does a cache hit stop the chain before the target/transaction?
6. **Target:** Does the business method execution count match expectations? Is there self-invocation or a `final`/`private` method?
7. **Version:** Across Spring 6.x, Spring 7.0, or different Boot versions, verify defaults and individual processor mechanics.

## 12. Practical Conclusion

Spring unifies **standard auto-proxy creator registrations within a context** so multiple proxy-based mechanisms can work together on one bean. "Unification" has two practical consequences: the infrastructure can recognize different advisors, and strong options like `proxyTargetClass=true` are applied consistently.

However, three things must always be kept separate: **what creates the proxy**, **which advisors apply**, and **in what order interceptors run**. Sharing a proxy does not replace the need for a `CacheManager`, `TransactionManager`, aspect beans, or calls going through the proxy. Logging–cache–transaction ordering and `@Async` specifics must still be verified for the specific context and Spring version.

### Official Spring Documentation

- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): unified auto-proxy creator and class/interface proxies.
- [@AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling `@Aspect`-based proxying.
- [Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): advice precedence.
- [Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, proxy mode, order, and cache hits.
- [@EnableTransactionManagement Javadoc (6.1.14)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html): transaction advisor, `proxyTargetClass`, and `AdviceMode`.
- [@EnableAsync Javadoc (6.1.8)](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): `AsyncAnnotationBeanPostProcessor`, `proxyTargetClass`, and ordering.
- [AsyncAnnotationBeanPostProcessor Javadoc (6.1.2)](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html): adding the async advisor to an existing proxy.
