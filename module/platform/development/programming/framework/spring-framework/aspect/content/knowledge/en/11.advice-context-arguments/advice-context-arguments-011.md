# Reading Annotations on the Right Method When the Target Is a Proxy in Spring AOP

## 1. Problem to solve

When writing advice in Spring AOP, we often want to read annotations on the **actual business method being called** to determine audit level, metric labels, validation policies, or logging behavior.

Example:

```java
public interface BillingOperations {
    String pay(String id);
}

public class BillingService implements BillingOperations {
    @TrackOperation("payment")
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

In Spring Framework, the caller may receive a **JDK dynamic proxy** implementing only `BillingOperations`, or a **CGLIB class-based proxy** subclassing `BillingService`. If an advice writes:

```java
Method method = ((MethodSignature) joinPoint.getSignature()).getMethod();
TrackOperation annotation = method.getAnnotation(TrackOperation.class);
```

then `annotation` **can be `null` even though the annotation genuinely exists on `BillingService.pay()`**: `method` can reflect the method declared on the **interface** when using a JDK proxy, while the annotation sits only on the **implementation**.

This is not a Java annotation bug, nor does it automatically prove the Spring pointcut is wrong. It is the difference between the **method representations** visible during a Spring proxy AOP call.

**Foundational handling in Spring:**

1. Get the `Method` from `MethodSignature`.
2. Determine the **actual target class** of the Spring bean.
3. Use `AopUtils.getMostSpecificMethod(method, targetClass)` to locate the concrete method on the implementation (and resolve bridge methods per the Spring API).
4. Use `AnnotatedElementUtils.findMergedAnnotation(...)` when you need support for **meta-annotations, composed annotations, and merged annotation attributes**.
5. If the annotation is still not found, review **whether the annotation sits on the interface or implementation, annotation placement, pointcut scope, proxy strategy, and Spring version**.

Example:

```java
Method declared = ((MethodSignature) joinPoint.getSignature()).getMethod();
Class<?> targetType = AopUtils.getTargetClass(joinPoint.getTarget());
Method specific = AopUtils.getMostSpecificMethod(declared, targetType);
TrackOperation operation =
        AnnotatedElementUtils.findMergedAnnotation(specific, TrackOperation.class);
```

This is a **fragment inside Spring advice**, requiring `joinPoint` as `JoinPoint`/`ProceedingJoinPoint`, imports, and the application-defined `TrackOperation` annotation. Section 8 provides a complete project.

**Lesson scope:** focuses on determining the **right method annotation in a Spring Aspect on Spring-managed beans invoked through a Spring AOP proxy**. General AspectJ/weaving topics are not the focus.

## 2. Three entities very easy to conflate

When Spring AOP executes advice, distinguish:

| Component | API / example | Meaning |
| --- | --- | --- |
| **Proxy** | `joinPoint.getThis()` | The Spring AOP proxy reference the caller passes through. May be a JDK proxy or CGLIB subclass. |
| **Target** | `joinPoint.getTarget()` | The business object the proxy delegates to. |
| **Method of join point signature** | `((MethodSignature) jp.getSignature()).getMethod()` | `java.lang.reflect.Method` describing the method reported to advice; may be an **interface method**. |
| **Specific method on target class** | `AopUtils.getMostSpecificMethod(method, targetClass)` | Suitable implementing method for inspecting implementation annotations. |
| **Annotation on specific method** | `AnnotatedElementUtils.findMergedAnnotation(specific, TrackOperation.class)` | Metadata, potentially including composed/meta-annotations per Spring lookup rules. |

What to remember:

```text
Caller
  |
  v
Spring AOP proxy                  <-- getThis()
  |
  | JoinPoint / MethodSignature
  | may describe BillingOperations.pay(...)
  v
BillingService target             <-- getTarget()
  |
  v
BillingService.pay(...)           <-- most specific method
  |
  +-- @TrackOperation("payment")  <-- annotation placed on implementation
```

With a JDK proxy, the runtime class of `getThis()` is a generated proxy class, not `BillingService`. If you call `getThis().getClass().getDeclaredMethod(...)` to find business annotations, you are usually **reading the wrong proxy infrastructure class**.

With a CGLIB proxy, `getThis().getClass()` is a generated subclass. That class is also **not a stable anchor** for reading annotations; method annotations are not guaranteed to be copied verbatim onto all generated proxy overrides.

## 3. Why is `MethodSignature.getMethod()` not always the implementation method?

### 3.1. JDK interface proxy

When Spring creates a JDK dynamic proxy for a target implementing `BillingOperations`, the proxy's public API consists of the interfaces it exposes. Calling `proxy.pay("P-1")` goes through a method invocation based on the interface contract.

Inside advice:

```java
Method signatureMethod =
    ((MethodSignature) jp.getSignature()).getMethod();
```

`signatureMethod.getDeclaringClass()` **can be `BillingOperations.class`**. If `@TrackOperation` is placed only on `BillingService.pay(String)`, then:

```java
signatureMethod.getAnnotation(TrackOperation.class)
```

can return `null`.

**Do not conclude the implementation lacks the annotation just because the interface `Method` does not have it.** Method annotations on an implementation do not "propagate upward" to the same-signature method in a Java interface.

### 3.2. CGLIB class proxy

When Spring creates a subclass proxy, the intercepted method may reflect the target class more closely, yet you still should not tie logic to "CGLIB always returns a fixed kind of `Method`". Advisors, bridge methods, generic types, and proxy implementations can affect representation in specific cases.

The unified solution for **both JDK and CGLIB** is normalizing to the target method via Spring APIs rather than branching manually:

```java
Method specific = AopUtils.getMostSpecificMethod(
    ((MethodSignature) jp.getSignature()).getMethod(),
    AopUtils.getTargetClass(jp.getTarget())
);
```

If the target cannot implement that signature or uses a custom `TargetSource`, Spring may return the original method; verify if the application uses complex proxies.

### 3.3. Distinguishing method name from `Method` object

`jp.getSignature().getName()` returns the method name such as `"pay"`, which is **insufficient** to find the exact annotation on overloads.

For example, if a class has:

```java
String pay(String id)
String pay(String id, String channel)
```

Knowing only the name `"pay"` does not identify which overload executed. `MethodSignature.getMethod()` carries the **parameter types**, and `AopUtils.getMostSpecificMethod` uses that signature information to match the right method on the target class.

Do not manually write:

```java
target.getClass().getMethod(jp.getSignature().getName());
```

because that looks up a **zero-argument** method, easily throwing `NoSuchMethodException` or selecting the wrong overload when the target has overloads. Spring's API avoids mistakes that manual reflection logic routinely makes.

## 4. Normalizing the method with `AopUtils.getMostSpecificMethod`

Spring Framework provides the API:

```java
public static Method getMostSpecificMethod(
        Method method, Class<?> targetClass);
```

The signature above is an **API description**, not a standalone program. `method` can be a method declared on an interface; `targetClass` is the actual target class type.

Example:

```java
Method interfaceMethod =
        BillingOperations.class.getMethod("pay", String.class);

Method actual = AopUtils.getMostSpecificMethod(
        interfaceMethod, BillingService.class
);
```

When `BillingService` implements the interface as in the example, `actual` represents **`BillingService.pay(String)`**.

### 4.1. Why not simply use `target.getClass().getMethod(...)`?

Hand-rolled reflection would also have to handle:

- Method **overloading**: must know exact parameter types.
- Class hierarchy: the method may be inherited from a superclass.
- Generic bridge methods: the compiler may generate a bridge method with an erased signature.
- Annotations placed on the implementation, interface, or supertype method.
- Generated proxy classes: never treat `proxy.getClass()` as a source of domain metadata.
- Method visibility and accessibility.

`AopUtils.getMostSpecificMethod` combines Spring's logic to find the matching implementation method; **the Spring 6.1.14 Javadoc confirms this API resolves bridge methods** to read attributes from the original method definition.

You can write:

```java
Method specific =
        AopUtils.getMostSpecificMethod(signatureMethod, targetClass);
```

instead of scanning `getDeclaredMethods()` and comparing name strings yourself.

### 4.2. Bridge methods with generics

Illustrative generics example:

```java
interface Handler<T> {
    void handle(T value);
}

class StringHandler implements Handler<String> {
    @TrackOperation("handle-string")
    public void handle(String value) {
        // ...
    }
}
```

The compiler may generate a **bridge method** to preserve polymorphism under Java type erasure. If reflection grabs the bridge method, an annotation attached to the source method `handle(String)` may not be observed as expected when calling only `getDeclaredAnnotation` on the bridge.

In Spring AOP, `AopUtils.getMostSpecificMethod` is the right starting point to select the target method **and resolve bridge methods**. When working outside AOP, `org.springframework.core.BridgeMethodResolver` can be used as needed, without adding redundant layers of manual resolution.

Do not assume every Java compiler/version generates and copies method annotations onto bridge methods the same way. Verify with Spring APIs and integration tests.

## 5. Reading annotations: `getAnnotation`, `findMergedAnnotation`, or `@annotation`?

There are at least three distinct needs:

### 5.1. Reading only annotations attached directly to that exact method

```java
TrackOperation direct =
        specificMethod.getDeclaredAnnotation(TrackOperation.class);
```

Appropriate when policy **intentionally recognizes only annotations placed directly** on the implementation method. It does not discover meta-annotations and does not "merge" attributes from composed annotations.

`specificMethod.getAnnotation(TrackOperation.class)` has a similar goal on the selected method using the `AnnotatedElement` API; do not expect it to discover interface annotations or composed annotations automatically.

### 5.2. Needing Spring annotation semantics, including meta-annotations

```java
TrackOperation marker = AnnotatedElementUtils.findMergedAnnotation(
        specificMethod,
        TrackOperation.class
);
```

Spring's `AnnotatedElementUtils.findMergedAnnotation` can search an **annotation hierarchy** and synthesize metadata from composed annotations, supporting `@AliasFor` per Spring rules.

When an application uses:

```java
@TrackOperation("critical")
public @interface CriticalOperation {}
```

and the method is marked:

```java
@CriticalOperation
public void cancel(String id) { /* ... */ }
```

then **direct** `getDeclaredAnnotation(TrackOperation.class)` on the method can return `null`, whereas **merged** annotation search can find `TrackOperation("critical")` via the `@CriticalOperation` meta-annotation. These fragments require annotation types with `@Retention(RUNTIME)` and appropriate `@Target`; the complete example defines them fully.

When reading aliased/overridden attributes in composed annotations, use `AnnotatedElementUtils` or `MergedAnnotations` instead of manually looping `getAnnotations()` and traversing the annotation tree.

### 5.3. If the goal is simply selecting annotated methods, bind directly in the pointcut

Spring `@AspectJ` supports:

```java
@Before(
    value = "execution(public * com.example..service.*.*(..))"
          + " && @annotation(audited)",
    argNames = "audited"
)
public void audit(TrackOperation audited) {
    System.out.println(audited.value());
}
```

This is a **fragment** using Spring's annotation-binding syntax. If you only need `TrackOperation` to filter the **advised join point** and read the corresponding annotation value, `@annotation(audited)` is often simpler than manual reflection.

However, **do not treat `@annotation` as always identical to `findMergedAnnotation` across all composed annotations, interface annotations, and proxy strategies**. They are two mechanisms with distinct matching/binding rules. When interfaces/implementations differ, generic bridges exist, or composed annotations are used, write tests on your actual Spring version.

If advice already runs via `execution(...)` yet needs to **check annotations under a custom fallback policy**, the `getMostSpecificMethod` + `findMergedAnnotation` pipeline offers clearer control over metadata lookup.

## 6. Obtaining the target class properly

Inside advice, two important references are:

```java
Object proxy = jp.getThis();
Object target = jp.getTarget();
```

For Spring AOP:

- `getThis()`: the Spring proxy.
- `getTarget()`: the target currently being advised.

When reading annotations of the **implementation method**, prioritize the target class:

```java
Class<?> targetClass = AopUtils.getTargetClass(jp.getTarget());
```

For a normal target object, this identifies the business class. Calling `jp.getThis().getClass()` can return a generated JDK/CGLIB proxy class and fail to find the needed method annotation.

### 6.1. How to identify the proxy

```java
Object bean = context.getBean("billingOperations");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

This is a **diagnostic fragment**, requiring the `context` variable. Checking proxy style does not replace locating the target method, but it helps explain why the same advice may observe different method representations across configurations.

### 6.2. Nested proxies and scoped targets

If the application uses scoped proxies, custom `TargetSource`, multiple proxy layers, or transaction/security advisors, `getTarget()` and `getTargetClass` may need to be interpreted for the **actual target layer being advised**. Spring also provides `AopProxyUtils.ultimateTargetClass(...)` for certain scenarios, though some unwrapping approaches can trigger target creation or behave improperly with scoped/non-singleton targets.

**Do not automatically unwrap every proxy down to the raw object just to read annotations.** Prefer class-metadata APIs, use Spring proxy utilities aware of target sources, and test against your system's real `ApplicationContext` and scopes.

## 7. Method annotations placed on interface, implementation, or superclass

A service may declare policies in multiple places:

```java
public interface BillingOperations {
    @TrackOperation("interface-policy")
    String pay(String id);
}

public class BillingService implements BillingOperations {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

These are **illustrative fragments**, not a complete project. When a method annotation is placed only on the interface:

- `BillingService.class.getMethod(...).getDeclaredAnnotation(...)` on the implementation method can return `null`.
- `BillingOperations.class.getMethod(...).getAnnotation(...)` can see the annotation.
- Spring merged annotation search with **find semantics** can locate metadata across the method hierarchy, including matching interface methods per the Spring API and version.
- If a codebase needs to **prefer the implementation annotation and fall back to the interface annotation**, document that policy clearly and test the exact precedence.

An intentional fallback pattern:

```java
Method signatureMethod =
        ((MethodSignature) jp.getSignature()).getMethod();

Method implementationMethod =
        AopUtils.getMostSpecificMethod(
                signatureMethod,
                AopUtils.getTargetClass(jp.getTarget())
        );

TrackOperation metadata = AnnotatedElementUtils.findMergedAnnotation(
        implementationMethod, TrackOperation.class
);

if (metadata == null && !implementationMethod.equals(signatureMethod)) {
    metadata = AnnotatedElementUtils.findMergedAnnotation(
            signatureMethod, TrackOperation.class
    );
}
```

This is a **fragment placed inside advice** and should not be copied verbatim when conflicting annotations exist on implementation and interface without defined precedence. `findMergedAnnotation` already performs hierarchy searches in many situations; the fallback illustrates **not forgetting the original interface `Method`**, rather than claiming the Spring API always requires two lookups.

### 7.1. `@Inherited` is not a solution for method annotations

Java's `@Inherited` affects annotation lookup only on **class inheritance** per Java's contract, **and does not make method annotations automatically inherited across overrides**. Do not add `@Inherited` to a method-level annotation expecting `Method.getAnnotation` to automatically merge annotations from an interface method.

If you need inheritance policies across a method hierarchy, use an appropriate Spring API such as `AnnotatedElementUtils.findMergedAnnotation`, while explicitly defining and testing precedence between interface, superclass, and implementation.

### 7.2. Composed annotations and `@AliasFor`

Advanced example:

```java
@TrackOperation("default")
public @interface BusinessOperation {
    // @AliasFor can be used to override TrackOperation attributes.
}
```

This is a **conceptual fragment**; overriding requires full `@AliasFor(annotation=..., attribute=...)`, retention, and target declarations. Do not assume attributes with the same name merge automatically as desired: Spring meta-annotation aliasing has strict rules and can fail on inconsistent configurations.

If you only need a fixed label for a composed annotation, `@TrackOperation("critical")` on the second annotation type suffices for the runnable example.

## 8. Complete Java 17+ example: JDK proxy, CGLIB, and annotations on implementation

Goals of the example:

1. Declare the `BillingOperations` interface **with no method annotations**.
2. Have `BillingService` implement the interface, placing **`@TrackOperation("payment")` directly on `pay`**.
3. Place **`@CriticalOperation`** (meta-annotated with `@TrackOperation("critical")`) on `cancel`.
4. Leave `ping` unannotated.
5. Use **one `@Around` Spring advice** selecting method executions of target `BillingOperations`, then resolve the most-specific method and merged annotation.
6. Run the same project in **two independent `ApplicationContext`s**: JDK proxy and CGLIB proxy. Verify the implementation annotations in both.
7. Directly compare the `Method` obtained from the interface with the most-specific implementation `Method` **without relying on generated proxy class names**.

Pinned environment: **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, Maven**. This is an illustrative version set, **not a claim of the latest versions**.

### 8.1. Project structure

```text
spring-aop-correct-method-annotation/
├── pom.xml
└── src/main/java/com/example/methodanno/
    ├── TrackOperation.java
    ├── CriticalOperation.java
    ├── BillingOperations.java
    ├── BillingService.java
    ├── InspectAspect.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-correct-method-annotation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` supplies `ApplicationContext` and the Spring AOP dependencies in the example's dependency tree. `aspectjweaver` provides the library for Spring to parse `@AspectJ` pointcut expressions. **Compile-time/load-time AspectJ weaving is not configured**.

### 8.3. `src/main/java/com/example/methodanno/TrackOperation.java`

```java
package com.example.methodanno;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
public @interface TrackOperation {
    String value();
}
```

Two intentional target types:

- `METHOD`: allows placing `@TrackOperation("payment")` directly on methods.
- `ANNOTATION_TYPE`: allows placing `@TrackOperation("critical")` **on another annotation** to create a meta-annotation.

`RUNTIME` lets Spring read the marker at runtime.

### 8.4. `src/main/java/com/example/methodanno/CriticalOperation.java`

```java
package com.example.methodanno;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@TrackOperation("critical")
public @interface CriticalOperation {
}
```

`@CriticalOperation` is a simple **composed annotation**. A method carrying only `@CriticalOperation` does not need to declare `@TrackOperation` directly; Spring's `findMergedAnnotation` can recognize `TrackOperation` through the meta-annotation.

### 8.5. `src/main/java/com/example/methodanno/BillingOperations.java`

```java
package com.example.methodanno;

public interface BillingOperations {
    String pay(String id);
    String cancel(String id);
    String ping();
}
```

The interface **has no method-level annotations**. This setup deterministically demonstrates the "reading the wrong method on the interface" pitfall.

### 8.6. `src/main/java/com/example/methodanno/BillingService.java`

```java
package com.example.methodanno;

public class BillingService implements BillingOperations {

    @Override
    @TrackOperation("payment")
    public String pay(String id) {
        System.out.println("[TARGET] pay " + id);
        return "paid:" + id;
    }

    @Override
    @CriticalOperation
    public String cancel(String id) {
        System.out.println("[TARGET] cancel " + id);
        return "cancelled:" + id;
    }

    @Override
    public String ping() {
        System.out.println("[TARGET] ping");
        return "pong";
    }
}
```

Three methods share the **target class** yet carry different annotations:

- `pay`: direct `@TrackOperation("payment")`.
- `cancel`: `@CriticalOperation`, indirectly carrying the `TrackOperation("critical")` meta-annotation.
- `ping`: no annotation under this policy.

### 8.7. `src/main/java/com/example/methodanno/InspectAspect.java`

```java
package com.example.methodanno;

import java.lang.reflect.Method;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;

@Aspect
public class InspectAspect {

    @Around(
        "target(com.example.methodanno.BillingOperations)"
        + " && execution(public * com.example.methodanno..*.*(..))"
    )
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Method signatureMethod =
                ((MethodSignature) pjp.getSignature()).getMethod();

        Class<?> targetClass = AopUtils.getTargetClass(pjp.getTarget());

        Method actualMethod = AopUtils.getMostSpecificMethod(
                signatureMethod, targetClass);

        TrackOperation marker = AnnotatedElementUtils.findMergedAnnotation(
                actualMethod, TrackOperation.class);

        String label = (marker == null) ? "none" : marker.value();
        System.out.println("[ASPECT] method="
                + actualMethod.getName() + ", marker=" + label);

        return pjp.proceed();
    }
}
```

Because the advice uses **`target(BillingOperations)` and `execution(public ...)`**, it applies only to public method executions on targets matching the interface and package in the demo; **it does not require the target method to have `TrackOperation`**. This is intentional so that unannotated `ping` is still inspected and prints `marker=none`.

If a production goal is **intercepting only annotated operations**, consider `@annotation` in the pointcut (after verifying annotation/implementation/interface semantics) or using a Spring `Pointcut`/advisor with an equivalent predicate. **Do not spread a reflective advice across every method in the whole application** when only a few annotated methods need it.

### 8.8. `src/main/java/com/example/methodanno/DemoApp.java`

```java
package com.example.methodanno;

import java.lang.reflect.Method;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;
import org.springframework.core.annotation.AnnotatedElementUtils;

public class DemoApp {

    @Configuration
    static class Beans {
        @Bean
        BillingOperations billingOperations() {
            return new BillingService();
        }

        @Bean
        InspectAspect inspectAspect() {
            return new InspectAspect();
        }
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class JdkProxyConfig {
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibProxyConfig {
    }

    private static void inspectContext(String name, Class<?> config)
            throws NoSuchMethodException {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {

            BillingOperations service = context.getBean(BillingOperations.class);

            System.out.println("[" + name + "] jdk="
                    + AopUtils.isJdkDynamicProxy(service));
            System.out.println("[" + name + "] cglib="
                    + AopUtils.isCglibProxy(service));

            Method apiMethod =
                    BillingOperations.class.getMethod("pay", String.class);

            Method implementationMethod = AopUtils.getMostSpecificMethod(
                    apiMethod, AopUtils.getTargetClass(service));

            System.out.println("[" + name + "] interfaceDirect="
                    + (apiMethod.getDeclaredAnnotation(TrackOperation.class)
                       != null));

            System.out.println("[" + name + "] implementationDirect="
                    + (implementationMethod.getDeclaredAnnotation(
                            TrackOperation.class) != null));

            System.out.println("[" + name + "] implementationMarker="
                    + AnnotatedElementUtils.findMergedAnnotation(
                            implementationMethod, TrackOperation.class).value());

            System.out.println("[" + name + "] pay="
                    + service.pay("P-1"));

            System.out.println("[" + name + "] cancel="
                    + service.cancel("C-2"));

            System.out.println("[" + name + "] ping="
                    + service.ping());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        inspectContext("JDK", JdkProxyConfig.class);
        inspectContext("CGLIB", CglibProxyConfig.class);
    }
}
```

The two contexts are created **independently**. If `@EnableAspectJAutoProxy(proxyTargetClass=false)` and `true` were placed in the same context, Spring merges auto-proxy infrastructure; the stronger class-based setting could dominate and skew the comparison. Two separate contexts ensure the test genuinely observes both strategies.

`apiMethod` in `DemoApp` is obtained **explicitly from the interface** to prove the direct annotation is absent, avoiding output assumptions about the exact details of `MethodSignature.getMethod()` under CGLIB runtime. This builds a more reliable test than asserting generated proxy class name strings.

### 8.9. Running the program and expected stdout

Requires JDK 17+, Maven, and dependency download access. From the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.methodanno.DemoApp
```

Lines printed by the program (ignoring environment-dependent Spring/Maven/SLF4J logs):

```text
[JDK] jdk=true
[JDK] cglib=false
[JDK] interfaceDirect=false
[JDK] implementationDirect=true
[JDK] implementationMarker=payment
[ASPECT] method=pay, marker=payment
[TARGET] pay P-1
[JDK] pay=paid:P-1
[ASPECT] method=cancel, marker=critical
[TARGET] cancel C-2
[JDK] cancel=cancelled:C-2
[ASPECT] method=ping, marker=none
[TARGET] ping
[JDK] ping=pong
[CGLIB] jdk=false
[CGLIB] cglib=true
[CGLIB] interfaceDirect=false
[CGLIB] implementationDirect=true
[CGLIB] implementationMarker=payment
[ASPECT] method=pay, marker=payment
[TARGET] pay P-1
[CGLIB] pay=paid:P-1
[ASPECT] method=cancel, marker=critical
[TARGET] cancel C-2
[CGLIB] cancel=cancelled:C-2
[ASPECT] method=ping, marker=none
[TARGET] ping
[CGLIB] ping=pong
```

**Explanation:**

1. The JDK context has an interface-based proxy; the CGLIB context forces a class proxy, while the **target implementation and aspect code remain unchanged**.
2. `interfaceDirect=false` because we deliberately omitted `@TrackOperation` from `BillingOperations.pay`.
3. `implementationDirect=true` because the annotation sits directly on `BillingService.pay`.
4. `implementationMarker=payment` is the value found on the implementation method via the Spring API.
5. The advice reads `pay` with marker `payment`, even though the JDK proxy exposes the interface to the caller.
6. The advice reads `cancel` with marker `critical` thanks to `@CriticalOperation` being meta-annotated.
7. The advice reads `ping` with marker `none` and still lets the target method execute; **not finding an annotation** does not mean **the method is not invoked**.
8. Both contexts show **one way to normalize the target method that works for both JDK and CGLIB**. There is no need to write a separate reflection branch just because the proxy type differs.

The command and stdout are **expected results based on the code**. When integrating into a real codebase, run under your project's exact Spring/JDK/proxy configuration; this example is not an automated verification for all `TargetSource` types, nested proxies, bridge methods, or annotation hierarchies.

## 9. When the annotation sits on the interface rather than the implementation

The demo places markers on the implementation. Yet another codebase might want annotations to act as an **interface API contract**:

```java
public interface BillingOperations {
    @TrackOperation("api-payment")
    String pay(String id);
}
```

and implementation:

```java
@Override
public String pay(String id) {
    return "paid:" + id;
}
```

These two fragments describe an **alternative setup**, without modifying section 8's runnable project.

In this model:

- Direct lookup on the interface method sees the marker.
- Direct lookup on the concrete method does not necessarily see the marker.
- `AnnotatedElementUtils.findMergedAnnotation(concreteMethod, TrackOperation.class)` has **find semantics** and can search the method hierarchy (including interfaces) per the Spring API.
- Whether an **`@annotation` pointcut matches** an annotation present only on an interface requires its own test; do not equate annotation hierarchy resolution with AspectJ pointcut matching.
- If the interface and implementation carry **two conflicting markers**, the application must define precedence rather than letting proxy-style details decide policy arbitrarily.

**Practical recommendation:** Choose one consistent source of truth. For example: "policy annotations always live on concrete service methods", or "the interface API is the primary declaration source and implementations do not override arbitrarily". Document and test the rule to avoid silent drift.

## 10. Handling merged annotations and `@AliasFor`

In Spring applications, composed annotations enable meta-policies:

```java
@TrackOperation("critical")
public @interface CriticalOperation {}
```

The complete form must include `@Target` and `@Retention` as in the runnable project. When `@CriticalOperation` is on a method, `getDeclaredAnnotation(TrackOperation.class)` usually misses it because `TrackOperation` is not attached directly to the method; `findMergedAnnotation` can find it.

If you want a composed annotation with an attribute to **override** `TrackOperation`'s `value`:

```java
@TrackOperation("default")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface ClassifiedOperation {

    @org.springframework.core.annotation.AliasFor(
        annotation = TrackOperation.class,
        attribute = "value"
    )
    String value() default "default";
}
```

This is an **annotation-definition fragment**; it requires importing `java.lang.annotation.*` or each type individually, and `TrackOperation` must allow `ANNOTATION_TYPE`. With `@ClassifiedOperation("vip")`, `findMergedAnnotation(method, TrackOperation.class)` can synthesize an annotation with `value="vip"`.

Caveats:

- Only aliases valid under Spring's `@AliasFor` semantics work; default values and meta-annotation structure must be consistent.
- Standard `getAnnotation` or `getDeclaredAnnotation` **does not automatically apply** Spring's meta-annotation attribute overrides.
- If code needs merged annotations across a class hierarchy, explicitly check `findMergedAnnotation` vs. `getMergedAnnotation`: **find semantics** searches more broadly along supported structures.
- Never build audit/security policies by reading an annotation's `toString()` or using runtime proxy class names; extract typed metadata by annotation type.

## 11. Common mistakes when using reflection inside Spring advice

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `method.getAnnotation(...)=null` while implementation has annotation | `MethodSignature.getMethod()` is the interface method on a JDK proxy. | Get target class, call `AopUtils.getMostSpecificMethod`, then look up the annotation. |
| Inspecting `getThis().getClass()` shows `jdk.proxy...` | Looking at the generated proxy class instead of the target. | Use `getTarget()`, `AopUtils.getTargetClass`. |
| Reflection call `getMethod(name)` throws | The real method takes parameters; overloads/parameter types were ignored. | Use `MethodSignature.getMethod()`, then resolve the target method. |
| Direct annotation is absent while meta-annotation is present | Used `getDeclaredAnnotation` instead of Spring merged search. | Use `AnnotatedElementUtils.findMergedAnnotation` when composed metadata is needed. |
| Generic method has a bridge method and metadata is wrong | Reading the compiler-generated bridge method. | Use `AopUtils.getMostSpecificMethod` / `BridgeMethodResolver` per Spring API. |
| Annotation sits only on interface; direct lookup on implementation returns null | Method-level annotations are not automatically inherited like class annotations. | Use find semantics or an explicit interface-method fallback policy. |
| Advice runs on unannotated methods | Broad `execution` pointcut; reflection inside advice is not a pointcut predicate. | Put annotation conditions in the pointcut where appropriate, or skip inside advice. |
| `@annotation(marker)` does not bind as expected | Advice parameter/`argNames` mismatch, or annotation placement/proxy style differs from assumption. | Check naming, types, and annotated methods; test implementation/interface. |
| Spring bean is not advised | Aspect is not a Spring bean, AOP is off, pointcut doesn't match, or caller bypasses proxy. | Check bean registration, `@EnableAspectJAutoProxy`, `AopUtils`, and invocation path. |
| CGLIB proxy does not intercept `final` method | CGLIB cannot override that method. | Adjust public method contract or proxy strategy appropriately. |
| Same method name across overloads, wrong annotation read | Used method name string instead of complete method signature. | Keep `Method` and parameter types during resolution. |
| Class moved/renamed and old expression fails to match | Hardcoded old package/class in pointcut string. | Use stable named pointcuts/annotation contracts + behavior tests. |
| `@Inherited` on method annotation does not help | Java `@Inherited` does not apply to methods as assumed. | Use hierarchy-aware Spring annotation utilities and design placement conventions. |
| Reading annotations via `proxy.getClass().getDeclaredMethods()` | Generated proxy overrides are not the source of truth. | Resolve target class/method first. |

## 12. Step-by-step diagnosis to find "the right method"

A workflow to follow when Spring advice runs yet annotation lookup returns `null`:

1. **Confirm a real proxy:** Is the bean created/managed by Spring, and what does `AopUtils.isAopProxy(bean)` report?
2. **Identify the method in advice:** `((MethodSignature) jp.getSignature()).getMethod()`, its declaring class, and its parameter types.
3. **Identify the real target:** `jp.getTarget()`, `AopUtils.getTargetClass(...)`; do not treat the generated class from `jp.getThis()` as the business class.
4. **Find the most-specific method:** `AopUtils.getMostSpecificMethod(signatureMethod,targetClass)`.
5. **Check placement:** Is the annotation on the concrete method, interface method, parent method, or a meta-annotation?
6. **Choose lookup semantics:** `getDeclaredAnnotation` for direct-only; `findMergedAnnotation` for hierarchy/composition.
7. **Handle generic bridge methods:** Spring APIs resolve many cases; test critical generic interfaces and overrides.
8. **Review the pointcut:** `@annotation` uses pointcut matching, which is not necessarily identical to custom reflection policies.
9. **Check method call boundaries:** Self-invocation or `new`-created target objects do not pass through the Spring proxy, so advice never runs to read metadata.
10. **Put all cases into integration tests** instead of debugging solely via class names in stdout.

Having `isAopProxy=true` alone **is not enough**: the bean may be proxied for transactions, caching, or another advisor while your audit pointcut does not match the method to observe.

## 13. Checklist for integration tests

A trustworthy test suite should cover these cases:

| Case | Expected outcome |
| --- | --- |
| Annotation directly on implementation, JDK proxy | Reads implementation metadata through the most-specific method. |
| Annotation directly on implementation, CGLIB proxy | Reads metadata consistently with JDK. |
| Annotation only on interface method | Reads metadata per documented hierarchy/fallback policy. |
| Annotation on superclass method or override | Reads with the exact precedence defined by the application. |
| Method with composed annotation | `findMergedAnnotation` reads the merged annotation and expected attributes. |
| Generic override with bridge method | Metadata read on original method, not misread on compiler-generated method. |
| Unannotated method | Returns null or `"none"` as intended without errors. |
| Two same-named overloads with different annotations | No confusion between methods or parameter types. |
| Caller bypasses proxy via `this` or `new` | Spring advice does not run under normal proxy AOP. |
| Switching proxy style during refactoring | Annotation lookup still resolves properly against the real target type. |

A good test asserts not only `method.getName()`, but **`marker.value()`** on the specific method, along with exact advice/target execution counts. If annotations drive security, audit, or transaction policies, also test **ineligible cases** and exception paths.

## 14. Use reflection inside advice or bind `@annotation` directly?

**Use `@annotation` binding when:**

- Policy depends strictly on the annotation on the method matched by the Spring pointcut engine.
- No custom fallback from implementation to interface or other meta-annotation resolution is needed.
- You want concise, type-safe advice with clear intent.
- Integration tests cover real JDK/CGLIB proxies and annotation placement.

**Use method resolution + Spring annotation utilities when:**

- Advice is selected broadly by `execution/target`, yet must read markers to classify behavior.
- `MethodSignature` may return an interface method while the marker sits on the concrete implementation.
- Code needs to read **composed/meta-annotations** with `@AliasFor`.
- An explicit policy is needed for method hierarchies, overrides, or generic bridge methods.
- You want consistency across proxy-style changes without touching generated proxy classes.

**Do not overuse reflection** on every invocation if a meaningful static/annotation pointcut can select directly. When method metadata truly must be read frequently, cache keyed by **method/target class or resolved method** using an appropriate thread-safe strategy. Cache only immutable metadata, never `JoinPoint` or request-specific state inside a singleton aspect; consider classloaders and lifecycle when applications hot-reload multiple contexts.

## 15. Boundaries of Spring AOP that still apply

Even with accurate annotation resolution, proxy-based Spring AOP retains its fundamental limits:

- **Spring manages the bean and has applicable advisors:** an object instantiated with `new` outside the container is not handled automatically by Spring AOP.
- **Callers go through the proxy:** internal `this.method()` calls on the target do not go back through the proxy.
- **JDK proxy:** calls pass through the contract of proxied interfaces; a JDK proxy cannot be cast to arbitrary concrete implementations.
- **CGLIB proxy:** `final` classes cannot be subclassed; `final`/`private` methods are not advised by overriding under the standard model.
- **Initialization timing:** constructor/init callbacks on a raw target differ from normal business calls after the proxy is handed to callers.
- **Context/scope:** creators operate per context; scoped proxies and custom target sources add indirection requiring dedicated testing.
- **Annotation placement:** Java reflection `@Inherited` does not automatically solve method hierarchies; Spring annotation search has its own semantics and limits.

Reading metadata accurately **does not replace call-boundary and pointcut design**. Even a perfectly placed annotation on an implementation will not trigger advice for self-invocation that the proxy never sees.

### Official Spring Framework documentation

- **AopUtils.getMostSpecificMethod — Spring Framework 6.1.14 Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/support/AopUtils.html
- **AnnotatedElementUtils — Spring annotation hierarchy, composed annotations:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html
- **BridgeMethodResolver — Spring Framework Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/BridgeMethodResolver.html
- **Declaring Advice — annotation binding with `@annotation`:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **Declaring a Pointcut — `@annotation`, `this`, `target`:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- **Proxying Mechanisms — JDK/CGLIB and self-invocation:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion:** When an object is a Spring AOP proxy, `MethodSignature.getMethod()` is not necessarily the **implementing method carrying the business annotation**. To read it reliably inside a Spring Aspect, determine the **target class**, normalize to the **most-specific method** via `AopUtils.getMostSpecificMethod`, and use **Spring merged annotation utilities** when meta-annotations or hierarchy search are needed. Testing under both JDK and CGLIB proxies prevents "the annotation is in source, yet advice reads null" bugs.
