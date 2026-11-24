# @args in Spring AOP: Filtering Calls by Annotation on the Runtime Argument Type

## 1. Practical Meaning of @args in Spring

A Spring service may accept a very broad declared parameter such as `Object`, an interface, or a superclass. When the application calls the service, actual arguments can belong to many different classes. Sometimes we want advice to run only if the **actual class of the argument is marked with an annotation**, rather than selecting by the declared type in the method signature.

In Spring AOP, the `@args` pointcut designator solves this exact requirement:

> `@args` limits matching to method-execution join points where the **runtime types of the actual arguments passed** carry the corresponding annotation.

Example:

```java
@Before("execution(* com.example.app.service..*.*(..))" +
        " && @args(com.example.app.aop.Reviewed)")
public void beforeReviewedArgument() {
    // Applies to methods taking exactly one argument,
    // when the runtime class of that argument carries @Reviewed.
}
```

This is an illustrative snippet, assuming the `Reviewed` annotation exists and the aspect is registered as a Spring bean. The single-position `@args(Reviewed)` expression requires **one argument** whose runtime type carries `@Reviewed`. The `execution(...)` part simultaneously restricts which Spring service methods are evaluated.

**Key point:** `@args` does not check annotations on **method parameters** (`@Target(PARAMETER)`), nor does it check annotations on the **method itself** (`@annotation`). It relies on the annotation on the **runtime type of the argument value**. Thus, even if a method declares `submit(Object value)`, a call passing `new ReviewedOrder()` can match, while `new PlainOrder()` does not.

This lesson focuses strictly on `@args` in **proxy-based Spring Framework / Spring AOP**, without expanding into AspectJ weaving join points outside Spring's mechanism.

### Expected Outcomes After This Lesson

You will be able to:
1. Write an annotation for use with `@args` using `@Target(TYPE)` and `@Retention(RUNTIME)`.
2. Distinguish declared parameter types from the argument's runtime class when Spring selects advice.
3. Write `@args` for single-argument methods, understanding count/position requirements and how to combine with `execution`.
4. Distinguish `@args` from `args`, `@annotation`, `@within`, `@target`, and annotations directly on parameters.
5. Verify behavior with a complete Java 17 + Spring Framework example containing annotated and unannotated arguments.
6. Recognize practical limitations: `null`, proxies passed as arguments, subtypes, retention, self-invocation, and runtime matching overhead.

## 2. First: Where Does the Annotation Live?

Suppose there is an annotation used to mark **sensitive data classes**:

```java
package com.example.app.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Reviewed {
    String value() default "review";
}
```

And two payload classes:

```java
@Reviewed("sensitive")
public class ReviewedOrder {
}

public class PlainOrder {
}
```

In a Spring service:

```java
public void submit(Object payload) {
    // Process payload.
}
```

Two calls with the same method signature but different **runtime classes**:

```java
service.submit(new ReviewedOrder()); // @args(Reviewed) can match.
service.submit(new PlainOrder());    // @args(Reviewed) does not match.
```

The snippets above are not a standalone project; the compilable project is in section 7.

Why is `@Target(TYPE)` important? The annotation must be attached to the **type** of the argument so `@args` can find it. `@Retention(RUNTIME)` keeps the annotation available while the program runs. An annotation existing only at `SOURCE` or `CLASS` level does not provide the runtime reflection information Spring AOP needs for this example.

**A common misconception:** Annotating a field holding an object, a local variable holding an object, or a parameter in the method definition does not mean the object's runtime class is annotated.

## 3. Declared Type and Runtime Type: The Difference That Decides the Outcome

Consider the method:

```java
public void publish(Object event) {
    System.out.println(event);
}
```

The declared type of parameter `event` is `Object`, yet at runtime:

```java
Object first = new ReviewedOrder();
Object second = new PlainOrder();

service.publish(first);
service.publish(second);
```

The first argument still has runtime class `ReviewedOrder`; the second is `PlainOrder`. `@args(Reviewed)` distinguishes the two calls even though the method's bytecode signature is identical.

We can visualize it as:

```text
Caller -> Spring AOP proxy -> publish(Object event)
                         |
                         +-- actual argument: ReviewedOrder instance
                         |       |
                         |       +-- runtime class has @Reviewed?
                         |               YES -> advice can run
                         |
                         +-- actual argument: PlainOrder instance
                                 |
                                 +-- runtime class has @Reviewed?
                                         NO -> advice skipped
```

In Spring, both calls must go through the **service's proxy** first. If a client creates the target with `new` or the service calls `this.publish(...)` from another method, advice may not run regardless of the argument's annotation.

### Simple Prediction Table

Assume the method takes **one** argument, Spring AOP is enabled, `@Before("@args(com.example.app.aop.Reviewed)")` is applied through a proxy, and there are no other pointcut constraints:

| Runtime argument | Does the argument's runtime class carry `@Reviewed`? | Corresponding advice |
| --- | --- | --- |
| `new ReviewedOrder()`, class marked `@Reviewed` | Yes | Can run |
| `new PlainOrder()`, unmarked class | No | Does not run |
| `Object`-typed variable holding `new ReviewedOrder()` | Yes | Can run, since runtime value is evaluated |
| Interface-typed variable holding an annotated implementation instance | Depends on annotation on the runtime class | Based on runtime class, not only the interface |
| `null` | No runtime class from which to read annotation | Cannot be used to infer an annotated type; test runtime behavior and design an explicit null policy |

On the last row, avoid writing business logic assuming `null` "carries the annotation" of the declared type. For a pointcut constraining runtime types, there is no object from which to read annotations when the argument is `null`. If behavior on `null` matters, handle `null` via explicit validation in a separate method/advice and test on your actual Spring/AspectJ version.

## 4. @args vs. Easily Confused Pointcuts

### 4.1. @args and args Are Not the Same

Both inspect actual arguments, but they check different things:

```java
@Pointcut("args(com.example.app.model.ReviewedOrder)")
public void hasReviewedOrderRuntimeType() {
}
```

`args(TypePattern)` checks the **runtime type of the argument**, such as an object of type `ReviewedOrder` or a matching subtype.

```java
@Pointcut("@args(com.example.app.aop.Reviewed)")
public void hasReviewedAnnotationOnRuntimeType() {
}
```

`@args(AnnotationTypePattern)` checks the **annotation on the runtime type of the argument**, without requiring a single specific class. If both `ReviewedOrder` and `FlaggedDocument` carry `@Reviewed`, `@args(Reviewed)` can match both without writing two type patterns.

| Design | Selects by | Example |
| --- | --- | --- |
| `args(com.example.app.model.ReviewedOrder)` | Runtime class/interface of the actual argument | Object of `ReviewedOrder`/compatible subtype |
| `@args(com.example.app.aop.Reviewed)` | Annotation on runtime class of the actual argument | Any runtime class carrying `@Reviewed` |
| `execution(* *.publish(com.example.app.model.ReviewedOrder))` | Method signature declaring parameter type | Method declaration taking `ReviewedOrder`; not equivalent to checking runtime objects |
| `execution(* *.publish(Object))` | Method signature declaring `Object` | Same method can receive both annotated and unannotated objects |

For example, `execution(* *.publish(Object))` alone does not know whether the actual payload class is annotated. Therefore, `@args` can add dynamic filtering to a generic method signature.

### 4.2. @args and @annotation

`@annotation` checks for an annotation on the **method being executed**:

```java
@Before("@annotation(com.example.app.aop.AuditedOperation)")
public void beforeAnnotatedMethod() {
}
```

This is a snippet assuming `AuditedOperation` targets `ElementType.METHOD`. An annotated method can match regardless of whether the argument is `ReviewedOrder` or `PlainOrder`.

Conversely:

```java
@Before("@args(com.example.app.aop.Reviewed)")
public void beforeAnnotatedArgumentType() {
}
```

selects by the argument's runtime annotation, without requiring the method to carry `@AuditedOperation`. Both conditions can be combined if needed.

### 4.3. @args and @within / @target

- `@within(TypeAnnotation)`: selects method executions declared in types bearing that annotation, depending on how Spring evaluates types/declaring types.
- `@target(TypeAnnotation)`: looks at the annotation on the **runtime target object type** behind the Spring proxy.
- `@args(TypeAnnotation)`: looks at the annotation on the **runtime types of actual arguments** passed to the method, not the target.

Suppose Spring target `OrderService` does not carry `@Reviewed`, while input `ReviewedOrder` carries the annotation: `@args(Reviewed)` can match; `@target(Reviewed)` does not match because the target service is unmarked. Moving the annotation from the payload class to the service class changes the semantics.

### 4.4. Annotations on Method Parameters Are Not @args

Example:

```java
public void publish(@NotNull Object event) {
}
```

`@NotNull` is attached to the **parameter declaration**, not to `event.getClass()`. Thus, it **does not satisfy** `@args(NotNull)` as an annotation on the runtime argument type. `@NotNull` itself in this example is also a different validation concept, not a reason for Spring AOP to automatically apply an aspect.

If the goal is checking annotations directly on Java method parameters, design an appropriate solution (such as validation or reflection in a custom advisor), rather than using `@args` expecting it to inspect `Method.getParameterAnnotations()`.

## 5. Argument Count and Position in @args

### 5.1. Single Position: Method Taking One Argument

```java
@Pointcut("@args(com.example.app.aop.Reviewed)")
public void oneAnnotatedArgumentType() {
}
```

This is the case Spring documentation explicitly describes: a method execution taking **one** argument whose runtime type carries `@Reviewed`. It does not mean "a method with any number of arguments, as long as one argument is annotated".

### 5.2. Multiple Positions and Wildcards

AspectJ-style annotation patterns support positional combinations. A guiding example:

```java
@Pointcut("@args(*, com.example.app.aop.Reviewed)")
public void secondArgumentAnnotated() {
}
```

This expression aims to select methods with **two** arguments where the runtime type of the **second** argument carries `@Reviewed` and the first position uses a wildcard. This example illustrates positional syntax, not part of the runnable project in section 7.

In systems with many overloads, varargs, nested collections, or mixed annotations, **verify the exact pattern syntax and test on your Spring/AspectJ version**; do not treat "any annotated argument works" as if all `@args` variants shared that semantics.

### 5.3. List<T>, Arrays, and Varargs

If a method accepts `List<Object>` containing a `ReviewedOrder`, the sole actual argument at runtime is a **List implementation**, not each element inside. `@args(Reviewed)` checks the runtime type of the `List` object itself; it **does not automatically traverse** items looking for annotations.

Likewise, when a method takes an array `ReviewedOrder[]`, the runtime actual argument is the **array class**, which is not treated as equivalent to an annotation on the array's component type. Varargs in Java can compile into an array parameter; therefore, distinguish call-site syntax from the actual arguments seen by Spring AOP.

If the requirement is "any item in a collection is annotated", write business validation/advice logic iterating the collection or use a suitable validation mechanism. Do not expect `@args` to do that automatically.

## 6. Constraining @args to a Spring Service Scope

`@args` is dynamic: the annotation on the runtime argument can change between calls to the same method.

You should restrict first using **static** conditions:

```java
@Aspect
public class ReviewedPayloadAspect {

    @Pointcut("within(com.example.app.service..*)")
    public void serviceLayer() {
    }

    @Pointcut("execution(public * *(..))")
    public void publicMethods() {
    }

    @Pointcut("@args(com.example.app.aop.Reviewed)")
    public void reviewedArgumentType() {
    }

    @Before("serviceLayer() && publicMethods() && reviewedArgumentType()")
    public void beforeReviewed() {
        // Runs only for calls matching layer, signature, and runtime arg.
    }
}
```

The snippet above depends on application packages/annotations and is not a standalone program. It expresses three layers of conditions:

1. `within(service..*)`: target method execution belongs to the service layer.
2. `execution(public * *(..))`: public method.
3. `@args(Reviewed)`: corresponding actual arguments have a matching runtime annotation.

**Avoid using `@args` as a sole security authorization rule.** If argument types can be constructed or influenced externally, a runtime annotation is metadata, not proof that the caller is authorized to perform an operation. Validation, authentication, and authorization must have proper trust boundaries. Spring AOP proxies also remain subject to limits around self-invocation and `final`/`private` methods.

## 7. Runnable Example: One Object Parameter, Two Runtime Payload Types

This example uses **Java 17, Spring Framework 6.1.14, and Gradle**, with no Spring Boot, web server, or database needed. We intentionally declare `submit(Object payload)` to prove `@args` inspects the **class of the actual payload** rather than the declared `Object` type.

Controlled conditions:
- A single `AnnotationConfigApplicationContext`.
- The aspect is registered via `@Bean`.
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` creates a class-based proxy for `OrderProcessor`.
- One payload class carries `@Reviewed` and one class does not.
- Every call to `submit(...)` in `main` goes through the Spring-managed service proxy.

### 7.1. Project Structure

```text
spring-aop-at-args/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── AppConfig.java
    ├── annotations/Reviewed.java
    ├── model/FlaggedPayload.java
    ├── model/PlainPayload.java
    ├── service/OrderProcessor.java
    └── aop/ArgumentAspect.java
```

### 7.2. Gradle Build

File `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-at-args'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.DemoApplication'
}
```

`spring-context` supplies `AnnotationConfigApplicationContext` and `@Configuration`/`@Bean`; `spring-aop` holds Spring AOP proxy infrastructure; `aspectjweaver` enables Spring to parse `@Aspect` pointcut expressions. This lesson pins Spring versions to avoid depending on AOP defaults that may vary with Spring Boot.

### 7.3. Annotation Placed on Types and Retained at Runtime

File `src/main/java/demo/annotations/Reviewed.java`:

```java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Reviewed {
    String value() default "review";
}
```

- `@Target(ElementType.TYPE)`: the annotation is attached to class/type declarations.
- `@Retention(RetentionPolicy.RUNTIME)`: the annotation can be inspected at runtime.
- `value` is illustrative metadata; the pointcut only needs the annotation present. To read annotation values inside advice, see binding in section 8.

### 7.4. Two Contrasting Payload Types

File `src/main/java/demo/model/FlaggedPayload.java`:

```java
package demo.model;

import demo.annotations.Reviewed;

@Reviewed("sensitive")
public final class FlaggedPayload {
}
```

File `src/main/java/demo/model/PlainPayload.java`:

```java
package demo.model;

public final class PlainPayload {
}
```

Both `final` classes can still be used **as arguments** to the service. Spring only needs to proxy the **service target**, not create CGLIB proxies for `FlaggedPayload` or `PlainPayload`. Do not confuse `final` on an *argument object* with `final` on a *Spring bean to be proxied*.

### 7.5. Spring Service Accepting Object

File `src/main/java/demo/service/OrderProcessor.java`:

```java
package demo.service;

public class OrderProcessor {
    private int targetCalls;

    public void submit(Object payload) {
        targetCalls++;
        String type = payload.getClass().getSimpleName();
        System.out.println("target:" + type);
    }

    public int targetCallCount() {
        return targetCalls;
    }
}
```

`submit` declares its parameter as `Object`. This method is not annotated with `@Reviewed`, yet the actual payload class can carry that annotation. Variable `targetCalls` counts target method executions; all calls in the demo are sequential, so `int` keeps output simple.

To focus on `@args`, the program does not pass `null` to `submit`. If `null` were passed, `payload.getClass()` would need null handling first.

### 7.6. Aspect Filtering by Runtime Annotation

File `src/main/java/demo/aop/ArgumentAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ArgumentAspect {
    private int adviceCalls;

    @Before(
        "execution(public void demo.service.OrderProcessor.submit(..))" +
        " && @args(demo.annotations.Reviewed)"
    )
    public void beforeReviewed(JoinPoint joinPoint) {
        adviceCalls++;
        Object argument = joinPoint.getArgs()[0];
        System.out.println(
            "advice:" + argument.getClass().getSimpleName());
    }

    public int adviceCallCount() {
        return adviceCalls;
    }
}
```

In the declaration:
- `execution(public void demo.service.OrderProcessor.submit(..))` selects only the matching method on the service.
- `@args(demo.annotations.Reviewed)` selects only calls with **one actual argument** whose runtime class carries `@Reviewed`.
- `JoinPoint.getArgs()[0]` reads the object passed to the invocation currently being advised.
- The call with `PlainPayload` does not trigger the advice; hence `beforeReviewed` is not invoked for that payload.

The advice is `@Before`, so it logs **before** the target method. We use a singleton aspect to count advice runs; this lesson runs sequentially, so do not use this mutable counter as a production concurrency model.

### 7.7. Registering Beans and Enabling Spring AOP

File `src/main/java/demo/AppConfig.java`:

```java
package demo;

import demo.aop.ArgumentAspect;
import demo.service.OrderProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    public ArgumentAspect argumentAspect() {
        return new ArgumentAspect();
    }
}
```

Spring bean `orderProcessor` is processed by the auto-proxy creator after Spring parses advisors from `ArgumentAspect`. `@Aspect` does not register a bean automatically, while `@Bean argumentAspect()` ensures the aspect is in the context. `proxyTargetClass=true` uses a class-based proxy so `context.getBean(OrderProcessor.class)` returns the expected type.

### 7.8. Entry Point

File `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.aop.ArgumentAspect;
import demo.model.FlaggedPayload;
import demo.model.PlainPayload;
import demo.service.OrderProcessor;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderProcessor processor =
                context.getBean(OrderProcessor.class);
            ArgumentAspect aspect =
                context.getBean(ArgumentAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(processor));

            processor.submit(new FlaggedPayload());
            processor.submit(new PlainPayload());

            Object polymorphic = new FlaggedPayload();
            processor.submit(polymorphic);

            System.out.println("adviceCount=" + aspect.adviceCallCount());
            System.out.println("targetCount=" + processor.targetCallCount());
        }
    }
}
```

The line `Object polymorphic = new FlaggedPayload();` is an important verification: the variable's declared type is `Object`, while the runtime class is still the annotated `FlaggedPayload`. Spring AOP should handle it just like the first call.

### 7.9. Running and Checking Results

In the directory containing `build.gradle`, run with a Gradle version supporting Java 17:

```bash
gradle run
```

If using the Gradle Wrapper, run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

**Lines printed by the Java application**, excluding Gradle logs/banners or environment logging:

```text
proxy=true
advice:FlaggedPayload
target:FlaggedPayload
target:PlainPayload
advice:FlaggedPayload
target:FlaggedPayload
adviceCount=2
targetCount=3
```

Interpretation:
1. `proxy=true` proves `OrderProcessor` is wrapped by a Spring AOP proxy.
2. The first call with `FlaggedPayload` prints `advice` then `target`.
3. The call with `PlainPayload` prints **only** `target` because its runtime class lacks `@Reviewed`.
4. The call via `Object polymorphic` is advised again because the actual runtime class is still `FlaggedPayload`.
5. `adviceCount=2` and `targetCount=3` prove only two of the three method invocations matched `@args`, even though all three entered the same `submit(Object)` method signature.

If you replace `@args(demo.annotations.Reviewed)` with just `execution(...)`, the advice can run for all three calls because the runtime annotation condition is gone. This clearly separates the role of each pointcut piece.

## 8. Binding in @args: Retrieving the Annotation Object or Argument

Spring allows binding pointcuts like `args` and `@args` to pass data into the advice method. This is a **different** mechanism from merely checking whether the annotation exists.

### 8.1. Binding the Annotation

Suppose `@Reviewed` has `value()`; you can use a parameter name in the pointcut:

```java
@Before(
    value = "execution(public void demo.service.OrderProcessor.submit(..))" +
            " && @args(reviewed)",
    argNames = "reviewed"
)
public void beforeReviewed(Reviewed reviewed) {
    System.out.println("label=" + reviewed.value());
}
```

This snippet replaces the advice method in section 7; do not register both in parallel if you only want one log. Import `demo.annotations.Reviewed`. The name `reviewed` in `@args(reviewed)` binds to the **annotation instance**, while the actual argument value is not that annotation itself.

`argNames="reviewed"` states the binding name explicitly; this helps when compiled code does not retain parameter names, though Spring also has other name discovery mechanisms.

### 8.2. Binding Actual Argument Together with Annotation

When you need both the argument and the annotation metadata, the expression can combine `args(payload)` with `@args(reviewed)`:

```java
@Before(
    value = "execution(public void demo.service.OrderProcessor.submit(..))" +
            " && args(payload) && @args(reviewed)",
    argNames = "payload,reviewed"
)
public void before(Object payload, Reviewed reviewed) {
    System.out.println(payload.getClass().getSimpleName());
    System.out.println(reviewed.value());
}
```

This is also an **alternative snippet** inside an `@Aspect`, not code to paste alongside the running project simultaneously. For a single-argument method, `args(payload)` retrieves the actual object while `@args(reviewed)` retrieves the annotation on its runtime type. When using annotations/binding in production, write integration tests for advice parameter binding and the proxy kind of your Spring version.

If you only need to inspect the object without binding the annotation, `JoinPoint.getArgs()` as in the main example has fewer requirements for parameter-name discovery.

## 9. Limitations to Check in Real Systems

### 9.1. Annotation Must Exist at Runtime

An annotation defined as follows is unsuitable for `@args`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface SourceOnlyFlag {
}
```

`RetentionPolicy.SOURCE` does not retain the annotation at runtime for the Spring/AspectJ matcher to read. Even though the code compiles, runtime calls will not match as desired. For marker types used with `@args`, use `RUNTIME` unless there is another design reason.

### 9.2. Annotations on Interfaces and Classes Are Not Always Equivalent

If an annotation is placed only on an **interface**, do not assume `getClass()` of an implementation carries that annotation. Java `@Inherited` (if used) affects certain cases of **inheriting annotations from a superclass**, and does not automatically propagate type annotations from interfaces to implementing classes.

`@args` inspects annotations on the actual argument's runtime type; therefore, check:
- Is the annotation placed on the **actual implementation class** or only on an interface?
- Is the runtime class a subclass or a proxy class?
- Does the annotation have `@Inherited`, and does it apply to the hierarchy in question?
- How will the Spring/AspectJ expression matcher view the runtime object in the actual configuration?

The safe approach is to **design clear annotation boundaries** and write tests against real classes/runtime arguments. Do not use `@args` to replace all forms of hierarchy annotation lookup.

### 9.3. The Argument Itself Is a Proxy

If **a Spring AOP proxy** is passed as an argument to another service, the argument's runtime class may be a JDK dynamic proxy or a CGLIB subclass, different from the implementation class in source code. Having the annotation on the implementation does not guarantee the proxy class exposes the same metadata in the exact way the `@args` matcher expects.

When applying `@args` to arguments that are framework proxies:
1. Identify the proxy type of the **argument object**, not just the proxy of the advised service.
2. Verify the matcher by testing with actual runtime arguments.
3. If business logic needs the annotation on the **target class behind the proxy**, consider resolving the target type using Spring utilities in deliberate metadata-checking code, rather than assuming `@args` unwraps every proxy.

### 9.4. null Has No Runtime Class

A variable `Object value = null` has no runtime class from which to read a type annotation. Do not assume the pointcut can infer "this is an annotated type" solely from the parameter declaration or generic type. Use explicit null validation, and if `null` is a valid input, test the behavior of your actual Spring AOP version and advice before relying on it.

### 9.5. Collections Are Not Inspected Recursively

A method `submit(List<ReviewedOrder> values)` receives a `List` object. `@args(Reviewed)` does not automatically iterate elements to look for `@Reviewed`. Similarly, a wrapper `Envelope<ReviewedOrder>` does not become an annotated runtime class just because its generic type argument carries an annotation. To inspect nested contents, write explicit traversal logic or use an appropriate validation layer.

### 9.6. Spring AOP Only Sees Calls Through Proxies

In Spring Framework, `@args` remains bound by all Spring AOP proxy boundaries:

- The target bean must be Spring-managed and discovered by the advice infrastructure.
- Calls must go through the Spring-managed proxy, not an object created with `new`.
- Self-invocation like `this.submit(payload)` inside the same target bypasses advice.
- Class-based proxies cannot intercept `final`/`private` methods via overriding.
- JDK proxies expose only methods belonging to the proxied interfaces; method availability can differ from CGLIB.
- `@args` does not turn Spring proxy AOP into a mechanism that intercepts constructors, field access, or unproxied method calls.

**Do not change pointcuts to fix self-invocation.** If a business rule requires advice on an internally called method as well, extract the operation into a collaborating bean and call it externally through the Spring bean proxy.

### 9.7. Dynamic Matching Has Runtime Overhead

`@args` depends on **actual arguments**, which can vary between two calls to the same method. Hence, this condition usually cannot be fully decided from the method signature alone when Spring creates proxies. AOP infrastructure may have to perform additional evaluation on each invocation.

Spring AOP documentation distinguishes static and runtime `MethodMatcher`s; runtime matching receives `Object... args` to inspect argument values. Therefore:
- Restrict with `execution(...)`/`within(...)` to the service methods that genuinely need it.
- Do not overuse `@args` application-wide just to check an annotation that a service could check explicitly once.
- Measure performance under real workloads if this is a hot path; do not infer a fixed overhead figure.
- Do not store per-invocation mutable business state in fields of a singleton aspect in concurrent systems unless thread safety has been designed.

## 10. Choosing the Right Pointcut for the Requirement

| Requirement | Appropriate tool |
| --- | --- |
| Select `submit` method whose **declared** parameter is `Object` | `execution(* *.submit(Object))` |
| Select calls whose runtime argument belongs to a specific class/interface | `args(TypePattern)` |
| Select calls where the **runtime class of the actual argument** carries `@Reviewed` | `@args(Reviewed)` |
| Select methods marked `@AuditedOperation` | `@annotation(AuditedOperation)` |
| Select calls on an annotated service target type | `@target(Marker)` when semantics are target runtime annotation |
| Select methods declared in an annotated type | `@within(Marker)` |
| Select Spring beans by name | `bean(namePattern)` |
| Select both layer and runtime argument annotation | `within(service..*) && @args(Reviewed)` |
| Check annotations directly on Java parameter declarations | Separate validation or reflection/advisor logic; `@args` does not perform this check |
| Inspect every item in a `List` or nested object | Iterate the argument or use appropriate validation; `@args` does not traverse deeply |

### Self-Check Questions

**Scenario A:** Service declares `void save(Object x)`, and the actual argument is an instance of `AnnotatedInvoice` marked with `@Reviewed`. If the call goes through a Spring proxy and the pointcut is `@args(Reviewed)`, can the advice run?

**Answer:** Yes. The runtime type of the actual argument is annotated.

**Scenario B:** Service declares `void save(@Reviewed Object x)`, while the passed object belongs to `PlainInvoice` with no type-level annotation. Will `@args(Reviewed)` advice run due to the annotation on the parameter declaration?

**Answer:** Annotations on method parameters cannot serve as the basis for `@args`; furthermore, `@Reviewed` targets `TYPE` in this example, so annotating a parameter like that would not even be valid. To mark parameters, you need an annotation with `@Target(PARAMETER)` and a different checking mechanism.

**Scenario C:** `@Reviewed` is placed only on the `List` element type while the method accepts `List<Object>`. Should you expect `@args(Reviewed)` to inspect each item automatically?

**Answer:** No. It checks the runtime type of the actual argument—the `List` object—without automatically traversing elements.

**Scenario D:** Inside the target bean, `process()` calls `this.submit(new FlaggedPayload())`. The payload class carries `@Reviewed`. Does the advice run?

**Answer:** With proxy-based Spring AOP, self-invocation bypasses the proxy so advice does not run for that internal call, even though a pointcut based on runtime arguments would match if the invocation went through the proxy.

## 11. Workflow for Debugging an @args Pointcut That Does Not Run

1. **Verify annotation definition.** Does it have `@Target(TYPE)` and `@Retention(RUNTIME)`? Is the annotation placed on the actual runtime class?
2. **Verify argument count.** Single-position `@args(Reviewed)` matches methods with one actual argument; multi-argument methods need a pattern matching the positions.
3. **Verify runtime class.** Print `argument.getClass()` in test code when non-null; do not look only at the parameter's declared type.
4. **Verify Spring bean/proxy.** Is the aspect a bean, is `@EnableAspectJAutoProxy` or Boot AOP auto-config active, and is the target called through a proxy?
5. **Verify static conditions.** If combined with `execution(...)` or `within(...)`, do the method and service match?
6. **Verify no self-invocation.** If called from another method on `this`, proxy advice is bypassed.
7. **Verify the argument is not an unexpected proxy.** If the argument object is proxied by Spring or another framework, its runtime class and metadata may differ from expectations.
8. **Verify null/collection semantics.** Do not infer annotations on nested elements or `null` variables.
9. **Check advice binding.** If using `@args(reviewed)`, the advice parameter must have the matching annotation type and Spring must be able to resolve the binding name.
10. **Write integration tests** with at least an annotated input, an unannotated input, and a broadly typed variable like `Object` to catch static vs. runtime type mix-ups.

## 12. Conclusion

In a Spring Aspect, `@args` is a pointcut designator for selecting method calls based on **annotations on the runtime types of actual arguments**. It fits situations where multiple payload classes pass through a broadly typed service API yet only certain marked payload types require extra handling.

Remember three boundaries:

- **Type:** `@args` inspects runtime type annotations on arguments, not method annotations or parameter-declaration annotations.
- **Shape:** Single-position `@args(Annotation)` constrains argument count and position; collections are not traversed deeply.
- **Proxy:** Only invocations through a Spring AOP proxy are advised; a matching pointcut still skips self-invocation bypassing the proxy.

Robust designs typically combine `execution`/`within` to narrow the layer with `@args` to check runtime conditions, use `RUNTIME` annotations, and include integration tests for subtypes, proxies, `null`, and key overloaded methods.

### Spring Reference Documentation

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): describes `@args` as a runtime annotation on actual argument types, with a single-parameter example; compares with `args`, `@target`, `@within`, and `@annotation`.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): advice parameters, `JoinPoint.getArgs()`, and `@args` binding.
- [Spring Framework — Spring AOP Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): static/dynamic `MethodMatcher` and evaluating `matches(Method, Class, Object...)`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundaries, JDK/CGLIB, and self-invocation.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): configuring Spring AOP and registering `@Aspect` as a Spring bean.
