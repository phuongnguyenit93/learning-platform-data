# The Interceptor Chain When a Method Is Called Through a Spring AOP Proxy

## 1. Key Takeaways

When a client calls a method **through a Spring AOP proxy**, Spring can execute multiple interceptors/advice before forwarding to the actual method on the target. Each interceptor in the chain decides **whether to continue calling further**, and also has the opportunity to observe or handle the result/exception when the inner call returns.

Core mental model:

```text
Client
  |
  v
Spring AOP proxy
  |
  v
Interceptor A: before
  |
  +--> Interceptor B: before
         |
         +--> Interceptor C: before
                |
                +--> Target.method()
                |
         <-- Interceptor C: after / error handling
  <-- Interceptor B: after / error handling
<-- Interceptor A: after / error handling
  |
  v
Client receives result or exception
```

Equivalent nested call shape:

```java
return interceptorA.invoke(() ->
        interceptorB.invoke(() ->
                interceptorC.invoke(() ->
                        target.method())));
```

This snippet is **pseudocode only**, not a Spring Java API. The thing to remember is that Spring processes the chain using **nested calls**: entering from outside to inside, then exiting from inside to outside. Therefore, a higher-priority interceptor usually runs its "before" logic earlier and its "after" logic later.

**Lesson scope:** explains the interceptor chain in **Spring AOP**'s auto-proxy mechanism for *method execution* on Spring beans. The lesson does not extend to AspectJ compile-time/load-time weaving or general aspect theory.

## 2. How Does Spring Prepare the Chain Before the Call Executes?

During container startup, Spring's auto-proxy creator finds advisors applicable to the bean. An advisor combines a join point selection condition (a pointcut, for applicable advisors) and an advice. With `@AspectJ` configuration, Spring reads advice methods declared in `@Aspect` beans, builds corresponding advisors, and can create a proxy for the target bean.

When the client actually calls a method through the proxy, the flow is described as follows:

1. **The proxy receives the call**. It can be a JDK dynamic proxy or a class-based proxy (CGLIB), depending on the target and configuration. Proxy types differ, but the interceptor chain principle is similar.
2. **Spring identifies the target and method**, then collects interceptors/advice matching the current method. The candidate set can be computed/cached according to configuration; for some dynamic pointcuts, conditions are also checked per call.
3. **Advisors are ordered** by their configured priority. Advice forms like `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` can also be adapted by Spring into interceptors to participate in the chain.
4. **An invocation object** holds information about the method, target, arguments, and current position in the interceptor chain.
5. **The call proceeds through each interceptor** via `proceed()`. At the end of the chain, Spring finally calls the real method on the target.
6. **The return value or exception unwinds outward** through the interceptors that proceeded. Each interceptor can run post-logic, handle errors, return a result, or throw an exception.

Note: this is a behavioral model, **not a guarantee** that Spring always rebuilds the advisor list from scratch for every method call; the implementation can cache lookup results and optimize many steps. From an application perspective, what matters is the order of selected advice, pointcut conditions at invocation time, and the path of `proceed()`.

### A Closer Look at the Spring AOP API

At a lower API level, Spring supports the interface:

```java
import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;

class TraceInterceptor implements MethodInterceptor {
    @Override
    public Object invoke(MethodInvocation invocation) throws Throwable {
        System.out.println("enter " + invocation.getMethod().getName());
        try {
            Object result = invocation.proceed();
            System.out.println("return " + result);
            return result;
        } catch (Throwable error) {
            System.out.println("throw " + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

This is an **API illustration snippet, not a standalone application**. Spring calls `invoke(MethodInvocation)` for an interceptor installed in the chain. When `invocation.proceed()` runs, control passes to the **next interceptor**, or to the target if the chain has ended. With annotation-based `@Around`, you usually work with `ProceedingJoinPoint.proceed()`; Spring connects that mechanism to the call chain beneath the proxy layer.

## 3. What Does `proceed()` Actually Mean?

In Spring AOP, `proceed()` **does not mean "immediately call the target regardless of other advice"**. It continues **the rest of the chain** inside the current interceptor.

If the order is `A → B → C → target`, then:

- When A calls `proceed()`, control enters B.
- When B calls `proceed()`, control enters C.
- When C calls `proceed()`, Spring continues to the target if no more interceptors remain.
- After the target returns, C resumes the code after C's `proceed()`; in turn B and then A continue their post-logic.
- If the target or an inner interceptor throws an exception, the exception unwinds back through the open call frames, unless an interceptor catches or alters it.

With `@Around`, this call is optional and decided by the advice:

| Behavior in around advice | Impact on the call |
| --- | --- |
| Call `proceed()` once, return the result | Normal path: continue through the chain and return the result |
| Do not call `proceed()` | **Short-circuit**: inner interceptors and the target are not invoked along this branch |
| Call `proceed()` multiple times | Can cause the remaining chain and target to execute multiple times; only do when intentional and safe |
| `return` a different value | Caller receives the value decided by the around advice, provided it matches the method contract |
| `catch` exception then re-`throw` | Caller still receives the error; outer interceptors can observe it |
| `catch` exception and return a fallback | Caller receives the fallback; outer interceptors see a normal completion instead of an error |

For `@Before`, Spring runs the advice beforehand and then automatically continues to the rest if the advice does not throw an exception; the author of `@Before` **does not need and does not have permission to call `proceed()` directly**. Similarly, `@AfterReturning` or `@AfterThrowing` do not use `proceed()` like an `@Around`.

## 4. Standalone Example: Two Nested Around Interceptors

The example below uses **Java 17+, Maven, Spring Framework 6.2.6**. We declare two aspects with explicit ordering:

- `OuterAspect`: `@Order(1)`, higher priority.
- `InnerAspect`: `@Order(2)`, lower priority.
- Both `@Around` advice match the `execute(...)` method of the same Spring service.

The example prints the entire entry/exit path, including when the method throws an exception. Spring Boot is not needed; `AnnotationConfigApplicationContext` is used to observe Spring AOP directly.

Structure:

```text
spring-interceptor-chain/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InterceptorChainDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-interceptor-chain</artifactId>
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
                    <mainClass>demo.InterceptorChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/java/demo/InterceptorChainDemo.java`:**

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
import org.springframework.core.annotation.Order;

public class InterceptorChainDemo {
    public interface WorkService {
        String execute(String value);
    }

    public static class WorkServiceImpl implements WorkService {
        @Override
        public String execute(String value) {
            System.out.println("TARGET " + value);
            if ("fail".equals(value)) {
                throw new IllegalArgumentException("bad request");
            }
            return "DONE:" + value;
        }
    }

    @Aspect
    @Order(1)
    public static class OuterAspect {
        @Around("execution(* demo..*.execute(..))")
        public Object wrap(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("OUTER enter");
            try {
                Object result = pjp.proceed();
                System.out.println("OUTER return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println("OUTER throw " + error.getMessage());
                throw error;
            } finally {
                System.out.println("OUTER finally");
            }
        }
    }

    @Aspect
    @Order(2)
    public static class InnerAspect {
        @Around("execution(* demo..*.execute(..))")
        public Object wrap(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("INNER enter");
            try {
                Object result = pjp.proceed();
                System.out.println("INNER return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println("INNER throw " + error.getMessage());
                throw error;
            } finally {
                System.out.println("INNER finally");
            }
        }
    }

    @Configuration
    @EnableAspectJAutoProxy
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkServiceImpl();
        }

        @Bean
        public OuterAspect outerAspect() {
            return new OuterAspect();
        }

        @Bean
        public InnerAspect innerAspect() {
            return new InnerAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            System.out.println("AOP_PROXY=" + AopUtils.isAopProxy(service));

            System.out.println("=== SUCCESS ===");
            String result = service.execute("ok");
            System.out.println("CLIENT " + result);

            System.out.println("=== FAILURE ===");
            try {
                service.execute("fail");
            } catch (IllegalArgumentException ex) {
                System.out.println("CLIENT caught " + ex.getMessage());
            }
        }
    }
}
```

**Run from the directory containing `pom.xml`:**

```bash
mvn -q compile exec:java
```

**Lines printed to stdout by the program, in order** (excluding Maven messages or environment logging):

```text
AOP_PROXY=true
=== SUCCESS ===
OUTER enter
INNER enter
TARGET ok
INNER return DONE:ok
INNER finally
OUTER return DONE:ok
OUTER finally
CLIENT DONE:ok
=== FAILURE ===
OUTER enter
INNER enter
TARGET fail
INNER throw bad request
INNER finally
OUTER throw bad request
OUTER finally
CLIENT caught bad request
```

Why is the order like that?

1. `@EnableAspectJAutoProxy` enables the auto-proxy mechanism; the `@Bean` methods provide both the target service and the two aspects. `@Aspect` classes must be registered as beans for Spring to detect them.
2. Spring creates a proxy for `WorkService` because both pointcuts match `execute(..)`. With the Spring Framework configuration and interface in the example, the proxy is typically a JDK dynamic proxy.
3. `@Order(1)` gives `OuterAspect` higher priority than `@Order(2)`: on **entry**, outer runs before inner. Both call `proceed()`, so the target is executed.
4. On the success branch, the target returns `DONE:ok`. Inner handles return and finally first, then outer handles return and finally, and finally the client receives the result.
5. On the failure branch, the target throws `IllegalArgumentException`. Inner catches it, prints info, and rethrows; outer catches and rethrows; only then does the client receive the exception. The `finally` blocks still execute in unwinding order.

The example intentionally has **one around advice per aspect** to avoid depending on the ordering of multiple advice of the same kind or different kinds within the same aspect.

## 5. What Order Does `@Order` Determine?

Suppose two aspects both advise the same method:

```java
@Aspect
@Order(10)
class MetricsAspect { /* ... */ }

@Aspect
@Order(20)
class AuditAspect { /* ... */ }
```

This is **illustrative code, not standalone runnable classes**. In Spring, a **smaller `@Order` value has higher priority**. When both around advice match the same method:

```text
metrics.enter          <- higher priority: enters first
    audit.enter        <- lower priority: enters later
        target()
    audit.exit         <- lower priority: exits first
metrics.exit           <- higher priority: exits later
```

Because of the nesting mechanism, do not assume "a higher-priority aspect always prints every line before a lower-priority aspect". Only **entry** goes from higher priority to lower priority; **exit** happens in the reverse order.

If two different aspects both apply and no order is specified, **there is no guarantee on relative order**. You can use `org.springframework.core.annotation.Ordered` instead of `@Order`. Do not rely on method declaration order or the order Spring happens to instantiate beans to establish a business contract.

### Multiple Advice in the Same `@Aspect`

In modern Spring Framework, advice types within the same aspect have precedence by kind: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. However, `@After` has **finally** semantics, so in practice it is invoked after `@AfterReturning` or `@AfterThrowing` in the same aspect when those apply. Multiple advice of **the same kind** in one `@Aspect` class do not have a stable order based solely on Java source line order.

If the outcome strictly depends on ordering, prefer separating responsibilities into distinct aspects with explicit `@Order`, or use a single `@Around` to coordinate within a small scope. Do not "fix" it by randomly reordering method declarations.

## 6. How Do Different Advice Kinds Enter the Chain?

Each advice kind has a different contract. In Spring AOP, common forms are:

| Advice kind | Effective timing | Typical effect |
| --- | --- | --- |
| `@Before` | Before proceeding to the target | Checks, logging, precondition validation; can throw an exception causing the call to stop |
| `@Around` | Wraps the rest of the chain | Decides whether to call `proceed()`, alters args/return value, measures duration, retries, or short-circuits |
| `@AfterReturning` | When execution finishes normally | Observes the return value, records outcome metrics; cannot replace the returned reference simply by `return`ing from advice |
| `@AfterThrowing` | When execution exits with a matching exception | Observes exceptions from the join point; not a catch-all callback for every error caused by other advice |
| `@After` | Ends method execution on both normal and error paths | `finally`-style cleanup |

Example advice broken into short snippets inside a Spring `@Aspect` bean:

```java
@Before("execution(* demo..*.execute(..))")
public void beforeExecution() {
    System.out.println("BEFORE");
}

@AfterReturning(
    pointcut = "execution(* demo..*.execute(..))",
    returning = "result"
)
public void afterSuccess(Object result) {
    System.out.println("RETURNED " + result);
}

@AfterThrowing(
    pointcut = "execution(* demo..*.execute(..))",
    throwing = "error"
)
public void afterFailure(Throwable error) {
    System.out.println("THREW " + error.getClass().getSimpleName());
}

@After("execution(* demo..*.execute(..))")
public void finallyExecuted() {
    System.out.println("AFTER finally");
}
```

The methods above are **illustrative snippets**, not a standalone compilable Java file; they require an `@Aspect` class, AspectJ annotation imports, bean registration, and a context. If you put all of them into the same aspect, do not predict stdout order solely by reading declaration order. Use the two-aspect example in section 4 when you need a truly deterministic trace.

Another note: when an inner `@Around` catches an exception and returns a normal fallback, outer advice may see a **successful result**. When an outer `@Around` short-circuits without calling `proceed()`, interceptors inside it — including inner `@Before` and `@After` — have no chance to run.

## 7. Return Values and Exceptions Flowing Through Interceptors

An interceptor does not receive an "isolated copy" of the call. It participates in **the same logical execution path** and produces the result the client receives.

Example Spring around advice returning a fallback when the service fails:

```java
@Around("execution(* demo..*.load(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

This is an **illustrative advice method**; the target's actual return type must be compatible with the fallback value. If this advice sits inside another `@Around`, the outer interceptor may receive the string `"FALLBACK"` as a normal return, even though the target threw an exception.

What happens when an interceptor changes the result?

```text
Caller
  |
  v
Outer interceptor
  |
  v
Recovery interceptor
  |
  v
Target -> throws IllegalStateException
  |
  v
Recovery interceptor catches -> returns "FALLBACK"
  |
  v
Outer interceptor sees normal return "FALLBACK"
  |
  v
Caller receives "FALLBACK"
```

**Do not swallow errors indiscriminately.** Outer interceptors (e.g., transaction, audit, retry) may rely on the result/exception to decide their behavior. An advice that turns an exception into success changes the signal seen by the rest of the chain. Analyze rollback boundaries, retries, logging, and HTTP error mapping when introducing fallbacks in real business logic.

With `@AfterReturning`, you can observe the return value, but `return`ing from the advice method **does not replace** the value the target method returns to the caller. To intentionally replace the return value, use `@Around` and return an appropriate object.

## 8. Where Do Pointcuts and Method Matching Fit in the Chain?

When a client calls the proxy, Spring only needs to execute the interceptors determined to match the method. Two things must be distinguished:

- **Whether there is a proxy:** the auto-proxy creator decides whether the bean needs a proxy based on matching advisors/conditions.
- **Which advisors match the current call:** the proxy determines the interceptor chain for the specific method; some pointcuts may additionally check args at call time.

For static pointcuts based on method signatures, interceptors can be selected per method and cached. For dynamic matching forms, the checker can use the arguments of the invocation itself. Just because a bean has a proxy does not mean every method on the bean runs all advisors.

Example:

```java
@Around("execution(* demo..*.execute(..))")
public Object aroundExecute(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

This is an **illustrative advice**: the `execution` expression matches *method executions* named `execute` within the matching package scope. It does not automatically match `cancel` or `status` methods on the same bean. If a method matches no advisor, Spring can invoke the target without running that advice logic.

**A Spring AOP proxy does not intercept constructors, field reads/writes, or arbitrary call sites**. The main boundary is *method execution join points* going through the Spring proxy. When the target calls `this.anotherMethod()`, the internal call runs directly on the target and normally bypasses advice matching only `anotherMethod()`, because it does not go through the proxy.

## 9. Two Proxy Forms, One Chain Principle

Spring AOP has two common proxy paths:

| Proxy type | How the client enters | Interceptor chain |
| --- | --- | --- |
| JDK dynamic proxy | Calls through an interface implemented by the proxy | Applies interceptors/advisors matching the call |
| CGLIB class-based proxy | Calls an eligible method on the proxy subclass | Applies interceptors/advisors matching the call |

How the proxy is created affects which methods can be intercepted and how beans are injected, but **does not change the meaning of `proceed()`**: continuing the chain toward the target.

Some limitations when using class-based proxies: a `final class` cannot be subclassed to create a CGLIB proxy; a `final method` or `private method` cannot be advised via the override mechanism. With a JDK proxy, callers interact through the proxy's interfaces; casting to the implementation class can fail.

Whether JDK or CGLIB is chosen, a direct call to a manually `new`'d object (not obtained from the Spring container) does not automatically go through the Spring AOP interceptor chain. When the same class calls its own method via `this`, that is also a call outside the proxy entry point.

## 10. Interceptor Chains in Spring Transactions, Caching, and Async

In a real Spring application, you can encounter an interceptor chain from multiple sources rather than only the `@Aspect`s you wrote yourself:

- **Transaction:** an interceptor associated with `@Transactional` may open or join a transaction before the inner part of the chain runs; on exit, it commits/rolls back according to the result, exception, and configured rules.
- **Cache:** an interceptor for `@Cacheable` can return a cached result without calling the target; on a cache miss, it can continue the chain to obtain the value.
- **Async:** the `@Async` mechanism can hand execution off to another executor/thread; the interceptor kind and continuation depend on configuration, so do not assume synchronous ordering like the console example when async is enabled.

All of these involve the caller interacting with a Spring bean through a proxy, yet each feature has its own semantics. **Do not assume** Spring places transaction/cache/async and your application `@Aspect` in a fixed order across every project: you must check `@Order`, `Ordered`, and the effective configuration of infrastructure advisors.

For example, if an around advice has higher priority than the transaction interceptor, code before `proceed()` in the around advice runs **before** the inner transaction starts; code after `proceed()` in the around advice runs **after** the inner transaction has finished processing. Whether you want metrics inside or outside the transaction, specify the ordering explicitly and verify the actual trace.

## 11. Debugging an Interceptor Chain Not Running as Expected

When logs do not appear or appear out of order, check in the following order:

1. **Is the client calling through the Spring proxy?** Inject or retrieve the bean from the context; avoid `new Implementation()` and recognize self-invocation via `this`.
2. **Is it actually an AOP proxy?** Use `AopUtils.isAopProxy(bean)`. This is only the first step: having a proxy does not mean every method has advice.
3. **Does the advisor match the method being called?** Check package, method name, access modifier, parameter types, annotations, target type, bean name, and runtime arguments.
4. **Are the aspects Spring beans?** `@Aspect` must be registered by the Spring container; plain Spring Framework may require `@EnableAspectJAutoProxy`, while Boot may enable it automatically with the appropriate starter and conditions.
5. **Is `@Order` ordering explicit?** Lower numbers enter earlier and exit later. If no order is defined between different aspects, do not predict fixed stdout.
6. **Is an interceptor short-circuiting?** Check `@Around` advice, cache hits, or early returns before `proceed()`; inner interceptors/target will not run.
7. **Was an exception caught or converted to a fallback?** An outer interceptor may see a normal return when an inner one handled the exception. Conversely, an interceptor throwing a new exception can mask the target's result.
8. **Is `proceed()` called multiple times?** Repeated runs can cause multiple data writes; only use intentionally such as controlled retries.
9. **How many advice are in the same aspect?** With multiple advice of the same kind, do not expect ordering based on Java source position.
10. **Is it an asynchronous call?** Observe thread/context and executor boundaries; a multi-threaded trace does not reflect a single sequential call stack like the simple example.

If you need to inspect from Java, you can use the `org.springframework.aop.framework.Advised` API on Spring AOP proxies that support it to view advisors:

```java
Object bean = context.getBean(WorkService.class);
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

This is a **supplementary snippet** for an application with a Spring context and `WorkService`, not a standalone example. It helps inspect advisors attached to the proxy, but is no substitute for determining **which advisor actually matches the method invocation** or dynamic runtime conditions. For proxies configured as frozen/opaque or other proxy types, inspection may differ.

## 12. Self-Check Scenarios

**A.** A chain has A `@Order(1)` and B `@Order(5)`, both `@Around`, both calling `proceed()` once. Target returns normally. Order?  
**Answer:** A-enter, B-enter, target, B-exit, A-exit.

**B.** A enters before B, but A immediately returns a value without calling `proceed()`. Do B and target run?  
**Answer:** No. A short-circuits the inner part of the chain.

**C.** Target throws an exception, B catches it and returns a normal fallback. What does outer A see when A's `proceed()` returns?  
**Answer:** A normal return value returned by B; the exception was handled by B. A does not automatically see the original error unless communicated otherwise.

**D.** Why does an `@AfterReturning` not replace the return value by doing `return "new"`?  
**Answer:** `@AfterReturning`'s contract is to run after successful execution and observe the result; to change the result, use around advice with an appropriate return value.

**E.** Method `process()` on the target calls `this.save()`, while advice only matches `save()`. Does the advice run via `process()`'s interceptor chain?  
**Answer:** Not for this internal call. The call `this.save()` does not re-enter the Spring proxy.

**F.** Two aspects have multiple advice kinds without declaring `@Order`. Can Java source declaration order be treated as a reliable execution order?  
**Answer:** No. Specify ordering between aspects and explicitly design cases with multiple advice of the same kind.

## 13. Official Spring Framework Documentation

- [Spring AOP — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Around`, `proceed()`, return/exception advice, and ordering rules.
- [Spring AOP APIs — Advice](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` and `MethodInvocation.proceed()`.
- [Spring AOP — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, path through proxy, self-invocation.
- [Spring AOP — Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method-execution pointcuts and applicability conditions.
