# Class-Level and Method-Level Filtering with the Spring Pointcut API

## 1. Lesson Objectives

In Spring AOP, not every call on a bean should run advice. For example: log only `charge(String)` operations on payment services, do not log `status()` on the same service, and do not log a method named `charge` belonging to a shipping service.

The **Spring Pointcut API** solves this requirement using two independent filters:

1. `ClassFilter`: determines **which target classes** fall within the pointcut's scope.
2. `MethodMatcher`: determines **which methods on those target classes** fall within the pointcut's scope.

Both filters combine into an `org.springframework.aop.Pointcut`. Advice is applied to a method execution through a Spring proxy when **both the class-level condition and the method-level condition are satisfied**; if the matcher is dynamic, argument values must also be checked on each invocation.

After this lesson, you will be able to read the Java interfaces of the Spring Pointcut API, implement static pointcuts for both classes and methods, connect a pointcut to advice via an advisor, distinguish static from dynamic matchers, and troubleshoot cases where advice does not run despite seemingly matching conditions.

The scope focuses on **Spring AOP proxies and the Pointcut API**. It does not delve into general aspect theory or AspectJ weaving.

## 2. Combining Two Filter Levels to Accurately Model Business Scope

An `org.springframework.aop.Pointcut` consists of `getClassFilter()` (selecting the target class) and `getMethodMatcher()` (selecting methods on that class). The corresponding interfaces provide the checks `ClassFilter.matches(Class<?>)` and `MethodMatcher.matches(Method, Class<?>)`. Only when the static filters match and the matcher reports `isRuntime() == true` does Spring also need to check `matches(Method, Class<?>, Object... args)` for the actual invocation. This is the matching structure of the Spring Pointcut API, not a direct call to the target.

Applying this to the lesson's payment example:

| Target class | Method | ClassFilter selects only BillingService | MethodMatcher selects charge(String) | Advice? |
| --- | --- | --- | --- | --- |
| `BillingService` | `charge(String)` | Yes | Yes | Yes, when caller goes through proxy |
| `BillingService` | `status()` | Yes | No | No |
| `ShippingService` | `charge(String)` | No | Yes by signature | No, excluded at class level |

The evaluation formula is `classMatch && staticMethodMatch && (!isRuntime || runtimeArgsMatch)`. Static results can be cached by Spring; dynamic results depend only on a single invocation. If an advisor does not match, the business method still proceeds normally unless another interceptor alters the flow. The following sections implement each filter level and verify these exact three table rows using `ProxyFactory`.

## 3. Class-Level Filtering: `ClassFilter`

The `matches(Class<?> clazz)` method receives the **target type** that Spring is evaluating. It returns `true` if the target class belongs to the set of classes requiring advice.

Example accepting only `BillingService` and its subclasses:

~~~java
ClassFilter billingOnly =
        clazz -> BillingService.class.isAssignableFrom(clazz);
~~~

This snippet assumes the `BillingService` class has already been declared. The meaning of `isAssignableFrom` is that the target can be used as a `BillingService`, thus accepting both the class itself and subclasses. Comparing `clazz == BillingService.class` matches only that exact class; consider your application's policy carefully.

Another example, selecting via a marker interface:

~~~java
ClassFilter auditedServices =
        clazz -> AuditedOperations.class.isAssignableFrom(clazz);
~~~

Assuming the application defines the `AuditedOperations` interface. This is often a better choice when different implementations belong to the same business domain, as it avoids forcing all of them to inherit from a single superclass.

**Important note:** A class filter is not used to inspect method names, parameter values, or return values. Once a class satisfies `ClassFilter`, `MethodMatcher` handles selecting specific methods. Do not rely carelessly on package-name strings: packages containing Spring-generated proxy classes, subclasses, and implementation classes can lead to false assumptions. Inspect the **target class** rather than inferring from the proxy class name observed at the caller.

### Default ClassFilter

Some convenience pointcuts allow setting a custom `ClassFilter`; when unrestricted, the default filter may be `ClassFilter.TRUE` (matching every target class). That does not mean every method matches, because `MethodMatcher` still retains the right to reject.

## 4. Method-Level Filtering: `MethodMatcher`

### 4.1. Static Filtering by Method Signature

`matches(Method method, Class<?> targetClass)` has enough information to inspect:

- Method name: `method.getName()`.
- Parameter types and count: `method.getParameterTypes()`, `method.getParameterCount()`.
- Return type: `method.getReturnType()`.
- Modifiers: `Modifier.isPublic(method.getModifiers())`, etc.
- Annotations/metadata that the implementation actively looks up on the method and target class.

Example requiring the exact method name `charge` with one `String` argument:

~~~java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().equals("charge")
            && method.getParameterCount() == 1
            && method.getParameterTypes()[0] == String.class;
}
~~~

This is the body when overriding `StaticMethodMatcherPointcut.matches`, not a standalone file. The `Method` object during method matching does not always match how the caller views the method through an interface; if you need implementation annotations or bridge/generic handling, you can look up the most-specific method via `AopUtils.getMostSpecificMethod(...)`.

### 4.2. Static Means Independent of Argument Values

The calls `charge("NORMAL-1")` and `charge("VIP-1")` have the **same name and signature**, so the static matcher above does not distinguish them. The advantage is that Spring can cache the matching result instead of recomputing it on every call.

With `StaticMethodMatcherPointcut`, `isRuntime()` is `false`. Spring will not invoke `matches(method, targetClass, args)` for every invocation. This is the default choice when filtering criteria rely solely on class and method metadata.

### 4.3. Dynamic Means Inspecting Arguments at Invocation Time

If you only want advice for `charge` when the code starts with `VIP-`, you must add a runtime check on `args`. Spring provides `DynamicMethodMatcherPointcut`; with it, `isRuntime()` is `true`.

~~~java
// Example of a custom pointcut class; corresponding Spring/Java types must be imported.
class VipChargePointcut extends DynamicMethodMatcherPointcut {

    @Override
    public ClassFilter getClassFilter() {
        return clazz -> BillingService.class.isAssignableFrom(clazz);
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass) {
        return method.getName().equals("charge")
                && method.getParameterCount() == 1
                && method.getParameterTypes()[0] == String.class;
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass, Object... args) {
        return args.length == 1
                && args[0] instanceof String id
                && id.startsWith("VIP-");
    }
}
~~~

The class above is an **illustrative variant** placed alongside the full example in Section 5. To use it, you must import `org.springframework.aop.ClassFilter`, `org.springframework.aop.support.DynamicMethodMatcherPointcut`, and `java.lang.reflect.Method`, and have `BillingService` available.

Important point: Spring only calls the dynamic matcher after the class-level and method-signature matching results allow it. A runtime matcher incurs overhead on every invocation that passes the static condition. Use it only when argument values are genuinely part of the advice selection policy.

## 5. Runnable Example: Combining Both Filter Levels with `ProxyFactory`

The example uses **Java 17** and **Spring Framework 6.1.x** (via Spring Boot 3.3.0 dependency management) to run Spring AOP as a plain Java program. It needs no HTTP server, no `@Aspect` annotations, and no Spring Boot startup. We create proxies directly via `ProxyFactory` to clearly see the relationship between Pointcut, Advisor, and Advice.

### 5.1. Structure

~~~text
pom.xml
src/main/java/com/example/pointcut/Demo.java
~~~

### 5.2. Maven Dependencies

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-pointcut-filters</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot parent is used here to manage dependency versions; there is no `@SpringBootApplication`. `spring-boot-starter-aop` brings Spring AOP and its related libraries onto the classpath. Proxies are created directly by `ProxyFactory`.

### 5.3. Complete Java Code

File `src/main/java/com/example/pointcut/Demo.java`:

~~~java
package com.example.pointcut;

import java.lang.reflect.Method;

import org.springframework.aop.MethodBeforeAdvice;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class Demo {

    public static class BillingService {
        public String charge(String code) {
            System.out.println("target:billing-charge:" + code);
            return "charged:" + code;
        }

        public String status() {
            System.out.println("target:billing-status");
            return "ready";
        }
    }

    public static class ShippingService {
        public String charge(String code) {
            System.out.println("target:shipping-charge:" + code);
            return "shipped:" + code;
        }
    }

    // Pointcut with both ClassFilter and MethodMatcher.
    public static class BillingChargePointcut
            extends StaticMethodMatcherPointcut {

        public BillingChargePointcut() {
            setClassFilter(clazz ->
                    BillingService.class.isAssignableFrom(clazz));
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("charge")
                    && method.getParameterCount() == 1
                    && method.getParameterTypes()[0] == String.class;
        }
    }

    public static void main(String[] args) {
        var pointcut = new BillingChargePointcut();

        MethodBeforeAdvice advice = (method, arguments, target) -> {
            System.out.println(
                    "advice:" + target.getClass().getSimpleName()
                    + "." + method.getName()
                    + "(" + arguments[0] + ")");
        };

        var advisor = new DefaultPointcutAdvisor(pointcut, advice);

        ProxyFactory billingFactory = new ProxyFactory(new BillingService());
        billingFactory.setProxyTargetClass(true);
        billingFactory.addAdvisor(advisor);
        BillingService billing =
                (BillingService) billingFactory.getProxy();

        ProxyFactory shippingFactory = new ProxyFactory(new ShippingService());
        shippingFactory.setProxyTargetClass(true);
        shippingFactory.addAdvisor(advisor);
        ShippingService shipping =
                (ShippingService) shippingFactory.getProxy();

        System.out.println("== Billing charge ==");
        System.out.println("result=" + billing.charge("B-1"));

        System.out.println("== Billing status ==");
        System.out.println("result=" + billing.status());

        System.out.println("== Shipping charge ==");
        System.out.println("result=" + shipping.charge("S-1"));
    }
}
~~~

In this code:

1. `BillingChargePointcut` extends `StaticMethodMatcherPointcut`. This Spring utility acts as both `Pointcut` and `MethodMatcher`, so we only override `matches(Method, Class)`.
2. The constructor calls `setClassFilter` to select targets belonging to `BillingService`. `ShippingService` is excluded at the class filtering step, even though it has a `charge(String)` method with the same signature.
3. `matches` selects only `charge(String)`. `BillingService`'s `status()` method passes the class filter but is excluded by the method filter.
4. `DefaultPointcutAdvisor(pointcut, advice)` pairs the **selection condition** with the **execution behavior**. This is the core wiring of the low-level Spring AOP API.
5. `MethodBeforeAdvice` logs before the target method runs. It does not select methods itself; the advisor determines where it applies.
6. Each `ProxyFactory` takes a real target, adds the same advisor, and creates a class-based proxy. `setProxyTargetClass(true)` allows obtaining the proxy as the concrete service type in the demo.

The service methods are `public`, non-`final`, and the classes can be subclassed. These are convenient conditions for class-based proxies.

### 5.4. Running

From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.pointcut.Demo
~~~

Excluding Maven or environment logs, the output produced by the program is:

~~~text
== Billing charge ==
advice:BillingService.charge(B-1)
target:billing-charge:B-1
result=charged:B-1
== Billing status ==
target:billing-status
result=ready
== Shipping charge ==
target:shipping-charge:S-1
result=shipped:S-1
~~~

**Why is there only one `advice:` line?**

| Call | ClassFilter | MethodMatcher | Advice? |
| --- | --- | --- | --- |
| `billing.charge("B-1")` | PASS: `BillingService` | PASS: `charge(String)` | Yes |
| `billing.status()` | PASS: `BillingService` | FAIL: name `status` | No |
| `shipping.charge("S-1")` | FAIL: `ShippingService` | Method level does not need to be selected | No |

All three calls still execute their business logic. A pointcut decides **where advice applies**, not whether to block method access. If execution needs to be forbidden in certain cases, there must be an advice and a clearly designed security policy.

## 6. Testing Each Filter Individually Before Creating Proxies

An advantage of the Pointcut API is that you can test matching results in Java without running the entire system. Using the `pointcut` created in Section 5:

~~~java
boolean billingClass =
        pointcut.getClassFilter().matches(BillingService.class);

boolean shippingClass =
        pointcut.getClassFilter().matches(ShippingService.class);

Method charge =
        BillingService.class.getMethod("charge", String.class);
Method status =
        BillingService.class.getMethod("status");

boolean chargeMethod =
        pointcut.getMethodMatcher().matches(charge, BillingService.class);
boolean statusMethod =
        pointcut.getMethodMatcher().matches(status, BillingService.class);

System.out.println(billingClass);
System.out.println(shippingClass);
System.out.println(chargeMethod);
System.out.println(statusMethod);
~~~

This is an **additional check snippet** to place inside `main`; it assumes the `pointcut` variable and nested service classes are already defined, and `main` must declare `throws NoSuchMethodException` or handle the exception from `getMethod`. When inserted properly into the example, the four corresponding lines are:

~~~text
true
false
true
false
~~~

Note: calling `MethodMatcher.matches` directly on a method of a class that does not match `ClassFilter` may still return `true`, because a method matcher alone does not necessarily check the class filter. To predict whether an advisor applies, you must check **both conditions**, not just query the method matcher alone.

### Why Not Use `getClass()` on the Proxy?

In the example, `billing.getClass()` is a Spring-generated proxy subclass, not the plain `BillingService.class`. The `ClassFilter` API is designed for the **target class** evaluated by Spring; in direct unit tests, use the known target class. For an existing bean in a Spring context, you can use `AopUtils.getTargetClass(bean)` to look up the target class via Spring's mechanism. Do not write class filters based on dynamically generated proxy class names like `BillingService$$SpringCGLIB$$...`.

## 7. Choosing a Pointcut API Implementation

Spring provides helper classes to avoid manually implementing both `Pointcut` and `MethodMatcher`:

| Need | Suitable Spring Type | Characteristics |
| --- | --- | --- |
| Select by class + method metadata | `StaticMethodMatcherPointcut` | `setClassFilter` and override `matches(Method, Class)`; `isRuntime=false` |
| Select methods by name or simple name pattern | `NameMatchMethodPointcut` | Static matcher by method name; class filter can be added |
| Select methods by regular expression | `JdkRegexpMethodPointcut` | Static matcher by regex; restrict by target class when needed |
| Select by AspectJ expression | `AspectJExpressionPointcut` | Uses expressions in Spring AOP proxies, e.g. `execution(...)`, `within(...)` |
| Need to inspect arguments on each call | `DynamicMethodMatcherPointcut` | Adds `matches(method, targetClass, args)` at runtime |
| Combine multiple pointcuts | `ComposablePointcut` or `Pointcuts` | Union/intersection of existing conditions |

A short example when you only want to match a method named `charge`:

~~~java
var nameMatch = new NameMatchMethodPointcut();
nameMatch.setMappedName("charge");
nameMatch.setClassFilter(clazz ->
        BillingService.class.isAssignableFrom(clazz));
~~~

This snippet requires importing `org.springframework.aop.support.NameMatchMethodPointcut`. `NameMatchMethodPointcut` provides a name-based matcher configurable with simple names/patterns, so there is no need to write a manual `MethodMatcher` for this case. However, if you need to distinguish overloads `charge(String)` and `charge(BigDecimal)`, a name-only matcher is insufficient; you must add signature checks.

### Combining Conditions with AND/OR

Suppose you have two pointcuts `P1` and `P2`:

- **Intersection**: both `P1` and `P2` must match.
- **Union**: at least one of `P1` or `P2` matches.

The utilities `org.springframework.aop.support.Pointcuts` and `ComposablePointcut` support composition. Avoid confusing the **intersection of two pointcuts** with simply adding another method condition to one pointcut while losing its class filter. When combining different advisors, multiple advices may run if each advisor matches.

In most Spring applications, expressing scope with `AspectJExpressionPointcut` or `@Pointcut` can be clearer. The Pointcut API is useful when **filtering conditions are built programmatically in Java, need reuse, or require custom advisor integration**.

## 8. Class and Method Matching in a DI-Based Spring Application

The `ProxyFactory` example creates proxies directly to make the mechanism clear. In real Spring Boot/Spring Framework applications, beans can be proxied automatically by advisors and auto-proxy creators. When using Spring DI:

- The pointcut/advisor must be registered and wired into the proxy creation process according to the application's Spring AOP configuration.
- Callers must obtain the **Spring-managed proxy**, not instantiate `new` targets themselves and expect advice to run.
- With JDK dynamic proxies, callers typically invoke public methods through a proxied interface. With class-based proxies, `final` classes/methods and `private` methods are not intercepted in the same way as public methods.
- Self-invocation `this.charge(...)` inside the target does not go through the proxy, so even if the class/method satisfies the filters, internal calls will not trigger advice.

**Satisfying matching conditions does not guarantee interception:** `ClassFilter=true` and `MethodMatcher=true` only prove the method is within the pointcut's scope; there must also be an advisor on the proxy and the call must actually go through that proxy.

### How Do Annotation and Expression Configurations Relate?

In Spring AOP, an expression like `execution(* com.example.billing..*(..))` can perform something similar to class/package filtering + signature-based method filtering; `within(com.example.billing..*)` focuses on declaring types. However, pointcut expressions must be translated into matchers by Spring, and not every AspectJ join point is supported by Spring proxy AOP. This lesson emphasizes the **core Java API** (`Pointcut`, `ClassFilter`, `MethodMatcher`) rather than replacing XML or `@Aspect` mechanisms with arbitrary interpretations.

## 9. Common Mistakes

### 9.1. Class Filter Uses Exact Equality When Subclasses Exist

~~~java
clazz -> clazz == BillingService.class
~~~

This condition does not match a subclass of `BillingService` when that subclass is the target class. If you want to accept subclasses, use `BillingService.class.isAssignableFrom(clazz)`. If a security or business policy permits only one exact type, exact equality may still be valid; decide based on the intended scope.

### 9.2. Method Filter Checks Only the Name, Accidentally Matching Multiple Overloads

~~~java
method.getName().equals("charge")
~~~

This can match `charge(String)`, `charge(int)`, and `charge(BigDecimal)` if all are intercepted by the proxy. When an exact signature is needed, compare `getParameterTypes()`, `getReturnType()`, or other relevant attributes.

### 9.3. Confusing a Method Matcher with Per-Call Inspection

A static matcher cannot inspect `args[0] == "VIP-1"` on individual invocations. `isRuntime=false` means Spring will not invoke the `matches(..., args)` variant. To select by argument values, use a dynamic matcher or conditional logic in advice, while accounting for overhead.

### 9.4. Checking Annotations on the Wrong Method

Methods can be viewed through an interface when using a JDK proxy. Annotations placed on an implementation method are not necessarily found by calling `method.getAnnotation(...)` on the interface method. If your problem requires annotations on the implementation, use `AopUtils.getMostSpecificMethod(method, targetClass)` and define a clear metadata policy. Do not assume Java inherits method annotations from interfaces.

### 9.5. Proxies, Self-Invocation, and Final Methods

If a method receives no advice despite the matcher returning `true`, check whether the caller holds the proxy or the raw target, whether the class/method is `final`, and whether the call comes from another bean through the proxy. Do not try to solve self-invocation by widening `ClassFilter`, because a filter does not create an extra pass through the proxy.

### 9.6. Making Matchers Slow or Side-Effectful

Static matchers should rely on stable metadata. Do not query a database, make HTTP calls, or mutate state inside `matches`. Spring may call matchers during proxy construction and caching, so conditions depending on per-call mutable state are unsafe in a static matcher. Dynamic matchers must be lightweight since they run frequently; if complex business data inspection is needed, consider a different design.

### 9.7. Too Broad at the Class Level, Too Narrow at the Method Level

For example, `ClassFilter.TRUE` combined with a `MethodMatcher` that only checks the name `charge` can apply advice to every bean with a method of that name, including unrelated services. Conversely, restricting to a single concrete class when the application uses multiple interface implementations can miss beans that need advice. Treat the class filter as the architectural/domain boundary and the method matcher as the operation selector.

## 10. Testing Checklist

For a custom pointcut in Spring:

1. **Class scope:** test included classes and excluded classes; if inheritance is involved, test subclasses or interface implementations too.
2. **Method scope:** test matching methods, differently named methods, overloads with different signatures, and methods that cannot be proxy-intercepted.
3. **Static/dynamic:** confirm `isRuntime()` matches your intent; if dynamic, test multiple argument values; avoid using static matchers for per-call varying requirements.
4. **Proxy:** call through the Spring proxy and verify advice runs the expected number of times; also verify self-invocation is skipped.
5. **Advisor:** ensure the pointcut is paired with advice on an actual proxy; a standalone class/method match is not enough.
6. **Behavior:** methods excluded from advice still execute their business logic properly; matched methods still return values or throw exceptions according to the advice contract.
7. **Cost:** keep filters cheap, deterministic, and reasonably scoped when the application has many beans or high call frequency.

## 11. Key Takeaways

**A Spring `Pointcut` splits the advice applicability decision into `ClassFilter` and `MethodMatcher`.** The class filter determines which target objects may be intercepted; the method matcher determines which operations qualify. With a static matcher, decisions rely on class/method metadata and can be cached. With a dynamic matcher, Spring also inspects argument values at call time. Even when both filters match, advice runs only if the advisor is installed on a Spring proxy and the caller invokes through the proxy.

Official documentation:

- [Spring Framework Reference — Pointcut API in Spring](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework API — Pointcut](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aop/Pointcut.html)
- [Spring Framework API — MethodMatcher](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aop/MethodMatcher.html)