# Disabling Command-Line Configuration Properties While Keeping ApplicationArguments

By default, Spring Boot processes arguments of the form `--property.name=value` for **two distinct purposes**:

1. Adding them to `Environment` as a `CommandLinePropertySource` so they can participate in externalized configuration.
2. Preserving the arguments of the `SpringApplication.run(args)` call so application code can read them via `ApplicationArguments`.

These two purposes **do not necessarily depend on each other**. If you do not want operators to alter Spring configuration purely via `--key=value` arguments, you can call **`SpringApplication.setAddCommandLineProperties(false)`** before `run(args)`. Spring Boot then skips adding the default command-line property source to `Environment`, **yet `ApplicationArguments` still exists**, still holding raw arguments, option arguments, and non-option arguments.

This design fits applications that need to accept business commands like `--job=import` or `--dry-run` without allowing those commands to accidentally override general settings such as `server.port`, `spring.profiles.active`, or `logging.level.root`.

This article uses **Java 17+ and Spring Boot 3.3.x**. This API exists in other Spring Boot versions too, though the examples below target Boot 3.3.

## 1. Two argument-processing streams — the core idea

Suppose an application runs with:

~~~text
--demo.mode=from-cli --dry-run input.csv
~~~

Under Spring Boot's default configuration:

- `--demo.mode=from-cli` is both parsed as option `demo.mode` in `ApplicationArguments` and eligible to become property `demo.mode=from-cli` in `Environment`.
- `--dry-run` is a named option without a value.
- `input.csv` is a non-option (positional argument), and does not automatically become a property named `input.csv`.

Now enable the mode **without adding command-line properties**:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

This is illustrative code requiring a configuration class `MyApplication` and corresponding imports. `setAddCommandLineProperties(false)` must be called on a **`SpringApplication` instance before running**, because the static call `SpringApplication.run(MyApplication.class, args)` provides no place to customize this instance.

After disabling it:

~~~text
                          String[] args
                                |
                   +------------+-------------+
                   |                          |
             ApplicationArguments       Spring Environment
             (still parses args)        (does not auto-add
                   |                     commandLineArgs)
             --demo.mode=...                  |
             --dry-run                  application.properties
             input.csv                  env vars / -D / ...
~~~

What gets disabled is **one channel feeding arguments into configuration**, not JVM argument reception or the parsing functionality of `ApplicationArguments`.

## 2. What does `setAddCommandLineProperties(false)` change?

| Behavior | Default (`true`) | When set to `false` |
|---|---|---|
| `ApplicationArguments.getSourceArgs()` | Keeps raw args | **Still keeps** raw args |
| `ApplicationArguments.containsOption("job")` | Can read options | **Still readable** |
| `ApplicationArguments.getOptionValues("job")` | Can read values | **Still readable** |
| `ApplicationArguments.getNonOptionArgs()` | Can read positional args | **Still readable** |
| `ApplicationRunner.run(ApplicationArguments)` | Receives args | **Still receives args** |
| `CommandLineRunner.run(String...)` | Receives raw args | **Still receives raw args** |
| `Environment.getProperty("demo.mode")` | Can read CLI value, usually high priority | **Does not read from default command-line property source** |
| `@Value("${demo.mode}")` | Can be overridden by CLI | Not overridden **by default CLI source** |
| `@ConfigurationProperties` | Can bind property from CLI | Does not bind from default CLI source |
| `application.properties`/YAML files | Loaded normally | **Still loaded** |
| OS environment variables and JVM `-D` | Separate config sources | **Still active** |

Note on the `Environment.getProperty(...)` row: setting `false` **does not force the property to be `null`**. If the same property name is declared in a file, OS environment, Java system properties, default properties, or a property source manually added by the application, that value can still be returned. What is removed is **the default override path from `--key=value`**.

Nor should this be called a feature that "disables all command-line configuration on the machine". For example, `-Ddemo.mode=from-jvm` is a **JVM system property**, a different source from application argument `--demo.mode=...`.

## 3. Runnable example: Environment reads from file, ApplicationArguments reads from CLI

Goal is to verify three things:

1. Passing `--demo.mode=from-cli`, yet `Environment` still uses `demo.mode=from-file` from `application.properties`.
2. `ApplicationArguments` still sees option `demo.mode`, flag `dry-run`, and non-option `input.csv`.
3. `@Value` also reads from normal configuration sources without taking the CLI override.

Create a Spring Boot 3.3.x, Java 17+ project with the `spring-boot-starter` dependency.

### Complete Java file

Place `src/main/java/com/example/arguments/NoCliPropertiesApplication.java`:

~~~java
package com.example.arguments;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class NoCliPropertiesApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(NoCliPropertiesApplication.class);

        // Disable adding commandLineArgs to Spring Environment.
        // Do NOT disable parsing and injecting ApplicationArguments.
        app.setAddCommandLineProperties(false);

        // No HTTP server needed for this console example.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Close context after runner finishes.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // No additional processing.
        }
    }

    @Bean
    ApplicationRunner inspectArguments(
            Environment environment,
            @Value("${demo.mode}") String configuredMode,
            ApplicationArguments injectedArguments) {

        return runnerArguments -> {
            System.out.println(
                    "Environment demo.mode = "
                            + environment.getProperty("demo.mode"));
            System.out.println(
                    "@Value demo.mode = " + configuredMode);

            List<String> names =
                    new ArrayList<>(runnerArguments.getOptionNames());
            Collections.sort(names);
            System.out.println("Option names = " + names);

            System.out.println(
                    "CLI demo.mode values = "
                            + runnerArguments.getOptionValues("demo.mode"));
            System.out.println(
                    "CLI dry-run present = "
                            + runnerArguments.containsOption("dry-run"));
            System.out.println(
                    "CLI dry-run values = "
                            + runnerArguments.getOptionValues("dry-run"));
            System.out.println(
                    "CLI absent values = "
                            + runnerArguments.getOptionValues("absent"));
            System.out.println(
                    "Non-option args = "
                            + runnerArguments.getNonOptionArgs());
            System.out.println(
                    "Raw args = "
                            + Arrays.toString(
                                    injectedArguments.getSourceArgs()));
        };
    }
}
~~~

Here `ApplicationArguments` is accessed in two places:

- The `ApplicationArguments injectedArguments` parameter of the `@Bean` factory method is injected by Spring from the context.
- The `runnerArguments` parameter of `ApplicationRunner.run(...)` is passed by Boot when invoking the runner.

Both can be used to read arguments. There is no need to construct `DefaultApplicationArguments` yourself or write a custom parser for standard options.

### Configuration file

Place `src/main/resources/application.properties`:

~~~properties
demo.mode=from-file
logging.level.root=INFO
~~~

Do not put `demo.mode=from-cli` into the config file. That value will be passed as a CLI argument to verify separation between the two sources.

### Running the application

If using Gradle Wrapper in a project configured with the Spring Boot plugin:

~~~bash
./gradlew bootRun --args='--demo.mode=from-cli --dry-run input.csv'
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=from-cli --dry-run input.csv"
~~~

If using Maven Wrapper and the Spring Boot Maven plugin configured with the main class:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--demo.mode=from-cli --dry-run input.csv"
~~~

The commands above only apply inside a **Spring Boot project with all required dependencies and plugins**. `NoCliPropertiesApplication.java` will not compile directly via `javac` if Spring Boot/Spring Framework are missing from the classpath.

### Output to observe

Ignoring Spring Boot startup logs, the lines **printed by the runner in the example** are:

~~~text
Environment demo.mode = from-file
@Value demo.mode = from-file
Option names = [demo.mode, dry-run]
CLI demo.mode values = [from-cli]
CLI dry-run present = true
CLI dry-run values = []
CLI absent values = null
Non-option args = [input.csv]
Raw args = [--demo.mode=from-cli, --dry-run, input.csv]
~~~

The order of `Option names` here is deterministic because the code **explicitly sorts** the list before printing. Do not rely on direct iteration order of `getOptionNames()` for output or business logic.

**Decisive point:** `Environment` and `@Value` both print `from-file`, yet `ApplicationArguments.getOptionValues("demo.mode")` still contains `from-cli`. Disabling the command-line property source **does not lose input data**.

The `Raw args` line also demonstrates that arguments preserve their order when passed from `String[] args` into `SpringApplication.run(args)`.

## 4. ApplicationArguments API: raw, option, and non-option

`org.springframework.boot.ApplicationArguments` is the interface providing both the raw argument array and the parsed form.

| API | Return Type | Meaning |
|---|---|---|
| `getSourceArgs()` | `String[]` | Raw arguments passed to SpringApplication. |
| `getOptionNames()` | `Set<String>` | Names of `--name` or `--name=value` options. |
| `containsOption(String name)` | `boolean` | Whether an option with this name exists. |
| `getOptionValues(String name)` | `List<String>` or `null` | Parsed values of an option. |
| `getNonOptionArgs()` | `List<String>` | Arguments not in option form, such as filenames. |

A common source of bugs is **the three states of `getOptionValues(...)`**:

~~~text
Option --foo absent            -> null
Option --foo present           -> []
Option --foo=bar present       -> [bar]
--foo=bar --foo=baz present    -> [bar, baz]
~~~

Therefore, check before reading the first element:

~~~java
List<String> values = args.getOptionValues("job");
if (values == null) {
    throw new IllegalArgumentException("Missing --job option");
}
if (values.size() != 1 || values.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Require exactly one --job=<name> option");
}
String job = values.get(0);
~~~

This is an illustrative snippet using a variable `args` of type `ApplicationArguments` inside an existing method, not a standalone Java file. Checking list size distinguishes an absent option, a valueless flag, a single valid value, and multiple repeated values.

### Write option syntax clearly

With `ApplicationArguments`, the valued form should be written:

~~~text
--job=import
~~~

Do not assume:

~~~text
--job import
~~~

is equivalent. Spring's command-line parser separates option `--job` and non-option `import` when passed as two separate tokens without `=`.

A flag like `--dry-run` can be checked via `containsOption("dry-run")`; for valued options, inspect `getOptionValues(...)` and validate business data.

When passing arguments from a shell, watch spaces and quotes. For example:

~~~bash
java -jar app.jar --job=import "--input=/data/monthly report.csv"
~~~

In the form above, the `--input=...` part is kept as **one token** by the shell. Without quotes, a path with spaces can split into multiple arguments.

## 5. Why is ApplicationArguments still available without CommandLinePropertySource?

`SpringApplication` still receives the original `String[] args` in `run(args)` and has its own mechanism to construct `ApplicationArguments` for the lifecycle and runners. Registering `ApplicationArguments` as a bean in the context, as well as passing it to `ApplicationRunner`, is **a separate mechanism** from adding CLI options to `Environment`'s property sources.

Two uses of the same input data:

~~~text
                            run(String[] args)
                                  |
                       Parse application args
                                  |
                 +----------------+------------------+
                 |                                   |
         ApplicationArguments                  Add to Environment?
                 |                                   |
       Injection / ApplicationRunner          setAddCommandLineProperties
                 |                              true / false
           Still works                               |
                                  true: add CLI source
                                  false: do not add CLI source
~~~

When set to `false`, Boot does not clear `String[] args`, does not disable `ApplicationRunner`, and does not disable `ApplicationArguments` injection.

### Why not just remove `commandLineArgs` after the context starts?

Configuration from `Environment` can be consumed **during bootstrap** to select active profiles, load config data, configure logging, set web server ports, and bind beans. If you wait until the context finishes starting before removing the property source, those decisions may **have already been applied**.

Therefore, to disable adding CLI options to `Environment` as designed, set:

~~~java
app.setAddCommandLineProperties(false);
~~~

**before** `app.run(args)`. Do not treat removing the property source after refresh as equivalent or always safe.

## 6. Clear comparison of Environment, @Value, @ConfigurationProperties, and arguments

Suppose you have:

~~~properties
# application.properties
demo.mode=from-file
~~~

And run:

~~~text
--demo.mode=from-cli
~~~

Results under the normal mechanism:

| Read approach | With CLI property source enabled | With CLI property source disabled |
|---|---|---|
| `Environment.getProperty("demo.mode")` | `from-cli` when no higher-priority source exists | `from-file` if no other source overrides |
| `@Value("${demo.mode}")` | `from-cli` under similar conditions | `from-file` under similar conditions |
| `@ConfigurationProperties(prefix="demo")` | Can bind `mode=from-cli` | Does not bind from default CLI source; uses remaining sources |
| `ApplicationArguments.getOptionValues("demo.mode")` | `[from-cli]` | **`[from-cli]`** |
| `ApplicationArguments.getSourceArgs()` | Contains token `--demo.mode=from-cli` | **Still contains that token** |

This table assumes no higher-precedence system property, environment variable, test property source, or programmatic configuration sets `demo.mode`. This is a **model explaining the mechanism**, not a guarantee that values cannot change in other environments.

`@ConfigurationProperties` reads from the configuration properties system built on `Environment` sources and the binder; it **does not automatically pull raw arguments from `ApplicationArguments`** just because an option shares the same name.

If an option's value represents a **business command** parameter, read and validate it via `ApplicationArguments`. If the value is **service configuration** (database, server, logging, endpoints), use official configuration sources such as config files, env vars, or system properties per application policy.

## 7. Impact on familiar Spring Boot options

Consider several command-line options commonly added to `Environment`:

| Argument passed to `run(args)` | With CLI source disabled | Where it can still be read |
|---|---|---|
| `--server.port=9090` | Does not auto-override `server.port` from command-line source | `ApplicationArguments.getOptionValues("server.port")` |
| `--spring.profiles.active=dev` | Does not auto-activate `dev` profile from command-line source | `ApplicationArguments.getOptionValues("spring.profiles.active")` |
| `--logging.level.root=DEBUG` | Does not auto-change root logging from command-line source | `ApplicationArguments.getOptionValues("logging.level.root")` |
| `--spring.main.banner-mode=off` | Does not auto-change banner mode via command-line property source | `ApplicationArguments.getOptionValues("spring.main.banner-mode")` |
| `--job=import` | Does not automatically become `job` config property | `ApplicationArguments.getOptionValues("job")` |
| `--dry-run` | Does not automatically become `dry-run` config property | `ApplicationArguments.containsOption("dry-run")` |

A few notes:

- Disabling the command-line property source does not block **another configuration path** such as `SPRING_PROFILES_ACTIVE` or `-Dspring.profiles.active=dev`. For instance, if the `dev` profile is enabled by an environment variable, it still takes effect.
- Code you write yourself can read `ApplicationArguments` and **explicitly** alter application state/configuration. Setting `false` does not stop such custom logic.
- Avoid putting parameters that Spring Boot needs during **config data loading** into a CLI option expecting them to work with the CLI source disabled. For example, `--spring.config.location=...` will not work via the default CLI configuration path.
- If the application needs to switch profiles or config locations, choose a channel intended for it, such as environment variables or JVM system properties, and check effective precedence order.

This is also why arguments should be separated by role: **business commands** differ from **runtime configuration**.

## 8. Distinguishing application arguments from JVM system properties

The easiest commands to confuse are:

~~~bash
java -Ddemo.mode=from-jvm -jar app.jar
java -jar app.jar --demo.mode=from-cli
~~~

In the first command, `-Ddemo.mode=from-jvm` is a **JVM system property**, processed by Java and placed in `System.getProperties()`. It is not a token in `main`'s `String[] args`.

In the second command, `--demo.mode=from-cli` is an **application argument**. It belongs to `String[] args` and appears in `ApplicationArguments`.

When using `setAddCommandLineProperties(false)`:

- The first command can still set `demo.mode=from-jvm` in `Environment`.
- The second command does not put `demo.mode=from-cli` into `Environment` via the default command-line source.
- CLI tokens can still be retrieved from `ApplicationArguments`; JVM `-D` flags do not automatically appear there.

**Do not treat `setAddCommandLineProperties(false)` as a comprehensive security policy** for configuration. It only disables one configuration source; operators can still control files, environment variables, system properties, container settings, or parameters interpreted by the app itself.

## 9. Using ApplicationRunner to handle business CLIs

When a console application performs import/export or batch jobs, organize options under an **explicit command contract**:

~~~text
--job=import --input=/data/orders.csv --dry-run
~~~

The runner can:

1. Verify there is exactly one `--job=<name>` and one `--input=<path>`.
2. Verify `job` belongs to the supported set, such as `import`, `export`.
3. Interpret `--dry-run` as preview mode.
4. Keep service environment settings from `application.properties`, OS environment, or system properties.
5. Return meaningful errors when values are missing, options are invalidly repeated, or paths do not exist.

Helper example to extract exactly **one** value:

~~~java
static String requireOneOption(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);
    if (values == null || values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected exactly one --" + name + "=<value>");
    }

    String value = values.get(0);
    if (value.isBlank()) {
        throw new IllegalArgumentException(
                "--" + name + " must not be blank");
    }
    return value;
}
~~~

This is an **illustrative method to place inside a class importing `ApplicationArguments` and `java.util.List`**, not a standalone file. The helper does not run imports, validate file contents, or open transactions; its purpose is to model input validation.

In the runner, you can use:

~~~java
String job = requireOneOption(args, "job");
boolean dryRun = args.containsOption("dry-run");
~~~

These two lines are illustrative code when `args` is an `ApplicationArguments`. When you want to allow multiple repeated values for an option, do not use `requireOneOption`; iterate `getOptionValues(...)` with clear processing rules.

### When does the runner execute?

`ApplicationRunner` is invoked by Spring Boot **after application context refresh** and before `ApplicationReadyEvent` / normal completion of `SpringApplication.run(...)`. This suits startup/batch tasks that need injected beans.

However, `ApplicationRunner` does not fully replace a dedicated command parser when command syntax grows complex: subcommands, positional argument groups, interdependent validation, help/usage text, completion, or exit codes. For large CLIs, consider an appropriate CLI library while keeping the boundary between runtime configuration and business args clear.

## 10. Comparing with CommandLineRunner and constructor injection

Both `ApplicationRunner` and `CommandLineRunner` are Spring Boot startup callbacks:

| Approach | Data received | When convenient |
|---|---|---|
| `ApplicationRunner.run(ApplicationArguments args)` | Arguments classified into options and non-options, plus raw args | Need to parse `--job=import`, `--dry-run`, or positional args. |
| `CommandLineRunner.run(String... args)` | Raw argument array | Need custom syntax parsing or forwarding raw args to another library. |
| Constructor injection of `ApplicationArguments` | Bean/class receives an arguments object | A service needs to know options as soon as it is created. |

`CommandLineRunner` example:

~~~java
@Bean
CommandLineRunner rawRunner() {
    return sourceArgs -> {
        System.out.println(Arrays.toString(sourceArgs));
    };
}
~~~

This is an illustrative snippet placed in a configuration class importing `CommandLineRunner` and `Arrays`. Adding it directly to the section 3 program would introduce a **second runner** and extra output, so keep a single runner when verifying the main program's stdout.

Constructor injection:

~~~java
@Component
public class JobOptions {

    private final ApplicationArguments args;

    public JobOptions(ApplicationArguments args) {
        this.args = args;
    }

    public boolean isDryRun() {
        return args.containsOption("dry-run");
    }
}
~~~

This is a supplementary class example requiring imports for `org.springframework.boot.ApplicationArguments` and `org.springframework.stereotype.Component`. Both approaches work after disabling the command-line property source: the `ApplicationArguments` object still exists in the context; only property resolution via `Environment` changes.

In larger applications, consider whether every service should read `ApplicationArguments` directly or whether it is better to parse once at the entry point and pass a **validated** business configuration object to the rest of the app. The latter makes services easier to test and avoids coupling business logic directly to Spring Boot.

## 11. Before-and-after comparison with a single change

In the section 3 program, change:

~~~java
app.setAddCommandLineProperties(false);
~~~

to:

~~~java
app.setAddCommandLineProperties(true);
~~~

or remove the call (default is `true`). Keep `application.properties` and the run command unchanged:

~~~text
--demo.mode=from-cli --dry-run input.csv
~~~

Then the first two lines **typically change** to:

~~~text
Environment demo.mode = from-cli
@Value demo.mode = from-cli
~~~

The lines from `ApplicationArguments` **do not change**, because the input `args` themselves did not change.

This control experiment clarifies the API's goal: it changes **participation in environment property resolution**, not how the application receives `String[] args`.

To inspect with a debugger, pause inside `ApplicationRunner.run(...)` and observe:

- `environment.getProperty("demo.mode")`.
- `runnerArguments.getOptionValues("demo.mode")`.
- `runnerArguments.getSourceArgs()`.

If you need to inspect property sources in code, inject `ConfigurableEnvironment` and read the names in `getPropertySources()`. When `setAddCommandLineProperties(false)` is used properly and no custom code adds it back, the default source named `commandLineArgs` is not added by `SpringApplication`.

## 12. Common mistakes

**Mistake 1 — "Setting false makes `ApplicationArguments` empty."**

No. The two mechanisms are independent; the section 3 example shows raw, option, and non-option args remain intact. If data is empty, check whether you actually passed `args` into `app.run(args)`.

**Mistake 2 — "Not seeing `--demo.mode=from-cli` in Environment means the CLI arg was lost."**

No. The data is still in `ApplicationArguments`; it is simply no longer a configuration source in `Environment` via the default mechanism.

**Mistake 3 — "You can set false after `run()`."**

Does not achieve the goal. Reading configuration and creating beans has already begun or finished. Set the option **before `run()`**.

**Mistake 4 — "`@Value("${job}")` should still pick up `--job=import`."**

After disabling the CLI property source, that is **no longer guaranteed**. If no `job` property exists in another source, the expression may fail to resolve or fall back to its declared default. For business commands, use `ApplicationArguments.getOptionValues("job")`.

**Mistake 5 — "`getOptionValues("dry-run") == null` when a flag has no value."**

False when `--dry-run` is present: the result is **an empty list `[]`**. `null` indicates the option did not appear at all. Use `containsOption(...)` to check flags.

**Mistake 6 — "`--job import` is the same as `--job=import`."**

They cannot be assumed equivalent in Spring Boot's option parser. Use `--job=import` syntax when you want an option with an explicit value.

**Mistake 7 — "Setting false forbids configuration from OS env or JVM system properties."**

False. Those sources are independent and can still override configuration from files.

**Mistake 8 — "Using false makes it safe to let users pass any parameters."**

Insufficient. Code can still read args and act on them. You still need validation, authorization limits, allowlists of valid commands, and strict avoidance of logging arguments containing secrets.

**Mistake 9 — "Adding `--spring.profiles.active=prod` will still enable the profile even with CLI properties disabled."**

Not via the default command-line property source channel. If the app needs a specific profile, set it from an allowed configuration source or configure it programmatically on purpose.

**Mistake 10 — "There is one shared `ApplicationArguments` across all different runs."**

Do not assume that. Arguments belong to a single `SpringApplication.run(...)` call and its created context. When running multiple contexts or repeated tests, track which application the args belong to.

## 13. Security and operational notes

The practical goal of `setAddCommandLineProperties(false)` is usually **separation of concerns**, not hiding arguments or creating a sandbox:

- **Configuration:** `--server.port=...` and other Boot options do not automatically override environment via the default command-line source.
- **Business logic:** `ApplicationArguments` remains readable and app code can react to `--job=delete`, `--dry-run`, `--input=...`. You must validate and authorize those commands yourself.
- **Secrets:** arguments on the process command line can be exposed via process-inspection tools, scripts, terminal history, or logs. Never use `ApplicationArguments` as a secret store.
- **Multi-source config:** files, environment variables, system properties, config imports, and manually added property sources continue operating by precedence order. Do not infer that setting `false` makes configuration immutable.
- **Testing:** verify both sides together: `Environment` does not receive CLI overrides while `ApplicationArguments` still receives args. Testing only one side easily misses regressions.

If the app relies on another deployment framework calling `SpringApplication.run(...)` directly where you do not control `main`, find a way to configure `SpringApplication` **before running** at the true entry point; do not patch beans too late to try achieving the same effect.

## 14. Self-verification exercises

Use the section 3 program with a single runner:

1. Run with `--demo.mode=from-cli --dry-run input.csv` and verify `Environment` remains `from-file`.
2. Change the CLI value to `--demo.mode=another`; observe `ApplicationArguments` changes while `Environment` remains `from-file`.
3. Remove `--dry-run`; `containsOption("dry-run")` becomes `false` and `getOptionValues("dry-run")` becomes `null`.
4. Add two options `--tag=a --tag=b`; verify `getOptionValues("tag")` returns a list of two values in order of appearance.
5. Remove `app.setAddCommandLineProperties(false)` and run again; observe the CLI value can override `demo.mode` in `Environment`.
6. Run with JVM system property `-Ddemo.mode=from-jvm`; verify that the system property source is not disabled by this API. Make sure `-D` is passed to the application's JVM process, not confused with the Gradle/Maven JVM.

### Official references

- Spring Boot 3.3 – Externalized Configuration, *Accessing Command Line Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 – SpringApplication, *Accessing Application Arguments*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 – `SpringApplication.setAddCommandLineProperties(boolean)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 – `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html

**Conclusion:** Call `SpringApplication.setAddCommandLineProperties(false)` **before** `run(args)` to stop automatically turning CLI options into Spring `Environment` properties. The data remains intact in `ApplicationArguments` and still works via injection or `ApplicationRunner`. That lets the application accept **business commands** via the CLI while keeping **runtime configuration** governed by explicitly chosen sources.
