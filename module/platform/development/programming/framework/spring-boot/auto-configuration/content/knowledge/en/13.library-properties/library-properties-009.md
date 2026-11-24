# Distinguishing Stable Public Properties from Internal Implementation Details

**Topic:** Spring Boot Auto Configuration  
**Context:** Library Properties  
**Goal:** Design a Spring Boot starter that lets applications configure supported behaviors while allowing the library to refactor its internal structure and algorithms without breaking user configuration.

## 1. When Does a Property Become a Public Contract?

Suppose the library `acme-dispatch-starter` allows applications to declare:

```yaml
acme:
  dispatch:
    enabled: true
    connect-timeout: 2s
    max-attempts: 3
```

Once the library publishes these keys in documentation and deployment examples, users have the right to expect:

- `acme.dispatch.enabled` determines whether the starter's default client is activated.
- `acme.dispatch.connect-timeout` controls the connection establishment timeout, with clear units.
- `acme.dispatch.max-attempts` controls the number of attempts, with the convention **including the initial attempt**.

They form **the public configuration interface** if the library commits to supporting their names, types, semantics, defaults, and invalid-value handling across compatible releases.

Conversely, the library might internally use `InternalBackoffCalculator`, an `Executor`, `ThreadFactory`, a connection pool, or a specific transport selection algorithm. When these are not published as extension points, they are **implementation details** that can change during refactoring. Users should not have to edit YAML simply because the library author renamed a helper class.

**Key boundary:** A public property expresses *behavior the user is permitted to request*; an internal detail expresses *how the library implements that behavior*. A property does not become stable merely because `Environment.getProperty(...)` can read it or the Binder accepts it.

## 2. Practical Distinction Table

| Element | Example | Nature | Appropriate commitment |
| --- | --- | --- | --- |
| Feature toggle flag | `acme.dispatch.enabled` | Public property | Boolean type, default, bean registration condition |
| Timeout | `acme.dispatch.connect-timeout=2s` | Public property | Unit, scope of application, expiration behavior |
| User-level retry policy | `acme.dispatch.max-attempts=3` | Public property | Whether initial attempt is included, valid bounds |
| Helper class | `demo.internal.RetryPlanner` | Internal detail | Can be replaced as long as the contract holds |
| Thread name or implementation name | `dispatch-pool-0`, `JdkTransport` | Usually internal | No stability commitment unless published |
| User-suppliable `DispatchClient` bean | `@Bean DispatchClient` | Spring-layer extension point | Separate Java/bean contract, not a property |
| Secretly read string | `acme.dispatch.internal-buffer-count` | Hidden API risk | Remove or publish deliberately |
| IDE suggestion metadata | `spring-configuration-metadata.json` | Property description | Does not guarantee runtime binding or compatibility by itself |

Do not equate "technically accessible" with "officially supported by the library." However, once a hidden key has shipped in a release and users come to rely on it, removing it can still break deployments. Therefore avoid creating hidden APIs from the start.

## 3. How to Decide Which Properties to Expose Publicly

Before adding a key, answer:

1. **What is the application's genuine need?** For example timeout, feature toggle, concurrency, or retry count. If it only tunes a temporary implementation detail, keep it internal.
2. **Are the semantics independent of the current implementation?** `connect-timeout` still makes sense if you swap HTTP clients; `apache-pool-validation-thread-name` locks users into one specific library.
3. **What are the type and bounds?** For `Duration`, clarify units; for `max-attempts`, specify at least 1 and whether there is an upper cap.
4. **What is the default when omitted?** Defaults are also public behavior. Changing a default can cause major changes for applications that omit the key.
5. **What scope does the property affect?** A single default client, the entire starter, or every bean sharing the interface?
6. **Can the outcome be tested externally?** If you can only assert a private helper's name, the property likely describes an implementation detail rather than a contract.
7. **When users need to customize the entire algorithm, is there an SPI or bean extension?** Do not keep adding low-level flags as a substitute for a clean extension point.

A good public API typically has **few keys with durable meaning**, rather than dozens of flags tied to individual helpers.

## 4. Modeling the Public Contract with `@ConfigurationProperties`

Spring Boot encourages using `@ConfigurationProperties` for typed configuration groups. A Java 17 example:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
```

What to understand:

- `@ConfigurationProperties` declares a property group with canonical names and clear types.
- `@DefaultValue` is used by the Binder only when the property is absent; it **does not write that value into the entire `Environment`**.
- `Duration` handles units like `ms`, `s`, `m`, avoiding ambiguous integers ("is it seconds or milliseconds?").
- Records suit configuration option groups that are immutable at startup.
- Relaxed binding lets Spring Boot map canonical kebab-case in files to Java camelCase. Documentation should pick one consistent canonical spelling.

Do not scatter lines like `environment.getProperty("acme.dispatch.max-attempts")` in many places and parse types ad hoc in each. That easily causes name drift, missing validation, missing metadata, and hard-to-test defaults. `@ConfigurationProperties` is the central data point; **the annotation by itself is not a backward-compatibility policy**.

### 4.1. Namespace Boundaries

A library should use a dedicated prefix, such as `acme.dispatch`, rather than grabbing namespaces used by Spring Boot like `spring.*`, `server.*`, or `management.*`. Spring Boot's own properties can still be read during integration, but new keys created for the library belong in its own namespace.

Documented names should use lowercase kebab-case:

```properties
acme.dispatch.enabled=true
acme.dispatch.connect-timeout=750ms
acme.dispatch.max-attempts=5
```

Changing `max-attempts` to `max-retries` is not a simple Java variable rename if users have already stored the old key in Kubernetes ConfigMaps, Helm values, or CI/CD configuration systems.

### 4.2. Validation Is Part of the Contract

An attempt count of 0 is usually meaningless. Jakarta Bean Validation can be used:

```java
@Validated
@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
```

The snippet above requires the corresponding imports (`@Validated` from Spring, `@Min` from Jakarta Validation) and a validation implementation on the classpath, such as `spring-boot-starter-validation`.

Validated types catch errors early when the application initializes, rather than waiting until a runtime task encounters an invalid retry count. Still, constraints must **be documented and tested**, not left hidden in code.

## 5. Public Defaults Must Match Auto-Configuration Conditions

A subtle bug is assuming `@DefaultValue("true")` in `DispatchProperties` automatically makes the bean registration condition see `acme.dispatch.enabled=true`.

In reality, these are two independent mechanisms:

- **The Binder** takes the default from the record if the key is missing.
- **`@ConditionalOnProperty`** inspects the effective value in `Environment` and does not guarantee reading defaults from the record.

Example:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.dispatch",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
DispatchClient dispatchClient(DispatchProperties properties) {
    return new DispatchClient(
            properties.connectTimeout(),
            properties.maxAttempts());
}
```

Omitting `acme.dispatch.enabled` makes the condition **not match** because `matchIfMissing=false`. With the record defaulting to `enabled=false`, both decisions agree. However, if someone changes only `@DefaultValue("true")`, the record may receive `true` while the factory still creates no bean when missing. Changing a public default requires checking both the condition annotation and tests.

If the feature is genuinely enabled by default, make `matchIfMissing=true` and the corresponding binding default explicit. Do not use internal defaults as an excuse to break the implemented contract.

## 6. Complete Example: Java 17, Spring Boot 3.3.5, and `ApplicationContextRunner`

This is a small Maven project illustrating three public properties, validation, and an extension point. Learners can compile and run tests without a real task-dispatching system or network connection.

### 6.1. File Structure

```text
dispatch-starter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DispatchProperties.java
    │   │   ├── DispatchClient.java
    │   │   └── DispatchAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/
        └── DispatchAutoConfigurationTest.java
```

### 6.2. Create `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>dispatch-starter-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The `spring-boot-configuration-processor` dependency builds metadata for IDE autocomplete, rather than controlling runtime binding. On newer toolchains, annotation processing may need to be declared explicitly in the Maven Compiler Plugin per official documentation.

### 6.3. `src/main/java/demo/DispatchProperties.java`

```java
package demo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
```

Public contract: `enabled=false`, 2-second timeout, up to 3 attempts including the initial attempt. `max-attempts` is at least 1; test code will prove a value of 0 is rejected.

If property descriptions are needed in metadata from the record, add Javadoc at the record level with `@param` tags for the three components. The annotation processor supports extracting matching descriptions from source code; when it cannot infer them, metadata can be supplemented via a separate file. Never create a properties class just to expose internal debug fields.

### 6.4. `src/main/java/demo/DispatchClient.java`

```java
package demo;

import java.time.Duration;

public record DispatchClient(Duration connectTimeout, int maxAttempts) {
}
```

In the example, the client only holds bound configuration for easy testing. A production library might use an HTTP client, queue, or other retry helper; users still only need to know the public semantics of timeout and attempts.

### 6.5. `src/main/java/demo/DispatchAutoConfiguration.java`

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(DispatchProperties.class)
public class DispatchAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.dispatch",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(DispatchClient.class)
    DispatchClient dispatchClient(DispatchProperties properties) {
        return new DispatchClient(
                properties.connectTimeout(),
                properties.maxAttempts());
    }
}
```

The property condition represents the **decision to enable/disable the library's fallback client**. The missing-bean condition is a **Spring-bean-layer extension point**, allowing the application to supply its own `DispatchClient` and preventing the starter from creating another bean of the same type.

`@EnableConfigurationProperties` registers and binds `DispatchProperties` as soon as the application context builds. When `enabled=false`, the properties bean still exists while the fallback client does not appear; this is an intentional design.

### 6.6. Registering Auto-Configuration

File:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content is exactly one line:

```text
demo.DispatchAutoConfiguration
```

Spring Boot 3.x uses this imports file to discover the starter's auto-configuration on the classpath. Renaming the class or moving its package affects the starter's distribution structure, yet **does not mean users must rename** published properties.

### 6.7. `src/test/java/demo/DispatchAutoConfigurationTest.java`

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DispatchAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DispatchAutoConfiguration.class));

    @Test
    void missingPropertiesUsePublicDefaultsAndDisableClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DispatchProperties.class);
            DispatchProperties p = context.getBean(DispatchProperties.class);
            assertThat(p.enabled()).isFalse();
            assertThat(p.connectTimeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(p.maxAttempts()).isEqualTo(3);
            assertThat(context).doesNotHaveBean(DispatchClient.class);
        });
    }

    @Test
    void explicitEnableUsesDefaultParameters() {
        runner.withPropertyValues("acme.dispatch.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DispatchClient.class);
                    DispatchClient client = context.getBean(DispatchClient.class);
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(2));
                    assertThat(client.maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void documentedKeysChangeObservableBehavior() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.connect-timeout=750ms",
                        "acme.dispatch.max-attempts=5")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    DispatchClient client = context.getBean(DispatchClient.class);
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofMillis(750));
                    assertThat(client.maxAttempts()).isEqualTo(5);
                });
    }

    @Test
    void explicitFalseTurnsDefaultOff() {
        runner.withPropertyValues("acme.dispatch.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(DispatchClient.class);
                });
    }

    @Test
    void invalidAttemptCountFailsValidation() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.max-attempts=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void undocumentedInternalLookingKeyHasNoSupportedEffect() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.internal-worker-count=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(DispatchProperties.class)
                            .maxAttempts()).isEqualTo(3);
                    assertThat(context.getBean(DispatchClient.class)
                            .maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void userProvidedClientMakesDefaultBackOff() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .withPropertyValues("acme.dispatch.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DispatchClient.class);
                    assertThat(context.getBean(DispatchClient.class)
                            .maxAttempts()).isEqualTo(9);
                    assertThat(context).hasBean("customClient");
                    assertThat(context).doesNotHaveBean("dispatchClient");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {
        @Bean
        DispatchClient customClient() {
            return new DispatchClient(Duration.ofSeconds(9), 9);
        }
    }
}
```

Run in the `dispatch-starter-demo` directory:

```bash
mvn test
```

Expected result when JDK 17+, Maven, and dependencies are available:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
```

This is the typical summary printed by Maven Surefire; the code itself prints no stdout. If the environment lacks Maven/JDK or cannot download dependencies, that is an execution-environment error rather than claiming tests passed.

The tests verify **promised behavior**: defaults, enable/disable, typed values, validation, and bean extension. They avoid depending on helper names or how retries are implemented internally.

**Note on unknown keys:** `@ConfigurationProperties` can ignore unknown fields by default. The `internal-worker-count` test illustrates a key that looks like internal configuration yet is not read by the record and does not alter behavior. An unknown key accepted without error **does not prove it is a supported option**. If an application needs strict rejection of typos, design a suitable detection/validation policy.

## 7. Metadata: A Discovery Tool, Not a Runtime Mechanism

Spring Boot can generate:

```text
META-INF/spring-configuration-metadata.json
```

This file helps IDEs suggest names, types, defaults, descriptions, and deprecations. When `spring-boot-configuration-processor` is used properly, most metadata is generated from `@ConfigurationProperties` classes.

An **illustrative** entry:

```json
{
  "properties": [
    {
      "name": "acme.dispatch.connect-timeout",
      "type": "java.time.Duration",
      "description": "Connection timeout for the default client.",
      "defaultValue": "2s"
    }
  ]
}
```

This is abbreviated JSON explaining the metadata structure, not byte-for-byte output of a Maven build. Real metadata may include `groups`, `sourceType`, `hints`, and multiple properties.

You can supplement metadata for cases the processor cannot infer using:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

The annotation processor merges supplemental metadata with auto-generated metadata. There is no need to create a supplemental file when existing info is already described accurately.

Three layers that must not be confused:

| Layer | What does it do? | What does it not do? |
| --- | --- | --- |
| `@ConfigurationProperties`/Binder | Reads, converts types, binds/validates values at runtime | Does not guarantee backward compatibility across releases by itself |
| Configuration metadata | Supplies info to IDEs, tooling, documentation generators | Does not make a key work if code does not read it |
| Documentation, tests, and versioning policy | Publishes and protects the contract users rely on | Does not replace runtime implementation |

A key appearing in metadata does not prove conditional beans were created; `ApplicationContextRunner` and behavior tests are needed. A key secretly read from `Environment` yet absent from metadata can still affect runtime; that is why hidden APIs must be avoided.

## 8. Public Properties and Internal Details During Refactoring

Suppose v1 uses `LegacyHttpTransport` and v2 uses `JdkHttpClientTransport`. If user-facing behavior of `connect-timeout=2s` remains equivalent, keep the public key unchanged.

**Internal changes that need not break the contract:**

- Renaming private helpers/packages.
- Changing thread-pool selection algorithms, provided public behavior stays unchanged.
- Swapping HTTP libraries while enforcing the same published timeouts/retries.
- Optimizing caches and internal scheduling mechanisms.
- Changing how beans not published as extension points are wired.

**Changes that can break the contract even though Java code still compiles:**

- Changing `max-attempts` from total attempts to retries **excluding the initial attempt**.
- Changing the `enabled` default from `false` to `true`.
- Changing the default timeout from `2s` to `30s`.
- Deleting `acme.dispatch.connect-timeout` or changing an implicit unit.
- Changing property precedence rules when users provide multiple configuration sources.
- Removing default-bean back-off even though the library published bean overrides as a supported customization path.

Do not equate changing a Java field in the library with changing the operator's contract. A property is an interface between the application and the library even when users recompile no source code.

### 8.1. Should You Add an "Internal Property" for Debugging?

Example of internal code:

```java
int workers = environment.getProperty(
        "acme.dispatch.executor.pool-implementation-size",
        Integer.class,
        4);
```

This is only an illustrative snippet inside an existing method requiring an `environment` variable of type Spring `Environment`.

If users discover the key and start relying on it, swapping the executor can break their behavior even though the key was undocumented. Better options:

- If **concurrency** is a legitimate need, create a neutral property such as `acme.dispatch.concurrency`, with clear defaults/constraints and tests.
- If it only serves debugging a bug, use log levels, metrics, or a dedicated test hook; avoid placing an unstable technical property in production config.
- If the whole strategy needs swapping, design a proper SPI/bean override rather than placing an implementation class name inside a property.

Do not name keys like `acme.dispatch.netty.worker-loops` when the library wants to keep the freedom to switch implementations and applications do not genuinely need Netty-level control.

## 9. Changing, Deprecating, and Migrating Public Properties

A published property should never be renamed/removed silently. Sample migration plan when changing `acme.dispatch.retry-count` to `acme.dispatch.max-attempts`:

1. Define the meaning and default of the new name. Ensure the rename does not accidentally alter semantics.
2. During the transition period, **runtime code must actually read/bind both the old key and the new key** if the library commits to compatibility.
3. Define a clear rule when users declare both—for example, the new key takes precedence—and add tests.
4. Record deprecation metadata with reason, since-version, replacement, and migration notice.
5. Remove the old key's binding path only according to the published versioning policy; update release notes and migration guides.

Example deprecation metadata structure:

```json
{
  "properties": [
    {
      "name": "acme.dispatch.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed to max-attempts to describe the total number of attempts.",
        "replacement": "acme.dispatch.max-attempts",
        "since": "2.1.0"
      }
    }
  ]
}
```

**Do not paste this JSON into the demo and assume the old name is automatically supported.** Metadata only signals tooling; code itself must implement aliasing/binding. Level `warning` usually applies to properties still handled during migration. Level `error` describes properties no longer handled; changing the metadata level does not automatically disable code that still reads the property.

`@DeprecatedConfigurationProperty` can be used on an appropriate getter of a JavaBean-style `@ConfigurationProperties` class to generate metadata. Do not mistake this deprecation marker annotation for an automatic aliasing mechanism, and do not assume it applies automatically to record components.

**Items to review for breaking changes:** renaming, changing type, changing unit, changing default, changing semantics, removing previously valid values, changing validation, and changing configuration source precedence. All can break old deployments even when Java code stays untouched.

## 10. Public Does Not Mean Exposing Secret Values

A configuration's name may be public while its value remains secret:

```properties
acme.dispatch.api-token=${DISPATCH_TOKEN}
```

If the library officially supports a key for credentials, document how to supply secrets safely, and avoid logging the value or leaking tokens in error messages. Document only **the name, type, and behavior** of the key; never ask users to commit real credentials into repositories.

Endpoints such as `/actuator/env` and `/actuator/configprops` can aid diagnosis, yet must restrict access and configure sensitive-data masking. "Public property" is an API stability concept, never permission to disclose data.

## 11. Debugging Configuration That Has No Effect

If a user sets `acme.dispatch.connect-timeout=750ms` yet the client still uses the default:

1. Verify **the exact prefix/key**; avoid confusing `connection-timeout` with `connect-timeout`.
2. Inspect the **effective** value in Spring `Environment`, including YAML, profiles, runtime environment, and command line. Do not check only a single file.
3. Check whether `DispatchProperties` was registered via `@EnableConfigurationProperties` or scanning.
4. Check whether the property bound properly to `Duration` and whether any conversion/validation error occurred.
5. Check whether `@ConditionalOnProperty` matched; `matchIfMissing` and record defaults are not the same mechanism.
6. Check whether `@ConditionalOnMissingBean` backed off because the application supplied its own `DispatchClient`. In that case, the active client is not necessarily the library's fallback bean.
7. Use the Condition Evaluation Report via `--debug` or `/actuator/conditions` when enabled and properly secured. The `configprops` endpoint helps inspect binding, but never expose secrets.

To diagnose a library API, prefer testing **output values/bean behavior**. Asserting only private helper class names causes valid refactoring to break tests while failing to prove what users rely on.

## 12. Checklist for Releasing a Public Property

| Check | Expectation |
| --- | --- |
| Canonical name and namespace | Clear, stable, does not occupy someone else's namespace |
| Type and unit | `boolean`, `Duration`, integers with clear descriptions |
| Defaults and missing branch | Binder and conditions are consistent |
| Validation | Nonsensical values report clear errors |
| Documentation | Includes YAML/properties examples and constraints |
| Configuration metadata | IDE autocompletes exact name/type/description |
| Runtime tests | Missing, true/false, override, invalid, user bean |
| Compatibility tests | No unintended alias loss or meaning drift |
| Internals | No accidental exposure of internal classes/helpers/secrets |
| Release notes | Clearly list added/modified/deprecated properties |

In Maven, you can package with:

```bash
mvn package
```

After building, verify the artifact contains `META-INF/spring-configuration-metadata.json` and `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` when the annotation processor is enabled and auto-configuration is properly packaged. Metadata may be incomplete if the processor did not run or source info is missing; in that case fix the build/config rather than substituting behavioral tests with faith that IDE autocomplete proves runtime behavior.

## 13. Self-Check Questions

**Question 1.** If a library replaces a Netty client with JDK `HttpClient` while still enforcing `connect-timeout` identically, must the property change?  
**Answer:** No. Timeout is public semantics independent of the implementation class.

**Question 2.** A helper class named `RetryPlanner` is deleted during refactoring. Is this a breaking change?  
**Answer:** No, if it was truly an internal detail, not part of a published contract/extension point, and public behavior is preserved.

**Question 3.** Does changing the `enabled` default from `false` to `true` in a record automatically enable the fallback when `@ConditionalOnProperty(matchIfMissing=false)`?  
**Answer:** No. Binder defaults do not add properties into `Environment`; conditions must align with the policy.

**Question 4.** Metadata specifies `"replacement"` for an old property. Does Spring Boot automatically recognize the alias?  
**Answer:** No. Metadata does not implement runtime binding/migration paths.

**Question 5.** Is any string ignored by the Binder without error a supported property?  
**Answer:** No. Unknown keys may be ignored; only keys with a clear contract and code reading them are supported options.

**Question 6.** Why can changing from "three total attempts" to "three retries after the initial attempt" break compatibility?  
**Answer:** Runtime behavior and service load change even though the property's name and type stayed the same.

**Question 7.** Users want to swap the entire implementation; should you expose the private helper class name as a property?  
**Answer:** Usually you should design an official extension point/bean override instead; making implementation classes public turns refactoring into a breaking change.

## 14. Principles to Remember

- **Public configuration contract** includes name, meaning, type, unit, default, validation, scope, and versioning policy.
- **Internal implementation** includes helper classes, algorithms, thread names, unpublished bean names, and wiring details that can change while preserving the contract.
- `@ConfigurationProperties` and metadata help build typed, discoverable configuration APIs; they do not decide release compatibility by themselves.
- Binder defaults differ from `@ConditionalOnProperty` decisions when missing. Always test both.
- `@ConditionalOnMissingBean` creates a separate extension point at the Spring bean layer; it is not synonymous with a configuration property.
- Deprecation metadata does not fix old keys by itself. Supporting transitions requires implementing and testing aliases at runtime.
- A few stable keys, clear documentation, and behavioral tests are more reliable than a long list of settings tied to temporary implementations.

### Official Documentation

- [Spring Boot 3.3 — Externalized Configuration and Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html)
- [Spring Boot — Generating Metadata with Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot — Configuration Metadata Format and Deprecation](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
