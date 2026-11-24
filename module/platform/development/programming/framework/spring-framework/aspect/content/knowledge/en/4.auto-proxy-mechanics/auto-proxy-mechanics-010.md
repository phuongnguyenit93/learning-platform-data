# Distinguishing AOP Proxies From Proxies Created by Other Mechanisms in Spring

## 1. Why Should You Not Conclude "Has Proxy Means Has `@Aspect`"?

Spring Framework uses **delegation and behavior enhancement** mechanisms in many places. When debugging a Spring bean, you may see a dynamically generated class containing `$$SpringCGLIB$$`, a JDK dynamic proxy, or an instance returning `true` for `AopUtils.isAopProxy(...)`. Those observations **do not automatically prove** that the bean is running advice from an application-written `@Aspect`.

Under the **Auto-Proxy Mechanics** topic, this lesson answers four specific questions:

1. How does a **Spring AOP** proxy using advisors/advice to intercept methods differ from proxies supporting **scopes** and proxies created by other utilities?
2. Why can `@Transactional`, `@Cacheable`, and `@Async` also use the AOP infrastructure even when the application writes no `@Aspect` class at all?
3. Why does a `@Configuration` class being **CGLIB-enhanced** by Spring not mean it is a Spring AOP proxy?
4. Which APIs should you rely on to verify **proxy type, advisors, target, and actual behavior** rather than guessing from class names?

The scope focuses on **Spring Framework/Spring Boot and proxy-based Spring AOP**; general aspect theory is not repeated.

## 2. Separating Three Axes to Identify a Proxy Accurately

A proxy should be classified by **who created it**, **its purpose**, and **the underlying technical mechanism**. These three are related, not identical.

| Axis | Question to ask | Examples |
| --- | --- | --- |
| Origin | Which BeanPostProcessor/FactoryBean/mechanism created or enhanced the instance? | Spring AOP auto-proxy creator, `ScopedProxyFactoryBean`, `ConfigurationClassEnhancer`, Spring Data repository factory |
| Purpose | What function does the proxy solve? | Invoking `@Before`, opening a transaction, caching results, looking up the right scoped target, preserving `@Bean` call semantics |
| Technology | How was the wrapper built? | JDK dynamic proxy, CGLIB subclass, bytecode enhancement, interface adapter |

Both Spring AOP and scoped proxies can use the same **`spring-aop` infrastructure** and the same JDK/CGLIB technologies. Conversely, `@Configuration` also uses CGLIB, yet serves a separate mechanism. Therefore, you cannot classify a proxy merely by `CGLIB` or `Proxy` in the class name.

### 2.1. Understanding the Phrase "AOP Proxy" Accurately

This phrase has two levels:

- **Technically a Spring AOP proxy:** an object created by Spring AOP infrastructure carrying the `SpringProxy` marker; detectable via `AopUtils.isAopProxy(object)`. It can serve business advisors, transactions/caching, **or scoped delegation**.
- **Proxy carrying advice from a specific `@Aspect`:** narrower. You must prove that the aspect's advisor is attached to the proxy and that method calls **match the pointcut** so the advice actually runs.

Therefore, **`isAopProxy == true` does not mean "my advice is running"**, and **`isAopProxy == false` does not mean the object is unenhanced by another mechanism**.

## 3. Comparing Common Mechanisms in Spring

| Case | Who creates/configures behavior | Usually uses a Spring AOP proxy? | Requires custom `@Aspect`? | Key significance |
| --- | --- | --- | --- | --- |
| `@Aspect` + `@EnableAspectJAutoProxy` | Spring AOP auto-proxy creator selects advisors from aspect beans | **Yes** | Yes, if you define `@AspectJ`-style advice yourself | Methods on target bean receive advice when called through proxy and pointcut matches |
| `@Transactional` with `@EnableTransactionManagement(mode = PROXY)` | Transaction advisor + `TransactionInterceptor` | **Yes** | **No** | Proxy coordinates transactions around methods matching metadata |
| `@Cacheable` with `@EnableCaching(mode = PROXY)` | Cache advisor + cache abstraction interceptor | **Yes** | **No** | Proxy checks/stores cache, can skip running target on cache hit |
| `@Async` with `@EnableAsync` | Async annotation processing/advisor | Usually **yes** in proxy mode; integration details can vary by version | **No** | Dispatches matching calls to an executor, subject to proxy limits |
| `@Scope(proxyMode = TARGET_CLASS)` or `<aop:scoped-proxy/>` | Scoped proxy factory/target source | **Detectable with `AopUtils`** because it uses Spring AOP infrastructure | **No** | Looks up the right scoped target at call time |
| `@Configuration(proxyBeanMethods = true)` | Spring `ConfigurationClassEnhancer` | **Not by default** | **No** | CGLIB subclass routes `@Bean` calls through the container |
| `@Lookup` method injection | Spring bean method override/subclass enhancement | **Not by default** | **No** | Replaces lookup method calls with bean retrieval |
| JDK proxy returned from a custom `@Bean` | Code using `java.lang.reflect.Proxy` | **Not by default** | **No** | Bean can be a JDK proxy without carrying the Spring AOP marker |
| Spring Data repository | Repository factory builds implementation/proxy and interceptors | Usually uses Spring Data's `ProxyFactory`/AOP base | **No** | Repository API dispatches to queries/implementations; do not infer `@Aspect` advice |

**Note on `@Transactional`, `@Cacheable`, `@Async`:** They are not examples of "not using Spring AOP" when in **proxy mode**; they are proof that **the AOP infrastructure also serves other Spring features** without needing a user-written `@Aspect` class. A single bean can simultaneously receive multiple advisors from multiple sources. With AspectJ weaving mode if configured separately, these mechanisms can work differently; the table focuses on proxy mode.

**Note on scoped proxies:** This is a case that easily surprises people. A scoped proxy can return `true` for `AopUtils.isAopProxy(...)`, yet its purpose is **selecting a target from the scope**, not automatically invoking an application `@Before`. The difference lies in **advisors/target source and behavior**, not just the proxy infrastructure type.

## 4. When Does Spring AOP Auto-Proxy Create a Proxy?

In `@AspectJ`-based Spring AOP, typical conditions are needed:

1. The aspect is already a **Spring bean** (`@Aspect @Component` within scan scope, or an `@Bean` returning the `@Aspect` instance).
2. Spring AOP support is active (e.g., `@EnableAspectJAutoProxy`; with Spring Boot, possibly via AOP/AspectJ starter auto-configuration).
3. An advisor/pointcut matches the target bean.
4. The bean is proxy-eligible and the client invokes the method **through the proxy**.

Illustrative call path:

```text
Client -> Spring bean reference (AOP proxy)
            -> interceptor/advice matching method
            -> target.method()
            -> return result
```

Spring AOP has two basic wrapper strategies:

- **JDK dynamic proxy** when proxying by interface: the object implements the exposed interfaces, not a direct instance of the implementation class.
- **CGLIB class-based proxy** when proxying by class: the object is a dynamically generated subclass of the target class, subject to `final`, `private`, and method-override limits.

It is **the advisor source and call path** that explain why advice runs. Class names generated by JDK or CGLIB only describe the proxy-creation technique.

## 5. Transaction/Cache/Async Proxies: AOP Without Necessarily Having `@Aspect`

### 5.1. `@Transactional`

With annotation-driven transaction management in **proxy mode**, Spring usually creates an advisor using `TransactionInterceptor` and `TransactionAttributeSource`, working with a `TransactionManager`. Clients call the transactional method through the bean proxy; the interceptor starts/joins a transaction, invokes the method, and commits/rolls back according to configuration.

```java
// Snippet to insert into an application with an appropriate transaction manager configured.
// Not a standalone program.
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Execute business logic inside transaction.
    }
}
```

You do not need to write an `@Aspect` to get transaction advice. Conversely, merely adding `@Transactional` without the required transaction infrastructure/manager and configuration does not guarantee transactions work.

`@Transactional` in **proxy mode** is also subject to the self-invocation limit: `this.pay()` inside the target can bypass the transaction interceptor. This happens because the mechanism is based on Spring AOP proxies.

### 5.2. `@Cacheable`

With `@EnableCaching` in proxy mode, Spring creates cache-related advisors/interceptors for matching beans:

```java
// Illustrative snippet, requires CacheManager and caching enabled.
@Cacheable("products")
public Product findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
```

A cache hit can return the result immediately, **without calling the target method**. Not seeing a log inside the target once does not mean the proxy/pointcut is broken. Check `CacheManager`, cache name, key, and cache advice. A proxy created for caching can yield `AopUtils.isAopProxy(bean) == true` even when the application declares no custom `@Aspect` at all.

### 5.3. `@Async`

In proxy configuration, `@Async` uses Spring infrastructure to handle invocations and hand off eligible executions to an executor. It does not require a user-written `@Aspect`. In Spring Framework, enabling `@EnableAsync`, providing an executor, and handling return types belong to async feature configuration; here what matters is that **proxies can be generated for different purposes**.

**Do not equate the three features:** Having a transaction proxy does not mean cache advice is enabled; having an async proxy does not mean every method runs off the current thread. To draw conclusions, inspect the actual advisors and annotation metadata.

## 6. Scoped Proxy: Using AOP Infrastructure to Look Up Targets by Scope

For example: a singleton needs to call a bean with a shorter scope (request/session) or a `prototype`. Instead of holding one fixed target from the wrong scope, Spring can inject a **scoped proxy**. This proxy retrieves the appropriate target instance from the container when a method is called.

```java
@Bean
@Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
       proxyMode = ScopedProxyMode.TARGET_CLASS)
public ScopedWorker scopedWorker() {
    return new ScopedWorker();
}
```

This is an **illustrative snippet inside an `@Configuration` class**, requiring imports for `@Bean`, `@Scope`, `ConfigurableBeanFactory`, and `ScopedProxyMode`. It is not a standalone program; section 8 has a runnable project.

For a `prototype` scoped proxy:

```text
Singleton caller -> same scoped proxy
                      |
            every method call
                      |
                  BeanFactory
                      |
               new prototype target
                      |
                 target.method()
```

With `request` or `session` scope, Spring looks up the target corresponding to the current request/session; if called when the scope is inactive, a scope-related exception can occur. Do not use a `request`-scoped bean directly in a console application without a request context.

**Key point:** a scoped proxy can be a **real Spring AOP proxy** in terms of marker/infrastructure (`ScopedProxyFactoryBean` uses Spring AOP proxy machinery), yet **that does not mean** it has `@Aspect` advice. If other matching advisors exist, multiple proxy roles can coexist or be combined.

## 7. `@Configuration` CGLIB Enhancement Differs From an AOP Proxy

An `@Configuration(proxyBeanMethods = true)` class (the default in full configuration mode) is enhanced by Spring with a CGLIB subclass so calls between `@Bean` methods respect the container and bean scopes:

```java
@Configuration(proxyBeanMethods = true)
public class SampleConfig {
    @Bean
    public Repository repository() {
        return new Repository();
    }

    @Bean
    public Service service() {
        return new Service(repository());
    }
}
```

This is an **illustrative snippet**, assuming `Repository` and `Service` classes exist. For singleton beans, calling `repository()` from `service()` is intercepted by the enhanced subclass to retrieve the bean from the container appropriately, rather than always creating an independent new instance.

Comparison:

| CGLIB-enhanced `@Configuration` | Class-based Spring AOP proxy |
| --- | --- |
| Created by `ConfigurationClassEnhancer` infrastructure | Created by Spring AOP proxy infrastructure |
| Goal is preserving `@Bean` method and inter-bean reference semantics | Goal is routing calls through interceptors/advisors |
| Does not automatically have the `SpringProxy` marker just for using CGLIB | Spring AOP proxy carries the `SpringProxy` marker |
| `AopUtils.isAopProxy(configBean)` is usually `false` | `AopUtils.isAopProxy(aopProxy)` is `true` |
| `configBean.getClass() != SampleConfig.class` can be `true` | Target class can also differ from runtime class due to proxying |

When using `@Configuration(proxyBeanMethods = false)`, Spring **does not use this cross-`@Bean` call enhancement**. However, setting `false` **is not a way to disable Spring AOP** for service beans; they are two separate mechanisms.

Also distinguish `@Lookup` method injection: Spring may use a subclass to override a lookup method to retrieve a bean, yet the purpose is **bean lookup**, not automatically running `@Aspect` advice.

## 8. Runnable Java 17+ Example: Comparing Three Spring Mechanisms and a JDK Proxy

The following program uses Spring Framework 6.2.19, Java 17+, Maven, and requires no Spring Boot, HTTP server, database, or transaction manager. It demonstrates:

- `BillingService` is proxied by an advisor from an `@Aspect`.
- `ScopedCounter` is proxied to supply matching `prototype` targets even though **no `@Aspect` advice targets it**.
- `AppConfig` is a CGLIB-enhanced configuration class, yet **is not a Spring AOP proxy** in this configuration.
- A `Runnable` using `java.lang.reflect.Proxy` returned from an `@Bean` is a **Spring-managed bean that is a JDK proxy**, yet not a Spring AOP proxy.

### 8.1. Directory Structure

```text
proxy-origin-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── BillingService.java
    ├── BillingAspect.java
    ├── ScopedCounter.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>proxy-origin-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
```

### 8.3. `BillingService.java`

```java
package example;

public class BillingService {
    public void charge() {
        System.out.println("billing: charge");
    }
}
```

### 8.4. `BillingAspect.java`

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BillingAspect {
    @Before("execution(* example.BillingService.charge(..))")
    public void beforeCharge() {
        System.out.println("aspect: before charge");
    }
}
```

### 8.5. `ScopedCounter.java`

```java
package example;

import java.util.concurrent.atomic.AtomicInteger;

public class ScopedCounter {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public int id() {
        return id;
    }
}
```

Each `ScopedCounter` instance holds its own `id`. If two calls to `id()` delegate to two new prototype targets, the results will differ.

### 8.6. `AppConfig.java`

```java
package example;

import java.lang.reflect.Proxy;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;

@Configuration(proxyBeanMethods = true)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public BillingService billingService() {
        return new BillingService();
    }

    @Bean
    public BillingAspect billingAspect() {
        return new BillingAspect();
    }

    @Bean
    @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
           proxyMode = ScopedProxyMode.TARGET_CLASS)
    public ScopedCounter scopedCounter() {
        return new ScopedCounter();
    }

    @Bean
    public Runnable plainJdkProxy() {
        Runnable delegate = () -> System.out.println("jdk: delegated");
        return (Runnable) Proxy.newProxyInstance(
            AppConfig.class.getClassLoader(),
            new Class<?>[] { Runnable.class },
            (proxy, method, args) -> method.invoke(delegate, args)
        );
    }
}
```

Why is using `new` inside `@Bean` methods still valid? Because **the returned value** is registered by Spring as a bean and can be processed by post-processing/proxying mechanisms. Calling `new` outside the container for a private instance does not automatically receive that mechanism.

### 8.7. `Main.java`

```java
package example;

import java.lang.reflect.Proxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService billing = context.getBean(BillingService.class);
            ScopedCounter counter = context.getBean(ScopedCounter.class);
            AppConfig config = context.getBean(AppConfig.class);
            Runnable jdk = context.getBean("plainJdkProxy", Runnable.class);

            System.out.println("billing Spring AOP proxy: "
                + AopUtils.isAopProxy(billing));
            System.out.println("scope Spring AOP proxy: "
                + AopUtils.isAopProxy(counter));
            System.out.println("scope targets differ: "
                + (counter.id() != counter.id()));
            System.out.println("config subclassed: "
                + (config.getClass() != AppConfig.class));
            System.out.println("config Spring AOP proxy: "
                + AopUtils.isAopProxy(config));
            System.out.println("plain JDK dynamic proxy: "
                + Proxy.isProxyClass(jdk.getClass()));
            System.out.println("plain Spring AOP proxy: "
                + AopUtils.isAopProxy(jdk));

            billing.charge();
            jdk.run();
        }
    }
}
```

Run in the directory containing `pom.xml` (requires matching Maven/JDK):

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed **by the program**, in order:

```text
billing Spring AOP proxy: true
scope Spring AOP proxy: true
scope targets differ: true
config subclassed: true
config Spring AOP proxy: false
plain JDK dynamic proxy: true
plain Spring AOP proxy: false
aspect: before charge
billing: charge
jdk: delegated
```

### 8.8. Why Do the Results Differ?

**`billing Spring AOP proxy: true`**: `BillingAspect` is a bean via `@Bean`, `@EnableAspectJAutoProxy` is enabled; the advisor from `@Before` matches `BillingService.charge()`. Spring returns an AOP proxy for the `billingService` bean, and when `billing.charge()` runs through the proxy, the advice prints before the business line.

**`scope Spring AOP proxy: true`**: `scopedCounter` is declared `prototype` with a scoped proxy. Spring AOP infrastructure creates a wrapper to look up the right scoped target. `BillingAspect` only targets `BillingService.charge()`, so **none of the example's `@Before` advice applies to `ScopedCounter.id()`**. Two calls to `counter.id()` fetch two different prototype targets, so the comparison returns `true`. A **different** method call on the scoped proxy can also fetch a new target; do not store long-lived state in a prototype target expecting it to be reused across calls through the scoped proxy.

**`config subclassed: true` yet `config Spring AOP proxy: false`**: `@Configuration(proxyBeanMethods = true)` causes the configuration class to be CGLIB-enhanced so Spring coordinates `@Bean` methods. No AOP advisor matches the configuration class in the example, and CGLIB enhancement itself is not a Spring AOP proxy.

**`plain JDK dynamic proxy: true` yet `plain Spring AOP proxy: false`**: `@Bean` `plainJdkProxy()` creates a dynamic proxy using Java reflection and returns it for Spring to manage. A JDK proxy **does not inherently carry the Spring AOP marker**, and has no Spring advisors in this configuration. If another advisor later wraps that bean further, observation of *the new reference* may change.

These are four groups differing in **purpose and origin**, even though they may all use proxy classes or all be returned by the Spring container.

## 9. Appropriate Diagnostic Toolkit

### 9.1. `AopUtils`: Detecting Spring AOP Proxies

Common APIs of `org.springframework.aop.support.AopUtils`:

```java
// Snippet placed in code with already-initialized bean references.
boolean springAop = AopUtils.isAopProxy(bean);
boolean jdkSpringAop = AopUtils.isJdkDynamicProxy(bean);
boolean cglibSpringAop = AopUtils.isCglibProxy(bean);
Class<?> targetClass = AopUtils.getTargetClass(bean);
```

- `isAopProxy` identifies **Spring AOP proxies**; it additionally checks the `SpringProxy` marker, rather than relying only on class names.
- `isJdkDynamicProxy` and `isCglibProxy` distinguish **the two Spring AOP strategies**.
- `getTargetClass` helps find the target type if information is available; do not assume it unwraps every custom proxy layer or nested proxy chain.

**Do not use `Proxy.isProxyClass(...)` alone to prove Spring AOP**: that is a check for **JDK dynamic proxies in general**, without requiring Spring. Similarly, `$$` or `$$SpringCGLIB$$` in a class name can belong to another form of CGLIB enhancement.

### 9.2. `Advised`: Viewing Advisors and Target Source (When Available)

A typical Spring AOP proxy can implement `org.springframework.aop.framework.Advised`. In section 8's example, you can add the following snippet at the end of `main` before closing the context to observe:

```java
// Snippet, not a standalone program:
if (billing instanceof org.springframework.aop.framework.Advised advised) {
    System.out.println("billing advisors: " + advised.getAdvisors().length);
    System.out.println("billing target source: "
        + advised.getTargetSource().getClass().getSimpleName());
}
if (counter instanceof org.springframework.aop.framework.Advised advised) {
    System.out.println("scope advisors: " + advised.getAdvisors().length);
    System.out.println("scope target source: "
        + advised.getTargetSource().getClass().getSimpleName());
}
```

The advisor count or target source class name depends on version/configuration, so **do not hardcode stdout** of this diagnostic snippet. What matters is:

- **Advisor** describes the advice/interceptor chain attached to the observed proxy.
- **TargetSource** supplies the target the proxy will invoke. With a scoped proxy, the target source retrieves the bean from the scope; do not equate it with a normal static target source.
- If a proxy is configured `opaque`, casting to `Advised` is not always possible; use `instanceof`.
- `Advised.getAdvisors()` reports advisors installed on **the observed proxy layer**, yet does not by itself prove an advice ran for a specific call. You must check method matching and behavior.

Do not call `advised.getTargetSource().getTarget()` arbitrarily when debugging request/prototype scopes: that operation may instantiate/fetch a target or require an active scope, leading to unintended side effects. Prefer observing the target source type and executing methods in a controlled context.

### 9.3. Confirming Where Advice Comes From

A bean confirmed by `AopUtils.isAopProxy(...)` can contain:

- Advisors declared from application-registered `@Aspect`s.
- Infrastructure advisors created by Spring transactions, caching, async, or other features.
- Interceptors serving scoped target routing.
- Advisors/delegation paths from framework extensions.

Therefore, when asking "Is **aspect X**'s advice being used?", you must check **whether the `@Aspect` bean exists, whether the aspect's advisor applies to the target, whether the method matches, and whether the call goes through the proxy**. Do not merely print one boolean flag.

### 9.4. Nested or Combined Proxies

In complex projects, a bean can pass through multiple post-processing layers or be wrapped by multiple proxies. For instance, an object originally returned by a factory as a proxy and then wrapped further by Spring AOP. In that case:

```text
Client
  -> outer proxy / interceptor A
      -> inner proxy / interceptor B
          -> target
```

Do not infer the **exact** order of interceptors or proxy layers solely from class names; inspect the `Advised` configuration, target source, and invocation trace of the running version. Spring also has mechanisms to unify/coordinate auto-proxy settings so two configuration annotations do not automatically create two separate proxies.

## 10. Decision Tree When Encountering a "Proxy-Looking" Bean

```text
Was the object obtained from Spring ApplicationContext?
|
+-- No: determine who created the object (new, JDK Proxy, mock, external factory)
|
+-- Yes: AopUtils.isAopProxy(bean)?
    |
    +-- false:
    |   +-- Proxy.isProxyClass(bean.getClass())?
    |   |      -> Could be a non-Spring-AOP JDK proxy
    |   +-- getClass() differs from original class / CGLIB enhancement?
    |          -> Check @Configuration, @Lookup, or another enhancement mechanism
    |
    +-- true:
        +-- isJdkDynamicProxy / isCglibProxy to know the form
        +-- instanceof Advised? Inspect advisors + target source if available
        +-- Is the @Aspect advisor you need present?
        |      -> Yes: proceed to check pointcut/method/invocation
        |      -> No: check transaction/cache/async/scope/other features
        +-- Call method through bean proxy, verify actual behavior
```

**A proxy "created by Spring" is not necessarily "created by Spring AOP auto-proxying from `@Aspect`".** At the same time, a scoped proxy is a counterexample to the overly simplistic classification "AOP proxy = developer-written advice": a scoped proxy can use the exact Spring AOP infrastructure, yet its purpose is scope resolution.

## 11. Common Diagnostic Mistakes

| Symptom | Common hasty wrong conclusion | Reliable way to check |
| --- | --- | --- |
| `bean.getClass().getName()` contains `$$SpringCGLIB$$` | Definitely has `@Aspect` advice | Check `AopUtils.isAopProxy`, `@Configuration` classes, advisors, and behavior |
| `Proxy.isProxyClass(bean.getClass()) == true` | This is a Spring AOP proxy | Check `AopUtils.isAopProxy`; plain JDK proxy may not be Spring AOP |
| `AopUtils.isAopProxy(bean) == true` | Every method runs my advice | Check eligible advisors, pointcuts, runtime methods, and proxied calls |
| Bean has `@Transactional`, `@Cacheable`, or `@Async` | Must have an `@Aspect` class | Check Spring annotation infrastructure and corresponding config/managers |
| Scoped proxy for `prototype` has AOP marker | It must be running aspect advice | Check target source, scope, and advisors; primary purpose is target lookup |
| `@Configuration(proxyBeanMethods = true)` creates a subclass | Configuration class is being intercepted by an aspect | Distinguish `@Bean` enhancement from AOP advisors |
| Bean has an AOP proxy, yet self-invocation has no log | Pointcut must be wrong | Check `this.method()`; internal calls run directly on target |
| Target log missing during `@Cacheable` call | No proxy exists | Could be a cache hit; check cache metrics/interceptor |
| Need to read `request`-scoped target with no request | Can call anytime to inspect | Only debug in the right active scope; avoid forcing scoped target retrieval early |
| `final` class with CGLIB proxy | AOP annotation definitely applied | CGLIB cannot subclass a `final` class; inspect proxy type and error messages |

## 12. Practice Exercises

**Scenario A.** `@Configuration(proxyBeanMethods = true)` gives the config bean a runtime class different from the source class. `AopUtils.isAopProxy(config)` equals `false`. Is this a contradiction?

**Answer:** No. CGLIB subclass enhancement for `@Bean` semantics differs from a Spring AOP proxy. Do not infer the presence of `@Aspect` advisors from subclassing.

**Scenario B.** A singleton injects a scoped proxy for a prototype bean. `AopUtils.isAopProxy(scoped)` is `true`, yet the project has no `@Aspect` at all. Is that valid?

**Answer:** Yes. A scoped proxy can use Spring AOP machinery to route each call to the right scoped target; no user-declared `@Aspect` advice is required.

**Scenario C.** A service has `@Transactional`, no custom `@Aspect`, yet `AopUtils.isAopProxy(service) == true`. Why?

**Answer:** Transaction management in proxy mode automatically registers an infrastructure advisor/interceptor to coordinate transactions. Spring AOP is not limited to user-written `@Aspect`s.

**Scenario D.** An `@Bean` returns a bean from `java.lang.reflect.Proxy.newProxyInstance(...)`. `Proxy.isProxyClass(...)` returns `true`, while `AopUtils.isAopProxy(...)` returns `false`. Is Spring AOP broken?

**Answer:** No. This is a plain JDK dynamic proxy without the Spring AOP marker; Spring managing a bean does not mean Spring created or added an AOP proxy for it.

**Scenario E.** `PaymentService`'s AOP proxy has a transaction advisor and an `@Aspect` advisor. Calling `pay()` from outside runs both; `this.refund()` inside the target does not trigger `refund()`'s own advice. Explain?

**Answer:** Two advisors can be attached together on the proxy, yet self-invocation via `this` does not re-enter the proxy. This is a limit of **proxy-based interception**, independent of whether the advisor comes from `@Transactional` or `@Aspect`.

## 13. Official Spring Sources

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB AOP proxies and self-invocation limits.
- [Spring Framework — Bean Scopes / Scoped Proxies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): scoped proxies, proxying targets by request/session/prototype.
- [Spring Framework — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): CGLIB enhancement and `proxyBeanMethods`.
- [Spring Framework — Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor using Spring AOP.
- [Spring Framework — Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): cache annotation proxy mode.
- [Spring Framework — AopUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): `isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, `getTargetClass`.
- [Spring Framework — Advised API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/Advised.html): advisors/target source observable on a Spring AOP proxy.
