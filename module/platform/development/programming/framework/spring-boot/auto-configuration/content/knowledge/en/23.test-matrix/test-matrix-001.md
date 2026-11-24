# Combinations of Present or Absent Dependency with Feature Enabled or Disabled

## 1. Two independent conditions decide whether an integration is active

A Spring Boot starter may integrate with an external library such as a payment SDK, notification client, codec, driver, or adapter. The underlying library may be an optional dependency, while the starter's auto-configuration remains on the application classpath.

When designing and testing, two separate questions need to be answered:

1. **Is the dependency present on the runtime classpath?** This is a technical condition: whether the JVM can load and use the classes that the integration needs.
2. **Has the operator enabled the feature?** This is a configuration condition: whether the application intentionally uses the integration in the current environment.

Having the library on the classpath does not mean the application wants to enable the feature. Conversely, a property enabling the feature cannot make a missing class appear on the classpath.

Spring Boot provides two commonly used conditions:

- `@ConditionalOnClass`: applies configuration only when the required class is present.
- `@ConditionalOnProperty`: applies configuration only when the property reaches the required value.

When both are placed on the same auto-configuration or nested configuration, they combine with an **AND** operation: both must match for that configuration to be applied.

For example, an audit integration requires the library `com.acme.audit.AuditClient` and the property `app.audit.enabled=true`. The default bean is registered only when both the class is present and the feature is enabled.

## 2. The 2 × 2 matrix to test

Suppose the policy of the example is:

- The `AuditClient` dependency is optional.
- The feature is enabled with `app.audit.enabled=true`.
- If the property is not declared, the feature is enabled by default because `matchIfMissing=true`.
- If the dependency is missing, the integration is not created even if the property is enabled.

Main matrix:

| Dependency on classpath | Feature property | Auto-configuration result |
| --- | --- | --- |
| Present | `true` | Matches both conditions; creates the default bean if no user bean exists yet |
| Present | `false` | Property condition does not match; does not create the default bean |
| Absent | `true` | Class condition does not match; does not create the bean |
| Absent | `false` | Neither condition matches; does not create the bean |

The matrix can be read along two axes:

- **Dependency present:** the property decides whether the feature is enabled or disabled.
- **Dependency absent:** the feature cannot operate; enabling the property also cannot create the required dependency.

An additional case that must be tested is an omitted property. With `matchIfMissing=true`, when the class is present and the property is not declared, the bean is still created. If the product policy is disabled by default, set `matchIfMissing=false` and test the opposite expectation.

### 2.1. Four meaningfully distinct states

**Dependency present + feature enabled:** the normal path. Auto-configuration can create the bean and the application can inject it.

**Dependency present + feature disabled:** the library is still on the classpath, but the integration bean is not registered. The application can use that library in another way; the property only controls the auto-configuration under consideration.

**Dependency missing + feature enabled:** the class condition blocks the integration. The example below chooses the policy of skipping the bean and letting the context continue starting up. If the product requires that enabling a feature while the library is missing must be a configuration error, a separate fail-fast check must be designed and startup failure must be tested.

**Dependency missing + feature disabled:** there is no reason to initialize the integration; the bean does not appear.

Do not merge the two "no bean" states into a single conclusion. Tests need to know whether the bean is absent because the property is disabled or because the library is missing. Without distinguishing the cause, a starter can accidentally hide a dependency packaging mistake.

## 3. Safe auto-configuration with an optional dependency

The example uses Spring Boot 3.5.0 and Java 17. Suppose an external library provides the `AuditClient` interface. The starter can create a default implementation when the class is present and the feature is enabled.

### 3.1. Placing the class condition on a nested configuration

```java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.audit.AuditClient")
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class AuditClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AuditClient auditClient() {
            return new DefaultAuditClient();
        }
    }
}
```

This is an architectural snippet. `AuditClient` and `DefaultAuditClient` belong to the example library, not Spring Boot classes.

Nested configuration matters because the outer auto-configuration does not need to directly reference the optional type in a method signature. Spring Boot can read the metadata of the nested configuration and skip it when the class is not on the classpath.

Do not place a method whose return type is an optional class directly on the root configuration and only attach `@ConditionalOnClass` to the `@Bean` method itself. The JVM may have to load/verify the return type and method references before the method condition is applied. When the dependency is actually absent, that can lead to linkage errors. Separating a nested configuration is the way to isolate references to the optional type.

### 3.2. Role of each annotation

| Annotation | Question | Effect when not matched |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the required library on the classpath? | Skips the nested configuration |
| `@ConditionalOnProperty` | Is the feature enabled by the property? | Skips the nested configuration |
| `@ConditionalOnMissingBean` | Has the application already provided a replacement bean? | Does not create the default bean |

`@ConditionalOnMissingBean` is the third condition in the example. It allows the application to provide its own `AuditClient`; in that case, auto-configuration does not create an additional default bean. This condition does not replace the classpath condition or the feature flag.

### 3.3. Understanding havingValue and matchIfMissing accurately

With the declaration:

```java
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

the result is:

| Value of `app.audit.enabled` | Condition |
| --- | --- |
| `true` | Matches |
| `false` | Does not match |
| `yes` | Does not match `havingValue="true"` |
| Not declared | Matches because `matchIfMissing=true` |

If `havingValue` is omitted, a property that is present and different from `false` may be considered a match. For a boolean feature flag, explicitly specify `havingValue="true"` to make the contract easy to read and avoid accepting unintended values.

`matchIfMissing` is a product decision, not a decorative detail:

- `true`: a missing property is interpreted as enabled by default.
- `false`: a missing property is interpreted as not enabled.

Choose one policy and write a test for the missing property case. Do not infer the default from the initial value of a `@ConfigurationProperties` object; the condition reads `Environment`, whereas the binder initializing an object is a separate mechanism.

## 4. Writing matrix tests with ApplicationContextRunner

`ApplicationContextRunner` helps create a small context for each combination. We load the exact auto-configuration under test, vary the properties and classloader per test, and then verify whether the bean is present or absent.

Key benefits:

- Each `run(...)` call creates an isolated context and closes the context after the callback.
- No need to start the entire application or a web server.
- Properties can be changed per test.
- A missing dependency can be simulated using `FilteredClassLoader`.
- Assertions focus on bean registration and condition outcomes.

### 4.1. Project structure

```text
audit-feature-matrix/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           ├── AuditClient.java
    │           └── AuditAutoConfiguration.java
    └── test/
        └── java/
            └── example/
                └── AuditAutoConfigurationTests.java
```

In a real starter, the auto-configuration class is also registered in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. The test below passes the class directly into `AutoConfigurations.of(...)`, because the goal is to test that class's conditions.

### 4.2. The pom.xml file

```xml
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
    <artifactId>audit-feature-matrix</artifactId>
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
</project>
```

`spring-boot-autoconfigure` provides the annotations and conditions for configuration code. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, `ApplicationContextRunner`, and `FilteredClassLoader`.

### 4.3. The src/main/java/example/AuditClient.java file

```java
package example;

public interface AuditClient {
    String serviceName();
}
```

### 4.4. The src/main/java/example/AuditAutoConfiguration.java file

```java
package example;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "example.AuditClient")
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class AuditClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        AuditClient auditClient() {
            return new DefaultAuditClient("catalog-service");
        }
    }

    private record DefaultAuditClient(String serviceName)
            implements AuditClient {
    }
}
```

In a real application, `AuditClient` usually comes from an optional dependency. In this demo project, the interface is placed in `src/main/java` so the project compiles; `FilteredClassLoader` hides the class from the test context to simulate an application without the library.

### 4.5. The src/test/java/example/AuditAutoConfigurationTests.java file

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void dependencyPresentAndFeatureEnabledCreatesBean() {
        runner.withPropertyValues("app.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.serviceName())
                            .isEqualTo("catalog-service");
                });
    }

    @Test
    void dependencyPresentAndFeatureDisabledSkipsBean() {
        runner.withPropertyValues("app.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void dependencyMissingAndFeatureEnabledSkipsBean() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .withPropertyValues("app.audit.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void dependencyMissingAndFeatureDisabledSkipsBean() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .withPropertyValues("app.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void missingPropertyUsesTheDocumentedDefault() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditClient.class);
        });
    }
}
```

### 4.6. Running the tests

In the directory containing `pom.xml`, use JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** five JUnit tests pass and Maven finishes with `BUILD SUCCESS` if dependencies download successfully. The code does not call `System.out.println`, so there is no fixed business stdout. Detailed reports are written in `target/surefire-reports`.

This is the expected result from the sample code, not an actual run result. When applying it to a project, run the tests with the starter's actual dependencies and version.

## 5. Reading test results and ConditionEvaluationReport

The first four tests correspond directly to the 2 × 2 matrix:

| Test | Class hidden? | Property | Result |
| --- | --- | --- | --- |
| `dependencyPresentAndFeatureEnabledCreatesBean` | No | `true` | Bean present |
| `dependencyPresentAndFeatureDisabledSkipsBean` | No | `false` | No bean |
| `dependencyMissingAndFeatureEnabledSkipsBean` | Yes | `true` | No bean |
| `dependencyMissingAndFeatureDisabledSkipsBean` | Yes | `false` | No bean |

The fifth test checks the default property. Because `matchIfMissing=true`, when the dependency is present and the key is not declared, the default bean is still created.

Do not only assert that the context starts successfully. Assert the bean by name or type and check important values. A context can start normally even if the auto-configuration was skipped completely.

### 5.1. Why use the bean name in missing-class tests?

In missing-dependency tests, `AuditClient` is not available to the context's classloader. Therefore, the assertion `doesNotHaveBean("auditClient")` avoids requiring the context to resolve that optional type. In tests where the dependency is present, you can assert by type and check bean behavior.

### 5.2. Inspecting why conditions matched or did not match

When a test does not produce the expected result, you can add a listener to print `ConditionEvaluationReport`:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(AuditAutoConfiguration.class)
                );
```

The report helps identify which condition matched, which condition did not match, and why. It is useful when multiple class conditions or property conditions are combined. In everyday tests, only enable the listener when diagnosing so logs do not become overly verbose.

## 6. Policy when the feature is enabled but the dependency is missing

The matrix above chooses the **graceful skip** policy: if the dependency is absent, the integration is not registered, even when the property is `true`. This is appropriate behavior when the integration is truly optional and the application can run without it.

Another product may require **fail fast**: if the user explicitly enabled the feature while the library is missing, startup must fail with a clear message. The two policies have different operational meanings:

| Policy | Dependency missing + property `true` | Suitable when |
| --- | --- | --- |
| Graceful skip | Does not create bean; context can still run | Feature is optional; application has a fallback or does not use the integration |
| Fail fast | Context fails with a clear configuration error | The enabled feature is a mandatory requirement for the application to work properly |

If choosing fail fast, do not let the error surface randomly as a `NoClassDefFoundError` when another bean is initialized. Design an intentional configuration check, avoid referencing the optional type in a class that needs to be loaded early, and write a dedicated test confirming startup failure along with a helpful message.

Do not write a test requiring fail-fast when the configuration only has `@ConditionalOnClass`: that annotation is designed to skip the branch when the class is absent. Tests must reflect the chosen policy.

## 7. Combining with a user-provided bean

The classpath and property conditions decide whether the nested configuration is applied. `@ConditionalOnMissingBean` then decides whether to create the default bean inside that configuration.

For example, the application can provide its own `AuditClient`:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean
    AuditClient customAuditClient() {
        return () -> "custom-audit";
    }
}
```

When the dependency is present, the feature is enabled, and the user bean is already registered, auto-configuration does not create the default `auditClient`. The user bean remains in place.

Distinguish clearly:

- The feature property disables the bean created by auto-configuration.
- `@ConditionalOnMissingBean` lets a user bean replace the default bean.
- The classpath condition prevents the integration configuration from being applied when the dependency is missing.

Do not treat a feature flag as a mechanism to remove every bean of the same type from the context. It only controls the configuration/bean to which that condition is attached.

## 8. Common mistakes when testing dependency and feature flag combinations

1. **Testing only dependency present and feature enabled.** The configuration may work on the happy path while failing to prove the disabled branch or absent dependency.
2. **Assuming property true guarantees the feature runs.** A property does not add a library to the classpath; the class condition can still fail to match.
3. **Assuming dependency present automatically enables the feature.** A feature flag may be disabled by default if `matchIfMissing=false`.
4. **Not deciding the default clearly when the property is missing.** Set `matchIfMissing` intentionally and add a test for the missing key.
5. **Putting `@ConditionalOnClass` on a `@Bean` method while the optional type is in the return signature.** Split out a nested configuration to avoid class loading before the method condition is applied.
6. **Checking only bean count.** Assert both bean name/type and key behavior to know the right bean was created.
7. **Reusing the same context for multiple combinations.** Each scenario needs its own context; call `runner.with...().run(...)` separately.
8. **Using a mock instead of classpath filtering.** A mock bean tests dependency injection; it does not simulate a missing library. Use `FilteredClassLoader` for the classpath branch.
9. **Not testing unusual property values.** With `havingValue="true"`, a value like `yes` is not equivalent to `true`; add tests if the configuration may receive non-standard values.
10. **Letting auto-configuration scan too broadly in tests.** Use `AutoConfigurations.of(...)` to load the group under test and avoid unrelated conditions.
11. **Not checking the condition report when tests fail.** `ConditionEvaluationReport` helps find which condition did not match.
12. **Confusing a user bean with the default bean.** When testing back-off, verify that the user bean exists and the default bean is not registered.
13. **Concluding graceful skip is fail-fast.** If startup failure is required when a dependency is missing, a separate policy and test are needed.
14. **Testing only inside the autoconfigure module where test dependencies are always present.** Add classpath tests using `FilteredClassLoader` and, if needed, a real consumer sample that does not declare the optional dependency.

## 9. Checklist before releasing a starter with an optional integration

- [ ] Identify which libraries are required dependencies and which are optional.
- [ ] Choose a clear feature property name and document its default value.
- [ ] Place `@ConditionalOnClass` to guard integrations that need external libraries.
- [ ] Place `@ConditionalOnProperty` to control the feature via configuration.
- [ ] Isolate optional types inside nested configurations when needed.
- [ ] Place `@ConditionalOnMissingBean` if applications are allowed to replace the default bean.
- [ ] Test all four combinations of dependency present/absent and feature enabled/disabled.
- [ ] Test the undeclared property case separately.
- [ ] Test user beans and back-off behavior if the starter supports overrides.
- [ ] Decide whether missing dependency when the feature is enabled should be graceful skip or fail fast.
- [ ] Check the condition report when results do not match expectations.
- [ ] Verify the runtime classpath of a real consumer; classloader tests do not replace checking the published dependency graph.
- [ ] Run tests on the Spring Boot version supported by the starter.

## 10. Self-check questions

**Question 1.** Why must both the classpath and the feature property be tested?  
**Answer:** The classpath indicates whether the integration can be loaded; the property indicates whether the application wants to enable it. These are two independent conditions.

**Question 2.** What happens when the dependency is present and the property is `false`?  
**Answer:** The class condition matches, but the property condition does not match, so the default integration bean is not created.

**Question 3.** If the dependency is missing but the property is `true`, does `@ConditionalOnClass` allow the bean to appear?  
**Answer:** No. The class condition does not match; a property cannot substitute for a missing dependency.

**Question 4.** What does `matchIfMissing=true` mean?  
**Answer:** When the property is absent from Environment, the property condition still matches. This is the enabled-by-default policy in the example.

**Question 5.** Why use a nested configuration for an optional dependency?  
**Answer:** It isolates method signatures and references to the optional type, allowing the class condition to exclude the configuration before the JVM has to load those types.

**Question 6.** What is `FilteredClassLoader` used for?  
**Answer:** To simulate a class or package being absent from the test context's classpath in order to test the `@ConditionalOnClass` branch.

**Question 7.** Is `@ConditionalOnMissingBean` the same as `@ConditionalOnClass`?  
**Answer:** No. One condition checks the classpath; the other checks beans already present in the BeanFactory.

**Question 8.** If the dependency is missing while the feature is enabled and the product requires startup to fail, is using only `@ConditionalOnClass` sufficient?  
**Answer:** No. `@ConditionalOnClass` will skip the configuration. A separate fail-fast design and startup failure test are required.

## Official References

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, class/property/bean conditions and testing: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — `FilteredClassLoader`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Takeaway:** Test the two axes separately: dependency present/absent and feature enabled/disabled. `@ConditionalOnClass` guards the ability to load the integration; `@ConditionalOnProperty` expresses the operational choice. Only when both conditions match does auto-configuration create the default bean; testing the full matrix helps catch classpath and configuration bugs before releasing a starter.
