# Configuration in the Classpath, External Files, Environment Variables, and Command Line

A Spring Boot application typically has to run across multiple environments: a developer's machine, testing environments, staging, and production. The code may be identical, while service addresses, timeouts, log levels, or operational options differ. Spring Boot solves this through **externalized configuration**: separating configuration values from code and merging configuration sources via `Environment`.

Four very common sources are files on the **classpath**, configuration files **outside the application**, process **environment variables**, and **command-line arguments**. Understanding how Spring Boot locates, loads, and prioritizes these sources allows you to deploy the same JAR across environments without recompiling.

## 1. What does externalized configuration mean?

Suppose an application connects to a Catalog service. Values that need to vary by environment might include:

- `app.catalog.base-url`: address of the Catalog API.
- `app.catalog.connect-timeout`: connection timeout.
- `app.catalog.enabled`: whether Catalog integration is enabled.
- `logging.level.com.example.catalog`: log level for the related package.

Instead of hard-coding those values in Java, the application can use `application.yml`:

~~~yaml
app:
  catalog:
    base-url: https://catalog-dev.example.test
    connect-timeout: 3s
    enabled: true

logging:
  level:
    com.example.catalog: INFO
~~~

When running in production, an operator can change `app.catalog.base-url` or the timeout via an external file, environment variable, or command-line argument. Components read configuration through Spring rather than manually opening individual files to look up values.

Configuration sources are merged by Spring into a prioritized `Environment`. If a property appears in multiple sources, the higher-precedence source determines the value read.

## 2. Files on the classpath: configuration packaged with the application

The classpath is the set of locations the JVM and class loader use to find classes and resources. In a Spring Boot application, configuration files are usually placed in:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

When building the JAR, these resources are packaged with the application. Spring Boot can search standard configuration files on the classpath, including these common locations:

~~~text
classpath:/
classpath:/config/
~~~

For example, `src/main/resources/application.yml` usually becomes the `application.yml` resource on the application's classpath:

~~~yaml
spring:
  application:
    name: catalog-service

app:
  catalog:
    base-url: https://catalog-default.example.test
    connect-timeout: 5s
    enabled: true
~~~

Advantages of classpath configuration:

- Easy to ship default configuration alongside the software version.
- Every artifact always carries a sensible set of defaults.
- Suitable for non-sensitive options that are not tied to a single environment.
- Developers see the default configuration right in the source code.

The limitation is that modifying a packaged file directly is usually inconvenient. On servers, containers, or Kubernetes, keep the JAR immutable and use external sources to override environment-specific values.

### .properties and .yml

Spring Boot supports both Java properties and YAML:

~~~properties
spring.application.name=catalog-service
app.catalog.base-url=https://catalog-default.example.test
app.catalog.connect-timeout=5s
app.catalog.enabled=true
~~~

This is equivalent to the YAML representation above. Standardize on a single primary format for a given configuration location; if `.properties` and YAML coexist with the same base name in one location, the `.properties` file takes precedence.

YAML is convenient for hierarchical structures. Properties work well for lists of key-value pairs and situations where only a few lines need editing.

## 3. Files outside the JAR: deployment-environment configuration

Spring Boot also searches for configuration files on the filesystem outside the JAR. Default search locations typically include:

~~~text
file:./
file:./config/
file:./config/*/
~~~

`./` refers to the **current working directory** of the process, not necessarily the directory containing the JAR file. This distinction matters when running the application through a service manager, Docker, or a deployment pipeline.

For example:

~~~text
/opt/catalog/
├── catalog-service.jar
└── config/
    └── application.yml
~~~

When the process runs with `/opt/catalog` as its working directory, `/opt/catalog/config/application.yml` is an external configuration source that Spring Boot can discover.

Suppose the JAR contains:

~~~yaml
app:
  catalog:
    base-url: https://catalog-default.example.test
    connect-timeout: 5s
~~~

While `./config/application.yml` outside the JAR contains:

~~~yaml
app:
  catalog:
    base-url: https://catalog-prod.example.test
    connect-timeout: 2s
~~~

With these default sources, the values outside the JAR have higher precedence than the packaged values. The application will receive the production `base-url` and a `2s` timeout.

External files are suitable when:

- Operations wants to manage environment-specific values.
- Configuration needs to change without rebuilding the artifact.
- Configuration needs to be mounted into a container or Pod.
- Multiple related settings should be managed together in one file.

**Editing a file outside the JAR does not mean Spring Boot automatically reloads configuration at runtime.** In a typical application, values are loaded at startup and bound into beans when the context initializes; a restart or a purpose-built refresh solution is needed for subsequent changes to take effect.

## 4. Precedence order among sources

A practical rule of thumb in a typical Spring Boot application is:

| Precedence | Source | Example |
|---|---|---|
| 1 — lower | Packaged file on the classpath | `classpath:/application.yml` |
| 2 | External configuration file | `file:./config/application.yml` |
| 3 | Operating system environment variable | `APP_CATALOG_BASEURL` |
| 4 — higher | Spring Boot command-line argument | `--app.catalog.base-url=...` |

This table focuses on the **four sources covered in this lesson**. Spring Boot's `Environment` also includes other sources such as Java system properties, `SPRING_APPLICATION_JSON`, programmatically supplied defaults, and test-specific sources. They have their own precedence positions and in some cases sit between or above the sources shown in the table.

Within standard Config Data files, Spring Boot also distinguishes between regular files and profile-specific files, as well as packaged versus external resources. In ascending order of precedence:

1. `application` file packaged inside the JAR.
2. `application-{profile}` file packaged inside the JAR.
3. `application` file located outside the JAR.
4. `application-{profile}` file located outside the JAR.

A regular external file can therefore override values in a packaged profile-specific file. Do not assume that merely naming a file `application-prod.yml` guarantees it always beats every other source.

### Example with the same property appearing in four places

Suppose `app.catalog.connect-timeout` has these values:

| Source | Value |
|---|---|
| `classpath:/application.yml` | `5s` |
| `file:./config/application.yml` | `3s` |
| Environment variable `APP_CATALOG_CONNECTTIMEOUT` | `2s` |
| Command line `--app.catalog.connect-timeout=1s` | `1s` |

If all four sources apply, the effective value under normal rules is `1s` because the command-line argument has the highest precedence in this group.

If the command-line argument is omitted, the environment variable `2s` is used. If the environment variable is also omitted, the external file `3s` is used. Without external configuration, the application falls back to the packaged value `5s`.

Precedence lets operators change a specific property without copying the entire default configuration file.

## 5. Configuring with environment variables

Environment variables are passed to the process when the application launches. They are very useful in Docker, Kubernetes, CI/CD, and cloud deployment platforms because they can be set differently per instance without modifying the artifact.

Spring Boot supports relaxed binding: kebab-case property names are transformed to map to environment variables.

Common rule for converting a canonical property name to an environment variable:

1. Replace dots `.` with underscores `_`.
2. Remove dashes `-` inside each segment.
3. Convert to uppercase.

For example:

| Canonical property | Environment variable |
|---|---|
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `server.port` | `SERVER_PORT` |
| `app.catalog.base-url` | `APP_CATALOG_BASEURL` |
| `app.catalog.connect-timeout` | `APP_CATALOG_CONNECTTIMEOUT` |
| `app.catalog.enabled` | `APP_CATALOG_ENABLED` |

In a Linux/macOS terminal:

~~~bash
export APP_CATALOG_BASEURL=https://catalog-prod.example.test
export APP_CATALOG_CONNECTTIMEOUT=2s
export APP_CATALOG_ENABLED=true

java -jar catalog-service.jar
~~~

In Windows PowerShell:

~~~powershell
$env:APP_CATALOG_BASEURL = "https://catalog-prod.example.test"
$env:APP_CATALOG_CONNECTTIMEOUT = "2s"
$env:APP_CATALOG_ENABLED = "true"

java -jar catalog-service.jar
~~~

The values are present in the child process's environment when the application starts from that shell.

### Note on dashes

For `app.catalog.connect-timeout`, the correct environment variable under relaxed binding rules is `APP_CATALOG_CONNECTTIMEOUT`, not `APP_CATALOG_CONNECT_TIMEOUT`. Dashes in a property name are **removed**, not turned into extra underscores.

If the property is a list or map, binding rules for indices and keys have additional details. For complex configurations, use `@ConfigurationProperties` and verify the actual bound result instead of guessing environment variable names.

### When environment variables are read

Environment variables are normally read by Spring Boot during application startup. Changing a variable in another shell after the JVM is already running does not automatically update the running process's `Environment`.

To change values for the next run, configure the environment variables in your manifest, service definition, or execution environment and restart the application per your deployment process.

## 6. Configuring with command-line arguments

Spring Boot accepts application arguments in the form:

~~~text
--property.name=value
~~~

For example:

~~~bash
java -jar catalog-service.jar \
  --app.catalog.base-url=https://catalog-cli.example.test \
  --app.catalog.connect-timeout=1s \
  --app.catalog.enabled=true
~~~

Arguments starting with `--` are placed into a command-line property source by Spring Boot when this feature is enabled by default. They have higher precedence than typical sources like configuration files and environment variables.

Distinguish carefully:

~~~text
java -Dserver.port=9090 -jar catalog-service.jar
java -jar catalog-service.jar --server.port=9090
~~~

The first line uses a **Java system property** via `-D` (placed before `-jar`). The second line uses a **Spring Boot application argument** starting with `--` (placed after the JAR name). Both can supply configuration, but they are two different property sources with different precedence levels.

### When should you use the command line?

Command-line arguments fit well when:

- You want to test a value quickly without editing files.
- Running a one-off batch job with custom settings.
- A deployment pipeline passes a few explicit overrides.
- Specifying a profile or configuration file location right at startup.

Do not pass passwords, tokens, or private keys directly on the command line if the environment risks exposing process arguments in process listings, deployment logs, or shell history. Prefer an appropriate secret management mechanism.

### If you do not want command-line properties

You can disable adding application arguments as a property source when constructing `SpringApplication`:

~~~java
SpringApplication application = new SpringApplication(Application.class);
application.setAddCommandLineProperties(false);
application.run(args);
~~~

In that case, `--...` values can still be received by code as application arguments via the args API, but `SpringApplication` will no longer automatically place them into `Environment` in the default way.

Only change this behavior when explicitly required; most applications should retain Spring Boot's standard command-line override mechanism.

## 7. Profiles combined with configuration sources

Profiles allow activating values by environment or feature group. For instance, the classpath contains:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

`application.yml` contains shared values:

~~~yaml
app:
  catalog:
    connect-timeout: 5s
    enabled: true
~~~

`application-prod.yml` overrides only values specific to production:

~~~yaml
app:
  catalog:
    base-url: https://catalog-prod.example.test
    connect-timeout: 2s
~~~

Activate the profile via the command line:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Or via an environment variable:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog-service.jar
~~~

When the `prod` profile is in effect, Spring Boot loads the corresponding config data documents according to precedence rules. Non-overridden properties can still come from `application.yml` or other sources.

Another approach is using multiple YAML documents and `spring.config.activate.on-profile`:

~~~yaml
app:
  catalog:
    connect-timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

app:
  catalog:
    connect-timeout: 2s
~~~

The second document is applied only when the `prod` profile is active.

**Do not place `spring.profiles.active` inside a document activated only by `spring.config.activate.on-profile`.** The property activating the profile must be provided from an appropriate source before Boot decides which profile-specific documents to apply.

If a property appears in both a profile-specific file and an environment variable, the environment variable source can still override it per its precedence. Profiles do not invert the overall precedence order among sources.

## 8. Specifying file locations with spring.config.location

By default, Spring Boot searches standard locations for Config Data. When you want to replace the search locations entirely, you can supply `spring.config.location` from the launch environment:

~~~bash
java -jar catalog-service.jar \
  --spring.config.location=optional:file:/etc/catalog/application.yml
~~~

This example points to `/etc/catalog/application.yml`. The `optional:` prefix allows the application to start even if that location is missing instead of failing startup over a missing location.

Common location forms:

~~~text
classpath:/custom/
file:./custom/
file:/etc/catalog/application.yml
optional:file:./custom/
~~~

Directory locations must end with `/` so Spring Boot can append standard configuration filenames such as `application.yml`. File locations are specified with the exact filename.

**`spring.config.location` replaces the default list of search locations.** If you specify only one file elsewhere, do not assume classpath locations and `./config/` will still be loaded as before.

Because this property is used very early to decide where to read Config Data from, pass it via a command-line argument, an environment variable such as `SPRING_CONFIG_LOCATION`, or a Java system property. Do not place it inside an `application.yml` file and expect Spring Boot to have found that file because of the property inside it.

### Adding rather than replacing: spring.config.additional-location

If you want to keep the default locations while adding a directory for operational configuration, use `spring.config.additional-location`:

~~~bash
java -jar catalog-service.jar \
  --spring.config.additional-location=optional:file:./operations/
~~~

Spring Boot still searches the default locations and then considers the additional location provided. Values in additional locations can override values loaded from default locations according to Config Data ordering rules.

This fits a layered model well:

- JAR holds defaults.
- `./config/` holds standard environment configuration.
- `./operations/` holds overrides injected by the deployment system.

With multiple locations, specific ordering and location group rules apply. When configuring multiple paths alongside profile-specific files, verify the actual precedence rather than relying purely on directory name order.

## 9. Importing extra Config Data with spring.config.import

Sometimes you need a primary configuration file that references an additional file. Spring Boot supports `spring.config.import`.

Example in `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./config/catalog-extra.yml

app:
  catalog:
    connect-timeout: 5s
~~~

When `./config/catalog-extra.yml` exists, Spring Boot reads it as imported Config Data. For overlapping properties, values from the imported document have higher precedence than the document that declared the import.

Example imported file:

~~~yaml
app:
  catalog:
    connect-timeout: 2s
~~~

The effective value will be `2s` unless overridden by a higher-precedence source.

If you omit `optional:` and the required file does not exist, Spring Boot can raise `ConfigDataLocationNotFoundException` and stop startup. This behavior is useful when the extra configuration is genuinely mandatory.

`spring.config.import` differs from `spring.config.location`:

- `location`: determines the Config Data search location list very early.
- `additional-location`: appends search locations to the default list.
- `import`: a configuration document currently being read declares another Config Data source.

For sensitive data or credentials, avoid placing real values in files committed to Git. Use a secret manager or mounted files from your deployment platform combined with appropriate import capabilities.

## 10. Reading configuration in Java with @ConfigurationProperties

After Spring Boot merges sources, beans can receive values via `Environment`, `@Value`, or `@ConfigurationProperties`.

For a group of related values, `@ConfigurationProperties` is usually the easiest option to manage. It supports relaxed binding and type conversion such as `Duration`, `URI`, numbers, and booleans.

For example:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

Enable scanning for configuration properties in the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

A service can inject `CatalogProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CatalogProperties properties;

    public CatalogService(CatalogProperties properties) {
        this.properties = properties;
    }

    public String target() {
        return properties.baseUrl().toString();
    }

    public Duration timeout() {
        return properties.connectTimeout();
    }
}
~~~

When instantiating `CatalogProperties`, the Binder reads `app.catalog.*` values from `Environment` according to precedence and converts them into the corresponding types. Consequently, the service does not need to know whether values came from a file inside the JAR, an external file, an environment variable, or the command line.

For mandatory configuration, you can add validation such as `@Validated` and Jakarta Validation constraints like `@NotNull`. The application needs a compatible validation provider, typically via `spring-boot-starter-validation`, to run validation.

### When to use Environment or @Value?

If you only need to look up a single property, you can read it using `Environment`:

~~~java
String applicationName = environment.getProperty(
        "spring.application.name",
        "catalog-service"
);
~~~

Or use `@Value`:

~~~java
public CatalogBanner(
        @Value("${spring.application.name:catalog-service}")
        String applicationName) {
    this.applicationName = applicationName;
}
~~~

`@Value` works well for individual values. When configuration consists of several related fields, `@ConfigurationProperties` provides a clearer type contract and is easier to validate and test.

## 11. Finding the cause when configuration values are unexpected

If the application gets the wrong endpoint, timeout, or profile, check in sequence:

1. Verify the property name is spelled correctly, especially `-`, `.`, and `_`.
2. Verify `application.yml` was packaged into the JAR at the expected path.
3. Check the actual working directory at runtime to see where `./config/` resolves.
4. Check whether an external file was loaded and has keys overlapping with the file in the JAR.
5. Check active profiles and related `application-{profile}` files.
6. Check the environment variables of the **running process itself**.
7. Check command-line arguments and Java system properties.
8. Check whether `spring.config.location`, `additional-location`, or `import` alters which files are loaded.

Spring Boot Actuator can provide the `env` and `configprops` endpoints to inspect loaded configuration and binding results when properly enabled. These endpoints may contain or reflect sensitive configuration details; restrict access and use Actuator's data-masking features.

You can pass `--debug` at launch to get extra diagnostics on auto-configuration conditions, though it does not replace checking property source order and actual bound values.

### Wrong working directory

Running:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar
~~~

resolves `./config/` differently from running from another directory:

~~~bash
java -jar /opt/catalog/catalog-service.jar
~~~

In the second case, `./config/` is resolved relative to the shell's current directory, not `/opt/catalog`. If you want paths independent of working directory, specify locations explicitly using absolute paths or configure the working directory in your service/container definition.

### YAML file not loaded as expected

Check YAML indentation, filename, and profile name. A file named `application-production.yml` will not be used automatically when the active profile is `prod`. The profile name must match, or an appropriate import/location must be declared.

If both `application.properties` and `application.yml` exist in the same location, check format precedence instead of assuming the YAML file listed later will win.

## 12. Security when externalizing configuration

Externalized configuration separates settings from code, **but does not automatically turn data into safely protected secrets**.

- Do not commit passwords, access tokens, or private keys to `application.yml` in your source repository.
- Do not log the entire `Environment` or configuration properties contents if sensitive fields exist.
- Restrict read permissions on external configuration files and secret-bearing volumes.
- Consider a secret manager, Kubernetes Secrets, or mounted config trees instead of placing secrets directly on the command line.
- Avoid passing secrets in command-line arguments because they can appear in process lists or logs.
- Use access control and masking for Actuator diagnostic endpoints.

Environment variables are often convenient for deployment, yet still carry exposure risks via container specs, debugging tools, or CI logs. Choose secret delivery methods according to your platform's security model, not convenience alone.

## 13. Choosing a configuration source per scenario

| Scenario | Typically suitable source | Reason |
|---|---|---|
| Application default values | Classpath `application.yml` | Ships with the artifact, easy to version-control |
| Deployment-environment-specific values | File outside the JAR | No need to rebuild the artifact |
| Overriding a few values in Docker/Kubernetes | Environment variables | Easy to inject per container/Pod |
| Quick experiment with one value | Command line | Applies to a single run only |
| Activating a profile at startup | Command line or environment variable | Takes effect during Config Data preparation |
| Adding an operational config directory | `spring.config.additional-location` | Keeps default sources while adding overrides |
| Configuration stored in a completely custom location | `spring.config.location` | Controls the search location list |
| Primary config file referencing another file | `spring.config.import` | Splits configuration across multiple sources |

A straightforward deployment workflow can start with a packaged `application.yml` for default values, add an external file outside the JAR for the environment, use environment variables for select overrides, and reserve command-line properties for run-specific adjustments.

The core insight is that Spring Boot does not require beans to know **where values come from**. `Environment` aggregates property sources by precedence; the Binder and injection mechanisms turn them into the data the application needs. When boundaries between classpath, external files, environment variables, and command-line arguments are cleanly designed, the same artifact can be deployed flexibly, predictably, and with fewer configuration mistakes.
