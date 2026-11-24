# Distinguishing Unimported Configurations, Unmatched Conditions, and Bean Creation Failures

> **Scope:** Spring Boot 3.3.x, Spring Framework 6.1, Java 17+. This lesson distinguishes three seemingly similar causes when an auto-configured feature does not work: **auto-configuration was not imported**, **a condition did not match**, and **the bean was selected for creation yet failed to instantiate**. The examples are scenarios observable via logs, the condition report, and tests, avoiding conflating "bean not found" with "application failed to start".

## 1. Three Different Questions

When a Spring Boot application receives a starter, many people immediately ask: "Why is bean X missing?". That question glosses over very important boundaries.

1. **Was the configuration discovered and imported?** Did Spring Boot bring the auto-configuration class name into `@Import` processing?
2. **Did the configuration or `@Bean` method pass its conditions?** The class may have been found, yet `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, etc., did not match.
3. **Once the bean definition was registered, was the bean instance created successfully?** A factory method, constructor, dependency injection, or lifecycle callback can throw an error during context initialization.

These three states are not equivalent. They require different evidence, different fixes, and different kinds of tests.

| State | What happened | What did not happen | Common symptoms |
| --- | --- | --- | --- |
| **Not imported** | Selector may not have found the candidate or removed it via exclusion | Spring never processed that auto-configuration as an active import | Missing imports resource, class absent from candidate list, explicit exclusion |
| **Condition did not match** | Configuration was an evaluation candidate; Spring/Boot checked relevant conditions | The corresponding bean definition was not registered, or the whole configuration was skipped | Negative matches in condition report, property/classpath/bean condition failure |
| **Bean creation failed** | Bean definition exists and Spring started creating the instance | No working bean resulted; for typical eager beans, context refresh fails | `BeanCreationException`, `Caused by` chain from constructor/factory/dependency/lifecycle |

**Warning:** The table is a diagnostic model. Boot has optimizations that filter conditions during the selection phase; a classpath condition can filter out a candidate early. For an accurate conclusion, verify the *cause* and processing timing rather than inferring solely from a class not appearing in one log list.

## 2. Timeline Map: From JAR to Object

```text
Application startup / SpringApplication.run(...)
                 |
                 v
@SpringBootApplication => @EnableAutoConfiguration
                 |
                 v
@Import(AutoConfigurationImportSelector.class)
                 |
                 +--> Read META-INF/spring/*.AutoConfiguration.imports
                 |      |
                 |      +--> Class name missing? ---------> NOT IMPORTED
                 |      |
                 |      +--> Excluded / filtered out? ----> NOT IMPORTED
                 |
                 v
Candidate auto-configuration evaluated
                 |
                 +--> @Conditional does not match -----> SKIPPED BY CONDITION
                 |
                 v
Register matching bean definitions
                 |
                 +--> @Bean method condition fails ----> BEAN NOT REGISTERED
                 |
                 v
Spring resolves dependencies, creates instance
                 |
                 +--> constructor/factory/init throws -> CREATION FAILED
                 |
                 v
ApplicationContext refresh succeeds
                 |
                 v
ApplicationRunner, CommandLineRunner, app serves requests
```

`AutoConfigurationImportSelector` selects configuration class names; `@Conditional` can act at class or bean-method level; the bean factory instantiates objects after bean definitions are registered. **Selecting a candidate does not mean Spring creates objects immediately.**

### 2.1. "Bean Absent" Is Not Yet a Root Cause

A query like `context.getBeanProvider(Client.class).getIfAvailable()` returning `null` can happen because:
- No configuration provides the bean;
- The auto-configuration class was not found or was excluded;
- A class-level condition failed;
- A bean-method-level condition failed;
- The bean was registered under a different type/name;
- The bean is configured as lazy and has not been created yet (in which case the bean *may still have a definition*; the provider can normally instantiate it when requested);
- The context already failed before the query could execute.

Therefore, separate the questions **was the bean definition registered?** and **was the instance created successfully?**. Do not treat a runner not printing an output line as proof that a configuration was not imported: the runner may never have run because the context failed.

### 2.2. Three States Do Not Preclude Mixed Scenarios

An application can have multiple auto-configurations where one class is excluded, another class fails a condition, and a third class's bean fails during creation. Thus diagnosis must be tied to **a specific configuration class and a specific bean**, rather than concluding the entire system is in one state.

## 3. Case 1 — Auto-Configuration Was Not Imported

An auto-configuration is automatically discovered by Spring Boot only when a valid discovery path exists. In Boot 3.x, a typical library declares the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example content:

```text
com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

This file contains the **fully qualified name** of the auto-configuration class — not bean names, not artifact names, and not an instruction to "create the bean immediately".

### 3.1. Common Reasons a Configuration Is Not Imported

- **Auto-configuration not enabled:** the application lacks `@EnableAutoConfiguration` (usually included via `@SpringBootApplication`), or `spring.boot.enableautoconfiguration=false` disabled the default mechanism.
- **JAR missing from runtime classpath:** the dependency is only in test/compile scope, excluded from the dependency graph, or the deployed artifact was not updated.
- **JAR present but missing imports resource:** the library compiles, yet the resource has the wrong name/path or was not packaged.
- **Wrong class name in imports:** package/class renamed without updating metadata, or mismatched artifact version published.
- **Explicitly excluded:** `@SpringBootApplication(exclude=...)`, `excludeName`, or `spring.autoconfigure.exclude` removes the configuration from the applied list.
- **Early candidate filtering:** import filters/classpath metadata can eliminate a candidate before Spring deeply processes the configuration class; this case requires verifying filters and relevant conditions rather than assuming "JAR not found".
- **Different class/resource loading mechanism than expected:** the ClassLoader or packaging approach in the deployment environment hides the imports resource.

In Boot 3.x, declaring auto-configuration candidates via the imports file is the standard approach. Older versions used the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `META-INF/spring.factories`; do not copy old metadata blindly without checking the convention for your Boot version.

### 3.2. Exclusion Is an Intentional "Do Not Import" Decision

Property example:

```properties
spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

When the class is listed as a valid candidate, that configuration is excluded from default auto-configuration. This **does not remove the JAR**, does not delete beans of the same type created by the app or other auto-configurations, and is not `@ConditionalOnProperty`.

Two corresponding annotation options:

```java
@SpringBootApplication(exclude = DemoAutoConfiguration.class)
```

```java
@SpringBootApplication(excludeName =
        "com.example.diagnostics.autoconfigure.DemoAutoConfiguration")
```

The two snippets above are **alternative annotation fragments**, not two annotations placed simultaneously on one class and not standalone Java files. `exclude` requires a compile-time class literal; `excludeName` takes an FQCN string and is useful when avoiding a compile-time dependency on that class.

**Check before excluding:** the target must be an eligible auto-configuration class, not a regular application `@Configuration`. When excluding a class that is present yet not a valid auto-configuration candidate, Boot may report an invalid exclusion configuration.

### 3.3. What Evidence Helps Classify "Not Imported"?

Check in order:
1. `jar tf` / artifact contents to verify the class and imports resource are packaged.
2. Build dependency graph and actual runtime classpath.
3. `@EnableAutoConfiguration` annotation and exclusions (annotation/property).
4. Condition evaluation report: inspect the **Exclusions** section; if a configuration does not appear in the report, gather evidence on imports/JAR instead of immediately concluding a condition failed.
5. If using a custom loader, inspect the active resource loader and ClassLoader.

**Common pitfall:** "Not seeing the auto-configuration in Positive matches" is not enough to confirm it was not imported. It could be in Negative matches, Exclusions, or Unconditional classes, or the report output may have been filtered differently.

## 4. Case 2 — Configuration or `@Bean` Condition Did Not Match

Suppose Boot evaluated the class, yet a condition blocked it:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class DemoAutoConfiguration {
    // @Bean methods are evaluated only if the class-level condition passes.
}
```

This is an **illustrative fragment**, not complete compilable code.

When `demo.feature.enabled=false`, the class-level condition does not match. Default beans of the class are not registered. **This is not a bean creation error**: the factory method was never called and did not throw an exception.

### 4.1. Distinguishing Class Conditions and Method Conditions

Two distinct condition levels:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(ClientAdapter.class)
    ClientAdapter clientAdapter() { /* ... */ }
}
```

This fragment uses hypothetical types and **does not compile standalone**.

- `@ConditionalOnClass` on the class decides whether to apply the entire configuration; if the SDK is missing, the guarded configuration is skipped.
- `@ConditionalOnMissingBean` on `@Bean` decides whether **only that default bean** is registered. If the application already supplied another adapter, the condition does not match and the default bean yields.
- When the default bean backs off, the context can still contain **the application's bean of the same type**. Hence "default bean not created" does not mean "no bean exists".
- A configuration can be imported yet **contribute zero beans**, or contribute only some bean methods depending on conditions.

### 4.2. Common Causes of Unmatched Conditions

| Condition | Question | Unmatched scenario |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the type present on the loader-visible classpath? | Optional SDK missing at runtime |
| `@ConditionalOnMissingClass` | Is the type absent? | A class that must be absent is present |
| `@ConditionalOnProperty` | Does the property value match the activation rule? | `enabled=false` or property missing when `matchIfMissing=false` |
| `@ConditionalOnBean` | Is a matching bean already known to Spring at check time? | Required bean type/name not present yet |
| `@ConditionalOnMissingBean` | Is a matching bean absent? | Application already declared a matching bean |
| `@ConditionalOnWebApplication` | Does the context have the matching web type? | Running a batch/non-web context |
| `@ConditionalOnResource` | Was the corresponding resource found? | Configuration file/resource not present |

Conditions based on bean definitions must pay attention to **configuration processing order**. Auto-configurations are deferred to allow application configurations to register bean definitions first, which does not mean every bean is already instantiated when conditions run.

### 4.3. How to Read the Condition Report

Run the application with `--debug`:

```bash
java -jar app.jar --debug
```

Or with the Maven plugin:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug"
```

Common sections in the condition evaluation report:
- **Positive matches**: conditions reported as having matched.
- **Negative matches**: conditions reported as not having matched, along with reasons.
- **Exclusions**: names of excluded auto-configurations.
- **Unconditional classes**: configurations reported as having no matching conditions at this level.

Formatting and wording can vary across versions/patches. A custom condition returning only a boolean may lack clear messages like Boot's built-in conditions; when good diagnostics are needed, consider `SpringBootCondition` with `ConditionOutcome`.

### 4.4. "Not Shown in the Report" Does Not Guarantee "Not Imported"

Some classpath conditions can be processed early from metadata and displayed via a separate reporting mechanism. Observability depends on Spring Boot version, log level, and how the report is collected. Cross-check the imports resource, exclusions, bean definitions, logs, and exception chains. Avoid jumping to conclusions from a single absent entry.

## 5. Case 3 — Bean Was Selected, Yet Creation Failed

Once Spring registers a bean definition, object creation can still fail:

```java
@Bean
DemoService demoService() {
    throw new IllegalStateException("Simulated bean creation failure");
}
```

This is a fragment placed inside a configuration, not a standalone Java file. The bean definition can exist, yet the **factory method** throws an exception when Spring invokes it. For a default eager singleton, context refresh usually fails and the Spring Boot application fails to complete startup.

### 5.1. Failure Points After a Bean Definition Is Registered

| Stage | Example failure | Typical evidence |
| --- | --- | --- |
| Resolve dependencies | Missing required bean, ambiguity, circular dependency | `UnsatisfiedDependencyException`, `NoUniqueBeanDefinitionException`, or related exceptions |
| Constructor/factory method | Runtime exception, missing credentials, invalid parameter | `BeanCreationException` with root cause |
| Property binding / validation | Invalid port/range, type conversion failure | Binding/validation exception |
| Init callback | `@PostConstruct`, `InitializingBean`, init method throws | `BeanCreationException` with nested cause |
| FactoryBean / type initialization | Factory or type resolution failure | FactoryBean creation/lookup exception |
| External resources | DB connection, message broker, or filesystem unavailable | Underlying driver/client exception, possibly wrapped |
| Runtime class/API linkage | `NoClassDefFoundError`, `NoSuchMethodError` | A form of `LinkageError`, not merely a false condition |

**Do not fix every startup error by adding `@ConditionalOnClass`**. If the class exists yet a dependency is misconfigured, an endpoint is unreachable, or a constructor throws an exception, the class condition may have matched completely legitimately.

### 5.2. Difference Between Eager, Lazy, and Subsequent Usage

Not every bean is created during context refresh:
- Typical **non-lazy** singletons are created during startup; bean creation failures cause startup to fail.
- **Lazy** beans may stay uninstantiated until requested; the context may start successfully while the failure surfaces later on a request or dependency lookup.
- Prototypes are normally created when fetched from the factory; errors occur only when actually requested.
- A business method throwing an exception **after the bean has been created** is a functional execution error, not necessarily a bean creation failure.

Therefore, "application started" does not prove every lazy bean works, and "startup failed" does not automatically mean a configuration was not imported. Read the exact exception and lifecycle.

### 5.3. Why Must You Read the Root Cause?

Conceptual condensed stack trace example:

```text
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'demoService'
Caused by: java.lang.IllegalStateException:
  Simulated bean creation failure
```

This is a **content illustration**, not a character-for-character guarantee of real log output. The root cause `IllegalStateException` clearly tells us the factory method was executed and threw an error. That is completely different from an unmatched condition, where the method is never called.

A chain can contain multiple wrapper layers — for example, an exception from dependency A wrapped inside a failure to create bean B. Read from the first failing bean down to the **deepest `Caused by`** to find the root culprit.

## 6. Quick Diagnostic Matrix

| Observation | First question to ask | Confirming evidence | Action to take |
| --- | --- | --- | --- |
| Configuration name missing from imports/JAR | Was metadata packaged properly? | `jar tf`, imports contents, dependency graph | Fix packaging/dependencies/metadata |
| Configuration appears in Exclusions | Who excluded it? | `spring.autoconfigure.exclude`, `exclude`/`excludeName` annotations | Remove exclusion if unintended |
| Configuration appears in Negative matches | Which condition failed to match? | Condition evaluation report | Fix property/classpath/bean condition or accept skip |
| Configuration matched yet default bean missing | Did the bean-method condition back off? | Report + bean definitions + user bean | Keep user override or adjust default policy |
| Context failed creating `demoService` | What did factory/constructor/init throw? | `BeanCreationException` + root cause | Fix code, dependencies, and runtime config |
| Context starts yet first request fails | Lazy bean or business method? | Request logs, lifecycle, lazy/prototype | Fix runtime call or bean initialization |
| Tests pass yet deployment lacks the bean | Does artifact/runtime differ from tests? | JAR manifest/imports, resolved versions, image | Check environment and classloader |

One practical rule: **gather evidence for the current layer before changing another layer**. Do not delete an exclusion to cure a constructor bug; do not flip a property flag to cure a missing imports resource.

## 7. Complete Demo: One Service, Three Outcomes

Create a small Spring Boot Maven project. The goal is to observe clearly:
1. **Not imported** by excluding the auto-configuration during selection;
2. **Condition unmatched** via property;
3. **Bean creation failure** via a factory method intentionally throwing an exception.

The example uses **Java 17, Spring Boot 3.3.13**, requiring no database or web server. When the app runs normally, the runner prints one line so you can see the bean working.

### 7.1. Project Structure

```text
autoconfig-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── diagnostics/
    │   │       ├── DemoService.java
    │   │       └── autoconfigure/DemoAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/diagnostics/
        └── AutoConfigurationDiagnosisTest.java
```

Place `DemoApplication` in package `com.example.app` and the auto-configuration class in `com.example.diagnostics.autoconfigure`. The two packages are sibling branches, so the app's default component scan does not pick up the library; the **imports resource** is responsible for registering the candidate.

### 7.2. Maven pom.xml

```xml
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

    <groupId>com.example</groupId>
    <artifactId>autoconfig-diagnosis-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

The parent manages dependency versions compatible with Boot 3.3.13. Install JDK 17+ and Maven before running `mvn` commands.

### 7.3. The DemoService Contract

Create `src/main/java/com/example/diagnostics/DemoService.java`:

```java
package com.example.diagnostics;

@FunctionalInterface
public interface DemoService {
    String handle(String request);
}
```

Keep the API Spring-neutral to illustrate "presence or absence of an implementing bean" without depending on web/database. It has no custom constructor or lifecycle.

### 7.4. Auto-Configuration with Both a Condition and a Failable Bean Path

Create `src/main/java/com/example/diagnostics/autoconfigure/DemoAutoConfiguration.java`:

```java
package com.example.diagnostics.autoconfigure;

import com.example.diagnostics.DemoService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoService.class)
    DemoService demoService(Environment environment) {
        boolean shouldFail = environment.getProperty(
                "demo.feature.fail", Boolean.class, false);

        if (shouldFail) {
            throw new IllegalStateException(
                    "Simulated bean creation failure");
        }

        return request -> "OK:" + request;
    }
}
```

Exact breakdown across the three states:

- If the class **is excluded**, the selector does not import `DemoAutoConfiguration`; Spring does not process `demoService` from this class.
- If the class **is evaluated yet `demo.feature.enabled=false`**, `@ConditionalOnProperty` does not match and `demoService` is not registered.
- If the class **is evaluated and conditions match**, the bean definition is registered; when Spring invokes the factory method, `demo.feature.fail=true` makes it throw `IllegalStateException`. This triggers a bean creation error, typically wrapped in `BeanCreationException`.
- `@ConditionalOnMissingBean(DemoService.class)` is another back-off path: when a consumer creates its own bean, the default factory method is not run. If the app already has a bean and `fail=true`, the app can still run because the default bean yielded. That is proper auto-configuration behavior.
- Because `demo.feature.enabled` uses `matchIfMissing=true`, when this property is omitted Spring treats the condition as matching by default. That is a choice of this example; not all Boot features are enabled by default.

### 7.5. Imports File Giving the Selector the Candidate Name

Create the exact file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

If this file is deleted from the artifact or has the wrong FQCN, Spring Boot 3.x discovery will not find this configuration. **In the demo, we use exclusion to simulate "not imported" without editing/deleting resources on every run.** Keep the imports file intact when testing the condition and bean creation states so you do not mix multiple causes.

### 7.6. App Observing the Bean on Successful Startup

Create `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.diagnostics.DemoService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printService(ObjectProvider<DemoService> services) {
        return args -> {
            DemoService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "SERVICE=ABSENT"
                    : "SERVICE=" + service.handle("ping"));
        };
    }
}
```

`ObjectProvider` is intentional: when the bean is not registered, the app can still start and print `SERVICE=ABSENT`. If the runner injected a required `DemoService` parameter directly, non-import or condition failure would trigger an injection failure on **the runner**, blurring the three states together. That is precisely why the demo avoids required injection.

### 7.7. Default Case: Configuration Present, Conditions Match, Bean Works

Run from the directory containing the POM:

```bash
mvn test
mvn spring-boot:run
```

Line printed by `ApplicationRunner`:

```text
SERVICE=OK:ping
```

Maven and Spring Boot may print additional startup logs. That is only the line *produced by the runner*, not the entire stdout.

### 7.8. Scenario A: Not Imported Due to Exclusion

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration"
```

Line printed by the runner:

```text
SERVICE=ABSENT
```

Reason: the configuration was removed from auto-configuration selection. `DemoService` is absent because **no default configuration was imported**, not because the `demoService` method threw an error.

Try adding `--debug` to read the Exclusions section:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration"
```

When troubleshooting a real project, check whether an exclusion is intentional or accidentally passed through environment/configuration.

### 7.9. Scenario B: Condition Did Not Match

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.feature.enabled=false"
```

The line printed by the runner is also:

```text
SERVICE=ABSENT
```

**Yet the cause differs from A.** In B, the class remains a candidate in imports and is not excluded; `@ConditionalOnProperty` blocks applying the configuration. The condition evaluation report will show a negative match on `DemoAutoConfiguration` for the property condition.

Read the report:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --demo.feature.enabled=false"
```

Do not compare only runner stdout: A and B produce **the same business output** yet have **different causes in the pipeline**.

### 7.10. Scenario C: Bean Selected, Yet Creation Failed

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.feature.fail=true"
```

Here `demo.feature.enabled` still defaults to true, so the configuration matches. `demoService(...)` is called and throws:

```text
java.lang.IllegalStateException: Simulated bean creation failure
```

Spring Boot **does not finish startup** when an eager singleton fails. Neither `SERVICE=ABSENT` nor `SERVICE=OK:ping` appears from the runner, because runners execute only after context startup succeeds. The console will show error logs and an exception chain broader than the snippet above; the snippet shows the **root cause** to look for.

Diagnosing with report/logs:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --demo.feature.fail=true"
```

Scenario C typically shows `BeanCreationException` wrapping `IllegalStateException`. This is **not a negative condition**; conditions can match while the factory method still fails.

### 7.11. Scenario D: Consumer Overrides the Default Bean

Add the following method **inside the `DemoApplication` class** (not as a standalone Java file):

```java
@Bean
DemoService customDemoService() {
    return request -> "CUSTOM:" + request;
}
```

Run with default properties:

```text
SERVICE=CUSTOM:ping
```

Even though imports and the class-level condition still allow processing the auto-configuration, `@ConditionalOnMissingBean` prevents registering the default bean because the app already supplied `DemoService`. This is a case of **the bean-method condition not matching while the app still has a bean of that type**.

If you run `demo.feature.fail=true` when the custom bean is already present, the default factory method is never called so no error is thrown; the result remains `SERVICE=CUSTOM:ping`. This demonstrates that "factory method fails" is not an inevitable consequence merely because a property exists — it depends on which bean definition was actually selected.

**Note:** Delete the custom method after the experiment to return to the default results in scenarios A–C.

## 8. Automatically Testing All Three States with ApplicationContextRunner

A good test suite does not merely assert "bean absent". It must distinguish:
- Context **starts successfully** yet the bean is absent;
- Context **fails to start** due to a bean creation error;
- Context **has the consumer's bean** and auto-configuration backs off.

Create `src/test/java/com/example/diagnostics/AutoConfigurationDiagnosisTest.java`:

```java
package com.example.diagnostics;

import com.example.diagnostics.autoconfigure.DemoAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiagnosisTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestApplication.class);

    @Test
    void defaultAutoConfigurationCreatesBean() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoService.class);
            assertThat(context.getBean(DemoService.class)
                    .handle("ping")).isEqualTo("OK:ping");
        });
    }

    @Test
    void explicitlyExcludedConfigurationIsNotApplied() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                        + DemoAutoConfiguration.class.getName())
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(DemoService.class);
                });
    }

    @Test
    void unmatchedConditionSkipsBeanWithoutFailingStartup() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(DemoService.class);
                });
    }

    @Test
    void factoryFailurePreventsContextStartup() {
        runner.withPropertyValues("demo.feature.fail=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }

    @Test
    void consumerBeanMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(ConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DemoService.class);
                    assertThat(context.getBean(DemoService.class)
                            .handle("ping")).isEqualTo("CUSTOM:ping");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class ConsumerConfiguration {
        @Bean
        DemoService customDemoService() {
            return request -> "CUSTOM:" + request;
        }
    }
}
```

The test deliberately puts `@EnableAutoConfiguration` on a test configuration so it flows through **`AutoConfigurationImportSelector`** and the imports file. Unlike:

```java
.withConfiguration(AutoConfigurations.of(DemoAutoConfiguration.class))
```

supplying the class directly as in the line above **bypasses candidate discovery from imports**, making it unsuitable when the test goal is proving exclusion in the selector. That line is an illustrative fragment, not part of the test class above.

### 8.1. Why Do Tests Not Assert "No Bean" for All Three Cases?

`factoryFailurePreventsContextStartup` does not assert `doesNotHaveBean` because **the context did not finish refreshing**. When the runner detects a startup failure, the proper checks are `hasFailed()` and `getStartupFailure()`; do not query beans as if the context were healthy.

The `explicitlyExcluded...` and `unmatchedCondition...` tests assert `hasNotFailed()` followed by `doesNotHaveBean(...)`, because missing the bean is the **expected** result when a configuration is unimported or blocked by a condition.

The default/consumer tests show the bean being created and overridden properly, though they do not fully replace an integration test against a published library JAR.

### 8.2. Running Tests and Checking Packaging

```bash
mvn test
mvn package
jar tf target/autoconfig-diagnosis-demo-0.0.1-SNAPSHOT.jar
```

In an executable JAR, you should see the resource:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In a regular library JAR, the resource sits directly under `META-INF/spring/...` from the root. If Maven tests pass yet the deployed artifact lacks the resource, runtime auto-configuration discovery will differ from tests.

### 8.3. Expectation Matrix

| Case | Config selected for evaluation? | Class/method condition matches? | Bean instantiated? | Resulting context |
| --- | --- | --- | --- | --- |
| Default | Yes | Yes | Succeeded | Started; `SERVICE=OK:ping` |
| Exclude configuration | No | Not evaluated via auto-config path | No default | Started; `SERVICE=ABSENT` |
| Property enabled=false | Candidate present; blocked by condition | No at class level | No default | Started; `SERVICE=ABSENT` |
| Property fail=true | Yes | Yes | **Failed** | **Startup failure**; runner does not run |
| Consumer supplies `DemoService` | Yes | Class matches; bean-method missing-bean condition fails | Consumer bean used | Started; `SERVICE=CUSTOM:ping` |

"Selected for evaluation" is conceptual; whether a class is filtered early via optimized import filters requires deeper analysis of the implementation. For the demo's property condition, the core cause remains **not matching**, not a missing imports resource.

## 9. ConditionEvaluationReport: Use Evidence Instead of Guessing

In Spring Boot, `ConditionEvaluationReport` records condition details for auto-configurations and certain other sources. When run with `--debug`, the app typically logs the condition report, helping inspect what matched or did not match.

### 9.1. Exclusions and Negative Matches Are Not the Same Section

- `Exclusions`: auto-configurations **explicitly requested to be excluded** via annotations/properties.
- `Negative matches`: conditions reported as **not satisfied** when evaluating a configuration or bean method.
- `Positive matches`: conditions **satisfied**.
- `Unconditional classes`: configurations reported as having no corresponding conditions at this level.

In the demo:
- Exclude `DemoAutoConfiguration` → check **Exclusions**.
- `demo.feature.enabled=false` → find the unmatched property condition reason.
- `demo.feature.fail=true` → the property condition still matches, yet logs show a bean creation error; do not look for the primary cause under Negative matches.
- Consumer bean → method-level `@ConditionalOnMissingBean` fails to match; you will see a reason noting an existing bean.

### 9.2. When a Class Does Not Appear in the Report

Do not jump to "config not imported". Check:
1. Does the imports resource contain that name in the **runtime artifact**?
2. Were any exclusions applied?
3. Is the class on the runtime classpath?
4. Was there an FQCN typo, version mismatch, or package move?
5. Was logging actually enabled/capturing the full report?
6. Did an optimized filter evaluate a class condition before the parsing step?

Similarly, do not conclude "the bean was already created" just from seeing a positive match on the class; the factory method can still fail when instantiating the bean.

### 9.3. Reading Bean Creation Failures Properly

An error chain typically looks like:

```text
Error creating bean with name 'demoService'
...
Caused by: java.lang.IllegalStateException:
  Simulated bean creation failure
```

This content is a **condensed illustration**, not a full stack trace guaranteed identical across patch versions. Read the deepest `Caused by`, while checking the first bean that failed. If bean B failed because injecting bean A failed, the fix likely belongs in A.

### 9.4. Actuator Conditions Endpoint

If `spring-boot-starter-actuator` is present, the `/actuator/conditions` endpoint can return conditions when configured to expose and authorized properly. This helps view the report over HTTP, yet **never expose the endpoint publicly in production without restrictions**: the report can leak dependency/configuration structure. The current demo does not need Actuator.

## 10. How to Classify Failures from Logs and Exceptions

### 10.1. Not Imported: Usually No BeanCreationException from That Bean

When a class is not imported, Spring does not call its factory method along that path. However, the application **can still** hit another error: a required bean elsewhere demands the missing service, throwing `UnsatisfiedDependencyException`.

Example:
- `FeatureAutoConfiguration` is excluded;
- Another controller/service requires injecting `FeatureClient`;
- No `FeatureClient` bean exists → startup may fail due to injection.

Here, the immediate cause is **missing dependency** on the controller/service; the upstream cause is that the configuration was excluded. Do not call this "auto-configuration factory method failed", because the method never ran.

### 10.2. Condition Unmatched: A Missing Bean Can Be Intended Design

`@ConditionalOnMissingBean` not matching when the consumer has its own bean is usually good behavior. `@ConditionalOnProperty` not matching when the user intentionally disabled a feature is also expected behavior.

Do not try to force every condition to match by deleting user beans or adding unneeded SDKs. First read the starter's contract: is it default-on or opt-in, and what classpath/bean/property/web environment requirements does it have?

### 10.3. Bean Creation Failed: Not Necessarily a Wrong Condition Config

If conditions match, the factory method is chosen, and it fails due to a missing token/URL, adding `@ConditionalOnProperty` may let startup avoid the error yet could also hide misconfiguration. Deciding between fail-fast and optional/degraded behavior must follow the business contract:
- Essential service → failing startup with a clear message may be right.
- Optional feature → disabling via property or a valid fallback may fit.
- Unstable external connection → retry/backoff/health policy instead of faking a classpath condition.

Conditions should be **side-effect-free**; a network probe inside `Condition.matches` is no substitute for health checks or connection management.

## 11. Common Mistakes

| Mistake | Why it leads to misdiagnosis | How to fix |
| --- | --- | --- |
| "No bean" = "auto-config not imported" | A condition may not have matched, or the default bean backed off | Check imports + exclusions + condition report |
| "Class missing from Positive matches" = "missing JAR" | Class may be in Negative/Exclusions/Unconditional classes | Read the full report and JAR metadata |
| "Condition true" = "object already created" | Conditions primarily decide definition registration | Inspect bean lifecycle and root cause |
| "Startup failed" = "wrong `@ConditionalOnClass`" | Could be a constructor, binding, injection, or external API error | Read stack trace and exception chain |
| "Change property and bean appears in running context" | Conditions are normally evaluated when building the context | Start a new context or use a properly designed runtime toggle |
| "Excluding auto-config removes the dependency" | JAR/classes remain on the runtime classpath | Edit the build graph if you want to drop the dependency |
| "`@ConditionalOnMissingBean` broke the service" | It yielded to the consumer bean; that type may still exist | Check bean owner/name/type |
| "Test a non-starting context with getBean" | Context did not complete refresh | Assert startup failure and root cause |
| "Test with AutoConfigurations.of tests discovery" | Passes the class directly, so it does not prove imports resource | Test `@EnableAutoConfiguration` + consumer/JAR |
| "Bean didn't fail at startup so it won't fail" | Lazy/prototype beans and runtime methods can fail later | Test lifecycle and first-use |
| "Enabling --debug replaces all error logs" | Report lists conditions, not factory failure stack traces | Combine report, cause, config, and runtime artifact |
| "Adding `@Conditional` to hide BeanCreationException suffices" | May merely mask the problem without fixing config contract | Clarify whether the feature is optional or required |

## 12. Diagnostic Checklist in Real Projects

When suspecting auto-configuration, follow these steps in order:

1. **Identify the exact bean and class under investigation:** bean name, type, expected auto-configuration, artifact/starter.
2. **Verify the runtime artifact:** run `mvn dependency:tree` or Gradle `dependencies --configuration runtimeClasspath`; check the deployed image/JAR, imports resource, and FQCN.
3. **Verify activation path:** is `@EnableAutoConfiguration` enabled? Is `spring.boot.enableautoconfiguration=false` set?
4. **Check exclusions:** `@SpringBootApplication(exclude...)`, `excludeName`, `spring.autoconfigure.exclude`, Exclusions in the report.
5. **Read class-level conditions:** `@ConditionalOnClass`, property, web/resource conditions; inspect Negative matches.
6. **Read bean-level conditions:** `@ConditionalOnMissingBean`, `@ConditionalOnBean`; check whether a user bean or another auto-config's bean exists.
7. **If context startup fails:** identify the first failing bean, full `Caused by` chain, method/constructor/init/binding/dependency.
8. **If context runs yet behavior is wrong:** inspect lazy beans, actual instances, and method-level/runtime exceptions.
9. **Reproduce with tests:** write dedicated tests for selection/exclusion, conditions, startup failure, and consumer override.
10. **Cross-check the real environment:** classloader, property precedence, profile, dependency versions, connectors to external services.

Do not change exclusions/properties blindly before gathering evidence. A fix that works locally might just mask a different production bug.

### 12.1. Useful Commands

Maven:

```bash
mvn dependency:tree
mvn test
mvn package
jar tf target/autoconfig-diagnosis-demo-0.0.1-SNAPSHOT.jar
```

Gradle (if the project has the wrapper):

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
```

Dependency commands show the graph resolved by the build tool; if the actual JAR is handled differently by a container/launcher/custom ClassLoader, inspect the classpath of the **running process**, not just the workspace graph.

## 13. Self-Check Questions

**Q1.** `DemoAutoConfiguration` is in the imports resource yet is listed in `spring.autoconfigure.exclude`. Is it applied like a normal auto-configuration?

**Answer:** No. Exclusion removes that name from the default auto-configuration set. The class/JAR may still be present, yet its factory methods do not run via the auto-configuration path.

**Q2.** `demo.feature.enabled=false` makes the runner print `SERVICE=ABSENT`. Can you conclude the imports file is missing?

**Answer:** No. In the demo, imports is still correct; the property condition failed to match, preventing the bean from being registered.

**Q3.** `demo.feature.fail=true` causes startup to fail. Can the condition report still show the class-level condition matching?

**Answer:** Yes. Conditions passed and the bean definition was registered, yet the factory method threw an exception when creating the instance.

**Q4.** Excluding the configuration still leaves a `DemoService` bean in the app. Is this contradictory?

**Answer:** No. The bean can be created by the application, component scanning, or another configuration. Exclusion only removes one specifically named auto-configuration.

**Q5.** `@ConditionalOnMissingBean(DemoService.class)` does not match while the app has a consumer `DemoService`. Is that a startup error?

**Answer:** No; that is intended back-off by design.

**Q6.** A `@Bean` method throws an exception yet is marked `@Lazy`. Why can the application report as started?

**Answer:** Because a lazy bean may not be instantiated during startup. When the bean is requested later, the failure surfaces; test first-use.

**Q7.** Why should a bean creation failure test assert `getStartupFailure()` rather than only `doesNotHaveBean`?

**Answer:** Because the context has already failed; querying it like a healthy context can be invalid and obscure the real cause.

**Q8.** If an auto-configuration has an unmatched `@ConditionalOnClass`, does the import selector always pick it and only then Spring skips it in every version/path?

**Answer:** No. Boot can filter classpath conditions early from metadata. What matters is identifying **a classpath condition failure**, without mistaking it for a missing imports resource.

**Q9.** Why is `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` not sufficient to test the imports resource?

**Answer:** Because the runner is given the auto-configuration class directly, without needing the selector to discover names from imports. Use a test with `@EnableAutoConfiguration` and inspect the artifact.

**Q10.** If a bean fails while binding configuration properties, at which layer should you fix it?

**Answer:** Bean creation/binding failure — check property values, conversion, validation, and the exception chain; do not blindly remove imports or disable class conditions.

## 14. Key Takeaways

Three conclusions must correspond to three kinds of evidence:

```text
NOT IMPORTED
  -> check candidate resource, classpath, @EnableAutoConfiguration, Exclusions

CONDITION DID NOT MATCH
  -> check condition report, classpath/property/bean condition, phase

BEAN CREATION FAILED
  -> check bean definition, BeanCreationException, deepest cause, lifecycle
```

In practice, a missing bean can be **correct behavior** for an optional feature, whereas a startup failure is a signal to fix code/config/dependencies. Only once you identify which layer you are on can you choose the exact fix and avoid treating the wrong symptom.

### Official Documentation

- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `ConditionEvaluationReport` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 — `ApplicationContextRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Framework 6.1 — `BeanCreationException` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanCreationException.html
- Spring Boot 3.3 — `ConditionalOnMissingBean` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
