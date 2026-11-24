# Keeping Annotation APIs Stable When Reusing Spring AOP Aspects Across Modules

## 1. The Problem to Solve

When multiple Spring modules share an aspect, the annotation developers place on services is the **public API between business modules and AOP infrastructure**. For example, the order module uses `@TrackedOperation("checkout")` and the payment module uses `@TrackedOperation("charge")`; both expect the aspect to recognize the same contract even as logging, metrics, or tracing implementations evolve. Changing the package, annotation name, attribute names, or attribute semantics arbitrarily can break compilation, cause already-compiled code to fail at runtime, or silently stop advice from applying without clear errors.

Goal: modules using the annotation depend only on a **stable contract**, while the Spring AOP aspect and bean registration can be updated independently; all contract changes are tested and released under control. The focus here is how Spring AOP discovers and applies annotations in multi-module applications.

## 2. Separating the Annotation Contract from the Spring Aspect

One organization with Java 17+/Spring Boot 3.x:

```text
operation-contract/            # API JAR: public annotation, no Spring required
  com/example/contract/TrackedOperation.java

operation-spring/              # Runtime JAR: @Aspect and Spring Boot auto-configuration
  com/example/spring/TrackedOperationAspect.java
  com/example/spring/TrackedOperationAutoConfiguration.java
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

checkout-app/                   # Spring Boot application using the annotation
  com/example/checkout/CheckoutService.java
  com/example/checkout/CheckoutApplication.java

billing-app/                    # another application able to use the same contract
```

Dependency relationship: `operation-spring → operation-contract`; each application depends on `operation-contract` to compile and `operation-spring` to enable AOP behavior. Applications need `spring-boot-starter-aop` at runtime (or equivalent Spring AOP setup). `operation-contract` is a small JAR holding only the contract; do not place `@Aspect`, `@Component`, loggers, or configuration beans in this JAR.

The stability anchor is the annotation's **fully qualified class name** (FQCN) along with its elements and semantics. The `TrackedOperationAspect` implementation name, sink type, or log output format are internal details of the Spring module.

## 3. Declaring the Contract for Proxy-Based Spring AOP

File `operation-contract/src/main/java/com/example/contract/TrackedOperation.java`:

```java
package com.example.contract;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedOperation {
    String value();
    String category() default "business";
}
```

- `RUNTIME` is required for Spring AOP to read the annotation at runtime. Changing to `CLASS` or `SOURCE` prevents `@annotation`-based advice from recognizing the annotation during normal runtime execution.
- `METHOD` establishes the public promise: the annotation applies to methods. If classes must also be supported later, a suitable pointcut must be designed at the same time; adding `TYPE` to `@Target` **does not automatically** make `@annotation` apply to every method in a class.
- `value()` is the required business operation name and must keep consistent semantics; `category()` has a default so existing code using `@TrackedOperation("checkout")` continues to work.
- `@Documented` supports Javadoc documentation, and is not an AOP activation condition. Do not blindly add `@Inherited` expecting method annotations to be inherited: Java's `@Inherited` only applies to class-level annotations, and does not solve proxies or method overrides.

If modules are released independently, publish the contract in a clearly versioned artifact; keep package `com.example.contract` and element names stable across compatible upgrades.

## 4. Spring Aspect Consuming the Published Contract

File `operation-spring/src/main/java/com/example/spring/TrackedOperationAspect.java`:

```java
package com.example.spring;

import com.example.contract.TrackedOperation;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TrackedOperationAspect {

    @Around(value = "@annotation(tracked)", argNames = "tracked")
    public Object record(ProceedingJoinPoint joinPoint,
                         TrackedOperation tracked) throws Throwable {
        try {
            Object result = joinPoint.proceed();
            System.out.printf(
                    "[track] %s category=%s status=SUCCESS%n",
                    tracked.value(), tracked.category());
            return result;
        } catch (Throwable error) {
            System.out.printf(
                    "[track] %s category=%s status=FAILURE type=%s%n",
                    tracked.value(), tracked.category(),
                    error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

`@annotation(tracked)` is the Spring AOP pointcut for proxy-handled method executions carrying the corresponding annotation; `tracked` is also bound into the advice to read attributes from the contract. `joinPoint.proceed()` invokes business logic exactly once and returns the original result; on error, the advice rethrows the exact original `Throwable` so it does not alter the service's error contract. `argNames` makes annotation binding explicit, without relying on compiler parameter name information.

The example uses `System.out` to show output directly; in real products, replace with a logger, metrics, or a dedicated sink. Avoid logging parameters containing passwords/sensitive data. Printing `SUCCESS` when the method returns **does not prove a `@Transactional` transaction has committed**: when advice runs depends on interceptor ordering. If durable post-commit auditing is required, design around transactions/events separately and verify advisor ordering.

## 5. Registering the Aspect at the Right Module Boundary

Spring Boot 3.x can auto-configure the aspect from the `operation-spring` JAR without forcing every application to manually scan the library package. File `operation-spring/src/main/java/com/example/spring/TrackedOperationAutoConfiguration.java`:

```java
package com.example.spring;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class TrackedOperationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(TrackedOperationAspect.class)
    TrackedOperationAspect trackedOperationAspect() {
        return new TrackedOperationAspect();
    }
}
```

The resource file at the **exact path** `operation-spring/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains a single line:

```text
com.example.spring.TrackedOperationAutoConfiguration
```

JAR packaging must preserve this resource. When an application has `operation-spring` and `spring-boot-starter-aop` dependencies, Spring Boot loads auto-configuration and has the machinery to create Spring AOP proxies. The aspect is managed as a Spring bean, while business modules only need to import the annotation from `operation-contract`.

Conditions of use: both JARs must share compatible contract versions; do not mix artifacts containing **two annotation classes with different FQCNs** and expect `@annotation` to treat them as one. When the library needs to allow disabling the feature, add a stably named property with `@ConditionalOnProperty`, document the default, and test existing apps before changing defaults. If not using Boot auto-configuration, the application can `@Import` a `@Configuration` declaring the aspect; pick one consistent mechanism to avoid creating duplicate equivalent beans/advices.

## 6. Applications Using the Annotation Without Knowing Aspect Details

File `checkout-app/src/main/java/com/example/checkout/CheckoutService.java`:

```java
package com.example.checkout;

import com.example.contract.TrackedOperation;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @TrackedOperation("checkout")
    public String checkout() {
        return "OK";
    }
}
```

File `checkout-app/src/main/java/com/example/checkout/CheckoutApplication.java`:

```java
package com.example.checkout;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService service) {
        return args -> System.out.println(service.checkout());
    }
}
```

These are the Java files for the multi-module example; they run inside a Spring Boot project with corresponding dependencies and build plugins configured, not as programs runnable with plain `javac` since they use Spring and AspectJ. When the project's Gradle setup configures Boot and module paths as above, you can run `./gradlew :checkout-app:bootRun` (Windows: `gradlew.bat :checkout-app:bootRun`).

Alongside Spring Boot's startup lines, under a valid proxy setup two lines produced by the example appear in exact order:

```text
[track] checkout category=business status=SUCCESS
OK
```

The `billing-app` module can simply place `@TrackedOperation("charge")` and use the corresponding dependencies; there is no need to copy `TrackedOperationAspect` source or create a same-named annotation in another package.

## 7. Contract Changes: Safe or Compatibility-Breaking?

| Change | Risk to Consuming Modules | How to Handle |
| --- | --- | --- |
| Keep FQCN, `value()` signature, `@Retention(RUNTIME)`, `@Target(METHOD)`, and semantics | Usually compatible | Aspect implementation can be upgraded independently |
| Add element `String category() default "business"` | Previously compiled/annotated code still has a valid value | Retest behavior when the new default applies |
| Add an element **without** a default | Old annotation sources fail to compile due to missing element; precompiled classes may also fail when read at runtime | Treat as a breaking change; design a default or major version |
| Rename `value()` to `operation()` or remove element | Sources using old name break; old aspect and binaries may fail | Keep old alias during transition or release a major version |
| Change package or rename `TrackedOperation` | New FQCN is a different annotation; old pointcut stops matching | Maintain a period accepting both old and new annotations, then migrate under control |
| Change `RUNTIME` to `CLASS`; narrow `@Target` | AOP fails to recognize it or sources stop compiling | Do not change while still honoring the old contract |
| Change default value, meaning of `value`, or recorded operation names | May compile fine yet alter logs/metrics/tracing or dashboards | Treat as an API behavior change; test and publish migration notes |
| Change only logging implementation, sink, or internal advice logic | Caller annotations need no changes | Verify observable behavior compatibility and advice ordering |

Even when a change is valid at the Java binary level, **Spring AOP behavioral compatibility** still requires testing: an aspect can alter its pointcut, bean registration condition, or advisor order without causing compile errors. Do not treat a passing build as proof that the aspect still executes.

### Release/Migration Strategy

1. Publish `operation-contract` as a versioned API, documenting annotation placement, the meaning of every attribute, defaults, and scope of application.
2. Prefer **adding optional elements with defaults**; do not change or remove elements currently used by callers. If semantics must change, introduce a clearly named new element and mark the old one `@Deprecated` during a transition period.
3. When forced to change an annotation FQCN, keep the old annotation and add explicit handlers for both in a transition release; guard against recording events twice if a method carries both. Remove the old path only in a major release with migration instructions.
4. For independent applications, align/pin `operation-contract` versions between compile classpath and runtime classpath; release the Spring aspect with its supported contract version range.
5. Maintain compatibility tests with an application using the annotation in the legacy syntax; do not test consumers only after updating them to the new API.

## 8. Spring AOP Pitfalls Easily Mistaken for API Bugs

Spring AOP is proxy-based, so preserving the annotation contract is still insufficient if calls do not pass through the proxy:

- **Self-invocation:** `this.checkout()` from another method in the same bean does not go through the Spring AOP proxy. Move operations needing interception to a separate bean or call from an external bean.
- **Objects not managed by Spring:** manually calling `new CheckoutService()` will have no AOP proxy.
- **Final/private methods and proxies:** private methods are not intercepted by Spring AOP; final methods cannot be overridden by CGLIB subclass proxies. With JDK dynamic proxies, calls must go through the proxy's interface. Prefer public methods invoked through Spring beans.
- **Placing annotations on interfaces/implementations:** annotation placement and proxy type can affect matching. Standardize on placing `@TrackedOperation` on public methods of concrete services in this example, and write integration tests if applications use interface-based proxies.
- **`@annotation` and `@within`/`@target`:** `@annotation` applies to annotations on matched methods; if extending the contract for class-level annotations, write the corresponding pointcut and define which takes precedence when both class and method carry the annotation.
- **Missing runtime registration:** the contract dependency allows compiling yet does not enable the aspect by itself. Check the auto-configuration JAR, AOP starter, aspect bean, and actual proxy. If an application lacks the AOP starter, the annotation becomes inert metadata and produces none of the expected behavior.
- **Multiple aspects/advisors:** a single method can have `@Transactional`, `@Async`, and multiple advices. When timing, transactions, or post-commit outcomes are part of the contract, test ordering with `@Order`/advisor config and actual runtime behavior.

## 9. Testing Checklist When Upgrading a Shared Aspect Version

Integration tests should start the Spring context of a real application, inject services from the context, and invoke through bean proxies. Minimum cases: an annotated method enters advice exactly once; an unmarked method is not recorded; default attribute `category="business"` is read properly; custom values flow through pointcut binding; return values remain unchanged; original exceptions are rethrown; works across two different consumer modules; enable/disable configuration (if supported by public API) behaves consistently; a consumer using legacy annotation syntax still works after upgrading the JAR.

Spring tests can also use `AopUtils.isAopProxy(service)` to detect missing proxies, yet checking the proxy **is not enough**: assert events/logs/metrics from the advice to prove the pointcut actually matched. If output is logs, use a test appender/mock sink rather than relying on Boot startup log strings. For new annotation elements, keep a test with unchanged legacy caller syntax and verify defaults.

## 10. Practical Rules to Apply

- **Stable contract:** FQCN, `@Retention`, `@Target`, elements, defaults, and annotation semantics are treated as a versioned API.
- **Controlled Spring runtime changes:** aspect, pointcut, bean registration, advisor order, and proxyability are tested at the integration level.
- **Independent consumers:** business code imports only one annotation from the shared artifact; it does not depend on the aspect's name or instantiation mechanism.
- **Explicit migration:** add attributes with defaults when possible; provide time-boxed dual support if renaming classes/packages; never change semantics silently.

Maintaining these boundaries lets multiple Spring modules reuse one annotation without having to rewrite sources across all consumers whenever the aspect implementation changes.
