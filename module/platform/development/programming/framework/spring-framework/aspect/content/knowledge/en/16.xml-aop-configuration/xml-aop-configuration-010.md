# Combining XML with Java Configuration Without Creating Duplicate Behavior in Spring AOP

## 1. Problem and Objectives

In a Spring Framework application with a long configuration history, some beans and Spring AOP advice are often declared in XML while newer features use `@Configuration`, `@Bean`, `@Aspect`, and `@EnableAspectJAutoProxy`. Both styles **can coexist**, because Spring routes them into the same proxy and advisor mechanism. The risk does not lie in a project having both file types, but in registering the same aspect, the same feature, or overlapping advisors so that a method gets audited, logged, or metered **twice**.

For example, a service executes `process("A")`. The goal is **exactly one audit record** for that call. If you both keep `<aop:aspect>` in XML and register an `@Aspect` performing the same function with the same pointcut, the audit may be recorded twice even though the business method ran once. Conversely, two independent advices on the same join point (such as audit and transaction) are valid behavior; do not treat every multi-advice case as a bug.

This lesson focuses on **Spring AOP managed by Spring ApplicationContext**:

- Loading XML beans from Java configuration via `@ImportResource`.
- Declaring XML schema-based aspects (`<aop:config>`/`<aop:aspect>`) alongside `@Aspect` aspects.
- Ownership rules for responsibilities, bean names, pointcuts, and auto-proxy to prevent double advice execution.
- Writing tests that assert **advice execution counts**, not just business return values.
- Spring proxy boundaries, context hierarchies, advisor ordering, and gradually migrating XML configuration to Java.

General AOP theory and standalone AspectJ weaving are outside the scope of this lesson.

## 2. Distinguishing Three Easily Confused Tasks

| What Is Configured | Example | Behavior |
| --- | --- | --- |
| **Bean registration** | `<bean id="paymentService" .../>` or `@Bean paymentService()` | Places business/advice objects into the Spring container; does not itself decide which beans get AOP. |
| **Advisor/aspect declaration** | `<aop:aspect ref="xmlAuditAdvice">` or `@Aspect` + `@Before` | Specifies which methods are intercepted and what logic runs there. |
| **Enabling auto-proxying** | `<aop:config>`, `<aop:aspectj-autoproxy/>`, `@EnableAspectJAutoProxy` | Tells Spring to create proxies and attach eligible advisors to beans. |

Standard auto-proxy mechanisms are unified/integrated by Spring. Thus having both `<aop:config>` and `@EnableAspectJAutoProxy` in the same context **does not by itself prove** each advice runs twice. However, they can both pick up two **advisors carrying the same behavior**, in which case the method is processed twice.

An obvious source of duplication:

~~~java
@Aspect
public class SharedAuditAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void beforeProcess() {
        // record an audit event
    }
}
~~~

~~~xml
<bean id="sharedAuditAspect" class="demo.SharedAuditAspect"/>

<aop:config>
    <aop:aspect ref="sharedAuditAspect">
        <aop:before method="beforeProcess"
                    pointcut="execution(* demo.PaymentService.process(..))"/>
    </aop:aspect>
</aop:config>
~~~

If `@Aspect` is auto-detected by Spring and an XML `aop:aspect` declaration also references that exact advice, **one advice method is declared through two paths**. This is a configuration to avoid. These fragments only illustrate a broken setup, **not** part of the runnable example below.

### Configuration Ownership Rules

1. **One bean has one registration owner** in a given application context: choose XML `<bean>` or Java `@Bean`/component scan; do not create two differently named beans for the same logic.
2. **One cross-cutting concern has one advice owner**: if XML already audits `process`, do not add another Java aspect auditing `process` with the same event. When migrating, remove the old declaration in the same step that introduces the new one.
3. **Two independent concerns can share Spring AOP**: one XML aspect audits `process`, while one Java aspect records operational events for `cancel`; each has a clear pointcut and separate tests.
4. **One clear `@AspectJ` auto-proxy activation point** for annotation-based aspects; avoid duplicate aspect bean registrations. If `<aop:config>` is also present to declare XML advice, Spring coordinates both mechanisms.

## 3. Diagram of Combining XML and Java Configuration

The example creates **exactly one Spring ApplicationContext**:

~~~text
AnnotationConfigApplicationContext(AppConfig.class)
                   |
                   +--> AppConfig.java
                   |      @Configuration
                   |      @ImportResource("classpath:spring/legacy-aop.xml")
                   |      @EnableAspectJAutoProxy(proxyTargetClass = true)
                   |      @Bean EventRecorder
                   |      @Bean JavaCancelAspect (@Aspect)
                   |
                   +--> legacy-aop.xml
                          <bean id="paymentService" ...>
                          <bean id="xmlAuditAdvice" ...>
                          <aop:config>
                             <aop:pointcut ...process(..)>
                             <aop:aspect ref="xmlAuditAdvice">
                                <aop:before method="beforeProcess" ...>
                             </aop:aspect>
                          </aop:config>
                   |
                   +--> Spring proxy for PaymentService
                          process("A") --> XML audit exactly once
                          cancel("B")  --> Java @Aspect exactly once
~~~

In this example:

- XML owns the `paymentService` business bean and the `xmlAuditAdvice` advice bean.
- Java configuration owns `eventRecorder` and `javaCancelAspect`.
- XML audit and Java aspect have **two separate responsibilities/pointcuts**.
- Both are tested through the **same Spring proxy** to verify there are no duplicate events.

Two aspects can apply to the *same* method if they implement two distinct concerns, provided you specify order and test each event. The example chooses two methods for clear observation and to avoid confusion.

## 4. Runnable Maven + Spring Framework 6.x + Java 17 Example

The sample app uses neither Spring Boot nor an HTTP server, so Spring AOP proxies can be observed cleanly. Maven, JDK 17+, and access to Maven repositories are sufficient. In Spring Boot 3.x, bean registration, `@ImportResource`, and anti-duplication rules are similar; dependencies and auto-configuration must align with the Boot BOM in use.

### 4.1. Structure

~~~text
mixed-spring-aop/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── AppConfig.java
    │   │   ├── EventRecorder.java
    │   │   ├── PaymentService.java
    │   │   ├── XmlAuditAdvice.java
    │   │   ├── JavaCancelAspect.java
    │   │   └── Main.java
    │   └── resources/spring/legacy-aop.xml
    └── test/java/demo/MixedAopConfigurationTest.java
~~~

### 4.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mixed-spring-aop</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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

`spring-context` enables Java configuration and XML loading; `spring-aop` supplies proxy/AOP APIs; `aspectjweaver` supports pointcut expressions and AspectJ annotations parsed by Spring AOP. This is **Spring AOP proxy**, not an AspectJ load-time weaving program. Versions are a fixed illustrative dependency set, not a recommendation of the latest version for every project.

### 4.3. `src/main/java/demo/PaymentService.java`

~~~java
package demo;

public class PaymentService {
    public String process(String orderId) {
        return "processed:" + orderId;
    }

    public String cancel(String orderId) {
        return "cancelled:" + orderId;
    }
}
~~~

The class is non-`final`, and methods are public and non-`final` so Spring can use a class-based proxy. Neither method contains audit code; that concern resides outside the service.

### 4.4. `src/main/java/demo/EventRecorder.java`

~~~java
package demo;

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
~~~

`EventRecorder` is a shared bean allowing tests to observe **advice execution counts**. `CopyOnWriteArrayList` keeps concurrent calls safe in this small example; production systems typically use logging, meter registries, or real audit sinks. Do not rely on framework log strings to count executions, since logging varies with environment config.

### 4.5. `src/main/java/demo/XmlAuditAdvice.java`

~~~java
package demo;

import org.aspectj.lang.JoinPoint;

public class XmlAuditAdvice {
    private final EventRecorder recorder;

    public XmlAuditAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void beforeProcess(JoinPoint joinPoint) {
        recorder.add("xml:process:" + joinPoint.getArgs()[0]);
    }
}
~~~

`XmlAuditAdvice` is an ordinary Java class **without `@Aspect` or `@Before`**. Spring recognizes it as advice from `<aop:before>` in XML. Only one `xmlAuditAdvice` bean is registered.

### 4.6. `src/main/java/demo/JavaCancelAspect.java`

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class JavaCancelAspect {
    private final EventRecorder recorder;

    public JavaCancelAspect(EventRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(public * demo.PaymentService.cancel(..))")
    public void beforeCancel(JoinPoint joinPoint) {
        recorder.add("java:cancel:" + joinPoint.getArgs()[0]);
    }
}
~~~

This is an **annotation-style aspect**. Here the class is not annotated with `@Component`, because `@Bean` in `AppConfig` registers it exactly once. Its pointcut applies only to `cancel`, avoiding overlap with the XML audit concern on `process`.

### 4.7. `src/main/resources/spring/legacy-aop.xml`

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

    <bean id="paymentService" class="demo.PaymentService"/>

    <bean id="xmlAuditAdvice" class="demo.XmlAuditAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="processOperation"
                      expression="execution(public * demo.PaymentService.process(..))"/>

        <aop:aspect id="xmlAuditAspect" ref="xmlAuditAdvice">
            <aop:before method="beforeProcess"
                        pointcut-ref="processOperation"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

`eventRecorder` is not declared in XML because it is managed by a Java `@Bean` in the **same context**. Spring resolves `ref="eventRecorder"` when initializing the advice bean. `proxy-target-class="true"` enforces a class-based proxy for the target, consistent with the Java config.

Note: there is **no** `<aop:aspectj-autoproxy/>` in this file. The Java configuration below enables `@AspectJ` auto-proxying; `<aop:config>` still provides schema-style advisors. Avoiding a duplicate declaration here clarifies responsibility, rather than implying two auto-proxy tags would necessarily run advice twice.

### 4.8. `src/main/java/demo/AppConfig.java`

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:spring/legacy-aop.xml")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public EventRecorder eventRecorder() {
        return new EventRecorder();
    }

    @Bean
    public JavaCancelAspect javaCancelAspect(EventRecorder recorder) {
        return new JavaCancelAspect(recorder);
    }
}
~~~

Wiring mechanism:

- `@ImportResource` loads bean and advisor definitions from the XML file into the context initialized from `AppConfig`.
- `@Bean` creates a single `EventRecorder` for both advices.
- `@Bean` registers exactly one `JavaCancelAspect` instance, whose `@Aspect` metadata is processed by Spring while `@EnableAspectJAutoProxy` is active.
- XML `<aop:config>` defines the advisor for `process`; Java `@Aspect` defines the advisor for `cancel`. Each path handles a separate feature.
- Both specify class-based proxies. Within one Spring application context, standard auto-proxy infrastructure is unified, and stronger proxy settings can apply across all advices sharing that infrastructure.

### 4.9. `src/main/java/demo/Main.java`

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventRecorder events = context.getBean(EventRecorder.class);

            System.out.println("proxy:" + AopUtils.isAopProxy(service));
            System.out.println(service.process("A"));
            System.out.println(service.cancel("B"));
            System.out.println("events:" + events.snapshot());
        }
    }
}
~~~

Run inside `mixed-spring-aop`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
~~~

**Lines explicitly printed by the Java code**:

~~~text
proxy:true
processed:A
cancelled:B
events:[xml:process:A, java:cancel:B]
~~~

Library/Maven logs (if any) depend on environment settings and are not part of the illustrative stdout. Crucially, the events array contains **exactly two events across two concerns**, not four events from accidentally double-registered advice.

## 5. Testing: Confirming Each Advice Runs Exactly Once

Create `src/test/java/demo/MixedAopConfigurationTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MixedAopConfigurationTest {

    @Test
    void xmlAndJavaAspectsCoexistWithoutDuplicateAdvice() {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            // Test actually invokes through the Spring AOP proxy.
            assertTrue(AopUtils.isAopProxy(service));
            assertTrue(AopUtils.isCglibProxy(service));

            assertEquals("processed:A", service.process("A"));
            assertEquals("cancelled:B", service.cancel("B"));

            // Count events, not just assert business results.
            assertEquals(List.of("xml:process:A", "java:cancel:B"),
                         recorder.snapshot());

            // Invoke repeatedly to ensure a 1 call : 1 advice ratio.
            assertEquals("processed:C", service.process("C"));
            assertEquals("cancelled:D", service.cancel("D"));
            assertEquals(
                    List.of("xml:process:A", "java:cancel:B",
                            "xml:process:C", "java:cancel:D"),
                    recorder.snapshot());
        }
    }

    @Test
    void everyAspectBeanIsRegisteredExactlyOnce() {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            assertArrayEquals(new String[] {"javaCancelAspect"},
                    context.getBeanNamesForType(JavaCancelAspect.class));
            assertArrayEquals(new String[] {"xmlAuditAdvice"},
                    context.getBeanNamesForType(XmlAuditAdvice.class));
        }
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

Expected: **2 tests pass** when configuration loads and Spring AOP applies properly. Assertions checking advice execution counts and bean counts catch multiple failure modes:

- One concern has two advisors → events duplicate even though the service ran only once.
- A Java aspect is registered via both `@Bean` and `@Component` → bean names/counts or events diverge from expectations.
- XML not loaded or wrong pointcut → `xml:process:A` event missing.
- `@EnableAspectJAutoProxy` missing or Java aspect unregistered → `java:cancel:B` missing.
- Caller gets target directly without proxy → `AopUtils.isAopProxy` fails and no advice events appear.

This is a **small integration test for configuration + proxy**, not just a unit test of the recorder class. When migrating from Spring XML to Java, keep these assertions throughout migration to catch missing deletions or leftover declarations immediately.

## 6. Configurations That Commonly Cause Duplication

### 6.1. One Feature Defined Simultaneously in XML and `@Aspect`

Suppose legacy XML still declares:

~~~xml
<aop:aspect ref="xmlAuditAdvice">
    <aop:before method="beforeProcess"
                pointcut="execution(* demo.PaymentService.process(..))"/>
</aop:aspect>
~~~

Later someone adds a new Java aspect also auditing `process`:

~~~java
@Aspect
class JavaAuditAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void beforeProcess() {
        // Record the same kind of audit event as the XML advice.
    }
}
~~~

If the `JavaAuditAspect` bean is registered and discovered by auto-proxying, **two advices performing the same function** will run for a single call unless other configuration blocks one path. Fix: designate **one owner of auditing**; delete the old XML definition once the Java aspect completely replaces it, or keep XML only until migration completes. If they are genuinely two independent concerns, give them distinct event names, scopes, and separate tests to clarify intended behavior.

### 6.2. One `@Aspect` Registered as Multiple Spring Beans

~~~java
@Aspect
@Component
class DuplicateCandidateAspect {
    // advice ...
}
~~~

~~~java
@Configuration
@ComponentScan("demo")
class Config {
    @Bean
    DuplicateCandidateAspect duplicateCandidateAspect() {
        return new DuplicateCandidateAspect();
    }
}
~~~

This is an **incorrect example**, not part of the runnable demo. If component scanning picks up `@Component` while a `@Bean` method registers another bean **with a different name**, Spring can hold multiple aspect instances of the same class. When advisors are created for both, a join point can be advised twice. If they share the **same bean name**, behavior may be a configuration error or bean overriding depending on container mode rather than assuming Spring silently drops duplicates.

Pick exactly one: `@Component` + scan **or** explicit `@Bean`. Do not try to fix duplication with `@Primary`; that annotation selects a candidate when injecting a bean, and does not automatically suppress advisors generated from another aspect bean.

### 6.3. Registering an `@Aspect` in Java and Referencing It Again as a Schema-Style XML Aspect

If a bean already carries `@Aspect` and `@Before`/`@Around`, and XML also has `<aop:aspect ref="sameBean">` declaring that same method, the application has **two sources of advice metadata** for the same logic. Choose one style as the concern owner. For a safe transition, keep shared logic in a collaborator Java bean and have only **one** XML advice **or** one `@Aspect` wrapper as owner; do not declare two wrappers on the same pointcut without clear intent.

### 6.4. Declaring Auto-Proxy Multiple Times

Tags like `<aop:config>`, `<aop:aspectj-autoproxy/>`, `<tx:annotation-driven/>` and annotations like `@EnableAspectJAutoProxy`/`@EnableTransactionManagement` participate in Spring proxy configuration. Per Spring docs, standard settings are unified; if one configuration requests `proxy-target-class="true"`, class-based proxying may take effect more broadly than expected.

Therefore:

- **Do not assume 2 proxy-enabling tags ⇒ advice runs 2 times.** Count actual advisors and events instead.
- Do not add standalone auto-proxy creators like `BeanNameAutoProxyCreator`/`DefaultAdvisorAutoProxyCreator` into a context that already has `<aop:config>` without an explicit design. Spring documentation warns that mixing direct creators with schema AOP can cause advice to be skipped or unexpected proxy setups.
- In large applications, standardize the JDK vs. CGLIB proxy policy and test both interface and implementation methods.

### 6.5. Duplication from Loading XML Files or Scanning Classes via Multiple Paths

For instance, `@ImportResource("classpath:spring/legacy-aop.xml")` loads the file, yet another `<import resource="legacy-aop.xml"/>` also loads the same configuration, or module bootstrapping creates two contexts both handling calls. Outcomes depend on bean definition naming, overriding, bean factories, and context relationships.

Do not guess the outcome from "imported twice". Inspect the **actual bean and advisor lists in the real context**, loading sources, bean names/aliases, and how many proxies/advices the target receives; use event-counting tests to identify actual consequences.

## 7. When Both XML and Java Must Apply to the Same Method

Two advices with different responsibilities on the same method are a valid setup, for example:

~~~text
process()
  -> Java security advice: check permissions
  -> XML audit advice: record event
  -> target PaymentService.process()
~~~

These are **two distinct behaviors**, not "auditing twice". What must be addressed is order and outcome:

- Entry/exit advice order depends on advisor/aspect precedence, such as `@Order` on a Java aspect or `order` on `<aop:aspect>`. A higher-precedence advice runs **earlier** on entry and **later** on exit if wrapping the invocation.
- If security rejects early, an inner audit may not run. Decide whether business auditing must record rejected requests or only accepted methods, then order accordingly.
- When Java transaction advice and XML audit advice both apply, decide whether auditing belongs outside or inside the transaction, and whether it should record on rollback.
- Write behavior-driven tests: for one `process("A")`, assert one `security:checked:A` and one `audit:process:A`; when order matters, assert an ordered event list instead of only checking counts.

Illustrative order declaration:

~~~xml
<aop:aspect id="auditAspect" ref="xmlAuditAdvice" order="20">
    <aop:before method="beforeProcess"
                pointcut="execution(* demo.PaymentService.process(..))"/>
</aop:aspect>
~~~

~~~java
@Aspect
@Order(10)
class SecurityAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void checkAccess() {
        // check caller permissions
    }
}
~~~

These two snippets are **not standalone runnable classes/files**. With `@Order(10)` and XML `order="20"`, the Java advice has higher precedence. When relying on exact ordering among multiple advisors in a system using transactions/security, test the complete context instead of trusting file declaration order.

## 8. Verifying When Migrating from XML to Java

To migrate **one concern** from XML to Java, first inventory the XML advisors, pointcuts, bean IDs, `order`, and methods that must match/not match. Write integration tests counting that specific advice across success and exception paths; prepare the new `@Aspect` class without registering it redundantly in the production context.

During the switch, **remove in one atomic change** the old XML `<aop:aspect>`/`aop:advisor` for that concern and register exactly one new `@Aspect` bean. Keep `@ImportResource` and other XML bean definitions if not yet migrated. Re-test event counts per invocation and advisor order; consider removing `<aop:config>` only when no schema-based AOP declarations remain.

The lesson **"Migrating XML configuration to annotations and checking equivalence"** serves as the detailed migration guide: XML → annotation mapping table, two independent contexts program, and comparing proxies/returns/exceptions/events. The current lesson focuses on **safe coexistence within one context** before and during migration.

## 9. How to Diagnose Incorrect Advice Execution Counts

### Inspecting Beans and Proxies

In tests, inspect the exact context/beans:

~~~java
PaymentService service = context.getBean(PaymentService.class);
boolean proxied = AopUtils.isAopProxy(service);
String[] javaAspectNames = context.getBeanNamesForType(JavaCancelAspect.class);
String[] xmlAdviceNames = context.getBeanNamesForType(XmlAuditAdvice.class);
~~~

This fragment runs **inside a test with a `context` variable**. With Section 5's code, both lists must have exactly one configured name. If aspects are created across parent and child contexts, inspect each context separately and check which context actually owns the service bean.

You can inspect a proxy's advisors:

~~~java
if (service instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
~~~

This is a **diagnostic snippet**, not fixed stdout; advisor names/classes can vary by Spring version and active starters. Do not assert advisor counts against an arbitrary constant: infrastructure may add interceptors you did not declare yourself. Instead, assert **business event** counts and each event type.

### Error and Resolution Matrix

| Symptom | Check First | Resolution |
| --- | --- | --- |
| One `process` call records two audit events | Do two advisors match the same pointcut with the same audit logic? | Choose one owner, remove duplicate audit declaration. |
| Java aspect runs twice | Do `@Component` and `@Bean` both create aspect beans? | Register a single instance. |
| XML advice does not run | Is `@ImportResource` path right, `<aop:config>`/`pointcut-ref` valid, bean called via proxy? | Inspect advisor list and verify pointcut. |
| Java `@Aspect` does not run | Is `@EnableAspectJAutoProxy` enabled and the aspect bean registered? | Add activation/bean in the proper place. |
| Bean class-cast error | Is proxy JDK interface-based or class-based? | Inject by interface or configure proxy appropriately. |
| Multiple audit records yet advice ran only once | Does logger/recorder have multiple appenders, or does target also log? | Separate advice events from external side effects. |
| Test passes even though advice did not run | Does the test only assert the service return value? | Assert both proxy status and event counters. |
| Advice order differs from expectation | Are `@Order` and XML `order` consistent? | Add before/after event ordering tests. |
| Internal method is not intercepted | Self-invocation calling `this.otherMethod()` | Call across a Spring bean/proxy boundary properly. |

### Spring Boot Notes

Spring Boot may auto-configure AOP and choose class-based proxies depending on properties/version. If a Boot project simultaneously uses `spring-boot-starter-aop`, `@EnableAspectJAutoProxy`, and XML `<aop:config>`, verify actual beans and advisors rather than assuming multiple activations create multiple proxies. With `@ImportResource`, watch out for bean definition overriding: two beans with the same name may be blocked by Boot defaults or silently override if enabled; **do not use overriding to resolve ambiguity**.

Spring AOP still intercepts only executions passing through a Spring proxy. Creating targets with `new` or non-proxied self-invocation can cause missing events; this is not a sign of having one or two configurations.

## 10. Project Adoption Checklist

- [ ] Only one `ApplicationContext` owns the beans/advisors being combined; parent/child relationships are clearly defined.
- [ ] Every AOP bean has a single registration path (`<bean>` or `@Bean`/component scan); names/aliases are unambiguous.
- [ ] For each concern, identify one primary pointcut/advice declaration source (XML schema or `@Aspect`).
- [ ] `@ImportResource` loads the right XML file; XML has the proper `aop` namespace and no unintended duplicate imports.
- [ ] `@EnableAspectJAutoProxy` (or equivalent activation) is active when `@Aspect` exists; `<aop:config>` is properly used while XML advice remains.
- [ ] Choose a consistent proxy strategy and check interface/final/self-invocation limits.
- [ ] When multiple concerns match one method, document responsibilities and `order`, backed by corresponding tests.
- [ ] Tests include `AopUtils.isAopProxy`, aspect bean counts, and per-method **advice invocation** counts across positive/negative paths.
- [ ] When migrating a concern, delete the old advice declaration **at the same time** the new advice is registered and re-run tests.

**Completion criteria:** XML beans and Java configuration load into the same Spring context; the expected proxy is created; each `process` call produces **one XML audit event**, each `cancel` call produces **one Java advice event**; no beans/aspects/advisors with duplicate responsibilities are unintentionally registered.

## Official References

- Spring Framework — Mixing Aspect Types: https://docs.spring.io/spring-framework/reference/core/aop/mixing-styles.html
- Spring Framework — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — ImportResource: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/annotation/ImportResource.html