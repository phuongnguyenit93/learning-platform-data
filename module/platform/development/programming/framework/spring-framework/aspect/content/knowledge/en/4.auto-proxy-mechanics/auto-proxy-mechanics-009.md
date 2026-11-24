# Circular Dependencies and the Risk of Unenhanced Early References in Spring AOP

## 1. The Problem to Understand

Spring AOP usually creates a **proxy** so clients invoke a Spring bean's methods through advice before or after entering the target object (**target**). When beans have a **circular dependency**, Spring may be required to hand a bean to another object **before that bean finishes its initialization lifecycle**. For a bean that should be wrapped by a Spring AOP proxy, this is a sensitive moment: clients may need the **proxy**, yet the container has only just created the **raw target**.

Three central questions:

1. In Spring's bean-creation cycle, when does an **early reference** appear?
2. How does Spring AOP coordinate with that mechanism to avoid one place holding the raw target while another holds the proxy?
3. Why is the most reliable fix **eliminating the circular dependency**, rather than trying to allow injecting an incompletely initialized bean?

**Scope:** This lesson analyzes only cases involving **Spring Framework, the Spring bean lifecycle, and Spring AOP auto-proxying**; it does not extend to standalone AOP theory, compile-time weaving, or other IoC frameworks.

## 2. Two Problems Easily Conflated

There are at least two different kinds of failures.

### 2.1. A Circular Dependency Preventing Spring From Creating Beans at All

Example:

~~~text
PaymentService
    |
    | constructor needs AuditService
    v
AuditService
    |
    | constructor needs PaymentService
    +---------------------------> PaymentService
~~~

If both constructors require an already-existing instance, Spring cannot finish creating either object first. With constructor circular dependencies like the above, the container can throw **`BeanCurrentlyInCreationException`** (usually inside the cause chain of `BeanCreationException` or `UnsatisfiedDependencyException`).

Spring AOP is not a tool for breaking constructor cycles. Configuring **`@EnableAspectJAutoProxy`** does not make this kind of cycle disappear on its own.

### 2.2. A Circular Dependency With an Early Reference That Differs From the Final Proxy

A circular dependency based on property/setter injection between **singleton beans** can sometimes be resolved by Spring handing out an **early singleton reference** after the object is allocated, before all dependencies, initialization callbacks, and BeanPostProcessors finish.

However, if Bean A must eventually be wrapped into a Spring AOP proxy:

~~~text
A raw target --------------------------> A final proxy
      |                                        ^
      | early reference                        |
      v                                        |
B holds reference to raw A          Other client receives A proxy
~~~

When B directly invokes raw A, the call path can **bypass advice**. We end up with two behaviorally non-equivalent references. This is the risk of **raw bean injected despite wrapping**.

Important: **not every circular dependency causes raw target injection**. Standard Spring AOP infrastructure has a hook to provide an **early proxy** when possible. The risk arises when it cannot guarantee the early reference matches the wrapper exposed at the end, or when a bean is created too early to receive full BeanPostProcessor processing.

## 3. Reviewing the Necessary Steps of the Spring Bean Lifecycle

For a typical singleton bean, one can picture:

~~~text
Register BeanDefinition
        |
        v
Create instance / invoke constructor
        |
        v
Populate properties / inject dependencies
        |
        v
Initialization (@PostConstruct, InitializingBean, init method...)
        |
        v
BeanPostProcessor, including Spring AOP auto-proxy infrastructure
        |
        v
Expose final bean (may be a proxy)
~~~

The detailed sequence has many hooks, so the diagram is intentionally simplified. Spring AOP proxy creation is performed via **`BeanPostProcessor`**; with the typical auto-proxy creator, a bean can be wrapped in the post-initialization step. In an eligible singleton cycle, Spring has an additional path to supply an **early singleton reference** between instantiation and completion of initialization.

Therefore:

- **Raw bean:** the target instance created by the constructor; cannot be assumed to be an AOP-processed object yet.
- **Early reference:** a reference exposed by the container while a singleton is under creation and another bean needs it; its value may be the raw object or a wrapper/proxy supplied by a post-processor.
- **Final exposed bean:** the reference normal users receive from `ApplicationContext.getBean(...)` after initialization succeeds.
- **AOP proxy:** a wrapper that can execute interceptors/advice for matching methods when clients call through it.

A bean having been allocated does not mean it already has all dependencies, has run initialization, or already has an AOP proxy. Avoid invoking business logic on an early reference simply because the reference variable is already non-`null`.

## 4. Why Could Spring Sometimes Resolve Setter-Based Cycles?

Consider two singletons:

~~~java
class Alpha {
    private Beta beta;

    void setBeta(Beta beta) {
        this.beta = beta;
    }
}

class Beta {
    private Alpha alpha;

    void setAlpha(Alpha alpha) {
        this.alpha = alpha;
    }
}
~~~

This is a **graph-describing fragment**, without bean registration annotations. When the container is allowed to attempt resolving singleton cycles, an execution sequence can be:

1. Start creating **Alpha**: its constructor does not need Beta, so a raw instance exists.
2. The container records that Alpha is currently in creation and can provide a **singleton factory** for early reference requests.
3. While injecting `beta`, Spring needs to create **Beta**.
4. When injecting `alpha` into Beta, Spring detects Alpha is in creation; if conditions allow, it obtains **Alpha's early reference**.
5. Finish Beta and assign Beta to Alpha.
6. Run initialization, BeanPostProcessors, and decide Alpha's final reference.

This mechanism **cannot apply when Alpha's constructor needs Beta and Beta's constructor needs Alpha**, because at the point where the cycle closes, neither instance has been created enough to be placed into the early singleton cache.

One consequence: the ability to resolve a circular dependency depends on **dependency kind, bean scope, container settings, and post-processors**; do not read "Spring supports circular references" as a guarantee that every cycle can create beans.

## 5. Three-Tier Singleton Reference Mechanism, at the Level Needed for AOP

In Spring's implementation, singleton reference resolution can be understood via three storage tiers:

| Tier / common name in implementation | What it holds | Role |
| --- | --- | --- |
| `singletonObjects` | Fully exposed singletons | Normal bean lookup path |
| `earlySingletonObjects` | Already-created early references | Reuses the same early reference if requested again later |
| `singletonFactories` | Factories capable of supplying early references | Allows BeanPostProcessors to create an early wrapper when needed |

While a bean is still initializing, Spring can register a factory. If another bean needs it, the factory is used to get an early reference. The object obtained from the factory **does not have to be the raw target**. Spring AOP infrastructure can participate to return a proxy.

~~~text
                  Bean A initializing
                           |
                    create raw target
                           |
                  singleton factory A
                           |
                  B needs dependency A
                           |
                           v
                 getEarlyBeanReference
                           |
             +-------------+-------------+
             |                           |
       early proxy                  raw target
     (if creatable)             (if not wrapped)
             |                           |
             v                           v
        B holds proxy               B holds raw target
             |                           |
             v                           v
   can be consistent with         risk of different behavior
   final exposed bean             compared to final proxy
~~~

This diagram illustrates **possibilities**, not a promise that every aspect is resolved by Spring in time to create an early proxy. A circular dependency can be rejected before an early reference exists, or fail when the final proxy differs from the injected reference.

## 6. Key Hook: `getEarlyBeanReference(...)`

Spring's infrastructure defines the callback on **`SmartInstantiationAwareBeanPostProcessor`**:

~~~java
Object getEarlyBeanReference(Object bean, String beanName)
~~~

This is an **illustrative API signature**, not a standalone Java program. The callback gives a post-processor the opportunity to provide a wrapper before the target is fully initialized.

Spring AOP's **`AbstractAutoProxyCreator`** implements this path. Conceptually:

~~~text
getEarlyBeanReference(rawA, "a")
      |
      +-- determine whether the bean needs a proxy
      |
      +-- if needed, may return an AOP proxy for rawA
      |
      +-- record state to avoid creating another
          inconsistent proxy at the end of initialization
~~~

Afterward, the post-processor handles the rest of the lifecycle knowing the bean may already have been given an early proxy. The goal is for **the early reference and the final exposed reference to be compatible**, rather than letting B hold the raw target while other clients receive a proxy with different behavior.

Two limits must be stated accurately:

- This callback is a **conditional** support mechanism. It **does not** make constructor-injection cycles solvable.
- `SmartInstantiationAwareBeanPostProcessor` has a default implementation returning the original bean; a custom post-processor or an unsuitable initialization scenario can still leave a **raw reference**.

Do not rely on "Spring automatically wraps all early references" to design circular dependency graphs.

## 7. When the Raw Target Was Injected Yet the Final Bean Becomes a Proxy

Suppose A is a service that must be Spring-AOP-proxied, while B holds an early reference to A:

~~~text
B.a ----------------------------------> A raw target

context.getBean(AService.class) ------> A final proxy
                                           |
                                           v
                                        A raw target
~~~

If B calls `a.process()` through the raw target, Spring AOP advice may not run. Other callers invoking through `A final proxy` do run the advice. The two call paths can produce different side-effect outcomes (such as missing audit or tracing), even though both reach the same target's business logic.

To prevent this state, Spring by default **does not allow raw injection despite the bean later being wrapped**. When an inconsistency is detected and dependent beans actually received the raw instance, Spring can throw **`BeanCurrentlyInCreationException`** with a description along the lines of:

~~~text
Bean ... has been injected into other beans [...] in its raw version
as part of a circular reference, but has eventually been wrapped.
~~~

The message above is a **sample excerpt**, not expected stdout of a specific program. Exact wording depends on the Spring version and bean-creation path.

On `AbstractAutowireCapableBeanFactory`'s API, there are two distinct options:

- **`setAllowCircularReferences(boolean)`**: whether the container attempts to handle certain circular dependencies.
- **`setAllowRawInjectionDespiteWrapping(boolean)`**: whether to accept a raw instance having been injected even though the final bean is wrapped afterward; default **`false`**.

Enabling raw injection despite wrapping to hide the error is risky because it allows calling code to bypass the AOP proxy. It is not a sound design fix for a service needing advice.

## 8. Runnable Program: Acyclic Design, Consistent Proxy

We build an example using **Spring Framework 6.2.12, Java 17+, Maven 3.9+**. The client uses `PaymentService`. The aspect logs through an independent `AuditRecorder` bean; the aspect **does not inject `PaymentService` back**.

~~~text
spring-aop-early-reference/
├── pom.xml
└── src/main/java/demo/
    ├── PaymentService.java
    ├── PaymentServiceImpl.java
    ├── AuditRecorder.java
    ├── LoggingAspect.java
    ├── CheckoutClient.java
    ├── AppConfig.java
    ├── CycleProbe.java
    └── App.java
~~~

### 8.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-early-reference</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext` and brings in the needed Spring AOP support; `aspectjweaver` provides pointcut/advice types for `@AspectJ` syntax. The approach here **remains Spring AOP proxying**, not class weaving with an AspectJ agent.

### 8.2. Service Interface and Implementation

**src/main/java/demo/PaymentService.java**

~~~java
package demo;

public interface PaymentService {
    String pay(String orderId);
}
~~~

**src/main/java/demo/PaymentServiceImpl.java**

~~~java
package demo;

public class PaymentServiceImpl implements PaymentService {

    @Override
    public String pay(String orderId) {
        System.out.println("SERVICE " + orderId);
        return "paid:" + orderId;
    }
}
~~~

The implementation does not depend on the aspect or recorder. Because the service has an interface, the client retrieves the bean by `PaymentService`; this matches the default JDK dynamic proxy of the plain Spring Framework configuration in the example.

### 8.3. Aspect Collaborator

**src/main/java/demo/AuditRecorder.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class AuditRecorder {

    private final AtomicInteger count = new AtomicInteger();

    public void record(String orderId) {
        count.incrementAndGet();
        System.out.println("AUDIT " + orderId);
    }

    public int count() {
        return count.get();
    }
}
~~~

`AuditRecorder` is independent and does not inject `PaymentService`. The `AtomicInteger` field keeps the example free from unsafe `int` increments in concurrent environments. This is only an in-memory counter; a real system needs an appropriate audit solution and a clear error policy.

### 8.4. Aspect Depending Only One-Way on the Recorder

**src/main/java/demo/LoggingAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class LoggingAspect {

    private final AuditRecorder recorder;

    public LoggingAspect(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(* demo.PaymentServiceImpl.pay(..))")
    public void beforePay(JoinPoint joinPoint) {
        String orderId = (String) joinPoint.getArgs()[0];
        recorder.record(orderId);
    }
}
~~~

The class has **`@Aspect`** so Spring AOP reads its advice. The `LoggingAspect` instance will be registered with `@Bean`, so `@Component` is not needed. The aspect receives `AuditRecorder` via its constructor, **not** the service being advised, and creates no circular dependency graph.

### 8.5. Client Receiving the Service Only From Spring

**src/main/java/demo/CheckoutClient.java**

~~~java
package demo;

public class CheckoutClient {

    private final PaymentService paymentService;

    public CheckoutClient(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        String result = paymentService.pay(orderId);
        System.out.println("CLIENT " + result);
    }
}
~~~

The client does not use `new PaymentServiceImpl()`. Spring resolves `PaymentService` from the container and can inject **the proxy** into the client.

### 8.6. Explicit, Acyclic Bean Configuration

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }

    @Bean
    public LoggingAspect loggingAspect(AuditRecorder recorder) {
        return new LoggingAspect(recorder);
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentServiceImpl();
    }

    @Bean
    public CheckoutClient checkoutClient(PaymentService paymentService) {
        return new CheckoutClient(paymentService);
    }
}
~~~

The dependencies form a directed acyclic graph:

~~~text
CheckoutClient ---> PaymentService (proxy) ---> PaymentServiceImpl
LoggingAspect ----> AuditRecorder
                       ^
                       |
              advice invoked on pay(...)
~~~

In terms of dependency injection, **`LoggingAspect` does not depend on `PaymentService`**; a pointcut condition intercepting a service method **is not equivalent to a Java dependency from the aspect onto the service**.

`@EnableAspectJAutoProxy` enables auto-proxying and aspect processing. `@Bean` registers the instances with Spring. `proxyBeanMethods = false` on `@Configuration` only controls interception of calls between `@Bean` factory methods; **it does not disable the Spring AOP proxy of `PaymentService`**.

### 8.7. Experiment With a Rejected Constructor Cycle

We create an **independent** second context solely to prove that a constructor cycle cannot be rescued by early singleton references. It contains neither `AppConfig` nor any service/bean from the success scenario, avoiding mixing failure causes.

**src/main/java/demo/CycleProbe.java**

~~~java
package demo;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CycleProbe {

    private CycleProbe() {
    }

    static class A {
        A(B b) {
        }
    }

    static class B {
        B(A a) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CycleConfig {
        @Bean
        A a(B b) {
            return new A(b);
        }

        @Bean
        B b(A a) {
            return new B(a);
        }
    }

    public static void demonstrate() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.setAllowCircularReferences(false);
            context.register(CycleConfig.class);

            try {
                context.refresh();
                System.out.println("CYCLE unexpectedly created");
            } catch (BeansException exception) {
                System.out.println("CYCLE rejected");
            }
        }
    }
}
~~~

`context.setAllowCircularReferences(false)` is called before `refresh()` so the test is consistent and removes any expectation that the container will try to resolve the cycle. Even when cycles are allowed, **constructor `A(B)` ↔ `B(A)`** cannot be completed using normal early references.

We only print the fixed line **`CYCLE rejected`** inside the catch block to avoid coupling the lesson to long stack-trace messages that may change between Spring releases. Catching here is only for **an error-demonstration program**, not how a production application should swallow startup failures.

### 8.8. Running Both the Normal Case and the Cycle Error

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            PaymentService service =
                    context.getBean(PaymentService.class);
            CheckoutClient client =
                    context.getBean(CheckoutClient.class);
            AuditRecorder recorder =
                    context.getBean(AuditRecorder.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(service));
            client.checkout("ORD-59");
            System.out.println("AUDIT_COUNT " + recorder.count());
        }

        CycleProbe.demonstrate();
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q clean compile exec:java
~~~

**Logical lines printed by the example itself:**

~~~text
IS_PROXY true
AUDIT ORD-59
SERVICE ORD-59
CLIENT paid:ORD-59
AUDIT_COUNT 1
CYCLE rejected
~~~

Spring or Maven may print startup warnings/errors for the probe context to stderr; those lines do not belong to the logical stdout listed above.

Meaning:

- **`IS_PROXY true`**: the regular service bean from the context was exposed by Spring AOP as a proxy.
- **`AUDIT`** appears before **`SERVICE`**: the `@Before` advice was indeed invoked before the target.
- **`AUDIT_COUNT 1`**: the Spring-managed recorder logged exactly one event.
- **`CYCLE rejected`**: the second context hit a constructor dependency cycle and failed on `refresh()`; the error is caught intentionally so the program proceeds to exit normally.

The example does not try to force a setter cycle to "succeed at all costs". The goal is to show a solution that can prove **the same proxy passes through advice** and **the dependency graph is acyclic**.

## 9. A Common AOP Design Mistake: An Aspect Depending on the Very Service It Advises

Consider the following dangerous configuration, **an anti-pattern example only** — do not add it directly to the runnable project in section 8:

~~~java
@Aspect
@Component
class TraceAspect {
    private final OrderService orderService;

    TraceAspect(OrderService orderService) {
        this.orderService = orderService;
    }

    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        // advice
    }
}

@Service
class OrderServiceImpl implements OrderService {
    private final TraceAspect traceAspect;

    OrderServiceImpl(TraceAspect traceAspect) {
        this.traceAspect = traceAspect;
    }

    public void submit() {
        // business logic
    }
}
~~~

To compile the fragment above, you would need the `OrderService` interface, Spring/AspectJ imports, and the corresponding package; this is **not a standalone runnable example**. The graph is:

~~~text
OrderServiceImpl -> TraceAspect -> OrderServiceImpl
~~~

Both sides require constructor dependencies. When Spring tries to create a proxy for the service, it also has to evaluate advisors from the aspect, making initialization order harder to diagnose. Still, the underlying design cause remains **a circular dependency between beans**.

**There is no absolute rule forbidding an aspect from injecting a service it advises** in every single case. However, doing so easily creates a circular graph or advice re-entrancy if the aspect calls methods matching the pointcut. A cleaner approach is for the aspect to depend on an **`AuditRecorder`**, **`EventPublisher`**, or independent collaborator; the service carries only business logic and does not inject the aspect.

## 10. If the Early Reference Is Already a Proxy, What Risks Remain?

Even when an `AbstractAutoProxyCreator` can return an **early proxy**, you must still understand the following limitations:

1. **The target has not finished initialization**. The proxy can point to an object whose fields/properties or init callbacks have not yet completed. If a caller invokes a method too early, the method may read unready state.
2. **Advisor selection can be affected by beans still under creation**. The aspect or the auto-proxy creator's dependencies may also participate in cycles, making wrapper determination hard to guarantee.
3. **BeanPostProcessor ordering matters greatly**. Custom BeanPostProcessors that do not handle early references, or that create different wrappers early vs. late, can cause the final object to differ from the early object.
4. **Some beans initialize too early for full auto-proxying**. In particular, BeanPostProcessors and the beans they directly depend on can be created while the container is still registering post-processors. A log like *not eligible for getting processed by all BeanPostProcessors* is a sign to investigate.
5. **The proxy still only intercepts eligible method invocations**. Self-invocation on the target bypasses the proxy, whether the proxy was created early or late.

Therefore, "Spring can handle setter cycles" does not mean "all Spring AOP advice is safe and all dependencies are initialized".

## 11. How to Fix: Break the Circular Dependency in Design

### 11.1. Extract an Independent Shared Bean

Broken graph:

~~~text
OrderService -> AuditService -> OrderService
~~~

Refactor to:

~~~text
OrderService --> PaymentRepository
TraceAspect  --> AuditRecorder
OrderService <-- Spring AOP proxy/advice matching (not a DI arrow)
~~~

This is the recommended solution. Place audit recording into `AuditRecorder` or an independent event publisher, **without injecting `OrderService` back** just to know an order ID or result. Advice can obtain arguments, signatures, and return values from `JoinPoint`/the respective advice parameters without creating a reverse dependency on the service.

When referencing data from a single invocation, pass that data via method/advice parameters; the service bean does not need to reference the aspect back.

### 11.2. Using `ObjectProvider` When Deferred Lookup Is Truly Needed

Spring can inject `ObjectProvider<T>` to **defer bean retrieval**:

~~~java
class DeferredCaller {
    private final org.springframework.beans.factory.ObjectProvider<OrderService>
            serviceProvider;

    DeferredCaller(
            org.springframework.beans.factory.ObjectProvider<OrderService>
                    serviceProvider) {
        this.serviceProvider = serviceProvider;
    }

    void callLater() {
        OrderService service = serviceProvider.getObject();
        service.submit();
    }
}
~~~

This is an illustrative fragment requiring a proper `OrderService.submit()` definition and bean registration in the context. `ObjectProvider` causes the dependency to be resolved **at `getObject()` time**, not when the constructor receives the provider.

This is **not an automatic cure for circular dependencies**. If `getObject()` is called right inside the constructor or `@PostConstruct` while the graph is still unstable, errors can still happen. When deferred lookup is truly needed, there must be a clear lifecycle boundary and a valid architectural reason.

### 11.3. `@Lazy` Can Defer Timing, Not Replace Design

Illustrative declaration:

~~~java
SomeClient(@Lazy OrderService orderService) {
    this.orderService = orderService;
}
~~~

Import `org.springframework.context.annotation.Lazy` when using this. With dependency injection, `@Lazy` can create a **lazy-resolution proxy** for the injection point and resolve the target bean only when a method is used. This dependency-deferring proxy **is not necessarily the Spring AOP proxy** executing advice.

If a method is called too early while the bean cycle still exists, the problem returns. Use `@Lazy` only after understanding at which phase the dependency needs to be used; for critical AOP graphs, refactoring out the cycle remains the preferred path.

### 11.4. Do Not Use Cycle-Allowing Configuration as a Default Solution

In **plain Spring Framework**, the bean factory can be configured to attempt resolving circular references, and `AbstractAutowireCapableBeanFactory`'s default for `allowCircularReferences` is **`true`**. In modern **Spring Boot** releases, the property `spring.main.allow-circular-references` defaults to **`false`**.

Trying to enable the property below in Boot:

~~~properties
spring.main.allow-circular-references=true
~~~

cannot resolve impossible constructor cycles and does not guarantee consistent Spring AOP proxies in every case. It is a temporary compatibility setting when migrating legacy systems, requiring evaluation, testing, and a plan to eliminate the cycle. Do not choose it as the first fix.

Enabling `setAllowRawInjectionDespiteWrapping(true)` to force the container to accept raw references is also not recommended; doing so can leave a dependency in some bean without expected advice running.

## 12. How to Investigate When Application Startup Fails

### Step 1: Draw the Dependency Graph From the Exception Chain

For example, logs may show multiple layers:

~~~text
UnsatisfiedDependencyException
  caused by BeanCurrentlyInCreationException
    "Requested bean is currently in creation ..."
~~~

Read the **bean names** in the exception and trace the cycle: service → collaborator → aspect → service; or service A → service B → service A. Do not read only the last class in the stack trace.

### Step 2: Determine Whether It Is a Constructor Cycle or an Early-Reference-Capable Cycle

- **Constructor ↔ constructor**: refactor; normally cannot be resolved via the early reference mechanism.
- **Singleton setter/property cycle**: early references may exist, yet container conditions and the auto-proxy creator must be analyzed.
- **Prototype or special scopes**: do not assume it can be resolved like singletons.
- **Aspect ↔ advised service**: inspect the DI graph and whether the aspect calls back into the service.

### Step 3: Check Which Beans Should Have Been Proxied

When the context can initialize, verify the bean obtained through the context:

~~~java
Object service = context.getBean("paymentService");

boolean isProxy =
        org.springframework.aop.support.AopUtils.isAopProxy(service);
System.out.println("IS_PROXY " + isProxy);
~~~

This is a debug fragment, runnable only when a `context` variable and a bean named `paymentService` exist. Do not infer that **every method** is intercepted solely from `isProxy == true`; test an invocation matching the pointcut.

### Step 4: Look for Signs of Raw Injection or Premature Initialization

Strings to watch for:

~~~text
Bean ... injected ... in its raw version
... but has eventually been wrapped

Bean ... is not eligible for getting processed
by all BeanPostProcessors
~~~

These are **message patterns**, not log output from a running system. The raw injection message suggests the final wrapper differs from the reference already handed to a dependent bean. The `BeanPostProcessor` message suggests a bean was created too early and missed full post-processing.

Do not try to fix this by removing the exception guard. Identify which bean triggers premature initialization and change the dependency graph or bean-creation phase configuration.

### Step 5: Verify Actual Calls Go Through the Proxy

If the context initializes successfully yet advice does not run:

- Check whether the method and signature match the pointcut.
- Check whether the caller uses the Spring-managed proxy or directly `new`s the target.
- Check whether there is self-invocation via `this.method()` inside the target.
- If custom wrappers/BeanPostProcessors exist, check whether the client holds **the final proxy** or a raw/early object.
- With JDK proxies, inject by interface if interfaces are implemented; do not cast the proxy to the implementation class arbitrarily.

## 13. Common Errors and Their Impacts

| Symptom | Possible cause | Action |
| --- | --- | --- |
| Startup reports `BeanCurrentlyInCreationException` | Constructor cycle, or raw bean was injected before being wrapped | Read root cause, draw dependency graph, break the cycle |
| Setter cycle used to work in plain Framework, fails after moving to Spring Boot | Boot rejects circular references by default | Refactor graph; do not enable the cycle-allowing property by default |
| Client A gets advice, Client B does not | B holds raw target or takes a direct path bypassing proxy | Verify proxy/target identity and injection sites; remove cycle |
| Aspect holds a reference to the service it advises | Dependency graph is hard to initialize or advice calls back into service | Extract independent collaborator; use `JoinPoint` data |
| Bean reports "not eligible for auto-proxying" | Premature initialization during the BeanPostProcessor phase | Inspect custom BPPs and prematurely initialized dependencies |
| `@Lazy` clears startup error but fails on call | Deferred lookup still triggers a cycle at runtime | Redesign dependency relationships; check `getObject()` timing |
| Allowed raw injection and then lost advice | Dependent bean holds raw target instead of final proxy | Do not use raw path; refactor and test proxy behavior |
| `AopUtils.isAopProxy` returns true, yet expected advice does not run | Proxy is from another advisor or pointcut does not match | Check aspect bean, advisors, and actual invocation |
| Referencing a bean before init finishes causes state bugs | Early reference invoked too early | Do not call business logic in constructors/init callbacks of a cyclic graph |

## 14. Key Distinctions to Remember

**A circular dependency** is a **dependency graph** issue. **A raw bean being injected and then wrapped in a proxy** is a **lifecycle reference-inconsistency** issue. The two are related, not identical: having a cycle does not necessarily mean a raw mismatch occurs, and having an early proxy does not make constructor cycles disappear.

**An AOP proxy** can route calls through advice, but only when the caller actually holds and uses the right proxy. An early reference can be a proxy if Spring AOP infrastructure can supply one; calling an early reference does not automatically mean bypassing AOP.

**Enabling circular references** only allows the container to attempt certain initialization paths. It does not make every dependency graph valid, nor is it a policy guaranteeing a bean has finished initialization when called.

**Reading the exception early** is usually more reliable than finding ways to suppress the exception: if the container reports a bean was injected raw and then wrapped, the warning aims to prevent inconsistent AOP behavior across callers.

## 15. Self-Assessment Questions

**1. Why can a constructor cycle `A(B)` and `B(A)` not be resolved using early singleton references?**

Because both constructors require an instance of the other before either instance can be created to register as an early reference.

**2. Is an early reference always the raw target?**

No. Spring AOP's auto-proxy creator can provide an early wrapper via `getEarlyBeanReference`. That depends on the situation and post-processors, not a universal guarantee.

**3. If one dependent bean holds the raw target while `context.getBean(...)` returns a proxy, what is the risk?**

Calls through the raw target can bypass advice while calls through the proxy run advice, leading to inconsistent cross-cutting behavior.

**4. Is `setAllowCircularReferences(true)` equivalent to `setAllowRawInjectionDespiteWrapping(true)`?**

No. The first allows attempting to handle circular references; the second allows a raw bean to stay injected even if the final bean is wrapped, a situation Spring avoids by default.

**5. Why can an aspect injecting the service it advises cause problems?**

Because the aspect and auto-proxy creator must participate in deciding how to advise the service, while the dependency graph may require the service to be finished before the aspect can be created. When the reverse direction exists, it easily causes a cycle or premature initialization.

**6. Does using `ObjectProvider` or `@Lazy` fix the root cause of a cycle?**

No. They defer when the dependency is resolved. If logic invokes it too early or the graph still contains an unresolvable cycle, failures still occur.

**7. After refactoring, what must be checked to prove AOP works?**

The bean initializes successfully, the service retrieved from the context is the appropriate proxy, advice is invoked before/after the expected method, and dependents no longer hold raw targets bypassing the proxy.

## 16. Official Spring Framework Documentation

- **Spring Framework — Dependency Injection (Circular dependencies)**: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- **Spring Framework — BeanPostProcessor and auto-proxying**: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- **Spring Framework API — AbstractAutoProxyCreator#getEarlyBeanReference**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html
- **Spring Framework API — AbstractAutowireCapableBeanFactory#setAllowCircularReferences / setAllowRawInjectionDespiteWrapping**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Boot — Common Application Properties (allow-circular-references)**: https://docs.spring.io/spring-boot/appendix/application-properties/index.html

**Lesson conclusion:** Circular dependencies can force Spring to hand out an early reference before a bean completes its lifecycle. Spring AOP infrastructure can provide an **early proxy** to stay consistent with the final proxy, yet not every cycle or custom post-processor is safe. Designing acyclic bean dependencies, registering aspects cleanly, and verifying calls go through the Spring proxy is the reliable way to prevent raw references from silently bypassing advice.
