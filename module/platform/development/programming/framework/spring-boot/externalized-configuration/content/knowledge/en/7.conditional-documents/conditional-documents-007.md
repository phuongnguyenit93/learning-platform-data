# Combining Profile and Deployment Platform Conditions in Spring Boot

## 1. The problem this lesson solves

A Spring Boot application can run in development (`dev`), staging (`staging`), or production (`prod`) environments. Even within the same `prod` environment, the application might run directly on a VM, on Cloud Foundry, or inside Kubernetes. In such cases, some values depend only on the **purpose of the environment**, while others are appropriate only for the **deployment platform**.

For example:

- In `dev`, the application uses a mock endpoint and enables easy-to-observe logging levels.
- In `prod`, the application selects the production endpoint and disables test-only features.
- When running on Kubernetes, the application needs certain container-appropriate options.
- A group of configuration settings is enabled only when **both** the profile is `prod` or `staging` **and** the detected platform is Kubernetes.

Spring Boot supports **conditional configuration documents** via two properties:

```properties
spring.config.activate.on-profile
spring.config.activate.on-cloud-platform
```

This lesson guides you through combining both conditions in a YAML or `.properties` document, document selection rules, override order when multiple documents are activated together, and an observer application you can test on a laptop without provisioning a Kubernetes cluster.

**Context:** Java 21, Spring Boot 3.3.x, Config Data configuration. All hosts, URLs, environment names, and feature flags in the examples are mock data for learning purposes.

After completing this lesson, you can:

1. Explain the difference between profiles and cloud platforms.
2. Write a multi-document `application.yaml` with `---` separators.
3. Use `on-profile` with a single profile or an expression like `prod | staging`.
4. Use `on-cloud-platform: kubernetes` to activate by platform.
5. Explain why having both conditions together forms an **AND** relationship.
6. Predict the final configuration when multiple documents match simultaneously.
7. Simulate a platform with `spring.main.cloud-platform` for controlled testing.
8. Retrieve results via `Environment`, `@ConfigurationProperties`, and tests.
9. Avoid invalid configuration mistakes when trying to activate profiles inside profile-dependent documents.

## 2. Profiles and cloud platforms answer two different questions

**Profile** is a label chosen by the application or operator to decide which configuration group suits a given context. Names such as `dev`, `staging`, `prod`, and `local` are conventions defined by the development team. You can run the `prod` profile on a laptop to inspect configuration without anything automatically turning the laptop into production infrastructure.

**Cloud platform** describes the runtime platform. Spring Boot provides `CloudPlatform` to detect several well-known deployment environments, including `KUBERNETES` and `CLOUD_FOUNDRY`. This mechanism uses signals from the environment and can be explicitly specified with the `spring.main.cloud-platform` property. The deployment platform does not predetermine the profile either.

| Question | Profile | Cloud platform |
| --- | --- | --- |
| What does it represent? | The application's configuration purpose/context | The detected or specified runtime platform |
| Who decides it? | Application, runner, pipeline, or deployment tool | Platform signals and/or override property |
| Examples | `dev`, `staging`, `prod` | `kubernetes`, `cloud_foundry`, `none` |
| How selected in the lab | `--spring.profiles.active=prod` | `--spring.main.cloud-platform=KUBERNETES` |
| Document condition | `spring.config.activate.on-profile` | `spring.config.activate.on-cloud-platform` |

Two independent axes form a **condition matrix**:

```text
                       CLOUD PLATFORM
                 Other / none      Kubernetes
               +----------------+------------------+
PROFILE  dev    | config dev     | config dev + K8s |
         staging| config staging | staging + K8s    |
         prod   | config prod    | prod + K8s       |
               +----------------+------------------+
```

The `+` sign in the diagram only means that matching documents are loaded and **property values are merged** according to precedence rules, not arithmetic addition. A document containing both `on-profile` and `on-cloud-platform` applies only in the intersecting cells that satisfy both conditions.

## 3. What is a conditional configuration document?

An `application.yaml` file can contain **multiple YAML documents**. Each document is separated by a `---` line. Spring Boot processes each document as part of Config Data, then puts the **activated** documents into `Environment`.

Simple example:

```yaml
app:
  message: from-base
---
spring:
  config:
    activate:
      on-profile: dev
app:
  message: from-dev
```

The first document has no condition and serves as the base configuration. The second document participates only when the `dev` profile matches. If you run with:

```bash
java -jar app.jar --spring.profiles.active=dev
```

then `app.message` can be `from-dev`. If `dev` is not activated and no other overriding source exists, the result is `from-base`.

Points to remember:

- `spring.config.activate.on-profile` checks a **profile expression**.
- `spring.config.activate.on-cloud-platform` checks **CloudPlatform**.
- These two keys are **not** commands to enable profiles or create a Kubernetes environment. They only decide whether an existing document is included in the Config Data set.
- When both conditions appear in **the same document**, Spring Boot requires **both** to match.
- For documents loaded from the same file, values in later documents can override matching keys in earlier documents. In a real application, you must also account for locations, imports, environment variables, CLI arguments, and other higher-precedence sources.
- A document that fails its condition contributes none of its properties. There is no notion of "taking partial values even when the condition is false".

The documents in the following examples all use non-sensitive keys so they can be observed without exposing secrets.

## 4. The `on-profile` condition: single profile, OR, AND, and NOT

Simplest form:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

Only the document containing the snippet above matches the `prod` profile.

When multiple profiles are needed, `on-profile` accepts an expression. Example:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"
```

The `|` sign denotes **OR**: only one of the two profiles needs to match. This is a good choice when `prod` and `staging` share a deployment configuration layer.

A stricter condition example:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & !legacy"
```

It requires `prod` to be active and `legacy` to be inactive. `&` is AND, and `!` is NOT. Parentheses can be used to express complex conditions when needed:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (blue | green)"
```

When using expressions, wrap them in YAML quotes so special characters are not interpreted as YAML syntax or hard to read. Profile names are conventions set by the team owning the application, so keep names short, clear, and consistent.

**Do not confuse** an `on-profile` expression with the `spring.profiles.active` configuration list. The following example uses two profiles at once:

```bash
java -jar app.jar --spring.profiles.active=prod,blue
```

A document with the `prod & blue` expression will match. A document with a `staging` condition will not be activated merely because `prod` is also a release environment.

## 5. The `on-cloud-platform` condition: platform detection

A document specific to Kubernetes:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  platform-note: running-on-kubernetes
```

Spring Boot includes this document in effective configuration only when the active cloud platform matches `KUBERNETES`.

Spring Boot has a platform detection mechanism using environment signals. On Kubernetes, it can inspect service-related environment variables, such as pairs of `*_SERVICE_HOST` and `*_SERVICE_PORT`, for detection. You should not manually create Kubernetes-like variables in production to spoof detection; when controlled testing is needed, use the framework-supported override property.

**Simulating Kubernetes on a laptop:**

```bash
java -jar app.jar --spring.main.cloud-platform=KUBERNETES
```

This option forces Spring Boot to treat the cloud platform as `KUBERNETES` for that run, so documents with `on-cloud-platform: kubernetes` can be activated without creating a cluster. It **does not** provide an API server, service discovery, volume mounts, DNS, or other Kubernetes features. Therefore, only use this for labs or testing configuration branches that do not depend on real infrastructure.

To test the non-cloud-platform branch, you can force:

```bash
java -jar app.jar --spring.main.cloud-platform=NONE
```

The `spring.main.cloud-platform` property is helpful for testing the matrix, though in real deployments you should decide whether to use auto-detection or explicit configuration and keep a consistent convention. `on-cloud-platform` is **not** a profile selection tool. Combining cloud platform with `prod` requires writing both conditions in the same document.

## 6. Combining both conditions in the same document

Example:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes
app:
  runtime-mode: release-on-kubernetes
  diagnostics-enabled: false
```

Condition evaluation is:

```text
documentActive =
    (activeProfiles match "prod | staging")
    AND
    (active CloudPlatform is KUBERNETES)
```

Truth table:

| Active profile | Cloud platform | Is the document loaded? | Why |
| --- | --- | --- | --- |
| `dev` | `NONE` | No | Neither branch matches |
| `dev` | `KUBERNETES` | No | Cloud matches but profile does not |
| `prod` | `NONE` | No | Profile matches but cloud does not |
| `prod` | `KUBERNETES` | Yes | Both branches match |
| `staging` | `KUBERNETES` | Yes | `staging` satisfies the OR expression and cloud matches |
| `staging` | `NONE` | No | Cloud does not match |
| No profile specified | `KUBERNETES` | No | Neither `prod` nor `staging` matches |

When no active profile is declared, Spring Boot has the concept of a **default profile**, usually named `default`. Thus, having no explicit active profile does not mean all profile expressions are disabled; for example, a conditional document `on-profile: default` can apply. The table above only examines `prod` and `staging`.

If you put `on-profile` and `on-cloud-platform` into **two different documents**, Spring Boot evaluates them separately. Two matching documents can both contribute properties, but you cannot treat putting one condition in document A and another in document B as creating an AND between them. To get AND, put both in the same document.

## 7. Hands-on application: Deployment Conditions Observer

We will create a Spring Boot console application that prints active profiles, cloud platform, and selected values. The application needs no Spring Web, Kubernetes SDK, or access to a Kubernetes cluster.

### 7.1. Project structure

```text
deployment-conditions/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/deployment/
    │   │   ├── DeploymentConditionsApplication.java
    │   │   └── DemoProperties.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/deployment/
            └── ProductionKubernetesTest.java
```

Create a Gradle project using Java 21 and Spring Boot 3.3.x. Use the Gradle Wrapper provided by the project generator so it does not depend on a system-wide Gradle installation.

`settings.gradle`:

```groovy
rootProject.name = 'deployment-conditions'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In a repository that already manages plugin versions via conventions or a version catalog, use the repository's existing management system. The snippet above only shows minimal configuration for a standalone project.

### 7.2. Designing the YAML documents

`src/main/resources/application.yaml`:

```yaml
# Document 1: applies to all environments.
spring:
  application:
    name: deployment-conditions
  main:
    web-application-type: none

demo:
  mode: base
  platform: generic
  endpoint: "https://service.example.test/base"
  features:
    audit: false
    metrics: false

---
# Document 2: only when dev profile is active.
spring:
  config:
    activate:
      on-profile: dev

demo:
  mode: development
  endpoint: "http://localhost:9091"

---
# Document 3: only when prod profile is active.
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production-generic
  endpoint: "https://service.example.test/prod"

---
# Document 4: applies with any profile if cloud is Kubernetes.
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

demo:
  platform: kubernetes

---
# Document 5: requires (prod or staging) AND Kubernetes.
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes

demo:
  mode: kubernetes-release
  features:
    metrics: true
```

Five documents illustrate four scope patterns:

1. **Common baseline**: document 1 sets safe values usable when no special condition applies.
2. **By profile**: documents 2 and 3 change `demo.mode`/`demo.endpoint` without modifying `demo.platform`.
3. **By cloud platform**: document 4 only changes `demo.platform` regardless of profile, so when running `dev` in Kubernetes, mode remains `development`.
4. **By intersection of both conditions**: document 5 only changes mode and metrics if cloud is Kubernetes **and** active profiles match `prod | staging`.

The `example.test` domain is used for illustration; it is not a real endpoint. The program only prints strings and sends no HTTP requests to those addresses.

**Document order matters.** For example, with `prod` + Kubernetes, document 3 sets `demo.mode=production-generic`, yet document 5 later sets `demo.mode=kubernetes-release` and also matches, overriding that value within the same file. Document 5 does not set `demo.endpoint`, so the endpoint remains the value from document 3.

### 7.3. Binding values into a Java object

`src/main/java/dev/example/deployment/DemoProperties.java`:

```java
package dev.example.deployment;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String mode,
        String platform,
        URI endpoint,
        Features features
) {
    public record Features(
            boolean audit,
            boolean metrics
    ) {}
}
```

`@ConfigurationProperties` binds the `demo.*` group in a strongly typed way. `URI` represents the endpoint as an address, and `boolean` gives feature flags concrete types. Values inside the record are the result **after Spring Boot selects and merges configuration sources**, not raw values from individual documents.

### 7.4. Printing configuration results from the application

`src/main/java/dev/example/deployment/DeploymentConditionsApplication.java`:

```java
package dev.example.deployment;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.cloud.CloudPlatform;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeploymentConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeploymentConditionsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            ConfigurableEnvironment environment,
            DemoProperties demo) {
        return args -> {
            CloudPlatform cloud = CloudPlatform.getActive(environment);

            System.out.println("=== DEPLOYMENT CONDITIONS ===");
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("cloudPlatform = "
                    + (cloud == null ? "<none>" : cloud.name()));
            System.out.println("demo.mode = " + demo.mode());
            System.out.println("demo.platform = " + demo.platform());
            System.out.println("demo.endpoint = " + demo.endpoint());
            System.out.println("demo.features.audit = "
                    + demo.features().audit());
            System.out.println("demo.features.metrics = "
                    + demo.features().metrics());

            System.out.println("Environment demo.mode = "
                    + environment.getProperty("demo.mode"));
        };
    }
}
```

`activeProfiles` shows explicitly activated profiles. `cloudPlatform` shows the platform Spring Boot determined to be active. The `demo.*` fields show which document supplied or overridden each value. `Environment.getProperty()` lets you cross-check a key against the value bound into the record.

The application does not print all environment variables or secrets; it only inspects pre-designed mock keys. In real projects, do not log all properties or expose sensitive configuration on public endpoints for diagnostics.

## 8. Running the profile and cloud platform matrix

From the project root directory, run the commands below. Each `bootRun` invocation starts a new process and prints the results. Because `web-application-type: none` is set, the application does not need to open an HTTP port.

### Experiment A — no profile selected, no cloud platform forced

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.main.cloud-platform=NONE'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.cloud-platform=NONE"
```

Expected:

```text
activeProfiles = []
cloudPlatform = NONE
demo.mode = base
demo.platform = generic
demo.features.audit = false
demo.features.metrics = false
```

Without forcing the cloud platform, detection depends on the actual environment. This experiment explicitly sets `NONE` to avoid pre-existing environment variables on a laptop or CI causing hard-to-explain differences.

### Experiment B — `dev` profile, cloud platform NONE

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --spring.main.cloud-platform=NONE'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --spring.main.cloud-platform=NONE"
```

Expected:

```text
activeProfiles = [dev]
cloudPlatform = NONE
demo.mode = development
demo.platform = generic
demo.endpoint = http://localhost:9091
demo.features.metrics = false
```

The profile condition matches so document 2 is loaded. The two Kubernetes-dependent documents are not loaded.

### Experiment C — `dev` with simulated Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --spring.main.cloud-platform=KUBERNETES'
```

Expected:

```text
activeProfiles = [dev]
cloudPlatform = KUBERNETES
demo.mode = development
demo.platform = kubernetes
demo.features.metrics = false
```

This case distinguishes the two conditions: document 4 can load because cloud matches, whereas document 5 does **not** load because `dev` does not match `prod | staging`. Therefore `mode` stays `development`.

### Experiment D — `prod` without Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=NONE'
```

Expected:

```text
activeProfiles = [prod]
cloudPlatform = NONE
demo.mode = production-generic
demo.platform = generic
demo.endpoint = https://service.example.test/prod
demo.features.metrics = false
```

The `prod` profile document matches, while the two documents requiring Kubernetes are skipped.

### Experiment E — `prod` on Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=KUBERNETES'
```

Expected:

```text
activeProfiles = [prod]
cloudPlatform = KUBERNETES
demo.mode = kubernetes-release
demo.platform = kubernetes
demo.endpoint = https://service.example.test/prod
demo.features.metrics = true
```

This is the centerpiece experiment: documents 3, 4, and 5 all match. `mode` and `metrics` come from document 5; `platform` comes from document 4; `endpoint` still comes from document 3 because document 5 does not override that key.

### Experiment F — `staging` on Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=staging --spring.main.cloud-platform=KUBERNETES'
```

Expected:

```text
activeProfiles = [staging]
cloudPlatform = KUBERNETES
demo.mode = kubernetes-release
demo.platform = kubernetes
demo.endpoint = https://service.example.test/base
demo.features.metrics = true
```

The expression `prod | staging` matches via `staging`, yet document 3 is only for `prod` and supplies no endpoint. `demo.endpoint` keeps the baseline value from document 1.

### Experiment G — testing a source with higher precedence than Config Data

Application arguments can override effective properties in the experiment:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=KUBERNETES --demo.mode=from-cli'
```

Expect `demo.mode=from-cli`. This does **not** mean document 5 stopped being activated; it still matches its conditions. Only the `demo.mode` key was overridden by a higher-precedence source. The `demo.platform` and `demo.features.metrics` keys still reflect the Kubernetes documents in the example.

On Windows, you can use `.\gradlew.bat bootRun --args="..."` with similar arguments. Note that the quotes are shell syntax to pass a single `--args` string to Gradle, while each `--spring...` argument inside is passed to the Spring Boot application.

### 8.1. Result comparison table

| Profile | Cloud | `demo.mode` | `demo.platform` | `demo.features.metrics` |
| --- | --- | --- | --- | --- |
| not selected | NONE | `base` | `generic` | `false` |
| dev | NONE | `development` | `generic` | `false` |
| dev | KUBERNETES | `development` | `kubernetes` | `false` |
| prod | NONE | `production-generic` | `generic` | `false` |
| prod | KUBERNETES | `kubernetes-release` | `kubernetes` | `true` |
| staging | KUBERNETES | `kubernetes-release` | `kubernetes` | `true` |
| prod + CLI override | KUBERNETES | `from-cli` | `kubernetes` | `true` |

Fill in the actual results after each command and compare every property, rather than checking only `demo.mode`. Differences across fields clearly illustrate how active documents are **merged**.

## 9. Multi-document configuration in `.properties`

YAML is not mandatory. Spring Boot 3.3 also supports **multi-document properties** with separator lines using `#---` or `!---` syntax.

Example `application.properties`:

```properties
demo.mode=base
demo.platform=generic
#---
spring.config.activate.on-profile=prod
demo.mode=production-generic
#---
spring.config.activate.on-cloud-platform=kubernetes
demo.platform=kubernetes
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
demo.mode=kubernetes-release
```

Watch the separator rules in `.properties`: the separator line must have no leading whitespace, exactly three hyphens, and the lines immediately before and after the separator must not use the same comment prefix as the separator line per Spring Boot's rules. Do not simply put a bare `---` string in `.properties` and expect it to work like YAML.

Documents in `.properties` are also conditionally evaluated and merged in order. To reduce confusion in real projects, choose one primary format per location. When both `.properties` and YAML exist at the same location, Spring Boot applies its own format precedence rules; that is a different precedence layer from document order within a single file.

## 10. Setting profiles and conditions correctly

### 10.1. `spring.profiles.active` must be placed in a valid location

A common mistake is trying to use a profile condition to activate another profile right inside the same document:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: metrics
```

This configuration is **invalid**. `spring.profiles.active` and `spring.profiles.default` must not be used inside profile-specific documents or documents activated by `spring.config.activate.on-profile`. Spring Boot applies similar constraints to other profile selection or expansion mechanisms such as `spring.profiles.include` and profile group definitions. Do not rely on a conditional document to modify the list of profiles already used to evaluate that very condition.

Set active profiles via CLI, environment variables, or an unconditional document, for example:

```bash
java -jar app.jar --spring.profiles.active=prod
```

If profile groups are needed, define `spring.profiles.group` in a valid profile-independent configuration and select the group via mechanisms supported by Spring Boot. Treat profile-selection configuration and profile-activated configuration as two separate responsibilities.

### 10.2. Cloud conditions do not change profiles automatically

For example, a document:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
```

does not automatically make the active profile `prod`. Kubernetes can run `dev` or `staging` applications. If your team wants a convention that every production deployment must enable `prod`, configure that in the deployment manifest/pipeline using a valid source.

### 10.3. A document can match yet still not decide the final value

When `prod` and Kubernetes both match, document 5 in the example is loaded. However, if `--demo.mode=from-cli` is present, the final value is still `from-cli`. Conditions only decide **whether a document participates**, whereas `PropertySource` precedence decides **which value wins**.

When diagnosing, ask two separate questions:

1. Was the document containing the key activated?
2. If so, which source ultimately decides that key?

Answering the first question does not guarantee the second.

### 10.4. Specify `spring.main.cloud-platform` at the right time

In the lab, passing `--spring.main.cloud-platform=KUBERNETES` on the command line helps Spring Boot determine the cloud platform while loading configuration. Do not expect a value declared **inside the very document that only activates when cloud is Kubernetes** to decide the cloud platform for that document. In real deployments, let the platform be detected from actual conditions or set an override via a stable source that takes effect early.

### 10.5. Profiles are not security

The `prod` profile does not mean the document can only be read in real production. Anyone controlling startup parameters can turn on `prod` on another machine. Therefore, do not put tokens, passwords, or private keys in source YAML just because a document has an `on-profile: prod` condition.

For secrets, use the platform's secret management, access controls, and external configuration sources; activation conditions only help select configuration. Never print secrets to logs when inspecting values.

## 11. Testing conditions with Spring Boot Test

A good way to keep behavior stable while refactoring configuration is writing tests for important combinations. For instance, verifying that `prod` + Kubernetes activates document 5, while `prod` + NONE still receives standard production configuration.

### 11.1. Testing the `prod` + Kubernetes branch

`src/test/java/dev/example/deployment/ProductionKubernetesTest.java`:

```java
package dev.example.deployment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
        "spring.main.cloud-platform=KUBERNETES"
})
@ActiveProfiles("prod")
class ProductionKubernetesTest {

    @Autowired
    DemoProperties demo;

    @Test
    void activatesProfileAndPlatformDocumentTogether() {
        assertEquals("kubernetes-release", demo.mode());
        assertEquals("kubernetes", demo.platform());
        assertEquals("https://service.example.test/prod",
                demo.endpoint().toString());
        assertTrue(demo.features().metrics());
    }
}
```

Run:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

This test sets the profile via `@ActiveProfiles` and forces the cloud platform using a test property. It does not need to call a real Kubernetes cluster. `@SpringBootTest` starts the context so conditional document values are loaded and bound just as in the application.

### 11.2. Testing the standard production branch

You can add another test class:

```java
package dev.example.deployment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
        "spring.main.cloud-platform=NONE"
})
@ActiveProfiles("prod")
class ProductionGenericTest {

    @Autowired
    DemoProperties demo;

    @Test
    void doesNotActivateKubernetesOnlyDocument() {
        assertEquals("production-generic", demo.mode());
        assertEquals("generic", demo.platform());
        assertFalse(demo.features().metrics());
    }
}
```

When both tests pass as expected, you have proof that the same `prod` profile can receive different values depending on cloud platform. If a new YAML document is appended at the end of the file later, these tests will catch value changes without launching the app and reading logs manually.

### 11.3. What else should you test?

For applications with many conditional configurations, choose additional business-meaningful combinations:

- `dev` + Kubernetes still does not receive release-specific values.
- `staging` + Kubernetes receives the combined document thanks to the OR operator.
- No active profile and `NONE` keeps baseline values.
- When setting a property via CLI, the effective value obeys source precedence order.
- Invalid or mistyped configuration is caught early via binding/validation.
- Sensitive values are not emitted to logs or inspection endpoints.

You do not necessarily need a test for every permutation if there are too many profiles and platforms. Prioritize combinations with distinct behavior or those that have previously caused deployment bugs.

## 12. Diagnosing when results differ from predictions

### 12.1. Profile document is not loaded

Check:

1. Exact profile name, e.g., `prod` differs from `production` unless your team configured an alias/group.
2. Where the active profile actually came from: CLI, environment variable, Java system properties, base config, or tests.
3. Whether the `on-profile` expression needs OR, AND, or NOT, and whether the `default` profile participates.
4. Whether the YAML document has `---` in the right place and `spring.config.activate.on-profile` sits inside the right document.
5. Whether another source overrides the same key after the document is loaded.

A common mistake is seeing `demo.mode=base` and concluding the YAML file was not found. The file may have been found, yet the `prod` document inside it was not activated.

### 12.2. Kubernetes document is not loaded even when running in a container

A container does not mean Kubernetes. Docker on a laptop is not detected by Spring Boot as Kubernetes by default. Check the cloud platform Spring Boot actually determines; the lab includes `CloudPlatform.getActive(environment)` for inspection.

If in real Kubernetes and detection differs from expectations, inspect environment signals, special runtime environments, detection rules of the Boot version in use, and `spring.main.cloud-platform` settings. In test environments, you can force `KUBERNETES` to isolate condition issues, though you must not treat that as proof a real cluster provided backing services.

### 12.3. Placing both `on-profile` and `on-cloud-platform` when only one condition is true

Spring Boot requires both to be true when they coexist in one document. For example, `dev` + Kubernetes does **not** activate the `prod | staging` + Kubernetes document. Resolve this by fixing the condition to match operational intent or moving truly shared keys into a document that only has `on-cloud-platform`.

### 12.4. Profile matches, cloud matches, yet value is still different

Check:

- Is there a conditional document appearing **later** in the same file that overrides the key?
- Does a profile-specific file like `application-prod.yaml` supply the same key?
- Are there `spring.config.import` or `spring.config.additional-location` declarations?
- Do environment variables or CLI arguments take higher priority than file configuration?
- When using `@ConfigurationProperties`, does the property name match relaxed binding rules?
- Was the app restarted after modifying the file?

For tricky cases, run the application in a controlled environment, enable Config Data diagnostic logging per appropriate guidelines, and inspect data through secured Actuator `env`/`configprops`. Do not dump secrets to logs to inspect precedence order.

### 12.5. Configuration fails because `spring.profiles.active` is inside a document with `on-profile`

This is a Spring Boot constraint. Move profile activation to a profile-independent source or startup argument. Do not try fixing it by wrapping an extra cloud condition, because the document still remains invalid for declaring active profiles.

### 12.6. Multiple profiles active simultaneously

If both `prod` and `staging` are enabled together, profile-conditional documents for each name can both match. When documents declare the same key, file order, locations, and profile-specific rules must be evaluated. Do not treat enabling multiple profiles as a mechanism that picks "only one environment". In most systems, maintain a clear convention to avoid combining conflicting profiles.

### 12.7. Values only update after restart

Conditional documents are resolved during Config Data loading at startup. Modifying `application.yaml` or changing environment variables outside the process does not automatically cause bound beans to pick up new values. Dynamic refresh mechanisms must be designed, secured, and tested separately. For this lesson, each experiment is a fresh restart.

## 13. When to use conditional documents vs. splitting files

Both approaches below are valid:

**Approach A: One file with multiple documents.**

```text
src/main/resources/application.yaml
  base document
  on-profile: dev document
  on-profile: prod document
  on-cloud-platform: kubernetes document
  combined profile + Kubernetes document
```

Pros: all conditions sit close together, making the matrix easy for learners to see, well-suited for small apps and moderate numbers of conditions. Cons: long files and multiple documents overriding the same key become hard to diagnose as the file grows.

**Approach B: Multiple files plus conditional documents.**

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

`application-prod.yaml` holds profile-specific properties; you can still use `on-cloud-platform` documents in an appropriate file to separate runtime cases. In large systems, splitting files by responsibility avoids concentrating too much logic in one file, though precedence across locations, profile-specific files, and documents must stay clear.

Pick a convention for the development team. For branches specific to Kubernetes and multiple profiles, combined conditions inside one document are often easier to express than duplicating many files. For real secrets or real endpoints, store them in externally managed configuration sources rather than embedding them into packaged documents.

## 14. Pattern for real deployments

A practical organization scheme:

- Packaged `application.yaml`: application name, shared parameters, and non-sensitive baseline values.
- `application-prod.yaml` or `on-profile: prod` document: general production behavior, such as feature flags and appropriate logging levels.
- `on-cloud-platform: kubernetes` document: Kubernetes-specific runtime options, such as a mock service DNS name in the lab.
- Document with **both** `on-profile: prod | staging` and `on-cloud-platform: kubernetes`: tuning a feature used only for releases on Kubernetes.
- Secrets, credentials, tokens, and system-specific addresses: supplied from externally managed sources such as environment variables, ConfigMap/Secret mounts, or secret stores, with proper access controls.

A Kubernetes deployment manifest can configure the profile via an environment variable:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
```

This is an **illustrative snippet** from a container spec, not a complete Kubernetes manifest. Spring Boot receives the `prod` profile; detecting Kubernetes is handled separately by the cloud platform mechanism. If an explicit cloud platform needs to be specified, you can add the corresponding configuration per environment policy, while avoiding conflicting duplicates across multiple sources.

This keeps the **two conditional axes** independent. For example, you can run the `staging` profile on Kubernetes to test the release branch under near-production conditions, or run `prod` on non-Kubernetes infrastructure and still receive general production properties.

## 15. Self-check exercises

**Exercise 1.** With `on-profile: "prod | staging"` and `on-cloud-platform: kubernetes`, is the document activated when the profile is `dev` on Kubernetes? Why?

**Exercise 2.** With the same document, when the `staging` profile is active but the cloud platform is `NONE`, is the document loaded?

**Exercise 3.** An `on-cloud-platform: kubernetes` document precedes a combined `on-profile: prod` + `on-cloud-platform: kubernetes` document. Both set `demo.mode` and both match. Within the same file and with no other sources, which value usually takes precedence?

**Exercise 4.** Can you use `spring.config.activate.on-profile: prod` in a document and put `spring.profiles.active=metrics` below it to auto-enable a secondary profile?

**Exercise 5.** Does running the `prod` profile on a laptop mean `CloudPlatform` is `KUBERNETES`? How do you simulate the cloud platform in the lab?

**Exercise 6.** Why might an already-activated document still fail to determine the final value of a key?

**Exercise 7.** The `prod` + Kubernetes profile returns `demo.endpoint` from the `prod` document, yet `demo.mode` from the combined document. What does that show about how Spring Boot merges documents?

**Exercise 8.** An engineer wants to store a production token in `application-prod.yaml` because that file is only loaded when the `prod` profile is active. What risk would you explain?

Hints:

1. No; the profile does not match, so AND evaluates to false.
2. No; the cloud platform does not match.
3. The combined document appearing later can override the same key when both are loaded.
4. No; `spring.profiles.active` is invalid inside a document activated by `on-profile`.
5. No. You can use `--spring.main.cloud-platform=KUBERNETES` in the lab.
6. Because precedence across documents, files, locations, and sources such as CLI still applies.
7. Different keys can keep values from different documents; only overlapping keys are overridden.
8. Packaged files can still be read from the artifact or repository; profiles are not a security boundary for secrets.

## 16. References and next steps

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): multi-document YAML/Properties, `spring.config.activate.on-profile`, `spring.config.activate.on-cloud-platform`, Config Data order.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): selecting profiles, default profiles, and restrictions on profile-selection properties.
- [Spring Boot — Deploying to the Cloud](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html): platform detection and specifying `spring.main.cloud-platform` when needed.

After this lesson, keep a working copy of **Deployment Conditions Observer** and the matrix results table. Whenever you encounter a configuration that "only breaks on Kubernetes production", check in order: actual active profiles, the cloud platform detected by Spring Boot, matching `activate` documents, document order plus external sources, and compare effective values per key. That is how to use conditional documents deliberately and verifiably.