# NoClassDefFoundError Due to Referencing Optional Classes Too Early

> **Spring Boot Auto Configuration → Troubleshooting.** This lesson explains why a library can compile successfully yet fail in a consuming application with NoClassDefFoundError when an optional dependency is missing. The focus is on when the JVM must resolve types in class signatures, the limits of @ConditionalOnClass on @Bean methods, how to isolate integrations in nested static configurations, and how to verify with Maven dependency tree, FilteredClassLoader, and a standalone consumer. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 1. Symptom and Core Cause

A library provides an optional JDBC feature. The auto-configuration module is compiled while spring-jdbc is on the compile classpath. The developer marks the dependency as optional so applications using only the core do not have to pull in JDBC.

A consuming application declares only the auto-configuration library, without spring-jdbc on the runtime classpath. When Spring starts up, the application unexpectedly stops with an error such as:

~~~text
java.lang.NoClassDefFoundError:
  org/springframework/jdbc/core/JdbcTemplate

Caused by: java.lang.ClassNotFoundException:
  org.springframework.jdbc.core.JdbcTemplate
~~~

This is a representative error pattern. The exact stack trace and missing class can vary depending on when the JVM must resolve types, the classloader, and which dependency is missing. What needs investigating is why a class belonging to an optional integration was touched when the application did not intend to use that integration.

A common cause in auto-configuration is referencing an optional type directly too early in a class or method signature. A condition may be designed to skip the feature when the class is absent, yet the JVM or Spring already had to read that type before the condition was evaluated.

A frequent example:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnClass(name =
            "org.springframework.jdbc.core.JdbcTemplate")
    NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
            JdbcTemplate jdbcTemplate) {

        return new NoticeJdbcHistoryWriter(jdbcTemplate);
    }
}
~~~

The code's intent is: if JdbcTemplate is absent, the method should not apply. However, the method signature already references JdbcTemplate. Before the method-level condition is applied, the JVM may have to load the class and process method references. If the type is absent, a linkage error can occur before Spring can skip the bean method.

Spring Boot documents this case explicitly in the ConditionalOnClass Javadoc: a condition on a @Bean method cannot protect a return type that the JVM may load eagerly; the solution is to extract the condition into a separate configuration class. Reference: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html.

## 2. Distinguishing Common Class Loading Errors

Not all class-loading errors have the same root cause. Read the exact exception type, class name, and Caused by section.

| Error | Common meaning | Where to investigate |
| --- | --- | --- |
| ClassNotFoundException | Explicit class-loading API such as Class.forName(...) could not find the class | Classloader, runtime classpath, class name |
| NoClassDefFoundError | JVM needed a class during linking/execution but could not find it, or the class failed earlier initialization | Runtime dependency, class signatures, static initializer |
| NoSuchMethodError | Class is present, but the loaded version lacks the method required by compiled code | Version conflict, dependency mediation |
| NoSuchFieldError | Class is present, but the referenced field does not exist in the runtime version | Version conflict, binary compatibility |
| AbstractMethodError | Runtime implementation does not provide a method expected by the caller | Incompatible interface/implementation versions |
| ExceptionInInitializerError | Static initializer threw an exception when the class was initialized | First exception in the static initializer |
| NoClassDefFoundError: Could not initialize class ... | Class failed during an earlier initialization attempt; subsequent uses cannot proceed | Find the root exception from the first initialization attempt |

ClassNotFoundException is typically a checked exception from explicit class-loading APIs. NoClassDefFoundError is a LinkageError thrown by the JVM when linking a class at runtime. Do not look only at the name NoClassDefFoundError and conclude that a JAR file is completely missing.

For example, the JdbcTemplate class might be present while another class it depends on was excluded from the runtime classpath. In that case, the class name in the error message may be a transitive dependency rather than the class your code calls directly.

### 2.1. Why Does Compilation Succeed While Runtime Fails?

Compile and runtime can use different classpaths.

- In the library module, Maven places declared dependencies on the compile classpath so the code compiles.
- If a dependency has optional=true, Maven does not propagate that dependency transitively to consumers.
- Consumers can compile and run core features without the optional integration.
- However, if the library's auto-configuration forces the JVM to resolve an optional type as soon as the configuration is loaded, consumers will fail even when not using the integration.

Example dependency:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-jdbc</artifactId>
    <optional>true</optional>
</dependency>
~~~

An optional dependency is still used when building the module that owns it. The optional attribute tells Maven that consumers do not automatically inherit this dependency transitively. Applications needing JDBC must declare the appropriate dependency themselves.

This is a sound contract for genuinely optional integrations, but it is safe only if the core code and auto-configuration can be loaded when the integration is absent.

## 3. Where Must the JVM Resolve Types?

The JVM does not necessarily load and resolve every class mentioned in the constant pool at the moment a class is loaded. Resolution can happen when the class or member is actually used. However, a framework may require reflection or metadata about methods to process configurations, causing types in method signatures to be resolved earlier than expected.

Places that easily create links to optional types include:

- A superclass or interface that the auto-configuration extends or implements.
- Field types or constructor parameters of the outer configuration.
- Return types, parameter types, or generic signatures of @Bean methods.
- Annotations containing class literals or annotation attributes requiring resolution.
- Static field initializers, static blocks, or static calls.
- Unconditional Class.forName(...) or reflection calls.
- @Import(OptionalConfiguration.class) on the outer configuration.
- Custom Condition classes loaded and referencing optional types before a classpath condition guards them.
- Helper classes invoked by the outer configuration in a constructor or static initializer.

Example of an unsafe outer configuration:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration
        extends JdbcBasedConfiguration {

    private final JdbcTemplate jdbcTemplate;

    public NoticeAutoConfiguration(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

As soon as the JVM has to load the outer configuration, it encounters JDBC types in the hierarchy, field, or constructor. A condition on another bean method cannot shield these references.

Another example is directly importing an optional config:

~~~java
@AutoConfiguration
@Import(NoticeJdbcConfiguration.class)
public class NoticeAutoConfiguration {
}
~~~

If NoticeJdbcConfiguration has method signatures using JdbcTemplate and is imported unconditionally, the optional boundary is broken.

Design rule: the outer/core auto-configuration must be loadable when the optional integration is completely absent from the classpath. Only a guarded nested configuration should reference optional APIs.

## 4. How Is @ConditionalOnClass Safe at the Class Level?

Spring Boot processes annotation metadata of configuration classes using ASM before loading the class itself. Thus, @ConditionalOnClass on a configuration class can reference a class not yet on the runtime classpath while still allowing Boot to inspect the metadata.

Class-level example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(JdbcTemplate.class)
static class JdbcConfiguration {
}
~~~

Or using the class name:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(
        name = "org.springframework.jdbc.core.JdbcTemplate"
)
static class JdbcConfiguration {
}
~~~

Both forms can be used directly on a configuration class. Using name is convenient when you want to keep the outer configuration free of optional type imports or when building composed/meta-annotations.

**Note on meta-annotations:** when using @ConditionalOnClass or @ConditionalOnMissingClass inside a composite annotation created by your library, use the name attribute. Spring Boot Javadoc guarantees ASM-based safe reading of class literals only when the annotation is placed directly on the conditional component, not in the same way for meta-annotations.

Reference: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html.

### 4.1. Why Is a Method-Level Condition Not Enough?

Look at this example:

~~~java
@Bean
@ConditionalOnClass(JdbcTemplate.class)
NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
        JdbcTemplate jdbcTemplate) {
    return new NoticeJdbcHistoryWriter(jdbcTemplate);
}
~~~

The condition is placed on the method, yet Spring must analyze method metadata, including the return type and parameter types. The JVM may already load or resolve these types before the method condition gets a chance to exclude the method.

Therefore, do not use method-level @ConditionalOnClass as a shield for a method signature containing optional types. Move the method into a nested @Configuration with a class-level condition.

## 5. Standard Fix Pattern: Nested Static Configuration

The structure should establish three boundaries:

~~~text
NoticeAutoConfiguration
  |
  +-- NoticeClient bean
  |     Does not reference optional JDBC APIs
  |
  +-- JdbcConfiguration (static nested class)
        @ConditionalOnClass(JdbcTemplate)
        @ConditionalOnProperty(...)
        |
        +-- NoticeJdbcHistoryWriter bean
              Signature includes JdbcTemplate
~~~

The outer class holds only core beans and nested configuration declarations. Each nested configuration is responsible for guarding all code requiring an optional library.

General pattern:

~~~java
@AutoConfiguration
public class MyAutoConfiguration {

    // Core beans that do not require optional libraries.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        OptionalAdapter optionalAdapter(OptionalClient client) {
            return new OptionalAdapter(client);
        }
    }
}
~~~

When the optional class is absent:
1. Boot reads metadata of the nested configuration.
2. @ConditionalOnClass does not match.
3. The nested configuration is not applied.
4. Method signatures containing optional types do not need to be processed as active bean methods.
5. The outer auto-configuration and core beans can still proceed.

When the optional class is present:
1. The class condition matches.
2. Boot processes the nested configuration.
3. Bean methods can reference optional APIs.
4. Remaining bean/property conditions decide whether individual beans get registered.

Make the nested class static so it does not retain an implicit reference to an instance of the outer class. Set proxyBeanMethods=false if cross-calling @Bean methods through a proxy is not needed.

### 5.1. Isolating Each Integration Separately

If a library supports JDBC, Kafka, and Redis, split them into separate nested configurations:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
    static class JdbcConfiguration {
        // Only JDBC code here.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.kafka.core.KafkaTemplate")
    static class KafkaConfiguration {
        // Only Kafka code here.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.data.redis.core.RedisTemplate")
    static class RedisConfiguration {
        // Only Redis code here.
    }
}
~~~

One integration missing its dependency should not break other integrations or core beans. Each nested configuration has its own conditions, properties, and beans.

Do not place optional types in imports, fields, or method signatures of the outer class. Nor should you use broad component scanning to discover all integration classes, because scanning can force Spring to inspect unprotected types.

## 6. Complete Example with Spring Boot 3.3.13

We create a notification library auto-configuration with two parts:
- NoticeClient: core feature, does not require JDBC.
- NoticeJdbcHistoryWriter: optional integration, requires JdbcTemplate.

When a consumer lacks Spring JDBC, core still runs. When a consumer has Spring JDBC, enables the property, and provides a JdbcTemplate bean, the writer is created.

### 6.1. Directory Structure

~~~text
notice-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   └── NoticeClient.java
    │   ├── java/com/acme/notice/autoconfigure/
    │   │   └── NoticeAutoConfiguration.java
    │   ├── java/com/acme/notice/jdbc/
    │   │   └── NoticeJdbcHistoryWriter.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationOptionalJdbcTest.java
~~~

### 6.2. pom.xml of the Auto-Configuration Module

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

In this module, spring-jdbc is present on the compile/test classpath to compile the JDBC integration. Maven optional ensures consumers do not automatically receive that dependency through the dependency graph.

spring-boot-autoconfigure is required to compile the auto-configuration. The test starter is only for testing.

### 6.3. NoticeClient.java — Core Independent of JDBC

File src/main/java/com/acme/notice/NoticeClient.java:

~~~java
package com.acme.notice;

public record NoticeClient(String source) {

    public String send(String message) {
        return source + ":" + message;
    }
}
~~~

This class uses only standard Java. It can be loaded and used in an application without Spring JDBC.

### 6.4. NoticeJdbcHistoryWriter.java — Dedicated to JDBC Integration

File src/main/java/com/acme/notice/jdbc/NoticeJdbcHistoryWriter.java:

~~~java
package com.acme.notice.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;

public class NoticeJdbcHistoryWriter {

    private final JdbcTemplate jdbcTemplate;

    public NoticeJdbcHistoryWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public String jdbcTemplateType() {
        return this.jdbcTemplate.getClass().getSimpleName();
    }
}
~~~

This class directly references JdbcTemplate. That is appropriate because it is the JDBC integration implementation. What must be ensured is that no core configuration loads this class when JDBC is absent.

### 6.5. NoticeAutoConfiguration.java — Outer Class Without JDBC References

File src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;
import com.acme.notice.jdbc.NoticeJdbcHistoryWriter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "org.springframework.jdbc.core.JdbcTemplate"
    )
    @ConditionalOnProperty(
            prefix = "acme.notice.jdbc",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JdbcConfiguration {

        @Bean
        @ConditionalOnBean(JdbcTemplate.class)
        @ConditionalOnMissingBean(NoticeJdbcHistoryWriter.class)
        NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
                JdbcTemplate jdbcTemplate) {

            return new NoticeJdbcHistoryWriter(jdbcTemplate);
        }
    }
}
~~~

In this example, NoticeAutoConfiguration declares no field, constructor, or method signature of type JdbcTemplate. All JDBC references live inside the nested JdbcConfiguration.

NoticeJdbcHistoryWriter and JdbcTemplate are imported in the same source file, but only the nested configuration uses them in bean methods. When an even stricter boundary is desired, JdbcConfiguration can be moved into a separate file; the key principle remains that the class must be guarded by a condition before Spring processes method signatures.

The two conditions on the nested configuration have distinct roles:
- ConditionalOnClass(name=...): verifies the JDBC API is on the classpath.
- ConditionalOnProperty: verifies whether the user enabled the integration.

The two conditions on the bean method:
- ConditionalOnBean(JdbcTemplate.class): creates the writer only when the context has a JDBC bean.
- ConditionalOnMissingBean(NoticeJdbcHistoryWriter.class): lets the application provide a custom writer replacement.

### 6.6. AutoConfiguration.imports

Create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

Spring Boot discovers the outer auto-configuration from the imports file. The nested JdbcConfiguration is managed inside the outer class and does not need to be registered as an independent candidate.

### 6.7. Testing with ApplicationContextRunner and FilteredClassLoader

File src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationOptionalJdbcTest.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;
import com.acme.notice.jdbc.NoticeJdbcHistoryWriter;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationOptionalJdbcTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    @Test
    void coreStartsWhenJdbcClassesAreMissing() {
        runner.withClassLoader(
                new FilteredClassLoader("org.springframework.jdbc")
        ).withPropertyValues("acme.notice.jdbc.enabled=true")
         .run(context -> {
             assertThat(context).hasNotFailed();
             assertThat(context).hasSingleBean(NoticeClient.class);
             assertThat(context).doesNotHaveBean(
                     "noticeJdbcHistoryWriter"
             );
         });
    }

    @Test
    void jdbcIntegrationStaysDisabledWhenPropertyIsFalse() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=false")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context).doesNotHaveBean(
                            "noticeJdbcHistoryWriter"
                    );
                });
    }

    @Test
    void jdbcClassAndPropertyAreNotEnoughWithoutJdbcTemplateBean() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context).doesNotHaveBean(
                            "noticeJdbcHistoryWriter"
                    );
                });
    }

    @Test
    void writerIsCreatedWhenClassPropertyAndBeanArePresent() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeJdbcHistoryWriter.class);

                    NoticeJdbcHistoryWriter writer =
                            context.getBean(NoticeJdbcHistoryWriter.class);

                    assertThat(writer.jdbcTemplateType())
                            .isEqualTo("JdbcTemplate");
                });
    }

    @Test
    void applicationWriterOverridesDefaultWriter() {
        NoticeJdbcHistoryWriter custom =
                new NoticeJdbcHistoryWriter(new JdbcTemplate());

        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .withBean(NoticeJdbcHistoryWriter.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeJdbcHistoryWriter.class);

                    assertThat(context.getBean(NoticeJdbcHistoryWriter.class))
                            .isSameAs(custom);
                });
    }
}
~~~

The first test simulates an application without Spring JDBC even though the test module still has the JDBC dependency on its classpath. FilteredClassLoader hides the package from the context's classloader. If the optional boundary is designed properly, the context still starts, the core bean is present, and the JDBC bean does not appear.

The remaining tests clearly isolate each condition:
- Class present, property false: integration is disabled.
- Class and property both match, but no JdbcTemplate bean: writer is not created.
- Class, property, and bean dependency all present: writer is created.
- Application provides its own writer: auto-configuration backs off.

### 6.8. Running the Tests

From the directory containing pom.xml:

~~~bash
mvn clean test
~~~

All five tests are expected to PASS. If coreStartsWhenJdbcClassesAreMissing fails with NoClassDefFoundError, inspect the stack trace to find which class is being loaded before the nested condition takes effect.

This test verifies behavior inside a context with a filtered classloader. It does not replace testing a standalone consumer where the optional dependency is genuinely absent from the runtime classpath.

## 7. Standalone Consumer: Verifying the Optional Dependency Is Not Pulled In

FilteredClassLoader is useful for simulating missing classes, but an artifact-level check is also needed. Build and install the auto-configuration module, then create a separate consumer application that depends only on that artifact.

### 7.1. Building and Installing the Library Module

From the notice-autoconfigure directory:

~~~bash
mvn clean install
~~~

The artifact is installed into the local Maven repository. The spring-jdbc dependency has compile/runtime scope inside the published module yet is marked optional, so consumers do not receive it automatically.

### 7.2. Consumer POM

The consumer declares only Boot and the library:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-autoconfigure</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Do not declare spring-jdbc in the consumer. The consumer does not need to know about NoticeJdbcHistoryWriter or JdbcTemplate when using only the core.

### 7.3. ConsumerApplication.java

~~~java
package demo.consumer;

import com.acme.notice.NoticeClient;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    ApplicationRunner report(NoticeClient client) {
        return args -> System.out.println(
                "notice: " + client.send("hello")
        );
    }
}
~~~

The application neither imports nor references the optional integration. Spring Boot automatically discovers NoticeAutoConfiguration via AutoConfiguration.imports inside the JAR.

### 7.4. Checking the Dependency Graph

From the consumer directory:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

If the optional dependency is declared properly, the command lists no spring-jdbc in the consumer's dependency tree.

Inspect the entire dependency tree if needed:

~~~bash
mvn dependency:tree
~~~

This helps detect if another starter accidentally pulls Spring JDBC in. If spring-jdbc appears in the tree, trace back the dependency branch rather than concluding that the optional flag is broken.

### 7.5. Running the Consumer

~~~bash
mvn clean package
java -jar target/notice-consumer-1.0.0.jar
~~~

Deterministic output of the example:

~~~text
notice: auto:hello
~~~

The core bean is created and runs. The JDBC nested configuration is skipped because the class is absent from the runtime classpath. The application does not need to add a JDBC dependency just to use NoticeClient.

If the user wants to enable history, they must add the corresponding JDBC dependency/starter, configure a DataSource, and ensure a JdbcTemplate bean is created. Then set:

~~~properties
acme.notice.jdbc.enabled=true
~~~

The property does not install the dependency by itself. It only enables the feature once the classpath and bean dependency conditions are satisfied.

## 8. Design Mistakes to Look For During Investigation

### 8.1. Optional Type in Outer @Bean Signature

Unsafe:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.SearchClient")
    SearchAdapter searchAdapter(SearchClient client) {
        return new SearchAdapter(client);
    }
}
~~~

Fix with a nested configuration:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.SearchClient")
    static class SearchConfiguration {

        @Bean
        SearchAdapter searchAdapter(SearchClient client) {
            return new SearchAdapter(client);
        }
    }
}
~~~

### 8.2. Optional Type in Superclass or Interface

Unsafe:

~~~java
@AutoConfiguration
public class JdbcAutoConfiguration extends JdbcSupportBase {
}
~~~

If JdbcSupportBase depends on JDBC, the outer class is no longer independent. Move the logic into a helper or a guarded nested configuration. Never let a core configuration inherit an implementation from an optional module.

### 8.3. Optional Type in Field or Constructor

Unsafe:

~~~java
@AutoConfiguration
public class MetricsAutoConfiguration {

    private final OptionalRegistry registry;

    public MetricsAutoConfiguration(OptionalRegistry registry) {
        this.registry = registry;
    }
}
~~~

Do not inject optional dependencies into the constructor of an outer configuration. Place the dependency in a method of a nested config or a factory method processed only when the classpath condition matches.

### 8.4. Optional Type in Static Initializer

Unsafe:

~~~java
static {
    OptionalClient.initializeGlobalDefaults();
}
~~~

A static initializer runs when the class is initialized. A condition cannot undo side effects that have already happened. Move initialization into a bean factory method inside a nested configuration; avoid global initialization at class-loading time.

### 8.5. Unconditional Class Literals and Reflection

Unsafe:

~~~java
private static final Class<?> CLIENT_TYPE = OptionalClient.class;
~~~

Or:

~~~java
Class.forName("com.vendor.OptionalClient");
~~~

If this code runs when the outer configuration is loaded, it can throw an error before a Spring condition guards the integration. If you need to check for a class, prefer @ConditionalOnClass or ClassUtils.isPresent(...) with an appropriate classloader inside a custom condition that holds no static reference to the optional type.

Do not use default Class.forName(...) with initialization if the goal is only to check presence; that operation can initialize the class and execute static initializers. In most auto-configurations, standard Spring Boot conditions are the better choice.

### 8.6. Meta-Annotation Using a Class Literal

When creating a composite annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(OptionalClient.class)
public @interface ConditionalOnOptionalClient {
}
~~~

This is not safe under the meta-annotation rules for ConditionalOnClass. Use the class name:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.OptionalClient")
public @interface ConditionalOnOptionalClient {
}
~~~

Spring Boot states explicitly that the class-literal value is handled safely only when the annotation is directly on the conditional component; composed annotations must use name.

## 9. Diagnostic Workflow for NoClassDefFoundError

Trace from the root exception to the dependency graph and the reference site.

### Step 1: Identify the Actually Missing Class

Read the first line and the entire cause chain:

~~~text
NoClassDefFoundError: org/springframework/jdbc/core/JdbcTemplate
Caused by: ClassNotFoundException:
  org.springframework.jdbc.core.JdbcTemplate
~~~

Record the exact binary name, not just a generic integration name. If the message says Could not initialize class, look for the first static initialization error earlier in the logs.

### Step 2: Locate Where the Class Is Referenced

In the stack trace, find the first frame belonging to library code or Spring parsing configurations. Check:
- Does the outer auto-configuration have a field/constructor/method signature containing that type?
- Which @Bean method has that return/parameter type?
- Is the condition on the class or on the method?
- Is a nested configuration already used to isolate the optional type?
- Is there a custom condition, static initializer, or unconditional @Import?

If the frame lies inside reflection such as getDeclaredMethods, getDeclaredConstructors, or Spring's configuration parser, inspect the method signatures of the configuration class being parsed.

### Step 3: Inspect the Consumer's Dependency Tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

You can view the detailed dependency tree:

~~~bash
mvn dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

And trace a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-jdbc --configuration runtimeClasspath
~~~

Compare the compile classpath and runtime classpath. A class existing in the IDE or tests does not mean it is packaged into the actual runnable application.

### Step 4: Check Optional, Scope, and Exclusions

In the library POM, check:
- Was the dependency marked optional unintentionally?
- Does the consumer need to declare the integration itself?
- Did an exclusion drop the class or a transitive dependency?
- Was the version overridden by dependency management?
- Was provided used when the application actually needs the dependency at runtime?

If the integration is mandatory, provide a starter that pulls in the required dependency. If the integration is optional, keep the optional dependency while guarding every reference to it.

### Step 5: Inspect the Published Artifact

Inspect the JAR:

~~~bash
jar tf target/notice-autoconfigure-1.0.0.jar
~~~

Ensure:
- The outer auto-configuration class is present.
- Nested configurations and integration classes are present in the artifact if the module provides them.
- AutoConfiguration.imports contains the exact FQCN.
- The dependency versions in the published POM match expectations.

If the class exists in the JAR while a dependency it requires is absent in the consumer, this is still a runtime classpath issue. Do not confuse the presence of a class file with the presence of the entire dependency graph.

### Step 6: Run a Consumer Without the Optional Dependency

Create a separate consumer declaring only the core/autoconfigure artifact. Verify:
- The dependency tree has no optional artifact.
- The context starts successfully.
- Core beans are present.
- Optional beans are absent.
- No NoClassDefFoundError occurs.

This is concrete proof that the optional boundary works.

### Step 7: Add the Dependency and Enable the Feature to Test the Positive Branch

Once the dependency-absent branch runs cleanly, add the optional dependency, configure the property, and provide base beans. Confirm the integration activates properly.

A well-built library must test both sides:
- Without optional dependency: core still runs.
- With optional dependency and full conditions: integration runs.

## 10. Do Not Catch LinkageError to Hide Configuration Bugs

A wrong fix is catching the error:

~~~java
try {
    Class.forName("org.springframework.jdbc.core.JdbcTemplate");
}
catch (NoClassDefFoundError ex) {
    // Ignore and continue
}
~~~

Or:

~~~java
try {
    return new NoticeJdbcHistoryWriter(...);
}
catch (LinkageError error) {
    return null;
}
~~~

This approach causes multiple problems:
- The condition was evaluated too late; the configuration may already have failed on load.
- It can swallow a real version incompatibility or static initialization failure.
- The ApplicationContext can continue in an incomplete state.
- Errors surface only when a request hits that code path.
- The original stack trace is hidden and harder to diagnose.

LinkageError is a JVM linkage failure, not a normal feature toggle mechanism. Express dependencies and conditions at the metadata/configuration level so Spring excludes the configuration before loading optional implementations.

If an external library throws an error inside a static initializer, fix the dependency or initialization code. Do not turn that error into a silent fallback.

## 11. When to Add the Dependency Instead of Changing Auto-Configuration

Not every NoClassDefFoundError is a library bug. A user may have enabled a feature while forgetting the required dependency.

| Situation | How to handle |
| --- | --- |
| Feature is designed as optional and user does not use it | Auto-configuration must skip safely when the class is absent |
| Optional feature is enabled, but dependency is missing | Document the required dependency clearly or let the condition not match per the documented contract |
| Feature is a mandatory starter requirement | Starter must pull that dependency onto the runtime classpath |
| Dependency has the class, but a transitive dependency is missing | Fix exclusions/version conflicts or the POM |
| Class is present, but method/field is incompatible | Align versions and inspect dependency mediation |
| Class fails to load due to static initializer | Fix the root cause in the initializer or environment |
| Code references optional type in outer config | Isolate the type in a nested configuration with a class-level condition |

If a feature is explicitly enabled while the dependency is missing, there are two design choices:
- Silent back-off: the application keeps running core, and the integration does not appear. Suitable when the feature is truly optional and the user may not have installed the dependency.
- Fail-fast with a clear message: use custom validation/startup checks where appropriate if enabling the feature without the dependency is an invalid configuration under the product contract.

Whichever option is chosen, never let accidental linkage errors dictate behavior. Document required properties, dependencies, and preconditions.

## 12. Regression Testing

A thorough test suite should cover these scenarios:

| Scenario | Optional class | Property | Bean dependency | Outcome |
| --- | --- | --- | --- | --- |
| Core-only consumer | Absent | Enabled or missing | Absent | Core runs, integration absent |
| JDBC present, feature disabled | Present | false | Present | Integration absent |
| JDBC present, feature enabled, missing bean | Present | true | Absent | Integration absent |
| JDBC present, feature enabled, bean present | Present | true | Present | Integration appears |
| User override | Present | true | Present | Custom bean retained |
| Incompatible dependency version | Present but wrong version | true | Present/absent | Binary compatibility error caught in test/build |

Use FilteredClassLoader to simulate a missing classpath quickly in ApplicationContextRunner. Use a standalone consumer to prove the Maven optional dependency genuinely does not propagate to runtime. Both methods complement each other.

Spring Boot documents using FilteredClassLoader in auto-configuration tests to simulate non-existent classes or packages. Reference: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html.

## 13. Common Mistakes to Avoid

1. **Placing @ConditionalOnClass on a @Bean method with an optional return type.** The JVM may have to load return/parameter types before the condition applies.
2. **Putting optional classes in the outer configuration constructor.** The outer config must be loaded before Spring evaluates nested bean conditions.
3. **Putting optional types in a superclass or interface.** The JVM must process the hierarchy when loading the outer class.
4. **Using optional types in fields or static initializers.** Resolution/initialization can occur too early.
5. **Unconditionally importing an optional configuration.** Direct @Import does not create a classpath guard by itself.
6. **Putting a class literal in a custom meta-annotation.** Composed @ConditionalOnClass must use name.
7. **Assuming a condition on the outer class guards every method in all situations.** Isolate method signatures containing optional types inside nested configurations as Boot recommends.
8. **Testing only on a full classpath.** Normal tests miss optional-boundary failures.
9. **Testing only with FilteredClassLoader.** You still need a standalone consumer artifact to verify the Maven dependency graph.
10. **Calling Class.forName unconditionally.** Can trigger linkage/initialization errors before conditions are processed.
11. **Catching NoClassDefFoundError and ignoring it.** This hides dependency bugs and incomplete configuration states.
12. **Confusing compile classpath with runtime classpath.** Successful IDE compilation does not prove the executable has all dependencies.
13. **Marking a dependency optional without documenting it.** Consumers will not know which artifact to add to enable the feature.
14. **Misusing provided or exclusions.** Dependencies required at runtime may be dropped from the executable.
15. **Letting core classes depend on optional implementations.** A core bean can drag optional types into the class-loading chain.
16. **Putting every integration into one giant configuration.** One missing optional class can break independent features.
17. **Not checking transitive dependencies.** The failing class might be a dependency of the optional class rather than the type called directly.
18. **Confusing NoSuchMethodError with NoClassDefFoundError.** One is typically a version mismatch; the other involves class linkage/initialization.
19. **Failing to distinguish an absent class from a class that failed initialization.** The message Could not initialize class requires finding the first exception.
20. **Verifying only that the bean is absent.** Also verify the context did not fail and core features still work.
21. **Not testing the positive branch.** Guards might be overly strict and inadvertently disable the integration even when dependencies exist.
22. **Using broad component scanning to discover integrations.** This can cause Spring to analyze optional classes outside protected boundaries.

## 14. Workflow for Designing Safe Optional Integrations

1. List dependencies needed only for integrations, not for core.
2. Mark Maven dependencies optional if consumers must opt into the integration explicitly.
3. Keep the outer auto-configuration referencing only core types and always-present Spring Boot APIs.
4. Create one nested static @Configuration per integration.
5. Place @ConditionalOnClass directly on the nested configuration, using name where appropriate.
6. Add @ConditionalOnProperty if the feature requires explicit enabling.
7. Put @Bean methods with optional return/parameter types inside the nested configuration.
8. Use @ConditionalOnBean when an underlying bean must exist.
9. Use @ConditionalOnMissingBean so consumers can override.
10. Avoid outer constructors, fields, superclasses, static initializers, and imports referencing optional types.
11. Use FilteredClassLoader to test missing classes/packages.
12. Build/install the artifact and create a standalone consumer.
13. Check the consumer's runtime dependency tree.
14. Run the core-only consumer and verify core still works.
15. Add the optional dependency, enable the feature, and verify the integration works.
16. Check version compatibility and exclusions if linkage errors persist.

## 15. Acceptance Checklist

- [ ] Identified the exact binary name in NoClassDefFoundError.
- [ ] Read the full cause chain and distinguished missing class from initialization failure.
- [ ] Inspected the consumer's runtime dependency tree.
- [ ] Optional dependencies are marked intentionally and documented.
- [ ] Outer auto-configuration does not reference optional types in hierarchy, fields, or constructors.
- [ ] Outer @Bean methods have no optional types in return/parameter signatures.
- [ ] Each integration has its own nested static configuration.
- [ ] @ConditionalOnClass is placed at the nested configuration level.
- [ ] Composed/meta-annotations use name instead of class literals.
- [ ] Optional bean methods reside only inside guarded configurations.
- [ ] Property conditions and bean conditions are placed at the right layers.
- [ ] No unconditional Class.forName or optional static initializers exist.
- [ ] LinkageError is never caught to suppress errors.
- [ ] Missing-classpath tests use FilteredClassLoader.
- [ ] Full-classpath and bean-dependency-present tests pass.
- [ ] User bean override tests pass if supported by the starter.
- [ ] Standalone consumer without the optional dependency still starts.
- [ ] Consumer dependency tree has no optional artifact when undeclared.
- [ ] Consumer enabling the integration after adding the dependency works properly.
- [ ] Inspected the artifact JAR and imports metadata.
- [ ] Distinguished missing-class errors from version incompatibility errors.

## 16. Self-Check Questions

**Question 1.** Why can a library compile yet fail in a consumer with NoClassDefFoundError?  
**Answer:** The library module's compile classpath has the dependency, but Maven does not propagate optional dependencies to consumers. Runtime may lack a class that an outer configuration or method signature referenced too early.

**Question 2.** Why is @ConditionalOnClass on a @Bean method not enough to protect an optional return type?  
**Answer:** The JVM may load or process the method signature before the method condition is evaluated. Spring Boot recommends extracting the method into a separate configuration class with a class-level condition.

**Question 3.** Why is @ConditionalOnClass safer at the configuration-class level?  
**Answer:** Spring Boot reads annotation metadata via ASM before loading the configuration class, allowing it to skip the class when the dependency does not exist.

**Question 4.** Why should nested static configurations be used?  
**Answer:** They isolate method signatures, fields, and implementations requiring optional APIs; the outer configuration remains loadable when the integration is absent.

**Question 5.** What does optional=true in Maven mean?  
**Answer:** The dependency is still used to build the declaring module, but it is not propagated transitively to consumers. Consumers must declare it themselves if they use that feature.

**Question 6.** How do ClassNotFoundException and NoClassDefFoundError differ?  
**Answer:** ClassNotFoundException usually comes from explicit class-loading APIs; NoClassDefFoundError is a LinkageError when the JVM needs a class for linking/execution or when the class previously failed initialization.

**Question 7.** Which tool tests an absent optional class in ApplicationContextRunner?  
**Answer:** FilteredClassLoader, such as new FilteredClassLoader("org.springframework.jdbc"), then assert the context has not failed and core beans remain present.

**Question 8.** What happens if the optional class is present, but no JdbcTemplate bean exists?  
**Answer:** The classpath condition matches, but ConditionalOnBean(JdbcTemplate.class) does not match, so the JDBC adapter bean is not created.

**Question 9.** Why should you avoid catching NoClassDefFoundError to ignore it?  
**Answer:** It is a serious linkage error; catching it can hide dependency/version bugs and leave the application running in an incomplete state.

**Question 10.** What should you check if the error message is Could not initialize class?  
**Answer:** Look for the first exception inside the static initializer or an earlier class initialization attempt. Do not assume a dependency JAR is missing.

## 17. Official References

- Spring Boot 3.3.13 Javadoc — ConditionalOnClass: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 Javadoc — FilteredClassLoader: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.3.13 Javadoc — ConditionalOnBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3.13 Javadoc — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Maven — Optional Dependencies and Dependency Exclusions: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Java SE 17 API — LinkageError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java SE 17 API — NoClassDefFoundError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html