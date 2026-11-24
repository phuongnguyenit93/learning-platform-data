# Importing XML Configuration with @ImportResource in Spring Core Container

## Objectives

Spring Framework allows applications to declare beans via **Java configuration** (`@Configuration` and `@Bean`), **component scanning** (`@Component` and stereotypes), or **XML configuration** (`<beans>`, `<bean>`, `<property>`, `<constructor-arg>`). In a long-lived project, migrating all XML configuration to Java in one shot may be unnecessary or too risky. Part of the legacy configuration remains valuable, especially when dealing with XML namespaces or already-stable integrations.

The **`@ImportResource`** annotation in Spring Core Container solves the problem of **using Java configuration as the primary entry point while importing additional bean definitions from XML resources**:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
    // Additional @Bean methods can be declared here.
}
```

Once Spring loads `AppConfig` into `AnnotationConfigApplicationContext`, the bean definitions in `legacy-beans.xml` are placed into **the same BeanFactory/ApplicationContext** as beans declared with `@Bean`. Because they share one container, they can reference and be injected into one another through Spring's dependency injection mechanism.

After this lesson, you will:

1. Understand what `@ImportResource` does, at which phase it runs, and how it differs from `@Import`.
2. Declare `classpath:`, `file:`, and multi-resource XML locations properly.
3. Write valid XML with `<beans>`, `<bean>`, `<property>`, `<constructor-arg>`, and `<alias>`.
4. Inject an XML bean into a Java `@Bean` parameter and reference **back** from XML to a Java bean.
5. Use the XML `context:property-placeholder` namespace with Java `@Value` when needed.
6. Distinguish bean names, aliases, independent bean counts, scopes, and lifecycles when combining both configuration sources.
7. Diagnose missing XML files, wrong namespaces/schemas, missing beans, or duplicate registrations.
8. Migrate gradually from XML to Java configuration while preserving bean-name contracts and compatibility tests.

**Core idea:** `@ImportResource` **imports bean definitions**; it does not copy objects, does not create a second container, and does not automatically convert XML syntax into `@Bean` methods in source code.

## 1. Context: Why Import XML from Java Configuration?

Suppose a system already has this resource:

```xml
<!-- src/main/resources/legacy-beans.xml -->
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="legacyClient" class="com.example.legacy.LegacyClient"/>
</beans>
```

This is an **illustrative** example: `com.example.legacy.LegacyClient` must actually exist on the classpath to be used.

At the same time, the newer application mostly uses:

```java
@Configuration(proxyBeanMethods = false)
class BillingConfig {
    @Bean
    BillingService billingService(LegacyClient legacyClient) {
        return new BillingService(legacyClient);
    }
}
```

If only `BillingConfig` is registered without loading XML, Spring does not know where the `legacyClient` bean comes from. This can be solved by importing XML:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class BillingConfig {
    @Bean
    BillingService billingService(LegacyClient legacyClient) {
        return new BillingService(legacyClient);
    }
}
```

Here `@ImportResource` keeps the legacy XML configuration intact while the new service continues using **dependency injection via `@Bean` method parameters**. There is no need to instantiate `LegacyClient` a second time in Java just because it comes from XML.

### One BeanFactory, Multiple Metadata Sources

```text
             AnnotationConfigApplicationContext
                          |
                Register AppConfig
                          |
           +--------------+--------------+
           |                             |
    Java @Bean methods          @ImportResource(...)
           |                             |
    BeanDefinition A              Read legacy-beans.xml
    BeanDefinition B                       |
           |                        BeanDefinition C
           |                        BeanDefinition D
           +--------------+--------------+
                          |
                        BeanFactory
                          |
             Dependency resolution
               by type / name / qualifier
                          |
                    Managed beans
```

Each bean definition is ultimately processed by Spring according to scope, lifecycle, autowiring, post-processors, factory methods, metadata, and relevant conditions. **The declaration source**—Java or XML—does not change whether that bean is a singleton, injected, proxied, or cleaned up like a normal bean.

## 2. Where Does @ImportResource Sit and What Attributes Does It Have?

The `@ImportResource` annotation belongs to:

```java
import org.springframework.context.annotation.ImportResource;
```

It is a **TYPE**-level annotation — typically placed on a `@Configuration` class:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
}
```

Main meaning of its attributes:

| Attribute | Purpose | Example |
| --- | --- | --- |
| `value` | List of resource locations to import; alias for `locations` | `@ImportResource("classpath:legacy.xml")` |
| `locations` | Explicit attribute name for resource locations | `@ImportResource(locations = {"classpath:a.xml", "classpath:b.xml"})` |
| `reader` | Select a specialized `BeanDefinitionReader` implementation when needed | `@ImportResource(reader = XmlBeanDefinitionReader.class, locations = "classpath:legacy.xml")` |

For standard XML, **you do not need to specify `reader`**: Spring uses `XmlBeanDefinitionReader` by default for XML. According to the 6.2 API, resources ending in `.groovy` are handled by the corresponding Groovy reader when that infrastructure is present; that is a capability of the annotation, not a requirement that every Spring app configure Groovy.

`value` and `locations` are **two alternate names for the same resource list**, not two independent import lists that get combined. Pick **one style** to avoid confusion.

### Importing One XML File

```java
@ImportResource("classpath:legacy-beans.xml")
```

### Importing Multiple XML Files

```java
@ImportResource(locations = {
    "classpath:legacy/repositories.xml",
    "classpath:legacy/integrations.xml"
})
```

Each file is read and contributes bean definitions into the same container. **It does not create two contexts** just because there are two files.

### Is @Configuration Required?

The annotation is primarily designed to pair with a configuration class processed by Spring. The most readable and verifiable pattern is:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class RootConfig {
}
```

Register `RootConfig.class` with `AnnotationConfigApplicationContext` or import it from another configuration class. Manually calling `new RootConfig()` inside a Java method **does not trigger** Spring's XML import; the annotation must be recognized by Spring's configuration processing.

## 3. How @ImportResource Differs from @Import, <import/>, and ClassPathXmlApplicationContext

Although all of them contain *import* in their name, their roles are very different.

| Mechanism | What Argument Does It Take? | Role |
| --- | --- | --- |
| `@Import(OtherConfig.class)` | Class/configuration/component/selector per annotation contract | Imports Java configurations or related Spring components |
| `@ImportResource("classpath:legacy.xml")` | Resource location string | Imports bean definitions from XML or reader-supported formats |
| XML `<import resource="other.xml"/>` | Resource path inside XML | XML imports another XML configuration file |
| `ClassPathXmlApplicationContext("legacy.xml")` | XML resource name | Creates a context in an XML-centric style |
| `@ComponentScan(basePackages = "...")` | Package names/marker classes | Scans classes annotated with stereotypes |

Example combining another Java config and XML:

```java
@Configuration(proxyBeanMethods = false)
@Import(RepositoryJavaConfig.class)
@ImportResource("classpath:legacy-integration.xml")
class ApplicationConfig {
}
```

This is an **illustrative snippet**; `RepositoryJavaConfig` must be a valid class in the project. `@Import` does not replace `@ImportResource` when the argument is an XML file. Conversely, `@ImportResource` does not scan Java packages for `@Service` classes.

### Two Directions for Combining Java and XML

Spring supports both organizational styles:

- **Java-centric:** Start with `AnnotationConfigApplicationContext(AppConfig.class)` and use `@ImportResource` to load the XML files to keep.
- **XML-centric:** Start with `ClassPathXmlApplicationContext`, and have XML declare/import appropriate `@Configuration` classes and enable annotation processing infrastructure when needed.

This lesson focuses on **Java-centric**, matching the goal “Importing XML configuration with `@ImportResource`”. There is no need to manually create both kinds of contexts for one simple application and pass objects between them.

## 4. Resource Locations: classpath:, file:, and Multiple Files

Because `@ImportResource` expects **resource locations**, the path must match where the XML is actually packaged/run.

### 4.1. classpath: Is the Usual Choice

With a Maven layout:

```text
my-app/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/AppConfig.java
        └── resources/
            ├── legacy-beans.xml
            └── legacy/
                └── adapters.xml
```

Maven places resources in `src/main/resources` onto the runtime classpath. Therefore:

```java
@ImportResource("classpath:legacy-beans.xml")
```

finds the file at the classpath root, while:

```java
@ImportResource("classpath:legacy/adapters.xml")
```

finds the file in the `legacy` directory inside the classpath.

**Common mistake:** Writing `@ImportResource("src/main/resources/legacy-beans.xml")` and assuming it always works when packaged as a JAR. A source-tree path is not a stable runtime resource location.

`classpath:/legacy-beans.xml` is also commonly written to emphasize the classpath root. When the app is packaged, Spring looks on the classpath, regardless of which directory the IDE happens to open.

### 4.2. file: Points to the Filesystem

```java
@ImportResource("file:/opt/myapp/config/legacy-beans.xml")
```

`file:` uses a path outside the JAR, useful for deployment-managed configuration. Make sure:

- The file exists where **the runtime machine/container** can read it.
- The path matches the operating system and volume mounts.
- Permissions, versioning, integrity, and rollout strategy are controlled.
- You do not embed secrets or depend on external files without clear security, configuration, and failure policies.

This snippet is illustrative; `/opt/myapp/config/legacy-beans.xml` is not part of the runnable project in section 7.

### 4.3. classpath*: and Resource Patterns

Spring has a `ResourcePatternResolver` mechanism supporting patterns like `classpath*:` in some contexts. When using resource patterns, understand that match counts can differ between an IDE, a JAR, and multiple dependencies containing same-named resources.

Illustrative example:

```java
@ImportResource("classpath*:META-INF/spring/legacy-context.xml")
```

This can match multiple resources across the classpath via the pattern resolver. **Do not** use a broad wildcard just to be sure “XML will be found”: importing multiple unintended XML copies can cause duplicate bean definitions or instantiate disallowed components. For a single explicit file, `classpath:legacy-beans.xml` is usually simpler and safer.

### 4.4. What Happens When a Resource Is Not Found?

If the location does not exist or cannot be read, XML parsing/registration throws an exception and the context fails to start. `@ImportResource` **does not mean** the XML is optional. Never assume a missing file will be silently skipped like an optional dependency.

Do not swallow all startup errors and let the application continue in an under-configured state; fix the file path and packaging instead.

## 5. Basic XML Declarations for Importing

Modern Spring XML typically starts with namespaces and schema declarations as follows:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyFormatter"
          class="com.example.legacy.LegacyFormatter">
        <property name="prefix" value="LEGACY:"/>
    </bean>
</beans>
```

This is an **illustrative** example: `com.example.legacy.LegacyFormatter` must have the corresponding constructor/property setter. For an XML-defined bean:

- `id` is typically the primary bean name.
- `class` is the **fully qualified Java class name** that the classloader must find.
- `<property name="prefix" value="..."/>` sets a property via the matching setter/JavaBean property.
- `<constructor-arg>` passes constructor arguments.
- `ref="otherBean"` references a bean definition with that name in **the same container**, even if that other bean was declared in Java.
- XML can declare `scope`, `init-method`, and `destroy-method` for the desired lifecycle.

A normal XML bean does not also need `@Component` on the Java class; once declared with `<bean>`, Spring has the bean definition from XML.

### Using constructor-arg Instead of property

```xml
<bean id="legacyProcessor"
      class="com.example.legacy.LegacyProcessor">
    <constructor-arg ref="legacyFormatter"/>
</bean>
```

This is also an illustrative snippet requiring `LegacyProcessor` to have a matching constructor. Choose constructor injection when a dependency is required; property injection is useful for older JavaBean libraries with setters, not something to pick merely because XML looks shorter.

### Aliases in XML

```xml
<alias name="legacyFormatter" alias="oldFormatter"/>
```

The `oldFormatter` alias points to **the same bean definition** as `legacyFormatter`. It **does not create** a new `LegacyFormatter` bean. With default singleton scope, looking up either name returns the same reference. Do not confuse an alias with two `<bean>` elements having different `id`s, which create two independent definitions.

## 6. How Do XML and Java Beans Interact Bidirectionally?

When importing XML into the same `AnnotationConfigApplicationContext`, dependency resolution is not split into a “Java zone” and an “XML zone”.

### 6.1. Java @Bean Receiving a Dependency Declared in XML

XML example:

```xml
<bean id="legacyGateway"
      class="com.example.gateway.LegacyGateway"/>
```

And Java config:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-gateway.xml")
class PaymentConfig {

    @Bean
    PaymentService paymentService(LegacyGateway legacyGateway) {
        return new PaymentService(legacyGateway);
    }
}
```

This is an illustration requiring real classes and files. Spring finds the `LegacyGateway` bean in the BeanFactory and passes it into the `paymentService` factory method. No `new LegacyGateway()` is needed in Java config.

If there are multiple `LegacyGateway` beans of the same type, the dependency can be ambiguous; choose via `@Qualifier`/`@Primary` or a clear interface hierarchy. XML beans can use `primary="true"` or `autowire-candidate` in corresponding scenarios.

### 6.2. XML ref Pointing to a Bean Declared in Java

Java config:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-dashboard.xml")
class AppConfig {

    @Bean("reportService")
    ReportService reportService() {
        return new ReportService();
    }
}
```

XML:

```xml
<bean id="legacyDashboard"
      class="com.example.legacy.LegacyDashboard">
    <property name="reportService" ref="reportService"/>
</bean>
```

Spring resolves `ref="reportService"` within the same BeanFactory. The condition is that the `reportService` bean exists and is compatible with the `setReportService(...)` property setter. Although Java config imports the XML via `@ImportResource`, bean definitions are processed together while building the context; XML does not have to appear after the Java bean in source order to be resolved.

**Remember:** `ref` references **a bean name**, unlike `value` which passes a string literal. Do not write `value="reportService"` when the property expects a `ReportService` instance.

### 6.3. Declaring Dependencies by Type or by Name?

- In Java, a factory method parameter like `ReportService service` expresses a dependency by **type**, optionally combined with a qualifier.
- In XML, `ref="reportService"` expresses a dependency by **bean name**.
- The same bean can be retrieved by both type and name, provided candidate selection is unambiguous.
- An alias in XML can supply a name compatible with old code while pointing to the same bean.

This is one reason to keep **bean names stable** when migrating XML configuration to Java: legacy XML consumers often reference explicit names.

## 7. Runnable Java 17 Project: XML ↔ Java in One ApplicationContext

This example can be run with **JDK 17+, Maven, and Spring Framework 6.2**. It uses no database, network, or Spring Boot.

We will create:

1. Beans `xmlStore` and `formatter` in XML.
2. XML alias `legacyStore` pointing to `xmlStore`.
3. Bean `messageService` via `@Bean`, receiving `MessageStore` and `PrefixFormatter` from XML.
4. Bean `xmlDashboard` in XML, whose `messageService` property references back to the Java-created bean.
5. ApplicationContext created **only once** via `AnnotationConfigApplicationContext`.

### 7.1. Directory Structure

```text
import-resource-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ImportResourceDemo.java
        └── resources/
            └── legacy-beans.xml
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>import-resource-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

### 7.3. Full Java Code

Create `src/main/java/demo/ImportResourceDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

public class ImportResourceDemo {

    public interface MessageStore {
        String persist(String formatted);
    }

    // Public and static class so Spring XML instantiation does
    // not need an instance of outer class ImportResourceDemo.
    public static class XmlMessageStore implements MessageStore {

        public XmlMessageStore() {
        }

        @Override
        public String persist(String formatted) {
            return "stored[" + formatted + "]";
        }
    }

    public static class PrefixFormatter {
        private String prefix;

        public PrefixFormatter() {
        }

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }

        public String format(String message) {
            return prefix + message;
        }
    }

    public static class MessageService {
        private final MessageStore store;
        private final PrefixFormatter formatter;

        public MessageService(MessageStore store,
                              PrefixFormatter formatter) {
            this.store = store;
            this.formatter = formatter;
        }

        public String submit(String message) {
            return store.persist(formatter.format(message));
        }
    }

    public static class XmlDashboard {
        private MessageService messageService;

        public XmlDashboard() {
        }

        public void setMessageService(MessageService service) {
            this.messageService = service;
        }

        public String status() {
            return "xml->java:" + messageService.submit("dashboard");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ImportResource("classpath:legacy-beans.xml")
    public static class AppConfig {

        @Bean
        public MessageService messageService(
                @Qualifier("xmlStore") MessageStore store,
                PrefixFormatter formatter) {
            return new MessageService(store, formatter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("xmlBean=" +
                    context.containsBean("xmlStore"));
            System.out.println("javaBean=" +
                    context.containsBean("messageService"));
            System.out.println("aliasSame=" +
                    (context.getBean("xmlStore") ==
                     context.getBean("legacyStore")));

            MessageService service =
                    context.getBean(MessageService.class);
            XmlDashboard dashboard =
                    context.getBean(XmlDashboard.class);

            System.out.println("service=" +
                    service.submit("order-42"));
            System.out.println("dashboard=" +
                    dashboard.status());
            System.out.println("storeBeanCount=" +
                    context.getBeanNamesForType(MessageStore.class).length);
        }
    }
}
```

Brief explanation of the Java file:

- `XmlMessageStore` and `PrefixFormatter` are **public static nested classes**. In Spring XML, their binary class names contain a `$` character. Making them `public static` avoids needing an outer instance when XML instantiates the object.
- `@ImportResource` is placed on `AppConfig`. `AnnotationConfigApplicationContext` loads this class and processes the XML from there.
- `messageService(...)` receives two dependencies **supplied by Spring**; `@Qualifier("xmlStore")` explicitly identifies which XML bean to retrieve.
- `proxyBeanMethods=false` is completely suitable because the `@Bean` method does not call another `@Bean` method directly.
- `XmlDashboard` has a setter because the example intentionally demonstrates **property injection from XML to a Java bean**; in new business code, constructor injection is usually better for required dependencies.

### 7.4. XML Declaring Two Beans and Referencing Back to Java

Create `src/main/resources/legacy-beans.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- XML-defined bean, injected by Java @Bean via type + qualifier. -->
    <bean id="xmlStore"
          class="demo.ImportResourceDemo$XmlMessageStore"/>

    <!-- Compatibility alias for the same bean. -->
    <alias name="xmlStore" alias="legacyStore"/>

    <!-- Setter property injection into an XML-defined bean. -->
    <bean id="formatter"
          class="demo.ImportResourceDemo$PrefixFormatter">
        <property name="prefix" value="XML:"/>
    </bean>

    <!-- XML-defined bean referencing back to Java @Bean messageService. -->
    <bean id="xmlDashboard"
          class="demo.ImportResourceDemo$XmlDashboard">
        <property name="messageService" ref="messageService"/>
    </bean>

</beans>
```

**Important when copying the code:**

- The XML class name uses `demo.ImportResourceDemo$XmlMessageStore` rather than `demo.ImportResourceDemo.XmlMessageStore`. The `$` is how the JVM identifies nested classes in binary class names.
- The XML is saved at **`src/main/resources/legacy-beans.xml`**, matching `classpath:legacy-beans.xml` directly.
- `<property name="prefix" value="XML:"/>` passes a **string** to the `setPrefix` setter.
- `<property name="messageService" ref="messageService"/>` tells Spring to look up **the Java bean named `messageService`**, not the string “messageService”.
- `legacyStore` is an alias for `xmlStore`. Both names are accepted when looking up the singleton bean.

### 7.5. Run Command

From the project directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImportResourceDemo
```

Requires JDK 17+ and Maven. Lines **printed by the program itself** (excluding Maven or Spring log messages):

```text
xmlBean=true
javaBean=true
aliasSame=true
service=stored[XML:order-42]
dashboard=xml->java:stored[XML:dashboard]
storeBeanCount=1
```

### 7.6. Why Is the Output Correct?

**`xmlBean=true`:** `xmlStore` is read by Spring from `legacy-beans.xml` while processing `@ImportResource`. It is a bean definition in the same context.

**`javaBean=true`:** `messageService` is contributed by Java `@Bean MessageService messageService(...)`; the default name is the method name.

**`aliasSame=true`:** XML `<alias name="xmlStore" alias="legacyStore"/>` adds an **alternate name** for the same singleton. Both `getBean` calls return the same reference.

**`service=stored[XML:order-42]`:** Java bean `MessageService` receives `PrefixFormatter` with prefix `XML:` from XML property injection. The service formats `order-42` into `XML:order-42` and calls the store bean, returning `stored[XML:order-42]`.

**`dashboard=xml->java:stored[XML:dashboard]`:** Bean `xmlDashboard` is defined in XML, yet its `messageService` property references the Java bean. `status()` calls the injected service to produce the string prefixed with `xml->java:`.

**`storeBeanCount=1`:** `getBeanNamesForType(MessageStore.class)` returns the list of **actual bean definitions** matching the type. The `legacyStore` alias is not a second `MessageStore` bean. Nor is another `new XmlMessageStore()` declared in Java.

### 7.7. Changes You Can Try Yourself

1. **Rename the alias** `legacyStore` to `oldStore` in XML, update `getBean("oldStore")`, and run. The primary name `xmlStore` stays unchanged.
2. **Change the prefix** from `XML:` to `LEGACY:` in XML. Both `service` and `dashboard` lines change accordingly without touching the Java factory method.
3. **Remove `@ImportResource`** from `AppConfig`. The context will fail to find the XML dependencies needed by `messageService`, so bean creation will fail instead of printing the output above.
4. **Change XML `ref="messageService"` to `ref="unknownService"`**. Spring has no bean with that name and reports a resolution error. This illustrates why bean names are a contract between Java and XML.
5. **Add a second XML bean implementing `MessageStore`**. The `MessageStore` parameter has `@Qualifier("xmlStore")` so it still selects the right bean; if you remove the qualifier with no winning candidate, Spring throws `NoUniqueBeanDefinitionException`.

## 8. Configuring Placeholders from XML and @Value in Java

An application can keep property placeholder configuration in XML while consuming those values in Java `@Configuration`. This is a case Spring's official documentation uses to illustrate `@ImportResource`.

Example `properties-config.xml` resource:

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

    <context:property-placeholder
            location="classpath:application-legacy.properties"/>
</beans>
```

File `src/main/resources/application-legacy.properties`:

```properties
app.label=legacy-enabled
app.retryLimit=3
```

Java config:

```java
// Illustrative snippet: CustomClient is an application class.
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:properties-config.xml")
class PropertyConfig {

    @Bean
    CustomClient customClient(
            @Value("${app.label}") String label,
            @Value("${app.retryLimit}") int retryLimit) {
        return new CustomClient(label, retryLimit);
    }
}
```

You need to import `org.springframework.beans.factory.annotation.Value` and the `Configuration`, `ImportResource`, and `Bean` annotations. This is an **illustrative extension snippet**, not part of the standalone runnable program in section 7. After importing the XML, `<context:property-placeholder>` registers the appropriate property placeholder resolution infrastructure for `@Value` to read values.

**Points to note:**

- `${app.label}` is Spring's placeholder syntax, **not** Java variable interpolation syntax.
- Spring reads the file from the runtime classpath. If the file is missing, a placeholder is unresolved, or a type cannot be converted, configuration may fail depending on the context and placeholder resolution policy.
- `retryLimit` in Java has type `int`; Spring converts the property string `3` to a number when the appropriate conversion mechanism is present.
- If the application already has a `PropertySourcesPlaceholderConfigurer` or another property resolver, avoid accidentally registering multiple processors with conflicting policies.
- In plain Spring Framework, you can also declare property sources purely in Java without keeping XML if only a simple properties file remains.

### Can @PropertySource Replace @ImportResource?

`@PropertySource("classpath:application.properties")` adds a property source to Spring's `Environment`; it **does not** read `<bean>` definitions from XML. If your sole goal is reading key-value pairs, `@PropertySource`/`Environment` or Boot's config mechanism may suffice. If the goal is keeping bean definitions or XML namespaces, use `@ImportResource`.

## 9. Loading XML Namespaces: When Does Java-Centric Still Make Sense?

Some long-lived integrations or third-party libraries provide XML namespaces for concise infrastructure declarations, such as `<context:property-placeholder>`. Spring can process namespace handlers when JARs containing the matching metadata/schema handlers are placed on the classpath.

`@ImportResource` lets a Java-centric application import only those XML resources:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource({
    "classpath:legacy/namespace-config.xml",
    "classpath:legacy/adapters.xml"
})
public class ApplicationConfig {
}
```

This is a multi-file illustration. There is no need to rewrite every XML namespace before starting to use Java configuration.

However:

- XML namespaces must declare valid `xmlns` and `xsi:schemaLocation`.
- The corresponding namespace handler/schema must be provided by valid dependencies on the runtime classpath.
- An unsupported namespace or removed API version can cause XML parsing errors.
- Migration should gradually reduce obsolete XML, rather than turning `@ImportResource` into a mechanism that hides configuration code the team no longer understands.

You can keep stable XML parts long-term if the cost/maintenance trade-off makes sense; there is no rule that every Spring Framework project must convert 100% to annotations.

## 10. Bean Names and Aliases When XML and @Bean Share a Container

Bean names are an especially important contract in hybrid configurations.

### Java @Bean Has a Default Name

```java
@Bean
PaymentService paymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

The default bean name is `paymentService`. XML can reference it:

```xml
<property name="paymentService" ref="paymentService"/>
```

If you rename the Java method `paymentService()` to `createService()` without an explicit name, the bean name changes. Legacy XML can break even though the Java type stayed the same.

### Preserving Explicit Bean Names During Refactoring

```java
@Bean("paymentService")
PaymentService createPaymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

The primary name remains `paymentService` while the factory method name changes. This is a useful technique during configuration migration while XML consumers still exist.

### Bean-Name Aliases in Both Formats

Java:

```java
@Bean(name = {"paymentService", "legacyPaymentService"})
PaymentService createPaymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

XML:

```xml
<alias name="paymentService" alias="oldPaymentService"/>
```

Both examples show that multiple names can point to one bean. You should not blindly use **both** without checking for collisions. Aliases solve name compatibility; they are not a way to create two implementations or copy bean state.

### Avoiding Name Collisions Between XML and Java

If XML registers:

```xml
<bean id="paymentService" class="com.example.LegacyPaymentService"/>
```

and Java also registers `@Bean("paymentService")`, two definitions compete for the same name. Exact behavior depends on the container and bean definition overriding policy; the application may fail or one definition may replace the other according to current rules. **Never rely on file-reading order to intentionally override** without configuring an explicit policy and testing it.

With Spring Boot, overriding may be rejected by default; with plain Spring Framework, BeanFactory has flags controlling overriding. Treat unintentional name collisions as **a design bug to fix**, rather than assuming “Java always overrides XML”.

## 11. Scopes, Lazy Beans, and Lifecycles in Hybrid Configuration

A bean declared in XML is still a normal Spring bean:

```xml
<bean id="client"
      class="com.example.LegacyClient"
      scope="singleton"
      lazy-init="true"
      init-method="initialize"
      destroy-method="shutdown"/>
```

The metadata in this example has the following meanings:

- `scope="singleton"`: one managed instance per BeanFactory.
- `lazy-init="true"`: attempts to defer singleton creation until needed; eager dependencies may still trigger earlier creation.
- `init-method="initialize"`: initialization callback invoked when Spring creates the managed bean.
- `destroy-method="shutdown"`: cleanup callback for eligible beans when the container shuts down, typically upon context close for singletons.

A bean created with Java `@Bean` can likewise use `@Scope`, `@Lazy`, and `initMethod`/`destroyMethod`. There is no separate set of lifecycle rules just because a bean comes from XML.

### Receiving XML Dependencies via Parameters Is Safe

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class ServiceConfig {

    @Bean
    ModernService modernService(LegacyClient client) {
        return new ModernService(client);
    }
}
```

This lets **BeanFactory** handle `LegacyClient`'s scope and lifecycle. You must not write `new ClassPathXmlApplicationContext(...)` inside `@Bean modernService()` to obtain the client, because doing so creates a **second** context with its own singletons/lifecycle, causing leaks and mismatched bean identities.

### Prototypes Injected into Singletons

If an XML bean is `scope="prototype"` while a Java singleton service receives it once via a constructor/factory parameter, the service typically holds a reference to the prototype created at injection time. This does not mean the service will automatically receive a fresh prototype on every request. If per-use lookup is needed, consider `ObjectProvider<LegacyClient>` or an appropriate factory.

### Cleanup

When creating `AnnotationConfigApplicationContext` in Java, close the context:

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use beans from XML and Java.
}
```

Closing the context triggers cleanup/lifecycle callbacks for eligible managed singletons. For prototypes, Spring does not by default manage destruction like singletons after handing the object to the client.

## 12. XML Cannot Rescue a Java Class Missing from the Classpath

`@ImportResource` reads **metadata**; it does not download missing class bytecode from the internet and does not automatically add Maven dependencies.

If XML contains:

```xml
<bean id="legacyAdapter"
      class="com.vendor.legacy.Adapter"/>
```

but `com.vendor.legacy.Adapter` is not in runtime dependencies, the container can throw `CannotLoadBeanClassException` or a corresponding bean-creation/classloading exception. Fixing the `@ImportResource` path will not fix a missing class.

During a multi-module migration:

1. Ensure the module/JAR containing the implementation class is on the runtime classpath.
2. Ensure the XML is at the right resource path.
3. Ensure XML schema/namespace dependencies match the current Spring version.
4. Ensure bean names and property/constructor argument types match.
5. Test that `ApplicationContext` creates both Java and XML beans.

Do not rely solely on Java compilation succeeding: XML bean class names are **strings**, so package/class rename errors sometimes appear only when Spring parses or instantiates the context.

## 13. Comparing with Other Configuration Options

| Need | Usually Suitable Option | Reason |
| --- | --- | --- |
| Keep legacy XML with Java as main bootstrap | `@ImportResource` | Inserts XML bean definitions into the same context |
| Import another Java configuration class | `@Import` | Type-safe class reference and composition |
| Only read properties | `@PropertySource`, `Environment`, or Boot mechanisms | No XML parser needed for plain key-values |
| Register stereotyped application classes | `@ComponentScan` | Scans packages without listing beans in XML |
| Register third-party clients via builders | `@Bean` | Strongly typed Java factory methods and parameters |
| XML as main bootstrap | `ClassPathXmlApplicationContext` | Fits XML-centric systems |
| Split one XML file into modules | XML `<import resource="..."/>` | Composition directly within the XML DSL |
| Select a specific bean among multiple type matches | `@Qualifier`/`@Primary` | Resolves ambiguity without dictating config source |

These are **complementary** tools, not an absolute good-vs-bad ranking. A greenfield project may need no XML; a legacy project can still use `@ImportResource` as a stable stepping stone.

## 14. Migrating from XML to Java Step by Step

A safe conversion plan should focus on **container contracts and behavior**, not just syntax changes.

### Step 1 — Identify the XML Boundary to Keep

For example, a project has three files:

```text
legacy/
├── repositories.xml
├── integrations.xml
└── properties.xml
```

Classify them:

- Which infrastructure beans must stay due to specialized namespaces/integrations?
- Which beans are application classes that can use `@Service`/`@Repository` or clear Java `@Bean` methods?
- Which bean names, aliases, qualifiers, and scopes are referenced by XML/Java consumers?
- Are there resources/lifecycles that need exact testing?

You do not need to change everything at once.

### Step 2 — Create a Root Java Configuration

```java
@Configuration(proxyBeanMethods = false)
@ImportResource({
    "classpath:legacy/repositories.xml",
    "classpath:legacy/integrations.xml",
    "classpath:legacy/properties.xml"
})
class RootConfig {
}
```

Now you can boot from `AnnotationConfigApplicationContext(RootConfig.class)` while old bean definitions still come from XML.

### Step 3 — Migrate One Bean at a Time

Suppose XML has:

```xml
<bean id="catalogRepository"
      class="com.example.catalog.JdbcCatalogRepository"/>
```

When migrating to Java:

```java
@Bean("catalogRepository")
CatalogRepository catalogRepository(DataSource dataSource) {
    return new JdbcCatalogRepository(dataSource);
}
```

This is illustrative; application classes and a `DataSource` must be present. **Do not leave both XML and Java registering the `catalogRepository` bean name in the same context** without an explicit policy. Remove the migrated XML definition in the same verified change.

Crucially, **preserve the exact bean name** when legacy consumers still reference `ref="catalogRepository"`.

### Step 4 — Preserve Equivalent Scope, Qualifiers, and Lifecycle

Convert:

```xml
<bean id="cacheClient"
      class="com.example.CacheClient"
      init-method="connect"
      destroy-method="close"/>
```

into the corresponding idea:

```java
@Bean(name = "cacheClient",
      initMethod = "connect",
      destroyMethod = "close")
CacheClient cacheClient() {
    return new CacheClient();
}
```

This is a structural example requiring the corresponding `CacheClient` class. If the old bean was prototype, lazy, or had special property injection/constructor arguments, migrate that metadata deliberately instead of copying only the name.

### Step 5 — Test the Context After Each Step

Verify:

- Primary bean names and aliases exist properly.
- Bean counts per interface did not accidentally increase.
- Java ↔ XML dependencies still resolve cleanly.
- Init/destroy callbacks are neither invoked twice nor dropped.
- Profiles/properties/conditionals match environment expectations.
- Migrated classes are no longer registered twice.
- No external connections or business workflows accidentally execute when testing the context.

### Step 6 — Remove @ImportResource Only When No Reason Remains

Once the XML no longer defines needed beans and has no XML namespace processors that must be kept, remove `@ImportResource` along with the unused resource. If the application still benefits from one stable XML file, keeping it is a perfectly acceptable engineering choice.

## 15. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `FileNotFoundException`/`BeanDefinitionStoreException` at startup | `@ImportResource` points to the wrong classpath/file | Check `src/main/resources` and runtime JAR; fix location |
| XML parse error or unrecognized namespace | Wrong `xmlns`, `xsi:schemaLocation`, or missing dependency providing the namespace handler | Fix schema/namespace and dependencies |
| `CannotLoadBeanClassException` | `class="..."` has wrong package, nested class name, or missing JAR | Fix fully qualified/binary class name and runtime classpath |
| `NoSuchBeanDefinitionException` | XML not imported, Java bean not registered, wrong `ref`/qualifier | Check root `@Configuration` and bean names/types |
| `UnsatisfiedDependencyException` | Java factory parameter requires an XML bean that does not exist or does not match | Verify the XML bean is registered with the right exposed type/qualifier |
| `NoUniqueBeanDefinitionException` | XML and Java register multiple beans for the same interface with no winner | Apply `@Qualifier`/`@Primary`/proper registry, remove accidental duplicates |
| Bean name collision | XML `id` matches `@Bean(name=...)` | Use distinct names; remove old definitions during migration |
| `ref="messageService"` cannot be resolved | Java bean actually has a different name or configuration was not loaded | Keep explicit name or fix `ref` |
| Bean has a property that is not set | Wrong `<property>`/setter name or incompatible type conversion | Check JavaBean setter and property type |
| Placeholder `${app.label}` unresolved | Property placeholder config not loaded or properties file missing | Verify `@ImportResource` XML, `context` namespace, and properties file |
| Alias treated as a second bean | Confusing `<alias>` with `<bean>` | Use `getBeanNamesForType`/`isAlias` to verify |
| Unexpected scope/proxy behavior | Creating a second context or calling `new` outside the container | Keep one context and obtain managed beans via DI |
| XML parses fine, but logic behaves wrong | Mismatched constructor/property types, lifecycle, or config values | Integration-test behavior rather than just checking file existence |
| Tests pass in IDE, fail when packaged | Resource path only worked in source tree or JAR lacks XML | Test the packaged artifact runtime classpath and Maven resource config |
| Service class registered twice | Both `@ComponentScan` on the class and XML `<bean>` declared | Keep one bean definition, or use distinct names/qualifiers if intentional |
| Security concern when loading external XML | Untrusted configuration resource, uncontrolled edits | Restrict XML paths and sources, review deployment and dependencies |

### Concise Diagnostic Workflow

1. **Metadata:** Is `@ImportResource` on a configuration class that Spring actually registers/imports/scans?
2. **Location:** Does the file actually exist on **the runtime classpath** or configured filesystem path?
3. **XML:** Are namespace/schema syntax, `class` name, `id`, `ref`, and `property` valid?
4. **Bean definitions:** Is the bean registered? Are there duplicate names or type ambiguities?
5. **Dependencies:** Do Java parameters and XML `ref`s point to the right types/names?
6. **Lifecycle/scope:** Does the bean have lazy/prototype/proxy semantics or init callbacks to watch out for?
7. **Readiness:** Are external resources configured safely? Do not run heavy business logic directly inside XML/Java factories.
8. **Test:** Use a real ApplicationContext to verify both wiring directions and output.

## 16. Testing Hybrid Configuration

### 16.1. Do Not Only Check That the XML File Exists

A syntactically valid XML file can still contain a misspelled class name, missing property setter, missing bean ref, or an initialization sequence causing a dependency cycle. Therefore, tests must **create an ApplicationContext** and retrieve key beans.

In the section 7 project:

```java
// Additional verification snippet, placed inside try with context.
if (!context.containsBean("xmlStore")) {
    throw new AssertionError("XML store missing");
}
if (!context.containsBean("messageService")) {
    throw new AssertionError("Java service missing");
}
if (context.getBean("xmlStore") !=
        context.getBean("legacyStore")) {
    throw new AssertionError("Alias must resolve same singleton");
}
if (!"stored[XML:order-42]".equals(
        context.getBean(MessageService.class).submit("order-42"))) {
    throw new AssertionError("Cross-config wiring incorrect");
}
```

If all checks pass, the assertions print no extra stdout. This is an **optional addition**, not part of `main`'s default output.

### 16.2. Testing the XML → Java Reference Direction

```java
// Also placed inside try with context from section 7.
String status = context.getBean(XmlDashboard.class).status();
if (!"xml->java:stored[XML:dashboard]".equals(status)) {
    throw new AssertionError("XML reference to Java bean failed");
}
```

This test confirms that `<property ... ref="messageService"/>` in XML resolves the Java `@Bean` properly.

### 16.3. Testing for No Duplicate Registrations

```java
// Uses MessageStore from the full example.
String[] stores = context.getBeanNamesForType(MessageStore.class);
if (stores.length != 1 || !"xmlStore".equals(stores[0])) {
    throw new AssertionError("Unexpected MessageStore definitions");
}
```

There is only one `MessageStore` bean in the main example. If after migration a new Java `@Bean` creates an extra `MessageStore`, the test catches the increased candidate count instead of mistaking an alias for a second bean.

### 16.4. Unit Tests Without XML for Pure Java Logic

Hybrid configuration does not force every unit test to read XML. `MessageService` only needs `MessageStore` and `PrefixFormatter`; you can create fake implementations and invoke business methods in plain Java. Use **integration tests** to prove Spring wiring and resource imports work, and unit tests to verify service logic quickly and reliably.

### 16.5. Contexts Created in Java Must Be Closed

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Assertions on XML beans and Java beans.
}
```

`try-with-resources` ensures `close()` is called even if an assertion fails, reducing resource leaks in integration tests.

## 17. Practice Exercises

### Exercise 1 — Importing One File

The file `src/main/resources/legacy/orders.xml` contains bean `orderRepository`. Write the annotation on a `@Configuration` class so Spring imports that file from the classpath.

**Answer:**

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy/orders.xml")
class OrdersConfig {
}
```

Do not use `src/main/resources/...` in the resource location.

### Exercise 2 — Distinguishing @Import and @ImportResource

You have a `MonitoringConfig` class containing `@Bean` methods and a `legacy/metrics.xml` file containing `<bean>` definitions. Which annotation should you use for each source?

**Answer:** `@Import(MonitoringConfig.class)` for the Java class; `@ImportResource("classpath:legacy/metrics.xml")` for the XML file. Both can be used on the same root config.

### Exercise 3 — Loading Multiple XML Files

Two resources `legacy/a.xml` and `legacy/b.xml` both exist. Write `@ImportResource` to import both.

**Answer:**

```java
@ImportResource(locations = {
    "classpath:legacy/a.xml",
    "classpath:legacy/b.xml"
})
```

Both contribute bean definitions into the same context; there is no separate context per file.

### Exercise 4 — XML Bean → Java @Bean

XML declares `<bean id="reportRepository" class="..."/>`. A Java factory needs an instance by interface `ReportRepository`. How do you inject it properly without creating a second context?

**Answer:**

```java
@Bean
ReportService reportService(
        @Qualifier("reportRepository") ReportRepository repository) {
    return new ReportService(repository);
}
```

This is an illustrative pattern; matching `ReportRepository`/`ReportService` and importing `@Qualifier` are required. Spring uses the current BeanFactory to resolve the dependency without calling `ClassPathXmlApplicationContext` inside the factory.

### Exercise 5 — Java @Bean → XML ref

`@Bean("priceCalculator")` creates a `PriceCalculator` bean. The XML for `LegacyCheckout` has a `setPriceCalculator` setter. Write the corresponding property injection.

**Answer:**

```xml
<property name="priceCalculator" ref="priceCalculator"/>
```

The name `priceCalculator` must match the Java factory's bean name, and the setter must accept a compatible type.

### Exercise 6 — Does an Alias Create a New Bean?

XML:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="oldClient"/>
```

How many bean definitions are there? With singleton scope, what is `getBean("primaryClient") == getBean("oldClient")`?

**Answer:** One bean definition and one alias; both names return the same singleton reference so the comparison evaluates to `true` within the same container, assuming bean creation succeeds.

### Exercise 7 — Refactoring a @Bean Method Name

Legacy XML references `ref="paymentService"`. Java `@Bean PaymentService paymentService()` is renamed to `createPaymentService()`. How do you avoid having to edit the XML?

**Answer:** Use `@Bean("paymentService")` on the new factory method to preserve the old explicit bean name.

### Exercise 8 — Duplicate Bean

Both XML and Java declare `id/name="customerRepository"`. Should you rely on “whichever source is read last” to pick the desired implementation?

**Answer:** No. Remove the old definition when migrating, or configure overrides transparently with integration tests and a valid reason. Avoid unintentional collisions.

### Exercise 9 — Resource Path in a JAR

`@ImportResource("src/main/resources/legacy.xml")` runs in the project directory but fails after packaging as a JAR. How do you fix it?

**Answer:** Place the file at `src/main/resources/legacy.xml` and import it with `@ImportResource("classpath:legacy.xml")` to use a resource path on the runtime classpath.

### Exercise 10 — Unresolved Placeholder

XML has `<context:property-placeholder location="classpath:settings.properties"/>` and Java has `@Value("${app.timeout}")`. However, bean creation fails due to a missing property. What should you check?

**Answer:** Whether `settings.properties` actually exists on the runtime classpath, key `app.timeout` exists, the XML `context` namespace is properly declared, the XML is imported via `@ImportResource`, there are no conflicting property processors, the target type is convertible, and the environment configuration is right.

### Exercise 11 — Program Output

In the section 7 example, why is `storeBeanCount=1` even though there are two names `xmlStore` and `legacyStore`?

**Answer:** `legacyStore` is only an alias for `xmlStore`. `getBeanNamesForType(MessageStore.class)` counts compatible bean definitions, not aliases as independent beans.

### Exercise 12 — Migration Strategy

An application has 50 XML bean definitions, of which 10 simple beans can be moved to Java. Outline a sequence that minimizes regressions.

**Answer outline:** Create a root Java config with `@ImportResource`; inventory bean names/aliases/scopes/dependencies/lifecycles; migrate one group at a time to `@Bean` or stereotypes; delete corresponding XML definitions to avoid duplicates; preserve public names where legacy consumers need them; run integration tests after each step; remove `@ImportResource` only when no XML is needed anymore.

## 18. Practical Implementation Checklist

- [ ] `@ImportResource` sits on a configuration class **processed by Spring**, not an unregistered class.
- [ ] Resource paths match the runtime classpath/filesystem and still work when packaged as a JAR.
- [ ] XML has a `<beans>` root, valid namespaces/schemas, and valid bean class names.
- [ ] Libraries supplying XML namespace handlers are on the classpath.
- [ ] Java `@Bean` and XML `<bean>` do not cause unintentional name/type collisions.
- [ ] Public bean names/aliases remain compatible during refactoring/migration.
- [ ] Java factory methods receive XML dependencies via **method parameters** instead of instantiating a new ApplicationContext.
- [ ] XML `ref` points to exact bean names registered by Java `@Bean` or other metadata sources.
- [ ] `scope`, `lazy-init`, and `init/destroy` semantics for legacy beans have been verified.
- [ ] Placeholder processors/`@Value` work with the right environment property files.
- [ ] Beans missing from the runtime classpath are not “masked” simply because an XML file still exists.
- [ ] Integration tests open one context and verify bidirectional Java ↔ XML wiring, alias identity, and type candidates.
- [ ] External resources/bean lifecycles are cleaned up via context close, without creating/leaking a second context.
- [ ] After migration, no unused XML files or un-updated legacy references remain.
- [ ] Untrusted XML resources are never fed into the system's configuration loading path.

## Summary

`@ImportResource` is the bridge between **Java-centric configuration ↔ XML bean definitions** in Spring Core Container. The annotation reads XML resources and imports bean definitions into **the same ApplicationContext**, so that:

- Java `@Bean` methods can receive dependencies from XML through standard dependency injection.
- XML `<bean>` definitions can use `ref` to point to beans declared by Java `@Bean`.
- Primary names, aliases, scopes, and lifecycles are managed by the same BeanFactory.
- Projects can migrate from XML to Java incrementally without replacing everything at once.

Use accurate resource paths, preserve public bean-name contracts, avoid duplicate definitions, and test both wiring directions. Once no XML or XML namespace is truly needed anymore, you can remove `@ImportResource` and maintain pure Java configuration.

## Official Spring Documentation

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): section **Combining Java and XML Configuration**, Java-centric `@ImportResource` examples, and XML-centric integration.
- [Spring Framework 6.2 — ImportResource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportResource.html): `value`, `locations`, `reader`, and choosing a bean definition reader.
- [Spring Framework 6.2 — The IoC Container: XML Bean Definition Basics](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): `<beans>`/`<bean>` structure, XML imports, and resource locations.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): parameter injection and bean metadata.
- [Spring Framework 6.2 — Using PropertyPlaceholderConfigurer](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-placeholderconfigurer.html): property placeholders and integration.
