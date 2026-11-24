# Designing a Dedicated Namespace for Library @ConfigurationProperties

## 1. Why Must a Library Have Its Own Configuration Namespace?

When multiple libraries are used in the same Spring Boot application, all of them read configuration through the **Spring Environment**. If library A and library B both define keys like `timeout`, `client.url`, or `enabled`, it becomes very hard for the application to tell which value belongs to which component. An environment change can unintentionally affect another library.

The solution is to design **a stable prefix owned by the library**, and place the library's options underneath that prefix. For example, for a hypothetical reporting library from the Acme organization:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 50
    timeout: 5s
~~~

The three full keys are `acme.reports.enabled`, `acme.reports.batch-size`, and `acme.reports.timeout`. The annotation in Java code will use that exact root:

~~~java
@ConfigurationProperties(prefix = "acme.reports")
~~~

**The namespace here is a namespace of property keys**, not a Java package, class name, Spring bean name, or Maven artifact name. The package `com.example.lib` can change during refactoring while the public namespace `acme.reports` remains unchanged.

Goals of a dedicated prefix:

- **Avoid collisions** with configuration from Spring Boot, the application, or other libraries.
- **Easy discoverability**: operators know which subsystem a key belongs to.
- **Easy extensibility**: add `acme.reports.retry.*` or `acme.reports.http.*` without cluttering other keys.
- **Easy testing and upgrading**: typed properties, validation, documentation, and metadata all share the same ownership scope.

A prefix does not by itself make data private or secure: values are still resolved from Spring Environment property sources according to configuration precedence.

## 2. Prefix Design Rules

Recommended pattern for a reusable library:

~~~text
<vendor-or-product>.<module-or-feature>[.<subgroup>].<property>
~~~

Examples:

| Key or prefix | Assessment |
| --- | --- |
| `acme.reports` | Appropriately isolated root for the reporting library |
| `acme.reports.http.connect-timeout` | HTTP parameter placed under a specific functional subgroup |
| `acme.reports.retry.max-attempts` | Clearly describes what is being configured |
| `client.timeout` | Prone to collision if there are multiple HTTP clients |
| `app.enabled` | Too generic when the library is embedded in multiple applications |
| `spring.reports`, `management.reports` | Should not arbitrarily claim namespaces belonging to the Spring Boot ecosystem |

`acme` is a fictional name; use a root matching the actual vendor or product of your library. The root should be **specific enough without being overly tied to implementation details**, such as avoiding unnecessary class names, package paths, or version numbers in the prefix.

Naming rules:

1. Use **lowercase** and **kebab-case** for each segment of the property name, with hierarchical segments separated by dots: `acme.reports.batch-size`.
2. Group by function: `acme.reports.http.*`, `acme.reports.retry.*`, `acme.reports.export.*`.
3. Names should express meaning/units: `connect-timeout` is better than `time`; `max-attempts` is better than `count`.
4. Do not use global keys like `enabled`, `url`, or `timeout` for the library's configuration API.
5. Two independent libraries should not share a single root just because their functions are similar. Even if they come from the same provider, each library still needs a distinct subgroup, such as `acme.reports` and `acme.billing`.
6. Choose the defaults and semantics of each key before release. Once users put them into YAML, Helm charts, or environment variables, the key becomes part of the **public configuration contract**.

The namespace does not have to match the Maven/Gradle groupId. You can choose `acme.reports` even if the library's groupId is `com.example.infrastructure`, as long as the public name is published consistently.

## 3. Canonical Keys and Relaxed Binding

In Spring Boot, a `@ConfigurationProperties` class receives values through the binder. The key format recommended in documentation is **lowercase kebab-case**:

~~~properties
acme.reports.enabled=true
acme.reports.batch-size=50
acme.reports.timeout=5s
~~~

Corresponding binding:

| In Java | In YAML/properties | Environment variable per canonical rules |
| --- | --- | --- |
| `boolean enabled` | `acme.reports.enabled` | `ACME_REPORTS_ENABLED` |
| `int batchSize` | `acme.reports.batch-size` | `ACME_REPORTS_BATCHSIZE` |
| `Duration timeout` | `acme.reports.timeout` | `ACME_REPORTS_TIMEOUT` |

Rule for converting a canonical name to an environment variable: **replace dots with underscores, remove dashes, then uppercase**. Therefore, the canonical form of `batch-size` is `ACME_REPORTS_BATCHSIZE`. Spring Boot supports relaxed binding, but do not design your documentation and implementation around a custom, non-standard set of names.

Example CLI override for a property:

~~~bash
java -jar reports-demo.jar --acme.reports.batch-size=80
~~~

`--acme.reports.batch-size` and `ACME_REPORTS_BATCHSIZE` are still representations of **the same logical property**. When two property sources both provide a value, Spring Boot uses its property source precedence mechanism. A dedicated prefix identifies *whose property it is*, not *which source wins*.

Some rules to avoid mistakes:

- The annotation uses `@ConfigurationProperties(prefix = "acme.reports")`; do not use camelCase such as `acmeReports` for the prefix.
- The `batchSize` field binds from `batch-size`; you do not need to name the Java field with a hyphen.
- If YAML configuration is mistyped as `acme.report.batch-size`, the value may fail to bind; `@ConfigurationProperties` **can ignore unknown fields by default**, so public keys need to be tested.
- Properties bind from many sources, not just `application.yml`. When diagnosing issues, also inspect command-line args, environment variables, and other property sources.

## 4. Using Typed @ConfigurationProperties Instead of Scattering @Value

For a library with many parameters, grouping them into a properties class helps control the contract, data types, and validation.

**src/main/java/com/example/lib/config/ReportsProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
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
}
~~~

Explanation:

- `@ConfigurationProperties(prefix = "acme.reports")` determines the single root bound into the class.
- This is JavaBean binding with getters/setters. A library can also use immutable constructor binding/records, as long as it fits the registration mechanism and target Spring Boot version.
- The `batchSize` field is `int`, and the value `acme.reports.batch-size=50` is converted and bound to this field.
- Using `Duration` lets users write `500ms`, `5s`, `1m` instead of an integer with an ambiguous unit.
- Defaults `enabled=true`, `batchSize=25`, and `timeout=3s` apply when the user does not configure the corresponding key. Do not change defaults unexpectedly between releases.
- `@Min(1)` prevents a zero or negative batch-size; `@NotNull` prevents a null timeout. `@Validated` enables Bean Validation for the properties object when the application has a Bean Validation provider on the classpath (for example `spring-boot-starter-validation`).
- Avoid accidentally printing credentials/tokens through the properties' `toString()`. Secrets still require proper provisioning and masking mechanisms.

**Very important point:** Putting `@ConfigurationProperties` on a class **is not enough by itself to automatically produce a Spring properties bean**. The library must register that class through an explicit mechanism.

## 5. Library Self-Registers Properties via Auto-Configuration

With Spring Boot 3.x, a library should proactively register properties in auto-configuration so that consuming applications do not have to add manual annotations.

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
    @ConditionalOnMissingBean(ReportClient.class)
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

There are three separate concepts here:

1. `@EnableConfigurationProperties(ReportsProperties.class)` registers the **properties bean**, and the binder populates data from the `acme.reports` namespace.
2. `@ConditionalOnProperty(prefix = "acme.reports", name = "enabled", havingValue = "true", matchIfMissing = true)` decides **whether to register the default ReportClient**. Reuse the library's own prefix, never a global `enabled` flag.
3. `@ConditionalOnMissingBean(ReportClient.class)` allows the application to provide a custom ReportClient; auto-configuration will back off and not create an extra default of the same type.

`matchIfMissing=true` matches the default `enabled=true` in `ReportsProperties`. If you want the feature disabled by default, you can choose `enabled=false` together with `matchIfMissing=false`, but you must design a consistent contract.

**When `acme.reports.enabled=false`:** the `ReportsProperties` bean can still exist and be bound/validated; only the `ReportClient` from the conditional method above is not registered. If the application declares its own `ReportClient`, the condition above does not remove that custom bean. Namespace, registration condition, and dependency injection are three distinct mechanisms.

For Spring Boot to discover the library's auto-configuration, create the exact resource:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

Each line lists a fully qualified auto-configuration class name. This is the Spring Boot 3.x discovery mechanism; do not name the file `AutoConfiguration.imports.txt` and do not rely on component scanning to find auto-configuration classes.

There is no need to add `@Component` to `ReportsProperties` when `@EnableConfigurationProperties` is already used. Arbitrarily mixing component scanning, properties scanning, and explicit registration can create duplicate beans and make the lifecycle hard to control. For a library, explicit registration on auto-configuration is easy to understand and easy to test.

## 6. Runnable Spring Boot 3.3.5, Java 17 Example

This is a small Maven project with an **application** using a **simulated library** located in a separate package. `ReportClient` only holds config in memory and makes no real HTTP calls, so the example runs standalone.

### 6.1. Directory Tree

~~~text
reports-demo/
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

The application is in package `com.example.app`; the simulated library is in `com.example.lib`. By default `@SpringBootApplication` only component-scans from the application package downward, so auto-configuration classes sit outside the scan area and are loaded via `AutoConfiguration.imports`. In a real system, these two parts are usually packaged into separate JARs.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reports-demo</artifactId>
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

`spring-boot-configuration-processor` generates metadata for IDE key suggestions; it does not directly perform binding at runtime. In a real published library, make sure the metadata is generated and packaged with the corresponding artifact.

### 6.3. The Two Complete Classes Already Written

Create `ReportsProperties.java` with the exact content from section 4 and `ReportsAutoConfiguration.java` from section 5, keeping the packages, imports, and paths intact. Both classes above are complete classes and can be placed into Java files according to the directory tree in section 6.1.

### 6.4. ReportClient.java

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

import java.time.Duration;

public final class ReportClient {
    private final int batchSize;
    private final Duration timeout;

    public ReportClient(int batchSize, Duration timeout) {
        this.batchSize = batchSize;
        this.timeout = timeout;
    }

    public String describe() {
        return "batchSize=" + batchSize + ", timeout=" + timeout;
    }
}
~~~

### 6.5. application.yml

**src/main/resources/application.yml**

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 50
    timeout: 5s
~~~

The `AutoConfiguration.imports` file from section 5 contains a single line `com.example.lib.autoconfigure.ReportsAutoConfiguration`.

### 6.6. ReportsDemoApplication.java

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
            System.out.println(
                    "client=" + (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Alongside the Spring Boot logs, the exact lines printed by the runner are:

~~~text
enabled=true
batchSize=50
timeout=PT5S
client=batchSize=50, timeout=PT5S
~~~

`Duration.toString()` represents 5 seconds as `PT5S`. You can observe `batch-size` bound into `batchSize` and the `ReportClient` bean receiving the same configuration.

To override a key:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.batch-size=80
~~~

When running this separate command, the line `batchSize=50` changes to `batchSize=80` and the client reports `batchSize=80`. That is an override via a property source, without changing library code.

To test the condition:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.enabled=false
~~~

Aside from logs, the runner prints:

~~~text
enabled=false
batchSize=50
timeout=PT5S
client=absent
~~~

`ReportsProperties` is still bound, while the default client is not registered. The two commands above are **two independent runs**; do not pass both override values simultaneously in the same command.

## 7. Testing Namespace and Conditions with ApplicationContextRunner

A good library should test that its prefix reads only the relevant keys and that conditions behave according to the contract. Create:

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
    void bindsPropertiesFromOwnedNamespace() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.batch-size=50",
                "acme.reports.timeout=5s")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .getBatchSize()).isEqualTo(50);
                    assertThat(context.getBean(ReportClient.class)
                            .describe()).isEqualTo(
                                    "batchSize=50, timeout=PT5S");
                });
    }

    @Test
    void disabledFeatureHasNoDefaultClient() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Test
    void unrelatedNamespaceDoesNotChangeOwnedSettings() {
        runner.withPropertyValues("other.reports.batch-size=900")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .getBatchSize()).isEqualTo(25);
                });
    }

    @Test
    void rejectsInvalidBatchSize() {
        runner.withPropertyValues("acme.reports.batch-size=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void userCanOverrideDefaultClient() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class)
                            .describe()).isEqualTo(
                                    "batchSize=99, timeout=PT1S");
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

The expected result is that **all five tests pass**. The assertions respectively verify proper binding, disabling the default bean, immunity from other namespaces, validation of `batch-size`, and a custom bean causing auto-configuration to back off.

If multiple real starters are added to an application, additional integration tests should be run to detect property and bean collisions absent from isolated test suites. `ApplicationContextRunner` is especially well suited for verifying an auto-configuration's contract without starting the entire application.

## 8. Extending a Namespace by Subgroups Without Breaking the Contract

Suppose the reporting library adds export, HTTP, and retry:

~~~yaml
acme:
  reports:
    enabled: true
    export:
      format: pdf
      output-directory: ./reports
    http:
      connect-timeout: 2s
      read-timeout: 10s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

The contract includes:

~~~text
acme.reports.enabled
acme.reports.export.format
acme.reports.export.output-directory
acme.reports.http.connect-timeout
acme.reports.http.read-timeout
acme.reports.retry.max-attempts
acme.reports.retry.backoff
~~~

There are two ways to organize typed properties:

- **A single root class with nested properties**, for example `ReportsProperties.Export`, `ReportsProperties.Http`, `ReportsProperties.Retry`. Suitable when the options are usually used together and share the same lifecycle.
- **Multiple dedicated classes sharing the same root**, for example `@ConfigurationProperties("acme.reports.http")` and `@ConfigurationProperties("acme.reports.retry")`. Suitable when components consume different configurations and need explicit per-type registration.

Illustration of a dedicated class (this snippet only sketches the contract and is not a standalone runnable Java file):

~~~java
@ConfigurationProperties(prefix = "acme.reports.retry")
public class ReportsRetryProperties {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(500);

    // Add corresponding getters/setters or constructor binding.
}
~~~

If there is a nested custom object, the metadata processor may need `@NestedConfigurationProperty` in certain structures to describe the property group. This annotation serves **metadata** and does not replace how Spring Boot binds or registers beans.

Do not place library configuration under `server.*`, `spring.*`, or `management.*` merely because the library relates to servers, Spring, or monitoring. Those roots already have platform semantics. If the library needs to read a standard Spring Boot property, follow **that exact standard contract**; do not hijack standard keys as a custom API.

## 9. Compatibility When Renaming Keys

A namespace is a public API. Renaming `acme.reports.batch-size` to `acme.reports.max-batch-size` may force deployments to update YAML, environment variables, command-line args, ConfigMaps, deployment manifests, documentation, and tests.

Controlled approach:

1. Identify why the rename is needed and its impact on users.
2. If a transition period supporting both old and new keys is required, **design runtime aliasing/migration** and define clear precedence if both appear together.
3. Mark the property deprecated in metadata, write release notes, provide instructions for renaming env vars, and publish an end-of-support schedule.
4. Test separately the cases with only the old key, only the new key, both keys, and neither key.
5. Do not change the root prefix simply because a Java package was renamed, internal classes were moved, or the Maven artifact changed.

**Warning:** Spring Boot's `@DeprecatedConfigurationProperty` only helps metadata and documentation tools recognize a deprecated property; it **does not automatically bind the old name to a newly named field** unless you build a compatibility mechanism.

Without a strong reason, keep `acme.reports` stable and add new subgroups instead. Stability of configuration names is usually more important than having names mirror the exact current class structure.

## 10. Metadata and Documentation for Users

Because the namespace is the direct touchpoint for library users, publish:

| Key | Java type | Default | Meaning / constraints |
| --- | --- | --- | --- |
| `acme.reports.enabled` | `boolean` | `true` | Enables registration of the default ReportClient by auto-configuration |
| `acme.reports.batch-size` | `int` | `25` | Must be >= 1 due to `@Min(1)` |
| `acme.reports.timeout` | `Duration` | `3s` | Timeout with units, must not be null |

So that IDEs can suggest keys when users edit YAML/properties, add `spring-boot-configuration-processor` and inspect the metadata file inside the JAR: `META-INF/spring-configuration-metadata.json`. You can supplement it with `META-INF/additional-spring-configuration-metadata.json` when the annotation processor cannot express enough information.

Metadata aids discovery/documentation but **does not replace binding, validation, or fallbacks**. Defaults in metadata must also stay consistent with defaults in code. For passwords/tokens, avoid printing sensitive information via loggers, `toString()`, Actuator, or custom error messages; a namespace does not automatically mask data.

Note that `ReportsProperties` is still registered and validated when `enabled=false` in the design above. If a user sets `batch-size=0` together with `enabled=false`, validation of the properties bean can still cause startup to fail. That is a semantic that should be documented or redesigned if there is a requirement to validate only when the feature is enabled.

## 11. Common Mistakes

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| YAML has `batch-size: 50` but code still receives 25 | Key is missing `acme.reports` or class is not bound | Check the full key and `@EnableConfigurationProperties` |
| Two libraries both change according to a global `timeout` | No clear root prefix | Separate prefixes for each library |
| `@ConfigurationProperties` cannot be injected | Class is annotated only, bean not registered | Register in auto-configuration using `@EnableConfigurationProperties` |
| IDE does not suggest `acme.reports.*` | Metadata missing from artifact | Check the configuration processor and JAR packaging |
| `enabled=false` yet the properties bean still exists | Condition is placed only on ReportClient | Distinguish the properties bean from the service bean |
| `enabled=false` yet a custom ReportClient exists | Custom bean is owned by the application | Condition on the default `@Bean` does not remove custom beans |
| Changing prefix causes old configs to receive defaults instead | Public contract has changed | Provide a migration path and test against old keys |
| Assuming deprecation metadata creates an alias | Metadata does not change the runtime binder | Implement deliberate support for old/new keys |
| Misconfigured property fails silently without an error | Unknown fields may be ignored | Test the contract, validate important fields, consider unknown-key policies |
| Secret exposed in startup logs | Logging the entire properties object | Mask sensitive fields, do not print raw configuration |

To diagnose, prioritize checking the `ReportsProperties` bean in tests and the client creation condition. Spring Boot Actuator can expose `/actuator/configprops` when the module and endpoint are configured/exposed, but access control and sensitive data masking must be enforced.

## 12. Self-Check Questions

**Question 1.** Why should a reporting library not place `timeout` at the root?  
**Answer:** Another library might also need a timeout; `acme.reports.timeout` clearly identifies the owner and meaning.

**Question 2.** What is the canonical property for the `batchSize` field in a class with prefix `acme.reports`?  
**Answer:** `acme.reports.batch-size`; the environment can use `ACME_REPORTS_BATCHSIZE`.

**Question 3.** Is placing `@ConfigurationProperties` on a class enough for the application to inject it?  
**Answer:** No. The class must be registered via an appropriate mechanism, such as `@EnableConfigurationProperties` on the library's auto-configuration.

**Question 4.** Why can the `ReportsProperties` bean still exist when `acme.reports.enabled=false`?  
**Answer:** In the example, the disable condition is placed only on the method creating the default `ReportClient`. Properties are registered independently to bind and validate.

**Question 5.** If a public property is renamed, does `@DeprecatedConfigurationProperty` ensure the runtime continues to understand the old name?  
**Answer:** No. You must proactively implement aliasing/migration and test it.

**Question 6.** What method can verify that the library is not affected by `other.reports.batch-size`?  
**Answer:** `ApplicationContextRunner` setting the key of another namespace and asserting that `ReportsProperties.batchSize` remains at the default 25.

## 13. Applying to a Real Library

Before releasing a library starter, confirm these decisions: the root namespace belongs properly to the organization/feature; keys have canonical names and clear units; typed `@ConfigurationProperties` are registered from auto-configuration; `@ConditionalOnProperty` conditions use the right prefix; defaults and validation are consistent; metadata is published; documentation includes YAML and env var examples; tests prove that other namespaces do not interfere and custom beans can replace the default.

**Remember:** `@ConfigurationProperties` is the public configuration interface of a library. A dedicated namespace like `acme.reports` keeps multi-starter systems clear about **which property belongs to which library**, prevents name collisions, supports testing, and helps users upgrade safely.
