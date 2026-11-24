# Distinguishing Reading Metadata with Spring APIs from Matching AspectJ Expressions in Spring AOP

## 1. Purpose and Scope

When building a custom annotation for a Spring bean, **two tasks** must be separated:

- **Reading metadata with Spring APIs:** actively looking up what annotations a `Method`/`Class` carries, what their attribute values are, and whether any meta-annotations or `@AliasFor` are merged by Spring.
- **Matching AspectJ expressions in Spring AOP:** declaring a pointcut so Spring selects which method executions run advice when a call **goes through a Spring proxy**. For example `@Around("@annotation(marker)")`.

**Finding an annotation does not mean advice is guaranteed to run.** Both approaches may inspect the same annotation, yet differ in inputs, search policies, and trigger timing.

The scope covers only **Spring Aspects / proxy-based Spring AOP** and Spring's annotation processing APIs; it does not cover general AspectJ theory or weaving by the AspectJ compiler/load-time agent.

## 2. Direct Comparison

| Criterion | Spring Metadata Reading APIs | AspectJ Pointcut in Spring AOP |
|---|---|---|
| Goal | Retrieve an annotation or configuration values | Select join points where advice applies |
| Trigger | Application code calls the API | Spring builds advisor/proxy and intercepts matching calls |
| Subject inspected | `AnnotatedElement`, `Method`, `Class<?>` | Method execution, target class, and proxy |
| Typical tools | `AnnotatedElementUtils`, `AnnotationUtils`, `AopUtils`, `BridgeMethodResolver` | `@annotation`, `@within`, `@target`, `execution`, `bean` |
| Result | Annotation, metadata, or `null` | Match/no match; can bind annotation into advice |
| Timing | Whenever code reads it, even if the method is never called | When Spring AOP applies advice to a call through a proxy |
| Composed annotations | `findMergedAnnotation` understands merge/meta-annotations/aliases per Spring rules | Does not equate by default to Spring API "merged annotation" policy |
| Common mistake | Reading the wrong method from an interface or proxy | Annotation exists yet self-invocation, missing proxy, or wrong pointcut |

Example: `AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class)` can return the annotation before `method` ever runs. Meanwhile, `@Around("@annotation(traceAction)")` only runs if Spring AOP actually intercepts a matching method execution.

## 3. Reading Metadata Properly with Spring

### 3.1. Java Reflection and Spring's Annotation APIs

For an annotation placed directly on a method, standard reflection can read it:

```java
Method method = OrderService.class.getMethod("checkout", String.class);
TraceAction marker = method.getAnnotation(TraceAction.class);
```

If the application uses meta-annotations/composed annotations, attribute aliases, or needs hierarchy annotation lookup, Spring provides utilities:

```java
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class);
```

Several APIs differ in lookup policy:

- `AnnotatedElementUtils.getMergedAnnotation(...)`: retrieves a merged annotation from an element with matching meta-annotations.
- `AnnotatedElementUtils.findMergedAnnotation(...)`: searches more broadly across the corresponding hierarchy and constructs a merged annotation.
- `AnnotationUtils.findAnnotation(...)`: utility to look up annotations via Spring's own search mechanism; do not assume it behaves identically to `findMergedAnnotation` in all cases.
- `MergedAnnotations`: selects a `SearchStrategy` and traverses detailed metadata when search rules must be explicit.

`@AliasFor` only has meaning under Spring's synthesized/merged annotation handling. An `@annotation` expression in an AspectJ pointcut does not automatically apply all lookup/merge rules of those APIs.

### 3.2. Proxy Class Differs from Target Class

A bean wrapped by Spring AOP may be a JDK dynamic proxy or a subclass proxy. `bean.getClass()` is not necessarily the class declaring the business method.

If you need to read annotations on the implementation:

```java
Class<?> targetClass = AopUtils.getTargetClass(bean);
Method method = targetClass.getMethod("checkout", String.class);
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(method, TraceAction.class);
```

`AopUtils.getTargetClass` retrieves the target type from a Spring proxy; from there you read the implementation method instead of mistakenly reading a proxy method. In applications with interfaces and overriding, annotation placement still needs clear consideration.

When the initial method comes from an interface/signature, you can find the most specific method and resolve compiler-generated bridge methods for generics:

```java
Method interfaceMethod = /* Method already obtained from signature/interface */;
Class<?> targetType = AopUtils.getTargetClass(bean);
Method specificMethod =
        AopUtils.getMostSpecificMethod(interfaceMethod, targetType);
Method userMethod =
        BridgeMethodResolver.findBridgedMethod(specificMethod);
TraceAction marker =
        AnnotatedElementUtils.findMergedAnnotation(userMethod, TraceAction.class);
```

This is an illustrative snippet **inside code that already has `bean` and `interfaceMethod` variables**, not a standalone Java program. `AopUtils.getMostSpecificMethod` and `BridgeMethodResolver` solve two distinct problems: locating the implementation method and resolving bridge methods.

### 3.3. Being Readable Does Not Mean Proxy-Interceptable

Metadata APIs inspect a reflective object, even if the method is never called. Spring AOP only runs advice when a method execution falls within the pointcut scope and **the call goes through a proxy**. A startup scan reading every annotation in a package does not cause advice to execute on those methods.

## 4. Pointcut Matching in a Spring Aspect

For method annotations, the clearest form is:

```java
@Around(value = "@annotation(traceAction)", argNames = "traceAction")
public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
        throws Throwable {
    System.out.println("AOP: " + traceAction.value());
    return pjp.proceed();
}
```

- `@annotation(traceAction)` identifies method executions matching the annotation and **binds the annotation instance** into the `traceAction` parameter.
- `argNames` makes the binding variable name explicit. `ProceedingJoinPoint` is a special parameter of around advice.
- `pjp.proceed()` lets the underlying method continue executing. Omitting it in `@Around` changes method behavior.
- If only filtering by annotation type, the fully-qualified type name `@annotation(demo.TraceAction)` can be used.

Related expressions supported by Spring AOP:

| Expression | Subject Matched | Application |
|---|---|---|
| `@annotation(demo.TraceAction)` | Annotation attached to method execution | Policy by method marker |
| `@within(demo.AuditedType)` | Executions within a marked type, per pointcut rules | Policy by type declaration |
| `@target(demo.AuditedType)` | Runtime target type carrying matching annotation | Policy by target type |
| `execution(public * demo.service..*(..))` | Method signatures within a package | Restricting a group of methods |
| `bean(orderService)` | Spring bean named `orderService` | Limiting to a bean (Spring-specific extension) |

**Putting `@TraceAction` on a class does not mean it matches `@annotation` on a method.** If the annotation belongs to a type, use the right type-level pointcut and understand the difference between `@within`/`@target`.

Expressions can be combined:

```java
@Around(value =
        "execution(public * demo.service..*(..)) && @annotation(traceAction)",
        argNames = "traceAction")
public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
        throws Throwable {
    return pjp.proceed();
}
```

This is an example placed inside an `@Aspect` class that imports the corresponding types. `demo.service` is only a sample package and must be changed to match the real project. Combine `execution` to prevent advice from matching too broadly.

## 5. Runnable Java 17+ Example with Spring Boot

This example uses Spring Boot 3.3.x, Spring AOP, and the `@TraceAction` annotation to demonstrate the two independent processing paths. Files are placed at the proper paths; the common Java package is `demo`.

**`settings.gradle`**

```groovy
rootProject.name = 'spring-aop-metadata-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**`src/main/java/demo/TraceAction.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TraceAction {
    String value();
}
```

`RetentionPolicy.RUNTIME` is required to read the annotation at runtime and for annotation-based pointcuts to work. `@Target(METHOD)` specifies this is a method marker.

**`src/main/java/demo/OrderService.java`**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @TraceAction("checkout")
    public String checkout(String orderId) {
        return "OK:" + orderId;
    }
}
```

**`src/main/java/demo/MetadataExplorer.java`**

```java
package demo;

import java.lang.reflect.Method;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

@Component
public class MetadataExplorer {
    private final OrderService orderService;

    public MetadataExplorer(OrderService orderService) {
        this.orderService = orderService;
    }

    public void showMetadata() throws NoSuchMethodException {
        Class<?> targetClass = AopUtils.getTargetClass(orderService);
        Method method = targetClass.getMethod("checkout", String.class);
        TraceAction marker =
                AnnotatedElementUtils.findMergedAnnotation(
                        method, TraceAction.class);
        System.out.println(
                "METADATA: " + (marker == null ? "missing" : marker.value()));
    }
}
```

`showMetadata()` only reads metadata on `checkout`; it **does not call `checkout`**, and therefore does not trigger advice for this method.

**`src/main/java/demo/TrackingAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {
    @Around(value = "@annotation(traceAction)", argNames = "traceAction")
    public Object trace(ProceedingJoinPoint pjp, TraceAction traceAction)
            throws Throwable {
        System.out.println("AOP: " + traceAction.value());
        return pjp.proceed();
    }
}
```

Spring creates an advisor/proxy from `@Aspect` when `spring-boot-starter-aop` is present and Boot's AOP configuration is active. The advice applies only to method executions matching `@annotation`, binding the marker to read `value()`.

**`src/main/java/demo/AopMetadataDemoApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AopMetadataDemoApplication implements CommandLineRunner {
    private final MetadataExplorer explorer;
    private final OrderService orderService;

    public AopMetadataDemoApplication(
            MetadataExplorer explorer, OrderService orderService) {
        this.explorer = explorer;
        this.orderService = orderService;
    }

    public static void main(String[] args) {
        SpringApplication.run(AopMetadataDemoApplication.class, args);
    }

    @Override
    public void run(String... args) throws Exception {
        explorer.showMetadata();
        System.out.println("RESULT: " + orderService.checkout("A1"));
    }
}
```

Run with the project's compatible Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows: `.\gradlew.bat bootRun`. For a new project without a wrapper, `gradlew`/`gradlew.bat` must be created or supplied; writing `build.gradle` alone does not generate the wrapper.

The **application lines** printed in order (Spring Boot may print extra startup logs):

```text
METADATA: checkout
AOP: checkout
RESULT: OK:A1
```

Interpretation: `METADATA` appears before the method call because the Spring API reads the annotation; `AOP` appears when the `orderService.checkout` call goes through the proxy and matches the pointcut; `RESULT` is the method's value after `pjp.proceed()`.

If `@TraceAction` is removed from `checkout` and no other advisor is added, metadata prints `missing` and the call does not run the `trace` advice. If only `explorer.showMetadata()` runs without calling `checkout`, metadata is still read, yet there is no `AOP` line.

## 6. Scenarios That Commonly Cause Misunderstanding

### 6.1. Self-invocation: Annotation Exists Yet Advice Does Not Run

Suppose we add to `OrderService`:

```java
public String process(String id) {
    return checkout(id); // equivalent to this.checkout(id)
}
```

Another bean calls `orderService.process("A1")`. The internal call from `process` to `checkout` executes directly within the target without passing through the Spring AOP proxy; the `checkout` advice does not run for this call. However, `AnnotatedElementUtils.findMergedAnnotation` still finds `@TraceAction` on the `checkout` method.

A clean design typically places the advised method in a bean that callers invoke through a Spring proxy. This is a characteristic of **Spring AOP proxy-based interception**, not a sign that the annotation was lost.

### 6.2. Annotations on Interfaces vs. Implementations

With JDK dynamic proxies, the signature may represent an interface method; the actual annotation may reside on the implementation or vice versa. When using `MethodSignature` inside advice for lookup, the returned method is not necessarily the target's method.

Lookup pattern inside advice (`pjp` variable already available):

```java
Method signatureMethod =
        ((org.aspectj.lang.reflect.MethodSignature)
                pjp.getSignature()).getMethod();
Class<?> targetType =
        org.springframework.aop.support.AopUtils.getTargetClass(pjp.getTarget());
Method specific =
        org.springframework.aop.support.AopUtils.getMostSpecificMethod(
                signatureMethod, targetType);
Method bridged =
        org.springframework.core.BridgeMethodResolver.findBridgedMethod(specific);
TraceAction marker =
        org.springframework.core.annotation.AnnotatedElementUtils
                .findMergedAnnotation(bridged, TraceAction.class);
```

This is an **illustrative snippet inside advice**, not a standalone Java file. For annotations placed only on interfaces/hierarchies, the pointcut must be tested on the exact proxy type and declaration site. `findMergedAnnotation` may see the annotation per Spring's search rules, yet that does not automatically guarantee `@annotation` matches identically.

### 6.3. Composed Annotations / Meta-Annotations

If a composed annotation merged by Spring via `@AliasFor` is defined, `findMergedAnnotation` can return the merged annotation where simple reflection returns none. Do not assume on that basis that `@annotation(demo.TraceAction)` also inherits all of Spring's merged semantics.

There are two design directions: (1) use the direct annotation targeted by the pointcut; (2) use an appropriate `execution` pointcut and then filter metadata inside the advice with `AnnotatedElementUtils`. Approach (2) has a broader interception scope and requires performance consideration. Choose it only when Spring's lookup/merge semantics are genuinely required.

### 6.4. Spring AOP Interception Limits

- Only Spring-managed beans get proxies/advisors created by Spring AOP; `new OrderService()` receives no container advice.
- Spring AOP supports method executions; it does not intercept field access, constructor execution, or other join points like AspectJ weaving.
- Private methods cannot be advised through proxy mechanisms; final methods cannot be overridden in subclass proxies. With interface-based proxies, methods are exposed through interfaces.
- Annotation matching requires runtime retention; `@Retention(SOURCE)` or `CLASS` is unsuitable for runtime annotation inspection in the examples.
- Annotations like `@Transactional` have Spring Transaction's own attribute lookup/advisor system; do not arbitrarily mimic it with a simple `@annotation(Transactional)` and assume identical results.

### 6.5. Is Reflection Needed on Every Advice Call?

If `@annotation(traceAction)` is already bound, use `traceAction.value()` directly. Only trace back to `Method` when additional metadata from the target class, aliases/composed annotations, generic methods, or other annotations must be read. For high-frequency advice, avoid unnecessary repeated reflection; cache by method/target after measuring and ensuring the cache key is accurate.

## 7. Checklist When Metadata Exists Yet the Spring Aspect Does Not Run

1. Does the call to the bean go **through the Spring proxy**, or is it calling `new` / `this.method()`?
2. Does the pointcut use `@annotation` for methods or `@within`/`@target` for types? Where is the annotation actually placed?
3. Does the annotation have `@Retention(RUNTIME)` and the proper target element?
4. Are interface/proxy methods being confused with implementation methods? Were `getMostSpecificMethod` and bridge methods checked?
5. Is the method within Spring AOP's supported scope and interceptable under the proxy strategy?
6. If using meta-annotations or `@AliasFor`, was the **pointcut tested** independently of `findMergedAnnotation` results?
7. Is the `@Aspect` a Spring bean, and are Spring AOP dependencies/configurations enabled?
8. Is "seeing the annotation at startup" being confused with "the method actually being called through a proxy"?

**Key point to grasp:** Spring APIs answer "what metadata is on the class/method I am inspecting?"; AspectJ pointcuts in Spring AOP answer "which method calls through a Spring proxy match to run advice?". Same annotation, yet two different questions, two mechanisms, and distinct limits.