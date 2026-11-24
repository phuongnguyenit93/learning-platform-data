# Preparing ApplicationArguments, Environment, and Profiles in the Spring Boot Startup Sequence

## 1. Role of the Three Components at Startup Time

When calling `SpringApplication.run(...)`, Spring Boot must know **which arguments the application was launched with**, **where configuration properties come from and what their final values are**, and **which profiles are active** before deciding how to load configuration, activate beans, and refresh `ApplicationContext`.

The three concepts are linked yet have distinct responsibilities:

| Component | Nature | Responsibility in startup | Example |
| --- | --- | --- | --- |
| `ApplicationArguments` | Object representing arguments passed into `run(String... args)` | Preserves raw source arguments; parses options and non-options so code can access them structurally | `--demo.user=Lan`, `--verbose`, `input.csv` |
| `Environment` | Central place aggregating `PropertySource` instances and Spring profile info | Provides effective properties after merging sources and applying precedence order | `spring.application.name`, `demo.message`, `server.port` |
| Active/default profiles | Set of logical environment names managed by `Environment` | Determines profile-specific config files and beans/configurations conditioned with `@Profile` | `dev`, `test`, `prod`, `default` |

**Key point:** `ApplicationArguments` answers "which arguments were passed to the application?", `Environment` answers "what value does a property currently have?", and profiles answer "which configuration branch and beans fit the environment?". A CLI parameter can be both an argument and injected into `Environment`, but the two APIs are not identical.

Example:

~~~bash
java -jar startup-demo.jar --spring.profiles.active=dev --demo.user=Lan input.csv
~~~

- `ApplicationArguments` sees two options `spring.profiles.active`, `demo.user`, and one non-option `input.csv`.
- By default, `SpringApplication` places CLI options in `--key=value` form into a high-precedence `CommandLinePropertySource`.
- `Environment` can return `dev` for `getProperty("spring.profiles.active")` and `Lan` for `getProperty("demo.user")`.
- The `dev` profile causes config data `application-dev.yaml` to be considered and eligible `@Profile("dev")` beans to be created.

Not every string in `ApplicationArguments` is a property. `input.csv` is a non-option; Spring Boot does not automatically turn it into a property named `input.csv`. A `--verbose` flag may be present with **no value** in `ApplicationArguments`; avoid assuming `getOptionValues("verbose").get(0)` is always valid.

## 2. Where This Step Fits in the Startup Sequence

Below is the **simplified logical sequence** of a typical Spring Boot run. Some internal operations may vary by version and configuration, but the major event milestones are the lifecycle contract published by Spring Boot.

~~~mermaid
flowchart TD
    A["main(String[] args)"] --> B["SpringApplication.run(args)"]
    B --> C["ApplicationStartingEvent"]
    C --> D["Initialize ApplicationArguments from args"]
    D --> E["Create and prepare Environment"]
    E --> F["Process CLI, config data, profiles, and PropertySources"]
    F --> G["ApplicationEnvironmentPreparedEvent"]
    G --> H["Create ApplicationContext, apply initializers"]
    H --> I["Load BeanDefinitions by conditions and profiles"]
    I --> J["refresh(): instantiate singletons, web server if any"]
    J --> K["ApplicationStartedEvent"]
    K --> L["ApplicationRunner / CommandLineRunner"]
    L --> M["ApplicationReadyEvent"]
~~~

The diagram only shows the conceptual flow: publishing `ApplicationEnvironmentPreparedEvent` also involves listeners, including the config data processing mechanism; it must not be assumed that **every** listener sees the exact same configuration regardless of listener ordering. Spring Boot also has `ApplicationContextInitializedEvent` after initializers run, `ApplicationPreparedEvent` before refresh, `AvailabilityChangeEvent` corresponding to liveness/readiness states, and `ApplicationFailedEvent` on failure.

### Boundaries to Remember

1. **Before `ApplicationContext` exists:** You cannot rely on an ordinary `@Bean` to catch very early events such as `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`. If you need to observe this milestone, register an appropriate listener via `SpringApplication.addListeners(...)` or a Boot-supported listener mechanism.
2. **During the Environment preparation stage:** Boot combines CLI, JVM system properties, OS environment variables, config data, and other sources; profiles are determined early enough to load profile-specific documents and evaluate bean registration conditions.
3. **Before `refresh()`:** The context has metadata/bean definitions; `@Profile` and related conditions are evaluated while processing configuration. `ApplicationArguments` can be injected as a bean once the context is prepared for bean creation.
4. **After `refresh()`:** Normal singletons have been created. `ApplicationStartedEvent` is published before runners; `ApplicationReadyEvent` is published after runners. If a runner throws an exception, the run may fail and never reach ready.
5. **Do not equate "Environment prepared" with "application ready":** At this point you cannot assume `@RestController`, connection pools, the embedded web server, or business beans are ready yet.

### Practical Dependency Relationships

~~~text
source args
  ├─> ApplicationArguments (option/non-option classification)
  └─> CLI PropertySource (default)
          │
          v
    Environment <--- config data / OS env / JVM -D / default properties
          │
          ├─> active/default profiles
          ├─> application-{profile}.yaml
          └─> @Profile / @Conditional / @ConfigurationProperties / @Value
                           │
                           v
                     BeanDefinitions → Bean instances
~~~

This is the data flow, not a claim that every step runs sequentially without overlap. Selecting profiles, loading config data, and configuring property sources interact during the early configuration phase.

## 3. How Is ApplicationArguments Created and Used?

`SpringApplication` takes the arguments passed from `main` and creates an `ApplicationArguments` implementation (typically `DefaultApplicationArguments`) to provide both raw data and parsed results.

~~~java
public static void main(String[] args) {
    SpringApplication.run(StartupDemoApplication.class, args);
}
~~~

With a custom launcher, you can also instantiate `SpringApplication` and call `run(args)`; the essential part is **passing `args` accurately** if you want Boot to see process arguments.

### APIs to Distinguish

| Method | Returns | Meaning |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | Original arguments in the order passed to `SpringApplication` |
| `getOptionNames()` | `Set<String>` | Keys of options starting with `--` |
| `containsOption("debug")` | `boolean` | Whether option `--debug` is present, even without a value |
| `getOptionValues("region")` | `List<String>` or `null` | All values for that option; `null` when the option does not appear, empty list when present without a value |
| `getNonOptionArgs()` | `List<String>` | Positional strings that do not begin like recognized CLI options |

Data example:

~~~bash
java -jar app.jar --region=vn --region=sg --dry-run invoices.csv
~~~

Key results:
- `containsOption("region")` is `true`; `getOptionValues("region")` is `[vn, sg]`.
- `containsOption("dry-run")` is `true`; `getOptionValues("dry-run")` is an empty list.
- `getOptionValues("missing")` is `null`; check for null before accessing.
- `getNonOptionArgs()` is `[invoices.csv]`.
- `getSourceArgs()` keeps all five strings after the JAR name in the exact order passed to the program.

Do not arbitrarily use `System.getProperty("region")` to read CLI arguments like `--region=vn`: Java system properties use JVM `-Dregion=vn` syntax and are handled by a different source. `--region=vn` typically becomes a Spring property in `Environment`, whereas `-Dregion=vn` must be placed before `-jar` for the JVM to recognize it.

### `ApplicationRunner` vs. `CommandLineRunner`

After the context is refreshed, Boot invokes beans implementing `ApplicationRunner` and `CommandLineRunner`. They share the role of running one-time initialization tasks, differing in their input argument types:

~~~java
@Bean
ApplicationRunner parsedRunner() {
    return args -> System.out.println(args.getNonOptionArgs());
}
~~~

~~~java
@Bean
CommandLineRunner rawRunner() {
    return args -> System.out.println(java.util.Arrays.toString(args));
}
~~~

Place the `@Bean` methods above inside a `@Configuration` class with appropriate imports, or inside the `@SpringBootApplication` class; these are standalone snippets illustrating the API signatures. When you have multiple runners, do not rely on arbitrary ordering; use `@Order` or `Ordered` if work genuinely requires order. In production, slow operations in a runner will delay `ApplicationReadyEvent` and Boot's readiness state.

You can inject `ApplicationArguments` directly into a bean constructor without reconstructing it from `System.getenv` or global variables. Still, using `ApplicationRunner` is usually clearer if the work needs to wait for dependent beans to finish initializing.

### When Disabling CLI Property Injection

~~~java
SpringApplication app = new SpringApplication(StartupDemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Here `ApplicationArguments` **still contains** the options and positional arguments, but CLI options are not automatically added to `Environment` via the default mechanism. If you pass `--spring.profiles.active=dev` while disabling CLI property injection, **do not assume the `dev` profile will be selected by that option itself**. Profiles can still be configured from another source or via the Java API. This is the clearest example showing that `ApplicationArguments` differs from `Environment`.

## 4. Environment: Aggregating Sources and Resolving Final Values

Spring Framework defines `Environment` as the access point for properties and profile information. Spring Boot adds multiple configuration sources and the config data processing mechanism.

Commonly used methods:

~~~java
String name = environment.getProperty("spring.application.name", "unknown");
String mode = environment.getProperty("demo.mode");
boolean enabled = environment.getProperty("demo.enabled", Boolean.class, false);

String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
boolean isDev = environment.acceptsProfiles(
    org.springframework.core.env.Profiles.of("dev"));
~~~

- `getProperty(...)` resolves according to `PropertySource` order and can return `null` when not found if no fallback value is given.
- The typed overload `getProperty(key, Boolean.class, defaultValue)` supports type conversion; invalid configuration can cause a conversion error.
- `getActiveProfiles()` reflects only profiles activated explicitly, programmatically, or via configuration.
- `getDefaultProfiles()` reports the fallback profiles used when no active profile is set; do not infer that `getActiveProfiles()` must contain `default`.
- `acceptsProfiles(Profiles.of("dev"))` evaluates the Environment's profile condition, taking Spring's default profile mechanism into account.

### Common Precedence Order

In a typical Spring Boot program, from lowest to highest (listing only the most essential sources):

1. Default properties set via `SpringApplication.setDefaultProperties(...)`.
2. Config data such as `application.yaml`, `application-dev.yaml`, and files outside the JAR.
3. OS environment variables, such as `DEMO_MESSAGE`.
4. Java system properties from `-Ddemo.message=...`.
5. Command-line options `--demo.message=...`, if CLI property injection is enabled.

The full order also includes `@PropertySource`, `SPRING_APPLICATION_JSON`, JNDI, servlet parameters, test properties, DevTools, and extension mechanisms. Check the exact Boot version when specialized sources define the same key. Never conclude that "YAML always has lower precedence than a file outside the JAR" without considering config data location, location groups, profiles, and higher-priority sources.

**Timing note:** `@PropertySource` on `@Configuration` is added while the context is refreshing, which is too late for certain properties read very early such as `logging.*` and `spring.main.*`. Therefore, do not use it as a reliable way to alter initial bootstrap behavior.

### Differences Between CLI, JVM, and OS Env

~~~bash
# Application arguments: SpringApplication receives --demo.message=CLI
java -jar app.jar --demo.message=CLI

# JVM system property: JVM receives -D before -jar
java -Ddemo.message=JVM -jar app.jar

# On a shell supporting inline env before the command, an environment variable can be:
DEMO_MESSAGE=ENV java -jar app.jar
~~~

The third example is for Unix/Linux shells; in PowerShell set `$env:DEMO_MESSAGE = 'ENV'` before running. Most operating systems disallow dots in environment variable names, so relaxed binding supports corresponding underscore forms. However, mapping dashes/underscores in **application-defined keys** must follow canonical property naming rules. For multiple grouped properties, `@ConfigurationProperties` is more suitable than a series of `@Value` annotations.

## 5. Loading Config Data and Selecting Profiles

Boot looks for `application.properties`/`application.yaml` and configuration files on the classpath, working directory, external `config/` directory, additional declared locations, and imported sources if any. Profile-specific files are typically named `application-dev.yaml` or `application-prod.properties`. **A profile-specific file is only applied when the corresponding profile is active**, except in cases intentionally handled by config/import rules.

Example:

**`src/main/resources/application.yaml`**

~~~yaml
spring:
  application:
    name: startup-demo

demo:
  message: "Default hello"
~~~

**`src/main/resources/application-dev.yaml`**

~~~yaml
demo:
  message: "Hello from dev"
~~~

Without the `dev` profile, `demo.message` from the common file is `Default hello`. When running with `--spring.profiles.active=dev`, the profile-specific file overrides the corresponding key, so the effective value in this example is `Hello from dev`. If the CLI adds `--demo.message=CLI`, that value in turn overrides the config data value.

### Active Profiles and Default Profile

- `spring.profiles.active=dev` sets the `dev` profile as active.
- When no active profile is set, Spring uses the default profile, named `default` by default; the default list can be changed with `spring.profiles.default`.
- `application-default.yaml` can be applied when no active profile is set.
- `spring.profiles.default=none` is Boot's supported way to disable the `default` profile fallback.
- `@Profile("dev")` marks a bean or configuration to exist only when the profile expression matches. `@Profile("!prod")` is a negated condition, not a way to treat all other environments as identical.

**Important boundary:** `Environment.getActiveProfiles()` can return an empty array even while Spring is using the default profile. The log message "No active profile set, falling back to ... default" does not mean `getActiveProfiles()` must return `["default"]`.

### Which Mechanisms Combine Profiles?

There are three common mechanisms:

1. `spring.profiles.active`: Selects one or more profiles, e.g., `dev,metrics`.
2. `spring.profiles.include`: Appends profiles onto the active list; it is not simply a replacement for `active`.
3. `spring.profiles.group.production`: Associates a logical profile name with member profiles, e.g., `production` additionally activates `proddb`, `prodmq`.

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

When `production` is active, Boot can additionally activate `proddb` and `prodmq` to load their respective configuration branches. Do not confuse a profile group name with a profile created programmatically in Java: groups are configuration processed by Boot in config data.

**Placement rule:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group` must reside in **profile-independent** configuration documents. Do not place these profile-control keys inside `application-dev.yaml` or a YAML document activated by `spring.config.activate.on-profile`. Doing so can cause `InvalidConfigDataPropertyException` or related configuration errors.

### Multiple Active Profiles Together

~~~bash
java -jar app.jar --spring.profiles.active=dev,metrics
~~~

Both `application-dev.yaml` and `application-metrics.yaml` may be evaluated. If they define the same property, normally the profile listed later overrides the earlier one **within the same config location group**. With multiple directories or complex location group configurations, actual precedence also depends on loading rules; do not infer the result solely from alphabetical order in filenames. Likewise, `@Profile({"dev", "metrics"})` on a bean expresses an **OR** condition between the two names, not AND; if you need a compound condition, use supported profile expressions such as `@Profile("dev & metrics")`.

## 6. Passing Profile Configuration via the `SpringApplication` API

You can add profiles programmatically before `run(...)`:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;

public final class AdditionalProfileLauncher {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(StartupDemoApplication.class);
        app.setAdditionalProfiles("audit");
        app.run(args);
    }
}
~~~

This is an **alternative launcher** used with the `StartupDemoApplication` class in the complete example below. `setAdditionalProfiles("audit")` adds the `audit` profile to those already selected via configuration/CLI; it does not remove profiles from `spring.profiles.active`.

For default application configuration:

~~~java
SpringApplication app = new SpringApplication(StartupDemoApplication.class);
app.setDefaultProperties(java.util.Map.of(
    "spring.application.name", "startup-demo",
    "demo.message", "Hello from Java defaults"));
app.run(args);
~~~

Default properties have low precedence. If `application.yaml` contains `demo.message`, the YAML value normally wins; if the CLI provides `--demo.message=...`, the CLI beats both. The snippets above are separate startup options; when implementing, choose **one** appropriate main launcher.

### When Do You Need to Intervene in Environment Early?

If you must supply an additional `PropertySource` **before bean creation**, Spring Boot provides the `EnvironmentPostProcessor` hook or supported bootstrap/config data mechanisms. Adding a property to Environment inside a `@Service` constructor, `@PostConstruct`, or `ApplicationRunner` is **too late** to reliably affect:
- profiles used to load initial config data;
- `@Profile` or `@ConditionalOnProperty` conditions already evaluated;
- early configuration of logging, `spring.main.*`, and application initialization.

`ApplicationContextInitializer` is invoked before loading bean definitions, so it can customize the context early, yet it still differs from profile selection and config data loading during the Environment phase. Pick a hook according to **when the data must be available**, and avoid assuming that putting a property into Environment at any arbitrary time will re-evaluate all configuration.

## 7. Runnable Example: Observing All Three Components in One Application

Create a Maven project via Spring Initializr with Java 17+, group `com.example`, artifact `startup-demo`, package `com.example.startup`, and the **Spring Boot Starter** dependency (the foundational starter; Web or Actuator is not required). Use a Spring Boot version compatible with the Java version on your machine, e.g., the 3.5.x line. The four files below create a command-line application displaying parsed arguments, effective properties, active profiles, and the presence of a profile-specific bean.

**`src/main/java/com/example/startup/StartupDemoApplication.java`**

~~~java
package com.example.startup;

import java.util.Arrays;
import java.util.List;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectStartup(
            Environment environment,
            ObjectProvider<DevOnlyMarker> devMarker) {
        return args -> {
            List<String> names = args.getOptionValues("demo.user");
            String user = (names == null || names.isEmpty())
                    ? "unknown" : names.get(0);

            System.out.println("user=" + user);
            System.out.println("inputFiles=" + args.getNonOptionArgs());
            System.out.println("activeProfiles="
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("message="
                    + environment.getProperty("demo.message", "missing"));
            System.out.println("devBeanPresent="
                    + (devMarker.getIfAvailable() != null));
            System.out.println("verboseFlag="
                    + args.containsOption("demo.verbose"));
        };
    }
}
~~~

**`src/main/java/com/example/startup/DevOnlyMarker.java`**

~~~java
package com.example.startup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevOnlyMarker {
}
~~~

**`src/main/resources/application.yaml`**

~~~yaml
spring:
  application:
    name: startup-demo

demo:
  message: "Default hello"
~~~

**`src/main/resources/application-dev.yaml`**

~~~yaml
demo:
  message: "Hello from dev"
~~~

Explanation: `ApplicationRunner` is invoked after refresh and receives `ApplicationArguments` directly in its lambda parameter. `ObjectProvider<DevOnlyMarker>` lets you check for an optional bean without requiring the bean to exist in other profiles. Because the bean is annotated with `@Profile("dev")`, it is only instantiated when the `dev` profile matches. `Environment` provides the final property values and active profile list.

### Building and Running

In the Maven directory containing the `pom.xml` generated by Spring Initializr:

~~~bash
mvn -q -DskipTests package
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --demo.user=Lan \
  --demo.verbose \
  input.csv
~~~

The `\` line continuation is Unix/Linux shell syntax; you can type the entire `java -jar ...` command on **one line** in PowerShell/cmd. The JAR name illustrates the default artifact version; if you changed `version` or the artifact name in `pom.xml`, use the actual JAR name.

When the configuration sources consist only of the four files above and the arguments match the command, the lines printed by `inspectStartup` are:

~~~text
user=Lan
inputFiles=[input.csv]
activeProfiles=[dev]
message=Hello from dev
devBeanPresent=true
verboseFlag=true
~~~

Boot also prints other startup log lines; the output block above excerpts only **the runner's lines**, without claiming that the entire stdout consists solely of these six lines.

Now run without activating `dev`:

~~~bash
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --demo.user=Minh \
  report.csv
~~~

The runner's lines:

~~~text
user=Minh
inputFiles=[report.csv]
activeProfiles=[]
message=Default hello
devBeanPresent=false
verboseFlag=false
~~~

**Explaining the empty value:** `activeProfiles=[]` indicates there is no explicit active profile; unless configured otherwise, the default profile `default` still applies via fallback. Consequently, `application-dev.yaml` and the `DevOnlyMarker` bean are not activated.

To demonstrate precedence order, run again with:

~~~bash
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --demo.user=Lan \
  --demo.message="CLI priority" \
  input.csv
~~~

This time the runner's `message=...` line becomes:

~~~text
message=CLI priority
~~~

Even though `application-dev.yaml` is still evaluated, the CLI property has higher precedence than config data for this key under Boot's default configuration.

## 8. Another Example of Timing Differences: Early Event and Late Runner

When you need to observe an early event, you can register a listener directly on `SpringApplication` before running. The snippet below is a standalone launcher reusing the application from section 7:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;

public final class EventLauncher {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupDemoApplication.class);

        app.addListeners(event -> {
            if (event instanceof ApplicationEnvironmentPreparedEvent) {
                System.out.println("EVENT=environment-prepared");
            }
        });

        app.run(args);
    }
}
~~~

`ApplicationEnvironmentPreparedEvent` is published before `ApplicationContext` is created. The example only prints the event milestone to avoid depending on internal listener ordering; do not read profile values inside an arbitrary listener and treat them as the final snapshot of the **entire** config data processing phase. With `ApplicationRunner` in the previous example, by contrast, config has been processed and the context has refreshed; that is a more appropriate time to read effective properties for runtime work.

This is also why you cannot create a `@Component` listening for `ApplicationStartingEvent` and assume Spring Boot can invoke it before the context exists. If you need ultra-early events, register listeners via `SpringApplication` or Boot metadata.

## 9. Common Errors and How to Diagnose Them

### "I passed `--spring.profiles.active=dev`, but the `@Profile("dev")` bean is missing"

Check whether arguments **actually reach `run(args)`**. A launcher calling `SpringApplication.run(MyApp.class)` without passing `args` drops command-line arguments. Check whether `setAddCommandLineProperties(false)` was called, because then `ApplicationArguments` still holds the option while `Environment` does not automatically receive CLI properties. Next, check the final profile value from higher-precedence sources, package scan scope, and where `@Profile` is declared.

### "`getActiveProfiles()` returns an empty array, so is the default profile working?"

It may **well be**. When no active profile is set, `Environment` uses the default profile. Inspect `getDefaultProfiles()` or `acceptsProfiles(Profiles.of("default"))` instead of treating `getActiveProfiles()` as the entire profile mechanism.

### "`getOptionValues(...)` throws `NullPointerException`"

The method returns `null` if the option name is absent. If the option is only a flag like `--dry-run`, the result is an **empty** list. Check both cases before calling `get(0)`. Do not assume an absent option and a valueless option have the same representation.

### "`application-dev.yaml` is not being loaded"

Check the profile name, filename, classpath/location, `spring.config.name` or `spring.config.location` settings, and whether the profile is active at the right moment during config data loading. `spring.config.location` **replaces** default locations, whereas `spring.config.additional-location` **adds** locations; both must be supplied early enough, typically via CLI, system properties, or OS env. You can use `optional:` if a location is allowed to be missing; otherwise, Boot may stop with `ConfigDataLocationNotFoundException`.

### "I put `spring.profiles.active` in `application-prod.yaml` and got an error"

`spring.profiles.active` and similar profile-control keys must live in **non-profile-specific** documents. Move them to `application.yaml` or specify them via environment/CLI, and put prod-specific properties in `application-prod.yaml`. Do not activate a profile inside the very document that is only read when that profile is already active.

### "I added `@PropertySource`, yet `logging.*` or `spring.main.*` did not change"

`@PropertySource` is normally processed during context refresh, **later** than when Boot reads several bootstrap settings. Move keys needed early into config data or an appropriate Environment source before `run`. This is a **timing** error rather than simply a property-name issue.

### "Running on another machine with the same JAR produces different properties"

Check environment variables, Java `-D` flags, CLI options, active profiles, files outside the JAR, working directory, and config data imports. Boot intentionally supports externalized configuration: the same artifact can behave differently across environments without being a bug.

### "Runners run before the app is ready"

Correct: `ApplicationRunner`/`CommandLineRunner` run **after `ApplicationStartedEvent` but before `ApplicationReadyEvent`**. If a runner performs long initialization work, readiness is delayed. Do not move heavy work into an Environment preparation listener for that reason; choose the right timing and dedicated background/initialization mechanism.

### "Passwords or tokens leak when logging arguments"

`ApplicationArguments.getSourceArgs()` may contain secrets if an operator passes them on the CLI. Do not print full `args`, `Environment`, or `PropertySources` to production logs. Use proper secret management mechanisms and restrict configuration/Actuator exposure; debug messages should include only non-sensitive fields.

## 10. Comparison Table: Which Stage Does Each Input Change Affect?

| Action | ApplicationArguments | Environment / profiles | Effect in later steps |
| --- | --- | --- | --- |
| Pass `--demo.user=Lan` | Contains option `demo.user` | CLI property added by default | Beans can read `demo.user` when created |
| Pass `file.csv` | Contains non-option `file.csv` | Does not automatically create property `file.csv` | Runners can process the path |
| Set OS env `DEMO_MESSAGE=...` | Absent unless matching CLI option exists | PropertySource from OS environment | Configured value may be overridden |
| Pass `-Ddemo.message=JVM` | Not part of `ApplicationArguments` | Java system property | Overrides config data per precedence |
| Run `--spring.profiles.active=dev` | Contains CLI option | Usually activates `dev` (if CLI properties enabled) | Loads `dev` config and creates `@Profile("dev")` beans |
| Call `setAdditionalProfiles("audit")` | Does not add source arguments | Appends profile via Java API | Can load config/beans for `audit` |
| Set `spring.profiles.group.production` | Does not create an option | Profile group processed in config data | Additionally activates member profiles |
| Add property inside `ApplicationRunner` | Argument data unchanged | Can add runtime property | Too late to reliably re-evaluate already chosen beans/profiles |
| Call `setAddCommandLineProperties(false)` | Still has raw/parsed args | Does not automatically add CLI PropertySource | `--spring.profiles.active` no longer drives Environment by default |

## 11. Implementation Checklist

1. **Preserve `args`** when calling `SpringApplication.run(...)` if you want to pass CLI options into the application.
2. **Choose the right API:** use `ApplicationArguments` for raw/parsed startup args, `Environment` or `@ConfigurationProperties` for effective config; use `ApplicationRunner` when post-refresh work is needed.
3. **Determine profiles early:** use `spring.profiles.active` via valid config, CLI/OS env, or `SpringApplication.setAdditionalProfiles(...)` before `run`.
4. **Put profile keys in the right file:** do not declare `spring.profiles.active`/`default`/`include`/`group` inside profile-specific documents.
5. **Know precedence order** and actual overriding sources before concluding a property does not work.
6. **Choose hooks by timing:** bootstrap/config data needs early sources; `@PropertySource`, `@PostConstruct`, and runners cannot substitute for the config data loading phase.
7. **Diagnose with evidence:** selectively print active/default profiles and non-sensitive properties, inspect config data logs when needed; never dump secrets.
8. **Test both directions:** run at least once with no active profile and once with `dev` to see the difference in profile files and `@Profile` beans.

### Self-Check Questions

**1.** Passing `--mode=fast report.csv`, what does `getNonOptionArgs()` contain? → `[report.csv]`, while `mode` is an option.

**2.** How does `--dry-run` differ from `--dry-run=true` in `getOptionValues("dry-run")`? → The first produces an empty list, while the second produces a list containing `"true"`.

**3.** Why doesn't `getActiveProfiles()=[]` prove that the default profile has no effect? → Spring uses `getDefaultProfiles()` as fallback when no active profile is set.

**4.** When the same key appears in YAML and CLI, which source wins without custom ordering? → The CLI option property usually overrides YAML.

**5.** Should you modify profiles from `ApplicationRunner` to change registered `@Profile` beans? → No; runners execute after refresh, too late to rerun initial profile-based bean selection.

**6.** What is the difference between `ApplicationEnvironmentPreparedEvent` and `ApplicationReadyEvent`? → The former occurs during the Environment setup phase before the context exists; the latter occurs after the context has refreshed and runners have completed successfully.

## 12. Official Documentation for Version Reference

- [Spring Boot — SpringApplication, Application Events, Application Arguments, and Runners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — ApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html)
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html)
- [Spring Framework — Environment and Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)

Documentation for other versions may change internal ordering, additional API names, or profile policies. When maintaining an application, cross-check against the exact Spring Boot and Spring Framework versions in your project's dependency tree.