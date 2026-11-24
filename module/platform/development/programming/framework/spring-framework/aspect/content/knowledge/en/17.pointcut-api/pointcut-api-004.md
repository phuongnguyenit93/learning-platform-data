# StaticMethodMatcherPointcut in Spring AOP and Its Use Cases

## 1. Why Do We Need a Static Pointcut?

When a Spring bean has many methods, we often want to attach an advice only to **a group of methods determined by class and signature**, such as:

- Logging calls to `OrderService.submit(String, int)`, while ignoring `status()`.
- Measuring execution time only for public methods marked with a business annotation.
- Applying an interceptor to methods belonging to a specific service group.
- Keeping method-selection rules in Java code when you do not want to use AspectJ expressions/`@Aspect`.

If the interception scope can be determined **without inspecting argument values on each call**, Spring AOP provides the base class `StaticMethodMatcherPointcut`.

This component belongs to the **Spring Framework AOP API**, not the general AspectJ language mechanism. It helps build a `Pointcut` with a static `MethodMatcher` that can be paired with an `Advice` via an `Advisor` on a Spring proxy.

```text
Caller
  |
  v
Spring proxy
  |
  +--> Advisor
         |
         +--> ClassFilter.matches(targetClass)
         |       false -> skip this advisor's advice
         |
         +--> StaticMethodMatcher.matches(method, targetClass)
                 false -> skip this advisor's advice
                 true  -> allow advice to join the interception chain
  |
  v
Target method (if advice allows continuing)
```

**Key point:** "static" refers to the **method-selection condition**, not that the advice runs only once. If a method matches and a caller invokes it 1,000 times through the proxy, the advice can run 1,000 times. Spring can store/reuse static match results to avoid unnecessary re-evaluation; the exact number of times `matches` is called is an implementation detail and should never become a business contract.

## 2. Fitting StaticMethodMatcherPointcut into the Spring AOP Architecture

The `org.springframework.aop.Pointcut` interface has two parts:

```java
public interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}
```

Here, `ClassFilter` determines whether the **target class** is within scope:

```java
public interface ClassFilter {
    boolean matches(Class<?> clazz);
}
```

And `MethodMatcher` decides whether the **method** matches:

```java
public interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

These are extracted API signatures for explanation, not files you need to create in your project.

`StaticMethodMatcherPointcut` is an abstract class in the package:

```java
org.springframework.aop.support.StaticMethodMatcherPointcut
```

It extends `StaticMethodMatcher` and also implements `Pointcut`. A typical subclass only needs to override:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    // Analyze name, signature, annotations, targetClass...
    return ...;
}
```

Note five important characteristics:

| Member | Behavior of StaticMethodMatcherPointcut | Consequence |
| --- | --- | --- |
| `getClassFilter()` | Returns `ClassFilter.TRUE` by default | If unchanged, does not restrict the target class |
| `setClassFilter(ClassFilter)` | Sets the target class filter | Narrows the class set before checking methods |
| `getMethodMatcher()` | Returns the pointcut's own matcher | Allows passing the pointcut into an advisor |
| `isRuntime()` | Always `false` | Spring skips the per-invocation `args` matching step |
| `matches(Method,Class,Object...)` | Not an extension point for static matchers | Only override `matches(Method,Class)` |

**No need to write all three `MethodMatcher` methods yourself.** This is precisely why you use the base class instead of implementing `Pointcut` and `MethodMatcher` from scratch.

## 3. Distinguishing Static Matching from Dynamic Matching

Suppose you want to record metrics for `submit(String sku, int quantity)`.

**Static condition**: "Is this a method named `submit`, accepting `String` and `int` on `OrderService`?" — Can be answered using `Method` and `targetClass`.

**Dynamic condition**: "Is the `quantity` value in the current call greater than 10?" — Must inspect the `args` array each time the method is called.

```text
submit("A", 2)   -> same Class and Method -> static matcher: TRUE
submit("A", 20)  -> same Class and Method -> static matcher: TRUE

If requiring quantity >= 10:
submit("A", 2)   -> dynamic matcher: FALSE
submit("A", 20)  -> dynamic matcher: TRUE
```

| Criterion | StaticMethodMatcherPointcut | DynamicMethodMatcherPointcut |
| --- | --- | --- |
| Data used for decision | `Method`, `Class<?>` | `Method`, target class, and `Object... args` |
| `isRuntime()` | `false` | `true` |
| Must inspect arguments on each call? | No | Yes, after passing the static check |
| Common use cases | method name/signature, class, annotation | conditions based on invocation parameter values |
| Matching cost | Typically low, optimizable/cacheable | Has an extra evaluation step per invocation |

**Do not use `StaticMethodMatcherPointcut` to check input values** such as `quantity > 0`. Even when a static matcher returns `true`, the advice code or the service itself must enforce business contracts if invalid data needs to be rejected. A pointcut decides *whether advice participates*, not where validation is performed by default.

## 4. Designing Clean and Sufficiently Tight Static Conditions

A basic implementation:

```java
import java.lang.reflect.Method;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public final class SubmitPointcut extends StaticMethodMatcherPointcut {
    public SubmitPointcut() {
        setClassFilter(OrderService.class::isAssignableFrom);
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass) {
        return method.getName().equals("submit")
                && method.getParameterCount() == 2
                && method.getParameterTypes()[0] == String.class
                && method.getParameterTypes()[1] == int.class;
    }
}
```

This is an excerpt: `OrderService` must exist in the same module. A standalone runnable version appears in Section 6.

Meaning of the two steps:

1. `setClassFilter(OrderService.class::isAssignableFrom)` restricts target classes to `OrderService` or its subtypes.
2. `matches(Method,Class)` identifies the exact `submit(String,int)` overload. It does not match the `submit(String)` overload or `status()`.

### Is Matching by Method Name Alone Enough?

The condition:

```java
return method.getName().equals("submit");
```

can accidentally match `submit(String)`, `submit(String,int)`, and `submit(Order)`. If the interceptor needs to read arguments at fixed positions or relies on the return type, you must check the appropriate signature. In some cases, the method name alone is sufficient; in that case, document clearly that **all overloads** will be selected.

### How Does Target Class Matter?

Another class that also has a `submit(String,int)` method does not necessarily belong in scope. If you keep the default `ClassFilter.TRUE` and the matcher checks only the name/signature, the advisor can intercept other classes as well. If the target is solely `OrderService`, configure an appropriate class filter.

Do not compare generated proxy names such as `clazz.getName().contains("CGLIB")`: that is an implementation detail, not a domain characteristic. Use class types, interfaces, annotations, or well-defined package structures.

### How Should Annotations Be Checked?

The presence of a runtime annotation on a method is **static metadata** with respect to a call. However, when using a JDK proxy, the method may be the declaration on the interface; metadata on the implementation may need to be looked up with Spring's API:

```java
// Illustrative snippet of logic inside matches(...):
Method specific = AopUtils.getMostSpecificMethod(method, targetClass);
return AnnotatedElementUtils.hasAnnotation(specific, Monitored.class);
```

Imports:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
```

`Monitored` is an application annotation that you must declare with `@Retention(RUNTIME)` and `@Target(METHOD)`. `AnnotatedElementUtils` supports how Spring handles certain meta-annotation/merged annotation cases; if a project has bridge methods, generic/interface methods, or complex overrides, test with the actual proxy type. Relying solely on `method.getAnnotation(...)` in all situations can miss annotations on the implementation.

## 5. From Pointcut to Advice: A Matcher Alone Does Not Intercept

`StaticMethodMatcherPointcut` only decides *whether a match occurs*. To affect a call, you must wire:

```text
StaticMethodMatcherPointcut
         +
MethodInterceptor (Advice)
         |
         v
DefaultPointcutAdvisor
         |
         v
Spring AOP proxy
         |
         v
Service target
```

In Java code, the structure typically looks like:

```java
MethodInterceptor interceptor = invocation -> {
    System.out.println("before");
    try {
        return invocation.proceed();
    } finally {
        System.out.println("after");
    }
};

var advisor = new DefaultPointcutAdvisor(
        new SubmitPointcut(), interceptor);

var proxyFactory = new ProxyFactory(target);
proxyFactory.addAdvisor(advisor);
Object proxy = proxyFactory.getProxy();
```

This snippet illustrates wiring: `target` and `SubmitPointcut` must be declared in the program. `DefaultPointcutAdvisor` pairs a `Pointcut` with an `Advice`; `ProxyFactory` creates the Spring AOP proxy.

Calling `invocation.proceed()` passes the call through the rest of the interceptor chain to the target (unless another interceptor blocks it further down). If you forget to call it without intentionally replacing the return value, the target method will not execute. The `finally` block still runs when the target throws an exception; that is **advice** behavior, independent of how the static pointcut selected the method.

**Distinguishing `Pointcut` and `@Pointcut`:** `org.springframework.aop.Pointcut` is an object with a `ClassFilter` and a `MethodMatcher`; `org.aspectj.lang.annotation.Pointcut` is an annotation used to declare pointcuts inside `@Aspect`. The two APIs are conceptually related, but their configuration differs.

## 6. Complete Example with Java 17 and Spring ProxyFactory

The example below needs no `@Aspect` or AspectJ Weaver. We use the Spring AOP API directly to demonstrate exactly how `StaticMethodMatcherPointcut` is wired into an advisor.

Verification goals:

- Intercept `OrderService.submit(String,int)` for any `quantity` value.
- Do not intercept `OrderService.submit(String)` (overload) or `OrderService.status()`.
- Do not intercept `OtherService.submit(String,int)`, even with the same name/signature.
- Record the exact call order `before → target → after` and preserve return values.

Structure:

```text
spring-static-pointcut/
├── pom.xml
└── src/
    ├── main/java/example/StaticPointcutDemo.java
    └── test/java/example/StaticPointcutDemoTest.java
```

### 6.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-static-pointcut</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. File src/main/java/example/StaticPointcutDemo.java

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class StaticPointcutDemo {

    public static class OrderService {
        private final List<String> events;

        public OrderService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("target:submit:" + sku + ":" + quantity);
            return "OK:" + sku + ":" + quantity;
        }

        public String submit(String sku) {
            events.add("target:overload:" + sku);
            return "OVERLOAD:" + sku;
        }

        public String status() {
            events.add("target:status");
            return "READY";
        }
    }

    public static class OtherService {
        private final List<String> events;

        public OtherService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("other:submit:" + sku + ":" + quantity);
            return "OTHER:" + sku + ":" + quantity;
        }
    }

    public static class SubmitPointcut extends StaticMethodMatcherPointcut {
        public SubmitPointcut() {
            // Only OrderService (or subclasses) qualify.
            setClassFilter(OrderService.class::isAssignableFrom);
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("submit")
                    && method.getParameterCount() == 2
                    && method.getParameterTypes()[0] == String.class
                    && method.getParameterTypes()[1] == int.class;
        }
    }

    public record Fixture(OrderService service, List<String> events) {}

    public static Fixture createFixture() {
        List<String> events = new ArrayList<>();
        OrderService target = new OrderService(events);

        MethodInterceptor trace = invocation -> {
            events.add("before:" + invocation.getMethod().getName());
            try {
                return invocation.proceed();
            } finally {
                events.add("after:" + invocation.getMethod().getName());
            }
        };

        ProxyFactory factory = new ProxyFactory(target);
        factory.setProxyTargetClass(true);
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));

        return new Fixture((OrderService) factory.getProxy(), events);
    }

    public static OtherService createOtherProxy(List<String> events) {
        ProxyFactory factory = new ProxyFactory(new OtherService(events));
        factory.setProxyTargetClass(true);

        MethodInterceptor trace = invocation -> {
            events.add("UNEXPECTED");
            return invocation.proceed();
        };

        // Same advisor, but ClassFilter does not select OtherService.
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));

        return (OtherService) factory.getProxy();
    }

    public static void main(String[] args) {
        Fixture fixture = createFixture();
        OrderService order = fixture.service();

        System.out.println(order.submit("A", 2));
        System.out.println(order.submit("B", 12));
        System.out.println(order.submit("A"));
        System.out.println(order.status());

        List<String> otherEvents = new ArrayList<>();
        OtherService other = createOtherProxy(otherEvents);
        System.out.println(other.submit("C", 99));

        System.out.println("orderEvents=" + fixture.events());
        System.out.println("otherEvents=" + otherEvents);
    }
}
```

Component-by-component explanation:

1. `SubmitPointcut` is a subclass of Spring's `StaticMethodMatcherPointcut`; the class filter excludes `OtherService` before inspecting methods.
2. `matches` inspects only **name and signature**. Whether `quantity` is 2, 12, or 0, the match result for `submit(String,int)` is identical.
3. `ProxyFactory` takes the target and adds `DefaultPointcutAdvisor`. Only `submit` calls through the proxy run the interceptor; instantiating `new OrderService(events)` directly and calling it produces no advice.
4. `factory.setProxyTargetClass(true)` requests a class-based proxy so the result can be cast to `OrderService`/`OtherService`. In applications using interfaces, a JDK proxy can be a good fit, provided the bean is retrieved via its interface.
5. The advice uses `try/finally`, so `after:submit` still occurs if the target throws an exception. This is a **guarantee written by the advice**, not automatically generated by the pointcut.

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.StaticPointcutDemo
```

Expected logical stdout (excluding Maven/Spring logs if any):

```text
OK:A:2
OK:B:12
OVERLOAD:A
READY
OTHER:C:99
orderEvents=[before:submit, target:submit:A:2, after:submit, before:submit, target:submit:B:12, after:submit, target:overload:A, target:status]
otherEvents=[other:submit:C:99]
```

Evidence from the output:

- Both `submit(String,int)` calls emit `before`/`after` despite differing quantities. That is the essence of **static** matching.
- `submit(String)` shares the same name but is a different overload, recording only `target:overload:A`.
- `status()` is not intercepted; `OtherService.submit(...)` also has no `UNEXPECTED` thanks to the class filter.
- Target methods still return their normal results because the interceptor calls `proceed()`.

## 7. Two-Layer Testing: Matcher Contract and Actual Proxy

A test that only calls `pointcut.matches(...)` does not prove the advisor is wired onto the proxy. A test that only checks logs from calling the service may miss an overly broad `ClassFilter` on the matcher. Combine both layers:

`src/test/java/example/StaticPointcutDemoTest.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.*;

class StaticPointcutDemoTest {

    @Test
    void staticMatcherMatchesOnlyExpectedClassAndSignature()
            throws Exception {
        var pointcut = new StaticPointcutDemo.SubmitPointcut();

        Method matched = StaticPointcutDemo.OrderService.class
                .getMethod("submit", String.class, int.class);
        Method overload = StaticPointcutDemo.OrderService.class
                .getMethod("submit", String.class);
        Method status = StaticPointcutDemo.OrderService.class
                .getMethod("status");

        assertTrue(pointcut.getClassFilter()
                .matches(StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getClassFilter()
                .matches(StaticPointcutDemo.OtherService.class));

        assertTrue(pointcut.getMethodMatcher()
                .matches(matched, StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getMethodMatcher()
                .matches(overload, StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getMethodMatcher()
                .matches(status, StaticPointcutDemo.OrderService.class));

        assertFalse(pointcut.getMethodMatcher().isRuntime());
    }

    @Test
    void springProxyAppliesInterceptorToEveryMatchingInvocation() {
        var fixture = StaticPointcutDemo.createFixture();
        var order = fixture.service();

        assertTrue(AopUtils.isAopProxy(order));
        assertEquals("OK:A:2", order.submit("A", 2));
        assertEquals("OK:B:12", order.submit("B", 12));
        assertEquals("OVERLOAD:A", order.submit("A"));
        assertEquals("READY", order.status());

        assertEquals(List.of(
                "before:submit",
                "target:submit:A:2",
                "after:submit",
                "before:submit",
                "target:submit:B:12",
                "after:submit",
                "target:overload:A",
                "target:status"), fixture.events());
    }

    @Test
    void anotherClassWithSameMethodSignatureIsExcluded() {
        List<String> events = new ArrayList<>();
        var other = StaticPointcutDemo.createOtherProxy(events);

        assertEquals("OTHER:C:99", other.submit("C", 99));
        assertEquals(List.of("other:submit:C:99"), events);
    }
}
```

Run:

```bash
mvn -q test
```

The three tests answer three questions:

| Test | Verification |
| --- | --- |
| `staticMatcherMatchesOnlyExpectedClassAndSignature` | ClassFilter and MethodMatcher accurately distinguish classes, overloads, and other methods; `isRuntime()==false` |
| `springProxyAppliesInterceptorToEveryMatchingInvocation` | Advice is attached to the Spring proxy, runs for both quantity=2 and quantity=12, and preserves target results |
| `anotherClassWithSameMethodSignatureIsExcluded` | ClassFilter prevents the advisor from applying to another class with the same method name/signature |

**Avoid writing tests asserting that "`matches` runs exactly once".** Spring may evaluate advisor applicability at proxy creation, on the first invocation, or through other internal code paths. The public contract here is not inspecting `args` at runtime, not a fixed invocation counter on the matcher method.

## 8. Suitable Real-World Use Cases

### 8.1. Recording Metrics for a Fixed Group of Methods

Select public methods on services matching a domain naming convention. For example, a filter such as:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().startsWith("find")
            && method.getParameterCount() <= 2;
}
```

This is a method snippet inside a `StaticMethodMatcherPointcut` subclass, not a standalone runnable class. To measure latency, the advice uses `System.nanoTime()` around `proceed()`; **method selection** does not measure latency itself. When an async service returns a `CompletableFuture`, elapsed time around `proceed()` does not necessarily reflect future completion time.

### 8.2. Applying Policy Based on Method Annotations

If a policy is declared statically via `@Measured` or `@Audited`, the matcher can inspect annotations on the method and use `ClassFilter` to narrow down to service packages/target types. Because annotation conditions are stable across invocations, they fit static pointcuts well. However, policies inside the advice still require careful design and testing for sensitive data and error handling.

### 8.3. Filtering by Signature, Overload, or Interface

For APIs with multiple same-named overloads, a static matcher accurately distinguishes `submit(String,int)` from `submit(String)`. When using JDK dynamic proxies, the reflected interface method may differ from the implementation method. Test **both the proxy type and actual annotation placement**. `ClassFilter` inspects only the target class; do not assume it refers to the proxy name.

### 8.4. Reusing One Pointcut Across Multiple Advices

Because a pointcut is independent of advice, the same pointcut instance or class can be attached to multiple advisors:

```java
var pointcut = new SubmitPointcut();

factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, metricsAdvice));
factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, auditAdvice));
```

This is a wiring snippet assuming `factory`, `metricsAdvice`, and `auditAdvice` already exist. If two advices both match, advisor ordering determines the observed execution order. Using `@Order` elsewhere does not automatically guarantee the order of advisors added manually to `ProxyFactory`; configure and test the exact order explicitly.

### 8.5. When Not to Use a Custom Static Matcher

- Simple method-name matching: consider `NameMatchMethodPointcut` to reduce boilerplate.
- Common package/annotation/interface expression conditions: `AspectJExpressionPointcut` or `@Pointcut` inside a Spring `@Aspect` can be more readable.
- Need to inspect argument values on each call: use an appropriate `DynamicMethodMatcherPointcut` or place the check in the advice/service according to responsibility.
- Need to intercept constructors, field access, or internal calls bypassing the proxy: Spring AOP proxies do not directly support those join points, even with a custom pointcut.

## 9. Composing Multiple Static Conditions

Spring supports `ComposablePointcut` and the `Pointcuts` utility to form unions or intersections of conditions.

- **Intersection:** the method must satisfy **both** requirements, e.g., matching service class *and* annotated method.
- **Union:** the method satisfies **at least one branch**, e.g., `submit` *or* `cancel`.

Illustrative example:

```java
// One pointcut selects submit(String,int).
var submit = new SubmitPointcut();

// Another pointcut selects cancel(String).
var cancel = new CancelPointcut();

// Create a combined pointcut, then pass it to DefaultPointcutAdvisor.
var combined = new ComposablePointcut(submit).union(cancel);
```

This is an API illustration snippet: `SubmitPointcut` comes from the Section 6 example, while `CancelPointcut` and the `cancel` method must be created before running. Import `org.springframework.aop.support.ComposablePointcut`. When composing complete pointcuts, preserve the pairing between **each branch's ClassFilter and its MethodMatcher**; do not blindly merge "all classes from both branches" with "all methods from both branches" if doing so causes over-matching.

When a pointcut is already simple, writing too many matcher classes and compositions can be harder to understand than a clear pointcut expression. Choose the API because it makes the interception contract explicit and testable, not to replace `@Aspect` everywhere.

## 10. Spring Proxy Limitations and Design Pitfalls

| Symptom | Cause | How to Verify/Fix |
| --- | --- | --- |
| `matches` test passes but advice never runs | Advisor not attached to proxy or caller uses raw target directly | Use `ProxyFactory`/real Spring bean proxy and `AopUtils.isAopProxy(...)` |
| Other methods are also intercepted | Matcher checks only name, failing to distinguish overloads/classes | Check name, parameter count, and types; set a ClassFilter |
| Correctly named method is not intercepted | `ClassFilter` excludes target class or signature mismatches | Unit test ClassFilter and MethodMatcher separately on the real class |
| Need to distinguish quantity=2 and quantity=12, yet advice always runs | Static matcher does not read `args` values | Use a dynamic matcher or conditional logic in advice/service |
| Interface vs. implementation overloads differ | Received `Method` may be the interface declaration | Use API to resolve most-specific method and test real proxy type |
| Caller inside bean uses `this.submit(...)` | Self-invocation bypasses the proxy | Invoke through an appropriate Spring-managed proxy/boundary |
| Target is a `final`/`private` method | Proxy-based AOP has overriding/interception limits | Design proxyable methods; write integration tests |
| Advice does not call target | Interceptor does not call `proceed()` | Continue the chain unless intentionally altering the contract |
| Matcher queries DB or logs I/O when matching | Side effects and overhead during advisor selection | Keep matchers pure, lightweight, and independent of mutable state |
| Test outcome depends on how many times `matches` is called | Treating caching strategy as a contract | Test match results and advice behavior, not internal call counts |

### Why Should a Matcher Be a Pure Function?

A method matcher receives static information about the method/class. If it depends on "current time", mutable global variables, request state, or external I/O, results may become inconsistent with how the framework caches static match results. Never put stateful business logic inside `matches`. Use truly static conditions, or move invocation-dependent logic into the appropriate component.

### Self-Invocation and Testing on Real Beans

Suppose `OrderService.status()` calls `this.submit("A",2)`. In standard Spring proxy mode, the internal call does not pass through the proxy, so advice for `submit` may not appear. This **does not prove the matcher is wrong**. When testing AOP behavior, always start from a caller holding the **proxy** rather than using the raw target object to verify interception.

### Clarifying Resources and Errors

A static pointcut can select the right method, yet it does not solve running advice on exceptions, transactions, async, or reactive flows. Those semantics are determined by the **Advice/Advisor and proxy chain**, not by the name `StaticMethodMatcherPointcut`. For example, a metrics interceptor with `finally` will still record duration on exceptions, whereas `@AfterReturning` applies only on normal returns.

## 11. Practice Exercises and Completion Criteria

Starting from `StaticPointcutDemo`:

1. Add a `submit(String,int,boolean)` method. Keep the current matcher and verify the new overload is **not intercepted**.
2. Replace `ClassFilter` with `ClassFilter.TRUE`, create an `OtherService` proxy with the same advisor, and observe it start emitting `UNEXPECTED` logs. Restore the old filter to fix it.
3. Change the matcher condition to select both `submit` and `status`; predict and then verify the event order.
4. Add a `@Measured` annotation on `submit` and update the matcher to select only annotated methods. Test an interface-backed implementation if the application uses JDK proxies.
5. To measure only calls with `quantity >= 10`: explain why a static matcher is insufficient; switch to a dynamic matcher or intentional condition in the interceptor, then test the 9/10 boundary.
6. Put one counter inside the advice itself and a diagnostic counter inside the matcher. Run multiple invocations and observe the difference, but **never turn Spring's matcher call count into a pass/fail assertion**, since optimization mechanisms vary.

An implementation meets the criteria when you can demonstrate: right target class, right method/overload, advice runs **every time a selected method is called through the proxy**, method return values/exceptions are preserved properly, out-of-scope methods and classes are not intercepted, and static conditions are not confused with dynamic argument checks.

### Official Spring Documentation

- Pointcut API and static/dynamic matchers: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- `StaticMethodMatcherPointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html
- `StaticMethodMatcher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/StaticMethodMatcher.html
- Advisor API: https://docs.spring.io/spring-framework/reference/core/aop-api/advisor.html
- Spring proxies and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html