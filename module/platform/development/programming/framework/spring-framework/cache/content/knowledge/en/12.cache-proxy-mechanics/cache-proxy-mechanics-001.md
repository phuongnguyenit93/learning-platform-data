# Proxy Mode and Calls Passing Through Spring Beans in Spring Cache

## Objectives

In the Spring Framework Cache Abstraction, annotating a method with **@Cacheable**, **@CachePut**, or **@CacheEvict** is not enough for the method to automatically get caching. In the default mode, Spring uses an **AOP proxy**: caching behavior is only applied when the call **passes through the Spring-managed proxy object**. Therefore, two statements calling the same method can produce different results solely because the call paths differ.

After this lesson, you will be able to:
1. Explain the **proxy mode** of @EnableCaching and the chain caller → proxy → cache interceptor → target method.
2. Distinguish a **Spring bean retrieved from ApplicationContext** from an object manually created with new, and distinguish a **call from another bean** from **self-invocation** via this.
3. Understand when Spring uses a **JDK dynamic proxy** or a **class-based proxy**, the effect of **proxyTargetClass**, and limitations with final/private/static methods.
4. Identify cases where annotations have no effect due to an unenabled proxy, wrong call path, bean initialization phase, or ApplicationContext scope.
5. Run a Java 17 + Spring Framework example demonstrating cache hit, cache miss, and **self-invocation not being intercepted**; choose a safe refactoring approach.

Context: **Spring Framework 6.2.x**, Java annotation-based caching configuration; the example uses **ConcurrentMapCacheManager** and does not require Spring Boot. Proxy principles still apply when using Caffeine, Redis, or other providers, but they do **not** replace connection configuration, TTL, or provider-specific key rules.

## 1. What Does Spring Cache Use Proxies For?

Spring Cache is a form of **cross-cutting concern**: checking, updating, or evicting the cache is added around business method calls without writing Cache.get/put/evict operations inside every method.

When enabling annotation caching with **@EnableCaching**, Spring creates the infrastructure to detect cache operations and attaches a **cache interceptor** to eligible beans. In proxy mode, Spring can hand callers a proxy object standing in front of the target.

~~~text
Caller (Controller / Service / Job / Test)
       |
       | calls via bean reference received from Spring
       v
Spring AOP proxy
       |
       v
CacheInterceptor
       |
       +-- @Cacheable: build key -> check cache
       |      HIT  -> return result, skip target method
       |      MISS -> call target -> put result into cache
       |
       +-- @CachePut: call target -> put result (subject to conditions)
       |
       +-- @CacheEvict: call target -> evict at configured timing
       |
       v
Target object containing business logic
~~~

The diagram illustrates typical synchronous behavior. Specific annotations can use condition, unless, key/keyGenerator, cacheResolver, and other options; the detailed order of steps also depends on the cache operation type.

**A proxy is not the cache.** The proxy is the gate intercepting calls; **CacheManager/Cache** is what stores entries. The proxy executes the caching logic via the interceptor and forwards the call down to the target when needed.

Two cases are frequently confused:
- **@Cacheable** with a cache hit → may skip calling the target method.
- **@CachePut** does not use a cache hit to skip the target method; the method still executes and Spring may put the result.
- **@CacheEvict** can evict after invocation (default) or before invocation if beforeInvocation=true.

What all three have in common: if a call completely **bypasses the interception mechanism**, these annotations do not perform any caching function on their own.

## 2. @EnableCaching Defaults to AdviceMode.PROXY

The **org.springframework.cache.annotation.EnableCaching** annotation has a **mode** attribute. The default value is **AdviceMode.PROXY**.

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {
    // @Bean definitions for CacheManager/KeyGenerator if needed.
}
~~~

This is an illustrative configuration snippet; a complete project needs a CacheManager or infrastructure capable of resolving caches. The runnable example later has an explicit CacheManager bean.

You can write the default mode explicitly:

~~~java
import org.springframework.context.annotation.AdviceMode;

@EnableCaching(mode = AdviceMode.PROXY)
~~~

The second snippet is an **illustrative annotation** placed on a @Configuration class; only use it in an appropriate configuration class context.

**Practical implications of PROXY:**
1. Spring finds managed beans and their corresponding cache-annotated methods.
2. A proxy is created when a bean is eligible; callers typically receive a **proxied bean reference** from the container.
3. Cache advice only triggers on calls **entering from outside through the proxy**.
4. Calls inside the target via **this.method()** do not go through that proxy.
5. Putting an annotation on a method **does not turn every Java call** into interception: Java does not natively understand caching annotations.

With Spring Boot, auto-configuration can help enable caching infrastructure, but you still need to verify that caching is enabled in your specific application. With plain Spring Framework, the explicit approach is @EnableCaching and a CacheManager bean.

### Why Doesn't Caching Work Immediately Upon Writing the Annotation?

An annotation is just metadata. Whether execution follows the annotation depends on:
- **Is annotation-based caching infrastructure active?**
- **Is the method on a Spring-managed bean?**
- **Does the call path go through the proxy?**
- **Can the method be proxied/intercepted under the current configuration?**
- **Are the cache name, key, and cache manager valid?**

Only when the relevant conditions are met does the cache interceptor get a chance to handle the invocation.

## 3. The Right Call Path: Getting the Bean from Spring and Calling from Outside

Typical usage:

~~~java
// Illustrative example inside a Spring-managed controller/facade.
public final class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service; // Spring injects the bean; do not instantiate with new.
    }

    public String get(String id) {
        return service.load(id); // Call from another object through the bean.
    }
}
~~~

This is a conceptual example; ProductController and ProductService must be registered as beans, and ProductService declared accordingly. In a real project, you can use constructor injection with @Service/@Component or @Bean.

The same logic, but calling **directly on a manually created object**:

~~~java
// NOT managed by Spring:
ProductService service = new ProductService();
service.load("P-01");
service.load("P-01");
~~~

The two calls above are plain Java and **do not go through a Spring AOP proxy**. Even though the load method has @Cacheable, Spring does not apply the annotation to this instance. On each call, execution follows the original Java code; no Spring cache interceptor intervenes.

**Distinguish three entities:**
- **Bean definition**: metadata for Spring to create/manage the object.
- **Target**: the instance executing the business logic.
- **Proxy bean reference**: the object callers receive from Spring, which can wrap the target and execute advice.

You should not rely on the assumption **target == proxy**. With subclass-based or interface-based proxies, the visible class/type may differ from the original class. What matters is that the caller receives and uses the bean reference provided by Spring.

## 4. Self-Invocation: The Classic Pitfall of Proxy Mode

Self-invocation is when a method inside the target object itself calls another method **on the same object**, usually via **this** or an implicit call without writing this.

~~~java
public class ProductService {

    @Cacheable(cacheNames = "products")
    public String load(String id) {
        return expensiveQuery(id);
    }

    public String loadTwice(String id) {
        String first = this.load(id);
        String second = load(id);   // Equivalent to this.load(id).
        return first + "|" + second;
    }
}
~~~

This is an illustrative snippet, not standalone runnable code. When an external caller invokes **proxy.load("P-01")**, Spring has a chance to intercept @Cacheable. But if an external caller invokes **proxy.loadTwice("P-01")**, the first call forwards down to **target.loadTwice**; from there, **this.load(...)** calls the target method directly without going back through the proxy. Both load calls inside loadTwice are not intercepted by the cache interceptor in the default proxy mode.

~~~text
CASE 1: caller -> proxy.load(id)
                     |
                     +--> CacheInterceptor --> Cache HIT / MISS
                                                  |
                                          (MISS) target.load(id)

CASE 2: caller -> proxy.loadTwice(id)
                     |
                     v
                 target.loadTwice(id)
                     |
                     +--> this.load(id) ---------> target.load(id)
                     +--> this.load(id) ---------> target.load(id)
                         (bypasses interceptor)
~~~

**Important:** Self-invocation bypasses the proxy **even when the called method is public and annotated with @Cacheable**. Changing proxyTargetClass from false to true **does not automatically fix** the this-call issue; both interface proxies and class proxies still have a proxy boundary.

This does not only affect @Cacheable. Self-invocation of @CachePut or @CacheEvict also skips put/evict behavior if those annotations are only applied via a Spring AOP proxy.

### Symptoms in Practice

Suppose you observe @Cacheable working effectively when called from a Controller, but calling that same @Cacheable method from within the same Service runs the database query every time. This is usually a **call path not going through the proxy**, not a TTL bug. Trace the call path before increasing TTL or changing providers.

## 5. JDK Dynamic Proxy and Class-Based Proxy

Spring AOP has two main proxy families in Java:

| Criterion | **JDK dynamic proxy** | **Class-based proxy (CGLIB)** |
| --- | --- | --- |
| Mechanism | Proxy implements the exposed interfaces | Proxy is a subclass of the target class |
| Commonly used when | Bean has eligible interfaces and class proxy is not forced | Bean has no eligible interfaces or config forces class proxy |
| Recommended injection type | Interface | Concrete class can be used if proxy limits allow |
| Proxied methods | Methods exposed via the interface/proxy | Overridable/advisable instance methods |
| Notable limitations | Cannot arbitrarily expose methods existing only on concrete class | Cannot proxy final classes; final methods cannot be overridden for advice |
| Self-invocation via this | **Not intercepted** | **Not intercepted** |
| Depends on cache provider? | No | No |

When choosing **@EnableCaching(proxyTargetClass = false)** (the default value), standard Spring Framework AOP prefers a JDK proxy when the target has interfaces and uses a class-based proxy when there is no interface to proxy. Thus, **false does not guarantee a JDK proxy** if the class declares no interfaces.

~~~java
@EnableCaching(proxyTargetClass = true)
~~~

The line above is an **illustrative annotation** on @Configuration. In PROXY mode, true requests class-based proxies. If mode=ASPECTJ, the proxyTargetClass attribute no longer plays a role in selecting the proxy type.

### Interface Proxy and Injection Type

Interface example:

~~~java
public interface CatalogApi {
    String find(String sku);
}

public class CatalogService implements CatalogApi {
    @Override
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        return lookup(sku);
    }
}
~~~

This is a standalone snippet; lookup and imports need to be added. With a JDK proxy, callers should inject **CatalogApi**, rather than assuming CatalogService concrete type is required:

~~~java
// Illustrative constructor:
public CatalogController(CatalogApi api) {
    this.api = api;
}
~~~

If the bean is actually a JDK proxy, attempting to cast the bean to CatalogService can fail because the proxy object **only implements the interface**. With a class-based proxy, a subclass of CatalogService is assignable to CatalogService.

For cache annotations, placing them on the **concrete class/method** is usually clearer and easier to control than placing them on the interface, especially if the project might switch to AspectJ weaving. Spring documentation warns that annotations on interfaces are not inherited under Java semantics and have limitations in weaving-based mode.

### Public, Private, Final, Static

- **Public instance methods** on a Spring bean are the recommended choice for @Cacheable, @CachePut, and @CacheEvict in proxy mode; safest when both JDK and class-based proxies must be supported.
- **Private methods** cannot be standard interception points through a Spring AOP proxy; annotations on private methods generally have no effect.
- **Final instance methods** cannot be overridden by a class-based proxy to add advice; do not expect @Cacheable to work on such methods with class proxies.
- **Final classes** cannot serve as targets for CGLIB subclass proxies; forcing class-based proxies hits Java inheritance limits.
- **Static methods** are not instance invocations passing through an AOP bean proxy; do not put @Cacheable on static methods expecting Spring Cache to intercept them.
- **Protected/package-private methods** may behave differently depending on proxy mechanism, Spring version, and AOP infrastructure; for annotation caching, **prefer public methods** per official guidance to avoid implementation dependence.
- **Constructors** and calls made while the target is not yet fully proxied are also unsafe places to rely on annotation caching.

**Do not turn every cache failure into a public/private issue.** First verify whether a proxy exists and the call actually passes through it; only then inspect visibility and proxy type.

## 6. Complete Java 17 + Spring Framework Example: External, Self, Cross-Bean, and New

This is a **runnable demo in a Maven project** using Java 17. We only use an in-memory cache so we can easily verify how many times the target method runs, without a database or TTL. The example shows:

1. Calling **CatalogService.fetch** from a bean retrieved from ApplicationContext → cache hit on the second call.
2. Calling **CatalogService.internalFetch**, which calls **this.fetch** → both calls run the real method and do not write an entry for B.
3. Another **OrderingService** calling the injected CatalogService bean → goes through the proxy, hits on the second call.
4. Creating **new CatalogService()** outside Spring → no proxy/interceptor.

### 6.1. Project Structure

~~~text
spring-cache-proxy-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCacheProxyDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

Spring-context pulls in the Spring modules needed for annotation caching and Spring AOP in this demo. Execution runs in a single JVM without requiring Redis or Caffeine.

### 6.3. src/main/java/demo/SpringCacheProxyDemo.java

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

import java.util.concurrent.atomic.AtomicInteger;

public class SpringCacheProxyDemo {

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "catalog")
        public String fetch(String sku) {
            return "load-" + loads.incrementAndGet();
        }

        public String internalFetch(String sku) {
            return this.fetch(sku); // Does not go back through the Spring proxy.
        }

        public int targetCalls() {
            return loads.get();
        }
    }

    public static class OrderingService {
        private final CatalogService catalog;

        public OrderingService(CatalogService catalog) {
            this.catalog = catalog; // Bean injected by Spring.
        }

        public String fetchThroughOtherBean(String sku) {
            return catalog.fetch(sku); // Goes through the proxy.
        }
    }

    @Configuration
    @EnableCaching
    public static class AppConfig {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        public OrderingService orderingService(CatalogService catalog) {
            return new OrderingService(catalog);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogService catalog = context.getBean(CatalogService.class);
            OrderingService ordering =
                context.getBean(OrderingService.class);

            System.out.println("isProxy="
                + AopUtils.isAopProxy(catalog));

            System.out.println("externalA1=" + catalog.fetch("A"));
            System.out.println("externalA2=" + catalog.fetch("A"));

            System.out.println("selfB1=" + catalog.internalFetch("B"));
            System.out.println("selfB2=" + catalog.internalFetch("B"));

            System.out.println("otherBeanB1="
                + ordering.fetchThroughOtherBean("B"));
            System.out.println("otherBeanB2="
                + ordering.fetchThroughOtherBean("B"));

            System.out.println("targetCalls=" + catalog.targetCalls());

            CatalogService plain = new CatalogService();
            System.out.println("newC1=" + plain.fetch("C"));
            System.out.println("newC2=" + plain.fetch("C"));
        }
    }
}
~~~

The program defines two container-managed services. CatalogService **does not implement an interface**, so the default Spring AOP configuration can still create a **class-based proxy** for it. The methods are overridable, public, and instance-based.

### 6.4. Compile and Run

Inside the **spring-cache-proxy-demo** directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringCacheProxyDemo
~~~

Stdout printed by the **System.out.println** statements in the example, excluding Maven or library logs:

~~~text
isProxy=true
externalA1=load-1
externalA2=load-1
selfB1=load-2
selfB2=load-3
otherBeanB1=load-4
otherBeanB2=load-4
targetCalls=4
newC1=load-1
newC2=load-2
~~~

### 6.5. Why Is the Output Like This?

| Call | Path | Cache state | Does real fetch method run? |
| --- | --- | --- | --- |
| catalog.fetch("A") 1st time | External via proxy | MISS, stores key A | Yes, loads=1 |
| catalog.fetch("A") 2nd time | External via proxy | HIT A | No |
| catalog.internalFetch("B") 1st time | External into internalFetch, then this.fetch | **Bypasses interceptor** for fetch | Yes, loads=2 |
| catalog.internalFetch("B") 2nd time | Same | **Bypasses interceptor** for fetch | Yes, loads=3 |
| ordering.fetchThroughOtherBean("B") 1st time | OrderingService → injected catalog proxy | MISS B, stores key B | Yes, loads=4 |
| ordering.fetchThroughOtherBean("B") 2nd time | Same | HIT B | No |
| plain.fetch("C") 1st time | new CatalogService outside Spring | No proxy | Yes, separate loads=1 |
| plain.fetch("C") 2nd time | Same | No proxy | Yes, separate loads=2 |

**isProxy=true** proves the catalog variable obtained from the context is an AOP proxy. CatalogService not having an interface does not prevent Spring from creating a subclass proxy in typical configuration. On the other hand, the manually instantiated **CatalogService plain** has an independent loads counter and no cache interceptor.

Important detail: the **catalog.internalFetch** call also passes through the proxy at the initial boundary. However, because **internalFetch has no cache operation**, the proxy simply delegates to the target. Inside the target, **this.fetch** does not re-enter the proxy; therefore @Cacheable on fetch is not applied. Starting a method from a proxy bean **does not mean nested calls are automatically intercepted**.

### 6.6. Try a Variation to Understand the Mechanism Yourself

If you reverse the order—calling **ordering.fetchThroughOtherBean("B")** first to cache B, and then calling **catalog.internalFetch("B")**—the this.fetch calls still run the target even though cache B already holds an entry. The reason is not a cache miss; the reason is that **the interceptor never gets a chance to check the cache**.

Therefore, seeing an existing entry in the cache while the method still executes is not enough to conclude @Cacheable has the wrong key: you must check whether the call passes through the proxy.

## 7. Recommended Fix for Self-Invocation: Extract into a Collaborating Bean

The cleanest design solution in many applications is to **move the cached method into a separate bean** and inject this bean into the calling class.

~~~text
OrderFacade (Spring bean)
     |
     | injected CatalogReader bean reference
     v
CatalogReader proxy
     |
     v
@Cacheable CatalogReader.find(sku)
     |
     +-- cache HIT -> return
     +-- cache MISS -> target CatalogReader.find(sku)
~~~

An illustration of how to organize it:

~~~java
@Service
public class CatalogReader {

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String sku) {
        return repositoryLookup(sku);
    }
}

@Service
public class OrderFacade {
    private final CatalogReader catalogReader;

    public OrderFacade(CatalogReader catalogReader) {
        this.catalogReader = catalogReader;
    }

    public String createOrder(String sku) {
        String product = catalogReader.find(sku);
        return "order-for-" + product;
    }
}
~~~

This is **illustrative structural code**; repositoryLookup, imports, and business implementation need to be added, so do not treat it as a standalone program. Benefits:
- The call path from **OrderFacade** to **CatalogReader** passes through the injected bean proxy.
- Clear separation between data reading and business orchestration responsibilities.
- Easy to write integration tests that genuinely go through ApplicationContext.
- No need to create circular bean dependencies, nor rely on AopContext or exposeProxy mechanisms.

You do not have to split every method into its own class. Only extract parts that have a distinct caching policy or parts frequently called internally that need interception.

### Alternative: Injecting Your Own Proxy

Some projects use **self-injection** or look up the proxy from the container to re-invoke the method through the proxy. Technically this can overcome the bypass, but it easily creates circular dependencies, makes testing harder, and couples code to the container. In modern Spring Boot, circular references are typically restricted by default configuration. Only choose this when you truly understand the lifecycle and have a clear reason; **extracting a bean** is usually simpler and safer.

### Alternative: AopContext.currentProxy()

You can configure exposeProxy and obtain the current proxy via AopContext. This ties business code to Spring AOP, only works within an appropriate advice context, and requires extra configuration; it should not be used by default just to rescue a self-invocation. **@EnableCaching(proxyTargetClass=true) alone does not enable exposeProxy**.

### Alternative: AdviceMode.ASPECTJ

If caching must work even for self-invocation at the bytecode level, Spring supports weaving mode:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.cache.annotation.EnableCaching;

@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

This is an **illustrative configuration snippet** on a configuration class, not a standalone runnable application. AspectJ caching requires **spring-aspects** and properly configured **compile-time weaving or load-time weaving**. Simply changing mode in the annotation without the proper dependencies/weaver will not make the program run with AspectJ.

In ASPECTJ mode, Spring can apply advice to internal calls via weaving (no longer bound by Java proxy boundaries like PROXY). In return, build/deployment becomes more complex and requires careful testing. **proxyTargetClass** plays no role in selecting proxy type in ASPECTJ mode.

## 8. How to Verify a Bean Is Actually a Proxy

When troubleshooting, first retrieve the container-managed bean:

~~~java
CatalogService service =
    applicationContext.getBean(CatalogService.class);
~~~

This is an illustrative snippet assuming applicationContext is provided. With a JDK proxy, you may need to retrieve the bean by **interface** rather than concrete class.

Check Spring AOP without relying on proxy symbols in the class name:

~~~java
import org.springframework.aop.support.AopUtils;

boolean isProxy = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean classProxy = AopUtils.isCglibProxy(service);
~~~

This is an illustrative snippet, not a standalone program; AopUtils lives in the spring-aop module. **isAopProxy** helps verify there is a proxy on the current reference. **isJdkDynamicProxy** and **isCglibProxy** help identify the proxy family. Not every proxy is created for caching: @Transactional, security, retry, or other advice can also create proxies. **isAopProxy=true only proves the object is a Spring AOP proxy, not that @Cacheable on a specific method is being intercepted**.

Behavioral testing is still needed: call the method twice with the same input through the proxy bean, and observe how many times the target method executes and what entries are written. If the cache misses every time despite having a proxy, continue checking cache name, key, condition, unless, TTL, eviction, or infrastructure configuration.

### Avoid Guessing from Class Names in Logs

JDK proxies may print names like jdk.proxy...; class proxies may show subclass/enhancer markers. Specific names depend on the runtime and version and should not be hardcoded into tests. Use AopUtils and method invocation behavior instead of string-matching class names.

## 9. Places Where Proxy Mode Is Easily Bypassed

### 9.1. Internal Method Calls via this or Implicit Calls

~~~java
@Cacheable("catalog")
public String find(String sku) { return query(sku); }

public String refreshView(String sku) {
    return find(sku); // self-invocation, does not go through the proxy.
}
~~~

This is an illustration. Even though refreshView is called from a controller through the proxy, calling find inside the target body is an internal call. If refreshView also has its own cache annotation, Spring can only apply **the operation on refreshView at the proxy boundary**, without automatically adding interception for find inside.

### 9.2. Objects Not Managed by the Container

~~~java
var service = new CatalogService();
service.find("A");
~~~

There is no Spring bean proxy; @Cacheable does not take effect automatically. Only when a class is registered via @Bean or @Component/@Service and properly injected can the caching infrastructure apply.

### 9.3. Initialization in Constructors or @PostConstruct

While an object is initializing, the bean proxy may not be complete or handed to callers yet. If @PostConstruct calls a cache-annotated method on this, do not expect caching advice to work. Spring also recommends not relying on cache proxies during initialization logic.

If cache warm-up is needed after the context is ready, call through the **bean proxy** from another component at an appropriate time, instead of calling cache-annotated methods directly in the constructor.

### 9.4. Beans in Different ApplicationContexts

In traditional Spring MVC, there may be a **root ApplicationContext** for services and a **child WebApplicationContext** for controllers. If @EnableCaching is only declared in the child context while the service lives in the root context, cache annotations on the service may not be processed as expected.

Place caching infrastructure in the context managing the beans to be cached, or configure it to match the context architecture. Do not assume that a single @EnableCaching anywhere in the application automatically scans every independent context.

### 9.5. Selecting a Bean by Concrete Type When Using a JDK Proxy

If a class implements an interface and the bean is a JDK dynamic proxy, injecting by class may not be assignable. Inject the appropriate interface, or deliberately configure a class-based proxy while understanding final class/final method limitations.

### 9.6. Multiple Advices and Application Order

@Cacheable can be combined with @Transactional, @Async, security, or other advice. Calls still need to pass through the proxy, but **advice ordering** can affect transaction boundaries, exceptions, threads, and cache update timing. The **order** attribute of @EnableCaching controls the caching advisor's order in the AOP chain; do not assume all advice automatically has the optimal order for every business case.

When caching data that changes in a transaction, distinguish **method return** from **transaction commit**. Putting or evicting cache entries at the wrong time can cause stale/dirty visibility. This is a cache-and-transaction coordination problem, not something fixed by switching from JDK proxy to class proxy.

## 10. Debug Sequentially Instead of Changing Cache Providers Immediately

When @Cacheable seems "not to work," check step by step:

| Step | Check | If incorrect |
| --- | --- | --- |
| 1 | Is @EnableCaching or equivalent present, with a valid CacheManager? | Add infrastructure; verify active beans/configs |
| 2 | Is the object a Spring-managed bean? | Do not use new for services needing interception |
| 3 | Is the caller invoking a reference from ApplicationContext/proper injection? | Use the bean proxy instead of target/raw instance |
| 4 | Is there self-invocation through this? | Extract into a collaborating bean, call via injected proxy |
| 5 | Is the method public and free of final/private/static restrictions? | Use an advisable public instance method |
| 6 | Does the class have an interface and is a JDK proxy injected by the right type? | Inject the interface or choose an appropriate class proxy |
| 7 | Does AopUtils.isAopProxy(reference) return true? | Check context/auto-proxy configuration |
| 8 | Does cache name exist, key build properly, and condition/unless allow caching? | Test actual keys and operations |
| 9 | Are TTL/eviction/provider settings dropping entries immediately? | Check storage policies rather than blaming the proxy first |
| 10 | Do other advices change ordering/transactions/threads? | Check advisor ordering and write integration tests |

**A minimal observation workflow:**
1. Use a **targetCalls** counter inside the real method.
2. Call twice with the same input via an injected service bean.
3. Compare the results and the number of times the target method runs.
4. Call similarly through an internal method using this.
5. Compare and inspect the cache via the proper CacheManager bean.

With @Cacheable and a non-expiring cache, expected result: via proxy, the second call hits; with self-invocation, the target method still runs. If a call throws an exception or the provider errors, behavior depends on CacheErrorHandler and the annotation; do not assume every call succeeds.

## 11. Distinguishing Call Path from Cache Key Design

Having a proxy but inconsistent keys can still miss every time:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String sku) {
    return repository.findName(sku);
}
~~~

This is an illustration. If the caller passes " A " the first time and "A" the second time, the String keys differ. The cache misses **even though the proxy works properly**. Similarly, when the return value is vetoed by unless, condition evaluates to false, the cache manager uses the wrong cache, or another operation evicts the entry, the symptom can be that the method runs multiple times.

Therefore, classify root causes into two branches:
- **Interceptor does not run:** caused by self-invocation, raw new, missing @EnableCaching, incompatible bean/context/proxy.
- **Interceptor runs but cache does not hit:** caused by key, condition, unless, cacheName, TTL, eviction, or provider.

This distinction prevents trying to "fix" the problem by changing hashCode(), increasing TTL, or switching to Redis when the real cause is **the method never passed through the proxy at all**.

## 12. Self-Check Questions

**1.** @Cacheable is on a public method, and the caller uses new Service().find("A"). Is the method intercepted by Spring Cache?

**No.** The object is not managed/proxied by Spring; annotations do not turn into caching logic on direct Java calls.

**2.** A controller injects ProductService and calls productService.find("A") via the Spring bean. Is this an appropriate call path for proxy caching?

**Yes**, if @EnableCaching/cache infrastructure is active and the method is advisable. External calls going through the proxy bean reference allow the caching interceptor to run.

**3.** Inside ProductService.refresh(), there is this.find("A") and find has @Cacheable. Does this call hit the cache under PROXY mode?

**Not via the annotation on find**, because self-invocation bypasses the proxy; if you want caching for find, move it to another injected bean or use an appropriate mechanism.

**4.** Does setting @EnableCaching(proxyTargetClass=true) make this.find go through the proxy?

**No.** This attribute selects class-based proxies; it does **not** alter internal this-call paths.

**5.** Why does a BeanService with an interface sometimes fail when injected by concrete class?

Because with a JDK proxy, the proxy bean implements the interface and is not necessarily a subclass of the concrete class. Injecting by interface is compatible with JDK proxies.

**6.** Does isAopProxy(bean)=true alone mean every cache annotation is working?

**No.** The proxy may have been created for another advice; a specific annotation may still be invalid, the method unintercepted, or the cache operation affected by conditions/keys/provider.

**7.** If you want caching to apply to self-invocation without refactoring to another bean, what option exists?

You can use AspectJ weaving with spring-aspects and proper compile-time/load-time weaving configuration; this is an advanced option requiring testing and accepting build/runtime complexity.

**8.** Are public methods and Spring-managed beans needed to safely demonstrate Spring Cache in proxy mode?

**Recommended**. Public instance methods on a Spring bean called through a proxy are easy to understand, easy to test, and aligned with Spring recommendations.

## Summary

- **@EnableCaching defaults to AdviceMode.PROXY**.
- Cache advice takes effect when callers **go through the Spring bean proxy**; manually instantiated objects and self-invocation via this typically **bypass** the cache interceptor.
- **proxyTargetClass** selects the proxy family, not an automatic fix for self-invocation. JDK dynamic proxies are interface-based; class-based proxies are subclass-based and limited by final classes/final methods.
- When a cache-annotated method needs to be called from internal logic, **extracting it to a collaborating bean and injecting that bean** is the maintainable choice.
- Only switch to **AdviceMode.ASPECTJ** when intra-class interception is required and **spring-aspects + weaving** are properly configured.
- When debugging, clearly distinguish **interceptor not called** from **interceptor ran but cache missed**.

### Official Documentation

- Spring Framework 6.2 – Annotation-based caching (enabling, proxy mode, self-invocation, and method visibility): https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- @EnableCaching API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring AOP – Proxying mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring AOP – Understanding AOP proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html#_understanding_aop_proxies
- @Cacheable API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/Cacheable.html
