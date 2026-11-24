# Registering Library Properties and Providing Intentional Defaults

## 1. Two Things a Spring Boot Library Must Do

A Spring Boot integration library typically needs to expose options so consuming applications can configure it without modifying library code. For instance, a reporting library might allow toggling the feature, choosing a batch size, and setting a timeout:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 25
    timeout: 3s
~~~

For these keys to take effect, the library must handle **two independent tasks**:

1. **Register properties:** bring the `@ConfigurationProperties` class into the `ApplicationContext` so Spring Boot binds values from the `Environment`.
2. **Provide intentional defaults:** define the values used when the application omits a property, while keeping the condition that creates default beans aligned with those same semantics.

Merely placing `@ConfigurationProperties` on a class does not guarantee that class becomes a bean. Likewise, a field initializer such as `private int batchSize = 25` does not automatically enable or disable an auto-configuration method guarded by `@ConditionalOnProperty`; the condition reads properties from the `Environment`, not Java field values.

This lesson uses the illustrative namespace **`acme.reports`**, Java 17, and Spring Boot 3.3.13. The examples can live inside a starter library or a project simulating a library and consuming application.

## 2. Designing Properties as a Public API

Property names, data types, defaults, and semantics form a contract between the library and the application. Users may store keys in YAML, environment variables, ConfigMaps, Helm charts, pipelines, or command-line arguments. Once released, renaming keys can impact many deployment environments.

A good namespace follows this form:

~~~text
<vendor>.<library-or-feature>.<property>
~~~

Example:

~~~properties
acme.reports.enabled=true
acme.reports.batch-size=25
acme.reports.timeout=3s
acme.reports.retry.max-attempts=3
~~~

Conventions to follow:

- Use a dedicated prefix with clear ownership; avoid global keys like `enabled`, `timeout`, or `url`.
- Use canonical lowercase kebab-case names in documentation and configuration.
- Group properties with the same purpose under sub-prefixes such as `http`, `retry`, or `export`.
- Document the type, unit, default, valid range, and impact of every key.
- Never place secrets/tokens in defaults; never supply dummy endpoints or credentials that could cause applications to connect to the wrong target.
- Keep names and semantics stable across releases; migrating legacy keys requires an explicit plan.

A good default must be safe, predictable, free of unexpected side effects, and fit for the library's purpose. For example, a 3-second timeout or batch-size of 25 may be reasonable defaults for the sample reporting library; a real library must choose based on load, resources, and API semantics.

## 3. Registering `@ConfigurationProperties` in a Library

Spring Boot offers several ways to register properties beans. For an auto-configuration library, the clearest approach is usually `@EnableConfigurationProperties` directly on the library's auto-configuration.

### 3.1. `@EnableConfigurationProperties`

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.config.ReportsProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {
}
~~~

`@EnableConfigurationProperties(ReportsProperties.class)` registers the properties bean and enables binding for that class. When the auto-configuration is loaded, applications can inject `ReportsProperties` into other beans.

Advantages for a library:

- Does not require users to add `@ConfigurationPropertiesScan` in their application.
- Does not depend on whether the application's component scan covers the library package.
- Centralizes property registration at the auto-configuration entry point.
- Explicitly lists the properties classes owned by the module.

One auto-configuration can register multiple classes:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
        ReportsProperties.class,
        ReportsRetryProperties.class
})
public class ReportsAutoConfiguration {
}
~~~

Register only the classes the module actually owns; avoid registering the same type redundantly through multiple uncoordinated mechanisms.

### 3.2. `@ConfigurationPropertiesScan`

An application can use:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

This annotation scans the application's package and subpackages for `@ConfigurationProperties` classes. This fits when **the application** owns its own properties classes.

For reusable libraries, do not force every application to scan the library's packages. If the library package lies outside the scan scope, properties may fail to register. Library auto-configuration should register its own types via `@EnableConfigurationProperties`.

### 3.3. `@Bean` + `@ConfigurationProperties` for Third-Party Types

If you need to bind properties onto a class not owned by the library or on which annotations cannot be placed, you can declare:

~~~java
@Bean
@ConfigurationProperties(prefix = "acme.reports.client")
ThirdPartyClientSettings clientSettings() {
    return new ThirdPartyClientSettings();
}
~~~

This is an illustrative method inside a configuration class. Spring Boot binds keys under the prefix onto the object returned by the method. This is helpful for third-party types with suitable setters.

Do not use multiple registration mechanisms for the same properties type without a clear reason. Registering a type twice can create unwanted bean instances or make it hard for readers to trace the configuration source.

## 4. Providing Defaults with JavaBean Field Initializers

The simplest and clearest approach is initializing fields with default values directly inside the properties class. Spring Boot binds user-supplied values onto the object; any omitted property retains its initialized value.

**ReportsProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.reports")
public class ReportsProperties {

    private boolean enabled = true;

    @Min(1)
    private int batchSize = 25;

    @NotNull
    private Duration timeout = Duration.ofSeconds(3);

    @Valid
    private Retry retry = new Retry();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        @Min(0)
        private int maxAttempts = 3;

        @NotNull
        private Duration backoff = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getBackoff() {
            return backoff;
        }

        public void setBackoff(Duration backoff) {
            this.backoff = backoff;
        }
    }
}
~~~

Explanation:

- `enabled = true`: the feature is enabled by default per the example's contract.
- `batchSize = 25`: small, predictable batch size; minimum allowed value is 1.
- `timeout = Duration.ofSeconds(3)`: timeout with an explicit unit.
- `retry = new Retry()`: the retry group object exists even when the application declares no sub-keys.
- `@Valid` on the nested object activates validation for fields inside `Retry`.
- `@Validated`, `@Min`, and `@NotNull` validate bound values when the application has a Bean Validation provider.

With JavaBean binding, getters/setters let the binder assign values from the `Environment`. If a property is absent, the initializer is kept. Java primitives have built-in defaults such as `0` or `false`; **do not rely on language defaults** when the contract requires another value. Write initializers explicitly.

### 4.1. Defaults for Nested Properties

YAML example:

~~~yaml
acme:
  reports:
    retry:
      max-attempts: 5
~~~

If only `max-attempts` is declared, the `backoff` field still retains `250ms`. If the entire `retry` group is omitted, the `new Retry()` initializer keeps both `3` and `250ms`.

If a nested object is nullable and uninitialized, do not assume the binder will always instantiate it just because sub-properties might exist. Design the object graph clearly: initialize nested beans, use constructor binding with appropriate defaults, or test the case where sub-properties are absent.

## 5. Defaults for Immutable Properties and Records

If you want immutable properties, use constructor binding. With Java records on Spring Boot 3.x, the canonical constructor is used for binding. The `@DefaultValue` annotation lets you declare defaults right on record components.

**ReportsRecordProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.reports")
public record ReportsRecordProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("25") @Min(1) int batchSize,
        @DefaultValue("3s") @NotNull Duration timeout) {
}
~~~

This is **an alternative** to the JavaBean class in Section 4; do not register both classes with the same prefix in a single demo application if they represent the same contract.

Points to remember:

- `@DefaultValue("25")` supplies the default when the property has no bound value.
- `Duration` accepts strings with units such as `3s`, `500ms`, `1m`.
- No setters are needed because records are immutable.
- For regular constructor-bound classes, ensure proper constructor binding; avoid annotating constructors meant for constructor binding with `@Autowired`.
- `@EnableConfigurationProperties` remains the clearest way to register record properties in auto-configuration.

For nested records, you can place `@DefaultValue` on the corresponding parameter to instantiate the nested object when sub-properties are omitted, and put defaults on the inner components. Verify with tests because null, empty, and an object containing defaults are distinct states.

## 6. Distinguishing Property Defaults from Bean Defaults

This is a common source of bugs in auto-configuration libraries.

A **property default** is the value of a property, such as `acme.reports.batch-size=25` when unconfigured by the user.

A **default bean** is a Spring object created out of the box by the library, such as `ReportClient`, when the application has not supplied a replacement bean.

These two are related but not identical. Example:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

Here:

- `@EnableConfigurationProperties` registers the properties bean.
- `@ConditionalOnProperty` controls the default client via the `enabled` flag.
- `@ConditionalOnMissingBean` allows the application to supply its own client.
- Field defaults in `ReportsProperties` determine `batch-size` and `timeout` when the user does not override them.

### 6.1. `matchIfMissing` Must Match the `enabled` Default

Suppose the properties class has:

~~~java
private boolean enabled = true;
~~~

But the bean method declares:

~~~java
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
~~~

When the user does not declare the property, the properties object will have `enabled=true`, yet the condition **will not match** because the property is missing from the `Environment` and `matchIfMissing=false`.

These are two different data-reading mechanisms:

- The binder creates the object and preserves the field initializer.
- `@ConditionalOnProperty` inspects properties in the `Environment`, not field initializers on the properties bean.

If the contract intends the feature to be enabled by default, align:

~~~java
private boolean enabled = true;
~~~

with:

~~~java
matchIfMissing = true
~~~

If the contract intends it to be disabled by default:

~~~java
private boolean enabled = false;
~~~

and:

~~~java
matchIfMissing = false
~~~

This is an essential rule to avoid situations where logs report `enabled=true` while the default bean is never registered.

### 6.2. `@ConditionalOnMissingBean` Is Not a Default Value

`@ConditionalOnMissingBean(ReportClient.class)` does not assign a default value to a property. It only decides whether the bean factory method applies when no matching bean exists yet.

Similarly, `@Primary` only prioritizes a bean when injecting a single-valued dependency. If the goal is to avoid creating a default client when the application already has its own client, use the appropriate condition; do not use `@Primary` as a substitute.

## 7. Complete Maven Project Example

The example uses **Java 17+ and Spring Boot 3.3.13**. We place the application class and the simulated library package in separate packages so Spring Boot discovers the auto-configuration via the official resource.

### 7.1. Directory Tree

~~~text
reports-defaults-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/ReportsDemoApplication.java
    │   │   └── lib/
    │   │       ├── ReportClient.java
    │   │       ├── config/ReportsProperties.java
    │   │       └── autoconfigure/ReportsAutoConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── ReportsAutoConfigurationTest.java
~~~

### 7.2. `pom.xml`

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
    <artifactId>reports-defaults-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-configuration-processor` generates metadata for IDE configuration hints; it is not a runtime component performing binding. `spring-boot-starter-validation` provides the Bean Validation implementation so constraints like `@Min` work.

### 7.3. `ReportsProperties.java`

Create **src/main/java/com/example/lib/config/ReportsProperties.java** with the complete JavaBean class from Section 4. Keep the exact package `com.example.lib.config`.

### 7.4. `ReportClient.java`

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

import java.time.Duration;

public record ReportClient(int batchSize, Duration timeout) {
    public String describe() {
        return "batchSize=" + batchSize + ", timeout=" + timeout;
    }
}
~~~

This record models a client bean using bound configuration; it does not connect to external services.

### 7.5. `ReportsAutoConfiguration.java`

**src/main/java/com/example/lib/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;
import com.example.lib.config.ReportsProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

The auto-configuration registers properties even when the feature is disabled. The `enabled` condition sits only on the `ReportClient` bean method, so users can still inject and inspect `ReportsProperties` when `enabled=false`.

### 7.6. `AutoConfiguration.imports`

Create the resource:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

Spring Boot 3.x uses this resource to discover the library's auto-configuration. In a real project, the resource is packaged inside the auto-configuration module's JAR.

### 7.7. `application.yml`

**src/main/resources/application.yml**

~~~yaml
# Intentionally omit acme.reports:
# the application will use defaults from ReportsProperties.
spring:
  application:
    name: reports-defaults-demo
~~~

Do not package a generic `application.yml` inside a library JAR just to provide user defaults. Application configuration files belong to the application and can collide when multiple libraries ship resources with the same name. Library defaults belong in typed properties or a clearly documented configuration mechanism.

### 7.8. `ReportsDemoApplication.java`

**src/main/java/com/example/app/ReportsDemoApplication.java**

~~~java
package com.example.app;

import com.example.lib.ReportClient;
import com.example.lib.config.ReportsProperties;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReportsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner inspect(
            ReportsProperties properties,
            ObjectProvider<ReportClient> clientProvider) {
        return args -> {
            ReportClient client = clientProvider.getIfAvailable();

            System.out.println("enabled=" + properties.isEnabled());
            System.out.println("batchSize=" + properties.getBatchSize());
            System.out.println("timeout=" + properties.getTimeout());
            System.out.println("retry.maxAttempts="
                    + properties.getRetry().getMaxAttempts());
            System.out.println("retry.backoff="
                    + properties.getRetry().getBackoff());
            System.out.println("client="
                    + (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

`ObjectProvider` is used so the runner works whether the client is present or absent. Injecting `ReportClient` directly as a required dependency would cause the context to fail when `enabled=false` because no matching bean exists.

Run:

~~~bash
mvn spring-boot:run
~~~

Besides startup logs, the runner prints:

~~~text
enabled=true
batchSize=25
timeout=PT3S
retry.maxAttempts=3
retry.backoff=PT0.25S
client=batchSize=25, timeout=PT3S
~~~

This is the output when no `acme.reports.*` properties are declared: the binder preserves field initializers and auto-configuration creates the default client because `matchIfMissing=true`.

### 7.9. Overriding Defaults with `application.yml`

Replace the file contents with:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 80
    timeout: 5s
    retry:
      max-attempts: 4
      backoff: 500ms
~~~

Run again:

~~~bash
mvn spring-boot:run
~~~

The runner lines become:

~~~text
enabled=true
batchSize=80
timeout=PT5S
retry.maxAttempts=4
retry.backoff=PT0.5S
client=batchSize=80, timeout=PT5S
~~~

Fields that are not overridden retain the class's defaults. For example, if only `batch-size: 80` is set, timeout and retry backoff keep their initial values.

### 7.10. Overriding with Command-Line Arguments

Without editing YAML, you can run:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--acme.reports.batch-size=90 --acme.reports.timeout=7s"
~~~

Here `batch-size` is 90 and `timeout` is 7 seconds. Command-line property sources have higher precedence than standard application configuration files, so they override YAML values.

To disable the feature:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.enabled=false
~~~

Key lines:

~~~text
enabled=false
batchSize=25
timeout=PT3S
client=absent
~~~

`ReportsProperties` still exists and keeps its defaults/bound values. The default `ReportClient` is not registered because the property condition does not match. If the application declares its own `ReportClient`, the missing-bean condition still allows the custom bean to exist.

## 8. Testing Defaults, Overrides, Validation, and Back-Off

Do not verify only through logs. A library should test its configuration contract using `ApplicationContextRunner`, which builds small contexts, accepts property overrides, and asserts beans without booting an entire application.

**src/test/java/com/example/app/ReportsAutoConfigurationTest.java**

~~~java
package com.example.app;

import java.time.Duration;
import com.example.lib.ReportClient;
import com.example.lib.autoconfigure.ReportsAutoConfiguration;
import com.example.lib.config.ReportsProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void bindsIntentionalDefaultsAndCreatesDefaultClient() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ReportsProperties.class);
            assertThat(context).hasSingleBean(ReportClient.class);

            ReportsProperties properties =
                    context.getBean(ReportsProperties.class);

            assertThat(properties.isEnabled()).isTrue();
            assertThat(properties.getBatchSize()).isEqualTo(25);
            assertThat(properties.getTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(properties.getRetry().getMaxAttempts()).isEqualTo(3);
            assertThat(properties.getRetry().getBackoff())
                    .isEqualTo(Duration.ofMillis(250));

            assertThat(context.getBean(ReportClient.class).describe())
                    .isEqualTo("batchSize=25, timeout=PT3S");
        });
    }

    @Test
    void bindsValuesThatOverrideDefaults() {
        runner.withPropertyValues(
                "acme.reports.batch-size=80",
                "acme.reports.timeout=5s",
                "acme.reports.retry.max-attempts=4",
                "acme.reports.retry.backoff=500ms")
                .run(context -> {
                    ReportsProperties properties =
                            context.getBean(ReportsProperties.class);

                    assertThat(properties.getBatchSize()).isEqualTo(80);
                    assertThat(properties.getTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.getRetry().getMaxAttempts())
                            .isEqualTo(4);
                    assertThat(properties.getRetry().getBackoff())
                            .isEqualTo(Duration.ofMillis(500));
                    assertThat(context.getBean(ReportClient.class).describe())
                            .isEqualTo("batchSize=80, timeout=PT5S");
                });
    }

    @Test
    void disabledFeatureKeepsPropertiesButDoesNotCreateDefaultClient() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .isEnabled()).isFalse();
                });
    }

    @Test
    void invalidBatchSizeFailsValidation() {
        runner.withPropertyValues("acme.reports.batch-size=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void applicationClientReplacesDefaultClient() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).describe())
                            .isEqualTo("batchSize=99, timeout=PT1S");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient(99, Duration.ofSeconds(1));
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Expected: **five tests pass**:

1. When properties are absent, defaults are bound and the default client is created.
2. User-provided properties override defaults.
3. When `enabled=false`, properties remain present but the default client is not created.
4. Invalid `batch-size` is rejected by validation.
5. An application-supplied bean causes auto-configuration to back off.

If the validation test does not fail as expected, check that `spring-boot-starter-validation` is added, the class has `@Validated`, the field has constraints, and the properties class is properly registered.

## 9. Precedence Order: Class Defaults vs. Property Sources

A field initializer is only a **fallback value when the binder receives no other value**. If a property is present from a configuration source, that source's value is bound according to Spring Environment precedence rules.

For example, the class has:

~~~java
private int batchSize = 25;
~~~

`application.yml` file:

~~~yaml
acme:
  reports:
    batch-size: 50
~~~

Environment variable:

~~~text
ACME_REPORTS_BATCHSIZE=80
~~~

Command-line argument:

~~~bash
--acme.reports.batch-size=100
~~~

When multiple sources supply the same key, the higher-precedence source determines the bound value. In standard Spring Boot, command-line arguments take precedence over environment variables and application config; environment variables take precedence over application configuration files. Exact details may depend on property source types and how the application is launched.

**Class defaults do not participate in this precedence race as a separate property source.** They simply remain intact when no value is bound to that field.

Do not put one default in Java and a different default in a demo application's YAML expecting users to guess which value is canonical. Keep one clear source of truth for the contract and test necessary overrides.

## 10. Data Types, Collections, and Nested Defaults

### 10.1. `Duration` and `DataSize`

For timeouts, use `Duration`:

~~~java
private Duration connectTimeout = Duration.ofSeconds(2);
~~~

Users can configure:

~~~yaml
acme:
  reports:
    connect-timeout: 500ms
~~~

For memory/data sizes, use `DataSize` instead of unitless integers:

~~~java
private DataSize maxPayload = DataSize.ofMegabytes(10);
~~~

Configuration:

~~~yaml
acme:
  reports:
    max-payload: 20MB
~~~

Choosing types that express units avoids confusing milliseconds with seconds or bytes with kilobytes. Document units and valid bounds clearly.

### 10.2. `List` and `Map`

You can declare:

~~~java
private List<String> supportedFormats =
        new ArrayList<>(List.of("csv", "json"));

private Map<String, String> headers = new LinkedHashMap<>();
~~~

The binder has specific rules when multiple property sources provide collections. In particular, **a list in a higher-precedence source generally replaces the previous list**; do not assume elements are automatically appended. Maps are bound by key and can combine entries from multiple sources. If the contract depends on merging vs. replacing, write tests covering multiple configuration sources.

Do not use mutable collections shared statically across application contexts. Each properties bean should own its own instance to prevent state leaks across tests or applications.

### 10.3. Null, Empty, and Default

These three states can differ:

- **Property omitted:** class/constructor defaults can be preserved.
- **Empty value declared:** the binder may handle it depending on converters and data types; it is not always equivalent to omitting the property.
- **Null declared in YAML:** depending on the type and binder, it may become `null` or another value; test rather than guessing.

If a property must always have a value, use validation like `@NotNull` and document how to configure it. If a default is valid, initialize it explicitly to avoid unexpected nulls.

## 11. Configuration Metadata and Documentation

Libraries should support IDE property autocomplete. Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

The processor generates metadata in:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata can describe property names, types, descriptions, default values, deprecations, and property groups. Inspect the generated metadata file packaged inside the actual artifact. Do not assume every complex field initializer is inferred perfectly by the processor. When needed, supplement with:

~~~text
META-INF/additional-spring-configuration-metadata.json
~~~

Metadata helps IDEs and documentation, but **does not perform binding, validate values, or create beans**. Defaults in metadata must match actual defaults in code.

When renaming keys, `@DeprecatedConfigurationProperty` helps tools identify the old property as deprecated. This annotation **does not create a runtime alias** for the new name. If legacy keys still need support, implement migration/aliasing with clear precedence rules and test both cases.

## 12. Choosing Safe and Intentional Defaults

Not every property should have a default. Decide based on impact:

| Property category | Default considerations |
| --- | --- |
| Feature flag | Decide explicitly between default-on and default-off; conditions must match that decision |
| Timeout | Use `Duration` with units; avoid infinite timeouts that can hang resources |
| Batch size | Choose a finite value controlling memory and throughput |
| Retry attempts | Moderate default; avoid infinite retries or load amplification |
| Endpoint | Set a default only if it is a stable public service; never point to the wrong environment |
| Username/password/token | Never provide dummy secrets or default credentials |
| TLS/SSL | Prefer secure defaults; never disable certificate verification just for convenience |
| Collection | Define clearly whether an empty list means unsupported, use default, or disable behavior |

Defaults must be documented. If a default affects cost, load, networking, or security, explain the rationale and how to override it.

Avoid defaults that trigger external actions immediately upon context startup. For instance, having a default endpoint does not mean the properties bean constructor should immediately open network connections or spawn background threads.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Injecting properties fails with bean not found | Only `@ConfigurationProperties` was added without registering the type | Use `@EnableConfigurationProperties` in auto-configuration |
| Application has to scan library packages itself | Library relied on consumer component scan | Register properties from auto-configuration |
| Properties say `enabled=true`, but default client is missing | Field initializer is not read by `@ConditionalOnProperty` | Align field default with `matchIfMissing` |
| Default bean is always created despite user's custom bean | Missing `@ConditionalOnMissingBean` or wrong type checked | Add condition matching the bean contract |
| Unexpected `0`/`false` primitive default | Relied on Java defaults instead of contract | Initialize fields explicitly or use `@DefaultValue` |
| Nested properties are null | Nested object not initialized or constructor designed poorly | Initialize nested bean/record and test when sub-keys are absent |
| Timeout value has unclear units | Used unitless `long` or `int` | Use `Duration` |
| Validation does not run | Missing validation provider or missing `@Validated`/constraints | Add starter validation and test startup failure |
| `enabled=false` yet properties bean still exists | Condition placed only on default service bean | This is normal behavior; move condition to properties registration only if omitting properties is truly desired |
| Renamed old key and users lost configuration | Assumed deprecated metadata creates a runtime alias | Implement migration/alias and test it |
| Multiple libraries have colliding property names | Prefix too generic | Design a dedicated namespace with clear ownership |
| Library JAR contains `application.yml` causing conflicts | Used application config file for library defaults | Put defaults in typed properties |

## 14. Library Release Checklist

Before releasing a starter/autoconfigure library, verify:

1. Prefix is owned by the library and uses canonical lowercase kebab-case.
2. Every properties class is registered via `@EnableConfigurationProperties` or an explicitly chosen mechanism.
3. Defaults in Java/records match the documented contract.
4. `@ConditionalOnProperty.matchIfMissing` aligns with the feature flag's default.
5. Default beans have `@ConditionalOnMissingBean` when applications are allowed to replace them.
6. Data types carry appropriate units: `Duration`, `DataSize`, `enum`, `List`/`Map`.
7. Validation has a provider, constraints, and tests.
8. Configuration metadata is generated and packaged.
9. No secrets or dangerous endpoints are used as defaults.
10. Tests cover defaults, overrides, disabled state, invalid values, and custom beans.
11. Migration guidance exists if public properties change.
12. Auto-configurations are published via `AutoConfiguration.imports` in Boot 3.x.

## 15. Self-Check Questions

**Question 1.** Why might merely annotating a class with `@ConfigurationProperties` not allow injecting the properties bean?  
**Answer:** The annotation describes how to bind, while the class still must be registered. Libraries typically use `@EnableConfigurationProperties(ReportsProperties.class)` in auto-configuration.

**Question 2.** If field `enabled=true` yet `@ConditionalOnProperty(matchIfMissing=false)`, what happens when the property is absent?  
**Answer:** The properties object has `enabled=true`, but the condition does not match because the property is absent from the `Environment`. The two mechanisms do not read from the same source.

**Question 3.** When you want a feature enabled by default, which configurations must stay aligned?  
**Answer:** The default in properties must be `true`, and `matchIfMissing=true` on the condition registering the bean.

**Question 4.** Does `@ConditionalOnMissingBean` provide a default value for `batch-size`?  
**Answer:** No. It decides whether the default bean is registered; `batch-size` values belong to `@ConfigurationProperties`.

**Question 5.** Why is using `Duration` better than an integer `timeout=3000`?  
**Answer:** `Duration` expresses time units explicitly and supports formats such as `500ms` or `3s`.

**Question 6.** When a feature is disabled, must the properties bean disappear?  
**Answer:** No. If `@EnableConfigurationProperties` is at the auto-configuration level and the condition sits only on the `ReportClient` method, properties remain available; only the default client is skipped.

**Question 7.** Does `@DeprecatedConfigurationProperty` automatically bind the old property name to the new field?  
**Answer:** No. It supports metadata/deprecation; runtime aliases must be implemented and tested separately.

**Key takeaway:** A well-designed Spring Boot library **registers its own properties**, **declares intentional defaults**, and **aligns bean creation conditions with those defaults**. Use `@EnableConfigurationProperties` in auto-configuration, field initializers or `@DefaultValue` for fallback values, `@Validated` for valid data, `@ConditionalOnProperty` for feature flags, and `@ConditionalOnMissingBean` for replaceable beans. Test defaults, overrides, and conditional branches before release.
