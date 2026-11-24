# proceed() to Continue the Interceptor Chain and Target Method in Spring AOP

## 1. The Core Problem

In **proxy-based Spring AOP**, an `@Around` advice has the authority to run code before and after a method call selected by a pointcut, and to decide **whether to continue that call path**. The single most important decision point is:

~~~java
Object result = pjp.proceed();
~~~

In this snippet, `pjp` is `org.aspectj.lang.ProceedingJoinPoint`, passed by Spring into the advice method. `proceed()` **transfers control to the rest of the Spring AOP interceptor/advice chain**, and at the end of the chain it reaches the actual target method **unless an inner interceptor explicitly returns or throws an error before then**.

In particular, `proceed()` must not be understood as a simple command equivalent to `target.method()`:

- It passes through **the remaining advisors/interceptors** applicable to the current invocation.
- An inner interceptor may log, start a transaction, serve a cache hit, block the call, or throw an exception.
- Only when the inner chain forwards all the way to the end is the target method actually invoked.
- Return values and exceptions travel back from the inner chain to `@Around`, and ultimately to the caller, unless the outer advice alters them.
- From an API standpoint, `proceed()` can be called **once, multiple times, or zero times**; this choice dramatically changes business behavior.

**Lesson scope:** this lesson focuses strictly on `@Around` and the Spring Aspect/Spring AOP chain on Spring-managed beans; it does not repeat general Aspect concepts or explain AspectJ bytecode weaving as an equivalent mechanism.

## 2. Boundary of a Spring AOP Call

The diagram illustrates a `GreetingService` bean intercepted by two advisors:

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> Outer @Around advice
   |      |
   |      +--> before proceed()
   |      |
   |      +--> pjp.proceed()
   |                |
   |                +--> Inner @Before advice
   |                |
   |                +--> Other advisor/interceptor, if any
   |                |
   |                +--> target.greet(...)
   |                |
   |                +--> returns result or throws Throwable
   |      |
   |      +--> after proceed() / catch / finally
   |
   v
Caller receives result or Throwable
~~~

When Spring prepares a bean, the auto-proxy creator finds **matching advisors** based on `@Aspect` beans, pointcuts, and types/methods. When a client invokes a method **through the proxy**, Spring executes the interceptor chain for that invocation. Advisor ordering determines who sits on the outside and who sits on the inside.

At `pjp.proceed()`:

1. The execution chain advances to the next applicable advisor.
2. If the next advisor is `@Before`, its logic runs before forwarding continues.
3. If an inner `@Around` **does not call proceed**, the call may stop right there without the target running.
4. When no interceptors remain, Spring invokes the target method on the target object.
5. The result or exception returns back through the interceptors that were entered.

Therefore, you should say **"proceed continues the interceptor chain toward the target"**, rather than "proceed is guaranteed to call the target directly right away."

## 3. A Properly Structured @Around Advice

Example inside a Spring-managed `@Aspect`:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    @Around("execution(* example.GreetingService.greet(..))")
    public Object aroundGreet(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("duration nanos: " + elapsed);
        }
    }
}
~~~

Key points to understand:

- `@Around` declares a pointcut so Spring knows **which calls are wrapped**.
- The **first** parameter of an around advice must be `ProceedingJoinPoint`.
- The `Object` return type lets the advice pass through or transform the return value. For target methods that return a value, do not declare the around advice as `void`, because Spring may return `null` to the caller.
- `throws Throwable` allows exceptions from the inner method/advisors to continue propagating outward; avoid catching and swallowing errors unintentionally.
- `pjp.proceed()` is the entry point into the inner chain.
- `finally` still runs whether the inner chain returns or throws an exception, provided the invocation entered this advice.
- The `start` variable is local **per invocation**, so it is not overwritten across concurrent threads like a shared mutable field on a singleton aspect.

This is an **illustrative snippet**, not a full standalone project; the complete project in section 6 produces deterministic stdout.

## 4. Comparing "With proceed" vs. "Without proceed"

### 4.1. With `proceed()`

~~~java
@Around("execution(* example.GreetingService.greet(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    Object value = pjp.proceed();
    System.out.println("after");
    return value;
}
~~~

For a target `greet()` that returns normally, the log sequence typically looks like:

~~~text
before
<inner advice, if any>
<target method>
after
~~~

The "after" section following `proceed()` **does not run if `proceed()` throws an exception**, unless you handle it separately with `catch` or `finally`.

### 4.2. Without Calling `proceed()`

~~~java
@Around("execution(* example.GreetingService.cached(..))")
public Object cachedValue(ProceedingJoinPoint pjp) {
    return "CACHED";
}
~~~

If this advice is invoked and returns `"CACHED"` **without proceeding**:

- The caller receives the value produced by the advice.
- The **inner** interceptors/advice were not invoked for this call.
- The target method **is not called** on this execution path.
- This may be **intentional** behavior for a cache hit, a call-blocking policy, or mock/test interception.
- If `proceed()` is omitted by mistake, business logic can silently "disappear" in a way that is very hard to diagnose.

**Do not misunderstand:** if an outer advice has already run, that outer advice's own "after/finally" logic can still execute even if it short-circuits. Saying "all advice is skipped" is false; only the layers not forwarded to are skipped.

### 4.3. Calling `proceed()` Without Returning Its Result

~~~java
// This approach is unsuitable for methods with a return value:
@Around("execution(* example.GreetingService.greet(..))")
public Object incorrect(ProceedingJoinPoint pjp) throws Throwable {
    pjp.proceed();
    return null;
}
~~~

The target method **may have executed successfully**, yet the caller sees `null` instead of the real result. If the outer return type is a primitive, Spring attempting to convert `null` to a primitive can throw an error. By default, use `return pjp.proceed();`, unless you are **intentionally** transforming or replacing the result under a clear contract.

## 5. Return Values and Exceptions Flowing Through proceed()

### 5.1. Normal Return

~~~java
Object result = pjp.proceed();
return result;
~~~

The value from inner layers is passed back to the caller. An around advice can also perform post-processing:

~~~java
Object result = pjp.proceed();
return ((String) result).trim();
~~~

The snippet above is **only safe** when the pointcut is strictly scoped to methods returning non-null `String` and trimming is part of the business contract. Do not cast/trim blindly on a pointcut matching arbitrary methods.

### 5.2. Target or Inner Interceptor Throws an Exception

~~~java
@Around("execution(* example.GreetingService.fail(..))")
public Object traceFailure(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("finally");
    }
}
~~~

If `fail()` throws `IllegalStateException`, the `finally` block executes and the exception continues propagating to the caller. You can catch the exception to log it:

~~~java
try {
    return pjp.proceed();
} catch (Throwable failure) {
    System.out.println("failed: " + failure.getClass().getSimpleName());
    throw failure; // Preserve error propagation behavior.
}
~~~

**Do not** replace an exception with a success result in a shared advice without an explicit business policy. Swallowing errors can break transaction rollback, retry policies, HTTP error mapping, or other infrastructure mechanisms.

### 5.3. Execution Order When an Error Occurs

If there is an outer `@Around` and an inner `@Before`:

- Outer may have already printed "before".
- Inner `@Before` runs when outer calls `proceed()`.
- Target throws an exception.
- Any "after" log placed right after `proceed()` does not run unless the exception is handled.
- Outer `finally` still runs.
- Caller receives the exception unless outer transforms it.

If an **inner advice throws an exception before the target runs**, outer `finally` can still execute, yet the target method **was never called**. Do not treat the execution of outer `finally` as proof that the target ran.

## 6. Runnable Java 17+ Example: Four Cases of proceed()

This is a standalone Maven project to verify behavior in practice:

- `GreetingService` is a Spring bean.
- `FlowAspect`: outer `@Around`, explicitly annotated with `@Order(1)`.
- `TraceAspect`: inner `@Before`, annotated with `@Order(2)` to guarantee order **between two different aspects**.
- `greet(String)`: outer calls `proceed(Object[])` with a transformed argument.
- `cached()`: outer **does not proceed**, returning a short-circuited result.
- `fail()`: `proceed()` forwards the call to the target which throws an exception; outer `finally` still runs.
- `callInternally()`: outer proceeds for the outer method; the target method calls `this.greet(...)`, so the inner invocation **does not go back through the Spring proxy**.

Uses **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, and **Java 17+**. No database, web server, or Spring Boot is required.

### 6.1. Directory Structure

~~~text
spring-around-proceed-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── GreetingService.java
    ├── FlowAspect.java
    ├── TraceAspect.java
    └── Main.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-around-proceed-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
~~~

The Spring Framework BOM manages consistent Spring module versions; AspectJ Weaver is used to parse `@AspectJ` expressions in Spring AOP. The presence of `aspectjweaver` **does not automatically enable AspectJ bytecode weaving**.

### 6.3. `GreetingService.java` — Target Business Object

~~~java
package example;

public class GreetingService {

    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "Hello " + name;
    }

    public String cached() {
        System.out.println("target: cached");
        return "FRESH";
    }

    public String fail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.greet("Self");
    }
}
~~~

The `cached()` method **contains real code** so we can verify that the target is not called when short-circuiting. In `callInternally()`, calling `this.greet("Self")` helps demonstrate self-invocation bypassing the AOP proxy path.

### 6.4. `FlowAspect.java` — Outer Around Advice

~~~java
package example;

import java.util.Locale;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class FlowAspect {

    @Around("execution(* example.GreetingService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("outer: before " + method);

        try {
            if ("cached".equals(method)) {
                System.out.println("outer: shortcut");
                return "CACHED"; // No proceed: inner/target will not run.
            }

            Object result;
            if ("greet".equals(method)) {
                Object[] args = pjp.getArgs().clone();
                args[0] = ((String) args[0]).toUpperCase(Locale.ROOT);
                result = pjp.proceed(args);
            } else {
                result = pjp.proceed();
            }

            System.out.println("outer: after " + method);
            return result;
        } finally {
            System.out.println("outer: finally " + method);
        }
    }
}
~~~

**Key learning points:**

- For `greet`, the advice creates a **copy** of the arguments array, modifies the first argument, and calls `pjp.proceed(args)`. In **Spring AOP**, the passed array must correspond to the **parameters of the target method**.
- For `cached`, the advice returns `CACHED` without calling `proceed`. The outer advice's own `finally` still runs per Java rules.
- For `fail` and `callInternally`, `pjp.proceed()` with no arguments preserves the caller's arguments.
- The `outer: after` line runs only when `proceed` returns normally; `outer: finally` runs even when the target or an inner advisor throws an exception.
- `@Order(1)` places this aspect **outside** the `@Order(2)` aspect on the entry path for the same join point.

**Illustration limitation:** The program intentionally branches on method names to keep stdout easy to read. In production code, use narrow pointcuts/annotations/bean scopes and split advice by method contract rather than switching on every method name in a service.

### 6.5. `TraceAspect.java` — Inner Advisor

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(2)
public class TraceAspect {

    @Before("execution(* example.GreetingService.*(..))")
    public void before(JoinPoint jp) {
        System.out.println("inner: before "
            + jp.getSignature().getName());
    }
}
~~~

This aspect helps prove that `proceed()` **does not jump directly to the target**. The normal execution path shows `inner: before ...` **after** `outer: before ...` and **before** `target: ...`.

If the outer advice decides to short-circuit, the inner advice is not called for that invocation. There is no guarantee that every advisor always executes.

### 6.6. `AppConfig.java` — Registering Spring Beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public FlowAspect flowAspect() {
        return new FlowAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
~~~

Both `@Aspect` classes are **registered as Spring beans via `@Bean`**, so `@Component` is not needed. Spring AOP detects the advice and creates a proxy for `GreetingService` because the pointcuts match.

`proxyTargetClass = true` makes the example use a class-based proxy so the service can be retrieved directly by `GreetingService.class`. Whether using JDK or CGLIB, **how `proceed` advances the advisor chain follows proxy-based Spring AOP rules**.

### 6.7. `Main.java` — Invoking the Four Cases

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingService service = context.getBean(GreetingService.class);

            System.out.println("proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- greet with modified argument --");
            System.out.println("caller: " + service.greet("An"));

            System.out.println("-- shortcut --");
            System.out.println("caller: " + service.cached());

            System.out.println("-- exception --");
            try {
                service.fail();
            } catch (IllegalStateException failure) {
                System.out.println("caller caught: " + failure.getMessage());
            }

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.callInternally());
        }
    }
}
~~~

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.8. Expected Program Stdout

Lines printed by the classes in the project itself, in exact order:

~~~text
proxy: true
-- greet with modified argument --
outer: before greet
inner: before greet
target: greet AN
outer: after greet
outer: finally greet
caller: Hello AN
-- shortcut --
outer: before cached
outer: shortcut
outer: finally cached
caller: CACHED
-- exception --
outer: before fail
inner: before fail
target: fail
outer: finally fail
caller caught: boom
-- self invocation --
outer: before callInternally
inner: before callInternally
target: callInternally
target: greet Self
outer: after callInternally
outer: finally callInternally
caller: Hello Self
~~~

Maven/Spring may emit additional environment logs; the output above includes only the example's `System.out.println` statements.

### 6.9. Step-by-Step Explanation

**Greet, with proceed(Object[]):**

1. Outer prints `outer: before greet`.
2. Outer transforms `"An"` to `"AN"` and calls `pjp.proceed(args)`.
3. Spring executes inner `@Before`, then target `greet("AN")`.
4. The method returns `"Hello AN"` back to outer.
5. Outer prints `after`, then `finally`, and the caller receives `Hello AN`.

This is direct proof that `proceed` went through **another advisor before reaching the target**, rather than calling the target immediately.

**Cached, without proceed:**

- Outer receives the invocation and returns `CACHED`.
- Neither `inner: before cached` nor `target: cached` appears.
- Outer's `finally` still runs before the caller sees the result.
- This is an **intentional short-circuit**, not a Spring bug forgetting to invoke the target.

**Fail, exception:**

- Outer calls `proceed()`, inner runs, target prints `target: fail` and throws `IllegalStateException("boom")`.
- `outer: after fail` **does not appear** because `proceed` did not return normally.
- `outer: finally fail` still appears.
- Caller catches the exception and prints `caller caught: boom`; the advice did not swallow the error.

**CallInternally, self-invocation:**

- Caller calls `callInternally()` through the proxy, so outer and inner run for **this outer method**.
- Inside the target, `this.greet("Self")` is an internal call; it **does not go back through the AOP proxy**.
- Therefore, there is no `outer: before greet`, no `inner: before greet`, and the argument remains `Self` (not upper-cased).
- The `Hello Self` result illustrates the proxy boundary; the fact that outer called `proceed()` **does not turn subsequent self-calls into proxied invocations**.

## 7. How Do proceed() and proceed(Object[]) Differ?

According to the Spring Framework documentation:

| API | Forwarded arguments | Use case |
| --- | --- | --- |
| `pjp.proceed()` | Uses the original arguments of the advised invocation | Proceed normally without modifying parameters |
| `pjp.proceed(new Object[] { ... })` | In Spring AOP, uses the array elements as **method arguments** for the forwarded invocation | Input normalization, controlled parameter adjustment |
| Not calling proceed | Does not send the invocation into the inner chain | Cache hit, access denial, intentional fallback |
| Calling proceed multiple times | Re-runs the inner chain multiple times if configuration allows | Retry, though easily duplicates side effects |

**Conditions for `proceed(Object[])`:**

1. The array must have a length **matching the number of method parameters** at the join point; for instance, `greet(String)` needs exactly one element.
2. Elements must have compatible types; `greet(String)` cannot accept an arbitrary `Integer`.
3. Do not call `pjp.getArgs()` and mutate it in place if you only intend a local transformation and want to avoid side effects on the argument array observed by other interceptors. The example uses `clone()`.
4. If a pointcut matches multiple methods with different signatures, blindly modifying `args[0]` can throw `ArrayIndexOutOfBoundsException` or `ClassCastException`. Narrow the pointcut and inspect signatures explicitly.
5. When a method takes primitive parameters, the `Object[]` array holds the corresponding wrapper values such as `Integer` for `int`; do not pass null for a primitive.
6. Replacing args changes the data seen by inner interceptors; apply it only when the business contract permits.

**Key difference between Spring AOP and the AspectJ compiler/weaver:** In proxy-based Spring AOP, the `proceed(Object[])` array corresponds to the **arguments of the underlying method**. In certain forms of around advice compiled with traditional AspectJ, positional binding/replacement semantics can differ. Do not copy `proceed(args)` code from another weaving mechanism without checking Spring Framework compatibility guidance. This lesson uses **Spring AOP** only.

## 8. "Continuing the Chain" Does Not Necessarily Reach the Target

Look at this path:

~~~text
Outer @Around
   |
   | proceed()
   v
Inner @Around
   |
   +-- cache hit --> return cached value
   |
   +-- cache miss --> proceed()
                        |
                        v
                    Inner @Before
                        |
                        v
                   Target method
~~~

On an inner cache hit:

- Outer **did call `proceed()`**.
- Inner received the call and decided to return early.
- The target was not called.
- Outer can still receive the value and print the `after` log.

Thus, claiming "outer called proceed so the target definitely ran" is **false**.

Conversely, if inner `@Before` throws an exception, outer `proceed()` also throws outward, even though the target was never called. You need to debug **layer by layer**, not just check for a single `proceed` call in source code.

A bean may also carry infrastructure advisors for transactions, caching, security, or tracing. Actual runtime ordering should be inspected from the Spring context/proxy advisor chain; **do not assume all advisors come from user-written @Aspect classes**.

## 9. Can proceed() Be Called Multiple Times?

The Spring Framework documentation explicitly states that around advice may call `proceed()` **zero times, once, or many times**. This is valid at the API level, but each `proceed` call can re-trigger **the entire inner part of the chain**.

Example **illustrative snippet**, not part of the standalone project in section 6:

~~~java
@Around("execution(* example.PaymentService.send(..))")
public Object retryOnce(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TransientOperationException ex) {
        return pjp.proceed();
    }
}
~~~

This snippet assumes `TransientOperationException` and `PaymentService` exist. What does it illustrate?

- If the first attempt fails, the second attempt can re-run **inner interceptors and the target**.
- If the operation has side effects such as creating orders, charging payments, sending emails, or publishing messages, repeating the invocation can cause **duplicate execution**.
- If interceptors include a transaction boundary, retry placed **outside vs. inside** the transaction interceptor can have very different semantics.
- Not every exception is transient; filter errors properly and define retry limits, delay/backoff, idempotency, and observability.
- An uncontrolled retry inside `@Around` can be far more dangerous than properly configured Spring Retry/Resilience infrastructure.

**Do not use this sample code verbatim in production.** Do not write infinite `while` loops or repeat `proceed` just to "make sure the method runs." Non-idempotent business operations require careful retry design, not just AOP syntax.

## 10. Advisor Ordering and @Order

When multiple advice methods across different aspects match the same method, Spring applies precedence rules. In the example:

~~~java
@Aspect
@Order(1)
public class FlowAspect { /* outer @Around */ }

@Aspect
@Order(2)
public class TraceAspect { /* inner @Before */ }
~~~

With `@Order`:

- **Lower numbers** have higher precedence.
- A higher-precedence aspect generally runs **earlier on entry to the join point**, and **later on exit**.
- Therefore, outer around logs `before` before inner before; outer after/finally runs after the inner chain has returned or thrown.

If no order is specified between two aspects, do not rely on a fixed stdout sequence for their logs. For multiple advice methods of the same kind within a single aspect, Java reflection does not guarantee method declaration order; do not infer runtime order from source code order.

### 10.1. Does Changing @Order Make proceed Call the Target Differently?

`@Order` primarily affects the **relative position of advisors/aspects in the chain**; it does not change pointcuts or modify the target bean. However, it can change whether a short-circuit happens **before or after** infrastructure advisors.

For example, with transactions/caching, advisor order can affect whether around advice executes inside or outside a transaction, meaning exceptions/rollbacks/commits may be observed at different points. Do not rearrange application-wide ordering merely to make logs print nicely. Always test business semantics when adjusting precedence.

## 11. When Should You Use @Around Instead of Simpler Advice?

The Spring Framework documentation recommends **choosing the least powerful advice type that meets the requirements**.

| Requirement | Advice to consider | Reason |
| --- | --- | --- |
| Log before a method executes | `@Before` | No need to explicitly call proceed |
| Handle successful results | `@AfterReturning` | Receives only the normal return branch |
| Track escaping exceptions | `@AfterThrowing` | Receives only the exceptional exit branch |
| Clean up when a method finishes on either branch | `@After` | Finally semantics without manipulating proceed |
| Measure duration with local start/end variables in the same invocation | **`@Around`** | Uses proceed and try/finally with per-call state |
| Intentional cache hit/short-circuit | **`@Around`** | Can skip proceed and return a substitute result |
| Replace arguments before invoking the method | **`@Around`** | Provides `proceed(Object[])` |
| Retry with policy and idempotency | `@Around` or dedicated infrastructure | Each proceed can re-run the inner chain |
| Only change log messages | Usually `@Before` or `@After` | No need to intrude on the return/throw path |

Not every logging advice needs `@Around`. Forgetting `proceed` in a logging `@Around` advice can **prevent business logic from executing** — a risk that a simple `@Before` does not create in the same way.

## 12. Notes on Methods Returning void, Primitives, and Futures

### 12.1. Methods Returning void

For a `void doWork()` target method, `pjp.proceed()` typically returns `null` as an `Object`; declaring the advice to return `Object` and writing `return pjp.proceed();` remains the proper structure. Do not arbitrarily change the around advice to `void` if the same pointcut also matches methods with return values.

### 12.2. Methods Returning Primitives

If the target returns `int`, the value passing through the advice is the corresponding wrapper object (e.g., `Integer`) at the `Object` interface level. If the advice returns `null` for a primitive return type, the caller/proxy may throw an exception because `null` cannot be unboxed. When short-circuiting, the substitute value must have a type compatible with the method.

### 12.3. Methods Returning CompletableFuture or Publisher

Suppose a method returns a `CompletableFuture<T>` or `Mono<T>`. `pjp.proceed()` can return **the handle representing the work** before the underlying work actually finishes.

- An around advice measuring time from before proceed to after proceed may measure only **the time to create/return the Future/Publisher**, not the full business latency.
- Errors from asynchronous computation may surface when the future completes or when the stream is subscribed to, not necessarily caught by a `try/catch` around `pjp.proceed()` itself.
- When metrics or cleanup must align with completion, attach callbacks/operators appropriate for the returned abstraction, or use suitable Spring integration.
- Do not call proceed multiple times just to "wait for the future's result."

This lesson does not expand into Reactive/Async configuration; it only emphasizes that **Spring AOP proceed at the method execution boundary** does not guarantee that asynchronous work has completed.

## 13. Proxy Boundaries and Self-Invocation

Even when an outer advice calls `proceed()`, internal calls within the target via `this.innerMethod()` still **do not go back through the proxy**.

~~~java
public String callInternally() {
    return this.greet("Self");
}
~~~

In the project in section 6, `callInternally()` is advised because the client calls it **through the proxy**, whereas `this.greet("Self")` is a direct Java call inside the target. As a result:

- There is no new `FlowAspect.around` invocation for the internal `greet`.
- There is no `TraceAspect.before` invocation for the internal `greet`.
- The `"Self"` argument is not upper-cased as it is when calling `service.greet("An")` directly from outside the proxy.

The common fix is to extract the method needing Spring advice into **another Spring bean** and call it through a dependency-injected bean reference. Do not instantiate with `new Bean()` and expect advisors to appear. Use `AopContext.currentProxy()` or self-injection only when you truly understand the coupling and proxy setup, not as a default.

Spring AOP supports both JDK dynamic proxies and CGLIB class-based proxies. **Switching JDK ↔ CGLIB strategies does not automatically fix self-invocation.**

## 14. proceed() in @Around vs. Low-Level invocation.proceed()

In addition to `@Aspect` style, Spring AOP also provides `org.aopalliance.intercept.MethodInterceptor`:

~~~java
// Illustrative snippet inside a class implementing MethodInterceptor.
@Override
public Object invoke(MethodInvocation invocation) throws Throwable {
    System.out.println("interceptor: before");
    Object value = invocation.proceed();
    System.out.println("interceptor: after");
    return value;
}
~~~

The two approaches serve different paths:

| Spring AOP form | Received parameter | Forwarding call | Typical usage |
| --- | --- | --- | --- |
| `@Around` annotation on Spring-managed `@Aspect` | `ProceedingJoinPoint` | `pjp.proceed()` / `pjp.proceed(Object[])` | AOP annotations using pointcut expressions |
| Programmatic Spring AOP / Advisor infrastructure | `MethodInvocation` | `invocation.proceed()` | `ProxyFactory`, custom MethodInterceptor, infrastructure advice |

They share the same chain-forwarding idea, yet **they do not share the same API types**. Do not mix up `ProceedingJoinPoint` and `MethodInvocation` when writing advice signatures. The `MethodInterceptor` example above is **not a standalone Java file**; it requires implementing the interface, adding imports, and registering with a Spring AOP proxy via `ProxyFactory`, an advisor, or related infrastructure.

A single invocation can pass through both low-level interceptors registered by the framework **and** advice declared with `@Aspect`. Therefore, concluding that "proceed only calls advice I wrote myself" is inaccurate.

## 15. Diagnosing When proceed() Does Not Produce Expected Results

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| "outer: before" is logged, no target log | Outer skipped proceed or an inner interceptor short-circuited | Inspect `return` branches and inner interceptor layers |
| Target runs, caller receives null | Advice forgot `return pjp.proceed()` or intentionally returned null | Verify return contract, especially for primitives |
| Target runs twice | `proceed()` called multiple times or a retry layer | Track invocation count and idempotency |
| `outer: after` missing when target throws | Code after proceed is not in finally | Move cleanup into try/finally, preserve exception |
| `outer: finally` runs without target executing | Inner advisor threw before target or short-circuited | Log each layer; do not infer target execution from finally |
| Direct service call via Spring proxy logs, `this.greet()` does not | Self-invocation | Extract to another bean and call via DI |
| `proceed(args)` throws type error | Arguments array has wrong length or types | Narrow pointcut and inspect method signature |
| Multiple aspects print unexpected stdout order | Missing precedence or another infrastructure advisor | Check `@Order` / `Ordered` and actual proxy advisor chain |
| `@Around` does not run | Aspect is not a bean, AOP disabled, pointcut doesn't match | Check `@Aspect @Component` / `@Bean`, dependencies, proxy |
| `AopUtils.isAopProxy(bean) == true` yet advice skips a specific method | Proxy may come from another advisor or method doesn't match | Check eligible advisors and method-level matching |
| Cache hit prevents call from reaching target | Intentional around short-circuit | Distinguish caching contract from missing proceed bug |
| Retry duplicates transactions/messages | Multiple proceeds re-execute side effects | Apply proper retry policies, idempotency, transaction boundaries |

### Diagnostic Checklist

1. Obtain the bean from `ApplicationContext` or constructor injection; do not substitute a `new` instance.
2. Check `AopUtils.isAopProxy(bean)`, remembering that this boolean **is not sufficient** to prove every method is advised.
3. Verify the `@Aspect` class is registered as a Spring bean and `@AspectJ` support is enabled.
4. Check whether the pointcut matches the target class/method.
5. Add logs before `proceed()`, before the target, and after `proceed()`; are there early return branches?
6. If multiple advisors exist, inspect `@Order` ordering and transaction/cache infrastructure.
7. If an exception occurs, inspect `catch`/`finally` and propagation to the caller.
8. If invoked multiple times, count `proceed` calls and target executions.
9. If replacing args, check argument count/types and the data observed by inner interceptors.
10. Test success, short-circuit, failure, and self-invocation like the standalone example, not just the happy path.

## 16. Practice Scenarios

**Scenario A:** Around advice prints "before" and then calls `pjp.proceed()`; an inner cache advice returns a cached value without proceeding. Does the target method run?

**Answer:** Not on that call. Outer forwarded to the **inner interceptor**, but inner blocked the path to the target. The caller can still receive the cached value.

**Scenario B:** Target `sum(int,int)` returns primitive `int`; around advice calls proceed yet returns `null`. Is the caller guaranteed to receive a result?

**Answer:** No. Null is incompatible with the primitive return contract and can throw an error. Return the result of proceed or a properly typed replacement value.

**Scenario C:** An `@Around` advice calls `proceed()` twice to "make sure saving succeeds." What effects can occur?

**Answer:** The target or inner advisors may run twice, causing duplicate writes/emails/transactions. Retries require an explicit policy and idempotency.

**Scenario D:** Outer around prints "before", target throws an exception. Code "after" placed past proceed does not run. How do you ensure a cleanup log still appears?

**Answer:** Put the cleanup inside `finally` wrapping proceed. If only after-finally behavior is needed, consider `@After` instead of `@Around`.

**Scenario E:** `pjp.proceed(new Object[]{"A"})` is called for method `greet(String)` in Spring AOP. What argument does the target receive?

**Answer:** In Spring AOP, the underlying target method receives `"A"` as its sole argument. The array must match the target's signature.

**Scenario F:** A caller invokes `service.callInternally()` through the proxy. Inside the target, it calls `this.greet("Self")`. Aside from `callInternally`, is there a separate around invocation for `greet`?

**Answer:** No. The internal call on `this` does not go through the Spring proxy, so it does not enter the advisor chain again for `greet`.

**Scenario G:** Outer around short-circuits yet still logs "outer: finally". Is that contradictory?

**Answer:** No. `finally` belongs to the outer advice itself, which already entered; only the inner advisors and target were skipped because proceed was not called.

**Scenario H:** A method returns an incomplete `CompletableFuture`, yet the around advice already printed "after". Did proceed wait for all background work?

**Answer:** No. Proceed may only have waited for the method to return the Future object. Async completion is a separate milestone and must be tracked with appropriate completion APIs.

## 17. Official Spring Documentation Sources

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `ProceedingJoinPoint.proceed()`, return values, short-circuiting, multiple proceeds, `proceed(Object[])`, and advice ordering.
- [Spring Framework — Spring AOP Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` and `MethodInvocation.proceed()` advancing the interceptor chain.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): around advice semantics and the recommendation to choose the least powerful advice type.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB AOP proxies, self-invocation, method restrictions.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` and registering aspect beans.
- [Spring Framework — AspectJ Pointcuts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): Spring pointcut expressions and method execution scope.
