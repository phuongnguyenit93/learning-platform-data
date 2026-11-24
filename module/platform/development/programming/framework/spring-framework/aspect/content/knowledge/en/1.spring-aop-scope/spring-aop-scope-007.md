# Spring AOP and Its Relationship with IoC, Dependency Injection, and Bean Lifecycle

## 1. Where Does Spring AOP Sit in the Spring Container?

The **Spring IoC container** (`ApplicationContext` or `BeanFactory`) is responsible for creating, configuring, wiring, and managing the lifecycle of beans. **Spring AOP** leverages that container to recognize aspects/advisors, identify eligible beans, and supply **AOP proxies** when needed. An application still uses IoC/DI normally without enabling AOP.

When a bean needs advice applied, the object a consumer receives from the container may be a **proxy** wrapping the business object (target), rather than the target directly. Calls from another bean entering the proxy pass through interceptors/advices and then reach the target's method. Not every bean or every method is proxied/advised: this depends on pointcuts, AOP configuration, and proxy type.

```text
Bean definition + @Component / @Bean + @Aspect
                    |
             ApplicationContext
                    |
              creates target bean
                    |
        resolves / injects dependencies
                    |
        runs lifecycle initialization
                    |
           auto-proxy creator
                    |
       exposes bean proxy (if needed)
                    |
              DI into consumer
                    |
Consumer --> AOP proxy --> advice --> target.method()
```

The diagram describes the **typical** flow for singletons. When circular dependencies, scoped proxies, custom `BeanPostProcessor`s, or special configurations exist, the actual path can be more complex.

### Role of Each Component

| Spring Component | Responsibility |
| --- | --- |
| `ApplicationContext` / `BeanFactory` | Manages beans, dependencies, and lifecycle |
| Target bean | Contains the business logic to be invoked |
| Aspect bean | Contains advice and pointcuts, itself managed by Spring |
| Auto-proxy creator | Spring infrastructure that determines advised beans and creates proxies |
| AOP proxy | Receives calls from callers, applies interceptors/advices, forwards to target |
| Dependency Injection | Supplies bean references from the container to consumers; that reference may be a proxy |

**IoC does not depend on AOP**, whereas Spring AOP's automatic proxy creation typically depends on the target and aspect being managed by Spring.

## 2. How Does the IoC Container Detect Aspects and Create Proxies?

With annotation-based configuration, the basic workflow:

1. Have the Spring AOP dependency and the AspectJ library supporting pointcut expression parsing.
2. Enable `@AspectJ` auto-proxying: in plain Spring Framework use `@EnableAspectJAutoProxy`; Spring Boot typically auto-configures this when the AOP dependency is present.
3. Register the aspect as a **Spring bean**: `@Aspect` combined with `@Component`, or create an aspect bean via `@Bean`.
4. Spring recognizes advices/pointcuts, selects matching target beans, and creates proxies. When a consumer requests a bean via DI, the container supplies the processed reference.

**Having only `@Aspect` is not enough for component scanning to register a bean.** `@Aspect` declares the AOP role; `@Component` or `@Bean` puts the aspect into the container. An aspect can also use constructor injection to obtain repositories/services, though circular dependencies between aspects and target beans should be avoided. A bean annotated with `@Aspect` is not a target for other aspects to auto-advise in Spring AOP.

Example of **plain Spring Framework** configuration (configuration snippet, not a standalone application):

```java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("demo.aop")
class AopConfig {
}
```

In Spring AOP's `@AspectJ` support, Spring uses the AspectJ pointcut language and the `aspectjweaver` dependency, yet **does not require the AspectJ compiler or load-time weaving** to intercept method calls on Spring proxies.

### Why Is `BeanPostProcessor` Important?

`BeanPostProcessor` receives callbacks before/after a bean's initialization phase. Certain AOP infrastructure components (auto-proxy creators) use this mechanism to wrap beans in proxies. Consequently, the `PaymentService` instance created and the instance injected into a consumer can be two distinct Java objects: the target and the proxy. Do not rely on `bean.getClass() == PaymentService.class` or speculative internal casts to draw conclusions about AOP.

AOP/auto-proxy infrastructure and post-processors have their own initialization rules, so some very early-created infrastructure beans may not receive advice in the same way as ordinary business beans.

## 3. Dependency Injection Determines the Call Path

A Spring-managed consumer can declare constructor injection:

```java
@Service
public class CheckoutService {
    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        paymentService.pay(orderId);
    }
}
```

This is an illustrative snippet; `PaymentService` is defined in the complete example below. If the container wrapped `PaymentService` in an AOP proxy, the dependency passed to the constructor can be the proxy itself. A consumer calling through this dependency will have advice applied when the pointcut matches.

Conversely, when writing `new PaymentService()` and calling methods directly on the self-created object, Spring does not automatically manage that object and does not attach an AOP proxy. The same happens when a consumer manually `new`s a dependency instead of receiving it via DI.

### Proxy Type and Dependency Type

- **JDK dynamic proxy** implements the target's interfaces. When using this type, injection points should be declared by interface; injecting the implementation class can fail because the actual runtime type is incompatible.
- **Class-based proxy (CGLIB)** is a subclass of the target, generally supporting DI by concrete class. Spring Boot defaults to class-based proxies when auto-configuring AOP; you can set `spring.aop.proxy-target-class=false` to choose JDK proxies when appropriate.
- With CGLIB, a `final` class cannot be subclassed to proxy; `final` or `private` methods cannot be overridden to advise in that manner.
- Plain Spring Framework and Spring Boot can choose different defaults; always examine the application's actual configuration.

Useful diagnostic functions: `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, `AopUtils.isCglibProxy(bean)`. They help identify the current proxy but do not replace checking pointcuts and call paths.

## 4. Bean Lifecycle: When Is Advice Activated?

For a typical singleton bean:

1. **Instantiation:** Spring creates the target via constructor or factory method.
2. **Dependency population:** the container configures the target and injects required dependencies.
3. **Initialization:** pre-initialization `BeanPostProcessor`s run; lifecycle callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods execute per Spring's rules.
4. **Post-initialization:** the auto-proxy creator may wrap the target and return a proxy.
5. **Use:** consumers receive the bean via DI and call methods through the proxy; advice runs if the pointcut matches.
6. **Destruction:** when the context closes, Spring coordinates destruction callbacks for applicable singletons (such as `@PreDestroy` or `DisposableBean.destroy()`).

From this sequence, there are three practical consequences:

**`@PostConstruct` runs within the target's lifecycle.** Calls at this step usually happen before the final proxy is exposed to consumers. Therefore, do not put logic expecting `@Transactional`, logging advice, or security advice inside `@PostConstruct`, or make internal calls from an init method assuming advice will definitely run.

**`@PreDestroy` is a container-executed callback.** Do not expect AOP to intercept it like an ordinary business method to release resources. Place cleanup directly in the callback; callbacks are also not guaranteed if the JVM is forcibly terminated.

**Bean scope affects lifecycle.** Spring invokes initialization for prototypes it creates, but does not manage full prototype destruction like singletons. Injecting a prototype directly into a singleton does not make it re-create automatically on every method call either. Scoped proxies are a separate mechanism that can coexist with AOP proxies.

## 5. Runnable Example: Spring Boot, DI, Advice, Init/Destroy, and Self-Invocation

Create a **Spring Boot 3.x, Java 17+** project using Spring Initializr, built with Maven, adding the **Spring AOP** dependency (`spring-boot-starter-aop`). A typical Boot project already includes the base starter. Place the following files in package `demo.aop`. Boot auto-configures AOP, so the example does not need `@EnableAspectJAutoProxy`.

**File `src/main/java/demo/aop/AopApplication.java`**

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AopApplication {
    public static void main(String[] args) {
        SpringApplication.run(AopApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PaymentService service) {
        return args -> {
            System.out.println("[di] proxy=" + AopUtils.isAopProxy(service));
            service.pay("A01");
            service.placeOrder();
        };
    }
}
```

**File `src/main/java/demo/aop/PaymentService.java`**

```java
package demo.aop;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PostConstruct
    void initialize() {
        System.out.println("[lifecycle] init target");
    }

    public void pay(String orderId) {
        System.out.println("[business] pay " + orderId);
    }

    public void placeOrder() {
        System.out.println("[business] placeOrder");
        this.pay("B02"); // Internal call, does not go through proxy
    }

    @PreDestroy
    void cleanup() {
        System.out.println("[lifecycle] destroy target");
    }
}
```

**File `src/main/java/demo/aop/TracingAspect.java`**

```java
package demo.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TracingAspect {
    @Around("execution(public void demo.aop.PaymentService.pay(java.lang.String))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("[aop] before");
        try {
            return joinPoint.proceed();
        } finally {
            System.out.println("[aop] after");
        }
    }
}
```

Run from the root directory of the Maven project:

```bash
mvn spring-boot:run
```

The `System.out` lines to note, in corresponding order (besides Spring Boot logs):

```text
[lifecycle] init target
[di] proxy=true
[aop] before
[business] pay A01
[aop] after
[business] placeOrder
[business] pay B02
[lifecycle] destroy target
```

Explanation of the output:

- `[lifecycle] init target` appears before the runner calls the service. There is no advice for `initialize()`.
- Spring injects the `PaymentService` bean into the `CommandLineRunner` parameter. The aspect applies to the `pay` method, so `AopUtils.isAopProxy(service)` evaluates to `true`.
- `service.pay("A01")` goes through the proxy: `[aop] before` runs prior to `pay`, followed by `[aop] after`.
- `service.placeOrder()` is called from outside, but the advice only selects `pay`. Inside the target, `this.pay("B02")` does not go through the proxy, so the two advice lines do not appear around `B02`.
- When the application finishes and the context closes normally, Spring invokes `@PreDestroy`; the `destroy target` line reflects a lifecycle callback, not business advice.

**The self-invocation limitation is a core property of proxy-based Spring AOP.** When advice for `pay` is needed during the flow from `placeOrder`, the straightforward approach is to move the part needing interception into another Spring bean, then constructor-inject that bean and call it through the Spring reference. Self-referencing proxies via special configuration are possible, but that approach couples code to AOP infrastructure and easily causes lifecycle/circular dependency problems.

## 6. Misconceptions Directly Related to Bean Lifecycle

| Case | Point to Check |
| --- | --- |
| `@PostConstruct` calls an advised method | Initialization callbacks typically run on the target before the final proxy is exposed; move work needing interception to a bean call after initialization. |
| Expecting `@PreDestroy` to run through advice | Cleanup is a container-coordinated lifecycle callback; write cleanup in the callback rather than relying on business interceptors. |
| Prototype bean injected directly into a singleton | Injection occurs during the singleton's lifecycle; the prototype is not re-created automatically on each method call. If a fresh instance is needed each time, consider an appropriate provider or lookup. |
| Scoped proxy confused with AOP proxy | A scoped proxy solves how a bean is referenced by scope; it does not imply application advisors exist. One bean can have multiple proxy layers. |
| Aspect injects the exact target it advises | Risks creating a circular dependency, leading to premature proxying or initialization failures. Separate observed dependencies into an independent bean and inspect the dependency graph. |

These cases are issues of **timing and bean reference origin**; checking `AopUtils` only tells you whether the current reference is a proxy, whereas lifecycle demands understanding when the container creates, injects, initializes, and destroys beans.

### A Note on DI Design

Constructor injection makes dependencies explicit and gives Spring the chance to supply the proper proxy. It **does not automatically resolve** circular dependencies. If you have to self-inject just to AOP-advise a method, reconsider service responsibility boundaries instead of working around the bean lifecycle.

`@Lazy` and scoped proxies also create indirect references, but are not synonymous with AOP advice. An application can have multiple proxy layers; identify the proxy's source using configuration and diagnostic tools rather than only checking runtime class names.

## 7. Analysis Checklist When a Call Is Not Intercepted by an Aspect

1. Do the target and aspect belong to the right `ApplicationContext`? Are `@ComponentScan`, `@Bean`, and AOP dependencies all present?
2. Does the aspect have `@Aspect` **and** is it registered as a bean? In plain Spring Framework, is `@EnableAspectJAutoProxy` or equivalent configuration enabled?
3. Does `AopUtils.isAopProxy(targetInjected)` return `true`? Is the proxy JDK or CGLIB, matching the dependency type?
4. Does the pointcut truly match the method **being called**? Is the method `private`/`final` such that a class proxy cannot intercept it?
5. Is the caller invoking through a Spring-injected reference, or via `new`, `this.method()`, or inside an initialization callback?
6. If logic depends on transactions/caching/async, check how those annotations create and use proxies in the current configuration.
7. If lifecycle-related, clearly distinguish `@PostConstruct`, calls after the context is ready, and `@PreDestroy`.

## 8. Review Questions

**1. Do IoC/DI need Spring AOP to operate?** No. IoC and DI are the foundation of bean management; Spring AOP can use them to automatically supply proxies.

**2. Why does DI into a service receive a proxy?** The auto-proxy creator can replace the bean reference exposed by the container with a proxy containing interceptors/advices.

**3. Why does `@Around` not run around `this.pay()`?** Because the call goes directly on the target, not through Spring's proxy reference.

**4. Can you rely on `@Transactional` running inside `@PostConstruct`?** You should not. Initialization callbacks typically run on the target before business call flows go through the proxy.

**5. Why does DI by interface work while DI by implementation sometimes fails?** A JDK proxy only implements the target's interfaces, whereas a class-based proxy uses a subclass of the target.

## Official Reference Documentation

- [Spring Framework: @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework: BeanPostProcessor / Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework: @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Boot: Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)