# Target Bean Scope Does Not Automatically Change Aspect Scope in Spring AOP

## 1. A Commonly Misunderstood Scenario

A Spring `@Aspect` records calls to `JobService`. A developer changes `JobService` from singleton to `@Scope("prototype")` and expects each `JobService` to also get its own copy of the aspect. In Spring AOP, that reasoning is **incorrect**.

**Target bean scope, Spring proxy lifecycle, and `@Aspect` bean lifecycle are separate decisions.** A singleton aspect can still advise multiple target instances, including targets with prototype/request/session scope.

This lesson covers only **Aspects in Spring**, the Spring bean factory, Spring AOP proxies, and advice execution scope. General AOP concepts are not repeated.

## 2. Three Objects to Distinguish

| Component | Role | Who decides its lifecycle? |
| --- | --- | --- |
| **Aspect bean** | Holds `@Before`, `@Around`, ... methods and advice dependencies | The Spring IoC container, the aspect's bean definition; singleton by default with `@Component` or `@Bean` |
| **Target bean** | Holds the business logic to which advice is applied | The target's bean definition: singleton, prototype, request, session, or custom scope |
| **AOP proxy** | The object the caller actually invokes so interceptors/advisors run | Proxy/advisor configuration and bean lifecycle; may add a scoped proxy when needed |

Looking only at `this`, `getClass()`, or proxy identity is not enough to conclude what scope the target has. With a request/session **scoped proxy**, one proxy reference can live long and delegate to different targets depending on the scope; with a **prototype bean** retrieved directly from `getBean()`, each lookup can create a new instance/proxy.

In a singleton `@Aspect`, fields are shared state across advice invocations. Two different targets **do not** turn those fields into separate state.

## 3. Incorrect Example: Storing Target State in an Aspect Field

~~~java
@Aspect
class WrongTrackingAspect {
    private String lastJobId;

    @Before("execution(* demo.JobService.execute(..))")
    public void before(JoinPoint jp) {
        lastJobId = ((JobService) jp.getTarget()).toString();
    }

    @After("execution(* demo.JobService.execute(..))")
    public void after() {
        // lastJobId may have been written by another target/proxy/call.
        System.out.println("completed " + lastJobId);
    }
}
~~~

Even if every `JobService` is a prototype, the singleton `WrongTrackingAspect` still has one `lastJobId` field. When two calls interleave, user A may log B's ID by mistake. The same bug happens when storing `JoinPoint`, request context, exception, `StopWatch`, `startNanos`, or an argument list in an aspect field.

The best approach for measuring across an invocation is usually a **local variable**:

~~~java
@Around("execution(* demo.JobService.execute(..))")
public Object time(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        // Record metric via a thread-safe dependency; do not store started in a field.
        System.out.println("elapsedNanos=" + elapsed);
    }
}
~~~

This is a snippet about scope, not an example for deterministic stdout: timing is nondeterministic and the Spring `@Around` must be registered in the container to run.

## 4. Java 17 + Spring Framework Demo: Prototype Target, Singleton Aspect

The following demo illustrates **two different targets**, **two proxies**, yet **one aspect bean** with a total advice count of two. All required code is listed.

~~~text
spring-aop-target-vs-aspect-scope/
  pom.xml
  src/main/java/demo/JobService.java
  src/main/java/demo/JobServiceImpl.java
  src/main/java/demo/AuditAspect.java
  src/main/java/demo/App.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-target-vs-aspect-scope</artifactId>
  <version>1.0.0</version>
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
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**JobService.java**

~~~java
package demo;

public interface JobService {
    String execute();
}
~~~

**JobServiceImpl.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class JobServiceImpl implements JobService {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    @Override
    public String execute() {
        return "job-" + id;
    }
}
~~~

Each target instance keeps its own `id`. `NEXT_ID` only serves to show that the constructor created two different targets; it is not aspect state.

**AuditAspect.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(* demo.JobService.execute(..))")
    public void beforeExecution() {
        System.out.println("aspectCall=" + calls.incrementAndGet());
    }

    public int callCount() {
        return calls.get();
    }
}
~~~

The aspect counter is **intentional** shared state and uses `AtomicInteger` for thread-safe concurrent increments. If you need to separate metrics per target, use a stable key in a concurrent registry and consider cleanup/lifecycle, rather than putting a `lastTarget` field on the singleton aspect.

**App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class App {
    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect(); // singleton by default for @Bean
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public JobService jobService() {
        return new JobServiceImpl();
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(App.class)) {
            JobService one = ctx.getBean(JobService.class);
            JobService two = ctx.getBean(JobService.class);

            AuditAspect aspectOne = ctx.getBean(AuditAspect.class);
            AuditAspect aspectTwo = ctx.getBean(AuditAspect.class);

            System.out.println("first=" + one.execute());
            System.out.println("second=" + two.execute());
            System.out.println("differentProxies=" + (one != two));
            System.out.println("aopProxy=" + AopUtils.isAopProxy(one));
            System.out.println("sameAspect=" + (aspectOne == aspectTwo));
            System.out.println("adviceCalls=" + aspectOne.callCount());
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
~~~

Expected `System.out` output produced by the application:

~~~text
aspectCall=1
first=job-1
aspectCall=2
second=job-2
differentProxies=true
aopProxy=true
sameAspect=true
adviceCalls=2
~~~

Reason: the `jobService()` bean method has prototype scope, so two `getBean(JobService.class)` calls create two separate targets. Spring AOP recognizes `AuditAspect`, creates an advisor for `JobService.execute()`, and creates a proxy for each bean that needs advice. The `AuditAspect` bean remains a singleton, is invoked twice, and increments the same `AtomicInteger`.

This is **expected output verified statically** against Spring AOP/Java APIs; Maven execution in the current environment is not claimed.

## 5. What Does Changing Target Scope Change?

### Singleton target

A singleton bean is usually retrieved repeatedly under the same proxy/target reference within a context. If matched by advice, multiple callers go through the same proxy; the aspect can also be a singleton. Target and aspect are **two different singletons**, and do not share each other's fields.

### Prototype target

Each time the container creates a new prototype bean, it can have a new target and a new proxy. If a singleton bean is injected once with a regular prototype bean, that prototype reference **does not automatically switch targets after each method call**. To get a new instance on demand, use `ObjectProvider<JobService>` or an appropriate lookup method:

~~~java
@Component
class WorkCoordinator {
    private final ObjectProvider<JobService> jobServices;

    WorkCoordinator(ObjectProvider<JobService> jobServices) {
        this.jobServices = jobServices;
    }

    void runTwice() {
        jobServices.getObject().execute();
        jobServices.getObject().execute();
    }
}
~~~

The snippet requires importing `org.springframework.beans.factory.ObjectProvider` and `org.springframework.stereotype.Component`, along with a prototype bean definition of `JobService`. Even though there are two targets across the two calls, the singleton aspect is still shared.

### Request- or session-scoped target

In a web application, a scoped proxy can be a long-lived injected object that delegates to different request/session targets according to the active context. Therefore, **having the same proxy reference does not prove having the same target reference**.

Common annotation example in web applications:

~~~java
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
@Component
class RequestJobService { /* ... */ }
~~~

This is an illustrative configuration snippet for a web environment, requiring imports of `org.springframework.context.annotation.Scope`, `ScopedProxyMode`, and `Component`; the Maven demo in section 4 does not need request scope and does not create a web request context.

## 6. Aspect Scope and Instantiation Models

In Spring's proxy-based `@AspectJ` support, the common and Spring AOP-supported model is **singleton aspects**. AspectJ instantiation models such as `perthis`, `pertarget`, and `percflow` are not a built-in Spring AOP proxy mechanism for creating a new aspect per target or per invocation.

If per-target state is needed, consider placing it on the target (when domain-appropriate), in a scope-resolved dependency, or using a registry keyed by target lifecycle with explicit cleanup. If the problem truly requires AspectJ instantiation or field/method join points outside Spring proxy execution, that is a separate AspectJ weaving integration design requirement, not a consequence of `@Scope` on a Spring target.

Avoid putting `@Scope("prototype")` on an aspect and **assuming by default** that every proxy target will receive its own aspect instance. Test the actual lifecycle of your configuration if designing outside the usual singleton model.

## 7. Consequences of Using Multiple ApplicationContexts

Singleton means **one instance per Spring bean definition within each corresponding container**, not necessarily strictly one instance per JVM.

- Two independent ApplicationContexts can create two different singleton aspect beans, each with its own counter.
- Parent/child contexts and bean visibility can cause an aspect to be registered in multiple places or advisors to appear unexpectedly.
- Prototype targets within the same context can still be advised by a singleton aspect.
- If tests create a new context, static fields like `JobServiceImpl.NEXT_ID` in the demo have a different lifecycle from Spring bean scope; do not equate Java static state with Spring singleton scope.

To distinguish them, inspect `ctx.getBean(AuditAspect.class)`, `ctx.isSingleton("auditAspect")`, `ctx.isPrototype("jobService")`, and via `AopUtils.isAopProxy`.

## 8. Conditions for Advice to Actually Run

Changing scope does not fix the underlying limitations of Spring AOP:

1. Callers must go through the Spring AOP proxy. Objects created with `new JobServiceImpl()` outside Spring are not automatically advised.
2. Self-invocation (`this.execute()` inside the target) does not go back through the corresponding proxy.
3. Spring AOP focuses on **method execution**, not directly intercepting constructors or field access.
4. JDK dynamic proxies expose interface methods; class-based proxies have limitations with `final`, `private`, and non-overridable methods.
5. The pointcut must actually match the target method, and the aspect/advisor must be registered in the right context.

Thus, if advice seems to run once and then stop, before concluding that scope "switched" the aspect, check whether the second call obtained a proxy from Spring or used a raw instance.

## 9. Concurrent Calls Still Share the Aspect

A prototype target can reduce field sharing **inside the target**, but it does not eliminate the possibility of two calls running concurrently inside the same singleton aspect. Similarly, a request scoped proxy may invoke different request-specific targets while using the same aspect recorder.

Do not do the following:

~~~java
@Aspect
class RiskyAspect {
    private long startedAt;
    private String currentUser;

    @Around("execution(* demo.JobService.execute(..))")
    Object around(ProceedingJoinPoint pjp) throws Throwable {
        startedAt = System.nanoTime();
        currentUser = findUser(); // assume a private helper
        return pjp.proceed();
    }
}
~~~

Place `startedAt` and user context in local variables or a scoped dependency with a clear contract. `ThreadLocal` is not automatically "per request" in `@Async`/reactive flows; if you use it, you must cleanup/restore and understand thread boundaries.

`AtomicInteger` works well for counters, but invariants spanning multiple fields or multiple map operations require synchronization or an overall atomic operation. Also, **do not keep references to prototype targets in a map forever** without eviction, as that creates a memory leak.

## 10. Testing Lifecycle and Advice Behavior

A practical integration test suite should assert:

| Check | Expectation in demo configuration |
| --- | --- |
| `ctx.isPrototype("jobService")` | `true` |
| `ctx.isSingleton("auditAspect")` | `true` |
| `ctx.getBean(JobService.class)` twice | Two different references |
| `ctx.getBean(AuditAspect.class)` twice | Same reference |
| `AopUtils.isAopProxy(jobService)` | `true` |
| Call `execute()` on both proxies | Aspect counter increments by two |
| Instantiate `new JobServiceImpl()` and call directly | Not automatically advised by Spring |
| Two threads call two targets concurrently | Shared aspect fields must be thread-safe |

When testing races, use `CountDownLatch`/barriers and assertions instead of relying on log order across threads; the scheduler does not guarantee output order. With Java 17, do not infer thread safety just because a single test run passes.

## 11. Common Pitfalls and How to Debug

**"The target is prototype now, why does the aspect only have one constructor call?"** — They are two separate bean definitions. Check `ctx.isSingleton("auditAspect")` and the target's own bean scope.

**"A proxy was injected into a singleton, why doesn't the target change?"** — Regular prototype injection happens once at injection time. Use `ObjectProvider` if you genuinely need a new prototype each time; for request-scoped proxies, configure delegation according to the appropriate scope.

**"Two different targets yet logs show the same user/startTime?"** — The aspect stored invocation data in a shared field. Fix with local variables and thread-safe dependencies.

**"I added `@Aspect` but nothing logs?"** — Check `@EnableAspectJAutoProxy`, advisor/pointcut, Spring-managed bean status, JDK/CGLIB proxy, method visibility, and self-invocation.

**"Single-threaded tests pass, production mixes requests?"** — Race bugs require testing with concurrency and data assertions, not just counting log lines.

## 12. Reference Documentation

- Spring Framework Reference — `@AspectJ` support and instantiation models: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — `@Bean`, `@Scope`, and Java-based configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html

**Practical takeaway:** Verify target scope, aspect scope, and proxy type **independently**. Even when the target is prototype or request-scoped, never put per-invocation data into fields of a singleton `@Aspect`; use local state and prove thread safety for genuinely shared data.