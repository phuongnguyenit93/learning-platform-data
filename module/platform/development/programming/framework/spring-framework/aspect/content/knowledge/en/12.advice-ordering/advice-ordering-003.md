# Smaller Order Values and Position in the Spring AOP Advice Chain

## 1. Key Takeaway

When **multiple Spring Aspects** have advice matching the same method execution of a Spring bean, determining execution order is critical. Spring AOP supports Spring's `@Order` annotation and the `Ordered` interface to declare precedence between **different aspects**.

**A smaller `order` value means higher precedence.** With two aspects:

~~~java
@Aspect
@Order(10)
public class AuditAspect { /* ... */ }

@Aspect
@Order(20)
public class MetricsAspect { /* ... */ }
~~~

`AuditAspect` has **higher** precedence than `MetricsAspect` because `10 < 20`. That does not mean **every line of code** in `AuditAspect` runs before every line of code in `MetricsAspect`: Spring AOP advice is nested inside an **interceptor chain**:

- When **entering** the join point, higher-precedence advice runs **before** lower-precedence advice.
- When **exiting** the join point (after returning or as an exception propagates back), higher-precedence advice runs its exit handling **after** the exit handling of lower-precedence advice.

With two `@Around` advice methods, picture it as:

~~~text
Caller
  |
  v
Order 10: before proceed()
    |
    v
  Order 20: before proceed()
      |
      v
   Target method
      |
      v
  Order 20: after proceed()
    |
    v
Order 10: after proceed()
  |
  v
Caller
~~~

**Concise rule:** smaller numbers sit on the **outside** of the chain (outer), larger numbers sit on the **inside** (inner). **First in — last out.**

In Spring AOP, this chain applies when the caller actually invokes a **Spring-managed bean through an AOP proxy** and the advisors match the method. `@Order` does not make every bean acquire a proxy automatically, does not alter pointcuts, and does not fix self-invocation.

## 2. Distinguishing "Order", "Precedence", and "Completion Order"

Three concepts need to be named accurately:

| Term | Meaning in Spring Aspect | Example `10` vs. `20` |
| --- | --- | --- |
| `order value` | The number returned by `@Order` or `Ordered.getOrder()` | `10` is smaller than `20` |
| `precedence` | Priority of the advice/aspect when building the processing chain | `10` has higher precedence than `20` |
| `on the way in` | The phase before the chain reaches the target method | `10` runs before `20` |
| `on the way out` | The phase when the result/exception travels back to the caller | `20` runs its "exit" part before `10` |
| `completion time` | The moment the advice code finishes | The outer aspect (`10`) typically finishes last if it performs wrapping logic |

If you only observe two `@Before` advice methods, it is easy to state inaccurately that "lower order runs first." That is true **in the before/on-the-way-in case**, but fails to describe the overall rule when `@After`, `@AfterReturning`, `@AfterThrowing`, or `@Around` are involved.

In particular, with two `@Around` methods and `try/finally`, the program observes exact nesting rather than random ordering dependent on thread scheduling. The full example in section 5 will use `@Order(10)`, `@Order(20)`, and `@Order(30)` on three different aspects.

### Example Without Explicit Order

~~~java
@Aspect
public class AuditAspect { /* matching advice */ }

@Aspect
public class MetricsAspect { /* matching advice */ }
~~~

When **two different aspects** match the same join point without declaring precedence, Spring **does not guarantee a deterministic order** between them. Output that looks fine on a dev machine can still change after changing bean registration, builds, or framework upgrades. If order has business significance, configure `@Order`/`Ordered` and write tests.

## 3. Setting Order in Spring Aspect

### 3.1. `@Order` at the Aspect Class Level

The most readable form:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.ProceedingJoinPoint;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        return pjp.proceed();
    }
}
~~~

This is a **valid illustrative Java class** provided the project has Spring AOP/AspectJ dependencies and the corresponding `WorkService`. A runnable version with full logging is in section 5.

`@Order` marks **aspect order**, not a bean filter. This class still needs to be **registered as a Spring bean** via `@Bean` or `@Component` + component scanning; placing `@Aspect`/`@Order` alone does not register the object in `ApplicationContext`.

### 3.2. The `Ordered` Interface

An aspect can declare it programmatically:

~~~java
@Aspect
public class ConfigurableAuditAspect
        implements org.springframework.core.Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Before("execution(* demo.WorkService.execute(..))")
    public void before() {
        // ...
    }
}
~~~

This is an illustrative class; it requires importing `org.aspectj.lang.annotation.Before` and registering the bean in the Spring context. `Ordered.getOrder()` is useful when priority needs to be expressed through Spring's API rather than a constant annotation.

**There is no need to use both `@Order` and `Ordered` on the same aspect** in learning examples. If combined, you must check Spring's precedence resolution rules and actual bean configuration to avoid confusion. Pick one mechanism and stay consistent across aspects.

### 3.3. Negative Values, 0, and Constants

Spring uses `int` to represent order. Examples:

| Value | Compared to 0 | Relative Precedence |
| --- | --- | --- |
| `-100` | Smaller | Higher than `0`, `10`, `100` |
| `0` | Intermediate | Higher than `10`, lower than `-100` |
| `10` | Greater than `0` | Lower than `0`, higher than `20` |
| `20` | Greater than `10` | Lower than `10` |
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Highest precedence value by convention |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Lowest precedence value by convention |

`@Order(0)` **does not** mean "no order"; it is a specific priority level. Nor is there a rule that "negative orders are reserved only for the framework." Choose values that express the relative ordering the application needs, and avoid treating absolute numbers as having magical meaning.

**Remember:** higher precedence means **smaller order**; do not read "order 100 is larger than order 10 so it runs first."

### 3.4. `@Order` Does Not Sort Bean Creation Order

In Spring Framework, `@Order` is used in several places, but in this lesson we examine **Spring AOP aspect ordering**. Do not confuse it with:

- Constructor or `@Bean` factory method invocation order;
- Dependency injection order, which depends on the dependency graph and container lifecycle;
- `BeanPostProcessor` registration order;
- Source-file method order inside an `@Aspect` class;
- Execution order between two independent service calls or across threads.

Determining which bean must initialize before another is a dependencies/lifecycle concern (e.g., constructor injection, `@DependsOn` where appropriate), **not a use case for aspect `@Order`**.

## 4. Actual Position in the Spring AOP Chain

Spring AOP combines each `Advisor` matching a method execution into an interceptor chain. A normal call through a Spring proxy flows from the caller into the advice layers, reaches the target, and then passes the return value or exception back out.

With three `@Around` aspects:

~~~text
                         PRECEDENCE HIGH
Caller                   Order 10 (outermost)
  |                         |
  |                         v
  |                      Order 20
  |                         |
  |                         v
  |                      Order 30
  |                         |
  |                         v
  |                    WorkService.execute()
  |                         |
  |                    Order 30: finally
  |                         |
  |                    Order 20: finally
  |                         |
  |                    Order 10: finally
  v
Caller observes result/error
                         PRECEDENCE LOW at core
~~~

Here:

- `@Order(10)` wraps **all of** `@Order(20)`, `@Order(30)`, and the target.
- `@Order(20)` sits in the middle.
- `@Order(30)` sits closest to the target, i.e., **inner**.
- When the method returns normally, the result travels along `30 → 20 → 10 → caller`.
- When the method throws an exception, if the aspects use `try/finally`, the `finally` blocks also run in the order `30 → 20 → 10` before the exception reaches the caller.
- An `@Around` aspect has the right **not to call `proceed()`**. If an outer aspect short-circuits, the target and inner advice **do not run**; `@Order` cannot force inner layers to be invoked.

This is the **advice chain of a single invocation**, not a time-based work queue or application-wide completion order.

## 5. Java 17+ Project Verifying Smaller Order Enters First / Exits Last

A plain Spring Framework Maven project testing two branches:

1. The method returns a normal result: all three around advice methods and the target run.
2. The method throws an exception: all three `finally` blocks exit in reverse order, and the exception still reaches the caller.

We record events into a **trace bean** and then assert **the entire sequence** before printing results. No Spring Boot, database, or mocking tools are needed.

Illustrative versions: Java 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22**. These versions are pinned for lesson reproducibility, not claimed to be the latest.

~~~text
spring-aop-order-chain/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── EventTrace.java
    │   ├── WorkService.java
    │   ├── OuterAspect.java
    │   ├── MiddleAspect.java
    │   └── InnerAspect.java
    └── test/java/demo/
        └── AdviceOrderTest.java
~~~

### 5.1. Maven Dependencies and Plugins

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-order-chain</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
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

`spring-context` provides Java config/`ApplicationContext`; `spring-aop` provides proxies and `AopUtils`; `aspectjweaver` supplies the types/APIs Spring needs to interpret `@AspectJ` pointcuts. Having only the `aspectjweaver` dependency does not enable AspectJ bytecode weaving. `junit-jupiter` and `maven-surefire-plugin` support the real test suite in section 5.8.

### 5.2. Shared Trace Bean

Create `src/main/java/demo/EventTrace.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public class EventTrace {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    public void clear() {
        events.clear();
    }
}
~~~

The project creates **one `EventTrace` singleton per ApplicationContext**. The service and the three aspects all inject this trace. The example runs sequentially, so `ArrayList` is sufficient; production with concurrent requests needs a thread-safe logger or collector. `snapshot()` returns a copy so order comparisons are unaffected by later additions.

### 5.3. Target Method with Two Exit Paths

Create `src/main/java/demo/WorkService.java`:

~~~java
package demo;

public class WorkService {
    private final EventTrace trace;

    public WorkService(EventTrace trace) {
        this.trace = trace;
    }

    public String execute(boolean fail) {
        trace.add("TARGET:enter");

        if (fail) {
            trace.add("TARGET:throw");
            throw new IllegalStateException("boom");
        }

        trace.add("TARGET:return");
        return "ok";
    }
}
~~~

`execute(false)` appends `TARGET:enter` then `TARGET:return` and returns `"ok"`. `execute(true)` appends `TARGET:enter` then `TARGET:throw` and throws `IllegalStateException("boom")`. There is no self-invocation or another thread in this example, allowing accurate observation of advice order on a single call.

### 5.4. Aspect Order 10 — Outermost

Create `src/main/java/demo/OuterAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAspect {
    private final EventTrace trace;

    public OuterAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("10:in");
        try {
            return point.proceed();
        } finally {
            trace.add("10:out");
        }
    }
}
~~~

`10:in` runs upon entering the outer aspect. `point.proceed()` forwards the invocation into the rest of the chain, where `@Order(20)` and `@Order(30)` live. `finally` ensures `10:out` runs **after the inner chain completes** or propagates an exception upward, even when the target throws `boom`.

### 5.5. Aspect Order 20 — Middle Layer

Create `src/main/java/demo/MiddleAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class MiddleAspect {
    private final EventTrace trace;

    public MiddleAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("20:in");
        try {
            return point.proceed();
        } finally {
            trace.add("20:out");
        }
    }
}
~~~

`@Order(20)` is greater than `10` so it has lower precedence than `OuterAspect`. Code in this aspect is entered **after** `10:in`, while `20:out` appears **before** `10:out`.

### 5.6. Aspect Order 30 — Closest to Target

Create `src/main/java/demo/InnerAspect.java`:

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class InnerAspect {
    private final EventTrace trace;

    public InnerAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(* demo.WorkService.execute(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        trace.add("30:in");
        try {
            return point.proceed();
        } finally {
            trace.add("30:out");
        }
    }
}
~~~

Among these three aspects, `30` is the largest order and lowest precedence, sitting **innermost**. It arrives right before the target in this illustrative chain, and `30:out` is the first "exit" marker once the target finishes.

### 5.7. Enabling Spring AOP and Verifying Both Paths

Create `src/main/java/demo/App.java`:

~~~java
package demo;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public EventTrace eventTrace() {
        return new EventTrace();
    }

    @Bean
    public WorkService workService(EventTrace trace) {
        return new WorkService(trace);
    }

    @Bean
    public OuterAspect outerAspect(EventTrace trace) {
        return new OuterAspect(trace);
    }

    @Bean
    public MiddleAspect middleAspect(EventTrace trace) {
        return new MiddleAspect(trace);
    }

    @Bean
    public InnerAspect innerAspect(EventTrace trace) {
        return new InnerAspect(trace);
    }

    public static List<String> expectedSuccess() {
        return List.of(
                "10:in", "20:in", "30:in",
                "TARGET:enter", "TARGET:return",
                "30:out", "20:out", "10:out");
    }

    public static List<String> expectedFailure() {
        return List.of(
                "10:in", "20:in", "30:in",
                "TARGET:enter", "TARGET:throw",
                "30:out", "20:out", "10:out");
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);
            if (!proxied) {
                throw new IllegalStateException("Missing Spring AOP proxy");
            }

            String result = service.execute(false);
            List<String> success = trace.snapshot();
            if (!"ok".equals(result) || !expectedSuccess().equals(success)) {
                throw new IllegalStateException("Success chain order wrong");
            }
            System.out.println("SUCCESS: " + String.join(" > ", success));

            trace.clear();

            try {
                service.execute(true);
                throw new IllegalStateException("Expected failure");
            } catch (IllegalStateException error) {
                if (!"boom".equals(error.getMessage())) {
                    throw error;
                }
            }

            List<String> failure = trace.snapshot();
            if (!expectedFailure().equals(failure)) {
                throw new IllegalStateException("Failure chain order wrong");
            }
            System.out.println("FAILURE: " + String.join(" > ", failure));

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Why does this example prove the question accurately?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP auto-proxying; all three `@Aspect` classes are registered as Spring beans, not merely annotated.
2. All three advice methods use the **same pointcut** `execution(* demo.WorkService.execute(..))`, so they compete for the exact same method join point.
3. Each aspect has a **different order**, avoiding ambiguous ties. `10` must enter before `20`, and then `30`.
4. `try/finally` in each `@Around` clearly shows the **way out** and continues working on the exception branch.
5. `expectedSuccess()` and `expectedFailure()` define the entire sequence upfront; the program actively throws if the trace is wrong rather than unconditionally printing `PASS`.
6. `trace.clear()` removes success events before testing failure, preventing stale data from skewing conclusions.
7. The `"boom"` exception is caught **at the caller**, after all three `finally` blocks have run; the advice only records markers without swallowing or transforming the exception.
8. This is **proxy-based Spring AOP**: no AspectJ compiler/agent or load-time weaving is used.

### Run Command

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the application's `System.out.println` on a successful run:

~~~text
PROXY: true
SUCCESS: 10:in > 20:in > 30:in > TARGET:enter > TARGET:return > 30:out > 20:out > 10:out
FAILURE: 10:in > 20:in > 30:in > TARGET:enter > TARGET:throw > 30:out > 20:out > 10:out
CHECK: PASS
~~~

Maven and loggers may print additional lines outside these application lines.

**Two standout observations:** smaller order appears earlier in the `in` section, yet appears later in the `out` section. If you only assert `10:in` before `20:in` and omit the `out` markers, the test only verifies **half** of the ordering semantics.

### 5.8. Running Integration Tests with JUnit Jupiter

File `src/test/java/demo/AdviceOrderTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdviceOrderTest {
    @Test
    void smallerOrderEntersFirstAndExitsLast() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("ok", service.execute(false));
            assertEquals(App.expectedSuccess(), trace.snapshot());
        }
    }

    @Test
    void allFinallyBlocksExitInReverseOrderOnException() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            WorkService service = context.getBean(WorkService.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));

            IllegalStateException error = assertThrows(
                    IllegalStateException.class,
                    () -> service.execute(true));

            assertEquals("boom", error.getMessage());
            assertEquals(App.expectedFailure(), trace.snapshot());
        }
    }
}
~~~

Run:

~~~bash
mvn clean test
~~~

If both tests pass, the Surefire report will show metrics similar to:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

Do not mistake this for a log from the reader's machine: this is the **expected result** when Maven/JDK are properly installed and the code runs as declared. The program may show additional build/framework logs, but assertions must hold for both success and exception paths.

## 6. With @Before and @After, How Does Order Manifest?

For two **different aspects** with different orders:

| Advice Type | Order 10 vs. Order 20 | How to Understand |
| --- | --- | --- |
| Two matching `@Before` | `@Before` of `10` runs before `20` | "On the way in" |
| Two matching `@AfterReturning` with normal target return | `@AfterReturning` of `20` runs before `10` | "On the way out" |
| Two matching `@AfterThrowing` with matching target exception | `@AfterThrowing` of `20` runs before `10` | Exception propagates outward |
| Two matching `@After` | `@After` of `20` runs before `10` | After-finally on the way out |
| Two matching `@Around` | `10:in → 20:in → target → 20:out → 10:out` | Outer/inner nesting |

This table is an explanatory model **when all advice methods apply and actually run**. When the target throws an exception, `@AfterReturning` does not run; when the target returns normally, `@AfterThrowing` does not run. `@After` can run on both paths. With `@Around`, if an advice method intentionally short-circuits or alters the exception/return value, the inner chain's outcome can change; do not assume a fixed sequence when an advice method does not call `proceed()`.

### Advice Ordering Differs from "Running Before/After the Same Java Method"

Example:

~~~java
@Aspect
@Order(10)
class A {
    @Before("execution(* demo.WorkService.execute(..))")
    public void before() { /* ... */ }
}

@Aspect
@Order(20)
class B {
    @AfterReturning("execution(* demo.WorkService.execute(..))")
    public void after() { /* ... */ }
}
~~~

These two classes are **illustrative snippets**, omitting package/imports/`@Bean`, and should not be added directly to the main project. Here `A.before` runs before the method and `B.after` runs after the method, but you **cannot** use that example to conclude lower order always runs before every advice: the two advice types inherently trigger at different phases. To observe true precedence between aspects, compare two advice methods of the same type or trace a full nested `@Around` chain.

## 7. Inside the Same @Aspect Class, @Order Does Not Order Individual Advice Methods

A very common mistake is thinking `@Order(10)` on an aspect class causes the advice method at the top of the source file to run before the advice method below it.

~~~java
@Aspect
@Order(10)
public class MixedAspect {
    @Before("execution(* demo.WorkService.execute(..))")
    public void first() {
    }

    @Before("execution(* demo.WorkService.execute(..))")
    public void second() {
    }
}
~~~

This is an **illustrative class** not yet registered as a Spring bean. Both `first()` and `second()` are `@Before` of the same type matching the same join point **within the same aspect**. Spring **does not guarantee the order between two advice methods of the same type** based solely on their declaration position in the source file: Java reflection does not preserve source declaration order in the way needed to infer precedence.

Per Spring Framework 6.2 documentation, for advice methods **of different types within the same `@Aspect`**, precedence is established by advice type, from highest to lowest:

~~~text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
~~~

However, `@After` has **after-finally** semantics, so even though its type precedence is listed before `@AfterReturning`/`@AfterThrowing`, when exiting the join point it is **actually invoked after** the corresponding return/throw handlers. Do not merely memorize the type precedence list and mechanically deduce log order.

If explicit ordering between two `@Before` steps is needed, easier-to-control options are:

1. Merge both steps into **one advice method** in explicit Java sequence; or
2. Move them into **two separate aspect classes**, each with an explicit `@Order` and an integration test.

Do not place `@Order` on two separate advice methods assuming Spring AOP treats them like two separate aspects: inter-aspect ordering is defined by the annotation/`Ordered` on the **aspect bean**, not source line numbers.

## 8. When Orders Are Equal or Undeclared

### 8.1. Two Aspects with the Same Order

~~~java
@Aspect
@Order(10)
class FirstAspect { /* ... */ }

@Aspect
@Order(10)
class SecondAspect { /* ... */ }
~~~

These two aspects share the same precedence value. **Do not use class names, bean names, or source method order to assume deterministic ordering**. If logic requires `FirstAspect` to wrap `SecondAspect`, assign **distinct** order values and verify with tests. And if order does not matter, the code must be independent of whichever runs first.

### 8.2. An Aspect Without Declared Order

An aspect without `@Order` or `Ordered` makes no relative precedence guarantee you can rely upon against other aspects. Spring has default ordering conventions, yet the system may also include advisors from transactions, caching, security, or other proxying mechanisms.

If the order between custom aspects and infrastructure advisors matters, determine the **effective order configuration of each advisor** (for instance, certain `@Enable...` infrastructure annotations have their own `order` attribute) and test in a real context, rather than relying on an untested "sure default."

### 8.3. Do Not Use Tied Order Levels as an Implicit Dependency

Seemingly minor changes such as adding an audit aspect, registering transaction infrastructure, or changing the classpath can shift execution order when multiple advisors share the same precedence. A safer design:

- Advice with sensitive side effects should minimize order dependencies whenever possible.
- If order must be depended upon, configure it explicitly and document it with tests.
- Do not rely on the order an IDE lists beans to deduce interceptor chain order.

## 9. Impact When Multiple Advisors Apply Together: Transaction, Security, Logging

In a Spring application, custom `@Aspect` classes are not the only source of advice. Mechanisms like `@Transactional`, caching, and security can join the proxy/advisor chain depending on configuration.

Theoretical example (not a standalone runnable transaction project):

~~~text
Logging @Around        (outer)
    |
    v
Transaction interceptor (inner)
    |
    v
Business method
~~~

If logging wraps outside the transaction interceptor:

- The `before` part of logging runs **before** the inner transaction startup proceeds.
- The `after/finally` part of logging can occur **after** the transaction interceptor in the same chain completes.
- If the order is reversed, the logger sits **inside** the transaction boundary and the timestamps/error scope it observes may differ.

Do not infer from this example that **every `@Transactional` configuration automatically has order 20**. Effective order depends on Spring configuration, advisors, and the application. Spring Framework allows configuring the transaction advisor's order via transaction infrastructure (e.g., the `order` attribute on `@EnableTransactionManagement` for proxy advice), but you must read the actual project configuration before drawing conclusions.

When verification is needed:

1. Confirm the target bean is genuinely a Spring AOP proxy.
2. Identify which advisors match and the order applied by the framework.
3. Set `@Order` on custom aspects if their relationship with other advisors must be constrained.
4. Write integration tests through the Spring bean, not objects manually instantiated with `new`.
5. Observe meaningful milestones, such as "transaction active before/during/after" using appropriate APIs, rather than guessing from a log line that might run elsewhere.

Advisor ordering does not replace transaction propagation/isolation/rollback configuration. It is one facet of the **Spring AOP chain**, not the entirety of transaction semantics.

## 10. Misconceptions and Fixes

| Misconception | Why It Is Wrong | How to Verify / Fix |
| --- | --- | --- |
| "`@Order(100)` takes priority over `@Order(1)` because the number is bigger." | The rule is reversed: **smaller** numbers mean **higher** precedence | Test with 10/20 to observe first-in, last-out |
| "Smaller order always finishes first." | Outer advice finishes after inner if it wraps `proceed()` | Record both `in` and `out` |
| "`@Order` changes method order inside the same `@Aspect`." | `@Order` primarily controls precedence between aspects | Merge advice or split into separate aspects |
| "Two `@Before` methods in the same aspect run in source-line order." | Reflection does not allow relying on source declaration order | Do not rely on line order |
| "I set an order, so the aspect is guaranteed to run." | You still need an aspect bean, a Spring AOP proxy, and a matching pointcut | Check `AopUtils.isAopProxy` and an event counter |
| "Different orders guarantee the target always runs." | `@Around` may omit `proceed()` | Test both target and advice events |
| "Order fixes self-invocation." | `this.otherMethod()` does not go through the Spring proxy | Call through a Spring-managed collaborator |
| "`@Order` defines which bean is created first." | It is not a dependency/lifecycle management mechanism | Use constructor dependencies / bean lifecycle APIs |
| "Omitting order still yields a fixed order across all aspects." | There is no such guarantee for precedence across different aspects | Declare order and test |
| "Outer advice is unaffected by exceptions." | Outer `@Around` can observe/transform exceptions from the inner chain | Use `try/finally` and maintain proper error policies |
| "Switching from JDK proxy to CGLIB fixes ordering." | Proxy strategy differs from ordering; each has its own configuration | Check `@Order`/`Ordered` and the advisor chain |
| "Aspect order and transaction order are always the same." | Transaction infrastructure has its own precedence configuration | Inspect ordering in a real context |

## 11. How to Debug When Order Is Unexpected

1. **Verify exact method execution:** do the pointcuts match the same Spring bean method? If one aspect does not match, it is not a matter of wrong chain placement.
2. **Verify the reference is a proxy:** `AopUtils.isAopProxy(service)` on the reference the caller uses. Objects created with `new` outside the container are not auto-proxied.
3. **Check `@Order` on the aspect class**, not merely on an advice method or a config file containing the aspect.
4. **Check `Ordered` as well** if the aspect implements this interface; verify the precedence value Spring actually uses.
5. **Check for duplicate orders:** two aspects with the same order will not satisfy strict ordering needs without a documented tie-breaker.
6. **Log both entry and exit:** with `@Around`, print markers before `proceed()` and in `finally`. Logging only `@Before` does not prove nesting.
7. **Test the exception branch:** success may look right while advice omits `finally`, alters exceptions, or returns early, changing the failure path.
8. **Check `proceed()`:** an outer aspect returning early skips inner advisors. Order values do not force target execution.
9. **Check multiple infrastructure advisors:** transaction/cache/security and custom aspects can share the chain. Do not compare only two classes written by your team.
10. **Check intra-aspect advice:** advice of the same type in one aspect has no guaranteed order based on source lines; split classes or merge logic.
11. **Do not infer from bean creation time:** chain order does not equate to Spring bean instantiation order.
12. **Lock down semantics with tests:** assert the full trace of before/after order and exception propagation as in section 5.

Check proxy at the call site:

~~~java
Object bean = context.getBean("workService");

System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
~~~

This is just a snippet to insert into a method that already has `ApplicationContext context`. If it returns `false`, aspect ordering is not the first cause to investigate.

## 12. Self-Check Exercises

**Exercise 1.** Two Spring aspects match method `execute()`: one has `@Order(-5)`, one has `@Order(100)`. Which aspect enters first?  
→ `-5` has higher precedence and enters first; if both wrap `proceed()`, it exits last.

**Exercise 2.** There are three around aspects 1/2/3. If all call `proceed()` once and then exit, what is the order?  
→ `1:in → 2:in → 3:in → target → 3:out → 2:out → 1:out`.

**Exercise 3.** `@Order(10)` outer `@Around` skips `proceed()`. Is `@Order(20)` inner guaranteed to run?  
→ No. The inner chain/target is only entered when the outer forwards via `proceed()` (or via some other mechanism outside the example).

**Exercise 4.** Why are two `@AfterReturning` aspects with orders 10/20 typically observed in the sequence 20 then 10?  
→ That is the direction of the result exiting **out** of the target; the higher-precedence aspect is on the outside so it runs later.

**Exercise 5.** Two `@Before` methods live in the same `@Aspect @Order(10)`. Does the method declared earlier in the source always run first?  
→ There is no guarantee based on source declaration order. Merge them or split into aspects with separate orders if order is mandatory.

**Exercise 6.** If an aspect with order 10 and a transaction advisor with order 20 both wrap a service method, is logging outside or inside the transaction?  
→ If both advisors are sorted by that precedence and both match, `@Around` logging order 10 is outer and transaction order 20 is inner. You must **verify runtime configuration** rather than assuming the transaction advisor is always order 20.

**Exercise 7.** If you put `@Order(10)` on an aspect without registering the aspect as a bean, does the advice run?  
→ No. `@Aspect`/`@Order` does not auto-register into Spring IoC; you need an aspect bean and AOP enablement.

**Exercise 8.** Why should you test both normal returns and thrown exceptions?  
→ To prove the chain unwinds in reverse order and outer advice can execute `finally` on both outcomes.

## 13. Quick Checklist

- [ ] Clearly stated **smaller value = higher precedence**.
- [ ] Distinguished **on the way in** from **on the way out**.
- [ ] Involved aspects are registered as Spring beans and target is a proxy.
- [ ] Order applies across **aspects**, not inferred from method position in source.
- [ ] No tied order values if the application requires strict ordering.
- [ ] `@Around` calls `proceed()` per the exact business contract.
- [ ] Tested the full trace of `in`, target, and `out` on the success path.
- [ ] Tested exceptions and `finally` on the failure path.
- [ ] If transaction/cache/security advisors exist, checked actual configured ordering.
- [ ] Did not confuse order with bean initialization or self-invocation.
- [ ] Advice logic does not leak data or accidentally alter exceptions when only logging is intended.

## 14. Official Documentation

- [Spring Framework 6.2 — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): precedence rules, smaller order, way-in/way-out, and intra-aspect advice ordering.
- [Spring Framework 6.2 — Schema-based AOP / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): ordering with `@Order`/`Ordered`, XML scope, and advisors.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring AOP using proxies with `@AspectJ` syntax.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): self-invocation, JDK/CGLIB proxies, and limitations.
- [Spring `Ordered` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/Ordered.html): `getOrder()`, `HIGHEST_PRECEDENCE`, `LOWEST_PRECEDENCE`.
- [Spring `@Order` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/Order.html): marking precedence via annotation.
