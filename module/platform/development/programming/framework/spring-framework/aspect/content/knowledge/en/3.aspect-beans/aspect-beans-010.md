# Checking Aspect Instance Counts and Shared State in Spring AOP

## 1. Objectives

When an `@Aspect` is registered as a Spring bean, key questions when running the application are:

- How many **aspect beans** of a given class exist in this `ApplicationContext`?
- Do two bean lookups return **the exact same object**?
- Is one aspect bean shared across **multiple target service beans**, multiple calls, or multiple threads?
- Does a mutable field in the aspect cause **data mixing across calls**?
- How do the number of **bean definitions**, the number of **runtime aspect instances**, and the number of **advice executions** differ?

This lesson focuses on **how Spring manages instances of `@Aspect` beans**, how to verify them at runtime, and how to protect state when advice runs across multiple beans/threads. This is specifically about Spring AOP proxies inside `ApplicationContext`; there is no need to review general AOP.

**Conclusion to verify programmatically:** with the common configuration of **one singleton `@Aspect` bean** in a Spring context, multiple target beans whose methods match the pointcut can use **the same aspect instance**. Consequently, a mutable instance field in the aspect is also shared across calls. **One aspect instance does not mean one advice execution, one target, one request, or one thread.**

## 2. Three Different Kinds of “Counts”

| Quantity | Exact meaning in Spring | How to check | What cannot be inferred |
| --- | --- | --- | --- |
| Number of **bean names / bean definitions** of the aspect class in the context | How many beans the context registered for type `MyAspect` | `context.getBeanNamesForType(MyAspect.class)` or `getBeansOfType(MyAspect.class)` in simple singleton cases | Does not directly measure how many times advice runs. With prototype or advanced aspect instantiation models, counting beans also does not reflect total instances created at runtime. |
| Number of shared **object identities** | Whether two references point to the same instance | `first == second`; `System.identityHashCode` can also be observed for debugging only | Does not tell how many proxies/targets or advice executions occurred. |
| Number of **advice invocations** | How many times advice ran at matching join points | Thread-safe counter, recorder, or integration test | Not identical to the number of aspect beans, targets, requests, or successful business transactions. |

**Basic example:** Spring creates one `countingAspect` bean with singleton scope. An `OrderService` and a `PaymentService` receive two different proxies; both have the aspect applied. After three service calls through proxies, the result can be **1 aspect bean, 1 aspect object, 2 target proxies, 3 advice executions**.

```text
ApplicationContext
│
├── countingAspect  ───────────────┐
│   singleton CountingAspect      │ same object, holds AtomicInteger
│                                  │
├── orderService (Spring proxy) ───┼─> advisor -> advice on CountingAspect
│                                  │
└── paymentService (Spring proxy) ─┘

Caller A and caller B invoke through the two proxies:
both can cause advice to mutate the state of countingAspect.
```

The diagram describes a common Spring AOP configuration; it does not imply Spring creates a separate advice instance per proxy.

## 3. Default Scope: One Singleton Aspect Bean per Context

When declaring `@Aspect` as a Spring bean via `@Component` or `@Bean` without specifying another scope, Spring uses **singleton scope** by default.

```java
@Aspect
@Component
public class CountingAspect {
    // A singleton Spring bean in the scanned context
}
```

or:

```java
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
    @Bean
    CountingAspect countingAspect() {
        return new CountingAspect();
    }
}
```

These are **two separate registration approaches**, not applied simultaneously to create duplicate beans. With a singleton bean definition, Spring normally creates one object and reuses it when injecting/looking up that bean in **the same context**. This aspect can contain advice applying to multiple target methods; Spring does not create a separate copy of the aspect just because more proxies exist.

Spring singleton is scoped **per container and per bean definition**, not a JVM-wide or process-wide singleton:

- Two different bean definitions of the same class can create **two instances** in one context; depending on advisors/pointcuts, this can cause advice to run twice.
- Two independent `ApplicationContext`s create two independent singleton beans; each context has its own instance.
- Two application processes or two replicas also do not automatically share Java objects, even if bean names/classes match.
- One context can have many target beans/proxies while the singleton aspect bean remains just one.

**Caution:** Spring supports **aspect instantiation models other than singleton**; therefore, any conclusion that “one aspect bean = one object” in this lesson applies first to the default singleton configuration. Section 8 covers the scope of advanced models.

## 4. Checking Spring Beans Before Checking Advice

In the current `ApplicationContext`, start from the bean registry:

```java
String[] names = context.getBeanNamesForType(CountingAspect.class);
System.out.println(java.util.Arrays.toString(names));

CountingAspect a = context.getBean(CountingAspect.class);
CountingAspect b = context.getBean("countingAspect", CountingAspect.class);
System.out.println(a == b);
```

This is an **illustrative snippet**, assuming the context has exactly one singleton `CountingAspect` bean named `countingAspect`. Then:

```text
[countingAspect]
true
```

How to read this:

1. `getBeanNamesForType` returns the names of beans matching the type according to the Spring container's lookup criteria.
2. `getBean(MyAspect.class)` requires a unique bean by type; if two beans of the same type exist without a suitable disambiguation mechanism, Spring may throw `NoUniqueBeanDefinitionException`.
3. `a == b` checks **exact identity**; for a singleton bean with the same name/definition, the result is true. `a.equals(b)` is unsuitable for concluding object identity because a class can override `equals`.
4. `getBeansOfType(MyAspect.class).size()` is convenient for checking bean counts of common singletons, but may **instantiate non-singleton beans** when queried. With advanced scopes, avoid treating this result as a count of all instances created/stored in the AOP runtime.
5. `System.identityHashCode(bean)` is useful for logs/debugging when tracing objects, though hash codes can collide; when possible, use `==` comparison to confirm two references are the exact same object.

A bean existing **does not mean every target has been proxied**. After the bean-counting step, check separately:

```java
OrderService order = context.getBean(OrderService.class);
boolean proxied = org.springframework.aop.support.AopUtils.isAopProxy(order);
System.out.println(proxied);
```

`isAopProxy` only confirms that the object is an AOP proxy; it does not confirm that **the advice of the aspect in question** matches a specific method. You must invoke the relevant method and observe the advice actually running.

## 5. Runnable Demo: One Aspect, Two Services, Three Calls

The example uses **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, and Gradle with the `application` plugin. This is a plain Spring Framework application to clarify instances and scope, without relying on Spring Boot auto-configuration.

### 5.1. Project Structure

```text
spring-aspect-instance-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/aspectstate/
    ├── AppConfig.java
    ├── Counted.java
    ├── CountingAspect.java
    ├── OrderService.java
    ├── PaymentService.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aspect-instance-demo'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.aspectstate.Main'
}
```

These are pinned versions so the project can be copied as a standalone example; in real Spring Boot projects, let the BOM/dependency management handle compatible Spring/AspectJ versions.

### 5.2. Annotation Selecting Methods to Count

**`Counted.java`**

```java
package com.example.aspectstate;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Counted {
}
```

Selecting by annotation keeps the pointcut focused on intentional methods, avoiding accidentally intercepting infrastructure methods.

### 5.3. Two Different Spring Target Services

**`OrderService.java`**

```java
package com.example.aspectstate;

public class OrderService {
    @Counted
    public String submit(String id) {
        return "order:" + id;
    }
}
```

**`PaymentService.java`**

```java
package com.example.aspectstate;

public class PaymentService {
    @Counted
    public String pay(String id) {
        return "payment:" + id;
    }
}
```

Here, both classes **do not need** `@Service` because they will be registered directly via `@Bean` in Spring configuration. What matters for Spring AOP is that the target is managed by the container and called by the caller through a proxy.

### 5.4. Aspect Holding a Shared Counter

**`CountingAspect.java`**

```java
package com.example.aspectstate;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class CountingAspect {
    private final AtomicInteger invocations = new AtomicInteger();

    @Before("@annotation(com.example.aspectstate.Counted)")
    public void beforeCountedMethod() {
        int number = invocations.incrementAndGet();
        System.out.println("advice#" + number);
    }

    public int getInvocationCount() {
        return invocations.get();
    }
}
```

This is an **intentionally stateful aspect for demonstration**. `AtomicInteger` makes increment/read operations safe when advice is invoked concurrently. It **does not prove all mutable state is safe**, nor does it turn a single-JVM counter into a multi-replica metrics system. In production, invocation-counting metrics are usually better placed into Micrometer/Observation; aspects should avoid accumulating per-request business data.

The `@Aspect` annotation describes the aspect. The class intentionally **does not have `@Component`** to ensure there is only one registration source in `AppConfig`.

### 5.5. Only One Aspect Bean, Two Target Beans

**`AppConfig.java`**

```java
package com.example.aspectstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public CountingAspect countingAspect() {
        return new CountingAspect();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }
}
```

The beans `countingAspect`, `orderService`, and `paymentService` are singletons by default. `@EnableAspectJAutoProxy` detects `CountingAspect` and applies the `@annotation` pointcut to both services. `proxyTargetClass=true` allows target proxies to be accessed by their concrete class type in the example; it does not affect the singleton aspect being shared.

### 5.6. Counting and Comparing the Exact Instance Registered by Spring

**`Main.java`**

```java
package com.example.aspectstate;

import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            String[] names = context.getBeanNamesForType(CountingAspect.class);
            CountingAspect first = context.getBean(CountingAspect.class);
            CountingAspect second =
                    context.getBean("countingAspect", CountingAspect.class);

            OrderService order = context.getBean(OrderService.class);
            PaymentService payment = context.getBean(PaymentService.class);

            System.out.println("aspectBeanNames=" + Arrays.toString(names));
            System.out.println("sameAspectInstance=" + (first == second));
            System.out.println("orderProxy=" + AopUtils.isAopProxy(order));
            System.out.println("paymentProxy=" + AopUtils.isAopProxy(payment));

            System.out.println(order.submit("ORD-1"));
            System.out.println(payment.pay("PAY-1"));
            System.out.println(order.submit("ORD-2"));

            System.out.println("adviceInvocations=" + first.getInvocationCount());
        }
    }
}
```

Run with Gradle installed:

```bash
gradle run --quiet
```

If using the Gradle wrapper, run `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**The program's `System.out` lines in exact order** (excluding other JVM/Spring/Gradle logs if logging is enabled by the environment):

```text
aspectBeanNames=[countingAspect]
sameAspectInstance=true
orderProxy=true
paymentProxy=true
advice#1
order:ORD-1
advice#2
payment:PAY-1
advice#3
order:ORD-2
adviceInvocations=3
```

### 5.7. Reading the Results Correctly

- `aspectBeanNames=[countingAspect]`: one Spring bean is registered under type `CountingAspect`.
- `sameAspectInstance=true`: two bean lookups by type/name indeed return **the same singleton object**.
- `orderProxy=true` and `paymentProxy=true`: Spring creates proxies for **two different targets** because methods on both match the pointcut.
- `advice#1` and `advice#3` belong to the two `OrderService.submit` calls; `advice#2` belongs to the `PaymentService.pay` call.
- `adviceInvocations=3`: the counter inside **the same aspect object** receives all three events. The counter does not reset when switching from target `OrderService` to `PaymentService`.

If the learning goal is “each service has its own counter”, this singleton aspect configuration **does not satisfy it**. Do not confuse target bean scope with aspect instance scope; two different services can still share a counter.

## 6. Verifying Shared State

### 6.1. State Shared Across Targets

From the demo, state after each call:

| Point in time | Target bean called | State of `CountingAspect.invocations` |
| --- | --- | --- |
| Immediately after retrieving beans | Not yet called | 0 |
| After `order.submit("ORD-1")` | `orderService` proxy | 1 |
| After `payment.pay("PAY-1")` | `paymentService` proxy | 2 |
| After `order.submit("ORD-2")` | `orderService` proxy | 3 |

This comes from the **shared singleton aspect**, not because `OrderService` and `PaymentService` share the same target instance. When an application has multiple callers, all callers entering methods matching the pointcut can use the same aspect bean.

### 6.2. State Shared Across Multiple Threads

A singleton aspect is not created separately per thread by Spring. When requests or tasks running on multiple threads concurrently call Spring service beans with advised methods, **they can concurrently access instance fields in the aspect**.

Code snippet **with a race condition bug**, used to recognize the anti-pattern:

```java
@Aspect
public class UnsafeCountingAspect {
    private int total;

    @Before("@annotation(com.example.aspectstate.Counted)")
    public void beforeCall() {
        total++; // non-atomic read-modify-write
    }

    public int count() {
        return total;
    }
}
```

This is an **illustrative snippet**, not replacing `CountingAspect.java` in the runnable demo. With two threads incrementing `total` concurrently, reads/writes can overlap and lose updates; the final value is smaller than the number of advice executions. `volatile int total` still does not make `total++` an atomic operation; `volatile` only provides appropriate visibility/happens-before semantics, and does not automatically protect a read-modify-write sequence.

Version for **an independent counter** like the `AtomicInteger` example:

```java
private final AtomicInteger invocations = new AtomicInteger();

@Before("@annotation(com.example.aspectstate.Counted)")
public void beforeCountedMethod() {
    invocations.incrementAndGet();
}
```

`AtomicInteger` is suitable when you truly want to count total invocations **in one aspect instance**, but does not protect a set of multiple fields that must be updated together. For example, “write `currentUser` and `currentOrder` and then read both in advice” cannot be fixed merely by making one field atomic.

### 6.3. Request Data Mixing Bug in a Singleton Aspect

Dangerous example:

```java
@Aspect
@Component
public class UnsafeAuditAspect {
    private String currentOrderId;

    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        currentOrderId = id;
        // Another thread can overwrite currentOrderId right after the assignment.
    }
}
```

This is a **standalone illustrative snippet**, assuming the target method has a `String id` parameter and component scan is enabled. The interleaving order can be:

```text
Thread A: record("ORD-A") -> currentOrderId = "ORD-A"
Thread B: record("ORD-B") -> currentOrderId = "ORD-B"
Thread A: reads currentOrderId -> sees "ORD-B" (wrong request)
```

The bug **does not originate from `@Aspect`**, but from storing request state in a Spring singleton object shared by multiple threads.

Replace with parameters/local variables of the advice itself:

```java
@Aspect
@Component
public class SafeAuditAspect {
    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        String orderId = id; // Value local to each invocation
        System.out.println("audit:" + orderId);
    }
}
```

The two classes `UnsafeAuditAspect`/`SafeAuditAspect` are only explanatory alternatives. Do not add both to the demo project because that would add extra advisors/logs to calls. For production, strip sensitive information from logs and delegate audit work to an appropriate service/repository/sink if persistence, retry, transaction, or security requirements exist.

### 6.4. Data Needed per Request: Do Not Move It to Aspect Fields

A singleton aspect can inject a **safe service** to process request data, but must not store request data in mutable fields of its own:

```java
@Aspect
@Component
public class AuditAspect {
    private final AuditWriter writer;

    public AuditAspect(AuditWriter writer) {
        this.writer = writer;
    }

    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        writer.write(id); // id is the parameter of the current call
    }
}
```

This is an **illustrative snippet**, requiring an `AuditWriter` Spring bean defined by the application. Having `writer` as `final` only ensures the dependency reference cannot be reassigned; `AuditWriter` itself must still be designed to be appropriately thread-safe. If using a request-scoped bean/proxy or security data context, understand request scope and context propagation under async execution; do not assume it works in every thread or non-web execution.

Sometimes `ThreadLocal` is used for per-thread context, but it must be properly cleared in `finally` and does not propagate automatically across `@Async`/task executors. The safest and easiest-to-test approach is passing data via method/advice parameters or the framework's own context/observation tools.

## 7. A Repeatable Concurrent Test

To avoid the claim “a singleton probably only runs on one thread”, we can perform an additional test **calling the same service proxy from multiple threads**. Using the exact `AppConfig`/`CountingAspect` of the demo, the example below is a **standalone runnable Java class** placed at `src/main/java/com/example/aspectstate/ConcurrentProbe.java`.

**`ConcurrentProbe.java`**

```java
package com.example.aspectstate;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ConcurrentProbe {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService order = context.getBean(OrderService.class);
            CountingAspect aspect = context.getBean(CountingAspect.class);

            ExecutorService executor = Executors.newFixedThreadPool(4);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 100; i++) {
                    final int number = i;
                    futures.add(executor.submit(
                            (Callable<String>) () -> order.submit("N-" + number)
                    ));
                }

                for (Future<String> future : futures) {
                    future.get(); // wait for completion and propagate failure if any
                }

                System.out.println("completed=" + futures.size());
                System.out.println("count=" + aspect.getInvocationCount());
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

To run this separate class with the same Gradle project, add the following task at the end of `build.gradle`:

```gradle
tasks.register('concurrentProbe', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.aspectstate.ConcurrentProbe'
}
```

Run:

```bash
gradle concurrentProbe --quiet
```

Advice from `CountingAspect` will print **100 `advice#...` lines in non-deterministic execution order**. **The last two lines printed by `ConcurrentProbe`** after all futures finish have exact output:

```text
completed=100
count=100
```

The output sample above shows only **the final two lines**, not the entire stdout of the test. The numbering order in advice lines and the completion timing of each thread's method are not guaranteed; `AtomicInteger` guarantees total count = 100 in a fresh context. This demonstrates that multiple threads concurrently mutate the state of **one aspect bean** and the counter increment is atomic.

To test the race condition of `int total++`, many concurrent iterations can be run to observe lost updates, though race outcomes are **non-deterministic**; one run happening to yield 100 does not prove code is safe. For software testing, use concurrency tests/stress tests, and reason about thread-safety design independently of a single run's result.

## 8. Complex Scopes: Do Not Automatically Equate Aspect Bean with Instance

In **standard Spring AOP `@AspectJ` configuration**, the default instantiation model is **singleton aspect instance in the application context**. Spring also has **per-object/per-type aspect instantiation models**, such as `perthis` and `pertarget`, described by Spring documentation as advanced features.

Example of **illustrative syntax**, not added to the singleton demo:

```java
@Aspect("perthis(execution(* com.example.aspectstate..*Service.*(..)))")
public class PerProxyAspect {
    // state bound to each proxy object matching the pointcut
}
```

- `perthis`: binds an aspect instance per object bound to `this` at matching join points; with Spring AOP proxies, `this` normally represents the proxy object. Instances are created according to this model's instantiation condition, not simply creating a new instance on **every** method call.
- `pertarget`: binds per matching target object; the `this`/`target` distinction matters in the Spring proxy mechanism.
- Advanced capabilities vary across Spring versions: for example, Spring Framework **7.x** docs also list `pertypewithin`, whereas older Spring **6.x** docs had a narrower list. Therefore, before using them, check **documentation for the exact version** and test with the project's actual context.
- `percflow`/`percflowbelow` are not among the Spring AOP proxy models supported by current documentation.

**Do not conclude that “putting `@Scope("prototype")` on a singleton `@Aspect` will create one instance per request”.** Spring bean scopes and `@AspectJ` aspect instantiation models have separate contracts; with a per-clause, check compatible aspect registration/scope in your Spring version. Even with one aspect instance per target, **multiple threads calling the same target can still share that aspect instance**. Per-target is not equivalent to request scope or thread isolation.

If the problem is counting per user/request/order, a stateless singleton aspect + a service storing state properly keyed by ID is usually easier to control than trying to create many aspect instances. Before choosing a per-clause, obtain clear evidence that **per-target aspect lifecycle** is a business requirement.

### Independent Contexts: Each Has Its Own Singleton

A completely different situation from `perthis` is creating two independent `ApplicationContext`s:

```java
try (var firstContext = new AnnotationConfigApplicationContext(AppConfig.class);
     var secondContext = new AnnotationConfigApplicationContext(AppConfig.class)) {
    CountingAspect first = firstContext.getBean(CountingAspect.class);
    CountingAspect second = secondContext.getBean(CountingAspect.class);
    System.out.println("sameAcrossContexts=" + (first == second));
}
```

This is an **illustrative snippet** placed in a class importing `AnnotationConfigApplicationContext` and declaring `AppConfig` as in the demo. It prints:

```text
sameAcrossContexts=false
```

Each context registers its own singleton aspect bean. In parent/child context models, you must also consider where targets/proxies/advisors are created, so do not infer “one aspect for the entire application” based solely on class name.

## 9. Verification Procedure for a Real Spring Application

When suspecting duplicate advice, shared state, or incorrect results, follow in order:

1. **Confirm the context being inspected:** retrieve from the exact `ApplicationContext` where the target bean is created; if root/child exists, clearly identify parent/child.
2. **Count bean names of the aspect class:** `getBeanNamesForType(MyAspect.class)`; if >1, check `@Component` combined with `@Bean`, `@Import`, or module configuration imported into the context multiple times.
3. **Check the bean definition's scope:** `context.isSingleton("beanName")` for the singleton bean scope question, or use `getBeanFactory().getBeanDefinition("beanName").getScope()` on the appropriate context/configurable bean factory. An empty scope string in a bean definition usually indicates the default singleton scope.
4. **Compare identity:** call `getBean("beanName")` twice and compare with `==` when checking singletons. Do not confuse with `equals` or the count of proxy objects.
5. **Check target proxy:** `AopUtils.isAopProxy(targetBean)`, JDK/class proxy type, and pointcut match. An aspect bean being present is insufficient to prove advice executes.
6. **Count advice with a thread-safe recorder:** on a specific method, run sequentially first, then test concurrently and verify each call records the exact event count.
7. **Audit all mutable fields in the aspect:** classify immutable config, dependency services, counters, caches, request contexts, user data. Mutable fields holding per-request state are a sign that redesign is needed.
8. **Check production environment:** multiple threads, async/reactive hand-offs, multiple replicas, effects of transaction/advisor ordering, and actual observability/log sources.

**Symptom cross-reference table:**

| Symptom | Possible explanation | How to confirm |
| --- | --- | --- |
| `getBeansOfType(MyAspect.class)` returns 0 | Aspect only has `@Aspect`, missing `@Component`/`@Bean`, or wrong context scanned | Check registration method, package scan, and imported configs |
| One aspect bean exists, yet advice runs 0 times | Spring AOP not enabled, missing dependencies, pointcut mismatch, target not proxied, self-invocation | Check `@EnableAspectJAutoProxy`/Boot auto-config, `AopUtils`, and actual method call |
| Advice runs twice on one method | Two beans/aspects with the same advice or multiple advisors matching | List bean names, advisor chain, and aspect registration sites |
| Two different services increment the same counter | Singleton aspect shared across multiple target beans | Retrieve the aspect bean, observe identity and count after each call |
| Data from request B appears in request A's log | Mutable field holding request context inside singleton aspect | Inspect fields, two concurrent calls, and how IDs are passed |
| Counter is lower than concurrent call count | `int++` hit a race condition or some calls did not go through proxy | Separate match/proxy checks; use `AtomicInteger` or a concurrency-safe recorder |
| Each context has a different counter | Singleton scope is per-bean/per-container | Compare aspect bean objects from each context |
| Using prototype gives unpredictable instance counts | Confusing Spring bean scope with aspect instantiation model | Check `@Aspect` per-clause and actual lifecycle in the Spring version |

### Do Not Count Solely via Console Output

Log lines can interleave under concurrency; loggers have async buffering; one advice can log multiple events or get filtered; retries and transaction rollbacks can alter observations. For QA purposes, use a **verifiable counter/test sink** and assert against the number of methods that actually went through the proxy. A counter may count **attempted method executions** rather than business successes if using `@Before`; do not call this number committed transactions.

## 10. Checklist Before Accepting a Design

- [ ] Clearly stated whether counting **aspect beans**, **aspect instances**, or **advice invocations**, without conflating the three concepts.
- [ ] Aspect is registered by Spring via `@Component` or `@Bean` and has the expected number of bean definitions.
- [ ] Confirmed default singleton scope or advanced instantiation model against documentation for the exact version.
- [ ] Distinguished single context, multiple contexts, multiple threads, and multiple replicas.
- [ ] Spring AOP proxy exists on the target needing advice; pointcut matches and calls go through the proxy.
- [ ] Aspect fields hold safe configuration/dependencies; no request-specific mutable data is kept in a singleton.
- [ ] Shared counters or collections are synchronized/thread-safe to the appropriate degree; composite state needs full protection.
- [ ] Examples/tests use a real context, compare object identity with `==`, and count advice with a reliable recorder/counter.
- [ ] Checked for self-invocation, duplicate aspect registration bugs, and `@Aspect` not being a Spring bean.
- [ ] If per-request/per-target state is needed, chose an appropriate lifecycle mechanism rather than inferring from `@Scope("prototype")`.

**Point to remember:** In default Spring AOP, **one singleton aspect bean can serve multiple proxies, multiple calls, and multiple threads**. Check bean counts and object identity in **the right context**, verify advice invocations separately, and proactively protect or eliminate mutable state in aspects. Do not use advice execution counts or target proxy counts to deduce the number of aspect instances.

## Official Documentation

- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
