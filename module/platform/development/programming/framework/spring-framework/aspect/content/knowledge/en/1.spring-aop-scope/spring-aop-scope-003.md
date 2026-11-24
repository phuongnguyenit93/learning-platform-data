# Spring AOP Intercepts Method Execution via Proxy

## 1. Objectives and Scope

After this lesson, you can explain why a method call on a Spring bean can run additional logic before/after the real method; distinguish a proxy from the target object; determine which calls go through Spring AOP and which go directly to the object; and diagnose cases where advice does not run.

**Focus:** Spring AOP uses a **proxy** managed by the Spring container to intercept *method execution* on Spring beans. General Aspect knowledge is not the topic here. Terms such as aspect, pointcut, and advice are used to describe how Spring configures the processing chain for a method.

## 2. The Actual Call Flow in Spring AOP

Suppose another component is injected with `OrderService` and calls `orderService.submit("A01")`. If advice applies to this method, the bean reference that component receives may be a **proxy** rather than the implementation object itself.

```text
Controller / Client bean
          |
          |  calls orderService.submit("A01")
          v
     Spring AOP proxy
          |
          |  (1) matches the method against advisors/pointcuts
          |  (2) runs the matching interceptor / advice chain
          |  (3) proceeds to target when allowed by advice
          v
   OrderServiceImpl.submit(...)
          |
          |  returns result or throws exception
          v
     advice handles result/error
          |
          v
     returns to Controller / Client
```

- **Target:** the object holding the real business implementation, e.g. `OrderServiceImpl`.
- **Proxy:** the intermediary object Spring returns when a bean qualifies for advisors; it receives calls from outside and coordinates advice and target.
- **Advisor / interceptor chain:** Spring selects the advices matching the invoked method and executes them in the configured order. A proxy does not necessarily have advice for *every* method of the bean.
- **Join point in Spring AOP:** is only **method execution**. Proxy-based Spring AOP does not directly intercept field reads, constructor calls, or arbitrary execution points.
- **Decisive point:** the critical path is `client → proxy → target`. If the client holds the target directly and calls it, the proxy's advice chain does not participate.

During bean creation, Spring's auto-proxy processor detects matching advisors/aspects and can create a proxy wrapping the bean. Applications typically retrieve proxies from `ApplicationContext` or via dependency injection; there is no need to manually invoke an "AOP function" in business methods.

## 3. Two Proxy Forms and Practical Consequences

| Mechanism | How It Is Created | Methods Callable from Outside |
| --- | --- | --- |
| **JDK dynamic proxy** | Proxy implements the bean's interfaces | Called via the interfaces exposed by the proxy |
| **Class-based proxy (CGLIB)** | Proxy is a subclass generated from the target class | Called via the proxy's class type for overridable methods |

In a typical Spring Framework configuration, if the target has an interface, JDK dynamic proxy is the default choice; if there is no interface, Spring uses a class-based proxy. Settings from Spring Boot or `proxyTargetClass=true` can change the default proxy type. Therefore, **do not infer the proxy type solely from whether the class has an interface** without checking the actual configuration.

With a JDK proxy, injecting beans by interface is usually safer than casting to the implementation. A class-based proxy **cannot** be created by subclassing a `final class`; `final method` and `private method` cannot be advised via overriding. Methods not visible from a subclass, such as package-private methods on a superclass in another package, also face limitations. `static` methods and direct calls on objects outside the Spring container are not proxy calls expected to be intercepted by Spring AOP.

Do not confuse proxy type with interception scope: **whether JDK or CGLIB, Spring AOP still works through calls routed to the proxy**. Choosing CGLIB does not automatically fix self-invocation issues.

## 4. Runnable Example: Calling Through Proxy and Observing Advice

Standalone example using **Java 17+, Maven, Spring Framework 6.2.6**. Place these exact two files. `spring-context` provides the container, `spring-aop` contains the proxy mechanism; `aspectjweaver` is used by Spring to interpret `@AspectJ` pointcut expressions. The example uses only Spring AOP and does not configure compile-time or load-time weaving.

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-proxy-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Main {
    public interface OrderService {
        String submit(String orderId);
    }

    static class OrderServiceImpl implements OrderService {
        @Override
        public String submit(String orderId) {
            System.out.println("TARGET submit " + orderId);
            return "OK:" + orderId;
        }
    }

    @Aspect
    static class AuditAspect {
        @Around("execution(* demo..*.submit(..))")
        public Object trace(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("BEFORE " + pjp.getSignature().getName());
            try {
                Object value = pjp.proceed();
                System.out.println("AFTER " + value);
                return value;
            } catch (Throwable error) {
                System.out.println("ERROR " + error.getClass().getSimpleName());
                throw error;
            }
        }
    }

    @Configuration
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class AppConfig {
        @Bean
        OrderService orderService() {
            return new OrderServiceImpl();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println("IS_AOP_PROXY=" + AopUtils.isAopProxy(service));
            System.out.println("RESULT=" + service.submit("A01"));
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout printed by the program, in exact order:

```text
IS_AOP_PROXY=true
BEFORE submit
TARGET submit A01
AFTER OK:A01
RESULT=OK:A01
```

Flow explanation:

1. `AnnotationConfigApplicationContext` creates the `orderService` and `auditAspect` beans. `@EnableAspectJAutoProxy` enables discovering `@Aspect` beans and creating proxies when appropriate.
2. `@Bean AuditAspect` registers the aspect with the container; merely placing `@Aspect` on a class **does not** automatically make it a Spring bean.
3. `@Around("execution(* demo..*.submit(..))")` applies to matching **executions** of `submit` in package `demo`. When the client retrieves the bean from the context, calls to the proxy are intercepted.
4. Advice prints `BEFORE`, calls `pjp.proceed()` to continue to the next item in the chain and ultimately the target; the target prints `TARGET` and returns `OK:A01`.
5. Advice prints `AFTER` and returns the **exact value** from `proceed()`; the client finally prints `RESULT`. When the target throws an error, the `catch` branch prints the error and rethrows it without swallowing the exception.

In `@Around`, forgetting to call `proceed()` means the target may **never run**; calling `proceed()` multiple times can cause the target to execute multiple times. This is powerful control of around advice, so it must be intentional. If you only need to record an event before a call, `@Before` is easier to read; if you only need to observe a successful result, consider `@AfterReturning`.

**Output caveat:** the lines above are the lines printed by the example itself. Messages from Maven, logging libraries, or the runtime environment may additionally appear depending on settings; they do not change the order of lines observed in the example.

## 5. When Is Advice Selected?

Spring needs these conditions satisfied simultaneously: the bean goes through the auto-proxy mechanism; the call targets the proxy object; the method can be intercepted by the proxy; and the pointcut matches that execution. Common ways to write Spring AOP pointcuts:

| Expression | Meaning in Spring AOP |
| --- | --- |
| `execution(* demo..service.*.*(..))` | Method execution on types in package `demo..service`, any method name and parameters |
| `execution(public * demo..*Service.*(..))` | Public method executions on types whose names end with `Service` in `demo` and subpackages |
| `@annotation(demo.TraceCall)` | Method execution carrying a matching `@TraceCall` annotation |
| `within(demo..service..*)` | Narrows declaring types to within `demo..service` |
| `bean(orderService)` | Restricts by Spring bean name; this is a Spring AOP-specific extension |

`execution` is the central choice when referring to **method execution**. `bean(...)` distinguishes multiple beans of the same type. `@annotation` is useful when you only want to intercept a tagged set of methods; pay attention to whether the annotation is placed on the interface or implementation and how the proxy mechanism can affect detection, so verify with actual tests.

Composition example:

```java
@Around("execution(public * demo..service..*Service.*(..)) && bean(*Service)")
public Object monitorService(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

This is only an **illustrative advice method**; it must sit inside an `@Aspect` bean and needs the appropriate imports. Avoid overly broad pointcuts like `execution(* *(..))` for all beans when the goal is only a group of services.

Spring AOP does not support AspectJ designators such as `call`, `get`, or `set` to intercept methods called at a source-code call site or field operations. Adding them to a Spring AOP pointcut can cause expression parsing errors. Likewise, because of the proxy mechanism, Spring AOP does not alter the bytecode of every `new` object in the program.

## 6. Self-Invocation: The Most Commonly Misunderstood Case

Consider a bean:

```java
class BillingService {
    public void checkout() {
        this.charge();          // direct call on target
    }

    public void charge() {
        System.out.println("charge");
    }
}
```

If a client calls `billingService.checkout()` **through the proxy**, advice matching `checkout()` can run. But once the target has entered `checkout()`, the call `this.charge()` goes **directly on the target object**, without returning to the proxy; thus, advice matching only `charge()` will **not** be triggered on this path.

```text
From client:
client -> proxy.checkout() -> advice(checkout) -> target.checkout()
                                                    |
                                                    | this.charge()
                                                    v
                                                target.charge()
                                           (does not go through proxy a second time)

An independent call:
client -> proxy.charge() -> advice(charge) -> target.charge()
```

Even when `proxyTargetClass=true` is set, the self-invocation rule still holds. The clearest solution is usually to **extract the operation needing interception into another Spring bean**, then inject that bean so the call goes through the proxy. If calling back through the proxy is unavoidable, techniques like self-injection via an interface or `AopContext.currentProxy()` with `exposeProxy=true` exist, but they introduce AOP coupling and complicate bean management; use them only after weighing design tradeoffs.

A variant of the same nature: instantiating `new OrderServiceImpl()` directly, passing the raw target instead of the bean supplied by Spring, or calling methods in a constructor before the proxy is complete. Those calls have no `client → Spring proxy` path for advice to intercept.

## 7. Distinguishing Proxy, Target, and Call Data When Debugging

Inside advice, Spring provides useful information:

- `pjp.getSignature().getName()`: name of the intercepted method.
- `pjp.getArgs()`: call arguments; consider masking sensitive data before logging.
- `pjp.getThis()`: the proxy receiving the call.
- `pjp.getTarget()`: the target object behind the proxy.
- `pjp.proceed()`: forwards through the rest of the advice chain to the target, if present.

On an actual bean, `pjp.getThis() == pjp.getTarget()` is typically `false`. Spring supports `this(Type)` to constrain the **proxy** type and `target(Type)` to constrain the **target** type in pointcuts; this is especially worth noting when a JDK proxy only implements an interface.

You can inspect a bean in Java:

```java
Object bean = context.getBean("orderService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

This is an **add-on snippet** for the previous example; it needs `import org.springframework.aop.support.AopUtils;` (already present in the example). Proxy-type check methods help diagnose, but **a bean being a proxy does not guarantee every method has advice**. You still need to check the pointcut and call path.

## 8. Real-World Spring Scenarios

**Transaction:** `@Transactional` in proxy mode typically starts/ends a transaction through an interceptor when a call enters the proxy. Placing `@Transactional` on a method and calling it via `this.method()` from the same bean does not create a new proxy call. Thus, "the annotation is there yet no new transaction starts" may stem from self-invocation, not an annotation bug.

**Caching:** With `@Cacheable`'s proxy mechanism, an external call through the bean proxy can check the cache before the target executes. An internal call `this.load()` typically goes straight to the implementation and bypasses the cache interceptor on that method. Adding the annotation does not mean every call path to the method gets cached.

**Asynchronous execution:** `@Async` also commonly relies on proxies. Calling internally via `this` may not dispatch the task to an executor as expected. To verify, observe the thread at the caller and inside the advised method, keeping in mind interceptor ordering and actual Spring settings.

All three examples highlight one Spring rule: cross-cutting behavior is triggered at the **proxy call boundary**. Specific annotations have their own mechanics and conditions; do not assume every advice or every annotation behaves identically.

## 9. Interceptor Ordering Seen from the Proxy Path

When two `@Around` advices both select one method, picture them as **two wrapping layers** around the call. Suppose aspect A has higher precedence than aspect B (for instance `@Order(1)` and `@Order(2)`), both call `proceed()` once, and no other interceptor alters the flow; the trace is typically:

```text
A before → B before → target → B after → A after
```

A smaller `@Order` value has higher precedence, so A enters first and exits last. If the target throws an exception, `after` code placed in `finally` still runs on the way back out; code that only runs after `proceed()` succeeds will not run when an error propagates. That is why you must look at **the interceptor chain and success/failure branches**, rather than inferring order from where advice methods sit in the source file.

Spring can combine transaction, cache, or other advisors on the same proxy. When you need *after-commit* auditing or exact timing of a transaction boundary, check the actual advisor order; a log line after `proceed()` does not by itself prove the commit succeeded.

## 10. Diagnostic Checklist When "Spring AOP Does Not Run"

1. **Is the bean managed by Spring?** Verify the client gets the bean via injection/context, rather than doing `new` and expecting a proxy.
2. **Is the aspect registered?** Does it have `@Aspect` and is it a Spring bean (e.g. `@Component` picked up by component-scan or `@Bean`)? Has configuration enabled `@AspectJ` support and included the `aspectjweaver` dependency?
3. **Was a proxy obtained?** Use `AopUtils.isAopProxy(bean)`. If `false`, check the context/configuration and whether advisors apply to the bean.
4. **Is the call going through the proxy or `this`?** Place breakpoints/traces at the caller, target, and advice to determine the path.
5. **Does the pointcut actually match the method?** Check package, type, name, modifiers, parameters, annotation, and bean name. `execution` describes *execution*, not the *call* site.
6. **Can the method be intercepted by the proxy?** Check interfaces for JDK proxies; for class-based proxies check `final`, `private`, visibility, and override constraints.
7. **Does the advice call `proceed()`?** With `@Around`, not continuing means the target may not run; catching an exception without rethrowing gives the caller different behavior.
8. **Do multiple interceptors match together?** Check `@Order`, transaction/cache/async, and other aspects to understand before/after ordering.

A reliable test approach is to retrieve the bean from the Spring context itself in tests, invoke it via the context-supplied reference, observe behavior outside the target, and compare against a direct call to the target. Testing plain `new ServiceImpl()` does not test Spring AOP.

## 11. Self-Check

**Scenario A.** A client injects `OrderService` and calls `submit()`; the method is intercepted by a matching `@Around` pointcut. Expected trace? — Advice logic runs before the target; advice calls `proceed()`; target runs; then advice processes the result before returning to the caller.

**Scenario B.** `checkout()` calls `this.charge()` within the same target, while advice only matches `charge()`. Does advice run? — No for this `this.charge()` call, because it does not pass through the proxy. Calling `charge()` from another bean through the proxy can run it.

**Scenario C.** Switching from JDK proxy to CGLIB makes `this.charge()` get intercepted automatically? — No. Changing the proxy type does not change the self-invocation path.

**Scenario D.** `@Aspect` is placed on a class without putting that class into the Spring context. Does advice run automatically? — No. The aspect must be registered with Spring and auto-proxy support must be enabled appropriately.

**Scenario E.** An aspect uses `@Around`, only prints "before", and returns `null` without calling `proceed()`. What happens? — The target may not execute; the caller receives `null` (or hits an incompatibility with the return type), because around advice decides whether to proceed.

## Spring Reference Documentation

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB and self-invocation.
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): enabling proxies, registering aspects, and advice.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method-execution pointcuts supported by Spring.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `proceed()`, results, exceptions, and ordering.