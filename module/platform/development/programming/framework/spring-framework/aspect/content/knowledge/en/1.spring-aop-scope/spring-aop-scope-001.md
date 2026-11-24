# The Role of Spring AOP for Shared Behavior Across Beans

## 1. What Problem Does Spring AOP Solve in a Spring Application?

In a Spring application, many business beans may need the same technical behavior: logging method calls, measuring duration, checking access policies, collecting metrics, or applying an operational rule across multiple services. If each service repeats this code itself, business logic gets mixed with infrastructure logic; every change has to be edited in multiple places and easily becomes inconsistent.

**Spring AOP (Aspect-Oriented Programming)** lets you place shared behavior in a **Spring-managed aspect**, then apply it to matching bean method executions. The service focuses on its business work; the aspect holds the shared responsibility, and Spring connects the two parts through a **proxy**.

For example: `OrderService.placeOrder()` and `InvoiceService.issueInvoice()` both need to record an audit mark before processing. Spring AOP lets you write one shared auditing advice instead of copying log statements into both services.

The scope of this article is **the mechanism and usage of Spring AOP on Spring beans**. General AOP theory or standalone AspectJ weaving outside Spring is out of scope.

## 2. How Does Spring Weave Shared Behavior into Beans?

In a proxy-based Spring AOP configuration, a matching call has the following general path:

```text
Calling bean (controller, another service, command runner...)
        |
        v
Spring AOP proxy of the target bean
        |
        +--> Evaluate pointcut: does this method call match?
                 |
                 +--> Yes: run the corresponding advice
                 |           |
                 |           v
                 |       Target bean method
                 |           |
                 |           v
                 |       Post-call advice (if any)
                 |
                 +--> No: forward directly to the target bean
        |
        v
Return result or throw exception to the caller
```

Components to identify when reading Spring AOP code:

| Spring AOP Component | Specific Role in the Application |
| --- | --- |
| **Target bean** | The bean containing the business method, e.g. `OrderService`. |
| **Proxy** | A representative object created by Spring that intercepts calls to matching methods and coordinates advice. |
| **Aspect** | A bean annotated with `@Aspect`, organizing shared interception rules. |
| **Pointcut** | An expression that selects the methods/executions to which advice will be applied, e.g. public methods of `*Service` classes. |
| **Advice** | Code that runs before, after, or around the target method. |
| **Join point** | In **Spring AOP**, the supported join point is a **method execution** of a Spring bean. |

Important consequence: Spring AOP generally **does not directly modify the source code or bytecode of business classes**. Interactions must go through the proxy for advice to have a chance to run; this is the basis for understanding the limitations in section 6.

## 3. Runnable Example: One Aspect for Two Service Beans

The example uses **Java 17+, Spring Framework 6.1.14, and Maven**. The application boots a small Spring container with `AnnotationConfigApplicationContext`, without needing Spring Boot or a web server.

Structure:

```text
spring-aop-beans/
├── pom.xml
└── src/main/java/com/example/demo/
    ├── DemoApp.java
    ├── OrderService.java
    ├── InvoiceService.java
    └── SharedAuditAspect.java
```

**`pom.xml`** — `spring-context` provides the container and Spring AOP integration; `aspectjweaver` provides the AspectJ types and expression parser that Spring AOP uses for the `@Aspect` syntax.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-beans</artifactId>
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

**`src/main/java/com/example/demo/OrderService.java`**

```java
package com.example.demo;

public class OrderService {
    public void placeOrder(String orderId) {
        System.out.println("[ORDER] created " + orderId);
    }
}
```

**`src/main/java/com/example/demo/InvoiceService.java`**

```java
package com.example.demo;

public class InvoiceService {
    public void issueInvoice(String orderId) {
        System.out.println("[INVOICE] created for " + orderId);
    }
}
```

**`src/main/java/com/example/demo/SharedAuditAspect.java`**

```java
package com.example.demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class SharedAuditAspect {
    @Before("execution(public * com.example.demo.*Service.*(..))")
    public void recordCall(JoinPoint joinPoint) {
        System.out.println("[AUDIT] " + joinPoint.getSignature().getName());
    }
}
```

The expression `execution(public * com.example.demo.*Service.*(..))` selects executions of `public` methods with any return type (`*`), belonging to classes whose names end with `Service` in the exact `com.example.demo` package; both the method name and parameter list can vary. This is a **shared rule across multiple beans**, not hardcoded to a single method. In a real application, you should narrow the pointcut closely to the responsibility being applied to avoid intercepting too many calls.

**`src/main/java/com/example/demo/DemoApp.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class DemoApp {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public InvoiceService invoiceService() {
        return new InvoiceService();
    }

    @Bean
    public SharedAuditAspect sharedAuditAspect() {
        return new SharedAuditAspect();
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(DemoApp.class)) {
            OrderService orderService = context.getBean(OrderService.class);
            InvoiceService invoiceService = context.getBean(InvoiceService.class);

            orderService.placeOrder("O-42");
            invoiceService.issueInvoice("O-42");
        }
    }
}
```

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.demo.DemoApp
```

The lines printed by the program, in exact order:

```text
[AUDIT] placeOrder
[ORDER] created O-42
[AUDIT] issueInvoice
[INVOICE] created for O-42
```

**Explanation of the output:** the two services do not call `SharedAuditAspect` at all. The container registers three beans, `@EnableAspectJAutoProxy` activates the auto-proxying infrastructure, and Spring detects the `@Aspect` bean and selects advice for each matching method. `context.getBean(...)` returns a bean reference processed by Spring; calls from outside go through the proxy, so an `[AUDIT]` line appears before each business line. Using `proxyTargetClass = true` selects a class-based proxy for the example where the services do not declare interfaces.

If you remove the aspect registration or disable the AOP infrastructure, both business methods can still execute, but the `[AUDIT]` lines produced by the advice will not appear.

## 4. Advice Types for Shared Behavior

| Advice | Timing and Appropriate Use Cases |
| --- | --- |
| `@Before` | Before the target method runs; logging calls, checking simple preconditions. |
| `@AfterReturning` | When the method returns normally; tracking success or the return value. |
| `@AfterThrowing` | When the method throws an exception; recording errors according to policy. |
| `@After` | When the execution finishes whether by success or error; cleanup/marking completion, similar in spirit to `finally`. |
| `@Around` | Surrounds the call, can decide when to call `proceed()`, measure duration, handle the result/exception. |

Example illustrating `@Around` when you genuinely need control both before and after:

```java
@Around("execution(public * com.example.demo.*Service.*(..))")
public Object timeCall(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed(); // Must be called for the business logic to actually execute.
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        // Send elapsedNanos to the appropriate metric system.
    }
}
```

This is an **illustrative method snippet**, placed inside an `@Aspect` bean along with `import org.aspectj.lang.annotation.Around;`; it is not a standalone program and **must not be added verbatim alongside the example's `@Before` advice expecting stdout to stay unchanged**. `try/finally` ensures the end measurement runs even when the method throws an error; `proceed()` forwards execution to the target bean. When simple advice suffices, prefer `@Before`/`@AfterReturning` over `@Around` to avoid unnecessary flow control.

Within the same call, the ordering when multiple aspects/advices apply also depends on advice type, precedence (`@Order`/`Ordered`), and configuration. When ordering has business significance, it must be specified explicitly and tested; do not infer ordering solely from the declaration order of methods.

## 5. Practical Value and Responsibility Boundaries

Spring AOP delivers value when **one rule applies consistently across many beans or many methods**:

- **Operational observability:** recording operation names, execution time, call counts, success/failure status; using appropriate metadata rather than printing every sensitive parameter.
- **Technical rules at service boundaries:** checking a shared condition, attaching metadata, or standardizing call tracing.
- **Integration of Spring-provided policies:** features such as declarative transactions `@Transactional` can use similar interception/proxying; prefer official Spring mechanisms rather than writing custom aspects to replace the transaction manager, security interceptor, or cache abstraction.

A service must still clearly express its own task: validating business data, computing, updating state, and managing domain invariants. If logic applies to only a single use case, writing it directly in the service or an explicitly invoked component is usually easier to understand. Nor does AOP turn an arbitrary operation into a transaction, synchronize threads, or provide distributed guarantees; advice only supplies an interception point on methods within the right scope.

Setting a pointcut too broadly—for example, matching every method in the entire application—can create unnecessary overhead, hidden dependencies, and noisy logs. Select packages, interfaces, annotations, or method names based on the responsibility that truly needs to be shared, accompanied by tests for both matched and unmatched beans.

## 6. Limitations to Recognize When Sharing Advice

Spring AOP applies advice at **method calls passing through a Spring bean's proxy**, without altering every Java execution path. In the example above, the two calls retrieved from `ApplicationContext` receive the audit behavior; the two service classes themselves do not call the aspect.

- **Self-invocation:** if `ReportService.export()` calls `this.validate()`, advice targeted only at `validate()` will not receive this internal call. To intercept `validate()` from another service, call it through an injected bean.
- **Objects outside the container:** `new OrderService().placeOrder("O-99")` only runs the logic of the manually created object and does not automatically receive Spring AOP advice; conversely, an instance **registered via `@Bean`** can still be proxied even though the factory method uses `new`.
- **Proxyability:** a JDK proxy exposes methods through interfaces; CGLIB uses subclassing and cannot override `final`/`private` methods. Constructors, field access, and static methods are not among the method-execution join points supported by Spring AOP.
- **Asynchrony and errors:** `@AfterReturning` on a method returning `CompletableFuture` does not prove the future has completed successfully. Observing advice should preserve the return value and exception, while using an appropriate mechanism to measure the actual completion time.

These boundaries help decide whether to separate behavior into another bean or use a specialized Spring mechanism. Proxy mechanics, bean management conditions, and comparisons with AspectJ weaving are analyzed separately in their respective articles.

## 7. How to Design and Test Shared Behavior

A safe workflow for applying Spring AOP:

1. **Identify truly repeated behavior:** for example, recording audit logs at service entry points, clearly distinguishing business data from technical metadata.
2. **Scope the application points:** select the right beans and methods via pointcuts; if explicit opt-in is needed, create a dedicated annotation for the group of methods to track.
3. **Choose minimal advice:** `@Before` for start markers, `@AfterReturning`/`@AfterThrowing` for outcomes, `@Around` when managing the entire execution lifecycle is required.
4. **Ensure calls go through the container:** inject services, invoke proxies from other beans, and avoid `new` or self-invocation for methods that require interception.
5. **Test both applied and unapplied cases:** call two services matching the pointcut and one bean/method that does not match; verify advice invocation counts, relevant ordering, and that business logic returns the expected result. Include an error case to confirm advice does not alter exceptions unintentionally.
6. **Monitor in operation:** avoid logging sensitive information and large payloads; measure overhead if advice runs on a hot path; note when a refactor renames a class/method so that a pointcut no longer matches.

This example shows that a change in `SharedAuditAspect.recordCall()` can update the audit behavior of **both `OrderService` and `InvoiceService`** without editing business code. That is Spring AOP's core role for shared behavior across beans: **centralizing technical rules, applying them consistently at Spring-managed methods, and keeping business boundaries clear**, while always respecting proxy limitations.