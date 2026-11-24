# Adding Profiles with `spring.profiles.include`

## 1. Why does an application need to include profiles?

In Spring Boot, **profiles** help select configuration and application components suited to each runtime scenario. An application can have `dev` for development, `test` for testing, and `prod` for production deployment. Beyond those environments, the application may also need shared functional configuration groups, such as `audit` (activity logging), `metrics` (instrumentation), or `shared-db` (shared database connectivity).

Suppose that when running in production, the application must simultaneously activate:

- `prod`: production-specific parameters;
- `metrics`: metrics configuration;
- `audit`: event-recording components.

You could list all of them via `spring.profiles.active=prod,metrics,audit`. However, if `metrics` and `audit` are always required by the application, operators have to remember to pass them in every launch command.

**`spring.profiles.include` solves the need to append profiles:** profiles declared via `include` are added to the active profiles set. It is useful for enabling one or more shared profiles while still allowing the deployment environment to choose the primary profile via `spring.profiles.active`.

Initial model:

```text
Launch command:           --spring.profiles.active=prod
application.yml:          spring.profiles.include=[metrics, audit]

Active profile set:       metrics, audit, prod
                          ↑ included      ↑ selected at runtime
```

Each profile in the active set can activate matching configuration documents and Spring components annotated with `@Profile`.

## 2. What is `spring.profiles.include`?

`spring.profiles.include` is a Spring Boot configuration property used to **add profile names** to the active profiles list during application initialization.

Example in `src/main/resources/application.yml`:

```yaml
spring:
  profiles:
    include:
      - metrics
      - audit
```

Equivalent in `application.properties`:

```properties
spring.profiles.include=metrics,audit
```

Both forms represent a list containing `metrics` and `audit`. They are **profile names**, not paths to configuration files. Spring Boot uses these names to activate profile behavior and locate matching configuration documents, if any exist.

For example, an application might have:

```text
src/main/resources/
├── application.yml
├── application-metrics.yml
├── application-audit.yml
└── application-prod.yml
```

In this case:

- `application.yml` provides non-profile-specific configuration and declares `include`.
- `application-metrics.yml` holds configuration applied when `metrics` is active.
- `application-audit.yml` holds configuration applied when `audit` is active.
- `application-prod.yml` holds configuration applied when `prod` is active.

A profile **can still be activated even if no corresponding `application-<profile>.yml` file exists**. For example, `@Profile("audit")` can still control bean registration. Therefore, do not treat profiles merely as file-reading switches.

## 3. Simple practice: adding a shared profile

Suppose the application has two files.

File `application.yml`:

```yaml
spring:
  profiles:
    include:
      - metrics

demo:
  mode: normal
  metrics-enabled: false
```

File `application-metrics.yml`:

```yaml
demo:
  metrics-enabled: true
  metrics-export-interval: 15s
```

When running:

```bash
java -jar app.jar
```

The `metrics` profile is added to the active profile set. Assuming no higher-precedence configuration source overrides them, the values are:

| Property | Value | Source explanation |
| --- | --- | --- |
| `demo.mode` | `normal` | From `application.yml` |
| `demo.metrics-enabled` | `true` | From `application-metrics.yml` |
| `demo.metrics-export-interval` | `15s` | From `application-metrics.yml` |

Note: `application-metrics.yml` is not loaded because the filename appeared directly in `include`. Spring Boot **activates the `metrics` profile**, and then Config Data can load documents for that profile.

If you remove `spring.profiles.include` and do not activate `metrics` another way, configuration for the `metrics` profile is no longer selected simply because the file exists.

## 4. Distinguishing `spring.profiles.active` and `spring.profiles.include`

The two properties have different meanings.

| Property | Primary role | Example |
| --- | --- | --- |
| `spring.profiles.active` | Selects active profiles, usually decided at deployment | `prod` |
| `spring.profiles.include` | Adds profiles to the active set | `metrics,audit` |

Example:

```yaml
# application.yml
spring:
  profiles:
    include: metrics
```

Run the application with:

```bash
java -jar app.jar --spring.profiles.active=prod
```

The application can activate both `metrics` and `prod`. Choosing `prod` via the command line **does not discard** `metrics` added by `include`.

Compare this with declaring `spring.profiles.active` in two sources:

```properties
# application.properties
spring.profiles.active=dev
```

```bash
java -jar app.jar --spring.profiles.active=prod
```

When only those two `active` settings exist, the command-line value has higher precedence so `prod` replaces the `dev` choice in the file. By contrast, `include` adds profiles through its own mechanism rather than acting as a second `active` value.

Do not think of `include` as a command that “always beats everything.” It only adds profiles; **final application property values** still follow property source precedence order.

## 5. Profile order and results when properties overlap

In Spring Boot's profile processing, **included profiles are added before active profiles**. Order matters when multiple profile-specific configuration documents contain the same key; across equivalent profile documents, a profile appearing later can override a profile appearing earlier.

Example using three files:

```yaml
# application.yml
spring:
  profiles:
    include: metrics

demo:
  message: "base"
```

```yaml
# application-metrics.yml
demo:
  message: "metrics"
  monitoring: true
```

```yaml
# application-prod.yml
demo:
  message: "prod"
  endpoint: "https://example.invalid"
```

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

The profile list in this example contains `metrics` and `prod`, with `metrics` added before `prod`. In this simple file structure, the expected result is:

```text
demo.message    = prod
demo.monitoring = true
demo.endpoint   = https://example.invalid
```

Explanation:

1. `application.yml` sets the common value `demo.message=base`.
2. `application-metrics.yml` sets `demo.message=metrics`.
3. `application-prod.yml` sets `demo.message=prod` and in this scenario takes precedence to override the duplicate key.
4. `demo.monitoring` exists only in the `metrics` configuration so it is preserved.

**Separate profile precedence from property source precedence.** An environment variable, JVM property, or command-line argument with higher precedence than Config Data can still override `demo.message`. If external files outside the JAR or import declarations exist, full Config Data ordering must be considered.

## 6. Valid places to declare `spring.profiles.include`

An important Spring Boot restriction is:

**`spring.profiles.include` may only be declared in non-profile-specific configuration documents.**

Valid example in base `application.yml`:

```yaml
spring:
  profiles:
    include:
      - metrics
      - audit
```

Or using non-profile-specific `application.properties`:

```properties
spring.profiles.include=metrics,audit
```

Do not place `spring.profiles.include` inside `application-prod.yml` to include `metrics` only when `prod` is active:

```yaml
# INVALID: application-prod.yml
spring:
  profiles:
    include: metrics
```

Similarly, do not place it inside a YAML document activated by `spring.config.activate.on-profile`:

```yaml
# INVALID: profile-specific document
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics
```

This is not merely a value-precedence issue; Spring Boot restricts using profile-activation control properties inside documents that are themselves selected only after profiles are determined. Invalid placement can cause startup to fail with a configuration error, such as an exception regarding an invalid property in a profile-specific document.

If you want a group-like profile name to activate other profiles, see **profile groups** in the next section instead of putting conditional `include` inside `application-prod.yml`.

## 7. Using profile groups when one profile should bring in several others

Suppose an operator only wants to specify `prod`, while the application should automatically activate `proddb` and `prodmq` whenever `prod` is selected.

Spring Boot provides **profile groups** to express this relationship:

```yaml
# application.yml
spring:
  profiles:
    group:
      prod:
        - proddb
        - prodmq
```

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

The `prod` group expands, causing `proddb` and `prodmq` to become active as well.

The difference:

- `spring.profiles.include=metrics`: adds `metrics` whenever the non-profile-specific document containing this property is applied.
- `spring.profiles.group.prod=proddb,prodmq`: defines that **when `prod` is selected**, Spring Boot additionally activates the group's member profiles.

For example, to have `metrics` in every run while enabling specific profiles when using `prod`:

```yaml
spring:
  profiles:
    include: metrics
    group:
      prod:
        - proddb
        - prodmq
```

When running with `--spring.profiles.active=prod`, the relevant profiles include `metrics`, `prod`, `proddb`, and `prodmq`. When running with `--spring.profiles.active=dev`, `metrics` can still be added, while the `prod` group does not activate merely because it is defined.

Like `spring.profiles.include`, `spring.profiles.group` declarations must live in non-profile-specific documents. This configuration defines **an activation relationship**, not an already-selected profile document.

## 8. `spring.profiles.include` is processed per PropertySource

An important detail is that `spring.profiles.include` is processed by Spring Boot **per PropertySource**. Thus multiple sources can contribute profiles to the active set.

For example, a non-profile-specific file contains:

```yaml
spring:
  profiles:
    include: audit
```

While another valid configuration source at startup provides:

```text
spring.profiles.include=metrics
```

Contrast this with `spring.profiles.active`: for `active`, the higher-precedence source normally selects the effective value for that property; for `include`, Spring Boot processes contributions across sources.

However, do not assume that **two declarations of the same key in the same document automatically concatenate into a list**. List syntax inside YAML/Properties must be valid. Across different documents or sources, verify the actual active profile set and applicable Config Data rules.

When using `application.yml` and environment variables, maintain one clear representation and avoid declaring the same key redundantly. The purpose of `include` is to make added profiles obvious, not to create hard-to-trace layers.

## 9. Activating profiles via environment variables and command line

You can set profile properties from familiar early startup sources. For example, setting the primary profile via command line:

```bash
java -jar app.jar --spring.profiles.active=prod
```

While `application.yml` contains:

```yaml
spring:
  profiles:
    include: metrics
```

Another option is supplying the primary profile via an environment variable in Bash:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

In PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

You can supply `spring.profiles.include` from an appropriate startup source, for example:

```bash
java -jar app.jar --spring.profiles.include=metrics,audit
```

This example adds two profiles from an application argument. When applied in environments with multiple configuration sources, inspect the actual active profile set.

**Note on commas and shells:** the `metrics,audit` value in a list property must reach the application intact; deployment tools, shells, and config formats have their own rules for quoting, whitespace, and list representation.

## 10. How does `spring.profiles.include` affect `@Profile`?

Spring Framework supports `@Profile` conditions on beans or configuration classes. Spring Boot activates profiles and then uses that active profile set while building the application.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class AuditConfiguration {

    @Bean
    @Profile("audit")
    public AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }
}

class AuditRecorder {
    public void record(String message) {
        System.out.println("AUDIT: " + message);
    }
}
```

Suppose `application.yml` declares:

```yaml
spring:
  profiles:
    include: audit
```

The `audit` profile is activated, so the `auditRecorder` bean can be registered without the caller needing `--spring.profiles.active=audit`.

If `audit` is not in the active profile set and is not activated by another mechanism, `@Profile("audit")` is not satisfied.

This shows that `include` affects **which beans are created**, not just whether `application-audit.yml` loads.

When using `@Profile` with complex conditions, remember that an expression like `@Profile("prod & audit")` checks both profiles simultaneously. Including a profile can make a previously unmet condition evaluate to true.

## 11. How to verify which profiles were activated

While learning or diagnosing issues, you can print the profile list from `Environment`:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfilesPrinter implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfilesPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("demo.mode = "
                + environment.getProperty("demo.mode", "<none>"));
    }
}
```

When `application.yml` declares `include=metrics,audit` and you run with `--spring.profiles.active=prod`, the printed profiles show the effective profile names, including both added profiles and the profile selected at launch.

This list is far more reliable than guessing from filenames. A profile can exist without its own profile file, or another configuration source can alter the active profile set.

To find why a property received an unexpected value, also use `environment.getProperty("demo.mode")` or appropriate Config Data diagnostics. Never log sensitive values when inspecting real configuration.

## 12. A complete example: environment profiles and feature profiles

Suppose an order-management application has these files:

```text
src/main/resources/
├── application.yml
├── application-logging.yml
├── application-audit.yml
├── application-dev.yml
└── application-prod.yml
```

`application.yml`:

```yaml
spring:
  profiles:
    include:
      - logging
      - audit

orders:
  retries: 1
  storage: local
  logging-enabled: false
  audit-enabled: false
```

`application-logging.yml`:

```yaml
orders:
  logging-enabled: true
```

`application-audit.yml`:

```yaml
orders:
  audit-enabled: true
```

`application-dev.yml`:

```yaml
orders:
  storage: in-memory
  retries: 1
```

`application-prod.yml`:

```yaml
orders:
  storage: postgres
  retries: 5
```

Running the development application:

```bash
java -jar app.jar --spring.profiles.active=dev
```

With these files and no other overriding sources:

```text
orders.storage         = in-memory
orders.retries         = 1
orders.logging-enabled = true
orders.audit-enabled   = true
```

Running the production application:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Result:

```text
orders.storage         = postgres
orders.retries         = 5
orders.logging-enabled = true
orders.audit-enabled   = true
```

Environment settings change according to `dev` or `prod`. Features declared in `include` are still added for both runs.

If later only production needs `audit`, do not rush to move `spring.profiles.include=audit` into `application-prod.yml`. Consider a profile group to activate `audit` only when `prod` is selected, or redesign configuration organization for maintainability.

## 13. Pitfalls to avoid

### 13.1. Confusing `include` with replacing `active`

Wrong: “If I add `spring.profiles.include=metrics`, `prod` will be dropped.”

Right: `include` **adds** `metrics`; the primary environment profile selection still operates simultaneously.

### 13.2. Confusing `include` with file import declarations

`spring.profiles.include=metrics` activates a **profile**, whereas `spring.config.import=classpath:feature.yml` specifies a **configuration resource** to load. The two properties serve different purposes.

Having a file named `application-metrics.yml` makes profile-based configuration intuitive, yet `include` does not ask you for a path to that file.

### 13.3. Placing `include` inside a profile-specific file

Do not put `spring.profiles.include` in `application-prod.yml` or a document activated by `spring.config.activate.on-profile=prod`. Move the declaration to a non-profile-specific document, or use profile groups if conditional activation is needed.

### 13.4. Expecting included profiles to always override active profiles

Included profiles are added before active profiles. In typical Config Data setups, an active profile chosen later can override overlapping keys from an included profile. System-wide precedence is also influenced by file locations, imports, and other configuration sources.

### 13.5. Assuming a profile only works if it has its own config file

Profiles are not just filename suffixes. They also affect `@Profile` conditions and documents activated by profile expressions.

### 13.6. Using `include` for dependencies needed in only one environment

If `proddb` is needed only when running `prod`, declaring `spring.profiles.include=proddb` in `application.yml` adds it even when running `dev`. Profile groups are a better fit when the intent is “selecting `prod` brings along `proddb`.”

### 13.7. Expecting `include` to disable a profile

`spring.profiles.include` is an additive mechanism. It provides no syntax to remove an active profile. Design profile lists and bean conditions cleanly rather than expecting `include` to negate a profile from another source.

## 14. Exercises: predict the outcomes yourself

### Exercise A: calculate the profile set

File `application.yml`:

```yaml
spring:
  profiles:
    include:
      - cache
      - audit
```

Launch:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Questions:

1. Which profiles are activated?
2. Is `application-cache.yml` required for the `cache` profile to exist?
3. Can a bean annotated with `@Profile("audit")` be registered?

Suggested answers:

1. The profile set contains `cache`, `audit`, and `prod` in this example.
2. Not necessarily; a profile is an activation state, whereas a profile-specific file is one way of providing Config Data.
3. Yes, provided no other condition or error prevents bean registration.

### Exercise B: calculate configuration values

Given:

```yaml
# application.yml
spring:
  profiles:
    include: common

demo:
  color: gray
  retries: 2
```

```yaml
# application-common.yml
demo:
  color: blue
  enabled: true
```

```yaml
# application-prod.yml
demo:
  color: red
  retries: 5
```

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Assuming no other files or sources override them, predict:

| Key | Expected value | Reason |
| --- | --- | --- |
| `demo.color` | `red` | Profile `prod` overrides the value from `common` |
| `demo.retries` | `5` | `application-prod.yml` overrides common configuration |
| `demo.enabled` | `true` | `application-common.yml` supplies the value |

Try also:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.color=black
```

`demo.color` becomes `black` because standard command-line arguments have higher precedence than Config Data files.

### Exercise C: identify an invalid declaration

Examine this document:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: audit
```

Question: Why should this configuration not be used?

Answer: this is a document activated only for profile `prod`, whereas `spring.profiles.include` may only be used in **non-profile-specific** documents. For “prod brings along audit,” you can define:

```yaml
spring:
  profiles:
    group:
      prod:
        - audit
```

in a non-profile-specific document, and then activate `prod` at startup.

## 15. Key takeaways

- `spring.profiles.include` **adds profiles** to the Spring Boot application's active profile set.
- Unlike `spring.profiles.active`, which selects primary profiles, `include` lets you configure auxiliary profiles that should be added regardless of whether the environment picks `dev` or `prod`.
- You can use a YAML list or a comma-separated list in Properties files.
- Included profiles are added **before** active profiles; this affects property overrides when profile-specific configuration documents exist.
- **Declare `spring.profiles.include` only in non-profile-specific documents.** Do not put it in `application-prod.yml` or documents using `spring.config.activate.on-profile`.
- If you need “selecting one profile brings along multiple other profiles,” use **profile groups**.
- A profile can activate profile-specific configuration files and `@Profile` conditions; it does not require its own file.
- Verify the profile set with `Environment#getActiveProfiles()` and verify individual values with `Environment#getProperty()`.