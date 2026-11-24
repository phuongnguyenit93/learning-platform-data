# Injecting Dependencies into an Aspect via Spring

## 1. Objectives and Scope

A Spring aspect often does not perform all work by itself. For example, advice may need to send events to an audit-recording bean, use a shared counter, or call an infrastructure service. Spring can **inject those beans directly into the aspect** just like regular Spring beans. For this to work, **the aspect must be registered and managed in the `ApplicationContext`**, and the Spring AOP infrastructure must be enabled to use its advice.

After this lesson, you can:

- Register an `@Aspect` class as a Spring bean using `@Component` or `@Bean`.
- Use **constructor injection** to provide dependencies to an aspect.
- Explain the relationship order between the Spring container, aspect bean, collaborator bean, advisor, and service proxy.
- Observe the same dependency bean being used from advice and from a client retrieving beans in the context.
- Distinguish **injecting a dependency into an aspect** from **injecting a service proxy into a client**.
- Diagnose missing beans, duplicate beans, circular dependencies, instantiating aspects with `new`, and scope or shared-data issues.

**Limitation:** This lesson only covers dependency injection in **proxy-based Spring AOP**. General AOP topics and AspectJ weaving outside Spring are not covered here.

## 2. An Aspect Is a Spring-Managed Bean

Three roles must be distinguished:

| Component | How does Spring use it? |
| --- | --- |
| `@Aspect` class | Declares pointcuts/advice; this annotation alone **does not automatically register a bean** |
| Aspect bean | Instance managed by `ApplicationContext`; can receive dependencies via constructor, `@Autowired`, `@Value`, etc. |
| Service proxy | Object provided by Spring AOP so that service calls pass through the appropriate interceptor/advice chain |

If the `AuditAspect` class has `@Aspect` and `@Component`, component scan can register it. Spring resolves constructor dependencies before the aspect is used. When Spring AOP reads advice from the aspect bean and creates a proxy for a matching service, calls through the proxy can execute the advice; the advice uses the previously injected dependency.

~~~text
                  ApplicationContext
                           |
          +----------------+----------------+
          |                |                |
    AuditStore bean   AuditAspect bean   OrderServiceImpl bean
          |                ^                |
          +-- inject ------+                |
                           |                |
                  @Before advice            |
                           +----- advisor --+
                                             |
                                         Spring proxy
                                             |
                                  App -> OrderService.submit()
~~~

`@Aspect` serves to identify AOP declarations; `@Component` or `@Bean` serves to **register the aspect as a bean**. Dependency injection is performed by the Spring container; advice runs when **the method matches the pointcut and the call passes through the Spring proxy**. Successful injection does not by itself guarantee that advice will run.

## 3. Runnable Example: An Aspect Receiving an AuditStore

Suppose `OrderService` processes order IDs. Each time the client calls `submit(...)`, Spring AOP triggers a `@Before` advice; the advice receives `AuditStore` via its constructor and asks that bean to record an event. This is a plain Spring Framework example with **Java 17+**, **Maven 3.9+**, and **Spring Framework 6.2.12**, requiring no Spring Boot or database.

Project structure:

~~~text
spring-aop-aspect-injection/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AppConfig.java
    ├── AuditStore.java
    ├── AuditAspect.java
    ├── OrderService.java
    └── OrderServiceImpl.java
~~~

### 3.1. Maven dependencies

Create **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-aspect-injection</artifactId>
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

`spring-context` provides the annotation container and pulls in required Spring modules, including Spring AOP. `aspectjweaver` provides AspectJ types and supports parsing `@AspectJ`-style pointcut expressions. The application **does not enable AspectJ weaving**; Spring still intercepts calls via proxies.

### 3.2. Create the Dependency Bean That the Aspect Will Use

**src/main/java/demo/AuditStore.java**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class AuditStore {

    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String message) {
        events.add(message);
        System.out.println("AUDIT " + message);
    }

    public int size() {
        return events.size();
    }
}
~~~

`@Component` makes `AuditStore` a candidate for component scanning. It gets the default bean name `auditStore`. This instance is responsible for storing illustrative events in memory. `CopyOnWriteArrayList` enables concurrency-safe add/read operations for a small example; in production applications with many events, choose an appropriate storage and synchronization mechanism rather than keeping all events unboundedly in a singleton.

Notice: `AuditStore` is a **regular Spring bean** and does not need to know it is being called from advice. The aspect depends on it, not the other way around.

### 3.3. Create the Service Contract and Bean

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String submit(String orderId);
}
~~~

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public String submit(String orderId) {
        System.out.println("SERVICE submit " + orderId);
        return "created:" + orderId;
    }
}
~~~

`@Service` helps Spring register `OrderServiceImpl` via component scan. The business method is unaware of auditing. Audit recording happens from the advice applied to service calls through the Spring proxy.

### 3.4. Injecting Dependencies via the Aspect's Constructor

**src/main/java/demo/AuditAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {

    private final AuditStore auditStore;

    public AuditAspect(AuditStore auditStore) {
        this.auditStore = auditStore;
    }

    @Before("execution(* demo.OrderServiceImpl.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        Object orderId = joinPoint.getArgs()[0];
        auditStore.record("submit " + orderId);
    }
}
~~~

This is the core of the lesson:

1. **`@Aspect`** declares that the class contains advice for Spring AOP to read.
2. **`@Component`** lets the component scanner discover `AuditAspect` and register a bean with the default name `auditAspect`.
3. **`private final AuditStore auditStore`** is a dependency of the aspect instance. The class does not instantiate `AuditStore` itself.
4. The constructor **`AuditAspect(AuditStore auditStore)`** tells Spring that the instance needs a bean of type `AuditStore`. Because this is the sole constructor, Spring can automatically select it without `@Autowired`.
5. **`@Before(...)`** runs before the target method if the call matches and passes through the proxy. The advice uses **the injected `auditStore` field itself** to record the event.

The pointcut `execution(* demo.OrderServiceImpl.submit(..))` targets the service's `submit` implementation method. Injecting a dependency does not directly affect pointcut matching conditions.

The `beforeSubmit` method receives `JoinPoint` supplied by the advice infrastructure at runtime, **not a constructor dependency injected by the container**. `JoinPoint` holds data about the current call such as arguments and signature; `AuditStore` is a Spring bean with its own lifecycle.

### 3.5. Configuring Spring AOP and Component Scan

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

- `@Configuration`: marks Spring's Java configuration source.
- `@ComponentScan(basePackages = "demo")`: registers `AuditStore`, `AuditAspect`, and `OrderServiceImpl` via stereotype annotations.
- `@EnableAspectJAutoProxy`: enables Spring AOP infrastructure to automatically detect advice from registered aspects and create proxies for service beans that have matching advisors.

In this plain Spring Framework example, if `@EnableAspectJAutoProxy` is omitted, constructor injection into `AuditAspect` can still work because the aspect is still a component; however, its advice will not automatically be applied to `OrderServiceImpl` without equivalent AOP infrastructure. Conversely, merely enabling auto-proxy without registering the aspect or `AuditStore` is also not enough.

### 3.6. Running the Application and Verifying Both Injection and Advice

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println(
                    "ASPECT_BEAN " + context.containsBean("auditAspect"));
            System.out.println(
                    "STORE_BEAN " + context.containsBean("auditStore"));

            OrderService service = context.getBean(OrderService.class);
            AuditStore store = context.getBean(AuditStore.class);

            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));
            System.out.println("COUNT_BEFORE " + store.size());

            String result = service.submit("ORD-42");
            System.out.println("RESULT " + result);
            System.out.println("COUNT_AFTER " + store.size());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

**Expected logical output**, excluding Maven-specific messages or logging output:

~~~text
ASPECT_BEAN true
STORE_BEAN true
IS_PROXY true
COUNT_BEFORE 0
AUDIT submit ORD-42
SERVICE submit ORD-42
RESULT created:ORD-42
COUNT_AFTER 1
~~~

Reading each stage:

- **`ASPECT_BEAN true`**: the aspect is already a bean, so Spring has the opportunity to inject `AuditStore`.
- **`STORE_BEAN true`**: the `AuditStore` dependency is also registered.
- **`IS_PROXY true`**: the service object retrieved from the context is wrapped by Spring in an AOP proxy; this example has an advisor matching `submit(...)`.
- **`COUNT_BEFORE 0`**: the store bean has not recorded any events yet.
- **`AUDIT submit ORD-42`**: the proxy triggers `@Before`; the advice calls a method on the injected dependency.
- **`SERVICE submit ORD-42`**: the business method runs after the advice.
- **`COUNT_AFTER 1`**: the same `AuditStore` bean that `App` retrieved from the context has received one more event.

With the default configuration, these `@Component` beans belong to **singleton scope**, so Spring supplies one shared `AuditStore` instance to `AuditAspect` and to `App`. When scopes are changed, one cannot assume by default that both consumers always see the exact same instance.

## 4. The Nature of Constructor Injection in an Aspect

Spring instantiates an aspect just like a bean with dependencies:

~~~text
@Component AuditStore
        |
        v
Spring can create the AuditStore bean
        |
        v
@Component @Aspect AuditAspect(AuditStore)
        |
        +-- resolve constructor argument by bean type
        +-- pass AuditStore into constructor
        +-- store dependency in final field
        |
        v
Spring AOP reads advice / advisors from the aspect bean
        |
        v
Service proxy invokes configured advice
        |
        v
AuditAspect.beforeSubmit(...) uses auditStore
~~~

The diagram illustrates **dependency relationships**, not necessarily that all beans in every application are initialized in a rigid order. The container may create other singletons earlier or later depending on the dependency graph and configuration.

**Why use constructor injection?**

- The aspect has required dependencies and is initialized in a complete state; there is no state where the object is constructed yet required business fields remain unassigned.
- `final` fields indicate the reference cannot be altered after construction.
- When unit testing the internal logic of the aspect in Java, a fake/stub `AuditStore` can be passed explicitly.
- The constructor accurately describes the dependency graph, allowing missing-bean errors to surface during container startup.

`@Autowired` on a single constructor is **not required** with Spring's modern constructor injection mechanism. If there are multiple constructors, it must be clear which constructor is selected; `@Autowired` can be used according to Spring's constructor resolution rules.

### Constructor Injection vs. Advice Methods

Do not confuse:

~~~java
public AuditAspect(AuditStore auditStore) { ... }
~~~

with:

~~~java
@Before("execution(* demo.OrderServiceImpl.submit(..))")
public void beforeSubmit(JoinPoint joinPoint) { ... }
~~~

The constructor is called by Spring to **create the aspect bean** and supply `AuditStore`. The advice is called by the AOP interceptor **every time a matching call goes through the proxy**; the `JoinPoint` object reflects the current invocation.

You cannot expect Spring to automatically inject an arbitrary service bean into any parameter of a `@Before` method. For persistent dependencies, use the constructor or bean injection mechanisms. For invocation data, use `JoinPoint` or appropriate argument binding.

## 5. Alternative: Registering the Aspect and Dependencies via @Bean

Without component scanning, Spring still injects dependencies into an aspect registered via Java configuration. To try this approach separately, **completely replace** the contents of `src/main/java/demo/AppConfig.java` in the example with:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    public AuditAspect auditAspect(AuditStore auditStore) {
        return new AuditAspect(auditStore);
    }

    @Bean
    public OrderService orderService() {
        return new OrderServiceImpl();
    }
}
~~~

In this variant, `@ComponentScan` has been removed, so leaving `@Component` or `@Service` on the classes **does not cause them to be registered twice**. Only the three `@Bean` methods above create the three corresponding beans. Because the bean names `auditStore` and `auditAspect` remain unchanged and `App` looks up the service by **OrderService.class**, **no changes to App.java are needed**. Run again:

~~~bash
mvn -q clean compile exec:java
~~~

The logical output remains:

~~~text
ASPECT_BEAN true
STORE_BEAN true
IS_PROXY true
COUNT_BEFORE 0
AUDIT submit ORD-42
SERVICE submit ORD-42
RESULT created:ORD-42
COUNT_AFTER 1
~~~

Here:

1. Spring invokes the `auditStore()` factory to obtain the dependency bean.
2. When `AuditAspect` is needed, Spring resolves the `AuditStore` parameter of the `auditAspect(...)` factory method; the method passes that bean into the constructor.
3. The `AuditAspect` bean has `@Aspect` in its class definition, so Spring AOP still detects its advice.
4. The service bean is managed by Spring even though the factory uses `new OrderServiceImpl()`; that instance is returned **to the container** and can undergo processing steps such as auto-proxying before the client receives it.
5. `@EnableAspectJAutoProxy` is still required in plain Spring Framework configuration.

What matters is **who manages the instance and how dependencies are resolved**. `new AuditAspect(...)` inside a `@Bean` method is valid because the instance is subsequently registered as a Spring bean. If the application creates `new AuditAspect(...)` outside the context without registering it, Spring AOP does not automatically use that instance as an aspect.

You can remove `@Component` from `AuditAspect` in the `@Bean` variant and the aspect still runs because the class still has `@Aspect` and the instance is managed by Spring through the factory method.

After experimenting, if you want to return to the scanner version, restore the original `AppConfig`. Do not keep both registration paths for the same service/aspect simultaneously unless multiple beans are intended; this can cause ambiguity, bean name collisions, or advice being applied multiple times.

## 6. Types of Dependencies That Can Be Injected into an Aspect

### 6.1. A Regular Service Bean

This is the case already run: `AuditAspect` receives `AuditStore` from Spring. You can also inject an interface instead of an implementation, for example:

~~~java
public interface AuditWriter {
    void write(String event);
}
~~~

If the aspect declares the constructor `AuditAspect(AuditWriter writer)`, Spring needs to find a bean implementing `AuditWriter`. When multiple implementations exist, ambiguity must be resolved, such as with **`@Qualifier`** or **`@Primary`** depending on the design. This interface snippet is **API illustration only** and does not replace any file in the runnable example.

Prefer interfaces when a collaborator has multiple implementations or needs test doubles. It is not necessary to create an interface for every small class just because dependency injection supports it.

### 6.2. Configuration Properties with @Value

An aspect can receive values resolved by Spring in its constructor:

~~~java
@Aspect
@Component
public class AuditAspect {

    private final AuditStore auditStore;
    private final boolean enabled;

    public AuditAspect(
            AuditStore auditStore,
            @org.springframework.beans.factory.annotation.Value(
                    "${audit.enabled:true}") boolean enabled) {
        this.auditStore = auditStore;
        this.enabled = enabled;
    }

    @Before("execution(* demo.OrderServiceImpl.submit(..))")
    public void beforeSubmit(org.aspectj.lang.JoinPoint joinPoint) {
        if (enabled) {
            auditStore.record("submit " + joinPoint.getArgs()[0]);
        }
    }
}
~~~

This is an **illustrative replacement version** for the entire `AuditAspect.java` content, not to be used simultaneously with the same-named class in Section 3. The example reads `audit.enabled`, defaulting to `true`, from property sources available to the Spring context. When using custom configuration, ensure the property source is loaded properly; in Spring Boot, appropriate configuration properties mechanisms can be used. **`@Value` only retrieves configuration values**; it does not determine whether a proxy exists or whether a pointcut matches.

### 6.3. Dependencies with a Shorter Lifecycle Than the Aspect

An aspect registered with `@Component` is normally a singleton, while a collaborator may use `request` or `prototype` scope. If a prototype bean is injected directly into a singleton via constructor, the dependency is usually resolved **once when the singleton is created**; it does not automatically create a new prototype instance on every advice invocation.

If per-call bean lookup is needed, Spring provides **`ObjectProvider<T>`**. Illustrative example:

~~~java
private final org.springframework.beans.factory.ObjectProvider<AuditContext>
        contextProvider;

public AuditAspect(
        org.springframework.beans.factory.ObjectProvider<AuditContext>
                contextProvider) {
    this.contextProvider = contextProvider;
}
~~~

In the advice, use `contextProvider.getObject()` at the moment it is actually needed. This snippet only illustrates how to declare the dependency: the `AuditContext` class and its corresponding bean must be defined; it is **not standalone runnable code**. For request-scoped dependencies, an active request scope or an appropriate scoped proxy is required. Calling on a thread without an HTTP request typically leads to a scope error; `ObjectProvider` does not create a request context by itself.

Do not store per-request mutable data in instance fields of a singleton aspect. If advice runs concurrently across multiple threads, such data easily gets mixed up between invocations.

## 7. Same ApplicationContext and Proxy Conditions

In the example, `AppConfig` enables AOP in the context containing `AuditAspect`, `AuditStore`, and `OrderServiceImpl`. This is the easiest situation to observe.

In applications with **multiple ApplicationContexts** (e.g., parent/child), verify:

- Whether the aspect bean and its dependencies can see each other through the context's bean resolution mechanism.
- Which context's auto-proxy infrastructure processes the service.
- Whether the configuration enabling Spring AOP is placed in the context containing the beans to be advised.

`@EnableAspectJAutoProxy` applies to **the context where it is declared**. One cannot automatically assume that enabling AOP in one context will make all beans in every related context become proxies.

In plain Spring Framework, if a service has an interface, Spring AOP often uses a **JDK dynamic proxy** when appropriate. The example calls `context.getBean(OrderService.class)` to use the interface. Do not assume the proxy has runtime type `OrderServiceImpl`. Configuring `proxyTargetClass = true` can select class-based proxies; this does not change how constructor injection happens inside the aspect.

**Two independent checks are required**:

1. **Injection**: the `AuditAspect` bean initializes, receives the `AuditStore` bean, and can call `record(...)`.
2. **AOP**: the returned `OrderService` bean is an appropriate proxy and calls to `submit(...)` actually run the advice.

`AopUtils.isAopProxy(service)` being `true` alone does not prove that **AuditAspect** is applied: the proxy could have been created by another advisor. Checking output behavior or asserting the state of the dependency provides more concrete evidence.

## 8. Common Errors When Injecting into an Aspect

| Symptom | Cause in Spring | How to resolve |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` when creating aspect | `AuditStore` not registered, package outside scan scope, or missing `@Bean` | Check `@Component`, package scan, and Java configuration |
| `NoUniqueBeanDefinitionException` for constructor dependency | Multiple matching beans of the same type exist, cannot determine which bean to use | Use `@Qualifier`, `@Primary`, or configure a single bean for that purpose |
| Aspect is created but advice does not run | Missing `@EnableAspectJAutoProxy`, pointcut does not match, or call does not go through proxy | Check AOP config, pointcut expression, and ensure client obtains service from Spring |
| `@Aspect` exists but bean is not in context | Only `@Aspect` added without component registration or `@Bean` factory | Add `@Component` in scan area or register the aspect with `@Bean` |
| Using `new AuditAspect(...)` in application code expecting advice to run | Instance is outside the Spring container | Register the aspect as a bean in the context |
| `BeanCurrentlyInCreationException` or circular dependency error | Aspect and collaborator/service depend cyclically on each other | Redesign dependency direction, separate audit collaborator from the service being advised |
| Incorrect audit count under concurrent calls | Shared mutable field in singleton aspect/collaborator is not thread-safe | Use appropriate concurrent structures, keep invocation data in local variables |
| Cannot obtain request-scoped bean in advice | Scope is not active on the current thread | Review where the call is triggered, use scoped proxy/provider as required |
| `null` injected when unit test uses `new AuditAspect()` incorrectly | Test bypassed constructor injection and the container | Pass dependency through constructor or create a Spring test context |
| Advice logs first but business logic does not run | Advice throws an exception; with `@Before`, an advice error can abort the call | Handle exceptions and define the error policy of the audit infrastructure |

Circular dependencies require extra attention in AOP because proxy creation may need to read advisors and aspect beans. For example, a graph `AuditAspect → AuditStore → OrderService → (advisor requiring AuditAspect)` is a design that easily becomes problematic. Keep collaborators used by aspects **simple and independent of the services being intercepted** whenever possible.

## 9. Distinguishing Dependency Injection from Self-Invocation and Advice Order

Being able to inject dependencies into an aspect does not change the **self-invocation** limitation of Spring AOP. If a method of `OrderServiceImpl` calls `this.submit(...)` internally, that internal call bypasses the proxy, so advice is not executed separately for `submit(...)`. This is a **call-path** issue, not a constructor injection error.

If multiple aspects share `AuditStore`, the aspects can be injected with the same singleton store. However, advice ordering can affect the order of events. In Spring, `@Order` can be used to control priority when needed, and actual behavior should be tested. Do not take class declaration order or bean name as proof of advice execution order.

For **`@Before`**, if `AuditStore.record(...)` throws an exception, the service method may not be called. When auditing is purely observational, deciding whether to catch/log/ignore audit errors must be based on business requirements; avoid automatically swallowing all errors and hiding failures.

## 10. How to Verify with a Short Test

You can test integration logic without relying on console log output by recreating the context and asserting directly on `AuditStore`:

~~~java
try (var context =
         new org.springframework.context.annotation
             .AnnotationConfigApplicationContext(demo.AppConfig.class)) {

    demo.OrderService service =
            context.getBean(demo.OrderService.class);
    demo.AuditStore store = context.getBean(demo.AuditStore.class);

    if (store.size() != 0) {
        throw new AssertionError("Store must begin empty");
    }

    String result = service.submit("T-1");

    if (!"created:T-1".equals(result)) {
        throw new AssertionError("Unexpected result: " + result);
    }
    if (store.size() != 1) {
        throw new AssertionError("Aspect did not record exactly once");
    }
}
~~~

This snippet is an **additional test fragment**, to be placed inside another test method or `main` in the Section 3 project; it is not a standalone Java file. Success result: no `AssertionError` is thrown. The test checks both the service result and the effect on the collaborator. If `@EnableAspectJAutoProxy` is removed in the plain Spring Framework example, the condition `store.size() == 1` will fail because advice does not run.

When unit testing `AuditAspect` in isolation, you can create `new AuditAspect(fakeStore)` and directly call `beforeSubmit` with a mocked `JoinPoint`. That style of test verifies advice logic but **does not verify that Spring created a proxy**; at least one integration test through `ApplicationContext` is needed for the Spring AOP mechanism.

## 11. Principles for Applying in Spring Applications

- Use **constructor injection** for required aspect dependencies, preferring `final` and explicit dependencies.
- Register aspects via **`@Component` + component scan** or **`@Bean`**; do not treat `@Aspect` as a way to register a Spring bean.
- Ensure injected collaborators have valid bean definitions and scopes compatible with the aspect's lifecycle.
- Keep business logic in services; the aspect should only perform supporting responsibilities such as observation or applying targeted cross-cutting rules.
- Avoid having an aspect depend back on the service it intercepts if it creates a circular dependency or causes unexpected re-entrant auditing logic.
- Limit per-request mutable state in singleton aspects; use advice parameters or collaborators designed to be thread-safe.
- Verify **both dependency injection and actual AOP advice**. Having a bean, having a proxy, and having an advice effect are three related but non-identical states.

## 12. Self-Assessment Questions

**1. Why is `@Aspect` not enough for Spring to inject `AuditStore`?**

Because `@Aspect` only declares an aspect. Spring must register `AuditAspect` as a bean (e.g., `@Component` in the scan scope or `@Bean`) before the container performs dependency injection.

**2. Does the constructor of `AuditAspect` need `@Autowired`?**

Not required when the class has only one constructor. Spring can automatically select that constructor and resolve dependencies by type, then apply bean selection rules if multiple candidates exist.

**3. Why is `COUNT_AFTER` equal to 1 even though `App` never directly calls `store.record(...)`?**

Because the service call through the proxy triggers the advice. The advice calls `record(...)` on the injected singleton `AuditStore`; `App` retrieves that same bean from the context to check the result.

**4. Does a `@Bean` configuration using `new AuditAspect(auditStore)` lose injection or advice capabilities?**

No. The instance returned from the `@Bean` factory is a Spring-managed bean. Spring AOP can read the `@Aspect` declaration and use its advice if the AOP infrastructure is active.

**5. If `AuditStore` is not registered, will the aspect run while skipping auditing?**

With a required constructor dependency, the context will fail when it needs to create `AuditAspect` because it cannot resolve the parameter; Spring does not pass `null` automatically to skip a dependency.

**6. Can a singleton aspect store the current order ID in a `lastOrderId` field?**

You should not use that field to represent per-invocation data, because multiple threads can overwrite each other. Use a local variable inside the advice or an appropriate context mechanism.

**7. If `IS_PROXY` is `true` but no audit is observed, what should be checked?**

Check whether the `AuditAspect` bean actually exists, whether the pointcut matches the method, whether the call passes through the proxy, and whether the proxy was created by a different advisor.

## 13. Official Spring Documentation

- Spring Framework — Dependency Injection: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework — `@Bean` methods: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework — `@AspectJ` support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Takeaway:** In Spring, an aspect receives dependencies via regular bean injection mechanisms once it is a Spring-managed bean. Whether the aspect's advice executes depends on Spring AOP configuration, pointcuts, and calls through proxies. The two mechanisms work together so aspects can use `ApplicationContext` services without instantiating dependencies themselves.
