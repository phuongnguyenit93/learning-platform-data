# Using Metadata and Class Conditions to Avoid Processing Unnecessary Integrations

## 1. Why Does a Custom Starter Need Early Filtering?

A Spring Boot library can support many technologies: HTTP clients, reporting SDKs, JSON codecs, database drivers, or messaging adapters. When an application adds a starter, the library's auto-configurations become candidates examined by Spring Boot. If every configuration scans packages, loads optional classes, creates beans, or probes external systems, startup wastes work on integrations the application does not use.

Spring Boot provides multiple layers to reduce that work:

1. **Auto-configuration imports list** determines which configurations are candidates.
2. **Auto-configuration metadata** allows Boot to early-filter candidates whose conditions definitely do not match.
3. **Class-level conditions** such as **@ConditionalOnClass** skip an integration configuration when the library is absent from the classpath.
4. **Nested configurations** isolate method signatures referencing optional libraries, preventing the JVM from having to load those types when the dependency is missing.
5. **AOT processing** can evaluate configurations and generate initialization code before the application runs, subject to classpath and Environment constraints.

These mechanisms are related but do not replace one another. Metadata helps filter candidates early; conditions decide whether a configuration is applied; AOT pre-generates part of the context processing result. Understanding each layer properly helps a starter start quickly and operate safely when optional dependencies are absent.

## 2. Distinguishing Spring Boot Metadata Files

There are three files commonly encountered in a custom starter. Their names look similar, but their purposes differ.

| File | Created or Maintained By | Purpose |
| --- | --- | --- |
| **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** | Starter author | Lists auto-configuration classes for Spring Boot discovery |
| **META-INF/spring-autoconfigure-metadata.properties** | spring-boot-autoconfigure-processor | Stores condition metadata for Boot to early-filter unsuitable auto-configurations |
| **META-INF/spring-configuration-metadata.json** | spring-boot-configuration-processor | Describes @ConfigurationProperties keys for IDEs, autocomplete, and configuration documentation |

### 2.1. AutoConfiguration.imports: Finding Candidates

A JAR containing auto-configuration needs the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line records the fully qualified name of an auto-configuration class:

~~~text
com.example.report.autoconfigure.ReportAutoConfiguration
com.example.report.autoconfigure.ReportWebAutoConfiguration
~~~

Spring Boot reads this file from JARs on the classpath to discover published configurations. Comments starting with the `#` character can be added.

This file **only lists candidates**. It does not prove the integration library is present, does not create beans, and does not replace conditions. A listed auto-configuration still needs appropriate conditions so it only activates in matching applications.

Auto-configurations should reside in a dedicated package, be loaded via the imports file, and not become targets of component scanning. Do not use @ComponentScan inside an auto-configuration to scan a large package area; if additional specific configurations or components are needed, use @Import.

### 2.2. spring-autoconfigure-metadata.properties: Early Filtering

Spring Boot has an annotation processor named **spring-boot-autoconfigure-processor**. The processor collects supported conditions on auto-configurations and generates the file:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

When this file is present, Spring Boot can use the metadata to **eagerly filter** auto-configurations that definitely do not match before deeply processing each configuration. For example, if an integration requires an SDK class and that class is not on the classpath, Boot can exclude the corresponding candidate early.

Benefits:

- Reduces the number of configurations that must be deeply processed.
- Avoids analyzing integration branches that will definitely not be used.
- Reduces condition evaluation work in later stages.
- Useful when a starter has many auto-configurations and many optional dependencies.

This file is generated at compile time. **Do not write or manually edit** this metadata file. Declare the annotation processor properly in the module containing the auto-configuration classes and verify that the file is packaged into the JAR.

Metadata only supports conditions recognized by the processor and Spring Boot version. It does not eliminate runtime condition evaluation when needed, and does not guarantee that every custom condition can be decided ahead of time.

### 2.3. spring-configuration-metadata.json: Assisting Configuration Authors

The file **META-INF/spring-configuration-metadata.json** serves a different purpose: describing properties declared with **@ConfigurationProperties**, such as key names, data types, descriptions, and value hints.

IDEs can use this file for autocomplete and to display help when users write application.yml or application.properties.

This file is typically generated by **spring-boot-configuration-processor**. It is not the file that the auto-configuration import selector uses to filter auto-configurations.

**Do not confuse the two processors:**

- **spring-boot-autoconfigure-processor** generates condition metadata for filtering auto-configurations.
- **spring-boot-configuration-processor** generates configuration metadata for IDEs and starter users.

A starter may need both processors if it both provides auto-configuration and publishes its own configuration keys.

## 3. Class Conditions: Loading an Integration Only When Required Classes Are Present

### 3.1. @ConditionalOnClass and @ConditionalOnMissingClass

**@ConditionalOnClass** allows a configuration to be applied when the required class is on the classpath. **@ConditionalOnMissingClass** does the opposite: the configuration is only applied when the specified class is absent.

Example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.report.ReportClient")
public class ReportAutoConfiguration {
    // Configuration for ReportClient.
}
~~~

When com.acme.report.ReportClient is not on the classpath, this auto-configuration is not applied.

If a condition is needed for multiple classes, multiple values can be listed. The condition only matches when all required classes are satisfied. Choose the exact classes representing the capability actually used; do not check an overly generic class that causes a feature to be enabled even when the specific integration lacks dependencies.

### 3.2. Why ASM Metadata Matters

Spring Boot reads configuration annotation metadata using ASM. ASM can read information from bytecode without loading and initializing the class in the normal way.

Therefore, for a class-level condition, you can use:

~~~java
@ConditionalOnClass(SomeOptionalClient.class)
~~~

even when that class is not on the consuming application's runtime classpath. Annotation metadata is read as type names in bytecode.

If you want to avoid a compile-time reference to the optional library, you can use the name attribute:

~~~java
@ConditionalOnClass(name = "com.acme.report.ReportClient")
~~~

name accepts the class name as a String. This approach is useful when the integration library is an optional dependency and the auto-configuration module does not want to expose its type in public APIs.

When using @ConditionalOnClass or @ConditionalOnMissingClass inside a meta-annotation to create a composed annotation, you must use name. Referencing a class via value in a meta-annotation is not handled the same way.

### 3.3. Placing Conditions on Configuration Classes Instead of Only on @Bean Methods

There is an important difference between a condition on a class and a condition on a method.

The following snippet is risky when ReportClient is optional:

~~~java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.acme.report.ReportClient")
    ReportService reportService(ReportClient client) {
        return new DefaultReportService(client);
    }
}
~~~

Before the method-level condition is applied, the JVM or introspection may have to load the class and process method signatures. If the method's return type or parameter references a missing class, the application may encounter a linkage error before the condition can exclude the method.

A safer approach is to **isolate every method depending on an optional type inside a nested @Configuration with a class-level condition**:

~~~java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.report.ReportClient")
    static class ReportClientConfiguration {

        @Bean
        ReportService reportService(ReportClient client) {
            return new DefaultReportService(client);
        }
    }
}
~~~

The nested configuration is only processed when the class condition matches. When the SDK is not on the classpath, Spring can skip this branch before processing methods whose signatures depend on the SDK.

In a large auto-configuration module, you can also place the condition on the top-level auto-configuration class if that entire configuration only makes sense when the SDK is present. Keep the class holding the condition free of direct references to optional types; move methods requiring the SDK into a nested configuration.

### 3.4. Combining Class Conditions with Property and Bean Conditions

A classpath condition answers whether the library can be used. A property condition answers whether the operator has enabled the feature. A bean condition allows the application to replace the default implementation.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.report.ReportClient")
@ConditionalOnProperty(
        prefix = "app.report",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService(ReportClient client) {
            return new DefaultReportService(client);
        }
    }
}
~~~

Conditions combine with logical AND. When the SDK is missing or the property is disabled, the configuration is not applied. When both conditions match, the default bean is only created if the application has not already provided a ReportService.

Place @ConditionalOnMissingBean on the auto-configuration or bean method matching the starter's contract. Bean conditions depend on bean definitions processed up to evaluation time; Spring Boot recommends using them in auto-configurations because auto-configurations are processed after user-defined bean definitions.

## 4. Structuring a Custom Starter to Avoid Pulling In and Processing Unused Dependencies

A custom starter is typically split into two modules:

~~~text
report-spring-boot-autoconfigure
    - Auto-configuration classes
    - Class/property/bean conditions
    - Configuration properties
    - Annotation processor metadata

report-spring-boot-starter
    - Dependency bundle for the default experience
    - Depends on the autoconfigure module
    - Declares the SDKs required by features enabled by default in the starter
~~~

In the autoconfigure module, the dependency on the SDK can be marked optional in Maven or compile-only in Gradle if the design expects consumers to choose the library themselves. The starter module declares the dependencies needed for the default experience.

Maven dependency example in the autoconfigure module:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>report-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
~~~

Gradle example:

~~~kotlin
dependencies {
    compileOnly("com.acme:report-sdk:1.2.0")
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
}
~~~

Class conditions guard the integration branch when the SDK is absent. Optional/compile-only dependencies control whether the library is transitively passed to consumers. The two mechanisms serve two different layers; declaring optional does not automatically replace a class condition.

If the default starter requires the SDK, the starter module must declare that dependency directly and in a scope suitable for the application runtime. If the starter has multiple optional features, it can be split into smaller starters by capability instead of pulling all SDKs into every application.

## 5. Complete Example: Report Starter That Creates a Bean Only When the SDK Is Present

The example below uses Java 17 and Spring Boot 3.5.0. To keep the demo project self-compiling, we create a small ReportClient class in source. In a real starter, this class comes from a separate SDK and the dependency is declared optional in the autoconfigure module.

The example tests three scenarios:

1. SDK present and property enabled: creates the default service.
2. SDK absent: skips the entire integration while the context still starts.
3. Property disabled: does not create the service even though the SDK is present.

### 5.1. Directory Structure

~~~text
report-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── example/
    │   │   │   ├── sdk/
    │   │   │   │   └── ReportClient.java
    │   │   │   ├── report/
    │   │   │   │   └── ReportService.java
    │   │   │   └── autoconfigure/
    │   │   │       └── ReportAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── example/
                └── autoconfigure/
                    └── ReportAutoConfigurationTests.java
~~~

### 5.2. File pom.xml

Maven Compiler Plugin 3.12.0 and later supports configuring annotation processors in the way Spring Boot recommends. The example uses 3.13.0 and the processor with matching Spring Boot version 3.5.0.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>report-autoconfigure-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.5.0</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

If the project also has @ConfigurationProperties and wants to generate metadata for IDEs, add spring-boot-configuration-processor to annotationProcessorPaths as a separate processor. That processor serves spring-configuration-metadata.json; it does not replace spring-boot-autoconfigure-processor.

### 5.3. File ReportClient.java

This is a mock SDK so the example can compile standalone:

~~~java
package example.sdk;

public final class ReportClient {

    public String status() {
        return "report-client-ready";
    }
}
~~~

### 5.4. File ReportService.java

~~~java
package example.report;

public interface ReportService {
    String status();
}
~~~

### 5.5. File ReportAutoConfiguration.java

~~~java
package example.autoconfigure;

import example.report.ReportService;
import example.sdk.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnClass(name = "example.sdk.ReportClient")
@ConditionalOnProperty(
        prefix = "app.report",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService(ReportClient client) {
            return client::status;
        }
    }
}
~~~

Key points:

- The auto-configuration class uses the class name as a String in @ConditionalOnClass.
- The auto-configuration class has no method signature directly referencing the SDK.
- The method accepting ReportClient sits inside a nested configuration, processed only when class-level conditions match.
- @ConditionalOnProperty allows disabling the feature even when the SDK is present.
- @ConditionalOnMissingBean allows the application to replace the default ReportService.

In a real autoconfigure module, if ReportClient comes from an optional SDK dependency, remove the mock class from the demo project and declare the SDK in the build file with the appropriate scope.

### 5.6. File AutoConfiguration.imports

Create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
example.autoconfigure.ReportAutoConfiguration
~~~

### 5.7. File ReportAutoConfigurationTests.java

~~~java
package example.autoconfigure;

import example.report.ReportService;
import example.sdk.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    @Test
    void createsReportServiceWhenSdkIsPresentAndFeatureIsEnabled() {
        runner.withPropertyValues("app.report.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);

                    assertThat(context.getBean(ReportService.class).status())
                            .isEqualTo("report-client-ready");
                });
    }

    @Test
    void skipsIntegrationWhenSdkIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(ReportClient.class))
                .withPropertyValues("app.report.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                });
    }

    @Test
    void skipsIntegrationWhenFeatureIsDisabled() {
        runner.withPropertyValues("app.report.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnService() {
        runner.withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasBean("customReportService");
                    assertThat(context).doesNotHaveBean("reportService");

                    assertThat(context.getBean(ReportService.class).status())
                            .isEqualTo("custom-report-service");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {

        @Bean
        ReportService customReportService() {
            return () -> "custom-report-service";
        }
    }
}
~~~

### 5.8. Running Tests

In the directory containing pom.xml, using JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

**Expected result:** four JUnit tests pass and Maven finishes with BUILD SUCCESS if dependencies download successfully. This is the expected outcome of the example, not an actual run result. The tests do not call System.out.println, so there is no fixed business stdout; reports are in target/surefire-reports.

The second test is important evidence: the SDK is hidden from the ApplicationContext's classloader, yet the context still starts and the integration bean is not registered. This test verifies the safety of the class condition; it does not replace checking the dependency graph of the published artifact.

## 6. Enabling the Annotation Processor to Generate Auto-Configuration Metadata

### 6.1. Maven

In the module containing auto-configuration classes, declare spring-boot-autoconfigure-processor on the Maven Compiler Plugin's annotation processor path:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-autoconfigure-processor</artifactId>
                <version>3.5.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Use an appropriate Maven parent/BOM to keep versions aligned with the module's Spring Boot version. If there are multiple annotation processors, declare all of them in the list; do not accidentally drop another processor when replacing the annotation processor path configuration.

### 6.2. Gradle

With Gradle, declare the processor in the annotationProcessor configuration:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

If the module also needs metadata for @ConfigurationProperties, add the corresponding processor:

~~~kotlin
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
~~~

Do not put an annotation processor in implementation just to make classes present on the runtime classpath. The processor is a build-time tool; it should run in the configuration dedicated to annotation processing.

### 6.3. The Processor Must Run in the Right Module

In a multi-module project, place spring-boot-autoconfigure-processor in the module that actually contains the @AutoConfiguration sources. Adding the processor only to an empty starter bundle will not generate metadata for sources located in a separate autoconfigure module.

After compiling/packaging, verify that the JAR contains both:

- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.
- META-INF/spring-autoconfigure-metadata.properties.

If the metadata file is missing, check the annotation processor path, compiler logs, module build, and JAR contents. Auto-configuration can still run via runtime conditions, but Boot will lack this file to perform early filtering based on generated metadata.

## 7. AOT: Shifting Some Configuration Decisions to Build Time

### 7.1. AOT Differs from Auto-Configuration Metadata

Both mechanisms are often mentioned together because both improve startup, yet their scopes differ:

| Mechanism | Timing | Scope |
| --- | --- | --- |
| Auto-configuration metadata | Library compile/package time | Early-filters auto-configuration candidates based on supported condition metadata |
| Spring AOT processing | Application build time | Analyzes ApplicationContext and generates necessary initialization code and bytecode/hints |
| Runtime condition evaluation | When the application runs in normal mode | Evaluates conditions against runtime classpath and Environment |

Auto-configuration metadata does not generate all of an application's bean definitions. AOT processing goes deeper: it analyzes the context at build time and generates Java/bytecode and runtime hints to reduce work required at startup.

### 7.2. Conditions Are Evaluated at Build Time

For an AOT-processed application, the classpath must be fully determined at build time. Conditions affecting whether a bean exists or not are evaluated against the Environment during the AOT build.

That means:

- The dependency classpath used at build time must match the running artifact.
- Profiles affecting bean presence must be selected when building AOT.
- Properties such as app.report.enabled, if they decide whether to create a bean, are evaluated at build time.
- A bean already created during AOT cannot be disabled again by changing a property at runtime.
- Do not design feature flags expecting to arbitrarily alter bean structure after the AOT artifact has been built.

For example, if you build AOT with app.report.enabled=true and the report bean is created, changing the property to false at runtime is not equivalent to running the application in normal mode. Configure the Environment/profile accurately when running AOT processing.

If an application needs to toggle an integration dynamically via a runtime property, consider keeping that decision at runtime or designing the bean to always exist while controlling its internal behavior via runtime configuration. The choice depends on whether the property changes behavior or changes bean existence.

### 7.3. RuntimeHints and Native Image

AOT can generate or consume RuntimeHints for operations difficult to infer via static analysis, such as:

- Reflection.
- Reading resources by name or pattern.
- Serialization.
- JDK dynamic proxies.

If a starter's SDK uses reflection or loads resource files dynamically, a class condition does not automatically satisfy native image requirements. Appropriate runtime hints must be supplied, such as via RuntimeHintsRegistrar and the Spring Boot/Spring Framework hints import mechanism.

Class conditions answer whether the integration is applied. Runtime hints describe dynamic operations that the runtime/native image must allow. These are two separate responsibilities.

### 7.4. When Should You Use AOT?

AOT is suitable when:

- You want to reduce application startup time.
- The classpath and bean set are relatively stable between build and runtime.
- The build/deploy process controls profiles and properties affecting conditions.
- You need to build a native image or leverage pre-generated initialization code.

AOT must be tested on the AOT-processed artifact, because regular context tests do not prove that native image or AOT runtime hints are complete. With Spring Boot, ApplicationContextRunner does not run inside a native image; use appropriate tests for native/AOT integration when compatibility confirmation is needed.

## 8. How to Verify Metadata and Filtering Behavior

### 8.1. Inspecting Files in the JAR

After building:

~~~bash
mvn clean package
jar tf target/report-autoconfigure-demo-1.0.0-SNAPSHOT.jar
~~~

Look for the paths:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

If the project has @ConfigurationProperties and the configuration processor, you may also see:

~~~text
META-INF/spring-configuration-metadata.json
~~~

On Windows PowerShell, you can extract metadata to read it:

~~~powershell
jar xf target/report-autoconfigure-demo-1.0.0-SNAPSHOT.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content META-INF/spring-autoconfigure-metadata.properties
~~~

Do not edit generated files to force a condition to match. Fix the annotations/source or build configuration and re-run the build.

### 8.2. Checking Runtime Conditions

Run the application with --debug to view the Condition Evaluation Report. The report helps identify which auto-configurations matched, did not match, and which condition was the reason.

In tests, you can use ConditionEvaluationReportLoggingListener with ApplicationContextRunner to print the report at INFO or DEBUG level. Use FilteredClassLoader to test branches when the SDK is missing.

A test suite should include:

| SDK | Property | Outcome |
| --- | --- | --- |
| Present | Missing, enabled by default | Bean is created |
| Present | true | Bean is created |
| Present | false | Bean is not created |
| Absent | true | Integration is skipped |
| Absent | false | Integration is skipped |
| Present | true and user bean already present | Default bean backs off |

### 8.3. Inspecting Consumer Artifacts

Tests in the autoconfigure module usually have the SDK on the test classpath. Therefore, tests using FilteredClassLoader are necessary but not sufficient to prove a consumer's dependency graph is correct.

Also check:

- Maven dependency tree or Gradle runtime classpath of a sample application.
- The published autoconfigure JAR contains the imports file and autoconfigure metadata.
- The starter bundle only pulls in dependencies needed for the default experience.
- An application using only the autoconfigure module without installing the SDK can start and skip the integration.
- An application adding the standard starter with the SDK runtime dependency activates the integration.

## 9. Optimizing Conditions Without Making Startup Unpredictable

### 9.1. Prefer Cheap Conditions Evaluable from Metadata

Class presence and properties are simple signals. Place class conditions at configuration boundaries so Boot can skip the entire integration branch when the SDK is absent.

Do not perform heavy work inside conditions:

- Do not open database or broker connections.
- Do not send HTTP requests to probe external services.
- Do not read large files or scan the entire filesystem.
- Do not create business beans to decide a condition.
- Do not use a condition as a place to run health checks.

Conditions should be fast, deterministic configuration decisions. Actual connectivity checks belong to client/health indicator lifecycles or integration tests.

### 9.2. Avoid Broad Component Scanning in Auto-Configuration

Auto-configurations are loaded via the imports file. There is no need to use component scan to rediscover classes the starter already knows explicitly.

If an integration has a few sub-configurations or specific components, use @Import to declare them explicitly. This clarifies scope and avoids scanning packages containing unrelated components.

### 9.3. Use Bean Conditions in the Right Place

@ConditionalOnBean and @ConditionalOnMissingBean typically depend on bean definitions registered up to the time the condition is evaluated. Spring Boot recommends placing these bean conditions on auto-configurations so they are evaluated after user-defined bean definitions.

Do not use bean conditions to replace class conditions for an optional SDK. Class conditions solve whether the library can be loaded; bean conditions solve whether a bean has already been supplied by the application.

### 9.4. Do Not Overuse SpEL Conditions Referencing Beans

@ConditionalOnExpression can be used for expression logic, but referencing a bean in SpEL can cause that bean to be instantiated very early during context refresh. That bean may not be fully post-processed, such as configuration properties binding, and its state may be incomplete.

If you only check a property, use @ConditionalOnProperty. If you check a class, use @ConditionalOnClass. Only use SpEL when an expression is truly necessary and does not inadvertently trigger early bean instantiation.

### 9.5. Auto-Configuration Order Is Not Bean Instantiation Order

@AutoConfigureBefore, @AutoConfigureAfter, and @AutoConfigureOrder control the order in which bean definitions are registered during auto-configuration processing. They do not guarantee the order in which bean instances are instantiated; that depends on dependency injection and relationships such as @DependsOn.

Use ordering to resolve configuration dependencies, not as a startup optimization trick or to force an SDK to initialize before everything else.

## 10. Common Mistakes

1. **Creating only AutoConfiguration.imports and assuming it is already optimized.** This file finds candidates; conditions and metadata decide which branches must be processed.
2. **Forgetting spring-boot-autoconfigure-processor.** Runtime conditions can still run, but the optimization metadata file is not generated.
3. **Placing the processor in an empty starter instead of the autoconfigure module.** The processor must run in the module containing the auto-configuration sources.
4. **Confusing autoconfigure metadata with configuration metadata JSON.** One file helps filter conditions; the other supports IDEs and property documentation.
5. **Hand-writing spring-autoconfigure-metadata.properties.** The file is generated by the processor; manual edits are error-prone and get overwritten.
6. **Putting an optional SDK type in a method signature of a configuration without a class boundary.** The JVM may load the type before the method-level condition takes effect.
7. **Attaching @ConditionalOnClass only to a @Bean method.** For optional return/parameter types, isolate the method in a nested configuration with a class-level condition.
8. **Using a class literal in a meta-annotation condition.** For composed annotations, use the name attribute.
9. **Using broad component scanning in auto-configuration.** This can cause Spring to process many unrelated classes.
10. **Assuming @ConditionalOnClass replaces dependency declarations.** The condition only decides whether to apply configuration; it does not add the SDK to the runtime classpath.
11. **Marking a dependency optional without re-declaring it in the starter.** Applications adding the starter may lack an SDK needed by default features.
12. **Using @ConditionalOnMissingBean instead of a class condition.** Bean conditions do not guard against loading optional classes.
13. **Making network or database calls inside conditions.** Startup becomes slow, environment-dependent, and hard to test.
14. **Assuming AOT still allows property changes to alter bean presence at runtime.** Conditions affecting beans are evaluated during the AOT build.
15. **Forgetting RuntimeHints for reflection/resources in native image.** Class conditions do not automatically register required dynamic operations.
16. **Testing only when the SDK is present.** You must test missing-classpath scenarios with FilteredClassLoader.
17. **Checking only the test context without inspecting the JAR.** The published artifact must contain the right imports file and metadata.
18. **Using @AutoConfigureBefore to force instance instantiation order.** The annotation only controls bean definition order.

## 11. Pre-Release Checklist for a Custom Starter

- [ ] Every auto-configuration is listed in AutoConfiguration.imports.
- [ ] Auto-configurations are not inadvertently rediscovered by component scan.
- [ ] Optional SDKs are declared with the proper scope in the autoconfigure module.
- [ ] The starter module declares dependencies needed for the default experience.
- [ ] @ConditionalOnClass guards SDK-dependent integrations.
- [ ] Optional types are isolated inside nested configurations.
- [ ] Property conditions have clear defaults if a feature has an enable/disable flag.
- [ ] @ConditionalOnMissingBean allows applications to replace default beans when appropriate.
- [ ] spring-boot-autoconfigure-processor runs in the module containing auto-configuration.
- [ ] The JAR contains spring-autoconfigure-metadata.properties.
- [ ] That file is not confused with spring-configuration-metadata.json.
- [ ] Tests cover both SDK present and SDK absent via FilteredClassLoader.
- [ ] Tests cover feature property enabled/disabled and user bean back-off.
- [ ] Condition Evaluation Report can explain skipped branches.
- [ ] If using AOT, Environment/profiles are configured at build time.
- [ ] If using native image, RuntimeHints for reflection/resources/serialization/proxies have been verified.
- [ ] Verified actual consumer dependency graph and JAR contents.

## 12. Self-Check Questions

**Question 1.** What is the job of AutoConfiguration.imports?  
**Answer:** Listing auto-configuration classes that Spring Boot can discover inside a JAR.

**Question 2.** Which processor generates spring-autoconfigure-metadata.properties?  
**Answer:** spring-boot-autoconfigure-processor.

**Question 3.** How does this metadata file speed up startup?  
**Answer:** Boot uses supported condition metadata to early-filter non-matching auto-configurations before deep processing.

**Question 4.** How is spring-configuration-metadata.json different?  
**Answer:** It describes configuration properties so IDEs can support autocomplete/documentation; it is not an auto-configuration filtering file.

**Question 5.** Why can @ConditionalOnClass check a class that is not on the runtime classpath?  
**Answer:** Spring Boot reads annotation metadata using ASM, without needing to load the class in the normal way to obtain type names.

**Question 6.** Why can a condition on a @Bean method be too late when the return type is an optional class?  
**Answer:** The JVM/introspection may have to load the class and method signatures before the method condition is applied; a nested configuration establishes a safe class-level boundary.

**Question 7.** Should an HTTP request be made in a condition to confirm an SDK works?  
**Answer:** No. Conditions must be fast and deterministic; connectivity checks belong in health checks or integration tests.

**Question 8.** Does AOT allow changing app.report.enabled to toggle a bean after building?  
**Answer:** No, if that property determines bean presence during AOT processing; conditions are evaluated against the build-time Environment.

**Question 9.** Does a class condition automatically add a dependency to the runtime classpath?  
**Answer:** No. The dependency must be supplied by the consumer or starter; the condition only decides whether to apply configuration.

**Question 10.** What problem do RuntimeHints solve?  
**Answer:** Describing operations such as reflection, resource loading, serialization, and JDK proxies that must be permitted in AOT/native environments.

## Official References

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, candidate imports, class conditions, and autoconfigure metadata: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — AutoConfigurationImportFilter: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html
- Spring Boot 3.5 API — AutoConfigurationMetadata: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationMetadata.html
- Spring Boot 3.5 Reference — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/3.5/reference/packaging/aot.html
- Spring Boot 3.5 How-to — Ahead-of-Time Processing and condition limitations: https://docs.spring.io/spring-boot/3.5/how-to/aot.html
- Spring Framework Reference — Ahead-of-Time Optimizations and RuntimeHints: https://docs.spring.io/spring-framework/reference/core/aot.html

**Takeaway:** AutoConfiguration.imports finds candidates; spring-autoconfigure-metadata.properties helps Boot filter early; @ConditionalOnClass guards branches needing a library; nested configurations keep optional types from loading prematurely. AOT takes one step further by processing the context at build time, so the classpath and bean-deciding properties must be chosen before packaging the artifact.
