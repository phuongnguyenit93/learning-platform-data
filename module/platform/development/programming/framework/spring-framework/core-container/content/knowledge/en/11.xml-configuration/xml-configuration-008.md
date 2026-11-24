# Enabling `annotation-config` and `component-scan` in Spring XML

## 1. The Problem to Solve

The Spring IoC Container manages beans through **bean definitions**. When migrating gradually from XML to annotations, two configuration elements are commonly mentioned:

```xml
<context:annotation-config/>
<context:component-scan base-package="com.example"/>
```

These two elements are easily confused as equivalent, yet they address **two distinct needs**:

- **`<context:annotation-config/>`**: registers annotation-processing infrastructure so Spring recognizes `@Autowired`, `@Value`, certain Jakarta lifecycle annotations, and Java configuration metadata **on beans already registered in the context**. It **does not scan the classpath** to find classes annotated with `@Component`.
- **`<context:component-scan base-package="..."/>`**: discovers classes annotated with `@Component` or compatible stereotypes within the specified packages, **registers them as beans**, and **implicitly enables `annotation-config` functionality by default**. Therefore, you usually do not need to write both elements together.

Example: class `OrderService` is declared in XML via `<bean class="...OrderService"/>` and has `@Autowired OrderRepository repository`. If the container lacks `AutowiredAnnotationBeanPostProcessor`, that field injection will not run. Once `annotation-config` is enabled and a matching `OrderRepository` bean exists, Spring injects the dependency. Conversely, a `@Service` class merely sitting on the classpath without being scanned, imported, or registered never becomes a Spring bean automatically.

### Learning Objectives

After this lesson, you will be able to:

1. Declare valid Spring XML Beans and Context namespaces and schemas.
2. Distinguish **component discovery**, **bean registration**, **annotation injection**, and **bean lifecycle**.
3. Know which processors `annotation-config` registers and what it **does not** do.
4. Understand which stereotype candidates `component-scan` selects, how it scans packages/subpackages, and how bean names are assigned.
5. Explain why `component-scan` implicitly includes `annotation-config` by default.
6. Distinguish `annotation-config="false"` from `use-default-filters="false"`.
7. Use `include-filter`/`exclude-filter` and understand scanning boundaries.
8. Run a Java 17+, Spring Framework 6.2.9 example comparing **four XML contexts**.
9. Handle bean definition conflicts, wrong base packages, missing dependencies, duplicate components, and parent-child context issues.
10. Choose suitable configuration while migrating gradually from XML-only to annotation-based configuration.

**Scope:** Spring Framework **Core Container**. Do not assume Spring Boot, an HTTP server, transaction proxies, a persistence provider, or a scheduler start working just from these two elements.

## 2. Conceptual Model: Four Distinct Stages

```text
A. JAVA CLASS EXISTS ON CLASSPATH
       |
       +-- Explicit XML <bean>
       |
       +-- <context:component-scan> finds @Component candidates
       |
       +-- @Configuration / @Import / registration APIs (when enabled)
       |
       v
B. BEAN DEFINITIONS IN REGISTRY
       |
       | Processors registered by annotation-config
       | or implicitly by component-scan
       v
C. BEANFACTORY CREATES INSTANCES AND INJECTS
       |
       | @Autowired, @Value, applicable lifecycle callbacks
       v
D. MANAGED BEAN IN CONTEXT
```

An annotation like `@Component` is metadata on a **class**; it does not register the class in every `ApplicationContext` by itself. An annotation like `@Autowired` is metadata on an **injection point**; it requires a matching `BeanPostProcessor` and an already-registered dependency candidate.

### Distinguishing Two Questions

**Is the bean registered?**

```java
boolean exists = context.containsBean("orderService");
```

If false, check XML `<bean>`, `component-scan`, `@Import`, or registration APIs.

**Has the bean been injected?**

```java
OrderService service = context.getBean(OrderService.class);
boolean ready = service.hasRepository();
```

This is an illustrative snippet; `OrderService` must define `hasRepository()` in the project. If the bean exists yet its dependency is `null`, inspect annotation processors and how the bean was created, not just package scanning.

## 3. Standard XML Namespace Syntax

`<context:annotation-config/>` and `<context:component-scan/>` belong to the **Spring Context namespace**, not the default Spring Beans namespace.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="orderRepository"
          class="com.example.OrderRepository"/>
    <bean id="orderService"
          class="com.example.OrderService"/>

</beans>
```

In this structural example, the classes must exist on the runtime classpath with valid constructors/wiring. The namespace URIs and `schemaLocation` allow the XML parser to recognize `<beans>`, `<bean>`, and `context:` elements.

### Common XML Errors

If the error says prefix `context` is not bound: `xmlns:context` is missing. If it says the element is not allowed inside `<beans>`: check schema pairs, placement/nesting, dependencies, and Spring versions. Do not drop the namespace prefix to write `<component-scan>` without understanding XML namespaces.

Spring resolves matching schema resources from modules on the classpath; schema URLs are **not** application API endpoints or places where business services are defined.

## 4. What Infrastructure Does `annotation-config` Register?

According to Spring 6.2 documentation, `<context:annotation-config/>` activates post-processors for annotation-based configuration in the **current `ApplicationContext`**. The main components documented include:

- `ConfigurationClassPostProcessor`: processes known configuration classes, including `@Configuration`, `@Bean`, and `@Import` metadata.
- `AutowiredAnnotationBeanPostProcessor`: processes `@Autowired`, `@Value`, and supported equivalents on injection points.
- `CommonAnnotationBeanPostProcessor`: handles `@Resource`, `@PostConstruct`, and `@PreDestroy` when the matching Jakarta annotations APIs are present.
- `PersistenceAnnotationBeanPostProcessor` when required Jakarta Persistence dependencies are present.
- `EventListenerMethodProcessor` along with processors supporting event-listener metadata.

**Subtlety:** the exact infrastructure registered depends on the classpath and Spring version; do not assume every processor from every framework stack is guaranteed to be registered if specialized libraries or infrastructure are absent.

### 4.1. XML Bean with `@Autowired`

```java
package com.example;

import org.springframework.beans.factory.annotation.Autowired;

public class PaymentService {
    @Autowired
    private PaymentRepository repository;

    public boolean isReady() {
        return repository != null;
    }
}
```

This is an illustrative snippet requiring a valid `PaymentRepository` bean. If XML declares:

```xml
<context:annotation-config/>
<bean id="paymentRepository"
      class="com.example.PaymentRepository"/>
<bean id="paymentService"
      class="com.example.PaymentService"/>
```

the processor can inject `PaymentRepository`. **`PaymentService` does not need `@Component`** because XML has already registered the class as a bean.

### 4.2. `@Value` and Property Placeholders

```java
@Value("${client.timeout:30}")
private int timeout;
```

This is an illustrative snippet inside a Spring-managed bean. The annotation processor handles injection, while `Environment`/property source infrastructure supplies the value and conversion. To load properties beyond system defaults, use `<context:property-placeholder location="classpath:app.properties"/>` or an appropriate property source configuration.

**Do not confuse:** reading a properties file does not create bean definitions automatically; enabling `@Value` does not automatically instantiate external service clients described in properties.

### 4.3. Lifecycle Annotations

`@PostConstruct` and `@PreDestroy` belong to Jakarta annotation APIs in Spring Framework 6+. Java 17 does not bundle all Jakarta APIs automatically; when using those annotations, declare a compatible dependency such as `jakarta.annotation-api`.

If a class is instantiated with `new` outside the container, `@PostConstruct` **does not run** just because the annotation is present. It requires Spring lifecycle management with the corresponding processor.

### 4.4. Java `@Configuration` Still Needs to Be Registered

`<context:annotation-config/>` can process metadata on a Java configuration class **already registered in the context**, for example:

```xml
<context:annotation-config/>
<bean class="com.example.JavaFeatureConfiguration"/>
```

Assuming `JavaFeatureConfiguration` has valid `@Configuration`/`@Bean` declarations, this is how XML and Java configuration can be combined. However, `annotation-config` **does not automatically find every `@Configuration` on the classpath**: the class source here is the XML `<bean>`.

## 5. What `annotation-config` Does Not Do

It is **not a master switch for all of Spring Framework**. Simply writing:

```xml
<context:annotation-config/>
```

does not mean:

- Every `@Service` class in every package is scanned automatically.
- `@Repository` always receives exception translation without the required infrastructure.
- `@Transactional` automatically provides transaction AOP; a transaction manager and proxy infrastructure/`<tx:annotation-driven/>` are still required.
- `@Scheduled` runs without scheduling support.
- `@Async` runs asynchronously without async processing/executor configuration.
- `@Controller` handles HTTP requests in a Core Container lacking Spring MVC/`DispatcherServlet` infrastructure.
- Java objects created via `new` outside the container suddenly get injected.
- Processors in a child context automatically apply to beans in a parent context.

**Bottom line:** `annotation-config` enables **processing of annotations**, not **discovering classes**.

## 6. Which Classes Does `component-scan` Find and Register?

```xml
<context:component-scan base-package="com.example.orders"/>
```

Instructs the scanner to search for candidate classes in package `com.example.orders` and its subpackages. By default, stereotype candidates typically include:

- `@Component`.
- `@Service`.
- `@Repository`.
- `@Controller`.
- `@Configuration` (meta-annotated with `@Component`).
- Custom annotations meta-annotated with `@Component`; in environments with JSR-330/Jakarta annotations, Spring-supported filters may also match.

Example:

```text
com.example
├── orders
│   ├── OrderService.java          <-- inside scanned package
│   └── persistence
│       └── OrderRepository.java   <-- inside scanned subpackage
└── billing
    └── BillingService.java        <-- NOT under base-package orders
```

For the scanner to pick up `OrderService` or `OrderRepository`, the class must match the stereotype/filters and be a valid component candidate. The package declaration in Java source, runtime classpath, scan root, and filters must all align.

### Bean Names of Scanned Classes

A scanned class `@Service public class OrderService` normally receives bean name `orderService` by naming convention; you can specify `@Service("primaryOrderService")`.

If two classes in different packages share the short class name `OrderService`, auto-generated bean names can collide. Do not rely on different Java packages to guarantee unique bean names when scanning multiple packages into **one** context.

### Component Scan Does Not Necessarily Instantiate Immediately

The scanner registers bean definitions; Spring creates instances later according to scope and lifecycle. By default, non-lazy singletons are instantiated during refresh. `@Lazy`, `@Scope`, and dependencies can alter timing; do not assume the scanner calls constructors the moment it encounters an annotation.

## 7. Why Does `component-scan` Implicitly Enable `annotation-config` by Default?

According to the Spring Reference, `<context:component-scan>` **implicitly enables** most of `<context:annotation-config/>`'s functionality. This distinguishes two configurations:

**Processing only:**

```xml
<context:annotation-config/>
<bean id="manualService" class="demo.ManualService"/>
```

Spring can process `@Autowired` on `manualService` if a matching dependency bean exists, **yet will not discover** any `@Component` classes outside XML.

**Discovery + processing:**

```xml
<context:component-scan base-package="demo.scanned"/>
<bean id="manualService" class="demo.ManualService"/>
```

The scanner discovers beans in `demo.scanned`; processors enabled by default can then inject `@Autowired` into both scanned components **and** the XML-registered `manualService`.

| XML configuration | Registers stereotype candidates | Processes `@Autowired` on XML beans |
| --- | --- | --- |
| `<bean>` only | No | No, unless processors come from another source |
| `annotation-config` + `<bean>` | No | Yes, when valid dependencies exist |
| `component-scan` + `<bean>` | Yes | Yes, by default |
| `component-scan annotation-config="false"` + `<bean>` | Yes | No processor added by the scanner; may still work if registered elsewhere |
| Both default scan and `annotation-config` | Yes | Yes; the `annotation-config` tag is usually redundant |

### Does Component Scan Inject Only Scanned Beans?

No. Registered processors operate on all compatible Spring-managed beans in the same context, regardless of whether a bean was registered via XML or scanning. **Registration mechanism is separate from injection mechanism.**

## 8. What Does `annotation-config="false"` Mean?

```xml
<context:component-scan
    base-package="demo.scanned"
    annotation-config="false"/>
```

This element **still scans the package** and registers candidate components. The flag solely states that **this scanner element will not automatically register the annotation processors it normally adds by default**.

Consequently, a scanned class with an `@Autowired` field may be instantiated with that field left un-injected. However, if `<context:annotation-config/>` comes from another XML file or `AutowiredAnnotationBeanPostProcessor` is registered via another path, injection can still occur.

**Do not state categorically that `annotation-config="false"` stops all annotations everywhere.** What is accurate is that it disables *auto-registration by that scanner*.

### Warning About Similar Attribute Names

- `annotation-config="false"`: still selects stereotype candidates, but skips auto-registering annotation processing infrastructure.
- `use-default-filters="false"`: disables the **default candidate filters** so the scanner stops picking up `@Component`/`@Service` automatically; only classes matching explicit include filters are registered.

One flag governs **post-processors**; the other governs **which bean definitions are discovered**.

## 9. Complete Java 17+ Example Comparing Four XML Configurations

This demo uses **Spring Framework 6.2.9**, **Java 17+**, **Gradle**, and `ClassPathXmlApplicationContext`. To isolate each scenario without interference from shared registration infrastructure, we open four contexts **independently and sequentially**:

1. `plain.xml` — XML `<bean>` only; no scan, no annotation-config.
2. `annotations.xml` — enables `annotation-config`, no scan.
3. `scanned.xml` — enables default `component-scan`.
4. `scan-no-annotations.xml` — enables scan with `annotation-config="false"`.

In production, when modules share beans, you normally load all sources into **one context**. Four contexts here serve as isolated test fixtures to observe each element's effect clearly.

### 9.1. File Structure

```text
xml-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── App.java
        │       ├── Formatter.java
        │       ├── ManualConsumer.java
        │       └── scanned/
        │           └── ScannedConsumer.java
        └── resources/
            ├── plain.xml
            ├── annotations.xml
            ├── scanned.xml
            └── scan-no-annotations.xml
```

Java types are public top-level classes; each file sits in its matching package.

### 9.2. Gradle Setup

**`settings.gradle`**

```groovy
rootProject.name = 'xml-context-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
```

This dependency brings in `spring-beans`/`spring-core` and annotation infrastructure for `@Autowired`/`@Component`. Neither Spring Boot nor extra Jakarta annotation APIs are needed because the program does not use `@PostConstruct`.

### 9.3. `Formatter.java` — Bean Registered Only via XML

**`src/main/java/demo/Formatter.java`**

```java
package demo;

import java.util.Objects;

public final class Formatter {
    private final String prefix;

    public Formatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String format(String value) {
        return prefix + ":" + value;
    }
}
```

The class has no `@Component`. XML `<bean id="formatter">` below is its sole bean definition source.

### 9.4. `ManualConsumer.java` — XML Bean with `@Autowired` Field

**`src/main/java/demo/ManualConsumer.java`**

```java
package demo;

import org.springframework.beans.factory.annotation.Autowired;

public final class ManualConsumer {
    @Autowired
    private Formatter formatter;

    public boolean wired() {
        return formatter != null;
    }

    public String describe() {
        return formatter.format("manual");
    }
}
```

`ManualConsumer` has no `@Component`, yet all four XML files declare `<bean id="manualConsumer" class="demo.ManualConsumer"/>`. If the context lacks a processor supporting `@Autowired` fields, this field stays `null`.

**Call `describe()` only in contexts where `wired()==true` is confirmed** so we do not trigger a `NullPointerException`.

### 9.5. `ScannedConsumer.java` — Discovered Only by Component Scan

**`src/main/java/demo/scanned/ScannedConsumer.java`**

```java
package demo.scanned;

import demo.Formatter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component("scannedConsumer")
public final class ScannedConsumer {
    @Autowired
    private Formatter formatter;

    public boolean wired() {
        return formatter != null;
    }

    public String describe() {
        return formatter.format("scan");
    }
}
```

This class has a stereotype and explicit bean name. In `annotations.xml` there is neither a scanner nor an XML `<bean>` for it, so it is not a bean. In `scanned.xml` and `scan-no-annotations.xml`, the scanner finds the class.

### 9.6. `plain.xml` — No `annotation-config` or Scan

**`src/main/resources/plain.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

Here this XML registers neither annotation processors nor package scanning. `ManualConsumer` is created without field autowiring, and `ScannedConsumer` is absent.

### 9.7. `annotations.xml` — Has `annotation-config`, No Scan

**`src/main/resources/annotations.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

`AutowiredAnnotationBeanPostProcessor` processes the field on the XML-declared `ManualConsumer`. `ScannedConsumer` remains unregistered.

### 9.8. `scanned.xml` — Scan Implicitly Enables Annotation Processing

**`src/main/resources/scanned.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.scanned"/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

Has both XML beans and a scanned bean. Processors registered automatically by the scanner inject the same `Formatter` singleton into both consumers' `@Autowired` fields.

### 9.9. `scan-no-annotations.xml` — Scans Without Adding Processors

**`src/main/resources/scan-no-annotations.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan
        base-package="demo.scanned"
        annotation-config="false"/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

`ScannedConsumer` is still registered as a bean by the scanner. However, because this fixture has no other source registering `AutowiredAnnotationBeanPostProcessor`, neither `@Autowired` field is processed.

### 9.10. `App.java`

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.scanned.ScannedConsumer;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext plain =
                     new ClassPathXmlApplicationContext("plain.xml")) {

            ManualConsumer consumer = plain.getBean(ManualConsumer.class);
            System.out.println("plain.manual-wired=" + consumer.wired());
            System.out.println("plain.scanned-count="
                    + plain.getBeanNamesForType(ScannedConsumer.class).length);
        }

        try (ClassPathXmlApplicationContext annotations =
                     new ClassPathXmlApplicationContext("annotations.xml")) {

            ManualConsumer consumer =
                    annotations.getBean(ManualConsumer.class);
            System.out.println("annotation.manual-wired=" + consumer.wired());
            System.out.println("annotation.manual-message="
                    + consumer.describe());
            System.out.println("annotation.scanned-count="
                    + annotations.getBeanNamesForType(
                            ScannedConsumer.class).length);
        }

        try (ClassPathXmlApplicationContext scanned =
                     new ClassPathXmlApplicationContext("scanned.xml")) {

            ManualConsumer manual = scanned.getBean(ManualConsumer.class);
            ScannedConsumer component =
                    scanned.getBean(ScannedConsumer.class);

            System.out.println("scan.manual-wired=" + manual.wired());
            System.out.println("scan.scanned-count="
                    + scanned.getBeanNamesForType(
                            ScannedConsumer.class).length);
            System.out.println("scan.scanned-wired=" + component.wired());
            System.out.println("scan.scanned-message="
                    + component.describe());
        }

        try (ClassPathXmlApplicationContext scanOff =
                     new ClassPathXmlApplicationContext(
                             "scan-no-annotations.xml")) {

            ManualConsumer manual = scanOff.getBean(ManualConsumer.class);
            ScannedConsumer component =
                    scanOff.getBean(ScannedConsumer.class);

            System.out.println("scan-off.manual-wired=" + manual.wired());
            System.out.println("scan-off.scanned-count="
                    + scanOff.getBeanNamesForType(
                            ScannedConsumer.class).length);
            System.out.println("scan-off.scanned-wired="
                    + component.wired());
        }
    }
}
```

### 9.11. Run Command

In the `xml-context-demo` directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows:

```bat
gradlew.bat run --quiet
```

Running `javac App.java` alone is insufficient because other files must be compiled and Spring JAR dependencies must be on the classpath. Gradle configures the classpath, compiles sources, and copies resources.

### 9.12. Exact Expected Program Stdout

```text
plain.manual-wired=false
plain.scanned-count=0
annotation.manual-wired=true
annotation.manual-message=xml:manual
annotation.scanned-count=0
scan.manual-wired=true
scan.scanned-count=1
scan.scanned-wired=true
scan.scanned-message=xml:scan
scan-off.manual-wired=false
scan-off.scanned-count=1
scan-off.scanned-wired=false
```

These are the **12 lines explicitly printed from Java**. Build/runtime tools may emit extra framework logs; those are not part of these `println` outputs.

### 9.13. Output Explanation

**`plain`**: XML registers `Formatter`/`ManualConsumer` with no processor or scanner, so `manual-wired=false` and `scanned-count=0`.

**`annotations`**: `annotation-config` enables the processor; `ManualConsumer` is injected and returns `xml:manual`. Without scanning, `ScannedConsumer` does not become a bean.

**`scanned`**: `component-scan` both registers `ScannedConsumer` and implicitly enables processors; both `@Autowired` consumers receive the XML `Formatter`.

**`scan-no-annotations`**: the scanner still registers `ScannedConsumer` (count 1), yet does not add processors; both `ManualConsumer` and `ScannedConsumer` keep `null` fields in this fixture. `main` only checks `wired()` and avoids calling `describe()` in this context.

**Do not mistake the four demo contexts for four contexts inside a single application.** They are independent experiments isolating the effect of each XML element.

## 10. `include-filter`, `exclude-filter`, and `use-default-filters`

By default, the scanner uses stereotype filters. To customize candidate selection, add filters.

### 10.1. Excluding a Group of Classes

```xml
<context:component-scan base-package="com.example.orders">
    <context:exclude-filter type="regex"
        expression="com\.example\.orders\.testsupport\..*"/>
</context:component-scan>
```

This is a structural snippet: the rule takes effect only if real packages and class names match the pattern. Backslashes `\` in the XML attribute are part of the regex, not Java string escapes.

### 10.2. Selecting Only a Custom Annotation

```xml
<context:component-scan base-package="com.example.jobs"
                        use-default-filters="false">
    <context:include-filter type="annotation"
        expression="com.example.jobs.WorkerTask"/>
</context:component-scan>
```

With this configuration, the scanner does not select all `@Component` classes by default, instead finding classes annotated with `WorkerTask` per the include filter. `WorkerTask` must be a real annotation type. `use-default-filters="false"` does not disable the scanner's annotation processors: that is a separate flag.

### 10.3. Common Filter Types

| `type` | `expression` | Meaning |
| --- | --- | --- |
| `annotation` | Fully qualified annotation class | Include/exclude annotations |
| `assignable` | Fully qualified base class or interface | Select classes matching the type hierarchy |
| `regex` | Regular expression for class name | Rules by class name pattern |
| `aspectj` | AspectJ type pattern | Filter by AspectJ type expression |
| `custom` | `TypeFilter` implementation class | Custom predicate |

A policy can combine include and exclude filters. However, filters do not replace module packaging or dependency governance; the scanner still inspects classes present on the classpath.

### 10.4. Example Distinguishing the Two Flags

**Disable processors only:**

```xml
<context:component-scan
    base-package="com.example"
    annotation-config="false"/>
```

`@Component` classes can still be registered.

**Disable default stereotype selection only:**

```xml
<context:component-scan
    base-package="com.example"
    use-default-filters="false">
    <context:include-filter type="annotation"
        expression="com.example.SpecialComponent"/>
</context:component-scan>
```

Annotation processors are still registered by the scanner by default, while only candidates matching the filter are discovered under the stated policy.

## 11. Mixing XML Beans and Scanned Beans in the Same Context

In practice, you might use XML for vendor/client libraries needing constructor arguments while business services use annotations:

```xml
<context:component-scan base-package="com.example.checkout"/>

<bean id="paymentGateway"
      class="com.example.vendor.ExternalGateway">
    <constructor-arg value="https://gateway.example.test"/>
</bean>
```

A `@Service` inside the scanned package can constructor-inject `PaymentGateway` when type/qualifier matches. Conversely, an XML `<bean>` can use `<constructor-arg ref="scannedService"/>` to reference a scanned and registered bean.

**Rule:** injection operates across the context's bean definitions without requiring both sides to come from the same declaration source. If the scanner does not scan the vendor class yet XML registered the vendor bean, it is still a valid candidate.

### Avoid Registering the Same Class Twice

Suppose `EmailService` carries `@Service` inside the scanned package, while XML also declares:

```xml
<bean id="emailService" class="com.example.EmailService"/>
```

This risks name/definition collisions or duplicate candidates depending on registration and overriding policies. If XML is meant to override configuration intentionally, design an explicit policy; do not leave duplicates behind from forgetting to delete old definitions during migration.

### Multiple Beans of the Same Type

If two beans both implement `NotificationSender`, injection by type may fail to find a unique candidate. Use `@Qualifier`, `@Primary`, or register only the intended implementation.

## 12. Limitations of Annotation Processing

### 12.1. Objects Must Be Managed by Spring

A `new ManualConsumer()` created directly by Java code **will not be injected** just because XML includes `annotation-config`. `BeanPostProcessor`s are invoked by Spring as part of BeanFactory lifecycle management, not as a global Java annotation interpreter for arbitrary objects.

### 12.2. Jakarta Libraries Must Be Present

In Java 17 / Spring 6+, if you use `jakarta.annotation.PostConstruct` or `jakarta.inject.Inject`, declare the proper Jakarta dependencies. Having `@Autowired` does not mean every Jakarta package is automatically available.

### 12.3. Transactions, Caching, Async, and Scheduling Need Separate Infrastructure

- `@Transactional`: requires a transaction manager and transaction advice infrastructure.
- `@Cacheable`: requires cache infrastructure.
- `@Async`: requires async-enabled annotation processors and an appropriate executor.
- `@Scheduled`: requires scheduling support.
- `@RequestMapping`: requires Spring MVC / web request mapping infrastructure.

Neither `annotation-config` nor `component-scan` in the Core Container **guarantees** those features operate on their own.

### 12.4. `@Repository` Exception Translation Is Not Automatic in Every Project

`@Repository` marks persistence/DAO roles. Exception translation can require `PersistenceExceptionTranslationPostProcessor` and matching adapters/infrastructure. Do not assume that merely scanning `@Repository` translates every JDBC/JPA exception into a specific Spring exception.

## 13. Parent-Child ApplicationContexts

A traditional web application may have a root context and a child servlet context. `<context:annotation-config/>` registers processors **only in the context containing it**.

```text
Root ApplicationContext
  ├── dataSource
  ├── orderRepository
  └── orderService

Child WebApplicationContext
  ├── orderController
  └── viewResolver
```

Enabling `annotation-config` only in the child does not register `BeanPostProcessor`s in the root context. Root beans need processors in the root context when using annotation injection. Bean visibility between parent and child is also asymmetric: the child can look up beans from the parent, whereas the parent cannot see beans defined only in the child.

This is a subtle bug to diagnose when child XML has `annotation-config` yet root services fail to receive annotation injection.

## 14. Common Pitfalls

### Pitfall 1: Enabling `annotation-config` and Forgetting `component-scan`

`@Component` classes are not discovered from the classpath automatically. Unless the type is declared in XML, imported, or registered, the app reports a missing bean.

### Pitfall 2: Scanning the Wrong `base-package`

`com.example.order` differs from `com.example.orders`. The package must match the Java `package` declaration and runtime classpath.

### Pitfall 3: Scanning Too Broadly

Scanning a large root package can pull test components, optional configurations, adapters, or unintended services into the context.

### Pitfall 4: Declaring Both `annotation-config` and Default `component-scan` Thinking It Scans More

Both elements together do not expand scanning scope. Default `component-scan` already enables processors; an explicit `annotation-config` is usually redundant.

### Pitfall 5: Misunderstanding `annotation-config="false"`

The scanner still discovers and registers classes. The flag only stops the scanner from adding annotation processors automatically. If processors come from elsewhere, injection can still run.

### Pitfall 6: Confusing It with `use-default-filters="false"`

That flag alters candidate filtering, not annotation processor registration.

### Pitfall 7: Bean Registered in XML Yet `@Autowired` Stays `null`

Check whether Spring created the object, whether the annotation processor is present, and whether a matching dependency bean exists in the context.

### Pitfall 8: Two Beans of the Same Type Causing `NoUniqueBeanDefinitionException`

Registering multiple implementations may be valid, but single-bean injection points need `@Qualifier`, `@Primary`, or a single candidate.

### Pitfall 9: Two Classes Sharing a Bean Name

Name collisions can happen even when two classes reside in different packages. Use scoped scan boundaries and explicit names or qualifiers where needed.

### Pitfall 10: Using `@PostConstruct` Without Jakarta APIs

Java 17 does not include every Jakarta annotation API out of the box. Add the right dependency version and ensure the processor is active.

### Pitfall 11: Thinking Scanning Instantiates Beans Immediately

Scanning primarily registers definitions; BeanFactory creates instances based on scope, lazy/depends-on settings, and dependency graphs.

### Pitfall 12: Expecting `annotation-config` Alone to Enable `@Transactional`

Transaction support is a separate stack requiring a transaction manager and advice configuration.

### Pitfall 13: Thinking a `@Controller` Bean Creates an HTTP Endpoint

A controller bean does not automatically set up Spring MVC `DispatcherServlet` and request-mapping infrastructure.

### Pitfall 14: Ambiguous Context Ownership

Beans in a root context are not processed by processors registered only in a child context.

### Pitfall 15: Testing with `new` and Concluding the Processor Is Broken

Objects outside Spring's lifecycle will never receive Spring field injection. Write real integration tests using `ApplicationContext`.

### Pitfall 16: Setting `use-default-filters="false"` While Forgetting Filters

`use-default-filters="false"` requires matching include filters; otherwise the scanner may register none of your expected beans.

### Pitfall 17: Component Inside a JAR Not Found by Scanner

Check that the dependency is packaged on the runtime classpath, verify directory/module entries, and verify classpath scanning resources.

### Pitfall 18: Using `@Value` Without a Property Source

Annotation injection handles `@Value`, yet values still need a valid property source and placeholder resolution infrastructure.

## 15. Step-by-Step Debugging Process

When `@Autowired` does not work, ask in order:

1. **Does the bean exist?** Check `getBeanNamesForType` and `containsBean`.
2. **How was the bean registered?** XML `<bean>`, scan, `@Bean`, or programmatic registration?
3. **Was the object created by Spring?** Never test DI on an object created with `new`.
4. **Is the processor present in the right context?** `annotation-config` or default `component-scan`, unless disabled.
5. **Does the dependency candidate exist?** If not, which scan, package, or registration source is missing?
6. **Are there multiple candidates of the same type?** Check `@Qualifier` or `@Primary`.
7. **Is a filter, profile, or condition excluding the bean?**
8. **Are root/child contexts involved?**
9. **Is there a wrong namespace, missing JAR, or wrong annotation package?**
10. **Are you mistaking a specialized framework stack for Core `annotation-config`?**

### Inspecting Processors Directly (When Needed)

Inside an active context:

```java
String[] names = context.getBeanNamesForType(
        org.springframework.beans.factory.annotation
            .AutowiredAnnotationBeanPostProcessor.class);
System.out.println(names.length);
```

This is an illustrative diagnostic snippet; the exact count depends on context infrastructure and Spring version. It does not replace verifying that your service actually received the expected dependency.

### Unit Tests vs. Integration Tests

Unit tests instantiate a service directly with constructor-injected fakes to test business logic. Integration tests boot the real XML context to verify scanning, bean registration, annotation processing, and lifecycle. Do not call `new` expecting Spring to populate `@Autowired` fields.

## 16. Roadmap for Migrating Legacy XML to Annotations

A controlled strategy:

1. Initially, XML registers most services, repositories, and adapters via `<bean>`.
2. Enable `<context:annotation-config/>` to use annotation injection on **known beans** while keeping XML registrations.
3. Choose a clear feature package and enable `<context:component-scan>` for new components.
4. Since scanning enables processors by default, you can remove the explicit `annotation-config` once scanning is active unless there is a specific reason to keep it.
5. When a class moves completely to `@Component` and is scanned, delete its duplicate XML `<bean>` to prevent conflicts.
6. Test bean names/types, qualifiers, scopes, and lifecycles before and after migration.
7. Expand `base-package` only with tests confirming no unwanted components or configurations are swept in.
8. Keep XML for vendor beans needing custom constructors or factory logic when helpful; Spring never forces 100% conversion to annotations.

**Note:** changing the source of bean definitions should not change resource ownership. In particular, never create two HTTP clients, DataSources, or pools because both XML and scanning register the same implementation.

## 17. XML Configuration Design Checklist

- XML includes valid `beans` and `context` namespaces and schema locations.
- It is clear which classes are registered by XML and which are discovered by scanning.
- `annotation-config` is enabled when annotation processing is needed without another scanner/infrastructure.
- When default `component-scan` is used, redundant duplicate processors are avoided.
- `base-package` covers the right feature and subpackages.
- `annotation-config="false"` is not mistaken for disabling scanning.
- `use-default-filters="false"` is paired with include filters as required.
- XML `<bean>` declarations and scanned components do not create unintended duplicates.
- Injection candidates have unambiguous types, names, or qualifiers.
- Parent/child context boundaries are verified if applicable.
- Specialized annotations have their own infrastructure rather than assuming Core Container provides them.
- Code has integration tests that start an `ApplicationContext` and verify actual injection.
- Scanned bean names are not treated as immutable contracts without a naming policy.
- Startup logs are checked alongside bean-definition/injection evidence, not merely “scan succeeded.”

## 18. Review Questions

**Q1.** Does `annotation-config` automatically scan packages for `@Service`?

**Answer:** No. It registers annotation processors for beans already registered in the context.

**Q2.** Does `component-scan` enable `annotation-config` functionality by default?

**Answer:** Yes. That behavior is documented in the Spring Reference, so writing both is usually unnecessary.

**Q3.** An XML bean has an `@Autowired` field; must the class itself carry `@Component`?

**Answer:** No, if the bean is already registered in XML and the context has the matching processor.

**Q4.** A class has `@Component` yet is not scanned, imported, or registered; does it appear automatically in the context?

**Answer:** No.

**Q5.** Does `annotation-config="false"` on the scanner stop the scanner from finding classes?

**Answer:** No. It stops the scanner from adding annotation processors automatically; candidate discovery still occurs.

**Q6.** What does `use-default-filters="false"` do?

**Answer:** It disables default stereotype candidate filters; include filters are needed to explicitly select classes.

**Q7.** In the demo, why is `annotation.scanned-count=0`?

**Answer:** `annotations.xml` has no component scan or registration source for `ScannedConsumer`.

**Q8.** In the demo, why is `scan-off.scanned-count=1` while `scan-off.scanned-wired=false`?

**Answer:** The scanner registered the bean without adding processors; that context had no other processor source.

**Q9.** Does the scanner inject `@Autowired` only for scanned beans?

**Answer:** False. Processors in the context process injection for Spring-managed beans created in that context, including XML-registered beans.

**Q10.** When two implementations of an interface exist in the context, how must `@Autowired` handle them?

**Answer:** Use appropriate candidate selection such as `@Qualifier`, `@Primary`, or register only one implementation where needed.

**Q11.** Does enabling `annotation-config` automatically give `@Transactional` transaction behavior?

**Answer:** No. Appropriate transaction management infrastructure is required.

**Q12.** Does enabling `annotation-config` in a child context process fields on beans in the root context?

**Answer:** No. A processor is scoped to the context in which it is registered.

**Q13.** Why do tests calling `new Service()` not reflect field injection?

**Answer:** Because there is no Spring BeanFactory lifecycle or `BeanPostProcessor` acting on manually constructed objects.

**Q14.** When XML defines a vendor bean and a scanned service needs it, can the dependency be injected?

**Answer:** Yes, provided both definitions reside in the relevant context and type/qualifier matches.

## 19. Official Documentation

- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): `<context:annotation-config/>` and processors.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): component scan, implicit annotation-config, filters, and flags.
- [Spring Framework 6.2 — `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): constructor/field/method injection.
- [Spring Framework 6.2 — XML-based Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): XML bean definitions and the container.
- [Spring Framework 6.2 — BeanFactory Post-processors](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): registry/instance post-processing.
- [Spring Framework 6.2 Javadoc — `AutowiredAnnotationBeanPostProcessor`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html).
- [Spring Framework 6.2 Javadoc — `ClassPathXmlApplicationContext`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html).

**Final takeaway:** In Spring XML, `<context:annotation-config/>` enables **annotation processing on existing beans**; `<context:component-scan/>` **discovers/registers components** and implicitly enables annotation processing by default. The two attributes `annotation-config="false"` and `use-default-filters="false"` control **two distinct layers**: processors and scanner candidate selection. Properly separating **bean registration** from **dependency injection** is the key to using both safely.
