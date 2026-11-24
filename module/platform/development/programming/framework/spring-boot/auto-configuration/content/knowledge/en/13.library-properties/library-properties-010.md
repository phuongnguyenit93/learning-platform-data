# Checking Configuration Source Precedence Within Auto-Configuration Scope

## 1. The Problem: Same Key, Multiple Sources—Which Value Does Auto-Configuration Receive?

A Spring Boot library might provide auto-configuration for a data-export feature. The library wants the feature **disabled by default**, allowing consuming applications to **enable/disable it via external configuration**, while also allowing the export format to change from `csv` to `json`.

Suppose the feature keys are:

```properties
acme.export.enabled=true
acme.export.format=json
```

In a real application, the same `acme.export.enabled` key can appear in many places: packaged config files, files outside the JAR, profile-specific configs, environment variables, Java system properties, command-line arguments, or test-specific properties.

**The question is not "which source was read first?", but "what is the final effective value in Spring `Environment` at the moment auto-configuration is evaluated?".** When a key appears multiple times, the highest-precedence source active for that context determines the result. Spring Boot does not pick values in the order seen in a README, and a library does not outrank the application merely because the library registers beans early.

After this lesson, you will be able to:

1. Explain precedence among `PropertySource`, `ConfigData`, environment variables, system properties, and command-line arguments in Spring Boot 3.3.
2. Distinguish the value `@ConditionalOnProperty` uses to **toggle beans** from the value `@ConfigurationProperties` **binds** into a configuration object.
3. Design a library's defaults and namespace so consuming applications remain in control of the feature.
4. Build a source conflict matrix and predict whether the bean is created and what configuration is bound.
5. Verify ordering with a Java 17+/Spring Boot 3.3 test having clear inputs and outputs.

## 2. PropertySource and Value Selection

Spring `Environment` represents the configuration visible to the application. Each `PropertySource` is a source capable of supplying key–value pairs. A `ConfigurableEnvironment` holds an **ordered** list of `MutablePropertySources`.

When resolving `acme.export.enabled`, Spring walks the active precedence order and takes the value from the highest-precedence matching source that supplies that key. If one source lacks the key, Spring checks the next source. Precedence applies **per key**, with no rule saying "once one source is chosen, every key of an object must come from that same source."

Example:

```text
HIGH Priority
┌─────────────────────────────────────────────┐
│ override: acme.export.enabled = true        │
│           (no acme.export.format)           │
├─────────────────────────────────────────────┤
│ base:     acme.export.enabled = false       │
│           acme.export.format  = csv         │
└─────────────────────────────────────────────┘
LOW Priority
```

Effective values:

```text
acme.export.enabled -> true   (from override)
acme.export.format  -> csv    (from base)
```

**There is no such thing as `format` becoming blank** just because the higher-precedence source omitted it. On the other hand, if the higher source has `enabled=false`, Spring does not ignore `false` to grab `true` from a lower source: `false` is a real value.

### Distinguishing Declaration Order from Precedence Order

This mechanism is completely different from:

- The order in which `@Configuration`/`@AutoConfiguration` classes are processed.
- The order in which beans are created or injected.
- The order of field names inside `@ConfigurationProperties`.
- The order of lines in a deployment guide.

Auto-configuration ordering can affect bean conditions based on already-processed bean definitions; when resolving properties, the effective configuration sources in `Environment` are what decide.

## 3. Standard Precedence Order in Spring Boot 3.3

According to Spring Boot 3.3 documentation, the following table goes from **lowest precedence to highest precedence**. A lower-row source, when supplying the same key and active, can override rows above it.

| Order | Configuration source | Practical meaning |
|---:|---|---|
| 1 | Default properties set via `SpringApplication.setDefaultProperties(...)` | Very low fallback values |
| 2 | `@PropertySource` on `@Configuration` | Additional source during context refresh |
| 3 | **Config data**: `application.properties`/`application.yml`, profiles, and imports | Standard file-based configuration |
| 4 | `RandomValuePropertySource` | Primarily for `random.*` |
| 5 | OS environment variables | Used in container/cloud deployments |
| 6 | Java system properties (`-Dkey=value`) | Can override corresponding env vars |
| 7 | JNDI `java:comp/env` | When running in a JNDI-capable environment |
| 8 | ServletContext init parameters | Applies to relevant servlet environments |
| 9 | ServletConfig init parameters | Applies to specific servlets |
| 10 | `SPRING_APPLICATION_JSON` / `spring.application.json` | JSON configuration injected into Environment |
| 11 | Command-line arguments `--key=value` | By default beats file, env, and system property sources in SpringApplication |
| 12–14 | Test properties via `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource` | Test-scoped sources, evaluated only in contexts that include them |
| 15 | Devtools global settings (when devtools is active) | Special source for development environments |

**This does not mean every source above exists in every run.** A CLI app without servlet support has no ServletConfig init parameters; normal production apps have no test sources; when devtools is inactive there are no devtools global settings. Moreover, code can insert custom `PropertySource`s via `addFirst`, `addLast`, `addBefore`, or `addAfter` and alter the actual order.

For common operational sources in Spring Boot 3.3, remember:

```text
command line: --acme.export.enabled=...
               ↑ higher priority
Java system property: -Dacme.export.enabled=...
               ↑
OS environment: ACME_EXPORT_ENABLED=...
               ↑
Config data: application-prod.yml / application.yml
               ↑
SpringApplication defaultProperties
               ↑ lower priority
```

Arrows point toward increasing precedence. When running with default `SpringApplication`, command-line arguments starting with `--` are added to Environment; this behavior can be disabled via `setAddCommandLineProperties(false)`. Never assert that command-line args always win if the application customized the default mechanism.

### 3.1. Specific Rules Inside Config Data

"Config Data" is not just a single file. With Spring Boot 3.3's default locations, file groups typically override from lowest to highest in this order:

1. `application.properties`/YAML packaged **inside the JAR**.
2. `application-{profile}.properties`/YAML **inside the JAR**.
3. `application.properties`/YAML **outside the JAR**.
4. `application-{profile}.properties`/YAML **outside the JAR**.

For example: the application packages `application.yml` with `acme.export.enabled=false`, an external `application-prod.yml` outside the JAR sets `acme.export.enabled=true`, and the `prod` profile is active; the external profile-specific config has higher precedence. If the command line then passes `--acme.export.enabled=false`, the final effective value is `false`.

Details that can alter the outcome:

- `spring.config.import`: imported sources can **take precedence over the file that triggered the import**, and with multiple imports, later imports can override earlier ones.
- `spring.config.location` replaces default config locations; `spring.config.additional-location` adds locations, generally letting additional files override.
- Multiple profiles active simultaneously: location grouping and profile order affect override rules; for simple profiles, later profiles can override earlier ones.
- If the same location contains both `application.properties` and `application.yml`, Spring Boot prefers `.properties`; standardize on one format to stay predictable.
- Multi-document YAML files: documents appearing later can override earlier documents when both apply.

**Why list these exceptions?** A library should never assume "external file beats JAR" when an application configured custom locations/imports/profiles. The right conclusion always rests on **the actual active source list**.

## 4. From Effective Value to Auto-Configuration

Consider the following auto-configuration (illustrative snippet; types are fully defined in section 7):

```java
@AutoConfiguration
@EnableConfigurationProperties(ExportProperties.class)
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.export",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ExportClient.class)
    ExportClient exportClient(ExportProperties properties) {
        return new ExportClient(properties.getFormat());
    }
}
```

Three distinct things happen:

1. Spring Boot collects and prepares `PropertySource`s, forming the effective Environment.
2. When evaluating the `@Bean` method, `@ConditionalOnProperty` reads the effective value of `acme.export.enabled`. If the key is missing or does not equal `true` (case-insensitive comparison), the condition does not match.
3. If the property condition matches and no other `ExportClient` bean causes `@ConditionalOnMissingBean` to fail, Spring registers the default bean; `@ConfigurationProperties` binds `acme.export.format` into `ExportProperties` to create `ExportClient`.

**A library does not dictate precedence order by declaring `@ConditionalOnProperty` before `@EnableConfigurationProperties`.** The two annotations read aspects of Environment according to their roles; they do not set source priority.

### 4.1. `@ConditionalOnProperty` and `@ConfigurationProperties` Have Different Roles

| Component | Responsibility | Based on what? |
|---|---|---|
| `@ConditionalOnProperty` | Should this configuration/bean be registered? | Property value present and matching condition at evaluation time |
| `@ConfigurationProperties` | Bind keys into a typed configuration object | Effective values via Spring Boot's Binder |
| `@ConditionalOnMissingBean` | Should it yield to a user-created bean? | Existing bean definitions / candidates |
| `@ConditionalOnClass` | Is a required dependency class on the classpath? | Classpath, not PropertySource |

A field `format = "csv"` initialized inside `ExportProperties` is **the object's Java default**, useful when `acme.export.format` is absent. It **does not automatically inject** `acme.export.format=csv` into Spring Environment for other condition annotations to see.

Likewise, if you set `private boolean enabled = true;` as a default inside a `@ConfigurationProperties` object while the bean condition uses `@ConditionalOnProperty(..., matchIfMissing=false)`, then **when the key is missing**, the conditional bean is still **not created**. Never assume an object's Java default puts that property into Environment.

### 4.2. Source Precedence Does Not Mean Value Validation

`@ConditionalOnProperty(havingValue="true")` requires the string `true`; values like `"yes"` or `"1"`, even if accepted by some Boolean conversion systems, **do not** match `havingValue="true"`. If a higher-precedence source has `acme.export.enabled=truue` while a lower source has `true`, Spring picks **`truue`** as the effective value; the condition does not match. It does not "fall back and retry" the lower `true` value.

With `havingValue` left empty, `@ConditionalOnProperty` defaults to matching any present value **other than `false`**. Therefore features requiring explicit opt-in should use `havingValue="true", matchIfMissing=false`. If invalid configuration must be rejected with a clear error message, use proper validation/config checking; the condition itself does not guarantee every typo fails startup.

### 4.3. Do Not Confuse One-Time Initialization with Dynamic Toggling

`@ConditionalOnProperty` is typically evaluated when creating the ApplicationContext. Editing a file on disk or an environment variable **after the context has started** does not automatically add or remove beans. If changing features without restarting is required, that is a separate runtime problem requiring a reload/refresh mechanism and consistent state management—it cannot be solved merely with PropertySource ordering.

## 5. Contract for a Library's Properties

Concrete design for the data-export library:

| Property | Purpose | Sample values | Recommended default |
|---|---|---|---|
| `acme.export.enabled` | Allows registering the default `ExportClient` | `true`/`false` | **Off when missing** (via `matchIfMissing=false`) |
| `acme.export.format` | Export data format | `csv` or `json` | `csv` in `ExportProperties` |
| `acme.export.batch-size` | Items processed per batch if needed later | Positive integer, e.g. `100` | Can have a sensible default and validation |
| `acme.export.endpoint` | Data target if integrating externally | Valid URL | Can be required only when the feature is enabled |

**Design principle:** a library should publish a **stable namespace**, kebab-case keys, and clear defaults; the deploying application should be where per-environment config values are decided. Avoid overly generic keys like `enabled` or `service.mode` that easily collide with the application and other starters.

For custom libraries you own, the typical model is:

- `@AutoConfiguration` to provide the bean registration mechanism.
- `@EnableConfigurationProperties(...)` or matching scanning to register typed properties.
- `@ConditionalOnProperty` to gate feature registration by config key.
- `@ConditionalOnMissingBean` to let applications supply a replacement bean if the library designs that extension point.
- Value defaults are usually declared in the properties object; application/profile/deployment configs can override published keys.

### Do Not Use a Starter's Config File to Compete with the Application

A starter may include properties/YAML resources, yet should not silently rely on **an `application.properties` bundled in the starter JAR** always being the sole default source or holding a fixed order in every app. Applications can have multiple config data locations, imports, profiles, and custom `PropertySource`s. Java defaults in `@ConfigurationProperties` and condition defaults are easier to reason about for library-owned options.

If a library forces values via `Environment.getPropertySources().addFirst(...)` in a startup hook, it can **accidentally override** sources supplied by the application/operator. That approach is appropriate only when explicitly required and with a documented precedence policy; for ordinary feature flags, it is an unfriendly design.

A library should document: full key names, expected types, defaults when omitted, which beans are affected, whether restarts are required, conditions for yielding to user beans, and override examples in `application.yml`/env/command line. This information matters more than listing every internal configuration class name.

## 6. Precedence Scenario Matrix to Test

For `acme.export.enabled` and `acme.export.format`, table conventions:

- **L** = a lower-precedence config source present.
- **H** = a higher-precedence config source present.
- **∅** = key not supplied by that source.
- Bean condition is `havingValue="true", matchIfMissing=false`.
- `ExportProperties.format` has Java default `csv` if that key is unconfigured.
- Assume no other `ExportClient` bean and no third PropertySource containing the same keys.

| Scenario | L: enabled / format | H: enabled / format | Effective values | `ExportClient` present? | Format used |
|---|---|---|---|---|---|
| 1. Override enables and changes format | `false / csv` | `true / json` | `true / json` | **Yes** | `json` |
| 2. Override disables | `true / csv` | `false / json` | `false / json` | **No** | Bean not created |
| 3. Higher source omits keys | `true / csv` | `∅ / ∅` | `true / csv` | **Yes** | `csv` |
| 4. Higher source only enables feature | `false / csv` | `true / ∅` | `true / csv` | **Yes** | `csv` |
| 5. `enabled` completely missing | `∅ / csv` | `∅ / json` | `∅ / json` | **No** | Bean not created |
| 6. Enabled value in higher source is mistyped | `true / csv` | `truue / json` | `truue / json` | **No** | Bean not created |
| 7. Higher source only changes format | `true / csv` | `∅ / json` | `true / json` | **Yes** | `json` |

In scenarios 2 and 5, the `ExportClient` bean is absent, yet if auto-configuration is still loaded and registers `ExportProperties`, the properties object may still be bound. Merely **not having the client bean** does not mean the library or entire auto-configuration was never evaluated.

A few additional scenarios in typical Spring Boot runs:

| Lower source | Higher source | Final value | Meaning |
|---|---|---|---|
| `application.yml: enabled=false` | `--acme.export.enabled=true` | `true` | CLI enables feature |
| `application.yml: enabled=true` | `ACME_EXPORT_ENABLED=false` | `false` | OS env disables feature if no higher source overrides |
| `ACME_EXPORT_ENABLED=true` | `-Dacme.export.enabled=false` | `false` | System property beats env |
| `-Dacme.export.enabled=false` | `--acme.export.enabled=true` | `true` | CLI beats system property |
| `application.yml: enabled=true` | `application-prod.yml: enabled=false` in same location, prod profile active | `false` | Profile-specific config overrides base config |
| `application.yml: enabled=false` | `spring.config.import=other.properties` where imported file sets enabled=true | `true` | Import is processed with precedence per Config Data rules |

**Note:** the environment variable corresponding to the dotted key is `ACME_EXPORT_ENABLED`. For keys with dashes, Spring Boot applies its own environment-variable naming rules; verify canonical names in documentation rather than guessing. And if another source outranks H, adjust the matrix to match actual sources.

## 7. Java 17+, Spring Boot 3.3 Example: Testing Source Precedence

To make a test **independent of the learner's machine environment**, the example does not require you to actually modify OS environment variables or command-line flags. We simulate two `MapPropertySource`s via Spring API: `simulatedDeployment` has higher priority than `simulatedConfigFile`. Then `ApplicationContextRunner` starts a fresh context for each scenario and checks the bean provided by auto-configuration.

This is a **direct simulation of PropertySource ordering rules**, without claiming `simulatedDeployment` is a source automatically created by Spring Boot. Comparing real files, env, and CLI is covered in sections 6 and 8.

### 7.1. Project Layout

```text
property-priority-demo/
├── pom.xml
└── src/
    ├── main/java/demo/priority/
    │   ├── ExportClient.java
    │   ├── ExportProperties.java
    │   └── ExportAutoConfiguration.java
    └── test/java/demo/priority/
        └── PropertyPriorityTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>property-priority-demo</artifactId>
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
</project>
```

Spring Boot's Maven parent configures compiler and test plugins appropriately. The example uses Maven so it fits easily in a standalone folder, though the same principles apply to Gradle projects.

### 7.3. ExportClient.java

```java
package demo.priority;

public record ExportClient(String format) {
}
```

Java 17 supports `record`. This object captures the actual format produced from configuration.

### 7.4. ExportProperties.java

```java
package demo.priority;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.export")
public class ExportProperties {

    private String format = "csv";

    public String getFormat() {
        return format;
    }

    public void setFormat(String format) {
        this.format = format;
    }
}
```

`format = "csv"` is the Java default; if Environment has `acme.export.format`, the Binder can override it. This class **contains no `enabled` field**, because the test wants `@ConditionalOnProperty` to decide the flag directly without triggering conversion errors from placing a mistyped string into a `Boolean` field. In production applications, you can add validation for flags/formats per contract requirements.

### 7.5. ExportAutoConfiguration.java

```java
package demo.priority;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(ExportProperties.class)
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.export",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ExportClient.class)
    ExportClient exportClient(ExportProperties properties) {
        return new ExportClient(properties.getFormat());
    }
}
```

In the test example we load the class into the context with `AutoConfigurations.of(...)`. When packaging a real library for Spring Boot auto-discovery, add the full name `demo.priority.ExportAutoConfiguration` into `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` of the corresponding JAR.

### 7.6. PropertyPriorityTest.java

```java
package demo.priority;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyPriorityTest {

    private static final String ENABLED = "acme.export.enabled";
    private static final String FORMAT = "acme.export.format";

    // Simulate two sources at the same level from config/deployment,
    // with simulatedDeployment having higher priority.
    private ApplicationContextRunner withSources(
            Map<String, Object> lower,
            Map<String, Object> higher) {

        return new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ExportAutoConfiguration.class))
                .withInitializer(context -> {
                    var sources = context.getEnvironment().getPropertySources();
                    sources.addLast(
                            new MapPropertySource("simulatedConfigFile", lower));
                    sources.addFirst(
                            new MapPropertySource("simulatedDeployment", higher));
                });
    }

    @Test
    void higherSourceEnablesAndOverridesFormat() {
        withSources(
                Map.<String, Object>of(ENABLED, "false", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "true", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("json");
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("true");
                });
    }

    @Test
    void higherFalseDisablesLowerTrue() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "false", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("false");
                });
    }

    @Test
    void lowerValueIsUsedWhenHigherOmitsKey() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of())
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("csv");
                });
    }

    @Test
    void higherOnlyEnablesWhileFormatComesFromLower() {
        withSources(
                Map.<String, Object>of(ENABLED, "false", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "true"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("csv");
                });
    }

    @Test
    void missingFlagKeepsFeatureDisabled() {
        withSources(
                Map.<String, Object>of(FORMAT, "csv"),
                Map.<String, Object>of(FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isNull();
                });
    }

    @Test
    void invalidHighPriorityFlagDoesNotFallBackToTrue() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "truue", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("truue");
                });
    }

    @Test
    void higherOnlyOverridesFormatAndKeepsLowerEnabled() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(FORMAT, "json"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("json");
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("true");
                });
    }
}
```

Run in `property-priority-demo` with JDK 17+ and Maven:

```bash
mvn test
```

When the build environment has all dependencies, the expected result is **7 tests PASS, 0 failures, 0 errors**. If the project has only the test file above, Maven Surefire typically reports 7 tests total; exact logs depend on Maven and plugin versions.

How to read the tests:

1. `simulatedConfigFile` is added with `addLast`: simulates a lower source, losing to values at the front of the list.
2. `simulatedDeployment` is added with `addFirst`: simulates a higher source, winning whenever both contain a key.
3. Each `withSources(...).run(...)` creates an isolated context. No earlier test leaks beans into a later test.
4. `AutoConfigurations.of(ExportAutoConfiguration.class)` loads the auto-config under test into the runner; `@ConditionalOnProperty` reads Environment containing both sources.
5. For `format`, `@ConfigurationProperties` uses the Binder to read the effective value, so `ExportClient` receives `csv` or `json` per scenario.
6. The `truue` flag test proves an invalid value in a higher source still **shadows** `true` in a lower source. The condition must not "fall back" to the lower value.
7. The test setting only `format` in the higher source while `enabled` comes from the lower source proves precedence applies **per key**.

### 7.7. Try Another Case Yourself

Change the `higherFalseDisablesLowerTrue` scenario to:

```java
withSources(
    Map.<String, Object>of(
        "acme.export.enabled", "true",
        "acme.export.format", "csv"),
    Map.<String, Object>of(
        "acme.export.enabled", "TRUE"))
```

Predicted result: the bean is created with format `csv`. `havingValue="true"` compares case-insensitively, while `format` is absent from the higher source so it comes from the lower source. This is a **suggested test input swap**, not a standalone Java method.

## 8. Real-World Config Example: Application Overrides Library

In an application using the library, the main file might say:

**`src/main/resources/application.yml`:**

```yaml
acme:
  export:
    enabled: false
    format: csv
```

**`application-prod.yml`** (when the `prod` profile is active and the file is loaded):

```yaml
acme:
  export:
    enabled: true
    format: json
```

Under normal conditions with both files in the same location and active profile `prod`, the effective values are `enabled=true` and `format=json`, so auto-config can create `ExportClient("json")`.

If the operator runs:

```bash
java -jar app.jar --spring.profiles.active=prod --acme.export.enabled=false
```

then the command-line property `enabled=false` outranks config data, disabling the feature; this holds even though `application-prod.yml` says `true`, assuming the application uses default `SpringApplication` and no higher-precedence custom source exists.

Or using:

```bash
java -Dacme.export.format=csv -jar app.jar --spring.profiles.active=prod
```

then the system property `format=csv` overrides `json` from the profile file, while `enabled=true` from the profile remains; the result can be `ExportClient("csv")`.

The CLI examples above are **deployment scenarios** requiring a built `app.jar` of a real Spring Boot application; they are not commands to run the Maven test project from section 7 directly. Do not confuse a standalone auto-config library project with an executable Spring Boot app.

### 8.1. Java Defaults Differ from Lower Sources in Environment

If you remove all `acme.export.format` keys from Environment, this lesson's `ExportProperties` has `format="csv"`, so the Binder keeps that Java default. Yet `Environment.getProperty("acme.export.format")` can return `null` because **object defaults do not become a PropertySource**.

Similarly, when `enabled` is absent, even if another properties object has a field `enabled=true`, `@ConditionalOnProperty(matchIfMissing=false)` still treats the missing-key condition as not matching. Test consistency between **the missing-key policy** and **Java object defaults** whenever a library declares both.

### 8.2. `@Value` and Canonical Key Names

When you must use `@Value`, prefer referencing keys in canonical lowercase kebab-case, such as `acme.export.batch-size`. Canonical naming helps Spring Boot resolve more relaxed-binding variants in property placeholders. For multiple structured properties, `@ConfigurationProperties` is usually clearer and supports metadata and validation better.

When using env vars, check naming rules: `acme.export.enabled` can be supplied by `ACME_EXPORT_ENABLED`. When properties contain dashes, the standard rule for converting to an env var is **drop dashes**, replace dots with underscores, and uppercase. Do not arbitrarily insert underscores everywhere assuming Spring will always recognize it.

## 9. How to Find Which Source Is Winning in a Real Application

When a feature unexpectedly enables or disables, locate **both the effective value and the source causing it**.

### 9.1. Initial Inspection Steps

1. Identify the full key name, e.g., `acme.export.enabled`, and the value auto-config expects.
2. Check `Environment.getProperty("acme.export.enabled")`: that value is the critical input to the condition.
3. List the sources present in `ConfigurableEnvironment.getPropertySources()` in their exact runtime order.
4. Check whether `--acme.export.enabled=...`, `-Dacme.export.enabled=...`, `ACME_EXPORT_ENABLED`, or a profile/config import file overrides it.
5. View Spring Boot's **Condition Evaluation Report** with `--debug`; if Spring Boot Actuator is present and accessible, `/actuator/conditions` shows why auto-configs/bean conditions matched or did not match.
6. If you need to inspect bound config, Actuator `/actuator/configprops` can help; `/actuator/env` can show sources and effective values depending on permissions, endpoint config, and sanitization. Never put secrets into logs.

### 9.2. Inspecting Property Sources in Code

A diagnostic snippet you can run in an application that has `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void inspect(
            ConfigurableEnvironment environment, String key) {

        System.out.println("effective=" + environment.getProperty(key));
        for (PropertySource<?> source : environment.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println("source=" + source.getName());
            }
        }
    }
}
```

This is a runnable Java class when invoked from an application with a Spring `Environment`, **not a standalone program with `main`**. It prints only source names to reduce the risk of accidentally logging sensitive config; for a key like `enabled`, printing the effective value is usually non-sensitive. Composite PropertySources created by Spring Boot/Binder can appear in the list, so understand source names, wrapper structures, and origin when tracing deeper; never assume the first source holding a property corresponds one-to-one with a file path on disk.

To identify exact source files/lines in config data, rely on Spring Boot's origin tracking or reports from appropriate endpoints. For sensitive data, preserve Actuator's hiding/sanitization policies.

### 9.3. Watch Out for Nulls, Empty Strings, and Placeholders

- **Omitted key**: Environment may return `null`; `@ConditionalOnProperty(matchIfMissing=false)` does not match.
- **Empty value declared**: counts as a present value in many PropertySource formats; with `havingValue="true"`, it does not match.
- **Value `false`**: is a valid value and shadows `true` from lower sources.
- **`SPRING_APPLICATION_JSON` containing null**: Spring Boot 3.3 records null values per JSON semantics, yet resolvers may treat null as an absent value, so null **is not guaranteed** to override a lower source.
- **Placeholders**: if config references another key, the resolved value can depend on remaining config sources; use canonical keys to avoid mismatches.

Write tests for these cases whenever a library requires a strict configuration contract.

## 10. Common Mistakes When Testing Source Precedence

| Symptom | Wrong assumption | How to check/fix |
|---|---|---|
| `application.yml` has `enabled=true` yet no bean is created | Assuming the file is the final source | Check system properties, env vars, CLI, profiles, imports, and other conditions |
| Higher source has `false` yet expecting fallback to `true` | Assuming only `true` values are "effective" | Precedence is based on **key presence**, not condition matching |
| `format` from lower file disappears when higher source declares only `enabled` | Assuming whole-object override | Check each key separately; `format` normally still comes from the lower source |
| Tests pass on laptop yet fail in CI | Different env/system property sources across environments | Isolate tests using a runner with explicitly ordered PropertySources |
| Changing `@AutoConfiguration(after=...)` to fix a wrong property value | Confusing auto-config ordering with property sources | Check `Environment.getProperty(...)` and `PropertySources` |
| Adding Java default `enabled=true` and expecting conditional bean when key is missing | Confusing object defaults with Environment | Set explicit `matchIfMissing` policy or provide defaults via an appropriate source |
| `enabled=truue` yet expecting startup to fail | Condition merely fails to match; it does not necessarily validate all input | Add dedicated validation/conditions if invalid config must error |
| CLI test has inputs that do not affect conditions | App customized away CLI properties or `ApplicationContextRunner` test does not parse CLI | Check how tests supply PropertySources and the real startup path |
| User bean exists so assuming the flag has no effect | `@ConditionalOnMissingBean` can make the default bean back off | Check both the property condition and the bean condition |
| Using a late `@PropertySource` to change `spring.main.*` | Source added at refresh may be too late for bootstrap properties | Set bootstrap options via an earlier-processed source |

If an auto-configuration has multiple conditions, merely confirming the property value is right **is not enough** to guarantee the bean appears. You must also check the classpath, existing beans, auto-config ordering, and dependency instantiation where relevant.

## 11. Quick Check Exercises

### Exercise 1: System Property Beats Environment

Suppose `ACME_EXPORT_ENABLED=true` is in the OS environment, while the JVM starts with `-Dacme.export.enabled=false`. No CLI or higher source exists. Does `@ConditionalOnProperty(havingValue="true")` match?

**Answer:** No. In default Spring Boot 3.3, system properties outrank OS environment variables; the key's effective value is `false`.

### Exercise 2: Per-Key Resolution

The lower source has `enabled=true, format=csv`; the higher source has only `format=json`. Is the bean created, and which format does it use?

**Answer:** The bean can be created because `enabled` from the lower source is still `true`. The final format is `json` from the higher source.

### Exercise 3: High-Priority Invalid Value

The lower source sets `enabled=true`; the higher source sets `enabled=treu`. Should the bean be returned?

**Answer:** With `havingValue="true"`, it does not match. The resolver does not fall back to `true` in the lower source merely because the higher-priority value was mistyped. To report clear errors on invalid config, additional validation is required.

### Exercise 4: Profiles and Command Line

`application-prod.yml` has `enabled=true`, the `prod` profile is active, and the command line passes `--acme.export.enabled=false`. Final value?

**Answer:** `false` under default `SpringApplication`, because CLI outranks config data.

### Exercise 5: User Bean Exists While Feature Flag Is On

`@ConditionalOnProperty(... havingValue="true")` matches; however, the application already registered a suitable `ExportClient`, and auto-config has `@ConditionalOnMissingBean(ExportClient.class)`. Is the library's default bean created?

**Answer:** No. The flag permits the feature, but the missing-bean condition makes the library yield to the application-provided bean. This is a **bean rule**, not a higher-priority config source.

### Exercise 6: Object Default

`ExportProperties.format` initializes to `"csv"`; the entire Environment lacks `acme.export.format`. Is `Environment.getProperty("acme.export.format")` guaranteed to return `"csv"`?

**Answer:** No. Java default values on objects do not create a PropertySource. The Binder can keep `"csv"` on the object while Environment still lacks the key.

## 12. Summary of Practical Rules

- **Configuration sources** determine the effective value of each key; a higher-precedence source containing the key beats lower sources under active rules.
- In standard Spring Boot 3.3, **command line** outranks system properties, OS environment, and config data; **test property sources** and custom sources can change order within their scope.
- Auto-configuration uses the **prepared Environment** to evaluate `@ConditionalOnProperty`; `@ConfigurationProperties` binds individual keys into objects without granting libraries special precedence.
- Design starters with **a dedicated namespace, clear defaults, and an explicit enable flag**, while allowing applications/deployments to override via Spring Boot's mechanism.
- Test **bean presence/absence**, **final bound values**, **missing/typo scenarios**, **source conflicts**, and **user-supplied replacement beans**.
- When outcomes defy expectations, inspect **PropertySources in actual order**, `Environment.getProperty(...)`, and the Condition Evaluation Report—never guess from a single `application.yml` file.

### Official Documentation

- [Spring Boot 3.3 — Externalized Configuration and PropertySource Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
