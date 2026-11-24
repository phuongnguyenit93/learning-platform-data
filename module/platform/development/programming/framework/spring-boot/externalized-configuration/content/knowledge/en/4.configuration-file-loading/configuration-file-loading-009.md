# When to Supply `spring.config.*` So Spring Boot 3.3 Discovers and Loads Configuration

## 1. Problem to Solve

Spring Boot 3.3 lets you change file names, search locations, and supplementary configuration sources through `spring.config.*` keys. A common trap is that **not every key can be placed into just any configuration file**. Some keys must be supplied **right when the application begins starting up**, before Spring Boot decides where to search for and read `application.properties` or `application.yaml`. Other keys are read **while** the Config Data loader is processing those configuration files.

For example:

```properties
spring.config.location=optional:file:./deployment/
```

If this line sits only inside an `application.properties` file discovered via default locations, Spring Boot does not use it to **go back and restart the discovery process from scratch**. To change where files are searched, put the value into an environment variable, JVM system property, or command-line argument **before `SpringApplication.run(...)` processes Config Data**.

Conversely, the following statement is a normal use case right **inside** `application.properties` or `application.yaml`:

```properties
spring.config.import=optional:file:./deployment/extra.properties
```

Because this is an instruction to **import additional data while reading an already-discovered file**, the Config Data loader can accept and execute it at the time the file is processed.

**Rule to remember:**

- **`spring.config.name`, `spring.config.location`, and `spring.config.additional-location`:** must be present **very early**, so Spring Boot knows **which names/locations** to search.
- **`spring.config.import` and `spring.config.activate.on-profile`:** operate **within the Config Data phase**; they are normally declared right inside configuration documents that Spring Boot has already found.
- **`spring.profiles.active` / `spring.profiles.default`:** are used to determine profiles and select `application-{profile}.*` files. They can be configured in **non-profile-specific** documents following Spring Boot's profile rules; they must not be declared arbitrarily inside profile-specific documents.
- **Ordinary application properties** (`app.*`, `server.port`, `spring.datasource.*`, etc.): are bound/consumed after the corresponding configuration source has been loaded, though some system properties such as logging are used fairly early as well.

## 2. Configuration Loading Timeline During Startup

Overview model:

```text
T0. Shell / runtime prepares the Java process
    ├─ OS environment: SPRING_CONFIG_LOCATION, ...
    ├─ JVM system properties: -Dspring.config.location=...
    └─ Program args: --spring.config.location=...

T1. main(String[] args), prepares SpringApplication
    ├─ may call setDefaultProperties(...) before run(...)
    └─ SpringApplication.run(args)

T2. Creates and prepares Environment before refreshing ApplicationContext
    ├─ receives early sources: system properties, environment variables,
    │  command-line options, and sources created by SpringApplication
    ├─ ConfigDataEnvironmentPostProcessor runs
    │  ├─ reads spring.config.name/location/additional-location
    │  ├─ determines which locations to search
    │  ├─ reads application.properties / application.yaml / .yml
    │  ├─ processes spring.config.import and profile-specific documents
    │  └─ adds Config Data PropertySources to Environment
    └─ Environment now includes file configuration sources

T3. Prepares, creates, and refreshes ApplicationContext
    ├─ @PropertySource on @Configuration may be added here
    ├─ creates beans / binds @ConfigurationProperties / @Value
    └─ starts server, runners, and application
```

The key component in Spring Boot 3.3 is `ConfigDataEnvironmentPostProcessor`. It processes Config Data **during Environment preparation**, before `ApplicationContext` finishes refreshing. Therefore, a property that steers the loader itself must be known **before or at the moment this component begins processing**, whereas values added via beans, `@PostConstruct`, `ApplicationRunner`, or `CommandLineRunner` arrive too late to redirect file discovery for that startup.

Timeline table:

| Where Value Is Supplied | Available When Choosing Where to Search Config Data? | How Used |
| --- | --- | --- |
| OS environment variables set before Java runs | **Yes** | `SPRING_CONFIG_LOCATION`, `SPRING_CONFIG_NAME`, `SPRING_CONFIG_ADDITIONALLOCATION` |
| JVM `-D...` before `main` runs | **Yes** | `-Dspring.config.location=...` |
| Command-line `--...` passed into `SpringApplication.run(args)` | **Yes**, under default configuration | `--spring.config.additional-location=...` |
| Values set via `SpringApplication.setDefaultProperties(...)` before `run` | **Yes**, with low precedence | Bootstrap defaults in code |
| `spring.config.import` inside a discovered Config Data document | **Processed during loading** | Imports additional files, config trees, or supported sources |
| `spring.config.location` present only in `application.yaml` found via defaults | **Too late to change the initial search list** | Move to an early source |
| `@PropertySource` on a `@Configuration` class | **Too late** | Do not use to choose `spring.config.location` |
| `@ConfigurationProperties`, `@Value`, `@PostConstruct`, runners | **Too late** | Use only to consume already-loaded configuration |

This diagram is a conceptual model of critical ordering, not every Spring Framework callback and listener. When libraries register custom `EnvironmentPostProcessor`s, exact ordering also depends on `Ordered` and registration order.

## 3. Three Keys That Must Be Supplied Early to Choose Name/Location

### 3.1. `spring.config.name`: changing the file base name

By default Spring Boot looks for the name `application`, meaning files such as:

```text
application.properties
application.yaml
application.yml
application-dev.properties
application-dev.yaml
...
```

To search for `service.yaml` or `service.properties`, pass it before startup:

```bash
java -jar myapp.jar --spring.config.name=service
```

When the `dev` profile is active, corresponding profile variants such as `service-dev.yaml` are also evaluated according to Config Data rules.

You can pass multiple comma-separated base names if the design needs more than one group of files:

```bash
java -jar myapp.jar --spring.config.name=common,service
```

**Wrong timing:** putting `spring.config.name=service` in `application.properties` and expecting Spring Boot to drop `application` and re-discover all configuration like a fresh bootstrap. To route initial discovery to `service`, that configuration must come from an early source.

### 3.2. `spring.config.location`: replacing default search locations

Without customization, Spring Boot searches for Config Data in typical default locations:

```text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
```

`spring.config.location` **replaces** the default location set with the set you specify. For example:

```bash
java -jar myapp.jar \
  --spring.config.location=optional:classpath:/config/,optional:file:./deployment/
```

In this example the loader uses the provided locations, interpreting `classpath:/config/` and `file:./deployment/` as directories; if you specify only `file:./deployment/` without a classpath location, packaged configuration at default locations may no longer be searched as before.

**Two syntax reminders:**

1. **Directory locations must end with `/`**, e.g., `file:./deployment/`. When pointing to a directory, Spring Boot appends the base name from `spring.config.name` and supported extensions.
2. **Specific file locations** must name the file explicitly, e.g., `file:./deployment/service.properties`; do not add a trailing `/`. Explicit locations and profile variants are handled by Config Data rules, not merely manual string concatenation.

`file:./...` is resolved against the **working directory of the Java process**, not automatically against the directory containing the JAR. If run from a different working directory, relative files may not be found.

### 3.3. `spring.config.additional-location`: keeping defaults and adding locations

If you want to **keep the default locations** while also loading files outside the JAR, prefer:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deployment/
```

Spring Boot still searches default configurations while adding `./deployment/` at the appropriate Config Data precedence tier. Additional locations are processed **after default locations** and can override matching keys in the default files.

Example layout:

```text
myapp.jar
deployment/
  application.properties
```

Inside the JAR:

```properties
# Packaged application.properties
app.title=Catalog
app.timeout=3s
```

File outside the JAR:

```properties
# deployment/application.properties
app.timeout=8s
```

Running with `--spring.config.additional-location=optional:file:./deployment/` from the directory containing `deployment` produces `app.title=Catalog` and `app.timeout=8s`, assuming no higher-precedence source overrides it.

There is no need to switch to `spring.config.location` when you only want to add places to read from. `additional-location` clearly conveys the intent to inherit existing configuration and override needed values at deployment time.

## 4. How to Pass Values Early Enough: Practical Examples

### 4.1. Command-line arguments `--spring.config.*`

```bash
java -jar myapp.jar \
  --spring.config.name=service \
  --spring.config.additional-location=optional:file:./deploy/
```

`--key=value` arguments must be in the argument array passed to `SpringApplication.run(args)`. By default Spring Boot adds them as a high-precedence `PropertySource` during bootstrap. If application code calls `setAddCommandLineProperties(false)`, you can no longer rely on this command-line property source.

In an IDE, you can configure the **Program arguments** field:

```text
--spring.config.additional-location=optional:file:./deploy/
```

This is a program argument, not a JVM option.

### 4.2. JVM system properties `-D`

```bash
java \
  -Dspring.config.name=service \
  -Dspring.config.additional-location=optional:file:./deploy/ \
  -jar myapp.jar
```

Place `-D` options **before `-jar`** so the JVM picks them up as system properties. This is useful when the application runner lets you configure JVM arguments.

In an IDE, you can put:

```text
-Dspring.config.additional-location=optional:file:./deploy/
```

into the **VM options** field.

### 4.3. OS environment variables

Standard environment variable names for relaxed binding are formed by replacing dots with `_`, removing `-`, and uppercasing:

```text
spring.config.name                → SPRING_CONFIG_NAME
spring.config.location            → SPRING_CONFIG_LOCATION
spring.config.additional-location → SPRING_CONFIG_ADDITIONALLOCATION
```

Unix-like shell example:

```bash
SPRING_CONFIG_NAME=service \
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./deploy/ \
java -jar myapp.jar
```

Or configure these variables in the container/Kubernetes runtime environment before the Java process is created. The values must exist when Java begins bootstrapping; modifying environment variables in a shell **after** the application has started will not make it reload Config Data locations.

On Windows PowerShell, you can set them for child processes:

```powershell
$env:SPRING_CONFIG_NAME = "service"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "optional:file:./deploy/"
java -jar myapp.jar
```

### 4.4. Configuring in Java before `run(...)`

If you need a launcher-bound default:

```java
import java.util.Map;
import org.springframework.boot.SpringApplication;

public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DemoApplication.class);
        app.setDefaultProperties(Map.of(
            "spring.config.additional-location", "optional:file:./deploy/"
        ));
        app.run(args);
    }
}
```

The call to `setDefaultProperties(...)` happens **before `run(...)`**, so `Environment` can see it when the Config Data loader begins processing. This is a **low-precedence default**, so other sources such as OS environment, JVM `-D`, or command line can override it. If you want operators to easily change configuration locations per environment, external parameter mechanisms are usually more flexible.

Some framework integrations construct `SpringApplicationBuilder`; the principle remains **putting the value into `Environment` before Config Data is processed**, rather than relying on code running after context refresh.

## 5. How Does `spring.config.import` Differ?

`spring.config.import` is not a request to "re-discover all files from scratch." It is an instruction to **add a Config Data source from an already-loaded document**. Therefore, it can appear right inside `application.properties` or `application.yaml`:

```properties
# src/main/resources/application.properties
app.name=api
spring.config.import=optional:file:./deploy/overrides.properties
```

```properties
# ./deploy/overrides.properties
app.name=api-deployed
app.connect-timeout=6s
```

In this example, Spring Boot first finds `application.properties` through default locations, then reads `spring.config.import` and imports `./deploy/overrides.properties`. Values from imported data take precedence over matching keys in the document that declared the import. The result is `app.name=api-deployed` unless overridden by a higher PropertySource.

**YAML equivalent:**

```yaml
app:
  name: api
spring:
  config:
    import: "optional:file:./deploy/overrides.properties"
```

Multiple locations can be imported:

```properties
spring.config.import=optional:file:./defaults.properties,optional:file:./override.properties
```

An import declared **later** takes precedence over an earlier import when conflicts occur under Config Data rules. Where the `spring.config.import` line appears inside the document does not give it special intra-file precedence; the loader processes it as a directive of the whole document.

### `spring.config.import` only works after the file containing it is found

If you put `spring.config.import` inside `./custom/application.yaml`, yet `./custom/` is not in the searched locations and was not added via `spring.config.additional-location`, that import itself **cannot help the loader discover the ignored file**.

Proper workflow:

1. Use an early source to ensure the file declaring the import is found, **or** place `spring.config.import` in a file already loaded by default.
2. Once that file is read, the loader resolves the imports declared inside it.
3. Ordinary properties from the imported file become part of `Environment` in Config Data precedence order.

Beyond `.properties`/YAML files, Spring Boot can import sources such as `configtree:` where appropriate; the requirement remains that **a valid Config Data document is loaded first so its import directive is discovered**.

## 6. Profiles and When `application-{profile}.*` Is Selected

During the same Config Data phase, Spring Boot determines the active profiles and uses them to select matching configuration documents.

**Shared configuration example:**

```yaml
# application.yaml
spring:
  profiles:
    active: dev
app:
  mode: base
```

**Profile-specific file example:**

```yaml
# application-dev.yaml
app:
  mode: development
```

When the `dev` profile is active, `application-dev.yaml` can override `app.mode` with `development`.

Profiles can be chosen from an early source:

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

A value from a high-precedence source such as the command line can override `spring.profiles.active` in the shared file, thereby changing which profile-specific files are evaluated during the Config Data phase.

**Limits to remember:**

- `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and similar profile-control properties **must not be used inside profile-specific documents or documents activated by `spring.config.activate.on-profile`** where Spring Boot prohibits it. Do not put `spring.profiles.active=prod` inside `application-dev.properties` hoping to switch profiles again.
- `spring.config.activate.on-profile` conditionally activates **a Config Data document** based on current profiles; it does not replace early location selection.
- `spring.config.import` can appear inside an appropriate Config Data document; when that document participates in loading, the related import is also processed under Config Data rules.
- If multiple profiles are active simultaneously, document loading order across profiles and location groups affects the final value; this is an **in-Config-Data** precedence rule, distinct from when `spring.config.location` is supplied.

Multi-document YAML example:

```yaml
# application.yaml — shared document
app:
  endpoint: https://api.example.test
---
spring:
  config:
    activate:
      on-profile: dev
app:
  endpoint: http://localhost:8081
```

With the `dev` profile, the second document is activated and can override `app.endpoint`. The shared document can declare imports; profile-specific documents can hold profile-only configuration. Use `---` to separate YAML documents; do not mix `.properties` separator syntax.

## 7. `optional:` and Handling Non-Existent Locations

A specified location that does not exist can cause startup to fail with a Config Data error, such as `ConfigDataLocationNotFoundException`.

For example:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

`optional:` allows a **specific location** to be absent without failing startup merely because that location does not exist. If other files are found and loaded, they participate in PropertySources normally.

`optional:` can be applied to imports:

```properties
spring.config.import=optional:file:./local.properties
```

Omit `optional:` if the file is truly a mandatory dependency and should fail early when missing.

Spring Boot also provides `spring.config.on-not-found=ignore` to ignore missing-location errors broadly; this setting must be supplied early enough for Config Data processing. However, placing `optional:` on individual locations usually clarifies intent and avoids silently skipping essential files.

**Note:** `optional:` skips missing-location errors. It does not turn invalid syntax, permission errors, invalid data, or binding failures into valid configuration.

## 8. Precedence Order: Early Supply Does Not Guarantee Final Value

**When** a source is supplied and **how high its precedence is** are two separate concepts.

In Spring Boot 3.3, considering familiar sources in a normal application run, typical precedence order for the same key is:

```text
(defaultProperties) < @PropertySource < Config Data
                    < OS environment < Java -D
                    < SPRING_APPLICATION_JSON < --command-line
```

This is an abridged view of the full default PropertySource list; sources like `random.*`, JNDI, Servlet init params, tests, and Devtools also have their own tiers.

For example:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./from-env/ \
java -Dspring.config.additional-location=optional:file:./from-jvm/ \
  -jar myapp.jar \
  --spring.config.additional-location=optional:file:./from-cli/
```

For **the same key** `spring.config.additional-location`, the command line has higher precedence than JVM properties and environment variables, so the effective value is `optional:file:./from-cli/` under default rules.

However, **a Config Data file loaded later cannot use `spring.config.location` inside itself to alter a bootstrap decision that has already happened**. It can contain ordinary application properties and `spring.config.import`, but it must not be treated as a source to restart search-location selection.

An accurate mental model:

1. **Before Config Data:** early sources supply `name/location/additional-location`; Spring Boot determines the initial search paths from the effective values in those sources.
2. **During Config Data:** the loader reads files, processes imports/profiles, and orders Config Data PropertySources.
3. **After loading:** properties present in `Environment` are resolved according to actual precedence; an application property like `server.port` can still be overridden by a command-line or JVM system property.

Therefore, if you need to change where configuration is loaded per deployment environment, place **bootstrap keys** in a source ready before the Config Data stage, and use `additional-location`/`import` appropriately to manage configuration content.

## 9. Cases Where "Configuration Exists, Yet Spring Boot Doesn't Pick It Up"

### Scenario A — Putting `spring.config.location` in the default file

```properties
# src/main/resources/application.properties
spring.config.location=file:./server-config/
```

**Wrong expectation:** Boot reads this file, then searches `./server-config/` instead and replaces the initial locations.

**Explanation:** initial locations were already decided before the file was loaded; a location-changing directive inside the file is not a search-redirect mechanism. If the application must read `./server-config/`, move `spring.config.location` or `spring.config.additional-location` to the command line, JVM, or OS environment.

### Scenario B — `@PropertySource` declaring the path

```java
@Configuration
@PropertySource("classpath:bootstrap.properties")
class EarlyProperties {
}
```

In `bootstrap.properties`:

```properties
spring.config.name=service
```

**Problem:** `@PropertySource` is added during context refresh, later than the Config Data processing stage. Do not rely on `@PropertySource` to control which files get loaded. This is also one reason Spring Boot recommends supplying keys like `logging.*` and `spring.main.*` from sufficiently early sources when behavior must occur before refresh.

### Scenario C — Changing environment variables after the process is running

```bash
# application is already running in another terminal or container
export SPRING_CONFIG_LOCATION=file:./new-location/
```

Modifying a shell's environment **does not modify the Environment of a running Java process**. You must start a new process (or build a dedicated configuration refresh mechanism with appropriate semantics) for the new Config Data location choice to take effect.

### Scenario D — Using a relative path with a different working directory

```bash
java -jar /opt/apps/myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

If run from `/home/operator`, the location is `/home/operator/deploy/`, not `/opt/apps/deploy/`. Use an absolute path or pin the working directory in the service manager or container manifest when determinism is required.

### Scenario E — Using `location` instead of `additional-location`

```bash
java -jar myapp.jar --spring.config.location=file:./deploy/
```

Here the author may accidentally **replace all default locations**, causing `application.properties` packaged in the JAR to no longer be searched as expected. When you only want to add deployment configuration alongside packaged configuration, use:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

### Scenario F — The configuration file containing `import` is not loaded itself

```text
conf/hidden/application.yaml
  spring.config.import: file:./extra.properties
```

If `conf/hidden/` is not a searched location, Boot never reads this import line. First, the **file containing the import** must be loaded. Import is not a mechanism that automatically searches every file on disk.

### Scenario G — Setting `spring.config.*` from a bean in `@PostConstruct`

```java
@PostConstruct
void init() {
    System.setProperty("spring.config.name", "service");
}
```

This call runs after the bean is created, far too late for the Config Data stage. It may change a JVM property at that later time, but it does not cause Boot to restart file discovery and loading for the current startup.

## 10. When Should You Write a Custom `EnvironmentPostProcessor`?

`EnvironmentPostProcessor` allows extending how `Environment` is prepared before context creation/refresh. However, **not every implementation runs before the Config Data processor**: they have an `Ordered` order and are invoked by Spring Boot in the Environment processing chain.

If you need to add a property **for `ConfigDataEnvironmentPostProcessor` to read**, your implementation must be **registered and run earlier** than the Config Data processor; simply writing an `EnvironmentPostProcessor` and setting a property is not enough. In addition, if you want to load a new configuration format as part of Config Data, you may need an appropriate `ConfigDataLocationResolver`/`ConfigDataLoader`, depending on the goal.

For simply passing a file path in a deployment environment, the command line, `-D`, OS environment, or `setDefaultProperties` before `run` is simpler and clearer. The extension points above are for framework/launcher requirements that genuinely need customization.

Do not use `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct`, or `@Value` inside a bean to change `spring.config.location` for the same startup.

## 11. How to Check Where Configuration Was Loaded From

1. **Identify bootstrap values before startup.** Record command-line options, JVM `-D` flags, `SPRING_CONFIG_*` variables, and `SpringApplication` setup before `run`.
2. **Distinguish `location` and `additional-location`.** Check whether the default location set was unintentionally dropped.
3. **Check `spring.config.name`.** If the base name was changed to `service`, do not look at `application.yaml` by habit and miss `service.yaml`.
4. **Verify the working directory.** For `file:./...`, check the actual directory the process uses, the trailing `/` on directory locations, and whether the file exists.
5. **Trace imports and profiles.** Imports are processed from the document containing them; profile-specific files participate only when the profile is active.
6. **Use logs when needed.** You can try `TRACE` logging for `org.springframework.boot.context.config` to observe Config Data loading (exact log detail depends on logging setup and initialization timing).
7. **Inspect post-startup results.** `Environment` or Actuator `env` can reveal effective values and actual PropertySource names; secure diagnostic endpoints and avoid logging sensitive configuration.

Example enabling logging at launch:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/ \
  --logging.level.org.springframework.boot.context.config=TRACE
```

However, startup logs are only a supporting aid; verifying paths must still rely on **values supplied before Config Data processing** and observed behavior.

## 12. Quick Reference Table

| Property | What Is It For? | Where Should It Be Declared? | Why? |
| --- | --- | --- | --- |
| `spring.config.name` | Choose base name instead of `application` | CLI `--`, JVM `-D`, OS env, default properties before `run` | Must know file name before searching |
| `spring.config.location` | **Replace** default locations | CLI/JVM/OS env or sufficiently early launcher | Must know where to look before reading Config Data |
| `spring.config.additional-location` | **Add** locations to defaults | CLI/JVM/OS env or sufficiently early launcher | Must add search locations before reading files |
| `spring.config.import` | Import extra Config Data from an already-found document | `application.properties`/YAML or suitable Config Data source | Read **during** Config Data processing |
| `spring.config.activate.on-profile` | Activate a document by profile | Inside a Config Data document | Condition for selecting the document being processed |
| `spring.profiles.active` | Determine active profiles | External source or valid shared document | Selects profile variants during Config Data, respecting profile-specific restrictions |
| `spring.config.on-not-found` | Policy for handling missing locations | Source sufficiently early for Config Data | Must be known when handling location errors |
| `app.*`, `server.port`, etc. | Application configuration values | Config Data files, OS env, JVM, CLI... | Consumed once the corresponding source is in `Environment` |

## 13. Complete Deployment Scenario

Suppose an application has this layout:

```text
myapp.jar
deployment/
  application-prod.properties
extras/
  feature-flags.properties
```

File packaged inside the JAR:

```properties
# classpath:/application.properties
app.name=order-service
app.timeout=3s
spring.config.import=optional:file:./extras/feature-flags.properties
```

Imported file:

```properties
# ./extras/feature-flags.properties
app.feature.new-checkout=true
```

Profile-specific file outside the JAR:

```properties
# ./deployment/application-prod.properties
app.timeout=10s
```

Command line:

```bash
java -jar myapp.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./deployment/
```

**Loading sequence:**

1. Before Config Data, `Environment` already received `spring.profiles.active=prod` and `spring.config.additional-location=optional:file:./deployment/` from the command line.
2. The loader searches the default locations plus `./deployment/` according to the early-supplied value.
3. While reading `classpath:/application.properties`, the loader sees `spring.config.import` and loads `./extras/feature-flags.properties` if the file exists.
4. Since profile `prod` is active, `./deployment/application-prod.properties` joins the corresponding Config Data group.
5. After loading, `app.name` comes from the file inside the JAR, `app.feature.new-checkout` from the imported file, and `app.timeout` is `10s` from the profile-specific file outside the JAR, unless overridden by a higher-precedence source.

This example combines **early bootstrap configuration**, **importing from a discovered file**, and **profile overrides in an additional location** in a single startup.

## 14. References

- Spring Boot 3.3 Reference — *Externalized Configuration*, sections **Config Data Files**, **Optional Locations**, **Wildcard Locations**, **Profile Specific Files**, **Importing Additional Data**, **PropertySource Order**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigDataEnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.3 Reference — *Application Events and Listeners*, *EnvironmentPostProcessor*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Takeaway:** `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are **inputs for selecting files**, so they must be available **before the Config Data loader decides where to search**. `spring.config.import` is a **directive inside a discovered file**, so it is processed while that file is being loaded. Distinguishing these two moments prevents most errors where "`spring.config.*` was declared, yet Spring Boot failed to read the expected configuration."