# Aspects as Infrastructure Beans and the Limit on Applying Advice to Aspects Themselves

## 1. Properly Understanding the Two Roles of an `@Aspect` in Spring

In Spring AOP, a class annotated with `@Aspect` can be registered **as a Spring bean** so that Spring finds, instantiates, injects dependencies into it, and extracts its advice/pointcut declarations. However, when Spring AOP automatically selects objects to proxy, **beans marked with `@Aspect` are excluded from the list of auto-proxying targets**. Therefore, an aspect cannot be intercepted by another aspect's advice through the **Spring AOP `@AspectJ` auto-proxy** mechanism.

This is an easily overlooked distinction:

- **Being a bean:** the aspect can have its lifecycle managed by the Spring container, be configured, receive dependency injection, and be retrieved via `getBean(...)` like ordinary beans.
- **Having an AOP infrastructure role:** the aspect provides advisors/advice for Spring to insert into **proxies of other target beans**; it does not become a target for Spring AOP auto-proxying merely because another aspect's pointcut matches a method name in the aspect.
- **Not synonymous with the `@Infrastructure` annotation or the `AopInfrastructureBean` interface:** calling an aspect an “infrastructure bean” here describes **its role**. An `@Aspect` class does not have to implement any marker interface to be excluded from auto-proxying.

**Rule to remember:** *An aspect bean is managed by Spring and supplies advice; however, Spring AOP does not automatically apply another aspect's advice to that `@Aspect` bean itself.* This rule belongs to the Spring AOP proxy mechanism, not an assertion about all bytecode weaving technologies or all manually created proxies.

This lesson focuses exclusively on Spring Framework and Spring AOP; it does not expand into general Aspect theory.

## 2. `@Aspect` Does Not Automatically Register a Spring Bean

The following code describes an aspect with advice:

```java
@Aspect
public class AuditAspect {
    @Before("execution(* com.example.app.service..*.*(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

Placing `@Aspect` on a class **only declares its aspect role**; it does not yet guarantee that the Spring container creates an instance and uses it.

There are two common ways to register it:

**Approach A — component scanning:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.app.service..*.*(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

With this approach, the class's package must lie within Spring's component-scan scope. `@Component` helps Spring discover the bean; `@Aspect` helps the `@AspectJ` mechanism recognize the advice declarations.

**Approach B — registering with `@Bean`:**

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

This is an illustrative configuration snippet, assuming the `AuditAspect` class is already defined as in the example along with appropriate Spring imports. In plain Spring Framework configuration, `@EnableAspectJAutoProxy` enables processing of `@AspectJ`-style aspect beans. Spring Boot applications with `spring-boot-starter-aop` usually have Boot enable AOP support automatically when classpath conditions are met; adding `@EnableAspectJAutoProxy` manually is not strictly necessary.

**Do not place `@Aspect` on a `@Bean` method expecting it to turn the object into an aspect.** Spring detects the aspect type from the actual class carrying `@Aspect`. Similarly, `@Aspect` alone does not replace `@Component` when using component scanning.

## 3. Where Does Spring Handle Aspect Beans Differently from Target Beans?

A simplified view of Spring's initialization cycle:

```text
ApplicationContext registers bean definitions
             |
             v
Enable @AspectJ auto-proxy (e.g., @EnableAspectJAutoProxy)
             |
             v
Find bean classes with @Aspect to build advisor list
             |
             +-------------------------------+
             |                               |
             v                               v
       Aspect bean                    Other target bean
       (@Aspect)                      (e.g., OrderService)
             |                               |
             |                               v
             |                        Does any advice apply?
             |                               |
             v                        Yes ---+--- No
   Spring AOP excludes from                 |         |
   @AspectJ auto-proxying                   v         v
             |                            Proxy   Normal bean
             v                              |
   Regular aspect instance                  v
   in the Spring context              Client calls proxy
                                              |
                                              v
                                    advice -> target method
```

Technically, Spring Framework has an auto-proxy creator, such as `AnnotationAwareAspectJAutoProxyCreator`, whose job is to find advisors, evaluate target beans, and create AOP proxies when needed. When processing aspects, Spring identifies classes annotated with `@Aspect` as sources of advice declarations and **skips auto-proxying the aspect itself**. This mechanism prevents an aspect from being affected by another aspect's advice like a business target.

**What stays the same?** Spring still injects constructor dependencies for the aspect, normal public methods of the aspect can still be called via the bean reference, and its advice is still used when method executions on target beans match the pointcut.

**What should not be expected?** If `LoggingAspect` has a pointcut matching `AuditAspect.maintenance()`, standard Spring AOP auto-proxying will not turn `AuditAspect` into a target proxy to run `LoggingAspect`'s advice.

### Three Concepts to Distinguish

| Object | Role | What does Spring AOP auto-proxy normally do? |
| --- | --- | --- |
| `@Aspect` bean | Source providing pointcuts/advice | Recognized to create advisors; **does not become a target for another aspect's advice** |
| Regular service/repository/controller bean | Potential target of advice | Can be proxied if an advisor matches and the bean is eligible |
| Special infrastructure such as `BeanPostProcessor` or `AopInfrastructureBean` | Supports container/AOP operation | Has its own ineligibility rules for auto-proxying; should not be completely equated with all aspect beans |

The word “infrastructure” describes an operational role. Do not infer that all beans used by infrastructure share the exact same mechanism or the exact same reason for being excluded from proxying.

## 4. Runnable Example: Advice Runs on Service but Not on Aspect Method

Java 17+ example run with Maven, Spring Framework 6.2.6. The program registers **two aspect beans**:

- `AuditAspect` has advice running before `WorkService.doWork()`; it also has a regular method `healthCheck()`.
- `ObserveAspect` has advice targeting any `healthCheck()` method matching its pointcut.
- When the client calls `WorkService.doWork()` via the context, `AuditAspect` advice runs.
- When the client calls `AuditAspect.healthCheck()` via the context, `ObserveAspect` advice **does not run**, even though the pointcut expression matches the method name. The reason is that `AuditAspect` itself is not auto-proxied by Spring AOP.

Project structure:

```text
aspect-bean-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AspectBeanDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>aspect-bean-demo</artifactId>
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
                    <mainClass>demo.AspectBeanDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/java/demo/AspectBeanDemo.java`:**

```java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AspectBeanDemo {

    public static class WorkService {
        public void doWork() {
            System.out.println("SERVICE doWork");
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* demo..*.doWork(..))")
        public void beforeWork() {
            System.out.println("AUDIT before doWork");
        }

        public void healthCheck() {
            System.out.println("ASPECT healthCheck");
        }
    }

    @Aspect
    public static class ObserveAspect {
        @Before("execution(* demo..*.healthCheck(..))")
        public void beforeAspectMethod() {
            System.out.println("OBSERVE before healthCheck");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }

        @Bean
        public ObserveAspect observeAspect() {
            return new ObserveAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            WorkService service = context.getBean(WorkService.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("SERVICE_PROXY="
                    + AopUtils.isAopProxy(service));
            System.out.println("ASPECT_PROXY="
                    + AopUtils.isAopProxy(aspect));

            service.doWork();
            aspect.healthCheck();
        }
    }
}
```

Run in the `aspect-bean-demo` directory:

```bash
mvn -q compile exec:java
```

Lines printed by the program, in order:

```text
SERVICE_PROXY=true
ASPECT_PROXY=false
AUDIT before doWork
SERVICE doWork
ASPECT healthCheck
```

Observations:

1. `SERVICE_PROXY=true` shows that `WorkService` received a Spring AOP proxy because the advice in `AuditAspect` matched `doWork()`.
2. `ASPECT_PROXY=false` shows that the `AuditAspect` bean was not `@AspectJ` auto-proxied, even though `ObserveAspect` has a pointcut matching the `healthCheck()` name.
3. The call `service.doWork()` goes through the proxy, printing `AUDIT before doWork` before the target prints `SERVICE doWork`.
4. The call `aspect.healthCheck()` is a regular method call on the aspect bean; it only prints `ASPECT healthCheck`. **No** `OBSERVE before healthCheck` line appears.
5. Both aspects are present in the container via `@Bean`. The advice not running on the aspect is **not** caused by forgetting to register `ObserveAspect`.

In Maven or the Spring runtime there may be additional tool/logging messages outside the lines printed by the example itself; they do not change the meaning of the lines listed above.

**Try extending it:** create a regular Spring bean named `HealthService` with a public `healthCheck()` method, register it with `@Bean`, retrieve it from the context, and call this method. If `ObserveAspect`'s pointcut matches the method, the call will be advised because that bean is a regular target. This is an independent way to verify that the pointcut is valid and the aspect is registered.

## 5. Why Is an Aspect Called an “Infrastructure Bean” Yet Still Needs Dependency Injection?

An aspect often needs a collaborator such as `AuditSink`, `Clock`, or `MetricsRecorder`. Spring can still create the bean and inject dependencies via constructor:

```java
public interface AuditSink {
    void record(String event);
}

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(* com.example.app.service..*.*(..))")
    public void beforeServiceCall() {
        sink.record("service-called");
    }
}
```

This snippet **illustrates a component inside an application**, not a standalone runnable file: an `AuditSink` implementation, imports, and appropriate scan configuration are needed.

Spring manages `AuditAspect` similarly to many other beans during creation and dependency provisioning. However, when `sink.record(...)` is called, the call to `sink` **can** go through the Spring AOP proxy of the `AuditSink` bean if that bean is advised and injected through a proxy. That is **different** from putting `AuditAspect` itself into a proxy so that advice intercepts its methods.

### Which Responsibilities Should Be Placed in an Aspect?

In Spring AOP, an aspect should primarily coordinate cross-cutting behavior at call boundaries: identify join points, read needed arguments, call collaborators, and proceed to the target when using around advice. If heavy business processing or long I/O is needed, consider extracting that logic into a dedicated Spring bean and injecting it into the aspect.

One benefit of this separation is that you can test, swap, or apply appropriate interceptors to **the dedicated bean**, rather than trying to use another aspect to intercept methods on an `@Aspect` bean.

### Recursion and Overly Broad Pointcuts

If an advice calls `auditSink.record()`, while that same advice's pointcut also covers `AuditSink.record()`, the application can generate an unintended recursive call chain. For collaborator beans, choose a narrow enough pointcut, separate packages by responsibility, or use `!within(...)` / `!bean(...)` conditions appropriately in Spring AOP.

This is a design issue of **the call path to a proxied bean**, distinct from Spring's rule of skipping the `@Aspect` bean itself during auto-proxying.

## 6. Notes on State and Lifecycle of Aspect Beans

Spring usually registers `@Aspect` beans under singleton scope unless the application configures otherwise. Because a singleton is shared by many calls, storing per-request mutable state in an aspect field can lead to race conditions or data mixing across threads:

```java
@Aspect
@Component
public class RequestTraceAspect {
    private String currentUser; // ERROR-PRONE if multiple requests run concurrently
}
```

The `currentUser` field here belongs to the shared aspect instance and is not automatically per-request data. Obtain data from method arguments, Spring request/security context when appropriate, or use a collaborator with the right scope and context propagation. With async/virtual threads, do not assume thread-local context is automatically propagated across every boundary.

This does not change just because the aspect is not auto-proxied: it is still an object with state and lifecycle managed by the container.

Specific note on `@Aspect` and `@Component`: if a class carries both, `@Component` serves scanning; `@Aspect` serves advisor detection and applying the no-auto-proxy-for-aspects rule. Do not use `@Repository` or `@Service` to change the nature of an `@Aspect` expecting another aspect's advice to run on it.

## 7. Common Misconceptions About Calls on Aspects

### 7.1. “If an aspect is a bean, another advice must surely be able to apply to it”

False in Spring AOP `@AspectJ` auto-proxying. Being a **managed bean** is only one part of proxy creation. An aspect is recognized as a source of advice and is intentionally excluded from the target set during auto-proxying.

### 7.2. “Writing a pointcut matching the aspect's method name is enough”

False. A pointcut matching the method is necessary when the target is eligible, but it does not override Spring's decision to skip auto-proxying of aspects.

### 7.3. “Putting `@Order(1)` on an aspect will make it advised by another aspect”

False. `@Order` controls the priority order of aspects/advice participating together in the interceptor chain on an **eligible target bean**. It does not turn an aspect into a target for other advice.

### 7.4. “Enabling `exposeProxy=true` or switching to CGLIB will solve it”

Fundamentally false. `exposeProxy` relates to retrieving the current proxy within an invocation already passing through a proxy; `proxyTargetClass=true` controls JDK/CGLIB proxy selection. Neither option exempts an aspect bean from the `@AspectJ` auto-proxy exclusion rule.

### 7.5. “Only `@Before` is restricted”

False. The issue lies in **the target bean not being auto-proxied**. Even if `@Around`, `@After`, `@AfterReturning`, or `@AfterThrowing` is declared in another aspect, they will not automatically intercept methods of an `@Aspect` bean when no proxy intercepts the call.

### 7.6. “An aspect cannot use an advised service”

False. An aspect can inject and call a Spring service bean. If the service receives a Spring AOP proxy and a pointcut matches, the service's interceptors can run normally. **The service bean** is advised, not **the aspect**.

### 7.7. “Anything carrying `@Aspect` can never have a proxy in any form”

Do not generalize that broadly. Spring's documentation speaks specifically of **ineligibility for Spring AOP `@AspectJ` auto-proxying**. Manually created proxies, other mechanisms, or AspectJ weaving have their own scopes/behaviors; they fall outside the auto-proxy decision considered here. In this lesson's example, `AopUtils.isAopProxy(aspect) == false` accurately reflects the setup used.

## 8. Design and Testing: Putting Logic in the Right Bean

Suppose you want to measure the time taken to record an audit initiated by `AuditAspect`. Trying to write a second aspect intercepting `AuditAspect.writeAudit()` will not achieve the goal with Spring AOP auto-proxying. Move the operation to be measured into a regular collaborator:

```text
Client -> proxy(BusinessService) -> AuditAspect advice
                                      |
                                      v
                              proxy(AuditWriter)
                                      |
                                      v
                         TimingAspect advice -> AuditWriter.write()
```

Skeleton API example:

```java
public interface AuditWriter {
    void write(String message);
}

@Service
public class DatabaseAuditWriter implements AuditWriter {
    @Override
    public void write(String message) {
        // Record audit data, e.g., using the mechanism chosen by the application.
    }
}

@Aspect
@Component
public class AuditAspect {
    private final AuditWriter writer;

    public AuditAspect(AuditWriter writer) {
        this.writer = writer;
    }

    @Before("execution(* com.example.app.service..*.*(..))")
    public void auditCall() {
        writer.write("Business method invoked");
    }
}

@Aspect
@Component
public class TimingAspect {
    @Around("execution(* com.example.app.audit.DatabaseAuditWriter.write(..))")
    public Object timeAudit(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT_WRITE_NS=" +
                    (System.nanoTime() - start));
        }
    }
}
```

This is an **architectural pattern, not a standalone program**: package declarations, imports, and an appropriate Spring context are still required. The point to grasp is that `DatabaseAuditWriter` is a Spring bean **without `@Aspect`**, so Spring can create a proxy for this bean so `TimingAspect` can advise `write(...)`. If `AuditWriter` were replaced by a `writeAudit()` method placed directly inside `AuditAspect`, `TimingAspect`'s advice would not automatically intercept that method under Spring AOP `@AspectJ` auto-proxying.

**Note:** the `DatabaseAuditWriter` class uses `@Service`, so it must lie within the component scan area or be registered equivalently. With JDK proxies, the collaborator is normally injected via the `AuditWriter` interface as shown. The `timeAudit` example for a `void` method still uses `Object` per around-advice signature; Spring handles the return value appropriately when proceeding with the invocation. Timing values depend on machine and workload, so this snippet has no fixed stdout.

Another option when you only want to observe inside `AuditAspect` is to invoke a timer/helper directly in the aspect's own code, or measure in tests. That measurement does not need to be done via another aspect's advice.

## 9. Checklist When Another Aspect Fails to Intercept an Aspect's Method

1. **Right bean and right annotation?** Does the class being called carry `@Aspect`, or is it just a regular Spring service? If it carries `@Aspect`, check the Spring AOP auto-proxy exclusion rule before checking the pointcut.
2. **Is the aspect registered?** Is there `@Bean`, `@Component` with component-scan, or an equivalent declaration? `@Aspect` alone is not enough for registration.
3. **Is `@AspectJ` support enabled?** With plain Spring, configure `@EnableAspectJAutoProxy` and related dependencies; with Boot, verify the active starter/auto-configuration.
4. **Are you inspecting the real bean from the context?** Use `AopUtils.isAopProxy(context.getBean(...))` to tell whether a Spring AOP proxy exists on the actual reference.
5. **Does the pointcut intercept other target beans?** Try a normal service matching the same kind of expression. If advice runs on the service but not on the aspect, the cause may be the aspect exclusion rule.
6. **Is the logic placed in the right location?** If you want advice on behavior initiated by an aspect, move reusable logic into a Spring collaborator bean and have the aspect inject it through a proxy.
7. **Is an infinite loop created?** If an aspect calls a collaborator already advised by another aspect, recheck the pointcuts of all related advisors.
8. **Are you confusing Spring AOP with another weaving mechanism?** The proxy conclusions in this lesson apply only to Spring AOP; if the project uses actual AspectJ weaving, evaluate it according to its own runtime/configuration.

## 10. Self-Check Questions

**1.** A class has `@Aspect` but lacks `@Component` and is not declared via `@Bean`. Will Spring automatically use its advice solely because of `@Aspect`?  
**Answer:** No. Spring must register the aspect as a proper bean for `@AspectJ` auto-proxy support to detect it.

**2.** Two aspects `A` and `B` are both Spring beans. `B` declares `@Before` matching method `A.ping()`. Will Spring AOP auto-proxy `A` to run `B`?  
**Answer:** No. `@Aspect` beans are excluded from Spring AOP auto-proxying.

**3.** If `A` calls a Spring service `S` to which `B` has an applicable pointcut, can `B` run?  
**Answer:** Yes, when `S` is an eligible bean, receives a proxy, and `A`'s call goes through that proxy.

**4.** Why cannot `@Order` fix the case where `B` does not advise `A`?  
**Answer:** `@Order` orders advice on a target that already has an interceptor chain; it does not make an aspect an eligible target.

**5.** `AopUtils.isAopProxy(auditAspect)` returns `false`, yet `AuditAspect` still logs calls to `PaymentService.pay()`. Is there a contradiction?  
**Answer:** No. `AuditAspect` is the source of advice; the Spring AOP proxy sits on `PaymentService`, and does not need to sit on `AuditAspect`.

**6.** What design is appropriate when wanting to time an I/O operation called by an aspect?  
**Answer:** Extract the I/O operation into an injected Spring collaborator bean that can be proxied; or time it directly inside the aspect's code depending on requirements, avoiding expecting another aspect's advice to intercept an aspect's internal method.

## Official Documentation

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): aspect beans are declared like normal beans, `@Aspect` is insufficient for component-scan, and official note that aspects are not advised by other aspects via Spring AOP.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): enabling `@AspectJ` auto-proxy processing via Java configuration or XML.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy/target, method interception limitations, and self-invocation.
- [Spring Framework — Using the Auto-Proxy Facility](https://docs.spring.io/spring-framework/reference/core/aop-api/autoproxy.html): role of auto-proxy creators and bean post-processing infrastructure.
