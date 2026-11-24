# Using spring-boot-properties-migrator When Upgrading Boot-Managed Properties

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Design and Evolution

## 1. The Problem: The App Still Compiles, Yet Configuration Meaning Changed

Upgrading a Spring Boot application is more than bumping a version number in Maven or Gradle. A new Spring Boot release can **rename, deprecate, relocate, or remove configuration properties** that the previous version accepted.

For example, a project has:

~~~properties
spring.kafka.retry.topic.delay=2s
~~~

In newer Spring Boot versions that document the corresponding change in the deprecated application properties list, the recommended key may move to:

~~~properties
spring.kafka.retry.topic.backoff.delay=2s
~~~

These two snippets illustrate a rename listed in Spring Boot 4.2 documentation; do not apply that replacement across every Boot version or application without verifying your dependencies and active features.

A typical scenario:

1. The application runs well on the older version.
2. The team upgrades Spring Boot or a related starter.
3. The build still succeeds because YAML/properties are plain text data.
4. Certain old keys are no longer recognized by their consumers, or are still accepted while deprecated.
5. The application starts with **different defaults**, ignores configuration thought to be active, or changes runtime behavior unexpectedly.

This is a dangerous failure mode: **there is no compile error**. A wrong or removed key can sit quietly in application configuration files without alerting developers.

Spring Boot provides the **`spring-boot-properties-migrator`** module to assist during upgrades. When added temporarily to the runtime classpath, the module can:

- Analyze effective configuration properties in `Environment` at startup.
- Detect properties that were renamed, deprecated, or are no longer supported according to the Boot version's metadata.
- Print diagnostic information so upgraders can fix configuration sources.
- **Temporarily migrate supported properties at runtime** to help the application transition while configs are being updated.

This tool is a **temporary bridge**, not a permanent compatibility layer, and cannot replace migration guides, release notes, functional testing, or actively updating real configurations.

### Learning Objectives

After this lesson, you will be able to:

1. Explain why changing Boot versions can break configuration without causing compile errors.
2. Distinguish **renamed**, **deprecated**, **removed** properties, and semantics changes.
3. Add `spring-boot-properties-migrator` with the proper dependency scope in Maven/Gradle.
4. Start the application with representative profiles and config sources to inspect diagnostics.
5. Turn warnings into actionable edits across YAML, properties, environment variables, CLI, and deployment manifests.
6. Understand the migrator's timing limits, especially regarding late-added `@PropertySource` entries.
7. Resolve conflicts when old and new keys coexist across sources with different precedence.
8. Verify real behavior with tests rather than assuming "migrator ran cleanly" suffices.
9. Use version-supported failure modes where available to catch remaining migrations.
10. Remove the migrator module once finished and verify the final artifact no longer depends on temporary migration.

## 2. Four Types of Configuration Changes to Recognize

### 2.1. Renamed Property — Key Name or Group Changed

An old key is replaced by a new key, sometimes changing prefix hierarchy too:

~~~text
Old name: spring.kafka.retry.topic.delay
New name: spring.kafka.retry.topic.backoff.delay
~~~

This example can be verified in Spring Boot 4.2's deprecated properties appendix. When upgrading to such a version, check whether the old key remains temporarily supported, has replacement metadata, and whether the migrator suggests converting it.

**Do not rename in just one file**: the same key may appear in ConfigMaps, environment variables, startup commands, Helm values, and profile-specific files.

### 2.2. Deprecated Property — Still Present, Should Not Continue Being Used

A property may be marked no longer recommended. It may still work in the current release yet is scheduled for removal in a later version.

That does **not** mean you may keep it forever because "it still works." In the next upgrade, compatibility can vanish.

In current Spring Boot docs, some properties are marked deprecated without a simple one-to-one replacement. Read `reason`, `replacement`, and the migration guide rather than applying a blanket rule.

### 2.3. Removed Property — No Longer Supported

When a property is removed outright, do not assume a direct equivalent key exists. The feature may be gone, redesigned, or require code changes.

For instance, diagnostics may report "no longer supported" rather than "renamed to X." In that case, consult release notes or API docs for the new capability. Never invent a replacement name just to silence warnings.

### 2.4. Behavior/Semantics Change — A New Name Alone Is Not Enough

Some changes turn a boolean into an enum or change value semantics. For example, deprecation lists in some Spring Boot releases replace an **enabled** property with a **mode** property. Copying `true` or `false` verbatim onto the new key may fail type checks or change meaning.

Conceptual diagram:

~~~text
old.feature.enabled=true
           |
           v
new.feature.mode=<appropriate enum value>
~~~

The keys `old.feature.*` and `new.feature.*` above **are hypothetical examples for illustration**, not real Spring Boot properties. Choose the new value only after understanding the concrete configuration contract.

For semantic changes, the migrator helps flag them yet **cannot make business decisions for you** or refactor changed Java code and dependencies.

## 3. What Is `spring-boot-properties-migrator`?

Maven/Gradle coordinates:

~~~text
org.springframework.boot:spring-boot-properties-migrator
~~~

This is an official Spring Boot module for migrating configuration properties. It differs from:

- `spring-boot-configuration-processor`: generates configuration metadata for IDEs and build tooling.
- `spring-boot-starter-validation`: provides Bean Validation for typed configuration values.
- `@ConfigurationProperties`: binds properties from `Environment` into Java objects.
- `spring.config.import`: brings additional Config Data into `Environment` construction.
- Database migration tools like Flyway/Liquibase: evolve database schemas, **not** configuration property keys.

The migrator focuses on **configuration-property migration during Spring Boot upgrades**.

### 3.1. When Does It Detect Issues?

The module analyzes `Environment` during Boot's integrated startup phase. Property sources prepared early enough are inspected. It logs diagnostics at startup and, where metadata permits, can temporarily translate properties at runtime.

Crucial point: **this is not a linter scanning your entire repository**. It does not inspect Git, Helm charts, all values files, all manifests, or production-only configs on its own. It observes **only the properties present in `Environment` for that specific startup run**, within Boot's supported lifecycle.

Running only with the `dev` profile does not prove `prod` configs are clean.

### 3.2. It Does Not Modify Source Files

Even when the migrator reports a key was temporarily migrated, the contents of `application.yml`, `application.properties`, Kubernetes ConfigMaps, or environment variables remain unchanged.

Nothing magically rewrites your source or deployment configs. Engineers must open the real sources and replace keys intentionally.

### 3.3. Why Is Runtime Migration Only Temporary?

Leaving this module installed permanently creates problems:

- A subsequent upgrade drops compatibility support.
- Diagnostics get ignored because the app still "boots."
- Dev and production use different sources while only one was tested.
- Runtime carries behavior diverging from the final configuration contract.
- A successful key rename masks an underlying semantic change.

Official Spring Boot documentation instructs you to **remove the dependency once migration is complete**.

## 4. Preparing Before Enabling the Migrator

Do not start by pushing the dependency to production without knowing what you are upgrading from and to.

### 4.1. Lock Down Source and Target Versions

Example:

~~~text
From: Spring Boot 3.x
To:   Spring Boot 4.x
~~~

This is just an example. Upgrading from `3.3` to `3.5`, `3.x` to `4.x`, or between minor versions involves different property change lists.

Before running:

1. Confirm the current Spring Boot version.
2. Pick the exact target version.
3. Read release notes and migration guides for all intermediate steps.
4. Check JDK, Spring Framework, and starter versions to upgrade.
5. Identify config sources per environment.
6. Prepare tests and rollback plans.

Do not read the latest version's deprecated properties page and assume it explains every behavior of an older Boot app.

### 4.2. Inventory Where Old Keys Can Live

| Source | Example | Where to Fix |
| --- | --- | --- |
| Default config inside JAR | `src/main/resources/application.yml` | Project source |
| Profile-specific file | `application-prod.yml` | Source/config repository |
| External config | `./config/application.properties` | Infrastructure or mounted file |
| Config Data import | `spring.config.import=...` | Imported file and its source |
| OS environment | `SPRING_KAFKA_RETRY_TOPIC_DELAY` per binding rules | Deployment env / CI |
| Java system property | `-Dspring.kafka.retry.topic.delay=2s` | Startup script / JVM options |
| Command line | `--spring.kafka.retry.topic.delay=2s` | Process args |
| Kubernetes ConfigMap | Keys or file contents | ConfigMap/Helm/GitOps |
| Test configuration | `@SpringBootTest(properties=...)` | Test code |
| Test resources | `application-test.yml` | Test configuration |
| Docker Compose/CI | `environment:` or startup flags | Compose/pipeline |
| Third-party secret/config manager | Per-environment key/values | Store and sync config |

Derive environment variable names using relaxed-binding rules for the **real** keys and Boot version in use. Never infer every deployed env variable blindly from an example table.

### 4.3. Avoid Changing Too Many Things at Once

An upgrade can simultaneously touch the JDK, Boot, framework, Jackson, Servlet APIs, starters, and configuration properties. Changing multiple config sources and business logic at the same time makes test failures hard to diagnose.

Best practice is maintaining a **before/after baseline**, breaking edits into reviewable steps, and running regression tests at each stage.

## 5. Installing the Migrator with Maven

In the Spring Boot application module's `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

If the project uses the Spring Boot parent or BOM, the dependency version is normally managed automatically. Without dependency management, specify a version matching the target Spring Boot release in your build config.

### 5.1. Why Use `runtime` Scope?

The migrator runs at application startup. It is not a business-code API imported in Java sources. `runtime` clarifies it is a runtime helper rather than a compile-time dependency.

### 5.2. Which Module Needs It?

In multi-module projects, add it to the runtime classpath **of the application that actually boots**. Adding it solely to a library module not packaged into the executable app means it will be absent when the service JVM runs.

Do not add the migrator indiscriminately to shared libraries for permanent release. Normally add it to the app module or wherever the upgraded executable artifact's runtime dependencies are managed.

### 5.3. Do Not Confuse with the Annotation Processor

Different dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

The processor generates metadata for IDEs; the migrator diagnoses and migrates properties at runtime. Both share similar names under the same group ID yet **serve completely different purposes**.

## 6. Installing the Migrator with Gradle

Gradle Groovy DSL:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
}
~~~

`runtimeOnly` emphasizes that the migrator is not an API called by business Java code. With Spring Boot's plugin/dependency management, you do not need to hardcode a version in the snippet; if managing versions manually, match the target release.

### 6.1. Do Not Add Only `testImplementation`

Placing the module only in test scope without putting it on the application's runtime classpath during upgrade trials means test runs may differ from the target runtime.

Conversely, if keeping the migrator in a test/staging packaging setup, verify how it lands on the runtime classpath of the **analyzed run**. The goal is inspecting an instance actually booting with the module present.

### 6.2. Do Not Commit as a Permanent Dependency

During an upgrade, a pull request may temporarily add the migrator for diagnostics. Once all keys are fixed, follow up with a commit/PR **removing the dependency**, running tests, and verifying the final artifact no longer includes it.

A migration task is complete only when the application runs properly without needing this bridge.

## 7. Core Workflow: Add, Run, Read, Fix, Rerun, Remove

Workflow diagram:

~~~text
Choose target Spring Boot version
               |
               v
Add spring-boot-properties-migrator
               |
               v
Start with test environment config
               |
               v
Read diagnostics from startup logs
               |
               v
Classify renamed / deprecated / removed
               |
               v
Fix files, env, CLI, config imports, manifests
               |
               v
Rerun with proper profiles and sources
               |
               v
Regression tests + behavior verification
               |
               v
Remove spring-boot-properties-migrator
               |
               v
Rerun startup & tests WITHOUT migrator
               |
               v
Deploy with monitoring and rollback
~~~

### 7.1. The First Run Must Represent Real Configuration

If the service normally starts with:

~~~bash
java -jar catalog-service.jar \
  --spring.profiles.active=staging
~~~

run a verification pass with `staging` and sources simulating real deployment conditions. You do not need production secrets just to check property names; use valid test credentials and test endpoints.

Starting with no profile may touch only the default file and miss all of `application-prod.yml` or production-only imported configs.

### 7.2. Read Full Logs, Not Just the "Started" Line

The migrator logs diagnostics during startup. A run may still report "Started ..." at the end after printing a list of properties needing fixes earlier in the log.

Do not check exit code 0 alone and assume zero config debt remains. Search logs for unsupported/renamed/deprecated property notices and record every one.

### 7.3. Fix Real Sources, Not Temporary Effective Values

When the migrator inserts a replacement at runtime, `Environment` reading the new key does not mean files were updated. Update the **real inputs** and confirm which source supplies the key on the next run without the migrator.

## 8. Hands-On Example with a Renamed Boot Property

**Illustrative context from Spring Boot 4.2's deprecation list**: several Kafka retry-topic properties moved under a `backoff` group.

Before:

~~~properties
spring.kafka.retry.topic.delay=2s
spring.kafka.retry.topic.max-delay=20s
spring.kafka.retry.topic.multiplier=2
~~~

Replacements listed in the corresponding documentation:

~~~properties
spring.kafka.retry.topic.backoff.delay=2s
spring.kafka.retry.topic.backoff.max-delay=20s
spring.kafka.retry.topic.backoff.multiplier=2
~~~

### 8.1. Why Include Version Context in the Example?

No single mapping applies across all Boot releases. Upgrading Boot 2.x to Boot 3.x has a different rename list. Always read the **target version's** appendix instead of copying an example as a universal recipe.

### 8.2. What If the App Does Not Use Kafka?

If the project has no Kafka retry-topic integration or disables that feature, the example keys may not apply. Do not add these properties just to "test the migrator" on an app without Kafka.

To practice, create a small sample app with the right version and starter, and test properties actually belonging to that module.

### 8.3. Updating YAML with the Same Mapping

Before:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        delay: 2s
        max-delay: 20s
        multiplier: 2
~~~

After:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 2s
          max-delay: 20s
          multiplier: 2
~~~

Note that in YAML, changing a key prefix can require restructuring **nested objects**, not just find-and-replace on a dotted string.

### 8.4. Verify Behavior After the Change

Do not stop at checking YAML contains the new names. Run an appropriate test proving the retry/backoff settings actually apply to the live component or bean—even after removing the migrator.

For numbers or `Duration`, verify conversion and units. A typo like `max-deley` can silently fall back to defaults without an immediate error.

## 9. Reading Diagnostics as an Actionable Backlog

An illustrative diagnostic snippet, **not a verbatim copy of a specific Spring Boot version**:

~~~text
Migration diagnostics
  Property: spring.kafka.retry.topic.delay
  Status: renamed/deprecated
  Suggested replacement:
    spring.kafka.retry.topic.backoff.delay
  Source: application.yml
~~~

Actual formatting, log levels, and source info vary by Boot version, metadata, and `PropertySource` type. Never write scripts tightly coupled to exact whitespace or phrasing from an example.

### 9.1. Action Table Built from Diagnostics

| Field to Record | Question | Example |
| --- | --- | --- |
| Old property | Which key was flagged? | `spring.kafka.retry.topic.delay` |
| Status | Renamed, deprecated, removed? | Renamed |
| Replacement | Is a new property specified? | `spring.kafka.retry.topic.backoff.delay` |
| Source | Where did the value come from? | `application-staging.yml` |
| Profile | Is the file/document active? | `staging` |
| Value | Do type or units need conversion? | `2s` |
| Owner | Which team manages this source? | Platform/Messaging |
| Test | What test proves correct behavior? | Retry policy integration test |
| Status | Updated across every environment? | Staging done, prod pending |

### 9.2. Triage by Risk Level

- **Pure rename:** usually fix the key first and run binding/functional tests.
- **Rename with type change:** read semantic details before changing values.
- **Removed, no replacement:** may require architecture changes or dropping a feature.
- **No diagnostics yet wrong behavior:** still inspect the migration guide, code, and inactive keys.

The migrator is an important signal, not full proof that the entire migration is done.

## 10. Relationship to Spring Boot Configuration Metadata

Spring Boot defines a JSON metadata structure describing configuration properties:

~~~text
META-INF/spring-configuration-metadata.json
~~~

A property can carry `deprecation` info such as `reason` or `replacement` in the metadata schema.

Illustrative structure:

~~~json
{
  "properties": [
    {
      "name": "example.old-timeout",
      "type": "java.time.Duration",
      "deprecation": {
        "level": "warning",
        "reason": "Old property name will be removed.",
        "replacement": "example.client.timeout"
      }
    }
  ]
}
~~~

**`example.*` here is purely a hypothetical key illustrating the schema**, not a Spring Boot key. Do not conclude that adding such metadata guarantees the migrator will provide runtime compatibility for arbitrary custom properties.

### 10.1. Deprecated Metadata Differs from Binding Semantics

Metadata tells tools about old keys and recommended replacements. Yet the application still needs consumers that actually support the new key, and old numeric/string values may not map equivalently.

Never treat a replacement string as proof data converts safely in all cases.

### 10.2. The Compiler Does Not Check YAML Keys

`application.yml` and `application.properties` are parsed at runtime. Compiling Java cleanly does not prove every key exists, matches the version, or is supported by the active starters.

That is why the migrator is so practical during upgrades: it bridges the gap between **dependency upgrades** and **configuration contract changes**.

### 10.3. The Migrator Is Not the Configuration Processor

`spring-boot-configuration-processor` generates metadata from `@ConfigurationProperties` classes, mainly for IDEs. `spring-boot-properties-migrator` runs inside the application to inspect and temporarily migrate config properties.

Do not add the annotation processor expecting runtime migration diagnostics.

## 11. PropertySource Precedence When Both Keys Coexist

Suppose you have two sources:

~~~yaml
# application.yml
spring:
  kafka:
    retry:
      topic:
        delay: 2s
~~~

And an externalized file updated for the new version:

~~~yaml
# ./config/application.yml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 5s
~~~

You now have **old key** and **new key** holding two different values.

"What is the final value?" cannot be answered merely by "external file beats packaged file", because runtime property translation and conflict handling also come into play.

**Safe migration rule:** avoid having old and new keys for the same setting active simultaneously across effective sources. Update every relevant source and verify the final value with tests after removing the migrator.

### 11.1. PropertySource Precedence Remains Part of the Picture

Spring Boot layers sources such as:

- Packaged Config Data inside the JAR.
- External Config Data outside the JAR.
- Imported Config Data.
- Profile-specific configs.
- OS environment variables.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Test property sources.

A higher-precedence source overrides values with the same key. When **renaming a key**, old and new names do not even match during initial lookups.

When using the migrator, inspect diagnostics and measure actual binding. Never assume "old always wins" or "new always wins" across all versions and conflict scenarios.

### 11.2. Avoiding Conflicts

1. List every source where the old key appears.
2. Decide the canonical post-upgrade value.
3. Replace the old key with the new key across all team-managed sources.
4. Remove obsolete overrides instead of merely layering new overrides on top.
5. Run with the migrator to catch stragglers.
6. Remove the migrator and verify the final value in a deployment-equivalent environment.

### 11.3. Example: CLI Can Override an Updated File

The YAML file already switched to the new key:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 5s
~~~

Yet the startup script still passes:

~~~bash
java -jar app.jar \
  --spring.kafka.retry.topic.delay=2s
~~~

Migration is incomplete in **startup arguments**. Update the launch script or CI/CD release job, not just YAML sources.

## 12. Profiles and Multi-Document Files: One Run Cannot Scan All Environments

A multi-document `application.yml`:

~~~yaml
app:
  deployment:
    label: "default"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  deployment:
    label: "production"
~~~

During Config Data loading, Spring Boot decides which documents are active based on profiles and conditions. Keys in inactive documents may **never enter `Environment`** for that run.

If an old key sits only in `application-prod.yml`, running with `dev` reports nothing.

### 12.1. Profile Verification Matrix

| Scenario | Goal |
| --- | --- |
| No explicit profile | Check default Config Data |
| `dev` | Check development documents |
| `test` | Check test-specific sources |
| `staging` | Check staging-equivalent manifests |
| `prod` in a safe test sandbox | Detect keys in production configs |
| Multiple active profiles together | Check ordering and overrides |
| Environment-specific config imports | Check keys from imported resources |

Never use real production secrets just to boot a test instance looking for old keys. Simulate the config using valid placeholders while noting any differences from production.

### 12.2. Cloud-Platform-Activated Documents

A Config Data document may activate only under a specific cloud platform condition. Running locally on a laptop with the same `spring.profiles.active` may not load Kubernetes-specific documents.

Therefore, pair **startup diagnostics** with **static searches across manifests and config repositories**; neither replaces the other.

## 13. Important Limitation: Late-Added `@PropertySource`

Spring Boot documentation explicitly notes that properties **added late to `Environment`**, such as via `@PropertySource`, **are not taken into account by the migrator**.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-boot-options.properties")
public class LegacyBootOptionsConfig {}
~~~

File:

~~~properties
# Example old key from a release the team is upgrading from.
spring.kafka.retry.topic.delay=2s
~~~

Because `@PropertySource` may be processed only during `ApplicationContext` refresh, the migrator has often already executed before that source is added. Never treat "no warnings logged" as proof that the file contains no old keys.

### 13.1. Why Timing Matters

A simplified lifecycle model:

~~~text
SpringApplication starts
          |
          v
Build/prepare Environment
  - OS env
  - system properties
  - command-line
  - Config Data and imports
          |
          v
Properties migrator analyzes available sources
          |
          v
ApplicationContext refresh
          |
          v
@Configuration processing
  - @PropertySource might be added here
          |
          v
Beans initialized
~~~

This diagram is conceptual and does not replace exact lifecycle hooks in every version. The key takeaway is that **the migrator cannot inspect sources added after its analysis phase**.

### 13.2. Handling Late-Added Sources

- Inspect `legacy-boot-options.properties` directly.
- Decide whether `@PropertySource` is truly needed for Boot-managed keys.
- If the file contains standard Boot config, consider moving it into Config Data or an import.
- Do not switch loaders abruptly just to expose keys to the migrator without verifying precedence and load timing.
- For custom configuration logic, write tests or static checks to catch unsupported keys.

### 13.3. Some Properties Must Be Supplied Very Early

Properties like `logging.*`, `spring.main.*`, and keys controlling Config Data locations are read by Spring Boot very early. Putting them in `@PropertySource` can already be too late for the desired effect, with or without the migrator.

The migrator does not turn a late-added source into a bootstrap property source.

## 14. Do Not Confuse Old-Key Detection with Behavior Testing

Suppose diagnostics show zero warnings. The application can still misbehave because:

- The new key has a different data type.
- Defaults changed.
- Auto-configuration was redesigned.
- An older starter was replaced or dropped from the classpath.
- A previously boolean option became a policy enum.
- The old key existed only in a source inactive during the test run.
- The test setup lacked the relevant dependency, so the property was never read as assumed.
- The client bean was built with a different value from a higher-precedence source.

Therefore, verify four layers together:

1. **Configuration diagnostics**: any old keys left?
2. **Binding**: what values did the final config bean receive?
3. **Behavior**: does the feature depending on that config work properly?
4. **Deployment**: do all instances and profiles share the updated contract?

## 15. Example: Testing Typed Configuration After Migration

Suppose an app has custom config for a client, and upgrading Boot changed how the client is constructed. Even for custom keys outside the migrator's scope, verify typed config:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        int maxAttempts
) {}
~~~

Test with `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsExpectedValues() {
        runner.withPropertyValues(
                "catalog.client.timeout=5s",
                "catalog.client.max-attempts=3"
        ).run(context -> {
            var config = context.getBean(
                    CatalogClientProperties.class);

            assertThat(config.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(config.maxAttempts()).isEqualTo(3);
        });
    }
}
~~~

This example **does not directly test the migrator** because `catalog.client.*` is a custom prefix. It illustrates a regression test worth having during configuration upgrades: after selecting property sources, Binder produces the expected typed object.

### 15.1. Testing Boot-Managed Auto-Configuration

For properties managed by a Spring Boot starter, regression tests should instantiate the actual bean and verify the configuration took effect. For example, if an HTTP client timeout property changed, an integration test should verify the Boot-created HTTP client uses the intended timeout/policy rather than merely asserting `Environment` holds a text value.

### 15.2. Testing Without the Migrator

While the dependency remains present, the app may keep working via the runtime migration bridge. Passing tests **with the migrator on the classpath** do not prove old keys are completely gone.

After updating sources, remove the dependency and run at least one startup and functional test against the final artifact. That catches remaining reliance on the temporary bridge.

## 16. Using the Fail Option When the Migrator Detects Issues

In Spring Boot 4.2, the upgrading documentation describes the property:

~~~properties
spring.properties.migrator.fail=on-warning
~~~

Options documented for that version:

| Value | Meaning |
| --- | --- |
| `never` | Do not fail startup on migration warnings/errors; documented default |
| `on-error` | Fail startup when an unsupported property is present |
| `on-warning` | Fail when a renamed or unsupported property is present |

Diagnostics are still logged regardless of the fail setting.

**Version note:** this is documented for **Spring Boot 4.2**, not a claim that `spring.properties.migrator.fail` exists or behaves identically in all 2.x, 3.x, 4.0, or 4.1 releases. Check the docs for the version **your application actually runs** before using it.

### 16.1. When to Enable `on-warning`

For a migration gate in CI or staging, failing on remaining renamed/unsupported properties can be useful where the target version supports it:

~~~properties
# Example applicable only to versions supporting this property.
spring.properties.migrator.fail=on-warning
~~~

Startup failure becomes an automated signal rather than an easily overlooked log warning.

### 16.2. Do Not Treat the Fail Gate as an All-Source Scanner

Even with `on-warning`, the migrator evaluates only properties it actually sees during its phase. Inactive profile files, late-added sources, and undeployed Helm values remain outside its scope.

Thus a fail gate is a helpful safeguard, not a substitute for reviewing config sources.

### 16.3. Do Not Leave the Fail Setting Behind Permanently

Once the migrator is removed from the runtime classpath, its dedicated property no longer enforces migration checks. Leaving it in production after removing the module can mislead operators into thinking deprecated keys are still blocked.

Remove both the dependency and temporary test flags once confirmed unnecessary.

## 17. Maven/Gradle Dependency Management and the Final Artifact

### 17.1. Maven Dependency Tree

After adding the migrator, run in your build environment:

~~~bash
mvn dependency:tree
~~~

to inspect the dependency graph. Maven supports filtering by artifact depending on plugin version, using the syntax matching your plugin.

### 17.2. Gradle `runtimeClasspath`

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Verify `spring-boot-properties-migrator` is present during the upgrade. After removal, rerun to confirm it is absent from the artifact's runtime classpath.

### 17.3. Inspecting the Real JAR

An executable Spring Boot JAR bundles runtime dependencies inside. In complex build pipelines, ensure the final release artifact uses the updated POM/Gradle config and does not pull the migrator back in transitively.

Do not just delete one line and assume deployed artifacts updated themselves. Rebuild the artifact and verify the version/digest being deployed.

### 17.4. Multiple Deployable Modules

If a repository builds multiple services or JARs, each service may have:

- Different target versions.
- Different starters.
- Different profiles and config sources.
- Different release pipelines.

Never claim "the whole monorepo is migrated" just because one module had clean diagnostics. List every application using Boot-managed properties and verify each runtime.

## 18. CI/CD: Turning Migration into Evidence-Backed Work

An upgrade pipeline should have clear stages.

### Stage A — Build on Target Version

Compile, run unit tests, check dependency compatibility, and package the candidate app.

### Stage B — Run Startup Diagnostics with the Migrator

Use a safe test environment representative of each important profile. Capture enough logs to read diagnostics without printing secrets.

### Stage C — Classify and Fix Keys

List old properties, replacements, sources, owners, and tests. Update YAML/properties, ConfigMaps, Helm values, startup args, and test resources.

### Stage D — Retest After Fixes

Rerun with the migrator. If supported by the target version, consider `fail-on-warning` as a migration gate. Also run integration tests proving expected application behavior.

### Stage E — Remove the Migrator

Remove the runtime dependency, rebuild, boot, and rerun tests against the exact final artifact.

### Stage F — Monitored Rollout

Gradually roll out new instances, checking readiness, key metrics, and functional errors. Keep a tested rollback path to the last known good **image + config** pair.

### 18.1. Do Not Search Logs Only for the Word "migrator"

Depending on version and logging config, messages may appear under class/module names or different labels. If pipelines parse logs to enforce migration, pin versions and test the parser. Where an official fail policy exists, prefer it over fragile log-grep scripts.

### 18.2. One Clean Startup Does Not Equal a Safe Upgrade

A service may start cleanly while a rarely used feature has altered semantics. Run business-path smoke and regression tests, not just startup health checks.

## 19. Configuration in Containers, ConfigMaps, and Helm

The migrator runs inside the app, whereas values often come from deployment manifests—especially via env vars.

Hypothetical Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:upgrade-candidate
          env:
            - name: SPRING_KAFKA_RETRY_TOPIC_DELAY
              value: "2s"
~~~

If the target version maps this to `spring.kafka.retry.topic.backoff.delay`, update the env var name to match the new canonical property:

~~~yaml
env:
  - name: SPRING_KAFKA_RETRY_TOPIC_BACKOFF_DELAY
    value: "2s"
~~~

**These two env names illustrate common relaxed-binding conventions**; in real environments, verify mappings for your exact version and source, especially for hyphens, list indices, or special map keys.

### 19.1. Editing Helm Values Does Not Guarantee Live Manifests Changed

A values file may be templated into env vars or ConfigMap files. After editing, render/diff actual manifests or inspect deployed cluster resources per your team's workflow.

Never assume a key is gone just because `grep` in one repo finds nothing; keys may be template-assembled or injected from an external secret/config store.

### 19.2. Rolling Restarts and In-Process Configuration

When a ConfigMap or Secret changes after a Pod is running:

- Container environment variables do not automatically update.
- Volume mounts may eventually reflect updated files, yet already-bound `@ConfigurationProperties` beans do not auto-refresh.
- New Pods usually must be created so startup picks up the updated configuration.

For Boot-upgrade rollouts, creating a new deployment revision cleanly pairs the **new image** with **migrated configuration**.

### 19.3. Never Use the Migrator to Rotate or Expose Secrets

When a property holding a password or token is renamed, update the source key name without exposing its value. The migrator is not a secret manager. Never log raw `Environment` or copy credentials into migration reports.

## 20. Boot-Managed Properties vs Application-Defined Properties

This lesson focuses on properties belonging to Spring Boot auto-configuration and modules for which Boot provides metadata.

Custom property example:

~~~java
@ConfigurationProperties(prefix = "example.payment")
public record PaymentProperties(
        String endpoint,
        Duration timeout
) {}
~~~

If your team renames `example.payment.timeout` to `example.payment.request-timeout`, that is a migration of a **team-owned configuration API**.

Never assume adding `spring-boot-properties-migrator` will automatically detect and translate arbitrary custom keys merely because the class uses `@ConfigurationProperties`.

### 20.1. Migrating Custom Keys

A self-managed transition strategy can include:

- Defining the new field/key.
- Documenting deprecation of the old key.
- Temporarily accepting both names with explicit precedence.
- Logging warnings **without leaking secrets** when the old key is used.
- Writing tests for old-only, new-only, both-present, and invalid values.
- Setting a version/deadline to drop old-key support.

That is the responsibility of the owning app or library's config API, separate from `spring-boot-properties-migrator`.

### 20.2. Third-Party Libraries

External starters outside Spring Boot may handle property deprecations differently or use different tooling. The migrator may not cover all of them, depending on metadata and integration.

Always read the third-party starter's release notes and check runtime behavior rather than expecting one Boot module to cover every classpath dependency.

## 21. Upgrade Changes Beyond Property Warnings

Boot upgrades can also require:

- Updating Java imports/packages when Spring Framework or Jakarta APIs shift.
- Changing starter dependencies or modularized auto-configurations.
- Updating security filter chain APIs.
- Adjusting serialization/Jackson behavior.
- Updating web server or embedded Servlet API compatibility.
- Updating HTTP client factories and timeout properties.
- Reviewing Actuator endpoints and management access policies.

The migrator focuses strictly on configuration properties it recognizes. It does not refactor code, fix dependencies, or preserve behavior across breaking framework API changes.

### 21.1. Never Ignore "Removed Without Replacement"

When a feature is removed, deleting the old key silences startup warnings while quietly losing the prior capability. Identify the replacement design—via code/config refactoring—or confirm removing the capability is intentional.

### 21.2. Type Changes Require Value Checks

New keys may expect enums, `Duration`, `DataSize`, or lists. For an old boolean, never copy `true` onto an enum key without checking docs. Likewise, `500` may imply a different unit when semantics change.

Tests should assert **component effects**, not just raw text in `Environment`.

## 22. Second Example: A Replacement That Changes Meaning

Current Spring Boot deprecated-properties lists include the classic example:

~~~text
spring.main.show-banner
    -> spring.main.banner-mode
~~~

The old property expressed "show banner or not" as a boolean; the new property expresses "banner mode" via distinct options. The values are **not a simple string-to-string copy**.

Example under the new API:

~~~properties
spring.main.banner-mode=off
~~~

This demonstrates **why you must never copy `false` from an old key to a new key without reading the new contract**. Check the migration guide for the exact version and setting.

### 22.1. Property Timing Note

`spring.main.*` is read very early during `SpringApplication` startup. When replacing bootstrap-era keys, placing them in a late source like `@PropertySource` may fail to take effect.

The migrator cannot fix a timing issue merely by remapping key names.

### 22.2. Test Banner Behavior Directly

If migrating to disable the banner in deployment, verify actual startup output with the new file/CLI rather than just checking `Environment` contains `spring.main.banner-mode=off`. A property may be read early before another source loads.

## 23. Do Not Equate Deprecation Warnings with Mandatory Startup Failures

In many versions, the migrator prints diagnostics while letting the application keep running. That is intentional to ease transitions.

However, a warning is still work to resolve because:

- A future version can remove compatibility.
- Some sources are not scanned.
- Runtime translation vanishes when the module is removed.
- Old names confuse future maintainers.

If your Boot version supports `spring.properties.migrator.fail`, configure a CI/staging gate. If your target version lacks that option, review logs or enforce custom checks—never configure a non-existent flag expecting the build to fail.

### 23.1. Warnings Do Not Mean Values Are Wrong

A deprecated property can migrate cleanly and run fine. Yet the goal of migration is **needing no bridge and using zero legacy keys**, not merely getting through startup.

### 23.2. Startup Errors Can Be Unbindable Values

If the new property expects an enum or different type, the app can fail conversion even after the key is right. Read the stack trace and metadata instead of blaming every post-upgrade failure on the migrator.

## 24. Inspecting Effective Sources Without Leaking Secrets

When diagnostics do not pinpoint which source needs editing, inspect `PropertySources` for a **non-sensitive** key.

Example:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
class PropertyOriginProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    PropertyOriginProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "spring.kafka.retry.topic.backoff.delay";

        System.out.println(
                "Effective value: " + environment.getProperty(key)
        );

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Use this snippet only in controlled diagnostics. Never dump the entire `Environment`; credentials may reside in property sources.

A `PropertySource` may lack detailed origin metadata or store keys differently from relaxed binding. `source.getProperty(key)` returning null does not prove Binder could not bind the value from an OS environment variable variant. When unsure, inspect the bound bean and official origin tracking.

### 24.1. Actuator `env` and `configprops`

If Spring Boot Actuator is enabled, `env` or `configprops` endpoints assist diagnosis. Always configure authorization, masking/redaction, and secure access; never expose sensitive endpoints publicly.

### 24.2. Log Key Names Instead of Raw Secrets

When logging migration tracking:

~~~text
Deprecated property detected: example.credential.old-name
Replacement property: example.credential.new-name
~~~

This is safe to consider logging if internal policy permits and values stay hidden. Never log password/token values merely to prove a key is set.

## 25. Upgrading Across Multiple Versions or Skipping Releases

A project might jump from Boot 2.x to 4.x. Deprecated properties may already have been removed in an intermediate release, so the final version's migrator metadata may not cover the entire history.

Strategy:

1. Read migration guides across every relevant major/minor release.
2. Check deprecations in intermediate versions before jumping.
3. When feasible, upgrade in sensible increments keeping regression tests green.
4. Identify features with changed behavior, not just renamed keys.
5. Run each target step's migrator where appropriate.
6. Never rely on "one clean run on the final version" to prove all old configs were caught.

### 25.1. Benefits of Cleaning Up Before a Major Upgrade

If on Boot 3.x preparing for Boot 4.x, a good prep step is:

- Read Boot 3.x's deprecation list.
- Fix deprecated keys while still supported in Boot 3.x.
- Run regression tests.
- Upgrade to Boot 4.x.
- Handle remaining key and behavior changes per the Boot 4.x migration guide.

This shrinks unknowns when crossing a major version boundary.

### 25.2. There Is No Safe Global "Rename All" Across Releases

Bulk string replacement can accidentally edit comments, docs, unrelated source code, or variables sharing substrings. In YAML, changing a prefix may also require changing nested object indentation. Favor verified mappings and reviewed diffs.

## 26. When Old Properties Live in Environment Variables and System Properties

Because externalized configuration spans many formats, the same key can be passed multiple ways.

Old key example:

~~~text
spring.kafka.retry.topic.delay
~~~

Could be supplied via JVM option:

~~~bash
java -Dspring.kafka.retry.topic.delay=2s -jar app.jar
~~~

Or command-line argument:

~~~bash
java -jar app.jar \
  --spring.kafka.retry.topic.delay=2s
~~~

Or an env var using the corresponding conversion rules.

If you update only `application.yml`, a startup script or ConfigMap may still inject the old key into `Environment`. The migrator can spot it when loaded early enough, yet the final fix is **updating the source itself**.

### 26.1. Never Use `System.setProperty` as a Production Band-Aid

Code like:

~~~java
System.setProperty(
    "spring.kafka.retry.topic.backoff.delay", "2s");
~~~

inside a late-instantiated bean does not necessarily affect already-run auto-configurations. It also creates JVM-wide side effects and obscures config provenance.

Key changes belong in **externalized sources read by Spring Boot at the proper lifecycle phase**.

### 26.2. Docker ENTRYPOINT and Kubernetes Args

Inspect container commands/args, Helm templates, and launch scripts. Legacy keys often hide outside the application module's repository.

## 27. A Migration Matrix to Track Progress

A tracking table might include:

| ID | Old Property | New Property/Action | Source | Version | Test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `spring.kafka.retry.topic.delay` | `spring.kafka.retry.topic.backoff.delay` | `application-staging.yml` | Per target appendix | Retry policy test | In progress |
| 2 | `spring.main.show-banner` | Choose appropriate `banner-mode` | Service CLI | Per target appendix | Startup banner test | Check semantics |
| 3 | Removed property, no replacement | Read migration guide and redesign | Helm values | Target version | Integration test | Pending |
| 4 | Custom `example.old-timeout` | App-owned migration | Shared library | Internal | Unit + integration | Assign owner |

This table illustrates work tracking; rows 3 and 4 do not represent real Spring Boot keys.

### 27.1. Definition of Done

A property is done only when:

- The old key is removed from **every owned source**.
- The new value has the right type and semantics.
- Relevant tests pass with evidence.
- Startup in matching profiles needs no temporary migration.
- No conflict remains between old and new keys.
- Deployment owners have updated manifests, scripts, and imports.
- The final artifact runs without the migrator.

If any criterion is unmet, keep the item in the migration backlog rather than declaring the upgrade complete.

## 28. Rollback: Restoring Both Artifact and Configuration

Suppose a service was upgraded to a new Boot version and updated keys. If rollout hits an issue, the team may roll back the container image. However, **new config may not be understood by the old image**, just as old config may not work on the new image.

Therefore manage them as paired releases:

~~~text
Release A = Image A + Config A
Release B = Image B + Config B
~~~

Proper rollback sometimes requires reverting both together. With Helm/GitOps, keep approved revisions and manifest snapshots. For secrets, version them in a secret manager—never commit raw values to Git.

### 28.1. Dual-Version Coexistence Window

During rolling deployments, old and new Pods run concurrently. If they require incompatible property sets, plan a transition strategy in the config store—such as versioned ConfigMaps or a compatible value set both images accept.

Never expect the runtime migrator to be present in every image or resolve cross-release conflicts automatically.

### 28.2. The Migrator Is Not a Rollback Mechanism

When the migrator helps a target build run temporarily with legacy keys, that is forward transition support. It does not restore behavior of older frameworks, earlier dependencies, or already-migrated external data.

## 29. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Adding the migrator completes the upgrade." | It is a diagnostic and transition aid; you must still update sources and tests. |
| "The migrator rewrites `application.yml`." | It never edits files; it only maps supported properties temporarily at runtime. |
| "Zero warnings means the whole repo is clean." | Only sources loaded and observed early enough are checked. |
| "`@PropertySource` is scanned like Config Data." | Late-added `@PropertySource` entries are not considered by the migrator. |
| "Every deprecated key has a replacement." | Some are removed or have no direct substitute. |
| "Just rename the key and keep the value." | Verify new types, semantics, and policies. |
| "Leave the migrator in production to be safe." | Spring Boot requires removing it after migration. |
| "Maven compile passes so YAML is fine." | Compilation does not validate runtime keys. |
| "Dev profile had no warnings, so prod is safe." | Prod uses different sources and documents. |
| "Seeing the new key in `Environment` means the client uses it." | Beans/clients have their own lifecycles; test actual behavior. |
| "`TestPropertySource` fixes OS env vars." | Test sources do not change OS process environment variables. |
| "New versions always accept old keys." | Removed compatibility stops old keys from working. |
| "No retest needed after removing the migrator." | Must test the final artifact without the bridge. |
| "The fail option exists in every Spring Boot version." | Check version docs; `spring.properties.migrator.fail` is documented in Boot 4.2. |
| "Rolling back the image alone is enough." | New config may be incompatible with the old image. |

## 30. Removing the Migrator Cleanly

Once configuration sources are updated:

### Step 1 — Remove the Dependency

Maven: delete the `spring-boot-properties-migrator` dependency block from `pom.xml`.

Gradle: delete the `runtimeOnly(...)` line from the build script.

### Step 2 — Remove Temporary Support Flags

If you used `spring.properties.migrator.fail` or migration-only CI scripts, remove them on schedule. Never leave behind a flag assuming Boot still enforces it after removing the module.

### Step 3 — Rebuild Cleanly from Updated Source

Use your project's build commands, for instance:

~~~bash
mvn clean verify
~~~

Or:

~~~bash
./gradlew clean test bootJar
~~~

These are example commands. Real projects should run team-defined tasks, profiles, and pipelines; not every Gradle module defines a `bootJar` task.

### Step 4 — Verify the Runtime Classpath

Inspect the dependency graph and, if needed, the executable JAR. Do not merely check that the line was deleted from source, as transitive dependencies or stale artifacts might still bundle it.

### Step 5 — Boot Without the Migrator

Start the app against the migrated configuration sources and verify bean/client behavior. A service that only starts with the migrator bridge present is not fully upgraded.

### Step 6 — Review Diff and Release

A migration PR should clearly document:

- Boot versions changed.
- Old and new keys.
- Modified config sources.
- Test coverage and results.
- Special behaviors verified.
- Confirmation the migrator was removed.
- Rollout and rollback plans.

## 31. Troubleshooting: Migrator Silent or Behaving Unexpectedly

### Scenario A — Dependency Added, Yet No Diagnostics Appear

Possible causes:

- Active sources contain no keys needing migration.
- Migrator is not on the runtime classpath of the running artifact.
- App is running a stale JAR or container image.
- Old key sits in `application-prod.yml` while `prod` is inactive.
- Property source was added late via `@PropertySource`.
- Key belongs to a third-party/custom starter unrecognized by the module.
- Logs were filtered or startup failed before the diagnostic phase.

Resolution: verify artifact/dependency, active profiles, effective sources, and target version deprecation docs.

### Scenario B — YAML Updated, Yet Warnings Persist

Possible causes:

- Old key still lives in CLI, env, config import, or external files.
- Edited the wrong file or wrong working directory.
- Higher-precedence legacy source is overriding.
- Another copy remains in a profile-specific location.
- Helm/ConfigMap has not been redeployed to the cluster.
- Pods/processes were not restarted to pick up updated configs.

Resolution: inventory all sources, inspect effective property sources in a safe environment, and recreate instances after process-level changes.

### Scenario C — App Starts, Yet Behavior Is Wrong

Possible causes:

- New value has altered semantics.
- Setting was removed and could not be auto-migrated.
- Bean/client does not actually read that key.
- Defaults changed in the upgrade.
- Higher-precedence source overrides the setting.
- Config bound properly yet a resource client retained old parameters.

Resolution: test component behavior and read the migration guide, not just logs.

### Scenario D — Build Fails Before Migrator Runs

The migrator runs only once the app boots to its phase. If builds fail on Java APIs, dependency versions, or classpath incompatibilities, fix those first. This module is not a compiler refactoring tool.

### Scenario E — Fail Policy Has No Effect

Verify whether your Spring Boot version supports `spring.properties.migrator.fail`. If unsupported, remove it and rely on log review and test gates rather than an unrecognized flag.

### Scenario F — Both Old and New Keys Exist Together

Eliminate conflicts by updating all effective sources, then verify startup **without the migrator**. Never build production logic around the order of a temporary migration bridge.

## 32. Hands-On Exercises

### Exercise 1 — Read the Target Version's Deprecation List

Pick a Spring Boot version you can test against. Open its deprecated application properties appendix. Find three entries: one with a replacement, one without a replacement, and one noting semantic changes. Cross-check the migration guide without assuming mappings from other versions.

### Exercise 2 — Add Migrator in Maven

Create a small Spring Boot project with proper dependency management. Add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Supply an actual deprecated property for your target version, start the app, and inspect diagnostics. Then update the key and recheck.

### Exercise 3 — Add Migrator in Gradle

Using Gradle Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
}
~~~

Build and run the application module. Inspect the runtime classpath, then remove the dependency after migrating.

### Exercise 4 — Update Nested YAML Keys

Using old key `spring.kafka.retry.topic.delay` and new key `spring.kafka.retry.topic.backoff.delay` on a version supporting that mapping, write before/after YAML carefully nesting under `backoff`. Test after removing the migrator.

### Exercise 5 — Multi-Profile Verification

Create `application.yml` and `application-staging.yml`; place a deprecated key only in staging. Run the app with no profile and then with `--spring.profiles.active=staging`. Compare diagnostics and explain why the first run does not prove staging is clean.

### Exercise 6 — Files Added via `@PropertySource`

Put a deprecated key in a file loaded exclusively via `@PropertySource`. Observe the migrator's detection gap. Design a review/static-search check and decide whether to migrate the file to Config Data.

### Exercise 7 — Precedence Between Old and New Keys

Put the old key in a packaged JAR file and the new key in an external file. Add a CLI override. Predict conflict risks, then design complete removal of the old key instead of relying on runtime migration.

### Exercise 8 — Warnings vs Failures

On a Spring Boot version supporting the fail policy, compare `never`, `on-error`, and `on-warning` in a test environment. Record which keys trigger startup failure. Do not use this flag on unsupported versions.

### Exercise 9 — CI Pipeline

Design a pipeline: build target Boot → startup diagnostics with migrator → update sources → regression tests → remove migrator → test final artifact → canary deploy. Define exit criteria for each step.

### Exercise 10 — Image and Config Rollback

An older image reads key A while the new image reads key B. If rolling back to the old image while config remains B, what breaks? Design a release bundle versioning both artifact and config.

## 33. Pre-Release Upgrade Configuration Checklist

### Preparation

- [ ] Identified exact source and target Spring Boot versions.
- [ ] Read release notes, migration guide, and target deprecated-properties appendix.
- [ ] Cataloged profiles and Config Data locations.
- [ ] Identified external-to-JAR sources, env vars, JVM options, CLI, and config imports.
- [ ] Separated Boot-managed, third-party, and custom properties.
- [ ] Added the migrator temporarily to the right runtime classpath.
- [ ] Prepared a test environment free of production secrets.

### Analysis and Fixes

- [ ] Booted all key profiles and saved diagnostics.
- [ ] Classified renames, deprecations, removals, and semantic changes.
- [ ] Confirmed mappings in the target version's documentation.
- [ ] Updated names and values across all effective config sources.
- [ ] Handled nested YAML structures and flat properties forms.
- [ ] Audited files loaded via `@PropertySource`.
- [ ] Eliminated conflicts between old and new keys.
- [ ] Removed old keys from manifests, startup args, and test resources.
- [ ] Tested real component behavior, not just raw `Environment` lookups.

### Closing Migration

- [ ] Reran the migrator across all relevant profiles.
- [ ] Enabled fail policy if supported by the target version and desired by workflow.
- [ ] Removed `spring-boot-properties-migrator` from dependencies.
- [ ] Removed migration-only flags and obsolete CI scripts.
- [ ] Rebuilt the final artifact from updated sources.
- [ ] Verified the migrator is absent from the runtime classpath and artifact.
- [ ] Ran startup and regression tests **without the migrator**.
- [ ] Prepared rollout, readiness, and paired code+config rollback plans.
- [ ] Confirmed no secrets were printed in logs or migration reports.

## 34. Key Takeaways

1. **`spring-boot-properties-migrator` assists with upgrading Spring Boot-managed configuration properties**, not fixing an entire application automatically.
2. It **inspects `Environment`, logs startup diagnostics, and temporarily migrates supported properties at runtime**. It never rewrites YAML/properties or manifests.
3. Add `org.springframework.boot:spring-boot-properties-migrator` temporarily as `runtime` in Maven or `runtimeOnly` in Gradle.
4. **Not all deprecated properties have direct replacements**; type and semantic changes require manual updates per the migration guide.
5. A single run detects only sources and profiles **loaded and visible at the right phase**.
6. Properties added late to `Environment`, such as via **`@PropertySource`**, are excluded from the migrator per Spring Boot docs.
7. When old and new keys coexist, do not rely on temporary translation for precedence. **Update all effective sources** and verify final values.
8. On supported versions (such as Spring Boot 4.2), `spring.properties.migrator.fail` can fail startup by severity; never assume availability across all versions.
9. **Warning-free startup is not enough**: verify binding, runtime behavior, profiles, CI/CD manifests, and dependency compatibility.
10. **Remove the migrator once fixes are complete**, then retest the final artifact without the bridge. This step is mandatory to prove standalone migration.

## Official References

- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html): upgrade process, `spring-boot-properties-migrator`, runtime diagnostics, and late-source limits.
- [Spring Boot 4.2 — Upgrading](https://docs.spring.io/spring-boot/4.2/upgrading.html): migration diagnostics and `spring.properties.migrator.fail` (`never`, `on-error`, `on-warning`) where supported.
- [Spring Boot — Deprecated Application Properties](https://docs.spring.io/spring-boot/appendix/deprecated-application-properties/): deprecated keys and replacements in the current release.
- [Spring Boot 4.2 — Deprecated Application Properties](https://docs.spring.io/spring-boot/4.2/appendix/deprecated-application-properties/index.html): example of `spring.kafka.retry.topic.*` moving to `spring.kafka.retry.topic.backoff.*`.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): config sources, precedence, profiles, imports, and Config Data.
- [Spring Boot — Configuration Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html): deprecation metadata, reasons, and replacements.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): typed binding and validation.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): major upgrade example and migrator guidance.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): version/metadata changes and Boot 4 upgrade tasks.
