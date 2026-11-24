# Lifecycle of an Aspect vs. Lifecycle of a Target Bean in Spring AOP

## 1. Core Question

In Spring AOP, both the **aspect** and the **target bean** can be managed by the Spring IoC container, yet they **do not inherently share the same scope, the same number of instances, or the same creation/destruction timing**.

A default `@Aspect` is normally **one Spring singleton per `ApplicationContext`**, while that same aspect can apply advice to many target beans: singletons, prototypes, or appropriately configured web-scoped beans. Conversely, target bean lifecycle methods are not necessarily calls passing through an AOP proxy, so advice does not automatically run merely because Spring is initializing or destroying a bean.

Understanding these two independent lifecycles helps answer practical questions:

- When does Spring create the aspect instance, and does it recreate the aspect every time a service is called?
- How are singleton and prototype beans proxied? What do two `getBean()` calls return?
- Why does `@Before` not run when a target calls a method on itself inside `@PostConstruct` or `afterPropertiesSet()`?
- Who calls `@PreDestroy`/`destroy()`, and what happens when the `ApplicationContext` closes?
- How do you avoid storing per-request or per-call state in a shared singleton aspect?

This lesson focuses on **the lifecycle of aspects used by Spring for Spring AOP** and their relationship with **proxied Spring beans**. Standalone AspectJ models outside Spring are only mentioned when needed to clarify mechanisms.

## 2. Distinguishing Three Objects in a Spring AOP Call

When Spring applies advice to a target bean via a proxy mechanism, we must distinguish:

| Component | Role | Relationship to lifecycle |
| --- | --- | --- |
| **Aspect bean** | Object containing `@Aspect` and advice such as `@Before`, `@Around`. | Usually singleton per context; has lifecycle callbacks like other Spring beans. |
| **Target bean** | Object containing business logic, e.g., `OrderService`. | Scope and lifecycle depend on bean definition: singleton, prototype, request, session... |
| **AOP proxy** | Representative object Spring can hand to callers instead of the raw target, to apply advisors/advice when methods match. | Usually created during bean post-processing; lifecycle/reusability depends on how the target and target source are configured. |

Simple call model:

```text
Spring ApplicationContext
  |
  +-- TraceAspect bean (typically 1 instance / context)
  |      └── advice / pointcut
  |
  +-- OrderService bean definition (e.g., singleton)
  |      └── raw target -> Spring AOP proxy -> caller
  |
  +-- InvoiceService bean definition (e.g., prototype)
         ├── getBean call #1: target A -> proxy A
         └── getBean call #2: target B -> proxy B

caller -> appropriate proxy -> aspect advice -> target.method()
```

This diagram describes a **typical proxy configuration**. With a scoped proxy or custom `TargetSource`, a single shared proxy may point to different targets across calls; one must not generalize that every proxy always holds a single fixed target.

**Core idea:** one singleton aspect can still run the same advice across hundreds of target beans or many calls; **the number of advice executions is not the number of times the aspect is instantiated**.

## 3. Typical Lifecycle of an `@Aspect` Aspect

### 3.1. Spring Must Register the Aspect as a Bean

`@Aspect` tells Spring that the class carries aspect declarations, yet this annotation alone does not automatically create a Spring bean. There are two common ways:

```java
@Aspect
@Component
public class AuditAspect {
    // Advice...
}
```

Or:

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

In the second configuration, the `AuditAspect` class must still have `@Aspect`, and the `@Bean` method registers it with the container. These examples only illustrate declaration syntax, not standalone Java files.

In plain Spring Framework, `@EnableAspectJAutoProxy` or XML `<aop:aspectj-autoproxy/>` is typically enabled. Spring Boot can auto-configure Spring AOP when the appropriate starter/conditions are present. If the aspect is not a bean or the proxy infrastructure is not enabled, having both the target and advice exist in source code is insufficient to guarantee advice execution.

### 3.2. What Does a Singleton Aspect Mean?

By default, Spring beans have `singleton` scope. With a regular `@Aspect` using the singleton model, there is **one aspect instance per bean definition within the same context**, not one instance per service bean, per thread, or per request.

For example, `AuditAspect` is created once and holds an `AtomicInteger` counting calls; when there are 1,000 calls through the proxy, the counter increments 1,000 times, while `AuditAspect`'s constructor does not run 1,000 times.

Distinctions to make:

- **Singleton per Spring context**, not JVM-wide singleton. Two independent `ApplicationContext`s can have two corresponding aspect instances.
- If **two different beans** of the same `@Aspect` class are registered, there can be two aspect instances and two sets of advisors; those are two bean definitions, not Spring cloning the aspect on each call.
- Scope does not automatically guarantee thread safety: a singleton aspect can be called concurrently by multiple threads. Fields holding state must be designed as thread-safe shared state or removed.

### 3.3. Aspect Lifecycle Callbacks Are Still Spring Bean Callbacks

Because an aspect is a Spring bean, it can participate in common lifecycle mechanisms:

- Instance creation and dependency injection.
- Initialization callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or `initMethod` when configured.
- Used by Spring to build advisors applied to matching targets.
- Destruction callbacks `@PreDestroy`, `DisposableBean.destroy()`, or `destroyMethod` when the scope/context falls under Spring's destruction management.

**There is no rule guaranteeing that an aspect's constructor always runs before every target bean's constructor.** Initialization order depends on the dependency graph, lazy initialization, proxy/advisor discovery, and how the context is created. When order truly matters, establish explicit dependencies and test; do not rely on incidental order observed in logs.

### 3.4. Aspects Are Normally Not Proxied by Spring AOP Itself

Spring Framework excludes classes annotated with `@Aspect` from the set of targets to be auto-proxied by Spring's own `@AspectJ` mechanism. Do not design a system assuming advice from aspect A will automatically intercept internal methods on aspect B via Spring AOP. Shared responsibilities should be attached to **proxied business beans**, not to lifecycle callbacks or aspect classes as default targets.

## 4. Target Bean Lifecycle and Where the AOP Proxy Appears

In a typical Spring container flow, the high-level diagram for a singleton bean with Spring AOP applied is:

```text
Read bean definition / register auto-proxy infrastructure
            |
            v
Create raw target instance
            |
            v
Inject dependencies and invoke pre-initialization callbacks
            |
            v
Invoke @PostConstruct / afterPropertiesSet / init method if present
            |
            v
Post-initialization BeanPostProcessor
(may return a Spring AOP proxy for an eligible bean)
            |
            v
Provide the completed bean/proxy to the caller
            |
            v
Caller invokes method through proxy -> advice may run
            |
            v
When scope/context ends: Spring invokes cleanup callbacks
according to the corresponding scope lifecycle
```

This is **the general order of the standard process**, not a guarantee that every extension behaves identically; proxies may also be created early in special situations such as circular references. What matters for this lesson is:

**Initialization callbacks are invoked on the raw bean before a normal AOP proxy is applied.** Therefore, if a target calls an advised method from `@PostConstruct`/`afterPropertiesSet()`, that internal call does not pass through the Spring AOP proxy.

Illustrative example:

```java
public class OrderService implements org.springframework.beans.factory.InitializingBean {
    @Override
    public void afterPropertiesSet() {
        placeOrder(); // Directly invoked on the raw target (this).
    }

    public void placeOrder() {
        // Business logic.
    }
}
```

If a pointcut matches `placeOrder()`, Spring does not automatically apply advice to the call inside `afterPropertiesSet()` the way it does for `context.getBean(OrderService.class).placeOrder()` after the proxy has been provided. Similarly, `this.placeOrder()` inside another method of the target is **self-invocation**, which does not go back through the proxy.

**Distinction:** `@Before` and `@After` are advice for a **method execution through a proxy**, not a pair of Spring lifecycle callbacks like `@PostConstruct`/`@PreDestroy`.

## 5. How Does Target Bean Scope Affect Proxy Creation?

| Target scope | Target creation | Typical observation when retrieving bean via Spring | Container destruction |
| --- | --- | --- | --- |
| `singleton` (default) | One target per bean definition in a context; usually eager at context refresh, unless lazy or other conditions apply. | Repeated `getBean()` calls with the same name usually return the same Spring bean reference (proxy if applicable). | Spring invokes destruction callbacks when closing the context, barring configuration/lifecycle exceptions. |
| `prototype` | Creates a new target each time the container resolves a request for that bean. | When using standard AOP auto-proxying, each retrieval of a prototype bean is processed to create a proxy for the new target. | **Does not automatically call destruction callbacks** when the context closes; the client must release resources manually if needed. |
| `request`/`session` in web apps | Created in request/session scope according to web-aware context mechanisms. | A scoped proxy can be injected so a longer-lived dependency always accesses the current target for the active scope. | Cleanup depends on scope and request/session termination mechanisms. |
| Custom scope/`TargetSource` | According to specific configuration logic. | A single proxy can forward to targets that change per lookup/call. | Must verify the specific scope/target source contract. |

The relationship between **aspect scope** and **target scope** is determined independently. In particular, `@Scope("prototype")` on a target **does not turn a singleton aspect into a prototype**.

### 5.1. Prototype Targets Are Created Repeatedly Yet Can Still Share the Same Singleton Aspect

Example: target `ReportService` has prototype scope. Two calls to `context.getBean(ReportService.class)` return two separate bean instances, each of which can be wrapped by Spring in a proxy; a single shared singleton `@Aspect` still applies advice to both.

Conversely, if a singleton bean is injected directly with a prototype dependency at initialization time, it normally **retains that exact prototype instance it received**. It does not automatically receive a new prototype on every call. To look up a fresh target repeatedly, `ObjectProvider`, method injection, or a properly configured scoped proxy can be used.

### 5.2. Scoped Proxies Differ from Advice AOP Proxies

A request/session/prototype bean can be given a scoped proxy to be injected into a longer-lived bean. The scoped proxy decides **which current target to select**; the AOP proxy/advisor decides **which calls run advice**. Both proxy types can coexist in a configuration, even forming multiple proxy layers when appropriate.

Therefore, seeing `AopUtils.isAopProxy(bean) == true` is not enough to conclude that the proxy already contains the advice you expect. You must check advisors and test invoking a method whose pointcut matches.

## 6. Complete Example: One Singleton Aspect, Two Target Scopes

This example uses **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, and Maven** to keep dependencies explicit. No Spring Boot or web server is needed.

We intentionally have `SingletonService.afterPropertiesSet()` call `run()` on the raw bean: **this is a business call that does not go through the AOP proxy**. After the container starts, the application retrieves the beans via the context and calls `run()` externally for comparison.

### 6.1. Project Structure

```text
spring-aop-lifecycle/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── AppConfig.java
    ├── TraceAspect.java
    ├── SingletonService.java
    ├── PrototypeService.java
    └── DemoApp.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the container and pulls in foundational Spring modules, including Spring AOP via the dependency tree matching the template; `aspectjweaver` provides the support needed for Spring to process `@Aspect`/pointcuts. This is still **Spring proxy AOP**.

### 6.3. `src/main/java/com/example/lifecycle/TraceAspect.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

@Aspect
public class TraceAspect implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();

    private final AtomicInteger adviceCalls = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
    }

    @Before("execution(public void com.example.lifecycle.*Service.run())")
    public void beforeRun() {
        adviceCalls.incrementAndGet();
    }

    public int calls() {
        return adviceCalls.get();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

`TraceAspect` has an instance counter to count advice executions, and `static` counters to observe initialization/destruction callbacks. The `static` counters only serve this single-run JVM example; production code should not use static fields as a mechanism to track business lifecycle.

`AtomicInteger` allows the counter to increment safely across multiple threads; using a singleton aspect by itself does not guarantee every type of mutable field is thread-safe.

### 6.4. `src/main/java/com/example/lifecycle/SingletonService.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class SingletonService implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();
    private static final AtomicInteger runs = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
        run(); // Directly invoked on the raw bean before the proxy is published.
    }

    public void run() {
        runs.incrementAndGet();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    public static int runCount() {
        return runs.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

`SingletonService` has exactly one call to `run()` **inside the initialization callback** and will receive another `run()` call from the main program through the proxy.

### 6.5. `src/main/java/com/example/lifecycle/PrototypeService.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class PrototypeService implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();
    private static final AtomicInteger runs = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
    }

    public void run() {
        runs.incrementAndGet();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    public static int runCount() {
        return runs.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

This class has `destroy()` to demonstrate that **Spring does not automatically call the destruction callback of a prototype bean when closing the context**, even though it ran the initialization callback each time a prototype was created.

### 6.6. `src/main/java/com/example/lifecycle/AppConfig.java`

```java
package com.example.lifecycle;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public SingletonService singletonService() {
        return new SingletonService();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public PrototypeService prototypeService() {
        return new PrototypeService();
    }
}
```

`@Bean` defaults to singleton, applying to `TraceAspect` and `SingletonService`. `PrototypeService` is marked prototype so each lookup from the container creates a new target. `@EnableAspectJAutoProxy(proxyTargetClass = true)` requests class-based proxies so interface-less services can be retrieved by their concrete class type.

### 6.7. `src/main/java/com/example/lifecycle/DemoApp.java`

```java
package com.example.lifecycle;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class);
        try {
            TraceAspect aspect = context.getBean(TraceAspect.class);

            SingletonService singletonA = context.getBean(SingletonService.class);
            SingletonService singletonB = context.getBean(SingletonService.class);
            PrototypeService prototypeA = context.getBean(PrototypeService.class);
            PrototypeService prototypeB = context.getBean(PrototypeService.class);

            System.out.println("singleton same=" + (singletonA == singletonB));
            System.out.println("prototype same=" + (prototypeA == prototypeB));
            System.out.println("singleton proxy=" + AopUtils.isAopProxy(singletonA));
            System.out.println("prototype proxy=" + AopUtils.isAopProxy(prototypeA));
            System.out.println("initialized: aspect=" + TraceAspect.initCount()
                    + ", singleton=" + SingletonService.initCount()
                    + ", prototype=" + PrototypeService.initCount());
            System.out.println("before external: singletonRuns="
                    + SingletonService.runCount() + ", adviceCalls=" + aspect.calls());

            singletonA.run();
            prototypeA.run();
            prototypeB.run();

            System.out.println("after external: singletonRuns="
                    + SingletonService.runCount()
                    + ", prototypeRuns=" + PrototypeService.runCount()
                    + ", adviceCalls=" + aspect.calls());
        } finally {
            context.close();
        }

        System.out.println("after close: aspectDestroyed=" + TraceAspect.destroyCount()
                + ", singletonDestroyed=" + SingletonService.destroyCount()
                + ", prototypeDestroyed=" + PrototypeService.destroyCount());
    }
}
```

Run in the directory containing `pom.xml` with Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.lifecycle.DemoApp
```

The lines printed by **the program**, in exact order (excluding Maven/Spring logs if the environment enables logging):

```text
singleton same=true
prototype same=false
singleton proxy=true
prototype proxy=true
initialized: aspect=1, singleton=1, prototype=2
before external: singletonRuns=1, adviceCalls=0
after external: singletonRuns=2, prototypeRuns=2, adviceCalls=3
after close: aspectDestroyed=1, singletonDestroyed=1, prototypeDestroyed=0
```

**Output explanation:**

1. Two retrievals of `SingletonService` return the same bean/proxy reference, while two retrievals of `PrototypeService` return two different references.
2. Both the singleton target and prototype targets match the pointcut `execution(public void ...*Service.run())`, so Spring processes them into AOP proxies.
3. One `TraceAspect` is initialized, one singleton service, and two prototype services. `TraceAspect` **is not cloned** to match the number of prototype instances.
4. Inside `SingletonService.afterPropertiesSet()`, `run()` ran once on the raw bean while advice remained 0. When the external caller invoked through proxies three times (`singletonA`, `prototypeA`, `prototypeB`), advice incremented by exactly 3.
5. After `context.close()`, Spring destroys the singleton aspect and singleton target. The two prototype targets that were created and initialized still have **no** automatic `destroy()` call from the container; the example does not manually release them so the difference can be observed.

This is an experiment on Spring container lifecycle and Spring AOP proxies. Do not interpret the result as “every method inside a constructor or `@PostConstruct` is always skipped because the pointcut didn't match”: the real issue is **not going through the proxy** at that moment.

## 7. Are `@PostConstruct` and `@PreDestroy` Advice?

**No.** These two lifecycle callback annotations manage **a bean's life cycle**, whereas Spring AOP advice manages **method executions through a proxy**.

| Situation | Who triggers it? | Does it automatically run `@Before`/ `@Around`? |
| --- | --- | --- |
| `@PostConstruct` on target bean | Spring during raw bean initialization | No; the callback runs before normal proxying is applied. |
| `InitializingBean.afterPropertiesSet()` | Spring during the init phase | No; same reason. |
| Caller uses bean injected from context and calls a method matching the pointcut | Caller goes through the AOP proxy | Yes, if proxy/advisor and call site are valid. |
| `this.someMethod()` from a method on the target | Raw target calls itself internally | Does not go through the proxy, usually does not trigger advice for the internal call. |
| `@PreDestroy`/`DisposableBean.destroy()` | Container during cleanup of managed-destruction beans | Not treated as an advised call by default; do not use advice to replace destruction callbacks. |
| Method on an object manually created with `new` outside Spring | Application code | No Spring AOP proxy to apply. |

A `@PostConstruct` callback wanting to run business logic after proxies are ready is usually a sign that the trigger point needs redesigning: you can move the work to another bean, use `ApplicationRunner` in Spring Boot, or use an appropriate post-context-refresh callback/event. Do not assume that calling an advised method from a constructor or initialization callback will trigger advice.

**Important with `@Transactional`:** Spring's transaction interceptor is also normally proxy-based. If a `@Transactional` method is called from the target itself inside `@PostConstruct`, the transaction proxy has no opportunity to intercept the call. This is a common lifecycle/proxy mistake, not an annotation syntax error.

## 8. Advanced Aspect Instantiation Models in Spring

### 8.1. Singleton Is the Default, but Not the Only Model

Spring Framework documentation on `@AspectJ` lists **aspect instantiation models** such as:

- **Singleton:** one default aspect instance in the application context.
- **`perthis(...)`:** conceptually one aspect instance associated with each matching `this` proxy object at the selected join point.
- **`pertarget(...)`:** aspect instance associated with each matching target object.
- **`pertypewithin(...)`:** listed in documentation of recent Spring versions, but actual support must be verified against the Framework line your application uses.
- **`percflow` and `percflowbelow`:** not supported by Spring proxy AOP according to current documentation.

These non-singleton models are **rules for creating aspect instances**, distinct from `@Scope("prototype")` of a **target bean**. They are not enabled just because a target is prototype, and cannot be inferred simply from the number of `getBean()` calls on the target.

Illustrative declaration example:

```java
@Aspect("perthis(execution(* com.example..service.*.*(..)))")
public class PerProxyUsageAspect {
    private int callsForAssociatedProxy;

    @Before("execution(* com.example..service.*.*(..))")
    public void record() {
        callsForAssociatedProxy++;
    }
}
```

This is **an illustrative class fragment**, requiring imports, bean registration, and a scope configuration compatible with the aspect instantiation style (normally a prototype-scoped aspect bean for the appropriate per-clause model), not a standalone program. Avoid using `perthis` or `pertarget` merely to count general metrics: complexity and lifecycle are harder to control than with a stateless singleton.

Spring AOP only intercepts **method executions on Spring beans via proxies**. Even when using `perthis`/`pertarget`, it does not turn into AspectJ compile-time weaving, and does not automatically fix self-invocation limitations or objects outside the container.

### 8.2. Do Not Confuse `@Scope("prototype")` on an Aspect with `perthis`/`pertarget`

`@Scope` is metadata for a Spring bean definition; `perthis`/`pertarget` are instantiation rules of `@Aspect`. For basic needs, **keeping the aspect singleton and free of per-request mutable state** is the easier choice to control. If a per-object aspect is needed, select a model supported by your Spring version and ensure the bean definition is compatible.

Additionally, Spring schema-based AOP via XML `<aop:aspect>` only supports the **singleton instantiation model** per the documentation, so do not mechanically convert a `perthis` aspect into schema configuration expecting the same lifecycle.

## 9. Designing State in Singleton Aspects: Avoiding Data-Sharing Bugs

A singleton aspect can be called concurrently from many requests/threads. An error-prone example:

```java
@Aspect
public class UnsafeDurationAspect {
    private long startedAtNanos;

    @Before("execution(* com.example..service.*.*(..))")
    public void before() {
        startedAtNanos = System.nanoTime();
    }

    @After("execution(* com.example..service.*.*(..))")
    public void after() {
        System.out.println(System.nanoTime() - startedAtNanos);
    }
}
```

This is an **anti-pattern example**, not a standalone runnable class. If thread A and thread B call simultaneously, the `startedAtNanos` field gets overwritten, producing wrong measurements. Even adding `volatile` only addresses value visibility, not making that state private to each call.

A better approach is using a local variable inside an `@Around` advice:

```java
@Around("execution(* com.example..service.*.*(..))")
public Object measure(org.aspectj.lang.ProceedingJoinPoint pjp) throws Throwable {
    long startedAtNanos = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - startedAtNanos;
        // Send elapsedNanos to a thread-safe metric recorder.
    }
}
```

This is also a **method fragment** inside an aspect with `import org.aspectj.lang.annotation.Around`. `finally` measures even when the method throws an exception; `proceed()` forwards the call to the target. The `startedAtNanos` variable is local to the invocation and therefore not shared across threads.

For aggregate counters, `AtomicInteger`/`LongAdder` or an appropriate metric registry can be used; for request-bound state, use request-scoped contexts or tracing contexts per the application architecture rather than keeping it in mutable instance fields of a singleton aspect.

## 10. Observing Lifecycles Properly When Testing Spring AOP

A test supporting this lesson should verify both **instance relationships** and **advice behavior**, rather than just printing constructor logs:

1. **Context and scope:** check `getBean()` twice for singleton/prototype; for web scopes, set up the corresponding request/session test context.
2. **Proxy:** check `AopUtils.isAopProxy(bean)` and applied advisors/pointcuts, rather than concluding solely from class names containing `$$SpringCGLIB$$`.
3. **Lifecycle callbacks:** count `afterPropertiesSet()`, `@PostConstruct`, `destroy()` depending on scope and close timing.
4. **Call path:** call the method externally through the proxy, then compare with internal calls from the target/initialization phase.
5. **Aspect instances:** measure the number of aspect beans in the context and the number of advice executions; the two numbers are independent.
6. **Context scope:** test parent/child contexts if present to avoid confusing per-context singletons with JVM-wide singletons.
7. **Thread safety:** if advice stores state, test under concurrent load and errors/exceptions, not just a single sequential call.

You can use `context.getBeanNamesForType(MyAspect.class)` to inspect aspect beans, `AopUtils.isAopProxy(target)` to recognize proxies, and `Advised.getAdvisors()` when needing to inspect the advisor chain. These are complementary checks: **a bean being proxied** does not mean **every method is advised**, and **one aspect bean** does not mean advice runs only once.

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible cause | Check/fix direction |
| --- | --- | --- |
| Advice does not run from `@PostConstruct` | Target is running init before proxy is finalized, or internal call on `this`. | Route calls needing interception through the bean/proxy externally after initialization; do not try to patch by re-enabling AOP. |
| Advice runs many times even though aspect initialized once | Singleton aspect is shared and advice runs for each matching call — normal behavior. | Distinguish instance count from invocation count; only flag an error if it exceeds expected calls. |
| Two instances of the same aspect class exist | Duplicate aspect registration via `@Component`, `@Bean`, XML, or multiple contexts. | Count bean names/contexts and unify the registration site. |
| `prototype` target is retained long-term inside singleton client | Prototype was injected once when the singleton client initialized. | Use `ObjectProvider`, method injection, or an appropriate scoped proxy. |
| Prototype has `destroy()` but it does not run on context close | Container does not automatically manage prototype destruction after handing it to the client. | Client manages cleanup/resources; if needed, invoke the corresponding release routine. |
| Request/session scope does not work outside web context | Web scope not registered/no active request. | Use a web-aware context, proper request/session test setup, and scoped proxy. |
| Singleton aspect has scrambled timing measurements | Shared mutable field across concurrent calls. | Use local variables in `@Around`, thread-safe metric collectors. |
| Aspect is created earlier than expected | Spring needs to initialize advisors/aspects, has dependencies, or eager bean creation. | Check `@Lazy`, bean graph, and AOP infrastructure; do not assume callback order from source order. |
| `@PreDestroy` not observed on object outside Spring | Object is not container-managed or does not belong to a destruction-managed scope. | Distinguish `new` from `context.getBean()` and ensure context is closed when needed. |
| `@Aspect` is present but no advice runs | Aspect is not a bean, auto-proxy not enabled, pointcut does not match, or caller bypasses proxy. | Check bean registration, enablement, proxy, pointcut, and call path in order. |

## 12. Design Conclusions in Spring AOP

For most Spring services, the most maintainable design is:

- **Stateless or minimal-state aspect, singleton by default**, containing only shared technical policies.
- **Target beans choose scope by business responsibility** (singleton for most stateless services; prototype or web scope when clearly needed).
- **Advice intercepts calls through Spring proxies** after the bean is put into use, not replacing init/destroy callbacks with advice.
- **Clean up resources according to the target scope's lifecycle**, especially not expecting the container to destroy prototypes automatically.
- **When needing to change the aspect instantiation model**, cross-check the exact Spring version, `@AspectJ` model, and bean definition type.

### Official References for Cross-Checking

- Spring Framework — Aspect Instantiation Models: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html

**A single singleton aspect can accompany many target beans and many calls; what determines whether advice runs is whether the call passes through an appropriate Spring proxy.** Spring bean lifecycles and AOP invocation lifecycles are related, yet must be observed and tested as two distinct mechanisms.
