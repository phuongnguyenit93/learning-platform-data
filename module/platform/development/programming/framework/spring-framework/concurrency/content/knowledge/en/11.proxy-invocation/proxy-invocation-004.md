# Interface-Based Proxies vs. Class-Based Proxies

## 1. Why Does Spring Need Proxies?

In the Spring Framework, many features do not merely execute the code of the original method—they also need to perform work **before, after, or around the call**. For example:

- `@Async`: dispatches the method to a `TaskExecutor` for asynchronous execution.
- `@Transactional`: opens/joins a transaction, committing or rolling back based on the outcome.
- Spring AOP: logging, timing, access control, or custom *advice*.
- Certain caching, retry, or security mechanisms implemented via interceptors/proxies.

Spring commonly supplies callers with **a proxy** instead of a direct reference to the business object (*target*). The proxy decides which interceptors to run before forwarding the call to the target.

```text
Bean A (caller)
      |
      | calls service.process()
      v
  [ SPRING PROXY ]
      |
      +-- advice/interceptor: @Async / @Transactional / AOP ...
      |
      v
  [ TARGET OBJECT ]
      |
      v
  business method
```

The **two primary proxy mechanisms** are **interface-based JDK dynamic proxies** and **class-based CGLIB proxies**. Which mechanism is chosen affects what type Spring can inject, which methods can be proxied, restrictions related to `final`, and whether annotations are applied at the call boundary.

**The most important point for concurrency:** whether using a JDK proxy or a CGLIB proxy, in Spring AOP's default *proxy-based* mode, **internal calls `this.someMethod()` on the target do not go through the proxy**. As a result, `@Async` may fail to create a new task and `@Transactional` may fail to open a transaction as expected.

## 2. Interface-Based Proxies: JDK Dynamic Proxies

### 2.1. Structure

A business object implements an interface:

```java
public interface ReportService {
    String generate(String id);
}

public class ReportServiceImpl implements ReportService {
    @Override
    public String generate(String id) {
        return "report:" + id;
    }

    public String internalStatus() {
        return "ready";
    }
}
```

These two declarations are an **API-illustrating snippet**, not a standalone program (each `public` type usually needs its own file). Spring can create a JDK dynamic proxy implementing `ReportService` and any selected interfaces of the target. A caller holding a reference of type `ReportService` invokes the proxy.

```text
ReportService interface
          ^
          | implements
          |
   JDK dynamic proxy ---- advice ----> ReportServiceImpl (target)
          ^
          |
      caller injects ReportService
```

**Characteristics:**

- The proxy is an object that **implements the interface**, not a subclass of `ReportServiceImpl`.
- Business methods routed through the proxy must belong to the **proxied interface**. The `internalStatus()` method exists only on the implementation class, not as an API callable through a `ReportService` variable.
- Under JDK proxy configuration, `proxy instanceof ReportService` is normally `true`, whereas `proxy instanceof ReportServiceImpl` is `false`.
- Therefore, inject by the compatible **interface type**; casting a JDK proxy to `ReportServiceImpl` is invalid and typically throws `ClassCastException`. Injecting a proxied bean by its concrete class can cause a dependency resolution failure at startup if the proxy type is not assignable.
- JDK proxies do not require the target class to be subclassable. However, methods must be exposed through the interface and the annotation/advisor mechanism must properly recognize the business method.

Do not interpret "interface-based proxy" as Spring generating **a new interface** containing code. The interface only defines the contract; the JDK generates a proxy class at runtime to forward calls to interceptors/the target.

### 2.2. Consequences for @Async

If a service has an `@Async` method present only on the implementation and not declared on the interface, a caller that only sees an interface-typed variable **cannot invoke that method directly**. For public APIs called from other beans, include the needed method signature in the interface or consider a class-based proxy with clear justification.

In Spring, it is good practice to place business annotations on the **implementation methods** to make the source of behavior explicit, especially when code might move across different proxy/weaving modes. Do not infer that switching from JDK to CGLIB automatically enables every `@Async`-annotated method: calls still must go through the proxy and be eligible for interception.

## 3. Class-Based Proxies: CGLIB Subclass Proxies

When the target has no suitable interface, or configuration forces class-based proxying, Spring can use **CGLIB** (repackaged inside `spring-core`) to generate a **runtime subclass** of the target class.

```text
ReportServiceImpl
       ^
       | extends
       |
 CGLIB-generated subclass(proxy)
       |
       +-- interceptor/advice
       +-- delegates method invocation to target
       |
     caller
```

**Core differences:**

- A CGLIB proxy is a subtype of the target class, so it can be injected as either the **concrete class** or an interface it implements.
- Public methods on the target—even if **not declared in an interface**—can be advised if the method is eligible for overriding/interception and an advisor applies to it.
- You do not need to write an interface solely so Spring can create a proxy.
- CGLIB relies on subclassing, so real Java inheritance constraints apply.

### Unavoidable Limitations

| Situation | CGLIB Class-Based Proxy |
| --- | --- |
| `final` class | Cannot be subclassed to proxy that class |
| `final` method | Cannot be overridden to advise that method |
| `private` method | Cannot be overridden/intercepted by a subclass |
| Methods with insufficient visibility | May not be advisable, e.g., package-private across a different parent package |
| Internal `this.process()` call | Still bypasses the proxy in Spring AOP proxy mode |
| Class inside a closed JDK/module | May encounter Java Module System restrictions |

**Do not confuse "CGLIB is a subclass" with "every `this.method()` call goes through the subclass proxy."** In Spring AOP, the proxy forwards the call to the target; inside the target, `this` is the target reference, so internal calls do not re-enter the proxy. That is why self-invoking `@Async` or `@Transactional` is not advised in either mode.

Spring commonly uses Objenesis when creating class-based proxies to avoid calling the constructor twice; however, you should not build business logic around proxy-instantiation details, and you must still respect subclassability, visibility, and Java module constraints.

### When Both Interfaces and Class-Based Proxies Are Involved

An implementation with an interface **can still** be CGLIB-proxied if `proxyTargetClass=true` is enabled. JDK proxying is not an immutable rule for every bean with an interface; it is **Spring AOP's default choice when class-based proxying is not forced**, while Spring Boot and auto-configurations may alter the final decision.

## 4. Quick Comparison of the Two Proxy Types

| Aspect | JDK Dynamic Proxy | CGLIB Class-Based Proxy |
| --- | --- | --- |
| Foundation | `java.lang.reflect.Proxy` | Subclass generated at runtime |
| Main requirement | At least one interface to proxy | Target class can be subclassed |
| Proxy type | Implements interface(s) | Extends target class |
| Injectable by interface | Yes | Yes, if target implements the interface |
| Injectable by concrete implementation | No, with a standard JDK proxy | Yes |
| Methods only on the implementation | Not exposed through the interface proxy | Can be advised if overriding/visibility are valid |
| `final` class | JDK proxy can still wrap an interface of a final target | Cannot be subclassed |
| `final` method | Can intercept calls **through the interface** before entering target | Cannot be advised via overriding |
| `private` method | Not part of the interface proxy contract | Cannot be advised directly |
| Internal `this.method()` call | Bypasses proxy | Bypasses proxy |
| JPMS restrictions | Subject to proxy/interface/JVM limits | May hit package-opening rules for subclass generation |

In practice, **call-boundary design** and **business correctness** matter far more than any performance gap between the two mechanisms. Do not switch to CGLIB assuming "it is always faster" or "it fixes self-invocation."

## 5. How Does Spring Choose the Proxy Type?

### 5.1. In Plain Spring Framework

With proxy-based Spring AOP, when the target has an interface and nothing forces class-based proxying, Spring typically chooses a **JDK dynamic proxy**. When no suitable interface exists, Spring uses a **CGLIB class proxy**. Class-based proxying can be forced with:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

or for transaction management:

```java
@EnableTransactionManagement(proxyTargetClass = true)
```

and for asynchronous processing:

```java
@EnableAsync(proxyTargetClass = true)
```

These are **annotation configuration snippets**, not standalone Java files. These annotations require imports, placement on an appropriate configuration class, and corresponding dependencies. `proxyTargetClass=true` is meaningful only in proxy mode; it **does not switch** to AspectJ weaving.

### 5.2. In Spring Boot

Spring Boot includes AOP auto-configuration and **typically defaults to CGLIB class-based proxies** for Spring AOP. When you want to enable JDK interface-based proxies for that auto-configuration, you can configure:

```properties
spring.aop.proxy-target-class=false
```

Or select class-based:

```properties
spring.aop.proxy-target-class=true
```

**Do not conclude** solely from this property that every `@Async`/`@Transactional` bean across all Spring Boot versions necessarily uses the same proxy type. The actual proxy type depends on Framework/Boot version, annotation attributes, bean type, post-processors, and combined proxy settings. When multiple auto-proxy processors operate together, forcing subclassing can have a broader impact than a single bean.

For instance, in **Spring Framework 6.2**, `@EnableAsync(proxyTargetClass = true)` can affect other Spring-managed beans requiring proxies, not only those with `@Async`. Do not treat it as an "isolated local switch" and overlook active transactions or AOP.

### 5.3. Check Instead of Guessing

Use the Spring API:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

This snippet runs in an environment with an actual Spring `bean` and the `spring-aop` module. Check after retrieving the bean from `ApplicationContext`, not on an object manually instantiated with `new`. `bean.getClass().getName()` can be helpful for debugging, but generated proxy class names should not be hard-coded in tests.

## 6. Hands-On Maven + Java 17 Example: JDK Proxy and CGLIB on the Same Target Type

This example creates proxies **using Spring's `ProxyFactory`**, independent of automatic bean scanning. That makes the JDK/CGLIB choice completely explicit. A `MethodBeforeAdvice` logs when `hello(...)` is invoked **through the proxy**; meanwhile, `localCall()` shows that self-invocation is not advised.

**Prerequisites:** JDK 17 or later, Maven 3.x, Spring Framework **6.2.10** (pinned version for the example).

Structure:

```text
spring-proxy-modes/
├── pom.xml
└── src/main/java/demo/ProxyModeDemo.java
```

### 6.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-proxy-modes</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.10</version>
        </dependency>
        <dependency>
            <groupId>aopalliance</groupId>
            <artifactId>aopalliance</artifactId>
            <version>1.0</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ProxyModeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. File src/main/java/demo/ProxyModeDemo.java

```java
package demo;

import org.springframework.aop.MethodBeforeAdvice;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

public final class ProxyModeDemo {
    // Contract that a JDK dynamic proxy can implement.
    public interface Greeter {
        String hello(String name);
    }

    // Must be non-final so CGLIB can generate a subclass.
    public static class GreeterImpl implements Greeter {
        @Override
        public String hello(String name) {
            return "hello:" + name;
        }

        // This method is NOT declared in the interface.
        public String localCall() {
            return "local:" + this.hello("inside");
        }
    }

    private static ProxyFactory createFactory(boolean classProxy) {
        ProxyFactory factory = new ProxyFactory(new GreeterImpl());
        factory.setInterfaces(Greeter.class);
        factory.setProxyTargetClass(classProxy);

        factory.addAdvice((MethodBeforeAdvice) (method, args, target) -> {
            if ("hello".equals(method.getName())) {
                System.out.println("advice:" + args[0]);
            }
        });
        return factory;
    }

    public static void main(String[] args) {
        Greeter jdk = (Greeter) createFactory(false).getProxy();
        System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(jdk));
        System.out.println("jdkConcrete=" + (jdk instanceof GreeterImpl));
        System.out.println(jdk.hello("outside"));

        GreeterImpl cglib =
                (GreeterImpl) createFactory(true).getProxy();
        System.out.println("cglibProxy=" + AopUtils.isCglibProxy(cglib));
        System.out.println("cglibConcrete=" + (cglib instanceof GreeterImpl));
        System.out.println(cglib.hello("outside"));
        System.out.println(cglib.localCall());
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Standard output from the program (excluding Maven logs):**

```text
jdkProxy=true
jdkConcrete=false
advice:outside
hello:outside
cglibProxy=true
cglibConcrete=true
advice:outside
hello:outside
local:hello:inside
```

### 6.3. Analysis of Each Observation

- `jdkProxy=true`: the factory was configured to use a JDK dynamic proxy. The variable `jdk` is a `Greeter`; the proxy does not extend `GreeterImpl`, so `jdkConcrete=false`.
- Calling `jdk.hello("outside")` from `main` goes through the proxy, so `advice:outside` appears before `hello:outside`.
- With `classProxy=true`, Spring creates a CGLIB proxy extending `GreeterImpl`. `cglibConcrete=true` is a consequence of the subclass relationship; calling `cglib.hello(...)` from `main` also goes through the advice.
- `cglib.localCall()` enters the target; inside the target, `this.hello("inside")` **does not re-enter the proxy**, so the output is just `local:hello:inside`, **without** `advice:inside`.
- The example demonstrates the principle of **Spring AOP proxies**. It does not use `@Async` or open DB transactions; the advice here is a simple `MethodBeforeAdvice` to make the interception boundary clear.

Even if an advisor is also added for `localCall()`, an external call may be advised on `localCall()` itself, yet that **does not trigger a second proxy call for `this.hello()`**.

**Why use Maven instead of `javac ProxyModeDemo.java`?** Because `ProxyFactory`, `MethodBeforeAdvice`, and CGLIB integration belong to Spring libraries; compiling directly with only the JDK without Spring on the classpath will fail. Maven downloads dependencies and builds the right classpath; the source code itself is standard Java 17.

## 7. Impact on @Async: External Calls vs. Self-Invocation

Consider a Spring-managed service:

```java
public interface NotificationService {
    java.util.concurrent.CompletableFuture<String> send(String id);
    void trigger(String id);
}
```

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationServiceImpl implements NotificationService {
    @Override
    @Async("notificationExecutor")
    public CompletableFuture<String> send(String id) {
        String result = "sent:" + id;
        return CompletableFuture.completedFuture(result);
    }

    @Override
    public void trigger(String id) {
        // WRONG if you expect @Async to apply to this call:
        this.send(id);
    }
}
```

These are **integration snippets**: the interface and implementation need separate files; the application must enable `@EnableAsync` and provide an executor bean named `notificationExecutor`.

There are two distinct paths:

```text
Bean A injects NotificationService
     |
     +-- notificationService.send("x")
     |        |
     |        +--> Spring proxy --> @Async interceptor --> executor
     |                                           |
     |                                           +--> target.send("x")
     |
     +-- notificationService.trigger("x")
              |
              +--> Spring proxy --> target.trigger("x")
                                      |
                                      +--> this.send("x")
                                              |
                                              +--> target.send("x") directly
                                                   (DOES NOT pass through @Async proxy)
```

Because `trigger()` calls `this.send()` on the same target, the body of `send()` on that path may execute **on the current thread** instead of being dispatched to the executor. This holds for **both JDK and CGLIB** in standard proxy mode.

### Preferred Fix: Call Through Another Bean

Extract the asynchronous method into a separate bean and keep orchestration in another bean:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class NotificationCoordinator {
    private final NotificationService notificationService;

    public NotificationCoordinator(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    public CompletableFuture<String> trigger(String id) {
        // Calls through the Spring-injected reference -> goes through the proxy.
        return notificationService.send(id);
    }
}
```

This is also an integration snippet alongside `NotificationService` above. Pros: clear async boundary, easy to test with another bean, and minimal coupling to AOP details. Ensure the injected object is actually a proxied Spring bean; instantiating `new NotificationServiceImpl()` manually and calling it will not be intercepted by Spring.

### Does Switching Proxy Type Solve Self-Invocation?

**No.** Setting `@EnableAsync(proxyTargetClass=true)` only changes the proxy creation mechanism; it does not make `this.send()` on the target go back through the proxy. If you need self-invocation to be intercepted, Spring supports `AdviceMode.ASPECTJ` with compile-time/load-time weaving, though that is a different mechanism with heavier dependencies and operational complexity. For most applications, designing explicit service-to-service calls is simpler and less risky.

## 8. Impact on @Transactional and Transaction Scope

With Spring transactions in proxy mode:

```java
@Service
public class BillingService {
    @Transactional
    public void charge(String id) {
        // DB operations that need to run inside a transaction.
    }

    public void chargeFromSameBean(String id) {
        this.charge(id); // Does not go through the transaction proxy.
    }
}
```

This is an illustrative snippet; it requires imports for `@Service`, `@Transactional`, a datasource/transaction manager, and a Spring environment. If another bean calls `billingService.charge(id)` through the proxy, Spring's transaction advice has the opportunity to open/join a transaction per the annotation. If `this.charge(id)` is called from the target, the advice of `charge` **is not triggered by that call**.

**Subtle distinction:** "self-invocation bypasses transaction advice" does not mean "there is definitely no transaction at all." If the outer method was already called through the proxy and **already has an active transaction**, the internal call can still execute within that existing transaction, yet it will not trigger the inner method's own transaction settings (such as `REQUIRES_NEW`). Conversely, if the outer method has no transaction, self-invocation will generally not start a new transaction merely because the inner method is annotated.

With asynchronous processing, imperative transactions managed by Spring are typically bound to the **current thread**. When `@Async` actually hands work off to another thread, the caller's transaction does not automatically follow as a reusable context. If an async task must perform DB operations inside a transaction, place the transaction boundary on a service/method invoked inside the worker through a properly managed Spring mechanism.

**Note on visibility in Spring Framework 6.x:** `@Transactional` on a JDK interface proxy typically requires `public` methods declared on the interface; with class-based proxies, Spring Framework 6.0+ can support `protected` or package-visible transactional methods under default settings, provided they are eligible for interception. Do not generalize this rule to every annotation/interceptor; for broad compatibility and easy testing, prefer **`public`, non-`final` methods invoked from another bean**.

Spring recommends generally placing `@Transactional` on **concrete classes/methods**. Placing annotations on interfaces can work in proxy mode in recent versions, yet AspectJ weaving does not inherit annotations from interfaces under Java rules; switching mechanisms could cause the annotation to be ignored.

## 9. Typical Configuration and Dependency Injection Pitfalls

### Pitfall A: Injecting the Implementation When the Bean Is Actually a JDK Proxy

```java
@Autowired
private ReportServiceImpl reportService; // May fail to assign a JDK proxy.
```

**Fix:** inject the `ReportService` interface or, if you have a valid need for the concrete type, configure/verify class-based proxying. Changing only the field declaration without checking how the bean is created easily leads to startup failures.

### Pitfall B: Casting a JDK Proxy to the Implementation

```java
ReportService service = applicationContext.getBean(ReportService.class);
ReportServiceImpl impl = (ReportServiceImpl) service; // Wrong with a JDK proxy.
```

This is an illustrative snippet given an existing `applicationContext`. A JDK proxy does not extend the implementation. **Do not** assume `applicationContext.getBean(...)` returns the raw target; Spring may return a proxy carrying advice.

### Pitfall C: Switching to CGLIB When the Class Is final

```java
public final class FinalService {
    public void execute() { }
}
```

A `final` class cannot be subclassed by CGLIB. In Kotlin, classes/methods are final by default; applications may require the `kotlin-spring`/all-open plugin or appropriate non-final design. Do not blindly strip `final` from objects guarding important invariants; determine the proxy mechanism and API boundary first.

### Pitfall D: Annotating a final/private Method and Expecting Advice

Having `@Async` or `@Transactional` on a `private`/`final` method does not mean a class-based proxy can intercept it. When CGLIB cannot override it, the advice does not behave as expected. **Fix:** move the logic to a `public` non-`final` method on another Spring bean and invoke it through the proxy; avoid changing visibility just to "pass" a check while self-invocation still remains.

### Pitfall E: Creating with new, or Calling Inside @PostConstruct

Instantiating `new BillingService()` does not pass through Spring post-processors and has no transaction interceptor. Likewise, `@PostConstruct` is part of bean initialization; do not rely on a proxy to self-invoke `@Async`/`@Transactional` methods there. Create a separate startup bean that calls the target bean after the context is established.

### Pitfall F: Assuming Both Proxy Types Fix All Internal Calls

Both JDK and CGLIB proxies are bounded by **call paths** when using Spring AOP proxies. `this.method()` does not go through the advice. Trying to use `AopContext.currentProxy()` requires configuring `exposeProxy=true` and accepting coupling to Spring AOP; this is not the recommended default. Splitting beans or calling through a dedicated orchestrating component is usually clearer.

### Pitfall G: Forcing CGLIB Everywhere Without Considering App-Wide Impact

A configuration-level `proxy-target-class` setting can affect many AOP/transaction/async beans simultaneously. Class proxies also carry constraints around `final`, module paths, and visibility. **Fix:** configure intentionally, and test proxy types along with transaction/async behavior after changes.

### Pitfall H: Inferring Behavior Solely from the Proxy Class Name

Runtime-generated names can vary across Framework, JVM, build, or configuration. Use `AopUtils.isAopProxy`, `AopUtils.isJdkDynamicProxy`, and `AopUtils.isCglibProxy` to inspect proxies instead of writing logic that depends on class-name strings.

## 10. Checklist for Checking Proxies in a Spring Application

When `@Async` does not run asynchronously, transactions do not roll back as expected, or bean injection fails:

1. **Is the bean Spring-managed?** Verify the object comes from `ApplicationContext`, not a fresh instance created with `new`.
2. **Is annotation infrastructure enabled?** For example, `@EnableAsync` for async processing, `@EnableTransactionManagement` or appropriate auto-configuration for transactions.
3. **What is the actual proxy type?** Use the three methods `AopUtils.isAopProxy`/`isJdkDynamicProxy`/`isCglibProxy`.
4. **What type does the caller hold?** With JDK proxies, the variable should use the proxied interface type; with class proxies, verify the class can be subclassed.
5. **Is the method eligible for interception?** Is it on the proxied JDK interface? Is it `final`/`private`/unavailable visibility on a class proxy? Is the annotation placed where Spring detects it?
6. **Does the call pass through the proxy?** `beanFromContainer.method()` differs from `this.method()` inside the target.
7. **Is the feature's advice registered?** The existence of a proxy alone does not prove the specific interceptor for `@Async`/`@Transactional` is applied.
8. **Is the async executor correct?** Check the executor name in `@Async("...")`, rejection behavior, and actual execution thread.
9. **Where does the transaction exist?** Verify method entry/commit/rollback, propagation, and thread boundaries; do not rely solely on annotations.
10. **Are there nested proxies or multiple advisors?** Inspect the actual bean type and interceptor chain; do not assume advice ordering without configuring/measuring it.

### Test Distinguishing External Invocation and Self-Invocation

Create two test cases:

```text
Case 1:
  otherBean -> proxiedService.process()
  expected: process advice is applied

Case 2:
  otherBean -> proxiedService.wrapper()
  target.wrapper() -> this.process()
  expected: internal call does NOT trigger separate process advice
```

For `@Async`, record thread names or use latches/futures to confirm a different worker; do not rely merely on `Thread.sleep`. For `@Transactional`, write an integration test with a real transaction manager/database, intentionally throw an exception, and verify rollback, because stdout alone does not prove transactions work.

## 11. Which Type Should You Choose for Service Design and Concurrency?

**Prioritize API design first, then choose the matching proxy:**

- If the application has **stable business interfaces**, injecting via interfaces keeps callers decoupled from implementations; JDK proxies work naturally.
- If there is no interface and you want to advise public methods of a class, CGLIB class proxies are a common choice, provided classes/methods can be subclassed/overridden.
- If the application uses Spring Boot, **do not assume plain Spring Framework and Spring Boot make the same proxy choice**; check Boot properties, annotation settings, and versions.
- If `final` must be used on a class or method, consider an interface proxy if the method is exposed via an interface, or refactor the architecture. Do not assume subclassing will work.
- If `@Async` is needed for parallel execution, splitting orchestration and async workers into **two different Spring beans** guarantees calls pass through the proxy and clarifies lifecycle/thread boundaries.
- If proper transactions are needed inside async processing, have the async service invoke a **separate transactional service** on the worker rather than expecting the caller's transaction to travel across the executor automatically.
- If bottlenecked by executor pools/DB connections, changing proxy types **will not solve overload**. Configure thread pools, queues, connection pools, timeouts, and backpressure at the appropriate layer.

### Reference Architecture Diagram

```text
RestController
      |
      v
JobCoordinator
      |
      | calls via Spring-injected interface
      v
AsyncWorker proxy
      |
      | @Async advice: submits to executor
      v
worker thread
      |
      v
AsyncWorker target
      |
      | calls via Spring-injected transactional service
      v
TransactionalService proxy
      |
      | @Transactional advice on worker thread
      v
TransactionalService target -> DB
```

This model cleanly separates the **proxy boundary**, **thread boundary**, and **transaction boundary**; these three do not necessarily coincide. The components above represent architectural roles, not mandatory class names required in every project.

## 12. Exercises and Self-Check Criteria

1. Run the Maven example in Section 6. Verify that a JDK proxy implements the interface but is not a subtype of the implementation, whereas a CGLIB proxy is a subtype.
2. Add a public `extra()` method only on `GreeterImpl`. Observe: a caller typed `Greeter` cannot call `extra()`, whereas a `GreeterImpl` variable from a CGLIB proxy can; if matching advice is added, external calls can be intercepted.
3. Try changing `GreeterImpl` to a `final class` and predict class-based proxy behavior. Do not treat a test as passing if it only creates a JDK proxy because you accidentally disabled `proxyTargetClass`.
4. Add `final` to `hello()` and examine why class-based advice is no longer guaranteed to intercept; compare with a JDK proxy on the interface method.
5. Measure the difference between `cglib.hello("outside")` and `cglib.localCall()`: why does only the first case print `advice:outside`?
6. In a Spring app, create an `@Async` method and another method calling `this.asyncMethod()`. Check the executing thread and refactor into another bean to prove the external call gets advised.
7. With `@Transactional(propagation = REQUIRES_NEW)`, test self-invocation and external invocation in an integration test with a database; compare actual transaction boundaries rather than judging only from source code.
8. Configure `spring.aop.proxy-target-class=false` in a Spring Boot app with AOP auto-configuration and an interface service. Read `AopUtils.isJdkDynamicProxy(...)` to verify under the actual topology/configuration; do not infer solely from the property if other proxy configurations exist.

**Pass criteria:** distinguish proxy vs. target, accurately describe advisable types and methods, predict injection/cast failures, clearly identify self-invocation bypasses, and verify with code/tests rather than relying on annotation names.

## 13. Summary and Official Documentation

| Question | Short Answer |
| --- | --- |
| What is a JDK dynamic proxy built on? | The target's interface(s) |
| What is CGLIB built on? | A subclass of the target class |
| Can an interface proxy be injected by implementation class? | No, with a standard JDK proxy |
| Can CGLIB proxy a `final` class / `final` method? | No |
| Can CGLIB intercept methods outside an interface? | Yes, if the class/method is eligible and an advisor applies |
| Does switching from JDK to CGLIB fix self-invocation? | **No** |
| Why does `@Async` on a self-call not switch threads? | The call does not pass through the async proxy interceptor |
| Is JDK/CGLIB chosen solely by `@EnableAsync` or one property? | Must consider version and overall AOP configuration; inspect the actual proxy |
| What is the common fix for self-invocation? | Extract a service and invoke it through a Spring-injected bean |

**References:**

1. [Spring Framework 6.2 – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, self-invocation, final/private/module constraints.
2. [Spring Framework 6.2 – Creating AOP Proxies with ProxyFactory](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/prog.html): creating advised proxies programmatically in Java.
3. [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, executors, and proxy mode.
4. [Spring Framework 6.2 – Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxy semantics, method visibility, AspectJ, and self-invocation.
5. [Spring Framework 6.2 – @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): `proxyTargetClass` and `AdviceMode.PROXY`.
6. [Spring Boot – Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): CGLIB default in AOP auto-configuration and the `spring.aop.proxy-target-class` property.

**Key takeaway:** JDK proxies are interface-based; CGLIB proxies are subclass-based. Both allow Spring to place interceptors **at the boundary of calls entering the proxy**, rather than altering calls between methods of the same target. For concurrency, understanding this boundary is essential so that `@Async` truly hands work off to an executor and `@Transactional` takes effect right where intended.
