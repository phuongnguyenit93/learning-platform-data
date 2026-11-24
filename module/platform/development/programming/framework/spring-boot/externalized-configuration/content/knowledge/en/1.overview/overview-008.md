# Learning Path and Sample Application for Observing Configuration in Spring Boot

## 1. What Does This Lesson Help You Accomplish?

In Spring Boot, the same application can run on a developer workstation, a testing environment, and production without editing Java code for each place. Configuration values are supplied externally via files, environment variables, startup arguments, and other sources. The hard part is not just declaring a property, but answering: **where did the final value come from, why did it beat other values, and what value is the Java object actually receiving?**

This lesson combines a **structured learning path** with a **Config Observer sample application**. The application displays a small set of test properties, active profiles, values resolved by Spring Boot, and the names of sources containing each property. By changing one configuration source at a time and restarting, you observe real effects rather than memorizing theory.

After practicing, you will be able to:

- Distinguish configuration sources, property keys, effective values, and bound objects.
- Use `application.yml`, `application-dev.yml`, environment variables, and command-line arguments.
- Explain an override scenario using evidence produced by the program.
- Use `@ConfigurationProperties`, `Environment`, and Actuator for controlled observation.
- Write binding tests and diagnose causes when a value differs from expectations.
- Recognize security boundaries: never expose secrets or the full runtime environment on public APIs.

**Baseline for examples:** Java 21, Spring Boot 3.3.x, Gradle, Spring Web, Spring Boot Actuator, and Validation. The code below uses standard Spring Boot 3.3 APIs; adjust plugin versions to match your project if needed.

## 2. Concept Map Before Writing Code

Picture the path from configuration to application behavior:

```text
application.yml / application-dev.yml
                   + environment variables
                   + Java system properties
                   + command-line arguments
                         |
                         v
               Spring Environment
        (reads PropertySources in order)
                         |
             +-----------+------------+
             |                        |
             v                        v
  Environment.getProperty()  @ConfigurationProperties
  (reads individual keys)    (binds a key group into Java)
             |                        |
             +-----------+------------+
                         |
                         v
                  Application behavior
```

Three questions to keep separate:

1. **Where is the value declared?** For example, `demo.message` might exist in a YAML file, an environment variable, and a command-line argument.
2. **What is the effective value?** When multiple sources supply the same property, the higher-precedence source determines the outcome.
3. **How does the application consume that value?** `Environment` reads directly; `@ConfigurationProperties` binds a whole group of keys into a strongly typed object.

A few practical rules are enough to get started:

- Settings in `application.yml` serve as the demo's baseline values.
- `application-dev.yml` supplements or overrides baseline values **when the `dev` profile is active**.
- In the scenarios of this lesson, environment variables can override file values, and command-line arguments can override both. Spring Boot's complete precedence order includes many other sources; do not generalize this experiment table into the entire precedence rulebook.
- `DEMO_MESSAGE` is the standard environment variable name for `demo.message` thanks to Spring Boot's property name mapping.
- Editing a configuration file on disk **does not automatically** change values inside a running Spring Boot process. In this lesson, we restart the application after each source change to observe the result clearly.
- Profiles select configuration groups by context. Profiles are not a secret storage mechanism.

## 3. Recommended Learning Path

| Stage | Focus | Core Practice | Sign of Understanding |
| --- | --- | --- | --- |
| 1. Baseline values | Keys, values, `application.yml` | Run app with no profile selected | Explain the three default values |
| 2. Profiles | `spring.profiles.active`, `application-dev.yml` | Run the `dev` profile | Point out which values changed and why |
| 3. External overrides | Environment variables and CLI args | Set the same key in three places | Predict and confirm the winning source |
| 4. Type-safe binding | `@ConfigurationProperties`, validation | Inspect the `DemoProperties` object | Understand startup failures from invalid config |
| 5. Observation and testing | `Environment`, `PropertySource`, Actuator, JUnit | View reports and run tests | Distinguish effective values from declared sources |
| 6. Real-world use | External files outside JAR, security, ops | Load external file, strip secrets from logs | Follow a diagnostic workflow for misconfiguration |

Complete stages 1–3 before diving into advanced sources such as config trees, deployment-platform configuration, or secret stores. Change **only one configuration factor** per stage so results remain easy to compare.

## 4. Sample Application: Config Observer

### 4.1. Scenario

Suppose a service has three learning-purpose properties:

| Key | Meaning | Baseline Value |
| --- | --- | --- |
| `demo.message` | Display message | `hello-from-base` |
| `demo.region` | Simulated region label | `local` |
| `demo.feature-enabled` | Simulated feature flag | `false` |

All three are **public, lab-only data**. The observation endpoint will not accept arbitrary user-supplied keys, preventing accidental exposure of passwords, tokens, or sensitive properties.

Minimal directory tree:

```text
config-observer/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat      # Gradle Wrapper
└── src/
    ├── main/
    │   ├── java/dev/example/configobserver/
    │   │   ├── ConfigObserverApplication.java
    │   │   ├── DemoProperties.java
    │   │   └── ConfigController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-dev.yml
    └── test/
        └── java/dev/example/configobserver/
            └── DemoPropertiesTest.java
```

You can generate a new Spring Boot Gradle project with the **Spring Web**, **Spring Boot Actuator**, and **Validation** dependencies, keep the Gradle Wrapper generated by the initializer, and place the contents below into the corresponding files.

### 4.2. Gradle Setup

`settings.gradle`:

```groovy
rootProject.name = 'config-observer'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the project's Gradle Wrapper to avoid Gradle version mismatches across machines. In repositories with centralized plugin version management, keep the repository setup and add only the missing dependencies.

### 4.3. Spring Boot Startup and Configuration Scanning

`src/main/java/dev/example/configobserver/ConfigObserverApplication.java`:

```java
package dev.example.configobserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigObserverApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigObserverApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` helps Spring Boot locate configuration binding classes in the current package and subpackages. This is why `DemoProperties` below is registered as a bean for the controller to inject.

### 4.4. Declaring Baseline and Profile Values

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: config-observer

server:
  address: 127.0.0.1
  port: 8080

demo:
  message: hello-from-base
  region: local
  feature-enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

`src/main/resources/application-dev.yml`:

```yaml
demo:
  message: hello-from-dev
  region: dev-lab
  feature-enabled: true
```

Points to observe:

- No profile active: the three `demo.*` keys come from `application.yml`.
- `dev` active: those three keys come from `application-dev.yml` unless a higher-precedence source overrides them.
- There is no need to repeat `server.port`, Actuator settings, or other baseline keys in `application-dev.yml`.
- `server.address: 127.0.0.1` restricts network access to the lab endpoints. Management endpoints `env` and `configprops` should only be used in controlled testing environments; in production, reduce exposure and configure proper protection.

**Note:** Actuator is configured here intentionally to permit inspecting property names for diagnostic learning. `show-values: never` instructs Actuator to mask values in sensitive endpoints; do not rely on that masking alone to protect secrets in custom application APIs.

### 4.5. Binding a Property Group into a Typed Object

`src/main/java/dev/example/configobserver/DemoProperties.java`:

```java
package dev.example.configobserver;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String message,
        @NotBlank String region,
        boolean featureEnabled
) {}
```

Here:

- Prefix `demo` groups `demo.message`, `demo.region`, and `demo.feature-enabled` into one object.
- `feature-enabled` in YAML binds to the Java field `featureEnabled` via relaxed binding.
- `@NotBlank` requires `message` and `region` to contain non-whitespace text; if a higher-precedence source overrides them with blank values, the application fails validation at startup.
- The `boolean` type enforces the feature flag's semantics. In larger systems, you can use stronger types, enums, durations, data sizes, and appropriate validation annotations.

`@ConfigurationProperties` works well when multiple properties belong to one functional group. For a single key, you may also see `@Value("${demo.message}")` in code; however, in this demo we use a binding object to keep related values together.

### 4.6. Scoped Observation Endpoint

`src/main/java/dev/example/configobserver/ConfigController.java`:

```java
package dev.example.configobserver;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/config")
public class ConfigController {

    private static final List<String> OBSERVED_KEYS = List.of(
            "demo.message",
            "demo.region",
            "demo.feature-enabled"
    );

    private final ConfigurableEnvironment environment;
    private final DemoProperties properties;

    public ConfigController(ConfigurableEnvironment environment,
                            DemoProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @GetMapping
    public Snapshot snapshot() {
        Map<String, Trace> traces = new LinkedHashMap<>();
        for (String key : OBSERVED_KEYS) {
            traces.put(key, trace(key));
        }
        return new Snapshot(
                Arrays.asList(environment.getActiveProfiles()),
                properties,
                traces
        );
    }

    private Trace trace(String key) {
        List<String> matchingSources = new ArrayList<>();

        for (PropertySource<?> source : environment.getPropertySources()) {
            // Spring Boot may place a composite adapter at the top of the list.
            // Skip the adapter to more easily inspect the underlying real sources.
            if ("configurationProperties".equals(source.getName())) {
                continue;
            }
            if (source.getProperty(key) != null) {
                matchingSources.add(source.getName());
            }
        }

        String firstMatch = matchingSources.isEmpty()
                ? "(not found via direct key lookup)"
                : matchingSources.get(0);

        return new Trace(
                environment.getProperty(key),
                firstMatch,
                matchingSources
        );
    }

    public record Snapshot(
            List<String> activeProfiles,
            DemoProperties bound,
            Map<String, Trace> observed
    ) {}

    public record Trace(
            String effectiveValue,
            String firstMatchingSource,
            List<String> matchingSourcesInOrder
    ) {}
}
```

This API intentionally separates **two kinds of evidence**:

- `effectiveValue`: the result of `Environment.getProperty(key)` that the application reads.
- `firstMatchingSource` and `matchingSourcesInOrder`: the names of `PropertySource` instances returning a value for the inspected key, in iteration order. This is a simple observation helper for the lab's sources, **not a complete provenance analyzer** for every kind of alias, import, placeholder, relaxed binding, or custom configuration source.

The `bound` field shows what the `@ConfigurationProperties` object actually received. For the three lab keys, the bound result should match each key's `effectiveValue`. If you extend this API later, continue using an allowlist of keys and never return sensitive values.

An illustrative response under default startup (source names can vary by path and packaging):

```json
{
  "activeProfiles": [],
  "bound": {
    "message": "hello-from-base",
    "region": "local",
    "featureEnabled": false
  },
  "observed": {
    "demo.message": {
      "effectiveValue": "hello-from-base",
      "firstMatchingSource": "Config resource 'class path resource [application.yml]' ...",
      "matchingSourcesInOrder": [
        "Config resource 'class path resource [application.yml]' ..."
      ]
    }
  }
}
```

The JSON example is abbreviated under `observed` for readability; the actual endpoint returns a report for all three keys. **Source names in the example are illustrative**; inspect the output on your own machine for exact names.

## 5. Running the Experiments in Sequence

### Experiment A — Baseline Configuration Only

On macOS/Linux:

```bash
./gradlew bootRun
curl -s http://127.0.0.1:8080/api/config
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
Invoke-RestMethod http://127.0.0.1:8080/api/config
```

Use a second terminal to make the HTTP request while the app is running. Expected observations:

```text
activeProfiles       = []
demo.message         = hello-from-base
demo.region          = local
demo.feature-enabled = false
```

`activeProfiles=[]` means no profile was explicitly activated; it does not mean the application has no configuration. `application.yml` is still loaded.

### Experiment B — Activate the `dev` Profile

Stop the previous process, then run:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
curl -s http://127.0.0.1:8080/api/config
```

Or PowerShell:

```powershell
.\gradlew.bat bootRun --args='--spring.profiles.active=dev'
Invoke-RestMethod http://127.0.0.1:8080/api/config
```

Expected output:

```text
activeProfiles       = [dev]
demo.message         = hello-from-dev
demo.region          = dev-lab
demo.feature-enabled = true
```

Look at `matchingSourcesInOrder` for `demo.message`: you will typically see both the profile-specific source and the baseline source; with no higher-precedence source present, the profile file determines the effective value.

### Experiment C — Environment Variable Overrides File

Stop the app. On macOS/Linux:

```bash
DEMO_MESSAGE=hello-from-env ./gradlew bootRun --args='--spring.profiles.active=dev'
```

On PowerShell:

```powershell
$env:DEMO_MESSAGE = 'hello-from-env'
.\gradlew.bat bootRun --args='--spring.profiles.active=dev'
```

Call `/api/config` again and compare:

```text
demo.message = hello-from-env   # from environment
demo.region  = dev-lab          # still from profile file
```

Changing just one key proves that the external source overrode only that key without wiping out remaining values. After testing in PowerShell, clear the variable from the session to avoid affecting subsequent runs:

```powershell
Remove-Item Env:DEMO_MESSAGE
```

### Experiment D — Command-Line Argument Overrides Environment Variable

On macOS/Linux:

```bash
DEMO_MESSAGE=hello-from-env ./gradlew bootRun \
  --args='--spring.profiles.active=dev --demo.message=hello-from-cli'
```

On PowerShell:

```powershell
$env:DEMO_MESSAGE = 'hello-from-env'
.\gradlew.bat bootRun --args='--spring.profiles.active=dev --demo.message=hello-from-cli'
Remove-Item Env:DEMO_MESSAGE
```

Expect an effective value of `hello-from-cli`. Even though YAML, profile, and environment variable all declare `demo.message`, the CLI argument wins in this experiment. Distinguish `--demo.message=...` (a Spring Boot application argument) from Gradle's own options; `bootRun --args='...'` passes what is inside `--args` to the application.

### Experiment E — Configuration from a File Outside the JAR

Create `external/application.yml` alongside `build.gradle`:

```yaml
demo:
  message: hello-from-external-file
  region: external-lab
```

Run:

```bash
./gradlew bootRun --args='--spring.config.additional-location=optional:file:./external/'
```

PowerShell uses the equivalent command with `.\gradlew.bat`. Inspecting `/api/config` shows values from the additional file are loaded, while `feature-enabled` keeps the baseline value if the external file does not declare it.

`spring.config.additional-location` is processed early while loading config data. The `optional:` prefix lets the app start even if the path does not exist; omit `optional:` when a missing file should fail startup. In real deployments, relative paths depend on the process's working directory, so prefer explicit paths or tightly controlled working directories.

**Caution on ordering:** This demo uses a single additional directory without complex imports or location groups. When using multiple locations and multiple profiles, check the exact config data rules before predicting the winning source.

### Experiment F — Invalid Configuration

Stop the app and intentionally pass an empty value:

```bash
./gradlew bootRun --args='--demo.message='
```

`@NotBlank` on `DemoProperties.message` causes binding/validation to reject the empty value, so the application refuses to start normally. This is the desired behavior: catching missing or invalid configuration at startup is far easier to handle than a delayed runtime business failure.

To recover, remove the empty argument and restart. Do not leave test environment variables or arguments in everyday run configurations.

## 6. Observing with Spring Boot Actuator

With Actuator enabled in `application.yml`, you can call:

```bash
curl -s http://127.0.0.1:8080/actuator/health
curl -s http://127.0.0.1:8080/actuator/env/demo.message
curl -s http://127.0.0.1:8080/actuator/configprops
```

Meaning of each endpoint:

- `/actuator/health`: shows the application is running; does not prove a particular configuration value.
- `/actuator/env/demo.message`: helps look up a property and its source in `Environment`. Values may be masked depending on endpoint configuration.
- `/actuator/configprops`: helps inspect beans using `@ConfigurationProperties`; bound values are normally masked to avoid exposing data.

By comparison, the lab's `/api/config` endpoint shows **visible values** because it only exposes three allowlisted dummy properties; Actuator provides broader **structural metadata** while restricting values. Seeing the two endpoints display differently does not automatically indicate broken binding.

Never enable public access to `env` or `configprops` on real systems just to debug. When production diagnostics are needed, use authentication, authorization, administrative networks, and proper masking policies. Never dump the entire `Environment`, all environment variables, or configuration containing passwords into logs.

## 7. Repeatable Binding Tests

`src/test/java/dev/example/configobserver/DemoPropertiesTest.java`:

```java
package dev.example.configobserver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.message=hello-from-test",
        "demo.region=test-lab",
        "demo.feature-enabled=true"
})
class DemoPropertiesTest {

    @Autowired
    private DemoProperties properties;

    @Test
    void bindsTestProperties() {
        assertEquals("hello-from-test", properties.message());
        assertEquals("test-lab", properties.region());
        assertTrue(properties.featureEnabled());
    }
}
```

Run:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Here the test declares its own configuration inputs, so the result does not depend on whether the runner has `dev` active in another terminal. For more complex tests, you can use `@ActiveProfiles("dev")`, `@TestPropertySource`, or dynamic properties for backing services; pick the mechanism that faithfully reflects the condition under test.

If you want to verify *precedence* between two sources in a test, state clear expectations about both sources and change only one variable at a time. Do not take a passing test as proof that every Spring Boot configuration type follows one simple identical order.

## 8. Experiment Log Table

Fill in actual results from the endpoint rather than copying the expected column:

| Run | Added or Changed Source | Predicted `demo.message` | Actual Value | First Matching Source |
| --- | --- | --- | --- | --- |
| A | `application.yml` only | `hello-from-base` | Fill in | Fill in |
| B | `dev` profile | `hello-from-dev` | Fill in | Fill in |
| C | `DEMO_MESSAGE=hello-from-env` and `dev` | `hello-from-env` | Fill in | Fill in |
| D | Add `--demo.message=hello-from-cli` | `hello-from-cli` | Fill in | Fill in |
| E | `external/application.yml` file | `hello-from-external-file` | Fill in | Fill in |
| F | `--demo.message=` | Startup fails due to validation | Fill in | N/A |

After each run, ask yourself: "Which sources did the application read?", "Did multiple sources declare this key?", "Does the value in `bound` match the effective value?", "Did this run actually start a fresh process?"

## 9. Common Issues and Root-Cause Diagnosis

**Edited `application-dev.yml` but still seeing `hello-from-base`.** Check that `activeProfiles` includes `dev`, the filename is `application-dev.yml`, the file is inside `src/main/resources`, and the app was restarted. If `activeProfiles` is right yet the value is wrong, check whether an environment variable or CLI argument is overriding it.

**Environment variable has a value but does not affect the application.** Verify the variable is set in the environment of the *Java process itself*, not merely in another terminal. Use the proper name (`DEMO_MESSAGE`, `DEMO_FEATURE_ENABLED`) and remember shells/sessions have separate variable scopes. With Gradle `bootRun`, the Gradle process's environment variables are generally passed to the child application.

**`DemoProperties` is not injected or holds an unexpected value.** Check the package, `@ConfigurationPropertiesScan`, the `demo` prefix, key names, data types, and validation annotations. `Environment.getProperty()` and relaxed binding into `@ConfigurationProperties` are not strictly equivalent for all custom keys; check exact keys, naming forms, and active sources when expanding the demo.

**The observation endpoint displays unfamiliar source names.** Spring Boot can add composite sources, test configuration, imported files, or library-provided sources. `PropertySource` names are diagnostic details and can vary by launch method. Rely first on the effective value, active profiles, and sources confirmed to declare the key.

**Values in Actuator are masked.** That may be an intentional endpoint protection policy, especially with `show-values: never`. Do not remove protection just to read sensitive properties. For this lab, the three dummy keys are sufficient to observe precedence.

**An external file is not loaded.** Check the path, working directory, YAML syntax, `file:` prefix, and trailing `/` on directories in `spring.config.additional-location`. If a missing file should fail startup, omit `optional:`.

**Edited a file but the running app did not change.** Check whether you actually restarted. Externalized configuration is processed at startup by default. Dynamic refresh, Spring Cloud Config, or hot reload features have their own lifecycles and prerequisites and are not assumed in this application.

## 10. Extensions After Completing the Basics

Once all six stages run cleanly, you can extend the lab in order:

1. **Placeholders and defaults:** add `demo.banner: "${demo.message:hello}"`, then observe values when the key is provided or missing. Note that placeholders can make explaining "the origin of the final value" subtler than scanning property sources directly.
2. **New configuration groups:** add `demo.timeout` as `Duration` and `demo.max-payload` as `DataSize`, with type-safe binding and validation to highlight the benefits of `@ConfigurationProperties`.
3. **Environment-specific configuration:** add a `test` profile with dummy values and test profile selection. Never put real credentials into committed files.
4. **Inspect advanced sources:** compare `spring.config.import`, config trees, or an external configuration provider. Each source type must be evaluated for loading behavior, precedence, failure when absent, and security policy.
5. **Production observability:** replace the demo API with selective logging of non-sensitive flags and authenticated diagnostics; never expose all configuration keys externally.

Self-check questions:

- If `demo.message` is declared in the base file, `dev` file, environment variable, and CLI, which one has the highest precedence in Experiment D?
- Why does `activeProfiles=[]` still yield a value for `demo.message`?
- Why is `DemoProperties` better than a large group of scattered `@Value` fields as configuration grows?
- Why should a simple `PropertySource` report note its limitations around relaxed binding or placeholders?
- When modifying a YAML file while the application is still running, what should you check before concluding the system picked up the new configuration?
- What risks can arise from an endpoint that exposes all environment variables?

## 11. What to Keep When Applying to Real Projects

The sample application demonstrated the path: **configuration sources → Spring Environment → binding or lookup → application behavior**. When moving from the lab to real systems, prefer strongly typed and validated configuration, declare sensible baseline defaults, organize profiles cleanly, manage secrets through mechanisms built for secrets, restrict management endpoints, and write tests for configuration that governs critical behavior.

Whenever you encounter a value whose origin is unclear, a reliable diagnostic workflow is: identify the canonical key, check active profiles, list sources that could provide the key, inspect the effective value, verify the binding result, and restart under reproducible conditions. That is the core skill this learning path and Config Observer are built to cultivate.
