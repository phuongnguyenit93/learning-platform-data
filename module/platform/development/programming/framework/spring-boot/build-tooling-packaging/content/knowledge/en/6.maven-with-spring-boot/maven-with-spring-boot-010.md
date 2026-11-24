# Distinguishing Maven Profiles from Spring Profiles

In a Maven-based Spring Boot project, the word **profile** appears at two very different layers. For example, `mvn -Pci clean verify` and `java -jar app.jar --spring.profiles.active=prod` both mention a "profile", yet they have **separate targets, timing, and effects**. Confusing the two mechanisms easily leads to thinking "I built with `-Pprod`, so the app is already running in production configuration", or accidentally building separate JARs per environment when only runtime configuration needs to vary at startup.

**Core rules:**

- **Maven profiles** select **build-process configuration**: properties, plugins, dependencies, repositories, and Maven tasks. Maven evaluates them when constructing the effective POM, before and during compile, test, and package goals.
- **Spring profiles** select **application configuration and beans at runtime**: `application-{profile}.yml` files, conditional config documents, `@Profile`-annotated beans, and environment parameters read by Spring Boot at startup.
- **Profiles sharing the same name are not linked automatically.** `-Pdev` does not set `spring.profiles.active=dev`; likewise, `--spring.profiles.active=dev` does not activate a Maven profile named `dev`.

This lesson uses Java 17, Spring Boot 3.3.13, and Maven 3.9.x as illustrative baselines. If your project uses different versions, consult the documentation for that release while keeping the same two-layer separation.

## 1. Side-by-Side Comparison

| Criterion | Maven Profile | Spring Profile |
| --- | --- | --- |
| Processed by? | **Apache Maven** when building the effective project model and executing the build | **Spring Framework/Spring Boot** when building the application context |
| Direct activation | `mvn -Pci clean verify` | `--spring.profiles.active=dev`, `SPRING_PROFILES_ACTIVE=dev`, or equivalent API |
| Typical declaration | `<profiles><profile><id>ci</id>...` in `pom.xml`; Maven settings | `application-dev.yml`, `@Profile("dev")`, Spring config properties |
| Primary timing | Build time: dependency resolution, compile, test, package, publish | App startup/runtime: load configuration, instantiate beans, serve requests |
| What it selects | Plugin executions, properties, dependencies/repositories/build settings | Bean definitions, profile-specific properties, config-driven app behavior |
| What it never does automatically | Does not automatically switch active Spring profiles | Does not modify the effective POM or pick Maven plugins |
| Verification | `mvn help:active-profiles`, `mvn help:effective-pom`, build logs | Spring startup log, `Environment#getActiveProfiles()`, tests, or safe endpoints |
| Can both be used together? | Yes, in the same dev or CI run | Yes, though each must be selected separately or bridged explicitly |

Reading commands by layer:

```text
mvn -Pci clean verify
    └──── Maven profile "ci" → affects build/testing

java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
                                          └──── Spring profile "prod" → affects runtime

mvn -Pci spring-boot:run -Dspring-boot.run.profiles=dev
       │                       └──── Spring profile "dev" passed via Boot Maven Plugin
       └──── Maven profile "ci" for the build/plugin process
```

The third command **explicitly uses two separate controls**. Having matching profile names is solely a team convention if maintained deliberately—not an automatic inference by Maven or Spring.

## 2. Maven Profiles Operate at the Build Layer

Maven reads `pom.xml`, parent POMs, settings, and activation state to construct the **effective POM**. When a Maven profile is active, Maven merges the profile's supported sections into the build model: properties, dependencies, repositories, build plugins, plugin executions, and so on. Subsequent phases and goals execute against that model.

Maven profiles can be declared in:

- **Project POM:** `<profiles>` inside `pom.xml`; can customize dependencies, plugins, and build settings.
- **User settings:** `~/.m2/settings.xml`; focuses on properties, repositories, and pluginRepositories within settings rules.
- **Global Maven settings:** `conf/settings.xml` inside the active Maven installation, affecting installation-wide builds.

**Common activation mechanisms:**

```bash
mvn -Pci clean verify
mvn -Pci,quality clean verify
mvn -Dbuild.env=ci clean verify
mvn help:active-profiles
mvn help:effective-pom -Pci
```

The third command activates a profile only if `pom.xml` defines a matching `<activation><property>`; `-Dbuild.env=ci` itself merely sets a Maven user property. Profiles can also activate by JDK, OS, file presence/absence, `activeByDefault`, or settings configuration. An `activeByDefault` profile in a POM is deactivated when another profile in the same POM is activated; never rely on assuming "both will always run".

**`-P` is a Maven option.** For example, `mvn -Pprod package` simply tells Maven to find profile id `prod` and apply its build effects. It does not enter Spring Boot's `Environment` just because its id matches `application-prod.yml`.

### Example Maven Profile Changing Only the Build

The following fragment goes inside `pom.xml` under `<project>`:

```xml
<properties>
    <build.mode>standard</build.mode>
</properties>

<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.mode>ci</build.mode>
        </properties>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

With `-Pci`, `build.mode` changes from `standard` to `ci` and Surefire is configured to fail if no tests are discovered under its rules. This is a **build quality policy**. The `build.mode` property is not automatically used by application code or written into the JAR; it has further effect only if a build plugin or resource filtering is configured to read it.

Inspecting the Maven property value:

```bash
mvn help:evaluate -q -DforceStdout -Dexpression=build.mode
mvn -Pci help:evaluate -q -DforceStdout -Dexpression=build.mode
```

The Maven Help Plugin evaluates these to `standard` and `ci`, respectively. The property name is project-chosen; it is **not** a special Spring Boot configuration key.

## 3. Spring Profiles Operate at the Application Layer

When Spring Boot starts creating the `ApplicationContext`, it builds an `Environment` from many property sources: command-line arguments, environment variables, system properties, `application.yml`/`application.properties` files, and externalized configuration sources. Active profiles tell Spring which profile-specific config sources and conditional beans to include.

Common ways to set Spring profiles:

```bash
# Run packaged JAR: command-line application argument
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev

# Run JAR with JVM system property; -D must precede -jar
java -Dspring.profiles.active=prod -jar target/profile-demo-1.0.0.jar

# Linux/macOS: process-scoped environment variable
SPRING_PROFILES_ACTIVE=dev java -jar target/profile-demo-1.0.0.jar

# Run via Spring Boot Maven Plugin
mvn spring-boot:run -Dspring-boot.run.profiles=dev
```

PowerShell (Windows) uses its own environment variable syntax:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar target/profile-demo-1.0.0.jar
```

When running `java -jar` directly, `-Dspring-boot.run.profiles=dev` is **not** a runtime argument of the Spring Boot Maven Plugin; use `--spring.profiles.active=dev` or the right property/environment variable. Conversely, when running `mvn spring-boot:run`, `-Dspring-boot.run.profiles` is a Spring Boot Maven Plugin user property that passes active profiles to the plugin-launched app.

When no profile is active, Spring uses its **default profile**, usually named `default`; that does not mean Maven activates a Maven profile named `default`. You can set `spring.profiles.default` in a non-profile-specific config document to change the fallback choice.

## 4. Runnable Example: One App, Two Independent Profile Layers

This small project runs the **same JAR** with both `dev` and `prod` runtime configs, while Maven profile `ci` changes only the build's test-check policy. This directly demonstrates that the two mechanisms operate independently.

### Project Structure

```text
profile-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/profile/
    │   │   ├── ProfileDemoApplication.java
    │   │   ├── ProfileController.java
    │   │   └── DevOnlyNotice.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-dev.yml
    │       └── application-prod.yml
    └── test/
        └── java/dev/example/profile/
            └── ProfileDemoApplicationTests.java
```

### Complete POM

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>profile-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <build.mode>standard</build.mode>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <build.mode>ci</build.mode>
            </properties>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-surefire-plugin</artifactId>
                        <configuration>
                            <failIfNoTests>true</failIfNoTests>
                        </configuration>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
```

The POM inherits appropriate dependency/plugin management from the Spring Boot starter parent. Enabling `-Pci` adds the Surefire configuration to the effective POM; it **does not** set `spring.profiles.active`.

### Java Code

`src/main/java/dev/example/profile/ProfileDemoApplication.java`:

```java
package dev.example.profile;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`src/main/java/dev/example/profile/ProfileController.java`:

```java
package dev.example.profile;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    private final String label;
    private final Environment environment;

    public ProfileController(@Value("${demo.label}") String label,
                             Environment environment) {
        this.label = label;
        this.environment = environment;
    }

    @GetMapping("/mode")
    public String mode() {
        String[] active = environment.getActiveProfiles();
        String names = active.length == 0 ? "(none)" : String.join(",", active);
        return "label=" + label + "; active=" + names;
    }
}
```

This illustrative endpoint intentionally exposes **only profile names** and a harmless label. Never turn it into an endpoint dumping the entire `Environment`, as real systems can contain passwords, tokens, and sensitive settings.

`src/main/java/dev/example/profile/DevOnlyNotice.java`:

```java
package dev.example.profile;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevOnlyNotice implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Dev-only startup hook");
    }
}
```

`@Profile("dev")` registers the `DevOnlyNotice` bean only when the Spring `dev` profile is active. This is a **runtime bean registration** decision, independent of Maven `-Pci`.

### Shared Configuration and Spring Profile-Specific Configuration

`src/main/resources/application.yml`:

```yaml
demo:
  label: base
```

`src/main/resources/application-dev.yml`:

```yaml
demo:
  label: dev
```

`src/main/resources/application-prod.yml`:

```yaml
demo:
  label: prod
```

When running with `dev`, Spring Boot loads the shared config and the `application-dev.yml` variant; `demo.label` from `dev` takes effect at runtime. When running `prod`, it uses `prod`. With no active profile, the shared config yields `base` (since this example has no `application-default.yml`).

**All three YAML files are packaged inside the JAR.** Packaging multiple `application-{profile}.yml` files does not activate all profiles simultaneously; selection happens when the application starts. In production, store only non-sensitive values here; credentials and secrets must be supplied by the deployment environment or secret manager.

### Test Selecting a Spring Profile Independently of the Maven Profile

`src/test/java/dev/example/profile/ProfileDemoApplicationTests.java`:

```java
package dev.example.profile;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("dev")
class ProfileDemoApplicationTests {
    @Autowired
    private MockMvc mvc;

    @Test
    void usesDevProfileConfiguration() throws Exception {
        mvc.perform(get("/mode"))
                .andExpect(status().isOk())
                .andExpect(content().string("label=dev; active=dev"));
    }
}
```

Here `@ActiveProfiles("dev")` is a **Spring TestContext Framework** annotation: it selects the Spring profile for the test application context. Whether you run `mvn test` or `mvn -Pci test`, this test explicitly activates `dev`. Maven profile `ci` adjusts only Surefire and the POM build property.

### Running and Comparing Results

In the project folder containing the POM, with JDK 17 and compatible Maven installed (or replace `mvn` with Maven Wrapper `./mvnw` if present):

```bash
mvn -version
mvn clean verify
mvn -Pci clean verify
mvn -Pci help:active-profiles
mvn -Pci help:evaluate -q -DforceStdout -Dexpression=build.mode
```

With the sample POM, `-Pci` activates Maven profile `ci`; `build.mode` evaluates to `ci` and the "fail if no tests" policy applies. `ProfileDemoApplicationTests` runs under Spring profile `dev` because of `@ActiveProfiles`.

Once `target/profile-demo-1.0.0.jar` is built, run each startup command **separately**, stopping the previous instance before starting the next to avoid port 8080 conflicts.

**Case 1 — no Spring profile activated:**

```bash
java -jar target/profile-demo-1.0.0.jar
```

From another terminal:

```bash
curl -s http://localhost:8080/mode
```

Exact body from the example:

```text
label=base; active=(none)
```

**Case 2 — Spring profile `dev`:**

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev
```

Body of `/mode`:

```text
label=dev; active=dev
```

The application also prints `Dev-only startup hook` to stdout during startup (alongside environment-dependent Spring Boot logs).

**Case 3 — same JAR, Spring profile `prod`:**

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
```

Body of `/mode`:

```text
label=prod; active=prod
```

Here the `DevOnlyNotice` bean does not exist in the application context because it carries `@Profile("dev")`.

**Case 4 — Maven profile `ci` and Spring profile `dev` together, running from source:**

```bash
mvn -Pci spring-boot:run -Dspring-boot.run.profiles=dev
```

Maven profile `ci` affects Maven's POM evaluation; Spring Boot Maven Plugin explicitly passes `dev` to the application at launch. If you omit `-Dspring-boot.run.profiles=dev` and have no other Spring config source, `-Pci` alone **does not cause** `application-dev.yml` to be selected.

## 5. Why "Maven `dev`/`prod`" Does Not Equal "Spring `dev`/`prod`"?

Suppose a project has Maven profile id `prod` and `application-prod.yml`:

```bash
mvn -Pprod package
```

This command **only** tells Maven to apply profile `prod` if defined in POM/settings. Maven may alter plugins, dependencies, resource filtering, or packaging based on that profile's contents. However, that command **does not start the application**, and does not automatically write "Spring active profile=prod" into the JAR.

If you subsequently run:

```bash
java -jar target/profile-demo-1.0.0.jar
```

Spring still uses default configuration unless `spring.profiles.active`, an environment variable, or another runtime config source is present. For `prod` profile, activate it at launch:

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
```

**Conversely**, when running `java -jar ... --spring.profiles.active=prod`, Maven is not running at all, so a Maven `prod` profile cannot "suddenly" activate. Any build-time differences were already baked into the chosen artifact.

A common pattern in CI/CD:

```text
Source + POM
    |
    | mvn -Pci clean verify
    v
Tested artifact (single JAR)
    |
    +--> Dev      : java -jar app.jar --spring.profiles.active=dev
    |
    +--> Staging  : java -jar app.jar --spring.profiles.active=staging
    |
    +--> Prod     : java -jar app.jar --spring.profiles.active=prod
```

In this diagram, environments have different Spring configurations while **consuming the exact same approved JAR**, assuming the build does not intentionally alter code/resources per environment. This avoids the classic bug where "QA tested one build, and production ran a different build".

## 6. When Should You Choose Which Mechanism?

| Requirement | Appropriate Mechanism | Reason |
| --- | --- | --- |
| Enable extra static analysis/coverage gates in CI | Maven profile `ci` | Changes build plugins and phases/goals |
| Select a Maven repository mirror or valid plugin parameters | Maven settings/POM profile | Belongs to resolution and build |
| Enable a mock endpoint locally but not in prod | Spring profile `dev` + `@Profile` or conditional config | Controls runtime beans |
| Choose logging levels, service URLs, ports | Spring runtime config/profiles | Can change without rebuilding |
| Select dev/test/prod databases | Spring profiles + externalized config/secrets | Runtime environment determines connections |
| Test Spring beans under `test` configuration | `@ActiveProfiles("test")` and `application-test.yml` | Tests application context at test runtime |
| Enforce "build must fail if zero tests exist" | Maven Surefire config inside `ci` profile | Build quality policy |
| Produce artifacts with genuinely different formats or dependencies | Maven build profile when specifically required | Modifies the artifact itself; every variant must be tested |
| Deploy the same artifact across multiple environments | Spring profiles/runtime env | Preserves artifact immutability |

**Choose by responsibility boundary**, not by `"dev/test/prod"` naming. Sharing names across layers can be convenient organizationally, provided documentation clearly states what each layer controls.

## 7. Spring Profile Activation Mechanisms and Precedence

Spring Boot supports multiple ways to set active profiles:

- `spring.profiles.active=dev` in shared configuration documents.
- `SPRING_PROFILES_ACTIVE=dev` via environment variable.
- `java -Dspring.profiles.active=dev -jar ...` via JVM system property.
- `java -jar ... --spring.profiles.active=dev` via command-line application argument.
- `SpringApplication.setAdditionalProfiles(...)` or `Environment` programmatically.
- `@ActiveProfiles` for Spring integration tests.

**Configuration precedence** follows Spring Boot's property source order. Under default settings, command-line application arguments override `spring.profiles.active` in `application.yml`. Never guess the final value solely from seeing an `application-dev.yml` file: that file applies only when the profile is active and not overridden by a higher-precedence source.

### Profile-Specific Files

When `dev` is active, Spring Boot loads `application.yml` and `application-dev.yml`. Within the same configuration location group, values in profile-specific files override shared values. When activating multiple profiles like `dev,local`, profile files load in order, generally "later profile wins" for matching keys in the same location group; location ordering and externalized config can also affect precedence.

Example:

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev,local
```

This activates two Spring profiles (not two Maven profiles). If `application-local.yml` does not exist, its absence **does not automatically cause an error**; Spring still processes `dev` and other sources.

### Using `spring.config.activate.on-profile` in Multi-Document YAML

Instead of separate files, you can place conditional documents inside `application.yml`:

```yaml
demo:
  label: base
---
spring:
  config:
    activate:
      on-profile: dev
demo:
  label: dev
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  label: prod
```

This is an **alternative** to the three config files in the example; avoid mixing both patterns without carefully checking precedence. These YAML blocks apply only when the matching Spring profile condition holds; they have nothing to do with Maven `<profiles>`.

**Do not declare `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, or `spring.profiles.group` inside profile-activated documents**, such as `application-prod.yml` or blocks with `spring.config.activate.on-profile`. Spring Boot restricts profile-selection properties to non-profile-specific documents; placing them in the wrong document can cause startup config failures.

To compose supporting profiles, `spring.profiles.include` or `spring.profiles.group.*` are **Spring Boot runtime** tools—not ways to import Maven profiles. Use them only when profile grouping is needed, avoiding tangled configurations that obscure which beans actually load.

### Profile-Conditional Beans

Common annotations:

```java
@Profile("dev")
@Component
class DevDiagnostics {
    // Bean is registered only when the Spring dev profile is active.
}
```

This is an **illustrative snippet**, not a complete file with package/imports. In real apps, apply `@Profile` to `@Component`, `@Configuration`, or `@Bean` as needed; expressions like `@Profile("!prod")` are possible, though think carefully when multiple profiles can be active simultaneously. Never rely on Maven `-Pdev` to toggle beans.

## 8. When the Two Profiles Interact and How to Build an Intentional Bridge

Some setups intentionally map a Maven property into the Spring runtime, typically via Spring Boot Maven Plugin config, system properties, application arguments, or resource filtering. Example POM fragment:

```xml
<properties>
    <app.runtime.profile>dev</app.runtime.profile>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <profiles>${app.runtime.profile}</profiles>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This is a **POM fragment**, not a standalone POM. When running:

```bash
mvn spring-boot:run -Dapp.runtime.profile=prod
```

Maven sets user property `app.runtime.profile=prod`, Spring Boot Maven Plugin reads it via `<profiles>`, and passes `prod` to activate the Spring profile when launching the app **via the plugin**. For `java -jar` on a packaged JAR, `spring-boot:run` plugin config **no longer controls runtime**; you still need environment/CLI/system properties when launching the JAR.

To explicitly link a **Maven profile** to a **Spring profile**, a Maven profile could define `app.runtime.profile` while the plugin reads it. However, that couples the two layers and easily causes confusion. Use it only with a clear justification (such as local dev convenience), document the wiring, and test actual behavior. Never use such a bridge to bake secrets or "build specifically for production" when runtime config suffices.

**Resource filtering is another kind of bridge with different consequences:** Maven can substitute placeholders in resources at build time and package values into the JAR. That makes artifacts differ per Maven profile, requiring building, testing, and tracking each variant. In particular, avoid filtering binary resources or embedding passwords/tokens into the app. Spring Boot starter parent uses dedicated filtering rules and delimiters to avoid colliding with Spring's `${...}` expressions; configure filtering intentionally and never assume a Maven property automatically becomes an environment property.

## 9. How Are Maven Tests, Spring Tests, and Spring Profiles Selected?

A Maven profile can determine **which test plugins run** or add checks, yet it does not automatically choose the tests' active Spring profile.

**Three distinct controls:**

1. **Maven `-Pci`:** alters the effective POM and Surefire/Failsafe/plugin configs; can affect test discovery or test JVM properties if explicitly configured.
2. **Spring Test `@ActiveProfiles("test")`:** selects the active Spring profile for the test application context, often paired with `application-test.yml`.
3. **Spring system property/environment:** can supply active profiles to the test process if the test framework/config permits; the outcome still depends on `@ActiveProfiles` and configured property sources.

**Sample command:**

```bash
mvn -Pci clean verify
```

With the `@ActiveProfiles("dev")` test in Section 4, the test's Spring profile remains `dev` regardless of Maven running `ci`. Never deduce `@ActiveProfiles("ci")` from the Maven profile name.

When running integration tests against real databases or containers, configure Spring tests clearly, supply appropriate test resources, and ensure Maven plugins/phases are actually bound. `mvn verify` does not conjure integration tests if the project has not configured them.

## 10. Remembering the Limits of Each Tool

### Maven Profiles Do Not Manage Runtime Environments

- Never automatically select `application-prod.yml` or `@Profile("prod")` beans.
- Seeing a profile id in the POM does not guarantee it ran; verify via `mvn help:active-profiles`.
- Can be affected by parents, settings, build environment, activation triggers, and `-D`.
- Can alter the artifact; if producing multiple JAR variants, track sources, versions, checksums, and CI evidence carefully.
- Should not store secrets in the POM. Repo credentials belong in Maven settings/CI secret managers; runtime secrets come from the deployment environment.

### Spring Profiles Do Not Change Build Configuration

- Never modify the dependency graph or compiler plugin that ran during the Maven build.
- Never make Maven run Failsafe, JaCoCo, or Checkstyle.
- Never turn a plain JAR into an executable JAR if Maven did not configure Spring Boot `repackage`.
- Can choose dramatically different beans/configs at runtime; the same JAR does not behave identically across environments.
- Do not guarantee production config safety by themselves: health checks, monitoring, validation, and secret management remain essential.

### `-P` and `-D` Flags Are Easily Confused

| Syntax | Primary Processor | Direct Effect |
| --- | --- | --- |
| `mvn -Pci package` | Maven | Activates Maven profile `ci` |
| `mvn -Dbuild.mode=ci package` | Maven | Sets Maven user property `build.mode` |
| `mvn spring-boot:run -Dspring-boot.run.profiles=dev` | Maven Plugin then Spring | Plugin passes active Spring profile to the app |
| `java -Dspring.profiles.active=dev -jar app.jar` | JVM then Spring | Sets JVM system property for Spring to read |
| `java -jar app.jar --spring.profiles.active=dev` | Spring Boot | Command-line application property |
| `SPRING_PROFILES_ACTIVE=prod` | Process environment then Spring | Spring reads environment variable on startup |

**Similar flags do not mean the same recipient.** Maven's `-D` sets a user property for Maven/plugins; `-D` before `-jar` sets a JVM system property for the launching Java process. Only an explicit forwarding config links the two layers.

## 11. Common Errors and How to Verify

| Symptom | Possible Cause | How to Verify and Fix |
| --- | --- | --- |
| Ran `mvn -Pdev package` yet app uses `base` | `-Pdev` activates only a Maven profile | Pass `--spring.profiles.active=dev` when running JAR; check runtime env vars |
| `mvn -Pci verify` succeeds, tests still use `test` or `dev` config | Tests use `@ActiveProfiles` or separate Spring config | Inspect annotations, Spring startup logs, and test config |
| Expected Maven profile is not active | Wrong profile id, settings config elsewhere, or unmatched activation | Run `mvn help:active-profiles` and `mvn help:effective-pom` |
| JAR launched with `prod` yet values look like `dev` | Higher-precedence property source, wrong file, or leftover env var | Inspect startup logs, property sources, and env of that exact process |
| Startup fails after putting `spring.profiles.active` in `application-prod.yml` | Profile selection property placed inside a profile-specific file | Move profile selection to a non-profile-specific file or startup flags |
| `@Profile("dev")` bean missing despite building with Maven `-Pdev` | Maven profile does not activate Spring profiles | Set active Spring profile and verify `Environment` |
| `mvn spring-boot:run -Dspring-boot.run.profiles=dev` works, `java -jar` ignores it | That property is handled by Boot Maven Plugin, not JAR runtime args | With JAR use `--spring.profiles.active=dev`/env/system property |
| CI and local produce different JARs | Differing Maven profiles/filters/plugins/dependencies | Compare active Maven profiles, effective POM, Maven/JDK, artifact checksums |
| Tokens leaked inside artifact | Filtered env/secrets into resources at build time | Remove secrets from POM/resources; supply from runtime/secret manager |
| Multiple Spring profiles overlap on a property | Spring config precedence and file/profile ordering | Check active profile list, `spring.config.location` order, and property sources |

To investigate without changing application code:

```bash
# Maven layer
mvn -Pci help:active-profiles
mvn -Pci help:effective-pom

# Spring runtime layer: inspect startup logs with actual launch args
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev
```

Spring Boot startup logs report active profiles or fallback to the default profile. If the app enables Actuator, environment/config endpoints can expose sensitive values; never expose them publicly just to debug profiles.

## 12. Self-Check Exercises

**Scenario A.** There is a Maven profile `ci` enabling style checks and a Spring profile `prod` containing a production database URL. Does `mvn -Pci clean verify` connect to the production DB?

*Answer:* You cannot assume it does from `-Pci` alone. A Maven profile does not activate Spring `prod`. Inspect the tests' active Spring profiles and test runtime config; normally tests should never touch production DBs.

**Scenario B.** You want to deploy the exact same tested JAR to `staging` and `prod` while changing service URLs and log levels. What should you choose?

*Answer:* Keep the single JAR unchanged, supply Spring runtime properties and the corresponding `spring.profiles.active` per environment, and manage secrets outside the artifact.

**Scenario C.** You want CI to fail if zero tests are discovered. Should you use a Maven or Spring profile?

*Answer:* Use Maven plugin configuration, such as inside a Maven `ci` profile like the Surefire example. Spring `@Profile` does not configure Maven test discovery policies.

**Scenario D.** A project has a Maven profile id `prod`, yet `mvn -Pprod package` does not produce production config automatically. Why?

*Answer:* Maven only applies the build settings declared inside profile `prod`. There is no automatic bridge to Spring runtime unless the project explicitly configures one. To run in production mode, select the Spring profile and config source at app launch.

**Scenario E.** A test carries `@ActiveProfiles("test")`, and a developer runs `mvn -Pdev test`. Which Spring test profile is selected?

*Answer:* `test` via the Spring annotation, unless a custom test context override is configured. Maven `dev` does not replace the annotation with its own profile name.

**Scenario F.** Both `application-dev.yml` and `application-prod.yml` exist inside the JAR; when running `java -jar app.jar` with no profile flags, which file takes effect?

*Answer:* Neither is activated merely by existing. Spring uses shared config and the default profile per Spring rules. In Section 4's example, `/mode` returns `label=base; active=(none)`.

### Key Takeaway to Remember

**Maven profiles control how artifacts are built and verified; Spring profiles control application configuration and beans when running.** They can work together when explicitly wired via plugins/properties/filtering, yet never link automatically simply by sharing names like `dev`, `test`, or `prod`. When troubleshooting, ask two exact questions: *Which Maven profiles were active at build time?* and *Which Spring profiles are active in the running process?* Then verify with the tool for the corresponding layer.

### Official References

- Apache Maven — Introduction to Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven — Guide to Configuring Plugins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Externalized Configuration (Profile-specific Files): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Framework — Integration Testing / @ActiveProfiles: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html