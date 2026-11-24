# Cross-Checking Source Code Inferences with a Minimal Context Experiment When Reading Spring Boot Auto-Configuration

When reading an auto-configuration class, we often see annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, and one or more `@Bean` methods. From the source code, we can **infer** which beans are likely to be registered. However, that inference still depends on classpath, properties, application-provided beans, processing order, context hierarchy, and the running Spring Boot version.

The reliable approach is to combine two kinds of evidence:

1. **Read the source code to form a hypothesis:** which class Boot discovers, which conditions must match, which bean methods are allowed to run, and which beans must back off.
2. **Build a minimal context to verify:** load only the auto-configuration under study, control properties and user beans, and observe bean definitions along with `ConditionEvaluationReport`.

Experimentation does not replace reading source code; source code does not replace runtime observation either. Both complement each other: source code explains *why* a branch was designed that way, while a context test confirms *under specific conditions* that branch actually occurs.

## 1. Start with the Exact Version and Artifact

Before reading classes on GitHub or in your IDE, identify the **actually resolved Spring Boot version**. An application may declare one version in its parent or BOM, yet transitive dependencies, plugins, or submodules can make a reader inspect the wrong artifact.

With Maven, start with:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

Read the version of `spring-boot-autoconfigure` in the output. This artifact contains most of Spring Boot's auto-configurations. Also check `spring-boot` and `spring-boot-test` if inspecting bootstrap or the test runner:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot,spring-boot-test,spring-boot-autoconfigure
```

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
```

Once you know the version, open the **matching-version sources JAR**. Maven can download sources JARs with:

```bash
mvn dependency:sources -DincludeGroupIds=org.springframework.boot
```

In the IDE, you can open `External Libraries` or use `Go to Declaration` to jump into source. If only bytecode is available, a decompiler is a temporary reading option; remember that bytecode does not preserve all comments, parameter names, or original source structure. Do not compare `main`-branch source against an application running Boot 3.3.x and assume every detail is identical.

**Rule:** record the version, artifact coordinates, and class you are reading. When an experiment yields a different result than predicted, the first step is confirming the test and application use the **same version**.

## 2. Trace the Auto-Configuration Loading Path Before Reading Conditions

A class named `*AutoConfiguration` is not automatically loaded just because it resides inside a dependency JAR. In Spring Boot 3.x, auto-configuration candidates are published in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line lists the fully qualified name of an auto-configuration class. When reading a starter or library, check this resource **inside the exact JAR**:

```text
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.storage.autoconfigure.StorageWebAutoConfiguration
```

The names above are only examples. In a real JAR, locate the resource via your IDE, the `jar tf` command, or an archive viewer. If the class is not listed, look for another registration mechanism or find out why the class is not a candidate.

At a high level, the path is:

```text
@SpringBootApplication / @EnableAutoConfiguration
                 |
                 v
      AutoConfigurationImportSelector
                 |
                 v
  Find candidates from AutoConfiguration.imports
                 |
                 v
       Apply exclusions / filters
                 |
                 v
       Order auto-configurations
                 |
                 v
     Process classes and @Conditionals
                 |
                 v
       Register matching bean definitions
                 |
                 v
       Instantiate beans per dependencies
```

`AutoConfigurationImportSelector` is a `DeferredImportSelector` dedicated to processing auto-configurations. It is a useful reference point when understanding import mechanics at the framework level. In ordinary applications, **do not invoke the selector directly or use its internal APIs**; use the official loading mechanism and test with `AutoConfigurations.of`.

Beyond the imports resource, check:

- `@SpringBootApplication(exclude = …)` or `excludeName`.
- The `spring.autoconfigure.exclude` property.
- `AutoConfigurationImportFilter` and early-filtering metadata if used by the library.
- Whether the starter is actually on the runtime classpath.
- Whether the auto-configuration was accidentally component-scanned or `@Import`ed via another path.

A class missing from the condition report may have **never been a candidate**, been excluded, or been filtered out early. Do not conclude "its condition passed" simply because it is absent from `negativeMatches`.

## 3. Read an Auto-Configuration in Order

Once you confirm the class is loaded, read through the following layers of information. Do not start by guessing from bean names.

### 3.1. Annotations on the Class

Example:

```java
@AutoConfiguration(after = ClientCoreAutoConfiguration.class)
@ConditionalOnClass(ClientApi.class)
@ConditionalOnProperty(
        prefix = "demo.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class ClientAutoConfiguration {
    // Nested configurations and bean methods...
}
```

This is an illustrative snippet; the `ClientApi` and `ClientCoreAutoConfiguration` types must exist in a real project.

Read each annotation and record a hypothesis:

- `@AutoConfiguration`: the class is a configuration designed for the auto-configuration mechanism.
- `after = …`: Boot must apply this class after the named auto-configuration. Ordering affects **bean definition order**, without itself dictating instance creation order.
- `@ConditionalOnClass`: required classes must exist on the classpath.
- `@ConditionalOnProperty`: properties must meet requirements. With `havingValue = "true"` and `matchIfMissing = false`, a missing or non-`true` property causes the condition not to match.
- `@Import` or nested configurations: may open additional configuration branches; continue tracing imported classes.

A class with multiple conditions typically applies only when **all required class conditions** match. If a class condition does not match, the bean methods inside are not processed as if the class were fully enabled.

### 3.2. Nested Configurations and Classpath Conditions

A library may need an API only when a specific feature is installed. Configurations are commonly split as follows:

```java
@AutoConfiguration
public class StorageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(StorageClient.class)
    static class StorageClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(StorageClient.class)
        StorageClient storageClient() {
            return new DefaultStorageClient();
        }
    }
}
```

This is an illustrative excerpt. Isolating classes with optional dependencies inside a nested configuration avoids loading nonexistent types when the optional library is absent. Spring Boot uses metadata to evaluate condition annotations; on a `@Bean` method, the JVM may need to load types appearing in the method signature before the method condition is applied. Therefore, inspect **condition placement**, not just annotation names.

### 3.3. Individual `@Bean` Methods

For each method, record:

- Default bean name and any declared alias names.
- Declared return type, especially interfaces vs implementations.
- `@Conditional` annotations placed directly on the method.
- Injected method parameters and whether they are required or optional.
- Whether `ObjectProvider`, `Optional`, `@Lazy`, or factory beans are used.
- Whether the method depends on properties or other beans.

Example:

```java
@Bean
@ConditionalOnMissingBean(StorageClient.class)
StorageClient storageClient(StorageProperties properties) {
    return new DefaultStorageClient(properties.endpoint());
}
```

Initial inference: when the configuration class applies, if no matching `StorageClient` bean exists and other conditions match, the method can register the default. Yet you must check declared types and previously processed bean definitions. `@ConditionalOnMissingBean` evaluates definitions Spring has processed **up to the moment the condition runs**, not a snapshot including every bean that might appear later.

**Pay attention to return types:** bean-type conditions may rely on the type metadata provided by the method signature. Do not look only at the runtime type of the `return`ed object; the declared return type matters for bean metadata analysis.

### 3.4. Properties and Default Values

Look for `@ConfigurationProperties`, `@DefaultValue`, constructor binding, field initializers, and related property conditions. Distinguish:

- Properties used to **decide whether a configuration is applied**.
- Properties used to **tune bean behavior after the bean is created**.
- Default values in the Java model vs default behavior of `@ConditionalOnProperty`.

For example, `matchIfMissing = true` can enable a condition even when the property does not exist, whereas `matchIfMissing = false` requires the property to exist with the specified value. You cannot conclude solely from seeing a key in `application.yml`; profiles, environment variables, command-line arguments, and property sources can override that value.

### 3.5. Ordering and Dependencies

If `@AutoConfigureBefore`, `@AutoConfigureAfter`, `before/after` on `@AutoConfiguration`, or `@AutoConfigureOrder` is present, record the before/after relationships. Then inspect whether bean methods use `@ConditionalOnBean` or `@ConditionalOnMissingBean`.

Auto-configuration ordering affects **when bean definitions are registered**; subsequent instance creation order depends on constructor injection, the dependency graph, and `@DependsOn`. Do not use bean instantiation order to infer condition evaluation order, or vice versa.

## 4. Turning Inferences into Testable Hypotheses

A good statement specifies **input conditions** and **expected observations**. Avoid vague statements like "this configuration will run".

Example using `ClientAutoConfiguration` above:

| Observed Source Code | Hypothesis to Verify | How to Construct the Scenario |
| --- | --- | --- |
| `@ConditionalOnClass(ClientApi.class)` | Without `ClientApi`, the configuration branch is not applied. | Use `FilteredClassLoader` to hide the class from the runner's classpath. |
| `@ConditionalOnProperty(... enabled=true)` | Setting `demo.client.enabled=false` prevents the configuration. | Use `withPropertyValues`. |
| `@ConditionalOnMissingBean(Client.class)` | With a custom bean of type `Client`, the default method backs off. | Use `withUserConfiguration` to supply a custom bean. |
| `@AutoConfiguration(after = Core.class)` | Configuration is applied after Core in the auto-configuration list. | Load both with `AutoConfigurations.of` and verify condition-dependent behavior. |
| `@Bean` returning `Client` | If conditions match, a bean of type `Client` is registered. | Check the bean by name and type in the context. |

A hypothesis must have a **falsification signal**. For instance, "when the property is false, no bean exists" is falsified if the bean is still present. Then you must check whether a bean of the same name/type came from user configuration, another auto-configuration, or another registration path.

### Three-Layer Evidence Cross-Check Table

| Evidence Layer | Question | Source |
| --- | --- | --- |
| Candidate/discovery | Was the class discovered by Boot and not excluded? | Imports resource, dependency tree, exclusions, import filters. |
| Condition/registration | Which conditions on the class or bean methods matched? | Annotations and condition code; ConditionEvaluationReport. |
| Runtime result | Which beans actually exist in the context and instantiate cleanly? | `ApplicationContextRunner`, bean names/types, startup failures, and dependency graph. |

Do not collapse three questions into one. A class can be a candidate yet fail a condition; a class condition can match yet a bean method backs off; a method can be registered yet instantiation fails due to dependencies or constructor errors.

## 5. Minimal Experiments with `ApplicationContextRunner`

`ApplicationContextRunner` is Spring Boot's test tool for creating a lightweight `ApplicationContext` with controllable configurations, properties, and user beans. Each `run` call builds a context for the test scenario and closes it after the callback.

This is the right way to verify auto-configuration because you do not need to launch the full application, HTTP server, database, or unrelated integrations. The test loads only the auto-configurations under investigation.

Common capabilities:

- `withConfiguration(AutoConfigurations.of(...))`: loads the auto-configurations under test.
- `withPropertyValues(...)`: creates environment variants.
- `withUserConfiguration(...)`: adds application bean configurations.
- `withBean(...)`: adds beans directly into the test context.
- `withClassLoader(new FilteredClassLoader(...))`: simulates missing optional classes/dependencies.
- `withInitializer(ConditionEvaluationReportLoggingListener...)`: logs the Condition Evaluation Report.

**Do not build a giant test context mirroring the whole app right away.** Create the smallest context capable of reproducing the hypothesis; after confirming each condition, expand the test to add real dependencies or configurations.

## 6. Complete Example: Reading Conditions Then Verifying with Context

We use a hypothetical auto-configuration with two condition layers:

1. Configuration activates only when `demo.feature.enabled=true`.
2. Default bean is registered only when the application has not provided `FeatureClient`.

Three experiments verify three states: matching property without custom bean; non-matching property; matching property with user custom bean.

### 6.1. Project Structure

```text
source-context-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── SourceVsContextTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>source-context-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
</project>
```

### 6.2. Complete Test File

Create `src/test/java/demo/SourceVsContextTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SourceVsContextTest {

    record FeatureClient(String source) {
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
    )
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeatureClient.class)
        FeatureClient featureClient() {
            return new FeatureClient("default");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        FeatureClient customFeatureClient() {
            return new FeatureClient("custom");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FeatureAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
            AssertableApplicationContext context, String sourceSuffix) {

        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith(sourceSuffix))
                .map(entry -> entry.getValue())
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No condition report entry ending with " + sourceSuffix
                ));
    }

    @Test
    void matchingPropertyRegistersDefaultBean() {
        runner.withPropertyValues("demo.feature.enabled=true")
                .run(context -> {
                    assertThat(context.getBeansOfType(FeatureClient.class))
                            .containsOnlyKeys("featureClient");

                    assertThat(context.getBean(FeatureClient.class).source())
                            .isEqualTo("default");

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isTrue();

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                                    + "#featureClient"
                    ).isFullMatch()).isTrue();
                });
    }

    @Test
    void propertyMismatchPreventsConfiguration() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(FeatureClient.class);

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isFalse();
                });
    }

    @Test
    void userBeanMakesDefaultMethodBackOff() {
        runner.withPropertyValues("demo.feature.enabled=true")
                .withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(FeatureClient.class))
                            .containsOnlyKeys("customFeatureClient");

                    assertThat(context.getBean(FeatureClient.class).source())
                            .isEqualTo("custom");

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isTrue();

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                                    + "#featureClient"
                    ).isFullMatch()).isFalse();
                });
    }
}
```

Run from the `source-context-lab` directory with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** three tests pass; Surefire typically prints a summary like `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0`. The test code does not call `System.out.println`, so there is no fixed business stdout.

### 6.3. Comparing Results Against Source Inferences

Before running, we read:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
static class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FeatureClient.class)
    FeatureClient featureClient() {
        return new FeatureClient("default");
    }
}
```

From source code, we formed three predictions:

| Experiment | Prediction from Source | Observations to Verify |
| --- | --- | --- |
| `enabled=true`, no user bean | Class condition matches; method condition matches; default is registered. | Only `featureClient`, source `default`; both report sources are full match. |
| `enabled=false` | Class condition does not match; method creates no default. | No `FeatureClient`; class report is not full match. |
| `enabled=true`, with user bean | Class condition matches; missing-bean method condition does not match. | Only `customFeatureClient`; class report is full match, yet method is not full match. |

This directly demonstrates the difference between a **class-level condition** and a **bean-method condition**. In the third case, the entire auto-configuration is not excluded; the class-level property condition still matches, while the `featureClient` method backs off because the user already registered a bean of the same type.

The `outcomesFor` helper reads `ConditionEvaluationReport` from the exact BeanFactory of the test context. The report groups conditions by source; a source can be a configuration class name or `ClassName#methodName`. `isFullMatch()` tells whether every outcome recorded for that source matched. To inspect detailed messages, iterate over each `ConditionAndOutcome` in the collection and check its condition/outcome.

**Do not assert only that the context starts successfully.** A context can start even when an auto-configuration was not applied. Assert both bean names/types and condition reports to prove the conclusion.

## 7. Adding One Variable at a Time When a Hypothesis Needs Classpath or Web Context

Once property and user-bean tests are clear, expand one factor at a time.

### 7.1. Simulating Missing Optional Class on Classpath

Spring Boot provides `FilteredClassLoader`:

```java
runner.withClassLoader(new FilteredClassLoader(OptionalClientApi.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(OptionalClient.class);
        });
```

This is an **illustrative snippet** requiring the corresponding class condition on the auto-configuration. If the optional class is referenced in a method signature, isolate that method inside a nested configuration with `@ConditionalOnClass` to avoid loading missing types from the classpath. This experiment simulates an absent dependency; it does not replace checking the application's actual runtime classpath.

### 7.2. Conditions Dedicated to Web Applications

If the source has `@ConditionalOnWebApplication`, the default non-web runner may not represent the application accurately. Use `WebApplicationContextRunner` for Servlet or `ReactiveWebApplicationContextRunner` for Reactive:

```java
new WebApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(WebFeatureAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasSingleBean(WebFeature.class);
        });
```

This is an excerpt; `WebFeatureAutoConfiguration` needs the matching Servlet condition. Do not add a web starter merely to force a regular test into a web context when unnecessary.

### 7.3. Enabling Report Logging in the Runner

You can have Spring Boot log the report during test execution:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(
                AutoConfigurations.of(FeatureAutoConfiguration.class)
        )
        .run(context -> {
            // Bean and condition assertions here.
        });
```

Import `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` and `org.springframework.boot.logging.LogLevel`. This is an optional snippet for tests; it is not the only way to view the report. For automated tests, reading `ConditionEvaluationReport` directly is usually more convenient than matching log strings.

## 8. When Source and Experiment Disagree, Check in Order

If predictions diverge from results, do not jump to blaming a framework bug. Check these points in order:

1. **Version:** do the sources JAR and runtime dependency share the exact same version?
2. **Discovery:** is the class in `AutoConfiguration.imports` of the actually resolved JAR?
3. **Exclusions/filters:** was the class removed by `exclude`, `spring.autoconfigure.exclude`, or an import filter?
4. **Classloader:** is the optional class actually visible to the classloader the context uses? Are there multiple versions of the dependency?
5. **Environment:** was the property overridden by a profile, environment variable, command line, or test property? Also check `matchIfMissing` and `havingValue`.
6. **User beans:** was the bean registered before the condition? Does the declared return type provide enough information? Is the condition matching by type, name, or annotation?
7. **Order:** did another auto-configuration register a bean earlier, or declare `before/after`?
8. **Context:** is the test using the right Servlet/Reactive/non-web context type and parent/child hierarchy?
9. **Method-level condition:** the class may match while a method still backs off; look up the `ClassName#methodName` key as well.
10. **Instance creation:** the condition matched and the definition was registered, yet instantiation may fail due to constructors, dependencies, post-processors, or external connections. Inspect startup exceptions and the dependency graph.

To include the report in a real application's logs, launch with `--debug`. If Actuator is configured, `/actuator/conditions` can provide a JSON condition report. Check the right context and protect operational endpoints; do not expose internal reports publicly just for temporary debugging.

## 9. What a Minimal Experiment Proves — and What It Does Not

| What the Experiment Can Prove | What It Does Not Automatically Prove |
| --- | --- |
| Given the test's exact classpath, properties, and user config, beans exist/do not exist as asserted. | Production has the exact same classpath, profiles, and property sources. |
| A specific condition source is full match or not full match in the test context. | Every context in the JVM has the same report or same outcome. |
| A user bean causes a method-level `@ConditionalOnMissingBean` to back off in test. | No other auto-configuration in the application also creates a similar bean. |
| An optional class hidden by FilteredClassLoader causes its branch not to match. | The dependency is completely absent across all real-world classloaders. |
| A Servlet/Reactive runner simulates the corresponding context type. | Embedded server, security, networking, or production lifecycle fully works. |

A minimal context experiment is valuable because it **isolates variables**. Once a test confirms one hypothesis, add real dependencies, real properties, or real integrations step by step. Running only one large `@SpringBootTest` and seeing a bean appear reveals the overall outcome, yet makes it hard to tell which exact condition decided it.

## 10. Practical Checklist When Reading an Auto-Configuration

- [ ] Verify the running Spring Boot version and artifacts.
- [ ] Locate the class in `AutoConfiguration.imports` of the right JAR.
- [ ] Check exclusions, import filters, and related metadata.
- [ ] Read class-level conditions before nested configurations.
- [ ] Trace `@Import`, nested configs, and `before/after/order`.
- [ ] Read each bean method, return type, bean name, and method-level conditions.
- [ ] Check property sources, defaults, and optional dependencies.
- [ ] Write a hypothesis with explicit inputs and expected beans/report.
- [ ] Create a small `ApplicationContextRunner`, one test case per variable.
- [ ] Assert beans by **name and type**, not only context startup.
- [ ] Read `ConditionEvaluationReport` to cross-check source classes/methods.
- [ ] When needed, expand with `FilteredClassLoader` or web-specific runners.
- [ ] If results diverge, check version, discovery, exclusions, classpath, properties, user beans, ordering, and context first.

**Conclusion:** reading source code gives us a hypothesis about the auto-configuration path; a small context test turns that hypothesis into repeatable evidence. Verify the exact version, the imports resource, every condition on the class and methods, and then build an `ApplicationContextRunner` controlling properties and user beans. Cross-checking both actual beans and `ConditionEvaluationReport` distinguishes **class not loaded**, **condition not matched**, **bean method backed off**, and **bean instance failed to create**.

### Official References

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReport.ConditionAndOutcomes`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html