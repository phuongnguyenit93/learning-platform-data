# Viewing Active Profiles and Config Data Loading Information in Logs

## 1. Lesson Objectives

In Spring Boot Externalized Configuration, an application can read configuration from many places: `application.yml`, `application.properties`, profile-specific documents, directories outside the JAR, `spring.config.import`, environment variables, Java system properties, and command-line arguments.

When a configuration value is wrong, the first question is usually not "where should I change the code?" but rather:

- **Which profiles are active in this run?**
- Which Config Data documents did Spring Boot load?
- Is a configuration file outside the JAR overriding the classpath file?
- Was the `application-prod.yml` document actually activated?
- Was `spring.config.import` resolved and loaded successfully?
- Was a key overridden by an environment variable, JVM option, or command-line argument?
- Did configuration fail to load, or was it loaded but failed binding/conversion/validation?

Spring Boot provides several diagnostic signals:

1. **Startup INFO logs:** typically show active profiles or the default profile.
2. **DEBUG/TRACE logs for the `org.springframework.boot.context.config` logger group:** help observe Config Data processing and resolution of configuration locations.
3. **Spring `Environment` and the `PropertySource` list:** show which sources are present and the effective value at a point in time.
4. **Config Data, binding, conversion, and validation error messages:** pinpoint which layer failed.
5. **Spring Boot Actuator** (if enabled and properly secured): helps inspect the environment and configuration properties of a running application.

The goal is to build an evidence-based log-reading workflow rather than guessing solely from the presence of a YAML file in the repository.

## 2. Why Can a Valid Configuration File Still Produce the Wrong Result?

Suppose the project has three documents:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

Common file:

```yaml
# application.yml
notification:
  endpoint: "https://default.example.invalid"
  timeout: 5s
  max-attempts: 3
```

Dev file:

```yaml
# application-dev.yml
notification:
  endpoint: "https://dev.example.invalid"
  timeout: 2s
```

Prod file:

```yaml
# application-prod.yml
notification:
  endpoint: "https://prod.example.invalid"
  timeout: 10s
  max-attempts: 5
```

If launched with:

```bash
java -jar app.jar --spring.profiles.active=dev
```

then Spring Boot can use values from the dev document for keys that document overrides. Conversely, when launched with:

```bash
java -jar app.jar --spring.profiles.active=prod
```

it can use the production values.

However, if the command line adds:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=750ms
```

then the final timeout typically comes from the command-line property `750ms`, no longer `10s` in `application-prod.yml`.

Therefore, **opening `application-prod.yml` alone is not enough to determine the value actually used**. You must inspect active profiles, loaded Config Data locations, and higher-precedence sources.

## 3. Distinguish Active Profiles, Default Profiles, and Loaded Documents

Three concepts are easily conflated into one:

| Concept | Meaning |
| --- | --- |
| Active profiles | Profile names currently considered active by Spring Environment |
| Default profiles | Default profiles considered when there are no active profiles |
| Config Data documents | Documents or configuration sources found, resolved, and loaded via the Config Data mechanism |

For example, when not declaring:

```properties
spring.profiles.active
```

Spring Boot may log that **no active profile is set**, then mention the default profile (typically `default` in standard setups).

That **does not mean** the application skipped `application.yml`. The base document can still be loaded.

Similarly, when the active profile is `prod`:

```text
active profiles: [prod]
```

you cannot infer every value must come from `application-prod.yml`. Spring Boot can still load base documents, imported documents, external classpath locations, and property sources outside Config Data.

**Conclusion:** active profiles are an important piece of information, but not a complete inventory of all `PropertySource`s or effective configuration values.

## 4. How Do Startup Logs Typically Display Profiles?

In a normal Spring Boot startup with startup info enabled, INFO-level logs may contain a message similar in meaning to:

```text
The following 1 profile is active: "dev"
```

or:

```text
No active profile set, falling back to 1 default profile: "default"
```

**These are illustrative examples of message form.** Exact profile counts, wording, language, and logger formatting can vary across Spring Boot versions and logging configurations.

When reading logs, focus on:

- Whether any profile is active.
- Which profiles are listed.
- **Which startup run** the log line belongs to.
- Whether multiple application processes or containers are emitting logs together.
- Whether any system automatically injects active profiles from environment or launcher.

If the log comes from an older JAR version or another pod, you may misdiagnose even when the profile line itself is completely valid.

## 5. Inspecting Profiles via Spring Environment

When you want to confirm with certainty which profiles the application sees after context initialization, read `Environment`.

Example:

```java
package com.example.configdemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfilePrinter implements ApplicationRunner {

    private final Environment environment;

    public ProfilePrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("defaultProfiles="
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
```

If `dev` is activated, illustrative output:

```text
activeProfiles=[dev]
defaultProfiles=[default]
```

If no active profile is set:

```text
activeProfiles=[]
defaultProfiles=[default]
```

Here `getActiveProfiles()` and `getDefaultProfiles()` return two distinct sets of information.

**Timing note:** `ApplicationRunner` executes after the Spring context has been refreshed. It confirms the Environment state at that time; it is not a step-by-step log of what Config Data did earlier.

## 6. Ways of Activating Profiles to Check

An active profile can be supplied in several ways.

### 6.1. Command-line arguments

```bash
java -jar app.jar --spring.profiles.active=dev
```

### 6.2. Java system property

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

For the JVM, `-D...` must be placed before `-jar` if it is meant to be treated as a Java system property.

### 6.3. Environment variable

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar .\app.jar
```

### 6.4. IDE Run Configuration

In an IDE, a developer might set:

```text
Program arguments:
--spring.profiles.active=dev
```

or:

```text
VM options:
-Dspring.profiles.active=dev
```

or an environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

These come from **different `PropertySource`s**, so when the same key name has multiple values, source precedence rules determine the outcome.

### 6.5. Gradle bootRun

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

In PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

`--args` passes program arguments to the application process. Do not confuse a `-D...` option passed to Gradle itself with a system property guaranteed to be passed to the application JVM.

## 7. Profiles Can Be Multiple Names, Not Necessarily One

An application can run with multiple active profiles:

```bash
java -jar app.jar --spring.profiles.active=dev,debug
```

In that case, documents or beans conditional on `dev` and `debug` can be evaluated according to their respective mechanisms and conditions.

Suppose:

```text
application.yml
application-dev.yml
application-debug.yml
```

Do not look only at profile `dev` and ignore the presence of `debug`, because another document/configuration group can override some values.

**Profile order can matter** in selecting profile-specific documents and overriding values when multiple profiles apply simultaneously. If two documents provide the same key, check the order and effective sources in the actual application.

When logs report multiple profiles, record the **entire list**, not just the first profile.

## 8. spring.profiles.include and Profile Groups

Besides `spring.profiles.active`, Spring Boot supports mechanisms that expand the profile set.

For example, in a document not restricted by profile:

```yaml
spring:
  profiles:
    include: "observability"
```

An application run with `prod` can simultaneously activate the additional profile `observability`.

Similarly, profile groups can be defined:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

When `production` is activated, this configuration group enables activating the member profiles under Spring Boot's mechanism.

**Important note:** `spring.profiles.active`, `spring.profiles.include`, and profile group definitions must obey placement rules regarding where they may be declared. They must not be placed arbitrarily in profile-specific documents or documents conditioned with `spring.config.activate.on-profile`.

When logs show more active profiles than you typed directly, check:

1. Is there `spring.profiles.include`?
2. Are there profile groups?
3. Did startup code or a test framework activate a profile?
4. Is a higher-precedence configuration source overriding `spring.profiles.active`?

Do not conclude this is a bug merely because the number of active profiles in the logs differs from what you typed directly.

## 9. spring.config.activate.on-profile Differs from spring.profiles.active

Example of a multi-document `application.yml` file:

```yaml
notification:
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

notification:
  timeout: 10s
```

The `---` marker separates YAML documents.

The property:

```text
spring.config.activate.on-profile
```

specifies **the condition for a configuration document to take effect**, and does not mean self-activating the `prod` profile.

To use the second document, the `prod` profile must be active from an appropriate configuration source/startup point.

In TRACE logs, you can see traces of processing and condition evaluation for Config Data documents. However, do not equate "a document was discovered" with "that document took effect in Environment."

Diagram:

```text
Document in application.yml
               |
               v
Has spring.config.activate.on-profile?
               |
        +------+------+
        |             |
       No            Yes
        |             |
        v             v
   Use under      Check active
   general rules  profile condition
                      |
                +-----+-----+
                |           |
              True        False
                |           |
                v           v
           Can be loaded   Do not apply
           per rules       that document
```

In practice, resolver details and document ordering are more intricate than the simplified diagram above.

## 10. What Is Config Data in Spring Boot?

**Config Data** is Spring Boot's mechanism for loading and combining configuration documents from supported locations, such as:

- `application.properties` or `application.yml` files on the classpath.
- Configuration files/directories external to the application.
- Files matching active profiles.
- Sources declared via `spring.config.import`.
- Location types supplied by Config Data extensions.

A high-level flow:

```text
SpringApplication.run()
          |
          v
Prepare Environment
          |
          v
Config Data:
  - Determine names/locations
  - Process imports
  - Evaluate profiles/activation
  - Load applicable documents
  - Order precedence
          |
          v
Spring Environment with multiple PropertySources
          |
          v
ConfigurationProperties Binder
          |
          v
Application configuration beans
```

Config Data is not a blanket term for **every PropertySource**. For example, Java system properties and environment variables typically participate in Environment, yet by themselves are not YAML documents loaded by the Config Data loader.

This is why even when you see Config Data files loaded, you still need to check non-Config-Data sources if the final value is unexpected.

## 11. Enabling TRACE for the Config Data Logger Group

When INFO logs show profiles without enough detail to find which files were loaded, a helpful technique is enabling TRACE for the logger group:

```text
org.springframework.boot.context.config
```

JAR launch example:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

In PowerShell:

```powershell
java -jar .\app.jar --spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE
```

This logger group covers components involved in preparing and processing Config Data in Spring Boot versions with the corresponding package structure.

When TRACE is enabled, logs **can** provide details about:

- Processing Config Data locations.
- Resolving candidate locations.
- Recognizing profile-specific documents.
- Importing declared sources.
- Document loading/application phases.
- Cases where configuration is missing or documents do not apply.

**There is no guarantee every Boot version prints the exact same messages or the same set of events.** Loggers, phrasing, and log levels can vary by version and logging implementation.

Also, do not treat TRACE as a stable machine-to-machine API for writing line-dependent log parsers across versions.

## 12. Why Pass logging.level as a Launch Argument?

The Config Data mechanism runs **very early** in the Spring Boot lifecycle. If you only declare:

```yaml
# application-prod.yml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

then depending on when `LoggingSystem` is configured and Config Data is processed, you might not see **all of the earliest events** of environment preparation.

For diagnostic testing, the most controllable approach is supplying the logger level right at startup:

```bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Or via Java system property:

```bash
java -Dlogging.level.org.springframework.boot.context.config=TRACE \
     -jar app.jar
```

These approaches make the logging configuration accessible from an early startup source, though one should not promise that every logging system or custom bootstrap shares the exact same timeline.

**Practical recommendation:** test via CLI or JVM property first, record the exact command executed, then read the logs of that exact process.

## 13. How to Run TRACE from an IDE

When an IDE runs the main class directly, configure Program arguments:

```text
--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE
```

Or in VM options:

```text
-Dspring.profiles.active=dev -Dlogging.level.org.springframework.boot.context.config=TRACE
```

The two options produce different PropertySource types, yet both can supply log levels and profiles to Spring Boot.

If the IDE has a dedicated field like **Active profiles**, understand that it is an IDE run-configuration convenience. It is not a second Spring Framework profile definition.

When reading logs in an IDE:

1. Confirm you actually started a fresh run.
2. Confirm the Run configuration belongs to the right module/main class.
3. Check whether Program arguments and VM options override each other.
4. Distinguish the main class run console from the Gradle task console.
5. If the IDE filters DEBUG/TRACE lines, check console visibility settings.
6. Do not take logs from a stopped debug session as logs from the current process.

## 14. How to Run TRACE with Gradle bootRun

With the Spring Boot Gradle plugin:

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE"
```

Here `--args` is the task option for passing **program arguments into the application process**.

Do not confuse:

```bash
./gradlew -Dlogging.level.org.springframework.boot.context.config=TRACE bootRun
```

with a command guaranteed to supply that Java system property to the application JVM; `-D` placed on the Gradle command typically affects Gradle's JVM and may not be forwarded by the task as expected.

If a system property is needed for `bootRun`'s JVM, configure the task explicitly or use program arguments as shown above.

**Distinguish logs:** Gradle also prints its own task logs. Lines about dependency resolution or the Gradle daemon are not Spring Boot Config Data logs.

## 15. How to Run TRACE with java -jar

Suppose an executable JAR already exists:

```text
build/libs/config-demo.jar
```

Command:

```bash
java -jar build/libs/config-demo.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Or:

```bash
java -Dspring.profiles.active=prod \
     -Dlogging.level.org.springframework.boot.context.config=TRACE \
     -jar build/libs/config-demo.jar
```

With the `-D...` approach, system properties go **before** `-jar`.

Common mistake:

```bash
java -jar app.jar -Dspring.profiles.active=prod
```

In the position after the JAR name, `-D...` is not interpreted by the JVM as a JVM system property. Unless the application has custom argument parsing for that form, the result will not match the correct command.

A more readable command when supplying Spring Boot command-line properties:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

## 16. --debug Is Not Equivalent to Config Data TRACE

Spring Boot supports the argument:

```bash
java -jar app.jar --debug
```

It can enable debug log levels for certain logger groups and support printing the **Condition Evaluation Report** when applicable.

The Condition Evaluation Report focuses on the conditions determining auto-configuration: why an auto-configuration was selected or not selected.

That is a different question from:

> How did Spring Boot resolve `file:./config/application-prod.yml` and which documents did it load?

Therefore:

| Goal | Appropriate tool |
| --- | --- |
| View basic active profiles | Startup INFO log and `Environment#getActiveProfiles()` |
| View Config Data steps | TRACE logger `org.springframework.boot.context.config` |
| View auto-configuration conditions | `--debug` / Condition Evaluation Report |
| View effective runtime values | `Environment` or secured Actuator |
| See why a configuration bean failed | Binding/conversion/validation exception |

**Do not just enable `--debug` and conclude that having no TRACE logs about a file means the file was not loaded.**

If both types of information are needed, you can combine `--debug` and TRACE logger-category configuration, while keeping log volume and sensitive data in mind.

## 17. Reading TRACE Logs in Sequence

When Config Data TRACE is enabled, read sequentially rather than spotting a single line and inferring everything from it.

**Step 1 — Identify a specific startup run.** Note the application name, process/container, startup timestamp, and artifact version if available.

**Step 2 — Find active/default profile information.** Record the exact profile list confirmed by the application.

**Step 3 — Look for location and resource messages.** Inspect classpath sources, directories outside the JAR, imported files, and locations not found.

**Step 4 — Look for profile-based document processing.** Are there documents that apply only when the matching profile is active?

**Step 5 — Look for Config Data loading errors.** Distinguish missing files, unresolvable imports, syntax errors, or unmet activation conditions.

**Step 6 — Cross-check effective runtime values.** Config Data logs show only part of the path; CLI, environment variables, or Java system properties can win.

**Step 7 — If the bean still fails, check binding/conversion/validation.** A file loading successfully does not guarantee every value inside it has the right type and is valid.

Do not try to read TRACE logs as an absolute list of properties actually used. They are diagnostic signals, not a complete per-key tracing database.

## 18. Illustrative Log Example with an Active Profile

Suppose you run:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

A paraphrased log might have a semantic structure similar to:

```text
INFO  ... Starting ConfigDemoApplication ...
INFO  ... The following 1 profile is active: "dev"
TRACE ... Considering configuration locations ...
TRACE ... Processing classpath application configuration ...
TRACE ... Processing profile-specific configuration ...
TRACE ... Applying configuration for active profile dev ...
INFO  ... Started ConfigDemoApplication ...
```

**This snippet is solely a content simulation for learning how to read logs**, not verbatim stdout from a specific Spring Boot version.

In real logs, logger names, messages, and line order can differ. One version may log `ConfigDataResource` objects and another may log information at the resolver/loader level.

Takeaways:

- The recorded profile is `dev`.
- There is activity related to Config Data processing.
- To be certain which file contributed a value, combine this with PropertySource order or runtime inspection.

## 19. Document Not Loaded Because Profile Is Inactive

Suppose:

```yaml
# application-prod.yml
notification:
  timeout: 10s
```

Run the application without enabling `prod`:

```bash
java -jar app.jar
```

Normally, `application-prod.yml` does not contribute profile-specific values if `prod` is not active.

Someone might read `application-prod.yml` in the repository and conclude the application must be using `10s`. Yet runtime uses the timeout from `application.yml`.

How to diagnose:

1. Check the active/default profiles log line.
2. Check whether CLI, VM options, or environment variables activate `prod`.
3. Enable Config Data TRACE to observe profile-based processing.
4. Confirm the effective value via the `@ConfigurationProperties` bean or a safe observation mechanism.
5. If needed, run an integration test with `prod` explicitly activated.

**Fix at the right layer:** activate the right profile or adjust the configuration source design; do not arbitrarily change defaults just to mask a profile-selection mistake.

## 20. A Discovered Document Is Not Guaranteed to Be Applied

Suppose `application.yml` has multiple documents:

```yaml
notification:
  enabled: true
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

notification:
  timeout: 10s
```

Config Data can encounter both documents while parsing the source. However, the second document only applies when the `on-profile: prod` condition matches.

Therefore, when searching for strings such as a filename in TRACE logs, distinguish:

- **Checked or discovered resource:** the resolver/loader interacted with that location.
- **Parsed document:** the document syntax was read.
- **Applied to Environment:** the document met conditions and entered the list of active sources.
- **Value actually won in Environment:** no higher-precedence source overrode that key.

These four states are not completely equivalent.

## 21. Default Config Data Locations and Working Directory

In standard Spring Boot setups, default search locations include classpath sources and locations external to the application, such as:

```text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
```

Locations may be processed according to specific Config Data groups and precedence rules; do not treat the simplified list above as a complete precedence chart.

**`./` depends on the Java process's working directory.**

For example:

```text
/opt/team/
  config/
    application.yml
  apps/
    service.jar
```

An operator runs:

```bash
cd /opt/team
java -jar apps/service.jar
```

which can make `./config/` point to `/opt/team/config/`.

However:

```bash
cd /opt/team/apps
java -jar service.jar
```

makes `./config/` point to `/opt/team/apps/config/`.

**The same JAR and the same profile with different working directories can lead to different sets of Config Data.**

If TRACE logs show only classpath config while you expect an external file, check the working directory before concluding Boot does not support external configuration.

## 22. spring.config.location and additional-location

There are two important properties:

```text
spring.config.location
spring.config.additional-location
```

High-level difference:

- `spring.config.location` redefines the default Config Data search locations according to its corresponding mechanism.
- `spring.config.additional-location` **appends** locations alongside the default locations.

Example:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/team/config/
```

The path `file:/opt/team/config/` is a directory-style location. The trailing `/` is important so the loader recognizes it as a configuration directory.

The `optional:` prefix is used when you want a missing location not to necessarily fail the application.

If you use:

```bash
java -jar app.jar \
  --spring.config.location=file:/opt/team/config/
```

understand that you are replacing the default location list rather than simply adding another place.

While reading TRACE, pay attention to whether a location is specified as **a file**, **a directory**, **a classpath resource**, or **a custom location**.

## 23. Why Config Data Cannot Be Diagnosed Using application.yml Alone

An application may package:

```text
BOOT-INF/classes/application.yml
```

yet at runtime also receive:

```bash
--spring.config.additional-location=file:/etc/my-service/
```

or:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION
```

supplied from the process environment.

In that case, documents outside the JAR can join the configuration sources depending on Config Data ordering rules.

Another scenario is that `application.yml` in the repository differs from the file packaged inside the running executable JAR. Therefore verify:

- Is the current artifact the right version?
- Was the resource file built into the JAR?
- Is the working directory right?
- Did `spring.config.location` replace the defaults?
- Is there a new import location?
- Does the profile match the document condition?

When needing to inspect the JAR:

```bash
jar tf app.jar
```

In typical Boot executable JARs, application resources reside under `BOOT-INF/classes/`. A file not in the artifact cannot magically appear via that artifact's classpath resources.

## 24. spring.config.import and How to Read Import Traces

Spring Boot supports importing documents:

```yaml
spring:
  config:
    import: "optional:file:./extra-config.yml"
```

When this source is loaded, Config Data processing can resolve the additional imported location.

Questions to answer when reading logs:

1. Was the document containing `spring.config.import` loaded?
2. Is the import property spelled and formatted correctly?
3. Is the path a relative or fixed location?
4. Does the imported resource exist?
5. Does it have the `optional:` prefix?
6. Does any profile affect the imported document?
7. Are multiple imports contributing the same key?
8. Does a higher-precedence source override the imported result?

Example:

```text
application.yml
       |
       +-- spring.config.import
                 |
                 v
          extra-config.yml
                 |
                 v
          PropertySource from import
```

Import does not merely mean "another file appended at the end." Spring Boot has rules about the position and precedence of imported documents.

In typical cases, imported data can override the document declaring the import under Config Data rules. However, the final value still depends on other sources and import order.

## 25. Missing Imports: Optional vs. Required

Look at:

```yaml
spring:
  config:
    import: "file:./local-overrides.yml"
```

If the file does not exist, Config Data can cause a startup failure because a required location was not found.

Symptoms may involve `ConfigDataLocationNotFoundException` or a corresponding Config Data error, depending on the specific situation.

If written as:

```yaml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
```

then the absence of the resource can be ignored under the optional mechanism.

**Do not turn every import into optional just to bypass startup errors.** If a file contains mandatory configuration such as production endpoints or security policies, optional can cause the application to use unintended defaults.

Workflow:

- If the file is genuinely optional: use optional and test the missing-file case.
- If the file is required: let the error surface early and fix the path/deployment permissions.
- If the file exists but has invalid content: optional **does not mean** ignoring all parse/binding errors.
- If the imported file loaded yet the value is overridden: check source order instead of merely adding optional.

## 26. A Complete Example to Practice Reading Config Data Logs

Create a project with the structure:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
  extra-flags.yml
```

Base file:

```yaml
# application.yml
spring:
  application:
    name: config-log-demo
  config:
    import: "classpath:extra-flags.yml"

demo:
  message: "base"
  timeout: 5s
  max-attempts: 3
```

Dev file:

```yaml
# application-dev.yml
demo:
  message: "development"
  timeout: 2s
```

Prod file:

```yaml
# application-prod.yml
demo:
  message: "production"
  timeout: 10s
```

Imported file:

```yaml
# extra-flags.yml
demo:
  enabled: true
```

A record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String message,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        boolean enabled) {
}
```

The examples use Java and Jakarta Validation for Spring Boot 3.x. If using a different version, adjust dependencies, packages, and APIs accordingly.

Register with:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigLogDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigLogDemoApplication.class, args);
    }
}
```

When run with `dev`, you have a small scenario sufficient to observe:

- Default file.
- Dev file.
- Imported file.
- Active profile.
- Values bound into the record.

## 27. Printing Non-Sensitive Values to Cross-Check with TRACE

Add a runner:

```java
package com.example.configdemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DemoConfigPrinter implements ApplicationRunner {

    private final DemoProperties properties;
    private final Environment environment;

    public DemoConfigPrinter(
            DemoProperties properties,
            Environment environment) {
        this.properties = properties;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("active="
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("message=" + properties.message());
        System.out.println("timeout=" + properties.timeout());
        System.out.println("maxAttempts=" + properties.maxAttempts());
        System.out.println("enabled=" + properties.enabled());
    }
}
```

When run:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

in the example without other overriding sources, the expected output has the meaning:

```text
active=[dev]
message=development
timeout=PT2S
maxAttempts=3
enabled=true
```

Because:

- `application-dev.yml` overrides `demo.message` and `demo.timeout` from the common file.
- `demo.max-attempts` still comes from the base configuration.
- `extra-flags.yml` provides `demo.enabled`.

**Do not confuse the final value lines from ApplicationRunner with logs from the Config Data loader.** The runner only displays the already-bound result after the Spring context is ready.

## 28. How to Tell Which Source Overrode a Key?

Config Data TRACE helps confirm the loading flow. However, to know which source is **providing a specific value**, you can inspect the `PropertySource` list in `ConfigurableEnvironment`.

Example printing **only source names**:

```java
package com.example.configdemo;

import org.springframework.core.env.ConfigurableEnvironment;

public final class PropertySourceReporter {

    private PropertySourceReporter() {
    }

    public static void printSourceNames(
            ConfigurableEnvironment environment) {

        int index = 0;

        for (var source : environment.getPropertySources()) {
            System.out.println(
                    (++index) + ". " + source.getName());
        }
    }
}
```

In a test or runner, call:

```java
PropertySourceReporter.printSourceNames(environment);
```

List order typically reflects precedence when Spring looks up the corresponding properties: sources earlier in the list usually have higher precedence.

**Warning:** some sources have composite structures, special name mappings, or distinct lookup behavior. Do not write production code that depends on fixed internal `PropertySource` names or counts.

### 28.1. Finding the First Source Containing a Non-Sensitive Key

For diagnostics in test/dev:

```java
import org.springframework.core.env.ConfigurableEnvironment;

public static void printCandidateSources(
        ConfigurableEnvironment environment,
        String key) {

    for (var source : environment.getPropertySources()) {
        Object value = source.getProperty(key);

        if (value != null) {
            System.out.println(
                    "Key " + key
                    + " found in source " + source.getName());
        }
    }
}
```

The snippet intentionally **does not print the value**, since a key may contain a token, password, or sensitive data.

It illustrates observing where a property is supplied under simple lookup. Not every PropertySource exposes all key spelling variants the same way, especially with environment variable relaxed binding. Therefore do not treat this result as a complete explanation for every Binder case.

For `@ConfigurationProperties`, the binder can handle property names, collection structures, and conversions that are more complex than a direct `source.getProperty(key)` call.

## 29. Using Environment to Read an Effective Key

Example:

```java
import org.springframework.core.env.Environment;

String message =
        environment.getProperty("demo.message");
```

If you manually pass:

```bash
java -jar app.jar --demo.message=from-cli
```

then under normal Spring Boot mechanics, the command-line property can beat the value from `application.yml`.

Output:

```text
demo.message = from-cli
```

but **do not infer Config Data was not loaded** just because CLI won. The YAML file can still sit in Environment and contribute other keys.

This is why TRACE logs and effective values should be used **together**:

- TRACE: helps show the configuration loading path.
- Environment: helps show the current value.
- Validation/binder: helps explain why the value could or could not create the bean.

## 30. Actuator env and configprops Assist Investigation

If the application has Spring Boot Actuator and the endpoints are appropriately enabled/secured, two helpful endpoints are:

```text
/actuator/env
/actuator/configprops
```

Overview:

- `env`: information about Environment/PropertySources and properties.
- `configprops`: information about `@ConfigurationProperties` beans and binding data the tool can display.

However:

1. Endpoints may not be exposed by default.
2. Response shapes and sensitive-value masking can differ across Spring Boot versions.
3. They can reveal internal configuration names or structures, and even secret data if misconfigured.
4. Do not expose them publicly on the Internet to solve a config bug.
5. Use authentication, authorization, a private management network, and an appropriate value-display policy.

Only open the necessary endpoints, in a controlled environment, then close or tighten permissions after investigation.

Do not disable sanitization just to "see all values" in production. For secrets, verify presence/status through a safe mechanism rather than requesting a plaintext token response.

## 31. Difference Between Config Data Logs and Binding Logs

After Config Data is processed, Spring Boot continues creating configuration beans. Errors can occur at this step.

Example:

```yaml
# application-prod.yml
demo:
  timeout: many-seconds
```

Expected bean:

```java
Duration timeout;
```

The following sequence can occur:

```text
Config Data loads application-prod.yml successfully
                |
                v
Environment has demo.timeout="many-seconds"
                |
                v
Binder looks up demo.timeout
                |
                v
ConversionService attempts String -> Duration
                |
                v
Conversion / binding error
```

The file was loaded; the error is not in the loader. If you keep enabling Config Data TRACE without inspecting the conversion cause, you may waste time.

Conversely, if the application reports a non-existent Config Data location before creating beans, editing `@DurationUnit` annotations will not fix a missing-file error.

**Diagnose at the right layer:** source loading → value selection → binding → conversion → validation → bean creation.

## 32. Distinguish Missing-File Errors from Missing-Property Errors

**Missing required file:**

```yaml
spring:
  config:
    import: "file:./critical-settings.yml"
```

If the resource does not exist, an error can occur during Config Data loading.

**Missing property inside an already-loaded source:**

```yaml
# application.yml
demo:
  message: "hello"
```

Yet the bean requires:

```java
@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotNull Duration timeout) {
}
```

The file can load successfully while `demo.timeout` is not provided. If validation runs, the bean can fail because a required value is missing.

Differences:

| Issue | Main symptom | Where to look |
| --- | --- | --- |
| Missing Config Data location | Location/import load failure | Path, `optional:` prefix, read permissions |
| File loaded but property missing | Binding or validation reports missing | Prefix, key, overriding sources, validation |
| Property present with bad format | Conversion/binding failure | Target type, raw value, converter |
| Valid type but out of bounds | Validation failure | `@Min`, `@NotBlank`, constructor invariant |

An INFO log saying "profile prod is active" does not prove every required production property exists.

## 33. Distinguish Misspelled Key Names from Invalid Values

Bean:

```java
@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @Min(1) int maxAttempts) {
}
```

Case A:

```yaml
demo:
  max-attemps: 4
```

The key `max-attemps` is misspelled. Binder does not automatically interpret this as `max-attempts` in all cases.

Case B:

```yaml
demo:
  max-attempts: many
```

Name is right, value cannot be converted to `int`.

Case C:

```yaml
demo:
  max-attempts: -5
```

Name is right, integer is type-valid, yet violates the `@Min(1)` constraint.

The three cases can produce different startup errors.

To increase detection of unknown keys within a bound prefix, consider:

```java
@ConfigurationProperties(
        prefix = "demo",
        ignoreUnknownFields = false)
```

However, this mechanism **is not a checker for all keys across all sources**. If you misspell the prefix `demo` itself as `dmeo`, the `demo`-prefixed bean might not notice that new group.

Config Data TRACE tells you which documents were loaded; it does not automatically verify every key in a document was read properly by a bean.

## 34. Source Precedence Can Mask a Valid File

Common file:

```yaml
demo:
  timeout: 5s
```

Prod file:

```yaml
demo:
  timeout: 10s
```

Environment variable:

```text
DEMO_TIMEOUT=30s
```

Command-line argument:

```bash
--demo.timeout=750ms
```

If all are present, standard Spring Boot precedence can let the CLI value beat the remaining sources.

This does not mean the YAML documents were not loaded. They can still contribute many other keys.

Diagram:

```text
Base Config Data      demo.timeout=5s
Prod Config Data      demo.timeout=10s
Environment variable  demo.timeout=30s
Command-line property demo.timeout=750ms
                         |
                         v
           Effective value: 750ms
                         |
                         v
              Duration.ofMillis(750)
```

So when an operator says "in `application-prod.yml` I set 10s," the next question should be "in the running process, is any environment variable or CLI argument overriding it?"

## 35. Why Config Data Logging and logging.level in YAML Can Mislead

Suppose you want to see TRACE logs for loading `application-prod.yml`, yet put the logger level itself inside `application-prod.yml`:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Part of Config Data resolution can happen before that logging configuration is fully applied.

When early messages do not appear, do not deduce the file was not loaded. Move the logger level to a CLI/JVM option right at startup:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Then cross-check against active profiles and PropertySources.

Even when using CLI, however, emitted messages still depend on the logger implementation, Spring Boot version, and bootstrap behavior. Do not take "missing a specific TRACE string" as sole proof that a file does not exist.

## 36. Use a Package-Level Logger Instead of Just a Single Class Logger

For example:

```text
org.springframework.boot.context.config
```

is a broader logger category than picking a specific class such as:

```text
org.springframework.boot.context.config.ConfigDataEnvironment
```

Enabling TRACE at the package level usually covers the activity of related components better, especially when you do not yet know which exact resolver/loader processes the data.

If logs are too noisy, you can narrow the category after identifying the area to investigate.

**Note:** implementation class names can change across versions; the package logger is usually a more practical starting point for diagnostics, not a public API guaranteed unchanged across every release.

## 37. Do Not Leave TRACE Enabled Long-Term in Production

TRACE logs can cause:

- Significantly increased log volume.
- Higher storage, transport, and search costs.
- Difficulty distinguishing important events among many internal messages.
- Potential exposure of deployment paths, internal locations, resource names, or protected config details.
- Increased risk if custom loggers/code print sensitive values.

Safe practices:

1. Enable TRACE in dev/test before applying in production.
2. If needed in production, limit scope and duration.
3. Use appropriate log access controls.
4. Avoid writing passwords, tokens, URLs with credentials, or sensitive info in extra messages.
5. Narrow the logger or revert to INFO after investigation.
6. Never attach log files containing secrets to tickets or public channels.

**Do not use TRACE as the default operating mode just in case a config error happens in the future.**

## 38. Scenario: Running in IDE Works, java -jar Fails

Symptoms:

- IDE runs the dev profile, `demo.timeout=2s`.
- JAR receives `demo.timeout=5s`.
- Same repository.

Hypotheses to check:

1. IDE has Program argument `--spring.profiles.active=dev`, while the JAR command does not.
2. IDE passes an environment variable, while the shell running the JAR does not.
3. IDE runs fresh sources/resources, while the JAR has not been rebuilt.
4. JAR starts from a different working directory, thus loading different external files.
5. JAR receives `spring.config.location` replacing default locations.
6. A command-line property overrides the dev configuration.
7. `application-dev.yml` was excluded from the artifact by build configuration.

Workflow:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Then read the profile log, loaded locations, and effective values.

If still different, verify the exact artifact:

```bash
jar tf app.jar
```

and look for `application*.yml` resources inside the JAR.

**Do not conclude "Spring Boot parses YAML differently between IDE and JAR" before checking inputs and the artifact.**

## 39. Scenario: Profile prod Is Active but Prod File Is Unused

Possible causes:

- `application-prod.yml` was not packaged or is not in a searched location.
- You set `spring.config.location`, replacing the default locations.
- The real config file has a base name other than `application`.
- `spring.config.name` points to a different name.
- A document has `spring.config.activate.on-profile` whose condition is unmet.
- A higher-precedence external Config Data location exists.
- A command-line or environment property overrides values from the prod file.
- You are reading logs from a different process.

To distinguish:

1. Check the actual active profiles.
2. Enable TRACE for `org.springframework.boot.context.config` at startup.
3. Inspect locations and processed resources.
4. List `PropertySource` names.
5. Read the effective value of a representative non-sensitive key.
6. Inspect the JAR and filesystem if the expected resource is not found.

Only fix once the failing layer is identified. Adding a new `@PropertySource` or `EnvironmentPostProcessor` merely because the prod file "isn't taking effect" can complicate the system without addressing the cause.

## 40. Scenario: application.yml Has spring.config.import, but Value Is Missing

Example:

```yaml
spring:
  config:
    import: "optional:file:./feature-flags.yml"
```

Possible causes:

1. `feature-flags.yml` does not exist in the current working directory.
2. The import is optional, so Spring continues without loading the missing file.
3. The document containing the import was not applied for the profile.
4. The file has content, yet does not declare the key you are looking for.
5. The key is overridden by a higher-precedence source.
6. The file loaded, yet the binder did not recognize the property name.
7. The path was interpreted relative to a different Config Data context than expected.

Questions to answer in logs:

- Was location `feature-flags.yml` considered?
- Is there any sign the resource was not found?
- Was any imported document actually applied?
- What values did the configuration properties bean receive?

**Do not look solely at `optional:` and conclude Spring Boot "loaded it successfully."** `optional:` permits missing locations under its rules; it does not confirm the file is present.

## 41. Scenario: Error When Profile-Specific Document Contains spring.profiles.active

Example to avoid:

```yaml
# application-prod.yml
spring:
  profiles:
    active: "prod"
```

A document loaded only when `prod` is active is not the right place to re-declare activating that profile.

Spring Boot restricts placing properties such as `spring.profiles.active` and `spring.profiles.include` inside profile-specific or profile-activated documents.

The right approach is usually:

```bash
java -jar app.jar --spring.profiles.active=prod
```

and:

```yaml
# application-prod.yml
demo:
  timeout: 10s
```

If you hit a Config Data profile-activation error, check where the profile properties are declared rather than only trying to raise logging levels.

TRACE logs can help point to the relevant document, but **fixing the profile declaration contract** is what resolves the error.

## 42. Scenario: Multiple Profiles and Overridden Keys

Suppose:

```yaml
# application-dev.yml
demo:
  mode: "development"
  timeout: 2s
```

```yaml
# application-debug.yml
demo:
  mode: "debug"
  timeout: 1s
```

Run:

```bash
java -jar app.jar --spring.profiles.active=dev,debug
```

Depending on profile-specific Config Data application rules and other sources, one of the two documents can contribute the effective value for `demo.timeout`.

To confirm accurately:

1. Record the order of active profiles.
2. Check actual loaded files/directories.
3. Identify which `PropertySource`s contain `demo.timeout`.
4. See which source comes earlier in Environment.
5. Read the final value on the bean/Environment.

Do not write "dev profile always beats debug" or vice versa without examining how documents are organized and applied in the running system.

If an absolute value is needed, move the environment rule into a source with clearly controlled precedence instead of relying on an obscure ordering.

## 43. Scenario: Using @PropertySource and Expecting to See It in Config Data TRACE

Spring Framework has the annotation:

```java
@Configuration
@PropertySource("classpath:company.properties")
public class CompanyPropertiesConfiguration {
}
```

The `@PropertySource` mechanism is processed while building the Spring context, separate from Spring Boot's Config Data mechanism.

Therefore, if a property is supplied by `@PropertySource`, TRACE logs from `org.springframework.boot.context.config` **are not the sole or always direct tool for observing how that source is handled**.

When diagnosing:

- Determine whether the source comes from Config Data or from annotation/context processing.
- Inspect the `PropertySource` list in Environment.
- Note that `@PropertySource` can be added relatively late, unsuitable for controlling certain early startup properties.

Do not lump every mechanism that adds a PropertySource into the single concept "Config Data loader."

## 44. Scenario: EnvironmentPostProcessor Adds a Custom Source

An application may have:

```java
public final class CompanySettingsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "companyOverrides",
                        Map.of("demo.timeout", "30s")
                )
        );
    }
}
```

This snippet illustrates the logic of an `EnvironmentPostProcessor`; to be invoked by Spring Boot, the processor must also be registered via the corresponding SPI.

If the `companyOverrides` source is placed first and contains `demo.timeout`, its value can beat Config Data documents.

In that situation, TRACE for loading `application-prod.yml` can confirm the file loaded, yet **the final timeout is still `30s` from the custom PropertySource**.

This is a second reason not to treat Config Data TRACE as an exhaustive table of runtime precedence.

## 45. Declaring the Log Category in application.yml

For lighter diagnostics when observing the earliest events is not required, you can use:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

in configuration that Spring Boot can read.

Or Properties:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

When needing to revert to normal levels:

```yaml
logging:
  level:
    org.springframework.boot.context.config: INFO
```

But remember:

- A YAML file must be loaded before its values affect logging.
- If the file is missing or the profile is inactive, the TRACE option inside that file may not take effect.
- Very early bootstrap steps are not necessarily recorded fully when the logging level is only configured via a late-loaded document.

To investigate Config Data loading itself for a suspect profile, **passing the logger level at startup** is much easier to control.

## 46. Why Not Print Every Property to Logs?

When unsure where a value was picked from, some developers try:

```java
// Not recommended:
for (var source : environment.getPropertySources()) {
    System.out.println(source.getSource());
}
```

This can print the entire content of sources, including passwords, API tokens, client secrets, connection strings, or internal details.

Even serializing an entire `@ConfigurationProperties` bean can leak secrets if the bean is a record with an auto-generated `toString()`.

Safer alternatives:

- Print **PropertySource names**, not the value Map.
- Read only a few identified non-sensitive keys.
- For secrets, only verify presence or absence using a controlled check.
- Do not send logs containing secrets to shared channels.
- Maintain appropriate logging levels and Actuator access controls.

A missing-configuration bug must never turn into a data-leak incident.

## 47. Log-Based Diagnosis Differs from Validation

Suppose a record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int maxThreads,
        @NotNull Duration timeout) {
}
```

Config Data:

```yaml
worker:
  max-threads: -4
  timeout: 3s
```

TRACE logs can show the YAML document loaded successfully. `Duration` can also convert successfully. Yet `maxThreads=-4` violates `@Min(1)` when validation runs with a suitable provider.

This is not a Config Data loading failure.

A separated diagnostic workflow:

```text
Config Data: file loaded? ----------> Yes
Environment: key present? ----------> Yes
Binding: "3s" to Duration? ---------> Yes
Validation: maxThreads >= 1? -------> No
Outcome: configuration bean failed
```

Trying to fix a validation issue by changing `spring.config.location` is going in the wrong direction.

## 48. Testing Profiles in an ApplicationContext

If you want to actually confirm a profile is activated and its document is loaded, create an integration test.

Example:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DevProfileConfigurationTest {

    @Autowired
    private Environment environment;

    @Autowired
    private DemoProperties properties;

    @Test
    void devProfileIsActive() {
        assertThat(environment.getActiveProfiles())
                .contains("dev");
    }

    @Test
    void devDocumentProvidesExpectedValues() {
        assertThat(properties.message())
                .isEqualTo("development");
    }
}
```

This test assumes `application.yml`/`application-dev.yml` files and the `DemoProperties` record are registered as in the earlier example.

If a test property source overrides `demo.message`, assertions must reflect the actual source set. Therefore an integration test should control inputs to avoid accidental dependence on developer settings.

**Difference:** the test above verifies runtime behavior of profiles and binding, whereas reading TRACE logs is primarily a diagnostic technique for a running system.

## 49. Testing an Application Running with Profile prod

Another test:

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Autowired
    private DemoProperties properties;

    @Test
    void usesProductionTimeout() {
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(10));
    }
}
```

For this snippet to compile, you need the corresponding imports for JUnit, AssertJ, `Duration`, Spring Boot Test, and the test dependency as in your project.

The test relies on the example data:

```yaml
# application-prod.yml
demo:
  timeout: 10s
```

It does not verify whether the production deployment directory has the right path or secrets; that belongs to integration/smoke tests in the deployment environment.

If the goal is to determine why **a production JAR run** received a different value, compare the logs and `PropertySource`s of the production process itself rather than relying only on tests using the project classpath.

## 50. Checking Profiles When Running the Real java -jar

For a built artifact, use the same standard command from the operational runbook:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Then:

1. Check INFO profile line.
2. Look for Config Data events.
3. Check whether the app loaded any unexpected external file.
4. Check whether startup had loader/binder/validation errors.
5. Check non-sensitive values in a runner or a secured inspection tool.
6. Once a conclusion is reached, disable TRACE or return to normal log levels.

If in a multi-replica deployment only one replica fails, tie logs to the specific **instance/pod/container**. Two replicas may run different versions or different environment variables.

Reading a profile line without process-identifying info in a distributed system easily leads to wrong conclusions.

## 51. Docker/Kubernetes Logs and Actual Profiles

A container may be run with:

```text
SPRING_PROFILES_ACTIVE=prod
```

yet do not assume that variable certainly entered the right container merely because a manifest or Docker Compose config mentions it.

Checkpoints:

- Was the variable passed into the final Java process?
- Did an entrypoint script modify or unset the variable?
- Did a command-line argument override the active profile?
- Does the working directory/container filesystem contain the external config path?
- Did the file mount succeed?
- Are multiple replicas or revisions running concurrently?

In a multi-instance environment, application logs are evidence of **the profile the process actually received**, while determining why the profile has that value also requires inspecting container configuration and the launch command.

Do not print the container's entire environment into logs for investigation if it contains secrets.

## 52. Enabling Logging via Environment Variables Can Hit Naming Issues

Spring Boot supports relaxed binding of environment variables. However, properties representing logging categories with dots/case sensitivity for class names must be handled carefully.

For example, package category:

```text
logging.level.org.springframework.boot.context.config
```

can be represented by an appropriate environment mechanism in many cases, yet case-sensitive logger class names can cause issues if the entire name is converted to an uppercase environment variable.

For reproducible diagnostics, **CLI or Java system property with the full category name** is usually clearer:

```bash
--logging.level.org.springframework.boot.context.config=TRACE
```

or:

```bash
-Dlogging.level.org.springframework.boot.context.config=TRACE
```

It preserves the exact dots and logger name.

## 53. Watch Out for Profiles Programmatically Activated by Code

In addition to `spring.profiles.active`, startup code or tests can add profiles through the Environment configuration API.

Conceptual example:

```java
ConfigurableEnvironment environment = ...;
environment.addActiveProfile("debug");
```

If the change happens at the right time, Environment's profile set can differ from the value read from a single property alone.

However, **do not alter active profiles after Config Data has already been resolved and assume Spring Boot will automatically reload all profile-specific documents**.

When you notice more active profiles in logs than expected, inspect custom initializers, environment post-processors, test annotations, and how `SpringApplication` is configured.

Changing profiles too late can also leave a hard-to-reason-about state between active profiles and already-loaded documents.

## 54. Why Changing Profiles at Runtime Does Not Auto-Reload Config Data

Config Data is prepared during startup. While the application is running, you might change an environment variable in another shell or replace a YAML file on disk, yet do not assume Spring Boot will automatically:

1. Detect the change.
2. Recompute active profiles.
3. Reload all Config Data documents.
4. Reapply source precedence.
5. Rebind all `@ConfigurationProperties`.
6. Recreate services that already used old values.

To have dynamic refresh, the application needs a dedicated mechanism, such as an explicitly designed and tested configuration refresh solution. Changing a file on the filesystem is not equivalent to a fresh startup.

Therefore, when startup logs show `prod`, someone later changing an environment variable to `dev` in another terminal **does not prove the application is using dev**.

To confirm the current profile, read the Environment of **the running process**, not just variables in the observer's shell.

## 55. When to Use --trace Instead of a Logger Category?

Spring Boot also has a global diagnostic logging option in certain launch modes, for example:

```bash
java -jar app.jar --trace
```

However, enabling general trace can increase log volume sharply and does not necessarily focus on Config Data specifically.

When the goal is clearly **observing configuration loading**, prefer enabling the exact category:

```text
org.springframework.boot.context.config=TRACE
```

If additional logging startup information is needed, add other loggers based on investigation findings rather than opening all TRACE logs uncontrollably.

Do not treat `--trace` or `--debug` as tools that "print every Config Data value" — they alter log verbosity rather than turning Spring Boot into a complete explainer for every key.

## 56. How to Record Diagnostic Evidence for Another Team to Reproduce

A good configuration bug report should include:

| Information | Example |
| --- | --- |
| Application/artifact name | `config-demo.jar` |
| Version/commit | A confirmed build identifier |
| Time and instance | Startup timestamp, pod/container |
| Active/default profiles | `[prod]` / `[default]` |
| Launch command without secrets | `java -jar app.jar --spring.profiles.active=prod` |
| Working directory | `/opt/team` |
| Config Data locations | Non-sensitive names/locations |
| Affected key | `demo.timeout` |
| Target type | `Duration` |
| Masked value if sensitive | Never put tokens/passwords in tickets |
| Key log error | E.g. exception type, key name |
| Expected result | `10s` |
| Actual result | `750ms` |
| Suspect PropertySource | Higher-precedence source name |

There is no need to attach the entire TRACE log if snippets contain excessive environment info or credentials. Select relevant diagnostic excerpts with proper information control.

## 57. Diagnostic Tool Comparison Table

| Symptom | First tool to use |
| --- | --- |
| Unknown active profile | Startup INFO log, `Environment#getActiveProfiles()` |
| Suspect profile file not loaded | Config Data TRACE |
| Suspect `spring.config.import` wrong path | Config Data TRACE and location errors |
| Suspect external-to-JAR source ignored | Working directory, location, Config Data TRACE |
| File loaded but strange value | `PropertySource` list, `Environment#getProperty()` |
| CLI/env may be overriding YAML | Inspect source order and process inputs |
| Wrong Duration/DataSize/Integer type | Binding/conversion exception |
| Negative number or blank string | Bean Validation / constructor invariant |
| Auto-configuration not activating | Condition Evaluation Report, `--debug` |
| `@ConfigurationProperties` bean missing | `ConfigurationPropertiesScan`/`EnableConfigurationProperties` |
| Value in repo missing from JAR | `jar tf`, artifact/version |
| Value changed but bean unchanged | Binding timing and refresh mechanism |

Knowing the right tool shortens root-cause investigation and prevents fixing the wrong layer.

## 58. Exercise A: No Active Profile

You see a log with the meaning:

```text
No active profile set, falling back to 1 default profile: "default"
```

`application.yml` has:

```yaml
demo:
  message: "base"
```

**Question:** can you conclude Spring Boot did not load `application.yml`?

**Answer:** no. Having no active profile does not mean base documents were not loaded. Default documents can still participate in Config Data.

## 59. Exercise B: prod Profile Active Yet Timeout Is Not 10s

`application-prod.yml`:

```yaml
demo:
  timeout: 10s
```

Run command:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --demo.timeout=500ms
```

**Question:** if the bean receives timeout 500ms, does that prove the prod file was not loaded?

**Answer:** no. Command-line properties typically take higher precedence than Config Data, so the prod file may have been loaded while its value was overridden.

## 60. Exercise C: Enable TRACE on the Right Category

**Task:** run the JAR with the `dev` profile and enable Config Data TRACE logs.

Command:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

**Question:** why not use only `--debug`?

**Answer:** `--debug` serves general debug info and the Condition Evaluation Report; when the target is Config Data processing, setting the specific logger category to TRACE is more direct.

## 61. Exercise D: Optional Import

File:

```yaml
spring:
  config:
    import: "optional:file:./extra.yml"
```

`./extra.yml` does not exist.

**Question:** can startup proceed without the imported file?

**Answer:** yes, because the `optional` prefix allows the location to be missing under its mechanism. However, if the application also has a bean requiring a key provided only by that file, it can still fail at binding/validation.

## 62. Exercise E: Document with on-profile

File:

```yaml
demo:
  message: "base"
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  message: "production"
```

Run without activating `prod`.

**Question:** does the second document self-activate `prod`?

**Answer:** no. `spring.config.activate.on-profile` sets the condition for applying the document; it does not activate the profile itself.

## 63. Exercise F: Working Directory

File exists:

```text
/opt/apps/config/application.yml
```

Person A runs:

```bash
cd /opt/apps
java -jar my-service.jar
```

Person B runs:

```bash
cd /home/user
java -jar /opt/apps/my-service.jar
```

**Question:** are both runs guaranteed to use the same `./config/application.yml`?

**Answer:** no. Relative paths resolve against the process's working directory. If the same file is required, use an absolute location or standardize the working directory.

## 64. Exercise G: Distinguish Three Error Types

**Scenario 1**

```yaml
spring:
  config:
    import: "file:./missing-required.yml"
```

File does not exist.

**Scenario 2**

```yaml
demo:
  timeout: not-a-duration
```

Bean expects `Duration`.

**Scenario 3**

```yaml
demo:
  retries: -3
```

Bean expects `@Min(1) int retries`.

Answer:

1. Config Data location/import error if a required location does not exist.
2. Conversion/binding error because the string cannot be converted to `Duration`.
3. Validation error when the integer is type-valid yet violates `@Min(1)`.

Config Data TRACE is an important tool for scenario 1, but does not replace reading exceptions for scenarios 2 and 3.

## 65. Exercise H: Profile Groups and Profile Count

Base file:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

Command:

```bash
java -jar app.jar --spring.profiles.active=production
```

**Question:** why might logs report multiple active profiles instead of only `production`?

**Answer:** because a group can activate additional member profiles under Spring Boot's mechanism. Inspect the actual active profile set via Environment and logs.

## 66. Exercise I: TRACE Logs Have No Line for an Imported File

You enable the Config Data TRACE logger and search for `local-settings.yml`, but find nothing.

**Question:** is that sufficient grounds to conclude the file was not loaded?

**Not yet.** Log granularity and phrasing depend on version/logger; in addition, check that you are looking at the right process, enabled logging properly, whether a source actually declared the import, and whether the effective value came from that file.

Combine logs with checks of startup configuration, PropertySources, and errors when a required resource is missing.

## 67. End-to-End Workflow: From a Config Error to Root Cause

When an operator reports "production app uses wrong configuration," you can perform:

1. **Identify the exact process:** service name, JAR/image, instance, timestamp.
2. **Confirm profiles:** read INFO logs, `Environment#getActiveProfiles()`, and check default profiles when needed.
3. **Confirm startup inputs:** CLI, JVM properties, environment variables, working directory, profile groups/includes.
4. **Enable Config Data TRACE on the right category:** `org.springframework.boot.context.config=TRACE` from an early startup source if needed.
5. **Confirm source locations:** classpath, external files, `additional-location`, `location`, `import`.
6. **Distinguish discovered sources from applied documents.**
7. **Confirm effective PropertySources and precedence order.**
8. **Cross-check a non-sensitive key:** value in Environment and configuration bean.
9. **Check binder/validation errors if the bean was not created.**
10. **Fix at the failing layer:** profile, location, precedence, key spelling, type, or constraint.
11. **Restart using the same reproducible method**, unless the system has an explicitly designed refresh mechanism.
12. **Turn off unnecessary TRACE logs and protect diagnostic evidence.**

A hard bug does not necessarily need more logs; it needs logs **at the right phase and responsibility**.

## 68. Summary

- Startup INFO logs typically show active profiles or the default profile. **No active profile does not mean `application.yml` was not loaded.**
- Active profiles, default profiles, and Config Data documents are related concepts, but **are not synonymous**.
- Enable **`logging.level.org.springframework.boot.context.config=TRACE`** to observe Config Data processing in Spring Boot versions with that logger group.
- When wanting to see early configuration preparation events, prefer passing the logger level via CLI or JVM system property **right at startup**.
- **`--debug` is not a direct substitute for Config Data TRACE.** It also serves auto-configuration/condition report investigation.
- `spring.config.activate.on-profile` only controls a document's activation condition; it does not activate a profile itself.
- `spring.config.import`, `spring.config.location`, `spring.config.additional-location`, and working directory affect finding and loading documents.
- **A loaded file does not guarantee its value wins.** CLI, system properties, environment variables, and higher-precedence sources can override it.
- You can list PropertySource names via `ConfigurableEnvironment` and read a non-sensitive key to cross-check with logs.
- Reading Config Data logs **does not replace** analyzing binding, type conversion, and Bean Validation errors.
- When viewing logs in production, limit TRACE scope, mask secrets, and secure endpoints/diagnostic output.
- A reliable workflow is **identify process → confirm profile → check Config Data → cross-check precedence → inspect bean and errors → fix the right layer**.
