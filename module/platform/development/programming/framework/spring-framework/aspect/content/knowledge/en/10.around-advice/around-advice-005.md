# proceed(Object[]) and Argument Replacement by Spring AOP Convention

## 1. Lesson Objectives

In Spring AOP, an `@Around` advice receives a `ProceedingJoinPoint` and has the authority to decide **when, with which arguments, and how many times** the target method actually executes. This lesson focuses on the two ways to continue the call:

- **`pjp.proceed()`:** forwards to the interceptor chain/target method with **the current arguments of the call**. When no earlier advice has modified them, those are the arguments originally passed by the caller.
- **`pjp.proceed(Object[] arguments)`:** continues the call with a **replacement argument array**, where each element corresponds to **one parameter of the advised method**, **in the same position and order**.

This second convention is critically important: **in Spring AOP, the array passed to `proceed(Object[])` represents the target method's argument list, not the advice method's parameter list**. If the target method accepts two parameters, the new array must supply two values, even when the advice method binds only one of those two parameters.

This lesson focuses on Spring Framework and Spring Aspect without repeating full AspectJ weaving coverage. We will build a Java 17+ Maven project running through a Spring bean proxy, observe arguments before and after the advice modifies them, and highlight common mistakes involving **arity (argument count), ordering, types, `null`, binding, and exception propagation**.

### Brief Mental Model

~~~text
Caller:
    service.submit(" alice ", 2)
               |
               v
       Spring AOP proxy
               |
               v
    @Around: pjp.getArgs() -> [" alice ", 2]
               |
               | pjp.proceed(new Object[] {"ALICE", 3})
               v
       OrderService.submit("ALICE", 3)
               |
               v
       result "order:ALICE:3"
               |
               v
       Advice returns the result
               |
               v
             Caller
~~~

The caller still **invoked `submit(" alice ", 2)`**, yet the target received `"ALICE", 3`. Only calls **going through the Spring AOP proxy** are handled by this advice; an instance of the same class created with `new` outside the container does not automatically receive advice.

## 2. Conditions for `proceed(Object[])` to Take Effect in Spring

### 2.1. The Around Advice Must Be a Spring-Managed Aspect

Example configuration:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public RewriteAspect rewriteAspect() {
        return new RewriteAspect();
    }
}
~~~

This is an **illustrative configuration snippet**, not a complete Java file. The full project is in section 5. Required elements:

1. The aspect class is annotated with `@Aspect` **and** registered as a Spring bean (via `@Bean` or appropriate component scanning).
2. The target is a Spring-managed bean. The Spring AOP auto-proxy creator evaluates advisors, creates a proxy when methods match, and provides the proxy reference to callers.
3. Method execution must match the `@Around` pointcut. `proceed(Object[])` is called **only inside the executing advice**.
4. The method to be advised must be compatible with JDK/CGLIB proxying. With class proxies, `final`/`private` methods cannot be intercepted by overriding; self-invocation can still bypass the proxy.
5. `ProceedingJoinPoint` must be the **first parameter of the `@Around` advice**. Only `@Around` advice receives the join point type with `proceed`; `@Before`/`@AfterReturning` do not have authority to control how the target method is called.

### 2.2. The Two Overloads

~~~java
Object result = pjp.proceed();
~~~

Passes no new array; the method continues with the argument list currently on the join point. This is the preferred choice if you only need to observe, log, measure time, or do something that does not alter arguments.

~~~java
Object result = pjp.proceed(
        new Object[] { "ALICE", Integer.valueOf(3) }
);
~~~

Uses a new argument list. In the `submit(String customer, int quantity)` example, the first element is a `String` and the second element is an `Integer` (the Java wrapper is unboxed to `int` when invoking the method). **The array has exactly two elements**, no more and no fewer.

Using `Object` as the advice return type and `return pjp.proceed(...)` is the standard way to preserve the return contract. For `void` target methods, advice still normally declares `Object` as its return type to stay consistent across the interceptor chain.

### 2.3. When Should You *Not* Use the Array-Accepting Overload?

If you only want to log before the call:

~~~java
@Around("execution(* demo.OrderService.passthrough(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("AROUND: pass unchanged");
    return pjp.proceed();
}
~~~

There is no need to copy or allocate a new array. In fact, if you only need to log *before* the method, a `@Before` advice is usually **less intrusive** and easier to reason about than `@Around`. Use `@Around` only when a real requirement calls for wrapping the entire invocation or modifying arguments/return values.

## 3. Spring AOP Convention: Argument Array Follows the **Target Method**

Suppose the target method is:

~~~java
public String submit(String customer, int quantity) {
    return "order:" + customer + ":" + quantity;
}
~~~

In Spring AOP, `proceed(Object[])` is interpreted as follows:

| Index | Target parameter type | Original argument | Replacement argument |
| --- | --- | --- | --- |
| `0` | `String customer` | `" alice "` | `"ALICE"` |
| `1` | `int quantity` | `2` (boxed when read via `Object[]`) | `3` (as an `Integer` inside `Object[]`) |

~~~java
Object[] original = pjp.getArgs();
Object[] replacement = original.clone();

replacement[0] = ((String) original[0]).trim()
        .toUpperCase(java.util.Locale.ROOT);
replacement[1] = ((Integer) original[1]) + 1;

return pjp.proceed(replacement);
~~~

This snippet sits **inside an `@Around` advice**. It does not treat `Object[]` as a list of *advice parameters*, but as **the exact two arguments of `submit(String,int)`**.

Why `clone()` before modifying?

- `pjp.getArgs()` is meant for **inspecting the argument list** of the join point; you should not rely on mutating the returned array directly always having stable semantics.
- Copying clearly expresses **the original arguments** vs. **the arguments forwarded to the target**.
- Cloning an array is a **shallow copy**: objects inside still point to the same references. If an element is a mutable object, modifying its fields is not solved by `clone()` alone.
- The caller still holds references to its original input objects. Replacing an element in the array passed to `proceed` differs from mutating the input object in place.

**The element count must match the number of parameters of the intercepted method**, not the number of bound variables in the advice declaration. Spring AOP executes method-execution join points; this is simpler and more direct than certain semantics of compiled/woven AspectJ language advice.

## 4. Difference From the AspectJ Compiler's `proceed(Object[])` Convention

This is a prominent warning in the official Spring documentation.

### 4.1. Proxy-Based Spring AOP

In Spring AOP, `proceed(new Object[]{...})` takes **all arguments of the target method** in parameter order. For example:

~~~java
public String inspect(String label, int units)
~~~

requires supplying **two** arguments if replacing them before continuing the call:

~~~java
return pjp.proceed(new Object[] { "BOB", 6 });
~~~

### 4.2. AspectJ Compiled Around Advice Has Different Rules

For advice compiled under the **traditional AspectJ language**, the number of values passed to `proceed` corresponds to **the number of parameters bound in the around advice**, rather than automatically being all target method parameters. Each value at a bound position replaces the corresponding entity at the join point.

Therefore, **do not copy a weaving/AspectJ-compiler example that binds one argument** and assume `proceed(new Object[]{oneArg})` is enough for a two-parameter target method in Spring AOP.

The Spring documentation suggests a portable pattern across both mechanisms: **bind all target method parameters in exact order in the advice signature**, then supply a new array with the same values/count in that order. Single-parameter example:

~~~java
@Around(
    value = "execution(* demo.Repository.findByName(..)) && args(name)",
    argNames = "name"
)
public Object normalizeName(
        ProceedingJoinPoint pjp, String name) throws Throwable {
    String normalized = name.trim();
    return pjp.proceed(new Object[] { normalized });
}
~~~

This is an **illustrative snippet**: `demo.Repository.findByName` is not in the project below, but is assumed to take exactly **one `String` parameter**. Because the advice binds the target's single parameter, `new Object[]{normalized}` fits Spring AOP's rule and matches the shape recommended by the docs to avoid differences when moving to an AspectJ compiler/weaver.

For a **two-parameter** target method, if cross-mechanism portability is needed, bind **both parameters in order**. In pure Spring AOP, the advice is not required to bind all of them if you obtain the full array with `pjp.getArgs()` and pass a matching array to `proceed`.

### 4.3. Illustrating Binding Only One Parameter of a Two-Parameter Method

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(..)) && args(label,..)",
    argNames = "label"
)
public Object inspect(
        ProceedingJoinPoint pjp, String label) throws Throwable {
    Object[] current = pjp.getArgs();   // Target method has 2 arguments.
    Object[] next = current.clone();
    next[0] = label.trim().toUpperCase(java.util.Locale.ROOT);
    next[1] = ((Integer) current[1]) + 2;

    return pjp.proceed(next);            // MUST pass all 2 elements.
}
~~~

Here the advice signature only declares `String label` alongside `ProceedingJoinPoint`, yet the intercepted method is `inspect(String,int)`. **The `next` array has length 2**, because `proceed(Object[])` by Spring AOP convention refers to the target method. This style highlights the difference and is **not portable verbatim to the AspectJ compiler** with different binding semantics.

The hands-on project in section 5 uses this exact scenario because it exposes the "confusing advice parameter count with target parameter count" mistake directly.

## 5. Complete Spring Framework Java 17+ Project

We run four separate cases using four differently named methods to avoid overlapping `@Around` advice:

1. `passthrough(String)`: uses `proceed()` and keeps arguments unchanged.
2. `submit(String,int)`: modifies **both arguments** using `proceed(Object[])`.
3. `inspect(String,int)`: advice **binds only one argument** (`label`) yet still passes **both values**.
4. `fail(String)`: modifies the argument before the target throws an exception, then **preserves exception propagation**.

### 5.1. Directory Layout

~~~text
spring-aop-proceed-args/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── OrderService.java
    └── RewriteAspect.java
~~~

Requires Java 17+, Maven 3.9+, Spring Framework 6.2.0, and AspectJ Weaver 1.9.22. Versions are pinned for reproducibility, not claimed to be the newest releases.

### 5.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-proceed-args</artifactId>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext`/Java configuration, `spring-aop` holds the proxy infrastructure and `AopUtils`, and `aspectjweaver` supports parsing Spring AOP's `@AspectJ` pointcut expressions. There is no `-javaagent` or weaving in this project.

### 5.3. `src/main/java/demo/OrderService.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class OrderService {
    private final AtomicInteger targetCalls = new AtomicInteger();

    public String passthrough(String input) {
        targetCalls.incrementAndGet();
        System.out.println("TARGET_PASS: [" + input + "]");
        return "pass:" + input;
    }

    public String submit(String customer, int quantity) {
        targetCalls.incrementAndGet();
        System.out.println(
                "TARGET_SUBMIT: " + customer + " x" + quantity);
        return "order:" + customer + ":" + quantity;
    }

    public String inspect(String label, int units) {
        targetCalls.incrementAndGet();
        System.out.println(
                "TARGET_INSPECT: " + label + " x" + units);
        return "inspect:" + label + ":" + units;
    }

    public String fail(String customer) {
        targetCalls.incrementAndGet();
        System.out.println("TARGET_FAIL: " + customer);
        throw new IllegalStateException("declined:" + customer);
    }

    public int getTargetCalls() {
        return targetCalls.get();
    }
}
~~~

These methods are `public`, the class is non-`final`, and they do not call each other internally, keeping the example focused on **modifying the argument list in Spring AOP**. `targetCalls` records how many times **the target was actually entered**; even `fail` increments the counter before throwing an exception.

Each method returns `String` (or throws before returning), letting `@Around` handle the result as `Object` while still returning a valid `String` to the caller.

### 5.4. `src/main/java/demo/RewriteAspect.java`

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class RewriteAspect {
    private final AtomicInteger adviceCalls = new AtomicInteger();

    @Around("execution(String demo.OrderService.passthrough(..))")
    public Object aroundPass(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();
        System.out.println("AROUND_PASS: original arguments");
        return pjp.proceed();
    }

    @Around("execution(String demo.OrderService.submit(..))")
    public Object aroundSubmit(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();

        Object[] original = pjp.getArgs();
        Object[] changed = original.clone();

        String customer = (String) original[0];
        int quantity = (Integer) original[1];

        changed[0] = customer.trim().toUpperCase(Locale.ROOT);
        changed[1] = quantity + 1;

        System.out.println("AROUND_SUBMIT: modified 2 args");
        return pjp.proceed(changed);
    }

    @Around(
        value = "execution(String demo.OrderService.inspect(..))"
              + " && args(label,..)",
        argNames = "label"
    )
    public Object aroundInspect(
            ProceedingJoinPoint pjp, String label) throws Throwable {
        adviceCalls.incrementAndGet();

        Object[] changed = pjp.getArgs().clone();

        changed[0] = label.trim().toUpperCase(Locale.ROOT);
        changed[1] = ((Integer) changed[1]) + 2;

        System.out.println("AROUND_INSPECT: 1 binding, 2 args");
        return pjp.proceed(changed);
    }

    @Around("execution(String demo.OrderService.fail(..))")
    public Object aroundFail(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();

        String customer = (String) pjp.getArgs()[0];
        Object[] changed = {
            customer.trim().toUpperCase(Locale.ROOT)
        };

        System.out.println("AROUND_FAIL: modified customer");
        return pjp.proceed(changed);
    }

    public int getAdviceCalls() {
        return adviceCalls.get();
    }
}
~~~

Explanation of each advice:

- `aroundPass`: simply forwards without altering inputs. It uses `proceed()` because no new argument array is needed.
- `aroundSubmit`: `getArgs()` yields two elements, clones the array, processes the `String` (trim + uppercase), and increments `int` from `2` to `3`. `proceed(changed)` passes both arguments down to the target.
- `aroundInspect`: the expression with `args(label,..)` **binds only the first element** to the `String label` advice parameter. `argNames="label"` simply helps Spring resolve the binding name in the advice signature. The target method still takes `(String,int)`, so `proceed(changed)` must contain **two** elements. `argNames` **does not** change Spring's array-length convention.
- `aroundFail`: alters the input and invokes the target. The exception from the target **passes straight through the advice** to the caller because the advice does not catch, swallow, or replace it. This preserves the business method's error contract.
- Every advice returns `Object` and `return pjp.proceed(...)` to preserve the result without producing an unexpected `null`.
- Pointcuts are scoped to **specific method names** and do not overlap, ensuring each invocation maps to exactly one advice in the example.

**Do not omit `throws Throwable`** when calling `ProceedingJoinPoint.proceed(...)`. It is declared on the API and ensures exceptions can propagate through the advice. In real applications, never swallow exceptions merely because the advice sits in a cross-cutting layer.

### 5.5. `src/main/java/demo/App.java`

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public RewriteAspect rewriteAspect() {
        return new RewriteAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            RewriteAspect aspect = context.getBean(RewriteAspect.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);

            String pass = service.passthrough("keep");
            System.out.println("RESULT_PASS: " + pass);

            String submit = service.submit(" alice ", 2);
            System.out.println("RESULT_SUBMIT: " + submit);

            String inspect = service.inspect(" bob ", 4);
            System.out.println("RESULT_INSPECT: " + inspect);

            boolean failed = false;
            try {
                service.fail(" bad ");
            } catch (IllegalStateException ex) {
                failed = "declined:BAD".equals(ex.getMessage());
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            int advice = aspect.getAdviceCalls();
            int target = service.getTargetCalls();
            System.out.println(
                    "COUNTS: advice=" + advice + ",target=" + target);

            if (!proxied
                    || !"pass:keep".equals(pass)
                    || !"order:ALICE:3".equals(submit)
                    || !"inspect:BOB:6".equals(inspect)
                    || !failed || advice != 4 || target != 4) {
                throw new IllegalStateException(
                    "Spring AOP proceed arguments verification failed");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Why does this example work according to Spring's design?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP and creates a class-based proxy when `OrderService` has matching advisors. Since `OrderService` does not implement an interface, retrieving via `getBean(OrderService.class)` is convenient.
2. `@Bean rewriteAspect()` turns `RewriteAspect` into a Spring bean so Spring detects the four `@Around` advisors.
3. The caller uses only the **reference retrieved from `ApplicationContext`**, so methods are invoked through the proxy where advice can replace the argument list.
4. `service.getTargetCalls()` is a method that does not match any of the four pointcuts, yet can still be called through the proxy; it returns the target counter without incrementing the advice counter.
5. Calling `fail(" bad ")` still propagates the exception after changing the argument to `"BAD"`. `failed` verifies both the **error type** and exact message content.
6. The combined assertion enforces matching results and **exactly four target calls**. If `proceed` were forgotten in one advice or array values were wrong, the program would not print `CHECK: PASS`.

### 5.6. Running Maven and Stdout

In the `spring-aop-proceed-args` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed explicitly by the example code, in order:

~~~text
PROXY: true
AROUND_PASS: original arguments
TARGET_PASS: [keep]
RESULT_PASS: pass:keep
AROUND_SUBMIT: modified 2 args
TARGET_SUBMIT: ALICE x3
RESULT_SUBMIT: order:ALICE:3
AROUND_INSPECT: 1 binding, 2 args
TARGET_INSPECT: BOB x6
RESULT_INSPECT: inspect:BOB:6
AROUND_FAIL: modified customer
TARGET_FAIL: BAD
CAUGHT: declined:BAD
COUNTS: advice=4,target=4
CHECK: PASS
~~~

Maven or logging frameworks may emit additional messages depending on environment configuration; the snippet above lists only `System.out.println` statements from the application.

The four comparisons:

- `passthrough("keep")`: **`proceed()`**, target sees `"keep"` unchanged.
- `submit(" alice ", 2)`: **`proceed(Object[])`**, target receives `("ALICE", 3)` instead of `(" alice ", 2)`.
- `inspect(" bob ", 4)`: advice **binds only `label`** yet still needs the full target array `("BOB", 6)`; target returns `inspect:BOB:6`.
- `fail(" bad ")`: target receives `"BAD"` before throwing the exception, and the caller catches `declined:BAD`.

`CHECK: PASS` appears only when the proxy exists, all results and exceptions are valid, and both advice and target counts equal four. Using `proceed()` in `aroundSubmit` instead of `proceed(changed)` would leave the target with unmodified arguments and fail the assertion.

## 6. Common Mistakes With `proceed(Object[])`

### 6.1. Array Has Fewer or More Elements Than Target Method Arguments

For `submit(String customer, int quantity)`:

~~~java
return pjp.proceed(new Object[] { "ALICE" });
~~~

**Wrong** in Spring AOP: the array has only one element while the target method takes two parameters.

~~~java
return pjp.proceed(new Object[] { "ALICE", 3, "extra" });
~~~

**Wrong** due to an extra element. In Spring AOP implementations, forwarding with a mismatched argument list length can cause `IllegalArgumentException`/invocation errors from the framework. Do not depend on an exact exception class/message across every variant, and **never invoke the target with a wrong-arity array** in production logic.

Correct:

~~~java
return pjp.proceed(new Object[] { "ALICE", 3 });
~~~

The snippets in this section are **illustrative expressions inside an `@Around` advice**; do not add them simultaneously to the main project.

### 6.2. Right Array Length, Wrong Order or Types

~~~java
return pjp.proceed(new Object[] { 3, "ALICE" });
~~~

The array has two elements, yet the target method expects `(String,int)`. This is wrong in **position/type** and can fail when the framework invokes the target via reflection/proxy, such as an argument type mismatch error.

Java primitive notes when using `Object[]`:

- `int` is represented via the `Integer` wrapper.
- `long` typically uses `Long`, and `boolean` uses `Boolean`.
- Do not expect arbitrary numeric wrappers to convert automatically into the desired primitive; always use the exact matching wrapper.
- `null` is not valid for a primitive parameter such as `int`; `null` can be used for reference parameters if the business contract allows.
- Check downstream validators/contracts: a trimmed/uppercased `String` can still alter data meaning, identifiers, security signatures, or business rules.

If an advice does not know the exact method signature because it uses a broad wildcard, do not assume the second element of every invocation is an `Integer`. Narrow the pointcut or inspect the method signature/arguments before transforming.

### 6.3. Confusing `pjp.getArgs()` With Passing `Object[]` to proceed

~~~java
Object[] args = pjp.getArgs();
args[0] = "CHANGED";

return pjp.proceed();
~~~

This is **not** a safe or portable way to guarantee the target receives `"CHANGED"`. `proceed()` continues with the join point's existing argument list; relying on mutating the array returned by `getArgs()` in place is not a contract you should depend on across adapters/versions. To express an explicit replacement via the Spring AOP API, **create a replacement array and call `proceed(newArgs)`**.

Clear-intent form:

~~~java
Object[] original = pjp.getArgs();
Object[] changed = original.clone();
changed[0] = "CHANGED";
return pjp.proceed(changed);
~~~

Even if a particular Spring/AspectJ version behaves differently when mutating the `getArgs()` array in place, the clone + `proceed(changed)` form remains the direct way to express argument list replacement for code review and testing.

### 6.4. Forgetting to Call `proceed`

~~~java
@Around("execution(* demo.OrderService.submit(..))")
public Object broken(ProceedingJoinPoint pjp) {
    return "fake-result";
}
~~~

This snippet is **valid in terms of what `@Around` can do**, yet if the requirement is to forward modified inputs, it is a logic bug: the target never runs. `@Around` has the power to short-circuit, so omit `proceed` only when that is an explicitly designed policy (e.g., cache hit or authorization failure with a valid fallback).

### 6.5. Calling `proceed` Twice Uncontrolled

~~~java
Object first = pjp.proceed(args1);
Object second = pjp.proceed(args2);
return second;
~~~

An `@Around` advice can invoke the target multiple times, yet operations that write data, charge payments, or send emails may be duplicated. Do not use `proceed(Object[])` to create ad-hoc retries. If retries are required, control idempotency, maximum attempts, exceptions, transactions, and argument lists for each attempt. Many systems should use a dedicated retry integration rather than a custom aspect.

### 6.6. Swallowing Exceptions or Returning the Wrong Result Type

~~~java
try {
    return pjp.proceed(changed);
} catch (Throwable error) {
    return null;
}
~~~

This snippet can lose the original exception and replace it with `null`, breaking the target method's contract. If you are only modifying arguments, let exceptions propagate naturally with `return pjp.proceed(changed);`. If handling exceptions/fallbacks is truly needed, treat it as an explicit requirement, ensure compatible return types, and test it.

`@Around` should declare return type `Object`. If an advice declares `void`, Spring has no return value to pass back like a value-returning method; this is a common cause of unexpected results when copy-pasting advice.

## 7. Other Considerations When Passing `Object[]` in Spring AOP

### 7.1. Varargs Methods

For a Java method:

~~~java
public String send(String topic, String... tags) {
    return topic + ":" + java.util.Arrays.toString(tags);
}
~~~

Varargs are represented as **one array parameter** (`String[]`) in bytecode. When Spring advises such a method, the reflection parameter list is `(String, String[])`, not one parameter per tag.

By method signature convention, the replacement array should have two elements:

~~~java
return pjp.proceed(
        new Object[] { "NEWS", new String[] { "java", "spring" } }
);
~~~

This is illustrative code inside an advice; `send` is not in the runnable project. Do not flatten `String... tags` into three or four `Object[]` elements based on tag count; that does not match the target method's parameter count in the JVM.

### 7.2. Overloaded Methods

If a class has:

~~~java
public void notify(String value) {
}

public void notify(String value, int retries) {
}
~~~

an overly broad pointcut such as `execution(* *.notify(..))` can match **both overloads**. An advice assuming `args.length == 2` will fail on the one-parameter overload. You should:

- Narrow the pointcut to a specific signature whenever possible;
- Or check `pjp.getArgs().length` and `pjp.getSignature()` before constructing the array;
- Or forward unchanged via `proceed()` if the invocation is outside the intended transformation scope.

This matters because `proceed(Object[])` does not infer parameter types from the desired element count; **the target method has already been selected** before the replacement array enters.

### 7.3. Generic/Bridge Methods and Interface Proxies

In Spring AOP, callers may pass through a JDK dynamic proxy or a class-based CGLIB proxy. The method signature handled by the framework can involve interfaces, implementations, generic bridge methods, or target methods. For methods with multiple overloads or generic erasure, test on the application's actual proxy configuration rather than reasoning from a single class's source code alone.

If a business method is exposed only through an interface, ensure calls to that method actually go through the Spring AOP proxy. Do not expect `proceed(Object[])` to modify arguments for objects instantiated directly with `new`, `this.method()` self-invocations, or `final`/`private` methods not intercepted by class proxies.

### 7.4. Null, Immutable, and Mutable Objects

`proceed(Object[])` **replaces the reference values passed down to the target**; it does not automatically deep-copy objects. Example:

~~~java
Object[] before = pjp.getArgs();
Object[] next = before.clone();

next[0] = java.util.List.copyOf(
        (java.util.List<?>) before[0]
);

return pjp.proceed(next);
~~~

If the target's first parameter is a `List`, the snippet above replaces the reference with an immutable copy (and `List.copyOf` rejects `null` elements). This can change target behavior if the target expects to mutate the list; therefore, transformations must have clear justification. Using `Object[]` does not mean every element is automatically serialized/cloned.

Choose copying and validation strategies based on the business contract: a DTO containing mutable nested objects may need a deep defensive copy or must strictly remain unmodified.

### 7.5. Side Effects and Transaction/Security Context

If the Spring AOP proxy also carries advisors for `@Transactional`, caching, or security, the advice sits inside an **interceptor chain** whose order depends on precedence. Replacing arguments with `proceed(Object[])` can affect downstream logic (and can affect keys/policies of inner advisors in the chain), yet never claim every advisor sees the exact same argument list without verifying ordering.

In particular:

- Do not alter identity/authentication arguments merely to "normalize" them if the security contract forbids it.
- Be careful with caching: altering arguments at one position in the chain can cause cache keys to be built from pre- or post-replacement arguments depending on ordering.
- Do not call `proceed` multiple times inside a transaction without controlling semantics and idempotency.
- If the logic only needs validation and throwing an exception before the target runs, `@Before` may suffice; use `@Around` to replace arguments only when genuinely required.

## 8. Testing `proceed(Object[])` in Real Projects

Do not stop at tests checking that the advice ran. Verify **what values the target actually received** and what the caller observed.

Minimum test matrix:

| Case | Arguments passed by caller | Arguments target should receive | Expectation |
| --- | --- | --- | --- |
| Unchanged | `passthrough("keep")` | `"keep"` | Unchanged due to `proceed()` |
| Replace `String` + primitive | `submit(" alice ",2)` | `("ALICE",3)` | Both positions accurate |
| Bind only one arg in advice | `inspect(" bob ",4)` | `("BOB",6)` | Spring uses all two method arguments |
| Exception propagation | `fail(" bad ")` | `"BAD"` then throws | Caller receives original exception |
| Wrong arity | `submit("A",1)` yet advice passes length-1 array | No valid invocation | Test verifies rejection, target does not run |
| Wrong position/type | `submit("A",1)`, array `[1,"A"]` | Incompatible with `(String,int)` | Must not be treated as valid behavior |
| Primitive receives `null` | `submit("A",1)`, array `["A",null]` | `int` cannot take `null` | Must validate before proceeding |
| Caller uses `new OrderService()` | Any | Calls target directly, no proxy | Around advice does not run |
| Self-invocation | `this.submit(...)` inside target | Internal Java call | Bypasses Spring proxy despite pointcut |

To write negative tests without leaving dangerous behavior in production code, create a **test-only aspect** or unit test that expects a sufficiently general exception and checks that the target counter does not increment. Inspect the root cause for your Spring version rather than hardcoding exact exception messages.

In section 5's project, the `adviceCalls` and `targetCalls` counters, return values, and exception messages provide four distinct proofs. The exercise does not depend on logging frameworks or unpredictable timing results.

### A Minimal Additional JUnit Test for Section 5's Project

If you want to turn the checks in `App.main()` into an automated integration test, add the `junit-jupiter` test dependency and a JUnit 5–compatible `maven-surefire-plugin` version, then create:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProceedArgumentsTest {
    @Test
    void replacementArgumentsReachTargetThroughSpringProxy() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            RewriteAspect aspect = context.getBean(RewriteAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals(
                "order:ALICE:3",
                service.submit(" alice ", 2));
            assertEquals(
                "inspect:BOB:6",
                service.inspect(" bob ", 4));
            assertEquals(2, aspect.getAdviceCalls());
            assertEquals(2, service.getTargetCalls());
        }
    }
}
~~~

This is a **complete `src/test/java/demo/ProceedArgumentsTest.java` file**, yet it needs the extra JUnit/Surefire dependencies mentioned above, so it **will not run with only section 5's minimal `pom.xml`**. The assertion values verify both argument-modification techniques inside one Spring `ApplicationContext`.

Make sure the test invokes calls through `context.getBean(...)`, not `new OrderService()`, because we need to verify **Spring AOP** semantics, not merely test a Java helper manipulating `Object[]`.

## 9. Structuring Parameter Binding for Portable Advice

In Spring AOP, this is valid for `inspect(String,int)`:

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(..)) && args(label,..)",
    argNames = "label"
)
public Object around(ProceedingJoinPoint pjp, String label)
        throws Throwable {
    Object[] all = pjp.getArgs().clone();
    all[0] = label.trim();
    return pjp.proceed(all);
}
~~~

However, because the advice binds only **one** parameter of the target, it is not the strongest choice if you want to reuse the same `@AspectJ` aspect source across **both Spring AOP and the AspectJ compiler/weaver**.

If a more portable pattern is the goal, bind all method parameters in full:

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(String,int))"
          + " && args(label,units)",
    argNames = "label,units"
)
public Object around(
        ProceedingJoinPoint pjp, String label, int units)
        throws Throwable {
    return pjp.proceed(new Object[] {
        label.trim(),
        units + 2
    });
}
~~~

In this form, the advice has two binding variables in the exact same order as the two method parameters. Listing all names in `argNames` helps Spring resolve bindings reliably; the Java `-parameters` compiler flag can help discover names, yet should not be an implicit assumption when sharing libraries.

These are **two alternative ways to write `aroundInspect`** in the aspect class; do not include both at once. The second pattern closely follows the Spring documentation's recommendation for minimizing `proceed(Object[])` differences between Spring proxy AOP and the AspectJ compiler/weaver. This lesson executes only under **Spring AOP**; the portability note helps prevent errors when reusing advice.

## 10. Runtime Troubleshooting

When the target receives wrong arguments, throws unfamiliar exceptions, or the advice does not run:

1. **Verify the pointcut:** does the `execution(...)` expression match the actual method on the Spring bean? If not, none of the `proceed` logic runs.
2. **Verify the Spring proxy:** check `AopUtils.isAopProxy(service)` on the exact reference the caller uses. Objects created outside the container and self-invocations are not advised.
3. **Print argument count:** check `pjp.getArgs().length` against **the target method's parameter count**, not the number of arguments bound in the advice.
4. **Check each index and type:** if the method takes `(String,int)`, the array must have `String` at index `0` and `Integer` at index `1`.
5. **Copy the array before mutating:** avoid depending on side effects from mutating `getArgs()` directly.
6. **Do not replace arguments unnecessarily:** if only logging/metrics is needed, keep `proceed()` or consider a narrower `@Before` advice.
7. **Check the return value:** around a `String`-returning method, the advice should return the `Object` produced by `proceed`, or a type-compatible fallback if permitted by requirements.
8. **Check exception propagation:** did the advice catch and swallow the error? If so, that is a business contract change requiring approval, not a default effect of `proceed(Object[])`.
9. **Check overloads, varargs, and generic bridges:** did the selected method match the expected signature? `String...` is `String[]` at the JVM boundary.
10. **Check ordering:** if multiple `@Around`/advisors match, `proceed` forwards into **the rest of the interceptor chain**, not necessarily straight to the target. Test with the real Spring context and advisor order when arguments affect cache/transactions/security.
11. **Verify raw vs. transformed:** log a marker inside the target or use a spy/test counter. Logging only before `proceed` does not prove the target received the new array.
12. **Read the root cause rather than guessing exception messages:** wrong length/types cause invocation failure, yet wrappers and error text can vary across versions/framework integrations.

Quick check at a call site that already has an `ApplicationContext` with the `OrderService` bean:

~~~java
OrderService service = context.getBean(OrderService.class);
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service)
);
~~~

This snippet is inserted into a method that has a `context` variable, not a standalone Java file. If it prints `false`, inspect bean/aspect/pointcut wiring before debugging array replacement.

## 11. Self-Check Questions

**1. For `transfer(String from, String to, int amount)` and an advice that binds only `amount`, how many elements does Spring AOP's `proceed(Object[])` array need?**  
**Three** elements, corresponding to `from`, `to`, and `amount`. Do not pass a one-element array merely because the advice has one bound parameter.

**2. When should you call `proceed()` instead of `proceed(Object[])`?**  
When you do not need to replace arguments and only want the method to proceed with the existing argument list.

**3. If `submit(" alice ",2)` is rewritten to `proceed(new Object[]{"ALICE",3})`, does the caller automatically see its input String variable become `"ALICE"`?**  
No. The advice passes a new list of values/references to the target invocation; it does not mutate the caller's local variables.

**4. Can you pass `new Object[]{"ALICE",null}` to `submit(String,int)`?**  
Invalid for primitive `int`. You must pass a compatible numeric wrapper matching the contract.

**5. Why can an advice using `args(label,..)` to bind one parameter still modify both method arguments?**  
Because `pjp.getArgs()` provides the join point's full argument list; `proceed(Object[])` accepts the full method argument list under Spring AOP's convention.

**6. Should you mutate `pjp.getArgs()[0]` directly and then call `proceed()`?**  
Do not rely on side effects on the returned array; express modifications explicitly with `clone()` and `proceed(changed)`.

**7. Can `@Around` omit `proceed`?**  
Yes in terms of capability, yet the target will not run if the advice short-circuits. Do so only when requirements genuinely call for it and the return/exception policy is defined.

**8. Does using `proceed(Object[])` cause `final` methods on the target to be intercepted?**  
No. It operates **only inside an around advice already entered through the proxy**, and does not bypass Spring's method interception limits.

**9. How many elements does varargs `send(String topic, String... tags)` require?**  
By JVM signature, **two** parameters: `String` and `String[]`; do not flatten tags into separate elements of `Object[]`.

**10. What is the biggest difference between Spring AOP and advice compiled by the AspectJ compiler?**  
Spring's `proceed(Object[])` uses the **underlying method's arguments** in order; traditional AspectJ-compiled around advice maps arguments to **the advice's bound parameters**. For portable code, bind all method arguments in order and construct a matching array.

## 12. Practical Checklist

- [ ] Spring bean is retrieved from `ApplicationContext` and its proxy has matching advisors.
- [ ] `@Around` accepts `ProceedingJoinPoint` as its first parameter, and the advice method declares `throws Throwable` if propagating exceptions.
- [ ] If not modifying arguments, prefer `proceed()`; if only logging before execution, consider `@Before`.
- [ ] If modifying arguments, use `proceed(Object[])` and supply the **exact count and order of the target method**.
- [ ] Array elements have compatible types, including primitive wrappers and `null`.
- [ ] When partially binding via `args(...)`, do not confuse the advice's binding count with the method's argument count.
- [ ] Do not depend on mutating `pjp.getArgs()` in place; create an explicit replacement array.
- [ ] Return the result of `proceed` when not intentionally transforming; do not swallow exceptions outside requirements.
- [ ] Do not call `proceed` multiple times when side effects are uncontrolled.
- [ ] Tested return values, target-observed arguments, exceptions, and proxy boundaries.
- [ ] When reusing code across Spring AOP and AspectJ weaving, follow the convention of binding all arguments in order as recommended by Spring.

## 13. Official Spring Framework Documentation

- [Spring Framework 6.2 — Declaring Advice, Around Advice, and Proceeding with Arguments](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): directly explains `proceed()`, `proceed(Object[])`, differences from the AspectJ compiler, and portable argument-binding patterns.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution(...)`, `args(...)`, Spring AOP method-execution semantics.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies and self-invocation limits.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): registering aspects and auto-proxying in a Spring context.
- [ProceedingJoinPoint JavaDoc (AspectJ)](https://www.javadoc.io/doc/org.aspectj/aspectjrt/1.9.22/org/aspectj/lang/ProceedingJoinPoint.html): the `proceed()`/`proceed(Object[])` API used by Spring via `@Around`.
