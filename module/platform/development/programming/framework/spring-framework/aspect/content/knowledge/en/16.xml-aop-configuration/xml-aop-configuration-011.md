# Migrating Spring AOP Configuration from XML to Annotations and Verifying Equivalence

In a Spring Framework application, XML-based AOP configuration and annotation-based aspect configuration can both create **Spring AOP proxies** to run advice around Spring bean methods. When migrating, the goal is not merely deleting XML: you must **preserve which beans are advised, pointcut expressions, advice types, execution order, proxy type, return values, and exception behavior**.

There are two distinct XML starting situations, so identify yours before editing:

1. **XML defines both pointcuts and advice**, such as `<aop:config>`, `<aop:aspect ref="...">`, and `<aop:around>`: migrate those definitions into a Java class with `@Aspect`, `@Pointcut`, `@Around`, etc., and enable proxies with `@EnableAspectJAutoProxy`.
2. **XML already uses aspect annotations** (classes have `@Aspect`, XML has `<aop:aspectj-autoproxy/>`): the advice definitions are already in Java; only migrate **bean registration and auto-proxy activation** to Java configuration, without rewriting advice just to replace XML syntax.

This lesson focuses on **Spring Aspect/Spring AOP**: the examples intercept Spring bean methods through proxies, without performing AspectJ compile-time or load-time weaving.

## 1. XML → Annotation / Java Configuration Mapping Table

| XML Configuration | Equivalent Java Configuration | What Must Be Preserved |
| --- | --- | --- |
| `<aop:config>` (schema-based AOP declaration) | `@Aspect` on advice class and `@EnableAspectJAutoProxy` in `@Configuration` | Which beans match, which methods are intercepted |
| `<aop:aspect ref="traceAdvice">` | Spring bean with an `@Aspect` class; created via `@Bean` or `@Component` | Same lifecycle and advice dependencies |
| `<aop:pointcut id="pc" expression="..."/>` | `@Pointcut("...")` on an empty-body method, or inline expression in advice | Preserve the exact expression and runtime conditions |
| `<aop:before method="before" pointcut-ref="pc"/>` | `@Before("pc()")` | Timing before method execution |
| `<aop:after method="after" pointcut-ref="pc"/>` | `@After("pc()")` | Runs after method finishes, including on error |
| `<aop:after-returning method="success" returning="result" .../>` | `@AfterReturning(pointcut="pc()", returning="result")` | Normal return path only, result binding |
| `<aop:after-throwing method="failure" throwing="error" .../>` | `@AfterThrowing(pointcut="pc()", throwing="error")` | Exception path only, bound exception type |
| `<aop:around method="around" pointcut-ref="pc"/>` | `@Around("pc()")` on a method taking `ProceedingJoinPoint` | `proceed()` count, return value, rethrown errors |
| `<aop:aspect order="10" ...>` | `@Order(10)` on `@Aspect` class or `Ordered` | Precedence across aspects; test actual ordering |
| `proxy-target-class="true/false"` on `<aop:config>` or `<aop:aspectj-autoproxy>` | `@EnableAspectJAutoProxy(proxyTargetClass = true/false)` | JDK vs. class-based proxy, injectable bean type |
| `expose-proxy="true"` | `@EnableAspectJAutoProxy(exposeProxy = true)` | Ability to use `AopContext.currentProxy()` if the app relies on it |
| `<bean .../>` or `<context:component-scan .../>` | `@Bean` or `@ComponentScan` with `@Component`/`@Service` | Both target and aspect beans registered in the right context |

**Note:** snippets like `@Before("pc()")` in the table assume a `@Pointcut` method named `pc` in the same aspect. If you inline the full pointcut expression in the annotation, that method is unnecessary. XML advice syntax can declare `pointcut="..."` directly instead of `pointcut-ref`; likewise, annotations allow inline expressions.

**Do not automatically assume everything is one-to-one.** Ordering across multiple advices inside one aspect can differ when switching declaration styles or adding new advice; proxy settings can be affected by other Spring configurations in the same context. Always verify actual runtime behavior.

## 2. Runnable Before-and-After Comparison Example

We create **two separate application contexts** with the same interface/target using Spring Framework 6, Java 17, and Maven. The first context defines advice in XML `<aop:config>`. The second context defines advice with `@Aspect` and enables it via `@EnableAspectJAutoProxy`. Each context has an independent `TraceLog` so test outcomes do not interfere.

The use case has two paths:

- `placeOrder("A-7")` returns `"OK:A-7"` and records events in the audit log.
- `placeOrder("bad")` throws `IllegalArgumentException`; advice records the failure event and **rethrows the original exception**.

The verification compares return values, proxy types, event ordering, and exceptions between both contexts. Using a single `@Around` advice on each side keeps the trace easy to inspect.

### 2.1. Maven Project Structure

```text
spring-aop-xml-migration/
├── pom.xml
└── src/main/
    ├── java/com/example/aopmigration/
    │   ├── OrderService.java
    │   ├── OrderServiceImpl.java
    │   ├── TraceLog.java
    │   ├── XmlTraceAdvice.java
    │   ├── AnnotatedTraceAspect.java
    │   ├── JavaAopConfig.java
    │   └── MigrationCheck.java
    └── resources/
        └── legacy-aop.xml
```

**`pom.xml`:** Maven and JDK 17 or higher; Spring 6 is compatible with Java 17. `aspectjweaver` is required for AspectJ types and pointcut parsing used by Spring AOP.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-xml-migration</artifactId>
    <version>1.0.0</version>

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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

In a Spring Boot project that already has dependency management, typically use `spring-boot-starter-aop` and let Boot manage versions instead of copying the entire Maven configuration above.

### 2.2. Shared Target Bean

**`OrderService.java`**

```java
package com.example.aopmigration;

public interface OrderService {
    String placeOrder(String orderId);
}
```

**`OrderServiceImpl.java`**

```java
package com.example.aopmigration;

public class OrderServiceImpl implements OrderService {
    @Override
    public String placeOrder(String orderId) {
        if ("bad".equals(orderId)) {
            throw new IllegalArgumentException("invalid order");
        }
        return "OK:" + orderId;
    }
}
```

**`TraceLog.java`**

```java
package com.example.aopmigration;

import java.util.ArrayList;
import java.util.List;

public class TraceLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

The example runs sequentially on a single thread, so `ArrayList` suffices for recording events; in multi-threaded applications, use a thread-safe recorder/logger. Both contexts create two separate `TraceLog` instances.

### 2.3. Before: Advice and Pointcut Declared in XML

**`XmlTraceAdvice.java`** is a POJO: no `@Aspect` yet because XML defines which advice runs.

```java
package com.example.aopmigration;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlTraceAdvice {
    private final TraceLog log;

    public XmlTraceAdvice(TraceLog log) {
        this.log = log;
    }

    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        log.add("enter:" + method);

        try {
            Object result = joinPoint.proceed();
            log.add("ok:" + result);
            return result;
        } catch (Throwable failure) {
            log.add("fail:" + failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
```

**`src/main/resources/legacy-aop.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="traceLog" class="com.example.aopmigration.TraceLog"/>
    <bean id="orderService" class="com.example.aopmigration.OrderServiceImpl"/>

    <bean id="xmlTraceAdvice" class="com.example.aopmigration.XmlTraceAdvice">
        <constructor-arg ref="traceLog"/>
    </bean>

    <aop:config proxy-target-class="false">
        <aop:pointcut id="orderOperation"
            expression="execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))"/>
        <aop:aspect ref="xmlTraceAdvice">
            <aop:around pointcut-ref="orderOperation" method="around"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Here `<aop:config>` connects `XmlTraceAdvice.around(...)` to the pointcut. The target bean `orderService` is supplied by Spring as a proxy because the pointcut matches. Since the target has the `OrderService` interface and XML sets `proxy-target-class="false"`, Spring can create a JDK dynamic proxy.

### 2.4. After: Aspect Annotations and Java Configuration

**`AnnotatedTraceAspect.java`** holds the advice definition directly in Java:

```java
package com.example.aopmigration;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class AnnotatedTraceAspect {
    private final TraceLog log;

    public AnnotatedTraceAspect(TraceLog log) {
        this.log = log;
    }

    @Pointcut("execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))")
    public void orderOperation() {
    }

    @Around("orderOperation()")
    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        log.add("enter:" + method);

        try {
            Object result = joinPoint.proceed();
            log.add("ok:" + result);
            return result;
        } catch (Throwable failure) {
            log.add("fail:" + failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
```

The body of `around` matches the XML version: before and after `proceed()`, it records the same events. Only the location where the **pointcut and advice type** are declared moves from XML to annotations.

**`JavaAopConfig.java`** replaces XML for registering beans and enabling proxies:

```java
package com.example.aopmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JavaAopConfig {
    @Bean
    public TraceLog traceLog() {
        return new TraceLog();
    }

    @Bean
    public OrderService orderService() {
        return new OrderServiceImpl();
    }

    @Bean
    public AnnotatedTraceAspect annotatedTraceAspect(TraceLog traceLog) {
        return new AnnotatedTraceAspect(traceLog);
    }
}
```

- `@EnableAspectJAutoProxy` enables proxy infrastructure for beans carrying `@Aspect`.
- `proxyTargetClass = false` keeps the preference for JDK proxies just like the original XML. If the system has other proxy settings, verify the actual runtime proxy type.
- `@Bean` registers the **target**, **log**, and **aspect** in the application context. `@Aspect` **does not auto-register a bean**; this example needs neither `@ComponentScan` nor `@Component`.
- `@Configuration(proxyBeanMethods = false)` fits the example because the `@Bean` methods do not call one another directly; Spring injects the dependency into `annotatedTraceAspect(TraceLog)`.

### 2.5. Running Both Configurations and Comparing Behavior

**`MigrationCheck.java`**

```java
package com.example.aopmigration;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class MigrationCheck {
    record RunResult(
            boolean proxy,
            boolean jdkProxy,
            String successValue,
            String errorType,
            String errorMessage,
            List<String> events
    ) {
    }

    private static RunResult run(String label, ApplicationContext context) {
        OrderService service = context.getBean(OrderService.class);
        TraceLog log = context.getBean(TraceLog.class);

        boolean proxy = AopUtils.isAopProxy(service);
        boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
        String successValue = service.placeOrder("A-7");

        String errorType = null;
        String errorMessage = null;
        try {
            service.placeOrder("bad");
            throw new AssertionError("Expected a rejected order");
        } catch (IllegalArgumentException failure) {
            errorType = failure.getClass().getSimpleName();
            errorMessage = failure.getMessage();
        }

        RunResult result = new RunResult(
                proxy, jdkProxy, successValue, errorType,
                errorMessage, log.snapshot()
        );
        System.out.println(label + " " + result);
        return result;
    }

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext xml =
                     new ClassPathXmlApplicationContext("legacy-aop.xml");
             AnnotationConfigApplicationContext java =
                     new AnnotationConfigApplicationContext(JavaAopConfig.class)) {

            RunResult before = run("XML", xml);
            RunResult after = run("JAVA", java);

            if (!before.equals(after)) {
                throw new AssertionError(
                        "AOP behavior changed after migration"
                );
            }
            if (!before.proxy() || !before.jdkProxy()) {
                throw new AssertionError("Expected JDK AOP proxy");
            }
            System.out.println("EQUIVALENT true");
        }
    }
}
```

Run inside the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.aopmigration.MigrationCheck
```

If using Windows PowerShell, quote the argument if required by your shell/Maven version:

```powershell
mvn -q compile exec:java "-Dexec.mainClass=com.example.aopmigration.MigrationCheck"
```

**Lines printed by `MigrationCheck` itself** (excluding Maven, Spring, or other library logs):

```text
XML RunResult[proxy=true, jdkProxy=true, successValue=OK:A-7, errorType=IllegalArgumentException, errorMessage=invalid order, events=[enter:placeOrder, ok:OK:A-7, enter:placeOrder, fail:IllegalArgumentException]]
JAVA RunResult[proxy=true, jdkProxy=true, successValue=OK:A-7, errorType=IllegalArgumentException, errorMessage=invalid order, events=[enter:placeOrder, ok:OK:A-7, enter:placeOrder, fail:IllegalArgumentException]]
EQUIVALENT true
```

`record RunResult` (Java 17) automatically provides `equals()` comparing all fields, including the event list. If an aspect is missing, a pointcut is wrong, advice swallows an exception, proxy types differ, or return values change, this comparison catches many kinds of regressions. The example checks **specific behavior of two calls**; a real system should expand the test suite across business methods and edge cases.

## 3. If XML Already Uses `<aop:aspectj-autoproxy/>`

This is a migration of **proxy bootstrapping** and bean registration, with no need to modify annotation advice.

**Before, in XML:**

```xml
<aop:aspectj-autoproxy proxy-target-class="false"/>
<bean id="orderService" class="com.example.aopmigration.OrderServiceImpl"/>
<bean id="annotatedTraceAspect"
      class="com.example.aopmigration.AnnotatedTraceAspect">
    <constructor-arg ref="traceLog"/>
</bean>
```

The abbreviated snippet above assumes XML already defines a `traceLog` bean; without it, the XML is incomplete. Since `AnnotatedTraceAspect` already has `@Aspect` and `@Around`, migrating to Java config can use Section 2.4's setup: `@EnableAspectJAutoProxy` and corresponding `@Bean` methods. Do not add `<aop:config>` to redeclare that same advice.

You can choose `@Component` on the aspect, `@Service` on the target, and `@ComponentScan` on the config instead of `@Bean`; **choose only one registration mechanism per bean**, avoiding duplicate beans that cause pointcuts to apply unexpectedly.

## 4. Equivalence Criteria to Check Before Removing XML

One test case returning the same result is not enough to prove full configuration equivalence. Compare systematically:

| Criterion | What Must Be Checked |
| --- | --- |
| **Spring beans** | Target, aspect, collaborators registered completely with required scopes; no duplicate beans or wrong application context |
| **Pointcut scope** | Expression kept identical or proven to match the exact same set of methods; test both advised methods and excluded methods |
| **Advice types** | `before`, `after`, `after-returning`, `after-throwing`, `around` preserve semantics and `JoinPoint`/return value/exception bindings |
| **Returns / exceptions** | `@Around` calls `proceed()` the exact number of times, returns the right result, does not swallow or alter exceptions unless the old version did |
| **Ordering** | If multiple aspects exist, preserve `order` via `@Order`/`Ordered`; test actual event ordering on shared pointcuts |
| **Proxy** | `proxy-target-class` → `proxyTargetClass`; check `AopUtils.isAopProxy` and `isJdkDynamicProxy`/`isCglibProxy` |
| **Call site** | Clients retrieve beans from the Spring context and call through proxies, never on objects created with `new` |
| **Edge cases** | Exception paths, `null` returns, boundary arguments, and unmatched methods all have tests |
| **Side effects** | Log/metrics/audit order, transactions, security advice, and other interceptors do not change unexpectedly |

### How to Write Integration-Level Spring AOP Tests

- **Positive and negative pointcut checks:** in each context, call a matched method and an unmatched method, verifying only the matched method gets advised. Do not test solely by instantiating the target class directly.
- **Error path checks:** force the target to throw an exception; compare exception type, message or error contract, and advice order.
- **Multi-aspect checks:** if transactions, tracing, auditing, or security run together, test actual execution order. `@Order` controls precedence across aspects, and does not guarantee arbitrary ordering among multiple advices declared in the same class.
- **Proxy checks:** use `AopUtils` and valid injection types. JDK proxies normally implement only interfaces; code injecting concrete classes can fail after migration if proxy type changes.
- **Real context checks:** if the application uses parent/child contexts (e.g., root/web), enable proxying in the exact context holding the target beans; activation in a child context does not automatically apply to beans in a parent context.
- **Self-invocation checks:** `this.otherMethod()` inside the same target bean normally bypasses the Spring proxy both before and after migration. If advice is required, route the call through an appropriate Spring bean/proxy.

The check suite in Section 2 shows how to compare outputs and proxies automatically; when refactoring real applications, put the same comparison logic into JUnit integration tests and expand across every method targeted by your pointcuts.

## 5. Differences That Easily Introduce Bugs During Migration

### 5.1. Forgetting `@EnableAspectJAutoProxy` or Forgetting to Declare the `@Aspect` Bean

`@Aspect` defines an aspect but does not automatically turn the class into a Spring bean. When removing XML `<aop:aspectj-autoproxy/>`, applications using Spring Framework Java config must enable proxies via `@EnableAspectJAutoProxy` (or an existing equivalent auto-proxy config). Then register the aspect class via `@Bean` or `@Component` with component scanning.

In Spring Boot with AOP auto-configuration, do not add annotations out of habit: inspect active Boot dependencies/configuration, then verify the actual runtime proxy.

### 5.2. Changing the Proxy Type

XML `proxy-target-class="false"` corresponds to Java `proxyTargetClass = false`. Changing it to `true` yields a class-based proxy that may expose a different set of methods than a JDK proxy, while having limits on `private`/`final` methods and `final` classes. In Boot apps, defaults may favor class-based proxies depending on config; therefore migration must check effective values rather than just reading annotations.

### 5.3. Editing the Pointcut While Changing Syntax

Do not simultaneously migrate and broaden `execution(* com.example.aopmigration.OrderServiceImpl.placeOrder(..))` to a wider package expression like `execution(* com.example..*(..))`. That changes which methods are advised and destroys equivalence verification. Keep the expression identical first, then widen it in a separate, tested change.

The same applies to `@annotation(...)`, `args(...)`, `this(...)`, `target(...)`: syntax may look alike, yet matching is influenced by proxy type, annotation placement, and runtime arguments. Test in a real Spring context when relying on them.

### 5.4. Advice and Transaction Ordering Changes

XML can specify `order` on `<aop:aspect>`; annotations can use `@Order` on the `@Aspect` class. However, a proxy may also contain Spring Transaction, Spring Security, and other advisors. Preserving one numeric order value is not enough if the overall advisor set changes. Inspect entry/exit events and transaction boundaries to confirm.

### 5.5. Duplicate AOP Configurations

Do not leave an XML `<aop:config>` advisor in place while adding an `@Aspect` performing **the same concern** if both are active: you may record audits twice or execute logic twice. Before deleting XML, map which old pieces are replaced by new classes; once equivalence is verified, keep only one definition source per advice. If running both side by side during migration, place them in **two isolated application contexts/test fixtures** as in the example, never in the same production context.

## 6. Safe Migration Workflow and Completion Criteria

1. **Snapshot the old state:** list target beans, aspects, pointcuts, advice types, `order`, proxy types, and related dependencies/bean scopes in XML.
2. **Freeze behavior with tests:** capture outcomes from the old config through Spring proxies, including success paths, error paths, matched and unmatched methods, and side-effect ordering.
3. **Map XML to annotations:** translate `<aop:aspect>` and advice to `@Aspect`/`@Before`/`@Around`...; preserve exact pointcut expressions and logic; register all beans.
4. **Switch proxy infrastructure:** use `@EnableAspectJAutoProxy` or corresponding Boot config; intentionally preserve proxy types and advisor ordering.
5. **Run the same test suite on the new config:** compare returns/exceptions/logs/side effects, advice invocation counts, proxy types, and any self-invocation paths.
6. **Remove duplicate config after passing:** delete replaced XML advisors and unused XML bean definitions; retain remaining XML bean configurations outside the migration scope.
7. **Run application integration tests:** confirm injection, transactions, security, exception handling, and invocations from real entry points still behave properly.

The **equivalence** criterion is: *the same calls into Spring beans through proxies yield the same results and side effects, match the same methods by pointcuts, and preserve relevant error/ordering contracts*. The `MigrationCheck` example provides a repeatable automated check; when applications have many aspects and methods, expand test coverage proportionally before declaring migration complete.