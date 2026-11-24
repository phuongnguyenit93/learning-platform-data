# Named Pointcuts and `pointcut-ref` in Spring AOP XML Configuration

## 1. The Problem to Solve

In Spring AOP, an application may need to apply multiple cross-cutting behaviors to the same group of methods: input validation, event recording, timing, or transaction management. If every advice repeats its own pointcut expression, interception scope easily drifts after method renames or package reorganization.

A **named pointcut** is a way to declare a method-selection expression once in Spring XML configuration:

```xml
<aop:pointcut id="orderOperations"
              expression="execution(* example.OrderService.place(..))"/>
```

Advice and advisors then use **`pointcut-ref="orderOperations"`**. `pointcut-ref` references the **`id` of an `aop:pointcut` element**, not a Java method name, aspect bean name, or AspectJ expression.

```text
                  <aop:pointcut id="orderOperations">
                                 |
                    +------------+------------+
                    |                         |
     <aop:before pointcut-ref>    <aop:after-returning pointcut-ref>
                    |                         |
            Before execution           On normal return
                    +------------+------------+
                                 |
                  Spring AOP proxy matches
                  OrderService.place(..)
```

The core idea is **one scope definition, multiple usage sites**. Spring still intercepts calls passing through a **Spring proxy**; XML does not turn Spring AOP into a tool that intercepts every execution point across the JVM.

### Three Elements to Distinguish

| XML Element | Role | Important Attribute Values |
| --- | --- | --- |
| `<aop:pointcut>` | Names a join-point selection expression | `id`, `expression` |
| `<aop:aspect>` | Binds XML advice elements to **a Spring bean** containing advice methods | `ref` points to bean; may have `order` |
| `<aop:before>`, `<aop:after-returning>`, `<aop:around>`... | Chooses when advice runs and the Java handler method | `method`, **`pointcut-ref` or `pointcut`** |
| `<aop:advisor>` | Binds an `Advice`/interceptor bean to a pointcut | `advice-ref`, `pointcut-ref`, may have `order` |

An `<aop:aspect ref="traceAdvice">` references a **bean containing ordinary advice methods**, whereas `<aop:advisor advice-ref="someInterceptor">` requires a bean conforming to the `Advice`/interceptor interface. Do not swap the two declarations merely because both have a `ref` attribute.

## 2. Exact Spring XML Syntax

In the Spring XML schema, a named pointcut has an **ID** and an **expression**; an advice uses either `pointcut-ref="id"` or `pointcut="expression"`, not both:

~~~xml
<aop:config>
    <aop:pointcut id="placeCalls"
                  expression="execution(* example.OrderService.place(..))"/>
    <aop:aspect ref="traceAdvice">
        <aop:before method="before" pointcut-ref="placeCalls"/>
    </aop:aspect>
</aop:config>
~~~

This fragment requires the `OrderService` and `traceAdvice` beans and the Java method `before`. `pointcut-ref` must be the ID `placeCalls`, **without `()`**. Inside `aop:config`, top-level elements follow the order **pointcut → advisor → aspect**. Boolean combinations in XML attributes use `and`, `or`, `not`, or escape `&&` as `&amp;&amp;`.

`proxy-target-class="true"` is optional if a class proxy is needed, not a prerequisite for named pointcuts to work. The runnable example in Section 5 declares one pointcut and two aspects referencing it.

## 3. Pointcuts at `aop:config` Level vs. Inside `aop:aspect`

**A shared (top-level) pointcut** is declared as a direct child of `aop:config`:

```xml
<aop:config>
    <aop:pointcut id="serviceCalls"
                  expression="execution(public * example..*Service.*(..))"/>

    <aop:aspect ref="auditAdvice">
        <aop:before method="recordAttempt"
                    pointcut-ref="serviceCalls"/>
    </aop:aspect>

    <aop:aspect ref="metricsAdvice">
        <aop:after-returning method="recordSuccess"
                             pointcut-ref="serviceCalls"/>
    </aop:aspect>
</aop:config>
```

This is an **illustrative XML snippet**, usable only once you have declared the corresponding beans and methods. Both aspects select the same set of join points; changing the expression on `serviceCalls` updates the scope for both.

**An aspect-local pointcut** is declared inside `aop:aspect`:

```xml
<aop:config>
    <aop:aspect ref="auditAdvice">
        <aop:pointcut id="localWrites"
                      expression="execution(* example..*Service.save*(..))"/>

        <aop:before method="recordAttempt"
                    pointcut-ref="localWrites"/>
        <aop:after-returning method="recordSuccess"
                             pointcut-ref="localWrites"/>
    </aop:aspect>
</aop:config>
```

Here the pointcut resides alongside the aspect declaration, suitable when only that aspect's advice needs it. If multiple aspects/advisors share it, promote the pointcut to the `aop:config` level so the scope contract is centralized and easier to read.

**Important note:** an XML pointcut's `id` is used for linking via `pointcut-ref`. You cannot write an expression like `expression="serviceCalls() and ..."` to invoke `id="serviceCalls"` as if calling a named `@Pointcut` in Java. According to Spring documentation, named pointcuts defined in XML **cannot be used as method names to compose a new pointcut expression**. If composition via method names is genuinely needed by your architecture, you can reference a `@Pointcut` method defined in an `@Aspect` type by its fully qualified name, such as `example.SharedPointcuts.businessMethods()`. The simplest approach in pure XML is declaring the final expression under a new `id`.

## 4. Distinguishing `pointcut-ref`, `pointcut`, `ref`, and `advice-ref`

Remember the difference lies in the **identifier kind**:

| Attribute | What Is the Value? |
| --- | --- |
| `<aop:pointcut id="placeCalls">` | ID of the XML pointcut definition |
| `<aop:before pointcut-ref="placeCalls">` | Reference to the exact pointcut ID |
| `<aop:before pointcut="execution(...)">` | Inline pointcut expression |
| `<aop:aspect ref="traceAdvice">` | ID of the **Spring bean** containing Java advice methods |
| `<aop:advisor advice-ref="interceptorBean">` | ID of a bean implementing Spring `Advice`/`MethodInterceptor` |
| `<aop:before method="before">` | Name of the Java method on the `traceAdvice` bean |

`pointcut-ref="placeCalls()"` and `expression="placeCalls()"` cannot reference an **XML ID** using named Java method syntax. A top-level ID is shared via `pointcut-ref`; if you need combined conditions, write the complete expression in the pointcut definition.

## 5. Runnable Example: Two Aspects Sharing One Named Pointcut

The example uses Java 17+, Spring Framework 6.2.8, AspectJ Weaver, and Maven. One `aop:config`-level pointcut selects only `OrderService.place(..)`. Both the quantity-checking aspect and the event-recording aspect use `pointcut-ref="placeCalls"`. The `status()` method is not selected.

Directory structure:

```text
named-pointcut-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── App.java
    │   │   ├── EventRecorder.java
    │   │   ├── OrderService.java
    │   │   ├── GuardAdvice.java
    │   │   └── TraceAdvice.java
    │   └── resources/spring-aop.xml
    └── test/java/example/XmlPointcutTest.java
```

### 5.1. Declaring Dependencies

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>named-pointcut-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

### 5.2. Java: Target Object and Two Advice Beans

`src/main/java/example/EventRecorder.java`:

```java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class EventRecorder {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

`src/main/java/example/OrderService.java`:

```java
package example;

public class OrderService {
    private final EventRecorder recorder;

    public OrderService(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public String place(String sku, int quantity) {
        recorder.add("target:place");
        return "PLACED:" + sku + ":" + quantity;
    }

    public String status() {
        recorder.add("target:status");
        return "READY";
    }
}
```

`src/main/java/example/GuardAdvice.java`:

```java
package example;

import org.aspectj.lang.JoinPoint;

public class GuardAdvice {
    private final EventRecorder recorder;

    public GuardAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void check(JoinPoint joinPoint) {
        int quantity = (Integer) joinPoint.getArgs()[1];
        if (quantity <= 0) {
            recorder.add("reject:" + quantity);
            throw new IllegalArgumentException("quantity must be positive");
        }
        recorder.add("guard:" + quantity);
    }
}
```

`src/main/java/example/TraceAdvice.java`:

```java
package example;

import org.aspectj.lang.JoinPoint;

public class TraceAdvice {
    private final EventRecorder recorder;

    public TraceAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void before(JoinPoint joinPoint) {
        recorder.add("before:" + joinPoint.getSignature().getName());
    }

    public void afterSuccess(JoinPoint joinPoint) {
        recorder.add("after:" + joinPoint.getSignature().getName());
    }
}
```

Here, `GuardAdvice` and `TraceAdvice` **do not have `@Aspect`**, because they are wired as schema-based aspects in XML. The interception condition lives in `<aop:pointcut>`; the Java methods only contain behavior. `JoinPoint` is the parameter supplied by Spring/AspectJ to advice and is used here to inspect the intercepted method and its arguments.

### 5.3. XML: Declaring the Pointcut Once, Referencing from Two Aspects

`src/main/resources/spring-aop.xml`:

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

    <bean id="eventRecorder" class="example.EventRecorder"/>

    <bean id="orderService" class="example.OrderService">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <bean id="guardAdvice" class="example.GuardAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <bean id="traceAdvice" class="example.TraceAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <aop:config proxy-target-class="true">
        <!-- Named pointcut at config level: shared across multiple aspects. -->
        <aop:pointcut id="placeCalls"
                      expression="execution(* example.OrderService.place(..))"/>

        <!-- Lower order means higher precedence. -->
        <aop:aspect id="guard" ref="guardAdvice" order="0">
            <aop:before method="check" pointcut-ref="placeCalls"/>
        </aop:aspect>

        <aop:aspect id="trace" ref="traceAdvice" order="1">
            <aop:before method="before" pointcut-ref="placeCalls"/>
            <aop:after-returning method="afterSuccess"
                                 pointcut-ref="placeCalls"/>
        </aop:aspect>
    </aop:config>
</beans>
```

**Points to observe:** `placeCalls` appears exactly once in the pointcut's `id` attribute yet is referenced by both aspects and multiple advice elements. To select an additional method, change the expression in one place. `order="0"` on `guard` makes the check run before `trace` on `place()`; a validation failure prevents the target method and inner advice from executing.

### 5.4. Running the Context and Verifying Behavior

`src/main/java/example/App.java`:

```java
package example;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder events = context.getBean(EventRecorder.class);

            System.out.println("value=" + service.place("A-1", 2));
            System.out.println("status=" + service.status());

            try {
                service.place("A-1", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println("error=" + ex.getMessage());
            }

            System.out.println("events=" + events.snapshot());
        }
    }
}
```

Command to run at the root of `named-pointcut-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.App
```

Stdout from the logic (excluding Maven/Spring environment logs if any):

```text
value=PLACED:A-1:2
status=READY
error=quantity must be positive
events=[guard:2, before:place, target:place, after:place, target:status, reject:0]
```

Explanation of each case:

- `place("A-1", 2)` matches `execution(* example.OrderService.place(..))`; guard records `guard:2`, trace records `before:place`, target records `target:place`, and upon normal return trace records `after:place`.
- `status()` **does not match** the pointcut, so it only records `target:status`. This proves the interception scope is sufficiently narrow.
- `place("A-1", 0)` matches, but guard has higher precedence and throws an exception before the target and trace run; `after-returning` also does not run because there is no successful return.

In real applications, avoid relying on ordering between multiple advice without explicitly declaring precedence. `order` controls aspect ordering; it does not alter the expression content. Also, this is an example checking a precondition in advice to demonstrate interceptor order, not a recommendation to move all business validation into Spring AOP.

## 6. Automated Testing: Named Pointcut Only Intercepts the Right Method

`src/test/java/example/XmlPointcutTest.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class XmlPointcutTest {
    @Test
    void namedPointcutIsSharedAndOnlyMatchesPlace() {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("PLACED:A-1:2", service.place("A-1", 2));
            assertEquals("READY", service.status());

            assertEquals(List.of(
                    "guard:2",
                    "before:place",
                    "target:place",
                    "after:place",
                    "target:status"), recorder.snapshot());
        }
    }

    @Test
    void failingGuardStopsTargetAndInnerAdvice() {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            IllegalArgumentException error = assertThrows(
                    IllegalArgumentException.class,
                    () -> service.place("A-1", 0));

            assertEquals("quantity must be positive", error.getMessage());
            assertEquals(List.of("reject:0"), recorder.snapshot());
        }
    }
}
```

Run:

```bash
mvn -q test
```

The two tests complement each other:

1. `AopUtils.isAopProxy(service)` verifies the bean is actually proxied. Checking the event list proves both guard and trace share the **exact same named pointcut**; `status()` is unaffected.
2. The error case proves the designed precedence and that the target/inner advice are not accidentally called after the guard rejects. If you delete `pointcut-ref` or mistype `placeCalls`, the application context may fail to initialize; if you widen the expression to `execution(* example.OrderService.*(..))`, the scope test will catch that `status()` gets intercepted.

For larger systems, have similar tests against an interface/JDK proxy if real configuration uses `proxy-target-class="false"`. An XML config test that only invokes a manually created `new OrderService(...)` Java object will not prove Spring proxy interception.

## 7. How Does `pointcut-ref` on an Advisor Differ from an Aspect?

In Spring XML there are two ways to connect:

**Approach A — schema aspect**: one Java bean contains multiple advice methods; `aop:before` and `aop:after-returning` invoke those methods via `method`.

```xml
<aop:aspect ref="traceAdvice">
    <aop:before method="before" pointcut-ref="placeCalls"/>
</aop:aspect>
```

**Approach B — Spring advisor**: a dedicated bean executing advice, for instance an implementation of `org.aopalliance.intercept.MethodInterceptor`, bound to a pointcut:

```xml
<!-- Snippet to add inside <beans> and <aop:config> respectively. -->
<bean id="metricsInterceptor" class="example.MetricsInterceptor"/>

<aop:config>
    <aop:pointcut id="placeCalls"
                  expression="execution(* example.OrderService.place(..))"/>

    <aop:advisor advice-ref="metricsInterceptor"
                 pointcut-ref="placeCalls"
                 order="2"/>
</aop:config>
```

`MetricsInterceptor` must implement `MethodInterceptor.invoke(MethodInvocation)` and call `invocation.proceed()` to continue the interceptor chain. The snippet above **is not part of the runnable example in Section 5**; to use it, create the actual bean/class and avoid redefining `placeCalls` in the same configuration.

For XML-declared transactions, Spring also combines `<tx:advice id="txAdvice">...</tx:advice>` with `<aop:advisor advice-ref="txAdvice" pointcut-ref="..."/>`. In that case `pointcut-ref` still selects the set of methods; `advice-ref` selects the transaction policy. They do not replace each other.

**Schema requirement:** inside an `aop:config`, place `aop:advisor` **after** `aop:pointcut` elements and **before** `aop:aspect` elements. This differs from Java annotation ordering because the XML schema enforces element positions.

## 8. Common Configuration Errors and How to Handle Them

Errors specific to named pointcuts include: mistyping the `pointcut-ref` ID causing Spring to fail resolution; moving `<aop:pointcut>` to an invalid XSD position; confusing an XML ID with a named Java method `pc()`; and editing a shared expression without negative tests for other aspects. Fix `pointcut-ref` with the exact ID without `()`, check element placement/structure in the right scope, and initialize a real context.

When renaming an `id`, scan all `pointcut-ref` attributes; when changing an expression while keeping the ID, verify the impact on **all consumer advisors/aspects**. If advice does not run despite a valid ID, distinguish expression mismatch from callers bypassing the proxy. For `&&` operators in XML, write `and` or `&amp;&amp;`.

## 9. Naming and Maintaining XML Pointcuts

Choose names that clearly state the **set of intercepted methods**, such as `orderWrites`, `invoiceServiceOperations`, or `publicBusinessMethods`. Names like `pointcut1` or `allMethods` do not help reviewers spot overly broad expressions. Watch out for three types of changes:

1. **Changing the expression while keeping `id`:** every advice/advisor using `pointcut-ref` receives the new scope. Update tests for all aspects consuming the pointcut.
2. **Changing `id`:** every `pointcut-ref` must be updated; missing one can make context initialization fail.
3. **Moving a pointcut from local to `aop:config` level:** keep the expression intact, adjust element placement and references so multiple aspects can share it; run regression tests.

Group pointcuts carrying the same business meaning, but do not reuse an overly broad pointcut for policies targeting different subsets (such as auditing all services vs. transactions only on write operations). A seemingly generic name whose expression lists very specific methods can also go stale during refactoring; tests guarding selection scope are essential.

If splitting configuration across multiple XML files, you can use `<import resource="other-aop.xml"/>` per Spring configuration rules; ensure the pointcut definition and reference actually lie within the XML/schema scope and bean definitions Spring can process. For complex configurations, an `ApplicationContext` initialization test is better evidence than assuming a global `id` will resolve regardless of where it is declared.

## 10. Verification Exercises

From the runnable example, perform the following steps in sequence:

1. Run `mvn -q test`, then change the `placeCalls` expression to `execution(* example.OrderService.*(..))`. Observe the test catching unexpected interception of `status()`; restore the original expression.
2. Change `pointcut-ref="placeCalls"` in `trace` alone to a nonexistent name. Observe the context initialization error; fix it back to the correct name.
3. Inside the `trace` aspect, try declaring a local pointcut for `status()` and a separate advice using its `pointcut-ref`. Verify that `place()` and `status()` produce events within their respective scopes.
4. Change the `order` of the aspects and update tests to observe the ordering difference. Specifically for when the guard throws an error, explain which advice gets a chance to run first.
5. Add a valid `MethodInterceptor` and bind it via `aop:advisor` to **the same top-level pointcut**. Prove with a test that the advisor and schema aspect share the exact same set of calls.

**Target outcome:** you can read XML and identify which expression selects methods, which `id` `pointcut-ref` points to, which bean owns the advice, what the execution order is, and which tests prove no extra calls are intercepted.

### Official Documentation

- Spring Framework 6.2 — *Schema-based AOP Support* (named pointcuts, scope, advisor, ordering): https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html
- Spring Framework — *Spring AOP Proxies* (self-invocation, proxy limitations): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — *Pointcut Expressions* (`execution`, `args`, etc. syntax): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html