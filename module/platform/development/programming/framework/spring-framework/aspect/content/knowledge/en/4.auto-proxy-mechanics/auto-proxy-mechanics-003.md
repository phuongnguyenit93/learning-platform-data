# Spring AOP Auto-Proxy: Target Bean Creation, Proxy Creation, and Returning the Reference to Dependents

## 1. The Problem to Understand

When a Spring bean has a method matching an advice, Spring AOP can automatically create a **proxy**. Another bean declaring constructor injection usually receives **the proxy provided by the container**, rather than directly holding the target object inside the proxy. From there, calls through the dependency are routed through the advice and then to the business logic.

Three objects/concepts to keep distinct:

- **Target bean**: the object performing business logic, created from a bean definition (e.g., an `@Service` class or an `@Bean` factory method).
- **AOP proxy**: the object representing the target to intercept matching method calls; Spring AOP uses a JDK dynamic proxy or a class-based proxy (CGLIB).
- **Dependent/consumer bean**: the bean using the target via dependency injection; it receives the reference Spring publishes for that bean name, which may be a proxy when auto-proxying applies.

In the example, a `CheckoutWorkflow` needs `OrderService`. Spring receives this requirement and ensures `OrderService` is created and initialized; if an advisor needs to intercept `OrderService.process()`, the container can provide an AOP proxy. When `CheckoutWorkflow` calls `service.process()`, the invocation through the proxy gives the advice the opportunity to execute.

**Lesson scope:** Spring AOP based on proxies and Spring's lifecycle/IoC. Do not generalize this to AspectJ bytecode weaving, and do not assume every method in a Spring bean is automatically advised.

## 2. Timeline Diagram of a Typical Singleton

```text
Register @Configuration, @Service, @Component, @Aspect, @Bean
                           |
                           v
              ApplicationContext starts up
                           |
                           v
           BeanPostProcessor infrastructure registered
          (including auto-proxy creator for Spring AOP)
                           |
                           v
        Container needs to create CheckoutWorkflow (consumer)
                           |
               Resolve constructor parameter
                           |
                    needs OrderService
                           |
             Look up OrderService bean definition
                           |
                           v
                  CREATE TARGET INSTANCE
                   (constructor/factory)
                           |
                 populate config/dependencies
                           |
              before-initialization processors
                           |
                  lifecycle init callbacks
                           |
              after-initialization processors
                           |
         Auto-proxy creator evaluates advisors/pointcuts
                   /                 \
           matching advice        no match
                   |                 |
             create AOP proxy    keep target
                   \                 /
                    \               /
                     v             v
                Publish bean reference
                           |
                           v
      Inject reference into CheckoutWorkflow constructor
                           |
                           v
        Workflow --> proxy --> advice --> target.process()
```

This is a **typical model**, not an immutable callback order for every kind of bean. A `BeanPostProcessor` may apply different logic in `postProcessBeforeInitialization`; the standard auto-proxy creator commonly creates the proxy in `postProcessAfterInitialization` or via a special path when an early reference is needed. Cases with circular dependencies, custom scopes, `FactoryBean`, post-processors creating beans too early, or special configurations have more complex paths.

The key point is that **the consumer receives the bean reference after it has gone through Spring's management process**. The result does not necessarily have the same Java object identity as the target behind the proxy.

## 3. From Bean Definition to Target Instance

### 3.1. A Bean Definition Is Not Yet an Object

Spring can know about a bean's existence through:

```java
@Service
public class OrderServiceImpl implements OrderService {
    // ...
}
```

or through an `@Bean` method:

```java
@Configuration
class OrderConfiguration {
    @Bean
    OrderService orderService() {
        return new OrderServiceImpl();
    }
}
```

These are two **alternative** ways to register the same bean role, not two snippets to enable simultaneously for the same target. They simply show where Spring gets the bean definition. A class with `@Service` must lie within component-scanning scope; `@Bean` creates and returns the object for the container to manage.

Do not confuse Spring knowing a bean definition with the moment the target is created. Normal singletons are usually pre-instantiated when the context starts, but can also be created only when requested if configured as lazy. For prototypes or beans with other scopes, the initialization lifecycle and number of instances can vary.

### 3.2. The Container Creates and Configures the Target

When an `OrderService` is needed, Spring selects the appropriate constructor or factory method to create the object:

1. Resolve any dependencies needed to invoke the constructor/factory method.
2. Create the target object.
3. Populate field/setter dependencies and configure properties Spring is responsible for.
4. Call `BeanPostProcessor.postProcessBeforeInitialization(...)` callbacks.
5. Run appropriate initialization callbacks, such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or a custom init method.
6. Call `BeanPostProcessor.postProcessAfterInitialization(...)`. The auto-proxy creator can return **a proxy distinct from the target instance**.

Here, the callback order is bean lifecycle logic; it does not mean business methods run through AOP inside the constructor or `@PostConstruct`. The target under construction is normally not yet used by other callers through the final proxy.

### 3.3. Why Does `new OrderServiceImpl()` Inside `@Bean` Still Work?

Inside a factory method invoked by the container, `new` creates the object that the method **returns to Spring**. Spring continues managing that object, runs post-processing, and can publish a proxy. However, if business code itself writes:

```java
OrderService x = new OrderServiceImpl();
x.process("OUTSIDE");
```

then variable `x` is a reference to an object not registered with the container; Spring will not weave an AOP proxy into that call. So the issue lies in **how the reference is obtained and used**, not merely the presence of the `new` operator.

## 4. The Auto-Proxy Creator Selects Beans and Builds Proxies

### 4.1. Which Component Is the Auto-Proxy Creator?

Spring AOP uses the `BeanPostProcessor` infrastructure. With `@Aspect` declarations, `@EnableAspectJAutoProxy` or the corresponding auto-configuration registers the mechanism that automatically finds advisors/advice and creates proxies when appropriate. Implementations in the `AbstractAutoProxyCreator` family perform this key work; this is Spring infrastructure, and applications do not normally call it directly.

A high-level sequence:

```text
target object + bean name + bean class
                    |
         auto-proxy creator inspects
                    |
     Should an advisor apply to this bean?
              /             \
            no              yes
             |                |
      return old target   select advisors
                              |
                         choose proxy type
                              |
                         create AOP proxy
                              |
                         return proxy
```

An advisor contains the applicability condition (pointcut) and the advice. If no advisor matches, or the bean does not belong to a group eligible for auto-proxying, the container can publish **the target itself**. You cannot infer that merely having `@Service`, `@Aspect`, or enabling Spring AOP means every bean is proxied.

### 4.2. When Is JDK Proxy or CGLIB Chosen?

In Spring Framework by default, `@EnableAspectJAutoProxy(proxyTargetClass = false)`:

- If the target implements suitable interfaces, Spring can create a **JDK dynamic proxy** implementing those interfaces.
- If the target has no interface to proxy, Spring creates a class-based proxy (CGLIB).
- With `proxyTargetClass = true`, Spring chooses a class-based proxy when the class can be proxied; a `final class` cannot be subclassed, and `final`/`private` methods cannot be advised via the override mechanism.

Spring Boot auto-configured AOP typically sets `spring.aop.proxy-target-class=true` by default. Therefore, check the actual configuration when comparing a plain Spring Framework app with Spring Boot.

The difference also matters for injection: a JDK proxy implements interfaces so consumers should inject by interface; if a consumer asks for the concrete class while Spring returns a JDK proxy, a type-compatibility error can occur. A CGLIB proxy is a subclass of the target so it can be compatible with the concrete class if the class is not restricted from proxying.

### 4.3. How Does Spring Publish the **Proxy Reference**?

Suppose the target has bean name `orderServiceImpl`. Normally, the auto-proxy creator returns the proxy object as the result of bean processing. When another bean looks up the dependency by type or name, `BeanFactory` provides **the post-processed bean reference**. For a normal singleton, subsequent retrievals of the bean from the same context/definition receive the already-published singleton reference, rather than recreating a new proxy on each injection.

```java
OrderService service = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(service));
```

If `OrderService` is advised and has been proxied, the result is `true`. If no advisor matches, it can be `false`, even though `OrderService` is still a valid Spring bean.

**Do not equate proxy and target by object identity.** With an AOP proxy, `service.getClass()` can be a JDK proxy class or a CGLIB-generated class; comparing `service.getClass() == OrderServiceImpl.class` is not a reliable check for AOP. Use `AopUtils.isAopProxy` and inspect the proxy type when needed.

## 5. The Consumer Receives the Proxy via Dependency Injection

### 5.1. Constructor Injection Makes the Dependency Flow Clear

```java
@Component
class CheckoutWorkflow {
    private final OrderService service;

    CheckoutWorkflow(OrderService service) {
        this.service = service;
    }

    void checkout(String orderId) {
        service.process(orderId);
    }
}
```

This is an illustrative snippet; the complete program is in section 7.

When Spring initializes `CheckoutWorkflow`, it must resolve the `OrderService` parameter before invoking the constructor. If the singleton target has not been created yet, Spring builds it first; after the auto-proxy step, the container uses the final reference for injection. Therefore, the consumer's `service` field can point to **the proxy**.

### 5.2. Actual Order Depends on Which Bean Is Created First

Not every bean necessarily has a fixed global initialization order. If the consumer has not been created yet while Spring has already pre-instantiated the target singleton, DI simply grabs the existing reference. If the consumer is an early-initialized bean and needs the target beforehand, resolving the dependency causes the target to be created before the consumer. In both normal situations, Spring's goal is to supply a dependency that has been properly processed by the container.

### 5.3. When the Consumer Invokes a Method

```text
CheckoutWorkflow.checkout()
          |
          | service.process("A-001")
          v
   AOP proxy of OrderService
          |
       [advice]
          |
   OrderServiceImpl.process()
```

Only **calls through the proxy** enter Spring AOP advice. If inside `OrderServiceImpl.process()` there is `this.anotherMethod()`, that internal call goes directly on the target, so advice intended for `anotherMethod()` will not run automatically. This is a consequence of proxy-based AOP, even when the target is a proper bean and the consumer receives the proxy correctly.

Similarly, a target reference held outside Spring, such as from `new`, does not automatically get replaced with a proxy just because the corresponding class also has a Spring bean.

## 6. Distinguishing Bean Lifecycle Callbacks from Business Calls Through the Proxy

| Moment | Runs on which object? | Should advice be expected to run? |
| --- | --- | --- |
| Target's constructor/factory method | Target being created | No |
| Setter injection / field injection | Target being configured | No |
| `@PostConstruct`, `afterPropertiesSet`, or custom init callback | Normally the target before the final proxy is published | Should not expect it |
| `postProcessAfterInitialization` in auto-proxy creator | Receives bean/target; may return proxy | This is the proxy-preparation step, not a business method through the proxy |
| Consumer calls `service.process()` on Spring-injected reference | Proxy, then target | Yes, if advisor/pointcut matches |
| Target calls `this.process()` | The target itself | No, because it bypasses the proxy |
| `@PreDestroy`/destroy callback | Managed by container bean lifecycle | Should not rely on advice for cleanup |

A bean having a proxy after initialization does not mean every callback in a constructor, `@PostConstruct`, or `@PreDestroy` will be AOP-intercepted. Do not place logic requiring `@Transactional`, security advice, or caching advice inside a lifecycle callback itself and expect it to behave like an external call through the proxy.

The `BeanPostProcessor` infrastructure must be initialized early. Post-processors themselves and some direct dependencies created early may **not be eligible to go through full post-processing/auto-proxying**; Spring may warn that a bean is not eligible for getting processed by all post-processors. When writing a `BeanPostProcessor` yourself, check its dependencies and avoid unnecessarily initializing business beans too early.

## 7. Runnable Example: Observing Target Init, Proxy, and Dependency Injection

The example uses **Java 17 + Spring Framework 6.2.x + Maven**, without Spring Boot. The `@EnableAspectJAutoProxy` infrastructure finds the aspect, selects the service bean, and publishes the proxy to `CheckoutWorkflow`.

Project structure:

```text
spring-auto-proxy-flow/
├── pom.xml
└── src/main/java/demo/autoproxy/
    ├── AppConfig.java
    ├── OrderService.java
    ├── OrderServiceImpl.java
    ├── TraceAspect.java
    ├── CheckoutWorkflow.java
    └── Main.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-auto-proxy-flow</artifactId>
    <version>1.0-SNAPSHOT</version>

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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. `AppConfig.java` — Registering Scanner and Auto-Proxy

```java
package demo.autoproxy;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan` locates Spring beans in `demo.autoproxy`, while `@EnableAspectJAutoProxy` provides the infrastructure to parse `@Aspect` and automatically create proxies. With this plain Spring Framework configuration, the service has an interface so the proxy is typically a JDK dynamic proxy.

### 7.3. `OrderService.java` — The Contract the Consumer Needs

```java
package demo.autoproxy;

public interface OrderService {
    void process(String orderId);
}
```

### 7.4. `OrderServiceImpl.java` — Target and Init Callback

```java
package demo.autoproxy;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService, InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("[target] initialized");
    }

    @Override
    public void process(String orderId) {
        System.out.println("[target] process " + orderId);
    }
}
```

`InitializingBean` is chosen to demonstrate a lifecycle callback without needing `@PostConstruct` configuration. The `afterPropertiesSet()` method is invoked by the container during target initialization. It is not a business call through the proxy.

### 7.5. `TraceAspect.java` — Aspect Managed by Spring

```java
package demo.autoproxy;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.autoproxy..*.process(..))")
    public void beforeProcess() {
        System.out.println("[advice] before process");
    }
}
```

`@Aspect` describes the aspect; `@Component` makes Spring discover and manage the aspect as a bean. The pointcut only selects `process` methods in this demo package, so the `OrderServiceImpl` target is advised.

### 7.6. `CheckoutWorkflow.java` — Bean Receiving the Spring-Provided Reference

```java
package demo.autoproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class CheckoutWorkflow {
    private final OrderService service;

    public CheckoutWorkflow(OrderService service) {
        this.service = service;
        System.out.println("[consumer] injected proxy="
                + AopUtils.isAopProxy(service));
    }

    public void checkout() {
        System.out.println("[consumer] checkout");
        service.process("A-001");
    }
}
```

The consumer receives `OrderService` via its constructor. Without creating `new OrderServiceImpl()`, it uses the reference Spring provides. `AopUtils.isAopProxy(service)` is used purely for diagnostics in the example.

### 7.7. `Main.java` — Creating the Context and Invoking the Consumer

```java
package demo.autoproxy;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(CheckoutWorkflow.class).checkout();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.autoproxy.Main
```

**Lines printed to stdout by the program** (Maven/Spring logs may appear depending on the environment):

```text
[target] initialized
[consumer] injected proxy=true
[consumer] checkout
[advice] before process
[target] process A-001
```

Explanation:

1. `OrderServiceImpl` is created by Spring, goes through its lifecycle, runs `afterPropertiesSet()`, and prints `[target] initialized`.
2. When `CheckoutWorkflow` is created and its constructor receives `OrderService`, the AOP infrastructure has already wrapped the service bean; Spring injects the proxy, so it prints `[consumer] injected proxy=true`.
3. Calling `checkout()` on the consumer leads to `service.process("A-001")`. The call through the Spring AOP proxy runs `@Before`, then executes the target `process()`.
4. `CheckoutWorkflow` has no matching advice, so it is **not necessarily** proxied; Spring can inject a proxy for its dependency while the consumer itself remains a regular bean.
5. How many times the target and proxy are created depends on bean scope and configuration. For a normal singleton in the example, Spring publishes one processed singleton reference of the service to the consumer.

**Regarding determinism of the log order:** There are no concurrent tasks, the aspect prints nothing during initialization, and the consumer constructor needs to resolve `OrderService`. Therefore, the target initialization line precedes the consumer injected line; the two advice/business lines are printed when `checkout()` is called.

## 8. Experimenting with Changes to Observe Proxy Boundaries

### 8.1. Creating the Target Manually with `new` Inside the Consumer

Change the `checkout()` method to:

```java
public void checkout() {
    System.out.println("[consumer] checkout");
    OrderService unmanaged = new OrderServiceImpl();
    unmanaged.process("B-002");
}
```

This is a **method replacement** inside `CheckoutWorkflow`, not a standalone class. The call `unmanaged.process("B-002")` is made directly on a manually created object, so `[advice] before process` does not appear for `B-002`. It also does not go through Spring's initialization callback; `afterPropertiesSet()` does not run automatically because the object was created only with Java's `new` operator.

Meanwhile, the `service` field injected at constructor time is still a proxy. The existence of that field does not automatically turn the `unmanaged` variable into a proxy.

### 8.2. Removing the Aspect

Remove `@Component` from `TraceAspect` and do not register that aspect with `@Bean`. When no other advisor needs to wrap the service, the service can be published as the raw target; then `AopUtils.isAopProxy(service)` yields `false`. The service **is still a Spring bean**, just without the corresponding advice.

### 8.3. Using an `@Bean` Factory Method Instead of `@Service`

You can remove `@Service` from `OrderServiceImpl` and add to `AppConfig`:

```java
@Bean
OrderService orderService() {
    return new OrderServiceImpl();
}
```

This is a fragment inside an `@Configuration` class, requiring `import org.springframework.context.annotation.Bean`. The returned object is a **container-managed** target; Spring still gets the chance to run lifecycle callbacks, auto-proxy, and inject the reference into the consumer. Having the factory use `new` does not make it an object outside Spring.

### 8.4. Switching to a Class-Based Proxy

Change `@EnableAspectJAutoProxy` to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

When the service class can be subclassed, Spring will use a CGLIB proxy. With this example, `AopUtils.isAopProxy(service)` still returns `true`. If you need to distinguish the proxy type, print:

```java
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

These two lines of code are an illustrative insertion inside the consumer or a method that has the `service` variable. For the initial example configuration, the expected results are `true`, `false` respectively; after forcing a class-based proxy, they are `false`, `true`. Changing the proxy type does not cause self-invocation to be advised.

## 9. Exceptions and Limitations to Understand Accurately

### 9.1. Circular Dependencies and "Early Bean Reference"

If bean A needs B and B needs A, Spring may encounter a **circular dependency**. For certain singleton cases using setter/field injection, `BeanFactory` has a mechanism to provide an **early reference** before the object finishes initialization to resolve the dependency cycle. The AOP infrastructure can participate via `SmartInstantiationAwareBeanPostProcessor.getEarlyBeanReference(...)` to ensure the early reference matches the final proxy.

However, this is a **special path**, not the normal flow for every bean:

- Do not teach that Spring always creates the proxy **after** injecting into all beans; an early proxy can appear before target initialization completes.
- Not every circular dependency can be resolved. In particular, constructor dependency cycles cannot be resolved like ordinary setter cycles.
- Modern Spring Boot restricts circular references by default. You should not enable configuration allowing circular dependencies just to mask a design issue.
- If one bean already received the raw target and the target is later proxied, Spring may throw an error regarding raw injection even though the final bean is a proxy. The good solution is to eliminate the cycle and let beans receive a stable final reference.

Therefore, the diagram in section 2 is the **happy path** for beans without circular dependencies; when debugging dependency cycles, you must examine how early references and actual proxies are supplied.

### 9.2. `BeanPostProcessor` Cannot Expect to Be Auto-Proxied Like a Business Bean

A `BeanPostProcessor` must be created very early to post-process beans that come later. Post-processors themselves and some dependencies they require early are often not eligible to receive full AOP processing. Spring's warning line typically contains text similar to `Bean '...' is not eligible for getting processed by all BeanPostProcessors`.

If you write an `@Bean` returning a `BeanPostProcessor`, pay attention to declaring its return type so Spring detects it early; declaring a `static @Bean` with few dependencies usually avoids prematurely creating unnecessary beans. Do not put complex business dependencies into auto-proxy-related processors themselves without good reason.

### 9.3. Different Scopes and Proxies

- **Singleton**: one Spring bean instance/reference per bean definition in the container under singleton scope; with AOP, the published reference can be a singleton proxy.
- **Prototype**: each time the container handles a bean request, it can create a new target and a new proxy if needed; injecting a prototype directly into a singleton usually resolves only once when building the singleton.
- **Scoped proxy**: used to defer resolution to the proper scope, which is another form of proxy; it can be combined with Spring AOP. Seeing a proxy-like class name is not enough to confirm aspect advice is running.

### 9.4. `FactoryBean` Differs from `@Bean`

`FactoryBean<T>` is a Spring contract that provides a product from `getObject()`; a factory method annotated with `@Bean` is simply a way to declare a bean definition. The two concepts are not equivalent. When processing a `FactoryBean`, the container has an extra layer for looking up the product and a separate post-processing path; do not mechanically apply the plain singleton diagram.

### 9.5. Same Class, Two `ApplicationContext`s

A bean belonging to context A is not automatically advised just because an aspect exists in context B. The auto-proxy infrastructure and advisor discovery are scoped per container. Applications with parent/child contexts need to check where the target, aspect, and auto-proxy creator are declared, and where the consumer retrieves its reference.

### 9.6. Not Every Method Can Be Advised

With proxy-based Spring AOP, only method invocations going through the proxy have a chance to run advice; CGLIB cannot override `private` or `final` methods, while a JDK proxy exposes the interface contract. The pointcut must match the actual method. Self-invocation `this.method()` bypasses the proxy under both types.

## 10. Diagnostic Checklist: "Injected Already, Yet the Aspect Does Not Run"

| Question | Impact on the flow |
| --- | --- |
| Is the target registered as a Spring bean? | If created manually with `new` outside the container, there is no standard auto-proxying |
| Does component scan cover the packages of both the service and the aspect? | Bean definitions or advisors will not be found if scanning is misconfigured |
| Is `@Aspect` registered via `@Component`/`@Bean`? | `@Aspect` alone does not guarantee the aspect becomes a Spring bean |
| Is Spring AOP enabled? | Requires `@EnableAspectJAutoProxy` or appropriate auto-configuration |
| Does the advisor/pointcut match the service method? | If it does not match, the raw target may be returned directly |
| Does the consumer receive the bean via Spring DI? | Only the injected reference has the chance to be a proxy |
| What does `AopUtils.isAopProxy(injectedService)` return? | Distinguishes a proxy reference from a target |
| Is the call path `consumer -> injectedService.method()` or `this.method()`? | Only the path through the proxy is intercepted |
| Is the proxy type compatible with the injection type? | JDK proxy is not the implementation class; CGLIB has `final` restrictions |
| Is there a circular dependency/early bean or premature initialization? | May receive an early reference or not be fully post-processed |
| Are there multiple contexts or special scopes? | May be using a bean/reference outside the advisor's scope |
| Does code expect advice in `@PostConstruct`? | Target initialization callback is not equivalent to an external call through the proxy |

A systematic way to check is: verify the bean definition → review auto-proxy conditions/limits → inspect the actual reference from the consumer → test the proxy with `AopUtils` → observe calls through that reference → check pointcuts and self-invocation. This path distinguishes bean-creation errors, proxy-creation errors, and calling the wrong reference.

## 11. Review Questions

**1. Does Spring create the target and then the proxy in every case?** For normal singletons, the proxy is usually created after initialization callbacks. There are early-proxy exceptions when resolving certain circular dependencies or when special post-processing infrastructure is involved.

**2. Why can a consumer's constructor receive an AOP proxy even when declaring the service's interface type?** When resolving dependencies, Spring provides the bean reference published by the container. With a JDK proxy, that reference implements the interface, so it satisfies the constructor parameter.

**3. Does Spring AOP create a proxy for every bean?** No. The auto-proxy creator evaluates advisors/pointcuts and applicability rules; beans that do not need interception can be published as-is.

**4. Does `new ServiceImpl()` inside an `@Bean` method lose AOP?** No. The object **returned** from the `@Bean` method is managed by Spring and can be auto-proxied.

**5. Why is `@PostConstruct` not guaranteed to trigger advice?** Because it belongs to the initialization step on the target, normally occurring before the consumer uses the proxy reference to invoke business methods.

**6. How can you be sure the consumer received a proxy?** Check the Spring-injected reference directly with `AopUtils.isAopProxy(...)` and the proxy type with `isJdkDynamicProxy` / `isCglibProxy` if needed; also ensure the pointcut actually matches the invoked method.

**7. What happens if a bean already received the raw target in a circular dependency?** That reference may differ from the final proxy and cause inconsistent behavior or bean creation failure; the sustainable solution is to remove the dependency cycle and route calls through a stable bean reference.

## Official Spring Documentation

- [Spring Framework — Container Extension Points / BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 — Using the Auto-proxy Facility](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/autoproxy.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
