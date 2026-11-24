# Ensuring Applications Do Not Need to Scan Library Packages: Designing Spring Boot Auto-Configuration

## 1. Goal of an Auto-Configuration Library

Suppose the `Acme Widget` library provides a shared service. A consuming application should only need to add the starter dependency and configure:

~~~yaml
acme:
  widget:
    endpoint: https://api.example.test
~~~

The application should not have to know the library's internal packages to widen component scanning:

~~~java
@ComponentScan({
    "com.example.application",
    "com.acme.widget"
})
~~~

That approach couples the application to the library's source structure. If the library renames packages, splits modules, or adds implementation packages, users might have to edit application configuration.

Spring Boot provides the **auto-configuration** mechanism so libraries declare their own required beans. Boot discovers configuration classes from metadata inside the JAR, evaluates conditions, and registers beans. As a result:
- The application only needs to enable auto-configuration, usually via `@SpringBootApplication`.
- The library publishes its own configuration classes in the JAR.
- Beans are registered using `@Bean`, `@Import`, and `@EnableConfigurationProperties`.
- `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` ensure configurations apply only when appropriate and let users replace defaults.
- The application's component scan only needs to cover packages owned by the application.

**Principle:** a library must describe its own Spring integration; applications should never have to scan library packages to find internal implementations.

## 2. Component Scan and Auto-Configuration Are Two Separate Mechanisms

`@SpringBootApplication` combines three main roles: application configuration, enabling auto-configuration, and component scanning. By default, component scanning starts from the package containing the application class and scans subpackages beneath it.

Example:

~~~text
com.example.shop
├── ShopApplication.java
├── controller
├── service
└── config

com.acme.widget
├── api
├── internal
└── autoconfigure
~~~

If `ShopApplication` lives in `com.example.shop`, default component scanning does not automatically expand into the sibling package `com.acme.widget`. This boundary is intentional: the application owns its packages; the library is responsible for registering its own public beans.

| Mechanism | Purpose | Source of information |
| --- | --- | --- |
| `@ComponentScan` | Finds classes with stereotypes like `@Component`, `@Service`, `@Repository` in scanned packages | Declared packages or the configuration class's package |
| `@EnableAutoConfiguration` | Finds and applies automatic configurations from dependencies | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |

Applications typically use both: component scanning for application code and auto-configuration for library integrations. A library's package does not need to be a subpackage of the application.

## 3. Declaring Auto-Configuration in `AutoConfiguration.imports`

In Spring Boot 3.x, a JAR containing auto-configuration needs the file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Example content:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Each line is the fully qualified name of an auto-configuration class. Multiple classes can be listed; comments starting with `#` are allowed. For nested classes, names in the file use `$` to separate the outer class and nested class.

Spring Boot reads this descriptor from JARs on the classpath. Thus a library can package its configuration in a separate JAR without placing that class under the application's package.

### Why Not Use `spring.factories` for This?

`META-INF/spring.factories` is still used by Spring for several other extensions. However, since Spring Boot 3.0, registering auto-configurations via the `EnableAutoConfiguration` key in that file was removed. Spring Boot 2.7 introduced `AutoConfiguration.imports` with a transition period; libraries targeting Boot 3.x should use the new descriptor.

Simply adding `@AutoConfiguration` to source code is not enough for a starter to be discovered automatically. The imports file must be packaged inside a JAR on the runtime classpath.

## 4. Organizing Modules so Consumers Only Add the Starter

A common structure:

~~~text
acme-widget/
├── acme-widget-autoconfigure/
│   ├── src/main/java/com/acme/widget/
│   │   ├── WidgetService.java
│   │   ├── DefaultWidgetService.java
│   │   ├── WidgetProperties.java
│   │   └── autoconfigure/
│   │       ├── WidgetAutoConfiguration.java
│   │       └── WidgetClientConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-widget-spring-boot-starter/
    └── build.gradle or pom.xml
~~~

The `autoconfigure` module contains auto-configuration classes, conditions, properties, bean factory methods, and the imports descriptor. The `starter` module is typically a dependency aggregator: declaring the autoconfigure module alongside appropriate runtime dependencies so consumers add a single dependency.

Gradle consumer:

~~~kotlin
dependencies {
    implementation("com.acme:acme-widget-spring-boot-starter:1.0.0")
}
~~~

Maven consumer:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

The imports file inside the `acme-widget-autoconfigure` JAR is still discovered by Boot when the starter declares that module as a transitive dependency. There is no need to copy the descriptor into the application project.

## 5. Library Example: Explicit Auto-Configuration and Bean Registration

This example uses Java 17+ and Spring Boot 3.3. Classes are kept small to focus on the registration mechanism.

**`WidgetService.java`:**

~~~java
package com.acme.widget;

public interface WidgetService {
    String endpoint();
}
~~~

**`DefaultWidgetService.java`:**

~~~java
package com.acme.widget;

public final class DefaultWidgetService implements WidgetService {

    private final String endpoint;

    public DefaultWidgetService(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String endpoint() {
        return endpoint;
    }
}
~~~

**`WidgetProperties.java`:**

~~~java
package com.acme.widget;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.widget")
public class WidgetProperties {

    private String endpoint = "https://default.example";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

**`WidgetAutoConfiguration.java`:**

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnClass(WidgetService.class)
@EnableConfigurationProperties(WidgetProperties.class)
@Import(WidgetClientConfiguration.class)
public class WidgetAutoConfiguration {
}
~~~

**`WidgetClientConfiguration.java`:**

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.DefaultWidgetService;
import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class WidgetClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(WidgetService.class)
    DefaultWidgetService widgetService(WidgetProperties properties) {
        return new DefaultWidgetService(properties.getEndpoint());
    }
}
~~~

The `AutoConfiguration.imports` file has a single line:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Registration flow:
1. The application's `@EnableAutoConfiguration` tells Boot to locate auto-configuration candidates.
2. Boot reads the descriptor and finds `WidgetAutoConfiguration`.
3. `@ConditionalOnClass` confirms the library API is on the classpath.
4. `@EnableConfigurationProperties` registers `WidgetProperties` and enables binding from the `Environment`.
5. `@Import` brings `WidgetClientConfiguration` into the context without package scanning.
6. The `@Bean` method creates the default `WidgetService` if the application does not already have a matching implementation.

No class has to be discovered via the application's component scan.

## 6. Use `@Import` Instead of Component Scanning Inside Auto-Configuration

Spring Boot recommends that auto-configurations **do not enable component scanning themselves to find additional components**. Explicitly import the required configurations:

~~~java
@AutoConfiguration
@Import({
        WidgetClientConfiguration.class,
        WidgetMetricsConfiguration.class,
        WidgetHealthConfiguration.class
})
public class WidgetAutoConfiguration {
}
~~~

Each imported class can contain `@Bean` methods and its own conditions. Supporting classes can reside in internal library packages; `@Import` registers them directly by class reference.

| Requirement | Mechanism |
| --- | --- |
| Register auto-configuration class | `AutoConfiguration.imports` |
| Load supporting configuration group | `@Import(SomeConfiguration.class)` |
| Register service/default bean | `@Bean` method |
| Register properties class | `@EnableConfigurationProperties` |
| Enable only when dependency is present | `@ConditionalOnClass` |
| Create default only when bean is absent | `@ConditionalOnMissingBean` |
| Dynamic registration from complex metadata | `ImportSelector` or `ImportBeanDefinitionRegistrar` when genuinely needed |

Do not use `@ComponentScan("com.acme.widget")` inside an auto-configuration. Broad scanning can accidentally register internal classes, test helpers, or components not meant as public API; it also ties the application to the library's package layout. Explicit import lists tell reviewers exactly which bean groups are loaded.

## 7. Letting Applications Replace the Default Bean

A library should provide useful defaults while allowing application overrides. The `widgetService` method uses:

~~~java
@Bean
@ConditionalOnMissingBean(WidgetService.class)
DefaultWidgetService widgetService(WidgetProperties properties) {
    return new DefaultWidgetService(properties.getEndpoint());
}
~~~

When the application declares a bean implementing `WidgetService`, the condition does not match and the default backs off.

Application-side configuration:

~~~java
package com.example.application;

import com.acme.widget.WidgetService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomWidgetConfiguration {

    @Bean
    CustomWidgetService customWidgetService() {
        return new CustomWidgetService();
    }

    static final class CustomWidgetService implements WidgetService {
        @Override
        public String endpoint() {
            return "custom://application";
        }
    }
}
~~~

The custom bean is registered from configuration owned by the application; the library's auto-configuration sees that bean definition and skips the default. No scanning of library packages is needed.

Use a concrete return type on `@Bean` methods. The default method returns `DefaultWidgetService` even though the condition checks the `WidgetService` interface, giving Spring complete type metadata.

Avoid registering the default via auto-configuration while also annotating `DefaultWidgetService` with `@Component`. Component scanning could create the default unconditionally and defeat back-off.

## 8. Registering Properties Without `ConfigurationPropertiesScan`

A `@ConfigurationProperties` class does not automatically become a bean merely by having the annotation. Auto-configurations should register properties classes explicitly:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
        WidgetProperties.class,
        WidgetRetryProperties.class
})
public class WidgetAutoConfiguration {
}
~~~

The application configures values through `application.yml` or `application.properties`; the binder reads from the `Environment`. Consumers do not have to write `@ConfigurationPropertiesScan("com.acme.widget")`.

Distinction:
- `@ConfigurationProperties` defines the prefix and data structure.
- `@EnableConfigurationProperties` registers specific classes as beans and enables binding.
- `@ConfigurationPropertiesScan` is a separate scanning mechanism for applications wanting to discover many of their own properties classes; auto-configuration libraries should not force consumers to enable it.

If a library has multiple properties classes, list them on the appropriate auto-configuration. For optional integration properties, register them in a child configuration with its own condition.

## 9. Distinguishing `@AutoConfigurationPackage` from Component Scan

The names of these mechanisms are easy to confuse:

- `@AutoConfiguration` marks an auto-configuration class.
- `@AutoConfigurationPackage` registers the root package that some Boot auto-configured features use as a base for finding entities or repositories.
- `@ComponentScan` searches for Spring components and configuration classes in specified packages.

`@AutoConfigurationPackage` does **not** replace component scan to register every `@Component` in a library. Nor does it mean every class in that package becomes a bean.

If the library needs helper beans, use `@Bean`, `@Import`, or a registrar. Do not expect adding a package to the auto-configuration packages list to turn every class inside into a bean.

## 10. Testing: Consumers Not Scanning Library Packages Still Receive Beans

`ApplicationContextRunner` can run a context using `@EnableAutoConfiguration` **without `@ComponentScan`**. Library auto-configuration is discovered from the imports descriptor on the test runtime classpath.

The test below uses Java 17+, Spring Boot 3.3, JUnit 5, and AssertJ.

File `src/test/java/com/example/application/LibraryAutoConfigurationDiscoveryTest.java`:

~~~java
package com.example.application;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.acme.widget.DefaultWidgetService;
import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import com.acme.widget.autoconfigure.WidgetAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class LibraryAutoConfigurationDiscoveryTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ApplicationConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ApplicationConfiguration {
        // Intentionally omit @ComponentScan.
    }

    @Test
    void libraryBeansAreDiscoveredWithoutComponentScanning() {
        runner.withPropertyValues(
                "acme.widget.endpoint=https://api.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(WidgetProperties.class);
                    assertThat(context).hasSingleBean(WidgetService.class);
                    assertThat(context).hasSingleBean(DefaultWidgetService.class);
                    assertThat(context.getBean(WidgetService.class).endpoint())
                            .isEqualTo("https://api.example.test");
                });
    }

    @Test
    void applicationBeanReplacesLibraryDefault() {
        runner.withUserConfiguration(CustomWidgetConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WidgetService.class);
                    assertThat(context).hasSingleBean(CustomWidgetService.class);
                    assertThat(context).doesNotHaveBean(DefaultWidgetService.class);
                    assertThat(context.getBean(WidgetService.class).endpoint())
                            .isEqualTo("custom://application");
                });
    }

    @Test
    void publishedImportsDescriptorNamesAutoConfiguration()
            throws IOException {

        String path =
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        try (InputStream input =
                     getClass().getClassLoader().getResourceAsStream(path)) {

            assertThat(input).isNotNull();

            String imports = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(imports.lines())
                    .contains(WidgetAutoConfiguration.class.getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomWidgetConfiguration {

        @Bean
        CustomWidgetService customWidgetService() {
            return new CustomWidgetService();
        }
    }

    static final class CustomWidgetService implements WidgetService {
        @Override
        public String endpoint() {
            return "custom://application";
        }
    }
}
~~~

The first test is the primary proof: the application configuration enables only `@EnableAutoConfiguration`, without component scanning. If `WidgetService` and `WidgetProperties` still appear, the library was loaded via the auto-configuration mechanism.

The second test proves the user bean is retained and the default backs off. The third test checks that the descriptor actually exists on the test runtime classpath and lists the auto-configuration class accurately.

Run with Gradle:

~~~bash
./gradlew test --tests "com.example.application.LibraryAutoConfigurationDiscoveryTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.application.LibraryAutoConfigurationDiscoveryTest"
~~~

**Expected result:** 3 tests PASS. Assertions verify bean registration, binding, and the descriptor, without depending on fixed stdout. This test example has been reviewed and was not executed in a specific project during the writing of this lesson.

## 11. Verifying the Imports File in the Published JAR

Context tests can pass in an IDE while the published JAR lacks the descriptor if resources are not packaged. Inspect the built artifact.

With Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:jar
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar
~~~

The output must contain the path:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Quick filter on Windows:

~~~powershell
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

Next, verify:
- The descriptor content has the exact fully qualified class name and package.
- The starter depends on the autoconfigure module.
- The autoconfigure module is on the application's runtime classpath.
- No exclusion or `spring.autoconfigure.exclude` removes the configuration class.

## 12. Common Mistakes and Diagnosis

| Symptom | Cause | Fix |
| --- | --- | --- |
| Application must add `@ComponentScan("com.acme.widget")` to get beans | Library relied on stereotype scanning instead of auto-configuration | Create auto-configuration and imports file; use `@Bean`/`@Import` |
| Class has `@AutoConfiguration` yet does not run | Missing or incorrect `AutoConfiguration.imports` file | Check resource in JAR and class name |
| IDE tests pass, but consumers after publish cannot find configuration | Resource not packaged or starter missing autoconfigure dependency | Inspect JAR and runtime dependencies |
| Properties exist, but service is missing | Bean method condition unmatched or missing dependency | Inspect Condition Evaluation Report and test each condition |
| Two default beans exist after adding scan | Default was both scanned as a component and created via `@Bean` | Keep only one registration path for the default |
| Descriptor lists class, yet no bean exists | Auto-configuration excluded or class-level condition unmatched | Check `--debug` and classpath/property/bean conditions |
| Library package rename breaks apps | Consumer hardcoded library package in `@ComponentScan` or `@Import` | Keep app scanning independent; update descriptor in artifact |
| Helper class is not registered | Missing `@Import` or `@Bean` declaration | Import supporting configuration or declare `@Bean` |
| Properties remain at default values | Properties class not enabled/scanned | Use `@EnableConfigurationProperties` |
| Duplicate beans or configuration runs twice | Loaded the same configuration through unnecessary multiple paths | Use the descriptor as the standard auto-configuration path |

Enable `--debug` or `debug=true` to inspect the Condition Evaluation Report. If the auto-configuration does not appear, check the imports file and runtime classpath. If it appears as a negative match, read the specific condition. If the class matches yet the bean method creates no bean, check conditions on the method or nested configuration.

With Actuator, `/actuator/conditions` can display condition evaluations when the endpoint is exposed appropriately. Do not expose sensitive endpoints in public environments just for debugging.

## 13. Principles for Designing an Auto-Configuration Library

- **Place auto-configurations in a dedicated package**, such as `com.acme.widget.autoconfigure`, to separate APIs, implementations, and integration configuration.
- **Register via `AutoConfiguration.imports`** in the JAR; never require consumers to scan library packages.
- **Do not put `@ComponentScan` inside auto-configuration** to scan internal packages. Use `@Import` for needed configuration groups.
- **Use `@Bean` for default beans** and `@ConditionalOnMissingBean` so users can override.
- **Use `@EnableConfigurationProperties`** to register properties classes without forcing consumers to run configuration property scanning.
- **Use conditions** so optional integrations activate only when dependencies exist or properties match.
- **Keep starters lean:** starters bundle dependencies; autoconfigure modules own metadata and configuration.
- **Test like an independent consumer:** use an application package distinct from the library package and do not component-scan the library.
- **Inspect published JARs:** verify the imports resource, class names, and runtime dependencies.
- **Keep APIs stable:** consumers depend on the starter, public SPI, and documented properties; never on internal implementation packages.

Overview model:

~~~mermaid
flowchart TD
    A["Application adds starter"] --> B["Autoconfigure JAR on runtime classpath"]
    B --> C["@EnableAutoConfiguration"]
    C --> D["Read AutoConfiguration.imports"]
    D --> E["Load WidgetAutoConfiguration"]
    E --> F["@Import supporting configurations"]
    F --> G["@EnableConfigurationProperties"]
    F --> H["@Bean + conditions"]
    G --> I["WidgetProperties bean"]
    H --> J["WidgetService bean"]
    I --> J
    J --> K["Application injects WidgetService"]
~~~

## Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): auto-configuration in external JARs, `AutoConfiguration.imports`, avoiding component scan in auto-configurations, and using `@Import`.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): auto-configuration annotation and metadata.
- [Spring Boot 3.3 — `@EnableAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): enabling the application's auto-configuration mechanism.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): testing contexts combining user configuration and auto-configuration with `ApplicationContextRunner`.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): scope and mechanism of component scanning.
