# Checking Java and XML Configuration to Avoid Overlapping Spring AOP Setup

## 1. Why check when a Spring application uses both Java config and XML?

A long-lived Spring application can simultaneously contain:

- Java configuration using `@Configuration`, `@EnableAspectJAutoProxy`, `@Bean`, or `@ComponentScan`.
- XML configuration with `<aop:aspectj-autoproxy/>`, `<aop:config>`, `<aop:advisor>`, `<bean>`, and `<context:component-scan/>`.
- Spring Boot auto-configuration or other Spring features that also use proxies, such as transaction interception.

Coexistence is **not inherently wrong**: Spring allows combining multiple ways of defining beans, aspects, and advisors. However, during a gradual migration from XML to Java config, it is very easy to leave old declarations behind, making it hard to tell which side enables proxying, how many times an aspect is registered, or whether a method has two advices performing the same job.

The goal of this verification step is to answer **three separate questions**:

1. **Auto-proxy:** within a single Spring `ApplicationContext`, how many proxy-creation mechanisms are participating, and what is the effective proxy configuration?
2. **Aspect bean:** is each intended aspect registered exactly once by bean name/type?
3. **Advice/advisor:** for a business method, how many advices actually match, in what order, and is behavior duplicated?

**Do not infer "advice runs twice" merely from seeing both `@EnableAspectJAutoProxy` and `<aop:aspectj-autoproxy/>`.** Spring merges standard auto-proxy declarations into one unified infrastructure within the same context; duplication must be proven at the aspect/advisor level and in execution results.

This lesson focuses on **Spring AOP configuration on Spring-managed beans**. Pure AspectJ weaving mechanisms and general AOP theory are outside the scope.

## 2. Java/XML declarations you may encounter and their meanings

| Declaration | Where it appears | Role in Spring AOP |
| --- | --- | --- |
| `@EnableAspectJAutoProxy` | `@Configuration` class | Enables detection of `@Aspect`-style aspect beans and automatic proxy creation for matching beans in the associated application context. |
| `<aop:aspectj-autoproxy/>` | XML `aop` namespace | Enables the same `@AspectJ` support in XML. |
| `<aop:config>` | XML `aop` namespace | Declares pointcuts, aspects, and advisors directly in XML; also participates in the auto-proxy system. |
| `@Bean` returning an `@Aspect` class | Java config | Registers **one aspect bean** for Spring to discover. |
| `@Aspect` + `@Component` | Component-scanned aspect class | Another way to register an aspect bean; `@Aspect` alone is not a component-discovery annotation. |
| `<bean class="...MyAspect"/>` | XML | Registers an aspect instance under a bean id, if the class carries `@Aspect`. |
| `<aop:aspect ref="...">` | XML | Uses an existing bean as the holder of advice methods declared via the XML schema. |
| `@ImportResource("classpath:...xml")` | Java config | Imports bean definitions from XML into the Java context; this is an XML **loading path**, and does not automatically enable Spring AOP. |
| `<context:component-scan ... />` | XML | Scans component beans; can overlap in scope with Java `@ComponentScan`. |

Distinguish clearly: **enabling AOP**, **registering an aspect bean**, and **defining advice** are three different actions. One AOP enablement can serve many aspects; another aspect bean with a different name but the same class can create an additional set of advices; two different advice definitions can match the same method.

## 3. Spring merges the auto-proxy creator: understand it before cleaning up config

Spring Framework documents that `<aop:config/>`, `<aop:aspectj-autoproxy/>`, and `<tx:annotation-driven/>` within the same context are coordinated through **a single unified auto-proxy creator**, taking the strongest proxy setting among the participating declarations. Corresponding configuration annotations such as `@EnableAspectJAutoProxy` and `@EnableTransactionManagement` also participate in this merging mechanism.

Example in the **same context**:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AopJavaConfig {
}
```

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

With the combination above, XML's request for class-based proxies (`true`) can **escalate the shared choice to class-based proxying**. Hence merely looking at the Java annotation and seeing `false` is not enough to conclude Spring will use JDK dynamic proxies. Conversely, do not count lines that enable AOP and assume each line adds another independent proxy layer.

Points to note when interpreting results:

- **"Merging the auto-proxy creator" does not mean duplicate aspects or advisors are deduplicated.** Two aspect beans or two valid matching advices can still cause behavior to execute multiple times.
- **`proxyTargetClass = true` does not make Spring intercept every method.** `final` classes/methods, `private` methods, and self-invocation still retain proxy AOP limitations.
- **Context scope matters.** A parent context and a child context are two separate bean/proxy domains; configuration in the parent does not automatically apply in the same way to beans belonging only to the child context.
- **Spring Boot can enable Spring AOP via auto-configuration** when dependencies and conditions match. Adding `@EnableAspectJAutoProxy` to a Boot application that already auto-configures AOP can be redundant and may even alter the expected proxy attributes.

**Maintenance goal:** establish a single clear owner of proxy configuration per context, even though Spring has an automatic merging mechanism to guard against duplicate enablement declarations.

## 4. Spring Framework 6 example: mixing Java and XML cleanly

The example below uses **Java 17+**, Spring Framework **6.1.14**, AspectJ `aspectjweaver` **1.9.22.1**, and Maven. These are fixed sample versions for demonstration, not a statement about the latest Spring release.

We establish a clear convention:

- **Java config enables `@EnableAspectJAutoProxy` and registers the aspect**.
- **XML only defines the business service bean** carried over from a legacy system.
- There is only **one** `TraceAspect` bean; calls to `OrderService` pass through the Spring proxy.

Directory structure:

```text
spring-aop-java-xml-check/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApp.java
    │   ├── AppConfig.java
    │   ├── OrderService.java
    │   └── TraceAspect.java
    └── resources/legacy-beans.xml
```

### 4.1. Maven declaration

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-java-xml-check</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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

`spring-context` manages beans and configuration; `spring-aop` implements proxying mechanics; `aspectjweaver` provides support for `@AspectJ` pointcut expressions. In an application that already has the appropriate Spring Boot AOP starter, you normally do not need to list all three artifacts manually.

### 4.2. XML retains the business bean

**`src/main/resources/legacy-beans.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderService" class="com.example.demo.OrderService"/>
</beans>
```

The XML above declares no `<aop:aspectj-autoproxy/>`, `<aop:config>`, or aspect bean. Its sole purpose is registering the legacy bean named `orderService`.

### 4.3. Java config is responsible for enabling AOP

**`src/main/java/com/example/demo/AppConfig.java`**:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.ImportResource;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@ImportResource` only tells Spring to load the XML file so `orderService` exists. The `traceAspect` bean is declared **exactly once in Java**. `@EnableAspectJAutoProxy(proxyTargetClass = true)` activates class-based proxying so the example can retrieve the bean as type `OrderService` even though the class implements no interface.

### 4.4. Service and aspect

**`src/main/java/com/example/demo/OrderService.java`**:

```java
package com.example.demo;

public class OrderService {
    public void place(String id) {
        System.out.println("[SERVICE] order " + id);
    }
}
```

**`src/main/java/com/example/demo/TraceAspect.java`**:

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public * com.example.demo.OrderService.place(..))")
    public void beforePlace() {
        calls.incrementAndGet();
        System.out.println("[ASPECT] before place");
    }

    public int count() {
        return calls.get();
    }
}
```

`@Aspect` marks the class as an aspect, while `@Bean` in `AppConfig` puts the object into the Spring container. There is no need to add `@Component` to `TraceAspect` in this example.

### 4.5. Verifying proxy, aspect bean count, and advice call count

**`src/main/java/com/example/demo/DemoApp.java`**:

```java
package com.example.demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("[CHECK] isProxy=" + AopUtils.isAopProxy(service));
            System.out.println("[CHECK] aspectBeans="
                    + context.getBeansOfType(TraceAspect.class).size());

            service.place("ORD-1");

            System.out.println("[CHECK] adviceCalls=" + aspect.count());
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.demo.DemoApp
```

Lines printed by the program itself, in exact order:

```text
[CHECK] isProxy=true
[CHECK] aspectBeans=1
[ASPECT] before place
[SERVICE] order ORD-1
[CHECK] adviceCalls=1
```

**Interpreting each check:**

- `isProxy=true`: the `OrderService` obtained by the caller is genuinely a Spring AOP proxy, not a `new`-created object.
- `aspectBeans=1`: there is exactly one bean of type `TraceAspect` in the context; counting beans matters more than counting configuration files.
- `adviceCalls=1`: exactly one advice call after one method call through the proxy. This is an **observable** check that detects overlapping conditions.
- The business line still runs after the advice: Spring AOP applied the cross-cutting behavior without modifying `OrderService`.

`AopUtils.isAopProxy` is a proxy-observation tool; in real systems, add tests for advice execution count and business results, because merely having a proxy does not prove the configuration has no duplicated logic.

## 5. Two overlap scenarios: one redundant case, one case that genuinely repeats behavior

### 5.1. Enabling auto-proxy again in XML: redundant, does not by itself prove repeated advice

Suppose `AppConfig` above already contains `@EnableAspectJAutoProxy(proxyTargetClass = true)`, yet the legacy XML file also has:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/aop
         https://www.springframework.org/schema/aop/spring-aop.xsd">

    <aop:aspectj-autoproxy proxy-target-class="true"/>

    <bean id="orderService" class="com.example.demo.OrderService"/>
</beans>
```

Adding `<aop:aspectj-autoproxy/>` like this is a **second AOP enablement declaration**. Within the same context, Spring merges standard auto-proxy support; this situation alone **does not create two aspect beans** and is not sufficient grounds to claim a call will run `beforePlace()` twice.

However, this configuration hurts maintainability and can obscure the `proxy-target-class` choice. When Java config is the official owner of AOP enablement, **remove the redundant XML line** after checking all dependent contexts, keeping XML solely for bean definitions. If XML is actually chosen to own AOP, do the reverse: keep only XML activation and remove the redundant Java annotation in that context.

Do not configure both places according to a "a little in each" habit because readers cannot easily determine the final proxy policy.

### 5.2. Registering the same aspect class as two beans: advice can run twice

Keep `@Bean traceAspect()` in Java, and **add** to `legacy-beans.xml`:

```xml
<bean id="traceAspectXml" class="com.example.demo.TraceAspect"/>
```

Now two separate beans exist:

```text
Java:  @Bean traceAspect()               --> traceAspect
XML:   <bean id="traceAspectXml" .../>    --> traceAspectXml
```

Both are beans of a class annotated with `@Aspect` and both contain `@Before` matching `OrderService.place()`. Even though Spring uses a single unified auto-proxy mechanism, it can create **two advisors corresponding to the two aspect instances**. Each call to `place()` through the proxy will print `[ASPECT] before place` twice; because they are two independent instances, `aspect.count()` on a single instance **is not the total advice count across both instances**.

Replace the `aspect.count()` check with a shared counter or event collector to prove execution counts when evaluating multiple instances. If running `DemoApp` unchanged, `context.getBean(TraceAspect.class)` can also throw `NoUniqueBeanDefinitionException` because two beans of the same type exist; that is another sign the configuration has duplicate registration.

**How to fix:** decide where the aspect bean belongs and remove the other registration. If the class has `@Component` and is scanned by both Java `@ComponentScan` and XML `<context:component-scan/>`, inspect the actual bean names. The same bean name can be treated as a duplicate definition or fail overriding rules; **different bean names** can create two instances. Do not assume every overlapping scan automatically produces two beans: the outcome depends on naming, metadata, and bean-definition overriding policy.

### 5.3. Two advice definitions with the same purpose

Another variant is:

- A Java aspect has `@Before` logging an audit event;
- XML `<aop:config>` also has an `<aop:advisor>` or `<aop:aspect>` selecting the exact same method and logging the exact same audit event.

Even with only one Java aspect bean, the system still has **two functionally similar advices**. Spring supports mixing annotation-based aspects and schema-defined advisors; their coexistence is valid in Spring, yet you must verify whether they are two intentional distinct policies or unfinished migration code.

**Do not fix by disabling all AOP.** Locate the exact duplicated advice declarations and unify them under a single policy owner.

## 6. Checklist of items to search when auditing Spring AOP configuration

When a codebase uses both Java and XML, search for the following symbol groups in **configuration files actually loaded by the application context**.

| Category | In Java | In XML | What to confirm |
| --- | --- | --- | --- |
| Proxy enablement | `@EnableAspectJAutoProxy` | `<aop:aspectj-autoproxy>`, `<aop:config>` | Who owns proxy policy in the context? Are there conflicting `proxyTargetClass` settings? |
| Config loading | `@Import`, `@ImportResource`, `@ComponentScan` | `<import>`, `<context:component-scan>` | Is a file or bean loaded/registered via multiple paths? |
| Aspect registration | `@Bean`, `@Component` + `@Aspect` | `<bean class="...">` | How many bean names/instances exist per aspect? |
| Advice attachment | `@Before`, `@After`, `@Around`... | `<aop:aspect>`, `<aop:advisor>` | Do multiple advices match the same method with the same purpose? |
| Features sharing proxies | `@EnableTransactionManagement` | `<tx:annotation-driven>` | Does a class-based proxy setting affect other interceptors? |
| Auto-configuration | Spring Boot starters, properties, and Java config | Imported legacy XML | Did Boot already auto-enable AOP before manual annotations/XML were added? |

**How to search in a repository** (for example when `rg` is available):

```bash
rg -n 'EnableAspectJAutoProxy|ImportResource|ComponentScan|@Aspect|@Bean' src/main/java
rg -n 'aspectj-autoproxy|aop:config|aop:advisor|aop:aspect|context:component-scan|<import' src/main/resources
```

Finding a text snippet is not enough to conclude it is active: a profile might not be enabled, an XML file might not be imported, a package might lie outside component scan, or the config might belong to another context. The audit must trace back to **context initialization**, the loaded config list, active profiles, and activation conditions.

With Spring Boot, cross-check `spring.aop.auto`, `spring.aop.proxy-target-class`, and auto-configuration for the running Boot version. When intending to turn off AOP, do not set a property alone while ignoring `@EnableAspectJAutoProxy` configurations explicitly enabled in code.

## 7. Inspecting the Spring container directly when duplication is suspected

### 7.1. Counting aspect beans by type and name

In a test environment, for example:

```java
String[] names = context.getBeanNamesForType(TraceAspect.class);
System.out.println(java.util.Arrays.toString(names));
```

Expected output for the sample project:

```text
[traceAspect]
```

If `traceAspectXml` also exists, two names may appear. **Do not rely on print order when testing multiple beans**; compare by name set or count.

Note: `getBeansOfType` can instantiate the corresponding singletons, whereas fetching bean definition names only reflects the queried context. When a system has parent/child contexts, audit both properly.

### 7.2. Observing the proxy and currently attached advisors

If the bean is a Spring AOP proxy supporting the `Advised` interface, you can list the advisors:

```java
Object bean = context.getBean("orderService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName()
                + " -> " + advisor.getAdvice().getClass().getName());
    }
}
```

This is a **diagnostic snippet** for tests or inspection environments, not an extension of `DemoApp` requiring exact stdout. Internal advisors may include various supporting types, and order/class names depend on the version. Counting advisors **does not equal** counting advices running on a method: you must inspect pointcuts and specific invocations.

### 7.3. Testing a single call against expected advice count

A useful test should include:

1. A target bean guaranteed to match the pointcut.
2. A non-matching bean/method to verify advice does not run out of scope.
3. A counter or event collector for the **total** runs of the audit/tracing policy.
4. Verification of business return values/exceptions and ordering when multiple different advice types exist.
5. Repetition across the Spring profiles/configuration combinations deployed in practice.

Simple example expectation: **one `service.place("ORD-1")` call → one audit event → one business execution**. Other cases where two different policies advise the same method can be valid; tests must state the expected count for **each responsibility**, rather than assuming every method has only one advice.

## 8. Distinguishing easily confused symptoms

| Symptom | Possible explanation | How to verify |
| --- | --- | --- |
| Both `@EnableAspectJAutoProxy` and `<aop:aspectj-autoproxy/>` exist | Redundant proxy-enablement declaration; Spring usually merges into one creator | Check actual context and config; do not assume duplicate logs before measuring. |
| Advice runs twice | Two aspect beans, two advisors, or two genuine interception layers | Count beans, list advisors, record advice count with a shared counter. |
| Injecting aspect by type reports non-unique bean | Same aspect class registered under multiple bean names | `getBeanNamesForType(MyAspect.class)`, inspect `@Bean`, `@Component`, and XML `<bean>`. |
| No advice despite XML existing | XML not imported, aspect is not a bean, pointcut does not match, or caller bypasses proxy | Check XML loading path, bean registry, `AopUtils.isAopProxy`, and call path. |
| Proxy is CGLIB even though Java annotation sets `proxyTargetClass=false` | XML or another config may request `proxy-target-class=true` | Audit all proxy settings in the same context, including transaction AOP. |
| Suspected AOP ran twice due to multiple identical log lines | One request may call the method twice or log at multiple layers | Attach a request/correlation id and measure a counter inside advice rather than comparing log strings alone. |
| Boot fails with duplicate bean name | Two definitions use the same name; Boot's override policy may reject it | Read the root exception and registration locations; assign a single owner. |
| Advice runs in web context but not on another bean | Different application context or call bypasses bean proxy | Check parent/child contexts, aspect registration location, and target bean proxy. |

In particular, when seeing two proxy layers or multiple different interceptors, do not automatically delete a layer before understanding what transaction, security, or async logic it executes. The goal is removing configurations with **overlapping responsibilities**.

## 9. Step-by-step Java/XML cleanup strategy while preserving behavior

A safe configuration migration approach:

1. **Identify exact running contexts.** Distinguish root, servlet context, or module contexts if the application has multiple layers.
2. **Choose the Spring AOP configuration owner per context.** For example, Java config enables `@EnableAspectJAutoProxy`, while XML keeps only un-migrated beans.
3. **List aspect beans by name/type** and remove functionally duplicate registrations. `@ComponentScan`, `@Bean`, and XML `<bean>` must be checked as three distinct sources.
4. **Compare pointcuts/advices in Java and XML.** For two advices with the same purpose, pick one definition aligned with the project's maintenance direction; do not alter business policy out of scope.
5. **Compare proxy choices before/after.** Check `proxyTargetClass`, interface injection, `final` methods, and `@Transactional` usage if present, because changing proxy mode can affect interceptability.
6. **Run observable tests.** Ensure each shared behavior executes the expected number of times, business logic returns the original result, and exception cases remain accurate.
7. **Only after confirming equivalence, delete redundant declarations** from the non-owning location. Keep tests so future XML/Java additions do not reintroduce duplication.

For a Spring Boot project using a Spring AOP starter, usually rely on the auto-configuration managed by that Boot generation and avoid re-enabling manually unless the application has a specific reason and has tested the impact. For plain Spring Framework, pick one of the two Java/XML auto-proxy enablement mechanisms for the same context and document where it is maintained.

## 10. End-of-lesson self-check

- If both Java and XML enable Spring AOP, **is advice guaranteed to run twice?** No. You must check beans and advisors; Spring has an auto-proxy creator merging mechanism.
- If there is only one auto-proxy creator, **is it impossible for aspects to be duplicated?** No. Two aspect beans or two advisors with the same pointcut can both run.
- If `@Aspect` is present, **is that enough for Spring to recognize it?** No. The class must be registered as a Spring bean with appropriate auto-proxy support.
- If `proxy-target-class=true` in XML and `false` in Java, **can you read only Java and trust it is a JDK proxy?** No. Proxy choices can be merged toward the stronger setting.
- If tests show `isAopProxy=true`, **does that prove advice ran once?** Not yet. You need to count matching advice events on a specific call.

### Spring Framework reference documentation

- Spring AOP: Proxying mechanisms — https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Enabling @AspectJ support — https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Declaring an aspect — https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Schema-based AOP support — https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Mixing aspect types — https://docs.spring.io/spring-framework/reference/core/aop/mixing-styles.html

In Spring AOP, Java/XML configuration is consistent when **the context loading path is well-defined, proxy enablement has a clear owner, each aspect is registered the exact intended number of times, and each advice policy executes the exact expected number of times on the target bean**. Checking both configuration and runtime behavior together distinguishes a harmless redundant declaration from a true duplication bug.
