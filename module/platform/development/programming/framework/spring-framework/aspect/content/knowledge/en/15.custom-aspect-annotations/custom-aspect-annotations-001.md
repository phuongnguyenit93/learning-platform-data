# Defining a Marker Annotation for Use with Spring AOP

## 1. What Role Does a Marker Annotation Play in a Spring Aspect?

In a Spring application, we often want to apply a cross-cutting policy across many service methods — for example auditing important business operations, tracking latency, or checking a type of operation — without hardcoding every method name in a pointcut expression.

A **custom marker annotation** can act as a **declarative contract**: developers mark the methods that are permitted/required to have the policy applied; a Spring AOP aspect defines a matching pointcut, and then the advice runs only when a **method execution through a Spring proxy** matches the condition.

```java
@TrackCall("payment")
public String charge(String reference) {
    return "charged:" + reference;
}
```

This is a **method fragment**; it requires defining `@TrackCall` and placing it in a Spring service bean.

Note three independent things:

1. **Define the annotation**: create a Java annotation type with the appropriate `@Target` and `@Retention`.
2. **Place the annotation on a method**: expresses business intent; does not execute code by itself.
3. **Declare a Spring `@Aspect`/advice**: select the join point using `@annotation`, then handle the logic when the call **goes through a Spring AOP proxy**.

A custom annotation **does not automatically enable Spring AOP**, **does not automatically turn a class into a Spring bean**, and **does not automatically cause interception**. It is the Spring AOP infrastructure together with advice/pointcuts that does that.

The scope of this article focuses only on **Spring Framework Aspect** using annotation-style `@AspectJ` through proxies, in accordance with the Spring Aspect topic constraints. General Java annotation knowledge is used only to the extent needed to configure Spring AOP, without expanding into standalone AspectJ weaving.

## 2. Defining a Minimal Annotation Usable at Runtime

Minimal annotation for methods:

```java
package com.example.marker;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
}
```

This is a **complete Java annotation definition**; it can be saved in `TrackCall.java` in the right package.

Meaning:

- `public @interface TrackCall` defines an annotation type, not a regular Java interface requiring method implementations.
- `@Target(ElementType.METHOD)` allows use on method declarations; prevents misplacing the marker on a class/field/parameter.
- `@Retention(RetentionPolicy.RUNTIME)` keeps the annotation queryable at runtime, serving reflection and Spring AOP matching/binding.
- Only when the method is called **through an appropriate Spring AOP proxy** and has a matching advisor does the marker affect execution.

For a marker with no attributes, usage is `@TrackCall`, with no parentheses needed.

In real applications, if you want to record an additional event label/type, the annotation can declare elements:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

This is an **alternative definition**; do not put it alongside the definition above in the same project. When there is `String value()` without a default, users must supply the label: `@TrackCall("payment")` or `@TrackCall(value = "payment")`. `logResult()` defaults to `false` so it can be omitted.

Attributes are **configuration metadata for advice**, not mutable variables. You should not store passwords, tokens, PII, raw SQL, or secret data in annotation attributes — annotation metadata is typically present in bytecode and can be read via reflection.

## 3. Which Meta-Annotations Should and Should Not Be Used

### 3.1. `@Retention(RUNTIME)` — the Right Choice for Spring AOP

| Retention | When Does Metadata Still Exist? | Suitable for Spring `@annotation`? |
| --- | --- | --- |
| `SOURCE` | In source, no longer in bytecode | **No** for use as a runtime marker |
| `CLASS` | In the class file, but not exposed by the JVM to runtime reflection via standard mechanisms | **No** for designs needing runtime matching |
| `RUNTIME` | Retained by the JVM for runtime lookup | **Yes**, should be used |

When `@Retention` is forgotten, Java defaults to `RetentionPolicy.CLASS`. This is a common pitfall: code annotated with `@TrackCall` still compiles, but an annotation-based Spring AOP pointcut may **fail to match as expected**.

Do not try to solve this by renaming the advice method or changing `@Before` to `@Around`; you must fix the annotation definition and **rebuild**.

### 3.2. `@Target(METHOD)` — Choosing the Right Contract Attachment Point

If the annotation is used to select **method executions** in Spring AOP, `ElementType.METHOD` is the natural target.

If you want to create **composed annotations** later:

```java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
}
```

`ANNOTATION_TYPE` allows this annotation to appear on the definition of another annotation. This is a **design variant**, not mandatory for a direct marker.

Distinguish between:

- `@annotation`: matches an annotation on **method execution**.
- `@target`: matches an annotation attached to the target **class/type**.
- `@within`: matches method executions belonging to an annotated type according to Spring semantics.
- `@args`: inspects annotations of **runtime argument types**.
- `args`: inspects/binds runtime argument values/types, **not** the method's own annotation.

Do not change `@Target` to `TYPE` just because an aspect targets a service class. Choose the designator based on where the marker is actually attached.

### 3.3. `@Documented` — Optional but Useful

```java
@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
}
```

`@Documented` helps the annotation appear in the Javadoc of the annotated element, if processed by the corresponding Javadoc tool. It **does not** govern Spring pointcut matching.

### 3.4. Do Not Expect `@Inherited` to Solve Method Annotation Inheritance

Java `@Inherited` applies inheritance semantics to **class-level annotation lookup**; it does not mean annotations on interface methods or superclass methods are automatically inherited by all overridden methods via `Method.getAnnotation()`.

If a policy needs to look up annotations on interface/superclass/implementation methods, see section 10 on `AopUtils.getMostSpecificMethod` and `AnnotatedElementUtils`; do not assume adding `@Inherited` to a method marker is enough.

### 3.5. `@Repeatable` Is Not a Mechanism Where Aspects Read Every Instance by Default

A Java repeatable annotation can hold multiple instances of the same annotation type. However, do not assume an `@annotation(TrackCall)` pointcut will **bind all** instances as you expect. If multiple policy records are needed on one method, you must define the container/repeatability and test against the exact Spring version/API; often a single annotation carrying array values is simpler.

## 4. A Marker Annotation Design with Safe Metadata

A practical example:

```java
package com.example.marker;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

Metadata:

- `value()` represents a stable **action name** such as `charge`, `cancel`; avoid depending on package/class/method names if they might be refactored.
- `logResult() default false` provides an explicit **opt-in** before printing results. In production, a data classification/redaction policy is still needed; `true` alone does not grant permission to log PII.
- `@Documented` is useful for API documentation.
- `METHOD` and `RUNTIME` keep the definition consistent with Spring pointcuts.

Usage:

```java
@TrackCall(value = "charge", logResult = true)
public String charge(String reference) {
    return "charged:" + reference;
}

@TrackCall("cancel")
public String cancel(String reference) {
    throw new IllegalStateException("already finalized");
}
```

These method fragments will have a full runnable project in section 8.

The annotation should be placed in a **stable API package** with a name expressing behavioral intent. Avoid using `@Audit` both to mark "allowed to call" and to signify "must log all PII", if those meanings require different policies. A marker is only **intent/metadata**; it does not replace authorization or business validation.

## 5. The Spring `@annotation` Pointcut as the Bridge to the Marker

Spring Framework supports `@annotation` in AspectJ-style pointcut expressions for Spring AOP. It selects method executions that carry the corresponding annotation.

### 5.1. Matching by Annotation Type

```java
@Before(
    "execution(public * com.example.marker.PaymentService.*(..))"
    + " && @annotation(com.example.marker.TrackCall)"
)
public void beforeTracked() {
    // Runs before the marked method.
}
```

This is an **advice fragment**, without the `@Aspect` class and imports. In the expression:

- `execution(public * com.example.marker.PaymentService.*(..))` limits to public methods of a specific service.
- `@annotation(com.example.marker.TrackCall)` selects methods carrying the matching marker type.
- `&&` requires **both conditions to hold**.
- Using the fully-qualified name in the pointcut string avoids ambiguity when the parser lacks Java import context.

A marker type **is not a pointcut expression based on the method name itself**. For example, merely renaming `charge()` to `submitCharge()` while keeping `@TrackCall` may not change the policy if the `execution` part is broad enough.

### 5.2. Binding the Annotation Instance to Advice

Named binding can be used:

```java
@Around(
    value = "execution(public * com.example.marker.PaymentService.*(..))"
          + " && @annotation(marker)",
    argNames = "marker"
)
public Object trace(ProceedingJoinPoint pjp, TrackCall marker)
        throws Throwable {

    System.out.println("action=" + marker.value());
    return pjp.proceed();
}
```

This is a **fragment** for an `@Aspect` class. With this pointcut:

- `marker` in `@annotation(marker)` is the **binding identifier**.
- `TrackCall marker` in the Java advice signature is the formal parameter receiving the annotation object.
- `argNames="marker"` helps Spring map the annotation binding name explicitly.
- `ProceedingJoinPoint` is **first in the advice parameter list**, so its name can be omitted from `argNames` per Spring rules.
- `marker.value()` and `marker.logResult()` allow the advice to retrieve **type-safe metadata** without manual reflection.
- `pjp.proceed()` executes the inner chain; the advice must return a value matching the method contract.

**Do not use `@annotation(TrackCall)` and then declare a `marker` parameter expecting Spring to bind automatically across unrelated names.** When the annotation object is needed, use consistent named binding across the expression, `argNames`, and signature.

### 5.3. Inline Pointcut or Reusable Named Pointcut?

A named pointcut can group the scope condition:

```java
@Pointcut("execution(public * com.example.marker.PaymentService.*(..))")
public void paymentOperations() {}
```

Then the advice combines it:

```java
@Before(
    value = "paymentOperations() && @annotation(marker)",
    argNames = "marker"
)
public void before(TrackCall marker) {
    System.out.println(marker.value());
}
```

These are two fragments placed in the **same aspect class**. If used by multiple aspects, the named pointcut should live in a stable class with appropriate accessibility and be referenced by Java package/class when needed.

It is not mandatory to create a named pointcut for a single-use example. The main goal is **clear and sufficiently narrow pointcut content**, not adding pointless layers of abstraction.

## 6. Which Advice Type Should Be Chosen to Use the Marker?

| Need | Suitable Advice | Notes |
| --- | --- | --- |
| Only log before the method is called | `@Before` | No need to control `proceed()`. |
| Observe normal return | `@AfterReturning` | Bind `returning` if needed; does not replace the returned reference by reassigning the parameter. |
| Observe exceptions | `@AfterThrowing` | Only when method invocation exits with a matching exception. |
| Cleanup/aggregation after any sync outcome | `@After` | Has finally semantics; must understand advisor ordering. |
| Measure surrounding duration, handle success/error in the same call | `@Around` | Keep start time/actor in **local variables**, return the exact result/exception. |
| Modify arguments/result or short-circuit | `@Around` | Only when business policy permits, ensuring types and side effects. |

A `@TrackCall` marker **is not required to be paired with `@Around`**. Choose the least powerful advice type sufficient for the requirement. The demo example uses `@Around` to observe **both success/failure paths** and read `logResult`, not because the annotation only works with `@Around`.

If multiple advices match the same annotated method, Spring ordering and `@Order` must be considered; **do not infer order from method position in the `@Aspect` class**.

## 7. What Does Spring Actually Need for the Marker to Take Effect?

Chain of conditions:

```text
Java annotation type
    @Retention(RUNTIME), @Target(METHOD)
                |
                v
Spring service method carrying marker
                |
          Caller uses bean
                |
                v
          Spring AOP proxy
                |
       pointcut @annotation match
                |
                v
         Spring @Aspect advice
                |
         target method execution
```

Required setup steps:

1. The service is a Spring-managed bean (e.g., `@Bean` or component-scanned `@Service`).
2. The aspect class has `@Aspect` and **is registered as a Spring bean** (e.g., `@Bean` or `@Component`). `@Aspect` alone is not a bean-registering stereotype annotation.
3. Enable Spring AOP infrastructure via `@EnableAspectJAutoProxy` or appropriate Spring Boot auto-configuration. There is no need to add both mechanically.
4. Have the AspectJ dependency supporting Spring pointcut parsing, typically `org.aspectj:aspectjweaver`.
5. The pointcut actually matches the method and annotation placement without being excluded by scope conditions.
6. The caller invokes through the **Spring proxy** reference, not by manually instantiating `new` on the target or calling `this.annotatedMethod()` internally.

`@EnableAspectJAutoProxy` uses **Spring proxy-based AOP**; it does not automatically enable full AspectJ compile-time/load-time weaving.

## 8. Runnable Java 17+ Maven Project with Success, Failure, and Unmarked Methods

Demo objectives:

- Define the `@TrackCall` annotation with `value` and `logResult`.
- Spring advises only the two methods carrying the annotation.
- Advice binds the annotation instance and reads metadata.
- The success method can print the return result when opted in.
- The failing method is audited and then **throws the original exception**.
- The unmarked method runs only the target, printing no audit line.
- Finally, assert the advised call count to verify **proper pointcut scoping**.

Pinned environment: **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven**. These are illustrative versions, not claimed to be the latest.

### 8.1. Project Structure

```text
spring-aop-marker/
├── pom.xml
└── src/main/java/com/example/marker/
    ├── TrackCall.java
    ├── PaymentService.java
    ├── TrackCallAspect.java
    ├── AppConfig.java
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
    <artifactId>spring-aop-marker</artifactId>
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

`spring-context` provides `ApplicationContext` and the corresponding Spring AOP dependencies via its dependency tree; `aspectjweaver` supports parsing `@AspectJ` pointcut expressions. The demo does not use a full weaving agent.

### 8.3. `TrackCall.java`

```java
package com.example.marker;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackCall {
    String value();
    boolean logResult() default false;
}
```

This annotation **does not contain advice logic itself**. The two method annotation elements are read when Spring binds `TrackCall marker` in the aspect.

### 8.4. `PaymentService.java`

```java
package com.example.marker;

public class PaymentService {

    @TrackCall(value = "charge", logResult = true)
    public String charge(String reference) {
        System.out.println("[TARGET] charge " + reference);
        return "charged:" + reference;
    }

    @TrackCall("cancel")
    public String cancel(String reference) {
        System.out.println("[TARGET] cancel " + reference);
        throw new IllegalStateException("already finalized");
    }

    public String status() {
        System.out.println("[TARGET] status");
        return "UP";
    }
}
```

Only `charge` and `cancel` are marked. `status()` does not carry `@TrackCall`. Each method is public, non-final, and Spring manages the target instance via `@Bean` in the next section.

In production, do not mark an operation just to log **all payment parameters**. The demo intentionally prints only a test reference and a non-sensitive string result.

### 8.5. `TrackCallAspect.java`

```java
package com.example.marker;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TrackCallAspect {

    private final AtomicInteger advisedCalls = new AtomicInteger();

    @Around(
        value = "execution(public * com.example.marker.PaymentService.*(..))"
              + " && @annotation(marker)",
        argNames = "marker"
    )
    public Object around(ProceedingJoinPoint pjp, TrackCall marker)
            throws Throwable {

        advisedCalls.incrementAndGet();
        String action = marker.value();
        System.out.println("[AUDIT] enter action=" + action);

        try {
            Object result = pjp.proceed();

            if (marker.logResult()) {
                System.out.println("[AUDIT] success action=" + action
                        + " result=" + result);
            } else {
                System.out.println("[AUDIT] success action=" + action);
            }
            return result;
        } catch (Throwable error) {
            System.out.println("[AUDIT] failure action=" + action
                    + " type=" + error.getClass().getSimpleName());
            throw error;
        }
    }

    public int advisedCalls() {
        return advisedCalls.get();
    }
}
```

Points to verify:

- `@annotation(marker)` binds the **annotation instance** present on the method being intercepted.
- `argNames="marker"` provides the explicit parameter name; `pjp` is the leading `ProceedingJoinPoint` and does not need to be listed.
- `pjp.proceed()` is called once per matching invocation in the demo.
- The success branch returns the **exact target result**; the failure branch rethrows the **exact exception**.
- `advisedCalls` is a shared aggregate counter so it uses `AtomicInteger`; there is no mutable field storing the user or join point of the most recent call.
- `logResult` is only used to illustrate an attribute; in production, data classification/redaction is needed to avoid logging full result objects or `toString()` methods with side effects.

### 8.6. `AppConfig.java`

```java
package com.example.marker;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public TrackCallAspect trackCallAspect() {
        return new TrackCallAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=true)` enables Spring AOP and uses a CGLIB class-based proxy for `PaymentService` (which does not implement a business interface). The aspect is registered as a Spring bean via `@Bean`. Simply having the `@TrackCall` annotation type on the classpath does not create a proxy without an advisor.

### 8.7. `DemoApp.java`

```java
package com.example.marker;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            PaymentService payment =
                    context.getBean(PaymentService.class);
            TrackCallAspect aspect =
                    context.getBean(TrackCallAspect.class);

            System.out.println("isProxy=" + AopUtils.isAopProxy(payment));

            System.out.println("[CALLER] charge");
            String charged = payment.charge("P-1");
            System.out.println("[CALLER] result=" + charged);

            System.out.println("[CALLER] cancel");
            try {
                payment.cancel("P-2");
            } catch (IllegalStateException error) {
                System.out.println("[CALLER] caught=" + error.getMessage());
            }

            System.out.println("[CALLER] status");
            System.out.println("[CALLER] health=" + payment.status());
            System.out.println("advisedCalls=" + aspect.advisedCalls());

            if (aspect.advisedCalls() != 2) {
                throw new AssertionError("Expected exactly two advised calls");
            }
        }
    }
}
```

The caller uses the **bean from the Spring context**, rather than instantiating `new PaymentService()` outside the container. The final count helps detect overly broad or non-matching pointcuts.

### 8.8. Run Command and Expected stdout

From the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.marker.DemoApp
```

Lines printed by the program (excluding other Maven/Spring logs if present in the environment):

```text
isProxy=true
[CALLER] charge
[AUDIT] enter action=charge
[TARGET] charge P-1
[AUDIT] success action=charge result=charged:P-1
[CALLER] result=charged:P-1
[CALLER] cancel
[AUDIT] enter action=cancel
[TARGET] cancel P-2
[AUDIT] failure action=cancel type=IllegalStateException
[CALLER] caught=already finalized
[CALLER] status
[TARGET] status
[CALLER] health=UP
advisedCalls=2
```

Order explanation:

1. Spring creates the proxy: `isProxy=true`.
2. `charge` carries `@TrackCall` so the aspect runs before the body: `[AUDIT] enter...`, then the target prints `[TARGET]`.
3. Target returns a string; `logResult=true` causes the aspect to print success with the result; the caller receives the same string.
4. `cancel` also carries the marker; the aspect runs, then the target throws `IllegalStateException`. The advice catches/logs the event and rethrows; the caller catches the same exception. `logResult` is irrelevant on the error branch.
5. `status` does not carry the annotation, so **only the target** prints a log; there is no `[AUDIT]` for this method.
6. `advisedCalls=2` shows the marker scoped exactly two invocations.

This is **expected stdout from static code review**, not a claim that Maven was executed in a specific environment. If modifying the Spring version, proxy configuration, JDK, annotation placement, or adding advisors, integration tests should be re-run.

## 9. Spring Proxy Boundary: A Valid Marker May Still Have No Advice

### 9.1. Self-invocation

```java
public class PaymentService {
    public String perform() {
        return charge("internal");
    }

    @TrackCall("charge")
    public String charge(String reference) {
        return "charged:" + reference;
    }
}
```

This is an **alternative configuration fragment**; do not copy it alongside the demo `PaymentService.java` without updating the corresponding class. When a caller invokes `proxy.perform()` and the target calls `this.charge()` on itself, the internal call normally **does not go through the proxy**. An aspect targeting `charge` may **not run**, even though the annotation is placed properly.

Similarly, `new PaymentService().charge(...)` outside the Spring container is not auto-proxied merely because the method has a marker.

### 9.2. JDK Dynamic Proxy and CGLIB

- **JDK proxy** exposes interfaces; calls must go through proxied interface methods.
- **CGLIB proxy** is a subclass proxy and cannot intercept `final`/`private` methods via normal overriding; a final class cannot be subclassed by CGLIB.
- When an annotation is on the concrete implementation while the interface lacks it, resolution/matching behavior must be tested when changing proxy strategy.
- If a method only has package visibility or is protected, behavior/callability through the proxy differs from the public API; markers should be designed for **public business operations** unless there is a special reason.

Spring Boot and Spring Framework core may choose different default proxy strategies depending on configuration. Do not tie promises of "always JDK" or "always CGLIB" to a Java annotation type.

### 9.3. Aspect Bean Not Registered

Wrong:

```java
@Aspect
public class TrackCallAspect {
    @Before("@annotation(com.example.marker.TrackCall)")
    public void before() {}
}
```

Without a scanned `@Component` or `@Bean` registration, Spring may **have no aspect instance** to create an advisor. The annotation on the target method is still present, but no advice runs.

Solution: enable `@EnableAspectJAutoProxy`/appropriate Boot AOP auto-configuration; register the aspect under the Spring bean lifecycle, and verify the correct `ApplicationContext`.

### 9.4. Verifying the Bean/Proxy Before Debugging Expressions

```java
System.out.println(AopUtils.isAopProxy(payment));
System.out.println(AopUtils.isJdkDynamicProxy(payment));
System.out.println(AopUtils.isCglibProxy(payment));
```

This is a fragment where `payment` is the bean reference returned by Spring. `isAopProxy=true` indicates a proxy exists, **it does not prove every desired advice matches**: the bean could have been proxied by transactions or another advisor. Always assert the event count of the exact aspect on the exact method.

## 10. Annotations on Interfaces, Implementations, and Classes

A marker attached directly to an implementation method is the easiest case to verify with Spring AOP. When placing a marker on an interface method, an overridden method, or a class, distinguish:

- Java reflection does not automatically inherit annotations on interface methods to implementation methods; `@Inherited` does not solve method annotations.
- `@annotation` targets method execution; `@within` and `@target` inspect types according to their respective semantics.
- With JDK proxies, `MethodSignature.getMethod()` may point to the interface method. If implementation metadata must be read, use `AopUtils.getMostSpecificMethod(...)` and Spring annotation utilities.

If multiple places declare the marker with different values, define which location takes precedence and test with both JDK/CGLIB. If the pointcut does not match in the first place, lookup inside the advice cannot make the advice run.

## 11. Composed Annotations and `@AliasFor`

When another annotation is meta-annotated with `@TrackCall`, the base type must have `@Target` allowing `ANNOTATION_TYPE`, and both annotation types must retain `RUNTIME`. Spring can read metadata via `AnnotatedElementUtils.findMergedAnnotation(...)`; `@AliasFor` expresses attribute overrides in the merged annotations model.

However, **Spring merged annotation lookup and AspectJ-style `@annotation` pointcuts are not the same algorithm**. Do not extend a marker's guarantees to composed annotations without integration tests measuring advice invocation counts. When multiple composition layers must be supported, consider a matcher/advisor based on Spring APIs or a sufficiently narrow `execution` pointcut that then resolves metadata.

## 12. Keeping Pointcut Scope Intentional

`@annotation(marker)` can match more beans than the business group intended to handle. A scope like `execution(public * com.example.payment..*Service.*(..)) && @annotation(marker)` makes the boundary clearer; however, when renaming packages or classes, integration tests must detect if the pointcut stops matching.

Choose scope based on contract and actual invocation patterns. Spring AOP only intercepts method executions going through a Spring proxy; it does not intercept field access or constructors merely because the annotation's `@Target` permits them.

## 13. A Marker Is Not a Security or Business Guarantee

`@TrackCall("transfer")` only describes the intent to apply tracking; it does not authenticate access permissions, does not guarantee a transaction has committed, and does not automatically make an operation safe to retry. If an advice decides to short-circuit or invoke `proceed()` multiple times, that is a business contract change requiring explicit testing. Do not use an auditing annotation as the sole security barrier when self-invocation or objects outside Spring can bypass the proxy.

## 14. Designing Small and Meaningful Attributes

Annotation elements can only be primitives, `String`, `Class`, enums, annotations, or arrays of permitted types. For instance, `String value()` should be a stable event name, while `boolean logResult() default false` only enables result logging under a controlled data policy. Avoid passwords, tokens, and request state in metadata; if values are a finite set of operation types, an `enum` is usually clearer than arbitrary strings.

Adding a required element or changing the default of an existing element is an API/behavioral change for already-annotated methods. Compatibility must be managed when multiple modules share an annotation.

## 15. Testing Two Layers of Behavior

Test **metadata** to confirm `@Target`, `@Retention(RUNTIME)`, required/default elements, and placement. Then test the **Spring context** by calling through the real bean proxy, including:

1. Marked methods receive advice exactly once with the right annotation values; unmarked methods are not advised.
2. Business return values and exceptions are preserved by `@Around`, including the error branch.
3. Two methods with different marker values do not mix up metadata; a singleton aspect does not store request/JoinPoint data in mutable fields.
4. Self-invocation and `new Target()` outside the container are not counted as intercepted by Spring AOP.
5. If supporting interfaces, overloads, composed annotations, or multiple advisors, write positive/negative tests for each case and each proxy strategy actually used.

Testing right where Spring enforces the policy avoids confusing reflection results or proxy existence with the specific advice having actually run.

## 16. Common Pitfalls

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Marker placed on method but advice does not run | Forgot `@Retention(RUNTIME)`, defaults to `CLASS` | Add proper retention, rebuild. |
| Annotation placed on class while using `@annotation` | `@annotation` inspects method join points, not type markers | Place marker on method or switch PCD to `@target`/`@within` as appropriate. |
| `@Target` forbids placing on method | Annotation only allows `TYPE`/`FIELD` | Add `ElementType.METHOD` per requirements. |
| Has `@TrackCall` but no AOP proxy | AOP not enabled, aspect bean not registered, caller uses `new` | Check `@EnableAspectJAutoProxy`/Boot config and Spring beans. |
| Self-invocation is not advised | `this.method()` bypasses the proxy | Refactor bean boundaries/call through the appropriate Spring proxy. |
| JDK proxy does not intercept concrete-only method | Method is not on the proxied interface | Call via the proper interface contract or choose class proxy when needed. |
| CGLIB does not intercept `final` method | CGLIB cannot override it | Change method/class contract or pick another strategy. |
| `@annotation(marker)` fails to bind | Wrong `argNames`/parameter type or expression | Synchronize identifier and advice signature. |
| Unmarked method still gets advised | Pointcut too broad, missing `&& @annotation(...)` | Narrow expression, add negative tests. |
| Interface annotated but direct implementation lookup returns null | Method-level annotations are not inherited like class annotations | Standardize placement and use Spring annotation utilities when needed. |
| Composed marker does not work as expected | Confusing direct `@annotation` matching with merged annotation lookup | Test separately; use `findMergedAnnotation`/appropriate matcher. |
| Reassigning result parameter in `@AfterReturning` not seen by caller | Advice parameter is a local reference | Use `@Around` if a replacement must be returned. |
| Caller invokes once but audit repeats | Multiple proxies/advisors or `proceed()` called multiple times | Diagnose chain, ordering, and retries. |
| Logs contain tokens/PII | `logResult=true` without redaction policy | Design safe defaults, audit allowlist. |
| Aspect shared field mixes up users | Singleton aspect holds per-invocation state | Use local variables and thread-safe event sinks. |
| Annotation treated as authorization | Marker does not protect call paths by itself | Use framework security and test proxy bypass/edge cases. |

## 17. Review Checklist Before Introducing a Custom Marker to a Module

- [ ] Annotation name expresses **consistent meaning**, not overloaded with too many responsibilities.
- [ ] Has `@Retention(RUNTIME)`.
- [ ] Has `@Target(METHOD)` or a specific target set fitting the policy.
- [ ] Has `@Documented` if helpful for API docs.
- [ ] Elements such as `value()`/`logResult()` have safe defaults and a clear API.
- [ ] Annotation does not store credentials or runtime mutable state.
- [ ] Aspect has `@Aspect` **and** is Spring-managed.
- [ ] Spring AOP auto-proxy is enabled and `aspectjweaver` is on the classpath.
- [ ] `@annotation` pointcut binds the right type/name with reasonable scope.
- [ ] Callers use the Spring proxy, without relying on self-invocation.
- [ ] Positive/negative integration tests exist for methods with/without the marker.
- [ ] Advice exception path and return contract have been verified.
- [ ] Clear convention exists on placing the annotation on interfaces vs. implementations.
- [ ] If using composed annotations, `@AliasFor`/merged semantics and pointcut matching were tested separately.
- [ ] If multiple aspects match, Spring ordering is controlled.
- [ ] Marker is not assumed sufficient to replace business validation, authorization, transactions, or idempotency.

### Official Spring Documentation

- Spring Framework — Declaring a Pointcut (`@annotation` and PCDs): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — Declaring Advice (binding annotation instance, `argNames`, `ProceedingJoinPoint`): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Enabling `@AspectJ` Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms (JDK/CGLIB, self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `AopUtils` and target method resolution: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework — `AnnotatedElementUtils`, merged annotations: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html

**Conclusion:** To build a marker annotation that genuinely works with Spring AOP, create an annotation type with **`@Target(METHOD)` and `@Retention(RUNTIME)`**, attach it to Spring-managed service methods, and declare a **Spring `@Aspect` bean** with an `@annotation` pointcut (and binding when metadata must be read). The annotation **only marks intent**; interception depends on the Spring AOP proxy, pointcut scope, advisor configuration, and actual call path.
