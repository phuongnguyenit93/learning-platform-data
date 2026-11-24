# Splitting Shared Files with Import and Proving Override Order in Spring Boot 3.3

## 1. Objectives of the Integrated Practice

A Spring Boot application often shares common configuration across services: HTTP timeouts, retry counts, feature flags, system domains, and observability options. If you duplicate every value across multiple `application.properties` files, any change must be edited in many places, becomes hard to audit, and invites drift.

Spring Boot supports **Config Data import** through the key:

```properties
spring.config.import=...
```

This mechanism lets one configuration document declare additional documents to load. However, developers must understand **override ordering**: a value sitting in `application.properties` does not automatically beat an imported file. Nor does putting a line at the bottom of a file guarantee it wins over other files.

This lab belongs to the **Integrated Practice** group of **Spring Boot Externalized Configuration**, using **Spring Boot 3.3.x**, **Java 17+**, JUnit 5, and a Maven or Gradle project.

We will structure configuration into three layers:

```text
application.properties
  └── spring.config.import
       ├── config/shared.properties       (shared defaults)
       └── config/service.properties      (service-specific settings)
```

Then we will prove:

1. Imported files are actually loaded by Spring Boot.
2. An imported file can **override** the file that declared `spring.config.import`.
3. Within an import list defining the same key, **later imports take higher precedence than earlier ones**.
4. Reversing the import order flips which value wins for duplicate keys.
5. The line position of `spring.config.import` within the same document does not affect precedence.
6. Application `--key=value` arguments can override values coming from Config Data.
7. Profile-specific variants of imported files can be discovered and participate in precedence.
8. Relative imports and fixed imports resolve paths differently.
9. Missing optional imports allow startup, whereas missing required imports typically fail startup.
10. Importing the same resource multiple times does not necessarily reload it multiple times.
11. Using `SpringApplication.run(...)` and `@TempDir` verifies real behavior instead of guessing from filenames.
12. Separating proof that "the file was loaded" from proof of "which value won".
13. Checking typed binding with `@ConfigurationProperties` and avoiding secret leaks while debugging.

## 2. What Is `spring.config.import`?

Declared in a `.properties` file:

```properties
spring.config.import=classpath:/config/shared.properties
```

Or in YAML:

```yaml
spring:
  config:
    import: classpath:/config/shared.yaml
```

Spring Boot processes imports during the **Config Data** phase while preparing `Environment`, before most application beans are created.

Visual flow:

```text
SpringApplication.run(...)
         |
         v
Config Data processes application.properties
         |
         +-- Discovers spring.config.import
         |
         v
Loads imported files
         |
         v
Adds PropertySources in precedence order
         |
         v
Environment#getProperty(...)
         |
         v
Binder binds into @ConfigurationProperties
```

Imports can point to:

- Classpath resources via `classpath:`.
- Filesystem files via `file:`.
- Paths relative to the file declaring the import.
- Config trees in supported scenarios.
- Additional location types provided by Config Data API extension libraries.

**This import is not `@Import` from Spring Java Configuration.** `@Import` registers bean configurations; `spring.config.import` loads **configuration data**.

## 3. Most Important Precedence Rules

Spring Boot 3.3 documentation states:

- Imported documents are treated as additional Config Data placed immediately after/above the declaring document per Boot's ordering.
- Values from an imported document **can override** keys of the same name in the document that declared the import.
- Multiple imports declared in **one** `spring.config.import` are processed in listed order; **later imports have higher precedence**.
- The line position of `spring.config.import` **within the same document** does not alter this rule.
- Relative imports resolve relative to the location of the document declaring the import.
- An import pointing to the same resource is loaded **once**, even if declared repeatedly.

Example:

```properties
# application.properties
spring.config.import=shared.properties
lab.import.mode=from-application
```

And:

```properties
# shared.properties
lab.import.mode=from-shared
```

Without a higher-precedence source, the effective value will be:

```text
lab.import.mode=from-shared
```

This can surprise developers used to thinking "the parent file always beats child files." With Spring Boot Config Data, look at **document placement in the source hierarchy**, not folder parent/child intuition.

### Multiple Imports

```properties
spring.config.import=shared.properties,service.properties
```

If both files declare:

```properties
lab.import.mode=...
```

then `service.properties` typically beats `shared.properties` within the same document when no higher-precedence source exists.

The purpose of this practice is to **prove** these rules with a real startup, not merely copy rules from memory.

## 4. "Shared First, Service Second" Architecture

Suppose an engineering team maintains:

- A shared set of defaults reused across many applications.
- A service-specific set of values for the `orders` service.
- Deployment values by profile or environment variables.
- Temporary overrides passed via CLI.

Architecture:

```text
                  +------------------------------+
                  | application.properties       |
                  | app name, import declarations|
                  +---------------+--------------+
                                  |
                                  v
                      Config Data import list
                                  |
                    +-------------+--------------+
                    |                            |
                    v                            v
           shared.properties             service.properties
           default timeout               service timeout
           default retry                 service mode
           shared flags                  service owner
                    |                            |
                    +-------------+--------------+
                                  |
                                  v
                           Spring Environment
                                  |
                                  v
                   @ConfigurationProperties / @Value
```

To ensure service-specific values override shared defaults, write:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Never write them in reverse order and expect `service.properties` to win just because its name sounds more specific.

### A Principle of Configuration Ownership

`shared.properties` should contain **broad, non-sensitive** values such as default retries, default timeouts, and shared flags.

`service.properties` holds service-specific differences.

Values belonging to **real deployment environments**—tokens, passwords, production endpoints, cloud region names—should be managed through deployment policies, environment variables, config trees, or secret managers, not baked into `shared.properties`.

## 5. Creating the Spring Boot 3.3 Project

Requirements:

- JDK 17 or newer compatible with Spring Boot 3.3.
- Maven Wrapper or Gradle Wrapper.
- Dependency `spring-boot-starter`.
- Test dependency `spring-boot-starter-test`.

Maven dependencies example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The real project needs a Spring Boot parent or dependency management aligned with **3.3.x**.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

This lab only needs a console app; there is no need to add a web starter or database.

## 6. Suggested Directory Structure

```text
config-import-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/
    │   │       └── importlab/
    │   │           ├── ImportLabApplication.java
    │   │           └── ImportSettings.java
    │   └── resources/
    │       ├── application.properties
    │       └── config/
    │           ├── shared.properties
    │           ├── service.properties
    │           └── service-prod.properties
    └── test/
        └── java/
            └── example/
                └── importlab/
                    └── ImportPrecedenceTest.java
```

Here:

```text
classpath:/config/shared.properties
```

resolves to:

```text
src/main/resources/config/shared.properties
```

once copied into the classpath/build output.

Distinguish the **repository source path** from the location URI Spring Boot uses. The `classpath:` prefix does not read `src/main/resources` directly at runtime; once packaged into a JAR, resources reside inside the artifact.

## 7. Root File: `application.properties`

Create:

`src/main/resources/application.properties`

```properties
spring.application.name=config-import-lab

# Config Data: shared first, service second.
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties

# Intentionally declare the same key to prove imports beat the root file.
lab.import.mode=from-application

# Marker present only in the file declaring the imports.
lab.import.application-marker=loaded
```

There are two kinds of keys:

- `lab.import.mode` is the **conflicting key** used to observe precedence.
- `lab.import.application-marker` is a **marker** confirming the root file was actually loaded.

If you test only the conflicting key without markers, an assertion on the final value alone does not prove every file participated.

### Why Use Prefix `lab.import`?

A dedicated prefix prevents accidental overrides by unrelated properties present in the OS environment.

Avoid overly generic keys such as:

```properties
mode=local
timeout=5s
```

in large labs, since generic names easily collide with library or framework properties.

## 8. Shared File: `shared.properties`

Create:

`src/main/resources/config/shared.properties`

```properties
# Shared default values.
lab.import.mode=from-shared
lab.import.timeout=10s
lab.import.retry-count=2
lab.import.enabled=true

# Marker present only in shared.
lab.import.shared-marker=loaded

# Default base URL that a service may override.
lab.import.base-url=https://shared.example.test/api
```

Purpose of each key:

| Key | Purpose |
| --- | --- |
| `lab.import.mode` | Key duplicated across all three files to demonstrate overrides |
| `lab.import.timeout` | Default wait time, overridden by service |
| `lab.import.retry-count` | Shared default that service keeps unchanged |
| `lab.import.enabled` | Shared flag |
| `lab.import.shared-marker` | Proof that the shared file was loaded |
| `lab.import.base-url` | Value that can vary by environment |

The `.example.test` domain in the example is an illustrative placeholder, not a real API.

## 9. Service-Specific File: `service.properties`

Create:

`src/main/resources/config/service.properties`

```properties
# This value beats both shared and application.
lab.import.mode=from-service

# Service requires a shorter timeout than the shared default.
lab.import.timeout=3s

# Keeps retry-count=2 from shared since it is not redeclared here.
lab.import.owner=orders-service
lab.import.service-marker=loaded
```

Across all three files, expected values are:

| Key | `application.properties` | `shared.properties` | `service.properties` | Expected final value |
| --- | --- | --- | --- | --- |
| `lab.import.mode` | `from-application` | `from-shared` | `from-service` | `from-service` |
| `lab.import.timeout` | — | `10s` | `3s` | `3s` |
| `lab.import.retry-count` | — | `2` | — | `2` |
| `lab.import.enabled` | — | `true` | — | `true` |
| `lab.import.owner` | — | — | `orders-service` | `orders-service` |
| `lab.import.application-marker` | `loaded` | — | — | `loaded` |
| `lab.import.shared-marker` | — | `loaded` | — | `loaded` |
| `lab.import.service-marker` | — | — | `loaded` | `loaded` |

**This table shows expected Boot 3.3 behavior** when no CLI arg, environment variable, system property, profile, or higher-priority source affects these keys. In the steps below, we verify it using `SpringApplication`.

## 10. Profile-Specific File: `service-prod.properties`

Create:

`src/main/resources/config/service-prod.properties`

```properties
# Config Data can consider profile-specific variants of imported files.
lab.import.mode=from-service-prod
lab.import.timeout=2s
lab.import.owner=orders-service-prod
```

Because `application.properties` imports:

```text
classpath:/config/service.properties
```

Spring Boot can consider its variant:

```text
classpath:/config/service-prod.properties
```

when the `prod` profile is active.

When `prod` is not active, `mode` from `service.properties` is:

```text
from-service
```

When `prod` is active with no higher-priority source:

```text
from-service-prod
```

**Avoid adding `application-prod.properties` declaring the same keys in the first test**, because that introduces an extra precedence axis that obscures the result. Isolate one rule per experiment.

## 11. Typed Java Model via `@ConfigurationProperties`

Create:

`src/main/java/example/importlab/ImportSettings.java`

```java
package example.importlab;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab.import")
public record ImportSettings(
        String mode,
        Duration timeout,
        int retryCount,
        boolean enabled,
        String owner
) {
}
```

Spring Boot binds:

```text
lab.import.retry-count -> retryCount
lab.import.timeout     -> Duration
```

With the files above, the record receives:

```text
mode       = from-service
timeout    = PT3S
retryCount = 2
enabled    = true
owner      = orders-service
```

`ImportSettings` must be registered so the runtime creates the configuration bean. This lab uses `@EnableConfigurationProperties` for explicitness.

### Do Not Infer Precedence Solely from the Typed Bean

If the bean has `mode=from-service`, we know the **binding outcome**, yet we do not know whether the other sources were loaded and overridden. Therefore combine:

1. A marker in each file.
2. Values from `Environment#getProperty`.
3. Typed values in `ImportSettings`.

Those three observations answer three slightly different questions.

## 12. Application Class Reading the Results

Create:

`src/main/java/example/importlab/ImportLabApplication.java`

```java
package example.importlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(ImportSettings.class)
public class ImportLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportLabApplication.class, args);
    }

    @Bean
    ApplicationRunner displayResults(
            Environment environment,
            ImportSettings settings
    ) {
        return args -> {
            System.out.println("mode="
                    + environment.getProperty("lab.import.mode"));

            System.out.println("timeout="
                    + settings.timeout());

            System.out.println("retryCount="
                    + settings.retryCount());

            System.out.println("enabled="
                    + settings.enabled());

            System.out.println("owner="
                    + settings.owner());

            System.out.println("application-marker="
                    + environment.getProperty(
                            "lab.import.application-marker"));

            System.out.println("shared-marker="
                    + environment.getProperty(
                            "lab.import.shared-marker"));

            System.out.println("service-marker="
                    + environment.getProperty(
                            "lab.import.service-marker"));
        };
    }
}
```

`ApplicationRunner` executes after the context has started. It is a convenient place to **observe** values; imports were already processed earlier during Config Data loading.

Never print passwords, API keys, or the entire `Environment` in real logs. This lab prints only non-sensitive sample values.

## 13. Running on a Development Machine

With Maven Wrapper:

```bash
./mvnw spring-boot:run
```

With Gradle Wrapper:

```bash
./gradlew bootRun
```

Expected output from `ApplicationRunner`:

```text
mode=from-service
timeout=PT3S
retryCount=2
enabled=true
owner=orders-service
application-marker=loaded
shared-marker=loaded
service-marker=loaded
```

Key observations:

- All three markers exist ⇒ all three files participated.
- `mode=from-service` ⇒ the second import wins for shared keys.
- `retryCount=2` ⇒ keys not overridden remain from shared.
- `timeout=PT3S` ⇒ the Binder converted `"3s"` into `Duration.ofSeconds(3)`.

If output differs, check active profiles, CLI arguments, system properties, env variables, or other configuration. Do not jump to blaming Spring Boot documentation.

## 14. Reversing the Order of the Two Imports

Keep all three files identical, changing only `application.properties`:

Original:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Reversed:

```properties
spring.config.import=classpath:/config/service.properties,classpath:/config/shared.properties
```

For duplicate keys, **shared is now listed second**, so it beats service:

```text
lab.import.mode=from-shared
lab.import.timeout=10s
```

Meanwhile:

```text
lab.import.owner=orders-service
```

remains present because shared does not declare that key.

This is a minimal experiment showing precedence flip **without changing values** inside any child file.

### Lesson Learned

The filename `shared` does not automatically give it lower priority than `service`. The order in the import list controls precedence in this scenario.

In larger projects with additional Config Data sources, final values may also depend on profiles and location groups. This lab isolates one rule at a time with controlled data.

## 15. Moving the Import Line in `application.properties` Does Not Change Precedence

Compare Approach A:

```properties
spring.config.import=classpath:/config/shared.properties
lab.import.mode=from-application
```

and Approach B:

```properties
lab.import.mode=from-application
spring.config.import=classpath:/config/shared.properties
```

Within the same **document**, both let the imported file override `lab.import.mode`.

Do not confuse two concepts:

- **Line position within a single document:** does not decide whether imports win or lose.
- **Location order within the import list:** determines which import wins when imports define the same key.

For multi-document YAML or multi-document `.properties`, ordering **between documents** follows separate rules; never generalize single-document behavior to multi-document files.

## 16. Why Should the Shared File Not Be Imported Last?

An unsuitable ordering when you want service overrides:

```properties
spring.config.import=classpath:/config/service.properties,classpath:/config/shared.properties
```

Here, `shared` overrides `service` keys whenever both declare the same name.

If the business requirement is:

```text
Service-specific values > Shared values
```

then choose:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

and document the convention clearly in the repository README:

> Imports on the right act as higher-priority overrides when property keys overlap.

If there are multiple layers:

```text
defaults → organization → service → environment
```

you can order the import list accordingly, provided you account for external sources outside this chain and verify with tests.

Avoid creating long import chains with unclear ownership. Every file should have a defined purpose and an override policy accepted by the team.

## 17. Fixed Imports: `classpath:` and `file:`

A location like:

```properties
spring.config.import=classpath:/config/shared.properties
```

is a **fixed location**. It resolves on the classpath rather than relative to the location of `application.properties`.

Another location:

```properties
spring.config.import=file:/opt/app/config/shared.properties
```

points to a file on the filesystem at a specific path.

On Windows, avoid manually concatenating `\` characters in ways that break URI syntax. In Java tests, use:

```java
path.toUri().toString()
```

to construct valid URIs from `Path`.

An external file outside the JAR fits well when:

- The same artifact runs across multiple environments.
- Operators supply configuration via mounted volumes.
- Configuration must change without rebuilding the JAR.
- Environment-specific values must not be hard-coded.

Note: updating a file on disk **does not mean** Spring Boot core automatically reloads all config data after startup. A restart or a dedicated refresh mechanism is normally required.

## 18. Relative Imports: `shared.properties`

If the file declaring the import resides at:

```text
/opt/app/config/application.properties
```

and contains:

```properties
spring.config.import=shared.properties
```

then this is an **import-relative location**: it resolves relative to the declaring file.

If that file resides at:

```text
/opt/app/config/shared.properties
```

it will be found without writing an absolute path.

With nested imports:

```text
/opt/app/config/
  application.properties
  common/shared.properties
  common/extra/labels.properties
```

`application.properties`:

```properties
spring.config.import=common/shared.properties
```

`common/shared.properties`:

```properties
spring.config.import=extra/labels.properties
```

The second import resolves relative to:

```text
/opt/app/config/common/shared.properties
```

not necessarily relative to the terminal's working directory.

### `optional:` Does Not Change the Location Kind

For example:

```properties
spring.config.import=optional:shared.properties
```

is still an **import-relative** location; it only changes what happens when the resource is absent.

Meanwhile:

```properties
spring.config.import=optional:file:./shared.properties
```

is a **fixed** location prefixed with `file:`, whose relative filesystem path depends on the process working directory at resolution time.

Adding `optional:` does not turn an import-relative path into a fixed location.

## 19. Sharing Files Across Multiple Services

Suppose two applications, `orders` and `billing`, share a common baseline.

One monorepo layout:

```text
configuration-bundle/
  shared.properties

orders-service/
  src/main/resources/
    application.properties
    config/orders.properties

billing-service/
  src/main/resources/
    application.properties
    config/billing.properties
```

This is source layout. For `classpath:/config/shared.properties` to work, the build must **package or expose the shared resource on each application's classpath**, for example via a shared resources library.

**Just sitting in the same monorepo does not mean** `orders` JAR's `classpath:` will automatically find files outside its classpath.

Another approach is deploying a shared mounted volume:

```text
/etc/company/config/shared.properties
```

Then each application imports:

```properties
spring.config.import=optional:file:/etc/company/config/shared.properties,classpath:/config/orders.properties
```

In this model, which values may be overridden should follow an explicit contract; never turn a shared path into a company-wide secret dump exposed broadly.

### Layered Precedence

A possible convention is:

```text
shared defaults
    ↓
service defaults
    ↓
environment-specific runtime config
    ↓
operator's CLI override
```

However, actual ordering must be implemented with valid Spring Boot mechanisms and verified by tests; never assume arrows in documentation enforce themselves without proper locations, profiles, and precedence.

## 20. `optional:` for Shared Imports When a Deployment Lacks the File

A packaged application might run locally without mounting the shared file:

```properties
spring.config.import=optional:file:./config/company.properties
```

If the file is missing, Spring Boot skips the import and continues startup.

If you omit `optional:`:

```properties
spring.config.import=file:./config/company.properties
```

and the file is missing, startup fails because the resource/location cannot be found.

Choose according to business semantics:

- **Required file:** missing must fail fast.
- **Optional file:** missing is acceptable because safe fallbacks exist.
- **Required secret:** missing must never be silenced so the app runs with unsafe default credentials.

`optional:` **does not mean** "ignore all errors". An existing file with broken YAML syntax, bad types, or Bean Validation failures will still fail startup.

### Never Use `optional:` to Mask Missing Required Production Config

If the application cannot operate safely without `company.properties`, keep the import required or enforce proper validation. Booting successfully with wrong values is far riskier than an explicit startup failure.

## 21. `spring.config.import` in YAML

If an application uses YAML consistently, you can write:

`application.yaml`:

```yaml
spring:
  application:
    name: config-import-lab
  config:
    import:
      - classpath:/config/shared.yaml
      - classpath:/config/service.yaml

lab:
  import:
    mode: from-application
```

`config/shared.yaml`:

```yaml
lab:
  import:
    mode: from-shared
    timeout: 10s
    retry-count: 2
```

`config/service.yaml`:

```yaml
lab:
  import:
    mode: from-service
    timeout: 3s
```

The list form clearly expresses import ordering.

A `.properties` file can import YAML and vice versa, as long as Spring Boot supports the resource and location. Still, teams should favor one consistent format to reduce confusion.

When both `.properties` and YAML share the same basename in the same location, Spring Boot 3.3 applies its own format precedence; avoid mixing same-named formats without testing.

## 22. Profile-Specific Imports

`service.properties` can have variants:

```text
service-dev.properties
service-prod.properties
```

When importing:

```properties
spring.config.import=classpath:/config/service.properties
```

with the `prod` profile active, Spring Boot can consider:

```text
classpath:/config/service-prod.properties
```

Example:

`service.properties`:

```properties
lab.import.mode=from-service
lab.import.timeout=3s
```

`service-prod.properties`:

```properties
lab.import.mode=from-service-prod
lab.import.timeout=2s
```

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected output in the isolated example:

```text
mode=from-service-prod
timeout=PT2S
```

If CLI also sets:

```text
--lab.import.timeout=750ms
```

CLI beats `2s`, because it is a higher-precedence source than Config Data under default Boot settings.

### Distinguishing Two Kinds of Profile Documents

- `application-prod.properties` is an **application-level profile-specific file** discovered during Config Data search.
- `service-prod.properties` is a **profile-specific variant of an imported file**.

Both relate to profiles, yet you should not assume all of their documents share identical precedence positions across every import/location combination. For complex layouts, write dedicated tests matching your exact file structure.

## 23. Duplicate Imports Do Not Reload the Same Resource Repeatedly

A config might accidentally list an import twice:

```properties
spring.config.import=shared.properties,shared.properties
```

Per Spring Boot 3.3 documentation, an import is loaded **once**, even if declared multiple times.

This prevents redundant processing, and it also means you should never rely on repeating an import to boost priority:

```text
shared,service,shared
```

is not a reliable way to make `shared` beat `service`. Because of resource deduplication and document discovery rules, "last occurrence wins" may not behave as you expect for the same resource.

Good convention: **import each resource once at an intentional position**. If multiple modules need a shared file, standardize one place responsible for importing it or verify per context.

### Do Not Test Duplicate Import Deduplication via a Single Property Value

If `lab.import.mode=shared`, seeing `shared` does not prove the file was only loaded once. Investigating load counts requires inspecting `PropertySource` entries or appropriate instrumentation (keeping in mind internal source names may vary). In this lab, deduplication is noted per official documentation, while runtime tests focus on precedence and presence.

## 24. Why a "Shared Defaults File" Can Override Unexpectedly

Suppose a developer writes:

`application.properties`:

```properties
lab.import.timeout=1s
spring.config.import=classpath:/config/shared.properties
```

`shared.properties`:

```properties
lab.import.timeout=10s
```

After startup, timeout is `10s`, **not** `1s`, because the imported document takes precedence over the declaring document.

If the intent is for application settings to override shared defaults, you have clean options:

1. Move app-specific overrides into an **imported file listed after shared**:

   ```properties
   spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
   ```

2. Supply overrides from a higher-precedence runtime source such as CLI or environment (where appropriate).
3. Reorganize files across Config Data locations intentionally and test precedence per case.

Do not rely on line ordering inside the root file:

```properties
spring.config.import=classpath:/config/shared.properties
lab.import.timeout=1s
```

Putting `timeout` at the bottom **does not** override the imported document.

## 25. Preparing a Real Startup Test Suite

A test that only does:

```java
new MapPropertySource("shared", ...)
```

and inserts it manually into `StandardEnvironment` tests the priority order you wired by hand, **but does not prove `spring.config.import` was handled by Spring Boot**.

Therefore use:

```java
SpringApplication.run(...)
```

to exercise real Config Data preparation.

A test can:

1. Create a temporary directory via `@TempDir`.
2. Write `application.properties`, `shared.properties`, `service.properties`.
3. Pass `--spring.config.location=file:.../application.properties` before startup.
4. Call `SpringApplication.run(...)`.
5. Inspect `context.getEnvironment()`.
6. Assert markers for each file.
7. Assert an overlapping key across files to prove precedence.
8. Assert the typed config bean if testing Binder behavior.
9. Close `ConfigurableApplicationContext` in `try-with-resources`.

No web server or database is needed to verify these rules.

## 26. Why Do Tests Use `@TempDir`?

If tests modify:

```text
src/main/resources/application.properties
```

directly, they can dirty the repository or interfere with other tests. If tests depend on:

```text
./config/shared.properties
```

outcomes vary with the working directory of Gradle, Maven, IDEs, or CI.

`@TempDir` provides an isolated temporary directory:

```java
@TempDir
Path temp;
```

Then:

```java
Path root = temp.resolve("case-one/application.properties");
Files.createDirectories(root.getParent());
Files.writeString(root, "...", StandardCharsets.UTF_8);
```

And use:

```java
root.toUri()
```

to produce a valid file URI on the current OS.

Pass it as:

```java
"--spring.config.location=" + root.toUri()
```

rather than building a `file:` string manually by concatenating `Path.toString()` with `/` or `\`.

## 27. Minimal Test Class

The examples below use JUnit Jupiter, AssertJ, and a minimal Spring Boot configuration class.

`src/test/java/example/importlab/ImportPrecedenceTest.java`:

```java
package example.importlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;

class ImportPrecedenceTest {

    @TempDir
    Path temp;

    @ConfigurationProperties(prefix = "lab.import")
    record TestSettings(
            String mode,
            Duration timeout,
            int retryCount,
            boolean enabled,
            String owner
    ) {
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TestSettings.class)
    static class MinimalApp {
    }

    static Path write(Path file, String text)
            throws IOException {
        Files.createDirectories(file.getParent());
        Files.writeString(file, text, StandardCharsets.UTF_8);
        return file;
    }

    static ConfigurableApplicationContext start(
            Path applicationFile,
            String... overrides
    ) {
        SpringApplication app =
                new SpringApplication(MinimalApp.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        List<String> arguments = new ArrayList<>();
        arguments.add("--spring.config.location="
                + applicationFile.toUri());

        arguments.addAll(Arrays.asList(overrides));

        return app.run(arguments.toArray(new String[0]));
    }

    // The @Test methods in the following sections
    // belong inside this same class.
}
```

### Why Not Use `@SpringBootTest` on Every Test?

`@SpringBootTest` fits many other integration tests. Here, each test needs to **choose its own startup location/imports** and observe the result. `SpringApplication.run` expresses that directly.

### Limitation of the Helper

The helper points `spring.config.location` to **a specific file**, which **replaces default search locations**. This scopes each test strictly to its temporary files.

As a result, the demo app's `src/main/resources/application.properties` cannot accidentally interfere with import precedence tests.

## 28. Test A — Imported File Loads and Beats Declaring File

Files created:

```text
test-a/
  application.properties
  shared.properties
```

In the test:

```java
@Test
void importedDocumentOverridesDeclaringDocument()
        throws IOException {

    Path dir = temp.resolve("test-a");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab.import.mode=from-application\n"
            + "lab.import.application-marker=loaded\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.shared-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-shared");

        assertThat(env.getProperty(
                "lab.import.application-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.shared-marker"))
                .isEqualTo("loaded");
    }
}
```

Result:

```text
application-marker=loaded
shared-marker=loaded
mode=from-shared
```

**Proof 1:** both application and shared markers exist ⇒ both files were loaded.

**Proof 2:** `mode` is declared in both files and resolves to `from-shared` ⇒ the imported document overrides the declaring document here.

Asserting `mode` alone could still pass if an unexpected source injected `from-shared`. Unique markers and a dedicated test prefix reduce false positives.

## 29. Test B — Shared First, Service Second

In the same test class, add:

```java
@Test
void laterServiceImportOverridesSharedAndParent()
        throws IOException {

    Path dir = temp.resolve("test-b");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties,service.properties\n"
            + "lab.import.mode=from-application\n"
            + "lab.import.application-marker=loaded\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.timeout=10s\n"
            + "lab.import.retry-count=2\n"
            + "lab.import.enabled=true\n"
            + "lab.import.shared-marker=loaded\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
            + "lab.import.owner=orders-service\n"
            + "lab.import.service-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-service");

        assertThat(env.getProperty(
                "lab.import.application-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.shared-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");

        TestSettings settings = context.getBean(
                TestSettings.class);

        assertThat(settings.mode())
                .isEqualTo("from-service");

        assertThat(settings.timeout())
                .isEqualTo(Duration.ofSeconds(3));

        assertThat(settings.retryCount()).isEqualTo(2);
        assertThat(settings.enabled()).isTrue();
        assertThat(settings.owner())
                .isEqualTo("orders-service");
    }
}
```

This test verifies both layers:

```text
Config Data import -> Spring Environment
Spring Environment -> @ConfigurationProperties Binder
```

`mode=from-service` proves **precedence among imports**.

`retryCount=2` proves keys defined only in shared are preserved even when the service file loads after it.

`Duration.ofSeconds(3)` proves the Binder converted `"3s"` into a `Duration` instead of leaving it as raw text.

## 30. Test C — Reversing Import Order Flips the Result

Use identical file contents, reversing only the import list:

```java
@Test
void reversingImportOrderMakesSharedWin()
        throws IOException {

    Path dir = temp.resolve("test-c");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=service.properties,shared.properties\n"
            + "lab.import.mode=from-application\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.timeout=10s\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
            + "lab.import.service-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-shared");

        assertThat(env.getProperty("lab.import.timeout"))
                .isEqualTo("10s");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");
    }
}
```

Result:

```text
mode=from-shared
timeout=10s
service-marker=loaded
```

Both `shared` and `service` still loaded. **Changing only import order** changes the final value of overlapping keys. This directly proves precedence.

If your team expects service overrides, Test C demonstrates the ordering you **must avoid** in real application configuration.

## 31. Test D — Import Line at Top vs. Bottom Behaves Identically

This tests a different property than Test C.

Prepare two directories:

```text
test-d/first/
  application.properties
  shared.properties

test-d/last/
  application.properties
  shared.properties
```

File A:

```properties
spring.config.import=shared.properties
lab.import.mode=from-root
```

File B:

```properties
lab.import.mode=from-root
spring.config.import=shared.properties
```

Both directories contain `shared.properties` with:

```properties
lab.import.mode=from-shared
```

Test:

```java
@Test
void positionOfImportLineDoesNotChangePrecedence()
        throws IOException {

    Path firstDir = temp.resolve("test-d/first");
    Path lastDir = temp.resolve("test-d/last");

    Path first = write(
            firstDir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab.import.mode=from-root\n"
    );

    Path last = write(
            lastDir.resolve("application.properties"),
            "lab.import.mode=from-root\n"
            + "spring.config.import=shared.properties\n"
    );

    write(firstDir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    write(lastDir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    try (ConfigurableApplicationContext firstContext =
                 start(first)) {
        assertThat(firstContext.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-shared");
    }

    try (ConfigurableApplicationContext lastContext =
                 start(last)) {
        assertThat(lastContext.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-shared");
    }
}
```

**What this proves:** the line position of `spring.config.import` within a single document does not change the precedence of the imported document relative to the declaring document.

**What this does not prove:** that ordering across multiple YAML/properties documents never matters. Multi-document configuration has its own rules.

## 32. Test E — Command-Line Argument Beats Imported Files

Files:

`application.properties`:

```properties
spring.config.import=shared.properties,service.properties
lab.import.mode=from-root
```

`shared.properties`:

```properties
lab.import.mode=from-shared
```

`service.properties`:

```properties
lab.import.mode=from-service
```

Run:

```java
@Test
void commandLinePropertyOverridesAllImportedFiles()
        throws IOException {

    Path dir = temp.resolve("test-e");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties,service.properties\n"
            + "lab.import.mode=from-root\n"
    );

    write(dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    write(dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.service-marker=loaded\n");

    try (ConfigurableApplicationContext context = start(
            root,
            "--lab.import.mode=from-cli"
    )) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-cli");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");
    }
}
```

Result:

```text
service-marker=loaded
mode=from-cli
```

The marker shows the service import still loaded. The final value from CLI confirms **the CLI source outranks Config Data** under default settings.

### Note on `SpringApplication.setAddCommandLineProperties(false)`

If an application explicitly calls:

```java
application.setAddCommandLineProperties(false);
```

then `--lab.import.mode=from-cli` is no longer added automatically as a property source. This test leaves the default enabled.

Always distinguish **default `SpringApplication` behavior** from applications that customize command-line argument handling.

## 33. Test F — Profile-Specific Variant of an Import

Directory:

```text
test-f/
  application.properties
  service.properties
  service-prod.properties
```

```java
@Test
void profileSpecificVariantOfImportCanOverrideBase()
        throws IOException {

    Path dir = temp.resolve("test-f");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=service.properties\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
    );

    write(
            dir.resolve("service-prod.properties"),
            "lab.import.mode=from-service-prod\n"
            + "lab.import.timeout=2s\n"
    );

    try (ConfigurableApplicationContext context = start(
            root,
            "--spring.profiles.active=prod"
    )) {
        assertThat(context.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-service-prod");

        assertThat(context.getEnvironment()
                .getProperty("lab.import.timeout"))
                .isEqualTo("2s");
    }
}
```

Proof: Boot checks profile-specific variants for imported resources rather than simply reading a literal `service.properties` file via a basic file API.

### When Not to Overgeneralize

When other locations or multiple active profiles like `prod,live` are present, precedence also depends on **location groups and document placement**. Test F proves only the isolated single-import, single-profile scenario.

## 34. Test G — Nested Relative Imports

File set:

```text
test-g/
  application.properties
  common/
    shared.properties
    extra/
      feature.properties
```

`application.properties`:

```properties
spring.config.import=common/shared.properties
```

`common/shared.properties`:

```properties
spring.config.import=extra/feature.properties
lab.import.mode=from-shared
```

`common/extra/feature.properties`:

```properties
lab.import.mode=from-nested
lab.import.nested-marker=loaded
```

Test:

```java
@Test
void nestedImportResolvesRelativeToDeclaringFile()
        throws IOException {

    Path dir = temp.resolve("test-g");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=common/shared.properties\n"
    );

    write(
            dir.resolve("common/shared.properties"),
            "spring.config.import=extra/feature.properties\n"
            + "lab.import.mode=from-shared\n"
    );

    write(
            dir.resolve("common/extra/feature.properties"),
            "lab.import.mode=from-nested\n"
            + "lab.import.nested-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-nested");

        assertThat(env.getProperty(
                "lab.import.nested-marker"))
                .isEqualTo("loaded");
    }
}
```

This test is significant because if the second import had mistakenly resolved relative to `application.properties` instead of `common/shared.properties`, the app would have failed to find:

```text
common/extra/feature.properties
```

Seeing `nested-marker=loaded` confirms the nested file at the right path was loaded.

## 35. Test H — Missing Optional Import Still Starts

Create:

`application.properties`:

```properties
spring.config.import=optional:missing.properties
lab.import.mode=fallback
```

Test:

```java
@Test
void optionalMissingImportStillAllowsStartup()
        throws IOException {

    Path dir = temp.resolve("test-h");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=optional:missing.properties\n"
            + "lab.import.mode=fallback\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        assertThat(context.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("fallback");
    }
}
```

What this proves: a **location marked optional** without a backing file does not fail startup.

Do not use this example to claim all parser or binding errors are ignored whenever `optional:` is present.

## 36. Test I — Missing Required Import Fails Startup

Without `optional:`:

```properties
spring.config.import=missing.properties
```

Test:

```java
@Test
void requiredMissingImportFailsStartup()
        throws IOException {

    Path dir = temp.resolve("test-i");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=missing.properties\n"
            + "lab.import.mode=fallback\n"
    );

    assertThatThrownBy(() -> start(root))
            .isInstanceOf(RuntimeException.class);
}
```

The assertion verifies that the application **cannot start successfully**. If a project needs to assert the exact failure class, inspect the exception chain for the Boot-version-specific Config Data location/resource-not-found exception.

Never assert the entire verbatim exception message: temporary paths, OS formatting, and Spring Boot wording can change across patch releases.

### Test Resource Caution

Another project might have a `missing.properties` on the classpath or somewhere the test accidentally sees. Keep test prefixes and paths distinct from real project resources.

## 37. Use `@TempDir` Instead of Testing Internal `PropertySource` Names

One debugging snippet:

```java
for (PropertySource<?> source :
        context.getEnvironment().getPropertySources()) {
    System.out.println(source.getName());
}
```

This requires `ConfigurableEnvironment`. In a test helper, you can write:

```java
ConfigurableEnvironment environment =
        context.getEnvironment();

for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

Imports:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

Source names normally reflect Config Data resources, yet exact name formatting can vary across Boot releases and paths.

**Do not** write brittle tests that only pass when a source name matches a long exact string like:

```text
Config resource 'file [...]' via location '...'
```

A unique marker property inside each file is much more stable proof of "which file was loaded".

### Avoid Printing Entire `PropertySource` Contents

Runtime data may contain secrets. Print only **source names** or non-sensitive sample keys locally; never dump whole maps, environments, or passwords into CI logs.

## 38. Extra Practice: Shared File Outside the JAR

A deployment layout:

```text
workspace/
  app.jar
  config/
    shared.properties
```

The application can import:

```properties
spring.config.import=optional:file:./config/shared.properties
```

Because this is a file-relative location resolved against the process working directory, verify the actual working directory at launch.

A steadier option in environments with fixed paths is:

```properties
spring.config.import=file:/etc/myapp/shared.properties
```

or using a placeholder/variable defined sufficiently early per deployment policy.

### Combining Packaged and External Files

You may want:

```properties
spring.config.import=classpath:/config/shared.properties,optional:file:./config/service-overrides.properties
```

With the external file listed second, overlapping keys take values from the external file when present. When absent, the classpath file still supplies defaults.

Verify by:

1. Running once **without** the external file.
2. Running once **with** the external file containing the same key.
3. Asserting the external marker appears only when the file exists.
4. Asserting the conflicting key flips according to precedence.

Never test only the happy path with the file present; testing the fallback path when absent is equally critical.

## 39. File Locations, `spring.config.location`, and `spring.config.additional-location`

Three easily confused mechanisms:

| Mechanism | Purpose |
| --- | --- |
| `spring.config.import` | A document declares additional locations to import |
| `spring.config.location` | **Replaces** default search locations |
| `spring.config.additional-location` | **Adds** locations alongside default search locations |

Example:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties
```

reads the explicit location, replacing defaults.

With:

```bash
java -jar app.jar \
  --spring.config.additional-location=file:./config/
```

Boot keeps default search locations and adds the directory.

Do not treat `spring.config.import` as just another spelling of `additional-location`. Import **belongs to a document**, has import-relative semantics, and follows import override rules. Additional location participates in application-level search locations.

### Why Does the Test Use Explicit `spring.config.location`?

In JUnit, the helper passes:

```java
"--spring.config.location=" + root.toUri()
```

to intentionally isolate the run to temporary test files. That is a **test isolation technique**, not a recommendation for every production app to use `spring.config.location`.

## 40. Do Not Misapply the ".properties Last Line Wins" Mental Model

Within **a single `.properties` file**, duplicate keys follow properties parser behavior, yet you should never build policy around duplicate keys in one file.

Ordering **across Config Data files** and **line order within one file** are completely different things.

Common mistake:

```properties
spring.config.import=shared.properties
lab.import.mode=from-application
```

followed by claiming:

> Because `lab.import.mode` is at the end of the file, it beats shared.

Spring Boot's rule for imported documents makes that assumption false.

Instead of duplicating keys in a single file, place each value in its proper tier:

```text
shared.properties  -> shared fallbacks
service.properties -> service overrides
runtime CLI/env    -> deployment overrides
```

When multiple documents in one file are truly needed, use proper multi-document properties or YAML syntax and verify each document's activation and precedence.

## 41. Deliberate Error Exercise: Wrong Import Path

Suppose:

```properties
spring.config.import=classpath:/configs/shared.properties
```

while the actual file is at:

```text
src/main/resources/config/shared.properties
```

differing by `configs` vs. `config`.

When a required resource is missing, Spring Boot fails startup before creating application beans.

Diagnosis steps:

1. Read `spring.config.import` verbatim.
2. Check whether it is a fixed or relative location.
3. Verify the exact path and file extension.
4. Check whether the resource was copied into the build output/JAR.
5. Check whether Gradle/Maven resource filtering altered the file.
6. Check whether profile-specific files exist.
7. Never slap `optional:` onto a typo just to hide a missing required file.

For a JAR, inspect contents with:

```bash
jar tf path/to/app.jar
```

Spring Boot executable JARs store resources under `BOOT-INF/classes`, unlike plain library JARs. Search for the resource inside the archive rather than assuming all JARs share one layout.

## 42. Another Error Case: External File Overridden by Another Source

You see:

```properties
# service.properties
lab.import.timeout=3s
```

yet the application receives:

```text
lab.import.timeout=1s
```

This is completely expected if runtime has:

```bash
java -jar app.jar --lab.import.timeout=1s
```

Or a Java system property:

```bash
java -Dlab.import.timeout=1s -jar app.jar
```

Or an environment variable:

```text
LAB_IMPORT_TIMEOUT=1s
```

In standard Spring Boot 3.3, CLI outranks Config Data, so seeing `1s` does not prove imports are broken.

When investigating, separate four questions:

```text
A. Was the file loaded?                 -> marker
B. Which file won within Config Data?   -> conflicting key + isolated test
C. Which source won system-wide?        -> Environment / PropertySources
D. Which value did the bean bind?       -> @ConfigurationProperties
```

Never rely on one piece of evidence to answer all four questions.

## 43. Placeholders in Shared Files

One file:

```properties
lab.import.base-url=https://shared.example.test/api
```

can be referenced by the service file:

```properties
lab.import.health-url=${lab.import.base-url}/health
```

When `Environment` resolves the placeholder, it pulls the effective value of `lab.import.base-url` across current sources.

If CLI overrides:

```text
--lab.import.base-url=https://deploy.example.test/api
```

then the resolved value of `lab.import.health-url` updates accordingly.

### Distinguish the Two Sources

- The document **declaring** `lab.import.health-url`.
- The source **supplying the value** for `${lab.import.base-url}`.

An origin pointing to `service.properties` does not tell the whole story for resolved placeholders. In complex configs, inspect referenced keys as well.

### Placeholders with Defaults

```properties
lab.import.health-url=${lab.import.base-url:https://local.example.test}/health
```

This is placeholder default syntax—not a second `spring.config.import`. Do not confuse the `:` inside `${...}` with the URI scheme of a Config Data location.

## 44. When Is Splitting Too Many Files Counterproductive?

Splitting files helps when:

- Multiple services genuinely share a clear baseline of defaults.
- Every file has an explicit owner and purpose.
- Service overrides sit in predictable layers.
- Deployment environments supply distinct inputs.
- Automated tests verify precedence relationships.

Splitting too many files causes trouble when:

- Import chains become hard to trace.
- Duplicate keys hide across many layers without anyone realizing.
- Engineers edit low-priority files by mistake.
- Circular imports or convoluted nested paths appear.
- Interactions with profiles, location groups, and CLI overrides become opaque.
- Drift grows across local, CI, staging, and production.

Avoid architectures where a single property is defined in ten files "just to make sure it has a value". Instead, define one default source and one or two intentional override tiers.

## 45. Precedence Scenarios Summary Table

| Scenario | Declaration | `lab.import.mode` with no higher source |
| --- | --- | --- |
| No import | Only `application.properties=application` | `application` |
| One imported file | Root=`application`, shared=`shared` | `shared` |
| Two imported files | Root=`application`, shared=`shared`, service=`service`; import `shared,service` | `service` |
| Reversed imports | Import `service,shared` | `shared` |
| Move import line to bottom of root | Import still `shared` | `shared` |
| CLI override | Import `shared,service`, CLI=`cli` | `cli` |
| Profile variant | Import `service.properties`, active `prod`, variant=`prod` | `prod` |
| Missing optional import | Root=`fallback`, `optional:missing` | `fallback` |
| Missing required import | `missing.properties` absent | Startup fails |
| Nested imports | Root→shared→nested, overlapping keys | Depends on document order, e.g. nested beats shared |

Each row describes an isolated scenario. Adding profile-specific external files, system properties, CLI args, test overrides, or a custom `EnvironmentPostProcessor` can alter final values.

## 46. Common Troubleshooting Table

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| Shared file not loaded | Wrong classpath path or extension | Check resource path and JAR contents |
| Service override loses | Service listed before shared in import list | Change order to `shared,service` |
| Root property overridden by import | Expected precedence contract | Move override to a later import or appropriate source |
| Moving `spring.config.import` line has no effect | Line position in same document does not govern precedence | Check order in the import list |
| `optional:` hides missing production file | Required resource marked optional | Enforce fail-fast and validation |
| Test passes only on developer laptop | Relative filesystem path depends on working directory | Use `@TempDir` + `Path.toUri()` |
| Test passes even when file wasn't read | Asserted only conflicting key supplied by CLI | Add per-file marker properties |
| `application-prod.properties` alters outcome | Profile-specific Config Data participates in precedence | Check active profiles and sources |
| Nested import looks in wrong directory | Confused import-relative with working directory | Resolve relative to declaring file |
| `file:` path fails on Windows | Broken manual URI concatenation | Use `Path.toUri()` in Java tests |
| Both YAML and properties share basename | Different formats follow format precedence | Stick to one format, or test explicitly |
| Missing location error | Required file does not exist | Fix path; use `optional:` only if truly optional |
| CLI override ignored | App disabled command-line properties or custom source added | Check `SpringApplication` configuration |
| Typed bean gets null despite key in `Environment` | Model/binding/registration mismatch | Check `@EnableConfigurationProperties` and Binder |
| `retry-count` fails to bind from env | Env var name violates canonical rules | Use `LAB_IMPORT_RETRYCOUNT` |
| `service-prod.properties` ignored | Profile inactive or file misplaced | Verify active profile and import URI |
| Output changes across environments | Different OS env or system properties | Compare actual runtime sources |
| Key is read yet feature stays off | Binding vs. business logic mismatch | Test runtime behavior separately |
| Edited file, running app keeps old value | Config Data normally loads at startup | Restart or use explicit refresh |
| Logs leak secrets | Dumped full `Environment` or CLI args | Log only sample keys, enable sanitization |

## 47. Diagnosing with Actuator When Needed

Spring Boot Actuator offers useful endpoints:

```text
/actuator/env
/actuator/configprops
/actuator/conditions
```

They answer different questions:

- `/actuator/env`: `PropertySource` entries and reported values/origins.
- `/actuator/configprops`: bound `@ConfigurationProperties` beans.
- `/actuator/conditions`: auto-configuration evaluation report—**not** a listing of every property value.

When `lab.import.mode` is wrong, start with `Environment`/`env` to locate the winning source.

If an endpoint returns `******`, that is sanitization protecting sensitive data, not the literal value. Never enable `management.endpoint.env.show-values=always` publicly just to inspect one key.

For the tests in this lab, **Actuator is unnecessary**: `SpringApplication.run` and `Environment#getProperty` suffice to prove import rules in isolation.

## 48. Running Tests with Gradle and Maven in CI

Run Maven:

```bash
./mvnw test
```

Run a single class when Surefire is configured:

```bash
./mvnw -Dtest=ImportPrecedenceTest test
```

Gradle:

```bash
./gradlew test
```

Or:

```bash
./gradlew test --tests example.importlab.ImportPrecedenceTest
```

If `ImportPrecedenceTest` lives in a submodule, target the proper module/project path.

### Why Should These Tests Run in CI?

Changing:

```properties
spring.config.import=shared.properties,service.properties
```

to:

```properties
spring.config.import=service.properties,shared.properties
```

will not cause a compilation failure, yet it silently flips effective configuration.

Tests B and C catch that regression immediately instead of waiting for production to pick up the wrong timeout or feature flag.

### Never Write CI-Machine-Specific Tests

Avoid hard-coding:

```text
C:\Users\someone\Desktop\configs\shared.properties
```

or:

```text
/home/developer/work/config/shared.properties
```

in tests. `@TempDir` and `Path.toUri()` keep tests portable across Windows, Linux, macOS, and CI agents.

## 49. Extended Exercise 1 — Three Import Tiers

Design:

```text
shared.properties
organization.properties
service.properties
```

Values:

```text
shared:       lab.import.timeout=15s
organization: lab.import.timeout=8s
service:      lab.import.timeout=3s
```

**Question:** If `service` must win, how should the import list be written?

**Answer:**

```properties
spring.config.import=shared.properties,organization.properties,service.properties
```

Expected result:

```text
lab.import.timeout=3s
```

**Practice:** write a test creating all three files with `@TempDir`, asserting each file's marker and a final timeout of `3s`.

## 50. Extended Exercise 2 — Preserving Fallbacks When Service Omits a Key

Shared defines:

```properties
lab.import.retry-count=4
lab.import.timeout=10s
```

Service defines only:

```properties
lab.import.timeout=3s
```

**Question:** Is `retry-count` lost?

**Answer:** No. Here, `retry-count=4` continues coming from shared, while `timeout=3s` comes from service.

That is a central advantage of shared defaults + service overrides: services declare only what differs.

## 51. Extended Exercise 3 — Declaring Document vs. Imported Document

`application.properties`:

```properties
spring.config.import=shared.properties
lab.import.mode=root
```

`shared.properties`:

```properties
lab.import.mode=shared
```

**Question:** If you move `lab.import.mode=root` to the bottom of the root file, does it win?

**Answer:** Not merely from line position. Within a single document, imported data can override keys of the same name in the declaring document.

## 52. Extended Exercise 4 — Missing Optional Import

Root:

```properties
spring.config.import=optional:secrets-local.properties
lab.import.mode=local
```

No `secrets-local.properties` file exists.

**Question:** Must startup fail?

**Answer:** No. `optional:` permits a missing location in supported cases. Still, if the application requires a mandatory secret, it should fail via validation or policy checks rather than running with missing credentials.

## 53. Extended Exercise 5 — External File Beats Shared Classpath

Root:

```properties
spring.config.import=classpath:/config/shared.properties,optional:file:./config/override.properties
```

Shared:

```properties
lab.import.mode=shared
```

External override:

```properties
lab.import.mode=external
```

**Question:** What is the final value in a clean runtime when the external file exists?

**Answer:** `external`, given this import list and no higher-priority source.

**Practice:** create the external file, launch the app from a known working directory, then rename the external file and rerun. Observe the fallback behavior once the optional file is gone.

## 54. Extended Exercise 6 — CLI Beats All Imports

Shared:

```properties
lab.import.mode=shared
```

Service:

```properties
lab.import.mode=service
```

Run:

```bash
java -jar app.jar --lab.import.mode=operator
```

**Question:** What does `Environment#getProperty("lab.import.mode")` normally return?

**Answer:** `operator` under Boot's default command-line property source. This does not mean the two imports failed to load; it simply reflects a higher-precedence source.

## 55. Extended Exercise 7 — Import-Relative Paths

Root located at:

```text
/project/config/application.properties
```

imports:

```properties
spring.config.import=common/shared.properties
```

`shared.properties` inside `/project/config/common/` imports:

```properties
spring.config.import=more/extra.properties
```

**Question:** Where does Boot look for `extra.properties`?

**Answer:** Relative to the second declaring file:

```text
/project/config/common/more/extra.properties
```

Not in `/project/config/more/` or the working directory.

## 56. Extended Exercise 8 — Profile-Specific Import

Import:

```properties
spring.config.import=service.properties
```

Files present:

```text
service.properties
service-prod.properties
```

**Question:** When the `prod` profile is active, which file can contribute override values?

**Answer:** `service-prod.properties` is a profile-specific variant of the imported resource; verify within your application's exact Config Data layout.

## 57. Extended Exercise 9 — Source Markers Present, Different Value Wins

Test output:

```text
shared-marker=loaded
service-marker=loaded
mode=from-cli
```

**Question:** Why do markers from both files exist even though `mode` came from neither?

**Answer:** Markers prove both files loaded. `mode=from-cli` proves a higher-precedence source won for the overlapping key. Presence and precedence are two distinct assertions.

## 58. Extended Exercise 10 — `@ConfigurationProperties`

Service file:

```properties
lab.import.timeout=250ms
```

In Java:

```java
@ConfigurationProperties(prefix = "lab.import")
public record ImportSettings(Duration timeout) {}
```

**Question:** Must you declare a `String` to accept `250ms`?

**Answer:** No. Spring Boot Binder converts durations into `Duration` when the model is registered and the value syntax is valid. Tests should assert `Duration.ofMillis(250)`.

## 59. Checklist for Real Projects

- [ ] Identified which file holds shared defaults.
- [ ] Identified which file holds service overrides.
- [ ] Assigned clear ownership and purpose to each file.
- [ ] Verified import list order matches intended precedence.
- [ ] Documented overlapping keys.
- [ ] Added markers/tests proving each file actually loads.
- [ ] Tested that later imports beat earlier imports.
- [ ] Tested reversing import order on an overlapping key.
- [ ] Tested that importing documents beat declaring documents.
- [ ] Avoided relying on line position to infer precedence.
- [ ] Distinguished fixed vs. import-relative locations.
- [ ] Verified external paths against OS and working directory.
- [ ] Defined clear policies for required vs. optional files.
- [ ] Tested profile-specific variants.
- [ ] Tested CLI/OS env overrides where relevant.
- [ ] Avoided importing the same resource repeatedly to raise priority.
- [ ] Wrote typed binding tests for critical `Duration`/`int`/`boolean` fields.
- [ ] Kept secrets out of publicly packaged shared files.
- [ ] Avoided logging full `PropertySource` contents.
- [ ] Added real startup tests using `SpringApplication`.
- [ ] Used `@TempDir` and valid URIs in file-based tests.
- [ ] Closed every context after assertions.
- [ ] Protected configuration changes with CI checks.
- [ ] Tested production-like behavior separately from test configs.
- [ ] Verified behavior on the project's exact Spring Boot version.

## 60. Summary

In Spring Boot 3.3, splitting configuration into shared and service layers can be expressed as:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Mental model:

```text
application.properties
       |
       v
shared.properties
       |
       v
service.properties
       |
       v
Spring Environment
       |
       +-- CLI / system properties / environment may override
       |
       v
@ConfigurationProperties
```

In an isolated setup where all three files define the same key:

```text
application: mode=from-application
shared:      mode=from-shared
service:     mode=from-service
```

**service** wins because it is the **later import**.

If you reverse the imports, **shared** wins. If you pass `--lab.import.mode=from-cli`, CLI beats all imports. If `service-prod.properties` exists and `prod` is active, the profile variant participates in precedence.

Core takeaways:

1. **Imported Config Data can override the document that declared the import.**
2. **Later imports in the same list have higher precedence than earlier ones.**
3. **The line position of `spring.config.import` within the same document does not change this rule.**
4. **Import-relative** paths resolve relative to the declaring file; `classpath:` and `file:` are fixed locations.
5. **`optional:` only tolerates missing locations**; it does not ignore syntax errors or validation failures.
6. **An imported resource loads once** per Spring Boot's contract—do not repeat imports as a precedence trick.
7. **Markers + conflicting keys + typed beans** are three complementary verification checks.
8. **Use `SpringApplication.run(...)` and `@TempDir`** to prove real Config Data behavior portably across machines.
9. **Do not confuse import order with total runtime precedence**: CLI, Java system properties, environment variables, and other sources can still decide the final value.
10. **Package once, deploy per environment**: keep shared defaults stable, overrides explicit, and secrets securely managed.

When these rules are backed by CI tests, splitting shared configuration files becomes an evidence-based design rather than a fragile guess. That is the goal of this integrated practice.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, Importing Additional Data, Fixed and Import Relative Locations, Property Ordering, Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 Java API — `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework API — `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html
- JUnit Jupiter User Guide — `@TempDir`: https://junit.org/junit5/docs/current/user-guide/
