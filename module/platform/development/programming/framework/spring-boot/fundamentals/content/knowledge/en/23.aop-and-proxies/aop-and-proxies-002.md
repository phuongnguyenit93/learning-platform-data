# Aspect, Advice, Pointcut, Join Point, and Target Object

In Spring Boot, an application may have dozens of services and repositories that all need logging, execution timing, error tracking, or transaction management. Writing code for those tasks inside every business method makes the codebase repetitive and hard to maintain.

**Aspect-Oriented Programming (AOP)** separates *cross-cutting* concerns from business logic. Common Spring AOP is **proxy-based**: when AOP is applied to a bean, external calls enter the proxy before reaching the real object.

Five central concepts:

- **Aspect:** a unit organizing a cross-cutting concern, such as logging or timing.
- **Advice:** code that executes before, after, or around method execution.
- **Pointcut:** a rule selecting which method executions advice applies to.
- **Join point:** a point during execution where AOP behavior can be attached. In Spring AOP, the supported join point is **method execution**.
- **Target object:** the object performing business logic, to which the proxy delegates.

Beyond these five concepts, you also need to understand **AOP proxy**: the intermediary object that receives consumer calls and runs matching interceptors/advice before forwarding to the target.

## 1. Why do we need AOP?

Suppose a service handles orders:

```java
@Service
public class OrderService {

    public String placeOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return "Placed " + orderId;
    }
}
```

You want to measure method execution time. The traditional way:

```java
public String placeOrder(String orderId) {
    long start = System.nanoTime();

    try {
        return doPlaceOrder(orderId);
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }
}
```

If a hundred methods need timing, you might have to add and maintain a hundred similar blocks. Services end up containing both business logic and logging/monitoring.

AOP lets you declare once: "every service method matching rule X will be timed by behavior Y."

This does not mean every kind of behavior belongs in AOP. Business rules that clearly depend on the domain should normally stay in services; AOP fits logic that is cross-cutting and can be expressed consistently.

## 2. Visualizing the relationships between concepts

When a bean is proxied, a call may flow like this:

```text
Controller / Consumer
        │
        │ service.placeOrder("A01")
        ▼
   Spring AOP Proxy
        │
        ├── Pointcut: does the method match?
        │
        ├── Advice before execution
        │
        ▼
   Target Object (OrderService)
        │
        ▼
   placeOrder("A01")
        │
        ▼
   Return result or throw exception
        │
        ▼
   Advice after / around
        │
        ▼
Controller / Consumer
```

In this example:

| Term | Meaning |
|---|---|
| Aspect | `TimingAspect` — component holding the timing logic |
| Advice | `measure(...)` annotated with `@Around` |
| Pointcut | Expression selecting methods of `OrderService` |
| Join point | The execution of `placeOrder("A01")` passing through the proxy |
| Target object | The `OrderService` instance executing the logic |
| Proxy | The object provided by Spring to coordinate the call |

**The pointcut selects where to apply; advice defines what to do; the aspect packages them; the target still handles business logic.**

## 3. What is an Aspect?

An aspect represents a distinct concern. For example:

- `ExecutionTimeAspect`: records timing.
- `AuditAspect`: produces audit events.
- `FailureMetricAspect`: counts errors by type.
- `TracingAspect`: supports traces/spans.
- `AccessCheckAspect`: applies extra checks at method boundaries.

Common Spring AOP declaration:

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ExecutionTimeAspect {
    // Advice and pointcuts live here.
}
```

`@Aspect` declares that the class carries AspectJ-style aspect metadata. `@Component` lets component scanning create a Spring bean.

**Having `@Aspect` alone is not enough to guarantee the class is managed by Spring**. The aspect must be registered as a bean via `@Component`, `@Bean`, or an equivalent mechanism, and the appropriate Spring AOP infrastructure must be present.

An aspect can contain multiple advice methods, and multiple advices can share the same pointcut.

## 4. What is Advice?

Advice is the cross-cutting concern code executed when a join point matches a pointcut.

Example:

```java
@Aspect
@Component
public class LoggingAspect {

    @Before(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void beforeServiceCall() {
        System.out.println("Entering service method");
    }
}
```

Here:

- `@Before` determines that the advice runs before the method.
- The string in the annotation is the pointcut expression.
- The body of `beforeServiceCall()` is the actual behavior.

Common advice types:

| Type | Annotation | When it runs |
|---|---|---|
| Before | `@Before` | Before the target method executes |
| After returning | `@AfterReturning` | After the method returns normally |
| After throwing | `@AfterThrowing` | After the method throws a matching exception |
| After/finally | `@After` | After the method completes, whether successfully or with an error |
| Around | `@Around` | Wraps the call, controlling whether execution proceeds |

Advice is not synonymous with pointcut. **Advice is the behavior; pointcut is the method-selection condition.**

## 5. What is a Pointcut?

A pointcut is an expression specifying which join points an advice should apply to.

```java
@Before("execution(* com.example.orders.service..*.*(..))")
public void beforeServiceMethod() {
    System.out.println("Starting service operation");
}
```

The part:

```text
execution(* com.example.orders.service..*.*(..))
```

selects methods with matching signatures inside the `com.example.orders.service` package and its subpackages.

A pointcut can be named for reuse:

```java
@Aspect
@Component
public class ServiceLoggingAspect {

    @Pointcut(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void serviceOperations() {
        // Method body used to name the pointcut.
    }

    @Before("serviceOperations()")
    public void logStart() {
        System.out.println("Service started");
    }

    @AfterReturning("serviceOperations()")
    public void logSuccess() {
        System.out.println("Service succeeded");
    }
}
```

The `serviceOperations()` method is not called as a business check step every time a method runs; Spring reads `@Pointcut` to obtain the expression.

The benefit of named pointcuts is avoiding duplicated expressions, reducing typos, and expressing scope with readable names.

## 6. What is a Join point?

In AOP theory, a join point is a point during execution where cross-cutting logic can be applied.

In **proxy-based Spring AOP**, the supported join point is **method execution**. Full AspectJ weaving systems may support constructor execution, field get/set, and other join point kinds; do not assume Spring proxy AOP supports those.

Example:

```java
orderService.placeOrder("A01");
```

If the call goes through a Spring AOP proxy and the pointcut matches, the **execution** of `placeOrder` is the join point handled by the advice.

Distinguish:

- The `OrderService` class defines target behavior.
- The pointcut expression determines which methods to select.
- The join point is the method execution event occurring.
- Advice is the behavior executed at that point.

Multiple calls to the same method can produce multiple advice executions.

## 7. Target object and proxy

**Target object** is the object containing the business method; **proxy** is the object standing in front of the target.

```text
Consumer
    │
    ▼
Proxy implementing/extending the bean's API
    │
    ├── Logging advice
    │
    ├── Timing advice
    │
    ▼
Target object: OrderService
    │
    ▼
Business method
```

Crucially, consumers usually inject a Spring bean reference. That reference may be a proxy, not the raw target object.

A proxy differs from the target in these ways:

- The proxy holds interception logic and forwards calls.
- The target executes business behavior.
- The proxy may have a different runtime class from the target.
- The target may not receive calls going through the proxy when calling its own methods.

A Spring proxy does not necessarily alter the target's source code. Service logic can still be written as a normal Java class.

## 8. Running example in Spring Boot

A Spring Boot project with proper AOP infrastructure typically uses the AOP starter matching the project version. Common Gradle dependency example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Starter and module names may vary across Spring Boot lines; use dependencies compatible with your actual version.

Imports under `org.aspectj.lang.annotation.*` come from the AspectJ annotation API. **Using `@Aspect` does not automatically mean compile-time weaving is active**: Spring AOP typically uses proxies.

### 8.1. Application class

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 8.2. Target service

```java
package com.example.orders.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public String placeOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return "Placed order " + orderId;
    }
}
```

### 8.3. Timing aspect

```java
package com.example.orders.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;

            System.out.println(
                joinPoint.getSignature().toShortString()
                    + " elapsed " + elapsed + " ns"
            );
        }
    }
}
```

Role of each part:

1. `@Aspect` marks the aspect.
2. `@Component` registers it as a bean.
3. `@Around` declares advice wrapping the method.
4. `execution(...)` is the pointcut selecting service methods.
5. `ProceedingJoinPoint` represents the join point with the ability to continue the call.
6. `proceed()` continues the interceptor chain and eventually reaches the target.
7. `finally` ensures timing is recorded even if the target throws an error.
8. `return` preserves the method result.

`System.out.println` is used for illustration. Production should use a logger and appropriate observability system.

### 8.4. Controller calling through the proxy

```java
package com.example.orders.web;

import com.example.orders.service.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public String place(@PathVariable String id) {
        return orderService.placeOrder(id);
    }
}
```

When a request:

```text
GET /orders/O-123
```

reaches the controller, the call to the Spring bean `OrderService` can pass through the proxy. The aspect records timing, and the target returns:

```text
Placed order O-123
```

The log might look like:

```text
OrderService.placeOrder(..) elapsed 38000 ns
```

The number is only an example of format. Actual time depends on the machine and workload.

## 9. @Before

`@Before` runs before the method execution selected by the pointcut.

```java
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BeforeLoggingAspect {

    @Before(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void before(JoinPoint joinPoint) {
        System.out.println(
            "Entering " + joinPoint.getSignature().toShortString()
        );
    }
}
```

`@Before` has no `proceed()` and does not directly replace the return value. If the advice method throws an exception, the call may fail before the target runs.

Suitable for simple pre-call logging or checks. When you need total elapsed time or control over target execution, `@Around` is usually more appropriate.

## 10. @AfterReturning

`@AfterReturning` runs only when the method completes normally.

```java
@Aspect
@Component
public class SuccessAspect {

    @AfterReturning(
        pointcut = "execution(* com.example.orders.service..*.*(..))",
        returning = "result"
    )
    public void afterSuccess(JoinPoint joinPoint, Object result) {
        System.out.println(
            "Success: " + joinPoint.getSignature().getName()
        );
    }
}
```

`returning = "result"` binds the method's return value to the parameter named `result`.

Notes:

- A method throwing an exception will not trigger `@AfterReturning` for that call.
- Advice can observe `result`.
- `@AfterReturning` is not an API for directly replacing the return value received by the caller.
- If you want to intentionally alter the result, use `@Around` with a compatible return type.

Avoid logging `result` verbatim if it contains sensitive information.

## 11. @AfterThrowing

`@AfterThrowing` runs when a method throws a matching exception.

```java
@Aspect
@Component
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* com.example.orders.service..*.*(..))",
        throwing = "error"
    )
    public void afterFailure(
            JoinPoint joinPoint,
            Throwable error) {

        System.out.println(
            "Failed method: " + joinPoint.getSignature().getName()
                + ", error type: " + error.getClass().getSimpleName()
        );
    }
}
```

`throwing = "error"` binds the exception to the advice parameter.

This advice is suitable for recording failure metrics or auditing errors. It does not automatically swallow exceptions or turn a failed call into a success.

If you need fallback, retry, or exception transformation, design that explicitly in `@Around` or an appropriate handling layer, considering transactions and idempotence.

## 12. @After

`@After` runs when method execution ends, regardless of whether it returns normally or throws an exception.

```java
@Aspect
@Component
public class CompletionAspect {

    @After(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public void after(JoinPoint joinPoint) {
        System.out.println(
            "Completed " + joinPoint.getSignature().toShortString()
        );
    }
}
```

It has semantics similar to `finally`, suitable for cleanup or recording completion.

| Method outcome | `@AfterReturning` | `@AfterThrowing` | `@After` |
|---|---:|---:|---:|
| Returns normally | Runs | Does not run | Runs |
| Throws matching exception | Does not run | Runs | Runs |
| Does not match pointcut | Does not run | Does not run | Does not run |

The table considers properly configured advices when the call passes through the proxy. When multiple advices have different orders, an exception may have already been handled or transformed at another layer in the interceptor chain.

## 13. @Around and ProceedingJoinPoint

`@Around` is the most flexible because it can run code before/after, decide when to call `proceed()`, and handle return values/exceptions.

Pattern:

```java
@Around(
    "execution(* com.example.orders.service..*.*(..))"
)
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long startedAt = System.nanoTime();

    try {
        Object value = pjp.proceed();
        return value;
    } catch (Throwable error) {
        // Record failure, then preserve the exception.
        throw error;
    } finally {
        long elapsed = System.nanoTime() - startedAt;
        System.out.println("Elapsed: " + elapsed);
    }
}
```

### 13.1. What happens if proceed is not called?

If the advice does not call `proceed()`, the rest of the interceptor chain and the target method may not execute.

That is sometimes the goal of a blocking/caching mechanism, but it can also cause hard-to-find bugs. For example, a data-writing method that gets skipped will not perform its expected side effects.

### 13.2. What happens if proceed is called multiple times?

If the advice calls `proceed()` multiple times where supported, the business logic may execute multiple times. For operations like sending emails, charging money, or inserting data, the consequences can be serious.

Do not use AOP retry without defining exception policies, transactions, attempt limits, and business idempotency.

### 13.3. Preserving types and exceptions

The safe form for observational advice is:

```java
return pjp.proceed();
```

`@Around` typically returns `Object` and declares `throws Throwable` so it can forward whatever result or error the target produces. If an advice returns an object incompatible with the method signature, the caller may encounter runtime type errors.

## 14. What information does JoinPoint provide?

`@Before`, `@After`, `@AfterReturning`, and `@AfterThrowing` advice can accept `JoinPoint`. `@Around` uses `ProceedingJoinPoint`.

```java
@Before(
    "execution(* com.example.orders.service..*.*(..))"
)
public void inspect(JoinPoint jp) {
    String methodName = jp.getSignature().getName();
    String signature = jp.getSignature().toShortString();

    Object[] args = jp.getArgs();
    Object proxy = jp.getThis();
    Object target = jp.getTarget();

    System.out.println(methodName);
    System.out.println(signature);
    System.out.println("Argument count: " + args.length);
    System.out.println("Proxy type: " + proxy.getClass().getName());
    System.out.println("Target type: " + target.getClass().getName());
}
```

Meaning:

| API | Information |
|---|---|
| `getSignature()` | Method signature |
| `getArgs()` | Array of call arguments |
| `getThis()` | Reference to the proxy |
| `getTarget()` | Reference to the target object |
| `getKind()` | Join point kind |
| `getSourceLocation()` | Source location when supported |

**getThis differs from getTarget:** in Spring proxy AOP, `getThis()` refers to the proxy, while `getTarget()` refers to the business object.

Do not grab `getTarget()` and call methods on it directly to bypass advice, as that can break transaction, logging, security, or other interceptor behavior.

Do not log all of `getArgs()` by default: the array may contain passwords, access tokens, personal data, or large payloads.

## 15. Writing pointcuts with execution(...)

Common syntax:

```text
execution(modifiers-pattern? return-type-pattern declaring-type-pattern?method-name-pattern(parameter-pattern) throws-pattern?)
```

Example:

```java
@Pointcut(
    "execution(* com.example.orders.service..*.*(..))"
)
public void serviceMethods() {}
```

Where:

- `execution` selects method execution join points.
- First `*`: any return type.
- `com.example.orders.service..*`: types in the package and service subpackages.
- `.*`: any method name.
- `(..)`: any number and types of parameters.

Other examples:

| Expression | Meaning |
|---|---|
| `execution(* com.example.orders.service.OrderService.placeOrder(..))` | `placeOrder` method of `OrderService` |
| `execution(public * com.example.orders.service..*.*(..))` | Public service methods in the package and subpackages |
| `execution(* com.example.orders.service..*.find*(..))` | Methods starting with `find` |
| `execution(* *(String))` | Methods taking a single `String` parameter within expression scope |
| `execution(* com.example.orders.service..*.*())` | Service methods with no parameters |
| `execution(* com.example.orders.service..*.*(..))` | Any service method with a matching signature |

Important point: **signature matching does not guarantee advice runs**. The call must pass through the proxy and the method must be interceptable by the proxy.

### 15.1. Wildcard symbols

- `*` is a wildcard in positions permitted by the expression.
- `()` is a method with no parameters.
- `(*)` is a method with one parameter of any type.
- `(..)` is a method with any number and types of parameters.
- `..` in a type pattern expresses package hierarchy.
- A dot separates the declaring type and method name.

Keep pointcuts narrow in scope. An overly broad expression can hit infrastructure methods or code that should not be tracked.

## 16. Other pointcut designators

Spring AOP supports a useful set of expression designators:

| Designator | Example | Purpose |
|---|---|---|
| `execution` | `execution(* com.example..service..*.*(..))` | By method signature |
| `within` | `within(com.example.orders.service..*)` | Restricts declaring types |
| `this` | `this(com.example.orders.api.OrderOperations)` | Checks proxy type |
| `target` | `target(com.example.orders.service.OrderService)` | Checks target type |
| `args` | `args(java.lang.String,..)` | By runtime argument types |
| `@annotation` | `@annotation(com.example.orders.aop.TrackExecution)` | By annotation on the method |
| `@within` | `@within(com.example.orders.aop.Tracked)` | By annotation on the declaring type |
| `@target` | `@target(com.example.orders.aop.Tracked)` | By annotation on the runtime target type |
| `@args` | `@args(com.example.orders.aop.AuditedArgument)` | By annotation on argument types |
| `bean` | `bean(orderService)` | By bean name; a Spring AOP extension |

Not every AspectJ designator is supported by Spring AOP. For instance, `call`, `get`, and `set` in AspectJ weaving do not mean Spring proxies support intercepting field access.

### 16.1. this() differs from target()

With a JDK dynamic proxy:

- The proxy implements interfaces and may not be an instance of the concrete target class.
- The target is the concrete implementation.

Thus `this(SomeInterface)` and `target(SomeConcreteClass)` can both match the same call, whereas `this(SomeConcreteClass)` may not match a JDK proxy. Use these designators when you genuinely need to distinguish proxy and target types.

### 16.2. bean() by name

```java
@Pointcut("bean(orderService)")
public void orderBeanOnly() {}
```

Or using a pattern:

```java
@Pointcut("bean(*Service)")
public void namedServiceBeans() {}
```

`bean` is specific to Spring AOP, so behavior depends on the registered bean name. Renaming a bean can alter aspect scope.

## 17. Using annotations to select methods

Selecting by package is convenient but can be too broad. Custom annotations let you mark methods that truly need tracking.

### 17.1. Declare the annotation

```java
package com.example.orders.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackExecution {
}
```

`RetentionPolicy.RUNTIME` allows infrastructure to inspect the annotation at runtime.

### 17.2. Mark the target

```java
package com.example.orders.service;

import com.example.orders.aop.TrackExecution;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @TrackExecution
    public String settle(String paymentId) {
        return "Settled " + paymentId;
    }

    public String status(String paymentId) {
        return "PENDING";
    }
}
```

### 17.3. Pointcut and advice

```java
package com.example.orders.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {

    @Pointcut(
        "@annotation(com.example.orders.aop.TrackExecution)"
    )
    public void trackedMethods() {}

    @Around("trackedMethods()")
    public Object measure(ProceedingJoinPoint pjp)
            throws Throwable {

        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            System.out.println(
                pjp.getSignature().getName() + " took "
                + (System.nanoTime() - started) + " ns"
            );
        }
    }
}
```

If `PaymentService` is managed by Spring and called through a proxy, `settle(...)` is selected by the advice, whereas `status(...)` does not match the annotation pointcut.

Note that placing an annotation on an interface vs. a concrete class and the proxy type can affect how matching works. Place annotations where interception is needed and test with your project's context.

## 18. Combining multiple pointcuts

Pointcut expressions can be combined using:

- `&&`: AND.
- `||`: OR.
- `!`: NOT.

These are **AspectJ pointcut expression** operators, unlike Spring profile expressions (profiles use `&` and `|`).

Example:

```java
@Aspect
@Component
public class ServiceTrackingAspect {

    @Pointcut(
        "within(com.example.orders.service..*)"
    )
    public void serviceLayer() {}

    @Pointcut(
        "@annotation(com.example.orders.aop.TrackExecution)"
    )
    public void trackedMethods() {}

    @Around("serviceLayer() && trackedMethods()")
    public Object track(ProceedingJoinPoint pjp)
            throws Throwable {

        long started = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            System.out.println(
                "Elapsed: " + (System.nanoTime() - started)
            );
        }
    }
}
```

This condition requires the method **to be in the service layer** and **bear `@TrackExecution`**.

An OR expression:

```java
@Pointcut(
    "within(com.example.orders.service..*)"
      + " || within(com.example.orders.repository..*)"
)
public void serviceOrRepository() {}
```

A NOT expression (assuming a `SkipTracking` annotation exists):

```java
@Pointcut(
    "within(com.example.orders.service..*)"
      + " && !@annotation(com.example.orders.aop.SkipTracking)"
)
public void trackedServiceExceptOptOut() {}
```

If an expression becomes too long, split responsibilities or use clearer marker annotations.

## 19. JDK dynamic proxy and class-based proxy

Spring AOP primarily uses two proxy mechanisms.

### 19.1. JDK dynamic proxy

- The proxy implements interfaces.
- Consumers can call through an interface.
- The proxy is not necessarily an instance of the concrete implementation class.
- Only methods exposed through the proxy's interfaces are intercepted this way.

```java
public interface OrderOperations {
    void submit(String orderId);
}

@Service
public class OrderService implements OrderOperations {

    @Override
    public void submit(String orderId) {
        System.out.println("Submit " + orderId);
    }
}
```

If Spring uses a JDK proxy, designing to inject `OrderOperations` is usually more appropriate than requiring the concrete type.

### 19.2. Class-based proxy (CGLIB)

- The proxy is a dynamically generated subclass of the target class.
- Can proxy classes without interfaces.
- Requires the target class and methods to comply with override rules.
- A `final class` cannot be subclassed.
- A `final method` cannot be overridden/intercepted.
- A `private method` cannot be overridden.

Some Spring Boot lines have `spring.aop.proxy-target-class` to control proxy type; defaults depend on version and configuration. Do not assume the proxy mode solely from whether a class has an interface.

### 19.3. Common limitations

Whether using JDK or class-based proxies:

1. The bean must be managed by Spring.
2. AOP infrastructure and the aspect must be active.
3. The pointcut must match.
4. The call must pass through the proxy.
5. The method must be interceptable.

That is why the same method sometimes triggers advice and sometimes does not, even when source code has not changed.

## 20. Self-invocation: calls within the same class bypass the proxy

Look at this service:

```java
@Service
public class ReportService {

    public void generateAll() {
        generateOne();
    }

    @TrackExecution
    public void generateOne() {
        System.out.println("Generating report");
    }
}
```

Consumer calls:

```java
reportService.generateOne();
```

If `reportService` is a Spring proxy, `generateOne`'s advice can run.

However, if the consumer calls:

```java
reportService.generateAll();
```

then inside the target, `generateAll` calls `this.generateOne()`. This internal call **bypasses the proxy**, so the advice dedicated to `generateOne` does not run.

```text
Consumer
   │
   ▼
Spring proxy
   │
   ▼
Target.generateAll()
   │
   └── this.generateOne()
            │
            └── Does not go through proxy
```

### Solution: extract a bean

```java
@Service
public class SingleReportService {

    @TrackExecution
    public void generateOne() {
        System.out.println("Generating report");
    }
}
```

```java
@Service
public class BatchReportService {

    private final SingleReportService singleReportService;

    public BatchReportService(
            SingleReportService singleReportService) {
        this.singleReportService = singleReportService;
    }

    public void generateAll() {
        singleReportService.generateOne();
    }
}
```

When `SingleReportService` is injected as a Spring bean proxy, calls from `BatchReportService` pass through the proxy, allowing advice to apply.

Techniques like self-injection or `AopContext.currentProxy()` exist, but they add coupling to AOP infrastructure. Extracting a bean is usually easier to read, test, and maintain.

## 21. Final, private, static, and new

Matching conditions alone are not enough for advice to work.

| Situation | Why advice may not run |
|---|---|
| Object created with `new` outside Spring | Not a Spring-managed AOP proxy |
| `private` method | Cannot be intercepted as an overridable proxy method |
| `final` method with class-based proxy | Method cannot be overridden |
| `final` class with class-based proxy | Class cannot be subclassed |
| `static` method | Not an instance method intercepted via a Spring proxy |
| Self-invocation | Call does not go through proxy |
| Aspect not registered as a bean | No corresponding advisor |
| Pointcut does not match | Advice does not select the join point |
| Bean excluded by `@Profile`/condition | No matching bean to proxy |

Do not change visibility arbitrarily just to make AOP run. Define appropriate public service boundaries and move advised behavior to methods/beans accessible through a proxy.

## 22. Ordering multiple aspects

A method can match multiple aspects:

- Tracing.
- Timing.
- Logging.
- Transaction interceptor.
- Security checks.

Advices form an interceptor chain. Ordering can affect measured durations, transaction boundaries, and how errors are recorded.

You can set `@Order`:

```java
@Aspect
@Component
@Order(10)
public class OuterAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        System.out.println("Outer before");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("Outer after");
        }
    }
}
```

```java
@Aspect
@Component
@Order(20)
public class InnerAspect {

    @Around(
        "execution(* com.example.orders.service..*.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        System.out.println("Inner before");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("Inner after");
        }
    }
}
```

An aspect with a lower `@Order` value normally has higher precedence: **enters first, exits last**.

Illustrative order:

```text
Outer before
Inner before
Target method
Inner after
Outer after
```

Do not rely on Java method declaration order to infer advice execution order across aspects. When ordering is a critical requirement, configure it explicitly and verify via an appropriate integration test.

## 23. AOP and other Spring annotations

Features such as transactions, caching, and async can use proxy/interceptor concepts in their respective Spring configurations.

Example:

```java
@Service
public class CheckoutService {

    @Transactional
    public Receipt checkout(CheckoutCommand command) {
        // Perform data operations.
        return new Receipt(command.orderId());
    }
}
```

When transaction management is enabled and a suitable transaction manager is present, a proxy can open/commit/roll back a transaction around the method.

Similarly:

- `@Cacheable` requires caching support and a cache manager.
- `@Async` requires asynchronous execution to be enabled.
- `@Transactional` requires appropriate transaction infrastructure.

**The AOP starter does not automatically make every module's annotations work.** Each feature has its own prerequisites/infrastructure.

These features are also typically subject to self-invocation limits: a `this.innerMethod()` call does not pass through the proxy, so advice configured specifically for `innerMethod` may not run.

## 24. AOP and reactive/asynchronous execution

A timing aspect:

```java
long start = System.nanoTime();
Object result = pjp.proceed();
long duration = System.nanoTime() - start;
```

measures **the synchronous execution portion of the `proceed()` call**.

If a method returns `Mono` or `Flux`, the method may only build and return a publisher; the real work happens upon subscription. Thus timing around `proceed()` can finish before the reactive task completes.

Example:

```java
public Mono<Order> loadOrder(String id) {
    return repository.findById(id);
}
```

Similarly, with `CompletableFuture`, the method may return the future before asynchronous processing finishes.

To measure end-to-end latency, instrument the right lifecycle: reactive signals such as `doOnSubscribe`/`doFinally` or appropriate observation/tracing mechanisms, as well as future completion.

**Do not treat timing around `proceed()` as the total duration of an asynchronous operation.**

## 25. Inspecting proxies and debugging

Spring AOP provides utilities to tell whether a Spring bean has been proxied:

```java
import org.springframework.aop.support.AopUtils;

boolean aopProxy = AopUtils.isAopProxy(orderService);
boolean jdk = AopUtils.isJdkDynamicProxy(orderService);
boolean cglib = AopUtils.isCglibProxy(orderService);
```

A debugging runner can print:

```java
@Component
public class ProxyInspector implements ApplicationRunner {

    private final OrderService orderService;

    public ProxyInspector(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
            "Is proxy: " + AopUtils.isAopProxy(orderService)
        );
    }
}
```

The example needs corresponding imports for `ApplicationRunner`, `Component`, and `AopUtils`.

If an aspect is not running, check in order:

1. Is the target a Spring bean?
2. Are the AOP dependency and auto-configuration ready?
3. Is the `@Aspect` class registered as a bean?
4. Is the bean excluded by a condition or profile?
5. Does the pointcut match the method signature?
6. Does the call go from a consumer into the proxy?
7. Is the method restricted by `private`, `final`, or self-invocation?
8. Is the JDK/CGLIB proxy type compatible with the injection type and called method?
9. Do multiple aspects alter control flow or exceptions?
10. Does asynchronous execution cause observation timing to differ from expectations?

Do not conclude advice is active merely by seeing `@Aspect` on a class.

## 26. Integration tests to verify advice runs

A unit test creating the target with `new` tests business logic, but does not create a Spring proxy to test advice.

You can use a bean counting advice executions:

```java
@Component
public class AdviceCounter {

    private final AtomicInteger counter = new AtomicInteger();

    public void increment() {
        counter.incrementAndGet();
    }

    public int value() {
        return counter.get();
    }
}
```

Aspect:

```java
@Aspect
@Component
public class CountingAspect {

    private final AdviceCounter counter;

    public CountingAspect(AdviceCounter counter) {
        this.counter = counter;
    }

    @Before(
        "execution(* com.example.orders.service.OrderService.placeOrder(..))"
    )
    public void count() {
        counter.increment();
    }
}
```

Test:

```java
@SpringBootTest
class OrderServiceAopTest {

    @Autowired
    OrderService orderService;

    @Autowired
    AdviceCounter counter;

    @Test
    void adviceRunsWhenCallingProxiedBean() {
        int before = counter.value();

        orderService.placeOrder("A01");

        assertEquals(before + 1, counter.value());
    }
}
```

The example assumes JUnit/Spring Test imports, Spring AOP setup, and classes from earlier sections. If JDK dynamic proxies are chosen, inject the proxied interface instead of the concrete target class.

Cases to test:

- Matching method: counter increments.
- Non-matching method: counter does not increment.
- Target throws exception: failure/finally advice behaves per contract.
- Self-invocation: inner method bypasses proxy.
- Two aspects: ordering according to `@Order`.

## 27. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@Aspect` declared but advice does not run | Aspect is not a bean or AOP infrastructure is missing | Check `@Component`, `@Bean`, dependencies |
| Annotated method is not intercepted | Object created with `new` | Use Spring-managed bean |
| Advice runs from controller but not when called internally | Self-invocation | Extract method to another bean |
| Pointcut does not match | Wrong package, class, or method pattern | Check expression |
| Target method is final/private | Proxy limitation | Change design/bean boundaries |
| Cannot inject concrete class | JDK proxy may be in use | Inject interface or configure appropriate proxy mode |
| Advice does not run on success | Using `@AfterThrowing` | Use `@AfterReturning` for success |
| Advice does not run on failure | Using `@AfterReturning` | Use `@AfterThrowing` or `@After` |
| Measured time unusually short for reactive method | `proceed()` only returns publisher | Measure on subscription/completion |
| ClassCastException or wrong return | `@Around` returns incompatible object | Return the result of `proceed()` |
| Data-writing operation runs multiple times | `proceed()` called repeatedly | Retry only with clear contract and idempotence |
| Logs contain secrets | Printing raw args/result | Redact and log only safe metadata |

## 28. Aspect design principles

### 28.1. One clear concern per aspect

A timing aspect should only measure/record duration; an auditing aspect should only record audits. Do not mix authorization, retry, database writes, and response transformation into one class with an overly broad pointcut.

### 28.2. Keep pointcuts narrow

Compare:

```java
@Around("execution(* *(..))")
```

with:

```java
@Around("@annotation(com.example.orders.aop.TrackExecution)")
```

The first is very broad; the second selects only marked methods. Choose expressions based on intent and architectural boundaries.

### 28.3. Preserve return values and exceptions

For observational advice, prefer:

```java
try {
    return pjp.proceed();
} finally {
    // Record measurements or cleanup.
}
```

Do not change how many times the target runs or swallow errors unless that is a clearly defined requirement.

### 28.4. Consider performance and security

Broadly applied advice can add overhead. Logging arguments/results can expose secrets and personal data. Use sampling, metrics, redaction, and production-grade monitoring systems.

### 28.5. Clarify ordering and transactions

An interceptor's position in the chain affects which portion of time is measured and transaction boundaries. When ordering matters, express it via `@Order` and verify in your actual setup.

## 29. Practice exercises

### Exercise A — Identify the five concepts

Given:

```java
@Aspect
@Component
public class LoggingAspect {

    @Before("execution(* com.example.shop.service..*.*(..))")
    public void log(JoinPoint jp) {
        System.out.println(jp.getSignature().getName());
    }
}
```

Identify the aspect, advice, pointcut, join point, and target when `ProductService.findById(...)` is called by a consumer via a proxy.

### Exercise B — Timing with @Around

Create `BookService.findById` and a timing aspect. Call it via a Spring-managed consumer. Have the method throw an exception and observe the `finally` block.

### Exercise C — Advice types

Create `@Before`, `@AfterReturning`, `@AfterThrowing`, and `@After` on a service method. Compare a successful call with a call throwing an exception.

### Exercise D — Named pointcut

Create `@Pointcut("within(com.example.shop.service..*)")`, then reuse it across two advices. Change the package and test the scope.

### Exercise E — Annotation pointcut

Create `@TrackExecution` with runtime retention. Mark one of two methods in a service and write an `@annotation(...)` pointcut applying only to the marked method.

### Exercise F — Self-invocation

Create `outer()` calling `inner()` in the same class. Attach advice to `inner()`. Compare calling from a consumer bean with calling internally; then extract `inner` into another Spring bean.

### Exercise G — Proxy type

Create an interface and implementation; use `AopUtils` to inspect JDK/class-based proxies. Explain why `getThis()` and `getTarget()` are not identical.

### Exercise H — Order and nested advice

Create two `@Around` aspects with `@Order(10)` and `@Order(20)`. Log before/after messages to observe nesting.

### Exercise I — Reactive timing

Create a method returning `Mono<String>` with delayed reactive work. Compare duration around `proceed()` with total time until reactive chain completion.

### Exercise J — Debug non-matching issues

Intentionally create a bean with `new`, or introduce self-invocation, or misspell the package in the execution pattern. Propose diagnoses starting from target/proxy/pointcut and fix each bug.

## 30. Key takeaways

1. **Aspect** encapsulates a cross-cutting concern.
2. **Advice** is behavior running before/after/around a method.
3. **Pointcut** is a rule selecting join points, such as `execution(...)` and `@annotation(...)`.
4. **Join point in Spring AOP** is method execution.
5. **Target object** holds business logic; **proxy** stands in front of the target to intercept calls.
6. `@Before` runs before the method; `@AfterReturning` after success; `@AfterThrowing` after an exception; `@After` acts like finally; `@Around` wraps and controls continuing the call.
7. `ProceedingJoinPoint.proceed()` continues the interceptor chain; omitting it can skip the target, and calling it multiple times can repeat side effects.
8. `JoinPoint.getThis()` refers to the proxy, while `getTarget()` refers to the target.
9. Pointcut matching is not enough: calls must pass through the proxy and methods must be interceptable.
10. JDK dynamic proxies rely on interfaces; class-based proxies rely on subclassing and are constrained by final/private.
11. Self-invocation is a common reason advice fails to trigger.
12. Multiple aspects can layer together; configure ordering when needed.
13. `@Transactional`, caching, and async can use proxies but require their own infrastructure.
14. Measuring around `proceed()` on reactive/async methods does not mean measuring until task completion.
15. AOP tests must invoke through Spring bean proxies, not just manually instantiated objects.
16. Advice should observe safely, avoid altering return values/exceptions unnecessarily, and avoid logging sensitive data.

**Core mindset:** when reading AOP code, ask in sequence: *Which concern is separated into the aspect? What does the advice do? Which methods does the pointcut select? Which join point actually executes? Which target object holds the business logic? And does the call go through the proxy?* Answering these questions helps you understand exactly when Spring AOP operates and why.
