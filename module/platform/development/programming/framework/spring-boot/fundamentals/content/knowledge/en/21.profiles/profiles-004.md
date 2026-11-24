# application-{profile}.properties or matching YAML

In a Spring Boot application, the same source code typically has to work across multiple environments: a developer's machine, testing, staging, and production. Those environments can use different service URLs, logging levels, timeouts, or enable different features. If you had to edit Java code for every deployment, configuration would quickly become hard to manage.

Spring Boot solves this need with **Spring Profiles** combined with its **externalized configuration** system. A particularly important convention is **`application-{profile}.properties`** or **`application-{profile}.yml` / `application-{profile}.yaml`**. When a profile is activated, Spring Boot can load the corresponding configuration file and use its values to supplement or override shared configuration values.

For example:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
└── application-prod.yml
```

In the typical case:

- `application.yml` contains values applied in common.
- `application-dev.yml` contains values for the `dev` profile.
- `application-test.yml` contains values for the `test` profile.
- `application-prod.yml` contains values for the `prod` profile.

**A filename does not activate a profile by itself.** `application-prod.yml` is only used as profile-based configuration when the `prod` profile is selected through Spring Boot's configuration mechanisms. This lesson belongs to the **Profiles** chapter of *Spring Boot Fundamentals*, focusing on file naming conventions, activation methods, precedence order, combining properties and YAML, common errors, and configuration testing methods.

## 1. What are profiles and what problem do they solve?

A **Profile** is an environment/configuration-context label that Spring can use to select appropriate beans or configuration. Common names:

- `dev`: local development on a personal machine.
- `test`: running integration tests.
- `staging`: a production-like environment for testing.
- `prod`: production environment.
- `cloud`: a shared configuration set for cloud environments.
- `batch`: a background-job execution mode.

Those are only illustrative names. Spring does not enforce that profiles must be named `dev` or `prod`; teams can choose names that accurately express their deployment setup.

Suppose an application calls a partner API:

| Property | Development | Production |
| --- | --- | --- |
| Base URL | Mock service on localhost | Real partner service |
| Connect timeout | 1 second | 5 seconds |
| Business log | DEBUG | INFO or WARN |
| Notification mode | Console | Real notification system |

Business logic does not need to hard-code these values. It only needs to use configuration that Spring Boot binds into beans or reads via `Environment`; the profile decides which value source is selected.

### 1.1. Profile-based configuration differs from profile-based beans

Spring has two common ways of using profiles:

1. **Profile-specific configuration files:** `application-dev.yml` provides property values when `dev` is active.
2. **Profile-specific beans:** `@Profile("dev")` allows registering a configuration or bean only in the matching profile.

Both mechanisms share the concept of active profiles, but have different responsibilities:

- Profile-specific files determine **configuration values**.
- `@Profile` determines whether a **bean definition is registered**.

Merely having `application-dev.yml` does not mean every bean automatically switches implementations. Conversely, `@Profile("dev")` does not require an `application-dev.yml` file to exist.

## 2. application-{profile} filename syntax

With the default base name `application`, Spring Boot looks for common configuration files and profile-based variants.

| File | Role |
| --- | --- |
| `application.properties` | Shared configuration in Java properties format |
| `application.yml` | Shared configuration in YAML format |
| `application.yaml` | Shared configuration in YAML format, full extension |
| `application-dev.properties` | Configuration for the `dev` profile |
| `application-dev.yml` | YAML configuration for `dev` |
| `application-dev.yaml` | Same as `.yml` extension, for `dev` |
| `application-prod.properties` | Configuration for the `prod` profile |
| `application-prod.yml` | YAML configuration for `prod` |

The part between `application-` and the extension is the **profile name**, not a Java package name or database name.

For example:

```text
application-local.yml     -> profile "local"
application-qa.properties -> profile "qa"
application-blue.yaml     -> profile "blue"
```

### 2.1. .yml and .yaml extensions

Both `.yml` and `.yaml` represent YAML. Spring Boot supports both in its normal configuration system. Project teams should choose one consistent convention to avoid creating two files with the same purpose and losing track of which takes precedence.

### 2.2. You do not need a file for every profile

If the application only differs between `dev` and `prod`, you may only need:

```text
application.yml
application-dev.yml
application-prod.yml
```

Not having `application-test.yml` is not automatically an error. When running with the `test` profile, shared values can still come from `application.yml` and other configuration sources. Issues only arise during binding or usage if the application requires a property that has no suitable value.

### 2.3. Filenames do not activate profiles

This is a very important point:

```text
Having application-prod.yml
          ≠
Profile prod is active
```

If you do not activate `prod` via the appropriate mechanism, Spring Boot does not automatically select `application-prod.yml` just because the file sits in `resources`.

## 3. Shared configuration and profile-specific configuration

Consider an application with a shared file:

```properties
# src/main/resources/application.properties
spring.application.name=catalog-service

app.notification.mode=console
app.notification.timeout=3s
app.notification.retry-count=2

logging.level.com.example.catalog=INFO
```

In development:

```properties
# src/main/resources/application-dev.properties
app.notification.timeout=1s
logging.level.com.example.catalog=DEBUG
```

In production:

```properties
# src/main/resources/application-prod.properties
app.notification.mode=remote
app.notification.timeout=5s
logging.level.com.example.catalog=WARN
```

Suppose only the `dev` profile is active. The final values can be understood as follows:

| Key | Shared value | Dev value | Result when dev is active |
| --- | --- | --- | --- |
| `spring.application.name` | `catalog-service` | Not declared | `catalog-service` |
| `app.notification.mode` | `console` | Not declared | `console` |
| `app.notification.timeout` | `3s` | `1s` | `1s` |
| `app.notification.retry-count` | `2` | Not declared | `2` |
| `logging.level.com.example.catalog` | `INFO` | `DEBUG` | `DEBUG` |

Spring Boot does not need a full copy of all properties in each file. Profile-specific files usually contain only **the values that differ from shared configuration**.

When only `prod` is active, `mode` becomes `remote`, `timeout` becomes `5s`, and the log level becomes `WARN`. `retry-count` still takes the shared value because it is not overridden.

### 3.1. This is a property addition and override mechanism

For scalar properties such as strings, numbers, booleans, or durations, profile-based configuration can override keys with the same name declared in the shared file within the same configuration location group.

However, Spring Boot's externalized configuration system has many other sources: environment variables, JVM system properties, command-line arguments, and configuration files outside the JAR. **Profile-specific files are not an absolute highest-precedence source ahead of everything else.**

For example, when running:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod --app.notification.timeout=10s
```

The `app.notification.timeout=10s` value from the command line normally takes precedence over `5s` in `application-prod.properties`.

### 3.2. Override only what needs to change

If `app.notification.retry-count` is always 2, leave it in the shared file. Copying the same property into three files means every change must be made in multiple places and easily causes drift between environments.

A good pattern:

```text
application.properties       -> broadly applicable defaults
application-dev.properties   -> only what differs in development
application-prod.properties  -> only what differs in production
```

Do not overuse profile files to duplicate the entire application configuration.

## 4. Writing equivalent configuration in YAML

The `.properties` examples above can be converted to YAML.

Shared file:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: catalog-service

app:
  notification:
    mode: console
    timeout: 3s
    retry-count: 2

logging:
  level:
    com.example.catalog: INFO
```

Development file:

```yaml
# src/main/resources/application-dev.yml
app:
  notification:
    timeout: 1s

logging:
  level:
    com.example.catalog: DEBUG
```

Production file:

```yaml
# src/main/resources/application-prod.yml
app:
  notification:
    mode: remote
    timeout: 5s

logging:
  level:
    com.example.catalog: WARN
```

Both styles describe the same property keys:

```text
Properties: app.notification.timeout=5s

YAML:
  app:
    notification:
      timeout: 5s
```

Spring Boot "flattens" the YAML structure into appropriate property names for binding into configuration beans.

### 4.1. Note on YAML indentation

YAML relies on indentation. Incorrect example:

```yaml
app:
  notification:
  timeout: 5s
```

The snippet above places `timeout` at the same level as `notification`, not under `app.notification` as intended.

Correct snippet:

```yaml
app:
  notification:
    timeout: 5s
```

Use spaces consistently and avoid tabs in indentation. If configuration has no effect, check YAML structure and property names before suspecting profiles.

### 4.2. Colons, # symbols, and special strings

YAML has its own special symbols. When a value contains characters with syntactic meaning or that might be type-inferred, quote it:

```yaml
app:
  notification:
    label: "Catalog: Production"
    marker: "value # not a comment"
```

Do not confuse YAML keys with Java expressions. Spring Boot parses configuration first and then provides values to beans or `Environment`.

### 4.3. Do you need to migrate from .properties to YAML?

Not required. Choose based on complexity:

| Criterion | .properties | YAML |
| --- | --- | --- |
| Syntax | `key=value` | Hierarchical by indentation |
| Readability with few keys | Very convenient | Convenient |
| Expressing nested structures | Longer key names | Compact and visual |
| Indentation risk | Low | Requires care |
| Lists / maps | Needs key naming convention | Has natural syntax |
| Multi-document config in one file | Has dedicated multi-document syntax | Clear `---` |

Neither style makes profiles "stronger". They only differ in representation.

## 5. How to activate a profile

Spring Boot only knows to load `application-{profile}.*` when that profile is determined to be active or default under Spring's rules.

### 5.1. Via command line

```bash
java -jar catalog-service.jar --spring.profiles.active=dev
```

When run like this, Spring Boot can load:

```text
application.yml
application-dev.yml
```

along with other configurations in supported locations.

Switching to production:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

No Java code edits or file renames are needed.

### 5.2. Via environment variables

On Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

On Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar catalog-service.jar
```

The `SPRING_PROFILES_ACTIVE` variable maps to the `spring.profiles.active` property via Spring Boot's environment-property mapping mechanism.

This is the common approach in containers, CI/CD, and deployment environments, where code and artifacts stay identical while each environment supplies different profile values.

### 5.3. Via shared configuration

You can declare in `application.properties`:

```properties
spring.profiles.active=dev
```

Or in `application.yml`:

```yaml
spring:
  profiles:
    active: dev
```

When the application is deployed, an environment variable or command-line argument can override this value according to configuration precedence. However, **hard-coding `dev` as the active profile in an artifact shared with production is usually not a good choice**. Let the deployment environment decide the profile unless the application has a special reason.

### 5.4. Via Java API

When a launcher needs programmatic control over profiles, you can add profiles before running:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(CatalogApplication.class);
    application.setAdditionalProfiles("batch");
    application.run(args);
}
```

`setAdditionalProfiles` adds a profile to the application. It is not identical to setting `spring.profiles.active`, which is a property subject to influence from various property sources.

In most deployment systems, prefer command-line args or environment variables rather than fixing profiles in code.

## 6. Active profiles and default profiles

If no active profiles are configured, Spring uses the default profiles set. The usual default profile name is `default`.

This has a notable consequence: **`application-default.properties`** or **`application-default.yml`** can be loaded when there are no active profiles.

For example:

```text
application.yml
application-default.yml
application-dev.yml
application-prod.yml
```

If there are no active profiles, the default configuration can be applied. If `dev` is activated, the configuration for `dev` is applied under the active profile mechanism.

### 6.1. Configuring the default profile

In shared configuration you can set:

```properties
spring.profiles.default=local
```

When there are no active profiles, `local` is used as the default profile, so `application-local.properties` or its YAML variant can be loaded.

**The default profile is not an active profile automatically added to every run.** It plays a role when there are no active profiles. If the application has active profile `prod`, do not assume the `local` profile is also applied just because `spring.profiles.default=local`.

### 6.2. Avoid unsafe defaults

A setting like `spring.profiles.default=local` can be convenient when running on a personal machine, but if deployment forgets to set `SPRING_PROFILES_ACTIVE`, the production application could run with local configuration.

For critical systems, require the environment to specify the profile explicitly, validate configuration at startup, and avoid providing risky fallback values.

## 7. Precedence: shared file, profile file, and external sources

This is the most error-prone area because **profile files are only one layer in Spring Boot's Config Data system**.

### 7.1. Within the same location

For a location being searched by Spring Boot, a profile-specific configuration file can override properties with the same key in the shared file.

For example:

```properties
# application.properties
app.feature.enabled=false
```

```properties
# application-prod.properties
app.feature.enabled=true
```

When the `prod` profile is active and no higher-precedence source overrides it, the final value of `app.feature.enabled` is `true`.

### 7.2. Files outside the JAR

By default, Spring Boot looks for config data from common locations on the classpath and filesystem, such as `classpath:/`, `classpath:/config/`, `./`, `./config/`, and additional locations under Boot's configuration rules.

Visualize:

```text
artifact.jar
  └── BOOT-INF/classes/application.yml
  └── BOOT-INF/classes/application-prod.yml

./config/
  └── application-prod.yml
```

Files outside the JAR can override values from files packaged inside the JAR under default precedence rules. This is the foundation of externalized configuration: one artifact, with each environment supplying appropriate external configuration data.

**Do not infer precedence solely from the `-prod` suffix.** You need to know the location, source type, and overrides supplied at startup.

### 7.3. High-precedence sources

In the standard Spring Boot configuration model, command-line properties and environment variables can override values in Config Data files.

For example:

```text
Inside JAR:
  application-prod.yml    app.notification.timeout=5s

In environment:
  APP_NOTIFICATION_TIMEOUT=8s

In CLI:
  --app.notification.timeout=10s

Resolved value:
  10s (if no higher-precedence source intervenes)
```

This is a high-level example of precedence; the system also supports other sources such as system properties, JSON configuration, test properties, and specialized mechanisms. When discrepancies occur, inspect actual property sources and origins rather than trying to memorize the entire order as a single rule of thumb.

### 7.4. .properties and YAML with the same name in the same location

If both `application-prod.properties` and `application-prod.yml` exist in the same location, in standard Spring Boot **the `.properties` file takes precedence over the YAML file** for overlapping properties.

For example:

```text
config/
├── application-prod.properties
└── application-prod.yml
```

This situation should be avoided: maintainers might edit YAML and see no effect because the same-key property in `.properties` is winning.

Recommendation: **each configuration group at a given location should stick to one format** unless there is a special integration requirement.

## 8. Multiple active profiles simultaneously

Spring allows activating multiple profiles:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

Boot can then load:

```text
application.yml
application-prod.yml
application-cloud.yml
```

This is one way to split configuration across multiple axes:

- `prod`: production policies.
- `cloud`: values for the cloud environment.

### 8.1. A profile listed later can win for the same key

Suppose:

```yaml
# application-prod.yml
app:
  http:
    timeout: 4s
```

```yaml
# application-cloud.yml
app:
  http:
    timeout: 8s
```

With `spring.profiles.active=prod,cloud`, among profile-specific files in the same location processed under Spring Boot's last-wins rule, the value from `cloud` can override the value from `prod`.

If changed to `spring.profiles.active=cloud,prod`, the result for overlapping keys can change accordingly.

Do not combine multiple profiles arbitrarily if they define many conflicting properties. Configuration becomes unpredictable and risky when adding new profiles.

### 8.2. Presence of a profile does not guarantee a dedicated property value

Not having `application-cloud.yml` does not render the `cloud` profile invalid. A profile can be used for `@Profile("cloud")` or `spring.config.activate.on-profile` documents. A profile-specific file is one property-supply mechanism, not the sole definition of a profile.

### 8.3. Multi-axis models require clear intent

For example, you might choose:

```text
prod + cloud
prod + onprem
dev + local
test + ci
```

However, you must design ownership: which keys belong solely to environment, which belong to infrastructure, and whether any keys are overridden across multiple files. If both `prod` and `cloud` set `app.http.timeout`, document the expected precedence explicitly.

## 9. Profile-specific YAML documents in the same file

Besides creating separate `application-dev.yml` and `application-prod.yml` files, Spring Boot supports **multi-document YAML** with the `---` marker. Each document can be activated using `spring.config.activate.on-profile`.

Example:

```yaml
# application.yml: shared configuration
app:
  notification:
    mode: console
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  notification:
    timeout: 1s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  notification:
    mode: remote
    timeout: 5s
```

Meaning:

- The first document has no activation condition, so it provides shared configuration.
- The second document is applied only when `dev` matches.
- The third document is applied only when `prod` matches.

This is an alternative to separate files when the amount of configuration is small. For larger projects, `application-{profile}.yml` files are often more convenient for separating responsibilities.

### 9.1. on-profile supports profile expressions

You can use profile expressions:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

This document is applied when the expression requiring both `prod` and `cloud` matches.

Another example:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

The document matches when `prod` is not active under profile expression semantics. When writing expressions, quote them to avoid conflicts with YAML syntax.

### 9.2. on-profile does not activate profiles

`spring.config.activate.on-profile=prod` means **"apply this document only when profile prod matches"**, not "set prod as an active profile".

If you want to activate `prod`, use the `spring.profiles.active` property from a valid configuration source, environment variable, or command line.

### 9.3. Avoid repeating the same configuration in multiple places unnecessarily

If the project already has `application-prod.yml`, redefining the same key in an `on-profile: prod` document inside `application.yml` can make it hard for maintainers to tell which source wins.

Pick one strategy:

- A shared file + `application-{profile}.*` files.
- Or a single multi-document YAML file for small, clear configurations.

They can be combined, but only when ownership and precedence order are explicitly defined.

## 10. Valid places to put spring.profiles.active

An important rule in modern Spring Boot's Config Data system is that properties determining **which profiles are activated** must be declared in a valid location, not inside a file that is only loaded after that profile is already active.

### 10.1. Valid configuration

In the shared file `application.properties`:

```properties
spring.profiles.active=dev
```

Or from the command line:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Or from the environment:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

### 10.2. Do not put active in application-prod.yml

Invalid configuration example:

```yaml
# application-prod.yml
spring:
  profiles:
    active: prod
```

Modern Spring Boot disallows `spring.profiles.active` in a profile-specific resource or a document activated by `spring.config.activate.on-profile`. This avoids a logical loop: Spring must know which profiles are active to load the file, yet the file tries to alter the set of active profiles.

In Spring Boot versions using Config Data, this situation can raise an error such as `InvalidConfigDataPropertyException` during startup.

### 10.3. Do not put active in a document with on-profile

Invalid example:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

This document is only applied after `dev` has already matched, yet tries to set a new active profile. That design is not allowed under modern Config Data rules.

### 10.4. default, include, and group also have their own rules

Properties `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group.*` must likewise be placed in **non-profile-specific** sources according to the corresponding rules. Do not move them into `application-prod.yml` or an `on-profile: prod` document expecting Boot to alter the profile set mid-load.

Think in two phases:

1. Determine the set of profiles to process.
2. Load the relevant profile-specific config data.

Separating these responsibilities keeps configuration results consistent.

## 11. spring.profiles.include and profile groups

When one profile always entails other profiles, Spring Boot provides mechanisms for declaring additions.

### 11.1. spring.profiles.include

In shared configuration:

```properties
spring.profiles.include=common-observability
```

This property is used to **add** profiles to the processed profile set, rather than merely serving as an alternative to `spring.profiles.active`.

Do not use include as a tangled chain of conditions; it fits when a common configuration set applies alongside other profiles.

### 11.2. Profile groups

You can declare profile groups in non-profile-specific configuration:

```properties
spring.profiles.group.production[0]=prod
spring.profiles.group.production[1]=cloud
spring.profiles.group.production[2]=observability
```

When activating the group:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring Boot can expand the profile set to include the members `prod`, `cloud`, and `observability`. Thus, operators only pick a single high-level profile label.

YAML equivalent:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - observability
```

### 11.3. When should you use groups?

Profile groups fit when configuration sets are reusable and clearly named. For example:

- `production` comprising `prod` + `observability`.
- `local-integration` comprising `dev` + `mock-services`.

However, do not create many poorly documented nested groups, as it becomes hard to trace why a given profile-specific file was loaded.

## 12. Combining profile files with @Profile

Suppose an application has two implementations for the same interface:

```java
public interface MessageSender {
    void send(String message);
}
```

Development implementation:

```java
@Component
@Profile("dev")
public class ConsoleMessageSender implements MessageSender {

    @Override
    public void send(String message) {
        System.out.println("[DEV] " + message);
    }
}
```

Production implementation:

```java
@Component
@Profile("prod")
public class RemoteMessageSender implements MessageSender {

    @Override
    public void send(String message) {
        // Send via configured external service.
    }
}
```

Profile-based configuration can supply timeouts/endpoints for implementations:

```yaml
# application-prod.yml
app:
  message:
    timeout: 5s
    endpoint: "https://messages.example.invalid/api"
```

When `prod` is active:

1. Spring processes beans with a matching `@Profile("prod")`.
2. The Config Data system loads properties corresponding to `prod`.
3. Beans receive the needed properties via `@ConfigurationProperties` or other binding mechanisms.

However, if `dev` and `prod` are active simultaneously, both implementations can be registered and constructor injection of the `MessageSender` interface can become ambiguous. Design profile combinations, `@Primary`, or qualifiers appropriately.

**Profile files do not automatically resolve conflicts among multiple beans of the same type.** Profiles and DI candidate resolution are two mechanisms that must work together.

## 13. Reading profile-specific values in Java code

Spring Boot recommends using strongly typed configuration for a group of related properties.

### 13.1. Example with @ConfigurationProperties

Shared file:

```yaml
# application.yml
app:
  downstream:
    base-url: "https://service.example.invalid"
    connect-timeout: 3s
```

Dev file:

```yaml
# application-dev.yml
app:
  downstream:
    base-url: "http://localhost:9090"
    connect-timeout: 1s
```

Prod file:

```yaml
# application-prod.yml
app:
  downstream:
    base-url: "https://api.partner.example.invalid"
    connect-timeout: 5s
```

Java record:

```java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.downstream")
public record DownstreamProperties(
        String baseUrl,
        Duration connectTimeout
) {
}
```

In Spring Boot where constructor binding for records is supported, you can register it using `@ConfigurationPropertiesScan` on the main application class:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Service using typed properties:

```java
package com.example.catalog.service;

import com.example.catalog.config.DownstreamProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerClientService {

    private final DownstreamProperties properties;

    public PartnerClientService(DownstreamProperties properties) {
        this.properties = properties;
    }

    public String target() {
        return properties.baseUrl();
    }
}
```

With `dev`, `target()` receives the localhost URL; with `prod`, it receives the production URL. Java code does not have to write `if ("prod".equals(...))` to pick the URL.

### 13.2. Why use Duration instead of String?

Spring Boot Binder can convert values like `1s`, `500ms`, or `5m` into `Duration`. This gives configuration clear types and avoids manually parsing strings across multiple services.

If a property is declared in an invalid format, the application can report a binding error during initialization instead of silently using an unsuitable value.

### 13.3. @Value for a single simple property

When reading only one small property:

```java
@Component
class GreetingPrinter {

    private final String banner;

    GreetingPrinter(@Value("${app.banner:Hello}") String banner) {
        this.banner = banner;
    }
}
```

This example uses a placeholder with a default value `Hello`. With multiple related properties, `@ConfigurationProperties` is usually easier to maintain because it groups configuration and supports clear validation/binding.

### 13.4. Environment for special needs

`Environment` also provides lookup methods:

```java
@Component
class ProfileDiagnostics {

    private final Environment environment;

    ProfileDiagnostics(Environment environment) {
        this.environment = environment;
    }

    void printCurrentMode() {
        System.out.println(
                environment.getProperty("app.notification.mode")
        );
    }
}
```

Do not let business code query active profiles in every branch to decide behavior. Prefer injecting configuration values or the right strategy bean, as that reduces coupling to environment names.

## 14. Lists and maps when overriding by profile

Not every configuration type merges the same way. This is a silent source of bugs when learners move from scalar properties to YAML lists.

### 14.1. Lists are usually replaced, not appended element by element

Suppose shared configuration has:

```yaml
app:
  routes:
    - "/health"
    - "/catalog"
```

`prod` configuration:

```yaml
app:
  routes:
    - "/public"
```

When binding a `List` with `@ConfigurationProperties`, Spring Boot normally takes **the list from the highest-precedence matching source**, rather than automatically concatenating into three elements.

If the goal is a list containing `/health`, `/catalog`, and `/public`, you must declare the full list in the winning source or structure configuration differently. Do not rely on an expectation that YAML lists will append.

### 14.2. Maps can be combined by key

For a map:

```yaml
# application.yml
app:
  labels:
    owner: platform
    stage: shared
```

```yaml
# application-prod.yml
app:
  labels:
    stage: production
```

When binding maps under Spring Boot's mechanism, keys can be combined from multiple sources: `owner` keeps the shared value, while `stage` takes the higher-precedence value.

However, exact behavior also depends on map value types and binding rules; for complex objects or nested lists, test the actual binding result rather than guessing from YAML structure.

### 14.3. Do not treat YAML as a generic deep-merge

Spring Boot works with property sources and binders, not by simply merging two YAML trees with an unconditional deep-merge algorithm. For collections, testing actual binding is the safe approach.

## 15. Secret values in profile-specific files

A common mistake is committing production passwords into `application-prod.yml`:

```yaml
spring:
  datasource:
    username: production_user
    password: my-real-password
```

That is not a safe way to manage secrets. Files in the repository or JAR can often be read by many people with access to the artifact.

Secrets should come from environment variables, a secret manager, or the platform's secure configuration source.

Example using placeholders:

```yaml
# application-prod.yml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal.example:5432/catalog"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
```

Here, `${DB_USERNAME}` and `${DB_PASSWORD}` are placeholders resolved by Spring from Environment, not real values. The deployment platform must provide the corresponding variables.

### 15.1. Do not put weak default secrets

Avoid patterns like:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD:password123}"
```

If an environment variable is accidentally omitted in production, the application could start with a weak secret. For required and sensitive information, it is usually better to fail clearly when configuration is missing than silently fall back to an unsafe default.

### 15.2. Logs and Actuator must also be protected

Endpoints `/actuator/env`, `/actuator/configprops`, and debug logging can reveal configuration structure, property sources, or internal metadata. Do not expose them arbitrarily to public users. Spring Boot has sanitization mechanisms, but do not treat them as an excuse to skip access control.

## 16. External configuration outside the JAR per profile

A major benefit of externalized configuration is not needing to rebuild the artifact whenever a URL, timeout, or logging level changes.

For example, the project builds:

```text
deploy/
├── catalog-service.jar
└── config/
    ├── application.yml
    └── application-prod.yml
```

If run from the `deploy` directory with matching default location settings:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Spring Boot can load `./config/application-prod.yml` outside the JAR. Values outside the JAR can override values packaged inside the artifact under default precedence.

### 16.1. The ./ path is the working directory

`./config/` is resolved relative to the **process working directory**, not necessarily the directory containing the JAR file.

If launched as:

```bash
cd /opt/app
java -jar /srv/releases/catalog-service.jar --spring.profiles.active=prod
```

then relative paths like `./config/` resolve relative to `/opt/app`, not automatically to `/srv/releases`.

This is a frequent cause when a file exists on disk yet Spring Boot does not find it because a service manager or Docker `WORKDIR` differs from expectations.

### 16.2. spring.config.location

You can specify locations to load using `spring.config.location`, for example:

```bash
java -jar app.jar --spring.config.location=optional:file:./deployment-config/
```

**Note:** `spring.config.location` replaces the default location set. If you want to keep defaults and add an extra location, `spring.config.additional-location` is usually more suitable.

### 16.3. spring.config.additional-location

Example:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./deployment-config/
```

Boot keeps the default locations and also checks the new location according to Config Data precedence rules. Profile-specific variants at the added location can also be considered.

### 16.4. The optional: prefix

`optional:` indicates that a specified location/resource may not exist without necessarily causing startup to fail because that location is missing.

Do not use `optional:` for sources containing **mandatory** configuration needed for the application to operate safely. If a file holds critical endpoints/secrets, silently skipping it can cause the application to use wrong defaults.

### 16.5. When location settings are read

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` participate in the **phase that determines where to load Config Data**. Therefore, they need to be provided early enough—for example via command-line arguments, environment variables, or JVM system properties—rather than being placed inside the very file Boot does not yet know where to find.

## 17. Importing additional configuration from a profile file

Spring Boot also supports `spring.config.import` to import another Config Data source. This is an advanced mechanism when configuration is split by module or supplied externally.

Example:

```properties
# application-prod.properties
spring.config.import=optional:file:./external/catalog-prod.properties
```

When the `prod` profile is loaded, this document can import the additional configuration source. Imported content participates in Config Data precedence rules; importing is not simply text concatenation into the original file.

### 17.1. Importing does not replace profiles

`spring.config.import` specifies additional configuration sources. `spring.profiles.active` determines the set of profiles processed. Keep these two responsibilities distinct.

If the imported document has profile-specific variants, the Config Data system can evaluate matching variants according to Boot's rules.

### 17.2. Do not create hard-to-trace import chains

If `application-prod.yml` imports A, A imports B, and B depends on the environment and multiple conditions, finding the origin of a property can become very hard. Set clear ownership rules:

- Shared configuration belongs to the application.
- Deployment configuration belongs to infrastructure.
- Sensitive configuration belongs to the secret manager.
- Module configuration contains only that module's keys.

## 18. Testing profile-based configuration

Do not wait until production to discover that `application-prod.yml` has wrong indentation, missing properties, or unintended overrides.

### 18.1. Using @ActiveProfiles in tests

Spring Test supports `@ActiveProfiles`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.catalog.config.DownstreamProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DevelopmentConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsDevelopmentOverrides() {
        assertThat(properties.baseUrl())
                .isEqualTo("http://localhost:9090");
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(1));
    }
}
```

`@SpringBootTest` initializes the Spring Boot application context for the test. `@ActiveProfiles("dev")` chooses the profile to test; the Config Data system loads values from `application-dev.yml` following normal rules.

### 18.2. Testing the production profile

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsProductionOverrides() {
        assertThat(properties.baseUrl())
                .isEqualTo("https://api.partner.example.invalid");
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

In this test, verify binding and configuration only; do not let tests automatically call real production services. Mock clients that perform network calls or test property binding using a small context as appropriate.

### 18.3. Testing when no profile is active

Another test can verify default configuration:

```java
@SpringBootTest
class DefaultConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsCommonDefaults() {
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
```

If the test execution environment sets `spring.profiles.active` or `spring.profiles.default` on its own, results may vary. Tests should control environment/profiles to avoid depending on a developer machine or CI setup.

### 18.4. Testing multiple profiles

You can use:

```java
@SpringBootTest
@ActiveProfiles({"prod", "cloud"})
class CloudProductionConfigurationTest {
    // Check overlapping keys and expected precedence order.
}
```

Do not only assert that the context starts. Assert important properties such as endpoints, timeouts, feature flags, or beans selected by profile.

### 18.5. Distinguishing test overrides from profile files

In `@SpringBootTest(properties = "...")`, values provided directly by the test can override `application-dev.yml`. For example:

```java
@SpringBootTest(properties = "app.downstream.connect-timeout=9s")
@ActiveProfiles("dev")
class OverrideTest {
}
```

If the test sees `9s`, that is not proof that `application-dev.yml` contains `9s`. To test profile files, minimize unnecessary test overrides and check origins when results differ from expectations.

## 19. Observing active profiles while the application runs

Spring provides an API to read the profile set:

```java
@Component
class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(environment.getActiveProfiles())
        );
        System.out.println(
                "Default profiles: "
                        + Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
```

The example requires imports such as `java.util.Arrays`, `org.springframework.boot.ApplicationRunner`, `org.springframework.boot.ApplicationArguments`, `org.springframework.core.env.Environment`, and `org.springframework.stereotype.Component`.

### 19.1. getActiveProfiles() can be an empty array

If no active profile is explicitly set, `getActiveProfiles()` can be empty while `getDefaultProfiles()` contains `default` or a configured default profile.

Do not conclude "no profile is being used" just because the active array is empty. You must account for default profiles.

### 19.2. Spring Boot logs active profiles

At startup, Spring Boot typically logs information about active/default profiles. This is the first place to check when `application-prod.yml` is not loaded.

Never print the entire Environment or property sources to production logs because they may contain sensitive information.

### 19.3. Actuator env and configprops

In an application with Spring Boot Actuator, endpoints such as `/actuator/env` and `/actuator/configprops` can help investigate resolved properties and bound configuration.

Available endpoints and detail levels depend on exposure/security/sanitization configuration. Expose them only to appropriate environments and authorized users; do not open them publicly just to view profile values.

### 19.4. Configuration-loading phase logs

When investigating which files were discovered, you can temporarily increase logging for Config Data:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

This is a diagnostic technique for development or controlled incidents. Logs can be very verbose and may reveal paths/configuration metadata. Turn it back off once the cause is found.

## 20. Common errors with application-{profile}

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| `application-dev.yml` has no effect | `dev` is not active | Check `spring.profiles.active` and startup logs |
| Profile is active yet a property does not change | Higher-precedence source, wrong key, or file not in a searched location | Check Environment / property origin and path |
| YAML fails to bind properly | Wrong indentation or mismatched key name | Check YAML structure and `@ConfigurationProperties` class |
| `application-prod.yml` exists yet is not loaded | Different profile active or file outside config location | Check filename, working directory, CLI config locations |
| Putting `spring.profiles.active` in a profile file causes an error | Activation property placed in an invalid location | Move active profile to a non-profile-specific source or environment |
| Value in YAML does not win | A `.properties` file with the same base/location has the same key | Choose one format; avoid duplicate files |
| When activating `prod,cloud`, unexpected value appears | Both files override the same key, profile order, or another source intervenes | Check profile order and property sources |
| List loses shared elements | List binding was replaced by a higher-precedence source | Declare the full required list in the winning source |
| Test profile accidentally calls real service | Test uses production profile and real client initializes automatically | Mock clients, isolate integration, and define test scope |
| Secret missing on deploy | Secret not supplied by environment / secret manager | Verify platform injection and validation |
| App behaves differently between local and container | Working directory or config location differs | Check `WORKDIR` and `./config/` path |

### 20.1. Do not fix by hard-coding profiles everywhere

If a profile file is not loaded, it can be tempting to patch individual beans:

```java
if ("prod".equals(activeProfile)) {
    timeout = Duration.ofSeconds(5);
}
```

This scatters environment policy into business code and makes the system hard to test. Normally, fix config discovery or property precedence at the configuration layer, then inject typed properties into services.

### 20.2. Do not use profile names as a substitute for security

Putting `@Profile("prod")` on a security configuration alone is not enough to keep other environments safe. Security policies should have protective defaults, explicit mandatory configuration, and independent tests, rather than relying entirely on a profile label that can easily be forgotten at startup.

## 21. Investigation steps when profile configuration is not applied

Suppose `application-prod.yml` declares `app.downstream.connect-timeout=5s` yet the application uses `3s`.

**Step 1 — Identify the actually active profiles.** Read startup logs or `Environment.getActiveProfiles()`. If `prod` is absent, not selecting the file is expected.

**Step 2 — Check the filename.** Ensure it is exactly `application-prod.yml`, not `applications-prod.yml`, `application-production.yml`, or an extension/suffix that does not match the actual profile name.

**Step 3 — Check the location.** Is the file in `src/main/resources`, on the runtime classpath, or in an external location outside the JAR that Spring Boot searches? Does `./config/` match the working directory?

**Step 4 — Check YAML structure/keys.** For example, is `connect-timeout` properly nested under `app.downstream`? With a typo, the property becomes a different key.

**Step 5 — Find overriding sources.** Is a CLI `--app.downstream.connect-timeout=3s`, environment variable, or external config winning?

**Step 6 — Check dual formats.** Do both `application-prod.properties` and `application-prod.yml` exist in the same location?

**Step 7 — Check binding.** Is `DownstreamProperties` registered, and are its prefix and property names correct? Are there validation or type conversion errors?

**Step 8 — Verify the result.** Write a test or run the application in a controlled environment, read the value from the bound bean, and record the final configuration.

An incident record template:

```text
Expected profile:
Observed active/default profiles:
Expected configuration file:
File location / working directory:
Expected property:
Observed resolved value:
Override source (if any):
Root cause:
Change applied:
Verification:
```

These details help distinguish **file not discovered**, **profile not activated**, **property overridden**, and **incorrect binding**.

## 22. Practice exercises

### Exercise 1 — Converting between .properties and YAML

Create shared configuration with `application.properties`:

```properties
app.banner=Welcome
app.timeout=3s
```

Create `application-dev.properties` overriding timeout with `1s`. Then convert both files to YAML in another demo project. Explain why both representations produce the same property values.

### Exercise 2 — Activating dev/prod

Create `application.yml`, `application-dev.yml`, and `application-prod.yml`, with each profile file overriding only `app.banner`. Run:

```bash
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=prod
```

Observe the value via `Environment.getProperty("app.banner")`.

### Exercise 3 — Checking the default profile

Create `application-default.yml` with a distinct banner. Run the application with no active profile, then run with `dev`. Determine when the default value is used.

### Exercise 4 — Multiple active profiles

Create `application-prod.yml` and `application-cloud.yml` overriding the same property. Run with `prod,cloud` and then `cloud,prod`. Record the results and explain the application order within the same location.

### Exercise 5 — Distinguishing @Profile from profile-specific files

Create two beans implementing `MessageSender` with `@Profile("dev")` and `@Profile("prod")`. At the same time, use `application-dev.yml` and `application-prod.yml` to configure timeout.

Explain the difference between selecting beans and selecting properties. Try activating both profiles to observe the multiple-beans-of-same-type issue.

### Exercise 6 — Using @ConfigurationProperties

Create a `DownstreamProperties` record with `String baseUrl` and `Duration connectTimeout`. Declare shared, dev, and prod values. Write two `@SpringBootTest` classes with `@ActiveProfiles("dev")` and `@ActiveProfiles("prod")` to verify binding.

### Exercise 7 — Testing external configuration files outside the JAR

Package the application with a default `application.yml`. Create a `./config` directory next to the working directory and place `application-prod.yml` inside it. Run with profile `prod`, determine which file is used, and try changing the working directory to see the effect.

### Exercise 8 — Finding configuration errors

Intentionally introduce three errors in a demo project:

1. Misname the file `application-production.yml` while activating `prod`.
2. Put `spring.profiles.active` inside `application-prod.yml`.
3. Have both `application-prod.properties` and `application-prod.yml` containing different values for the same key.

For each case, predict the symptom and the proper layer to fix it.

### Exercise 9 — Lists and maps

Create a `List<String>` and a `Map<String, String>` in `@ConfigurationProperties`. Declare shared values, then declare partial values in `application-prod.yml`. Determine the actual bound result and explain the difference between list replacement and map key overriding.

### Exercise 10 — Designing secure production configuration

An application needs a datasource URL, username, and password in production. Decide which values can live in `application-prod.yml` and which belong in a secret manager/environment. Design validation so the application fails clearly when required secrets are missing.

## 23. Summary

The **`application-{profile}.properties`** or **`application-{profile}.yml` / `application-{profile}.yaml`** convention allows Spring Boot to manage differences between environments without modifying business code. The shared file carries shared values; profile-specific files override only what needs to differ. Spring Boot selects profile-specific documents based on active/default profiles and combines them with other property sources according to Config Data rules.

Core principles:

- **Filenames do not activate profiles.** Profiles must be chosen via `spring.profiles.active`, default profiles, appropriate APIs, or corresponding mechanisms.
- **Profile-specific config overrides shared values** for matching keys when precedence conditions allow, but does not always beat command-line arguments, environment variables, or external configuration.
- **`.properties` and YAML are two representations.** Avoid using both with the same base name/location simultaneously, as it easily causes conflicts.
- **Multiple active profiles are ordered.** When overriding the same key in the same location, the later profile can generally win.
- **`application-default.*` applies when there are no active profiles.** The default profile is not automatically used alongside every active profile.
- **`spring.config.activate.on-profile` only selects a document**; it does not activate a new profile.
- **Do not place `spring.profiles.active` or profile-expanding properties in profile-specific files.** Provide them early enough from a valid configuration source.
- **Pay attention to how lists and maps bind.** Lists are typically replaced; maps can combine keys.
- **Do not commit production secrets to repositories or JARs.** Use external secret sources and clear validation.
- **Use `@ConfigurationProperties` and profile-based tests** to reduce ad-hoc property reads in business code.

When a configuration value is not what you expect, follow the chain **which profiles are active → which files are found → which location and format take precedence → which property overrides → which bean receives the final value**. Understanding this chain is the foundation for deploying the same Spring Boot application across multiple environments predictably, testably, and safely.
