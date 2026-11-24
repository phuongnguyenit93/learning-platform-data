# Preserving Return Contracts When Advice Wraps Target Methods in Spring AOP

## 1. The problem: around advice can change what the caller receives

In **Spring AOP**, a Spring-managed bean can be wrapped by a JDK dynamic proxy or a CGLIB proxy so that advice executes when a caller invokes a method through the proxy. With `@Around`, advice does not only run before and after the method; it also **decides whether to forward the call, which value to return, or which exception to throw**.

This establishes a very clear responsibility: **if the goal of an aspect is purely logging, tracing, metrics, or observing results, it must preserve the target method's contract**. You must not inadvertently drop the return value, return the wrong type, turn the result into `null`, change the semantics of `Optional`, or swallow exceptions.

The most important rule:

~~~java
@Around("execution(* demo.CatalogService.*(..))")
public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
    // Perform behavior before entering the target if needed.
    Object result = pjp.proceed();
    // Only observe result; do not change the reference unless required.
    return result;
}
~~~

This snippet is an **illustrative advice method**: it must be placed inside a `@Aspect` Spring bean, with imports for `org.aspectj.lang.ProceedingJoinPoint` and `org.aspectj.lang.annotation.Around`, along with a valid target bean and pointcut. It is not a standalone Java program.

**Why must it return `Object`?** According to the Spring Framework documentation, `@Around` should declare `Object` as its return type; the value returned by the advice is the value that **the caller of the target method sees**. Typically, you should `return pjp.proceed();` even when the target method is `void`. If the `@Around` method itself is declared to return `void`, Spring passes `null` back to the interceptor chain, losing the target method's return value; for methods returning a primitive, `null` can even cause an invocation error.

This content focuses on **Spring Aspect in Spring Framework**, without shifting to general AspectJ weaving theory.

## 2. What does a return contract include?

In Java, a "return contract" is not just a `return` keyword. For a caller using a Spring AOP proxy, the meaningful properties must be preserved:

| Contract element | Example method | What purely observational advice must preserve |
| --- | --- | --- |
| **Declared type** | `String label(...)` | The caller continues to receive a `String` object, or `null` if the method contract allows it |
| **Value** | `int quantity()` | Preserve the exact numeric value; do not accidentally return `0` or another value |
| **Non-null primitive** | `boolean enabled()` | Do not return `null` or a mismatched wrapper type for a primitive |
| **Reference identity** | `Customer findById(...)` | Do not substitute another object when the requirement is only observation; Spring has special handling when a target returns `this` itself |
| **Nullability** | `String nullable()` | If the target legitimately returns `null`, advice must not turn it into the string `"null"` |
| **Result container** | `Optional<String> lookup()` | Keep `Optional.empty()` as empty; do not turn it into `null` or another `Optional` |
| **Value-less method** | `void ping()` | The target must be invoked unless there is a short-circuit requirement; do not force a tangible value back to the caller |
| **Exception** | `String fail()` | If the target throws an error, observational advice must not silently return a successful fallback |
| **Generic contract** | `List<Order> findAll()` | Do not return a `List` containing incompatible elements even if the raw `List` type appears valid |
| **Lazy/async return** | `CompletableFuture<Result>` or reactive types | Do not replace the wrapper or implicitly block/subscribe unless required; completion occurs outside the method return point |

For example, a caller may write:

~~~java
String code = service.label("ada");
int quantity = service.quantity();
Optional<String> maybe = service.search(false);
~~~

If advice wraps these methods but replaces `String` with `Integer`, returns `null` for `int`, or turns `Optional.empty()` into `null`, the caller-side code breaks even though **the business target still ran normally**.

**Preserving the contract** does not mean Spring restricts `@Around` to observation only. Spring **allows** advice to intentionally return a replacement value; that must be a designed, documented, and tested requirement rather than an unintended side effect of logging.

## 3. Going through the proxy chain: who decides the return value?

~~~text
Caller: String value = service.label("ada")
                         |
                         v
                 Spring AOP proxy
                         |
                         v
           @Around advice: before logic
                         |
                    pjp.proceed()
                         |
                         v
           Inner interceptors (if any)
                         |
                         v
              Target.label("ada")
                         |
                         | return "ADA"
                         v
              interceptor chain
                         |
                         v
           @Around advice receives Object "ADA"
                         |
                  return result
                         |
                         v
              Caller sees "ADA"
~~~

If the advice writes:

~~~java
Object result = pjp.proceed();
return result;
~~~

then it continues the chain, receives the result object (or `null`), and returns it back to the proxy. For a target returning primitive `int`, the value traveling along the AOP interceptor path is represented as the corresponding wrapper, such as `Integer`, before the proxy hands the value back to the caller.

If the advice writes:

~~~java
pjp.proceed();
return null;
~~~

then the target **may still run**, but the return value from the target **has been discarded by the advice**. The caller sees `null` (if the return type is a reference) or encounters an error if the method declares a primitive. This is a very different bug from forgetting `proceed()`: in this case, the target's side effects still happen, and only the return value is lost.

If the advice writes:

~~~java
return "fixed-result";
~~~

without **calling `proceed()`**, the target may not run at all. This is valid within the technical capabilities of `@Around` (for example, a cache hit), but it alters the contract and side effects, so it is only correct when explicitly designed.

## 4. Distinguishing @Before, @AfterReturning, and @Around

When you only want to **record the return value** without altering the result, using `@AfterReturning` is usually safer and less intrusive than `@Around`.

~~~java
@AfterReturning(
    pointcut = "execution(String demo.CatalogService.label(..))",
    returning = "result",
    argNames = "result"
)
public void observe(String result) {
    System.out.println("OBSERVED: " + result);
}
~~~

This advice receives the return value when the target method **completes normally**. `@AfterReturning` **cannot return a completely different object reference to replace the caller's return value**. It has no `proceed()` and by convention is declared `void`.

There is a conceptual caveat to understand: if the returned object is **mutable**, Java code inside `@AfterReturning` can still modify the contents of that same object; that is a side effect the caller can see. **Inability to replace the reference** is different from **inability to mutate the object**. If the requirement is observation only, do not modify mutable return objects.

`@Before` is sufficient when you only need to run logic **before** the method without needing the result. `@AfterThrowing` lets you observe exceptions thrown by the target. `@After` (after-finally) is used when you need cleanup on completion regardless of success or error. **Choose `@Around` only** when you need state spanning before and after within the same invocation, to change arguments or return values, to short-circuit, or to control the method execution chain as required.

Note: even a simpler advice type can itself throw an exception and cause the invocation to fail; "less power to intervene" reduces the surface area for mistakes, and does not replace designing an error policy for logging or metrics.

## 5. Java 17+ example: one around advice preserving multiple result types

This plain Spring Framework project applies a shared `@Around` advice across `CatalogService` methods while **never altering the values**. It thoroughly verifies:

1. `String` returned normally;
2. Primitive `int`;
3. Primitive `boolean`;
4. `Optional<String>` both present and empty;
5. `void` method;
6. Legitimate `null` reference;
7. Exception from the target propagated with its exact type and message to the caller.

The program includes combined assertions and an advice call counter, rather than printing "PASS" unconditionally.

File structure:

~~~text
spring-aop-return-contract/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── CatalogService.java
    │   └── PreserveResultAspect.java
    └── test/java/demo/
        └── ReturnContractTest.java
~~~

Uses Java 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22**, and JUnit Jupiter **5.11.0**. Versions are pinned for the example, with no claim that they are the latest. Neither Spring Boot nor AspectJ bytecode weaving is used.

### 5.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-return-contract</artifactId>
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

`spring-context` provides `AnnotationConfigApplicationContext` and Java configuration. `spring-aop` contains proxy and advisor support. `aspectjweaver` provides the library types that allow Spring to understand `@AspectJ` pointcuts; merely adding this dependency **does not enable weaving**. `junit-jupiter`/Surefire are used to run simple integration tests within the same project.

### 5.2. Target with different return types

Create `src/main/java/demo/CatalogService.java`:

~~~java
package demo;

import java.util.Locale;
import java.util.Optional;

public class CatalogService {
    public String label(String input) {
        System.out.println("TARGET: label " + input);
        return input.toUpperCase(Locale.ROOT);
    }

    public int quantity() {
        System.out.println("TARGET: quantity");
        return 7;
    }

    public boolean enabled() {
        System.out.println("TARGET: enabled");
        return true;
    }

    public Optional<String> search(boolean exists) {
        System.out.println("TARGET: search " + exists);
        return exists ? Optional.of("found") : Optional.empty();
    }

    public void ping() {
        System.out.println("TARGET: ping");
    }

    public String nullable() {
        System.out.println("TARGET: nullable");
        return null;
    }

    public String fail() {
        System.out.println("TARGET: fail");
        throw new IllegalStateException("boom");
    }
}
~~~

This class is non-`final`; its methods are all `public` and non-`final`, allowing CGLIB to create a class-based proxy and intercept them. `search(true)` returns `Optional.of("found")`; `search(false)` returns `Optional.empty()`; these are two valid results **distinct from `null`**. `nullable()` is allowed to return `null` by illustrative design; `quantity()` and `enabled()` are primitives and therefore **cannot have the Java value `null`**.

### 5.3. Aspect that preserves values and does not swallow exceptions

Create `src/main/java/demo/PreserveResultAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;

@Aspect
public class PreserveResultAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Around("execution(* demo.CatalogService.*(..))")
    public Object preserve(ProceedingJoinPoint point) throws Throwable {
        String method =
                ((MethodSignature) point.getSignature()).getName();

        System.out.println("AROUND: enter " + method);
        try {
            Object result = point.proceed();
            System.out.println("AROUND: return " + method);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "AROUND: throw " + method
                    + " " + error.getClass().getSimpleName());
            throw error;
        } finally {
            calls.incrementAndGet();
        }
    }

    public int calls() {
        return calls.get();
    }
}
~~~

Design notes:

- `@Aspect` only marks the class containing advice; Spring still needs it registered as a **bean**.
- `@Around` has **return type `Object`** and `throws Throwable`, matching the `ProceedingJoinPoint.proceed()` API.
- `Object result = point.proceed(); return result;` preserves the exact reference/result returned by the inner interceptor chain, without manually casting to `String` or a specific wrapper.
- For `int` and `boolean`, Spring AOP handles boxing/unboxing at the interceptor/proxy boundary; the advice simply needs to return the exact object it received. **Do not** return `null` or a string `"7"` instead of `Integer`.
- For `void`, the return from `proceed()` can be `null` at the interceptor layer; `return result;` remains the proper way to preserve void method semantics. Do not change the advice method itself to `void`.
- For `Optional.empty()` or `null` from the target, the reference/result is forwarded as-is, without unrequested "normalization".
- The `catch(Throwable error)` block here only **prints a marker and executes `throw error` immediately**; it does not lose the original exception type. If logging the error type is not needed, you can omit `catch` and keep `try/finally`.
- `finally` increments `calls` even when the target throws an exception. This counter measures **how many times the advice was invoked**, not the number of successes.
- The pointcut selects methods on `CatalogService`, and the example deliberately invokes each method through the Spring bean proxy. It does not attempt to intercept constructors, field accesses, or objects created with `new` outside the container.

If a logger can throw an exception (such as a serialization or log sink failure), production code needs an error policy so logging does not accidentally alter business outcomes; printing to `System.out` is only appropriate for minimal examples.

### 5.4. Spring configuration and main method

Create `src/main/java/demo/App.java`:

~~~java
package demo;

import java.util.Optional;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    public PreserveResultAspect preserveResultAspect() {
        return new PreserveResultAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            CatalogService service = context.getBean(CatalogService.class);
            PreserveResultAspect aspect =
                    context.getBean(PreserveResultAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            String label = service.label("ada");
            System.out.println("CALLER_LABEL: " + label);

            int quantity = service.quantity();
            System.out.println("CALLER_QUANTITY: " + quantity);

            boolean enabled = service.enabled();
            System.out.println("CALLER_ENABLED: " + enabled);

            Optional<String> present = service.search(true);
            System.out.println("CALLER_PRESENT: " + present);

            Optional<String> absent = service.search(false);
            System.out.println("CALLER_ABSENT: " + absent);

            service.ping();
            System.out.println("CALLER_PING: complete");

            String nullable = service.nullable();
            System.out.println("CALLER_NULL: " + (nullable == null));

            boolean caught = false;
            try {
                service.fail();
            } catch (IllegalStateException error) {
                caught = "boom".equals(error.getMessage());
                System.out.println("CALLER_EXCEPTION: " + error.getMessage());
            }

            int count = aspect.calls();
            System.out.println("ADVICE_COUNT: " + count);

            if (!proxy
                    || !"ADA".equals(label)
                    || quantity != 7
                    || !enabled
                    || !Optional.of("found").equals(present)
                    || !Optional.empty().equals(absent)
                    || nullable != null
                    || !caught
                    || count != 8) {
                throw new IllegalStateException(
                        "Return contract was not preserved");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Why is this a genuine test of Spring AOP?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables the auto-proxy creator and class-based proxies for matching beans. `CatalogService` does not need an interface in this example.
2. `@Bean catalogService()` returns a Spring-managed instance; the caller uses the bean from `ApplicationContext` rather than calling `new CatalogService()` directly outside it.
3. `@Bean preserveResultAspect()` registers the aspect in the same context so Spring picks up the `@Around` advisor.
4. `AopUtils.isAopProxy(service)` confirms that the bean reference is actually an AOP proxy, not merely the target invoked directly.
5. Eight calls through the proxy: `label`, `quantity`, `enabled`, `search(true)`, `search(false)`, `ping`, `nullable`, `fail`. Therefore `ADVICE_COUNT` is expected to be **8**, even though the `fail` call ends with an exception.
6. The caller receives **the right types and values**: `String`, `int`, `boolean`, `Optional` present/empty, `void`, `null` reference, and `IllegalStateException`.
7. The final condition checks the proxy, all values, types observed via Java assignments, and the exception before printing `CHECK: PASS`. If `@Around` had accidentally returned `null` from `quantity`, the program would not get past the Java assignment into `int`.

### 5.5. Running Maven and comparing stdout

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

The `System.out.println` lines from the application, in order:

~~~text
PROXY: true
AROUND: enter label
TARGET: label ada
AROUND: return label
CALLER_LABEL: ADA
AROUND: enter quantity
TARGET: quantity
AROUND: return quantity
CALLER_QUANTITY: 7
AROUND: enter enabled
TARGET: enabled
AROUND: return enabled
CALLER_ENABLED: true
AROUND: enter search
TARGET: search true
AROUND: return search
CALLER_PRESENT: Optional[found]
AROUND: enter search
TARGET: search false
AROUND: return search
CALLER_ABSENT: Optional.empty
AROUND: enter ping
TARGET: ping
AROUND: return ping
CALLER_PING: complete
AROUND: enter nullable
TARGET: nullable
AROUND: return nullable
CALLER_NULL: true
AROUND: enter fail
TARGET: fail
AROUND: throw fail IllegalStateException
CALLER_EXCEPTION: boom
ADVICE_COUNT: 8
CHECK: PASS
~~~

This is the **expected stdout based on the source code**, not a claim that Maven was executed on the learner's machine. Maven/SLF4J may produce additional lines. `CHECK: PASS` only occurs when every condition in the code is satisfied.

### 5.6. Integration tests with JUnit Jupiter

Create `src/test/java/demo/ReturnContractTest.java`:

~~~java
package demo;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReturnContractTest {
    @Test
    void preservesReferencePrimitivesVoidOptionalNullAndException() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            CatalogService service = context.getBean(CatalogService.class);
            PreserveResultAspect aspect =
                    context.getBean(PreserveResultAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("ADA", service.label("ada"));
            assertEquals(7, service.quantity());
            assertTrue(service.enabled());
            assertEquals(Optional.of("found"), service.search(true));
            assertEquals(Optional.empty(), service.search(false));

            service.ping();
            assertNull(service.nullable());

            IllegalStateException error = assertThrows(
                    IllegalStateException.class, service::fail);
            assertEquals("boom", error.getMessage());

            assertEquals(8, aspect.calls());
        }
    }

    @Test
    void plainObjectOutsideSpringIsNotAutoProxied() {
        CatalogService raw = new CatalogService();
        assertFalse(AopUtils.isAopProxy(raw));
        assertEquals("ADA", raw.label("ada"));
    }
}
~~~

Command to run:

~~~bash
mvn clean test
~~~

Expected result in the Surefire report when run successfully:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

JUnit directly verifies the **contract observed by the caller**. Seeing that a bean is a proxy or that advice logs is not enough: advice can run yet accidentally return the wrong value. Each assertion corresponds to a category of return behavior, including thrown exits.

## 6. Critical bug: declaring @Around as void loses the return value

**Wrong** example for a `String` method:

~~~java
@Around("execution(String demo.CatalogService.label(..))")
public void wrong(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
}
~~~

An advice method returning `void` causes Spring to use `null` as the advice result; the caller of `String label(...)` may receive `null` even though the target returned `"ADA"`. If the pointcut matches the primitive method `int quantity()`, `null` cannot be returned as an `int`: Spring AOP can throw `AopInvocationException` because `null` is incompatible with the primitive return type.

**Correct fix:**

~~~java
@Around("execution(String demo.CatalogService.label(..))")
public Object correct(ProceedingJoinPoint point) throws Throwable {
    return point.proceed();
}
~~~

These two snippets are **standalone illustrative alternatives** and should not be added to the runnable project in section 5, which already has an `@Around` on `CatalogService`. Avoid having faulty advice active alongside correct advice when verifying standard output.

According to the Spring docs, `@Around` should declare **`Object`** as its return type even when the target method is `void`. For a `void` target, `return point.proceed()` remains the idiom that keeps the chain intact; there is no need to specially write `return null` unless there is a requirement to change behavior.

## 7. Bugs from omitting return, replacing the reference, or returning the wrong type

### 7.1. Target runs but result is discarded

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object broken(ProceedingJoinPoint point) throws Throwable {
    point.proceed();  // The target may still have run.
    return null;      // But the result from the target was discarded.
}
~~~

For a method returning `String`, the caller can receive `null` without any exception inside the advice. For primitives, the proxy cannot return `null` as an `int` or `boolean`. The fix: **`return point.proceed();`**.

### 7.2. Substituting a different reference when not requested

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object replaces(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return "FORCED";
}
~~~

Even though the `String` type is valid, the value `"FORCED"` is no longer the target's result. If the business logic does not require transformation, this is a semantic bug. If an application intentionally needs caching, fallback, or masking at a boundary, replacing the return value can be valid, but it must be documented and tested for contract compatibility.

### 7.3. Wrong object type

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object wrongType(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return Integer.valueOf(42);
}
~~~

The target declares `String label(...)`, yet the advice returns `Integer`. Returning `Object` from `@Around` does not permit the caller's interface or concrete class method to return any arbitrary type. At the proxy/caller boundary, a `ClassCastException` or corresponding type conversion/invocation error may appear. Do not rely on the exact exception message across JDK/CGLIB/configurations; **returning the wrong type is invalid**.

### 7.4. Returning null for a primitive

~~~java
@Around("execution(int demo.CatalogService.quantity())")
public Object nullPrimitive(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return null;
}
~~~

There is no Java `null` value for primitive `int`. In Spring AOP, a `null` result incompatible with a primitive can be reported by the framework as `AopInvocationException`; depending on the proxy/chain, there may also be wrapper exceptions. Do not use this as a way to "return a default". If a requirement specifies a fallback of 0, it must be an explicit policy decision, not something improvised inside logging.

### 7.5. Optional: do not turn empty into null

~~~java
@Around("execution(* demo.CatalogService.search(..))")
public Object badOptional(ProceedingJoinPoint point) throws Throwable {
    Object result = point.proceed();
    return result == null ? null : Optional.empty();
}
~~~

Wrong for `search(true)`: even though the target returns `Optional.of("found")`, the advice replaces it with empty. Wrong for `search(false)` if downstream callers need to distinguish a valid empty Optional container from a method returning null. If the contract declares `Optional<T>` with a non-null convention, **preserve the `Optional` object** when merely observing. Only transform when there is a clear requirement.

All snippets in section 7 are **independent anti-pattern examples**, not code to add to the reference project. During code review, specifically look for patterns like `proceed(); return null;` or catching and returning defaults not specified by the API contract.

## 8. Exceptions are also part of the contract observed by the caller

### 8.1. Propagating the exact exception when only logging is needed

~~~java
@Around("execution(* demo.CatalogService.fail(..))")
public Object traceFailure(ProceedingJoinPoint point)
        throws Throwable {
    try {
        return point.proceed();
    } catch (Throwable error) {
        System.out.println("Error: " + error.getClass().getSimpleName());
        throw error;
    }
}
~~~

The advice must **rethrow the exact `error` object** if it does not intend to translate exceptions. When the target throws `IllegalStateException("boom")`, the caller still observes that exception. Adding `throws Throwable` to the advice method matches `ProceedingJoinPoint.proceed()`.

### 8.2. Swallowing exceptions turns a thrown exit into a normal return

~~~java
@Around("execution(* demo.CatalogService.fail(..))")
public Object hidesFailure(ProceedingJoinPoint point)
        throws Throwable {
    try {
        return point.proceed();
    } catch (Throwable error) {
        return null;
    }
}
~~~

This is a **major contract change**: instead of letting the caller handle the failure, the advice returns `null` as if it were a normal return. For a method returning `String`, caller code may have no idea the target failed. For a primitive return, `null` is also type-incompatible.

If the true business goal is fallback or recovery, define the exception classes to handle, ensure the fallback has a valid type, consider impacts on transactions/caching and logging/auditing, and write integration tests. In many cases, error handling belongs at the **service boundary** or in dedicated circuit breaker/retry integrations rather than an ad-hoc around advice.

### 8.3. Using finally for cleanup without altering the outcome

~~~java
@Around("execution(* demo..service..*.*(..))")
public Object measure(ProceedingJoinPoint point)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - start;
        // Record metric; do not throw another exception from cleanup.
    }
}
~~~

This pattern preserves both normal returns and exceptions from `proceed()` because the `return` is inside `try` and `finally` does not alter the result. `System.nanoTime()` only measures elapsed duration, not wall-clock timestamps. In production, you need to guard metric recording against failures if metric errors must not affect business outcomes.

A `return` statement inside `finally` or an exception thrown inside `finally` can **override the outcome** of `try`. Avoid that pattern in observational around advice.

## 9. Primitives, references, void, generics, and async: type-safety checklist

### Primitives and boxing

In Java, `int quantity()` and `boolean enabled()` cannot return `null`. At the interceptor boundary, the result may be boxed into `Integer`/`Boolean`. Returning `String "7"` instead of `Integer.valueOf(7)` is not a type conversion automatically guaranteed by the proxy. Unless intentionally transforming, **return the original object** from `proceed()`.

### Nullable references

When a method `String nullable()` is designed to permit `null`, observational `@Around` should preserve `null`. Do not treat "no value" as an AOP error in itself. If the API contract forbids `null`, fix it at the service/validation layer or define an explicit policy; a logging aspect should not invent defaults.

### Void methods

A `void ping()` method does not provide a value to the caller. In Spring AOP, an around advice `Object preserve(...)` still returns the result of `proceed()` to keep the chain consistent. Do not declare the advice as `void` just because it can match a `void` method; the same aspect may match other methods that return values.

### Optional

`Optional.empty()` is a valid object, **not synonymous with `null`**. Preserve the `Optional<T>` result when only observing. Arbitrarily returning `Optional.empty()` instead of `Optional.of(...)` can make callers believe the data does not exist.

### Generics

Suppose a Spring service declares `List<Order> findAll()`. Runtime type erasure may cause the proxy to check only the raw `List` type; returning a `List<String>` from `@Around` might not fail immediately, but caller code reading elements as `Order` will fail. Test the **element contract** as well, not just `result instanceof List`.

### Async / Future / reactive

For `CompletableFuture<Result> fetchAsync()`, the "return contract" includes both the **wrapper** and its future completion or exceptional completion behavior. Advice returning `Result` directly instead of `CompletableFuture<Result>` is a type mismatch; calling blocking `join()`/`get()` without a requirement can block threads and change exceptions or timing. With Reactor `Mono<T>`/`Flux<T>`, subscription and signals happen outside the method return point; if you need to observe **asynchronous outcomes**, choose the appropriate integration or callbacks rather than assuming logging after `proceed()` means the pipeline has finished.

## 10. When multiple aspects participate in the interceptor chain

An `@Around` advice can sit outside other advice such as transaction, cache, or security; when it calls `pjp.proceed()`, it delegates down to **the rest of the interceptor chain**, not necessarily directly to the target right away.

~~~text
Caller
  |
  v
Outer audit @Around
  | proceed()
  v
Inner transaction/cache advisor
  | proceed() or short-circuit per its semantics
  v
Target method (when invoked)
  |
  v
Inner advisor returns result / throws exception
  |
  v
Outer @Around receives result / exception
  |
  v
Caller
~~~

Therefore, **preserving the contract** means preserving the result or exception actually returned by the inner chain, not assuming the value came directly from the target.

A cache advisor may intentionally return a cache hit without executing the target. If the outer audit aspect returns the exact `pjp.proceed()` result, it does not break caching behavior. If the outer aspect coerces the result to an invalid type, or invokes the target directly via reflection to bypass the interceptor chain, it can break cache, transaction, and security policies.

When using `@Order` to determine outer/inner precedence, **smaller** values generally have higher precedence: outer advice enters first and completes after the inner chain returns. Do not rely on source code declaration order to infer ordering between aspects. Test against the real Spring context whenever outcomes depend on order.

## 11. How to design a safe around advice

A skeleton with a clear purpose:

~~~java
@Aspect
public class TimingAspect {
    @Around("execution(* demo..service..*.*(..))")
    public Object measure(ProceedingJoinPoint point) throws Throwable {
        long started = System.nanoTime();
        try {
            return point.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            // Metrics sink must have a clear failure policy.
        }
    }
}
~~~

This is an **illustrative snippet**; it requires importing `@Aspect`, `@Around`, and `ProceedingJoinPoint`, registering the aspect as a Spring bean, and using an actual package pointcut. If the code only needs to log **before** the method, `@Before` is simpler. If it only needs to log a **successful result**, `@AfterReturning` usually has the right level of intervention. Use `@Around` when you need local state across before/after the invocation or need to alter execution flow for a clear purpose.

A good code review should ask:

1. Does the advice truly need `@Around`, or are `@Before`/`@AfterReturning` sufficient?
2. Does every success branch `return` the exact value returned by `proceed()`?
3. Does every failure branch preserve the exception according to the contract?
4. Is there any accidental `return null` or default? If so, is the target return type a reference or primitive?
5. Do any matched methods have `Optional`, generic collections, async wrappers, or nullable contracts?
6. Is `proceed()` called the exact number of times required? Could retries cause side effects?
7. Could self-invocation, raw target references, `final` methods, or a non-matching pointcut prevent advice from running?
8. Could logging/metrics code throw an error that alters the outcome?
9. If intentional transformation is needed, are caller-facing results and exceptions tested accordingly?
10. If multiple advisors match, have actual ordering and transaction/cache semantics been verified?

## 12. Practice exercises for spotting faulty cases

### Exercise 1: forgetting to return

Pattern:

~~~java
Object result = point.proceed();
return null;
~~~

With `String label()`, the caller may receive null. Fix by changing it to `return result;`. With `int quantity()`, null is incompatible with the primitive; never let that broken pattern into production.

### Exercise 2: coercing every result to String

Pattern:

~~~java
Object result = point.proceed();
return String.valueOf(result);
~~~

If the aspect matches `int`, `boolean`, or `Optional`, the declared method return type does not match `String`. If the aspect only needs to log, log `String.valueOf(result)` to the logger and then **`return result;`**.

### Exercise 3: "silent" fallback

Pattern:

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    return "";
}
~~~

For a method that throws an error where the contract expects the caller to see the exception, this is a bug. For primitive/Optional methods, the string `""` is also the wrong type. If fallback is intentional, it must match specific methods, specify which exception types are handled and use the right return type, document the behavior, and test it.

### Exercise 4: void method

A `void ping()` method does not require the caller to receive a value. In a shared `@Around Object` advice matching multiple methods, still use:

~~~java
return point.proceed();
~~~

Do not change the advice to `void` just because one target method returns `void`. Spring docs recommend an `Object` return type so you do not discard return values of value-returning methods.

### Exercise 5: Optional

If `search(false)` returns `Optional.empty()`, the advice invocation should preserve that result object. Seeing `Optional.empty()` does not mean the target returned `null`. Returning `null` from the aspect can cause `search(false).isPresent()` on the caller side to throw `NullPointerException`.

### Exercise 6: exceptions

In logging-only `@Around`:

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    logException(error);
    throw error;
}
~~~

`logException` is a **hypothetical** helper with its own error policy, not a method defined in the runnable project in section 5. Do not let the helper throw a different exception if the requirement is to preserve the original exception.

## 13. Debugging when the caller receives the wrong result despite a correct target

1. **Check the proxy**: use `AopUtils.isAopProxy(service)` on the reference actually being called. If false, do not immediately blame around advice.
2. **Inspect the pointcut**: does the method returning the wrong result actually match this `@Around`? Is another aspect in the chain?
3. **Check the advice signature**: does `@Around` declare return type `Object`, `ProceedingJoinPoint` as its first parameter, and `throws Throwable`?
4. **Check the success path**: is `proceed()` called once and its exact result returned, or is it called and discarded?
5. **Check the failure path**: is there a `catch` accidentally returning a default/`null`? Is `finally` throwing another error?
6. **Compare the return type**: use `MethodSignature.getReturnType()` to identify whether the method declares `String`, `int`, `void`, etc.; compare against the result object or fallback.
7. **Especially with primitives**: `null` cannot be delivered for `int`/`boolean`; check for `AopInvocationException` or corresponding wrapper errors.
8. **With generics**: check element types and caller usage behavior, not only the raw class.
9. **With Optional/async**: distinguish `Optional.empty()`/`null` and wrapper objects whose results complete later.
10. **Verify multiple advisors**: transaction/cache/security can change how results or exceptions are produced; inspect actual precedence/order.
11. **Do not replace target calls with direct reflection**: calling `method.invoke(target, ...)` is not equivalent to `ProceedingJoinPoint.proceed()` and can bypass inner AOP advisors.
12. **Write integration tests**: assert caller-facing results of representative methods, exception propagation, and advice invocation counts, rather than only checking whether a Spring bean has an AOP proxy.

### Snippet for inspecting return types inside advice

~~~java
MethodSignature signature =
        (MethodSignature) point.getSignature();
Class<?> declaredReturn = signature.getReturnType();
System.out.println("Declared: " + declaredReturn.getTypeName());

Object result = point.proceed();
System.out.println("Is null: " + (result == null));
return result;
~~~

This is a snippet inside `@Around` assuming `point` is in scope and `MethodSignature` is imported; it is not a standalone runnable file. Avoid logging the contents of `result` if it contains sensitive data or has a `toString()` with side effects. Only read metadata when needed and do not parse the generated proxy's class name string.

## 14. Pre-merge checklist for a Spring @Around advice

- [ ] The business requirement states clearly whether this is **observation** or **intentional transform/short-circuit**.
- [ ] If only pre-method work is needed, use `@Before`; if only reading a successful result, consider `@AfterReturning`.
- [ ] `@Around` declares `Object` and `ProceedingJoinPoint` as its first parameter.
- [ ] Every normal success branch returns the **exact result** of `proceed()` when there is no replacement policy.
- [ ] `proceed()` is called the exact number of times required; no unintended skipping or retrying.
- [ ] Thrown exits propagate the original exception when only logging/tracing.
- [ ] No `return` inside `finally`, and logging/metrics cannot accidentally alter the outcome.
- [ ] Tested representative reference types, primitives, void, nullable, Optional, and exceptions.
- [ ] Any fallback matches the declared return type/nullability, and is documented and tested.
- [ ] Aspect and target are Spring-managed beans; callers go through the proxy, avoiding self-invocation.
- [ ] Caller-facing integration tests exist, not just advice invocation counts.
- [ ] If the chain includes transaction/cache/security, ordering and return/exception interactions have been reviewed.
- [ ] Sensitive data is not written to logs just because advice has access to `getArgs()` or the result.

## 15. Official Spring Framework documentation

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `Object` return type, `proceed()`, caller-facing meaning of return values, notes on `@Around void` and `@AfterReturning` not replacing references.
- [Spring Framework 6.2 — Advice API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html): `MethodInterceptor.invoke` returning the invocation value, `AfterReturningAdvice` observing values only, and exceptions from advice.
- [Spring Framework 6.2 — AOP Concepts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html): `@Around` is the most powerful advice type; choose the least powerful advice that meets the requirement.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy boundaries, JDK/CGLIB, self-invocation.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): registering `@Aspect` Spring beans and enabling auto-proxying.
