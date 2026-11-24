# Importing Properties or YAML Files from Classpath and File System

Spring Boot supports **Config Data Import** so that a configuration file being loaded can declare additional `.properties` or `.yml`/`.yaml` files as configuration sources for the application. This feature is especially useful when you want to separate shared configuration, feature-group parameters, operational configuration outside the JAR, or environment-specific values into clearly purposed files.

The focus of this lesson is the **`spring.config.import`** key: where to write it, how to import files from the **classpath** and **file system**, how paths are resolved, what precedence imported sources have, how missing files are handled, and how it interacts with profiles. Examples use the Config Data mechanism from Spring Boot 2.4 and later, including Spring Boot 3.x.

## 1. Config Data loading flow map

~~~text
Startup arguments / runtime environment
        |
        v
Spring Boot prepares Environment and locates initial Config Data
        |
        v
application.properties / application.yml
        |
        +-- spring.config.import=classpath:defaults/client.yml
        |              |
        |              +-- Reads file located on the classpath
        |
        +-- spring.config.import=optional:file:./config/local.properties
                       |
                       +-- Reads external file from the file system
        |
        v
Merge PropertySources by precedence and active profiles
        |
        v
Environment -> @Value / @ConfigurationProperties / configuration conditions
        |
        v
Beans consume the effective values
~~~

An import is part of **configuration preparation during application startup**. It is not a Java command that reads a file inside a service, nor is it an automatic file watcher for changes while the application is running. Spring Boot processes import locations, configuration documents, and profiles before configuration-dependent beans are initialized.

**One sentence to remember:** a file being loaded can declare `spring.config.import` to instruct Spring Boot to load additional Config Data at a specified location, then combine the imported file's keys into `Environment`.

## 2. Requirements for import to work

A Spring Boot project typically has a root configuration file:

~~~text
order-service/
  src/
    main/
      java/
      resources/
        application.yml
~~~

The root file in `src/main/resources` is packaged onto the classpath when building a Java application using standard structure. Spring Boot automatically recognizes `application.properties` or `application.yml` files in the default configuration locations.

To **import an additional file**, place the `spring.config.import` property inside a Config Data document currently being loaded by Spring Boot. For example:

~~~properties
# application.properties
spring.config.import=classpath:defaults/client.properties
~~~

or:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:defaults/client.yml"
~~~

From here, Spring Boot locates and loads the declared location. An imported file does not have to be named `application.properties` or `application.yml`: you can use purpose-driven names such as `client-defaults.yml`, `mail.properties`, or `regional-overrides.yaml`.

However, **merely placing a file on the classpath or in a directory outside the JAR is not enough for Spring Boot to import it automatically**. The file must be discovered through the default Config Data mechanism, specified via an appropriate location setting, or referenced by `spring.config.import`.

## 3. Two common path sources: classpath and file

| Prefix | Meaning | Example |
| --- | --- | --- |
| `classpath:` | Locates a resource via the application classpath | `classpath:defaults/client.yml` |
| `file:` | Locates a file via a file system path | `file:./config/local.properties` |
| No prefix | Relative location resolved against the location of the file declaring the import | `client-overrides.yml` |
| `optional:` before the location | Allows skipping when the location does not exist | `optional:file:./config/local.properties` |

### 3.1. Importing from classpath

Suppose the project has:

~~~text
order-service/
  src/main/resources/
    application.yml
    defaults/
      client.yml
      cache.properties
~~~

In `application.yml`:

~~~yaml
spring:
  config:
    import: "classpath:defaults/client.yml"
~~~

In `src/main/resources/defaults/client.yml`:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

Spring Boot loads keys such as `app.client.base-url` and `app.client.connect-timeout` into the configuration system. When the application is packaged, `defaults/client.yml` can live inside the JAR; the `classpath:` syntax still applies because the application's class loader locates that resource.

A properties-file version is also valid:

~~~properties
# src/main/resources/defaults/cache.properties
app.cache.ttl=20m
app.cache.maximum-size=64MB
~~~

~~~properties
# application.properties
spring.config.import=classpath:defaults/cache.properties
~~~

With `classpath:`, Spring Boot looks for **resources visible to the class loader**, not files relative to the directory where the user stands when invoking `java -jar`.

### 3.2. Importing from the file system

Suppose deployment files are organized as follows:

~~~text
order-service/
  order-service.jar
  config/
    client-overrides.properties
~~~

In the main Config Data document:

~~~properties
spring.config.import=optional:file:./config/client-overrides.properties
~~~

File outside the JAR:

~~~properties
# ./config/client-overrides.properties
app.client.base-url=https://internal-api.example.test
app.client.connect-timeout=800ms
~~~

In an example run from the `order-service/` directory:

~~~bash
java -jar order-service.jar
~~~

`file:./config/client-overrides.properties` references the file via a file system path relative to **the process's working directory**. If the same JAR is launched from a different working directory, `./config/...` may point elsewhere. Therefore, when deployment configuration is not found, check the actual working directory of the process, container, or service manager.

You can use an absolute path on a Unix-like system:

~~~properties
spring.config.import=file:/etc/order-service/client-overrides.yml
~~~

Absolute paths differ across Linux, macOS, and Windows. With Docker/Kubernetes, verify that the mount path actually exists **inside the container's filesystem**; a path on the host machine does not automatically appear inside the container unless mounted.

## 4. Writing spring.config.import in properties and YAML

### Single file

~~~properties
spring.config.import=classpath:config/client.properties
~~~

~~~yaml
spring:
  config:
    import: "classpath:config/client.yml"
~~~

### Multiple files in one declaration

`spring.config.import` can accept a comma-separated list of locations in properties:

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-local.properties
~~~

In YAML, you can use a comma-separated string:

~~~yaml
spring:
  config:
    import: "classpath:defaults/client.yml,optional:file:./config/client-local.yml"
~~~

Or a YAML list with one location per line:

~~~yaml
spring:
  config:
    import:
      - "classpath:defaults/client.yml"
      - "optional:file:./config/client-local.yml"
~~~

Both YAML styles describe the import locations. For locations containing `:`, quotes in YAML help both readers and the parser treat the value as a string. In `.properties` files, `:` after the first `=` is part of the value and does not require quotes.

**The order of imports in the same list matters when keys collide:** locations imported later have higher precedence than locations imported earlier, according to Config Data Import rules. You must also inspect external configuration sources and active profiles before determining the application's final value.

## 5. Complete example: defaults in the JAR and overrides outside the JAR

This is a common scenario when the same artifact is run across multiple environments.

~~~text
order-service/
  src/main/resources/
    application.yml
    defaults/
      client.yml
  config/
    client-local.yml
~~~

**Step 1 — Main file `application.yml`:**

~~~yaml
spring:
  application:
    name: order-service
  config:
    import:
      - "classpath:defaults/client.yml"
      - "optional:file:./config/client-local.yml"

app:
  client:
    connect-timeout: 5s
    max-retries: 1
~~~

**Step 2 — Default values on the classpath:**

~~~yaml
# src/main/resources/defaults/client.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

**Step 3 — Override file outside the JAR:**

~~~yaml
# ./config/client-local.yml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 750ms
~~~

If the process runs with a working directory containing the `./config` directory above and no higher-precedence source exists, the effective values table in this example is:

| Key | `application.yml` | `defaults/client.yml` | `config/client-local.yml` | Effective value |
| --- | --- | --- | --- | --- |
| `app.client.base-url` | Not declared | `https://api.example.test` | `http://localhost:8090` | `http://localhost:8090` |
| `app.client.connect-timeout` | `5s` | `3s` | `750ms` | `750ms` |
| `app.client.max-retries` | `1` | `2` | Not declared | `2` |

A very easy-to-miss point: **imported Config Data has higher precedence than the document that declared the import**. Therefore, `max-retries=2` in `defaults/client.yml` beats `max-retries=1` in `application.yml` in this example. The second import can in turn override keys from the first import.

In this example, if `./config/client-local.yml` does not exist, the `optional:` keyword allows skipping that location; the remaining values still load normally. In that case `app.client.base-url` is `https://api.example.test` and `app.client.connect-timeout` is `3s`, assuming no other source overrides them.

For the external file to actually be used, you must maintain the exact **path** and **working directory** in the run command. When working with source files in an IDE, `./config/client-local.yml` does not necessarily get copied into the JAR and does not need to be copied if you want to keep customization outside the artifact.

## 6. Precedence: what does import beat and what can override it?

Spring Boot prepares `PropertySource` objects with a precedence order. When the same key exists in multiple sources, the value belonging to the highest-precedence source is the one the application receives.

For normal imports:

1. An imported document is placed in the Config Data chain near the document declaring `spring.config.import`.
2. **Values from the imported document take precedence over values in the importing document**.
3. If a single declaration imports multiple locations, **imports declared later can override values from earlier imports**.
4. If a location imports a file that has profile-specific versions, activating a profile can change the set of loaded documents and the resulting precedence.
5. Sources outside the Config Data group, such as command-line arguments, can have higher precedence and override existing values.

Example:

~~~properties
# application.properties
spring.config.import=classpath:config/common.properties
app.scheduler.enabled=false
~~~

~~~properties
# config/common.properties
app.scheduler.enabled=true
~~~

With these two documents and no other overriding source, Spring Boot sees `app.scheduler.enabled=true` as the effective value. Do not reason along the lines of "because `application.properties` is the main file, the line in it always wins."

When running:

~~~bash
java -jar order-service.jar --app.scheduler.enabled=false
~~~

The command-line argument can override it so the effective value is `false` in this situation.

### Can imports load repeatedly in an infinite loop?

Spring Boot tracks imported Config Data documents and does not load the same document infinitely just because multiple places reference the same location. That does not mean every complex import graph should be used: a shallow structure, transparent paths, and a design free of circular references remain much easier to maintain.

Confusing configurations often arise when multiple files define the same key and nest multiple levels of imports. Assign clear roles to each file such as `defaults`, `region`, and `local override` so you can explain which source wins.

## 7. Fixed locations and relative locations

`spring.config.import` supports both **fixed location** and **import-relative location** syntax.

### Fixed location

A location is considered fixed when it starts with `/` or has a source prefix such as `classpath:` or `file:`:

~~~properties
spring.config.import=classpath:defaults/client.yml
~~~

~~~properties
spring.config.import=file:./config/client.yml
~~~

A fixed location is resolved according to the prefix mechanism rather than based on the location of the document declaring the import.

### Import-relative location

A location without a prefix can be resolved **relative to the directory of the document importing it**.

Suppose the classpath files are:

~~~text
src/main/resources/
  application.properties
  features/
    checkout.properties
    rules.properties
~~~

File `features/checkout.properties`:

~~~properties
spring.config.import=rules.properties
app.checkout.enabled=true
~~~

When `features/checkout.properties` has been loaded from the classpath and declares `rules.properties`, Spring Boot resolves the relative reference at the same corresponding directory location, namely the resource `features/rules.properties`.

If the same `spring.config.import=rules.properties` line appears in another file in a different directory, the inferred location may differ. This is why you must know **which file declares the import**, rather than blindly copying an import value from an example into another location.

**To avoid confusion in deployment instructions:** use explicit `classpath:` or `file:` prefixes when you want to state the exact source and path; use import-relative intentionally when files are packaged together as a group in the same directory.

## 8. Missing files: optional: and startup failures

Not every imported file is always present. Default configuration bundled with the application should usually be mandatory; override files specific to developers or individual environments can often be optional.

### Mandatory import

~~~properties
spring.config.import=file:./config/required-client.properties
~~~

If a mandatory location cannot be found, Spring Boot may stop startup with an error related to `ConfigDataLocationNotFoundException` or a message stating that the required location could not be found. This helps prevent silently running with missing configuration.

### Optional import

~~~properties
spring.config.import=optional:file:./config/local.properties
~~~

If `./config/local.properties` does not exist, Spring Boot **skips that location** instead of stopping solely because the location is missing. However, `optional:` **does not fix syntax errors**, severe access errors, or required values missing from beans after loading. It only expresses the allowed absence of the configuration source.

You can use `optional:` with classpath:

~~~properties
spring.config.import=optional:classpath:defaults/preview.properties
~~~

Recommended usage rules:

| File type | Typical appropriate import | Reason |
| --- | --- | --- |
| Essential defaults packaged with the application | `classpath:defaults/client.yml` | A missing file indicates broken packaging |
| Developer machine overrides | `optional:file:./config/local.properties` | Other machines may not have it |
| Mandatory config supplied by deployment environment | `file:/etc/order-service/runtime.properties` | Should fail if missing |
| Experimental file not used in every environment | `optional:classpath:config/experiment.yml` | Allows intentional absence |

Choosing `optional:` is an operational decision: if the system cannot run safely without the file, keep the import mandatory and define validation for required keys.

## 9. How do profiles affect imported files?

Config Data Import integrates into Spring Boot's **profile-specific configuration** processing. When an import points to a resource that has matching profile-specific versions, Spring Boot can also consider profile-specific variants of that location.

Example:

~~~text
src/main/resources/
  application.properties
  config/
    client.properties
    client-dev.properties
    client-prod.properties
~~~

Main file:

~~~properties
spring.config.import=classpath:config/client.properties
~~~

Base file:

~~~properties
# config/client.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
~~~

`dev` profile file:

~~~properties
# config/client-dev.properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=500ms
~~~

`prod` profile file:

~~~properties
# config/client-prod.properties
app.client.base-url=https://internal-api.example.test
app.client.connect-timeout=2s
~~~

When running:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Spring Boot considers the variant matching the active profile and can use the values from `client-dev.properties`. When the `prod` profile is active, the `client-prod.properties` variant is considered.

If a value appears in multiple documents or multiple profiles are active at once, the result must be evaluated according to Config Data rules and actual profile order. **Profiles do not mean an arbitrary file with a `-prod` suffix is automatically loaded:** the file must still lie within the scope of a location loaded or imported by Spring Boot.

### Profile-only imports

You can declare an import inside a profile-activated YAML document:

~~~yaml
# application.yml
spring:
  application:
    name: order-service
  config:
    import: "classpath:defaults/client.yml"

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev-client.yml"
~~~

The section below the `---` separator is applied only when the `dev` condition matches. Only then does Spring Boot evaluate this document's import of `./config/dev-client.yml`.

In YAML, `---` is the document separator. In `application.properties`, Spring Boot supports a special Config Data document separator written as `#---`:

~~~properties
spring.config.import=classpath:defaults/client.properties

#---
spring.config.activate.on-profile=dev
spring.config.import=optional:file:./config/dev-client.properties
~~~

Do not put `spring.profiles.active` inside a document already constrained by `spring.config.activate.on-profile`; the profile activation mechanism restricts which sources are permitted to specify active profiles.

## 10. When extension hints are needed for extensionless files

Some configuration sources are mounted into containers under filenames without `.properties` or `.yaml` extensions. Spring Boot Config Data supports **extension hints** to specify the format of an imported file.

For example, an external file outside the JAR at `/etc/order-service/client-config` actually contains YAML:

~~~yaml
app:
  client:
    connect-timeout: 2s
~~~

It can be imported with:

~~~properties
spring.config.import=file:/etc/order-service/client-config[.yaml]
~~~

The `[.yaml]` syntax is an **extension hint**, not a requirement to name the actual file `client-config[.yaml]`. It tells Spring Boot to read the content using the YAML format even though the filename has no extension.

If the file has a standard extension such as `client.properties`, `client.yml`, or `client.yaml`, a hint is normally unnecessary.

## 11. Comparing import with spring.config.location and additional-location

The three mechanisms are related but serve different purposes:

| Mechanism | Role | Example |
| --- | --- | --- |
| `spring.config.import` | A Config Data document being loaded declares additional sources to import | `spring.config.import=classpath:defaults/client.yml` |
| `spring.config.location` | Specifies the locations used to search for default Config Data, replacing the default location set per Boot's rules | `--spring.config.location=file:./deploy/application.yml` |
| `spring.config.additional-location` | Adds locations alongside the default locations | `--spring.config.additional-location=optional:file:./extra-config/` |

Example passing a location at startup:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:./extra-config/
~~~

**Why not declare `spring.config.location` inside `application.yml` itself?** Properties that choose where to look for Config Data must be processed very early, before Spring Boot knows which `application.yml` file to read. Therefore, they belong in sources available from the start, such as command-line arguments, system properties, or appropriate environment variables. In contrast, `spring.config.import` is designed to reside inside an already loaded document and pull in related documents.

If you want a root file to import feature-based configuration files, `spring.config.import` is usually a good fit. If you want the deployment environment to decide **the initial configuration search directories**, consider `spring.config.additional-location` or `spring.config.location`.

## 12. How does a Java application read imported values?

After Spring Boot loads the locations, most application code does not need to know whether a key came from the classpath or the file system. Everything can be looked up via `Environment`:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientSettingsReader {
    private final Environment environment;

    public ClientSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public Duration timeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }

    public String baseUrl() {
        return environment.getProperty("app.client.base-url");
    }
}
~~~

When multiple keys belong to the same configuration group, bundle them into a bean:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Register the properties bean using `@ConfigurationPropertiesScan` on the Spring Boot application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Once configuration is bound, Java code can use `ClientProperties` with `URI`, `Duration`, and `int` types. The object reflects **the effective values determined by the configuration process**, rather than implying "data is always taken from `client.yml`."

### Does import automatically create beans?

A line like:

~~~properties
spring.config.import=classpath:defaults/client.properties
~~~

only feeds values into the configuration system. If the code declares no bean, uses no `@Value`, does not call `Environment`, and has no relevant auto-configuration, custom keys in the file do not turn into application behavior on their own.

A key like `server.port` can be used automatically by Spring Boot because the framework recognizes it. By contrast, `app.client.connect-timeout` is an application-defined key and must be consumed by application code.

## 13. A runnable JAR practice walkthrough

Suppose you have built `order-service.jar` with two classpath files:

~~~text
src/main/resources/
  application.properties
  defaults/
    client.properties
~~~

File `application.properties`:

~~~properties
spring.application.name=order-service
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-overrides.properties
app.client.max-retries=1
~~~

File `defaults/client.properties`:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Case A — no file outside the JAR:

~~~bash
java -jar order-service.jar
~~~

The client group values from the two files will be `base-url=https://api.example.test`, `connect-timeout=3s`, and `max-retries=2`, assuming no other source overrides them.

Case B — create an external file outside the JAR:

~~~text
./config/client-overrides.properties
~~~

Content:

~~~properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=900ms
~~~

Then launch from the matching working directory:

~~~bash
java -jar order-service.jar
~~~

The client group values become `base-url=http://localhost:8090`, `connect-timeout=900ms`, and `max-retries=2` according to the import rules in the example.

Case C — keep the external file and pass an additional argument:

~~~bash
java -jar order-service.jar --app.client.connect-timeout=100ms
~~~

Now `connect-timeout` has an effective value of `100ms` because command-line arguments have higher precedence in a typical startup scenario. This demonstrates that imports add data sources to `Environment`, while selecting the final value still depends on source ordering.

## 14. Troubleshooting import errors with a tracing workflow

When the application reports a missing file or unexpected configuration values, follow this sequence.

### A. Check exact location names and prefixes

Compare `classpath:config/client.yml` with the actual location on the classpath, or `file:./config/client.yml` with the actual location on the filesystem. Being off by one directory level can cause a location lookup failure.

Check whether the `.properties`, `.yml`, or `.yaml` extension is written accurately. If the file intentionally has no extension, use the appropriate extension hint mechanism.

### B. Verify the document declaring the import was actually loaded

If `spring.config.import` resides in a document active only for `dev`, yet the application runs `prod`, that import may not be applied. Confirm the process's actual active profiles before concluding the imported file is broken.

Similarly, if using relative import, verify the location **of the document declaring the import**, as it affects path resolution.

### C. Check the working directory for `file:./...`

In a container or service manager, the Java command may be invoked from a directory different from the one containing the JAR. `file:./config/client.yml` is a path relative to the process; it does not implicitly sit beside the JAR file.

For example, in a container you may need to mount configuration into `/app/config` and set the working directory to `/app`, or declare an accessible absolute path. Do not infer host paths from paths inside the container.

### D. Verify whether `optional:` reflects intent

Missing mandatory files must be fixed in the mount path, file path, or packaging pipeline. Use `optional:` only when a file's absence is legitimate. Do not slap `optional:` onto every error and ignore the fact that the application lacks critical parameters.

### E. Check for overridden keys

A successfully loaded file may still not supply the winning value because a higher-precedence source exists: a later import, a profile-specific variant, an environment variable, or a command-line argument.

Identify the **canonical key**, search every place that could declare that key, and inspect precedence. For instance, `app.client.connect-timeout` across three documents can differ without any syntax error.

### F. Check type conversion and validation errors

Values in YAML/properties after import are bound to Java types. A string `"abc"` is unsuitable for `Duration` if the application expects a duration; `max-retries=none` is unsuitable for `int`. These are data or target-type errors, not necessarily import path errors.

### G. Inspect using controlled diagnostic tools

If the application includes Spring Boot Actuator, the `env` and `configprops` endpoints—when properly configured and secured—can help trace sources and bound values. Sensitive values can be masked; never expose secrets or print tokens/passwords to logs for debugging.

Some versions/configurations can provide useful source or origin details during investigation. You can also enable appropriate diagnostic logging in test environments, while avoiding overly verbose logging in production unless needed.

## 15. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "A file in `src/main/resources/config` will be imported automatically because it has a YAML extension." | It must belong to a configuration search location or be referenced via an appropriate import. |
| "Classpath imports use the path of the directory where the Java command runs." | `classpath:` locates resources on the classpath, including resources packaged inside the JAR. |
| "`file:./config/...` always searches next to the JAR." | The `./` path depends on the process's working directory. |
| "The main `application.yml` file always beats the file it imports." | Imported values take precedence over the document that calls the import. |
| "If an imported file doesn't exist, Spring Boot always skips it." | By default, a mandatory location causes an error; `optional:` allows intentional absence. |
| "`optional:` ignores any configuration error." | It is meant for non-existent locations, not to cure conversion or validation errors. |
| "A profile-specific file only needs to exist to be used." | Active profiles and location search/import rules must cause the file to be loaded. |
| "Replacing a file outside the JAR updates beans immediately." | Config Data is normally processed at startup; dynamic refresh requires a separate mechanism. |
| "Importing automatically creates beans containing all `app.*` keys." | Importing only puts keys into configuration sources; the application decides how to consume them. |
| "`spring.config.import` is equivalent to `spring.config.location`." | One mechanism declares imports inside Config Data; the other selects where initial Config Data is searched. |

## 16. When to organize on the classpath vs. on the file system?

**Classpath configuration** fits defaults tied to the application version: recommended timeouts, default feature lists, and settings that normally do not change between environments. This gives the build artifact a clear, reproducible configuration baseline.

**External configuration outside the JAR** fits values decided by the deployment environment: service addresses, environment capacity parameters, feature flags, and integration paths. It lets you share a single JAR across multiple environments while configuration data is supplied at deployment time.

A common pattern is:

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-overrides.properties
~~~

If an external file outside the JAR must exist in production, use a mandatory import at the production location or check for missing configuration via validation. Do not store real passwords or API keys inside classpath files committed to a repository; use proper environment secret systems and file access permissions.

For sensitive configuration mounted as multiple files, Spring Boot also offers Config Tree Import (`configtree:`). That is a Config Data variant for directory structures containing individual keys; it differs from directly importing a YAML/properties file and is not required when you only need the two formats covered here.

## 17. Self-check exercises

### Scenario 1: importing from classpath

Given `src/main/resources/config/limits.properties`:

~~~properties
app.api.rate-limit=200
~~~

In `application.properties`:

~~~properties
spring.config.import=classpath:config/limits.properties
~~~

**Question:** which key is added to `Environment`? **Answer:** `app.api.rate-limit` with the string value `200`. A bean reading configuration can bind that value to a number.

### Scenario 2: external file outside JAR does not exist

~~~properties
spring.config.import=optional:file:./config/local.properties
~~~

**Question:** must missing this file stop startup? **Answer:** no, `optional:` allows skipping a missing location. However, if a bean still requires a key provided only by that file, the bean may fail later.

### Scenario 3: imported file and importing file share the same key

~~~properties
# application.properties
spring.config.import=classpath:defaults/retry.properties
app.retry.max-attempts=1
~~~

~~~properties
# defaults/retry.properties
app.retry.max-attempts=4
~~~

**Question:** when no other source overrides it, what is the effective value? **Answer:** `4`. The imported document takes precedence over the document declaring the import.

### Scenario 4: two import locations

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/local-client.properties
~~~

Suppose both files define `app.client.connect-timeout` and the external file outside the JAR actually exists.

**Question:** which value wins between the two imports? **Answer:** the value from `./config/local-client.properties`, because the later import has higher precedence in this example. A source with higher precedence than the entire Config Data group can still change the final outcome.

### Scenario 5: file location outside container

The application runs inside a container with working directory `/app`, while the deployer mounts the file to `/etc/service/runtime.yml`. Configuration still reads:

~~~properties
spring.config.import=file:./config/runtime.yml
~~~

**Question:** why might the import fail? **Answer:** Spring Boot looks for `/app/config/runtime.yml`, not `/etc/service/runtime.yml`. Fix the import to the actual path inside the container or adjust the mount/working directory.

### Scenario 6: profile variant

~~~properties
spring.config.import=classpath:config/client.properties
~~~

Both `client.properties` and `client-prod.properties` exist; the process runs with `--spring.profiles.active=prod`.

**Question:** does Boot read only the unsuffixed file? **Answer:** no. Config Data Import supports evaluating profile-specific variants of imported locations. Check the actually loaded values and precedence if multiple other documents also take effect.

## 18. Quick reference table

| Goal | Typical syntax |
| --- | --- |
| Import properties from classpath | `spring.config.import=classpath:config/common.properties` |
| Import YAML from classpath | `spring.config.import=classpath:config/common.yml` |
| Import properties outside JAR | `spring.config.import=file:./config/overrides.properties` |
| External file that may be absent | `spring.config.import=optional:file:./config/local.properties` |
| Multiple imports in order | `spring.config.import=classpath:defaults/a.yml,file:./config/b.yml` |
| YAML syntax for import | `spring.config.import: "classpath:defaults/a.yml"` |
| Import relative to declaring file | `spring.config.import=other.properties` |
| Extensionless file containing YAML | `spring.config.import=file:/etc/service/settings[.yaml]` |
| Add config directory from launch command | `--spring.config.additional-location=optional:file:./extra-config/` |
| Activate profile at runtime | `--spring.profiles.active=prod` |

For every import, answer in order: **where is the declaring file located → what prefix does the location have → how is the actual path resolved → is the file mandatory → which profiles are active → how does precedence determine the effective key → which bean will consume that value**. This is a concrete enough trace path to understand and operate configurations split across the classpath or file system.
