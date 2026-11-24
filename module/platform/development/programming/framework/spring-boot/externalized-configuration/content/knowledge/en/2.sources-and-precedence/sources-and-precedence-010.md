# Experimenting with Multiple Sources Declaring the Same Configuration Key

## 1. Experiment Goals and Questions

A Spring Boot application can receive the same property from multiple places: an `application.yml` file packaged inside the JAR, a config file outside the JAR, an operating system environment variable, a Java system property, and a command-line argument. When these sources declare the same key, Spring Boot must determine **one effective value** to supply to Java code.

This lab uses a single key, `lab.marker`, with intentionally distinct values in each source, to answer four questions:

1. When only one source exists, which value does the bean receive?
2. When adding a new source with the same key, which source takes precedence?
3. When removing a higher-precedence source, does the value automatically fall back to a lower source?
4. Are values accessed via `Environment` and values bound via `@ConfigurationProperties` consistent?

The expected outcome of the experiment, using standard Spring Boot configuration and no extra sources, is:

```text
Command-line arg       --lab.marker=from-cli
          >
Java system property   -Dlab.marker=from-jvm
          >
Environment variable   LAB_MARKER=from-env
          >
External JAR config    ./config/application-prod.yml
          >
External JAR config    ./config/application.yml
          >
Packaged JAR config    application-prod.yml
          >
Packaged JAR config    application.yml
```

The `>` symbol means **higher precedence for the same `lab.marker` key** in the scenario under test. This is the order among the sources *included in the experiment*, not the complete list of every `PropertySource` Spring Boot supports. For example, test configuration, `SPRING_APPLICATION_JSON`, or extra application-registered sources would change the picture if introduced.

## 2. Preparing a Small App to Observe Results

We will use a Spring Boot application packaged as an executable JAR. No database, HTTP endpoints, or complex business logic are needed. The application simply prints the value of `lab.marker` once the context has initialized.

Minimal structure:

```text
config-priority-lab/
├── src/main/java/com/example/configlab/
│   ├── ConfigLabApplication.java
│   └── LabProperties.java
├── src/main/resources/
│   ├── application.yml
│   └── application-prod.yml
└── config/                         # created later, placed outside JAR
    ├── application.yml
    └── application-prod.yml
```

The two files in `src/main/resources` become resources inside the JAR after packaging. By contrast, the `config/` directory next to where we run commands will be a configuration source **external** to the build. To watch each source enter in order, **do not create** the two files under `config/` yet.

### 2.1. Defining the Configuration Target Object

Create `LabProperties.java`:

```java
package com.example.configlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab")
public record LabProperties(String marker) {
}
```

`@ConfigurationProperties(prefix = "lab")` instructs Spring Boot to bind the `lab.marker` property to the `marker` component of the record. This is an example of strongly typed binding: a property name in configuration maps to a Java object field. A single-constructor record works cleanly with Spring Boot 3 constructor binding.

Create `ConfigLabApplication.java`:

```java
package com.example.configlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(LabProperties.class)
public class ConfigLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigLabApplication.class, args);
    }

    @Bean
    ApplicationRunner reportConfiguration(
            Environment environment,
            LabProperties properties) {
        return args -> {
            String fromEnvironment =
                    environment.getProperty("lab.marker");

            String fromBinding = properties.marker();

            System.out.println("=== CONFIG PRIORITY LAB ===");
            System.out.println("Environment = " + fromEnvironment);
            System.out.println("Bound bean  = " + fromBinding);
            System.out.println("===========================");
        };
    }
}
```

In this example, `ApplicationRunner` runs once application startup reaches the runner execution phase. We measure the same property in two ways:

- `Environment.getProperty("lab.marker")`: looks up the effective value by key.
- `properties.marker()`: reads the value bound by Spring Boot into the `LabProperties` bean.

If configuration sources and binding are set up properly, both lines must show the same value. The experiment does not rely on the ordering of other startup logs; only inspect the two lines after the `CONFIG PRIORITY LAB` header.

### 2.2. Creating Configuration Packaged Inside the JAR

In `src/main/resources/application.yml`:

```yaml
lab:
  marker: from-packaged-default
```

In `src/main/resources/application-prod.yml`:

```yaml
lab:
  marker: from-packaged-prod
```

The name `application-prod.yml` designates configuration for the `prod` profile. Without activating this profile, values in that file will not be applied merely because the file exists. When `prod` is active, `from-packaged-prod` overrides `from-packaged-default` for the same key, provided no higher-precedence source exists.

After adding both files, package the application with your build tool, such as the Gradle `bootJar` task, and use the actual path to the generated JAR. In the commands below, `app.jar` is just a placeholder name for the **packaged executable JAR**, not a default filename generated by Spring Boot.

Make sure you open your terminal in the project directory, where `./config/` will later live. Your current working directory matters because Spring Boot by default searches for external configuration relative to the directory where the application is launched.

## 3. Run A — Using Only application.yml Inside the JAR

Before creating the `config/` directory and before setting any environment variables or Java system properties for the lab key, run:

```bash
java -jar app.jar
```

Expected output:

```text
=== CONFIG PRIORITY LAB ===
Environment = from-packaged-default
Bound bean  = from-packaged-default
===========================
```

We have one source for `lab.marker`: `application.yml` packaged inside the JAR. Spring Boot loads this file via Config Data, feeds the property into the configuration system, and returns the exact same value via both lookup and binding.

What to observe is not just the printed string. Notice the boundary: **`ConfigLabApplication` code does not know which YAML file stores the property**. The code only names the key or prefix; Spring Boot decides which source supplies the value.

If both lines print `null`, verify that the YAML file was actually packaged into the JAR, the record is registered with `@EnableConfigurationProperties`, and there are no typos in the prefix or key name. If a different value appears, a configuration source from your machine's environment may be overriding the JAR value.

## 4. Run B — Activating the prod Profile

Keep the exact same JAR, adding the profile selection argument:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected output:

```text
Environment = from-packaged-prod
Bound bean  = from-packaged-prod
```

Because `prod` is active, Spring Boot loads configuration from `application-prod.yml`. For the same `lab.marker` key, profile-specific configuration inside the JAR has higher precedence than non-profile configuration inside the same JAR.

Distinguish clearly:

- `--spring.profiles.active=prod` determines **which profile is active**.
- `application-prod.yml` supplies **a candidate value** for `lab.marker`.
- Final value selection still obeys the precedence order of all configuration sources.

Thus, profiles do not create a separate lookup system. They control which configuration sources participate in the same `Environment`.

## 5. Run C — Adding application.yml Outside the JAR

Now create the `config` directory in the terminal's working directory and add `./config/application.yml`:

```yaml
lab:
  marker: from-external-default
```

Keep the same JAR and keep the `prod` profile active:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected output:

```text
Environment = from-external-default
Bound bean  = from-external-default
```

The interesting point is that `application-prod.yml` *inside the JAR* declares `from-packaged-prod`, yet the chosen value is `from-external-default` from `application.yml` *outside the JAR*. Under the default rules for standard Config Data locations, external configuration outside the JAR outranks configuration packaged inside the JAR.

This lets you run a single build across multiple machines: each deployment environment can place external configuration outside the JAR without recompiling. Remember, however, that `./config/` is resolved relative to the **process working directory**, not necessarily the directory containing the JAR. Running the app from another directory may prevent the external file from being found as expected.

In this run, the candidate list for `lab.marker` is:

| Source | Value | Effective? |
| --- | --- | --- |
| Inside JAR, `application.yml` | `from-packaged-default` | No |
| Inside JAR, `application-prod.yml` | `from-packaged-prod` | No |
| Outside JAR, `config/application.yml` | `from-external-default` | **Yes** |

You do not need to delete the two values inside the JAR; Spring Boot selects according to source precedence.

## 6. Run D — Adding Profile-Specific Configuration Outside the JAR

Also create `./config/application-prod.yml`:

```yaml
lab:
  marker: from-external-prod
```

Run again:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected output:

```text
Environment = from-external-prod
Bound bean  = from-external-prod
```

Now all four files contain `lab.marker`. Within the standard Config Data scope of this lab, the order from high to low is:

1. Outside JAR: `config/application-prod.yml`.
2. Outside JAR: `config/application.yml`.
3. Inside JAR: `application-prod.yml`.
4. Inside JAR: `application.yml`.

That is why `from-external-prod` wins. Profile configuration and file location **together** determine precedence; you cannot simply conclude "any file with a profile beats any file without a profile" while ignoring whether the file sits inside or outside the JAR.

If you run again **without** `--spring.profiles.active=prod`, the two `application-prod.yml` files are normally unused, and `from-external-default` takes effect. This is an independent check proving that profile activation governs which sources are evaluated.

## 7. Run E — Environment Variable Overrides YAML

Keep all four config files. On Linux/macOS, set the environment variable for a single run:

```bash
LAB_MARKER=from-env java -jar app.jar --spring.profiles.active=prod
```

On Windows PowerShell:

```powershell
$env:LAB_MARKER = "from-env"
java -jar app.jar --spring.profiles.active=prod

# Clean up the variable after the experiment so it does not affect later runs
Remove-Item Env:LAB_MARKER
```

Expected output while the environment variable is set:

```text
Environment = from-env
Bound bean  = from-env
```

In Spring Boot, `LAB_MARKER` is the environment variable form corresponding to property name `lab.marker`. For the standard configuration sources used here, OS environment variables have higher precedence than Config Data files.

Thanks to this, the runtime environment can override a default inside the JAR or config files without modifying code. For instance, a deployment platform can pass per-instance environment variables.

One practical note: if you run `export LAB_MARKER=from-env` in Bash, the variable persists in that shell session until `unset LAB_MARKER` or the session ends. In PowerShell, `$env:LAB_MARKER` likewise persists in the shell process until removed or changed. If you forget this step, later YAML experiments will yield unexpected results.

## 8. Run F — Java System Property Overrides Environment Variable

Keep the `LAB_MARKER=from-env` environment variable and add the Java system property `lab.marker` via the JVM `-D` flag:

Linux/macOS:

```bash
LAB_MARKER=from-env java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod
```

Windows PowerShell:

```powershell
$env:LAB_MARKER = "from-env"
java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod
Remove-Item Env:LAB_MARKER
```

Expected output:

```text
Environment = from-jvm
Bound bean  = from-jvm
```

Here both the `from-env` environment variable and the `from-jvm` JVM value exist, yet `from-jvm` wins because Java system properties have higher precedence than OS environment variables in Spring Boot's standard source order.

Syntactically, `-Dlab.marker=from-jvm` must appear **before `-jar`** for the JVM to treat it as a system property. Writing `java -jar app.jar -Dlab.marker=from-jvm` turns that string into an application argument with a different meaning. In Spring Boot, to pass a property directly as an application argument, use `--lab.marker=value` as shown in the next step.

Do not confuse the Java system property `System.getProperty("lab.marker")` with the environment variable `System.getenv("LAB_MARKER")`. They are two distinct storage mechanisms in the JVM and OS; Spring's `Environment` aggregates those sources in precedence order.

## 9. Run G — Command-Line Argument Has the Highest Precedence in the Lab

Keep both the environment variable and the Java system property from the previous step, then add the Spring Boot argument `--lab.marker=from-cli`:

Linux/macOS:

```bash
LAB_MARKER=from-env java -Dlab.marker=from-jvm -jar app.jar \
  --spring.profiles.active=prod \
  --lab.marker=from-cli
```

Windows PowerShell (one line):

```powershell
$env:LAB_MARKER = "from-env"
java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod --lab.marker=from-cli
Remove-Item Env:LAB_MARKER
```

Expected output:

```text
Environment = from-cli
Bound bean  = from-cli
```

At this point, all seven lab sources simultaneously supply `lab.marker`:

| Precedence Order in Lab | Declaring Source | Value |
| ---: | --- | --- |
| 1 — highest | `--lab.marker=...` argument | **`from-cli`** |
| 2 | Java system property `-Dlab.marker=...` | `from-jvm` |
| 3 | Environment variable `LAB_MARKER` | `from-env` |
| 4 | `./config/application-prod.yml` | `from-external-prod` |
| 5 | `./config/application.yml` | `from-external-default` |
| 6 | `application-prod.yml` inside JAR | `from-packaged-prod` |
| 7 — lowest | `application.yml` inside JAR | `from-packaged-default` |

Every source supplies a candidate value, yet `Environment` returns `from-cli` as the effective value, and `LabProperties.marker()` receives `from-cli` as well.

**The order above applies within the scope of the selected sources**, with the `prod` profile active and command-line properties handled in default mode. Spring Boot also supports sources such as `SPRING_APPLICATION_JSON`, servlet environment parameters, and test properties. An application can also customize source registration itself; do not treat this table as an immutable order for every Spring program.

## 10. Reversing the Experiment: Removing High-Precedence Sources One by One

Adding sources step by step shows which source overrides which. **Removing sources in reverse order** proves that lower-precedence values are still retained and can be used whenever higher sources are absent.

Keep all four YAML files and the `prod` profile; execute independent runs in a clean, controlled shell environment:

| Scenario | Remaining Sources for `lab.marker` | Expected |
| --- | --- | --- |
| A | Command line, JVM, OS env, and four YAMLs | `from-cli` |
| B | Omit `--lab.marker=from-cli` only; JVM and OS env remain | `from-jvm` |
| C | Omit both CLI and `-Dlab.marker`; OS env remains | `from-env` |
| D | Omit CLI, JVM, and env var; four YAMLs remain | `from-external-prod` |
| E | Temporarily rename/delete `config/application-prod.yml`, keep remaining external YAML | `from-external-default` |
| F | Also temporarily rename/delete `config/application.yml`, keep `prod` profile | `from-packaged-prod` |
| G | No external YAML, `prod` profile inactive | `from-packaged-default` |

For steps E/F, only temporarily rename the lab's config files if you want to keep their contents; do not edit files inside the JAR. For steps B/C, you must actually omit the argument or environment variable from the new run command.

You can run step D independently using the following command in a shell where `LAB_MARKER` is no longer set:

```bash
java -jar app.jar --spring.profiles.active=prod
```

When the output prints `from-external-prod`, it confirms that removing the top three sources allows the value from external profile config to surface. This mechanism is commonly called **precedence-based override**: multiple sources are preserved in the system, and key lookup decides the winning value.

Remember that each row in the table is **a fresh application startup**. Changing an environment variable or file while the application is already running does not guarantee the `LabProperties` bean automatically updates; this experiment compares configuration state across startups.

## 11. Looking Under the Hood: What Does Environment Do?

So far, we have seen *which source wins* from the printed strings. To understand *why*, distinguish:

- **PropertySource**: represents a source holding multiple properties, such as Java system properties, environment variables, or Config Data sources.
- **Environment**: provides property lookup across those sources in precedence order, while also managing profile state.
- **ConfigurationProperties binding**: uses the configuration system to map property names to Java fields and convert types as needed.
- **Configuration-consuming bean**: simply receives bound values without deciding which file to read.

With `lab.marker`, the application receives a string so type conversion is barely noticeable. If you replace the key with `lab.timeout` and value `5s`, and use a `Duration timeout` record component, Spring Boot converts the text duration representation into a Java object. **Source precedence** answers "which input value is chosen"; **binding** answers "how that value is populated into a Java type". These are two separate questions.

When deeper analysis is needed, you can iterate over `ConfigurableEnvironment.getPropertySources()` in a test program or inspect information via Spring Boot Actuator's `env` and `configprops` endpoints if your project enables and secures them appropriately. However, aggregated sources and detailed representations can vary across versions, so never write business logic depending on the internal name of a `PropertySource`.

Do not print the full list of properties in a real application because it can leak access keys, passwords, and connection strings. This lab intentionally uses only `lab.marker` with harmless strings.

## 12. Why Does the Value in YAML Differ from the Bean Result?

A common reasoning mistake is opening `application.yml`, seeing `lab.marker: from-packaged-default`, and assuming the bean will definitely receive that string. In a multi-source model, this file is just **one candidate**. When the bean is created, Spring determines the effective value from all loaded sources.

Several scenarios easily cause confusion:

### 12.1. Forgetting an Environment Variable Set Earlier

If you ran `export LAB_MARKER=from-env` or `$env:LAB_MARKER = "from-env"`, subsequent runs may still receive `from-env` even after editing YAML. Check and clear the variable in your shell before concluding the YAML experiment failed.

### 12.2. Running the JAR from the Wrong Directory

A file sitting next to the JAR is not guaranteed to be found automatically if the process starts from a different directory. Default search locations like `./config/` are relative to the working directory. Keep `pwd` or `Get-Location` consistent when comparing, or explicitly configure external locations when needed.

Spring Boot supports `spring.config.additional-location` to add Config Data search locations. That is a separate operational tool; if used, record it in your experiment setup because it can alter the set of sources and precedence.

### 12.3. Failing to Activate the Right Profile

`application-prod.yml` is not always loaded. If you forget `--spring.profiles.active=prod`, check whether `prod` is being activated by another source. Do not guess active profiles solely from filenames.

### 12.4. Confusing JVM Arguments with Application Arguments

The two commands below have different meanings:

```bash
java -Dlab.marker=from-jvm -jar app.jar
java -jar app.jar --lab.marker=from-cli
```

The `-D` form is a Java system property; the `--lab.marker=...` form is a command-line property received by Spring Boot via application arguments. Under standard configuration, `--` arguments beat `-D` if both declare the same key.

### 12.5. Extra Sources Beyond the Lab Scope

If a real system uses `SPRING_APPLICATION_JSON`, test properties, imported configuration, multiple profiles, or code that alters `PropertySources`, results can differ from the lab table. Expand the list of sources under analysis rather than forcing the outcome to match the sample table.

### 12.6. Reading Values at Runtime and Expecting Automatic Updates

`@ConfigurationProperties` is normally bound when the bean is created. Editing an external config file after Spring Boot is already running does not mean the app reloads the configuration object. To test a new source reliably, stop and restart the process. Dynamic configuration refresh, if required, must be designed explicitly.

## 13. Follow-Up Scenario: Using Different Values per Machine

Suppose a team deploys the same shared JAR:

```yaml
# application.yml inside the JAR
lab:
  marker: safe-default
```

A developer machine with no extra declarations receives `safe-default`. A staging host with `LAB_MARKER=staging` receives `staging`. A production host with `LAB_MARKER=production` receives `production`. The exact same `LabProperties` class and `properties.marker()` code keep working.

Of course, in real applications, configuration typically consists of service URLs, timeouts, connection pool sizes, or feature flags rather than a marker string. The principle remains identical: code defines **property names and usage**, while the deployment environment supplies **concrete values**. Never hardcode production addresses, passwords, or tokens in code just because the program can run with them.

When the same key exists in multiple sources, disciplined operations matter: document which sources are allowed to override, restrict sensitive overrides, define sensible defaults, and inspect effective state through secured diagnostic channels.

## 14. Reinforcement Exercises

Predict the output before running; then verify using `Environment` and `LabProperties`:

**Exercise 1 — Two sources inside the JAR:** With `application.yml` and `application-prod.yml` as prepared, why does running without a profile yield `from-packaged-default` whereas activating `prod` yields `from-packaged-prod`?

**Exercise 2 — External and packaged sources:** When `application-prod.yml` inside the JAR is active, why does adding `./config/application.yml` change the result to `from-external-default`?

**Exercise 3 — Environment variable:** Both `config/application-prod.yml` and `LAB_MARKER` set the same key. If you remove the environment variable from **a new run**, which value does Spring Boot use?

**Exercise 4 — JVM and CLI:** In the command below, what are the candidates for `lab.marker` and what is the final value?

```bash
LAB_MARKER=os java -Dlab.marker=jvm -jar app.jar \
  --spring.profiles.active=prod \
  --lab.marker=cli
```

**Exercise 5 — Restoring a lower-precedence value:** When you remove `--lab.marker=cli` from Exercise 4's command, which source becomes effective? What if you also remove `-Dlab.marker=jvm`?

**Exercise 6 — Type conversion:** Replace `lab.marker` with `lab.timeout`, configuring `1s` in YAML, `LAB_TIMEOUT=4s` in the environment, and `--lab.timeout=2s` on the command line. Use `@ConfigurationProperties` with a `Duration timeout` component. Before running, predict what `timeout.toSeconds()` returns and why.

Across these exercises, clearly distinguish three stages: **which sources participate**, **which source has the highest precedence for the key**, and **the bean receiving the bound value**. That is the essence of experimenting with externalized configuration when multiple sources declare the same key.

## 15. Summary of Experiment Results

With unchanged Java code, we produced a verifiable sequence of outputs:

```text
Profile inactive, no external config:
    from-packaged-default

prod active, no external config:
    from-packaged-prod

Add ./config/application.yml:
    from-external-default

Add ./config/application-prod.yml:
    from-external-prod

Add LAB_MARKER:
    from-env

Add -Dlab.marker:
    from-jvm

Add --lab.marker:
    from-cli
```

The takeaway is not memorizing this example sequence. Always ask: **"At this startup, which `PropertySource` instances are participating, and which source has the highest precedence for the key being read?"**

Answer that question first, and only then examine binding and how beans consume the configuration. Doing so turns investigating a configuration value that "doesn't match YAML" into an observable, repeatable process instead of randomly editing config files.