# Using @annotation to Select Annotated Methods in Spring AOP

## 1. Lesson Objectives

In a Spring Framework application, instead of matching method names by a fixed naming convention, we can explicitly mark **Spring bean methods** that need cross-cutting logic with an annotation and write a Spring AOP pointcut using `@annotation`.

This lesson specifically answers:

1. Which method executions does `@annotation(...)` select in Spring AOP, and how does it differ from plain `execution(...)`?
2. How do you write a custom `@Retention(RUNTIME)`, `@Target(METHOD)` annotation and use `@Before` to intercept only marked methods?
3. How do you **bind the annotation instance to the advice** to read the annotation's `value`/`tag` attribute?
4. Can `@annotation` be combined with `execution` to restrict to the exact package, class, and service layer?
5. Why does an annotated method still not run advice when called via `this.method()`, on a `new` object, or on a method not interceptable through a Spring proxy?
6. How do you observe and diagnose results using a Spring AOP proxy and an advice counter?

**Scope limitation:** This is **Spring AOP on Spring-managed beans**, using `@AspectJ` syntax while executing via JDK/CGLIB proxies. Do not confuse this with AspectJ bytecode weaving, and do not treat annotations as JVM interceptors for arbitrary objects.

## 2. Understanding `@annotation` in the Context of Spring AOP

Spring AOP supports the `@annotation` pointcut designator to select **method executions where the corresponding method has the specified annotation**. This is a join point matching condition when the call **goes through a Spring AOP proxy**.

Example annotation:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

With methods on a Spring bean:

~~~java
@TrackedAction("checkout")
public void checkout() {
    // ...
}

public void preview() {
    // ...
}
~~~

If both calls go through the bean proxy and satisfy advice conditions, only `checkout()` matches `@annotation(demo.TrackedAction)`; `preview()` does not match merely by being in the same class.

### Two Important Usage Forms

**Selecting an annotation by type name:**

~~~java
@Before("@annotation(demo.TrackedAction)")
public void before() {
    System.out.println("Annotated method");
}
~~~

`demo.TrackedAction` is the fully qualified name of the **annotation type**. This advice only needs to know the method is marked, without reading annotation attributes.

**Binding the annotation instance to an advice parameter:**

~~~java
@Before(value = "@annotation(trackedAction)", argNames = "trackedAction")
public void before(TrackedAction trackedAction) {
    System.out.println(trackedAction.value());
}
~~~

In this form, `trackedAction` is a **binding variable name**, not the annotation class name. Spring infers the `TrackedAction` type from the advice parameter, binds the matching annotation object, and lets you read `trackedAction.value()`.

These are two illustrative snippets that must be placed inside an `@Aspect` registered as a Spring bean, not complete Java programs. Do not put **both** advices into the same example if you only want a single log line: when two advices both match, both can run.

Syntax notes:

- `@annotation(demo.TrackedAction)`: matches by **annotation type**.
- `@annotation(trackedAction)`: binds the annotation by **variable name**; that name must match the advice parameter receiving the annotation (or be inferred properly by Spring).
- You can specify `argNames = "trackedAction"` explicitly to avoid relying on parameter names after compilation. When the advice has `JoinPoint` as its **first** parameter, you do not need to list the `JoinPoint` parameter name in `argNames`.
- For multi-condition pointcuts, use `&&` and `||` as in AspectJ pointcut expressions, e.g., `execution(public * demo.AuditService.*(..)) && @annotation(trackedAction)`.

### How Does `@annotation` Differ from `execution`?

| Pointcut | Primary matching rule | When to use |
| --- | --- | --- |
| `execution(* demo.AuditService.ship(..))` | By method signature/execution | Apply to a specific method name or group of methods |
| `execution(public * demo..service..*(..))` | By visibility, return type, package/type, method | Apply uniformly across the service layer |
| `@annotation(demo.TrackedAction)` | By methods bearing `@TrackedAction` | Apply only to explicitly marked methods |
| `execution(* demo.AuditService.*(..)) && @annotation(demo.TrackedAction)` | Must satisfy both class/method scope and annotation | Reduce evaluation area / avoid unintended matches |
| `@annotation(trackedAction)` | By annotation and binds its value for the advice | Advice needs annotation attributes for audit/log/tagging |

`@annotation` does not remove the need for a **Spring AOP join point interceptable through a proxy**. An annotated method called directly on the target still will not trigger advice automatically.

## 3. Creating the Annotation Properly

Two Java meta-annotations are especially important:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

- `@Retention(RetentionPolicy.RUNTIME)`: keeps the annotation at runtime so the AOP mechanism can use metadata at runtime. If `SOURCE` is used, the annotation disappears after compilation; `CLASS` does not guarantee availability via Java runtime reflection.
- `@Target(ElementType.METHOD)`: allows attaching the annotation to **methods** (it does not turn it into a class/field/parameter annotation).
- `String value()`: required attribute. When writing `@TrackedAction("fulfillment")`, `"fulfillment"` is the value of `value`.
- You can add defaults such as `String category() default "general";`. If advice needs attributes, bind the annotation rather than parsing annotations as strings.

**You do not need `@Inherited`** for this lesson. Java's `@Inherited` primarily applies to annotations on **classes**; it does not automatically make an annotation on an interface or superclass method appear as a direct annotation on every overriding method. When working with interface methods, overriding methods, or Spring composed/meta-annotations, verify how the Spring/AspectJ resolver actually resolves method annotations for your proxy type rather than assuming inheritance arbitrarily.

And do not confuse `@TrackedAction` with `@Aspect`:

- `@TrackedAction` is the annotation marking **business methods** for the pointcut to find.
- `@Aspect` marks the **class containing advice**; Spring only finds it if that class is **registered as a Spring bean**.
- `@EnableAspectJAutoProxy` (or corresponding auto-configuration) enables Spring AOP support so advice executes through proxies.

## 4. Runnable Example: Two Annotated Methods, One Unannotated Method

The small Maven project below uses **Java 17+**, **Spring Framework 6.2.0**, and **AspectJ Weaver 1.9.22**. This is plain Spring Framework, without Spring Boot and without an AspectJ compiler/agent.

Complete structure:

~~~text
spring-annotation-pointcut/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── TrackedAction.java
    ├── AuditService.java
    └── TraceAspect.java
~~~

### 4.1. Maven Configuration

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotation-pointcut</artifactId>
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
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` creates the `ApplicationContext` and processes Java config; `spring-aop` provides proxies/interceptors/`AopUtils`. `aspectjweaver` provides the library Spring uses when interpreting pointcut/`@AspectJ` expressions; **there is no `-javaagent` here**, because runtime is still proxy-based Spring AOP.

`<parameters>true</parameters>` tells `javac` to retain parameter names so Spring can look them up when needed. The example still declares `argNames` explicitly so learners can see the exact binding variable being used.

### 4.2. Annotation File with Runtime Retention

Create `src/main/java/demo/TrackedAction.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

### 4.3. Service with Marked and Unmarked Methods

Create `src/main/java/demo/AuditService.java`:

~~~java
package demo;

public class AuditService {
    @TrackedAction("fulfillment")
    public void ship(String orderId) {
        System.out.println("SERVICE: ship " + orderId);
    }

    public void ping() {
        System.out.println("SERVICE: ping");
    }

    @TrackedAction("account")
    public void adjust(String customerId) {
        System.out.println("SERVICE: adjust " + customerId);
    }

    public void callShipInside() {
        System.out.println("SERVICE: callShipInside");
        this.ship("A-101");
    }
}
~~~

For `ship(...)` and `adjust(...)`, the annotation on the **implementation method** is recognized by `@annotation` when callers invoke through the proxy. `ping()` has no annotation, so it does not match. `callShipInside()` also has no annotation; inside it calls `this.ship(...)`, allowing us to observe the **self-invocation** limit of Spring AOP proxies.

All methods are `public` and the class is non-`final`, so a CGLIB class proxy can intercept them. In a minimal project, `@Service` is unnecessary because the service is created with `@Bean` from `Demo`.

### 4.4. Aspect Binding the Annotation Value

Create `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before(
        value = "execution(* demo.AuditService.*(..)) && @annotation(trackedAction)",
        argNames = "trackedAction"
    )
    public void before(JoinPoint point, TrackedAction trackedAction) {
        adviceCount.incrementAndGet();
        System.out.println(
            "ADVICE: tag=" + trackedAction.value()
            + " method=" + point.getSignature().getName()
        );
    }

    public int count() {
        return adviceCount.get();
    }
}
~~~

Exact breakdown of how the advice matches:

1. `execution(* demo.AuditService.*(..))` limits method executions to `AuditService`. This is an extra scope constraint to prevent identically named annotations in other classes from accidentally matching.
2. `@annotation(trackedAction)` accepts only matching methods that have an annotation whose type can bind to parameter `TrackedAction trackedAction`.
3. `argNames = "trackedAction"` explicitly maps the binding variable name in the pointcut to the advice parameter. The first parameter `JoinPoint point` is handled specially by Spring, so it does not need to appear in `argNames`.
4. `trackedAction.value()` reads the attribute of the **annotation attached to the method currently evaluated by Spring AOP**. For example, it prints `fulfillment` or `account` without manual reflection logic.
5. `point.getSignature().getName()` retrieves the name of the method being advised at the join point. In the example, this produces `ship` or `adjust`.
6. `adviceCount` increments only inside the advice; `AtomicInteger` keeps the measurement clean. The program invokes sequentially, so simulating multiple threads is unnecessary.

Common pitfall: `trackedAction` in the pointcut expression is **not** a Java variable outside the method; it is a binding name used by Spring/AspectJ to pass the annotation instance into the advice method.

### 4.5. Enabling AOP, Registering Beans, and Checking Results

Create `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public AuditService auditService() {
        return new AuditService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            AuditService service = context.getBean(AuditService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean isProxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + isProxy);

            service.ship("A-100");
            service.ping();
            service.adjust("C-200");
            service.callShipInside();

            int count = aspect.count();
            System.out.println("ADVICE_COUNT: " + count);

            if (!isProxy || count != 2) {
                throw new IllegalStateException(
                    "Expected @annotation advice exactly twice");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Why is `@EnableAspectJAutoProxy(proxyTargetClass = true)` used?

- It enables **Spring AOP auto-proxying**, allowing Spring to create a subclass proxy for `AuditService` even though the class implements no interface.
- It does not automatically trigger advice on every method; the proxy/advisor still checks which methods match the pointcut.
- `@Bean auditService()` registers the service as a Spring-managed bean. `@Bean traceAspect()` registers the aspect; merely putting `@Aspect` on a class without registering a bean is not enough.
- `context.getBean(AuditService.class)` returns a Spring reference; when a matching advisor exists, this is a proxy rather than an object constructed via `new` outside the container.
- `service.callShipInside()` enters the target method, and then `this.ship("A-101")` is a **direct internal call**. Even though `ship` is annotated, the internal call bypasses the proxy, so `before` does not run a third time.

### 4.6. Running Maven and Expected Stdout

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the Java code in the example, in exact order:

~~~text
PROXY: true
ADVICE: tag=fulfillment method=ship
SERVICE: ship A-100
SERVICE: ping
ADVICE: tag=account method=adjust
SERVICE: adjust C-200
SERVICE: callShipInside
SERVICE: ship A-101
ADVICE_COUNT: 2
CHECK: PASS
~~~

Maven or loggers in the runtime environment may produce additional output. These ten lines are the `System.out.println` messages from the example.

Interpretation:

- `PROXY: true`: the service bean was wrapped by Spring AOP into a proxy.
- `ship("A-100")` has `@TrackedAction("fulfillment")` and is called through the proxy, so the advice prints `fulfillment` before the business code.
- `ping()` has no `@TrackedAction`, so there is no corresponding `ADVICE` line.
- `adjust("C-200")` has `@TrackedAction("account")`; the advice is invoked and binds the value `account`.
- `callShipInside()` is unannotated. The `this.ship("A-101")` call still executes service code, **without going back through the proxy**, so no `ADVICE: tag=fulfillment` appears for `A-101`.
- `ADVICE_COUNT: 2` verifies the advice ran exactly twice on the marked calls that went through the proxy.
- `CHECK: PASS` appears only after confirming the proxy exists and the count equals `2`.

The main goal is to prove **both the annotation condition and the Spring proxy boundary**, avoiding the misconception that `@annotation` intercepts every Java call to an annotated method.

## 5. Separating Scope and Annotation Using @Pointcut

In a real project, multiple advices can share the same constraint. You can define a named pointcut:

~~~java
@Pointcut("execution(public * demo.AuditService.*(..))")
public void auditServiceOperations() {
}

@Before(
    value = "auditServiceOperations() && @annotation(trackedAction)",
    argNames = "trackedAction"
)
public void before(JoinPoint jp, TrackedAction trackedAction) {
    System.out.println("Tracked: " + trackedAction.value());
}
~~~

This is an **excerpt meant to be placed inside an `@Aspect`**; do not add it verbatim into `TraceAspect` when it already has a `before(...)` serving the same role. It requires importing `org.aspectj.lang.annotation.Pointcut`, `Before`, `JoinPoint`, and the `TrackedAction` annotation. The `auditServiceOperations()` method only describes the pointcut; **its body must be empty** and contain no business logic.

Benefits:

- `auditServiceOperations()` expresses the **Spring service scope**; `@annotation(trackedAction)` adds the requirement that the method carry the annotation.
- You can reuse the named pointcut for `@Before` or `@Around` while keeping code readable.
- When changing package/class scope, update the named pointcut definition instead of repeating multiple expression strings.
- Combining a scoping designator clarifies intent and avoids overly broad `@annotation(...)` pointcuts across the whole application.

If you want to apply this to multiple service classes in the same package, replace the `demo.AuditService.*(..)` constraint with an `execution(...)` matching your package convention and retest matching on actual beans. Do not try to "fix" annotation matching by widening the pointcut to the entire JVM.

## 6. Distinguishing @annotation from Other @-Designators in Spring

Spring AOP supports a set of context-based designators; the `@` prefix does not mean all of them inspect the same location:

| Designator | Meaning for Spring AOP method execution | Example purpose |
| --- | --- | --- |
| `@annotation(X)` | The method at the join point has an annotation of type `X` | Audit specifically marked methods |
| `@within(X)` | The join point is in a class type carrying the matching annotation | Select methods inside marked classes |
| `@target(X)` | The runtime target object has a type marked with that annotation | Select by annotation on the target object's type |
| `@args(X)` | Based on an annotation on the runtime type of the argument passed to the method | Select by metadata on input objects |
| `execution(...)` | Selects method executions by signature and scope | Select services/packages/methods needing advice |
| `within(...)` | Restricts by method-declaring type/scope | Narrow advisor evaluation scope |

For example, a marked class:

~~~java
@TrackedService
public class OrderService {
    public void submit() {
    }
}
~~~

If `@TrackedService` is an annotation with `@Target(TYPE)` and `@Retention(RUNTIME)`, `@within(demo.TrackedService)` or `@target(demo.TrackedService)` have a **different** meaning from `@annotation(demo.TrackedService)`: an annotation marking only the **class** does not automatically appear on each method. The snippet above illustrates a `@TrackedService` annotation not defined in the demo project; it is not a standalone runnable file.

Similarly, `@args` does not check annotations on a method's declared parameters; it relies on the **runtime type of the argument**. When you only need to mark a business method for AOP handling, `@annotation` is more appropriate and easier to control.

## 7. Important Limitations in Spring AOP

### 7.1. Having an Annotation Is Not Enough Without Going Through a Proxy

An accurate pointcut expression still will not run in the following situations:

- The object was created with `new AuditService()` outside `ApplicationContext`.
- The `@Aspect` class was not registered as a Spring bean, or `@EnableAspectJAutoProxy` was not enabled in the active context.
- The caller invokes the annotated method via `this.ship()` from another method on the same target (self-invocation).
- `private`/`final` methods cannot be intercepted via class-based subclass proxies; `final` classes cannot be subclassed by CGLIB.
- The `execution(...)` pointcut scope is too narrow, causing the annotated method to fall outside the specified range.
- A bean was initialized too early to be auto-proxied, or calls go to the raw target instead of the Spring bean reference.

Specifically, **`proxyTargetClass = true` does not fix self-invocation**. CGLIB is still a Spring proxy sitting at the caller-target boundary. The least framework-coupled solution is moving the method needing advice into another bean and calling it via a Spring-injected dependency.

### 7.2. Annotations on Interfaces and Implementations

In Java, method-level annotations are not inherited automatically across interface/implementation relationships. With Spring AOP, actual matching can be affected by:

- JDK proxy vs. CGLIB proxy;
- whether the annotation is placed on the interface method, implementation method, or an overridden method;
- how Spring resolves the concrete method/bridge method on the target;
- certain Spring-specific meta-annotation/composed-annotation mechanisms.

**Easily verifiable recommendation:** in simple demos, place the annotation directly on the **implementation method** that is the intended join point, such as `AuditService.ship` and `AuditService.adjust`; write integration tests using the real proxy configuration if the project intentionally places annotations on interfaces or base classes. Do not assume `@Inherited` automatically causes an annotation on an interface method to appear on the implementation method.

If a library uses specialized annotations with Spring, do not assume `@annotation(...)` always follows the exact same **merged/meta-annotation** lookup rules as all Spring annotation utilities. AspectJ pointcut matching and Spring annotation discovery are not completely identical APIs. When you need "direct or meta-annotation" semantics, test empirically and consider retrieving specific metadata with appropriate Spring utilities rather than merely changing the pointcut string.

### 7.3. @annotation Does Not Turn Every Annotation into Special Business Logic

`@TrackedAction` is only an application marker. Declaring an annotation alone does not generate logs, transactions, validation, or security. You need a matching **aspect/advisor**, a Spring context managing the target, and a proxy capable of intercepting the method.

Likewise, if an application already uses `@Transactional` or `@Cacheable`, those annotations work through Spring's own infrastructure mechanisms when enabled. Do not assume every annotation is automatically recognized by your custom pointcut or shares the same advisor order. When multiple advices run on one method, check ordering with `@Order` or the appropriate ordering mechanism if logic requires consistency.

### 7.4. Should You Use @Around Instead of @Before?

`@Before` is appropriate when the goal is auditing or recording metadata before a method runs. If you need to measure execution time or inspect return values or exceptions around a call, you can choose `@Around`, but you **must call `proceed()`** when you want the business method to continue:

~~~java
@Around(
    value = "execution(* demo.AuditService.*(..)) && @annotation(trackedAction)",
    argNames = "trackedAction"
)
public Object around(
        ProceedingJoinPoint pjp, TrackedAction trackedAction) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long nanos = System.nanoTime() - started;
        System.out.println(trackedAction.value() + ": " + nanos + " ns");
    }
}
~~~

This is an **illustrative advice-replacement snippet** inside an `@Aspect`, requiring imports of `org.aspectj.lang.ProceedingJoinPoint` and `org.aspectj.lang.annotation.Around`. It is not a standalone runnable program and you should not keep both `@Before` and `@Around` simultaneously when testing a single advice output line.

Note that `System.nanoTime()` measures relative elapsed duration, **not** an absolute timestamp. Execution times and nanosecond stdout vary by machine, which is why the main hands-on example uses `@Before` for deterministic output.

## 8. Debugging When an Annotated Method Does Not Run Advice

A practical diagnostic workflow:

1. **Confirm the annotation is visible at runtime:** check `@Retention(RUNTIME)` and `@Target(METHOD)` and exact placement on the intended method. A class-level annotation will not match a method `@annotation`.
2. **Check the Spring bean:** is the method being called on a bean produced by `ApplicationContext` or an object created with `new`? Is the aspect registered as a bean and AOP enabled?
3. **Check the proxy:** use `AopUtils.isAopProxy(service)`, `isJdkDynamicProxy(service)`, and `isCglibProxy(service)` on the **actual reference used by the caller**.
4. **Read the entire pointcut expression:** does `execution(...)` match the exact package/class/method, and is `@annotation(...)` an annotation type or a binding variable name?
5. **Check advice binding:** when using `@annotation(variable)`, the advice method must declare a parameter of the matching annotation type; if `-parameters` is not used or names cannot be inferred, declare `argNames` explicitly.
6. **Measure count and execution order:** increment a counter inside the advice and log a distinct marker to confirm advice runs before the business method. Do not rely solely on whether the bean has a proxy.
7. **Check self-invocation and visibility:** `this.method()`, `private`, `final`, JDK vs. CGLIB, or methods not exposed on the proxy can prevent advice from running.
8. **Check annotation placement across interfaces/overrides:** place the annotation on the implementation as a control check; retest with the actual proxy strategy.
9. **If there are multiple contexts/auto-proxy creators:** ensure both aspect and target belong to the right context; AOP configuration is typically scoped per `ApplicationContext`.
10. **After fixing:** rerun tests in a full context and confirm the marker, counter, and business method result.

### Common Mistakes with Annotation Binding

**Mistake 1 — mistaking `@annotation(trackedAction)` for a class name**

~~~java
@Before("@annotation(trackedAction)")
public void before() {
    // No annotation parameter to bind as intended
}
~~~

In this case, you used a **binding name**, yet the advice did not declare a corresponding `trackedAction` parameter. Change it to `@annotation(demo.TrackedAction)` if you only need type matching, or add a `TrackedAction trackedAction` parameter as in the working example.

**Mistake 2 — writing an annotation without `RUNTIME` retention**

~~~java
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

This is an **incorrect retention example for runtime matching needs**: `CLASS` does not retain the annotation at runtime as required. Do not include this snippet in the active project alongside the standard `TrackedAction`.

**Mistake 3 — method is annotated but outside scope**

~~~java
@Before("execution(* demo.AuditService.ship(..)) && @annotation(demo.TrackedAction)")
public void before() {
}
~~~

If you attach `@TrackedAction` to `adjust`, this expression still **does not match `adjust`** because it selects only `ship`. Annotation matching and method-signature matching form an **AND** relationship here.

**Mistake 4 — using a proxy yet making a self-call**

~~~java
public void outer() {
    this.ship("A-101");
}
~~~

When `outer` is called on a Spring bean proxy, code inside the target calling `this.ship` goes directly to the target; do not blame `@annotation`. This is a limitation of Spring proxy-based AOP.

## 9. Extended Hands-On Exercises

### Exercise 1: Select Three Methods with One Annotation

Add a method to `AuditService`:

~~~java
@TrackedAction("refund")
public void refund(String orderId) {
    System.out.println("SERVICE: refund " + orderId);
}
~~~

Call `service.refund("R-300")` from `Demo.main()` after obtaining the bean proxy. This adds:

~~~text
ADVICE: tag=refund method=refund
SERVICE: refund R-300
~~~

If you still call the original two annotated methods once each and add one `refund` call through the proxy, `ADVICE_COUNT` must be `3`. Remember to update the `count != 2` assertion to `count != 3`; otherwise, the check fails due to the old expectation, not a broken advice.

### Exercise 2: Match Annotations Only in a Specific Service

Compare:

~~~java
@Before("@annotation(demo.TrackedAction)")
public void logAnnotated() {
}
~~~

and:

~~~java
@Before("execution(* demo.AuditService.*(..)) && @annotation(demo.TrackedAction)")
public void logServiceAnnotated() {
}
~~~

These two snippets are **two illustrative options**; do not add them simultaneously to the demo aspect alongside the existing advice if you want to count each join point once. The first form is broader: it selects annotated methods on any interceptable Spring bean; the latter restricts to the `AuditService` scope.

### Exercise 3: Extract Self-Invocation into Another Bean

Move the annotated `ship` method into a `ShippingService` Spring bean, then have `AuditService` receive `ShippingService` via constructor injection; when `AuditService` calls `shippingService.ship("A-101")`, the call through the dependency proxy can be advised. Before concluding, confirm Spring creates the bean and the advisor matches. Do not "fix" it by calling `new ShippingService()` inside the target.

## 10. Retention Checklist

- [ ] Custom annotation uses `@Retention(RUNTIME)` and `@Target(METHOD)`.
- [ ] The `@Aspect` class is registered as a **Spring bean**.
- [ ] The context has Spring AOP enabled via `@EnableAspectJAutoProxy` (or equivalent auto-configuration).
- [ ] The target service is also a Spring bean; callers invoke methods through the proxy.
- [ ] `@annotation(demo.TrackedAction)` is **type selection**; `@annotation(trackedAction)` is **instance binding**.
- [ ] When binding, the advice parameter has the matching `TrackedAction` type and the binding name is specified via `argNames` or compile-time parameter metadata.
- [ ] The `execution(...)` pointcut scope does not accidentally exclude desired annotated methods.
- [ ] Methods are not `private`/`final` uninterceptable under the active proxy; no self-invocation bypasses the proxy.
- [ ] Verified both proxy status and advice execution count, not merely the presence of the annotation.

## 11. Spring Framework Documentation

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `@annotation` among pointcut designators supported by Spring AOP.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): binding annotation instances, `argNames`, `@Before`, and `@Around`.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` and how Spring registers aspects.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): calls going through proxies, self-invocation, and JDK/CGLIB limits.
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring uses `@AspectJ` declaration style while remaining proxy-based Spring AOP.
