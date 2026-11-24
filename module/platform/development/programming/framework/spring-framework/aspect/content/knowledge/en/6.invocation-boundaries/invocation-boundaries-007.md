# Unmanaged objects and the limits of automatic proxying in Spring AOP

## 1. The most important boundary: Spring AOP only auto-wraps Spring beans

Spring AOP works primarily by **creating proxies for Spring beans that have matching advisors**. `@EnableAspectJAutoProxy` turns on the mechanism that discovers aspects/advisors and wraps beans inside the `ApplicationContext`; it does not register a global interceptor for every Java call.

The exact same class, method, and pointcut expression produce different outcomes when references originate differently:

- **Reference obtained from the Spring container:** if the bean was processed by the container and has matching advisors, callers receive a Spring AOP proxy; calls through this reference can trigger advice.
- **Reference created with `new` outside the container:** the object did not go through the context's `BeanPostProcessor`/auto-proxy creator pipeline. Calling methods on that reference is an ordinary Java call and does not automatically trigger Spring AOP advice.
- **An instance created with `new` yet returned from `@Bean`:** this is still a Spring bean once the container registers and processes the factory method's return value; it **can be proxied**. Container ownership of the instance, not the `new` keyword by itself, defines the boundary.
- **Holding a direct reference to the target alongside the Spring proxy:** calling through the raw target reference can still bypass advice; calls must go through the **proxy** returned by Spring.

Key takeaway:

> **A pointcut matching a class/method name is only the advisor selection condition; Spring AOP also requires a Spring-managed bean and a call passing through the proxy.**

This lesson covers only Spring AOP and auto-proxying limits. AspectJ compile-time/load-time weaving is a separate mechanism and does not activate merely by adding `@Aspect` or the `aspectjweaver` library.

## 2. At what stage does Spring create proxies?

When `@EnableAspectJAutoProxy` is used, Spring registers an auto-proxy creator, typically `AnnotationAwareAspectJAutoProxyCreator`. This component extends the `AbstractAutoProxyCreator` infrastructure, which hooks into `BeanPostProcessor` callbacks during the bean creation lifecycle.

High-level flow:

~~~text
             ApplicationContext
                     |
           create/receive bean instance
                     |
          pass through BeanPostProcessors
                     |
          any matching advisor?
                  /       \
                No        Yes
                 |         |
              target     create proxy
                 |         |
                 +----+----+
                      |
            container supplies reference
                      |
          caller invokes method via reference
                      |
                [if it is a proxy]
                      |
                 advice chain
                      |
                target.method()
~~~

Compare with a call outside the container:

~~~text
new Notifier("manual") --> raw Notifier object --> send()
                                                  |
                                                  v
                                               target code

ApplicationContext.getBean(Notifier.class)
          |
          v
      Spring AOP proxy --> @Before advice --> target.send()
~~~

The auto-proxy creator is a component **of the Spring container**, not a hook installed into every JVM class. When a developer manually calls `new Notifier(...)` inside an ordinary method, Spring has no idea that object should be processed as a new bean. Having annotations or pointcuts mention `Notifier` does not turn a manually instantiated object into a Spring bean.

Distinguish two moments:

1. **Bean creation:** Spring inspects advisors and may issue a proxy in place of the target. This is the auto-proxying infrastructure's job.
2. **Method invocation:** when callers invoke through the proxy, interceptors/advice run before/after/around the target according to matched advisors. Unproxied objects do not gain an interceptor chain on their own.

Being a Spring bean does not guarantee a proxy either: an applicable advisor must exist, the bean must be eligible for processing, and the method must be interceptable by that proxy type.

## 3. Common scenarios

| How the object is obtained | Is it a container-processed Spring bean? | Does Spring AOP apply automatically? |
| --- | --- | --- |
| `context.getBean("notifier")` or constructor-injected bean | Yes, if the bean definition exists in that context | Potentially; requires a matching advisor and proxy creation |
| `@Component` in a component-scanned package | Yes | Potentially, when advice/proxy conditions match |
| `@Bean Notifier notifier() { return new Notifier(...); }` | Yes; factory method result goes through bean pipeline | Potentially; `new` inside `@Bean` does not exclude AOP |
| `new Notifier(...)` inside a controller/service/helper without registering the instance | No | Not automatically auto-proxied by Spring AOP |
| `new Notifier(...)` in `main` outside `ApplicationContext` | No | Not automatically auto-proxied by Spring AOP |
| Object created internally by a third-party library, not put in container | No, under that usage | Not auto-proxied by `@EnableAspectJAutoProxy` alone |
| Object created by a custom factory and returned to Spring via a bean definition | Yes, if Spring actually manages the factory result | Potentially; inspect lifecycle and advisors |
| Prototype bean created by `context.getBean(...)` each time | Yes; each instance fetched via container | Can be post-processed/proxied as Spring creates each instance |
| Object annotated `@Component` yet instantiated with `new` | Manually created reference bypassing container | No; annotations do not transfer ownership of the instance |
| Bean is proxied yet code retains and calls a direct target reference | Raw target reference outside proxy call path | Does not run advice via the raw target reference |

The table considers **proxy-based Spring AOP**. Explicitly creating proxies with Spring APIs or configuring AspectJ weaving are separate mechanisms, not automatic behavior of `@EnableAspectJAutoProxy`.

## 4. Java 17+ example: same class, only the Spring bean triggers advice

Runnable with plain Spring Framework; no Spring Boot, HTTP server, database, or Java agent needed.

Structure:

~~~text
spring-aop-boundary/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── Notifier.java
    └── TraceAspect.java
~~~

Requires JDK 17+, Maven 3.9+; the project pins Spring Framework 6.2.0 and AspectJ Weaver 1.9.22 for a consistent learning baseline.

### 4.1. Maven dependencies

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-boundary</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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
                <configuration>
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` supplies `ApplicationContext` and Java configuration. `spring-aop` supplies auto-proxy utilities and proxy infrastructure. `aspectjweaver` provides the API/parser for `@AspectJ`-style pointcuts in Spring; having that dependency alone **does not enable weaving**.

### 4.2. Same `Notifier` class for both objects

Create `src/main/java/demo/Notifier.java`:

~~~java
package demo;

public class Notifier {
    private final String label;

    public Notifier(String label) {
        this.label = label;
    }

    public void send() {
        System.out.println("TARGET: " + label);
    }
}
~~~

`Notifier` is non-`final` and `send()` is `public` and overridable, making it straightforward for class-based proxying. `label` simply distinguishes the container-managed object from the manually created one; both invoke the exact `Notifier.send()` method.

### 4.3. Aspect with a counter incremented only inside advice

Create `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before("execution(* demo.Notifier.send(..))")
    public void beforeSend() {
        adviceCount.incrementAndGet();
        System.out.println("ADVICE: before send");
    }

    public int getAdviceCount() {
        return adviceCount.get();
    }
}
~~~

Key points to observe:

- `@Aspect` marks the aspect class with syntax Spring AOP understands, **without registering it as a Spring bean automatically**.
- `@Before("execution(* demo.Notifier.send(..))")` matches execution of `Notifier.send()`. By class/method signature, both instances have the identical signature.
- `beforeSend()` prints `ADVICE` and increments the counter. If the manually created object does not trigger advice, the counter will not increment when it is called.
- `AtomicInteger` makes counting actual advice executions explicit. The example runs sequentially so no separate concurrency setup is needed.

### 4.4. Configuration, calls, and verification

Create `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public Notifier notifier() {
        return new Notifier("managed");
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            Notifier managed = context.getBean(Notifier.class);
            Notifier manual = new Notifier("manual");
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean managedProxy = AopUtils.isAopProxy(managed);
            boolean manualProxy = AopUtils.isAopProxy(manual);

            System.out.println("MANAGED_PROXY: " + managedProxy);
            System.out.println("MANUAL_PROXY: " + manualProxy);

            managed.send();
            manual.send();

            int calls = aspect.getAdviceCount();
            System.out.println("ADVICE_COUNT: " + calls);

            if (!managedProxy || manualProxy || calls != 1) {
                throw new IllegalStateException(
                        "Spring AOP proxy boundary verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Mechanics in the program:

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` registers the auto-proxy creator for the Spring context; class-based proxying fits because `Notifier` implements no interface. This flag **does not** tell Spring to intercept every object constructed with `new`.
2. `@Bean notifier()` **has `new Notifier("managed")` inside**, yet its return value is handed to Spring as a bean. Spring can process it, wrap it in a proxy, and publish the proxy reference to callers; `AopUtils.isAopProxy(managed)` will be `true`.
3. `@Bean traceAspect()` registers the `TraceAspect` instance in the same context so Spring finds the `@Before` advisor.
4. `new Notifier("manual")` inside `main` **never passes through `BeanFactory`**, so `AopUtils.isAopProxy(manual)` is `false`. It has the same class and `send` method, yet no proxy.
5. `managed.send()` enters the proxy, then the advice, then the target. `manual.send()` runs only the class code; it does not pass through a proxy just because the pointcut matches by name.
6. The verification check asserts contrasting proxy states and **only one actual advice execution**. Printing `CHECK: PASS` proves the application observed this boundary accurately.

### 4.5. Running and verifying output

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the Java code above, in order:

~~~text
MANAGED_PROXY: true
MANUAL_PROXY: false
ADVICE: before send
TARGET: managed
TARGET: manual
ADVICE_COUNT: 1
CHECK: PASS
~~~

If Maven/framework logs additional messages outside the program, focus on those seven lines. Why is this the result?

- **`MANAGED_PROXY: true`** proves the Spring-supplied bean was wrapped when an advisor matched.
- **`MANUAL_PROXY: false`** proves a standalone `new`-ed object does not become a Spring proxy.
- **`ADVICE: before send`** precedes `TARGET: managed`, confirming the method was intercepted through the proxy.
- **`TARGET: manual`** appears **without a second `ADVICE` line**, even though the object is of the same `Notifier` class.
- **`ADVICE_COUNT: 1`** is the direct measurement from the aspect bean; had advice executed for `manual`, the count would have increased.
- **`CHECK: PASS`** prints only when both proxy statuses and the advice count match.

The example deliberately uses the same class/method and runs both references side by side to rule out "the method didn't match the pointcut". The difference comes from **object origin and how it is invoked**, not from code inside the target.

## 5. Three situations easily confused when seeing the `new` keyword

### 5.1. `new` inside `@Bean` still creates a Spring-managed bean

~~~java
@Configuration
class ServiceConfig {
    @Bean
    Notifier notifier() {
        return new Notifier("created-in-bean");
    }
}
~~~

This is an **excerpted configuration snippet** (requiring `@Configuration`/`@Bean` imports and `Notifier` as in the example). The Spring container invokes the factory method, receives the instance, runs the bean lifecycle, and can return an AOP proxy. Using `new` to instantiate the object does not make the result an "out-of-container object".

Therefore, do not judge by a simplistic rule like "if `new` appears, Spring AOP doesn't run". Always ask **who owns the instance after creation** and **which reference the caller invokes**.

### 5.2. `new` inside a Spring bean does not automatically register child objects

Illustrative example:

~~~java
public class DispatchService {
    public void dispatch() {
        Notifier temp = new Notifier("inner-manual");
        temp.send();
    }
}
~~~

Even if `DispatchService` is a Spring bean and proxied, `temp` is still just a local object instantiated inside the method. Spring does not treat it as a new bean or attach an AOP proxy to the `temp` reference. Its `send` method receives no Spring AOP advice merely because the enclosing object is a Spring bean.

This snippet uses the `Notifier` class already declared; to run it, `DispatchService` must be registered in the context and `dispatch()` called from an entry point. Do not assume Spring manages the entire object graph created manually by beans.

### 5.3. A raw object registered as a bean while code retains the old reference

Suppose an instance was created manually and later **registered into the container in a way that lets Spring post-process it**. Spring may publish an AOP proxy for that instance while external code still holds a variable pointing directly to the original object:

~~~text
  Object target = new Notifier(...)
          |
          +--> rawTarget variable still points to target
          |
          +--> Spring receives this instance as a bean
                         |
                         +--> auto-proxy creator returns AOP proxy
                                            |
                                      managedReference
~~~

Calling `managedReference.send()` can run advice; calling `rawTarget.send()` still goes straight to the target. The two references **are not identical** merely because they relate to the same target object. To ensure advice runs, prefer fetching/injecting the container-provided reference and do not retain raw targets on business call paths.

Do not assume calling `registerSingleton(...)` on an already running `BeanFactory` undergoes the exact same lifecycle/post-processing as a bean definition registered and instantiated normally; supplying pre-built instances to the container must follow the proper API/lifecycle.

## 6. Limits related to the Spring AOP boundary

### 6.1. Having a bean is not enough; calls must traverse the proxy

Even with an already-proxied Spring-managed bean:

~~~java
public class OrderService {
    public void place() {
        this.confirm();
    }

    public void confirm() {
        System.out.println("confirmed");
    }
}
~~~

If advice targets only `confirm()` and a caller invokes `place()` through the Spring proxy, the internal `this.confirm()` call inside the target **does not go back through the proxy**; advice on `confirm()` may not run. This is **self-invocation**, a different cause from "unmanaged object", though both relate to the call-path boundary.

In Spring AOP, the standard design fix is moving `confirm()` to a separate bean and calling it via a Spring-injected dependency. Do not mistakenly assume switching from JDK proxy to CGLIB or setting `proxyTargetClass = true` makes `this.confirm()` pass through the proxy.

### 6.2. Classes and methods must be compatible with proxying

Spring AOP inspects beans automatically, yet proxies have limits:

- With **JDK dynamic proxies**, only methods exposed on the proxy's interfaces can be called through the proxy as an interface type; never cast the proxy down to the implementation class.
- With **CGLIB class proxies**, `final` classes cannot be subclassed; `final`/`private` methods cannot be overridden for interception by a subclass proxy.
- Calls to **static methods**, constructors, field accesses, or objects not managed by Spring are not automatically intercepted by Spring AOP proxies as Spring bean method executions.
- If a bean has no matching advisor/pointcut, Spring does not force-create a proxy merely because `@EnableAspectJAutoProxy` is enabled.
- If a bean is instantiated too early, outside normal `BeanPostProcessor` processing, it may not be auto-proxied as expected. Diagnose this separately from `new` outside the container.

Common thread: **living in the same JVM as a Spring AOP application does not mean every call traverses a proxy**.

### 6.3. `@Autowired`, `@Transactional`, or `@Cacheable` on manually `new`-ed objects

When code does:

~~~java
public class Processor {
    // Illustrative example; this class is not yet registered as a Spring bean.
    @org.springframework.beans.factory.annotation.Autowired
    private Notifier notifier;

    public void process() {
        notifier.send();
    }
}
~~~

If callers run `new Processor()` manually, Spring's dependency-injection callbacks do not run for that instance. `notifier` may stay `null`, causing a `NullPointerException` when `process()` is called. Similarly, annotations powered by Spring AOP such as `@Transactional`/`@Cacheable` (in proxy mode) do not turn a manually instantiated object into a proxy on their own.

This is an **illustrative dependency-injection snippet**, not a standalone compilable project: it uses `Notifier` from the example and has no `main` method. Distinguish clearly:

- **DI not running on a raw object** is a container ownership issue.
- **Advice not running on a raw object** is a Spring AOP proxy issue.
- **A proxied bean calling its own internal method** is a proxy call-path issue.

These three situations have similar symptoms yet require different fixes.

## 7. Designing so objects are Spring-managed

### 7.1. Registering with `@Component` or `@Bean`

If a service belongs to the application layer and needs Spring AOP, register it in `ApplicationContext`:

~~~java
@Component
public class NotificationService {
    public void send() {
        // application logic
    }
}
~~~

This snippet belongs in `NotificationService.java` with `import org.springframework.stereotype.Component;` and requires component scanning enabled for its package. With `@Bean` configuration, the style in section 4's example is even more explicit because it does not depend on package scanning.

Make sure the aspect is also registered as a bean:

~~~java
@Aspect
@Component
public class MonitoringAspect {
    @Before("execution(* demo.NotificationService.send(..))")
    public void before() {
        System.out.println("advised");
    }
}
~~~

This illustrative snippet needs `org.aspectj.lang.annotation.*` and `org.springframework.stereotype.Component` imports in a project with component scanning; `@Aspect` alone **is not enough** for Spring to scan the class as a bean. Use these snippets only when the application has appropriate AOP and scanning configuration.

### 7.2. Inject services instead of creating them with `new`

Instead of:

~~~java
public class Sender {
    private final Notifier notifier = new Notifier("manual");

    public void doSend() {
        notifier.send();
    }
}
~~~

let Spring inject the managed bean:

~~~java
public class Sender {
    private final Notifier notifier;

    public Sender(Notifier notifier) {
        this.notifier = notifier;
    }

    public void doSend() {
        notifier.send();
    }
}
~~~

These two snippets are **two alternative versions** of a `Sender` class; do not put both into the same project simultaneously. `Sender` must also be declared as a Spring bean (via `@Bean`/`@Component`) so the container performs constructor injection. With a proxied Spring-managed `Notifier`, `Sender`'s dependency is normally the proxy reference; `doSend()` follows the right path for Spring advice to run.

Constructor injection exposes dependencies in the class API, simplifies testing, and prevents forgetting bean registration.

### 7.3. Need a fresh object on every call?

Do not assume you must fall back to `new` just because business logic needs a separate instance each time. Spring provides **prototype scope** and on-demand container retrieval:

~~~java
@Configuration
class NotificationConfig {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Notifier notifier() {
        return new Notifier("prototype");
    }
}
~~~

This configuration snippet is illustrative: it needs imports for `@Configuration`, `@Bean`, `@Scope`, `ConfigurableBeanFactory`, and `Notifier`. Whenever the Spring container creates a prototype bean from this definition, the bean passes through the appropriate processing mechanisms, including auto-proxying if advisors match.

A consumer can inject `ObjectProvider<Notifier>` and call `provider.getObject()` **each time a new instance is needed**. Remember: injecting a prototype directly into a normal singleton resolves only once when the singleton is created; it does not spawn a new prototype on every singleton method call.

### 7.4. When an object must be created by an external library

For a callback object created by another SDK/framework, options depend on lifecycle control:

1. If you control the factory, let Spring manage the factory/result via a bean definition and pass **the proxy reference** to callers, avoiding holding stale raw references.
2. If you cannot replace the external factory yet callers are application-managed, place a **Spring-managed adapter/service** as the Spring AOP entry point and delegate internally to the SDK object. Advice applies at **the adapter's boundary**, without intercepting internal methods inside the SDK object.
3. If you genuinely must advise an unmanaged object directly, **Spring AOP provides programmatic proxy creation APIs** (`AspectJProxyFactory`/`ProxyFactory`) for eligible targets. This is explicit: callers must receive and invoke the resulting proxy; `@EnableAspectJAutoProxy` auto-proxying does not do this automatically for arbitrary raw objects. If requirements exceed proxy limits, evaluate other mechanisms with their own configuration costs.

A Spring adapter is usually the simplest way to keep cross-cutting concerns like logging, auditing, or tracing at the application boundary without taking over a third-party library's internal lifecycle.

## 8. Creating proxies manually for unmanaged objects: limits and API example

Spring Framework also provides `org.springframework.aop.aspectj.annotation.AspectJProxyFactory` to create AOP proxies **explicitly**. An illustrative snippet placed **inside a Java method alongside section 4's `Notifier` and `TraceAspect`**:

~~~java
Notifier raw = new Notifier("external");

org.springframework.aop.aspectj.annotation.AspectJProxyFactory factory =
        new org.springframework.aop.aspectj.annotation.AspectJProxyFactory(raw);

TraceAspect manualAspect = new TraceAspect();
factory.addAspect(manualAspect);

Notifier proxy = factory.getProxy();
proxy.send();

System.out.println(manualAspect.getAdviceCount()); // 1
~~~

This **is not a standalone runnable project**, rather a snippet using additional APIs in a project that already has Spring AOP/AspectJ dependencies. Because `Notifier` has no interface, Spring can create an appropriate class-based proxy for the target in the example. `factory.addAspect(manualAspect)` uses a specific aspect instance; the advice counter is read from **that instance** rather than an aspect bean in `ApplicationContext`.

Differences from auto-proxying:

- The developer **explicitly chooses the target**, **adds the aspect**, and **obtains the proxy** via `factory.getProxy()`.
- Only calls on `proxy` traverse advice; calling `raw.send()` still bypasses the proxy.
- Manual proxying does not register the raw target as a Spring bean or grant container lifecycle/DI.
- When using Spring AOP auto-proxying for regular application services, prefer Spring-managed beans rather than scattering manual proxy creation across the codebase.

## 9. Diagnosing why advice does not run for an instance

Follow this checklist in order:

1. **Determine where the object is created:** `new` inside a controller, factory, SDK, deserializer, callback, or fetched via `context.getBean(...)`? Distinguish `new` **inside a `@Bean` factory** from `new` inside a regular method.
2. **Verify Spring container bean management:** bean name/definition, component scanning, right `ApplicationContext`, and right scope? Both a managed bean and raw objects of the same class may coexist.
3. **Inspect the actual reference being called:** call `AopUtils.isAopProxy(reference)` on the reference at the call site, not just on another instance in the context.
4. **Check proxy type and advisors:** `AopUtils.isJdkDynamicProxy`/`isCglibProxy`, and whether the method-execution pointcut matches. Having a bean does not guarantee advice applies.
5. **Identify the method invocation boundary:** does the caller invoke through the proxy, through a raw target, or `this.method()` on the same target?
6. **Check method limits:** JDK interfaces, CGLIB `final`/`private`, static methods, and constructors are not interceptable method executions like normal business methods.
7. **If DI is also missing:** was the object injected and initialized by Spring, or manually `new`-ed? Do not treat `@Autowired`'s presence as proof the container manages the instance.
8. **If the bean is Spring-managed yet lacks a proxy:** check whether auto-proxy creator is enabled, the aspect is registered as a bean, advisors match, and the bean was not instantiated prematurely before all BPPs ran.
9. **After fixing:** invoke the same method via the Spring-provided reference, confirm advice output/counters or integration tests. Do not check only that the business method returns a normal value.

Diagnostic snippet to drop into an application that already has a `context` variable:

~~~java
Object bean = context.getBean("notifier");

System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(
        org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(
        org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

This snippet is not a standalone Java file; its purpose is inspecting the reference Spring **actually provides**. If code also holds another raw reference and invokes it, checking `bean` tells you nothing about whether raw calls traverse advice.

## 10. Common misconceptions

**"The pointcut names the right package/class/method, so it catches objects created with `new` too."** False for proxy-based Spring AOP. Pointcuts only determine which advisors apply to join points reachable through a proxy; they do not weave interceptors into every instance of the class in the JVM.

**"`@Component` on a class guarantees every `new ThatClass()` is managed."** False. The annotation registers a bean definition when component scanning applies. Separately created instances still do not pass through Spring IoC.

**"Because `@Bean` contains `new`, Spring cannot proxy it."** False. The factory method hands the instance to the container; bean post-processing can wrap it.

**"The parent bean is a proxy, so objects it creates are proxied too."** False. Objects manually instantiated inside a method are separate instances; Spring does not automatically post-process the entire object graph created inside methods.

**"If a Spring bean has a proxy, every method call on it gets advised."** False. Self-invocation, method modifiers, call sites, proxy types, and pointcuts all affect execution. Having a proxy does not make every method an intercepted join point.

**"I called `getBean(...)` once to get the proxy; my old raw reference turns into a proxy automatically."** False. Variables pointing straight to the target do not transform into proxies simply because the container handed a wrapper to someone else.

**"Adding the AspectJ Weaver dependency auto-proxies objects outside Spring."** False. `aspectjweaver` is commonly used so Spring can parse `@AspectJ` syntax; true AspectJ weaving requires separate compiler/weaver setup and a different mechanism.

## 11. Self-check

1. **Two `Notifier` objects of the same class: one fetched from the Spring context, one `new`-ed in `main`. Which one automatically receives advice?**  
   The object processed and exposed by the container through a proxy; the standalone `new`-ed object is not auto-wrapped by Spring AOP.

2. **Why can `return new Notifier(...)` inside a `@Bean` still receive AOP?**  
   Because Spring manages **the return value of the bean factory method**, passing it through BPP/auto-proxying before publishing it.

3. **If a raw object is wrapped in a manual proxy, do all variables pointing to the raw object receive advice?**  
   No. Callers must use the variable pointing to **the proxy**; raw references still invoke the target directly.

4. **Why can `@Autowired` on a field of a manually `new`-ed object stay `null`?**  
   Because Spring never performed dependency injection on that instance.

5. **If two methods on the same Spring bean call each other via `this`, do both run advice?**  
   No. The internal call on the target can bypass the Spring proxy.

6. **When needing multiple advised instances, what is the Spring-native solution?**  
   Register a prototype/factory under Spring and obtain instances from the container (`ObjectProvider` when needed), instead of creating raw objects outside `BeanFactory`.

7. **Does `AspectJProxyFactory` mean `@EnableAspectJAutoProxy` does the same automatically for any raw object?**  
   No. It is an **explicit** proxy-creation API; auto-proxying belongs to the Spring bean lifecycle.

## 12. Official documentation

- [Spring Framework — AOP @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): Spring parses `@AspectJ` syntax while runtime AOP remains proxy-based.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): auto-proxying for Spring beans.
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): aspects must be registered as beans; `@Aspect` alone is not enough.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB limits and self-invocation.
- [Spring Framework — Programmatic Creation of @AspectJ Proxies](https://docs.spring.io/spring-framework/reference/core/aop/aspectj-programmatic.html): `AspectJProxyFactory` API.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): Spring-managed singleton/prototype scopes and requesting scoped instances.