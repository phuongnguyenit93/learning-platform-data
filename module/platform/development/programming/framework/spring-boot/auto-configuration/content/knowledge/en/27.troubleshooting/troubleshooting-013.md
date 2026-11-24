# Side Effects of Accidentally Scanning Auto-Configuration Packages or Directly Importing Internal Configurations

## 1. Why Can an Auto-Configuration Run Unexpectedly?

A Spring Boot library typically provides auto-configuration to register default beans when an application adds its starter. That configuration may depend on the classpath, properties, web stack, or application-provided beans.

Spring Boot has a dedicated loading path for auto-configuration: classes are published in the JAR's `AutoConfiguration.imports` file, then processed in the auto-configuration pipeline with appropriate ordering and conditions.

Problems arise when an application or library accidentally widens component scanning to the package containing auto-configuration classes. A class annotated with `@AutoConfiguration` is also a `@Configuration` class. Therefore, if its package falls within `@ComponentScan` scope, Spring can discover the class as a regular configuration component.

Another scenario occurs when an application directly imports an internal configuration class inside the library. The internal configuration can then be registered without going through the conditions on the outer auto-configuration class.

Consequences can include:

- Default beans appearing even though the feature property is disabled.
- Exclusions failing to block configurations loaded via component scan or direct `@Import`.
- `@ConditionalOnMissingBean` evaluating too early and missing application custom beans.
- Duplicate bean names causing `BeanDefinitionOverrideException`.
- Multiple beans of the same type making injection ambiguous and causing `NoUniqueBeanDefinitionException`.
- Optional integrations loading even when their dependency or feature should stay inactive.
- Unexpected beans, controllers, repositories, or security configurations entering the application.
- Auto-configuration runner tests behaving differently from the real application with broad component scanning.

This lesson uses **Java 17 and Spring Boot 3.3.13** as a baseline. The principles below apply to Spring Boot 3.x auto-configuration architecture.

## 2. Distinguishing Component Scanning from Auto-Configuration Imports

Both mechanisms can bring configuration classes into the `ApplicationContext`, yet their purposes and processing order differ.

### 2.1. Component Scanning

`@ComponentScan` searches for matching classes within specified packages. Common stereotypes discovered include:

- `@Component`.
- `@Service`.
- `@Repository`.
- `@Controller` and `@RestController`.
- `@Configuration`.
- Custom annotations meta-annotated with `@Component`.

`@SpringBootApplication` includes `@ComponentScan`. Without customizing scan packages, the package of the `@SpringBootApplication`-annotated class is the default scan root.

Example:

~~~java
package com.example.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
}
~~~

With this layout, default component scanning focuses on `com.example.app` and its subpackages.

If changed to:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme"
})
public class Application {
}
~~~

Spring scans both `com.acme` and its subpackages. If the Acme library places auto-configurations or helper `@Configuration` classes there, those classes can be discovered as components.

### 2.2. Auto-Configuration Imports

Spring Boot looks for the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file lists auto-configuration classes published by the library, one fully qualified class name per line:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration
~~~

Spring Boot loads these classes inside the auto-configuration mechanism, which applies exclusions, ordering, and conditions before registering configurations.

### 2.3. Why Can `@AutoConfiguration` Still Be Found by Component Scanning?

`@AutoConfiguration` is meta-annotated with `@Configuration`. `@Configuration` itself is a Spring component stereotype. Consequently, an auto-configuration class can become a component-scanner candidate if its package is scanned.

This does not mean component scanning is a valid way to publish auto-configurations. Spring Boot documentation requires auto-configurations to be loaded solely by declaring them in `AutoConfiguration.imports`, placed in a dedicated package, and never targeted by component scanning.

**Design rule:** Auto-configuration is an entry point managed by Spring Boot; component scanning is for application-scoped components.

## 3. Processing Pipelines and Key Differences

The two loading paths can be visualized as follows:

~~~text
AUTO-CONFIGURATION PATH
AutoConfiguration.imports
          |
          v
Candidate set
          |
          v
Exclusions and auto-configuration ordering
          |
          v
Auto-configuration conditions
          |
          v
Register bean definitions
          |
          v
Instantiate beans by dependency


COMPONENT SCAN / DIRECT @Import PATH
@ComponentScan or @Import
          |
          v
Discover / import configuration class
          |
          v
Conditions directly on class or bean method
          |
          v
Register bean definitions
          |
          v
Instantiate beans by dependency
~~~

Key points to remember:

1. Component scanning does not automatically apply `AutoConfigurationImportSelector` exclusion lists.
2. Direct `@Import` does not place a class into Boot's auto-configuration candidate list for ordering by `@AutoConfigureBefore` or `@AutoConfigureAfter`.
3. Conditions attached directly to the class or bean method are still evaluated when scanned/imported.
4. Conditions on an outer auto-configuration class do not automatically transfer onto a helper configuration scanned independently.
5. `@ConditionalOnBean` and `@ConditionalOnMissingBean` see only bean definitions already processed at evaluation time. The auto-configuration path is designed to run after user-defined bean definitions; configurations scanned as regular configurations may be processed at a different point.

Do not assume every condition is ignored when scanning the wrong package. Conditions on the scanned class itself remain active. The problem is that the loading path changed, so exclusions, ordering, and outer-configuration conditions may no longer guard child configurations.

## 4. Side Effects of Scanning the Wrong Package

### 4.1. Beans Appear Even When the Feature Property Is Off

Suppose a library has:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

A `false` property stops the outer auto-configuration from applying. Along the proper loading path, the helper `ReportsClientConfiguration` is imported only when `ReportsAutoConfiguration`'s condition matches.

Yet if the application directly scans the package containing the helper:

~~~java
@ComponentScan("com.acme.reports.autoconfigure")
~~~

the component scanner can discover `ReportsClientConfiguration` independently. Bean methods inside the helper are processed even though the outer configuration's property is `false`.

As a result, the feature is disabled at the auto-configuration level yet its beans still appear via an alternate loading path.

### 4.2. Exclusions No Longer Block the Configuration

An application may exclude the auto-configuration:

~~~java
@SpringBootApplication(
        excludeName =
                "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class Application {
}
~~~

This exclusion governs importing candidates in the auto-configuration mechanism.

If the same class is also found by component scanning, the component scanner can still register it as a regular configuration class. Exclusions are not a global filter across every configuration-loading path.

Similarly, if the application directly `@Import`s an internal configuration, excluding the outer auto-configuration name does not automatically exclude that internal configuration.

### 4.3. Ordering Is Bypassed

Annotations such as:

~~~java
@AutoConfigureBefore(...)
@AutoConfigureAfter(...)
@AutoConfiguration(beforeName = "...")
@AutoConfiguration(afterName = "...")
~~~

are used to order auto-configurations in Spring Boot's pipeline.

If an auto-configuration is component-scanned or directly `@Import`ed, do not expect those ordering metadata attributes to control order the way they do when loaded via `AutoConfiguration.imports`.

This can cause bean conditions to observe a different state, especially when two configurations provide default beans or depend on beans registered by the other.

Auto-configuration ordering also governs only bean definition registration order. Actual object creation order is still determined by dependencies and `@DependsOn`.

### 4.4. `@ConditionalOnMissingBean` Evaluates at the Wrong Time

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

`@ConditionalOnMissingBean` relies on bean definitions already processed when the condition runs.

In normal auto-configuration, Spring Boot loads auto-configurations after user-defined bean definitions. Thus, application custom beans are already registered so default beans can back off.

If a helper configuration is component-scanned and processed like regular application configuration, it may be evaluated before other user configurations are processed. The condition may then miss the custom bean.

Symptoms can include:

- Default bean still gets registered.
- Multiple candidates of the same type exist.
- Duplicate bean names fail registration.
- Outcomes depend on configuration processing order.

This is one reason Spring Boot recommends placing `@ConditionalOnBean` and `@ConditionalOnMissingBean` on auto-configuration classes or bean methods in the auto-configuration path, rather than using them as general bean-selection mechanisms across scanned configurations.

### 4.5. Optional Integrations Load Unexpectedly

Suppose an outer auto-configuration has:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.optional.PdfSdk")
@ConditionalOnProperty(
        prefix = "acme.reports.pdf",
        name = "enabled",
        havingValue = "true")
@Import(PdfClientConfiguration.class)
public class PdfAutoConfiguration {
}
~~~

If an application directly imports `PdfClientConfiguration`, the conditions on `PdfAutoConfiguration` do not automatically apply to the helper.

If the helper references optional classes absent from the classpath, class analysis or loading can fail with errors like `NoClassDefFoundError`. If the dependency is present while the property is off, the helper can still create unwanted beans.

Any helper carrying optional dependency boundaries must be designed so it cannot be safely loaded solely via a parent class condition if it could ever be imported independently.

### 4.6. Bean Pollution and Injection Errors

Overly broad package scanning can pull non-application components into the context:

- An internal service not intended for consumers.
- A repository binding to an unconfigured data source.
- A controller exposing unexpected endpoints.
- A security filter or configuration altering the filter chain.
- Two implementations of the same type making injection ambiguous.

Common errors:

~~~text
NoUniqueBeanDefinitionException
BeanDefinitionOverrideException
NoSuchBeanDefinitionException
NoClassDefFoundError
~~~

Exact exception names depend on the collision type and when beans are instantiated.

### 4.7. Tests and Production Can Differ

A test using:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(ReportsAutoConfiguration.class));
~~~

tests the specified auto-configuration path. It does not reproduce a broad `@ComponentScan` in the real application.

Consequently, auto-configuration unit tests can pass while the real application still loads helpers via component scan. Consumer tests using the application's real package scanning and starter JAR are needed.

## 5. Where Should Application Packages Be Placed?

### 5.1. Place the Main Application Class in the Application's Root Package

Good structure:

~~~text
com.example.app
├── Application.java
├── customer
│   ├── CustomerController.java
│   └── CustomerService.java
└── billing
    ├── BillingController.java
    └── BillingService.java

com.acme.reports
├── ReportClient.java
└── autoconfigure
    ├── ReportsAutoConfiguration.java
    └── internal
        └── ReportsClientConfiguration.java
~~~

Main class:

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

The default scan root is `com.example.app`. Package `com.acme.reports` sits outside the application's component scan area; Spring Boot still discovers `ReportsAutoConfiguration` via `AutoConfiguration.imports`.

### 5.2. Avoid the Default Package

Never place the main class or Java classes in the default package (no `package` declaration).

The default package can force scanning mechanisms to read classes across many JARs on the classpath. That makes scan scope hard to control and can introduce unexpected components.

Use reverse-domain-name packages, such as `com.example.app`.

### 5.3. When an Application Has Multiple Business Packages

If scanning multiple packages belonging to the application itself is needed, use marker classes to pinpoint each area:

~~~java
@SpringBootApplication(scanBasePackageClasses = {
        Application.class,
        BillingPackage.class,
        CustomerPackage.class
})
public class Application {
}
~~~

Marker classes should reside in packages owned by the application source code. Never use a marker class from an external library to inadvertently widen the scan root into vendor packages.

`scanBasePackageClasses` and `scanBasePackages` control component scanning. They do not replace specialized mechanisms like `@EntityScan` or `@ConfigurationPropertiesScan`.

### 5.4. Do Not Widen the Scan Root to Entire Dependency Namespaces

Risky example:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme",
        "org.springframework"
})
public class Application {
}
~~~

This scope is far too broad. Spring may read configurations/components inside numerous libraries that the application never intended to manage via component scan.

Scan only packages the application owns. Spring Boot libraries should publish their own auto-configurations via the imports mechanism.

## 6. Designing Custom Auto-Configurations Properly

### 6.1. Auto-Configuration as the Entry Point

An auto-configuration class should:

- Carry the `@AutoConfiguration` annotation.
- Have appropriate classpath, property, or bean conditions.
- Be published in `AutoConfiguration.imports`.
- Reside outside packages scanned by consumer applications.
- Not enable `@ComponentScan` to locate helpers.
- Use explicit `@Import` to load required internal configurations.

Example:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

### 6.2. Explicitly Imported Helper Configuration

~~~java
package com.acme.reports.autoconfigure.internal;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    public ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

This helper is imported by the root auto-configuration when the root condition is satisfied.

In real libraries, helper classes can be kept in internal packages or nested configurations to discourage consumers from depending on implementation classes. If a helper is not intended as public API, do not encourage consumers to import it directly.

### 6.3. `AutoConfiguration.imports` Lists Only Entry Points

Create file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Do not list a helper configuration as a separate auto-configuration candidate if it is purely an implementation detail imported by the root class.

### 6.4. Do Not Use Component Scan Inside Auto-Configuration

Do not write:

~~~java
@AutoConfiguration
@ComponentScan("com.acme.reports")
public class ReportsAutoConfiguration {
}
~~~

This ties bean registration scope to package layout and stereotype annotations on every class in that package.

Use:

~~~java
@AutoConfiguration
@Import({
        ReportsClientConfiguration.class,
        ReportsMetricsConfiguration.class
})
public class ReportsAutoConfiguration {
}
~~~

An explicit import list tells reviewers precisely which configurations activate and lets internal packages be refactored without shifting scan scope.

## 7. Distinguishing Auto-Configuration Imports from Direct Helper Imports

Not every `@Import` is wrong. Separate these two scenarios.

### 7.1. Valid: Root Auto-Configuration Imports Helper

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

Spring Boot loads the root class via `AutoConfiguration.imports`. The root condition determines whether the helper is imported. The helper is imported explicitly as an implementation piece of the feature.

### 7.2. Risky: Application Directly Imports Internal Helper

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ReportsClientConfiguration.class)
public class ApplicationConfiguration {
}
~~~

The application configuration bypassed `ReportsAutoConfiguration`. Property conditions on the root no longer guard the helper. Even with `acme.reports.enabled=false`, the helper can still create `ReportClient`.

The consumer also becomes coupled to the library's internal package. If the vendor reorganizes packages or splits modules, application code breaks even if the starter API did not change.

### 7.3. Directly Importing the Root Auto-Configuration Also Requires Care

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ReportsAutoConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Here, conditions directly on `ReportsAutoConfiguration` still run. However, the class is imported via standard `@Import` rather than Boot's candidate list.

Do not expect auto-configuration ordering and exclusions to work identically to the `AutoConfiguration.imports` path. Once a class is published as an auto-configuration, let Spring Boot manage loading it.

### 7.4. When an Application Truly Needs an Explicit Public Configuration

If a library has a use case requiring consumers to opt into configuration manually, provide a consumer-facing API configuration and document clearly:

- Which classes are public API.
- Which conditions must be configured.
- Which dependencies are mandatory.
- Which beans are registered.
- How it behaves when combined with starter auto-configuration.

Never turn an internal package into public API merely because consumers can technically reach that class.

## 8. Complete Maven Example Reproducing the Bug

The example below uses Java 17 and Spring Boot 3.3.13. The Acme library has a property-guarded root auto-configuration. A helper configuration creates `ReportClient`.

Test goals:

1. Auto-configuration loaded properly: property `true` creates the bean.
2. Property `false`: proper auto-configuration path creates no bean.
3. Application directly imports helper: bean appears despite property `false`.
4. Component scanning library package: helper is discovered even when root condition is `false`.
5. Exclusion fails to stop component scan from loading the class.
6. Application custom bean makes default auto-configuration back off.

### 8.1. Project Structure

~~~text
wrong-package-scan-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/app/
    │   │   │   └── Application.java
    │   │   └── com/acme/reports/
    │   │       ├── ReportClient.java
    │   │       └── autoconfigure/
    │   │           ├── ReportsAutoConfiguration.java
    │   │           └── internal/
    │   │               └── ReportsClientConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/tests/
            └── ReportsScanningTests.java
~~~

### 8.2. `pom.xml`

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>wrong-package-scan-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
</project>
~~~

### 8.3. `ReportClient.java`

**src/main/java/com/acme/reports/ReportClient.java**

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

### 8.4. `ReportsAutoConfiguration.java`

**src/main/java/com/acme/reports/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

### 8.5. `ReportsClientConfiguration.java`

**src/main/java/com/acme/reports/autoconfigure/internal/ReportsClientConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.internal;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    public ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

### 8.6. `AutoConfiguration.imports`

Create file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Only the root auto-configuration is published. The helper is imported by the root class using `@Import`.

### 8.7. `Application.java`

**src/main/java/com/example/app/Application.java**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`Application` sits in `com.example.app`. Thus, default component scanning does not scan `com.acme.reports`. Auto-configuration is still found via the imports resource.

To enable the feature:

~~~properties
acme.reports.enabled=true
~~~

### 8.8. `ReportsScanningTests.java`

**src/test/java/com/example/tests/ReportsScanningTests.java**

~~~java
package com.example.tests;

import com.acme.reports.ReportClient;
import com.acme.reports.autoconfigure.ReportsAutoConfiguration;
import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsScanningTests {

    private final ApplicationContextRunner bootRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BootConfiguration.class);

    @Test
    void autoConfigurationCreatesDefaultWhenEnabled() {
        bootRunner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://default.example.test");
                });
    }

    @Test
    void autoConfigurationDoesNotCreateBeanWhenDisabled() {
        bootRunner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Test
    void directImportOfInternalConfigurationBypassesRootProperty() {
        new ApplicationContextRunner()
                .withUserConfiguration(DirectInternalImportConfiguration.class)
                .withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void broadComponentScanFindsHelperEvenWhenRootConditionIsFalse() {
        new ApplicationContextRunner()
                .withUserConfiguration(BroadComponentScanConfiguration.class)
                .withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void autoConfigurationExclusionDoesNotStopComponentScan() {
        new ApplicationContextRunner()
                .withUserConfiguration(ExclusionAndBroadScanConfiguration.class)
                .withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void userBeanMakesDefaultAutoConfigurationBackOff() {
        bootRunner
                .withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ReportsClientConfiguration.class)
    static class DirectInternalImportConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = ReportsAutoConfiguration.class)
    static class BroadComponentScanConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(
            excludeName =
                    "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
    @ComponentScan(basePackageClasses = ReportsAutoConfiguration.class)
    static class ExclusionAndBroadScanConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }
}
~~~

### 8.9. Running the Tests

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

Expected results:

| Test | Outcome |
| --- | --- |
| Property `true` via auto-configuration | One default `ReportClient` exists |
| Property `false` via auto-configuration | No `ReportClient` exists |
| Direct helper import when property `false` | `ReportClient` still appears |
| Component scan of library package when property `false` | `ReportClient` still appears |
| Exclude root auto-configuration yet still component-scan | Scanned class can still create `ReportClient` |
| User bean declared before auto-configuration | Default bean backs off, custom endpoint retained |

The middle tests intentionally reproduce misconfigurations to show loading paths bypassing the root gate. They are not configurations to keep in a production application.

## 9. How to Investigate When an Unexpected Bean Appears

### 9.1. Inspect Package Scanning

Search for declarations that can widen scan scope:

~~~text
@SpringBootApplication(scanBasePackages = ...)
@SpringBootApplication(scanBasePackageClasses = ...)
@ComponentScan(...)
@ComponentScan(basePackages = ...)
@ComponentScan(basePackageClasses = ...)
~~~

Also look for XML configuration, custom `ImportSelector`, or `ImportBeanDefinitionRegistrar` if the application uses them.

Search command across source:

~~~bash
rg -n "@ComponentScan|scanBasePackages|basePackages|AutoConfiguration.imports|@Import" src
~~~

Compare the main application class's package against the library's actual packages. Check whether component scanning covers the auto-configuration or helper package.

### 9.2. Enable the Condition Evaluation Report

Run the application with:

~~~bash
java -jar application.jar --debug
~~~

Or configure:

~~~properties
debug=true
~~~

The Condition Evaluation Report shows which auto-configurations matched/did not match and why. If the report shows the root auto-configuration did not match yet the bean still exists, inspect component scan paths or direct helper imports.

You can use the Actuator `conditions` endpoint if the application already has Actuator and the endpoint is properly exposed/secured:

~~~text
GET /actuator/conditions
~~~

### 9.3. Inspect the Source of the `BeanDefinition`

Once you know the bean name, inspect registration metadata:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.ConfigurableApplicationContext;

public static void inspectReportClient(
        ConfigurableApplicationContext context) {

    var beanFactory = context.getBeanFactory();

    if (!beanFactory.containsBeanDefinition("reportClient")) {
        System.out.println("reportClient definition not found");
        return;
    }

    BeanDefinition definition =
            beanFactory.getBeanDefinition("reportClient");

    System.out.println(
            "resource = " + definition.getResourceDescription());
    System.out.println(
            "factory bean = " + definition.getFactoryBeanName());
    System.out.println(
            "factory method = " + definition.getFactoryMethodName());
    System.out.println(
            "bean class = " + definition.getBeanClassName());
}
~~~

For beans created via `@Bean` methods, factory bean and factory method usually trace back to the configuration class that registered the bean. Resource description may or may not be present depending on the `BeanDefinition` kind.

If multiple beans share a type, list bean names:

~~~java
String[] names = context.getBeanFactory()
        .getBeanNamesForType(ReportClient.class);

System.out.println(java.util.Arrays.toString(names));
~~~

Do not call only `getBean(type)` and stop. When multiple candidates exist, type lookup throws `NoUniqueBeanDefinitionException`; listing names reveals all registration sources.

### 9.4. Compare Test Context vs. Application Context

Use `ApplicationContextRunner` to verify separately:

- Proper auto-configuration with property `true`/`false`.
- Whether user-defined beans cause the default to back off.
- Whether directly imported helpers create beans.
- Whether broad package component scanning discovers helpers.
- Whether exclusions are bypassed by another scan path.

Then run a consumer smoke test using the application's real starter JAR and component-scan setup. That catches differences between isolated auto-configuration tests and the real application context.

## 10. Ordered Remediation Steps

### 10.1. Narrow Component Scanning First

Place the main class in the application's root package and scan only packages the application owns.

Replace:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme"
})
~~~

with:

~~~java
@SpringBootApplication
~~~

once the main class sits in the proper root package.

If the application spans multiple separate package trees, use marker classes inside application source code.

### 10.2. Keep Auto-Configurations Outside Scan Roots

Place the library's packages under a distinct namespace, such as `com.acme.reports`, while application scanning targets only `com.example.app`.

Do not rely on classes being internal or package-private to shield them from component scanning. The primary safeguard is not scanning that package.

### 10.3. Remove `@ComponentScan` from Auto-Configurations

Replace component scanning inside auto-configurations with explicit `@Import`.

If a helper serves only an optional integration branch, import the helper from a nested configuration carrying the corresponding conditions.

### 10.4. Do Not Import Internal Configurations in Applications

If a consumer currently has:

~~~java
@Import(ReportsClientConfiguration.class)
~~~

remove that import and add the published starter/artifact. Let Spring Boot load `ReportsAutoConfiguration` from the imports resource.

If the application needs a specific standalone feature, ask the provider for a supported API configuration instead of referencing classes in internal packages.

### 10.5. Place Conditions at the Right Boundary

The root auto-configuration should hold feature-enablement conditions. Helper configurations should be imported solely through the root class.

For optional classes, isolate classpath conditions inside nested configurations:

~~~java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.optional.PdfSdk")
    @ConditionalOnProperty(
            prefix = "acme.reports.pdf",
            name = "enabled",
            havingValue = "true")
    static class PdfConfiguration {

        @Bean
        PdfClient pdfClient() {
            return new PdfClient();
        }
    }
}
~~~

This keeps references to optional APIs inside guarded configuration scopes. Still, if a nested configuration could ever be scanned directly or imported independently, ensure its own condition boundary is safe.

### 10.6. Use Exclusion Filters as a Transitional Measure

If package scanning cannot be narrowed immediately, explicitly exclude the auto-configuration or internal package from component scan:

~~~java
@ComponentScan(
        basePackages = "com.acme",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.acme\\.reports\\.autoconfigure\\..*"))
~~~

This is an application-side safeguard. It does not replace designing narrow package scans and may need updating whenever library packages change.

To exclude a single class, use an `ASSIGNABLE_TYPE` filter. When excluding an entire internal package, a package regex can be easier to manage, though the pattern must be tested carefully.

## 11. Design Principles to Prevent Recurrence

### For Consuming Applications

- [ ] Main application class resides in the application's root package.
- [ ] Component scanning covers only application-managed packages.
- [ ] Do not scan vendor namespaces or `org.springframework`.
- [ ] Do not import internal starter packages.
- [ ] Use exclusions only for published auto-configuration candidates.
- [ ] Use dedicated `@EntityScan` or `@ConfigurationPropertiesScan` when specialized scopes are needed.

### For Libraries/Starters

- [ ] `@AutoConfiguration` classes are listed in `AutoConfiguration.imports`.
- [ ] Auto-configurations reside in dedicated packages and are never scanned.
- [ ] `@ComponentScan` is never enabled inside auto-configurations.
- [ ] Use explicit `@Import` for helper configurations.
- [ ] Optional integrations have their own classpath conditions.
- [ ] `@ConditionalOnMissingBean` sits on the auto-configuration path processed after user beans.
- [ ] Internal helpers are not promoted as consumer API.
- [ ] Starters do not pull unneeded optional dependencies onto the default classpath.
- [ ] Consumer tests cover both enabled and disabled property states.
- [ ] Tests catch accidental auto-configuration package scans and direct helper imports.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Bean appears despite feature property `false` | Helper config scanned/imported independently | Narrow scan; import helper only from root auto-config |
| `excludeName` fails to block bean | Class is still component-scanned or directly imported | Trace loading path and remove that path |
| Default bean fails to back off for custom bean | `@ConditionalOnMissingBean` runs before custom definition is processed | Keep default bean in the auto-configuration path |
| Multiple beans of the same type | Two configurations both register implementations | Inspect bean names and `BeanDefinition` sources |
| `BeanDefinitionOverrideException` | Two definitions use the same bean name | Eliminate duplicate registration path and clarify ownership |
| `NoClassDefFoundError` when optional SDK is absent | Helper loaded directly outside classpath gate | Isolate optional APIs in a conditioned nested configuration |
| `@AutoConfigureAfter` stops having effect | Auto-config scanned/imported like regular config | Load auto-config solely via imports |
| Unit tests pass, yet production fails | Test runner does not mirror broad application scan | Add consumer tests with real package scanning |
| Component scan picks up unexpected controllers/repositories | `scanBasePackages` too broad | Use marker packages and application root scan |
| Library package refactoring breaks application | Consumer depended on internal class | Use published starter/API and migration guide |
| `@Import` of helper enables feature even when disabled | Import bypasses root class condition | Remove direct import; use published entry point |
| Condition report shows root no-match, yet bean exists | Alternate registration path exists | Inspect component scan, `@Import`, and `BeanDefinition` source |

## 13. Self-Check Questions

**Question 1.** Why can `@AutoConfiguration` be discovered by component scanning?  
**Answer:** Because `@AutoConfiguration` is meta-annotated with `@Configuration`, and `@Configuration` is a component stereotype. If its package is scanned, the class can be discovered like regular configuration.

**Question 2.** Through which mechanism should auto-configuration classes be loaded?  
**Answer:** By declaring the class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Question 3.** Why can component-scanning a library's package cause helper beans to appear even when the feature property is `false`?  
**Answer:** The helper configuration can be scanned independently without passing through the root auto-configuration's condition.

**Question 4.** Where does `@SpringBootApplication` component-scan by default?  
**Answer:** The package containing the `@SpringBootApplication`-annotated class and its subpackages, unless configured otherwise.

**Question 5.** Does `excludeName` block a class from being component-scanned?  
**Answer:** No. Exclusions govern auto-configuration import candidates; component scanning is a separate registration path.

**Question 6.** Should `@ComponentScan` be used inside a custom auto-configuration to locate helpers?  
**Answer:** No. Use explicit `@Import` so the configuration list stays controlled and independent of package scanning.

**Question 7.** Why is `@ConditionalOnMissingBean` sensitive to accidental package scanning?  
**Answer:** Conditions see only already-processed bean definitions. Standard auto-configuration runs after user definitions; helpers scanned as regular configs may run too early.

**Question 8.** If an application needs to import a starter's internal configuration class, what should be done?  
**Answer:** Request a supported API configuration from the library or use the starter. Do not depend on internal packages.

**Question 9.** How do you trace the origin of an unexpected bean?  
**Answer:** List bean names by type, inspect `BeanDefinition` `factoryBeanName`/`factoryMethodName`/`resourceDescription`, enable `--debug`, and inspect component scans/imports.

**Question 10.** Why are consumer tests needed beyond auto-configuration unit tests?  
**Answer:** Consumer tests replicate the real application's classpath, imports resource, and package scanning, catching unintended loading paths that isolated runners miss.

## 14. Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Structuring Your Code](https://docs.spring.io/spring-boot/3.3/reference/using/structuring-your-code.html)
- [Spring Boot 3.3 — Using the @SpringBootApplication Annotation](https://docs.spring.io/spring-boot/3.3/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Framework 6.1 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.1/core/beans/classpath-scanning.html)

**Key takeaway:** Auto-configurations must go through `AutoConfiguration.imports` so Spring Boot manages conditions, ordering, and exclusions. Component scanning should target only application packages. Helper configurations are explicitly imported from the root auto-configuration; consumers must not import internal packages. When a bean appears despite a disabled feature or ignored exclusion, inspect component scanning and direct `@Import` before changing conditions.
