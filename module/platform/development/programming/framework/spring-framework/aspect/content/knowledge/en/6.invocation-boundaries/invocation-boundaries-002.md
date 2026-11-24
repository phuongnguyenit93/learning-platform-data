# Self-invocation via `this` and why advice is bypassed in Spring AOP

## 1. Lesson objectives

When using **proxy-based Spring AOP**, a method can receive advice when called from another bean yet **not receive advice** when called via `this` inside its own class. This is known as **self-invocation** (an internal call to the object itself).

Example:

```java
public void placeOrder() {
    this.saveOrder(); // Internal call, does not go back through the Spring AOP proxy
}

public void saveOrder() {
    // Can be a method targeted by an advice
}
```

If `placeOrder()` is called **through the proxy**, advice targeting `placeOrder()` can still run. However, once execution has entered the **target object** and calls `this.saveOrder()`, that second call **does not go through the proxy**, so advice targeting `saveOrder()` specifically is not triggered for that call. If an external client calls `proxy.saveOrder()`, the advice for `saveOrder()` can run normally again.

After this lesson, you will be able to:

1. Explain the **proxy boundary** in Spring AOP and why self-invocation bypasses advice.
2. Predict the exact output when calling the same method externally vs. internally from the target.
3. Distinguish self-invocation from other reasons why advice does not run (pointcut, bean registration, `final` methods, objects created with `new`).
4. Refactor code toward **splitting responsibilities into separate Spring beans** and calling across proxies.
5. Understand the trade-offs of **self-injection** or `AopContext.currentProxy()`, and the practical implications for transactions/caching/async in proxy mode.

This lesson covers only **Spring Aspect/Spring AOP behavior**; it does not re-introduce general Aspect concepts.

## 2. Two key objects: proxy and target

Suppose an application has an `OrderService` bean matching an advisor from an `@Aspect` class. Spring can return an **AOP proxy** to clients instead of returning the target directly.

```text
Call from another bean/client
           |
           v
   OrderService proxy
           |
           +--> Pointcut/advisor matches outer method?
           |         |
           |         +--> run corresponding advice
           |
           v
      Target object
           |
           +--> logic inside method
                  |
                  +--> this.innerMethod()
                              |
                              v
                        Target method directly
                        (DOES NOT go back to proxy)
```

On the first call path, the client holds a **proxy reference**. Spring gets the chance to build the interceptor/advice chain for the method called via the proxy. Inside the target, however, `this` points to **the object executing business logic**, not a new call to the Spring AOP proxy. Calling a method via the `this` reference does not automatically route back to the proxy to re-evaluate advisors.

In Spring AOP, **advice is inserted along calls passing through a proxy**, rather than automatically injected into every Java call inside a class. Spring uses `@AspectJ` to describe pointcuts/advice, while runtime execution remains **proxy-based Spring AOP** unless separate weaving is configured.

### 2.1. Why does a matching pointcut still fail to run?

Consider this example:

```java
@Before("execution(* example.OrderService.saveOrder(..))")
public void auditSaveOrder() {
    System.out.println("advice: saveOrder");
}
```

The pointcut expression may **match `OrderService.saveOrder()` accurately**. That only answers "which method falls within the advisor's scope?". For advice to execute, the invocation must pass through **the Spring AOP proxy carrying that advisor**.

`this.saveOrder()` invokes the method directly on the target. Therefore:

- The pointcut **is not necessarily wrong**.
- The aspect **is not necessarily unregistered**.
- The bean **is not necessarily missing a proxy**.
- Rather, **that specific call bypassed the proxy boundary**.

This is the difference between **advisor applicability** and **an invocation actually traversing the advisor**.

## 3. Comparing call paths

Assume both `outer()` and `inner()` are public, the target is a Spring bean with an AOP proxy, and a pointcut advisor targets `inner()`.

| Call | Passes through proxy when entering `inner()`? | Does advice specifically for `inner()` have a chance to run? |
| --- | --- | --- |
| Another bean calls `service.inner()` on the Spring-provided reference | **Yes** | **Yes**, if pointcut and other conditions match |
| Another bean calls `service.outer()`, and `outer()` uses `this.inner()` | **No** for the `inner()` call | **No** on the internal `inner()` call |
| Inside `outer()`, calling `inner()` without writing `this` | **No** | **No**; the implicit call is still `this.inner()` |
| External code calls `new Service().inner()` | **No** | **No** because the instance is not Spring-proxied |
| `outer()` calls `anotherBean.inner()` via an injected bean reference that is proxied | **Yes** on the second bean | **Yes**, if an advisor matches |
| Inside target, using `AopContext.currentProxy()` and calling the method on the proxy | **Yes**, when proxy is exposed and called validly | **Yes**; however this couples business code tightly to Spring AOP |
| Inside target, injecting its own proxy and calling via that reference | **Yes**, if Spring actually injects the appropriate proxy | **Yes**; yet carries design/circular-dependency configuration costs |

**Clear distinction:** When `outer()` is called through the proxy, advice targeting `outer()` **can still run**. Only advice corresponding to `inner()` is bypassed at the internal call step. Do not loosely say "self-invocation makes all AOP on `outer()` disappear".

## 4. Runnable Java 17+ example: observing three paths

The example uses **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Maven, and `@EnableAspectJAutoProxy`. No HTTP server or database is used so that only Spring AOP boundaries are observed.

### 4.1. Project structure

```text
spring-aop-self-invocation/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── PersistenceService.java
    ├── WorkflowService.java
    ├── TraceAspect.java
    └── Main.java
```

### 4.2. Maven: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-aop-self-invocation</artifactId>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

In real applications, `spring-*` versions should be managed via the **Spring Framework BOM** or Spring Boot BOM to avoid version mismatches. This example declares explicit versions to form a self-contained project that is easy to experiment with.

### 4.3. Target with self-invocation: `OrderService.java`

```java
package example;

public class OrderService {

    public void submit() {
        System.out.println("order: submit");
        this.persist();
    }

    public void persist() {
        System.out.println("order: persist");
    }
}
```

`submit()` calls `this.persist()` inside **the same target class**. There is no Spring bean lookup or proxy reference between the two methods.

### 4.4. Separate target illustrating the fix: `PersistenceService.java`

```java
package example;

public class PersistenceService {

    public void persist() {
        System.out.println("storage: persist");
    }
}
```

### 4.5. Coordinator bean calling another bean: `WorkflowService.java`

```java
package example;

public class WorkflowService {

    private final PersistenceService persistenceService;

    public WorkflowService(PersistenceService persistenceService) {
        this.persistenceService = persistenceService;
    }

    public void submit() {
        System.out.println("workflow: submit");
        persistenceService.persist();
    }
}
```

Unlike `this.persist()` in `OrderService`, the `persistenceService` reference receives **a Spring-provided bean**. If that bean is proxied, the call passes through the proxy.

### 4.6. Two advice methods declared in a Spring aspect: `TraceAspect.java`

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(* example.OrderService.persist(..))")
    public void beforeOrderPersist() {
        System.out.println("advice: order persist");
    }

    @Before("execution(* example.PersistenceService.persist(..))")
    public void beforeStoragePersist() {
        System.out.println("advice: storage persist");
    }
}
```

Both pointcuts target a method named `persist()`, but on **different target classes**. This avoids ordering dependencies between multiple advice methods for the same invocation and keeps stdout predictable.

### 4.7. Spring configuration: `AppConfig.java`

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public PersistenceService persistenceService() {
        return new PersistenceService();
    }

    @Bean
    public WorkflowService workflowService(PersistenceService persistenceService) {
        return new WorkflowService(persistenceService);
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Notes:

- `TraceAspect` has `@Aspect` and does not need `@Component` because it is **registered via `@Bean`**.
- `@EnableAspectJAutoProxy` enables Spring AOP auto-proxying for the context; `proxyTargetClass=true` forces **class-based proxies** for eligible targets.
- Both `OrderService` and `PersistenceService` have methods matching the pointcuts and can receive proxies.
- Switching from JDK to CGLIB **does not cure self-invocation**. Choosing CGLIB here merely lets the example use concrete types directly and demonstrates this point clearly.

### 4.8. Running the demo: `Main.java`

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService order = context.getBean(OrderService.class);
            PersistenceService storage = context.getBean(PersistenceService.class);
            WorkflowService workflow = context.getBean(WorkflowService.class);

            System.out.println("order is proxy: " + AopUtils.isAopProxy(order));
            System.out.println("storage is proxy: " + AopUtils.isAopProxy(storage));

            System.out.println("-- call 1: external direct --");
            order.persist();

            System.out.println("-- call 2: self invocation --");
            order.submit();

            System.out.println("-- call 3: another bean --");
            workflow.submit();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

**Lines printed by the methods in the example, in exact order:**

```text
order is proxy: true
storage is proxy: true
-- call 1: external direct --
advice: order persist
order: persist
-- call 2: self invocation --
order: submit
order: persist
-- call 3: another bean --
workflow: submit
advice: storage persist
storage: persist
```

### 4.9. Analyzing the output

**Call 1 — `order.persist()`:** `order` is a reference to the **AOP proxy** returned by Spring. The proxy receives the `persist()` invocation, finds the matching advice in `TraceAspect`, prints `advice: order persist`, then invokes the target and prints `order: persist`.

**Call 2 — `order.submit()`:** `submit()` is called through the proxy, but no advice in this example targets `submit()`. When the target starts executing `submit()`, `order: submit` is printed. The `this.persist()` statement inside the target calls `persist()` directly; because it **does not go through the AOP proxy a second time**, `advice: order persist` **does not appear**. The line `order: persist` still appears — the business method **was not skipped**, only the **advice** was bypassed.

**Call 3 — `workflow.submit()`:** `WorkflowService` holds a Spring-injected reference to `PersistenceService`. When it calls `persistenceService.persist()`, the invocation passes **through another bean's proxy**, so `beforeStoragePersist()` runs. This is the common design fix: place the behavior needing advice into **another Spring service** and invoke it via dependency injection.

The output demonstrates **precisely one cause of advice bypass** without involving transactions, caching, or databases. If you add other advisors or change configuration, the output may differ and should be re-verified.

## 5. CGLIB still suffers from self-invocation: why?

A common misconception: "JDK proxies only intercept interfaces, so enabling CGLIB means `this.inner()` will be advised." This is **false for proxy-based Spring AOP**.

Regarding proxy types:

- **JDK dynamic proxy:** the proxy implements interfaces; external callers invoke interface methods on the proxy.
- **CGLIB proxy:** the proxy is a subclass capable of intercepting overridable methods; external callers invoke methods on the proxy.

Yet in both forms, once an interceptor has forwarded the call into **the target executing business logic**, an internal call via `this` on the target **never crosses a proxy boundary**. The Spring documentation explicitly states that self-invocation using the `this` reference, whether explicit or implicit, bypasses advice.

The example in section 4 already forced `proxyTargetClass = true`, meaning CGLIB is used — yet `this.persist()` **still does not execute** `beforeOrderPersist()`.

**Additionally, a `private` or `final` method cannot be advised by Spring AOP CGLIB via overriding.** That is a *different* limitation from self-invocation. With self-invocation, even when `inner()` is `public` and completely proxiable, the internal call path still bypasses the proxy.

## 6. Preferred fix: split into separate beans and call via DI

### 6.1. Initial design

```java
@Service
public class OrderService {

    public void submit() {
        validate();
        this.persist();
    }

    public void persist() {
        // Code expected to be advised separately.
    }

    private void validate() {
        // ...
    }
}
```

This is an **illustrative snippet in a Spring application with component scanning**, not a standalone Java program. If the advisor only matches `persist()`, the internal call here will not trigger the advice.

### 6.2. Extracting the method needing an advisor into another bean

```java
@Service
public class OrderPersistenceService {

    public void persist() {
        // Logic that needs Spring AOP advice.
    }
}
```

```java
@Service
public class OrderService {

    private final OrderPersistenceService persistence;

    public OrderService(OrderPersistenceService persistence) {
        this.persistence = persistence;
    }

    public void submit() {
        validate();
        persistence.persist(); // Passes through the Spring-injected reference.
    }

    private void validate() {
        // ...
    }
}
```

The snippets above require importing `org.springframework.stereotype.Service` and appropriate component scanning/AOP configuration. Spring will create a proxy for `OrderPersistenceService` when an advisor matches; the constructor parameter receives the reference provided by Spring.

**Why does this work?** At `persistence.persist()`, the target being invoked is **another bean dependency**, which can be a proxy. A call through this reference enters the Spring AOP interceptor chain before reaching the target.

Additional benefits:

- Clearer boundary between **orchestration** and **advised operations**.
- Avoids direct coupling to `AopContext`.
- Easier unit testing because `OrderPersistenceService` can be mocked/faked via the constructor.
- Avoids self-injection and certain circular dependency issues.
- Works for boundaries where `@Transactional`, `@Cacheable`, `@Async`, or custom `@Aspect` all require calls through a proxy.

**Condition:** The dependency must be an **actual proxied Spring bean**, not an object created with `new`; the pointcut must still match that method. Simply splitting a class does not make Spring automatically apply advice.

### 6.3. Split by true functional boundaries, not mechanically

Do not extract every private method just to run AOP. Consider creating a separate bean only when a method has an **independent contract** requiring proxy interception, such as an independent transactional operation, an async task, or business logic needing dedicated auditing. Normal internal helper calculations can remain `private` methods in the same class.

## 7. Second option: inject the bean's own proxy reference

The Spring documentation mentions **self injection** as an option when splitting beans is inconvenient. The idea is for the class to hold **the proxy reference provided by Spring**, and then call `self.inner()` instead of `this.inner()`.

Illustrative example:

```java
@Service
public class OrderService {

    private final ObjectProvider<OrderService> selfProvider;

    public OrderService(ObjectProvider<OrderService> selfProvider) {
        this.selfProvider = selfProvider;
    }

    public void submit() {
        selfProvider.getObject().persist();
    }

    public void persist() {
        // Advice targets persist() when called through the proxy.
    }
}
```

This is an **illustrative snippet**, requiring imports for `org.springframework.beans.factory.ObjectProvider` and `org.springframework.stereotype.Service`. It is not part of the standalone project in section 4.

`ObjectProvider` defers bean lookup until `submit()` is invoked. If the context has finished initializing and `OrderService` is properly proxied, `selfProvider.getObject()` can return **the proxy reference** and `persist()` gets intercepted.

**Conditions/risks to check:**

1. The provider must resolve to **the right bean**. If multiple `OrderService` beans share the same type, a qualifier or selection mechanism is required.
2. Do not invoke the provider too early inside constructors/`@PostConstruct`: at that point the proxy lifecycle may not be complete.
3. Avoid hard-to-debug circular dependencies, especially in modern Spring Boot which restricts circular references by default.
4. If the bean uses a JDK interface proxy, do not expect the proxy to be assignable to the concrete class. When using a self proxy via interface, choose the **exposed proxied interface** as the provider type.
5. Self-injection makes the class aware of the container/proxy and is generally less clean than splitting services.

In other words, self-injection can be used deliberately when needed, but **should not be the default remedy** for an unclear design boundary.

## 8. Last resort: `AopContext.currentProxy()`

Spring provides the `AopContext.currentProxy()` API to retrieve the current thread-bound proxy when **exposing the proxy** is enabled. However, the Spring documentation warns that this approach is **discouraged** because business code becomes tightly coupled to Spring AOP.

Illustrative snippet:

```java
// Inside an eligible OrderService class, with the outer method called via proxy:
public void submit() {
    ((OrderService) AopContext.currentProxy()).persist();
}
```

Requires importing `org.springframework.aop.framework.AopContext`. With Spring Java configuration, you must enable:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

**These are two supplementary snippets, not a standalone program.** They also require `submit()` initially to be called **through the proxy** in an invocation where Spring exposes the proxy, and `OrderService` must be a type the proxy can be cast to (such as CGLIB in the configuration above).

Limitations:

- `AopContext.currentProxy()` can throw `IllegalStateException` when no current proxy is exposed (e.g. called on a manually `new`-ed target, outside a proxy context, or when `exposeProxy=false`).
- Enabling `exposeProxy=true` adds coupling and overhead; **it does not fix calls that did not enter a proxy in the first place**.
- With a **JDK proxy**, casting the proxy to the implementation class is wrong; you must cast to an exposed interface.
- It does not turn `private`/`final` methods into join points advisable via Spring proxy.
- Using this API just to "patch" every self-invocation is not recommended. Whenever possible, **refactor to avoid self-invocation that needs advice**.

## 9. Why fetching a bean from ApplicationContext inside a method is not a good solution

You may encounter code like:

```java
public void submit() {
    applicationContext.getBean(OrderService.class).persist();
}
```

With the right context/proxy, the call on the retrieved bean can go through the proxy. However, this embeds a **service locator** directly inside a business method, coupling the code to `ApplicationContext`, making unit testing harder, and obscuring dependency cycles. When using JDK proxies, looking up the bean by concrete type can also fail.

Prefer constructor injection of **another bean with its own responsibility**. If staying in the same class is unavoidable, use a managed and clearly documented self-reference rather than scattering `getBean(...)` throughout business methods.

## 10. Connection to `@Transactional`, `@Cacheable`, and `@Async`

The following Spring features typically rely on infrastructure advisors/proxies in **proxy mode**, even though they do not require writing an `@Aspect` yourself. Therefore, they share the exact same **self-invocation** issue.

### 10.1. `@Transactional`: does not trigger a new interceptor on internal calls

Illustrative example:

```java
@Service
public class PaymentService {

    public void checkout() {
        this.savePayment(); // Does not pass through the transaction proxy.
    }

    @Transactional
    public void savePayment() {
        // Expected a transaction to start when calling savePayment().
    }
}
```

If `checkout()` is called from outside while `checkout()` **has no transaction of its own** and no other transaction is active, the `@Transactional` annotation on `savePayment()` will **not open a transaction for this internal call**. That is because the transaction interceptor is never invoked at the `this.savePayment()` step.

**Important nuance:** If `checkout()` was already called through a transaction proxy and **a transaction is active**, code inside `savePayment()` can still run **within the existing transaction**. However, `savePayment()`'s **own `@Transactional` metadata is not evaluated for the internal invocation**, so it does not open a new transaction boundary according to its own attributes.

Example:

```java
@Transactional
public void checkout() {
    this.savePayment();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void savePayment() {
    // ...
}
```

When `checkout()` passes through the proxy, the outer transaction is opened. Yet `this.savePayment()` **does not enter a new interceptor**, so the `REQUIRES_NEW` configuration on `savePayment()` **neither starts a new transaction nor suspends the outer transaction** on this call path.

Requires importing `org.springframework.transaction.annotation.Transactional` and `org.springframework.transaction.annotation.Propagation`; running this in practice also requires transaction management, a transaction manager, and corresponding resources. This is only an illustrative snippet and **not** part of the standalone Maven project in section 4.

**Proper approach:** Move the `REQUIRES_NEW` operation to another Spring bean, inject that bean, and call it through the transaction proxy. Test with a real database/transaction manager to verify propagation, commit, and rollback.

### 10.2. `@Cacheable`

```java
@Service
public class ProductService {

    public Product refresh(String id) {
        return this.findById(id); // Bypasses the caching proxy at the internal step.
    }

    @Cacheable("products")
    public Product findById(String id) {
        // Read data.
    }
}
```

If `refresh()` calls `this.findById(id)`, the cache interceptor for `findById` does not run on that call step. Move the cached lookup operation to another Spring bean and call it through the bean proxy when caching semantics must be preserved. The snippet requires the corresponding classes and cache configuration and is not standalone.

### 10.3. `@Async`

```java
@Service
public class NotificationService {

    public void register() {
        this.sendEmail(); // Synchronous call inside the same target.
    }

    @Async
    public void sendEmail() {
        // Task intended to run via the async interceptor.
    }
}
```

In proxy mode, the internal call `this.sendEmail()` **does not pass through the async proxy**, so the `@Async` annotation on this method does not offload execution to an executor. If `register()` has no async mechanism of its own, `sendEmail()` executes synchronously on the calling thread. For proper async behavior, extract it into a Spring bean processed by `@EnableAsync`/Boot infrastructure, call it through the proxy, and verify thread/exception semantics.

**Learning boundary:** These transaction/cache/async examples solely illustrate the consequences of the **Spring AOP proxy boundary**; they do not replace dedicated lessons on transactions, caching, or concurrency.

## 11. Calls during the initialization lifecycle

Self-invocation does not happen only in ordinary business methods. For example:

```java
@PostConstruct
public void init() {
    this.loadData();
}
```

Because `@PostConstruct` executes during the bean initialization lifecycle, you should not rely on a finalized AOP proxy to guarantee advice for `loadData()`. Similarly, calling an advised method from a **constructor** or from code executing before the container finishes the bean lifecycle very easily bypasses interception.

If startup work needs advice, consider triggering it **after the context is ready** through a lifecycle-appropriate coordinator bean calling the target bean via a Spring reference. With Spring Boot, `ApplicationRunner`/`CommandLineRunner` can be used when appropriate, while verifying startup ordering and transactions/resources.

Do not move `this.loadData()` into `@PostConstruct` expecting the call to "go through the proxy" merely because `@Aspect` exists.

## 12. How is self-invocation different from other AOP failures?

| Symptom | Cause to check | Distinguishing clue |
| --- | --- | --- |
| `inner()` runs advice when called externally but not when called from `outer()` | **Self-invocation** via `this` | Same Spring bean/proxy; only the call path differs |
| No calls to `inner()` run advice at all | Aspect not a bean, AOP not enabled, or pointcut mismatch | Check aspect bean, auto-proxy config, advisor |
| `AopUtils.isAopProxy(service) == false` | Bean has no proxy or a non-Spring instance is used | Check `context.getBean`, registration, advisor match |
| `private` or `final` method receives no advice via class-based Spring proxy | Proxy/method-overriding limitation | Even external calls cannot rescue an unproxiable method |
| `inner()` called via proxy yet advice still does not run | Pointcut, method signature, runtime args, or advisor mismatch | Check `@Before`, class/method, proxy type, runtime match |
| Object created with `new Service()` receives no advice | Instance outside container, not wrapped in a Spring proxy | Calls on that object never enter Spring AOP |
| Aspect bean exists yet the aspect itself has no proxy | Normal Spring AOP behavior | The aspect bean is an **advisor source**, not a regular auto-proxy target |
| JDK proxy cannot be cast to implementation | Runtime type is an interface-based proxy | Inject/call via interface or use a verified class-based proxy |
| Setting `proxyTargetClass = true` still lets self-invocation bypass advice | Both JDK and CGLIB are proxy-based | Must change **the call path**, not just the proxy strategy |

### Quick diagnostic checklist

1. **Obtain the bean from Spring:** `context.getBean(...)` or constructor injection, never manual `new`.
2. **Check the proxy:** `AopUtils.isAopProxy(bean)`; remember that proxy presence **does not prove** every method has advice.
3. **Trace the call path:** place debugger breakpoints/logs in `outer()` and `inner()`; is there a `this.inner()` or implicit `inner()`?
4. **Compare:** call `inner()` directly from an external caller on the Spring proxy. If advice appears on that path and vanishes on the internal path, self-invocation is a very strong candidate cause.
5. **Check pointcut/advisor:** class, method, visibility, runtime matching, JDK/CGLIB; do not tweak the expression when the real issue is the call path.
6. **Refactor and retest:** move the method needing advice to another Spring bean, call it via dependency injection, and verify actual stdout/transaction/cache/async behavior.
7. **Regression test:** verify business behavior beyond merely counting advice logs, especially transaction propagation, rollback, and data state.

## 13. Should AspectJ weaving be used to handle self-invocation?

**Proxy-based Spring AOP** and **AspectJ weaving** are two different mechanisms:

| Proxy-based Spring AOP | AspectJ compile-time/load-time weaving |
| --- | --- |
| Creates proxies to intercept calls passing from clients through the proxy | Modifies/weaves class bytecode according to weaving configuration |
| Self-invocation `this.inner()` bypasses the proxy so `inner()`'s advice does not run | Not subject to that self-invocation limit because advice does not depend on traversing a Spring proxy |
| Suitable for most advice needs on Spring-managed beans | Handles broader join points/scopes but requires different tooling and configuration |
| `@EnableAspectJAutoProxy` is **not** a switch that enables AspectJ weaving | Requires the AspectJ compiler or weaver and corresponding weaving setup |

The Spring Framework documentation confirms that compile-time or load-time AspectJ weaving **does not suffer from the self-invocation issue of Spring AOP proxies**, because the advice behavior lives in the bytecode rather than depending on a wrapper proxy.

However, **merely adding `aspectjweaver` or `@Aspect` to the classpath does not enable weaving**. In most cases, prefer fixing the Spring bean boundary (splitting services) instead of switching the entire AOP mechanism just for a single internal call.

Specifically for `@Transactional`, `AdviceMode.ASPECTJ`/weaving requires `spring-aspects` and separate AspectJ configuration; it is not equivalent to `@EnableAspectJAutoProxy` and is not automatically activated simply by adding a Spring Boot AOP/AspectJ starter. This lesson does not walk through full weaving setup because the focus is the Spring proxy boundary.

## 14. Knowledge-check scenarios

**Scenario A.** `service.outer()` is called through a Spring AOP proxy. Inside `outer()`, the code writes `inner()` instead of `this.inner()`. Will advice targeting `inner()` run?

**Answer:** No, if it is a call to a method on the same target: shorthand `inner()` is still self-invocation on `this` and does not go back through the proxy.

**Scenario B.** Setting `@EnableAspectJAutoProxy(proxyTargetClass=true)` switches from JDK proxy to CGLIB. Will that make `this.inner()` run advice?

**Answer:** No. CGLIB is still a Spring AOP proxy; self-invocation inside the target continues to bypass the proxy.

**Scenario C.** `outer()` was advised and is running inside a transaction. It calls `this.inner()`, while `inner()` has `@Transactional(REQUIRES_NEW)`. Will a new transaction be created automatically?

**Answer:** Not for an internal call in proxy mode. `inner()` can run inside `outer()`'s existing transaction, but `inner()`'s `REQUIRES_NEW` propagation is not evaluated by the transaction interceptor for this invocation.

**Scenario D.** Moving `inner()` to `InnerService` and injecting `InnerService` into `OuterService`. When calling `innerService.inner()`, is advice guaranteed to run?

**Answer:** Only if `InnerService` is a Spring bean with a matching proxy/advisor, the method is advisable, and the caller actually invokes it through the proxy reference. Splitting the class **is not enough** without proper bean/AOP registration.

**Scenario E.** `AopUtils.isAopProxy(service)` returns `true`, yet `this.inner()` still produces no log. Is this contradictory?

**Answer:** No. `isAopProxy` checks that **the `service` reference** is a proxy; the `this.inner()` call inside the target does not traverse that proxy reference.

## 15. Official Spring references

- [Spring Framework — Proxying Mechanisms (Spring 6.2)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): directly explains self-invocation via `this`, refactoring/self-injection/`AopContext` options, and differences from weaving.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy`, AspectJ library on the classpath, auto-proxying Spring beans.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxy mode, external method call boundaries, and self-invocation.
- [Spring Framework — Understanding Transaction Proxy Infrastructure](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): role of AOP proxies and transaction interceptors.
- [Spring Framework — AopContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/AopContext.html): proxy exposure requirement and `currentProxy()`.
- [Spring Framework — AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): identifying Spring AOP proxies and related utilities.