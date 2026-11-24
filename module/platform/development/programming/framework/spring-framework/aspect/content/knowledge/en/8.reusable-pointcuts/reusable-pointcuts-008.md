# Testing Matched and Unmatched Pointcut Cases in Spring AOP

## 1. Objective: verifying both "matched" and "unmatched"

In Spring AOP, a pointcut expression specifies **which method executions on Spring beans** an advice will care about. Testing only a single method where advice runs is insufficient: an overly broad pointcut can accidentally intercept other methods, causing excess logging, slowing down the application, or applying policies in the wrong places.

The goal of this practice lesson is to organize the pointcut into **two named conditions**, combine them with `&&`, and then use **JUnit 5 and a real Spring ApplicationContext** to assert:

1. **Positive case (match):** a method satisfying *both* conditions, called through a Spring proxy → `@Before` runs exactly once, before the target.
2. **Negative case 1:** a method matching the class/signature scope yet **lacking the annotation** → no advice.
3. **Negative case 2:** a method carrying the annotation yet **not matching the return type required by the pointcut** → no advice.
4. **Negative case 3:** a method carrying the annotation yet belonging to **another class** → no advice.
5. **Proxy-boundary negative case:** invoking the annotated method via `this.method()` from inside the target → no advice for the internal call.
6. **Self-instantiated object negative case:** same class/method yet created with `new` outside Spring → no Spring auto-proxy.

This lesson focuses on **Spring Framework - Aspect**, specifically how to **test organized pointcuts**; it does not go deep into AspectJ theory outside Spring. The `@Aspect`/`@Pointcut` syntax originates from AspectJ, yet Spring AOP executes via **JDK/CGLIB proxies** on Spring-managed beans rather than bytecode weaving.

## 2. Two layers of pointcut testing

### Layer 1: testing whether the expression matches a method

Spring provides `org.springframework.aop.aspectj.AspectJExpressionPointcut` to represent a pointcut using AspectJ syntax. Given a `Method` and a target class, you can check `matches(method, targetClass)`. This is a **method-level match check**, useful for catching patterns that are too broad or too narrow.

~~~java
AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
pointcut.setExpression(
    "execution(public void demo.PaymentService.*(..))"
    + " && @annotation(demo.Measured)"
);
boolean matches = pointcut.matches(
    PaymentService.class.getMethod("pay"),
    PaymentService.class
);
~~~

This is an **illustrative snippet placed inside a Java method** with `import org.springframework.aop.aspectj.AspectJExpressionPointcut`; the corresponding classes are defined in the full project below. At this stage it does not yet prove Spring **created a proxy or executed advice**; it only checks the expression against the method signature and metadata.

### Layer 2: integration test calling methods through Spring bean proxies

An integration test using `AnnotationConfigApplicationContext` should verify in turn:

- The context enables `@EnableAspectJAutoProxy`; the aspect has been registered as a bean.
- The service retrieved from the context is indeed an AOP proxy when an advisor applies (`AopUtils.isAopProxy`).
- Methods are invoked **through the bean reference provided by Spring**.
- Observe the **marker inside the advice**, the marker's order relative to the target method, and how many times the advice runs.
- Call methods that *do not* match to assert **no advice marker appears**, rather than merely asserting the target still runs.

**The two layers do not replace each other.** `pointcut.matches(...) == true` does not guarantee advice will run when called via `this` or a `new` object. Conversely, seeing that a proxy exists does not prove every method in the class matches the pointcut.

## 3. Designing a test-case matrix before writing the aspect

Suppose the target pointcut is:

~~~text
execution(public void demo.PaymentService.*(..))
    &&
@annotation(demo.Measured)
~~~

Meaning:

- Condition A: a `public` method returning `void`, declared in `demo.PaymentService`.
- Condition B: a method marked with `@Measured`.
- Operator `&&`: both A **and** B must hold.

Matrix for the project in section 4:

| Invoked method | Right class + public void? (A) | Has @Measured? (B) | Advice runs via proxy? |
| --- | --- | --- | --- |
| `PaymentService.pay()` | Yes | Yes | **Yes: 1 time** |
| `PaymentService.preview()` | Yes | No | **No** |
| `PaymentService.refund()` (returns `String`) | No | Yes | **No** |
| `OtherService.pay()` | No, different class | Yes | **No** |
| `PaymentService.callPayInside()` | Yes | No | **No** at entry method |
| `this.pay()` inside `callPayInside()` | Right signature and annotated | Yes | **No**, because self-invocation bypasses proxy |
| `new PaymentService(...).pay()` | Right signature and annotated | Yes | **No**, because object is not Spring auto-proxied |

The last two rows distinguish **expression mismatch** from **no join point passing through the proxy**: a method can satisfy the annotation/signature yet not be intercepted by AOP in that specific call.

If you only test `pay()` without testing `preview()`/`refund()`/`OtherService.pay()`, it is very hard to catch accidentally dropping one of the two pointcut constraints.

## 4. Runnable Maven/Java 17+ project

We write **one small project** with complete code and tests. No Spring Boot, web server, database, mocking framework, or Spring TestContext is needed because `AnnotationConfigApplicationContext` is sufficient for this integration test demonstration.

Directory structure:

~~~text
spring-pointcut-match-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── Measured.java
    │   ├── EventLog.java
    │   ├── PaymentService.java
    │   ├── OtherService.java
    │   ├── MatchAspect.java
    │   └── AopConfig.java
    └── test/java/demo/
        └── PointcutMatchTest.java
~~~

Requirements: JDK 17+, Maven 3.9+, and ability to resolve dependencies. Fixed versions used for this exercise: **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, **JUnit Jupiter 5.11.0**; do not treat these as the latest library versions.

### 4.1. Create `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-match-test</artifactId>
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
        </plugins>
    </build>
</project>
~~~

- `spring-context` provides the container and Java configuration.
- `spring-aop` provides auto-proxying, `AopUtils`, and `AspectJExpressionPointcut`.
- `aspectjweaver` supplies the library types Spring needs to parse `@AspectJ` syntax; it does **not** automatically enable weaving.
- `junit-jupiter` is JUnit 5 for writing `@Test` methods and assertions; `maven-surefire-plugin` executes them via Maven commands.

### 4.2. Annotation marking methods

Create `src/main/java/demo/Measured.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Measured {
}
~~~

`@Retention(RUNTIME)` keeps the annotation available when AOP inspects methods at runtime. `@Target(METHOD)` prevents misapplying the annotation to classes/fields. It is solely a metadata marker; the annotation itself executes no advice.

### 4.3. Standalone EventLog to avoid relying on loggers or stdout

Create `src/main/java/demo/EventLog.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public class EventLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

The test project creates a fresh context per test and each test invokes methods sequentially, so `ArrayList` suffices. In a real concurrent application, a logger/thread-safe event sink or proper test synchronization is needed. `snapshot()` creates an unmodifiable list externally so assertions cannot accidentally mutate results.

### 4.4. Advised service and unmatched cases

Create `src/main/java/demo/PaymentService.java`:

~~~java
package demo;

public class PaymentService {
    private final EventLog log;

    public PaymentService(EventLog log) {
        this.log = log;
    }

    @Measured
    public void pay() {
        log.add("PAY");
    }

    public void preview() {
        log.add("PREVIEW");
    }

    @Measured
    public String refund() {
        log.add("REFUND");
        return "ok";
    }

    public void callPayInside() {
        log.add("CALL_INSIDE");
        this.pay();
    }
}
~~~

Intentional details:

- `pay()`: `public void` and `@Measured` → **matches both A and B**.
- `preview()`: `public void` yet unannotated → satisfies only A.
- `refund()`: has `@Measured` yet returns `String` → satisfies only B.
- `callPayInside()`: unannotated entry method; `this.pay()` inside the target does not go through the Spring proxy → advice does not run for the internal call. The `PAY` event is still added because the business method still executes.
- Class and methods are non-`final`, easily wrapped by Spring in a class-based proxy.

Create `src/main/java/demo/OtherService.java`:

~~~java
package demo;

public class OtherService {
    private final EventLog log;

    public OtherService(EventLog log) {
        this.log = log;
    }

    @Measured
    public void pay() {
        log.add("OTHER_PAY");
    }
}
~~~

`OtherService.pay()` has the **same annotation** and matching return type yet does not belong to `PaymentService`. This is a negative case guarding against accidentally writing only an overly broad `@annotation(demo.Measured)`.

### 4.5. Splitting conditions into two named pointcuts

Create `src/main/java/demo/MatchAspect.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class MatchAspect {
    private final EventLog log;

    public MatchAspect(EventLog log) {
        this.log = log;
    }

    @Pointcut("execution(public void demo.PaymentService.*(..))")
    public void paymentVoidMethod() {
    }

    @Pointcut("@annotation(demo.Measured)")
    public void measuredMethod() {
    }

    @Before("paymentVoidMethod() && measuredMethod()")
    public void beforeMeasuredPayment() {
        log.add("ADVICE_PAY");
    }
}
~~~

Key points about **organizing pointcuts** in Spring AOP:

1. `paymentVoidMethod()` is the **pointcut signature** (the name to reference); the `execution(...)` expression determines which method executions are evaluated. A `@Pointcut` method must have a `void` return type and an empty body.
2. `measuredMethod()` represents the condition that a method has the `@Measured` annotation.
3. `@Before("paymentVoidMethod() && measuredMethod()")` reuses both named pointcuts; if you want to further narrow by package/bean name, you can combine new conditions while preserving meaningful names.
4. `ADVICE_PAY` is added only inside the advice method, so this event serves as proof that the advice actually executed.
5. Another bean having `@Measured` but not inside `PaymentService` is not advised, because `&&` requires **both** conditions.
6. `@Aspect` only marks the aspect class; it must be registered as a Spring bean in the configuration below.

### 4.6. Registering Spring-managed beans and enabling AOP

Create `src/main/java/demo/AopConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public EventLog eventLog() {
        return new EventLog();
    }

    @Bean
    public PaymentService paymentService(EventLog log) {
        return new PaymentService(log);
    }

    @Bean
    public OtherService otherService(EventLog log) {
        return new OtherService(log);
    }

    @Bean
    public MatchAspect matchAspect(EventLog log) {
        return new MatchAspect(log);
    }
}
~~~

`@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP and requests class-based proxies for beans needing proxying. Because `PaymentService` implements no interface, a class proxy is suitable for retrieving the bean by `PaymentService.class`. Depending on infrastructure/bean types, Spring may select a class-based proxy even when `proxyTargetClass` is unset; setting `true` makes the choice explicit in the demo.

**Not every bean in the context gets proxied.** The Spring auto-proxy creator evaluates advisors. `OtherService` has no method matching `paymentVoidMethod() && measuredMethod()`; therefore the lesson does not depend on whether `OtherService` has a proxy, asserting only that **no advice from `MatchAspect`** runs for it.

`EventLog` is injected into the services and the aspect, sharing the same singleton bean within a context. Each test creates a **fresh context** so events do not leak between tests.

## 5. Integration test suite with JUnit Jupiter

Create `src/test/java/demo/PointcutMatchTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class PointcutMatchTest {

    @Test
    void positiveCaseAnnotatedPublicVoidPaymentMatches() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertTrue(AopUtils.isAopProxy(service));

            service.pay();

            assertEquals(List.of("ADVICE_PAY", "PAY"), log.snapshot());
        }
    }

    @Test
    void negativeCaseMissingAnnotationDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            service.preview();

            assertEquals(List.of("PREVIEW"), log.snapshot());
        }
    }

    @Test
    void negativeCaseWrongReturnTypeDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertEquals("ok", service.refund());

            assertEquals(List.of("REFUND"), log.snapshot());
        }
    }

    @Test
    void negativeCaseAnnotationOnDifferentClassDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            OtherService other = context.getBean(OtherService.class);
            EventLog log = context.getBean(EventLog.class);

            other.pay();

            assertEquals(List.of("OTHER_PAY"), log.snapshot());
        }
    }

    @Test
    void negativeCaseSelfInvocationSkipsAdvice() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertTrue(AopUtils.isAopProxy(service));

            service.callPayInside();

            assertEquals(
                    List.of("CALL_INSIDE", "PAY"),
                    log.snapshot());
        }
    }

    @Test
    void negativeCasePlainJavaObjectHasNoAutoProxy() {
        EventLog log = new EventLog();
        PaymentService plain = new PaymentService(log);

        assertFalse(AopUtils.isAopProxy(plain));

        plain.pay();

        assertEquals(List.of("PAY"), log.snapshot());
    }

    @Test
    void staticPointcutMethodMatchesAreCorrect() throws Exception {
        var pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public void demo.PaymentService.*(..))"
                + " && @annotation(demo.Measured)");

        assertTrue(pointcut.matches(
                PaymentService.class.getMethod("pay"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                PaymentService.class.getMethod("preview"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                PaymentService.class.getMethod("refund"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                OtherService.class.getMethod("pay"),
                OtherService.class));
    }
}
~~~

These are **seven complete test methods**. Each test checks a single concern, avoiding tests that perform too many actions and obscure which advice caused a change.

### Analyzing the assertions

**Positive test:**

~~~java
service.pay();
assertEquals(List.of("ADVICE_PAY", "PAY"), log.snapshot());
~~~

Asserts **both advice presence and exact order**: `@Before` appends `ADVICE_PAY` before the business method appends `PAY`. If the pointcut does not match or the call bypasses the proxy, the list contains only `PAY` and the test fails.

**Negative test for missing annotation:**

~~~java
service.preview();
assertEquals(List.of("PREVIEW"), log.snapshot());
~~~

If `measuredMethod()` is accidentally deleted or replaced with a broad expression, `ADVICE_PAY` will appear before `PREVIEW` and the assertion will fail.

**Negative test for wrong return type:**

~~~java
service.refund();
assertEquals(List.of("REFUND"), log.snapshot());
~~~

`refund` still carries `@Measured`, yet `execution(public void ...)` excludes it because it returns `String`. If the pointcut is written with only `@annotation(demo.Measured)`, this test fails.

**Negative test for wrong class:**

~~~java
other.pay();
assertEquals(List.of("OTHER_PAY"), log.snapshot());
~~~

If the `demo.PaymentService` constraint is dropped from the named pointcut, advice can spill over onto other classes carrying the same annotation.

**Negative test for self-invocation:** `callPayInside()` enters the target and calls `this.pay()`; `pay` still logs `PAY`, yet the internal call does not pass through the proxy. This test helps distinguish a **pointcut mismatch** from a **call path bypassing the Spring proxy**.

**Negative test for plain object:** `new PaymentService(log)` is not a Spring bean, even though its method satisfies the pointcut syntax. `@EnableAspectJAutoProxy` does not automatically attach interception to raw Java objects.

**Direct pointcut check test:** `AspectJExpressionPointcut.matches(...)` checks the method's "shape" against the expression. Combined with the integration tests above, it proves both **accurate matching** and **Spring AOP executing advice at runtime**.

Note: `staticPointcutMethodMatchesAreCorrect` creates no container, so it checks only the expression and does not replace the six behavioral tests. If the static check returns true, do not assume calls via `this` or `new` will be advised.

## 6. Running tests and reading actual results

Run from the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

If Maven has downloaded all dependencies and all tests pass, the expected summary in the Surefire report looks like:

~~~text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
~~~

The report file is typically named:

~~~text
target/surefire-reports/demo.PointcutMatchTest.txt
~~~

Do not hardcode Maven's entire stdout because Maven/JDK versions, terminals, and loggers can insert different lines. **The command must exit with code `0`** and report `7` passing tests; whenever `mvn clean test` returns non-zero, inspect the assertion failure or root cause before declaring completion.

To run only one specific test:

~~~bash
mvn -Dtest=PointcutMatchTest#positiveCaseAnnotatedPublicVoidPaymentMatches test
~~~

You can select a negative test to verify an individual boundary:

~~~bash
mvn -Dtest=PointcutMatchTest#negativeCaseWrongReturnTypeDoesNotMatch test
~~~

Running a single test is convenient while debugging, yet **insufficient** to claim the entire pointcut is right: you must rerun all positive/negative tests.

If your IDE does not recognize JUnit 5, verify `src/test/java`, the `junit-jupiter` dependency with `scope=test`, and `maven-surefire-plugin`. If Spring does not create an AOP proxy, check `@EnableAspectJAutoProxy`, the `MatchAspect` bean, the `aspectjweaver` dependency, and the pointcut.

## 7. "Mutation"-style testing: intentionally breaking the pointcut

A good way to evaluate a test suite is to **introduce intentional bugs**, run the tests to confirm assertions catch them, and then **restore the correct configuration**.

Apply the changes below **one change at a time** in `MatchAspect.java`:

### Mutation A: removing the annotation condition

Replace:

~~~java
@Before("paymentVoidMethod() && measuredMethod()")
~~~

with:

~~~java
@Before("paymentVoidMethod()")
~~~

Then `public void` methods in `PaymentService` can be advised even without `@Measured`. `negativeCaseMissingAnnotationDoesNotMatch` will fail (receiving `ADVICE_PAY` then `PREVIEW` instead of just `PREVIEW`). `negativeCaseSelfInvocationSkipsAdvice` may also fail because the entry method `callPayInside()` is now advised when the caller hits the proxy; this does not mean self-invocation was fixed.

### Mutation B: removing the class and return-type condition

Replace:

~~~java
@Before("paymentVoidMethod() && measuredMethod()")
~~~

with:

~~~java
@Before("measuredMethod()")
~~~

Then `PaymentService.refund()` and `OtherService.pay()` (also annotated) can trigger advice too. The two corresponding negative tests catch the broadened scope.

### Mutation C: disabling auto-proxy

Remove `@EnableAspectJAutoProxy(proxyTargetClass = true)` from `AopConfig` (assuming the minimal project has no other AOP configuration). `positiveCaseAnnotatedPublicVoidPaymentMatches` fails because `AopUtils.isAopProxy(service)` is no longer true and the event list lacks `ADVICE_PAY`.

This mutation tests **Spring AOP infrastructure**, not just pointcut syntax correctness. After each mutation, restore the valid file and rerun the full `mvn clean test`.

### Mutation D: changing `&&` to `||`

Replace AND with OR for the two conditions:

~~~java
@Before("paymentVoidMethod() || measuredMethod()")
~~~

Now methods satisfying only A **or** B are also advised; the negative tests for annotation/class/return type will catch it. This is a textbook example of why testing only one positive match **does not protect the scope** of a pointcut.

In a team project, you can use a mutation testing framework to automate this, though no extra tool is required for this lesson: editing manually, running Maven, and reverting is enough to see the value of the test matrix.

## 8. Organizing pointcuts for testability and reuse

In a large project, an `@Aspect` class can use its own named pointcuts:

~~~java
@Pointcut("within(demo..service..*)")
public void serviceLayer() {
}

@Pointcut("@annotation(demo.Measured)")
public void annotatedOperation() {
}

@Before("serviceLayer() && annotatedOperation()")
public void before() {
    // ...
}
~~~

This is an **illustrative snippet placed inside an `@Aspect`**, not a standalone runnable replacement for the test project above. The package `demo..service..*` must be adjusted to match your actual package. Named pointcuts are `void` methods with empty bodies; they are a way to name and **combine expressions**, not Java callbacks invoked directly by callers.

If multiple aspects share pointcuts, you can move `@Pointcut` declarations to a `public @Aspect` class such as `CommonPointcuts`, and reference them by fully qualified name:

~~~java
@Before("demo.CommonPointcuts.serviceLayer()"
      + " && demo.CommonPointcuts.annotatedOperation()")
public void before() {
    // ...
}
~~~

This snippet illustrates code organization; **`demo.CommonPointcuts` is not part of the declared example project** and therefore cannot compile on its own. In a real app you must define `CommonPointcuts`, set appropriate visibility, and ensure expressions reference the exact FQCN.

Even when reusing pointcuts, you need **negative tests for each condition**: one constraint by package, one by annotation, one by visibility/return type, and so on. Negative tests prevent unintended changes from broadening the pointcut and make code reviews easier.

## 9. Sources of false positives/false negatives in Spring AOP tests

### 9.1. Looking only at `isAopProxy()`

`AopUtils.isAopProxy(service)` tells you that the bean is an AOP proxy. **It does not tell you which methods your specific advice matched**. A bean may be proxied for transactions, caching, or another advisor. Assert the marker placed **inside the advice under test** and verify business target logic executes in the right order.

### 9.2. Using a `new` object instead of a Spring bean

If you construct:

~~~java
PaymentService service = new PaymentService(new EventLog());
service.pay();
~~~

this is a plain Java object, not managed by `AnnotationConfigApplicationContext`, so it is not auto-proxied by Spring. When testing runtime aspects, retrieve `context.getBean(PaymentService.class)` or inject the bean. Using `new` is still useful as a **negative case**, but it can never be a positive test for Spring AOP advice.

### 9.3. Self-invocation

From a method already inside the target, calling `this.pay()` bypasses the proxy so advice on `pay()` does not run. This **does not mean `pay()` fails to match the pointcut**; it merely shows that the internal Java call did not pass through the interceptor. To test matching, call `service.pay()` directly on the Spring bean proxy.

### 9.4. Mistakes placing annotations on interfaces/overrides

Java method annotations are not automatically "inherited" like method overrides. When a project uses interface-based JDK proxies, an annotation may sit on an interface method or an implementation method. Spring/AspectJ resolution mechanisms have specifics around concrete methods and bridge methods. For reliable tests, verify the annotation **is recognized by Spring AOP under the real proxy configuration**; in the demo, `@Measured` is placed directly on the implementation method to avoid extra variables.

### 9.5. Methods that cannot be intercepted via proxy

- With JDK proxies, the method must be exposed on the interface so normal callers invoke it through the interface type.
- With CGLIB, `final` classes cannot be subclassed; `final` or `private` methods cannot be overridden to intercept via class proxying.
- Static methods, constructors, and field accesses are not method execution join points intercepted by Spring AOP in the same way as instance methods on a proxy.

A static pointcut matcher may inspect method metadata, yet if there is no proxy call path at runtime, no advice executes. Do not write assertions based purely on annotations while ignoring proxy conditions.

### 9.6. Advice order when multiple aspects match

The example has only one `@Before` advice, so `["ADVICE_PAY", "PAY"]` is straightforward to verify. In a system with multiple advice methods or transaction advisors, configure or test ordering with `@Order`/`Ordered` whenever order is a business requirement. Do not assert arbitrary ordering across multiple advisors if the application has not defined ordering.

### 9.7. Tests leaking state

If you use a static counter in an aspect, tests sharing the same JVM can affect one another; if you use a cached singleton context across multiple tests, event lists may retain entries from earlier tests. The demo solves this by **creating a dedicated context per test**. For large integration suites, consider resetting spies/recorders and managing context lifecycles explicitly; never rely on JUnit method execution order.

## 10. Scaling test scope to real projects

When using pointcuts organized by package/annotation/bean name, build a matrix along three axes:

- **Target region:** service class in the right package, service class outside the package, interface vs implementation, managed bean vs raw object.
- **Selection markers:** annotation present/absent, method name, visibility, return type, argument types, bean name matching/not matching.
- **Call paths:** external caller via proxy, self-invocation, `final`/`private` methods, other co-applied advisors.

Do not create tests for every pointless combination. Have at least one positive case for each expected branch and **one separate negative case for each constraint** easy to miss. If a pointcut contains `A && B && C`, at minimum consider testing: `A∧B∧C` (match), `¬A∧B∧C`, `A∧¬B∧C`, `A∧B∧¬C` (no match), plus key proxy boundaries.

Example test targets for the expression:

~~~text
execution(public * demo..service..*.*(..))
    &&
@annotation(demo.Measured)
    &&
bean(*Service)
~~~

A good matrix includes: right package + annotation + bean name; outside package; missing annotation; different bean name; self-invocation; manually `new`ed object. Each case must state its **expectation before running the test**, rather than adjusting expectations to match accidental output.

You can use `@SpringJUnitConfig`/Spring TestContext to reduce context setup boilerplate in a multi-bean application, though when using context caching remember to reset the recorder. In this minimal lesson, `AnnotationConfigApplicationContext` is enough and requires no extra `spring-test` dependency.

## 11. Checklist for reviewing a pointcut test suite

- [ ] Pointcut is named, its scope is clear, and conditions are properly combined with `&&`/`||`/`!`.
- [ ] Each independent condition has an **unmatched case**; at least one case matches everything.
- [ ] Tests run against a **Spring-managed bean proxy** rather than a manually `new`ed object for positive advice checks.
- [ ] Both `@Aspect` and targets are beans in the same `ApplicationContext`, with AOP enabled.
- [ ] Positive tests assert that the advice marker actually appears, strictly **before/after** the target per advice type, not just `isAopProxy`.
- [ ] Negative tests assert **no advice marker** while the business method still runs if expected.
- [ ] Checked cases where annotation/method matches yet class/return type is wrong.
- [ ] Self-invocation and raw Java objects are contrasted where they pose application risks.
- [ ] Tests are state-independent, relying neither on execution order nor flaky logs.
- [ ] Maven/Surefire output records all tests passing; on failure, trace the root assertion or exception.
- [ ] Static method matcher is not conflated with runtime proxy advice execution.

## 12. Spring and JUnit reference documentation

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): named pointcuts, expression composition, and method execution join points.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before` and referencing pointcuts in advice.
- [Spring Framework 6.2 — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): `AspectJExpressionPointcut` and static/dynamic matching.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies and self-invocation.
- [Spring Framework 6.2 — Unit Testing](https://docs.spring.io/spring-framework/reference/6.2/testing/unit.html): distinguishing Spring-context-independent unit tests from integration tests.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/5.11.0/user-guide/): JUnit Jupiter `@Test` and assertion APIs.
