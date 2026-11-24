# Choosing One Format and Handling Coexisting `.properties` and YAML

## 1. Problem to solve

In Spring Boot 3.3, the same application can be configured using either `application.properties` or `application.yaml`/`application.yml`. Both approaches produce properties for Spring Boot to consume, such as `server.port`, `spring.application.name`, or `app.payment.timeout`.

When starting a project, the team typically picks just one format. After adding several features or upgrading the project, both formats may end up in the same directory. Three important questions then arise:

1. When should you choose `.properties`, and when should you choose YAML?
2. If both files declare the same key, which value does Spring Boot use?
3. When profile configuration, external files outside the JAR, or environment variables are involved, how do you know the final value for certain?

The goal of this lesson is to provide criteria for choosing a format, explain configuration loading rules in **Spring Boot 3.3**, and practice determining effective values. To follow along, you only need to understand key–value pairs, directory structure, Java 17, and how to launch a Spring Boot application.

**Working principle:** prefer **one primary format for application configuration**. If you temporarily need both, clearly manage which file owns which keys and verify actual precedence order. Having both formats does not automatically cause an error, yet duplicate keys make it easy for readers to misjudge where a value comes from.

## 2. How do `.properties` and YAML express the same configuration?

### 2.1. `.properties`: one key per line

File `src/main/resources/application.properties`:

```properties
spring.application.name=order-service
server.port=8080

app.payment.enabled=true
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=3s
app.payment.max-retries=4
```

Each line has the form `key=value`; `:` is also allowed as a separator in Java properties syntax, though `=` is usually easier to read. Dots represent nested key groups in a flat form. In the example, keys starting with `app.payment` together describe one feature.

This is a compact option when the configuration set does not have deep nesting and you want to scan each key independently. Most text editors, scripts, and deployment systems work smoothly with plain key–value pairs.

### 2.2. YAML: hierarchical structure via indentation

`src/main/resources/application.yaml` can express the exact same data:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  payment:
    enabled: true
    endpoint: https://payments.example.test
    connect-timeout: 3s
    max-retries: 4
```

Spring Boot flattens the YAML structure into keys that can be looked up in `Environment`. For example:

```text
app.payment.enabled=true
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=3s
app.payment.max-retries=4
```

Therefore, **YAML is a presentation layer**, not a separate configuration API. Beans consuming configuration use the same logical keys as with `.properties`.

Spring Boot supports YAML through the SnakeYAML library. In standard Spring Boot applications using official starters, the required library is already provided as a dependency. If you customize your classpath manually, ensure the YAML loader is available.

### 2.3. Example with lists

`.properties`:

```properties
app.notification.recipients[0]=ops@example.test
app.notification.recipients[1]=support@example.test
```

YAML:

```yaml
app:
  notification:
    recipients:
      - ops@example.test
      - support@example.test
```

Both bind to `List<String> recipients`. When a list setting is overridden from a higher-precedence source, do not assume elements will be merged position by position across sources. Under Spring Boot's list binding behavior, a higher-precedence source normally **replaces the entire list**; this matters especially when both common and profile files define a list.

### 2.4. Syntax differences that cause mistakes

| Situation | In `.properties` | In YAML |
| --- | --- | --- |
| Key grouping | Write out `app.payment.timeout=3s` | Use indentation levels under `app` and `payment` |
| Lists | Indices `[0]`, `[1]` or binder-supported notation | Use `-` in sequences |
| Comments | Line starting with `#` or `!` | `#` starts a comment in valid syntactic positions |
| Values with `:` or `#` | Watch properties syntax and escape characters | Wrap value in quotes if it could be parsed as syntax |
| Strings looking like numbers/booleans | Treated mainly as text when reading properties | YAML has scalar types; quote when preserving string form |
| Quotes | `"` is not stripped automatically like in YAML | Quotes are part of string syntax and usually excluded from value |
| Misindentation | Not applicable | Can alter structure or make YAML unparseable |

For example, if an identifier must preserve leading zeros, explicitly declare it as a string in YAML:

```yaml
app:
  branch-code: "0012"
```

When writing YAML, **use spaces for indentation; never use tabs**. Be especially careful with strings containing special characters, values starting with `{`, `[`, `*`, `&`, or values easily confused with other data types. Standardize key naming with lowercase and hyphens, such as `connect-timeout`, across both formats.

## 3. Choosing a format based on practical needs

Neither format is always better for every project. Choose based on your actual configuration, maintainers, and tooling.

| Criterion | Usually favors `.properties` | Usually favors YAML |
| --- | --- | --- |
| Few keys, relatively flat | Very concise, one key per line | Can be longer due to nesting |
| Many key groups with parent–child hierarchy | Repeats prefixes, though easy to search full keys | Easy to see hierarchy and functional groups |
| Lists and nested object groups | Possible via indices or binder conventions | List and object syntax feels more natural |
| Scripts manipulating individual keys | Easy to handle in properties-friendly tooling | Needs YAML-aware tools for safe edits |
| Reviewing diffs in pull requests | Changing a key is usually one line | Changing indentation or ordering can affect whole blocks |
| Team conventions | Fits if the project already uses properties | Fits if the project already uses YAML with syntax checks |

A sensible choice:

- **Small projects or flat configuration:** `application.properties` works well.
- **Projects with many configuration groups and lists:** `application.yaml` works well.
- **Projects already standardized on one format:** keep the existing convention rather than switching formats on preference alone.
- **Projects temporarily using both during gradual migration:** establish clear rules on where keys live, exceptions, and conflict checks.

Both `.yml` and `.yaml` are YAML extensions supported by Spring Boot. To make configuration locations predictable, standardize on **one filename extension** across the project; avoid creating both `application.yml` and `application.yaml` in the same place and relying on their processing order.

## 4. Which files does Spring Boot 3.3 read and in what order?

At startup, Spring Boot collects configuration sources into `PropertySource` entries inside `Environment`. **A higher-precedence source decides the value of a conflicting key.** Keys present in only one source are still available.

Separate two layers of rules:

1. **Format selection rules between `.properties` and YAML in the same location.**
2. **Overall precedence rules across locations, profiles, and other sources.**

Do not oversimplify every case to "properties always beats YAML".

### 4.1. Both formats in the same location: `.properties` takes precedence

The official **Spring Boot 3.3** documentation recommends using one format consistently across an application and states clearly: if both `.properties` and YAML files exist in **the same location**, `.properties` takes precedence.

Example with two files in `src/main/resources/`:

`application.properties`:

```properties
app.ui.title=Title from properties
app.ui.page-size=25
```

`application.yaml`:

```yaml
app:
  ui:
    title: Title from YAML
    accent-color: blue
```

When no profile or higher-precedence source overrides these keys, the expected outcome is:

| Key | Effective value | Reason |
| --- | --- | --- |
| `app.ui.title` | `Title from properties` | Present in both files in the same location; `.properties` wins |
| `app.ui.page-size` | `25` | Only in `.properties` |
| `app.ui.accent-color` | `blue` | Only in YAML |

This is **key-by-key overriding**, meaning YAML is not ignored wholesale just because a properties file exists.

### 4.2. Profile-specific files can beat common files

Suppose we add:

`application-dev.yaml`:

```yaml
app:
  ui:
    title: Title for dev environment
    accent-color: orange
```

If the `dev` profile is active and no higher-precedence source intervenes, `app.ui.title` from the **profile file** can override the key in the common `application.properties`. Profile file precedence must be evaluated before drawing final conclusions.

Startup example:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Within the same location:

- `application.properties` and `application.yaml` are both **common** files; for duplicate keys, `.properties` wins.
- `application-dev.properties` and `application-dev.yaml` are both **dev profile** files; for duplicate keys in the same location, `.properties` wins.
- An active `application-dev.yaml` can override a value from the **common** `application.properties`, because profile precedence applies during Config Data loading.

If `dev` is not enabled, `application-dev.yaml` does not become an active profile configuration source merely by existing in the project.

### 4.3. Files outside the JAR can beat packaged files inside the JAR

Spring Boot checks default configuration locations, including classpath locations and external locations such as the working directory and its `config/` subdirectory.

Conceptually for default Config Data, precedence increases from top to bottom:

```text
Common application file inside JAR
          <
Profile-specific file inside JAR
          <
Common application file outside JAR
          <
Profile-specific file outside JAR
```

This means `./config/application.yaml` provided at deployment can override a key from `application.properties` packaged inside the JAR, even though the external file is YAML and the packaged one is properties. **Location and profile also determine precedence.**

Spring Boot also supports customizing locations and location groups; when a project sets `spring.config.location` or `spring.config.additional-location`, inspect the actual configuration rather than mechanically applying the default diagram.

### 4.4. Environment variables and startup arguments can override files

For example:

```bash
java -jar app.jar --app.ui.title="From command line"
```

Under standard startup configuration, this command-line argument has higher precedence than the configuration files discussed above. Environment variables such as `APP_UI_TITLE` can also override file values.

Do not assume renaming `.yaml` to `.properties` will make that file beat command-line arguments, environment variables, or other configuration sources. **Same-location format precedence is only one piece of the full mechanism.**

## 5. Scenario table: which file actually wins?

Assume every example below uses the same key `app.ui.title`, no other overriding source is present, and only the specified profile is active.

| Scenario | Winning source for duplicate key | Explanation |
| --- | --- | --- |
| `application.properties` and `application.yaml` both in `src/main/resources` | `application.properties` | `.properties` wins over YAML at the same location and common level |
| `application-dev.properties` and `application-dev.yaml` same location, `dev` active | `application-dev.properties` | Same profile level; `.properties` wins |
| `application.properties` and `application-dev.yaml` same location, `dev` active | `application-dev.yaml` | Profile file has higher precedence than common file here |
| `application.properties` in JAR, `./config/application.yaml` outside | External YAML | External config locations have higher precedence than packaged ones by default |
| Config file sets `app.ui.title=A`, run with `--app.ui.title=B` | Command-line argument `B` | Application arguments have higher precedence than Config Data files |
| Config file sets `app.ui.title=A`, environment sets `APP_UI_TITLE=B` | Environment variable `B` | Environment variables can override file values |
| Only YAML has `app.ui.accent-color=blue`; properties lacks that key | YAML | No conflict to override |

This table illustrates common cases, **not an exhaustive list of every configuration source**. When multiple profiles, multi-document files, `spring.config.import`, library-provided sources, or custom locations are involved, check each mechanism's rules as well.

## 6. Hands-on: observing both formats coexisting

This example uses **Java 17 + Spring Boot 3.3.x** and the `spring-boot-starter` dependency. You can generate a minimal project with Spring Initializr. Place classes under package `example.configformat`; run from your IDE, Maven, Gradle, or a packaged JAR.

### Step 1 — create both configuration files

`src/main/resources/application.properties`:

```properties
spring.application.name=config-format-demo
app.ui.title=UI from properties
app.ui.page-size=25
```

`src/main/resources/application.yaml`:

```yaml
app:
  ui:
    title: UI from YAML
    accent-color: blue
```

### Step 2 — create a typed configuration class

`src/main/java/example/configformat/UiSettings.java`:

```java
package example.configformat;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.ui")
public record UiSettings(
        String title,
        int pageSize,
        String accentColor
) {
}
```

`@ConfigurationProperties` binds keys prefixed with `app.ui` to the `UiSettings` record. Whether the origin is `.properties` or YAML, Java code works with the same data type.

### Step 3 — register the properties class and print values

`src/main/java/example/configformat/ConfigFormatApplication.java`:

```java
package example.configformat;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigFormatApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigFormatApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(UiSettings ui) {
        return args -> {
            System.out.println("title=" + ui.title());
            System.out.println("pageSize=" + ui.pageSize());
            System.out.println("accentColor=" + ui.accentColor());
        };
    }
}
```

`@ConfigurationPropertiesScan` registers the configuration type so Spring creates a bean. Spring then injects the `UiSettings` bean into `showConfig(...)`; there is no need to write file-reading code inside `ApplicationRunner`.

### Step 4 — run with common configuration

Example using the Maven wrapper on systems supporting the command:

```bash
./mvnw spring-boot:run
```

Or run a packaged JAR:

```bash
java -jar app.jar
```

`app.jar` is an illustrative name; replace it with the actual JAR path.

Expected output of the three lines printed by `ApplicationRunner`:

```text
title=UI from properties
pageSize=25
accentColor=blue
```

These three lines show that properties can be combined from both files, while the duplicate key `title` follows precedence rules.

### Step 5 — enable the `dev` profile

Add `src/main/resources/application-dev.yaml`:

```yaml
app:
  ui:
    title: UI for dev
    accent-color: orange
```

Run:

```bash
java -jar app.jar --spring.profiles.active=dev
```

With no higher-precedence source:

```text
title=UI for dev
pageSize=25
accentColor=orange
```

Remember to **repackage** if you added a file to `src/main/resources` while running a previously built JAR. Running via the build tool uses updated resources after the build tool processes them.

### Step 6 — add a profile-specific properties file

Add `src/main/resources/application-dev.properties`:

```properties
app.ui.title=Dev UI from properties
```

Restarting with the `dev` profile yields the expected output:

```text
title=Dev UI from properties
pageSize=25
accentColor=orange
```

Explanation: both `application-dev.properties` and `application-dev.yaml` are in the same location for the same profile; `title` comes from `.properties`, while `accent-color` is not overridden by `.properties`.

### Step 7 — override with a command-line argument

```bash
java -jar app.jar --spring.profiles.active=dev --app.ui.title="From CLI"
```

Expected output:

```text
title=From CLI
pageSize=25
accentColor=orange
```

This exercise shows that profile files and formats do not have the final word: startup arguments can still override them.

## 7. If you must keep both formats in a running project

### 7.1. Organize configuration with clear ownership

A project migrating gradually might temporarily keep:

```text
src/main/resources/
├── application.properties
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

During the transition, document the convention clearly in project docs, for example:

- `application.properties`: holds only legacy keys not yet migrated.
- `application.yaml`: holds new primary configuration grouped by feature.
- `application-{profile}.yaml`: holds only values that vary by profile.
- Once a key is moved to YAML, delete **the old declaration of that exact key** from the properties file in the same source so the new setting is not shadowed.

Before editing configuration files, maintainers should check whether deployment environments inject additional external files or environment variables. A same-named key elsewhere can produce runtime values different from what source files alone suggest.

### 7.2. Migrate by key groups

Suppose the old properties file has:

```properties
app.mail.from-address=noreply@example.test
app.mail.retry-count=3
app.cache.enabled=true
```

To migrate the `app.mail` section to YAML:

```yaml
app:
  mail:
    from-address: noreply@example.test
    retry-count: 3
```

After migrating, the properties file should retain only:

```properties
app.cache.enabled=true
```

If you keep `app.mail.retry-count=3` in properties alongside a new `retry-count: 5` in YAML at the same location, Spring Boot can still pick `3` from properties. Someone editing YAML may think changing it to `5` took effect when it actually did not.

Therefore, format migration **must remove duplicate legacy declarations at the same time**. You can migrate one configuration group at a time to keep impact easy to verify; there is no need to convert the whole project at once.

### 7.3. Do not switch formats hoping to change precedence

Renaming `application.yaml` to `application.properties` will not stop environment variables or command-line arguments from overriding a key. Conversely, placing a file in a different location can change precedence even with identical content.

Before migrating, answer:

1. In which files and sources is this key currently declared?
2. Which profiles are actually active?
3. Does the application load config from the classpath, an external directory, or a custom location?
4. Do any startup arguments, JVM properties, or environment variables override it?
5. What value must take effect after migration?

Answering these questions prevents shadowed-configuration bugs, especially in staging or production environments.

## 8. Advanced settings that change the picture

### 8.1. `spring.config.location` and `spring.config.additional-location`

By default, Spring Boot searches standard locations for Config Data. Two important settings are:

- `spring.config.location`: **replaces** the default search locations with the specified ones.
- `spring.config.additional-location`: **adds** locations alongside the defaults; added locations can override default values.

Example of a packaged application deployed with an external directory:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./custom-config/
```

The trailing `/` indicates a directory path. The `optional:` prefix lets the application continue if that location does not exist. If a file in the added location shares a key with a packaged file, the added source can override according to Config Data loading rules.

Location-defining properties such as `spring.config.location` and `spring.config.additional-location` are evaluated very early at startup. Supply them via environment variables, JVM properties, or command-line arguments; do not place them inside a file whose own discovery depends on those settings.

### 8.2. `spring.config.import`

Spring Boot 3.3 can import additional configuration from elsewhere. For example, in `application.properties`:

```properties
spring.config.import=optional:file:./extra-settings.yaml
app.mode=standard
```

If `extra-settings.yaml` exists and contains:

```yaml
app:
  mode: imported
```

The value from the imported file can override the key in the file declaring the import. This is **configuration data importing**, not simply a same-location `.properties` vs. YAML selection rule.

Avoid nested or duplicate imports that create confusing override layers. If your project uses imports, clearly define which file serves as defaults and which provides intentional overrides.

### 8.3. Multiple documents in a single file

YAML supports document separation via `---`:

```yaml
app:
  label: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: dev
```

When the `dev` profile is enabled, the second document activates and can override `app.label`. Spring Boot also supports multi-document separation in `.properties` files using `#---` or `!---` per its documented syntax.

Therefore, never assume knowing filenames alone reveals all effective configuration sources. One file can contain multiple logical documents with different activation conditions.

## 9. Cases requiring care when converting between formats

### 9.1. Strings, quotes, and special characters

Two forms may *look* alike yet parse differently:

```properties
app.message="Hello"
```

```yaml
app:
  message: "Hello"
```

In YAML, quotes normally delimit strings. In `.properties`, double quotes do not carry the same syntactic role and can become part of the parsed value. When migrating, do not mechanically copy quotes from YAML into properties.

For strings needing `#`, `:`, or special leading/trailing characters, pick the safe representation for the format you are using. What matters is **the parsed value**, not just how the line looks visually.

### 9.2. Lists and profile overrides

Common file `application.yaml`:

```yaml
app:
  endpoints:
    - https://a.example.test
    - https://b.example.test
```

`application-dev.yaml`:

```yaml
app:
  endpoints:
    - http://localhost:8081
```

When binding into `List<String>`, the list from the higher-precedence profile source normally replaces the common list. Do not expect the resulting list to contain all three items. If you need environment-specific entries preserved alongside common ones, model your configuration appropriately and test binding for that data type.

### 9.3. `Map` fields and nested values

With `Map` structures or nested beans, some values can be aggregated by sub-key during binding. Behavior differs from lists. When converting from properties to YAML, pay attention to whether the target structure is a `List`, `Map`, or object with fixed fields.

### 9.4. `@PropertySource` is not Boot's YAML loader

`application.yaml` is loaded by Spring Boot's Config Data mechanism. Do not infer that `@PropertySource("classpath:custom.yaml")` works automatically the same way as default YAML loading. Standard `@PropertySource` does not load YAML in that manner without custom handling. When extra YAML files are needed, look at Config Data and `spring.config.import` in Spring Boot 3.3.

### 9.5. Secrets do not become safe by changing file formats

Passwords, API keys, and tokens must never be committed to Git in either `.properties` or YAML. File formats provide neither encryption nor access control. Choose secret delivery appropriate for your deployment infrastructure, and avoid logging sensitive information to console, logs, or error reports.

## 10. How to determine the value actually in use

When a setting behaves unexpectedly, follow this investigation sequence:

**Step 1 — identify the exact key.** For example, `app.ui.title` can bind from naming variants under relaxed binding rules. Do not confuse `title` with `page-title`.

**Step 2 — identify active profiles.** Check `--spring.profiles.active=...`, environment variable `SPRING_PROFILES_ACTIVE`, or other relevant settings. Remember that active profiles determine which `application-{profile}` files apply.

**Step 3 — locate conflicting sources.** Check common files, profile files, JAR-packaged files, external files, and startup sources. If both `.properties` and YAML exist in the same location, apply the format rule for that scope.

**Step 4 — inspect the effective value.** In development, you can use `Environment` to read a non-sensitive key:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
ApplicationRunner printTitle(Environment environment) {
    return args -> System.out.println(
        "app.ui.title=" + environment.getProperty("app.ui.title")
    );
}
```

This is an example **bean method inside a `@Configuration` or `@SpringBootApplication` class**, not a standalone Java file containing only a method. Never print passwords or secrets just to diagnose configuration.

**Step 5 — observe configuration loading when needed.** You can temporarily enable detailed logging for the config subsystem in development:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Only enable diagnostic logging where appropriate, and review output before sharing it. Once the cause is found, restore normal logging levels.

**Step 6 — check the packaged artifact and startup command.** A freshly edited `application-dev.yaml` in source might not yet be inside the JAR being executed. Containers or deployment platforms may also mount external files. Runtime behavior depends on **the actual artifact and environment being run**.

## 11. Recommended conventions for Spring Boot 3.3 projects

A simple, maintainable convention:

1. **Pick one standard format** (`application.properties` or `application.yaml`) and use it consistently across project-owned config files.
2. **Keep key names clear** in lowercase kebab-case, such as `app.payment.connect-timeout`.
3. **Group keys by feature**, making `@ConfigurationProperties` binding and co-located edits easy.
4. **Use profiles for values that genuinely differ by environment**; avoid duplicating all common settings in every profile file.
5. **When migrating formats, remove legacy duplicate keys** from any source that could shadow the new one, and verify loaded values.
6. **Keep deployment settings in proper external sources**, never committing real secrets to Git.
7. **Test at least one default configuration and one profile configuration** by inspecting effective properties in the running app, not just reading file contents.
8. **Document intentional multi-source overrides**, especially when loading external files outside the JAR or using `spring.config.import`.

An example clean layout when choosing YAML:

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
├── application-test.yaml
└── application-prod.yaml
```

An analogous layout with `.properties` is equally valid. Profile names are project conventions; Spring Boot does not require `dev`, `test`, or `prod`.

## 12. Prediction and verification exercises

### Exercise 1 — both formats in the same directory

`application.properties`:

```properties
app.feature.enabled=true
app.feature.label=properties
```

`application.yml`:

```yaml
app:
  feature:
    enabled: false
    color: green
```

**Question:** What are the values of `enabled`, `label`, and `color` when no other override exists?

**Expected answer:** `enabled=true`, `label=properties`, `color=green`. The duplicate key comes from properties, while keys present only in YAML remain usable.

### Exercise 2 — adding a profile

`application.properties`:

```properties
app.mode=default
```

`application-dev.yml`:

```yaml
app:
  mode: development
```

Launch with `--spring.profiles.active=dev`.

**Question:** What is `app.mode`?

**Expected answer:** `development`. An active profile-specific file can override a common file, even when they use different formats.

### Exercise 3 — adding a command-line argument

Using the same files from Exercise 2, run:

```bash
java -jar app.jar --spring.profiles.active=dev --app.mode=cli
```

**Expected answer:** `cli`, because command-line arguments have higher precedence than the Config Data files shown.

### Exercise 4 — migrating formats

Initially:

`application.properties`:

```properties
app.mail.retry-count=3
```

Add `application.yaml`:

```yaml
app:
  mail:
    retry-count: 5
```

**Question:** Why might the application still receive `3`, and what must be done if you truly intend to switch to YAML?

**Expected answer:** both files are in the same location and at the same configuration level, so `.properties` takes precedence. When migrating intentionally, remove the old duplicate declaration in properties, then verify the loaded value.

### Exercise 5 — external file outside the JAR

A JAR contains `application.properties` with `app.mode=packaged`. At deployment, an external config directory outside the JAR contains `application.yaml` with `app.mode=external` in a default location searched by Spring Boot.

**Question:** Why can you not simply apply the rule "properties beats YAML"?

**Expected answer:** because precedence rules between external locations and packaged files also apply. By default, the external file can override the file inside the JAR.

## 13. Summary of key points to remember

Remember these five relationships:

```text
.properties and YAML
    -> two ways to represent configuration keys

Multiple PropertySources
    -> Spring Environment selects the effective value

Both formats in the same location and configuration level
    -> .properties takes precedence for duplicate keys

Profiles, external locations outside JAR, and startup sources
    -> also change the precedence order

@ConfigurationProperties
    -> binds the final values into typed Java objects
```

When deciding between `.properties` and YAML in Spring Boot 3.3, choose the format that keeps configuration clearest for your team and stay consistent. When both coexist, the key question is **which sources hold duplicate keys and in what order they are loaded**. Inspecting values in `Environment` or a `@ConfigurationProperties` bean gives you real evidence instead of guessing from filenames.

### References

- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot Reference — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
