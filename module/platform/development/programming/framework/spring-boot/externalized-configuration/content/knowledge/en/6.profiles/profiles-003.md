# The Default Profile and the `spring.profiles.default` Property in Spring Boot 3.3

## 1. Why understand the default profile?

Spring Boot uses **profiles** to select configuration and beans suited for each runtime environment, such as `dev`, `test`, `staging`, or `prod`. When at least one **active profile** is present, Spring Boot considers files like `application-dev.yaml` or `application-prod.properties` and the corresponding `@Profile` conditions.

But what happens when **no active profile is declared**? Spring Framework has a set of **default profiles** used as a fallback. Spring Boot 3.3 defaults this set to `[default]`, meaning a profile named `default` is considered when no active profiles exist.

You can customize that default name with the property:

```properties
spring.profiles.default=local
```

This is the topic of this article: distinguishing **active profiles** from **default profiles**, understanding exactly when `spring.profiles.default` takes effect, when `application-default.*` or `application-local.*` is loaded, valid placement rules, and how to inspect it at runtime.

**Foundational rule:**

> If there is at least one active profile, Spring uses the active profiles. If there are no active profiles, the default profiles set is used to evaluate profile conditions; by default that set contains the name `default`.

**The default profile is not implicitly a “safe,” “development,” or “production” environment by some hidden standard.** `default` is simply a fallback profile name. Its contents are decided entirely by your project.

## 2. Three concepts to keep separate

| Concept | Definition | Example |
| --- | --- | --- |
| **Active profiles** | Profiles explicitly activated via configuration, command line, API, or profile-addition mechanisms | `dev`, `prod`, `test` |
| **Default profiles** | The fallback profile set used when **there are no active profiles** | Defaults to `[default]`; can be changed to `[local]` |
| **Profile-specific configuration** | Files or configuration documents that participate only when the corresponding profile is accepted | `application-default.yaml`, `application-prod.properties`, documents with `spring.config.activate.on-profile` |

Spring's `Environment` provides the relevant methods:

```java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
```

Example when the application has not set `spring.profiles.active`:

```text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["default"]
```

After setting `spring.profiles.default=local` in common configuration:

```text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["local"]
```

When running with `--spring.profiles.active=prod`, even if default is still configured as `local`:

```text
getActiveProfiles()  -> ["prod"]
getDefaultProfiles() -> ["local"]
```

In the last case, `local` still appears in **default profiles** yet **is not used as a fallback**, because `prod` is already active. Therefore, you cannot inspect `getDefaultProfiles()` alone and conclude that profile is currently active for `@Profile` conditions.

## 3. Default behavior when nothing is configured

Suppose an application has three files in `src/main/resources`:

```text
src/main/resources/
├── application.yaml
├── application-default.yaml
└── application-prod.yaml
```

Their contents:

**`application.yaml`**:

```yaml
app:
  greeting: "Hello from common config"
  timeout: 3s
```

**`application-default.yaml`**:

```yaml
app:
  greeting: "Hello from default profile"
```

**`application-prod.yaml`**:

```yaml
app:
  greeting: "Hello from production"
  timeout: 10s
```

Launch **without** supplying an active profile:

```bash
java -jar myapp.jar
```

Under standard Boot 3.3 profile behavior:

- `application.yaml` is always the common configuration document if present in a searched location.
- There is no active profile, so the default profiles set `[default]` is used.
- `application-default.yaml` is considered as the profile-specific file for the `default` profile.
- `application-prod.yaml` is not considered merely because the file exists.

Expected result assuming no higher-precedence source overrides it:

```text
app.greeting = Hello from default profile
app.timeout  = 3s
```

Because `application-default.yaml` does not declare `app.timeout`, the common value `3s` remains in effect. Profile-specific files can override matching keys from common configuration.

**Note:** `application-default.yaml` is not a default file that is always loaded. It participates only when the `default` profile is accepted, primarily when there are no active profiles and the default profile is still named `default`.

## 4. `spring.profiles.default`: changing the fallback profile set

### 4.1. Declaring in `application.properties`

```properties
# application.properties — non-profile-specific document
spring.profiles.default=local
```

When no active profile exists, Spring Boot uses `local` instead of `default`. Therefore, profile-specific configurations such as `application-local.properties` or `application-local.yaml` can be considered.

Example:

```text
src/main/resources/
├── application.properties
├── application-local.properties
├── application-default.properties
└── application-prod.properties
```

```properties
# application.properties
spring.profiles.default=local
app.mode=common
```

```properties
# application-local.properties
app.mode=local-fallback
```

```properties
# application-default.properties
app.mode=old-default
```

When running `java -jar myapp.jar`, the result is `app.mode=local-fallback`, because the default profiles set is `[local]`. The presence of `application-default.properties` does not cause it to load when `default` is no longer an accepted profile.

### 4.2. Equivalent declaration in YAML

```yaml
# application.yaml
spring:
  profiles:
    default: local
```

YAML syntax uses nested mappings, equivalent to the flat property `spring.profiles.default=local`. Use one clear configuration format per location, because when both `application.properties` and YAML exist in the same location, Spring Boot has format precedence rules that can cause surprises.

### 4.3. Multiple default profiles

Default profiles are a **set of profile names**, not necessarily a single name. You can configure a comma-separated list:

```properties
spring.profiles.default=local,metrics
```

Or:

```yaml
spring:
  profiles:
    default: local,metrics
```

If there are no active profiles, both `local` and `metrics` belong to the fallback set, so `application-local.*` and `application-metrics.*` can participate in loading. When both profiles supply the same property, ordering across profile-specific files follows Config Data precedence rules, including the rule that a later profile can override an earlier profile **within the same location group**.

This **does not mean** every source with a default profile appends to the list. `spring.profiles.default` is an ordinary property subject to PropertySource precedence order; if declared differently in multiple places, the higher-precedence value is used.

### 4.4. Sources for supplying the property

You can set `spring.profiles.default` in:

**Common configuration file:**

```properties
spring.profiles.default=local
```

**Command-line option:**

```bash
java -jar myapp.jar --spring.profiles.default=local
```

**JVM system property:**

```bash
java -Dspring.profiles.default=local -jar myapp.jar
```

**Environment variable:**

```bash
SPRING_PROFILES_DEFAULT=local java -jar myapp.jar
```

With Docker Compose or Kubernetes, you can declare `SPRING_PROFILES_DEFAULT` as a container environment variable before the Java process starts. The goal is to define a **fallback** for runs that do not supply `spring.profiles.active`.

Unlike properties that determine file lookup paths such as `spring.config.name` or `spring.config.location`, `spring.profiles.default` **is allowed in common Config Data documents** such as `application.properties`/`application.yaml`; Spring Boot processes profile information during the Config Data phase and has rules for resolving profile-specific files.

## 5. How does `spring.profiles.default` differ from `spring.profiles.active`?

The two properties serve different roles:

- `spring.profiles.active=prod`: **explicitly selects the active profile** as `prod`.
- `spring.profiles.default=local`: **selects only the fallback profile** as `local` when there are no active profiles.

Example common configuration:

```properties
spring.profiles.default=local
app.name=inventory-service
```

**Case A — no active profile passed**

```bash
java -jar myapp.jar
```

Here `local` is the fallback. If `application-local.properties` exists, it can participate in loading; `@Profile("local")` can match.

**Case B — passing `prod` as the active profile**

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

Now `prod` is the active profile. `local` is not added simply because it is the default profile. `application-prod.properties` is considered, while `application-local.properties` is not considered as a fallback.

**Case C — passing an active profile with the same name as default**

```bash
java -jar myapp.jar --spring.profiles.active=local
```

Now `local` is an **actual active profile**, no longer just a fallback. The `local` files and conditions may produce the same outward effect, yet `environment.getActiveProfiles()` will differ from Case A.

Comparison table:

| Launch configuration | `getActiveProfiles()` | `getDefaultProfiles()` | Profiles considered if no other addition mechanism applies |
| --- | --- | --- | --- |
| Nothing set | `[]` | `[default]` | `default` |
| `spring.profiles.default=local` | `[]` | `[local]` | `local` |
| `spring.profiles.default=local,metrics` | `[]` | `[local, metrics]` | `local` and `metrics` |
| `spring.profiles.default=local` and `spring.profiles.active=prod` | `[prod]` | `[local]` | `prod` |
| `spring.profiles.active=default` | `[default]` | `[default]` | `default` as an explicit active profile |
| `spring.profiles.default=none`, no active | `[]` | `[none]` | fallback profile named `none` |

The values in the table illustrate cases without `setAdditionalProfiles`, `spring.profiles.include`, profile groups, or other extensions adding active profiles.

### The default set does not automatically “join” the active set

Suppose `spring.profiles.default=local` and `spring.profiles.active=prod`. Do not infer that the application runs with both `local,prod`. If you truly want both profiles active, specify them in active profiles or use an appropriate profile-addition mechanism:

```bash
java -jar myapp.jar --spring.profiles.active=local,prod
```

Then both `local` and `prod` are **active**, and the fact that `local` is also the default name has no bearing on that decision.

## 6. The `none` value: avoiding implicit use of a profile named `default`

The official Spring Boot 3.3 documentation gives the example:

```properties
spring.profiles.default=none
```

Or:

```yaml
spring:
  profiles:
    default: "none"
```

**Practical meaning:** changes the default profile name from `default` to `none`. If the application has no active profiles, `application-default.*` and beans restricted to `@Profile("default")` are no longer activated solely by fallback.

However, understand this accurately: `none` is **a profile name**, not a universal command to “disable the profile mechanism completely.” With this setting, `getDefaultProfiles()` can return `["none"]`, and if the application contains `application-none.yaml` or `@Profile("none")`, they can still be considered when no active profile is present.

Therefore:

- Use `spring.profiles.default=none` when you want to avoid picking up settings intended for the default profile named `default`.
- Do not mistakenly create `application-none.*` if your goal is to use only common configuration when no active profile is set.
- Do not use `none` as an active profile name just to mean “no profile selected”; `--spring.profiles.active=none` **actually activates** a profile named `none`.

**Intentional example:**

```text
src/main/resources/
├── application.yaml
├── application-default.yaml
└── application-prod.yaml
```

```yaml
# application.yaml
spring:
  profiles:
    default: "none"
app:
  log-format: plain
```

If no active profile is specified, `application-default.yaml` is not picked up via the `default` fallback. The value `app.log-format=plain` from common configuration continues to be used unless another source overrides it.

## 7. Relationship with `application-default.*`, `application-local.*`, and profile-specific files

Spring Boot loads configuration from searched locations via the Config Data mechanism. Alongside `application.properties`/`application.yaml`, Boot considers `application-{profile}.properties`/`application-{profile}.yaml`/`application-{profile}.yml` variants for the applicable profile set.

**Example:**

```text
config/
  application.properties
  application-default.properties
  application-local.properties
  application-prod.properties
```

When `config/` is a searched location:

- No active profile, default still `default` → considers `application-default.properties`.
- No active profile, `spring.profiles.default=local` → considers `application-local.properties`.
- Active profile `prod` → considers `application-prod.properties`, even if the default property is `local`.
- Active profiles `local,prod` → considers both profiles according to Config Data precedence rules.

Common files **are still considered in every case**. Default profiles do not replace `application.properties`; they decide which **profile-specific auxiliary** files are added to Config Data when no profile is explicitly activated.

When the same key appears in both the common document and a profile-specific document in the same location group, the profile-specific file has higher precedence. However, if there are locations outside the JAR, imports, or multiple location groups, evaluate the full Config Data order; you cannot deduce which wins across all sources from filename alone.

**Practical example:**

```properties
# application.properties
spring.profiles.default=local
app.base-url=https://api.example.test
app.read-timeout=3s
```

```properties
# application-local.properties
app.base-url=http://localhost:8080
```

```properties
# application-prod.properties
app.base-url=https://api.prod.example.test
app.read-timeout=10s
```

Result:

| How it is run | `app.base-url` | `app.read-timeout` |
| --- | --- | --- |
| No active profile | `http://localhost:8080` | `3s` |
| `--spring.profiles.active=prod` | `https://api.prod.example.test` | `10s` |

The first row shows that fallback `local` does not erase all common properties: only overridden keys change. The second row shows that default `local` is ignored when `prod` is active.

## 8. Default profiles and multi-document YAML

Beyond `application-{profile}.*` files, Boot allows multiple **Config Data documents** inside a single YAML file, separated by `---`, activating a document based on profiles:

```yaml
# application.yaml — common document
spring:
  profiles:
    default: local
app:
  message: "common"
---
# Document considered only when local applies
spring:
  config:
    activate:
      on-profile: local
app:
  message: "local-fallback"
---
# Document considered only when prod applies
spring:
  config:
    activate:
      on-profile: prod
app:
  message: "production"
```

When **there is no active profile**, the default is `local`, so the document with `spring.config.activate.on-profile=local` is considered. The expected value of `app.message` is `local-fallback`, unless a higher-precedence source overrides it.

When launched with:

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

The document activated by `prod` is considered, and the `local` document is not selected merely because it is the default name. The expected value of `app.message` is `production`.

**Place it correctly:** `spring.profiles.default` belongs in the **common, non-profile-specific document**, such as the first document in the example. Do not move that property into a document with `spring.config.activate.on-profile`.

In multi-document `.properties` files, document boundaries are represented by `#---` (on its own line), not YAML's `---`. Example:

```properties
# application.properties — common document
spring.profiles.default=local
app.message=common
#---
spring.config.activate.on-profile=local
app.message=local-fallback
```

At runtime, `spring.config.activate.on-profile` uses a profile expression to decide whether the document is activated. When the default profile is used, that profile can satisfy the corresponding activation condition.

## 9. Default profiles and `@Profile` on beans

Profiles do not just control which files load. Spring Framework uses `@Profile` conditions to decide bean/configuration registration.

Example:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class StorageConfig {

    @Bean
    @Profile("local")
    StorageClient localStorage() {
        return new InMemoryStorageClient();
    }

    @Bean
    @Profile("prod")
    StorageClient prodStorage() {
        return new CloudStorageClient();
    }
}
```

Assume `StorageClient`, `InMemoryStorageClient`, and `CloudStorageClient` are types defined by the application.

When `spring.profiles.default=local` and there are no active profiles, `@Profile("local")` can match via fallback; when the active profile is `prod`, `@Profile("prod")` matches and the `local` fallback is not used.

An example using the initial default:

```java
@Configuration
@Profile("default")
public class DefaultCacheConfig {

    @Bean
    CacheAdapter defaultCacheAdapter() {
        return new LocalCacheAdapter();
    }
}
```

With `spring.profiles.default` left uncustomized and no active profiles, this class can be registered. However, if the application sets `spring.profiles.default=none` or `local`, `@Profile("default")` is no longer satisfied by fallback.

### `@Profile("default")` does not mean “unconditional bean”

This is a common reasoning error. `@Profile("default")` is still a profile condition:

- Matches when there are no active profiles and default profiles contain `default`.
- Does not match when the active profile is `prod`, unless `default` itself is also activated.
- Does not match via fallback if default profiles have been changed to a set that does not contain `default`.

A bean **without** `@Profile` is generally not filtered by this profile condition. If a feature must always be present regardless of runtime environment, do not annotate it with `@Profile("default")` thinking `default` means common configuration.

### Negated profile expressions

`@Profile("!prod")` can match whenever `prod` is not active, including when using the default profile `default` or `local`. That differs from `@Profile("default")`: the negated expression checks **absence of prod**, whereas `default` checks that the accepted profile names include `default`.

## 10. Mandatory restriction: do not place `spring.profiles.default` in profile-specific documents

Spring Boot 3.3 documentation explicitly states that both of these properties **may only be used in non-profile-specific documents**:

- `spring.profiles.active`
- `spring.profiles.default`

This means **do not** declare them inside:

1. `application-dev.properties`, `application-prod.yaml`, or any file belonging to a specific profile.
2. A YAML or `.properties` document activated by `spring.config.activate.on-profile`.

**Valid example:**

```yaml
# application.yaml — non-profile-specific document
spring:
  profiles:
    default: local
app:
  name: shared
```

**Invalid example — placing default inside a profile-specific file:**

```properties
# application-local.properties
spring.profiles.default=prod
```

**Invalid example — placing default inside a conditional document:**

```yaml
# application.yaml
app:
  name: common
---
spring:
  config:
    activate:
      on-profile: local
  profiles:
    default: prod
```

The reason is that properties determining the profile set must be resolved under Config Data processing rules. Allowing a conditionally profile-activated document to alter the profile set right inside that same document risks circular dependencies in configuration.

When you need a common fallback, place `spring.profiles.default` in a **common document** or an external source such as OS environment/CLI/JVM system property. If you want a group of settings to apply only to `local`, use `spring.config.activate.on-profile=local` or `application-local.*` to declare the corresponding **application properties**.

## 11. PropertySource precedence: multiple places setting `spring.profiles.default`

`spring.profiles.default` follows configuration source precedence order. Example:

```properties
# application.properties
spring.profiles.default=local
```

But running with:

```bash
java -jar myapp.jar --spring.profiles.default=staging
```

If there are no other active profiles, the command-line value outranks the configuration file value, so the fallback is `staging`. `application-staging.*` can be considered instead of `application-local.*`.

Similarly, you might have:

```bash
SPRING_PROFILES_DEFAULT=local \
java -Dspring.profiles.default=staging -jar myapp.jar
```

Under Boot 3.3's default PropertySource order, JVM system property `-D...` takes higher precedence than an OS environment variable for the same key, so `staging` wins. This is the rule for **picking the property value**, while the fallback decision itself applies **only if no active profile exists**.

If you simultaneously pass:

```bash
java -jar myapp.jar \
  --spring.profiles.default=staging \
  --spring.profiles.active=prod
```

then default profiles can be `[staging]`, yet the application uses `prod` because it is the active profile. The command line does not automatically turn a default profile into an active profile.

## 12. Other mechanisms that can prevent the fallback from being used

Do not look solely for `spring.profiles.active` and conclude there are definitely no active profiles. Spring Boot and Spring Framework have additional mechanisms that add profiles to the active set, such as:

- `spring.profiles.include`: adds requested profiles to the active set, subject to Boot's document restrictions and processing rules.
- `spring.profiles.group.<group-name>`: expands a logical profile into a group of profiles when that group is activated.
- `SpringApplication.setAdditionalProfiles(...)` or `SpringApplicationBuilder.profiles(...)`: activates extra profiles from startup code.
- `ConfigurableEnvironment.setActiveProfiles(...)`/`addActiveProfile(...)` if invoked at an appropriate stage.
- In tests, Spring Test's `@ActiveProfiles` can activate one or more profiles for the test context.

Example:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("metrics");
app.run(args);
```

When `metrics` is actually added to active profiles, the default profile may no longer be used as a fallback.

**Checkpoint:** inspect `environment.getActiveProfiles()` **after the Environment preparation phase**. This list reflects active profiles, including those added through mechanisms the application uses. If it is non-empty, do not expect `spring.profiles.default` to activate an extra profile.

### Tests with `@ActiveProfiles`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {

    @Test
    void loadsApplicationContext() {
    }
}
```

In this test, `test` is the active profile supplied by the test framework. If `application.properties` contains `spring.profiles.default=local`, that does not automatically cause `application-local.*` to load via fallback in the test. Typically, `application-test.*` files are considered when `test` is active.

Do not assume that **every** `@SpringBootTest` automatically activates `test`; if no profile is specified and no other mechanism activates one, the test can still use the application's default profile.

## 13. Relationship with early configuration and Config Data

Spring Boot resolves the profile set and profile-specific files during `Environment` preparation, before `ApplicationContext` finishes refreshing. Therefore, distinguish these property groups:

| Group | Example | When / how supplied |
| --- | --- | --- |
| Determine names and locations to **start searching files** | `spring.config.name`, `spring.config.location`, `spring.config.additional-location` | Must be available very early from OS environment, JVM `-D`, command line, or launcher before `run`. |
| Select active/default profiles during Config Data | `spring.profiles.active`, `spring.profiles.default` | Can be declared in **non-profile-specific Config Data documents**, or an early enough external source. |
| Activate a Config Data document | `spring.config.activate.on-profile` | Declared inside the document to be controlled. |
| Profile-specific business values | `app.*`, `server.*`, `spring.datasource.*` | Placed in profile-specific files or appropriately activated documents. |

A subtle case to avoid confusing:

```properties
# application.properties, in default location
spring.profiles.default=local
spring.config.location=file:./custom/
```

`spring.profiles.default=local` is valid configuration in a **common document** for choosing the fallback profile; however, `spring.config.location` inside the file already being loaded is not a reliable way to reroute the search location list already chosen at an earlier stage. To change initial locations, pass `spring.config.location` from an early source, then let the discovered files determine profiles via Config Data.

If `spring.config.location` or `spring.config.name` was changed early on, the application might no longer read the `application.properties` file you are editing. When encountering “I set `spring.profiles.default` but it had no effect,” verify **whether the file containing the property is actually among the loaded Config Data sources**.

## 14. Runtime observation: active or default?

A safe diagnostic technique is printing profile **names** and a few non-sensitive configuration values after the Environment is prepared. Example using `ApplicationRunner`:

```java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ProfileDiagnostics {

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return args -> {
            System.out.println("Active profiles:  "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("Default profiles: "
                    + Arrays.toString(environment.getDefaultProfiles()));
            System.out.println("Configured spring.profiles.default: "
                    + environment.getProperty("spring.profiles.default"));
        };
    }
}
```

Assuming `spring.profiles.default=local` and no active profile, the output can be:

```text
Active profiles:  []
Default profiles: [local]
Configured spring.profiles.default: local
```

Running with `--spring.profiles.active=prod`:

```text
Active profiles:  [prod]
Default profiles: [local]
Configured spring.profiles.default: local
```

Key point: the `spring.profiles.default` value **still exists** even when it **is not the profile set currently being used**.

### Checking which profile is accepted

Spring Framework provides an API to evaluate profile conditions:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean localApplies = environment.acceptsProfiles(Profiles.of("local"));
boolean prodApplies = environment.acceptsProfiles(Profiles.of("prod"));
```

If active profiles are empty and default profiles are `[local]`, `localApplies` can be `true`. If the active profile is `prod`, `prodApplies` is `true`, while `localApplies` is usually `false` when only those profiles exist.

This is useful when diagnosing `@Profile` conditions and profile-activated Config Data documents. Check results under the exact same startup conditions, because passing additional profiles via CLI, test framework, or API can change the answer.

### Signs in startup logs

Spring Boot typically logs a message indicating which active profiles are in use, or noting that no active profile was set and it is falling back to the default profile. For example, you might see a message like:

```text
No active profile set, falling back to 1 default profile: "default"
```

Exact text depends on version and logging configuration. If `spring.profiles.default=local` is configured properly, the fallback message will show `local` instead of `default`.

Do not treat the fallback log message as an error. It simply indicates no profile was explicitly activated and the default profiles mechanism was used.

## 15. Common misleading scenarios

### Scenario A: `application-default.yaml` exists but is not read

**Possible cause:** an active profile such as `prod` was supplied via command line, environment variable, test, or API; or `spring.profiles.default` was changed to `local`/`none`. In that case, `default` is no longer in the accepted fallback profile set.

**How to handle:** check `getActiveProfiles()`, `getDefaultProfiles()`, and the sources declaring `spring.profiles.active` and `spring.profiles.default`.

### Scenario B: Setting `spring.profiles.default=dev` and seeing the app “run in dev” everywhere

Default `dev` takes effect **whenever there is no active profile**, including in staging or production if the launcher forgets `spring.profiles.active`. Choosing fallback `dev` is therefore a configuration decision with operational impact. For applications requiring strict environment separation, set active profiles explicitly in production and choose a fallback aligned with safety requirements.

### Scenario C: Setting `spring.profiles.default=none` yet `@Profile("none")` still matches

This can happen because `none` is still a **default profile name**. Do not use the name `none` for special beans/files if the team's intent is “no custom fallback.”

### Scenario D: Putting default in `application-prod.yaml`

`spring.profiles.default` in a profile-specific file is invalid configuration under Boot 3.3 rules. Move the property to a common document or an external source.

### Scenario E: Setting active profile `default` and thinking it is a fallback

`--spring.profiles.active=default` **explicitly activates** the profile named `default`. This puts `default` into `getActiveProfiles()`, which differs from having no active profile and `getDefaultProfiles()` containing `default`.

### Scenario F: Using `@Profile("default")` for a bean needed in every environment

This bean disappears when the active profile switches to `prod` or when the default profile is renamed. Shared beans should not have profile conditions attached unnecessarily.

### Scenario G: Configuration scattered across multiple sources

One file declares `spring.profiles.default=local`, while an environment variable sets `SPRING_PROFILES_DEFAULT=none`. The higher-precedence value wins, so the application does not use `local` as fallback as expected. Check precedence instead of checking only the file you just edited.

### Scenario H: `application-default.properties` in a location that is not searched

Even when the default profile is `default`, the file loads only if it resides in a location/basename that Config Data searches. If `spring.config.location` or `spring.config.name` was changed early, verify the profile-specific file is in the location/name actually being used.

### Scenario I: Tests unexpectedly using local configuration

A `@SpringBootTest` without `@ActiveProfiles` can pick up the `local` fallback from `spring.profiles.default=local`. If the test needs isolated configuration, declare `@ActiveProfiles("test")` or an appropriate active profile source.

## 16. Quick-reference recipes

### Recipe 1 — Rely solely on Spring Boot defaults

```text
No spring.profiles.active declared
No spring.profiles.default declared
→ activeProfiles = []
→ defaultProfiles = [default]
→ application-default.* considered if present in a searched location
```

### Recipe 2 — Choose `local` as fallback

```properties
# application.properties
spring.profiles.default=local
```

```text
No active profiles
→ falls back to local
→ application-local.* / @Profile("local") can take effect
```

### Recipe 3 — Explicitly choose production

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

```text
activeProfiles = [prod]
→ default profiles remain only a fallback set
→ application-prod.* / @Profile("prod") can take effect
```

### Recipe 4 — Prevent the `default` profile from applying implicitly

```properties
# application.properties — common document
spring.profiles.default=none
```

```text
No active profiles
→ fallback named none
→ does not implicitly apply application-default.* or @Profile("default")
→ avoid creating application-none.* / @Profile("none") if you want only common configuration
```

### Recipe 5 — Using default profile with multi-document YAML

```yaml
# application.yaml — common
spring:
  profiles:
    default: local
app:
  feature-enabled: false
---
spring:
  config:
    activate:
      on-profile: local
app:
  feature-enabled: true
```

When there is no active profile, the `local` document matches and `app.feature-enabled` resolves to `true`, unless overridden by a higher-precedence source.

## 17. Key facts to remember

1. Spring Boot 3.3 defaults to **a profile named `default`** when **there are no active profiles**.
2. `spring.profiles.default` changes the **fallback profile set**; it does not activate a profile when `spring.profiles.active` is already present.
3. `application-default.*` is a **profile-specific** file; it is not guaranteed to always load. When default is changed to `local`, Boot can load `application-local.*` when there are no active profiles.
4. `spring.profiles.default=none` is the standard way to **avoid falling back to the `default` profile**; `none` is still a default profile name, so avoid creating configuration named `none` unless intended.
5. `spring.profiles.default` and `spring.profiles.active` may only be placed in **non-profile-specific documents** or appropriate external sources.
6. `@Profile("default")` is subject to profile condition evaluation, unlike a bean with no `@Profile`.
7. When troubleshooting, inspect both `getActiveProfiles()` and `getDefaultProfiles()`; check Config Data locations, property sources, and additional profiles.

## 18. References

- Spring Boot **3.3** Reference Guide – **Profiles**, *Adding Active Profiles*, *Profile Groups*, and default profile explanation: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot **3.3** Reference Guide – **Externalized Configuration**, *Profile Specific Files*, *PropertySource Order*, *Working With Multi-Document Files*, and *Activation Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3** Reference Guide – **Properties and Configuration**, *Set the Default Profile Name*: https://docs.spring.io/spring-boot/3.3/how-to/properties-and-configuration.html
- Spring Framework – `Environment`, `ConfigurableEnvironment`, `Profiles`, and `@Profile`: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Key message:** `spring.profiles.default` answers the question “**if there is no active profile, which profile should be used?**” It does not replace `spring.profiles.active` and does not add a fallback to an application that already has active profiles.