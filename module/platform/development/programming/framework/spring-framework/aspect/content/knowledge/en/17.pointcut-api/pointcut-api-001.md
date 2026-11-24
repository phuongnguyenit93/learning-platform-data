# Pointcut, ClassFilter, and MethodMatcher in Spring AOP

## 1. The Problem: How Does Spring Decide Which Calls Receive Advice?

A Spring AOP interceptor should not run for every method in an application. We typically want to measure execution time only for business methods, check a specific group of services, or log operations conditionally. A **Pointcut** is the contract that selects which *method executions* an advice is allowed to participate in when a call goes through a **Spring AOP proxy**.

Spring provides two familiar approaches:

- Declaring pointcuts using AspectJ expressions in `@Aspect`/XML, which is usually suitable for rules based on method names, annotations, or packages.
- Using the **Spring Pointcut API** directly when you need to compose conditions in Java, reuse a filter, or make conditional decisions based on actual runtime arguments.

This lesson focuses on the second approach: the three interfaces in Spring and how to wire them to a Spring advisor/proxy.

```text
Caller -> Spring proxy -> Advisor
                              |
                              v
                          Pointcut
                           /    \
                 ClassFilter    MethodMatcher
                 class matches?  method matches?
                       \          /
                        \        /
                           yes
                            |
                         advice
                            |
                       target method
```

If `ClassFilter` rejects the class or `MethodMatcher` rejects the method, the corresponding advice will not participate in that call. The target method can still run normally through the proxy if no other advice rejects it.

## 2. Spring's Three Core Interfaces

### 2.1. `Pointcut`: Combining a Class Filter and a Method Matcher

The `org.springframework.aop.Pointcut` API:

```java
public interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}
```

Spring uses **both** to determine whether an advisor applies to a method on a target class. `Pointcut.TRUE` is a pointcut that always matches, which is useful when advice is needed everywhere, though it can be too broad for business logic.

A pointcut **only describes the selection condition**. It does not contain execution code to run before or after the target. In Spring AOP, `DefaultPointcutAdvisor` pairs a pointcut with an `Advice` to create an interception rule.

### 2.2. `ClassFilter`: Selecting the Target Class Group

The `org.springframework.aop.ClassFilter` API:

```java
public interface ClassFilter {
    boolean matches(Class<?> clazz);
}
```

In a service example:

```java
ClassFilter orderClasses =
        clazz -> OrderService.class.isAssignableFrom(clazz);
```

This condition matches `OrderService` and its compatible subclasses. If you only use `clazz == OrderService.class`, the filter excludes subclasses and may cause surprises when the application is extended. Conversely, a filter like `clazz.getSimpleName().endsWith("Service")` might be unintentionally broad.

`ClassFilter.TRUE` allows every class; choose it only when the method filter or another pointcut is truly narrow enough.

**Note:** the `clazz` argument represents information about the **target class** that Spring uses when matching, not the proxy name generated for the caller to invoke. A matching class filter does not guarantee that every method in the class will be intercepted: `MethodMatcher` must still match.

### 2.3. `MethodMatcher`: Static and Argument-Based Method Selection

The `org.springframework.aop.MethodMatcher` API:

```java
public interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

The two matching phases have different meanings:

1. `matches(Method, Class<?>)` is a **static check** based on the method and target class; Spring can optimize or cache its result depending on proxy characteristics.
2. If the static result is `true` **and** `isRuntime() == true`, Spring proceeds to call `matches(Method, Class<?>, Object... args)` **for each invocation**, before the advice, to check the specific arguments.

When `isRuntime() == false`, the 3-parameter match is not used to decide advice at runtime. When `isRuntime() == true`, the static condition is still the **first gate**; returning `false` at this stage means the argument check may never run.

| Condition Type | Example | When Is It Matched? | Cost |
| --- | --- | --- | --- |
| `ClassFilter` | Only `OrderService` | When Spring determines advisor applicability for a target class | Usually infrequent |
| Static `MethodMatcher` | Method name is `submit` and has two parameters | Can be checked/cached in the proxy chain | Lower than dynamic |
| Dynamic `MethodMatcher` | `quantity >= 10` on each `submit` call | On each invocation whose method matched statically | Higher; must inspect args every time |

A condition like `quantity >= 10` **cannot be matched using `Method` reflection alone**: `Method` describes the signature, not the value of `quantity` in each individual call.

## 3. Advice Decision Order in a Spring Proxy

Consider an advisor containing a dynamic pointcut:

```text
1. Caller invokes proxy.submit("A-1", 12).
2. Spring checks whether the target class passes ClassFilter?
   └─ No -> advisor does not apply.
3. Does method submit(String,int) pass matches(Method,Class)?
   └─ No -> advisor does not apply.
4. If isRuntime() is true, check matches(Method,Class,args)
   └─ False -> skip advice for this invocation.
5. If all conditions are true, run advice.
6. If advice calls proceed(), the chain continues to target.
```

**Spring AOP characteristic:** the same method may run advice on some calls and not on others if a dynamic matcher is used and calls have different arguments. However, Spring AOP is still a **proxy-based** mechanism: self-invocation `this.submit(...)` typically does not go through the proxy, even if all match conditions hold. `final`/`private` methods have their own proxy limitations; a pointcut cannot fix these limitations on its own.

An advisor may not even be added to the proxy chain if Spring determines the entire class/method is inapplicable; therefore, you should not rely on side effects inside `matches` to execute business logic.

## 4. Choosing Helper Classes Instead of Re-implementing Every Interface

Spring provides utility classes:

| API | When to Use? | Details |
| --- | --- | --- |
| `StaticMethodMatcherPointcut` | Condition depends only on class/method | Override `matches(Method,Class)`; `isRuntime() == false` |
| `DynamicMethodMatcherPointcut` | Must inspect arguments on each call | Override the dynamic check, and narrow the static check if known in advance |
| `NameMatchMethodPointcut` | Select methods by simple name/pattern | No need to write a custom matcher |
| `JdkRegexpMethodPointcut` | Select methods using regex | Check patterns and scope before applying broadly |
| `AspectJExpressionPointcut` | Want to use AspectJ pointcut syntax in Spring | Suitable for many common rules |
| `ComposablePointcut` / `Pointcuts` | Need union/intersection of pointcuts | Can combine filters without creating new classes |

`StaticMethodMatcherPointcut` already implements `Pointcut` and `MethodMatcher`; it defaults to `ClassFilter.TRUE`, which can be replaced with `setClassFilter(...)`.

`DynamicMethodMatcherPointcut` also implements `Pointcut` and `MethodMatcher`; this class allows all classes by default via `getClassFilter()`, so it can be overridden to narrow the scope. Unlike a static matcher, the dynamic mechanism must check arguments at the time the method is actually invoked.

You should prefer a **static pointcut** if the selection condition can be determined from the class/method. A dynamic matcher is appropriate when argument values decide *whether advice runs*, though it incurs an extra check on every statically matching call.

## 5. Complete Java 17+ Example: Static and Dynamic Matchers on the Same Spring Proxy

Illustrative example:

- The first advisor applies only to `OrderService.submit(String, int)`. It uses `StaticMethodMatcherPointcut` and `ClassFilter`.
- The second advisor runs only when it is also the `submit` method **and** `quantity >= 10`. It uses `DynamicMethodMatcherPointcut`.
- `OrderService.status()` matches neither method matcher, so it produces no advice logs.
- `OtherService.submit(...)` has a method with the same name but is rejected by the class filter.

We use `ProxyFactory` to observe the Spring AOP API directly. `ProxyFactory` belongs to Spring Framework and creates a Spring proxy from a target and advisors; the example does not use AspectJ weaving or `@Aspect` annotations.

Structure:

```text
spring-pointcut-api/
├── pom.xml
└── src/
    ├── main/java/example/PointcutDemo.java
    └── test/java/example/PointcutDemoTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>spring-pointcut-api</artifactId>
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

`src/main/java/example/PointcutDemo.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.ClassFilter;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.DynamicMethodMatcherPointcut;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class PointcutDemo {
    public static class OrderService {
        private final List<String> events;

        public OrderService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("target:submit:" + quantity);
            return "OK:" + sku + ":" + quantity;
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
            events.add("other:submit");
            return "OTHER:" + sku + ":" + quantity;
        }
    }

    // Select only OrderService (and subtypes) + submit(String,int).
    public static class SubmitPointcut extends StaticMethodMatcherPointcut {
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

    // Static: select the exact method. Dynamic: only run advice when quantity >= 10.
    public static class BulkPointcut extends DynamicMethodMatcherPointcut {
        @Override
        public ClassFilter getClassFilter() {
            return OrderService.class::isAssignableFrom;
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("submit")
                    && method.getParameterCount() == 2
                    && method.getParameterTypes()[0] == String.class
                    && method.getParameterTypes()[1] == int.class;
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass,
                               Object... args) {
            return args.length == 2
                    && args[1] instanceof Integer quantity
                    && quantity >= 10;
        }
    }

    public record Fixture(OrderService service, List<String> events) {}

    public static Fixture createFixture() {
        List<String> events = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new OrderService(events));
        factory.setProxyTargetClass(true);

        MethodInterceptor trace = invocation -> {
            events.add("static:before");
            Object result = invocation.proceed();
            events.add("static:after");
            return result;
        };

        MethodInterceptor bulk = invocation -> {
            events.add("bulk:before");
            Object result = invocation.proceed();
            events.add("bulk:after");
            return result;
        };

        // First advisor is outer; second advisor is inner.
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new BulkPointcut(), bulk));

        OrderService proxy = (OrderService) factory.getProxy();
        return new Fixture(proxy, events);
    }

    public static void main(String[] args) {
        Fixture fixture = createFixture();
        OrderService service = fixture.service();

        System.out.println(service.submit("A-1", 2));
        System.out.println(service.submit("B-2", 12));
        System.out.println(service.status());
        System.out.println(fixture.events());

        // Same method name but different target class -> excluded by ClassFilter.
        List<String> otherEvents = new ArrayList<>();
        ProxyFactory otherFactory =
                new ProxyFactory(new OtherService(otherEvents));
        otherFactory.setProxyTargetClass(true);
        otherFactory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(),
                (MethodInterceptor) invocation -> {
                    otherEvents.add("SHOULD_NOT_RUN");
                    return invocation.proceed();
                }));
        OtherService other = (OtherService) otherFactory.getProxy();
        System.out.println(other.submit("C-3", 99));
        System.out.println(otherEvents);
    }
}
```

Code explanation:

1. `SubmitPointcut` selects the exact `OrderService` class and `submit(String,int)` method. Spring does not need to inspect args to decide on this advisor.
2. `BulkPointcut` uses the same static condition, then activates the advice only if the second parameter is an `Integer` with a value of at least `10`. Java boxing converts the primitive `int` argument into an `Integer` in the `Object... args` array.
3. `ProxyFactory.addAdvisor(...)` pairs the matching condition with a `MethodInterceptor`. With the first advisor on the outside, trace events wrap around bulk events when both match.
4. `invocation.proceed()` advances to the next interceptor/target; if omitted, the target method may not run. `ClassFilter` is not responsible for replacing `proceed()`.
5. Events are stored in a `List` purely for demonstration. The example runs sequentially; if used in a multi-threaded setting, a thread-safe structure and appropriate synchronization policy are required.

Run with Java 17 and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.PointcutDemo
```

Expected logical output (excluding environment-dependent Maven/Spring logs):

```text
OK:A-1:2
OK:B-2:12
READY
[static:before, target:submit:2, static:after, static:before, bulk:before, target:submit:12, bulk:after, static:after, target:status]
OTHER:C-3:99
[other:submit]
```

Key observations:

- `submit(...,2)` matches the static matcher, but the dynamic matcher returns `false`, so only `static:*` appears.
- `submit(...,12)` matches both advisors, showing `static:before` → `bulk:before` → target → `bulk:after` → `static:after`.
- `status()` only adds `target:status`.
- `OtherService.submit` does not have `SHOULD_NOT_RUN` because `ClassFilter` excludes that target class. Creating a proxy for a target with `ProxyFactory` does not guarantee that every advisor will run.

## 6. Testing ClassFilter, MethodMatcher, and the Proxy Path Separately

In real systems, good tests should verify both the **pure matching conditions** and **behavior through the Spring proxy**. Tests that only call `matches(...)` can miss advisor wiring bugs; conversely, tests that only inspect logs can miss untested dynamic cases.

`src/test/java/example/PointcutDemoTest.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.*;

class PointcutDemoTest {
    @Test
    void classAndMethodMatcherHaveExpectedContract() throws Exception {
        var staticPc = new PointcutDemo.SubmitPointcut();
        var dynamicPc = new PointcutDemo.BulkPointcut();

        Method submit = PointcutDemo.OrderService.class
                .getMethod("submit", String.class, int.class);
        Method status = PointcutDemo.OrderService.class
                .getMethod("status");

        assertTrue(staticPc.getClassFilter()
                .matches(PointcutDemo.OrderService.class));
        assertFalse(staticPc.getClassFilter()
                .matches(PointcutDemo.OtherService.class));
        assertTrue(staticPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class));
        assertFalse(staticPc.getMethodMatcher()
                .matches(status, PointcutDemo.OrderService.class));
        assertFalse(staticPc.getMethodMatcher().isRuntime());

        assertTrue(dynamicPc.getMethodMatcher().isRuntime());
        assertTrue(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class));
        assertTrue(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class, "A", 10));
        assertFalse(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class, "A", 2));
    }

    @Test
    void proxyOnlyAppliesAdvisorsWhenFiltersMatch() {
        var fixture = PointcutDemo.createFixture();
        var service = fixture.service();

        assertTrue(AopUtils.isAopProxy(service));
        assertTrue(service instanceof Advised);
        assertEquals("OK:A:2", service.submit("A", 2));
        assertEquals("OK:B:12", service.submit("B", 12));
        assertEquals("READY", service.status());

        assertEquals(List.of(
                "static:before",
                "target:submit:2",
                "static:after",
                "static:before",
                "bulk:before",
                "target:submit:12",
                "bulk:after",
                "static:after",
                "target:status"), fixture.events());
    }
}
```

Run:

```bash
mvn -q test
```

The two tests verify different contracts. The first directly tests `ClassFilter`, method signatures, and `isRuntime()`, including the same method with different args. The second creates a Spring proxy and checks the actual events; ensuring `status` produces no advice protects against overly broad matching. When renaming methods or changing classes, a similar test helps catch scope regressions.

**Note on test design:** `Advised` helps verify that the proxy supports advisor inspection; tests should not couple to generated class name details (such as the `$$SpringCGLIB$$` string) because that is not a stable API.

## 7. Do You Have to Implement `Pointcut` Yourself?

No. If you already have a `ClassFilter` and `MethodMatcher`, you can combine them with `ComposablePointcut`:

```java
// Illustrative snippet applicable in a program with two matching conditions.
ClassFilter filter = OrderService.class::isAssignableFrom;
MethodMatcher matcher = new SubmitPointcut().getMethodMatcher();

Pointcut result = new ComposablePointcut(filter, matcher);
```

Relevant imports:

```java
import org.springframework.aop.ClassFilter;
import org.springframework.aop.MethodMatcher;
import org.springframework.aop.Pointcut;
import org.springframework.aop.support.ComposablePointcut;
```

Note that `SubmitPointcut` is the example class from Section 5, so when using this snippet in another package you need to reference `PointcutDemo.SubmitPointcut` or import the appropriate nested class.

`ComposablePointcut` provides `intersection(...)` and `union(...)` to combine conditions. There is an important difference:

- **Intersection:** the advice applies when all conditions are true. For example, the service class matches **and** the method has a specific annotation.
- **Union:** the advice applies when at least one pointcut branch is true. For example, both `submit` **or** `cancel` operations need the same audit advice.

When combining **two complete Pointcuts** with a union, Spring preserves the pairing between each branch's `ClassFilter` and its own `MethodMatcher`; it does not arbitrarily mix one branch's class filter with the other branch's method matcher. This avoids over-matching that a naive union could cause.

You can reuse `ClassFilters`, `MethodMatchers`, and `Pointcuts` in `org.springframework.aop.support` to compose conditions. However, for common method name, annotation, and package rules, `AspectJExpressionPointcut` or `@Pointcut` is usually more concise; do not build a complex matcher hierarchy without a clear need.

## 8. Connecting a Pointcut to an Advisor and a Spring Bean

Relationship diagram:

```text
Pointcut                          Advice
(ClassFilter + MethodMatcher)     (MethodInterceptor ...)
        |                                  |
        +-------------+--------------------+
                      |
             DefaultPointcutAdvisor
                      |
               Spring AOP proxy
                      |
                    Target
```

In the Section 5 example, `ProxyFactory` builds a proxy **programmatically** and attaches the advisors directly. In a Spring application using IoC, an advisor can be registered as a bean and discovered by an appropriate auto-proxy creator, or configured via `@Aspect`/XML. Do not confuse registering a standalone `Pointcut` bean with having an active advisor: **a Pointcut not paired with an Advice and proxy mechanism will not run on its own**.

If you only want to apply advice to a single bean constructed in Java code, direct `ProxyFactory` is the simplest example. If multiple beans need a consistent policy, use proper advisor/auto-proxy configuration or a pointcut expression in `@Aspect`.

### Distinguishing the `Pointcut` API and the `@Pointcut` Annotation

| API | Nature | Typical Wiring |
| --- | --- | --- |
| `org.springframework.aop.Pointcut` | Java object providing `ClassFilter` and `MethodMatcher` | `DefaultPointcutAdvisor` or `ProxyFactory` |
| `org.aspectj.lang.annotation.Pointcut` (written `@Pointcut`) | Annotation marking a method that declares an expression inside `@Aspect` | `@Before`, `@Around`, etc. advice |
| `aop:pointcut` in XML | Schema element declaring a named pointcut expression | `pointcut-ref` on an advisor/aspect advice |

All three relate to **selecting** join points, but you cannot directly swap Java annotation syntax for an `org.springframework.aop.Pointcut` instance. What they share is that they only take effect on paths interceptable by Spring AOP.

## 9. When to Choose a Static vs. Dynamic Matcher?

**Use a static matcher** when:

- Selecting by method name/signature, class, package, or annotation whose value does not depend on individual invocations.
- You need low runtime overhead and predictable behavior.
- You want tight interceptor scope protection with minimal stateful logic.

**Use a dynamic matcher only when truly necessary** to inspect args or state available only at invocation time, such as recording metrics for orders with quantity 10 or more. Every invocation must evaluate the dynamic condition, so do not put I/O, DB queries, or heavy processing inside `matches(...,args)`.

A dynamic matcher decides **whether the advice participates**, rather than turning the pointcut into a reliable validation mechanism. In the example, an order with quantity 2 is still sent to the target normally; only the bulk advice is skipped. If the rule is "quantity must be positive", validation must live in the business layer or in an interceptor with clearly designed responsibility and corresponding error handling.

**Do not cache dynamic results by Method** because the same Method can be called with different args; for instance, `submit("A", 2)` and `submit("A", 12)` require different advice outcomes.

## 10. Limitations and Common Pitfalls

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Advice does not run even though the matcher directly returns true | Call bypasses the Spring proxy, or advisor is not attached | Retrieve the actual bean/proxy, check `AopUtils.isAopProxy`, and call through it |
| A same-named method is intercepted on another class | Using `ClassFilter.TRUE` with an overly broad name matcher | Narrow `ClassFilter`; test a different class with the same method name |
| Dynamic advice always runs or never runs | Forgot the static phase, wrong `isRuntime`, or checked wrong arg index | Directly test both `matches` overloads and events when calling the proxy |
| `matches(Method,Class)` returns false hoping dynamic will save it | Spring filters statically before examining args | Ensure the static check returns true for the target method |
| Method still runs when the dynamic condition is false | Pointcut only filters advice, does not necessarily block target | Place validation where the contract belongs |
| Error when `proceed()` is not called | Around interceptor halted the chain | Ensure `invocation.proceed()` is called unless intentionally replacing the result |
| `ClassFilter` relies on proxy name | Proxy names vary by runtime/framework | Match on target class/interface/appropriate annotation |
| Performance degrades under high call volume | Dynamic matcher inspects args on every invocation | Prefer static; benchmark hot paths |
| `final`, `private`, or self-invocation is not intercepted | Spring AOP proxy limitations | Design bean entry points rather than relying on internal calls |
| Union combination over-matches | Combining conditions at the wrong level | Use `ComposablePointcut`, test each branch and the intersection |

**Verify before going to production:** one positive match test, one non-matching method test, one non-matching class test, one test varying args so the dynamic result changes, and one test calling through the Spring proxy. If the advisor enforces security or transactions, also test rejection cases and ordering relative to other advisors.

## 11. Advanced Practice Exercises

Starting from the program in Section 5:

1. Change `SubmitPointcut` to select both `submit` and `status`; predict the event list when calling `status`. Then revert it and run the tests.
2. Add `OrderService.cancel(String sku)` and a separate matcher; use `ComposablePointcut.union(...)` to attach the same trace interceptor to both `submit` and `cancel`. Ensure `OtherService.submit` remains unintercepted.
3. Change the bulk condition to `quantity >= 20` and test values 19/20, including the boundary. Verify `isRuntime() == true`.
4. Create a pointcut that selects only methods annotated with a custom annotation. Compare a reflection-based Java matcher implementation with `AspectJExpressionPointcut` in Spring, and test annotations on interfaces vs. implementations.
5. Measure invocation times in an isolated test environment with and without a dynamic matcher, avoiding logging I/O inside the benchmark. Base conclusions on real measurements rather than guesses.

You should be able to explain why **`Pointcut = ClassFilter + MethodMatcher`**, why a dynamic matcher only runs after the static step, how Spring wires a Pointcut into an Advisor, and the limitations when calls do not pass through a proxy.

### Spring References

- Spring Framework – Pointcut API: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Spring Framework 6.2 – `Pointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/Pointcut.html
- `StaticMethodMatcherPointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html
- `DynamicMethodMatcherPointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/DynamicMethodMatcherPointcut.html
- `ComposablePointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/ComposablePointcut.html
- Spring proxy & self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html