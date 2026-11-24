# Profile-Specific Variants of Imported Files in Spring Boot

Spring Boot supports loading configuration from other files using the `spring.config.import` property. When profiles are activated, Spring Boot does not only look at the imported file under the exact declared name, it also **automatically considers profile-specific variants** of that file, if they exist and apply.

For example, an import pointing to `file:./config/payment.yml` can cause `file:./config/payment-prod.yml` to also be loaded when the `prod` profile is active. This is part of Spring Boot's **Config Data** system, helping separate common configuration from environment-specific configuration without needing a separate import line for each profile.

This lesson uses Spring Boot 3.3.x and Java 21; the focus is on profile variant discovery, effective values, precedence order, and practical file organization.

## 1. Reviewing `spring.config.import`

In `src/main/resources/application.yml`, you can declare:

~~~yaml
spring:
  config:
    import: "optional:file:./config/payment.yml"
~~~

Meaning:

- `spring.config.import` tells Spring Boot to load another configuration resource during Config Data processing.
- `file:./config/payment.yml` is a file system path, resolved based on the process's **working directory**.
- `optional:` allows skipping the declared location if it does not exist. If the configuration is mandatory, omit this prefix so Spring Boot fails when it is missing.
- When the imported file has keys matching the importing document, the imported document can **override** values in the importing document according to Config Data precedence rules.
- This import is processed at application startup, not as a file load on every incoming request.

Example in the main file:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"

app:
  payment:
    timeout: 2s
    mode: packaged
~~~

And the file `config/payment.yml`:

~~~yaml
app:
  payment:
    timeout: 5s
    mode: imported
~~~

If no higher-precedence source overrides them, the effective values are `app.payment.timeout=5s` and `app.payment.mode=imported`. Where the import line sits inside the same document is not a switch determining whether it takes precedence; Spring Boot processes the imported document via the Config Data mechanism.

## 2. What is a profile-specific variant?

A *profile-specific variant* is a configuration file version with a profile name suffix placed right before the file extension:

| Imported file | Active profile | Variant that may be considered |
| --- | --- | --- |
| `payment.yml` | `dev` | `payment-dev.yml` |
| `payment.yml` | `prod` | `payment-prod.yml` |
| `payment.yaml` | `staging` | `payment-staging.yaml` |
| `payment.properties` | `test` | `payment-test.properties` |
| `feature.yml` | `dev,prod` | `feature-dev.yml`, `feature-prod.yml` |

This rule applies to **imported resources**, not only default files named `application.yml`. The base name stays the same, with a hyphen and profile name inserted before the extension.

Example:

~~~text
config/
├── payment.yml
├── payment-dev.yml
├── payment-test.yml
└── payment-prod.yml
~~~

If the import configuration is:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

then:

- Without `dev`/`test`/`prod` enabled: uses the contents of `payment.yml` as the common configuration.
- With `dev` enabled: Spring Boot considers `payment.yml` and `payment-dev.yml`.
- With `prod` enabled: Spring Boot considers `payment.yml` and `payment-prod.yml`.
- Without `payment-staging.yml`: there is no specific content from that variant; the common file can still supply configuration when the `staging` profile is active.

The actual active profiles are determined by Spring's `Environment`, and can be activated via `spring.profiles.active`, environment variables, or other configuration sources. If no profile is set, Spring Boot typically uses a default profile named `default`; a file such as `payment-default.yml` can be considered under the corresponding profile-specific mechanism.

## 3. Complete example: common imported file, dev, and prod

Suppose the application has the structure:

~~~text
catalog-app/
├── build/libs/catalog-app.jar
├── config/
│   ├── payment.yml
│   ├── payment-dev.yml
│   └── payment-prod.yml
└── src/main/resources/
    └── application.yml
~~~

### 3.1. `application.yml` file inside the application

~~~yaml
spring:
  application:
    name: catalog-app
  config:
    import: "file:./config/payment.yml"

server:
  port: 8080

app:
  payment:
    mode: application-default
    retry-count: 2
    timeout: 3s
~~~

There is only **one** import directive, explicitly pointing to `payment.yml`. There is no need to write extra imports for `payment-dev.yml` or `payment-prod.yml`.

### 3.2. `config/payment.yml` file: common configuration

~~~yaml
app:
  payment:
    mode: standard
    retry-count: 3
    timeout: 5s
    provider: sandbox
~~~

### 3.3. `config/payment-dev.yml` file: overrides for dev

~~~yaml
app:
  payment:
    mode: debug
    timeout: 15s
    provider: mock
~~~

### 3.4. `config/payment-prod.yml` file: overrides for prod

~~~yaml
app:
  payment:
    mode: live
    retry-count: 5
    provider: production
~~~

At startup, the application's configuration and imported documents combine according to precedence rules. Keys not redeclared can still come from a previously loaded source; keys present in a matching profile variant override the common version when both apply.

### 3.5. Expected results across profiles

| Property | No specific profile active | `dev` | `prod` |
| --- | --- | --- | --- |
| `app.payment.mode` | `standard` | `debug` | `live` |
| `app.payment.retry-count` | `3` | `3` | `5` |
| `app.payment.timeout` | `5s` | `15s` | `5s` |
| `app.payment.provider` | `sandbox` | `mock` | `production` |

Reasons:

- `mode`, `retry-count`, and `timeout` from the common `payment.yml` file override the corresponding values in the `application.yml` document that declared the import.
- With `dev`, `payment-dev.yml` replaces only `mode`, `timeout`, and `provider`; `retry-count` is still taken from `payment.yml`.
- With `prod`, `payment-prod.yml` replaces `mode`, `retry-count`, and `provider`; `timeout` is still taken from `payment.yml`.
- When a profile has no matching variant, only the other active sources determine the value.

The table assumes no environment variable, Java system property, CLI argument, other import, or test property overrides the keys in the example.

## 4. Activating profiles so Spring Boot selects variants

### 4.1. Via command-line argument

Running dev:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev
~~~

Running prod:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod
~~~

Omit `spring.profiles.active` if you want to observe configuration with no specific profile active.

### 4.2. Via environment variable

Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar build/libs/catalog-app.jar
~~~

Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar build/libs/catalog-app.jar
~~~

### 4.3. Via Java system property

~~~bash
java -Dspring.profiles.active=prod -jar build/libs/catalog-app.jar
~~~

Across sources declaring profiles or application properties, Spring Boot still applies standard `PropertySource` precedence. For example, `--app.payment.mode=manual` can override the `live` value from the prod file. Profiles decide **which documents apply**; precedence decides **the final value** when multiple documents supply the same key.

## 5. Demonstrating with Java and `Environment`

A small Spring Boot application can observe the values loaded from files as follows:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

import java.util.Arrays;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    ApplicationRunner showPaymentConfig(Environment env) {
        return (ApplicationArguments args) -> {
            System.out.println("activeProfiles="
                    + Arrays.toString(env.getActiveProfiles()));
            System.out.println("mode="
                    + env.getProperty("app.payment.mode"));
            System.out.println("retry-count="
                    + env.getProperty("app.payment.retry-count", Integer.class));
            System.out.println("timeout="
                    + env.getProperty("app.payment.timeout"));
            System.out.println("provider="
                    + env.getProperty("app.payment.provider"));
        };
    }
}
~~~

To run the example, add `spring-boot-starter` (and the dependencies appropriate for your real application) to the project. Only if `spring-boot-starter-web` is used does the `server.port` property take effect to control the HTTP server port.

When running:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev
~~~

the configuration output might look like:

~~~text
activeProfiles=[dev]
mode=debug
retry-count=3
timeout=15s
provider=mock
~~~

Running with `--spring.profiles.active=prod`:

~~~text
activeProfiles=[prod]
mode=live
retry-count=5
timeout=5s
provider=production
~~~

`Environment` represents effective property values. Reading individual keys with `getProperty` is a way to observe configuration after sources have been merged and overridden.

## 6. Binding imported configuration with `@ConfigurationProperties`

When the number of keys grows, use type-safe binding instead of calling `Environment.getProperty` in many places.

With the YAML contents from section 3:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String mode,
        int retryCount,
        Duration timeout,
        String provider) {
}
~~~

In the main application, enable scanning for configuration beans:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Import `org.springframework.boot.context.properties.ConfigurationPropertiesScan` and the corresponding Spring Boot classes. Because these are excerpted code illustrations, keep valid package declarations and imports in your project.

A bean consuming the configuration:

~~~java
@Component
class PaymentPrinter implements ApplicationRunner {

    private final PaymentProperties properties;

    PaymentPrinter(PaymentProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(properties.mode());
        System.out.println(properties.retryCount());
        System.out.println(properties.timeout());
        System.out.println(properties.provider());
    }
}
~~~

Import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner`, and `org.springframework.boot.ApplicationArguments`. Names like `retry-count` in YAML bind to `retryCount` via *relaxed binding*, while `5s` or `15s` are converted to `Duration`.

**Key point:** `@ConfigurationProperties` does not need to know whether a specific file came from `payment.yml` or `payment-prod.yml`. The binder only cares about the final value present in `Environment`.

## 7. Spring Boot discovers variants of *imported files*, not only `application.yml`

A common misconception is that Spring Boot automatically reads `application-prod.yml` but does not do the same for imported resources with other names. In reality, when Config Data imports a resource that supports profile-specific variants, variants of that resource **are also considered**.

Example:

~~~yaml
spring:
  config:
    import:
      - "file:./config/inventory.properties"
      - "file:./config/payment.yml"
~~~

When `prod` is active, in addition to the two base resources, Spring Boot can also consider:

~~~text
config/inventory-prod.properties
config/payment-prod.yml
~~~

You do not need to list these two variants explicitly in the import list. Each profile-specific variant applies its values according to Config Data ordering. Sharing the name `application` is not required.

Note the distinction from `spring.config.name`: that property controls the configuration name searched in standard *config locations*, whereas `spring.config.import` names the resource to import. If you have explicitly imported `payment.yml`, you do not change `spring.config.name` for Spring Boot to recognize `payment-prod.yml`.

## 8. Using `spring.config.import` inside a profile-activated document

You can place an import inside a YAML document that only applies when a profile condition matches. Example `application.yml`:

~~~yaml
spring:
  application:
    name: catalog-app

app:
  payment:
    mode: basic

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev/payment.yml"

---
spring:
  config:
    activate:
      on-profile: prod
    import: "file:./config/prod/payment.yml"
~~~

Meaning:

- The first document is the common configuration.
- The second document is active only when the `dev` profile expression matches; only then does it declare an import to the `dev` directory.
- The third document corresponds to `prod`.
- Within each import, Spring Boot can still consider profile-specific variants of the imported file itself, such as `config/prod/payment-prod.yml`, if they exist.

This differs from always importing `config/payment.yml` and letting Spring Boot automatically discover `payment-dev.yml` and `payment-prod.yml`. When the primary need is adjusting certain keys per environment, **one common import plus filename variants** is usually cleaner. Profile-specific imports are useful when environments use very different locations or sets of resources.

Inside a profile-specific document, use `spring.config.activate.on-profile` to guard the document. Do not place `spring.profiles.active` or `spring.profiles.default` inside a profile-restricted document; Spring Boot limits profile-activating properties to documents not tied to a profile condition.

## 9. Override order: main file, imported file, and profile variant

Place three configurations side by side:

~~~yaml
# application.yml
spring:
  config:
    import: "file:./config/feature.yml"
app:
  feature:
    enabled: false
    label: from-application
~~~

~~~yaml
# config/feature.yml
app:
  feature:
    enabled: true
    label: from-import
~~~

~~~yaml
# config/feature-prod.yml
app:
  feature:
    label: from-prod-import
~~~

When the `prod` profile is active, within the scope of these three documents, the effective result is typically:

~~~text
app.feature.enabled = true
app.feature.label   = from-prod-import
~~~

Explanation:

1. The main file declares `enabled=false`, `label=from-application`.
2. Contents of the imported document take precedence over the importing document for colliding keys, so `enabled=true` and `label=from-import` are considered.
3. The `feature-prod.yml` variant applies to the active profile and replaces `label` with `from-prod-import`.
4. Because the prod variant does not declare `enabled`, the value from the common `feature.yml` file continues to be used.

This illustrates a minimal set of files. If other imported resources, other profiles, `application-prod.yml`, environment variables, or CLI arguments are present, they can influence the final result. Never rely solely on filename to conclude a key is guaranteed to beat all other sources.

### When multiple imports exist

Spring Boot allows:

~~~yaml
spring:
  config:
    import:
      - "file:./config/feature.yml"
      - "file:./config/override.yml"
~~~

Imports are processed in declaration order; an import appearing later can have higher precedence than an earlier import for the same property. With `prod`, variants `feature-prod.yml` and `override-prod.yml` are also considered if present. When multiple sources share keys, verify the actual order and effective values via `Environment`.

## 10. Multiple profiles active at the same time

You can launch with:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev,metrics
~~~

If the application imports `config/payment.yml`, variants `payment-dev.yml` and `payment-metrics.yml` can be applied if they exist.

Another case:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev,prod
~~~

When multiple profiles are active and profile-specific files define the same key, Spring Boot uses a precedence strategy based on profile order—typically **the profile listed later wins** among sources at the same precedence level. Because location groups, imports, and external sources also factor in, avoid activating conflicting profiles without checking the order.

For instance:

~~~yaml
# config/payment-dev.yml
app:
  payment:
    mode: debug
~~~

~~~yaml
# config/payment-prod.yml
app:
  payment:
    mode: live
~~~

If `dev,prod` are activated together and both configurations sit at the corresponding level, `live` may become the final value. With `prod,dev`, `debug` may win. In real deployments, avoid combining `dev` and `prod` since they usually represent mutually exclusive environments.

Profile groups (`spring.profiles.group.*`) can activate multiple related profiles from a single group name; imported variants are then evaluated against the resulting set of active profiles.

## 11. Distinguishing a profile-specific imported file from directly importing a profile file

There are two distinct approaches:

**Approach A — Import the base file, automatically pick up variants**

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

When `prod` is active, Spring Boot can consider `payment-prod.yml`. This is preferred when environments share the same structure and differ only in values.

**Approach B — Explicitly import a profile file**

~~~yaml
spring:
  config:
    import: "file:./config/payment-prod.yml"
~~~

This explicitly requests `payment-prod.yml` to be imported whenever the declaring document is processed, whether or not the `prod` profile is active. It does **not** automatically make that file conditional on `prod`. If you only want this import when `prod` is active, place the import directive inside a document with `spring.config.activate.on-profile: prod` or organize the import appropriately.

Do not manually append `-prod` to an import name merely to achieve profile-specific behavior that Spring Boot already supports.

## 12. File locations, relative paths, and `optional:`

### 12.1. File paths depend on the working directory

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

`file:./config/payment.yml` is a path relative to the Java process's working directory, not necessarily the directory containing the JAR. For instance, if the JAR is in `/opt/catalog/catalog-app.jar` yet launched from `/tmp`, that location points to `/tmp/config/payment.yml`.

In a container or service manager, explicitly define the working directory or use an absolute path such as:

~~~yaml
spring:
  config:
    import: "file:/etc/catalog/payment.yml"
~~~

The variant `file:/etc/catalog/payment-prod.yml` sitting next to the base file will be considered when applicable.

### 12.2. Imports relative to the declaring resource

Spring Boot also supports relative locations when no fixed prefix such as `file:` or `classpath:` is used. For example, inside `classpath:/config/application.yml`:

~~~yaml
spring:
  config:
    import: "payment.yml"
~~~

This is an *import-relative location* and resolves relative to the resource containing the import directive. Meanwhile, `file:./config/payment.yml` is a fixed file-system path relative to the working directory. Understanding this distinction prevents "file not found" errors when moving an application between an IDE and deployment environments.

### 12.3. With or without `optional:`

If the imported file is mandatory:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

If this location does not exist, Spring Boot normally stops startup with `ConfigDataLocationNotFoundException` or a related config loading error.

If the imported file may be absent:

~~~yaml
spring:
  config:
    import: "optional:file:./config/payment.yml"
~~~

Spring Boot can skip that location. However, when a file or key is missing, values critical to the application may still be absent. `optional:` **does not create default values** and does not guarantee configuration beans will bind successfully.

### 12.4. No need to create every profile variant

If `payment.yml` already holds common configuration and only the `prod` environment needs differences, simply add `payment-prod.yml`. You do not have to create empty `payment-dev.yml` or `payment-test.yml` files. When no variant exists for a profile, the common file can still supply values.

## 13. Profile-specific files vs. multi-document YAML files

In addition to `-prod` filenames, Spring Boot lets you define multiple documents in the same YAML file using the `---` separator and `spring.config.activate.on-profile` conditions.

Example `config/payment.yml`:

~~~yaml
app:
  payment:
    mode: standard
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  payment:
    mode: debug
    timeout: 20s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  payment:
    mode: live
    timeout: 2s
~~~

When importing `config/payment.yml`, the common document along with any matching conditional documents will be processed. This is an alternative to splitting variants into three separate files: `payment.yml`, `payment-dev.yml`, and `payment-prod.yml`.

Choose the approach according to scale:

- Separate profile-specific files are easier to permission and manage when differences are large.
- Multi-document YAML works well when differences are small and readers want to see cases side by side.
- Avoid duplicating configuration for the same keys across both approaches without a clearly designed override order.

Note that `---` must begin a new document without indentation as a child key. `spring.config.activate.on-profile` accepts a profile expression; for example, `on-profile: "prod | staging"` applies the document when either profile matches.

## 14. Import configuration is evaluated during Config Data processing

Startup can be pictured as follows:

~~~text
Application starts
       |
       v
Spring Boot determines initial config sources and profiles
       |
       v
Load document containing spring.config.import
       |
       v
Resolve imported location
       |
       v
Evaluate base file and applicable profile-specific variants
       |
       v
Assemble PropertySources by Config Data precedence rules
       |
       v
Environment supplies final values to binder / beans
~~~

This diagram is a conceptual illustration, not the exact internal steps of the processor. In practice, profile resolution and Config Data reading can occur across multiple passes because documents may declare further imports and profile conditions.

The key point to remember is that **imports are processed before regular configuration beans are created and bound**. Therefore, a bean using `@ConfigurationProperties` can directly receive values from `payment-prod.yml` without manually reading filenames or managing profiles.

An imported resource may be declared in multiple places, but Spring Boot attempts to import that resource only once during Config Data processing. Do not use repeated imports of the same file as a mechanism to duplicate or manually boost precedence.

## 15. Common errors and how to check them

### Error 1: wrong filename suffix

~~~text
Correct:   payment.yml
           payment-prod.yml

Unintended: payment.yml
            prod-payment.yml
            payment.prod.yml
~~~

When importing `payment.yml`, names like `prod-payment.yml` or `payment.prod.yml` are not profile variants under the `<base>-<profile>.<extension>` convention. If you want to use a custom name, you must import that name intentionally.

### Error 2: activating a profile that differs from the variant name

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=production
~~~

The command above runs with the `production` profile; it does not automatically convert into `prod`. If you want automatic loading of a variant of `payment.yml`, name it `payment-production.yml` or change the activated profile to match the filename.

### Error 3: imported file is not in the expected directory

Check the working directory and the path in `spring.config.import`. With `file:./config/payment.yml`, the process must find `./config/payment.yml` relative to where Java was launched. Use an absolute path for diagnosis if in doubt.

### Error 4: missing base file or mandatory import

If an import specifies a mandatory location that cannot be loaded, the application may stop before creating beans. Create the file at the right location or use `optional:` **only when the file's absence is genuinely permitted**.

### Error 5: values from the profile-specific file do not appear

Check in order:

1. Is the desired profile present in `Environment.getActiveProfiles()`?
2. Do the `-<profile>` suffix and file extension match the base imported file?
3. Was the imported file actually found/loaded successfully?
4. Are YAML/properties keys spelled and indented properly?
5. Is a higher-precedence source, especially CLI or environment variables, overriding that key?

### Error 6: declaring profile activation in an inappropriate place

Do not place `spring.profiles.active` inside a YAML document already restricted by `spring.config.activate.on-profile` or inside a profile-specific configuration resource. Activate profiles from a source independent of profile conditions such as CLI, environment variables, or a valid common document.

### Error 7: diagnosing by file content instead of final value

A `payment-prod.yml` file may contain `app.payment.mode=live`, yet the program still receives `manual` if launched with:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --app.payment.mode=manual
~~~

This is property precedence behavior, not necessarily a file-selection bug. Use `Environment` or controlled diagnostic tools to tell the two situations apart.

## 16. Observing how Spring Boot processes imports and profiles

You can increase configuration processing log verbosity:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --logging.level.org.springframework.boot.context.config=TRACE
~~~

The logs show detailed Config Data processing; exact message text and log formatting may vary across versions. TRACE logging is suited to development or diagnostics and should not necessarily stay enabled long-term in production.

In Java code, print active profiles and the key under observation:

~~~java
System.out.println(Arrays.toString(env.getActiveProfiles()));
System.out.println(env.getProperty("app.payment.mode"));
~~~

If the application already uses Spring Boot Actuator, the `env` and `configprops` endpoints can help trace provenance and inspect bound configuration, provided the endpoints are enabled and properly secured. Never expose secret values in logs or endpoints just to verify an import.

## 17. Practice exercises

### Exercise 1 — Predict values from common and dev files

The main file imports `optional:file:./config/notification.yml`. Create:

~~~yaml
# config/notification.yml
app:
  notification:
    channel: email
    retries: 3
~~~

~~~yaml
# config/notification-dev.yml
app:
  notification:
    channel: console
~~~

When running with `--spring.profiles.active=dev`, what are the effective values?

**Answer:** `channel=console` and `retries=3`, assuming no other source overrides them.

### Exercise 2 — Switch profiles without changing the import

Keep:

~~~yaml
spring:
  config:
    import: "file:./config/notification.yml"
~~~

Also create `config/notification-prod.yml` containing `app.notification.channel: queue`. Run once with `dev` and once with `prod`. Verify that **no edit to `spring.config.import` is needed**, yet the `channel` value changes according to profile.

### Exercise 3 — Try multiple override sources

In `notification-prod.yml`, set `app.notification.retries: 5`. Run:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --app.notification.retries=8
~~~

Predict the result. **Answer:** `8`, because the CLI argument has higher precedence than Config Data in this scenario.

### Exercise 4 — Profile condition on an import document

In `application.yml`, create a second document with:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: test
    import: "optional:file:./config/test/notification.yml"
~~~

Run with `test` and then with `prod`. Observe when the `./config/test/notification.yml` resource is evaluated. Explain why the `test`-conditioned document does not proactively import that file when only `prod` is active.

### Exercise 5 — Diagnosing an unrecognized variant

The application imports `file:./config/report.properties`, yet when running with `prod`, the file `config/report.production.properties` is not picked up by suffix. Rename it properly to `report-prod.properties` (or adjust the profile/import logic appropriately) and test again.

## 18. Takeaways

- `spring.config.import` loads configuration from other resources; when a profile is active, **profile-specific variants of the imported resource are also considered**.
- For an import of `payment.yml`, the standard variant is `payment-<profile>.yml`, such as `payment-prod.yml`.
- There is no need to write a separate import for each variant if you only want Spring Boot to select configuration by profile automatically.
- The common version provides baseline values; the profile-specific version can override corresponding keys.
- Final values still depend on other imports, location groups, and other `PropertySource` entries; CLI or environment variables can override config data.
- Use `spring.config.activate.on-profile` if the import action itself must depend on a profile; use `-prod` variants when the imported file is common while values differ by profile.
- When configuration behaves unexpectedly, check active profiles, filenames, paths, keys, and overriding sources.

## References

- [Spring Boot 3.3 — Externalized Configuration, Importing Additional Data](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot 3.3 — Profile-specific Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.profile-specific)
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
