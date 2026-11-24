# Declaring Named Pointcuts with `@Pointcut` in Spring AOP

## 1. Why name a pointcut?

In Spring AOP, annotations such as `@Before`, `@Around`, and `@AfterReturning` often need an expression to specify **which method invocations on Spring beans will be advised**. Writing long expressions inline on every advice easily leads to repetition and maintenance difficulties:

```java
@Before("execution(public * com.example.shop.service.*.*(..))")
public void audit() { /* ... */ }

@AfterReturning("execution(public * com.example.shop.service.*.*(..))")
public void recordSuccess() { /* ... */ }
```

These two advice methods duplicate the same method selection policy. When the package scope or service name changes, multiple places need to be updated and it is easy to miss one. Spring supports declaring a **named pointcut** using `org.aspectj.lang.annotation.Pointcut`. You declare a `void` method annotated with `@Pointcut("...")`, and then **reference the method name** in advice or in another pointcut.

```java
@Pointcut("execution(public * com.example.shop.service.*.*(..))")
public void serviceOperation() {}

@Before("serviceOperation()")
public void audit() { /* ... */ }

@AfterReturning("serviceOperation()")
public void recordSuccess() { /* ... */ }
```

This is a **fragment** inside an `@Aspect` class registered as a Spring bean, not a standalone Java file.

The most important point: **`serviceOperation()` is the name of a pointcut parsed and referenced by Spring, not a method containing business logic to be invoked at runtime.** The pointcut method body is normally empty, and Spring does not invoke that method body whenever a join point matches.

The scope of this lesson is **Spring Aspects using the `@AspectJ` annotation-style on Spring-managed beans via proxies**, focusing strictly on Aspects in Spring as required. It does not go into AspectJ weaving outside Spring or join point kinds not supported by Spring AOP.

## 2. Anatomy of a named pointcut

A typical declaration:

```java
import org.aspectj.lang.annotation.Pointcut;

@Pointcut("execution(public * com.example.shop.OrderService.submit(..))")
public void orderSubmission() {}
```

There are three parts to distinguish:

| Component | Meaning |
| --- | --- |
| `@Pointcut("execution(...)")` | **Pointcut expression**: describes which method executions match. |
| `public void orderSubmission()` | **Pointcut signature**: the name and formal parameters (if any) for other locations to reference. |
| `{}` | **Method body**: normally empty; not the place to handle actual invocations. |

### Syntax rules

1. A method annotated with `@Pointcut` **must return `void`**.
2. The method name is the pointcut name: write `orderSubmission()` in an advice expression **with parentheses**, even when the signature takes no parameters.
3. If the pointcut needs to bind arguments, the signature can declare Java parameters; these are **parameters used for binding**, which does not mean Spring will invoke the method body.
4. Java visibility such as `private`, `protected`, or `public` determines **where the pointcut name can be referenced** according to standard rules; it **does not change the scope of method executions matched by the pointcut expression**.
5. The expression inside the annotation is an AspectJ pointcut expression supported and parsed by Spring. Spring AOP only supports **method execution join points on beans managed through Spring proxies**.

Another illustrative example:

```java
@Pointcut("within(com.example.shop.service..*)")
private void inServiceLayer() {}

@Pointcut("execution(public * *(..))")
private void publicMethod() {}

@Pointcut("inServiceLayer() && publicMethod()")
private void publicServiceMethod() {}
```

When referencing `publicServiceMethod()`, Spring combines **both conditions**. You do not need to copy the `within(...)` and `execution(...)` expressions to every advice.

## 3. A named pointcut is not an advice and does not trigger logic on its own

A common misconception is thinking that:

```java
@Pointcut("execution(* com.example..service.*.*(..))")
public void businessOperation() {
    System.out.println("pointcut invoked");
}
```

will print a log every time a service method runs. **That is not the case.** The method body is just an ordinary Java body; Spring AOP uses **annotation metadata** and does not invoke the body to decide matching.

If some code actually calls `businessOperation()` like a regular Java method, it merely executes the Java body like any other method. It **does not trigger advice, does not execute a query to find join points, and does not run the methods described by the expression**.

Standard practice:

```java
@Pointcut("execution(* com.example..service.*.*(..))")
public void businessOperation() {}

@Before("businessOperation()")
public void traceServiceCall(org.aspectj.lang.JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}
```

This is a **fragment** inside an aspect, requiring `@Before`, `@Pointcut` imports, and bean registration. `businessOperation()` is the referenced name; logging must be placed inside the **advice method**, not in the pointcut body.

It is also important to distinguish `@Pointcut` from the Spring `org.springframework.aop.Pointcut` **interface**. The `@Pointcut` annotation belongs to the `@AspectJ` declaration style; the `Pointcut` interface belongs to the Spring AOP infrastructure API. Both express "selecting join points", but they are not interchangeable syntaxes at the annotation site.

## 4. Referencing a named pointcut within the same aspect

An aspect can place `@Pointcut` and multiple advice methods in the same class:

```java
package com.example.shop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class ServiceAspect {

    @Pointcut("execution(public * com.example.shop.OrderService.*(..))")
    private void orderServiceOperations() {}

    @Before("orderServiceOperations()")
    public void beforeOrderService(JoinPoint jp) {
        System.out.println("before " + jp.getSignature().getName());
    }

    @AfterReturning("orderServiceOperations()")
    public void afterSuccess() {
        System.out.println("success");
    }
}
```

The class above is a Java class with full imports, but it is **not yet a standalone runnable example** because it still lacks `OrderService`, `@EnableAspectJAutoProxy`, and aspect bean registration.

Because `orderServiceOperations()` is a **private method in the same class**, both `@Before` and `@AfterReturning` can reference it by its short name. `public` is not required just because advice resides in the same aspect.

Concrete advantages:

- A single change to the `OrderService` scope consistently affects both advice methods.
- The name `orderServiceOperations` is easier to understand than a repeated long expression.
- Reviewers can look at the expression to see **what is selected**, and look at the advice to see **what is done**.
- You can write integration tests to verify a shared interception point used by multiple advice methods.

**Note on execution count:** if both `@Before` and `@AfterReturning` share the same named pointcut, a single method invocation that returns normally can trigger **two different types of advice**. This is designed behavior, not Spring registering the pointcut twice.

## 5. Sharing pointcuts across multiple aspects using a dedicated class

When multiple aspects care about the same set of methods, expose a named pointcut in a dedicated class and reference it by its fully qualified name:

```java
public class CommonPointcuts {
    @Pointcut("execution(public * com.example.shop.service..*.*(..))")
    public void serviceOperation() {}
}

// Inside an @Aspect bean:
@Before("com.example.shop.aop.CommonPointcuts.serviceOperation()")
public void audit() {}
```

These two illustrative code snippets belong in their respective files/packages. A class containing only `@Pointcut` declarations does not need to be a Spring bean; a class containing advice must be an aspect bean. For pointcuts shared across packages, the declaring class and method must be accessible (usually `public`). The lesson **"Sharing Pointcuts Across Aspects"** covers shared contracts, multiple advice methods, and testing in depth.

## 6. Combining named pointcuts with `&&`, `||`, `!`

Named pointcuts can be combined using `&&` (intersection), `||` (union), and `!` (negation). For example:

```java
@Pointcut("within(com.example.shop.service..*)")
private void serviceLayer() {}

@Pointcut("execution(public * *(..))")
private void publicMethod() {}

@Pointcut("serviceLayer() && publicMethod()")
private void publicServiceMethod() {}
```

In this example, an advice referencing `publicServiceMethod()` selects only public method executions in the service layer; the `private` visibility of the pointcut declaration methods is not a matching condition. When combining complex AND/OR expressions, use grouping parentheses and test cases that satisfy only one side. The lesson **"Combining Pointcuts by Architecture Layer or Functional Group"** analyzes grouping patterns, runnable examples, and matching outcomes.

## 7. Binding parameters through a named pointcut

A named pointcut can declare **formal parameters** to pass invocation data into an advice. For example:

```java
@Pointcut(
    value = "execution(public * com.example.shop.OrderService.submit(..))"
          + " && args(orderId)",
    argNames = "orderId"
)
public void submittingOrder(String orderId) {}

@Before(
    value = "submittingOrder(orderId)",
    argNames = "orderId"
)
public void traceSubmission(String orderId) {
    System.out.println("submitting " + orderId);
}
```

This is a **fragment inside `@Aspect`**. It differs from a parameterless named pointcut:

- `args(orderId)` is a **binding expression**, requiring a matching argument and binding its actual value.
- The method `submittingOrder(String orderId)` declares the type of the bound argument.
- `submittingOrder(orderId)` in `@Before` **passes the binding by name**, not calling a `void`-returning Java method.
- `argNames` clarifies parameter names for Spring/AspectJ binding and reduces reliance on compiler parameter metadata.
- The advice receives the **argument value of the invocation**, not an object created by `@Pointcut`.

If `submit(String orderId)` is invoked from a client through a Spring proxy with `"A-01"`, `traceSubmission` receives `"A-01"`.

A parameterized pointcut must be referenced with the **exact number of binding arguments**. Do not use `submittingOrder()` for a pointcut signature that requires `String orderId`, or declare mismatched names in `argNames`.

### `args` filters by runtime type, not by value checks

`args(orderId)` can match based on the advice parameter type; it does not check `orderId.startsWith("VIP")` simply because the name is `orderId`. If business logic needs to select special values, put that condition inside the appropriate advice or business policy, and test the result.

### Multiple parameters case

```java
@Pointcut(
    value = "execution(public * com.example.shop.OrderService.submit(..))"
          + " && args(orderId, request)",
    argNames = "orderId,request"
)
public void submittingOrder(String orderId, OrderRequest request) {}
```

This is a **fragment** that requires the `OrderRequest` class and corresponding method, not a standalone project. The `submit` method must take two matching arguments for the expression to match, or `args(...)` must be adjusted with `..` if more arguments are to be allowed.

Especially with `null`, primitives/boxing, varargs, or generic collections, test directly on your application's Spring version because runtime/type-matching has rules that a short named expression cannot replace.

## 8. Complete Java 17+ example: sharing `@Pointcut` across advice

The following Maven example runs pure Spring Framework and intentionally separates named pointcuts into a **`CommonPointcuts` class** to demonstrate reusability from another `@Aspect`.

Illustrative versions chosen: **JDK 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1**. This is a consistent sample version set, not claimed to be the latest.

Observed requirements:

1. `CommonPointcuts.orderSubmissions()` combines two smaller pointcuts.
2. `CommonPointcuts.submissionWithId(String)` binds a parameter from the actual invocation.
3. `AuditAspect` declares `@Before` for submission binding and `@AfterReturning` for the shared named pointcut.
4. Calling `OrderService.submit(...)` through the Spring AOP proxy runs both advice methods according to their responsibilities; calling `preview(...)` does not run the advice.
5. `@Pointcut` methods have empty bodies; there is no output from them.

### 8.1. Directory structure

```text
spring-named-pointcuts/
├── pom.xml
└── src/main/java/com/example/named/
    ├── AppConfig.java
    ├── OrderService.java
    ├── CommonPointcuts.java
    ├── AuditAspect.java
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
    <artifactId>spring-named-pointcuts</artifactId>
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

`spring-context` provides ApplicationContext and core Spring modules (including Spring AOP in the sample dependency graph); `aspectjweaver` provides the pointcut parser/matcher for `@AspectJ`. There is no AspectJ compiler or weaving agent: this is **Spring proxy-based AOP**.

### 8.3. `src/main/java/com/example/named/OrderService.java`

```java
package com.example.named;

public class OrderService {
    public String submit(String orderId) {
        System.out.println("[SERVICE] submit " + orderId);
        return "accepted:" + orderId;
    }

    public String preview(String orderId) {
        System.out.println("[SERVICE] preview " + orderId);
        return "preview:" + orderId;
    }
}
```

The `OrderService` class is a target bean with two public methods. The pointcut in this lesson intentionally selects only `submit`, not `preview`.

### 8.4. `src/main/java/com/example/named/CommonPointcuts.java`

```java
package com.example.named;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * com.example.named.OrderService.*(..))")
    public void orderServiceMethods() {}

    @Pointcut("execution(public * com.example.named.OrderService.submit(..))")
    public void submitMethods() {}

    @Pointcut("orderServiceMethods() && submitMethods()")
    public void orderSubmissions() {}

    @Pointcut(
        value = "orderSubmissions() && args(orderId)",
        argNames = "orderId"
    )
    public void submissionWithId(String orderId) {}
}
```

**Why organize it this way?**

- `orderServiceMethods()` describes the target class scope.
- `submitMethods()` describes the business operation.
- `orderSubmissions()` is the **intersection** of both conditions, keeping consumers unaware of expression details.
- `submissionWithId(String)` names the pointcut with an added **binding argument**.
- The `CommonPointcuts` class only contains shared public named pointcuts. It is not an aspect bean and **does not need to be registered as a bean**.

`orderServiceMethods()` can match both `submit` and `preview`; `orderSubmissions()` matches only `submit`. For demonstration purposes, the two conditions are intentionally kept separate for observability even though they could be merged into a shorter expression.

### 8.5. `src/main/java/com/example/named/AuditAspect.java`

```java
package com.example.named;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger beforeCount = new AtomicInteger();
    private final AtomicInteger successCount = new AtomicInteger();

    @Before(
        value = "com.example.named.CommonPointcuts.submissionWithId(orderId)",
        argNames = "orderId"
    )
    public void beforeSubmit(String orderId) {
        beforeCount.incrementAndGet();
        System.out.println("[AOP before] " + orderId);
    }

    @AfterReturning(
        pointcut = "com.example.named.CommonPointcuts.orderSubmissions()",
        returning = "result",
        argNames = "result"
    )
    public void afterSuccess(String result) {
        successCount.incrementAndGet();
        System.out.println("[AOP success] " + result);
    }

    public int beforeCount() {
        return beforeCount.get();
    }

    public int successCount() {
        return successCount.get();
    }
}
```

Here, a **parameterized** named pointcut supplies `orderId` to `@Before`, while a **parameterless** named pointcut is used for `@AfterReturning`. Both intentionally select `submit` yet retrieve different data:

- `@Before`: retrieves the **input** `orderId`, before the target method runs.
- `@AfterReturning`: retrieves the **output** via `returning="result"`, after the target method completes normally.
- The two counters accurately measure how many times each advice ran, not how many times a pointcut body was called.

### 8.6. `src/main/java/com/example/named/AppConfig.java`

```java
package com.example.named;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring `@AspectJ` support and uses class-based proxying so `OrderService` does not need to declare an interface. `AuditAspect` is registered via `@Bean`, because `@Aspect` **does not automatically turn a class into a Spring bean**. `CommonPointcuts` is merely a class defining pointcut metadata and does not need `@Bean`.

### 8.7. `src/main/java/com/example/named/DemoApp.java`

```java
package com.example.named;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            String result = service.submit("ORD-1");
            System.out.println("submitResult=" + result);

            String preview = service.preview("ORD-2");
            System.out.println("previewResult=" + preview);

            System.out.println("beforeCount=" + aspect.beforeCount());
            System.out.println("successCount=" + aspect.successCount());
        }
    }
}
```

### 8.8. Running the example and checking stdout

Requirements: JDK 17+, Maven able to download dependencies. In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.named.DemoApp
```

Lines printed in order by the example code (excluding any Maven/SLF4J logs):

```text
isAopProxy=true
[AOP before] ORD-1
[SERVICE] submit ORD-1
[AOP success] accepted:ORD-1
submitResult=accepted:ORD-1
[SERVICE] preview ORD-2
previewResult=preview:ORD-2
beforeCount=1
successCount=1
```

**Explanation:**

1. `isAopProxy=true`: the auto-proxy creator applied the advisors from `AuditAspect` to `OrderService`.
2. For `submit("ORD-1")`, `orderSubmissions()` evaluates to true and `submissionWithId(orderId)` binds `"ORD-1"`. `@Before` prints the first line.
3. The target prints `[SERVICE] submit ...`, and then `@AfterReturning` prints the return value.
4. `preview("ORD-2")` belongs to `orderServiceMethods()` but **not to `submitMethods()`**, so the intersection `orderSubmissions()` is false: there is no `[AOP]` line for preview.
5. Both counters equal 1. Spring did not have to execute the body of `CommonPointcuts.orderSubmissions()` to determine the match.
6. `@AfterReturning` only runs if the target method **returns normally**. If the target throws an exception, this advice does not run; a separate exception-handling policy is required if needed by the application.

This complete example prioritizes easily verifiable results: **one matched business method, one unmatched method, and two advice methods reusing a named pointcut in two ways**.

## 9. Referencing named pointcuts in other aspects or XML

### 9.1. Multiple aspects referencing the same class

Suppose `CommonPointcuts` has `public void orderSubmissions()`. Both an audit aspect and a metrics aspect can reference it:

```java
@Before("com.example.named.CommonPointcuts.orderSubmissions()")
public void auditCall() {
    // ...
}
```

```java
@Around("com.example.named.CommonPointcuts.orderSubmissions()")
public Object timeCall(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - start;
        // Send elapsed to the metric recorder.
    }
}
```

The two snippets above are **method fragments** belonging to their respective `@Aspect` classes (not standalone runnable code). They only reuse the **method selection rule**; each aspect remains responsible for its own logic. When running together, having multiple advice methods select the same method is normal, though ordering must be checked if there is a dependency between advice methods.

### 9.2. Referencing from a Spring XML advisor

Spring documentation also shows that a public named pointcut can be referenced by its fully qualified name inside `<aop:advisor>`, for example:

```xml
<aop:config>
    <aop:advisor
        pointcut="com.example.named.CommonPointcuts.orderSubmissions()"
        advice-ref="someAdvice"/>
</aop:config>
```

This is an **XML fragment**, requiring a file with the `aop` namespace and a `someAdvice` bean implementing the appropriate Spring `Advice`. It illustrates pointcut definition reusability, **not that you must enable both an XML advisor and Java advice simultaneously for the same behavior**.

If an application is migrating from XML to Java configuration, check for **duplicate advice functionality** and bean registration; Spring has mechanisms to coalesce standard auto-proxy creators, but it does not automatically deduplicate two distinct advice definitions just because they use the same named pointcut.

## 10. Common mistakes when using `@Pointcut`

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| Logic written inside `@Pointcut` method never runs | The named method is only a signature/metadata, not an advice callback. | Move the logic into `@Before`, `@Around`, `@AfterReturning`, etc. |
| `@Pointcut` method returns `boolean` or `String` | Invalid signature; a named pointcut must return `void`. | Change to `void` with an empty body. |
| Advice uses `@Before("serviceOperation")` | Missing `()` on parameterless pointcut name. | Write `@Before("serviceOperation()")`. |
| Another aspect cannot find the named pointcut | Method is `private`, missing fully qualified class name, or wrong package/type. | Use a `public` method and `com.example.CommonPointcuts.name()` when sharing. |
| `args(id)` fails to bind properly | Pointcut signature and `argNames` / advice parameter are out of sync. | Match names, order, types, and argument count; add explicit `argNames`. |
| Advice runs on many unintended services | Named pointcut is too broad, e.g., `execution(* *(..))`. | Restrict package/class/method in the expression and combine conditions. |
| `@Pointcut` declared but no advice runs at all | Aspect is not a bean, Spring AOP is not enabled, pointcut does not match, or caller bypasses proxy. | Verify `@Bean`/`@Component`, `@EnableAspectJAutoProxy`, `AopUtils`, and call path. |
| Assuming a separate `@Pointcut` class must be a bean | Confusing metadata definition with component lifecycle. | A named pointcut container does not need to be a bean to be referenced by type. |
| Changing `private` to `public` expecting the pointcut to match more methods | Confusing the visibility of the pointcut method with the visibility of the target method. | Put `public` inside `execution(public ...)`, do not rely on the Java modifier of the pointcut method. |
| Referencing `@Pointcut` name without `()` when combining | Invalid pointcut reference. | Write `inServiceLayer() && publicMethod()`. |
| Using `@Pointcut` with `call(...)`/field access | Spring proxy AOP does not support AspectJ call/get/set join points. | Use supported designators, primarily `execution`, for method execution via Spring proxy. |
| Advice does not run due to self-invocation | Calling `this.method()` from inside the target bypasses the proxy. | Move the business boundary to another bean and call through the proxy; a named pointcut does not fix self-invocation. |
| Two advice methods run on the same method and appear to duplicate the pointcut | Two independent advice methods reference the same named pointcut. | Inspect the advisors/bean instances and expected advice count per policy. |

## 11. Designing maintainable pointcut names and locations

A good name describes the **set of calls to select**: `serviceOperation()`, `orderSubmission()`, `auditedPaymentOperation()`. Names like `pointcut1()` or names that merely mirror `execution(...)` characters make the intent hard to understand at call sites. Avoid names that promise security when the pointcut only selects methods and does not itself enforce permissions.

Definitions used exclusively by one aspect can remain `private`; shared definitions should have an owning class and a clear public API. Renaming a named pointcut or the package of its containing class requires auditing all reference strings in advice/XML. The lesson **"Naming Pointcuts by Intent Instead of Expression String Details"** guides how to evaluate intent and preserve the matched set after changes.

## 12. Testing named pointcuts in Spring

To prove a named pointcut works, initialize a Spring context with AOP enabled, retrieve the target from the context, and invoke it through the proxy. Run at least **one method that must match** and **one method that must not match**; assert that the advice event/counter changes accurately while the target returns the expected result. For `A && B`, include cases that satisfy only A, only B, and both.

Contrast with `this.method()` and objects instantiated with `new` when the architecture risks bypassing the proxy. `AopUtils.isAopProxy(bean)` only tells whether a bean is proxied, not whether a specific advice actually ran. The lesson **"Testing Matched and Unmatched Pointcut Cases"** provides a full matrix and JUnit integration tests.

## 13. Quick summary and official documentation

| Question | Answer |
| --- | --- |
| How is a named pointcut declared? | A `void` method annotated with `@Pointcut("expression")`. |
| Does the `@Pointcut` method body run on a match? | No; Spring uses the name/signature and annotation metadata. |
| How to reference it in the same aspect? | `@Before("namedPointcut()")` or an equivalent advice annotation. |
| How to reference it from another class? | `com.example.CommonPointcuts.namedPointcut()` with appropriate Java visibility. |
| Can conditions be combined? | Yes: `&&`, `||`, `!`; name the smaller expressions. |
| Can arguments be passed into advice? | Yes: `args(name)`, formal parameters, and matching `argNames`. |
| Does `CommonPointcuts` need to be a Spring bean? | No, if the class only contains named pointcut definitions for referencing. |
| Does `@Pointcut` solve self-invocation? | No; Spring AOP remains proxy-based. |

Spring Framework Documentation:

- Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Declaring Advice (Binding Parameters to Advice): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion:** `@Pointcut` turns method-invocation selection criteria in Spring AOP into **a named, reusable, and composable definition**. A named pointcut describes **where to apply**, while the advice contains **the logic to execute**; for the advice to run, the target must still be a Spring bean and the invocation must pass through the appropriate proxy.
