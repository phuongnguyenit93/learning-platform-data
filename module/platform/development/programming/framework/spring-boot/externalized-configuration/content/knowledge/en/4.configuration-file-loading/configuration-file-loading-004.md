# Replacing Default Locations with `spring.config.location`

In Spring Boot, `application.properties` and `application.yml` files are usually discovered automatically in familiar locations on the classpath and in the working directory. When deploying the same application build across multiple environments, we may want to **read configuration only from a specified directory or file** instead of having the application scan all default locations. The `spring.config.location` property addresses that need.

Key point to grasp: `spring.config.location` **replaces Spring Boot's default configuration file search locations** with the locations passed at startup. It does not disable other configuration sources such as environment variables, Java system properties, or command-line arguments. It also differs from `spring.config.additional-location`, which preserves the default locations and adds new ones.

This lesson uses the context of Spring Boot 3.3.x and Java 21.

## 1. Where Does Spring Boot Look for Configuration When No Location Is Specified?

Spring Boot supports *externalized configuration*: configuration can live inside the JAR, outside the JAR, or be supplied by the runtime environment. For config data such as `application.properties`, `application.yaml`, and `application.yml`, Spring Boot searches locations by default such as:

| Default Location | Meaning |
| --- | --- |
| `optional:classpath:/` | Classpath root, typically `src/main/resources` during development |
| `optional:classpath:/config/` | The `config` directory on the classpath |
| `optional:file:./` | The current working directory of the process |
| `optional:file:./config/` | The `config` directory under the working directory |
| `optional:file:./config/*/` | Direct subdirectories of `./config/` |

These locations participate in the config data loading mechanism, following Spring Boot's precedence and override rules. `optional:` means the location may not exist and its absence is ignored. Do not interpret this table as a list of every Spring `PropertySource`: these are only the default **config data file** search paths.

Project example:

~~~text
catalog-service/
├── build/
│   └── libs/
│       └── catalog-service.jar
├── config/
│   └── application.yml
└── src/
    └── main/
        └── resources/
            └── application.yml
~~~

When running inside the `catalog-service` directory without location overrides, Spring Boot can examine both the configuration packaged inside the JAR and the external configuration at `./config/`. The external configuration outside the JAR can override keys from the packaged configuration according to config data precedence order.

## 2. `spring.config.location` Replaces the Default Location List

Suppose we want to run the application using configuration placed inside a `deployment` directory:

~~~text
catalog-service/
├── catalog-service.jar
├── deployment/
│   └── application.yml
└── config/
    └── application.yml
~~~

Run command:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

In this case, the discovery mechanism for **standard config data files** uses `file:./deployment/` instead of the default list. Spring Boot searches for `application.properties`, `application.yml`, or `application.yaml` inside this directory, along with profile-specific variants when applicable.

One way to visualize this:

~~~text
WITHOUT spring.config.location
  → searches default locations on the classpath and filesystem

WITH --spring.config.location=file:./deployment/
  → uses the specified location: ./deployment/
  → does not automatically search the replaced default locations
~~~

Therefore, **do not assume `src/main/resources/application.yml` is still loaded** when `spring.config.location` points exclusively to another directory. Settings in the packaged file may no longer take effect unless that file is included in the loaded locations or imported via another mechanism.

Distinguish the scope: this replacement applies to **config data search locations**, not the entire externalized configuration mechanism. For example, the CLI argument `--server.port=9090` can still override `server.port` from the loaded file.

## 3. Passing the Location at Startup

`spring.config.location` is used very early, before Spring Boot decides which files to load. Therefore, pass it through a source available at **startup time**, such as a command-line argument, Java system property, or environment variable.

### 3.1. Command-line argument

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

With a specific file:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/application-prod.yml
~~~

With an absolute path on Linux:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:/etc/catalog/application.yml
~~~

Wrap the entire argument in quotes if the path contains spaces or characters meaningful to the shell:

~~~bash
java -jar catalog-service.jar '--spring.config.location=file:./my config/'
~~~

### 3.2. Java system property

Be sure to place `-D...` **before** `-jar`:

~~~bash
java -Dspring.config.location=file:./deployment/ -jar catalog-service.jar
~~~

This is a JVM system property. If mistakenly placed after the JAR name without using the application argument syntax, the JVM will not recognize it as a system property.

### 3.3. Environment variable

On Linux/macOS:

~~~bash
export SPRING_CONFIG_LOCATION=file:./deployment/
java -jar catalog-service.jar
~~~

In Windows PowerShell:

~~~powershell
$env:SPRING_CONFIG_LOCATION = 'file:./deployment/'
java -jar catalog-service.jar
~~~

Spring Boot recognizes the environment variable name `SPRING_CONFIG_LOCATION` corresponding to `spring.config.location`. This approach fits Docker, Kubernetes, deployment scripts, and runtime configuration management systems.

### 3.4. Do not rely on `application.yml` to change its own location

The following example is not a reliable way to decide where Spring Boot initially searches for files:

~~~yaml
# Do not place startup location resolution logic in a file waiting to be found
spring:
  config:
    location: file:./deployment/
~~~

Spring Boot must **know where to search before loading files**. Therefore, pass `spring.config.location` via command-line arguments, system properties, or environment variables outside the config data loading process. This is an important distinction from ordinary application properties like `server.port`.

## 4. Directory Paths Differ from File Paths

Spring Boot distinguishes a **search directory** from an **explicitly named file**.

### 4.1. Directory: must end with a `/`

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

The trailing `/` tells Spring Boot that `deployment/` is a directory. Spring Boot appends appropriate configuration file names based on `spring.config.name`, which defaults to `application`, and considers profile-specific variants when needed.

For example:

~~~text
deployment/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

With `--spring.profiles.active=prod`, Spring Boot can load the shared `application.yml` and the profile-specific `application-prod.yml` from the declared directory. Values in the active profile's file can override shared values for the same key.

### 4.2. Specific file: specify the full name and extension

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/application.yml
~~~

When a specific file is passed, Spring Boot uses that file name directly as the configuration location, instead of using `spring.config.name` to scan for arbitrary names in the same directory. With explicitly named files, the config data mechanism can also consider corresponding profile variants where applicable.

Example pointing to a specific operator-managed configuration file:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./ops/catalog.yml
~~~

Do not confuse the meanings of these notations:

| Location | Interpretation |
| --- | --- |
| `file:./ops/` | Directory containing files named according to Spring Boot conventions |
| `file:./ops/application.yml` | Specific YAML file |
| `file:/etc/catalog/` | Directory outside the JAR at an absolute path |
| `classpath:/config/` | `config` directory on the classpath |
| `classpath:/config/application.yml` | YAML file packaged on the classpath |

`classpath:` refers to resources on the classpath, usually packaged with the application. `file:` refers to resources on the filesystem. For deployment configuration that must change independently of the JAR, a `file:` path outside the JAR is generally appropriate.

### 4.3. Relative paths depend on the working directory

In `file:./deployment/`, `./` is resolved from the **working directory of the Java process**, not automatically from the directory containing the JAR.

Suppose the JAR is located at `/opt/catalog/catalog-service.jar`. These two commands can point to different locations:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

~~~bash
cd /tmp
java -jar /opt/catalog/catalog-service.jar --spring.config.location=file:./deployment/
~~~

The first command searches in `/opt/catalog/deployment/`; the second searches in `/tmp/deployment/`. In service scripts, containers, or CI/CD, use explicit paths and set the working directory intentionally.

## 5. Missing Locations and the `optional:` Prefix

By default, if a declared location is required to exist but does not, Spring Boot can halt startup with an error such as `ConfigDataLocationNotFoundException`.

For example:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./does-not-exist/
~~~

If the directory does not exist, the application will encounter a config data loading error. This is helpful when a deployment configuration file is mandatory and running without it should be caught early.

When you want to allow a location to be missing, prepend `optional:` to each such location:

~~~bash
java -jar catalog-service.jar --spring.config.location=optional:file:./deployment/
~~~

If `./deployment/` does not exist, Spring Boot skips this location. **Skipping a location does not mean automatically restoring the default list.** Since `spring.config.location` still replaces the default list, the application may end up without configuration from the old `application.yml` files unless you re-declare them.

You can combine required and optional locations:

~~~bash
java -jar catalog-service.jar '--spring.config.location=classpath:/base/,optional:file:./overrides/'
~~~

In this example, `classpath:/base/` is required to exist; `file:./overrides/` may be absent. Files in the two locations are evaluated according to the precedence order of the location groups.

**When should you use `optional:`?** Use it if the application still has sufficient valid configuration when that location is absent. If all operational configuration is mandatory, keep the location required so startup fails immediately when missing.

## 6. Multiple Locations, Ordering, and Location Groups

`spring.config.location` allows specifying multiple locations. For locations processed sequentially, later locations can override matching property keys from earlier locations.

For example:

~~~bash
java -jar catalog-service.jar '--spring.config.location=optional:classpath:/defaults/,optional:file:./deployment/'
~~~

Suppose:

~~~yaml
# classpath:/defaults/application.yml
app:
  display-name: "Default catalog"
  page-size: 20
~~~

~~~yaml
# file:./deployment/application.yml
app:
  display-name: "Production catalog"
~~~

When both exist and are loaded, the expected result is:

~~~text
app.display-name = Production catalog
app.page-size    = 20
~~~

`app.display-name` in the later location overrides the same key in the earlier location; `app.page-size` still comes from the first source if the later source does not provide it.

Spring Boot also distinguishes commas `,` and semicolons `;` when listing locations:

- **Comma `,`** separates location groups processed sequentially.
- **Semicolon `;`** groups multiple locations at the same level, which is especially important when processing profile-specific configuration.

Syntax example:

~~~text
spring.config.location=classpath:/cfg/,classpath:/ext/
spring.config.location=classpath:/cfg/;classpath:/ext/
~~~

Both list two directories, but how groups are structured can make the **order in which profile-specific files are applied** differ. When `application-dev.yml` and `application-prod.yml` exist across multiple directories and multiple profiles are active simultaneously, choose the separator intentionally rather than treating them as equivalent.

If only a single directory is needed, there is no need to worry about location groups. When multiple groups override each other, explicitly document the expected order and value for shared keys.

## 7. Profile-Specific Configuration in a New Location

Suppose:

~~~text
deployment/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Contents of `deployment/application.yml`:

~~~yaml
app:
  endpoint: https://api.example.org
  retry-count: 3
~~~

Contents of `deployment/application-dev.yml`:

~~~yaml
app:
  endpoint: http://localhost:8080
~~~

Contents of `deployment/application-prod.yml`:

~~~yaml
app:
  retry-count: 5
~~~

Run for the dev environment:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=dev
~~~

Effective results for the example keys:

~~~text
app.endpoint    = http://localhost:8080
app.retry-count = 3
~~~

Run for the prod environment:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=prod
~~~

Result:

~~~text
app.endpoint    = https://api.example.org
app.retry-count = 5
~~~

Shared configuration from `application.yml` is combined with the profile-specific configuration from the new directory, and matching property names are resolved according to config data precedence. Multiple profiles, multiple location groups, or imports can make the actual ordering more complex, but the principle of declaring the location early remains the same.

## 8. Comparing `spring.config.location`, `spring.config.additional-location`, and `spring.config.import`

All three mechanisms relate to loading additional files, but solve different needs.

| Mechanism | Scope | When to Use |
| --- | --- | --- |
| `spring.config.location` | **Replaces** the default config data search locations | When you want explicit control so the application only searches specified locations |
| `spring.config.additional-location` | **Adds** locations alongside the default ones | When you want to keep `application.yml` packaged in the JAR and add external configuration |
| `spring.config.import` | **Imports** another configuration resource from an already-loaded document | When a configuration file references additional needed files or sources |

### 8.1. Replacing all locations

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

If the application previously relied on a `spring.application.name` value present only in `classpath:/application.yml`, that value may disappear because the default classpath location was replaced.

### 8.2. Keeping defaults and adding overrides

~~~bash
java -jar catalog-service.jar --spring.config.additional-location=optional:file:./deployment/
~~~

In this case, Spring Boot can still load configuration at the default locations and then use values in the `deployment` directory to override matching keys.

This is typically the right choice when organizing configuration as:

~~~text
application.yml inside the JAR  → shared defaults
./deployment/application.yml    → environment-specific values
~~~

Use `spring.config.location` only when **replacement** is intentional.

### 8.3. Importing configuration from an already-loaded file

For example, inside an `application.yml` loaded by Spring Boot:

~~~yaml
spring:
  config:
    import: optional:file:./secrets/feature.yml
~~~

This mechanism instructs Spring Boot to consider the imported resource; it does not have the same meaning as replacing the entire startup search path. A prerequisite is that the document containing `spring.config.import` must itself be loaded through an active location. If `spring.config.location` causes that document not to be loaded, the import directive inside it will not be applied either.

## 9. Combining `spring.config.location` and `spring.config.name`

By default Spring Boot uses the base name `application` to search for `application.yml`, `application.yaml`, or `application.properties`. You can change the base name via `spring.config.name`, which must also be supplied at startup.

Suppose:

~~~text
settings/
├── catalog.yml
└── catalog-prod.yml
~~~

Run:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./settings/ --spring.config.name=catalog --spring.profiles.active=prod
~~~

Now Spring Boot looks for files with the base name `catalog` inside `settings/` rather than only defaulting to `application`. The profile-specific file `catalog-prod.yml` participates when the `prod` profile is active.

This is useful when multiple applications share a configuration directory but have separate file names:

~~~text
shared-config/
├── catalog.yml
├── catalog-prod.yml
├── billing.yml
└── billing-prod.yml
~~~

However, if only one specific file is needed, passing the file path directly to `spring.config.location` is usually simpler.

## 10. Complete Spring Boot Example

### 10.1. Java code reading the final values

The application uses `spring-boot-starter`; if an HTTP server is needed, add `spring-boot-starter-web`.

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(Environment environment) {
        return args -> {
            System.out.println("app.mode = "
                    + environment.getProperty("app.mode", "<missing>"));
            System.out.println("app.endpoint = "
                    + environment.getProperty("app.endpoint", "<missing>"));
            System.out.println("spring.application.name = "
                    + environment.getProperty("spring.application.name", "<missing>"));
        };
    }
}
~~~

`Environment` returns the effective values according to configuration source precedence; printing them helps observe the difference between the new location and the default locations.

### 10.2. Configuration packaged inside the JAR

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog-service
app:
  mode: packaged
  endpoint: https://packaged.example.org
~~~

### 10.3. External configuration

Create `deployment/application.yml` in the working directory:

~~~yaml
app:
  mode: external
  endpoint: https://external.example.org
~~~

Run with the replacement location:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Example output:

~~~text
app.mode = external
app.endpoint = https://external.example.org
spring.application.name = <missing>
~~~

Because `spring.application.name` is declared only in the packaged configuration, when the default locations are completely replaced, the example no longer loads that value. This directly illustrates the effect of `spring.config.location`.

Try again with:

~~~bash
java -jar catalog-service.jar --spring.config.additional-location=file:./deployment/
~~~

Expected output:

~~~text
app.mode = external
app.endpoint = https://external.example.org
spring.application.name = catalog-service
~~~

With `additional-location`, the default configuration is retained to provide keys not present in the external file.

**Practical note:** In Gradle/Maven or an IDE environment, the working directory may differ from the directory where the JAR sits. Place `deployment/` in the actual working directory or switch to an absolute path.

## 11. Common Error Scenarios

### 11.1. Forgetting the trailing `/` on a directory path

~~~bash
# Intending to specify a directory
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Directory notation requires a trailing `/`. If you write `file:./deployment`, do not assume Spring Boot will still treat it as a directory location and append `application.yml`. Explicitly include the slash, or specify the full file name.

### 11.2. Relative path depending on the working directory

~~~bash
java -jar /opt/catalog/catalog-service.jar --spring.config.location=file:./deployment/
~~~

Check which directory the process is running in, especially when invoked from systemd, cron, Docker, or an IDE. The reliable fix is usually to use `file:/absolute/path/`.

### 11.3. Default configuration inside the JAR disappears

When using `spring.config.location`, do not rely on `classpath:/application.yml` unless you include it in the location list or import it from an already-loaded document. If your goal is to keep default values inside the JAR, consider `spring.config.additional-location`.

### 11.4. Optional directory does not exist

~~~bash
java -jar catalog-service.jar --spring.config.location=optional:file:./deployment/
~~~

The application may not report a *missing location* error, yet still lack properties required by beans or business logic. `optional:` only changes how an absent location is handled; it does not ensure the application's configuration is complete.

### 11.5. The right file was loaded, yet the value is unexpected

A file containing `server.port: 8081` may have been loaded, yet the CLI argument `--server.port=9090` still overrides that value.

Distinguish:

1. **Which files are loaded?** Depends on `spring.config.location`, `spring.config.name`, profiles, imports, and paths.
2. **Which value is effective?** Depends on the precedence order across all `PropertySource`s, including environment variables and command-line arguments.

These are two separate diagnostic steps; inspecting the contents of the loaded file alone is not enough.

### 11.6. Declaring multiple paths with wrong precedence assumptions

When multiple directories contain `application.yml`, location groups and profile-specific variants can change the override order. Start with a single location or a simple group, then add each source intentionally. If using `;` in a shell, wrap the entire argument in quotes so the shell does not interpret it as a command separator.

## 12. Observing Configuration Loading

When you want to see which files Spring Boot searched for, you can increase the log level for the config data mechanism:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --logging.level.org.springframework.boot.context.config=TRACE
~~~

Trace logs can reveal the config data search and loading process, though exact log messages vary by version. Do not rely on a fixed log message in business code.

To observe final values, use `Environment` in a bean as shown in the example above. When the system already uses Spring Boot Actuator, the `env` and `configprops` endpoints can assist diagnostics, provided access is properly secured to avoid exposing sensitive information.

When a required location does not exist, the startup error message is usually the clearest sign. Check the file name, extension, working directory, read permissions, and trailing `/` on directory locations.

## 13. Hands-On Exercises

**Exercise 1 — Distinguishing replacement from addition.** Inside the JAR you have:

~~~yaml
app:
  color: blue
  page-size: 10
~~~

Inside `deployment/application.yml` you have:

~~~yaml
app:
  color: green
~~~

Predict `app.color` and `app.page-size` when running respectively with:

~~~text
--spring.config.location=file:./deployment/
--spring.config.additional-location=file:./deployment/
~~~

Answer: with `location`, `color=green` and `page-size` no longer has a value from the packaged file; with `additional-location`, `color=green` and `page-size=10`. This assumes no other source supplies or overrides these keys.

**Exercise 2 — Recognizing required locations.** What happens if `./settings/` does not exist in these two cases?

~~~text
--spring.config.location=file:./settings/
--spring.config.location=optional:file:./settings/
~~~

Answer: the first case can halt startup because the location is not found; the second skips the missing location. Both still **replace** the default locations.

**Exercise 3 — Activating a profile in an external directory.** Create:

~~~text
deployment/application.yml
deployment/application-prod.yml
~~~

In the shared file set `app.timeout: 5s`; in the prod file set `app.timeout: 15s`. Run:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=prod
~~~

Read `app.timeout` using `Environment` or bind `Duration` with `@ConfigurationProperties`. The expected result is `15s`.

**Exercise 4 — Configuring via environment variable.** Set `SPRING_CONFIG_LOCATION=file:./deployment/` and run the JAR without passing `--spring.config.location`. Observe the effective value, then re-test after unsetting the environment variable.

**Exercise 5 — Changing the default name.** Create `settings/catalog.yml` and run with `--spring.config.location=file:./settings/ --spring.config.name=catalog`. Verify that configuration is read from the file named `catalog.yml`.

## 14. Summary

`spring.config.location` is the mechanism that determines **the set of config data locations searched when Spring Boot starts**. When this property is declared, the default locations are replaced. If a location points to a directory, end it with `/` and remember that `file:./...` paths depend on the working directory. Use `optional:` when missing a location is acceptable; use profiles when there are multiple environment configuration variants.

If you want to keep the default configuration files and only add external sources outside the JAR, use `spring.config.additional-location`. When diagnosing an unexpected value, check both **which files were loaded** and **the property source precedence order**.

## References

- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Working With Multi-Document Files and Profile-specific Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)