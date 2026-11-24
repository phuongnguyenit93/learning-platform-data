# Canonical Kebab-Case Key Names in Spring Boot Placeholders

## 1. Why Does Key Casing and Formatting Inside `${...}` Matter?

Spring Boot allows referencing one configuration setting from another, from Java code, or from annotations using **property placeholders**. For example:

```yaml
catalog:
  display-label: "Sample product"

screen:
  title: "${catalog.display-label}"
```

The `${catalog.display-label}` syntax instructs Spring Boot to look up a property named `catalog.display-label` and replace it with its effective value at placeholder resolution time.

However, the same configuration concept can be written in several naming styles depending on the source:

```text
catalog.display-label       # canonical kebab-case
catalog.displayLabel        # camelCase in some files
CATALOG_DISPLAYLABEL        # environment variable per Spring Boot rules
```

`@ConfigurationProperties` has **relaxed binding** to map naming variants onto a Java property. When writing **placeholders**, Spring Boot recommends using **canonical lowercase kebab-case names**, such as `${catalog.display-label}`. This allows the placeholder resolver to apply lookup logic compatible with relaxed binding.

If you write `${catalog.displayLabel}`, the ability to match other variants—especially `catalog.display-label` and its corresponding environment variable—may be restricted. This is a subtle bug: the application works when configuration sits in a test file, yet fails to receive the value when moved to a standardized YAML file or container.

This lesson helps you:

- Identify canonical syntax for multi-level properties.
- Distinguish **key names in sources** from **reference names in placeholders**.
- Use `${key}` and `${key:default}` properly.
- Explain why kebab-case maintains consistency across configuration files, environment variables, and `@ConfigurationProperties`.
- Practice comparing canonical placeholders, camelCase, default values, and override arguments.
- Diagnose "the property exists, yet the placeholder does not pick it up" scenarios.
- Organize key names clearly so they are easy to maintain and less prone to collisions.

**Technical context:** Java 21 and Spring Boot 3.3.x. Examples in this lesson use non-sensitive dummy strings.

## 2. Structure of a Canonical Key Name

A Spring Boot property name is recommended to follow the pattern:

```text
feature-group.sub-property
```

Easy rules to remember:

1. Use **lowercase**.
2. Use a dot `.` to separate **groups/levels** of properties.
3. Use a hyphen `-` to separate words **within the same name segment**.
4. When referencing via a placeholder, use this exact canonical form.
5. Keep one consistent naming convention across all documentation and application-defined keys.

Examples:

| Meaning | Recommended canonical name | Other forms that may appear |
| --- | --- | --- |
| Catalog display label | `catalog.display-label` | `catalog.displayLabel` |
| Client request timeout | `client.request-timeout` | `client.requestTimeout` |
| Maximum retry attempts | `retry.max-attempts` | `retry.maxAttempts` |
| Cache feature flag | `cache.feature-enabled` | `cache.featureEnabled` |
| Remote API base URL | `remote.api-base-url` | `remote.apiBaseUrl` |
| Batch page size | `batch.page-size` | `batch.pageSize` |

A dot does not have the same meaning as a hyphen:

```text
remote.api-base-url
remote.api.base-url
```

The two keys above describe **two different hierarchical structures**. The first places `api-base-url` under `remote`; the second places `base-url` under `remote.api`. Do not replace `.` with `-` or vice versa just to make a name look more uniform.

Similarly:

```text
catalog.display-label
catalog.display.label
```

may both be valid keys, but they should not be treated as the same property simply because they share the same English words.

### 2.1. Canonical Does Not Mean Java Variable Names

In Java, fields and record components are usually written in camelCase:

```java
public record CatalogProperties(String displayLabel) {}
```

That is Java syntax convention. In YAML and placeholders, the recommended style is instead:

```yaml
catalog:
  display-label: "Sample product"
```

```java
@Value("${catalog.display-label}")
private String displayLabel;
```

Spring Boot can bind `catalog.display-label` to the Java field `displayLabel`. **Java naming is not a reason to turn the placeholder into `${catalog.displayLabel}`.**

### 2.2. Canonical Does Not Require Every Source to Use the Same Character Style

A standard environment variable cannot use `.` or `-` in the way `.properties` or YAML files do. Spring Boot supports mapping property names to environment variable style, so **the name you enter in the OS** and **the name you reference in code** can differ.

Example:

```text
Canonical name:         catalog.display-label
Environment variable:   CATALOG_DISPLAYLABEL
Placeholder in code:    ${catalog.display-label}
```

The purpose of the canonical form is to provide **one stable reference name** regardless of which source supplies the value.

## 3. How Placeholders and Relaxed Binding Relate

Distinguish two mechanisms:

- **Property placeholder:** `${...}` references a value from `Environment` and substitutes it into another string or a `@Value` injection point.
- **Configuration properties binding:** `@ConfigurationProperties` groups multiple keys and binds them to properties of a Java bean, with its own name-mapping and type-conversion rules.

Suppose YAML contains:

```yaml
catalog:
  display-label: "from-yaml"
```

Java:

```java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String displayLabel) {}
```

The binder can map from `display-label` to `displayLabel`. With placeholders, reference:

```java
@Value("${catalog.display-label}")
String displayLabel;
```

This style lets Spring Boot use relaxed-binding-compatible logic to locate the value when the name in a source has variants.

Comparison:

```text
RECOMMENDED
${catalog.display-label}

PRONE TO MATCHING LIMITATIONS
${catalog.displayLabel}
```

A classic example in Spring Boot 3.3:

- `${demo.item-price}` can consider `demo.item-price` and `demo.itemPrice` in configuration files as well as the corresponding environment form `DEMO_ITEMPRICE`.
- `${demo.itemPrice}` does not have the same ability to match `demo.item-price` and `DEMO_ITEMPRICE`.

This does not mean every arbitrary combination of uppercase letters, underscores, dots, or casing is equivalent. Relaxed naming rules depend on the source, the nature of the property, and the queried name form. Therefore, **learning and using canonical names** is more sustainable than memorizing individual variants that happen to work by coincidence.

### 3.1. Source Precedence Still Applies

Canonical form helps with name resolution. It **does not change the precedence order** among YAML files, profile files, environment variables, Java system properties, and command-line arguments.

Example:

```yaml
catalog:
  display-label: "from-file"
```

If the process also has a valid environment variable:

```text
CATALOG_DISPLAYLABEL=from-env
```

then under normal rules, the environment value takes precedence over the application file. The canonical placeholder receives the effective value after Spring Boot processes the sources. Do not treat the placeholder returning `from-env` as proof that the YAML file was not loaded; the file can still contribute other properties.

## 4. Three Places to Keep Key Names Consistent

### 4.1. In `application.properties`

Direct style:

```properties
catalog.display-label=from-properties
ui.header-text=${catalog.display-label}
```

In `application.properties`, `.` expresses hierarchy within the key name itself, while `-` stays inside a segment.

### 4.2. In `application.yaml`

Nested style:

```yaml
catalog:
  display-label: "from-yaml"

ui:
  header-text: "${catalog.display-label}"
```

YAML nesting produces a structure equivalent to `catalog.display-label`. If a flat key is needed, you can write:

```yaml
catalog.display-label: "from-yaml"
```

though for large groups of properties, nesting is usually easier to read.

### 4.3. In Java `@Value`

```java
@Value("${catalog.display-label}")
private String catalogLabel;
```

`@Value` also supports default values:

```java
@Value("${catalog.display-label:Label not set}")
private String catalogLabel;
```

Remember: after `:` is the placeholder's fallback **when the property is not resolved**, not a profile name or property type. The property name in the expression should still be canonical.

## 5. Environment Variable Rules: Dots, Hyphens, and Underscores

Spring Boot follows a common rule for converting a canonical name to an environment variable name:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-`.
3. Convert the name to uppercase.

Examples:

| Canonical property | Corresponding environment variable |
| --- | --- |
| `catalog.display-label` | `CATALOG_DISPLAYLABEL` |
| `client.request-timeout` | `CLIENT_REQUESTTIMEOUT` |
| `cache.feature-enabled` | `CACHE_FEATUREENABLED` |
| `remote.api-base-url` | `REMOTE_APIBASEURL` |
| `retry.max-attempts` | `RETRY_MAXATTEMPTS` |
| `batch.page-size` | `BATCH_PAGESIZE` |

The most common confusion is:

```text
CATALOG_DISPLAYLABEL   # corresponds to catalog.display-label
CATALOG_DISPLAY_LABEL  # usually represents nested levels catalog.display.label
```

Similarly, do not write `CLIENT_REQUEST_TIMEOUT` and assume it always maps identically to `client.request-timeout`. In other configuration systems, conventions may differ; this lesson follows Spring Boot's relaxed binding mechanism.

A container example:

```yaml
# Partial container configuration, illustrating only the env field.
env:
  - name: CATALOG_DISPLAYLABEL
    value: "from-container"
```

In application code, still use:

```java
@Value("${catalog.display-label}")
String label;
```

This keeps the configuration contract consistent across local runs, Docker deployments, and managed variable environments.

### 5.1. Hyphens Are Removed, Not Replaced with Underscores

Look again at the key:

```text
service.mail-server-host
```

It represents two levels: `service` and `mail-server-host`. The environment variable name is:

```text
SERVICE_MAILSERVERHOST
```

If you manually replace every hyphen with `_`, you get:

```text
SERVICE_MAIL_SERVER_HOST
```

The second name can be interpreted as levels `service.mail.server.host`, different from the original structure. This is a real-world cause of an environment variable "existing in the container" yet the canonical placeholder failing to receive the expected value.

### 5.2. Avoid Designing Two Easily Colliding Keys

If a configuration group intentionally contains both:

```text
feature.my-flag
feature.myflag
```

then when mapped under environment variable rules, both keys can collapse to the same collision-prone form. Do not create names distinguished only by hyphens when the application must support multiple source styles. Choose semantically independent names, use clear hierarchy, and test critical deployment cases.

## 6. Default Value Syntax `${key:default}`

Placeholders generally take two forms:

```text
${key}
${key:default}
```

With `${catalog.display-label}`, if no source supplies the key and the placeholder resolver requires resolution, the application can throw an error during startup or bean creation.

With:

```yaml
ui:
  header-text: "${catalog.display-label:Catalog}"
```

Spring Boot uses `Catalog` when `catalog.display-label` cannot be resolved.

Key points:

- **The fallback belongs to the placeholder**; it does not automatically create a new property named `catalog.display-label` in `Environment`.
- Fallbacks are used when the property has no resolvable value; do not assume an empty string, whitespace-only string, or wrong-type value will always trigger the fallback.
- If the value contains `:` such as a URL, write the expression clearly and test it in context.
- Placeholders can be nested, but many layers of fallbacks make configuration hard to read without a clear reason.

Nested example:

```yaml
ui:
  header-text: "${catalog.display-label:${defaults.display-label:Catalog}}"
```

Meaning: prefer `catalog.display-label`; if missing, read `defaults.display-label`; if both are missing, use `Catalog`.

Although you could write:

```yaml
ui:
  header-text: "${catalog.displayLabel:Catalog}"
```

this is not a good choice. Fix **the key name inside the placeholder** to canonical form instead of adding a fallback to hide a source mapping bug.

## 7. Sample Application: Canonical Placeholder Observer

We will create a small Spring Boot console application to observe **the same key referenced in two ways**, while also binding into `@ConfigurationProperties`. The program prints:

- The YAML file value of a sample configuration property.
- The value received via `@Value` with a canonical placeholder.
- The value received via `@Value` with a camelCase placeholder for comparison.
- The value via a `@ConfigurationProperties` bean.
- The value of a placeholder with a fallback.

The program uses only public dummy data for learning; it does not print secrets or all environment variables.

### 7.1. Project Structure

```text
canonical-placeholder/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/placeholder/
    │   │   ├── CanonicalPlaceholderApplication.java
    │   │   ├── CatalogProperties.java
    │   │   └── PlaceholderReport.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/placeholder/
            └── CanonicalPlaceholderTest.java
```

You can generate the project from Spring Initializr with Java 21 and Spring Boot 3.3.x using Gradle. No web dependency is needed since the application only prints a report. Use the project's Gradle Wrapper (`gradlew` and `gradlew.bat`) rather than relying on a globally installed Gradle version.

### 7.2. Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'canonical-placeholder'
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

In a repository with its own build conventions, follow the Spring Boot and Gradle versions used by that repository. The Gradle file above only illustrates a standalone project.

### 7.3. Baseline YAML Declaration

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

catalog:
  display-label: "from-kebab-file"

ui:
  canonical-title: "${catalog.display-label:missing}"
  camel-title: "${catalog.displayLabel:missing}"
  subtitle: "${catalog.subtitle:No subtitle configured}"
```

In this file, `catalog.display-label` is in canonical form; there is no `catalog.displayLabel` as an independent key name.

The two properties `ui.canonical-title` and `ui.camel-title` let you observe how placeholders resolve. At runtime, `ui.canonical-title` is expected to receive the value from `catalog.display-label`, whereas `ui.camel-title` may receive the `missing` fallback because the reference is non-canonical.

`ui.subtitle` demonstrates standard fallback syntax: `catalog.subtitle` does not exist, so the result is `No subtitle configured`.

### 7.4. Application Entry Point

`src/main/java/dev/example/placeholder/CanonicalPlaceholderApplication.java`:

```java
package dev.example.placeholder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CanonicalPlaceholderApplication {

    public static void main(String[] args) {
        SpringApplication.run(CanonicalPlaceholderApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` discovers the binding record class below.

### 7.5. Creating the Typed Binding Bean

`src/main/java/dev/example/placeholder/CatalogProperties.java`:

```java
package dev.example.placeholder;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String displayLabel) {}
```

The name `displayLabel` in the record uses camelCase because that is Java convention. With `catalog.display-label` in YAML, the Spring Boot binder can create a bean whose `displayLabel()` equals `from-kebab-file`.

This is the key contrast: **the binder supports relaxed binding**; placeholders should use canonical names so compatible name-lookup logic is applied.

### 7.6. Printing the Report by Access Method

`src/main/java/dev/example/placeholder/PlaceholderReport.java`:

```java
package dev.example.placeholder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class PlaceholderReport {

    @Bean
    ApplicationRunner printReport(
            Environment environment,
            CatalogProperties catalog,
            @Value("${catalog.display-label:missing}")
            String canonicalValue,
            @Value("${catalog.displayLabel:missing}")
            String camelValue,
            @Value("${ui.canonical-title:missing}")
            String uiCanonical,
            @Value("${ui.camel-title:missing}")
            String uiCamel,
            @Value("${ui.subtitle:missing}")
            String subtitle) {
        return args -> {
            System.out.println("=== CANONICAL PLACEHOLDER ===");
            System.out.println("canonical @Value = " + canonicalValue);
            System.out.println("camelCase @Value = " + camelValue);
            System.out.println("bound displayLabel = "
                    + catalog.displayLabel());
            System.out.println("ui.canonical-title = " + uiCanonical);
            System.out.println("ui.camel-title = " + uiCamel);
            System.out.println("ui.subtitle = " + subtitle);
            System.out.println("Environment canonical = "
                    + environment.getProperty("catalog.display-label"));
        };
    }
}
```

The program intentionally places both references side by side to demonstrate the naming difference. In real business code, use `@ConfigurationProperties` for groups of properties and only use `@Value` when a single isolated value is genuinely needed.

`Environment.getProperty("catalog.display-label")` inspects the value by its canonical name. It is not a substitute for secret-protection policies or a complete property-origin reporting tool.

### 7.7. Running the Program

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

With the baseline file above, the notable lines are:

```text
canonical @Value = from-kebab-file
camelCase @Value = missing
bound displayLabel = from-kebab-file
ui.canonical-title = from-kebab-file
ui.camel-title = missing
ui.subtitle = No subtitle configured
Environment canonical = from-kebab-file
```

If a line on another machine differs from expectations, check external value sources before drawing conclusions about the placeholder mechanism. Environment variables or CLI arguments may be supplying another name form or overriding the value.

## 8. Experiment A: Changing the Key in the File to camelCase

Edit the `catalog` section of `application.yaml` to:

```yaml
catalog:
  displayLabel: "from-camel-file"
```

Keep the placeholders unchanged:

```yaml
ui:
  canonical-title: "${catalog.display-label:missing}"
  camel-title: "${catalog.displayLabel:missing}"
```

Restart the application. Key expectations:

```text
canonical @Value = from-camel-file
camelCase @Value = from-camel-file
bound displayLabel = from-camel-file
```

Both references can see the value in camelCase form. However, the fact that the camelCase reference **works in this experiment** does not make it a better style. The difference becomes clearer when switching back to kebab-case or using environment variables.

After the experiment, restore the original YAML with:

```yaml
catalog:
  display-label: "from-kebab-file"
```

and remember to restart. Standard externalized configuration is loaded at application startup; editing the file does not automatically update running beans.

## 9. Experiment B: Environment Variable Overrides the File

With the original baseline file:

```yaml
catalog:
  display-label: "from-kebab-file"
```

provide the environment variable following canonical rules:

```text
CATALOG_DISPLAYLABEL=from-env
```

macOS/Linux (Bash):

```bash
CATALOG_DISPLAYLABEL=from-env ./gradlew bootRun
```

Windows PowerShell:

```powershell
$env:CATALOG_DISPLAYLABEL = 'from-env'
.\gradlew.bat bootRun
Remove-Item Env:CATALOG_DISPLAYLABEL
```

Notable results:

```text
canonical @Value = from-env
bound displayLabel = from-env
ui.canonical-title = from-env
```

The canonical placeholder and bean binding read the higher-precedence environment source. The placeholder `${catalog.displayLabel:missing}` is not fully equivalent to `${catalog.display-label:missing}`; in this experiment it may fall back to `missing` if no source defines the exact form it queries.

Verify the environment variable name before running. If you declare:

```text
CATALOG_DISPLAY_LABEL=from-env
```

that is not the standard mapped name for `catalog.display-label` under the hyphen-removal rule. It usually represents a property structure with an extra separator level.

When using Gradle `bootRun`, the Java process environment typically inherits from the Gradle process. When running in Docker or CI, ensure the variable is present in **the environment of the process actually running the application**, not just in another terminal or pipeline step.

## 10. Experiment C: CLI Override and Why Canonical Is Still Needed

Stop the application and run:

```bash
./gradlew bootRun --args='--catalog.display-label=from-cli'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--catalog.display-label=from-cli"
```

Expected:

```text
canonical @Value = from-cli
bound displayLabel = from-cli
```

The application argument `--catalog.display-label=...` supplies the canonical name and by default takes precedence over application files. Although some camelCase argument syntax may also be handled by the framework, keep one canonical convention across CLI, YAML, and placeholders to avoid confusion across environments.

Distinguish that `--args="..."` is an option of the Gradle `bootRun` task, while `--catalog.display-label=...` inside it is a **Spring Boot argument**. If running the JAR directly:

```bash
./gradlew bootJar
java -jar build/libs/canonical-placeholder-0.0.1-SNAPSHOT.jar \
  --catalog.display-label=from-cli
```

The JAR file name may differ when build conventions or project versions change; use the project's actual artifact name.

## 11. Experiment D: Fallbacks and Nested Placeholders

### 11.1. When a Property Is Absent

YAML:

```yaml
ui:
  subtitle: "${catalog.subtitle:No subtitle configured}"
```

Because `catalog.subtitle` does not exist yet, Spring Boot uses the default string. If you add:

```yaml
catalog:
  display-label: "from-kebab-file"
  subtitle: "Promotion active"
```

then `ui.subtitle` pulls from `catalog.subtitle`.

### 11.2. When There Are Two Fallback Levels

Change to:

```yaml
ui:
  subtitle: "${catalog.subtitle:${defaults.subtitle:No subtitle configured}}"
```

Meaning:

1. Prefer `catalog.subtitle`.
2. If missing, use `defaults.subtitle`.
3. If both are missing, use `No subtitle configured`.

This is a valid example of a **nested placeholder**, though you should not overuse deep nesting in real systems: operators will struggle to tell which source determines the final value.

### 11.3. When the Value Is Intentionally an Empty String

If a source declares:

```properties
catalog.subtitle=
```

then the property may be considered **present with an empty string**. The `${catalog.subtitle:...}` fallback is not a check for "whether the string has meaningful text." If you need to reject blank strings, use validation in `@ConfigurationProperties`, such as `@NotBlank`, or explicit business rules.

### 11.4. If the Property Is Required

For configuration needed for the application to function, silently using a fallback can hide deployment errors. You can omit the fallback:

```java
@Value("${catalog.display-label}")
String displayLabel;
```

or use `@ConfigurationProperties` with appropriate validation. Fallback decisions should be based on business semantics, not on a desire to force the program to start at all costs.

## 12. Testing Behavior with Spring Boot Test

When renaming keys in YAML or migrating from files to environment variables, tests can verify that the configuration contract still holds.

Example:

`src/test/java/dev/example/placeholder/CanonicalPlaceholderTest.java`:

```java
package dev.example.placeholder;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "catalog.display-label=from-test"
})
class CanonicalPlaceholderTest {

    @Autowired
    CatalogProperties catalog;

    @Test
    void bindsCanonicalKeyToCamelCaseJavaComponent() {
        assertEquals("from-test", catalog.displayLabel());
    }
}
```

Run:

```bash
./gradlew test
```

On PowerShell:

```powershell
.\gradlew.bat test
```

This test verifies that a **canonical name** in a configuration source binds to a camelCase Java field. For more complex systems, write tests for key sources and important defaults instead of assuming every naming variant is supported by the library.

To test placeholders directly, a bean using `@Value("${catalog.display-label}")` can be injected in the test context, then asserted against the `catalog.display-label=from-test` input. Note that if multiple sources declare the same key, the test also needs to control precedence order and active profiles.

### 12.1. A Quick Check with Both Key Forms

Place side by side:

```yaml
catalog:
  display-label: "from-kebab"
```

and:

```java
@Value("${catalog.display-label:missing}")
String canonical;

@Value("${catalog.displayLabel:missing}")
String nonCanonical;
```

When running the lab, compare both results. Then change **only one factor**: rename the YAML key to `displayLabel`. Compare the results again.

The takeaway is that **a non-canonical placeholder may happen to work with one declaration style**, yet easily lose compatibility with others. Using canonical names eliminates inconsistency at the point of reference.

## 13. Common Key Naming Mistakes

### 13.1. Using camelCase in Placeholders Because the Java Field Is camelCase

```java
// Not recommended as a convention
@Value("${client.requestTimeout:5s}")
String timeout;
```

While the file uses:

```yaml
client:
  request-timeout: 5s
```

Fix:

```java
@Value("${client.request-timeout:5s}")
String timeout;
```

The record component name `requestTimeout` stays unchanged. Only normalize the property inside `${...}`.

### 13.2. Replacing Hyphens with Dots

```text
Intended:          service.connection-timeout
Different key:     service.connection.timeout
```

If you use a new key with an extra dot, that is a structural change, not merely a style tweak. Align configuration schemas, files, environment variables, and binding types before deploying.

### 13.3. Misnaming Environment Variables

```text
APP_FEATUREENABLED   # corresponds to app.feature-enabled
APP_FEATURE_ENABLED  # usually interpreted as app.feature.enabled
```

When a value from Docker is not picked up, verify the exact variable name after canonical conversion. Do not add a slew of aliases in code just to work around a typo in a manifest.

### 13.4. Writing Uppercase in Placeholders

```java
@Value("${CATALOG_DISPLAYLABEL}")
String label;
```

That syntax targets an environment-specific property name, coupling code to the deployment style. If the intent is to read the Spring Boot property `catalog.display-label`, use:

```java
@Value("${catalog.display-label}")
String label;
```

This keeps Java code independent of whether the value comes from YAML, CLI, or environment variables.

### 13.5. Using Fallbacks to Mask Key Name Errors

```yaml
ui:
  title: "${catalog.displayLabel:Catalog}"
```

If the file actually contains `catalog.display-label`, the fallback may cause the application to return `Catalog`, misleading developers into thinking operators did not configure it. The best fix is:

```yaml
ui:
  title: "${catalog.display-label:Catalog}"
```

Only after the canonical name is right should you decide whether a fallback is appropriate.

### 13.6. Mixing Two Similar Keys in the Same File

```properties
catalog.displayLabel=from-camel
catalog.display-label=from-kebab
```

This configuration makes binding and placeholder resolution unpredictable because two close representations exist for the same concept. Choose a single canonical key, migrate values to it, and remove ad-hoc aliases unless an explicit compatibility contract requires them.

### 13.7. Forgetting Higher-Precedence Sources

You edit `application.yaml`, yet the `CATALOG_DISPLAYLABEL` environment variable or CLI still has a different value. The canonical placeholder returns the higher-precedence source. That is correct Externalized Configuration behavior, not a sign that kebab-case is ignored.

### 13.8. Expecting New Values to Take Effect Immediately

Spring Boot typically processes configuration files and injects/binds values at startup. If you edit YAML while the process is running, `@Value` or `@ConfigurationProperties` beans do not automatically update in a basic setup. Restart the application or use a dedicated refresh mechanism; such mechanisms have their own lifecycle and constraints.

## 14. Workflow for Diagnosing a Placeholder Not Receiving Its Value

When encountering an example like:

```java
@Value("${catalog.displayLabel:missing}")
String label;
```

and the result is unexpected, you can step through:

1. **Identify what the property means.** In this example, it is "catalog display label," not some secondary property.
2. **Rewrite the canonical name.** Under the current schema, it is `catalog.display-label`.
3. **Check where the value is declared.** `application.yaml`, `application-dev.yaml`, an external file outside the JAR, environment variables, system properties, or CLI.
4. **Update the placeholder to canonical form.** Use `${catalog.display-label:missing}`.
5. **Check environment variable mapping.** If the source is the OS, use `CATALOG_DISPLAYLABEL` per canonical rules.
6. **Check profiles and locations.** A file existing does not mean it is loaded; the profile might not be active or the location might have been replaced via `spring.config.location`.
7. **Check precedence.** Is another source declaring the same property with higher precedence?
8. **Restart cleanly and observe.** Keep only one variable changed per attempt, and record the effective value from the application.
9. **Check fallbacks.** If the application returns the default string, distinguish between a genuinely missing property and a misspelled name.
10. **Retest the configuration contract.** Add tests for the canonical name used by the application and documentation.

In a lab exercise, you can use `Environment.getProperty("catalog.display-label")` to inspect a dummy key. If using Actuator `/actuator/env` in a test environment, restrict access and do not automatically expose sensitive values. There is no need to dump the entire `Environment` just to inspect one specific property.

## 15. Distinguishing Placeholders, SpEL, and Shell Expansion

Three syntaxes may look similar but are processed at different layers:

| Syntax | Who processes it? | Example |
| --- | --- | --- |
| `${catalog.display-label}` | Spring's property placeholder resolver | `@Value("${catalog.display-label}")` |
| `#{...}` | Spring Expression Language (SpEL), in supported contexts | `@Value("#{2 * 3}")` |
| `${VAR}` in a shell script | The shell, before Java receives arguments | `echo "${HOME}"` |

Do not equate `${...}` syntax in YAML files with shell expansion. In Spring configuration, Spring processes placeholders; in a shell, the command interpreter may process the string before launching the application. When writing test commands containing `$`, use appropriate quoting to avoid unintended shell substitution.

For example, passing a literal placeholder in a Bash command may require single quotes to preserve `$`, whereas when you actually want to pass a property value you normally just run:

```bash
./gradlew bootRun --args='--catalog.display-label=from-cli'
```

This distinction matters when writing deployment scripts, CI pipelines, and Docker entrypoints: shell expansion errors can occur before Spring Boot ever sees the configuration.

## 16. When to Prefer `@ConfigurationProperties` Over `@Value`

For a single value, `@Value("${catalog.display-label}")` is easy to read. But when multiple related properties exist, consider:

```yaml
client:
  base-url: "https://api.example.test"
  connection-timeout: 3s
  max-attempts: 4
```

Binding bean:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        java.net.URI baseUrl,
        java.time.Duration connectionTimeout,
        int maxAttempts
) {}
```

Spring Boot binds the property group into the record with `URI`, `Duration`, and `int` types. This is the right mechanism for structured, validated configuration reused across multiple places.

Meanwhile, placeholders usually appear when you want to use **the value of one property inside another property's value**, such as:

```yaml
client:
  base-url: "https://api.example.test"

report:
  endpoint: "${client.base-url}/reports"
```

Even when the Java bean uses camelCase `baseUrl`, the name inside the placeholder remains **`client.base-url`**.

Note that Spring Boot supports deep relaxed binding and type conversion for `@ConfigurationProperties`, whereas `@Value` is not a mirror of the entire binder feature set. The more properties you have, the more centralizing them in a typed bean reduces reliance on scattered placeholder strings.

## 17. Practice Exercises

Write out the canonical name and corresponding environment variable for the following fields:

| Java property | Prefix | Expected canonical | Environment variable |
| --- | --- | --- | --- |
| `requestTimeout` | `client` | `client.request-timeout` | `CLIENT_REQUESTTIMEOUT` |
| `featureEnabled` | `search` | `search.feature-enabled` | `SEARCH_FEATUREENABLED` |
| `maxRetries` | `worker` | `worker.max-retries` | `WORKER_MAXRETRIES` |
| `displayName` | `product` | `product.display-name` | `PRODUCT_DISPLAYNAME` |
| `baseUrl` | `proxy.upstream` | `proxy.upstream.base-url` | `PROXY_UPSTREAM_BASEURL` |

Next, consider these questions:

**Question 1.** A YAML file contains `client.request-timeout`. Should you use `${client.requestTimeout}` or `${client.request-timeout}`? Why?

**Question 2.** Which environment variable corresponds to `search.feature-enabled` under canonical rules: `SEARCH_FEATURE_ENABLED` or `SEARCH_FEATUREENABLED`?

**Question 3.** If both a YAML file and an environment variable define the same property, does a canonical placeholder automatically pick the newly edited file or the higher-precedence value in `Environment`?

**Question 4.** How is `${catalog.subtitle:Default subtitle}` evaluated when the property is missing? If the property exists with an empty string value, will `Default subtitle` always be used?

**Question 5.** Why shouldn't `feature.search-timeout` and `feature.search.timeout` be used interchangeably?

**Question 6.** You have a record `ClientProperties(Duration connectTimeout)`. How should the key name be written in YAML and in placeholders?

**Question 7.** Why doesn't a camelCase placeholder returning the right value on a developer's machine guarantee compatibility when deployed with environment variables?

**Question 8.** Do you need to rename the Java field `displayLabel` to `display-label` to match canonical style?

Hints:

1. `${client.request-timeout}`, because it is the canonical reference name.
2. `SEARCH_FEATUREENABLED` (remove hyphens, replace dots with underscores, uppercase).
3. The effective value according to property source precedence order.
4. Fallbacks apply when the property cannot be resolved; empty strings are a separate case to handle explicitly.
5. Dots create a different property hierarchy level.
6. `client.connect-timeout` in YAML and `${client.connect-timeout}` in placeholders; Java stays `connectTimeout`.
7. Because camelCase in placeholders can prevent resolving the corresponding relaxed names.
8. No; Java still uses camelCase, while YAML/placeholders use kebab-case.

## 18. Convention Template for Real Projects

A development team can document its convention as follows:

```text
Property keys:       canonical kebab-case, hierarchy separated by dots.
Java fields:         camelCase.
YAML/properties:     use canonical form.
@Value placeholders: use ${canonical.property-name}.
Default values:      only add when business-meaningful.
Environment vars:    dot -> underscore, hyphen -> removed, uppercase.
Secrets:             managed in a secure source, never logged.
```

End-to-end example:

```yaml
# application.yaml
notification:
  sender-name: "System"
  retry-delay: 5s

mail:
  sender-label: "${notification.sender-name}"
```

```java
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        String senderName,
        java.time.Duration retryDelay
) {}
```

```text
Environment variable:
NOTIFICATION_SENDERNAME=Operations

Placeholder:
${notification.sender-name}

Effective value by source and precedence:
Operations
```

Keeping placeholder names canonical keeps configuration readable as it moves from packaged files to external files, from laptops to containers, or from tests to production. Whenever something goes wrong, check **the canonical key name, the actual source name, the source's mapping, and precedence order**. Starting from these four factors usually finds the root cause faster than tweaking fallbacks or adding ad-hoc aliases.

### References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), **Property Placeholders** section and usage of canonical names.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), **Relaxed Binding** and **Binding From Environment Variables** sections.
- [Spring Framework — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html), on placeholders and value expressions in beans.