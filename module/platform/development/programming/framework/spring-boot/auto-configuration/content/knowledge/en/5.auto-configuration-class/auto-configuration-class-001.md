# @AutoConfiguration and Its Relationship with @Configuration

> **Module:** Spring Boot — auto-configuration, "Auto-Configuration Class" group. This lesson explains the Spring configuration nature of `@AutoConfiguration`, how Spring Boot discovers and activates it, how it differs from regular `@Configuration`, bean creation conditions, processing order, `proxyBeanMethods=false`, and how to write and test an auto-configuration yourself. Examples use Java 17, Spring Boot 3.5.7, and Maven.

## 1. Core Answer

**`@AutoConfiguration` is a specialized Spring Boot annotation meta-annotated with `@Configuration(proxyBeanMethods = false)`.** Therefore, an `@AutoConfiguration` class is also a **Spring configuration class**: it can declare `@Bean` methods, contain nested configurations, use `@Import`, and carry `@Conditional` annotations.

The difference does not lie in the ability to write `@Bean` methods. It lies in **role** and **the path by which it is loaded**:

- Regular `@Configuration` represents configuration that an application or library **explicitly brings into the context** via component scan, `@Import`, or direct registration.
- `@AutoConfiguration` represents **default configuration that can be applied automatically** when the application enables `@EnableAutoConfiguration` (typically via `@SpringBootApplication`), the class is **listed in the imports file**, and the relevant conditions match.
- Auto-configuration is designed to **back off in favor of user configuration**, typically via `@ConditionalOnMissingBean`, and to activate only when the classpath/property/context matches.
- Spring Boot requires auto-configuration to follow its own structure and candidate-loading metadata; merely annotating a class with `@AutoConfiguration` is **not enough** for it to automatically appear in another application.

A rule to remember: **every auto-configuration is a configuration, but not every configuration is an auto-configuration**.

## 2. Annotation Relationship: Meta-annotations and Meaning

In Spring Boot 3.5, the declaration of `@AutoConfiguration` has the following conceptual form:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore
@AutoConfigureAfter
public @interface AutoConfiguration {
    // value, before, beforeName, after, afterName
}
```

This is an **explanatory excerpt of the annotation structure**, not standalone compilable source code, as imports, element declarations, and library implementation details have been omitted.

- `@Configuration(proxyBeanMethods = false)` makes a class annotated with `@AutoConfiguration` a configuration class processed by Spring; at the same time, it defaults to **not using a CGLIB proxy to intercept calls between `@Bean` methods**.
- `@AutoConfigureBefore`/`@AutoConfigureAfter` provide metadata about the order in which auto-configurations are applied.
- The `before`/`after` attributes reference other configuration classes; `beforeName`/`afterName` accept class names as strings when you want to avoid a direct dependency on a type that might not exist.
- `value` is an alias for the configuration bean name from `@Configuration`. It is not the name of an imports file or the names of beans created by individual methods.

The meta-annotation nature has a practical consequence: Spring's `@Configuration` processing code still understands `@AutoConfiguration` classes. Spring Boot adds **the candidate selection, exclusion, condition evaluation, and ordering pipeline**, rather than inventing a different container to store beans.

### Distinguishing Three Commonly Confused Annotations

| Annotation | Provided by? | Role | Can it auto-register library beans just by annotating the class? |
| --- | --- | --- | --- |
| `@Configuration` | Spring Framework | Declares a class containing bean definitions, imports, and context configuration | No. The class still needs to be component-scanned, imported, or registered. |
| `@AutoConfiguration` | Spring Boot | Marks configuration that Boot can apply automatically, with ordering metadata and conventions | No. Standard Boot 3.x auto-discovery requires the class name in `AutoConfiguration.imports`. |
| `@EnableAutoConfiguration` | Spring Boot | Activates the mechanism that selects and imports auto-configurations in an application | This annotation **enables the candidate selection system**, not an annotation for individual auto-configuration classes. |

`@SpringBootApplication` includes `@EnableAutoConfiguration`, `@ComponentScan`, and `@SpringBootConfiguration`. Thus, a standard Spring Boot application can both scan application components and import auto-configurations from dependencies.

## 3. Same @Bean Declaration, Different Paths into the ApplicationContext

### 3.1. Regular `@Configuration`

```java
package com.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationSettings {

    @Bean
    public String applicationLabel() {
        return "my-app";
    }
}
```

If the class lies within the application's `@ComponentScan` scope, Spring registers the configuration class and the `applicationLabel` bean. It can also be brought in via `@Import(ApplicationSettings.class)` or as a configuration source for `AnnotationConfigApplicationContext`.

If the class is outside the scan scope, is not imported, and is not registered by other means, **Spring does not automatically know about that class** merely because it has `@Configuration`.

### 3.2. `@AutoConfiguration`

```java
package com.example.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    public String greetingLabel() {
        return "default-greeting";
    }
}
```

This is a valid configuration class, but **to be automatically discovered by Boot via the auto-configuration mechanism** it must be listed in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.example.autoconfigure.GreetingAutoConfiguration
```

There is no need to move `com.example.autoconfigure` into `@ComponentScan`. In fact, the Spring Boot documentation recommends keeping auto-configuration in **its own package, outside component scan**, and avoiding having an auto-configuration itself enable component scanning of other classes.

The example above shows the minimal declaration; to publish a useful auto-configuration, conditions are usually needed so default beans are not forced onto applications. Section 6 writes a conditional version and a runnable example.

### 3.3. Do Not Confuse Spring's `@Import` with the `AutoConfiguration.imports` File

- `@Import(SomeConfiguration.class)`: a configuration **explicitly imports** the specified class; applies to Spring configuration in general.
- `AutoConfiguration.imports`: a **text resource** inside a JAR listing classes that Boot will consider as auto-configurations when `@EnableAutoConfiguration` is active.
- Java `import com.example.X;`: merely shortens type names in Java source; it is **not** a Spring bean registration mechanism.

## 4. Lifecycle from Class to Bean: Five Distinct Stages

```text
@SpringBootApplication
  |
  +-- @ComponentScan
  |      \-- finds the application's @Configuration / @Component classes by package
  |
  \-- @EnableAutoConfiguration
         \-- AutoConfigurationImportSelector
              \-- ImportCandidates locates ...AutoConfiguration.imports files
                   \-- retrieves the list of candidate class names on the classpath
                        \-- applies exclusions and metadata/condition filtering
                             \-- processes @AutoConfiguration classes
                                  \-- evaluates conditions at the class and @Bean levels
                                       \-- registers matching bean definitions
                                            \-- instantiates beans according to dependencies
```

These levels must be kept separate:

1. **Class on classpath:** the `.class` file is present, though it is not necessarily a Spring candidate.
2. **Listed in imports:** Spring Boot knows about the class as an auto-configuration candidate.
3. **Evaluated for application:** the class is not excluded and its relevant conditions are evaluated.
4. **Bean definition registered:** only `@Bean` methods whose conditions match contribute a bean definition.
5. **Bean instance created:** Spring instantiates according to lifecycle and dependency relationships, typically during context refresh (for non-lazy singletons).

You cannot deduce from "has `@AutoConfiguration`" that "its beans always exist". Even a successfully imported class can result in **0 business beans created** because `@ConditionalOnMissingBean` or property/classpath conditions did not match.

Spring Boot may use metadata to filter out unsuitable configurations early, though which details are checked at which step is an implementation detail; the principle to grasp is **candidate != applied configuration != registered bean**.

## 5. Why Do Auto-Configurations Usually Need Conditions?

If a library creates default beans unconditionally, an application may encounter errors from multiple beans of the same type or receive unintended configuration. Condition annotations let Spring Boot provide useful defaults while letting users configure things themselves.

| Condition | Where placed? | Primary meaning |
| --- | --- | --- |
| `@ConditionalOnClass(SomeApi.class)` | Usually class/nested configuration level | Applies only when the API/library is on the classpath. |
| `@ConditionalOnMissingClass("...")` | Usually class level | Applies only when the class is absent. |
| `@ConditionalOnBean(SomeType.class)` | Class or method | Active only when a matching bean is already registered and visible to the condition. |
| `@ConditionalOnMissingBean(SomeType.class)` | Usually `@Bean` level | **Back-off**: creates the default bean only if no matching bean exists yet. |
| `@ConditionalOnProperty(prefix = ..., name = ...)` | Class or method | Selects based on a property in `Environment`. |
| `@ConditionalOnWebApplication` | Class/nested configuration | Applies only to matching web environments. |

Conditions can be used on regular `@Configuration` classes; they are **not exclusive** to `@AutoConfiguration`. However, `@ConditionalOnBean` and `@ConditionalOnMissingBean` inspect bean definitions **that have already been processed at evaluation time**. Spring Boot ensures auto-configuration is processed after user-defined configurations in the standard flow, so this kind of condition is **best suited to auto-configuration**.

**Back-off is not a bean-deletion operation.** When `@ConditionalOnMissingBean` does not match, Spring Boot **does not register the default bean** from that method. If the user registers a corresponding bean, the user's bean remains intact.

### Class-Level Conditions vs. Method-Level Conditions

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "vendorAdapter")
    Object vendorAdapter() {
        return new Object();
    }
}
```

This is an **illustrative snippet**; imports are omitted and the class is not yet registered in imports. A class-level `@ConditionalOnClass` that does not match prevents the entire configuration. If the class level matches but a bean named `vendorAdapter` already exists, only the bean method with that condition backs off.

**Be careful with classes absent from the classpath:** A `@Bean` method whose signature returns an optional SDK type can cause the JVM to load that type too early. When depending on an API that may be absent, move the method into a nested `@Configuration(proxyBeanMethods=false)` guarded by `@ConditionalOnClass` at the class level.

## 6. Complete Example: @AutoConfiguration Provides Default, Application @Configuration Replaces It

This exercise uses a `GreetingService` interface. An auto-configuration in a package outside the application root provides a default bean, while an application `@Configuration` provides a custom bean when the `custom` profile is active.

### 6.1. Source Structure

```text
configuration-relationship/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example
    │   │   ├── api/GreetingService.java
    │   │   ├── autoconfigure/GreetingAutoConfiguration.java
    │   │   ├── app/DemoApplication.java
    │   │   ├── app/UserGreetingConfiguration.java
    │   │   └── external/ExternalConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test
        └── java/com/example/testing
            ├── GreetingAutoConfigurationTest.java
            └── ApplicationWiringTest.java
```

Note that `com.example.app`, `com.example.autoconfigure`, `com.example.api`, and `com.example.external` are **separate package branches**.

### 6.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>configuration-relationship</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The example does not need a web server. The imports file is placed in the same artifact for easy learning; when building a shared starter, you normally package auto-configuration in a separate library module/JAR.

### 6.3. Library Contract

File `src/main/java/com/example/api/GreetingService.java`:

```java
package com.example.api;

@FunctionalInterface
public interface GreetingService {
    String greet();
}
```

### 6.4. Auto-Configuration and Default Bean

File `src/main/java/com/example/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.example.autoconfigure;

import com.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return () -> "from-auto";
    }
}
```

Here:

- `@AutoConfiguration` turns the class into a configuration with Spring semantics and supplies Boot's auto-configuration metadata.
- `@ConditionalOnClass` demonstrates a classpath condition; in the sample project, `GreetingService` is always present so the condition matches.
- `@ConditionalOnProperty` allows disabling the default via `demo.greeting.enabled=false`. Because `matchIfMissing=true`, omitting the property still allows the default.
- `@ConditionalOnMissingBean(GreetingService.class)` creates the `defaultGreetingService` bean **only when no bean of type `GreetingService` already exists** from the application or another matching source.
- The method declares `GreetingService` as its return type, which is sufficient for the condition to check the right type in this example. In real integrations, consider declaring the most specific return type possible so bean metadata is clear.

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.autoconfigure.GreetingAutoConfiguration
```

When running Spring Boot, this file is **mandatory for standard discovery**. If you delete it from the artifact and keep only the `@AutoConfiguration` annotation, the class in a package outside scan will not be discovered automatically.

### 6.5. Configuration Owned by the Application

File `src/main/java/com/example/app/UserGreetingConfiguration.java`:

```java
package com.example.app;

import com.example.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return () -> "from-user";
    }
}
```

This is a regular `@Configuration`, found by `@ComponentScan` because it resides in `com.example.app`. Without the `custom` profile, the class is not applied. When the profile is enabled, the `customGreetingService` bean is declared **before auto-configuration**, so the `@ConditionalOnMissingBean(GreetingService.class)` condition on the default does not match and backs off.

The distinction does not depend on the application bean having the same name as the default bean: they have different names, `customGreetingService` and `defaultGreetingService`. The condition here evaluates by the **type** `GreetingService`.

### 6.6. A `@Configuration` Outside Scan Scope

File `src/main/java/com/example/external/ExternalConfiguration.java`:

```java
package com.example.external;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExternalConfiguration {

    @Bean
    public String externalMarker() {
        return "external-config";
    }
}
```

This class has `@Configuration` but belongs to `com.example.external`, outside the scan tree starting at `com.example.app`. It also does not appear in `AutoConfiguration.imports`. Therefore, the `externalMarker` bean **does not appear** in the sample application's context. You could load the class with `@Import(ExternalConfiguration.class)` if you truly wanted to, but merely placing it on the classpath is not enough.

### 6.7. Main Application and Output

File `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.api.GreetingService;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            Map<String, GreetingService> services =
                context.getBeansOfType(GreetingService.class);

            String message = services.isEmpty()
                ? "none"
                : services.values().iterator().next().greet();

            System.out.println("service.count=" + services.size());
            System.out.println("service.message=" + message);
            System.out.println(
                "default.exists=" + context.containsBean("defaultGreetingService")
            );
            System.out.println(
                "external.exists=" + context.containsBean("externalMarker")
            );
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17 and Maven:

```bash
mvn -q spring-boot:run
```

Four lines printed by the program (excluding Spring Boot startup logs):

```text
service.count=1
service.message=from-auto
default.exists=true
external.exists=false
```

Explanation: `@ComponentScan` finds `UserGreetingConfiguration` but the `custom` profile does not match; `GreetingAutoConfiguration` in the package outside scan is still loaded via the imports file and creates the default bean. `ExternalConfiguration` is not loaded by any path.

### 6.8. Enable User Configuration to Observe Back-off

Run:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=custom
```

Output lines from the program:

```text
service.count=1
service.message=from-user
default.exists=false
external.exists=false
```

The `custom` profile causes `UserGreetingConfiguration` to contribute its bean to the context. Auto-configuration is still a candidate, but the default method **does not register a bean** because `@ConditionalOnMissingBean` sees that `GreetingService` already exists.

### 6.9. Disable the Default via Property

Without enabling the custom profile; run:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.greeting.enabled=false
```

Lines printed by the application:

```text
service.count=0
service.message=none
default.exists=false
external.exists=false
```

This is the branch where the class-level `@ConditionalOnProperty` **does not match**, different from the back-off branch when the user declares a bean. If you both enable the custom profile and disable the default, the user's bean still exists: the property belongs to the auto-configuration and has no effect of removing user configuration.

## 7. proxyBeanMethods=false: The Real Relationship with @Configuration

Spring Framework allows configuring `@Configuration(proxyBeanMethods = true)` (the default of `@Configuration`). In this mode, the class can be enhanced by Spring via CGLIB so that calls between `@Bean` methods are intercepted, returning the container-managed bean according to the method's semantics.

Conceptual example when `proxyBeanMethods=true`:

```java
@Configuration(proxyBeanMethods = true)
class FullModeConfig {
    @Bean
    Helper helper() {
        return new Helper();
    }

    @Bean
    Worker worker() {
        return new Worker(helper());
    }
}
```

**This is an illustrative fragment, not a standalone compilable Java file**, because `Helper`, `Worker`, and annotation imports are not defined. If `helper` is a singleton, the `helper()` call inside `worker()` is handled by the proxy to retrieve the singleton bean managed by Spring.

With `@Configuration(proxyBeanMethods = false)`, Spring **does not intercept direct calls** to `helper()` in that manner. A normal Java call may create a new instance outside the registered singleton bean. Therefore, the design pattern compatible with false is to **inject dependencies as `@Bean` method parameters**:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    Helper helper() {
        return new Helper();
    }

    @Bean
    Worker worker(Helper helper) {
        return new Worker(helper);
    }
}
```

This is also a fragment using illustrative classes `Helper` and `Worker`. Spring resolves the `Helper helper` parameter from the context, instead of code directly calling the `helper()` method.

**`@AutoConfiguration` has `proxyBeanMethods=false` by annotation definition.** Consequently, when designing an auto-configuration, do not write code relying on interception between `@Bean` methods. Using dependency injection via parameters/constructors is simpler, avoids extra instances, and makes the dependency graph explicit.

Several points to remember:

- `proxyBeanMethods=false` **does not mean** Spring disables singleton scope. Beans managed by the container still follow their scope; only direct Java calls to `@Bean` methods are not proxy-intercepted as in full configuration mode.
- It is different from proxies created by `@Transactional`, AOP, or Spring Security; those proxies serve different semantics.
- `@Configuration(proxyBeanMethods=false)` is still a valid configuration class, not a plain class.
- For auto-configurations with multiple interdependent beans, passing method parameters is the safe and testable choice.

## 8. @AutoConfiguration and Processing Order Rules

An auto-configuration often needs to be evaluated after another auto-configuration—for example, metrics configuration depending on a client that has already been registered. Spring Boot supports:

```java
@AutoConfiguration(after = ClientAutoConfiguration.class)
public class MetricsAutoConfiguration {
    // ...
}
```

This is an **illustrative fragment**; `ClientAutoConfiguration` is a placeholder name and has no import. If you want to avoid a direct dependency on the other class, you can use:

```java
@AutoConfiguration(
    afterName = "com.vendor.client.ClientAutoConfiguration"
)
public class MetricsAutoConfiguration {
    // ...
}
```

The `before`/`beforeName` attributes work in the opposite direction; use dedicated mechanisms like `@AutoConfigureBefore`, `@AutoConfigureAfter`, or `@AutoConfigureOrder` when appropriate.

**Auto-configuration ordering only controls the order of configuration processing / bean definition registration.** It does not determine the subsequent order of bean instantiation; bean creation order depends on dependencies, scope, and `@DependsOn`.

Because `@ConditionalOnBean`/`@ConditionalOnMissingBean` conditions are based on beans already processed, auto-configuration ordering can affect condition outcomes when multiple default configurations contribute related beans. Therefore, clearly specify dependencies between auto-configurations when a real relationship exists.

Do not rely on line order in `AutoConfiguration.imports` as a contract determining runtime bean order.

## 9. Testing Auto-Configuration in the Right Context

First write dedicated tests for the auto-configuration instead of booting the entire application. `ApplicationContextRunner` creates lightweight contexts with specified configurations, which is well suited for testing the default branch, back-off branch, and property branch.

File `src/test/java/com/example/testing/GreetingAutoConfigurationTest.java`:

```java
package com.example.testing;

import com.example.api.GreetingService;
import com.example.autoconfigure.GreetingAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(GreetingAutoConfiguration.class)
        );

    @Test
    void createsDefaultWhenUserBeanMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("defaultGreetingService");
            assertThat(context.getBean(GreetingService.class).greet())
                .isEqualTo("from-auto");
        });
    }

    @Test
    void backsOffWhenUserBeanExists() {
        runner.withUserConfiguration(UserProvidedConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context).doesNotHaveBean("defaultGreetingService");
                assertThat(context.getBean(GreetingService.class).greet())
                    .isEqualTo("from-user-test");
            });
    }

    @Test
    void propertyCanDisableAutoConfiguration() {
        runner.withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserProvidedConfiguration {
        @Bean
        GreetingService userGreetingService() {
            return () -> "from-user-test";
        }
    }
}
```

The test class resides in `com.example.testing`, **outside the application's scan package `com.example.app`**. The nested `UserProvidedConfiguration` is only passed to `ApplicationContextRunner` in the second test, avoiding the pitfall of a test configuration accidentally being component-scanned when the real application boots.

Add an integration test to verify the imports loading path and scan scope.

File `src/test/java/com/example/testing/ApplicationWiringTest.java`:

```java
package com.example.testing;

import com.example.api.GreetingService;
import com.example.app.DemoApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class ApplicationWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void importsAutoConfigurationButDoesNotScanExternalConfig() {
        assertThat(context.getBean(GreetingService.class).greet())
            .isEqualTo("from-auto");
        assertThat(context.containsBean("defaultGreetingService")).isTrue();
        assertThat(context.containsBean("externalMarker")).isFalse();
    }
}
```

This test is intended to run with the **default profile** (without forcing the `custom` profile from the environment or Maven). When running in CI where a custom profile is pre-activated, set an explicit profile for the test so expectations reflect the right context.

Run from the project directory:

```bash
mvn -q test
```

Expected result: **4 tests pass** (3 runner branches and 1 integration test). The `mvn -q test` command normally does not print verbose output on success; check the Surefire reports in `target/surefire-reports` if you need to verify the test count.

**Distinguish the two testing goals:**

- `ApplicationContextRunner` with `AutoConfigurations.of(...)` tests the exact behavior of the provided configuration; it **does not prove** that the imports file was packaged properly.
- `@SpringBootTest` boots a real application with `@EnableAutoConfiguration` and discovers the imports file; it helps catch missing `.imports` resources, overly broad package scans, or unexpectedly registered beans.

## 10. When You Need to Customize or Exclude an Auto-Configuration

Three different actions:

| Goal | How to do it | Consequence |
| --- | --- | --- |
| Keep the auto-configuration but replace the default bean | Declare your own `@Bean GreetingService` and let `@ConditionalOnMissingBean` back off | User bean exists; default bean is not registered. |
| Keep the candidate class but disable via a designed property | `demo.greeting.enabled=false` | The property condition on the auto-configuration does not match. |
| Completely exclude an auto-configuration from the applied set | `@SpringBootApplication(exclude=GreetingAutoConfiguration.class)` or `spring.autoconfigure.exclude=com.example.autoconfigure.GreetingAutoConfiguration` | Boot does not apply that auto-configuration; this does not delete user-declared beans. |

A regular `@Configuration` class that is not in the auto-configuration list **should not be controlled with `spring.autoconfigure.exclude`**. Use `@Profile`, `@Conditional`, scan/import configuration, or a mechanism suited to how the class itself is registered.

Also do not treat `@Primary` as a back-off mechanism: it only affects bean selection during autowiring when multiple matching beans exist; it does not prevent another `@Bean` method from registering a bean.

### Inspecting via the Condition Evaluation Report

Run:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

The Condition Evaluation Report helps identify which conditions matched, which did not match, and why. With the `custom` profile, a negative match on `@ConditionalOnMissingBean(GreetingService.class)` is the **expected behavior**, because the user-provided bean has already been registered.

If Spring Boot Actuator is present with the `/actuator/conditions` endpoint exposed and appropriately secured, condition outcomes can be inspected at runtime. This endpoint is not publicly exposed over HTTP by default.

## 11. Common Mistakes When Confusing @Configuration and @AutoConfiguration

| Incorrect claim | Accurate understanding |
| --- | --- |
| "`@AutoConfiguration` is not a `@Configuration`." | It is a specialized configuration annotation meta-annotated with `@Configuration(proxyBeanMethods=false)`. |
| "Just putting `@AutoConfiguration` on a class in a JAR makes Boot find it automatically." | The class must be registered in `AutoConfiguration.imports` per the standard mechanism. |
| "Every class with `@Configuration` is an auto-configuration." | Regular classes are discovered via scan, import, or direct registration; they do not automatically participate in Boot's candidate selection. |
| "Beans in an auto-configuration are always created." | Class/bean/property conditions may not match, or the auto-configuration may be excluded. |
| "Add `@ComponentScan` for the library's package to see the auto-configuration." | The standard way is using imports; auto-configurations should stay outside component scan. |
| "`proxyBeanMethods=false` eliminates singletons." | Singletons are still managed by Spring; only interception of direct calls between `@Bean` methods is omitted. |
| "Auto-configuration ordering is bean instantiation ordering." | Configuration processing order and bean instance creation order are two different concepts. |
| "When a user bean exists, Boot deletes the default bean." | With `@ConditionalOnMissingBean`, the default bean is never registered in the first place. |
| "Adding `@Primary` surely makes auto-configuration back off." | `@Primary` does not replace a back-off condition. |
| "`@ConditionalOnMissingBean` always sees every bean even if registered later." | The condition relies on bean definitions already processed up to the time of evaluation. |

## 12. Checklist When Writing an Auto-Configuration Class Yourself

1. Identify the **contract** the library provides and which default beans can be replaced by the application.
2. Place the class in a **dedicated package of the autoconfigure module**, avoiding the application's component-scan scope.
3. Use `@AutoConfiguration`; if integrating optional libraries, place `@ConditionalOnClass` in a safe location.
4. Register the fully qualified class name in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside the JAR.
5. Put `@ConditionalOnMissingBean` by appropriate type/name on default beans, and consider a property allowing users to enable/disable it.
6. Write `@Bean` methods using **parameter dependency injection**, since `proxyBeanMethods=false`.
7. Specify `before`/`after` if there is a genuine constraint with another auto-configuration; do not use ordering to compensate for a missing bean dependency.
8. Test with `ApplicationContextRunner`: default case, user bean back-off, and non-matching property/classpath conditions.
9. Integration-test with a Spring Boot app to confirm **the imports file is packaged** and beans have the right component-scan scope.
10. Inspect the Condition Evaluation Report when behavior differs from expectations, and check specific bean names and types.

## 13. Self-Check Questions

1. Why can `@AutoConfiguration` also process `@Bean` methods? **Because it is meta-annotated with `@Configuration`.**
2. There is a `GreetingAutoConfiguration.class` file in a dependency, but imports is missing; will Boot find it via standard auto-discovery? **No.**
3. Does a `@Configuration` outside scan scope and not imported create beans? **No**, unless registered via another mechanism.
4. In the demo, without enabling the `custom` profile, does `defaultGreetingService` exist? **Yes**, because the conditions match.
5. When enabling the `custom` profile, is the default bean created and then replaced? **No**. The `@ConditionalOnMissingBean` condition does not match, so the default method is not registered.
6. If `demo.greeting.enabled` is disabled while `custom` is enabled, is the user bean lost? **No**, the property applies only to the conditional auto-configuration class.
7. With `@AutoConfiguration`, is calling a `@Bean` method directly from another `@Bean` method guaranteed to return the container singleton? **No**; use parameter injection to obtain the managed bean.
8. Does adding `@AutoConfiguration(after = OtherAutoConfiguration.class)` guarantee your bean is instantiated after the other bean? **No**. It governs configuration processing order, not instance lifecycle.
9. Can `@ConditionalOnProperty` be used on a regular `@Configuration`? **Yes**; conditions are not restricted to auto-configuration.
10. When the integration test passes but the `ApplicationContextRunner` test fails because a user bean is missing, what should you check? **Context runner only loads explicitly specified configurations**; you need to add `withUserConfiguration(...)` when testing the back-off branch.

## Official Sources

- [Spring Boot 3.5 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation definition, `@Configuration(proxyBeanMethods=false)`, `before/after`.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports mechanism, class organization, conditions, ordering, and testing.
- [Spring Boot 3.5 API — EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): activation, exclusion, and meaning of the base package.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): default configuration and back-off.
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): `@Configuration`, `@Bean`, `@Import`, and configuration semantics.
