# Combining Multiple Configuration Sources in One Spring ApplicationContext

## 1. Problem Statement

In a Spring Framework project, not every bean comes from the same file or the same declaration style. A growing application may have:

- Beans created by the application via **Java configuration** (`@Configuration` and `@Bean`).
- Beans kept in **XML configuration** from legacy systems.
- Services/adapters discovered via **component scanning** (`@ComponentScan` with `@Component`, `@Service`, `@Repository`, etc.).
- Beans registered **programmatically** at bootstrap (`register`, `registerBean`, `registerBeanDefinition`).
- Smaller configurations composed via **`@Import`**, or XML sources connected via **`@ImportResource`**.

Spring can feed all of these **bean definitions** into **one IoC Container**, and then resolve dependencies among them without forcing every class to use the same annotation style.

The point of this topic is not merely “loading multiple files”: what matters is that **configuration sources contribute metadata**, while **one BeanFactory/ApplicationContext** uses that metadata to instantiate and manage objects under unified rules. As a result, a bean from XML can be injected into a component-scanned service, and a `@Bean` method can consume a programmatically registered bean.

### Learning Objectives

After this lesson, you will know how to:

1. Distinguish **bean definition sources** from **property sources** and from **multiple separate ApplicationContexts**.
2. Compose Java configurations with `@Import` and XML with `@ImportResource`.
3. Combine `@ComponentScan` with `@Bean`, XML beans, and `registerBean` registrations.
4. Build a context in the proper sequence: **register sources → `refresh()` → use → `close()`**.
5. Resolve dependencies across sources; handle duplicate bean names, multiple candidates of the same type, initialization ordering, and processors.
6. Choose a strategy for integrating legacy XML with new Java configuration without accidentally creating nested contexts.
7. Run a Java 17+ example with **four different bean registration mechanisms** working together inside **one `AnnotationConfigApplicationContext`**.

## 2. Central Concept: One Context, Multiple Metadata Sources

A Spring bean is an object managed by the container according to a bean definition/registration. The container needs to know the bean class or supplier/factory, name, scope, dependencies, and other management attributes. That metadata can come from multiple places.

```text
Java @Configuration/@Bean ─────┐
                              │
XML <bean> / @ImportResource ──┤
                              │
@ComponentScan ────────────────┼──> BeanDefinitionRegistry
                              │             │
registerBean(...) ────────────┘             v
                                     BeanFactory / Context
                                              │
                                Dependency resolution + lifecycle
                                              │
                                       Bean instances
                                              │
                                  One ApplicationContext
```

**One context** means the registrations contribute to **one registry/factory and one shared dependency resolution mechanism**. A default singleton bean is a singleton **within that container**, not a JVM-wide singleton.

For example:

- `Formatter` comes from Java `@Bean`.
- `LegacyPrefixer` comes from XML `<bean>`.
- `AggregationService` comes from `@ComponentScan`.
- `AuditSink` comes from `context.registerBean(...)`.

When `AggregationService` has a constructor requiring all three dependencies, Spring finds candidates in the same context and injects them; the service **does not need to know** which style was used to declare each dependency.

### Do Not Confuse “Multiple Sources” with “Multiple Containers”

If you create:

```java
var context1 = new AnnotationConfigApplicationContext(JavaConfig.class);
var context2 = new ClassPathXmlApplicationContext("legacy.xml");
```

these are **two separate ApplicationContexts** that do not automatically share registries or singleton caches. To access beans from another context, you must establish a parent-child relationship or connect them intentionally. That is **different** from Java and XML contributing bean definitions into **one** context.

The snippet above is illustrative; it requires imports and real `JavaConfig` and `legacy.xml`. Do not use it if the goal is to compose beans into the same context.

## 3. Five Common Ways to Contribute Configuration

| Approach | Example | Effect | Suitable Scenario |
| --- | --- | --- | --- |
| Java factory method | `@Bean Formatter formatter()` | Registers bean from factory method | Library objects, explicit configuration, builders |
| Java configuration import | `@Import(PricingConfig.class)` | Loads additional configuration/types | Composing functional modules |
| XML import | `@ImportResource("classpath:legacy.xml")` | Loads XML bean definitions into a Java context | Legacy XML integration, specialized XML namespaces |
| Component scanning | `@ComponentScan(basePackageClasses=JobService.class)` | Searches for classes with stereotypes/filters | Services, adapters, and app-owned components |
| Programmatic registration | `context.registerBean("auditSink", AuditSink.class, AuditSink::new)` | Registers bean via API before refresh | Dynamic bootstrap, test fixtures, runtime plugins/modules |

These approaches **can work together**. However, each bean should have a **clear registration owner**; never assume that declaring the same class across multiple sources will cause Spring to automatically “merge” them into one bean.

## 4. Approach 1 — Java @Configuration and @Bean

Java configuration expresses bean definition sources in type-checked Java source code:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormattingConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter("java");
    }
}
```

This is a condensed configuration assuming `Formatter` is a project class with a constructor taking `String`. In the complete demo below, that class will be declared in full.

When `FormattingConfiguration` is loaded via `@Import` or `register`, Spring recognizes the factory method and registers a bean named `formatter`. When an object is needed, Spring invokes the method and manages the result according to scope/lifecycle.

**Characteristics:**

- The `@Bean` return type helps Spring predict the type for dependency resolution.
- A factory method can receive bean dependencies through parameters: `Formatter formatter(AppSettings settings)`.
- No `@Component` is needed on the returned object's class.
- `proxyBeanMethods=false` does not disable `@Bean`; it only disables inter-bean method interception within that configuration class. Use method parameter injection to wire beans, avoiding cross-calling factory methods in ways that create extra objects.
- A `@Configuration` class in source code still needs to be **loaded into the context** via a valid path; the annotation alone does not create a context.

## 5. Approach 2 — @Import Composing Multiple Java Configurations

Suppose the reports module declares a bean, while the formatting module provides a dependency:

```java
@Configuration(proxyBeanMethods = false)
@Import(FormattingConfiguration.class)
public class ReportsConfiguration {
    @Bean
    ReportService reportService(Formatter formatter) {
        return new ReportService(formatter);
    }
}
```

`ReportService` and `Formatter` are example types; this snippet goes inside a class with matching imports. When `ReportsConfiguration` is registered, Spring processes `@Import` and registers definitions from `FormattingConfiguration`.

This approach has two main benefits:

1. **Clear composition:** load only the root configuration; child sources are imported by design.
2. **Explicit dependencies:** `reportService(Formatter formatter)` states it needs a `Formatter` bean; it does not call `new FormattingConfiguration().formatter()`.

`@Import` does not create a child context. Both beans live in the container being built. An application can also call `context.register(ConfigA.class, ConfigB.class)` instead of a centralized import configuration; both are ways of loading configuration metadata, not different kinds of beans.

## 6. Approach 3 — XML Bean Definitions via @ImportResource

In a system migrating from XML to Java configuration, Spring allows keeping some beans in XML and loading them into a Java context with `@ImportResource`.

**Java configuration:**

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
public class ApplicationConfiguration {
}
```

**`src/main/resources/legacy-beans.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyPrefixer" class="demo.legacy.LegacyPrefixer">
        <constructor-arg value="xml"/>
    </bean>
</beans>
```

The class `demo.legacy.LegacyPrefixer` must exist on the classpath and have a constructor accepting `String`. The XML file is a **classpath resource**, placed on the runtime classpath by Gradle from `src/main/resources`.

**When is this advantageous?**

- There are many legacy XML definitions you do not want to migrate all at once.
- A library/framework integration is more convenient with an XML namespace than Java config.
- You want a Java-centric style: new config written in Java, legacy parts imported only where needed.

`@ImportResource` lets **XML and Java contribute definitions into one context**; it does not spin up another `ClassPathXmlApplicationContext` behind the scenes for each imported file.

### 6.1. Java-Centric or XML-Centric?

**Java-centric** uses `AnnotationConfigApplicationContext` as the startup point and `@ImportResource` to load XML bean definitions into **the same context**. **XML-centric** can use `ClassPathXmlApplicationContext`, declare Java configuration classes in XML, and enable appropriate annotation configuration processing (such as `<context:annotation-config/>`). Both approaches are valid; do not open two independent contexts and assume they share beans.

### 6.2. Difference from XML `<import/>`

XML `<import resource="feature-beans.xml"/>` loads additional XML from the current resource; `@ImportResource("classpath:...")` loads XML from Java configuration; `@Import(SomeConfig.class)` loads classes/selectors/registrars via Java metadata. In this overview lesson, all three are **sources of bean definitions for the same container**. Path syntax, namespaces, aliases, and XML migration paths are practiced separately in the next `@ImportResource` lesson.

## 7. Approach 4 — @ComponentScan and Stereotypes

A class whose source is managed by the application can carry `@Component`:

```java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public final class HealthMarker {
    public String label() {
        return "scanned";
    }
}
```

A configuration class with:

```java
@ComponentScan(basePackageClasses = HealthMarker.class)
```

scans **the package containing `HealthMarker` and its subpackages**, not just `HealthMarker` alone. The default scanner recognizes `@Component` and appropriate stereotypes/meta-annotations.

Combining multiple configuration sources is useful because a scanned class **can inject** beans from XML, `@Bean`, or registration APIs. For example:

```java
@Component
public final class ReportCoordinator {
    private final Formatter formatter;
    private final LegacyPrefixer prefixer;

    public ReportCoordinator(Formatter formatter, LegacyPrefixer prefixer) {
        this.formatter = formatter;
        this.prefixer = prefixer;
    }

    public String format(String value) {
        return prefixer.wrap(formatter.format(value));
    }
}
```

This is an illustrative class (requiring package/type imports), not a standalone file from the main demo. A single constructor is usually auto-selected by Spring for injection without `@Autowired`. Crucially, **the two dependencies do not need to be scanned**: they can come from Java or XML.

### 7.1. Why Should Scan Scope Be Limited?

If you scan an overly broad root package, Spring may additionally discover:

- Multiple unintended `@Configuration` classes, pulling in other `@Bean` definitions.
- An implementation meant only for tests.
- Components with conflicting bean names or implementing the same interface, causing duplicates/ambiguity.
- Components belonging to modules you did not intend to enable.

Therefore, `basePackageClasses` or `basePackages` should align with appropriate boundaries. `@Import` at the composition root makes modules visible, while `@ComponentScan` lets a module pick classes it owns; the two do not conflict.

## 8. Approach 5 — Programmatic Registration Before refresh()

Spring allows registering beans via Java API:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(
        "auditSink",
        AuditSink.class,
        AuditSink::new
);

context.register(AppConfiguration.class);
context.refresh();
```

`AppConfiguration` and `AuditSink` are illustrative types; `AnnotationConfigApplicationContext` must be imported. The `registerBean` API accepts a name, bean class, and `Supplier`, creating a bean definition for the container to use during initialization.

**Do not confuse the two:**

- `context.registerBean("auditSink", AuditSink.class, AuditSink::new)`: registers **a bean definition with a supplier**; Spring manages the instance created from that definition.
- `AuditSink sink = new AuditSink()` in an external Java variable: only creates a Java object. It does not automatically become a Spring bean and does not receive injection/callbacks unless registered via an appropriate API.

### 8.1. Why Must Registration Happen Before refresh()?

`AnnotationConfigApplicationContext` has a no-arg constructor so you can add configurations via `register(...)`, `scan(...)`, and `registerBean(...)`, and then **call `refresh()`** for Spring to process metadata/processors and create required singletons.

Recommended bootstrap sequence:

```text
new AnnotationConfigApplicationContext()
   |
register(AppConfiguration.class)
registerBean("auditSink", AuditSink.class, AuditSink::new)
   |
refresh()
   |
getBean(AggregationService.class)
   |
close()
```

Some container variants expose APIs allowing definition registration after refresh, but **do not treat that as default behavior** when the problem is multi-source bootstrap: post-processors, singleton pre-instantiation, events/lifecycles, and configuration conditions may have already executed. Complete all registrations before `refresh()` if you want one set of bean definitions processed consistently from the start.

### 8.2. How registerBean Differs from register(Class...) and scan(String...)

- `register(AppConfiguration.class)`: registers an **annotated component/configuration class** for Spring to process its class metadata.
- `scan("demo.scanned")`: instructs the scanner to find candidates in a package.
- `registerBean("auditSink", AuditSink.class, AuditSink::new)`: registers a bean definition directly, without needing `@Component` on the class or scanning.
- `registerBeanDefinition(...)` on the registry: low-level API requiring a prepared `BeanDefinition`; usually only needed for framework/integration code.

They are simply different ways to **contribute registrations into the same context**.

## 9. Runnable Example: Java + XML + Component Scan + Programmatic Bean

This is the centerpiece example. We need four beans from four different sources:

| Bean | Class | Source |
| --- | --- | --- |
| `formatter` | `Formatter` | `@Bean` from an `@Import`ed Java configuration |
| `legacyPrefixer` | `LegacyPrefixer` | XML `<bean>` loaded via `@ImportResource` |
| `aggregationService` | `AggregationService` | `@Component` found via `@ComponentScan` |
| `auditSink` | `AuditSink` | `context.registerBean(...)` at bootstrap |

`AggregationService` has a constructor taking **all three dependencies**: `Formatter`, `LegacyPrefixer`, and `AuditSink`. Spring must locate the beans by type within **one context** in order to instantiate the service.

### 9.1. Project Structure

```text
multi-source-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── App.java
        │       ├── config/
        │       │   ├── AppConfiguration.java
        │       │   └── FormattingConfiguration.java
        │       ├── javaformat/
        │       │   └── Formatter.java
        │       ├── legacy/
        │       │   └── LegacyPrefixer.java
        │       ├── audit/
        │       │   └── AuditSink.java
        │       └── scanned/
        │           └── AggregationService.java
        └── resources/
            └── legacy-beans.xml
```

Each public top-level class lives in a file matching its class name and package path.

### 9.2. Gradle Configuration

**`settings.gradle`**

```groovy
rootProject.name = 'multi-source-context-demo'
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

Spring Context already brings in the Spring Core/Beans dependencies needed to process XML and annotation configurations. The example runs on Java 17+, requiring no Spring Boot, servlet container, or database.

### 9.3. Java Bean: Formatter

**`src/main/java/demo/javaformat/Formatter.java`**

```java
package demo.javaformat;

import java.util.Objects;

public final class Formatter {
    private final String source;

    public Formatter(String source) {
        this.source = Objects.requireNonNull(source);
    }

    public String format(String value) {
        return source + "[" + value + "]";
    }
}
```

This class has **no `@Component`**. It becomes a Spring bean through a Java configuration factory method.

**`src/main/java/demo/config/FormattingConfiguration.java`**

```java
package demo.config;

import demo.javaformat.Formatter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormattingConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter("java");
    }
}
```

The default bean name is `formatter`; the return type is `Formatter`. Spring can inject it into services located in other packages.

### 9.4. XML Bean: LegacyPrefixer

**`src/main/java/demo/legacy/LegacyPrefixer.java`**

```java
package demo.legacy;

import java.util.Objects;

public final class LegacyPrefixer {
    private final String prefix;

    public LegacyPrefixer(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String wrap(String input) {
        return prefix + "(" + input + ")";
    }
}
```

No stereotypes or Spring annotations.

**`src/main/resources/legacy-beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyPrefixer" class="demo.legacy.LegacyPrefixer">
        <constructor-arg value="xml"/>
    </bean>
</beans>
```

XML bean named `legacyPrefixer` with a constructor receiving the string `xml`. XML is a second definition source, not an independent ApplicationContext.

### 9.5. Programmatic Bean: AuditSink

**`src/main/java/demo/audit/AuditSink.java`**

```java
package demo.audit;

import java.util.concurrent.atomic.AtomicInteger;

public final class AuditSink {
    private final AtomicInteger records = new AtomicInteger();

    public String record(String message) {
        int number = records.incrementAndGet();
        return "AUDIT#" + number + ":" + message;
    }

    public int count() {
        return records.get();
    }
}
```

The class carries no stereotype. We do **not** write `@Bean AuditSink` in Java config and do **not** declare it in XML. The entry point will call the `registerBean` API directly before `refresh()`.

### 9.6. Component-Scanned Bean: AggregationService

**`src/main/java/demo/scanned/AggregationService.java`**

```java
package demo.scanned;

import demo.audit.AuditSink;
import demo.javaformat.Formatter;
import demo.legacy.LegacyPrefixer;

import org.springframework.stereotype.Component;

@Component
public final class AggregationService {
    private final Formatter formatter;
    private final LegacyPrefixer prefixer;
    private final AuditSink audit;

    public AggregationService(
            Formatter formatter,
            LegacyPrefixer prefixer,
            AuditSink audit) {
        this.formatter = formatter;
        this.prefixer = prefixer;
        this.audit = audit;
    }

    public String execute(String input) {
        return audit.record(
                prefixer.wrap(
                        formatter.format(input)
                )
        );
    }
}
```

It has **one constructor** requiring three dependencies. Spring Framework 6.2 can constructor-inject a single constructor even without `@Autowired`. The container will look up `Formatter`, `LegacyPrefixer`, and `AuditSink` beans after all metadata sources have been loaded.

The class is annotated with `@Component` so the scanner will pick it up, **but the scanner does not automatically create the three dependencies**. They come from three other sources.

### 9.7. Java Composition Root: Importing Java + XML + Scan

**`src/main/java/demo/config/AppConfiguration.java`**

```java
package demo.config;

import demo.scanned.AggregationService;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportResource;

@Configuration(proxyBeanMethods = false)
@Import(FormattingConfiguration.class)
@ImportResource("classpath:legacy-beans.xml")
@ComponentScan(basePackageClasses = AggregationService.class)
public class AppConfiguration {
}
```

Three annotations compose the sources:

1. `@Import(FormattingConfiguration.class)`: loads `@Bean Formatter` from the Java module.
2. `@ImportResource("classpath:legacy-beans.xml")`: loads the legacy XML bean.
3. `@ComponentScan(basePackageClasses = AggregationService.class)`: scans package `demo.scanned`, picking up `AggregationService`.

`AppConfiguration` **does not register `AuditSink`**, because the programmatic source will register it at bootstrap. Separating that makes the effect of the API clear.

### 9.8. Entry Point: A Single ApplicationContext

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.audit.AuditSink;
import demo.config.AppConfiguration;
import demo.scanned.AggregationService;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfiguration.class);
            context.registerBean(
                    "auditSink",
                    AuditSink.class,
                    AuditSink::new
            );

            context.refresh();

            System.out.println("java-bean="
                    + context.containsBean("formatter"));
            System.out.println("xml-bean="
                    + context.containsBean("legacyPrefixer"));
            System.out.println("scanned-bean="
                    + context.containsBean("aggregationService"));
            System.out.println("programmatic-bean="
                    + context.containsBean("auditSink"));

            AggregationService service =
                    context.getBean(AggregationService.class);
            System.out.println("result=" + service.execute("ok"));

            AuditSink audit = context.getBean(AuditSink.class);
            System.out.println("audit-count=" + audit.count());
            System.out.println("same-audit="
                    + (audit == context.getBean("auditSink", AuditSink.class)));
        }
    }
}
```

There is no command creating a separate `ClassPathXmlApplicationContext`. All four sources feed into `context`, which has one `refresh()` and one `close()`. `try-with-resources` ensures the context is closed after use; with real resources, Spring can invoke appropriate destruction callbacks.

### 9.9. Running and Output

From the `multi-source-context-demo` directory:

```bash
gradle run --quiet
```

If the project has Gradle Wrapper, use `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows). Running `javac App.java` alone is not enough because the application has multiple source files and needs Spring dependencies on the classpath; Gradle handles both.

**Lines printed by the program:**

```text
java-bean=true
xml-bean=true
scanned-bean=true
programmatic-bean=true
result=AUDIT#1:xml(java[ok])
audit-count=1
same-audit=true
```

Gradle or runtime logging, if present, is environment output distinct from the seven `System.out.println` lines listed above.

### 9.10. Why Is the Output Accurate?

**`java-bean=true`:** `FormattingConfiguration` is loaded via `@Import`, and its `@Bean` factory method registers the name `formatter`.

**`xml-bean=true`:** `@ImportResource` loads `legacy-beans.xml` and registers `legacyPrefixer`.

**`scanned-bean=true`:** `@ComponentScan` scans the package containing `AggregationService` and the scanner picks up the `@Component` class, whose default bean name is `aggregationService`.

**`programmatic-bean=true`:** `context.registerBean("auditSink", ...)` registers a bean definition with a supplier before refresh.

**`result=AUDIT#1:xml(java[ok])`:** `formatter.format("ok")` returns `java[ok]`; `LegacyPrefixer.wrap(...)` returns `xml(java[ok])`; `audit.record(...)` numbers the first write as 1 and returns the string above.

**`audit-count=1`:** `record` ran only once. `AuditSink` is registered as a default singleton and the service uses the exact instance created by the container.

**`same-audit=true`:** lookup by type and lookup by name within the same context return **the same singleton bean** `auditSink`.

The exercise demonstrates the independence between **how a bean is declared** and **how a consumer receives its dependencies**: `AggregationService`'s constructor does not know whether its beans came from XML, Java config, or API registration.

## 10. Understanding Container Refresh Order When Using Multiple Sources

In the demo:

```text
1. new AnnotationConfigApplicationContext()
   |
2. register(AppConfiguration.class)
   |
3. registerBean("auditSink", AuditSink.class, AuditSink::new)
   |
4. refresh()
   |
   +--> ConfigurationClassPostProcessor:
   |      @Import FormattingConfiguration
   |      @ImportResource legacy-beans.xml
   |      @ComponentScan demo.scanned
   |
   +--> bean definitions become available in registry
   +--> corresponding BeanFactoryPostProcessor / BeanPostProcessor
   +--> create non-lazy singletons & resolve dependencies
   |
5. getBean(AggregationService.class)
   |
6. close()
```

This is a **logical model**, not a guarantee of exact internal step-by-step ordering for every extension point. Some configuration processing registers definitions during the BFPP phase, and the container may have special processors that run early. The essential part is that **sources must be loaded/registered in time, before consumer beans are created**, so the BeanFactory can see the dependency candidates.

### 10.1. Registering Bean Definitions Does Not Immediately Instantiate Objects

Calling `registerBean` typically registers metadata and a supplier; calling `register` loads class metadata. On a context that has not yet called `refresh()`, many application beans have not been created yet. When `refresh()` runs, Spring prepares processors, resolves dependencies, and typically pre-instantiates non-lazy singleton beans.

That explains why you do not need to sort registration calls in “formatter first, prefixer second, service last” order in bootstrap code. Properly declared dependencies are resolved by the bean factory; avoid relying on side effects of registration order as a business contract.

### 10.2. Why Do Bean Names and Return Types Matter?

A bean definition holds name/type/factory-method metadata. When `AggregationService` requests `Formatter`, Spring needs to find a matching candidate type. For `@Bean`, the return type should be declared specifically enough for the injection points that need it.

If you write `@Bean Object formatter() { return new Formatter("java"); }`, before the instance exists Spring may only predict the bean type as `Object`, and injection by `Formatter` may fail to resolve at the required stage. Return `Formatter` or the appropriate interface that consumers actually inject.

## 11. Distinguishing Multiple Bean Definitions from Multiple Property Sources

Two kinds of “configuration sources” are often called by the same name:

**A. Bean definition sources:** XML `<bean>`, Java `@Bean`, component scanning, programmatic registration. They determine **which beans exist** and how beans are created.

**B. Property value sources:** `application.properties`, environment variables, system properties, `@PropertySource`, `Environment`, secret stores, Spring Boot config data, etc. They primarily supply **configuration values** for beans.

Example:

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:client.properties")
class ClientConfiguration {
    @Bean
    ClientOptions clientOptions(Environment environment) {
        return new ClientOptions(
                environment.getRequiredProperty("client.endpoint")
        );
    }
}
```

`ClientOptions` is a hypothetical demo class; importing `@PropertySource`, `@Bean`, `@Configuration`, `Environment`, and a `client.properties` file are required. `@PropertySource` adds a resource to `Environment`/property sources; it **does not automatically create a `ClientOptions` bean**. The `@Bean` factory method is the bean definition source, while properties are data used to construct the object.

### 11.1. One XML Resource Can Configure Both Beans and Properties

XML can use `<context:property-placeholder location="..."/>` alongside `<bean>`. Those are two cooperating mechanisms: the property resolver fills in values, while bean elements define objects. During migration, verify **post-processor registration order** and which property files are actually found on the classpath.

### 11.2. Spring Boot application.properties Is Not @ImportResource

Spring Boot automatically manages value configuration sources (`application.properties`/YAML, environment, command-line arguments, profiles, etc.) under its own rules. That does not mean Boot automatically reads every `legacy-beans.xml` file and registers all beans inside it. To import legacy XML, you still need `@ImportResource` or an equivalent XML loading mechanism.

**Remember:** “loaded a properties file” is different from “registered a bean from an XML file”.

## 12. Use @ImportResource or XmlBeanDefinitionReader?

### 12.1. @ImportResource: Simple When Java Config Is the Root

For most Java-centric applications, choose:

```java
@Configuration
@ImportResource({
    "classpath:legacy-beans.xml",
    "classpath:integration-beans.xml"
})
class AppConfiguration {}
```

This is declarative: when the configuration is processed, Spring loads the listed XML resources. It fits when the set of XML files is fixed per module/deployment.

### 12.2. XmlBeanDefinitionReader: Flexible for Dynamic Bootstrap

When you want direct control over XML sources, Spring also provides `XmlBeanDefinitionReader`, for example used with `GenericApplicationContext`:

```java
GenericApplicationContext context = new GenericApplicationContext();

XmlBeanDefinitionReader xml = new XmlBeanDefinitionReader(context);
xml.loadBeanDefinitions("classpath:legacy-beans.xml");

context.registerBean("auditSink", AuditSink.class, AuditSink::new);
context.refresh();
```

This snippet requires importing `GenericApplicationContext`, `XmlBeanDefinitionReader`, and `AuditSink`. Here you orchestrate XML and programmatic registration yourself, but if you also want to use `@Configuration` and `@ComponentScan` on the same `GenericApplicationContext`, you must additionally **register the appropriate annotation configuration infrastructure** (for example, using `AnnotationConfigApplicationContext`, or `AnnotatedBeanDefinitionReader` and `ClassPathBeanDefinitionScanner`). Therefore, do not assume that simply instantiating `GenericApplicationContext` will automatically process all `@Configuration` annotations.

### 12.3. Selection Criteria

| Need | Preferred Approach |
| --- | --- |
| App mostly uses Java configuration, with a little XML | `@ImportResource` |
| Want explicit management of configuration classes/modules | `@Import` |
| Legacy project mostly in XML | `ClassPathXmlApplicationContext` or XML-centric + annotation processors |
| Bootstrap selects XML resources at runtime | `XmlBeanDefinitionReader` with a suitable context/registry |
| Test fixture just needs one extra object | `registerBean` or a test configuration `@Bean` |
| Many stereotyped services in clear packages | `@ComponentScan` |

Do not pick a complex mechanism just because you have multiple sources; one composition root with `@Import`/`@ImportResource` and a few `@Bean` methods is usually enough.

## 13. Avoid Creating Another Context Just to Fetch a Dependency

An anti-pattern:

```java
public ReportService reportService() {
    ClassPathXmlApplicationContext legacy =
            new ClassPathXmlApplicationContext("legacy-beans.xml");
    LegacyPrefixer prefixer = legacy.getBean(LegacyPrefixer.class);
    return new ReportService(prefixer);
}
```

This is a counterexample with a hypothetical `ReportService` and missing imports. It spins up a separate XML context while creating a service:

- Singleton beans of the XML context do **not** share a cache with the Java context.
- You have to manage/close both contexts properly.
- Cross-context dependency resolution is not automatically available.
- It easily leaks resources, duplicates pools, duplicates lifecycles, and makes testing hard.
- It can accidentally create multiple instances of the same type when the author thought there was only one.

The right solution when **one context** is needed:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
class RootConfiguration {
    @Bean
    ReportService reportService(LegacyPrefixer prefixer) {
        return new ReportService(prefixer);
    }
}
```

`ReportService` is still a hypothetical type. The XML bean is loaded into the same context and supplied via parameter injection. There is no need to create a separate XML context manually.

## 14. One Context Can Still End Up with Multiple Beans of the Same Type

Combining multiple sources increases the chance of duplicate definitions. Two issues must be distinguished:

### 14.1. Duplicate Bean Names

For example, XML already defines:

```xml
<bean id="formatter" class="demo.javaformat.Formatter">
    <constructor-arg value="xml"/>
</bean>
```

while Java configuration also declares `@Bean Formatter formatter()`. Both registrations use **the same name** `formatter`. Behavior depends on overriding rules and registration order:

- Some environments reject bean definition overriding and throw an error.
- Some environments allow overriding definitions under specific rules.
- Spring Boot is generally stricter about duplicate definitions by default than some plain Spring Framework setups.

**Never rely on “whoever registers last wins” as a business contract.** Pick one owner per bean name or design intentionally distinct names.

### 14.2. Multiple Beans of the Same Type

XML declares `legacyFormatter` and Java `@Bean` declares `formatter`, both having bean class/return type `Formatter`. Now an injection point requesting a single `Formatter` encounters multiple candidates.

Valid ways to handle this:

- `@Qualifier("formatter")` at the injection point if you want the Java bean.
- `@Primary` on the default bean when there is genuinely one preferred choice.
- Capability-specific names/qualifiers (for example `publicJsonMapper` and `internalJsonMapper`).
- Inject `List<Formatter>` or `Map<String, Formatter>` when business logic intentionally needs multiple implementations.
- Load only the needed module/bean set into the context.

Do not turn every bean into `@Primary` or carelessly enable bean overriding to ignore conflicts.

## 15. Component Scan Can Accidentally Reload Java Configurations

`@Configuration` also carries `@Component` stereotype semantics. Consequently, if `@ComponentScan` scans a package containing other configurations, Spring can discover and process them automatically. When you have already `@Import`ed a configuration and the same class is also scanned, Spring generally deduplicates metadata for the same configuration class; however, broad scanning **can still load configurations/modules you did not intend to enable**.

In the demo, `@ComponentScan(basePackageClasses=AggregationService.class)` scans only `demo.scanned` instead of all of `demo`; this keeps `demo.config` out of unnecessary scan coverage.

A clean structure:

```text
demo.config   -> Java configurations / composition root
demo.scanned  -> application components of this module
demo.legacy   -> XML-managed classes
demo.audit    -> programmatically registered classes
```

Package separation here clarifies intent, but **does not automatically create isolation**: once bean definitions are loaded, they still belong to the same context.

## 16. Does Annotation Processing Still Work for XML and Programmatic Beans?

**Yes, if the context registers the corresponding annotation infrastructure.** For example, `AnnotationConfigApplicationContext` prepares the core annotation configuration processors, enabling Spring to process `@Autowired` and appropriate callbacks/infrastructure on managed beans regardless of whether their definition came from XML or `registerBean`.

An XML-declared class with an `@Autowired` field can still be injected when the instance is created by Spring and an appropriate `AutowiredAnnotationBeanPostProcessor` is active. **Component scanning is not the sole prerequisite for annotation processing.**

### Distinguish from XML-Centric Contexts

If using `ClassPathXmlApplicationContext` with plain XML and wanting `@Autowired` processing, you typically use `<context:annotation-config/>`, or `<context:component-scan/>` which includes common annotation processors. Simply reading `<bean>` definitions from XML **does not mean** all annotations are automatically enabled across every BeanFactory variant.

### And Not Every Annotation Works Automatically

`@Transactional` requires transaction management; `@Scheduled` requires scheduling infrastructure; `@RequestMapping` requires web mapping. Just because a bean is combined into a context does not mean every annotation from every stack gains behavior automatically.

## 17. Bean Names, Scope, Lifecycle, and Cross-Source Dependencies

### 17.1. Same Default Singleton Within the Same Context

If `AuditSink` is registered programmatically once as a default singleton, an XML-managed bean and another Java-managed bean injecting `AuditSink` will receive the same container-resolved bean. In the demo, `same-audit=true` illustrates identity within one context.

If you create **two** separate ApplicationContexts, each context can have its own singleton; do not expect identity across context boundaries.

### 17.2. Scope Always Matters

A bean from XML can declare `scope="prototype"`; a `@Bean` can use `@Scope("prototype")`; programmatic registration can use `BeanDefinitionCustomizer` to configure scope. When a singleton consumer injects a prototype directly, Spring typically supplies a prototype instance at the time the singleton is created; it does not fetch a fresh prototype on every method call. Use `ObjectProvider<T>`/`Provider<T>` when intentional deferred lookup is needed.

### 17.3. Lifecycle and Resources

If an XML bean or Java bean returns an HTTP client or connection pool, you must determine:

- Who owns the client/pool?
- Is the init callback invoked by the container?
- Does shutdown need `destroy-method`, `@Bean(destroyMethod=...)`, `@PreDestroy`, or another closing API?
- Could two pools be created accidentally because the same source was loaded twice or a factory method was called directly?

Centralize resources into managed bean definitions and close **the context that owns them** at the right time. For externally owned resources, do not let Spring mistakenly close a resource it does not own.

### 17.4. Circular Dependencies Across Configurations

An XML bean with a constructor `ref` to a Java bean while that Java bean constructor-injects the XML bean can create a circular dependency. Coming from two different sources **does not change Spring's cycle-handling rules**: constructor cycles are generally unresolvable and require redesigning the dependency direction.

## 18. Adding a PropertySource Without Creating Duplicate Beans

A multi-source system often has multiple properties files. For example:

**`src/main/resources/service.properties`**

```properties
service.prefix=production
```

**Java config:**

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:service.properties")
class ServiceSettingsConfiguration {
    @Bean
    String servicePrefix(Environment environment) {
        return environment.getRequiredProperty("service.prefix");
    }
}
```

This is a structural Java snippet requiring the corresponding imports. `@PropertySource` adds a **value** source to `Environment`; `@Bean String servicePrefix(...)` is what creates the bean named `servicePrefix`.

In real applications, you do not necessarily expose every configuration string as a `String` bean (which can cause injection ambiguity); typically you group properties into a strongly typed settings object or use configuration binding if the framework supports it.

### 18.1. Property Precedence Is Not Bean Override Order

Suppose both the system environment and a property file define `service.prefix`. `Environment` has a precedence order among `PropertySource`s; that is **different** from having two bean definitions named `servicePrefix`. One selects **configuration values**, while the other decides **bean registration**—they must be debugged separately.

### 18.2. @Value Placeholders Need an Appropriate Resolver

In `AnnotationConfigApplicationContext`, environment/property resolution is built in, but with some low-level containers or custom placeholder syntaxes, an appropriate processor/resolver is required. Do not expect `@PropertySource` to create a bean correctly just because the properties file was read without error.

## 19. Common Integration Mistakes

### Mistake 1 — Creating Two Independent ApplicationContexts and Assuming Shared Singleton Caches

Two contexts do not automatically share bean definitions. If you want one context, use `@ImportResource`/`@Import` or readers on the same registry. If you want a parent-child hierarchy, configure the parent explicitly and understand dependency visibility.

### Mistake 2 — Forgetting @ImportResource So the XML Resource Never Loads

A Java context does not automatically discover an XML file just because it sits in `src/main/resources`. Load it via `@ImportResource` or `XmlBeanDefinitionReader` in the right bootstrap path.

### Mistake 3 — Wrong Classpath Path

`@ImportResource("classpath:legacy-beans.xml")` requires the resource at the runtime classpath root. If the file is placed at `src/main/resources/config/legacy-beans.xml`, the path must be `classpath:config/legacy-beans.xml`. The build/test runtime classpath must contain the resource.

### Mistake 4 — Overly Broad Component Scan

`@ComponentScan("demo")` can pick up unintended modules/configurations. Use a package marker inside the target package, or explicit `@Import`, instead of scanning the entire project.

### Mistake 5 — Programmatic Bean Registration After refresh() Expecting Full Lifecycle Re-run

Many refresh and post-processing steps have already completed. At bootstrap, register before refresh; if genuine dynamic registration is needed, understand the API/lifecycle and test that case separately.

### Mistake 6 — Duplicate Bean Name from XML and @Bean

An XML bean id `formatter` collides with `@Bean formatter()`. Depending on overriding policy and processing timing, this may error or replace a bean definition. Use a single owner or intentionally distinct names.

### Mistake 7 — Multiple Candidates of the Same Type Causing Injection Ambiguity

Two `Formatter` beans from XML and Java while a constructor expects one `Formatter`. Use `@Qualifier`, `@Primary`, collections, or reorganize modules. Do not assume Java sources always take priority over XML.

### Mistake 8 — XML-Declared Bean Has @Autowired Without Processor Enabled

In an XML-centric context lacking `<context:annotation-config/>` or equivalent infrastructure, field/method annotations may do nothing. Check the ApplicationContext type and registered processors rather than blindly widening component scanning.

### Mistake 9 — Loading XML Requiring a Namespace Without the Dependency

An XML file using namespaces for transactions, AOP, JMS, or Spring Security may need the corresponding module/schema/namespace handler on the classpath. The XML in the demo uses only the Spring beans namespace, so those extra modules are not needed.

### Mistake 10 — Mixing XML and Java Config While Calling new on Configurations

Calling `new ConfigurationClass()` manually or invoking a `@Bean` method from an unmanaged object can produce objects outside the container. Pass dependencies via constructor/factory method parameters; let BeanFactory manage source-derived instances.

### Mistake 11 — Hiding the Type Behind @Bean Object

Spring cannot always predict the concrete type before the factory method runs. This can cause missing candidates or prevent infrastructure processors from being detected early. Return types should be specific enough, especially for `BeanFactoryPostProcessor`/`BeanPostProcessor`.

### Mistake 12 — Java Compiles, but XML Constructor Does Not Match

For example, XML `<constructor-arg value="abc"/>` when a vendor class has no matching constructor. The error only surfaces while reading/creating the bean. When integrating XML, check constructor signatures, package names, and type conversions.

### Mistake 13 — Confusing @Import with @ImportResource

`@Import` takes configuration/component/selector/registrar class types. `@ImportResource` takes XML resource locations (or sources supported by an appropriate reader). Do not pass `"classpath:legacy-beans.xml"` to `@Import` or a configuration class to `@ImportResource`.

### Mistake 14 — Inferring Initialization Order from Import Order

Do not assume XML loaded first creates singletons before Java beans or vice versa. The dependency graph, scopes, lazy-init, BFPP/BPP, and early bean creation affect timing. If an initialization ordering constraint is genuinely needed, `@DependsOn` or bean-definition `depends-on` can be used, though expressing real dependencies is best.

### Mistake 15 — Beans Are in Context, but Specialized Stacks Are Not Active

Having a controller bean does not mean an HTTP server/mapping is running; having a repository bean does not mean transactions are enabled. Combining bean definitions only solves **basic registry/DI/lifecycle**, not bootstrapping every other framework infrastructure automatically.

## 20. Verifying a Context After Composing All Sources

### 20.1. Checking by Bean Name

```java
context.containsBean("formatter");
context.containsBean("legacyPrefixer");
context.containsBean("aggregationService");
context.containsBean("auditSink");
```

Place these in `main` after `refresh()` as in the demo. These lookups verify **bean name presence**. They do not prove dependencies were wired properly unless actual behavior is exercised.

### 20.2. Checking by Bean Type

```java
Formatter formatter = context.getBean(Formatter.class);
LegacyPrefixer legacy = context.getBean(LegacyPrefixer.class);
AuditSink audit = context.getBean(AuditSink.class);
AggregationService service = context.getBean(AggregationService.class);
```

This snippet uses the demo's classes and context. If a type has multiple candidates, `getBean(Type.class)` can fail; in that case use name + type or qualifiers at injection points.

### 20.3. Inspecting Bean Definitions and Declaration Sources

```java
var factory = context.getBeanFactory();

var javaDefinition = factory.getBeanDefinition("formatter");
var xmlDefinition = factory.getBeanDefinition("legacyPrefixer");
var scanDefinition = factory.getBeanDefinition("aggregationService");
var apiDefinition = factory.getBeanDefinition("auditSink");

System.out.println(javaDefinition.getFactoryMethodName());
System.out.println(xmlDefinition.getBeanClassName());
System.out.println(scanDefinition.getBeanClassName());
System.out.println(apiDefinition.getBeanClassName());
```

This is an observation snippet, not fixed stdout across all environments. A bean definition may describe a factory method or a class name; some fields may be `null` depending on the registration mechanism. Here, `formatter` comes from `@Bean` (factory method), the XML bean specifies a class, the scanner knows the class, and programmatic registration knows the class/supplier. `BeanDefinition.getResourceDescription()` can provide the resource origin to aid investigation.

### 20.4. Investigating Missing Beans Methodically

When `UnsatisfiedDependencyException` occurs, check:

1. Was the class/bean definition actually loaded from **the expected source**?
2. Was the XML resource found, and are its format/schema valid?
3. Does component scan cover the right package? Is it excluded?
4. Did programmatic registration happen before refresh?
5. Were bean candidates filtered out by `@Profile`/`@Conditional`?
6. Are there multiple candidates of the same type or duplicate bean names?
7. Did bean construction fail because of another dependency rather than a missing scan?

This approach is faster than sprinkling `@ComponentScan` or `@Autowired` onto arbitrary classes.

## 21. Multi-Source Architecture in Real Projects

### 21.1. XML → Java Migration Phase

A safe roadmap:

1. Pick **one context as the composition root** and clarify who owns bootstrap.
2. Keep legacy XML in one or a few `@ImportResource` references.
3. Add new beans in Java configuration, using `@Import` to group them.
4. Use tightly scoped component scanning for new stereotyped code.
5. Avoid creating a separate context just to grab a single bean.
6. Use integration tests to verify bean names, types, qualifiers, and cross-source behavior.
7. Migrate groups of XML beans to `@Bean` when beneficial, without needing to move everything at once.
8. After migrating each group, remove the old definition to prevent duplicate registrations.
9. Verify lifecycle and shutdown behavior for long-lived resources.

This is a configuration-level “strangler migration”: gradually shifting bean ownership while keeping the application runnable.

### 21.2. Splitting by Module While Sharing One Context

```text
bootstrap/
    AppConfiguration.java
    App.java

pricing/
    PricingConfiguration.java
    DiscountService.java

legacy/
    legacy-beans.xml

integration/
    HttpClientConfiguration.java

scanned/
    EventHandler.java
```

The composition root decides **which configurations to load**, while each module owns its bean definitions. Even though configurations come from different source files, they can contribute to **one** context when deployment requires it.

### 21.3. Should You Ever Use Multiple ApplicationContexts?

**Yes**, when you genuinely need a parent-child hierarchy, a child web context, isolation, or different lifecycles. But that is a separate architectural decision, not a requirement for using XML and Java together.

In a typical hierarchy, **child** can look up beans in **parent**, whereas parent cannot see beans existing only in child. A duplicate bean name in child can shadow the same-named bean in parent per lookup rules. Scopes/lifecycles are not automatically merged into one unified bean factory either. Thus, if the requirement is “multiple sources in **one** context”, prefer composing into a single registry instead of opening extra containers.

## 22. Practice Exercises

### Exercise 1 — Moving an XML Bean to Java @Bean

In the demo, try moving `LegacyPrefixer` from XML to:

```java
@Bean
LegacyPrefixer legacyPrefixer() {
    return new LegacyPrefixer("java-config");
}
```

Put the method into Java configuration and **remove `@ImportResource` or the old XML definition** before running to avoid two sources declaring the bean name `legacyPrefixer`. Predict the output after the change: the middle portion of the string will be `java-config(java[ok])` instead of `xml(java[ok])`. No change to `AggregationService`'s constructor is needed.

### Exercise 2 — Adding an XML Bean of the Same Formatter Type

Add an XML bean `Formatter` named `legacyFormatter`. Then predict the outcome of autowiring `AggregationService(Formatter ...)`.

Answer: **multiple `Formatter` candidates** may appear; to keep intent clear, use `@Qualifier("formatter")` or distinguish them with markers/primary according to the use case. Never assume the Java bean takes precedence just because it did not come from XML.

### Exercise 3 — Changing the Programmatic Bean to @Bean

Move `AuditSink` into Java config:

```java
@Bean
AuditSink auditSink() {
    return new AuditSink();
}
```

After removing the `context.registerBean("auditSink", ...)` line at bootstrap, the program can still print the same values as before if the other dependencies remain unchanged. This proves consumers do not need to know the registration source.

### Exercise 4 — Removing Component Scan and Using registerBean(Class)

Replace scanning for `AggregationService` with:

```java
context.registerBean(AggregationService.class);
```

This call must be placed **before `refresh()`**, after removing the corresponding `@ComponentScan`. For a class with one public constructor and all required dependency beans present, Spring can instantiate the service via constructor injection. The bean name generated may differ if different APIs/metadata are used; tests should look up by type, or pass the explicit name `"aggregationService"`.

### Exercise 5 — Distinguishing Property Sources from Bean Sources

Create `settings.properties` containing `app.prefix=config-value`, then use `@PropertySource` to supply the value to a `@Bean` factory method. Verify that:

- The property is read via `Environment`.
- The property does not automatically create a bean of your target class.
- The new bean only appears when a registration source (`@Bean`, XML, scan, or API) exists.

## 23. Review Questions and Answers

**Q1.** Can one `AnnotationConfigApplicationContext` simultaneously hold beans from XML, Java `@Bean`, and component scan?

**A:** Yes. You can use `@ImportResource` to import XML, `@Import`/`register` for Java configuration, and `@ComponentScan` to discover components—all within one context.

**Q2.** Does `@ImportResource` create an additional independent `ClassPathXmlApplicationContext`?

**A:** No. It imports bean definitions from XML into the Java context being configured.

**Q3.** Is `@ComponentScan` required in order for an XML bean to be injected into a scanned component?

**A:** Scanning is needed only if you choose to discover the consumer component via the scanner; the XML bean is still registered independently. Once the consumer is in the context, injection by type operates over the shared set of bean candidates.

**Q4.** Why must `registerBean` calls finish before `refresh()` during bootstrap?

**A:** So processors and beans instantiated during refresh see the registration right from the start, avoiding adding beans after the startup lifecycle has already run.

**Q5.** There are two beans of type `Formatter` with different names. What can happen when injecting a single `Formatter`?

**A:** Without a way to select a unique candidate (qualifier/primary/matching name), Spring may throw `NoUniqueBeanDefinitionException`.

**Q6.** Does `application.properties` automatically declare a Spring bean `Formatter`?

**A:** No. It typically supplies configuration values, not bean definitions; a matching factory/configuration/registration is needed to produce a bean object.

**Q7.** If two ApplicationContexts both load the same XML file, do they share that file's singletons?

**A:** Not automatically. Each context has its own bean factory and singleton registry.

**Q8.** In the demo, which source did each of the four beans come from?

**A:** `Formatter` from Java `@Bean`, `LegacyPrefixer` from XML, `AggregationService` from component scan, and `AuditSink` from programmatic registration.

**Q9.** Does Spring resolve constructor injection based on the bean definition source or on matching candidates?

**A:** Based on dependency metadata, type, qualifier, scope, and resolution rules; consumers generally do not need to know whether a source bean came from XML or Java.

**Q10.** When migrating an XML bean to Java, what is the first critical concern?

**A:** Ensuring **one clear registration owner**, avoiding unintentional duplicate registrations of the same name/type, and verifying behavior, scope, and lifecycle after migration.

## 24. Implementation Checklist

Before combining multiple configuration sources, confirm:

1. **There is only one ApplicationContext if the goal is a shared registry.**
2. Every source is loaded/registered properly: `@Import`, `@ImportResource`, `@ComponentScan`, `registerBean`/`register`.
3. XML resources exist at the right classpath path and their namespaces are supported by libraries.
4. Component scanning is scoped by package/filters and does not pull in unintended modules.
5. Java `@Bean` methods declare clear return types; dependencies are expressed via factory method parameters where appropriate.
6. Programmatic registrations finish before `refresh()` during bootstrap.
7. Bean names do not collide unexpectedly; injected types have either a single unique candidate or explicit qualifiers.
8. Scope, lazy-init, callbacks, and resource ownership are verified in the shared container.
9. Annotation processors/stack-specific infrastructure are enabled when needed, never assumed merely because a bean exists.
10. Test with the same context: expected beans exist by name/type, cross-source behavior executes for real, and resources close cleanly.
11. If using parent-child contexts, document visibility/lifecycle separately; do not treat them as one context.
12. Property sources and bean definition sources are kept distinct in documentation and diagnostic logs.

## 25. Official References

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, cross-configuration bean dependencies, and `@ImportResource`.
- [Spring Framework 6.2 — Instantiating the Spring Container with AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/instantiating-container.html): `register`, `scan`, `refresh`.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): stereotypes, base packages, filters.
- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): annotation processors when mixing with XML.
- [Spring Framework 6.2 — Bean Definitions and XML Imports](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): XML `<bean>`, `<import/>`, and bean metadata.
- [Spring Framework 6.2 — GenericApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html): `registerBean` overloads.
- [Spring Framework 6.2 — ImportResource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportResource.html): importing bean definitions from resources.
- [Spring Framework 6.2 — PropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/PropertySource.html): distinguishing property metadata from bean registration.

**Remember:** Java configuration, XML, component scan, and programmatic APIs can all contribute bean definitions into **one Spring ApplicationContext**. The container resolves dependencies among them using the same IoC, scope, and lifecycle mechanisms. **One context with multiple sources is not the same as multiple contexts**, and a `@PropertySource` value source is not a bean definition source. Clear registration ownership and checking for name/type collisions are the keys to safe composition.
