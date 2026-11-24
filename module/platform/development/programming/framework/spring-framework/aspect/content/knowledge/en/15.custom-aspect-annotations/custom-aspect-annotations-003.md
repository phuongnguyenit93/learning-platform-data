# Binding Annotation Values to Advice in Spring AOP

## 1. The Problem to Solve

In Spring AOP, a custom annotation can both mark the method to be intercepted and supply **per-method configuration**. For example, for methods in a Spring service, we want an aspect to log according to the business name, priority, or masking rules declared by the annotation:

~~~java
@TrackOperation(action = "order.create", sensitive = false)
public String create(String orderId) {
    return "created: " + orderId;
}
~~~

An advice should receive the TrackOperation object directly to call action() and sensitive(). That way, there is no need to write a separate aspect for each action or hardcode method names in the advice.

**Scope:** How Spring interprets @AspectJ-style pointcut expressions, binds the annotation object to an advice parameter, and the boundaries when Spring invokes beans through an AOP proxy. General Java annotation/AOP knowledge is used only to the extent required to implement this accurately in Spring.

## 2. Two Meanings of @annotation: Selecting Methods and Binding Values

Spring AOP supports the @annotation pointcut designator to match methods invoked through a Spring proxy where that method carries the specified annotation. There are two different ways to express this:

**Filtering by annotation type name only:**

~~~java
@Before("@annotation(demo.TrackOperation)")
public void beforeAnyTrackedMethod() {
    // Runs when the advised method matches TrackOperation.
    // Does not receive the annotation object in an advice parameter.
}
~~~

**Binding the annotation to an advice parameter:**

~~~java
@Before(value = "@annotation(track)", argNames = "track")
public void beforeTrackedMethod(TrackOperation track) {
    System.out.println(track.action());
    System.out.println(track.sensitive());
}
~~~

In the second case:

1. track inside the string "@annotation(track)" is a **binding variable name**, not a class name.
2. TrackOperation is the actual Java type of the advice parameter. The Spring/AspectJ expression determines the type to match and passes the matched annotation into that parameter.
3. argNames = "track" explicitly declares the variable name in the expression matching the advice parameter; this ensures reliable operation when compilation does not preserve Java parameter names.
4. action() and sensitive() retrieve the values **declared on the invoked method**, not values automatically read from the business arguments of that method.
5. Annotation attributes are declared with compile-time valid values; the advice receives that configuration metadata when Spring intercepts the corresponding call.

Do not use the expression "@annotation(demo.TrackOperation)" and expect Spring to automatically pass TrackOperation into an unbound parameter. To receive the object, use the variable-name form and a matching parameter.

## 3. Defining a Custom Annotation Suitable for Spring Proxies

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackOperation {
    String action();
    boolean sensitive() default false;
}
~~~

In the application, the annotation above is placed on methods intercepted by a Spring AOP proxy:

~~~java
@Service
public class OrderService {
    @TrackOperation(action = "order.create")
    public String create(String id) {
        return "created: " + id;
    }

    @TrackOperation(action = "order.cancel", sensitive = true)
    public void cancel(String id) {
        // Business logic processing
    }
}
~~~

- RetentionPolicy.RUNTIME is a critical condition so the annotation is present at runtime for Spring AOP and reflection/annotation resolution mechanisms.
- Target(METHOD) establishes that the problem uses a **method-level** annotation. If the annotation is placed on a class, consider @within or @target designators depending on the goal rather than expecting @annotation to match classes.
- The action() field is required at the usage site; sensitive() has a default so it can be omitted.
- Spring only applies advice to invocations **going through the configured bean proxy**. Marking a method does not make direct Java calls or self-invocations automatically intercepted.

## 4. Runnable Example: Binding TrackOperation in @Around

The example below uses **Java 17, Spring Framework 6.1.15, and Maven**. It demonstrates that the exact annotation values of the create/cancel methods are passed into a single advice, while the unmarked preview method is not intercepted.

Directory structure:

~~~text
spring-annotation-binding/
├── pom.xml
└── src/main/java/demo/
    ├── Application.java
    ├── TrackOperation.java
    ├── OrderService.java
    └── TrackingAspect.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotation-binding</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
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
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TrackOperation.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackOperation {
    String action();
    boolean sensitive() default false;
}
~~~

**src/main/java/demo/OrderService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @TrackOperation(action = "order.create")
    public String create(String orderId) {
        return "created: " + orderId;
    }

    public String preview(String orderId) {
        return "untracked: " + orderId;
    }

    @TrackOperation(action = "order.cancel", sensitive = true)
    public String cancel(String orderId) {
        throw new IllegalStateException("cancelled");
    }
}
~~~

**src/main/java/demo/TrackingAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {

    @Around(value = "@annotation(track)", argNames = "track")
    public Object around(ProceedingJoinPoint joinPoint, TrackOperation track)
            throws Throwable {
        // Spring binds the exact method's annotation into track.
        String action = track.action();
        boolean sensitive = track.sensitive();

        System.out.println("trace.enter: " + action
                + ", sensitive=" + sensitive);

        try {
            Object result = joinPoint.proceed();
            System.out.println("trace.success: " + action);
            return result;
        } catch (Throwable error) {
            System.out.println("trace.error: " + action
                    + ", " + error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Application.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println(service.create("O-42"));
            System.out.println(service.preview("O-42"));

            try {
                service.cancel("O-42");
            } catch (IllegalStateException error) {
                System.out.println("caught: " + error.getMessage());
            }
        }
    }
}
~~~

In the directory containing pom.xml, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program in order:

~~~text
trace.enter: order.create, sensitive=false
trace.success: order.create
created: O-42
untracked: O-42
trace.enter: order.cancel, sensitive=true
trace.error: order.cancel, IllegalStateException
caught: cancelled
~~~

The Maven command may print extra messages from the Maven environment or Spring Logging; the program lines above are the expected logical output.

Explanation:

- @EnableAspectJAutoProxy enables Spring's proxy-based @AspectJ processing. aspectjweaver provides the APIs needed for Spring to parse AspectJ pointcut expressions; the example does not use compile-time weaving.
- @ComponentScan registers OrderService and TrackingAspect in the Spring context. Calling context.getBean(...) retrieves an object that may have been proxied by Spring.
- create and cancel have the same annotation type but **different action and sensitive values**. At each join point, Spring passes the corresponding TrackOperation object into track.
- preview does not carry TrackOperation so there is no trace log.
- The advice calls proceed() **once** and returns the original result, or rethrows the Throwable. Logging the error does not turn an application failure into success.
- The ProceedingJoinPoint parameter at the front of the advice signature is **omitted from the argNames string** according to Spring binding rules. Thus argNames only lists "track".
- The compiler is configured to preserve parameter names, yet the example still uses explicit argNames to clearly demonstrate the correspondence with the pointcut.

## 5. How Spring Maps Binding Names to Advice Parameters

Principle structure:

~~~text
Pointcut expression:  @annotation(track)
                                  │
                                  │ binds the matched annotation object
                                  ▼
Advice parameter:     TrackOperation track
                                  │
                                  ├── track.action()
                                  └── track.sensitive()
~~~

Binding names belong to the **pointcut/advice namespace**. Any valid Java identifier can be chosen, as long as it matches consistently. For example, to use the name policy:

~~~java
@Around(value = "@annotation(policy)", argNames = "policy")
public Object intercept(ProceedingJoinPoint pjp, TrackOperation policy)
        throws Throwable {
    System.out.println(policy.action());
    return pjp.proceed();
}
~~~

Regarding how parameter names are resolved, Spring can use argNames information, parameter names stored in bytecode when compiled with javac -parameters, or name inference from the pointcut expression per Spring documentation. When binding is complex, explicitly declare argNames to avoid errors like "ambiguous binding", "argument names not available", or binding to the wrong parameter. When declaring argNames and the advice accepts JoinPoint/ProceedingJoinPoint as the first parameter, it is normally unnecessary to list that join point parameter.

**Common pitfall: mismatched binding name**

~~~java
// Wrong: variable "track" in the pointcut does not match argNames="label".
@Before(value = "@annotation(track)", argNames = "label")
public void wrong(TrackOperation label) {
    // May fail to resolve/bind the parameter when creating the advisor.
}
~~~

Fix: use the exact same name in the pointcut expression, argNames, and Java signature.

### Binding Multiple Objects Simultaneously

Spring allows combining annotation binding and method-argument binding. The illustrative example below assumes the matching method has a String as its first argument:

~~~java
@Before(
    value = "@annotation(track) && args(orderId,..)",
    argNames = "track,orderId"
)
public void beforeWithArgument(TrackOperation track, String orderId) {
    System.out.println("action=" + track.action()
            + ", orderId=" + orderId);
}
~~~

- @annotation(track): retrieves the **method's** metadata.
- args(orderId,..): matches and binds the **first business argument value** of the call, according to the data type declared in the advice; .. allows additional trailing arguments.
- If the method does not have a first argument of a compatible type, the execution point does not match the combined expression.
- Do not read orderId as a replacement for track.action(): these are two different data sources. For sensitive information, check track.sensitive() before putting arguments into logs.

Binding can also be combined with target(...) or return value/exception types in the corresponding advices; each additional variable needs a properly matching parameter/condition.

## 6. Extracting @Pointcut to Reuse Annotation Binding

When multiple advices share the same condition, the pointcut can be named. The annotation object **must still be declared as a parameter of the @Pointcut method**, then passed to each advice calling that pointcut.

~~~java
@Aspect
@Component
public class ReusableTrackingAspect {

    @Pointcut(value = "@annotation(track)", argNames = "track")
    public void methodsWithTracking(TrackOperation track) {
        // This method only declares the pointcut; it contains no business logic.
    }

    @Before(value = "methodsWithTracking(track)", argNames = "track")
    public void before(TrackOperation track) {
        System.out.println("start: " + track.action());
    }

    @AfterReturning(
        value = "methodsWithTracking(track)",
        argNames = "track"
    )
    public void afterSuccess(TrackOperation track) {
        System.out.println("returned: " + track.action());
    }
}
~~~

The snippet above is an **independent variant for illustration**; do not add it alongside the example in section 4 unless you want overlapping logs from multiple aspects.

An important point: @AfterReturning runs when the Java method returns normally; it does not automatically guarantee that asynchronous work inside a Future/Publisher has completed. If the method returns an async handle, appropriate observation for that return type is needed. The goal here is to illustrate how the bound TrackOperation object is forwarded through a named pointcut to each advice.

Package/service scopes can be combined to restrict join points:

~~~java
@Pointcut(
    value = "within(demo..*) && @annotation(track)",
    argNames = "track"
)
public void trackedInDemo(TrackOperation track) {}
~~~

within(...) restricts where methods are declared/executed by type expression, while @annotation(track) both filters methods and binds the annotation. Narrowing the scope is useful if multiple modules share the same annotation or the application has many beans.

## 7. Comparing Related Designators in Spring

| Designator | Subject Inspected | When to Use |
| --- | --- | --- |
| @annotation(track) | Annotation attached to the executed method matched by Spring AOP | Bind per-method configuration into advice |
| @annotation(demo.TrackOperation) | Annotation type on the method, without declaring a binding variable | Only need to filter methods |
| @within(trackType) | Annotation on the declaring type of the intercepted method | Apply configuration per class/type |
| @target(trackType) | Annotation on the runtime class of the target object | Apply configuration per target |
| @args(marker) | Annotation on the **runtime type of an argument** | Bind an annotation of the argument's type, not the method's annotation |
| args(orderId,..) | Argument values passed when calling the method | Bind business input data; can be combined with @annotation |

Each designator has different matching rules. If an annotation is placed on a class while the advice only has @annotation(methodTag), do not expect the class annotation to naturally become methodTag. Similarly, @args does not pull annotations directly from the method.

A common need: class configuration serves as the default, while method-level annotations override it. **Combining and deciding this precedence is Spring aspect logic designed by the application itself**, and does not arise automatically just from writing @annotation. Annotation lookup via Spring utilities (AopUtils, AnnotatedElementUtils) can be considered when combining annotation metadata is truly needed, after determining the join point and desired semantics.

## 8. Annotation Metadata Boundaries with Spring AOP Proxies

### 8.1. Beans Must Go Through the Spring Proxy

~~~java
@Service
public class OrderFacade {
    @Autowired
    private OrderService service;

    public void externalCall() {
        service.create("O-1"); // Through bean proxy; advice can run.
    }
}
~~~

Conversely, inside the same bean:

~~~java
@Service
public class InternalService {
    public void outer() {
        inner(); // this.inner(): internal call bypasses the proxy.
    }

    @TrackOperation(action = "internal.inner")
    public void inner() {}
}
~~~

If only outer() is called from outside, inner() is invoked directly on this, so advice targeting inner() normally does not run in Spring proxy mode. Place interception boundaries on calls through an appropriate Spring-managed bean or restructure the service. The annotation itself does not solve self-invocation.

### 8.2. Annotation Placement on Interfaces vs. Implementations

Spring can create a **JDK dynamic proxy** for beans with interfaces or a **class-based proxy**. The proxy type and the resolved actual method can affect whether an annotation is visible/matched when configuration puts the annotation on an interface, implementation, or overridden method.

An easily verifiable convention is to place the annotation **directly on the concrete method of the Spring service**, as in OrderService in the example, and write integration tests calling through the exact bean proxy used in production. If a project requires annotations on interfaces, specifically verify behavior when switching proxyTargetClass, inheritance, and bridge methods; do not assume method annotations are automatically inherited by Java. Java's @Inherited is only for annotation inheritance on types, and does not generally solve method annotations on interfaces/overrides.

### 8.3. Scope of Advisable Methods

Spring AOP proxies support method execution join points through bean proxies; they do not automatically intercept constructors, field accesses, calls to manually instantiated objects with new, or any call not going through the proxy. Final classes/final methods have significant limitations for class-based proxies. Specific visibility and proxy configurations also determine advisability; do not rely on private methods as typical join points.

For overloaded methods with the same name, the annotation metadata of the **exact method** needs to match; an annotation is not automatically picked up for a method solely based on method name.

### 8.4. Retention and Composed Annotations

Lacking @Retention(RUNTIME) can prevent advice from seeing the annotation at runtime. For custom composed/meta-annotations (annotation A attached to annotation B), Spring has its own merged annotation system supporting many features like @Transactional. However, do not assume by default that every meta-annotation combination will bind via @annotation(track) identically to a directly attached annotation across all configurations/versions. When composed annotation semantics are needed, clarify the matching mechanism and test it; if only direct binding is needed, declaring the annotation right on the method is simplest.

## 9. When to Use @Before, @Around, @AfterReturning, @AfterThrowing?

Only need to **read configuration from the annotation and log/check preconditions before running**: @Before with parameter binding is usually enough.

Need to measure synchronous duration, control proceed() directly, capture results, or block calls according to the policy described by the annotation: use @Around, while clearly determining whether short-circuiting, modifying arguments, or modifying return values is part of the service contract. @Around advice is powerful and can easily alter business behavior if proceed() is forgotten or called multiple times.

Need to receive the annotation together with the return value when the **method returns normally**:

~~~java
@AfterReturning(
    value = "@annotation(track)",
    returning = "result",
    argNames = "track,result"
)
public void afterReturn(TrackOperation track, Object result) {
    System.out.println(track.action() + ": " + result);
}
~~~

returning="result" binds the **method return value**, whereas @annotation(track) binds the **annotation metadata**. Using a concrete type for the returning parameter (e.g., String instead of Object) lets Spring restrict join points to methods whose return value fits that type.

Need to receive the annotation and the error thrown during method invocation:

~~~java
@AfterThrowing(
    value = "@annotation(track)",
    throwing = "error",
    argNames = "track,error"
)
public void afterError(TrackOperation track, Throwable error) {
    System.out.println(track.action() + ": " + error.getClass().getSimpleName());
}
~~~

throwing="error" binds the corresponding exception, and does not replace annotation binding. If a method returns a Mono/Future normally yet the async object emits an error later, this @AfterThrowing advice does not automatically observe the async signal. Handling depends on the actual API type; do not treat annotation binding as a mechanism to observe every lifecycle.

**Do not place multiple advices with overlapping side effects** just to receive the same annotation if unnecessary. If multiple related aspects exist (e.g., security/metrics/transaction), advisor ordering can change before/after semantics; use @Order and test when order actually matters.

## 10. Designing Annotation Values: Policy Metadata, Not Global State

Annotations are suited for storing static metadata on a method, for example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditPolicy {
    String event();
    Level level() default Level.INFO;
    boolean includeResult() default false;

    enum Level { INFO, WARN }
}
~~~

This declaration is independent of the TrackOperation example above. A Spring advice can bind AuditPolicy to select the log level or event type:

~~~java
@Before(value = "@annotation(policy)", argNames = "policy")
public void onAuditPolicy(AuditPolicy policy) {
    System.out.println(policy.event() + " at " + policy.level());
}
~~~

The action/event/level values are static configuration on the matched method. They do not vary per invocation based on the request. When runtime data is needed (userId, orderId, tenant, correlation id), obtain it from method arguments, security context, or the corresponding execution context; it can be combined with annotation metadata, but do not stuff request data into a mutable field on a singleton @Aspect.

Example of error-prone shared state:

~~~java
@Aspect
@Component
class WrongAspect {
    private String currentAction; // Wrong: mutable field shared across requests.

    @Before(value = "@annotation(track)", argNames = "track")
    public void before(TrackOperation track) {
        currentAction = track.action();
    }
}
~~~

With multiple threads processing concurrently, currentAction gets overwritten, leading to incorrect logs/correlation. Replace with local variables inside each advice invocation; if shared counters are required, use appropriate concurrency-safe mechanisms. The bound annotation object is method metadata; storing it in a currentAction field to "remember" the current request is unnecessary.

If the advice enforces an actual policy (authorization, data control), do not treat the annotation as proof that the user is authorized; verify identity/permissions through Spring Security components or a configured policy service. The annotation only describes the rule to apply.

## 11. Diagnosing Binding Errors in Spring Applications

| Symptom | Possible Cause | How to Verify and Fix |
| --- | --- | --- |
| Advice does not run even though method has annotation | Bean not going through proxy, self-invocation, @EnableAspectJAutoProxy not active, annotation placed elsewhere | Retrieve bean from ApplicationContext, check proxy type and executed method |
| Spring reports failure to determine binding parameter | Names in pointcut/argNames/signature differ, missing -parameters when needed | Add explicit argNames, verify parameter receives the right annotation type |
| Annotation in advice is null or does not match | Annotation lacks RUNTIME, method/class/interface annotation resolution differs from assumption | Use @Retention(RUNTIME), place directly on test method, test with real proxy |
| Used @annotation(demo.TrackOperation) yet want to read action() | Expression only filters type, has no binding variable | Use @annotation(track) with parameter TrackOperation track |
| @Around runs yet business logic does not execute | Forgot to call proceed() | Call proceed() exactly once unless intentionally short-circuiting per contract |
| Method executes yet return type is wrong | Advice returns an unexpected type or fails to return proceed() result | Preserve return contract; do not turn a String into a Mono or vice versa |
| Advice logs wrong orderId across concurrent requests | Mutable field used in singleton aspect | Use local variables and safe context/counter mechanisms |
| Overridden or interface method not intercepted | Differences in method annotation lookup/proxy strategy | Test with real JDK/class proxy; determine where annotation must be placed |
| Method fails yet @AfterReturning still runs | Method returns a Future/Publisher, error occurs after synchronous return | Distinguish Java method return from asynchronous outcome |
| Only wanted to filter yet accidentally bound wrong type | Used a variable name, advice accepts wrong annotation class | Verify consistent type, expression, and signature |

### Minimum Testing

Use a Spring integration test (initializing ApplicationContext or @SpringJUnitConfig / @SpringBootTest depending on the application) and **obtain the service from the context**, rather than instantiating it with new. Test:

1. Two methods using the same TrackOperation with different action/sensitive values: advice receives **each exact value**, without mixing up another method's values.
2. Method without the annotation: not intercepted by this advice.
3. @Around advice returns the original String and preserves exceptions from the target.
4. Call via self-invocation: confirm Spring proxy limitations, or design another service boundary.
5. Run multiple annotated methods concurrently: bound values do not cross between invocations.
6. If using interfaces, overloads, composed annotations, or multiple advisors, test the exact proxy configuration and advisor order that will run in production.

Tests can capture invocations via a thread-safe spy/collector instead of comparing println output when concurrency does not guarantee ordering.

## 12. Quick Adoption Workflow

1. Determine what metadata the custom annotation carries and set retention to RUNTIME; choose METHOD when configuring per method.
2. Attach the annotation to the right method in a Spring bean; verify callers actually go through the proxy.
3. Write pointcut "@annotation(variable)" with an advice parameter typed as the corresponding annotation.
4. Declare argNames matching variable (omit the first JoinPoint parameter from argNames if applicable).
5. Read annotation attributes inside advice; store per-invocation data in local variables, never assigning to shared mutable fields.
6. Choose the advice type and preserve proceed()/return/exceptions per contract.
7. Test annotation values across multiple methods, unmarked methods, errors, proxy strategies, and concurrency.

Key takeaway in Spring: **@annotation(variable) both identifies the method intercepted by the Spring AOP proxy and binds the exact annotation instance to the correspondingly named advice parameter**. One aspect can handle many methods with distinct configurations declared right on their annotations, while Spring preserves its proxy mechanism and method execution timing.

Official reference documentation:
- Spring Framework, Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework, Declaring Advice (Passing Parameters to Advice / Explicit Argument Names): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework, @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
