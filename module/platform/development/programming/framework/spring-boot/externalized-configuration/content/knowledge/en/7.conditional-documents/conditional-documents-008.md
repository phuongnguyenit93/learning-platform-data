# Limitations of Loading Multi-Document Files via @PropertySource and @TestPropertySource in Spring Boot 3.3

## 1. Core issue

In Spring Boot 3.3, a configuration file can consist of multiple **logical documents** placed inside the same physical file. Documents are separated by `---` for YAML or `#---`/`!---` for `.properties`. Spring Boot's **Config Data** mechanism recognizes each document, applies `spring.config.activate.*` conditions, and adds valid documents to `Environment` in precedence order.

By contrast, Spring Framework annotations such as:

- `@PropertySource`: declares a property source on a `@Configuration` class.
- `@TestPropertySource`: supplies additional files or inline properties to the `ApplicationContext` in tests.

**do not automatically use Spring Boot's multi-document Config Data loader**. Consequently:

1. Multi-document `.properties` files **are not processed with multi-document semantics** when loaded through these two annotations. To a standard properties loader, `#---`/`!---` lines are merely comments; a `spring.config.activate.on-profile` condition does not toggle the section after the separator on or off.
2. YAML files in general **are not directly supported by these two annotations with the default factory**, even single-document YAML. Spring Framework 6.1 (shipped with Spring Boot 3.3) allows configuring a custom `PropertySourceFactory`, yet a custom factory for reading YAML **does not automatically gain full Config Data semantics**, especially document activation conditions.
3. If you need **multi-document support, profile/cloud activation, and precedence between documents**, use `application.properties`/`application.yaml` loaded by Spring Boot via Config Data, or a valid `spring.config.import`/`spring.config.location`.

This is a **limitation of the loading mechanism**, not a syntax error in the `.properties`/YAML file: the exact same file can work properly through Config Data while producing different results when read as an ordinary `PropertySource`.

## 2. What is multi-document?

### 2.1. A `.properties` file with two documents

```properties
# src/main/resources/application.properties
demo.mode=standard
demo.endpoint=https://api.example.test

#---
spring.config.activate.on-profile=dev
demo.mode=development
demo.endpoint=http://localhost:8080
```

When the **Config Data loader** loads this file:

- Document 1 has no condition, so `demo.mode=standard` and `demo.endpoint=https://api.example.test` serve as shared configuration.
- Document 2 is activated only if the `dev` profile expression matches.
- If `dev` is not active, document 2 is unused; shared values remain intact.
- If `dev` is active, document 2 is added afterward and can override `demo.mode` and `demo.endpoint` to the dev values.

Example runs:

```bash
java -jar myapp.jar
# demo.mode: standard (if dev is not activated)

java -jar myapp.jar --spring.profiles.active=dev
# demo.mode: development
```

These are the semantics Spring Boot describes under **Working With Multi-Document Files** and **Activation Properties**.

### 2.2. YAML equivalent

```yaml
# src/main/resources/application.yaml
demo:
  mode: standard
  endpoint: https://api.example.test
---
spring:
  config:
    activate:
      on-profile: dev
demo:
  mode: development
  endpoint: http://localhost:8080
```

In YAML, `---` is standard document-separation syntax. Within Config Data, Spring Boot can load multiple YAML documents, flatten them into property key-value pairs, and apply `spring.config.activate.on-profile` per document.

Do not use `#---` to separate YAML documents: in YAML that is merely a comment line with no document-splitting behavior. Conversely, for `.properties`, use `#---` or `!---`, not a bare `---`.

### 2.3. Separator rules for `.properties`

According to Spring Boot 3.3:

- The separator must be `#---` or `!---`, placed at the **start of the line**, with no leading whitespace.
- It must have **exact three dashes**.
- The lines immediately before and immediately after the separator **must not share the same comment prefix** as the separator.
- Valid documents are processed **from top to bottom**; a later document can override matching keys from an earlier document when both are active.

Readable formatting example:

```properties
demo.mode=standard
#---
spring.config.activate.on-profile=dev
demo.mode=development
```

The following example is **not a valid separator** because of leading indentation:

```properties
demo.mode=standard
  #---
spring.config.activate.on-profile=dev
demo.mode=development
```

A `#---` in the right place is special syntax understood by **Spring Boot Config Data**. Traditional `java.util.Properties` readers treat it as a comment line; they have no concept of a "second document".

## 3. Per-document applicability conditions: `spring.config.activate.*`

Spring Boot 3.3 supports typical activation properties:

| Property | Meaning in Config Data |
| --- | --- |
| `spring.config.activate.on-profile` | Activates the document only when the profile expression matches, e.g. `dev`, `prod | staging`, `!prod`. |
| `spring.config.activate.on-cloud-platform` | Activates the document only if the environment is detected as the matching cloud platform, e.g. `kubernetes`. |

Example `.properties` with two conditions:

```properties
app.label=generic
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
app.label=k8s-runtime
```

The second document takes effect only when **both conditions** of the document are met: profiles match one of `prod` or `staging`, and Spring Boot detects the cloud platform as `kubernetes`. If the conditions are not met, `app.label` keeps the `generic` value from the shared document, unless overridden by another source.

**Do not confuse with `@Profile` on beans:** `spring.config.activate.on-profile` is a **Config Data document** activation mechanism, whereas `@Profile` filters beans/`@Configuration`. Both mechanisms can depend on profile names, yet they operate at different processing layers.

A document can contain regular properties, such as `app.label`, along with the condition controlling whether that document loads. Conditions **are only applied when the document itself is processed by the Config Data loader**.

## 4. How does `@PropertySource` load files?

`@PropertySource` is a **Spring Framework** annotation, typically placed on a `@Configuration` class:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:/settings/features.properties")
public class FeatureSettingsConfiguration {
}
```

With the default factory, Spring Framework reads resources in **properties/XML properties** format and adds the key–value pairs to `Environment`. This is a valid way to add **simple** properties that do not require Spring Boot Config Data multi-document interpretation.

Single-part file example:

```properties
# src/main/resources/settings/features.properties
feature.search.enabled=true
feature.search.max-results=20
```

You can read `feature.search.enabled` and `feature.search.max-results` via `Environment` or appropriate binding.

What is **missing** when using the default annotation is logic to:

- Recognize `#---` as a boundary between multiple Config Data documents.
- Interpret each document's `spring.config.activate.on-profile`.
- Interpret `spring.config.activate.on-cloud-platform` to exclude a document.
- Apply file/profile selection rules and document order like Boot's Config Data loader.

Therefore, **"loading one file as a PropertySource" and "loading a multi-document file via Config Data" are two different behaviors**.

### When `@PropertySource` is processed

`@PropertySource` on `@Configuration` is added during `ApplicationContext` refresh. This is also **later** than the stage where Spring Boot determines Config Data search locations and early bootstrap settings like logging or `spring.main.*`.

Do not put `spring.config.location` or `spring.config.name` inside a file loaded via `@PropertySource` expecting them to redirect the initial loading of `application.*`.

## 5. Clear failure example: same file, different results

Suppose we have the file:

```properties
# src/main/resources/settings/modes.properties
demo.mode=standard
#---
spring.config.activate.on-profile=prod
demo.mode=production
```

### Approach A: loading via Config Data

In `src/main/resources/application.properties`:

```properties
spring.config.import=classpath:/settings/modes.properties
```

When the `prod` profile is not enabled, the value from the imported file is:

```text
demo.mode=standard
```

When running `--spring.profiles.active=prod`, the second document of the imported file is activated, so:

```text
demo.mode=production
```

This example assumes no higher-precedence source overrides `demo.mode`.

### Approach B: loading directly via `@PropertySource`

```java
@Configuration
@PropertySource("classpath:/settings/modes.properties")
public class ModeConfiguration {
}
```

With standard `.properties` parsing, `#---` is a comment and both `demo.mode=...` lines reside in the same property set. When a key appears multiple times, the later value can overwrite the earlier value in the map produced by the parser:

```text
demo.mode=production
spring.config.activate.on-profile=prod
```

Even when the active profile is **not** `prod`, `demo.mode` can still be `production` from the `@PropertySource` source (unless a higher-precedence source overrides it). The `spring.config.activate.on-profile=prod` line here is simply **a property read as data**, and does not turn the section below it into a conditionally activated document.

**This is a dangerous bug:** the application appears to run and does not necessarily throw syntax errors, yet values from another profile leak into the current environment. Therefore, do not use `@PropertySource` as a substitute for `spring.config.import` on multi-document files.

## 6. `@TestPropertySource` has similar limitations

`@TestPropertySource` is used by the Spring TestContext Framework on test classes to add files or inline properties into the test `Environment`:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.properties")
class FeatureServiceTest {
}
```

Example of a valid file when using the annotation:

```properties
# src/test/resources/test-overrides.properties
app.feature-enabled=true
app.timeout=2s
```

This is appropriate for applying **fixed properties for a test**, without relying on profile-activated documents inside the same file.

If `test-overrides.properties` is written as:

```properties
app.feature-enabled=false
#---
spring.config.activate.on-profile=test
app.feature-enabled=true
```

then `@TestPropertySource` **does not use the multi-document Config Data loader** to decide whether to skip the second document. With the standard properties parser, `#---` is a comment, `spring.config.activate.on-profile=test` is an ordinary property pair, and the later value `true` can win within the same file **even when the `test` profile is inactive**.

You cannot add `@ActiveProfiles("test")` as a way to "upgrade" the annotation to automatically support `#---`. `@ActiveProfiles` sets profiles for the test context; `@TestPropertySource`'s file reader remains the default Spring TestContext mechanism.

### How is `@TestPropertySource(properties = "...")` different?

The annotation allows declaring properties directly in test code:

```java
@SpringBootTest
@TestPropertySource(properties = {
    "app.feature-enabled=true",
    "app.timeout=2s"
})
class FeatureServiceTest {
}
```

These strings are **inline properties**, not Config Data documents. `@TestPropertySource(properties = ...)` is convenient when you only need to override a few keys for a test; it does not support using `#---` to conditionally enable a section by profile.

### Precedence order in tests

Test properties are added as one or more separate `PropertySource` entries and usually have higher precedence than normal application configuration. This means a misloaded multi-document file via `@TestPropertySource` can **shadow** a valid value from `application-test.properties`. When a test receives an unexpected value, first check **whether it was loaded from Config Data or from a test annotation**.

In Spring Framework, `@TestPropertySource` inline properties have higher precedence than properties from files declared in `locations`. The complete order when `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, or custom initializers are also present depends on the specific test mechanisms; do not assume every annotation sits at the exact same layer.

## 7. YAML: default limitations and the `PropertySourceFactory` option

Spring Boot 3.3 supports `application.yaml`/`application.yml` when loaded via Config Data. However, Spring Framework **does not use a YAML parser by default** just because an annotation points to a file ending in `.yaml` or `.yml`:

```java
// Not the default way to load YAML via Spring Framework
@Configuration
@PropertySource("classpath:/settings/features.yaml")
class InvalidAssumptionConfig {
}
```

```java
// @TestPropertySource also does not automatically understand YAML without an appropriate factory
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.yaml")
class InvalidAssumptionTest {
}
```

Do not assume either approach above yields the same outcome as placing `features.yaml` in Config Data.

### Advanced customization: `factory`

- `@PropertySource` has a `factory` attribute to specify a custom `PropertySourceFactory`.
- Since Spring Framework **6.1**, `@TestPropertySource` also has a `factory` attribute to use a dedicated factory for other formats like YAML.
- Helper classes such as Spring Framework's `YamlPropertiesFactoryBean`, `YamlMapFactoryBean`, or Spring Boot's `YamlPropertySourceLoader` can assist manual YAML loading tasks.

The example only illustrates **how to declare a custom factory**, not the factory itself:

```java
@Configuration
@PropertySource(
    value = "classpath:/settings/features.yaml",
    factory = CustomYamlPropertySourceFactory.class
)
class FeatureYamlConfig {
}
```

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/test-overrides.yaml",
    factory = CustomYamlPropertySourceFactory.class
)
class FeatureYamlTest {
}
```

`CustomYamlPropertySourceFactory` must be **a class implemented by the project** adhering to the `PropertySourceFactory` interface; Spring Boot does not provide a class with that name automatically.

**Important:** a custom factory can parse YAML into property values, yet it **does not automatically** perform every Config Data step: splitting documents into independent sources, evaluating `on-profile`/`on-cloud-platform` conditions, setting origin/precedence, handling imports, locations, and activation rules. To get those features, use the built-in Config Data mechanism rather than rebuilding it yourself.

## 8. When multiple documents are needed, load via Config Data

### Method 1 — Place directly in `application.properties`

```properties
# src/main/resources/application.properties
service.transport=http
service.connect-timeout=3s

#---
spring.config.activate.on-profile=prod
service.transport=https
service.connect-timeout=10s

#---
spring.config.activate.on-profile=dev
service.transport=http
service.connect-timeout=1s
```

**Expected results:**

| Active profile | `service.transport` | `service.connect-timeout` |
| --- | --- | --- |
| Neither `prod` nor `dev` | `http` | `3s` |
| `prod` | `https` | `10s` |
| `dev` | `http` | `1s` |

If `prod` and `dev` match simultaneously, you must consider **document order and other Config Data sources**. In the file above, the `dev` document appears after the `prod` document, so it can override matching keys if both are active.

Do not place `spring.profiles.active` or `spring.profiles.default` inside a document **activated by `spring.config.activate.on-profile`**: Boot 3.3 restricts profile-set-control properties there. Put them in an unconditional shared document or an appropriate startup source.

### Method 2 — Import a separate multi-document file

Suppose you want to keep `settings/notifications.properties` separate:

```text
src/main/resources/
├── application.properties
└── settings/
    └── notifications.properties
```

**`application.properties`:**

```properties
spring.config.import=classpath:/settings/notifications.properties
```

**`settings/notifications.properties`:**

```properties
notifications.enabled=false
notifications.channel=console
#---
spring.config.activate.on-profile=prod
notifications.enabled=true
notifications.channel=email
```

`spring.config.import` is handled by the **Config Data loader** when it reads the document declaring the import. Thus, the imported file can use multi-document and activation rules just like other Config Data documents. This is the solution when you want a custom-named file that still needs profile conditions.

If the location might be missing, use `optional:`:

```properties
spring.config.import=optional:classpath:/settings/notifications.properties
```

`optional:` only permits a missing resource; it does not make invalid syntax or invalid conditions valid.

### Method 3 — Split into profile-specific files

Instead of combining into one multi-document file, you can organize as:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

**`application.properties`:**

```properties
app.mode=standard
app.timeout=3s
```

**`application-dev.properties`:**

```properties
app.mode=development
app.timeout=1s
```

**`application-prod.properties`:**

```properties
app.mode=production
app.timeout=10s
```

When the corresponding profile is activated, Spring Boot evaluates `application-{profile}.properties` alongside the shared configuration. This approach is often easier to read when the number of environment-specific properties is large. With multiple locations and profiles, precedence still follows Config Data order.

### Method 4 — Specify file locations early

If the file is outside default locations:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deployment/
```

Or when you need to **replace** the default location list:

```bash
java -jar myapp.jar \
  --spring.config.location=optional:file:./deployment/application.properties
```

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read very early. Pass them via OS environment variables, JVM system properties, or command-line arguments **before Config Data decides where to search for files**. Do not put them in `@PropertySource` expecting Config Data loading to rewind to the initial discovery step.

If you only want to include an additional file and already have an `application.properties` being loaded, using `spring.config.import` is usually clearer.

## 9. How should multiple profiles be configured in tests?

### Option A — `@ActiveProfiles` and profile-specific files

Example:

```text
src/test/resources/
└── application-test.properties
```

**`application-test.properties`:**

```properties
billing.base-url=http://localhost:19090
billing.enabled=false
```

**Test class:**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class BillingConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestConfiguration() {
        assertEquals("http://localhost:19090",
                environment.getProperty("billing.base-url"));
        assertEquals("false",
                environment.getProperty("billing.enabled"));
    }
}
```

In a normally configured Spring Boot Test project, `@ActiveProfiles("test")` activates the `test` profile; Config Data can load `application-test.properties` from the test classpath. You do not need `@TestPropertySource` to force a multi-document file to work.

### Option B — Multi-document Config Data in tests

Place shared configuration and test-specific documents in `src/test/resources/application.properties` or an imported Config Data file:

```properties
app.region=global
app.retry-count=3
#---
spring.config.activate.on-profile=test
app.region=test-lab
app.retry-count=1
```

Use `@SpringBootTest` along with `@ActiveProfiles("test")`. Here the file is loaded by **Spring Boot Config Data**, and documents are properly activated by profile.

**Note:** `src/test/resources/application.properties` can shadow the identically named file in `src/main/resources` depending on classpath/build setup. If you only need to add some properties, use `application-test.properties` or a separate import to reduce confusion.

### Option C — A few test overrides: `@TestPropertySource` is still a great fit

```java
@SpringBootTest
@TestPropertySource(properties = {
    "billing.base-url=http://localhost:19090",
    "billing.enabled=false"
})
class BillingServiceTest {
}
```

Or:

```java
@SpringBootTest(properties = "billing.enabled=false")
class BillingServiceTest {
}
```

These approaches are helpful when you only need to **override directly** a few properties, without toggling multiple conditional documents. There is no reason to create a multi-document file when test data consists of just a few fixed key/value pairs.

### Option D — Separate file without conditions: `@TestPropertySource(locations=...)`

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.properties")
class BillingServiceTest {
}
```

**`test-overrides.properties`:**

```properties
billing.base-url=http://localhost:19090
billing.enabled=false
```

This remains fully supported because the file is just **an ordinary set of properties**.

## 10. Comparing support scope

| Feature | Config Data in Spring Boot 3.3 | Default `@PropertySource` | Default `@TestPropertySource` |
| --- | --- | --- | --- |
| Single-part `.properties` file | Yes | Yes | Yes |
| `.yaml`/`.yml` file | Yes | Not supported out of the box | Not supported out of the box |
| Splitting `.properties` by `#---`/`!---` into multiple documents | Yes | No | No |
| Splitting YAML by `---` per Spring Boot semantics | Yes | No | No |
| Per-document `spring.config.activate.on-profile` | Yes | No | No |
| Per-document `spring.config.activate.on-cloud-platform` | Yes | No | No |
| `spring.config.import` and locations via Config Data mechanism | Yes | Not performed automatically | Not performed automatically |
| Adding properties from a regular file to `Environment` | Yes | Yes | Yes (in test context) |
| Overriding a few inline test values | Via other sources/CLI/test API | Not primary purpose | Yes, with `properties={...}` |
| Custom factory to read other formats | Dedicated Config Data SPIs | Has `factory` | Has `factory` since Spring Framework 6.1 |

**"No" in the table means the default annotation/factory lacks those semantics.** Writing your own `PropertySourceFactory` or an extension SPI can provide custom behavior, but that outcome must be verified against the implementation and must not be assumed to be standard Spring Boot Config Data behavior.

## 11. If you only want to load a file by profile without multi-document Config Data

Another option is making a `@Configuration` class conditional:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.context.annotation.PropertySource;

@Configuration
@Profile("dev")
@PropertySource("classpath:/settings/dev-only.properties")
class DevOnlyPropertiesConfiguration {
}
```

When the bean/configuration profile condition `dev` matches, this class is processed and `dev-only.properties` can be added to `Environment`. The file must be in **regular, non-multi-document properties format**.

This is a valid option for certain bean configurations or application settings evaluated **after context refresh**. It is **not equivalent** to Config Data:

- The source is added **later**; it cannot be used for configuration needed very early, such as `spring.config.location` file routing or part of logging configuration.
- `@PropertySource` precedence order also **differs** from Config Data.
- It does not honor `spring.config.activate.*` inside the loaded file, nor does it provide document splitting.

If your true goal is a "profile-specific configuration file" in Spring Boot, `application-dev.properties` or Config Data imports remain the more conventional choices.

## 12. Why shouldn't `#---` be processed by a regular properties parser?

The `#---` comment line **has no special meaning** in standard Java Properties. Standard parsers typically read each `key=value` pair, and for repeated keys, the last value replaces the previous one. Example:

```properties
service.level=basic
#---
spring.config.activate.on-profile=prod
service.level=advanced
```

If the entire file is loaded as a single properties document, the logical result is roughly:

```text
service.level=advanced
spring.config.activate.on-profile=prod
```

There is no information stating "`advanced` applies only if profile prod"; that information only exists when Config Data splits documents and processes activation before placing them into `Environment`.

This explains why an application or test can **throw no exception** yet still run with configuration belonging to the wrong environment. When seeing incorrect values, do not check only profile names; check **which source and which loader mechanism** placed the key into `Environment`.

## 13. Diagnosing file loading failures and wrong conditions

### 13.1. Common symptoms

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `@TestPropertySource` loads a file with `#---` yet dev/prod values appear in every test | File was read by standard properties parser as one key/value set | Move conditional content to `application-{profile}.*` or Config Data import |
| `@PropertySource` reading YAML does not produce expected properties | Default annotation has no YAML parser | Use Config Data YAML or a custom factory if truly needed |
| `spring.config.activate.on-profile` still appears in `Environment` with no conditional effect | It was merely read as an ordinary property | Check whether the file goes through the Config Data loader |
| Multi-document `application.properties` does not activate properly | Wrong separator or profile mismatch | Check `#---`, whitespace, and active/default profiles |
| Imported file is not loaded | File containing `spring.config.import` wasn't found or location is wrong | Verify Config Data locations and resource path |
| Test profile changes yet property keeps a fixed value from test annotation | `@TestPropertySource` has its own precedence | Find and inspect `@TestPropertySource`/inline test overrides |

### 13.2. Observing values and sources

Diagnostic code example:

```java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class PropertySourceDiagnostics {

    @Bean
    ApplicationRunner showDemoMode(ConfigurableEnvironment env) {
        return args -> {
            String key = "demo.mode";
            System.out.println("Effective value: " + env.getProperty(key));

            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Source containing " + key + ": "
                            + source.getName());
                }
            }
        };
    }
}
```

This snippet helps verify:

- Do multiple sources declare `demo.mode`?
- From which source does the effective value come according to `Environment` lookup order?
- Does the source name indicate a Config Data resource or a property source from a test annotation/custom source?

Specific `PropertySource` names can vary depending on the loading method; the code above prints only source names and one non-sensitive property, avoiding printing full configurations containing secrets.

If Spring Boot Actuator is enabled with appropriate security configuration, the `/actuator/env` endpoint can also help inspect property sources and partially masked values. Do not expose diagnostic endpoints publicly merely to inspect multi-part documents.

### 13.3. A simple test

To verify the mechanism, create `src/main/resources/application.properties`:

```properties
demo.mode=base
#---
spring.config.activate.on-profile=dev
demo.mode=dev
```

Run 1:

```bash
java -jar myapp.jar
```

When no active/default profile matches `dev`, `demo.mode` is expected to be `base`.

Run 2:

```bash
java -jar myapp.jar --spring.profiles.active=dev
```

`demo.mode` is expected to be `dev`.

Then compare by moving **the exact same `.properties` content** into a file attached via `@PropertySource`. If only the standard properties loader is used, the final value `dev` can still appear even when `dev` is inactive. That is a clear indicator of a loader difference, not a bug in `@Profile` or `@ActiveProfiles`.

## 14. Misconceptions to avoid

**Misconception 1: "The file ends in `.properties`, so Boot definitely handles `#---`."** Incorrect. You must know **which loader loaded the file**. An `application.properties` file handled by Config Data and a `test-overrides.properties` file read by `@TestPropertySource` share the same file format yet have different document semantics.

**Misconception 2: "With `@ActiveProfiles` present, `@TestPropertySource` understands `on-profile`."** `@ActiveProfiles` supplies profiles to the test context; it does not make `@TestPropertySource`'s properties parser split documents by `#---`.

**Misconception 3: "The annotation loads `.yaml` the same way Boot loads `application.yaml`."** `@PropertySource`/`@TestPropertySource` by default do not use the same YAML loader as Config Data. Loading YAML through these annotations requires an appropriate factory, and even then the factory typically still lacks activation semantics.

**Misconception 4: "A `spring.config.activate.on-profile` line in any `PropertySource` conditions nearby keys."** This condition has meaning when the Config Data loader processes a **document**. Putting the same key in an ordinary `PropertySource` creates no conditional scope.

**Misconception 5: "Just put `spring.config.import` in `@PropertySource` and Boot will load the imported file."** `@PropertySource` is processed after the standard Config Data phase; an import property read late in this source does not trigger Config Data to run again. Place imports in valid Config Data documents.

**Misconception 6: "After `#---`, subsequent lines are skipped."** In a standard properties parser, only **the comment line itself** is ignored; key/value lines after it are still read, so matching keys can be overwritten.

**Misconception 7: "Multiple `locations` files in `@TestPropertySource` act as multiple logical documents."** Each file can become a separate test property source, yet that is still not multi-document Config Data with `spring.config.activate.*` conditions.

**Misconception 8: "Having a custom YAML factory is enough to replace Config Data."** A factory handles reading the format; to match Config Data semantics requires additional logic for document splitting, activation, precedence, imports, and origin. Do not assume these behaviors appear automatically.

## 15. Choosing the right tool for each purpose

1. **Need a single config file with multiple sections toggled by profile/cloud platform:** use **Config Data** and `#---`/`---`, with `spring.config.activate.*`.
2. **Need a separate file loaded by Config Data even though its name is not `application`:** set `spring.config.import` inside a discovered Config Data file, or configure locations early.
3. **Need one file per environment:** use `application-dev.properties`, `application-prod.yaml`, or corresponding variants.
4. **Need a simple properties file added during bean configuration:** `@PropertySource` works well if it does not depend on very early startup and does not use multi-document features.
5. **Need a few fixed test properties:** `@TestPropertySource(properties=...)` or `@SpringBootTest(properties=...)`.
6. **Need a separate properties file for tests:** `@TestPropertySource(locations=...)` with a single-document file.
7. **Need profile conditions for test configuration:** `@ActiveProfiles` with profile-specific or multi-document Config Data; do not rely on `@TestPropertySource` understanding separators.
8. **Need YAML via annotation for a specialized reason:** implement `PropertySourceFactory` and clearly verify supported semantics; if standard activation semantics are needed, prefer moving to Config Data.

## 16. References

- Spring Boot **3.3** Reference – **Externalized Configuration**, sections *Working With Multi-Document Files*, *Activation Properties*, *Working With YAML*, *Importing Additional Data*, and *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework **6.1** Reference – **Context Configuration with Test Property Sources**, attributes `locations`, `properties`, and `factory`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework **6.1** API – `TestPropertySource`, especially `factory()` and default supported file formats: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/TestPropertySource.html
- Spring Framework Reference – **Using @PropertySource** and `PropertySourceFactory`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/propertysource.html

**Knowledge takeaway:** In Spring Boot 3.3, **multi-document formatting is a capability of the Config Data loader**. `@PropertySource` and `@TestPropertySource` read properties sources by default as a single key/value set and do not automatically split or filter sections via `spring.config.activate.*`. To preserve proper conditional multi-document behavior, load files via **Config Data**, using profile-specific files or `spring.config.import`; the two annotations are suited for simple property sources and test overrides.
