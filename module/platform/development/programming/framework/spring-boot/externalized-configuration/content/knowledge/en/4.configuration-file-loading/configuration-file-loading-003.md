# Changing the Configuration File Base Name with `spring.config.name`

## 1. Why Change the Configuration File Name?

When creating a Spring Boot application, the common practice is to put configuration in files with the base name `application`:

```text
src/main/resources/
├── application.properties
├── application.yml
└── application-prod.yml
```

The term "base name" refers to the part before the file extension such as `.properties`, `.yml`, or `.yaml`. For example, `application.yml` has the base name `application`.

By default, Spring Boot searches for files with the base name `application` in supported configuration locations. However, a project may want to use `billing.yml`, `orders.yml`, or `my-service.properties` to clearly express its deployment purpose.

The **`spring.config.name`** property lets you specify the base name that Spring Boot's configuration loading mechanism will search for.

For example:

```bash
java -jar app.jar --spring.config.name=billing
```

Spring Boot then searches for files with the base name `billing`, such as `billing.properties`, `billing.yml`, or `billing.yaml`, in the active configuration search locations.

**Important distinction:** the command above does not rename physical files, does not copy files, and does not automatically create new files. You must prepare `billing.yml` or the corresponding file where Spring Boot can read it.

## 2. What Does `spring.config.name` Change?

Suppose the project has this structure:

```text
src/
└── main/
    └── resources/
        ├── application.yml
        └── billing.yml
```

Contents of `application.yml`:

```yaml
demo:
  message: "Default configuration"
  timeout-seconds: 10
```

Contents of `billing.yml`:

```yaml
demo:
  message: "Billing service configuration"
  timeout-seconds: 25
```

If you start the application normally:

```bash
java -jar app.jar
```

Spring Boot uses the default base name `application`. Therefore, the configuration above can provide `demo.message=Default configuration` and `demo.timeout-seconds=10`.

If you start with:

```bash
java -jar app.jar --spring.config.name=billing
```

Spring Boot uses `billing` as the base name for configuration file discovery. When no higher-precedence source overrides it, the values become:

```text
demo.message = Billing service configuration
demo.timeout-seconds = 25
```

Notably, `spring.config.name=billing` **does not mean loading `application.yml` first and then overriding it with `billing.yml`**. Discovery by base name has changed; `application.yml` is no longer searched under the default name unless you add `application` to the list of names or load that file via another mechanism.

## 3. Three Ways to Set `spring.config.name` Before the Application Runs

`spring.config.name` is an early-initialization property. Spring Boot needs to know this value **before deciding which configuration files to read**. Common ways to set it are command-line arguments, Java system properties, and OS environment variables.

### 3.1. Command-line argument

```bash
java -jar app.jar --spring.config.name=billing
```

This is convenient for manual runs or quick verification. The `--spring.config.name=billing` syntax is an application argument passed after `-jar app.jar`.

### 3.2. Java system property

```bash
java -Dspring.config.name=billing -jar app.jar
```

Note that `-Dspring.config.name=billing` is placed **before** `-jar`, because it is a JVM option.

### 3.3. Environment variable

On Bash or POSIX-compatible shells:

```bash
export SPRING_CONFIG_NAME=billing
java -jar app.jar
```

Or applied only for a single run:

```bash
SPRING_CONFIG_NAME=billing java -jar app.jar
```

On Windows PowerShell:

```powershell
$env:SPRING_CONFIG_NAME = "billing"
java -jar app.jar
Remove-Item Env:SPRING_CONFIG_NAME
```

The `SPRING_CONFIG_NAME` variable is the environment-variable representation of the `spring.config.name` key. Applying these different forms follows Spring Boot's configuration-reading mechanism.

**Do not expect placing `spring.config.name` inside `application.yml` itself to switch discovery from `application.yml` to another file.** By the time Spring Boot reads `application.yml`, the selection of configuration file names and locations has already occurred. Provide this property from a source available during early initialization.

## 4. Combining with Profile-Specific Configuration

Spring Boot supports profile-specific configuration file variants. When the base name is `application` and the `prod` profile is active, a common file is `application-prod.yml`.

If you change the base name to `billing`, profile naming rules apply accordingly:

```text
src/main/resources/
├── billing.yml
├── billing-dev.yml
└── billing-prod.yml
```

For example, `billing.yml` holds shared values:

```yaml
demo:
  message: "Shared value"
  timeout-seconds: 20
```

The file `billing-prod.yml` holds profile-specific configuration:

```yaml
demo:
  message: "Production value"
```

Run:

```bash
java -jar app.jar --spring.config.name=billing --spring.profiles.active=prod
```

When there is no higher-precedence configuration source:

| Property | Effective Value | Source Explanation |
| --- | --- | --- |
| `demo.message` | `Production value` | `billing-prod.yml` overrides the shared value |
| `demo.timeout-seconds` | `20` | `billing.yml` provides the un-overridden value |

The right way to understand this is:

1. `spring.config.name=billing` determines the base name to search for.
2. `spring.profiles.active=prod` activates the `prod` profile.
3. The Config Data mechanism examines files matching the base name and profile in the active search locations.
4. Configuration sources are combined according to precedence rules; properties present only in the shared file can still be used.

Changing the base name **does not change profile names**, nor does it disable the overriding behavior of profile-specific configuration.

## 5. Multiple Base Names Can Be Configured

`spring.config.name` accepts a comma-separated list of base names.

For example:

```bash
java -jar app.jar --spring.config.name=application,billing
```

This instructs Spring Boot to look for both files named `application` and files named `billing` in the corresponding configuration locations.

One layout is:

```text
src/main/resources/
├── application.yml
├── application-prod.yml
├── billing.yml
└── billing-prod.yml
```

This configuration is useful when you want to **keep the default `application` name while adding a group of files under a custom name**. If you only pass `--spring.config.name=billing`, do not assume `application.yml` will still be searched as before.

When files share the same key, the result is not decided by "merging JSON/YAML contents arbitrarily." Spring Boot has rules for location order, documents, profiles, and property sources. You must distinguish **selecting which files are searched** from **selecting the effective value** among those files.

In examples where you need certainty about which source is effective, read the property you want to verify directly from `Environment` instead of guessing from the file name alone.

## 6. Base Name Differs from Search Locations

`spring.config.name` answers **"Which base file name should be searched?"**; whereas `spring.config.location` or `spring.config.additional-location` answers **"Where should we search?"**.

By default, Spring Boot 3.x examines familiar locations such as the classpath root, `classpath:/config/`, the current working directory, `./config/`, and direct subdirectories of `./config/` under the default search mechanism. These locations relate to application deployment, not just the `src/main/resources` layout during development.

Example of external configuration outside the application:

```text
deploy/
├── app.jar
└── config/
    └── billing.yml
```

In `deploy/config/billing.yml`:

```yaml
server:
  port: 9095
demo:
  message: "Configuration outside JAR"
```

When the working directory is `deploy/`, you can run:

```bash
java -jar app.jar --spring.config.name=billing
```

The default search mechanism can find `./config/billing.yml`. The working directory of the **running Java process** is a crucial factor: changing the working directory can cause `./config/` to point elsewhere.

If you want to specify the directory explicitly, use both name and location:

```bash
java -jar app.jar \
  --spring.config.name=billing \
  --spring.config.location=file:./config/
```

The trailing `/` on `file:./config/` indicates it is a directory. With a **directory** location, Spring Boot can combine the name from `spring.config.name` to search for matching files.

Conversely, if `spring.config.location` points to a **specific file**, such as:

```bash
java -jar app.jar --spring.config.location=file:./config/billing.yml
```

then the file path is specified directly; choosing a base name no longer has the same meaning for that file location.

Also note: `spring.config.location` can **replace the default search location list**; `spring.config.additional-location` adds locations alongside the default ones. Choose the appropriate property to avoid accidentally dropping needed configuration sources.

## 7. Distinguishing from Similarly Named Properties

| Property | Question the Property Answers | Example |
| --- | --- | --- |
| `spring.config.name` | Which base name to use when searching for files? | `billing` |
| `spring.config.location` | Which locations to load configuration from instead of the defaults? | `file:./config/` |
| `spring.config.additional-location` | Where to look for additional configuration? | `file:./deploy-overrides/` |
| `spring.config.import` | Which extra configuration resource to import? | `optional:file:./secrets.properties` |
| `spring.application.name` | What is the logical identifying name of the application? | `billing-service` |
| `spring.profiles.active` | Which profile to activate? | `prod` |

A common mistake:

```yaml
spring:
  application:
    name: billing
```

The configuration above sets the **application name** to `billing`. It does **not** automatically rename the default configuration file from `application.yml` to `billing.yml`. `spring.application.name` and `spring.config.name` serve two independent purposes.

Another mistake is putting:

```yaml
spring:
  config:
    name: billing
```

inside `application.yml` and expecting Spring Boot to stop reading `application.yml` and immediately switch to `billing.yml`. That does not satisfy the requirement of choosing the file name **before the Config Data reading phase**; pass `spring.config.name` at launch time.

## 8. Runnable Practical Example

### Step 1: Prepare two files

File `src/main/resources/application.yml`:

```yaml
demo:
  source: "application"
  greeting: "Hello from default configuration"
```

File `src/main/resources/custom.yml`:

```yaml
demo:
  source: "custom"
  greeting: "Hello from custom.yml"
```

### Step 2: Add code to read configuration

Use a component that runs after the Spring Boot application starts:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationNamePrinter implements ApplicationRunner {

    private final Environment environment;

    public ConfigurationNamePrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String source = environment.getProperty("demo.source", "<missing>");
        String greeting = environment.getProperty("demo.greeting", "<missing>");

        System.out.println("demo.source = " + source);
        System.out.println("demo.greeting = " + greeting);
    }
}
```

### Step 3: Run with the default name

After packaging the application into `app.jar`, run:

```bash
java -jar app.jar
```

Assuming no other source overrides `demo.source` and `demo.greeting`, the printed output will be:

```text
demo.source = application
demo.greeting = Hello from default configuration
```

### Step 4: Run with a custom base name

```bash
java -jar app.jar --spring.config.name=custom
```

The printed output changes to:

```text
demo.source = custom
demo.greeting = Hello from custom.yml
```

No Java code change is needed to get a different result. The startup argument decides which group of configuration files the application searches for.

### Step 5: Combine with a profile

Add `src/main/resources/custom-test.yml`:

```yaml
demo:
  greeting: "Hello from test profile"
```

Run:

```bash
java -jar app.jar --spring.config.name=custom --spring.profiles.active=test
```

Expected output:

```text
demo.source = custom
demo.greeting = Hello from test profile
```

Explanation: `demo.source` comes from `custom.yml`; `demo.greeting` is overridden by the profile file `custom-test.yml`.

Note that a real environment may set properties via command-line arguments, JSON, environment variables, or other higher-precedence sources, in which case the final result may differ from the example.

## 9. Confusing Scenarios

### 9.1. Changing the name in the command without renaming the file

Scenario:

```text
Only application.yml exists
Run with --spring.config.name=custom
```

There is no `custom.yml` (or corresponding format) in the searched locations. Values that exist only in `application.yml` will not automatically be used under the new base name.

Not every failure to find a custom-named file stops the application immediately: with the default search locations, the application can still run using other configuration sources. Problems may arise when a required component needs a missing property. A location or file explicitly marked as required via Config Data can raise a location-not-found error if the resource does not exist.

### 9.2. Using the full file name instead of the base name

The intent of `spring.config.name` is to declare a base name such as:

```text
billing
orders
custom
```

Do not use `spring.config.name=billing.yml` as a substitute for a full file path. If you need to point to one specific resource, consider `spring.config.location` with a file path.

### 9.3. Placing the JVM option in the wrong position

Correct:

```bash
java -Dspring.config.name=custom -jar app.jar
```

Correct for an application argument:

```bash
java -jar app.jar --spring.config.name=custom
```

These two syntaxes belong to two different parameter-receiving mechanisms. Do not move `-D...` to the end of the command and expect the JVM to read it as a system property.

### 9.4. Reading a file from an unexpected path

Suppose `custom.yml` is packaged in the JAR, but the host machine also has `./config/custom.yml`. The Config Data mechanism can load configuration from multiple locations with different precedences; an external file can override same-key values in the packaged file.

Therefore, if you see an unexpected value, check separately:

- What base name is being used?
- Which locations are being searched?
- Which profile is active?
- Does the property appear in a higher-precedence source?

### 9.5. Adding a second name and forgetting to keep the first

When you need to load both the default file and a service-specific file, explicitly specify all needed names, such as `--spring.config.name=application,custom`. Setting only `custom` can drop values you previously relied on in `application.yml`.

### 9.6. Expecting the profile to change the base name automatically

Setting `--spring.profiles.active=prod` does not automatically pick `billing.yml` just because the application is named billing. Profiles only provide context for selecting profile-specific documents/files; the base name is still determined by `spring.config.name`.

## 10. Inspecting Configuration Sources for Diagnostics

To determine where a key's value is coming from, you can read `Environment`:

```java
String value = environment.getProperty("demo.greeting");
System.out.println(value);
```

If you need to trace property sources in a controlled development environment, Spring Boot Actuator provides the `env` endpoint when included in the application and configured to allow access. Be careful to restrict exposure of configuration data that may contain sensitive information.

Do not look solely at a file name and conclude all properties come from that file. `spring.config.name` defines the **candidate file names searched**, while the final selected value also depends on locations, profiles, and property source precedence.

## 11. Reinforcement Exercise

Consider the directory:

```text
src/main/resources/
├── application.yml
├── payment.yml
└── payment-dev.yml
```

The files contain:

```yaml
# application.yml
demo:
  mode: "application"
```

```yaml
# payment.yml
demo:
  mode: "payment"
  currency: "VND"
```

```yaml
# payment-dev.yml
demo:
  mode: "payment-dev"
```

Predict the output when no other source overrides these keys:

| Startup Command | `demo.mode` | `demo.currency` |
| --- | --- | --- |
| `java -jar app.jar` | `application` | Not present in files searched under the default name |
| `java -jar app.jar --spring.config.name=payment` | `payment` | `VND` |
| `java -jar app.jar --spring.config.name=payment --spring.profiles.active=dev` | `payment-dev` | `VND` |

Try adding `--demo.mode=cli` to the last command. Then `demo.mode` becomes `cli` because command-line arguments for ordinary properties have higher precedence than values from configuration files.

## 12. Takeaways

- `spring.config.name` changes the **base name** Spring Boot uses to search for configuration files; the default is `application`.
- Pass only the name portion, such as `payment`, rather than passing `payment.yml` or a path by default.
- Provide `spring.config.name` from a source available early at startup: `--spring.config.name=...` argument, `-Dspring.config.name=...` JVM property, or `SPRING_CONFIG_NAME` environment variable.
- When profiles are used, the new base name continues to work with profile suffixes, such as `payment-dev.yml` when the `dev` profile is active.
- Multiple base names can be declared, e.g., `application,payment`, when multiple file groups need to be searched.
- `spring.config.name` chooses the **name**; `spring.config.location` and `spring.config.additional-location` relate to **locations**. `spring.application.name` only sets the application name.
- Changing the base name does not alter the overall precedence order among property sources. To understand the effective value, check sources, locations, and profiles as well.