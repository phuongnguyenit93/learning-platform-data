# `aop:config` and `aop:aspect` Declaration in Spring AOP via XML

## 1. Purpose and Context

Spring Framework allows declaring **Spring AOP proxies, pointcuts, and advice in XML** using the `aop` namespace. This approach is useful when maintaining projects configured with Spring XML or when adding cross-cutting behavior to existing beans without placing AOP annotations directly on business classes.

This lesson focuses on two elements:

- `<aop:config>`: the container for declaring pointcuts, advisors, and aspects so Spring automatically creates proxies for matching beans.
- `<aop:aspect>`: maps **a Spring bean containing advice methods** to pointcuts and advice types declared in XML.

The running example traces a payment method using **proxy-based Spring AOP**. General aspect-oriented programming concepts are mentioned only where needed to understand exact Spring behavior.

After this lesson, you will be able to explain the roles of `ref`, `id`, `pointcut-ref`, and `method`; write a complete XML file; run a Java 17+ application; verify that a proxy is actually created; and diagnose cases where XML is valid yet advice does not run.

## 2. XML Elements and Key Relationships

`<aop:config>` creates schema-based AOP definitions; `<aop:aspect ref="loggingBean">` binds a **registered advice bean** to a list of corresponding methods/pointcuts. The following outline shows all three kinds of names:

~~~xml
<bean id="targetService" class="demo.TargetService"/>
<bean id="loggingBean" class="demo.LoggingAdvice"/>
<aop:config>
    <aop:pointcut id="serviceCall"
                  expression="execution(* demo.TargetService.work(..))"/>
    <aop:aspect id="loggingAspect" ref="loggingBean">
        <aop:before method="beforeWork" pointcut-ref="serviceCall"/>
    </aop:aspect>
</aop:config>
~~~

This is a fragment; `TargetService.work` and `LoggingAdvice.beforeWork` must exist accordingly. **`loggingBean`** is a Spring bean ID; **`loggingAspect`** is the aspect declaration ID; **`serviceCall`** is a pointcut ID. `method="beforeWork"` invokes the Java method on the `loggingBean` bean; `pointcut-ref="serviceCall"` does not point to a Java method. If you also declare `aop:advisor`, maintain the XSD order **pointcut → advisor → aspect**.

Execution mechanism: caller → Spring AOP proxy → matching advisor → advice method → target. Unlike `<aop:aspectj-autoproxy>`, the Java POJO `LoggingAdvice` does not need `@Aspect`; the advice metadata already lives in XML.

## 3. Pointcut Forms, Scopes, and Declaration Choices

### Shared Pointcut

~~~xml
<aop:config>
    <aop:pointcut id="paymentOperations"
                  expression="execution(public * demo.PaymentService.*(..))"/>
    <aop:aspect ref="auditBean">
        <aop:before method="check" pointcut-ref="paymentOperations"/>
        <aop:after method="finish" pointcut-ref="paymentOperations"/>
    </aop:aspect>
</aop:config>
~~~

This example is a fragment: `auditBean` must be declared as a Spring bean and have both matching methods. A pointcut at the `aop:config` level can be referenced by aspects/advisors in the configuration, helping avoid repeating expressions.

The expression `execution(public * demo.PaymentService.*(..))` describes public methods, any return type, any name, any number of parameters, belonging to class `demo.PaymentService`. It does **not** mean "every service in the demo package". Choose actual packages/classes/methods to bound the scope.

### Inline Pointcut Inside Advice

~~~xml
<aop:aspect ref="auditBean">
    <aop:before method="check"
                pointcut="execution(* demo.PaymentService.pay(..))"/>
</aop:aspect>
~~~

`pointcut="..."` is suitable when an expression is used only once; `pointcut-ref="..."` is suitable when reusing a named pointcut. Do not put both on the same advice.

### Local Pointcut Inside an Aspect

~~~xml
<aop:aspect ref="auditBean">
    <aop:pointcut id="withinPayments"
                  expression="within(demo..*)"/>
    <aop:before method="check" pointcut-ref="withinPayments"/>
</aop:aspect>
~~~

`within(demo..*)` is an illustrative expression for types under the `demo` package; in real projects, narrow it down if you do not want to match too many beans. A local pointcut is scoped to that aspect's configuration.

### Combining Conditions and XML Escaping

~~~xml
<aop:pointcut id="namedPayment"
              expression="execution(* demo.PaymentService.pay(..)) and args(orderId)"/>
~~~

In XML, the `&&` operator must be written `&amp;&amp;`; Spring also supports the words `and`, `or`, and `not`, which are often easier to read. For expressions containing `<` or `>` in attribute values, those must also be escaped with valid XML syntax. For expressions with bindings such as `args(orderId)`, the advice method must declare the matching parameter/binding; the fragment above only illustrates pointcut syntax.

## 4. Runnable Example: Creating Proxies and Declaring `aop:aspect`

The minimal example below uses **Spring Framework 6.2.x, Java 17+, Maven**. It does not require Spring Boot and does not start a web server; the goal is to observe a method call passing through a Spring AOP proxy and XML-configured advice.

### 4.1. File Structure

~~~text
xml-spring-aop/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── BillingService.java
    │   │   ├── TraceAspect.java
    │   │   └── Main.java
    │   └── resources/
    │       └── spring/aop-context.xml
    └── test/java/demo/
        └── XmlAopTest.java
~~~

### 4.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-spring-aop</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
~~~

Versions are pinned so the example is reproducible; in real applications, align with your project's BOM/framework version. `aspectjweaver` provides the AspectJ components needed for Spring AOP pointcut expressions; **it does not mean the example uses AspectJ load-time weaving**.

### 4.3. `src/main/java/demo/BillingService.java`

~~~java
package demo;

public class BillingService {
    public String pay(String orderId) {
        System.out.println("service.pay:" + orderId);

        if ("bad".equals(orderId)) {
            throw new IllegalArgumentException("invalid order");
        }
        return "paid:" + orderId;
    }
}
~~~

The `pay` method is public and non-final; the class is also non-final so the example can use a class-based proxy.

### 4.4. `src/main/java/demo/TraceAspect.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;

public class TraceAspect {
    private final AtomicInteger invocationCount = new AtomicInteger();

    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        invocationCount.incrementAndGet();
        String orderId = (String) joinPoint.getArgs()[0];
        System.out.println("aspect.before:" + orderId);

        try {
            Object result = joinPoint.proceed();
            System.out.println("aspect.after-returning:" + result);
            return result;
        } catch (Throwable exception) {
            System.out.println("aspect.after-throwing:"
                    + exception.getClass().getSimpleName());
            throw exception;
        } finally {
            System.out.println("aspect.finally:" + orderId);
        }
    }

    public int invocationCount() {
        return invocationCount.get();
    }
}
~~~

This is an ordinary Java Spring bean: **no `@Aspect` or `@Around`**. `trace(ProceedingJoinPoint)` is invoked because XML declares `<aop:around method="trace" .../>`. `orderId` is a local variable per invocation; the counter uses `AtomicInteger` because aspect beans are usually singletons and may serve multiple concurrent calls.

Calling `joinPoint.proceed()` controls execution of the target method. On success, the advice returns the original result; on failure, the advice logs the trace and rethrows the exception without swallowing it. The `finally` block runs on both success and failure paths.

### 4.5. `src/main/resources/spring/aop-context.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="traceAspectBean" class="demo.TraceAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payOperation"
                      expression="execution(public * demo.BillingService.pay(..))"/>

        <aop:aspect id="billingTrace" ref="traceAspectBean">
            <aop:around pointcut-ref="payOperation" method="trace"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

Notable points:

- `traceAspectBean` is the bean containing advice logic; `billingTrace` is the XML identifier of the aspect; `payOperation` is the pointcut identifier.
- `proxy-target-class="true"` asks Spring to use a class-based proxy so the example can look up the bean via `BillingService.class`. With an interface and JDK proxy, bean retrieval/casting can differ.
- `pointcut-ref="payOperation"` avoids repeating the expression.
- `aop:config` registers the AOP proxy mechanism for matching Spring beans; there is no need to add `<aop:aspectj-autoproxy/>` to this purely schema-style example.

### 4.6. `src/main/java/demo/Main.java`

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                     new ClassPathXmlApplicationContext("spring/aop-context.xml")) {
            BillingService service = context.getBean(BillingService.class);

            System.out.println(service.pay("ok"));

            try {
                service.pay("bad");
            } catch (IllegalArgumentException exception) {
                System.out.println("caller.caught:" + exception.getMessage());
            }
        }
    }
}
~~~

Run inside the `xml-spring-aop` directory with Maven and JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
~~~

**Stdout lines printed by the Java code itself**, in order:

~~~text
aspect.before:ok
service.pay:ok
aspect.after-returning:paid:ok
aspect.finally:ok
paid:ok
aspect.before:bad
service.pay:bad
aspect.after-throwing:IllegalArgumentException
aspect.finally:bad
caller.caught:invalid order
~~~

Maven or library logs (if logging is configured differently) are not part of the verification output above. Both the success trace and failure trace pass through a Spring AOP proxy created from XML.

### 4.7. Testing the Proxy and Advice in `src/test/java/demo/XmlAopTest.java`

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class XmlAopTest {
    @Test
    void xmlAspectInterceptsSuccessAndFailureThroughProxy() {
        try (var context =
                     new ClassPathXmlApplicationContext("spring/aop-context.xml")) {
            BillingService service = context.getBean(BillingService.class);
            TraceAspect trace = context.getBean("traceAspectBean", TraceAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertTrue(AopUtils.isCglibProxy(service));
            assertEquals(0, trace.invocationCount());

            assertEquals("paid:ok", service.pay("ok"));
            assertThrows(IllegalArgumentException.class,
                    () -> service.pay("bad"));

            assertEquals(2, trace.invocationCount());
        }
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

Expected: **1 test passes, with 2 total advice invocations**. The test verifies both proxy configuration and that Spring actually invokes the advice; asserting only the payment result without asserting `invocationCount` would not sufficiently prove that XML AOP is working.

## 5. Declaring Advice Types in `aop:aspect`

Spring XML schema supports the familiar advice types, without requiring `around`:

| XML Element | When It Runs | Conditions and Method Signature |
| --- | --- | --- |
| `<aop:before>` | Before calling target | Advice method usually returns `void`, may accept `JoinPoint`. |
| `<aop:after-returning>` | Target/advice chain completes normally | May use `returning="retVal"` to receive the return value. |
| `<aop:after-throwing>` | Target/advice chain exits with a matching exception | May use `throwing="error"` to receive the exception. |
| `<aop:after>` | After method finishes, even on failure | Similar to `finally` semantics; not used to replace return handling. |
| `<aop:around>` | Surrounds the invocation | Method must accept `ProceedingJoinPoint` first, return `Object`, and call `proceed()` to execute target. |

Alternative declaration example **not part of the running configuration in Section 4**:

~~~xml
<aop:aspect id="audit" ref="auditAdviceBean">
    <aop:before pointcut-ref="payOperation" method="beforePayment"/>
    <aop:after-returning pointcut-ref="payOperation"
                         method="afterSuccess"
                         returning="result" arg-names="result"/>
    <aop:after-throwing pointcut-ref="payOperation"
                        method="afterError"
                        throwing="error" arg-names="error"/>
    <aop:after pointcut-ref="payOperation" method="cleanup"/>
</aop:aspect>
~~~

Corresponding methods in the `auditAdviceBean` bean, for example:

~~~java
public void beforePayment() {
    // Runs before.
}

public void afterSuccess(Object result) {
    // Receives the return value on success.
}

public void afterError(Exception error) {
    // Receives exceptions matching the parameter type.
}

public void cleanup() {
    // Runs when the invocation completes.
}
~~~

These are **illustrative methods inside an advice class**, not a standalone Java file. `returning` and `throwing` specify variable names bound to advice method parameters; `arg-names` explicitly declares bindings when parameter name metadata in bytecode is unavailable. An `Exception` signature only matches compatible exceptions; an advice catching `Throwable` has a broader scope.

### Which Advice Fits Best?

- Only need pre-check/logging before execution: prefer `before`.
- Only need to process the return value: `after-returning`.
- Only need to record errors: `after-throwing`.
- Need cleanup regardless of success or error: `after`.
- Need timing spanning before/after, modifying arguments, deciding retries, or blocking target calls: `around`. With `around`, forgetting to call `proceed()` prevents the target method from running.

If multiple advice methods need to run at the same join point, determine their order explicitly; do not infer order solely from Java method names.

## 6. Aspect Ordering and Extended Configurations

### Ordering Across Aspects

You can declare `order` directly:

~~~xml
<aop:config>
    <aop:pointcut id="operation"
                  expression="execution(* demo.BillingService.pay(..))"/>

    <aop:aspect id="security" ref="securityAdviceBean" order="0">
        <aop:before method="verify" pointcut-ref="operation"/>
    </aop:aspect>

    <aop:aspect id="tracing" ref="traceAdviceBean" order="10">
        <aop:around method="trace" pointcut-ref="operation"/>
    </aop:aspect>
</aop:config>
~~~

This is an illustrative fragment: both advice beans and methods must exist. **A smaller order value means higher precedence.** Higher-precedence advice runs earlier on the way in and later on the way out. When multiple advice elements are inside the *same* `<aop:aspect>`, per Spring documentation, the declaration order of advice elements determines precedence; if logic becomes complex, separate aspects and test the actual order.

### How Does `aop:advisor` Differ from `aop:aspect`?

~~~xml
<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* demo.BillingService.pay(..))"/>
    <aop:advisor pointcut-ref="serviceOps" advice-ref="methodInterceptorBean"/>
</aop:config>
~~~

`aop:advisor` connects a **bean implementing a Spring AOP advice interface** (such as `MethodInterceptor`) with a pointcut; whereas `aop:aspect` lets you group multiple plain Java advice methods into an aspect via XML. If both advisor and aspect appear in the same `aop:config`, place advisor before aspect as required by the schema.

### `<aop:aspectj-autoproxy/>` Does Not Replace `<aop:aspect>`

`<aop:aspectj-autoproxy/>` enables auto-detection for beans annotated with `@Aspect`; `<aop:config>` configures pointcuts/advice directly in XML. Both styles use Spring AOP, but their declaration metadata differs. For the example in Section 4, only `<aop:config>` and a plain Java bean are needed.

## 7. Proxy-Based AOP Limitations to Know

XML schema-based AOP only intercepts **method executions passing through a Spring proxy** of a managed bean. Creating objects with `new` or calling `this.inner()` from inside the target will not automatically trigger new interceptors. JDK proxies normally expose interface methods; CGLIB subclass proxies cannot override private/final methods or final classes.

An `aop-context.xml` file that is not imported/loaded into the Spring context will not create advisors, even if the file sits on the classpath. Advice classes are usually singletons: store per-invocation data in local variables, not in shared mutable fields. The dedicated lesson on **proxy-target-class/expose-proxy** explains and tests each proxy limitation.

## 8. Diagnosing When XML Configuration Does Not Work

If XML parses successfully yet advice does not run, verify in order: (1) the context loaded the right XML and all `ref` bean IDs exist; (2) `method` matches the Java signature on the advice bean; (3) `pointcut-ref`/expression matches the actual class/method; (4) the target is retrieved from the Spring context and called through the proxy; (5) whether another advisor or overlapping config alters behavior.

Use `AopUtils.isAopProxy(bean)` as a supplementary config check, then **assert counters/events inside the advice** for one method that should match, one method that should not match, and both success and exception paths. A bean being proxied does not mean all advice runs on every method.

## 9. Implementation Checklist

- [ ] The XML file declares `beans`, `aop` namespaces, and appropriate XSDs.
- [ ] Target bean and advice bean are managed in the **same appropriate ApplicationContext** or contexts visible to each other.
- [ ] Child elements of `aop:config` follow schema order; `ref`, `pointcut-ref`, and `method` all exist.
- [ ] Pointcut expressions match only intended methods/packages; combined conditions are validly escaped in XML.
- [ ] Choose the least powerful advice type that meets the need; with `around`, call `proceed()` and preserve exceptions/return values properly.
- [ ] Check class/interface proxy, public/final methods, self-invocation, and how callers retrieve the bean.
- [ ] Test via `ClassPathXmlApplicationContext` or a real Spring context, measuring advice invocations rather than checking responses alone.
- [ ] If multiple aspects exist, test advice ordering with `order` or `Ordered`.
- [ ] Do not store request-specific data in mutable fields of a singleton aspect.

**Expected outcome:** a business bean keeps its code untouched, Spring creates a proxy from `<aop:config>`, executes the advice method on the bean referenced by `<aop:aspect ref="...">`, and returns the proper value/exception to the caller. These are verified in tests, not merely assumed from successful XML parsing.

## References

- Spring Framework Reference — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework Reference — AOP Concepts: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html