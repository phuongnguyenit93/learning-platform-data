# `application.properties` and `application.yml` Files

Spring Boot allows externalizing configuration from source code so the same application can run in development, testing, and production environments with different values. The two most common formats are **`application.properties`** and **`application.yml`** (or the standard YAML extension **`application.yaml`**). Spring Boot loads these files into `Environment`, after which beans can read values via `@Value`, `Environment`, or type-safe binding with `@ConfigurationProperties`.

In the **SPRING_CLOUD_CORE** module, externalized configuration is the foundation for distributed applications to declare service names, registry addresses, timeouts, dependent endpoints, and Spring Cloud options. Understanding both file formats properly helps avoid overridden configuration bugs, unactivated profiles, invalid YAML indentation, or applications unexpectedly continuing to use default values.

## 1. Learning Objectives

After this lesson, learners can:

1. Write the same configuration using both `application.properties` and `application.yml`.
2. Explain how Spring Boot locates, loads, and merges configuration from the classpath and outside the application.
3. Create profile-specific files such as `application-dev.yml` and understand the override order.
4. Use placeholders, environment variables, lists, and nested structures properly.
5. Choose appropriately among `spring.config.location`, `spring.config.additional-location`, `spring.config.name`, and `spring.config.import`.
6. Inspect actual values in `Environment` and troubleshoot common configuration loading errors.
7. Explain the relationship between Spring Boot configuration files, Config Client, and Spring Cloud's refresh mechanism.

## 2. Two Formats, Same Environment

### 2.1. `application.properties`: key-value format

Each line represents one property. Hierarchical structure is written using dots in the key name:

~~~properties
spring.application.name=orders-service
server.port=8080

clients.inventory.base-url=http://inventory-service
clients.inventory.connect-timeout=250ms
clients.inventory.read-timeout=700ms

management.endpoints.web.exposure.include=health,info
~~~

The advantage of `.properties` is simplicity and easy searchability, making it suitable for flat configurations or when each key needs to be declared explicitly. The disadvantage is that deeply nested property groups, lists of objects, and complex maps can become hard to read as the file grows.

### 2.2. `application.yml`: hierarchical format

YAML represents structure through indentation. The same configuration above can be written as:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

clients:
  inventory:
    base-url: http://inventory-service
    connect-timeout: 250ms
    read-timeout: 700ms

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Nested keys in YAML are flattened into dot-separated keys when placed into the Spring `Environment`. For example, `clients.inventory.read-timeout` is the property name readable from both formats.

| Criterion | `.properties` | `.yml` / `.yaml` |
| --- | --- | --- |
| Representation | `key=value` or `key:value` | Nested structure using indentation |
| Grouping properties | Uses dot-separated prefixes | Uses YAML levels |
| Lists | Can use `[0]`, `[1]` indices or a format suited for the binder | Uses `-` markers |
| Reading multi-level config | Can become verbose when many keys share prefixes | Usually easier to read |
| Splitting multiple documents | Uses the special `#---` separator | Uses the YAML `---` separator |
| Loading mechanism | Spring Boot Config Data | Spring Boot Config Data and SnakeYAML |

Both formats can provide the exact same values to `Environment`; choosing a format is a representational choice. A project should standardize on one primary format to reduce confusion.

### 2.3. Avoid declaring both formats with the same name in the same location

If both `application.properties` and `application.yml`/`application.yaml` exist in the same location, Spring Boot prioritizes **`.properties`**. This easily causes confusion when developers edit the YAML file while the application still reads values from the properties file in the same location.

For example:

~~~text
src/main/resources/
  application.properties
  application.yml
~~~

If both files declare `server.port`, the value in `application.properties` takes precedence at that configuration location. Choose one primary format or remove duplicate configuration so behavior stays clear. Spring Boot documentation recommends using a single consistent format across the entire application.

## 3. How Spring Boot Locates Configuration Files

### 3.1. Default locations

Spring Boot automatically searches for `application.properties`, `application.yaml`, and corresponding YAML variants in default locations. For a conventionally launched application, the location groups include:

1. Classpath root, e.g., `src/main/resources/application.yml` after packaging.
2. `classpath:/config/`.
3. The current working directory, usually the directory where the application launch command is executed.
4. The `./config/` directory beneath the working directory.
5. Immediate subdirectories beneath `./config/`.

Locations are evaluated in order; values in higher-precedence locations can override values loaded earlier. Configuration placed outside the JAR is commonly used to adjust the application per deployment environment without rebuilding the artifact.

Example structure:

~~~text
orders-service/
  config/
    application.yml
    application-prod.yml
  orders-service.jar
~~~

When launched from the `orders-service` directory, Spring Boot can find configuration in the `config/` directory outside the JAR. The `application-prod.yml` file is considered when the `prod` profile is active.

**Note:** relative locations depend on the *working directory*. Running the same JAR from two different directories can cause Spring Boot to discover different external files.

### 3.2. Classpath configuration and external configuration

A common organizational pattern:

- `src/main/resources/application.yml`: shared default values packaged inside the JAR.
- `./config/application.yml`: deployment environment configuration located outside the JAR.
- `./config/application-prod.yml`: values applied only for the `prod` profile.

Example file on the classpath:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    connect-timeout: 200ms
    read-timeout: 500ms
~~~

External file outside the JAR:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 900ms
~~~

Values that are not overridden still come from lower-precedence configuration sources, while `read-timeout` is replaced by the value from the external file. Configuration can be supplied to a container or server via a volume mount, deployment directory, or configuration management tool.

### 3.3. Changing file names or search locations

Three properties to distinguish:

| Property | Effect |
| --- | --- |
| `spring.config.name` | Changes the base name Spring Boot uses when searching for files; e.g., `myservice` searches for `myservice.properties` or `myservice.yaml` |
| `spring.config.location` | Specifies the locations to search and **replaces** the default locations |
| `spring.config.additional-location` | Adds new locations alongside the default locations |

They can be passed from the command line:

~~~bash
java -jar orders-service.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

Or via environment variables:

~~~bash
SPRING_CONFIG_NAME=orders
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./deploy-config/
~~~

Properties controlling file discovery are read very early. Provide them via environment variables, JVM system properties, or command-line arguments before Config Data is loaded. Placing `spring.config.location` inside the very file it is supposed to help discover is generally too late.

If a location is a directory, the path must end with `/`. If it is a specific file, Spring Boot loads that specified file. Multiple locations can be separated by commas; declaration order affects override precedence.

**Key distinction:**

- Use `spring.config.location` when you want to define the set of configuration locations yourself.
- Use `spring.config.additional-location` when you want to keep the default locations and add external deployment configuration.

### 3.4. Optional locations and missing file errors

If a specified Config Data location does not exist, the application may fail on startup by default. Add the `optional:` prefix when a file or location is genuinely optional:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=optional:file:./local-overrides/
~~~

Do not mark every configuration as optional. If the application requires an endpoint or security credentials to serve business logic, continuing startup with unsuitable default values can cause later failures that are harder to diagnose.

## 4. Profile-Based Configuration

Profiles allow sharing the same source code while varying values by environment or runtime purpose.

### 4.1. Profile-specific files

File naming convention:

~~~text
application.yml
application-dev.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

The `application.yml` file contains shared defaults:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    connect-timeout: 200ms
    read-timeout: 500ms
    base-url: http://localhost:8081
~~~

The `application-prod.yml` file declares only what needs to change:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 900ms
~~~

When the `prod` profile is active, values in `application-prod.yml` override corresponding values in the non-profile file. Keys not declared in the profile file continue to come from shared configuration or other sources.

### 4.2. Activating profiles

Profiles can be activated from the command line:

~~~bash
java -jar orders-service.jar --spring.profiles.active=prod
~~~

Or via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

In a development environment, a default can be set in `application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Do not hardcode `prod` inside the packaged configuration file of the application. Deployment environments should explicitly select the profile via runtime configuration to avoid accidentally booting in the wrong mode.

If no active profile is set, Spring `Environment` uses the default profile (typically named `default`). When multiple profiles are activated, a profile evaluated later can override values from an earlier profile under the last-wins rule.

### 4.3. Override order to remember

There are two levels to distinguish:

- **Overall configuration source order:** command-line arguments, environment variables, system properties, and other sources have their own precedence relative to Config Data.
- **Order within Config Data:** packaged files, profile-specific packaged files, external files, and external profile-specific files are evaluated in a defined order.

Simplified example:

| Source | `clients.inventory.read-timeout` |
| --- | ---: |
| `classpath:/application.yml` | `500ms` |
| `classpath:/application-prod.yml` | `700ms` |
| `./config/application.yml` | `800ms` |
| `./config/application-prod.yml` | `900ms` |
| Environment variable `CLIENTS_INVENTORY_READTIMEOUT` | `1s` |
| Command line `--clients.inventory.read-timeout=1200ms` | `1200ms` |

With the common sources above, the final value is `1200ms`. Without the command-line argument, the environment variable can override Config Data. This table is an illustrative example, not an exhaustive list of every `PropertySource` or testing rule.

**Common pitfall:** the order of locations in `spring.config.location` and the concept of a *location group* can affect the ordering of profile-specific files. With multi-directory configurations, commas and semicolons are not always equivalent. When coordinating multiple locations, refer to the Profile Specific Files section in the Spring Boot documentation for your exact version.

## 5. Syntax of `application.properties`

### 5.1. Keys, values, and separators

Properties can be written as:

~~~properties
spring.application.name=orders-service
server.port=8080
clients.inventory.base-url=http://localhost:8081
clients.inventory.read-timeout=700ms
~~~

The `=` sign is the common style; properties files also support `:` in key-value syntax. Use lowercase keys with hyphen-separated words (`kebab-case`) to stay consistent with Spring Boot conventions.

Comments usually start with `#` or `!`:

~~~properties
# Timeout for Inventory Service
clients.inventory.connect-timeout=250ms
! This is a comment using properties syntax
~~~

If a value contains characters requiring escaping or special whitespace, follow Java properties escaping rules. For complex values, inspect the actual result in `Environment` rather than relying solely on how it looks in the file.

### 5.2. Lists and indexed keys

Lists can be declared using indices:

~~~properties
clients.inventory.zones[0]=north
clients.inventory.zones[1]=south
clients.inventory.zones[2]=central
~~~

Some simple cases can use comma-separated form:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
~~~

When binding into a `List`, the indexed representation explicitly identifies each element, especially for lists of nested objects.

### 5.3. Placeholders and default values

Spring Boot supports `${...}` placeholders inside property values:

~~~properties
clients.inventory.base-url=${INVENTORY_URL:http://localhost:8081}
clients.inventory.read-timeout=${INVENTORY_READ_TIMEOUT:700ms}
spring.application.name=${SERVICE_NAME:orders-service}
~~~

The `${KEY_NAME:default_value}` syntax allows falling back to a default value if the referenced key does not exist. Properties can also reference other properties:

~~~properties
app.region=ap-southeast-1
app.instance-label=${spring.application.name}-${app.region}
~~~

Placeholders help avoid repeating values, but avoid creating circular reference chains. For sensitive data such as passwords and tokens, pull values from an appropriate secret store or secure configuration source; never commit real secrets into the repository.

## 6. Syntax of `application.yml`

### 6.1. Indentation and nested structure

YAML uses whitespace to represent structural levels. For example:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080
~~~

Practical rules:

- Use spaces, never tabs, for indentation.
- Keep indentation levels consistent within the same structure.
- A space is required after the `:` of a key when declaring a scalar in standard syntax.
- Each nested level must be indented by the exact expected number of spaces.
- Quote strings containing special characters or values that the parser might otherwise interpret as another data type.

A common mistake is improper indentation causing `read-timeout` to belong to a different group or making the file fail to parse. When in doubt about YAML, use an IDE with YAML validation and inspect startup error logs.

### 6.2. Strings, booleans, numbers, and durations

YAML supports scalar types. For example:

~~~yaml
clients:
  inventory:
    enabled: true
    port: 8081
    connect-timeout: 250ms
    read-timeout: 700ms
    base-url: "https://inventory.internal.example/api"
    description: "Inventory service for orders"
~~~

Certain values can be parsed as booleans, numbers, or scalar types according to YAML rules. If you want to preserve a value as a string, wrap it in quotes:

~~~yaml
feature:
  release-code: "0012"
  display-value: "on"
  label: "2026-11"
~~~

For URLs, expressions, passwords, or strings containing `#`, colons, and special characters, quoting makes intent clearer. Never put real secrets into committed configuration files.

### 6.3. Lists

YAML represents lists using hyphens:

~~~yaml
clients:
  inventory:
    zones:
      - north
      - south
      - central
~~~

This structure corresponds to indexed property keys:

~~~properties
clients.inventory.zones[0]=north
clients.inventory.zones[1]=south
clients.inventory.zones[2]=central
~~~

Lists of objects can also be expressed cleanly:

~~~yaml
clients:
  downstream:
    - name: inventory
      base-url: http://inventory-service
      read-timeout: 700ms
    - name: pricing
      base-url: http://pricing-service
      read-timeout: 500ms
~~~

When binding to Java objects, the target type must match the list structure. Avoid mixing elements of different types within the same list if you want predictable binding.

### 6.4. Maps and special keys

Maps can be written in the form:

~~~yaml
routing:
  service-urls:
    inventory: http://inventory-service
    pricing: http://pricing-service
~~~

When map keys contain special characters that must be preserved, use bracket notation inside quotes:

~~~yaml
routing:
  metadata:
    "[/v1/inventory]": inventory
    "[/v1/pricing]": pricing
~~~

Without bracket notation where needed, certain characters in keys may be stripped during binding. Check Spring Boot's map binding rules if map keys contain `/`, dots, or characters outside alphanumeric sets.

### 6.5. Placeholders in YAML

Uses the same placeholder syntax as `.properties`:

~~~yaml
spring:
  application:
    name: "${SERVICE_NAME:orders-service}"

clients:
  inventory:
    base-url: "${INVENTORY_URL:http://localhost:8081}"
    read-timeout: "${INVENTORY_READ_TIMEOUT:700ms}"
~~~

Resolved values are placed into `Environment` and can be bound into beans. For complex configurations, verify the final bound types, especially `Duration`, `DataSize`, lists, and maps.

## 7. Using `@ConfigurationProperties` to Consume Configuration

Configuration files are only data sources. The application needs a way to read those values. For structured groups of properties, `@ConfigurationProperties` is usually better suited than scattering many individual `@Value` annotations.

### 7.1. Defining a typed configuration class

Suppose `application.yml` contains:

~~~yaml
clients:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 250ms
    read-timeout: 700ms
    zones:
      - north
      - south
~~~

This can be bound into a Java record:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "clients.inventory")
public record InventoryClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        List<String> zones
) {}
~~~

To register the record, you can enable `@ConfigurationPropertiesScan` on the application class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Or explicitly register the configuration class using `@EnableConfigurationProperties(InventoryClientProperties.class)` in an appropriate configuration class.

### 7.2. Why use typed properties?

- Groups related keys together into a single object.
- Converts `250ms` into `Duration` and URLs into `URI`.
- Supports binding nested structures, lists, and maps.
- Simplifies testing and documenting configuration.
- Allows adding validation to catch invalid configuration at startup.

For example, a negative timeout or invalid URL should be caught early rather than failing on the first request. When using Jakarta Bean Validation, include the appropriate validation dependency and annotations; do not assume validation is automatically active merely by declaring `@ConfigurationProperties`.

### 7.3. Canonical property names

Use **lowercase kebab-case** property names in configuration files and placeholders, for example:

~~~properties
clients.inventory.read-timeout=700ms
~~~

Spring Boot supports relaxed binding and can accept equivalent spellings such as camelCase or underscores depending on the property source. Even so, choosing one canonical form keeps configuration files, placeholders, and environment variables consistent.

## 8. Environment Variables and Deployment Configuration

In container or cloud environments, environment variables are commonly used to pass values that vary between deployments without modifying files inside the JAR.

Spring Boot maps canonical property names to environment variable names using these core rules:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-`.
3. Convert everything to uppercase.

Examples:

| Property name | Environment variable |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `clients.inventory.read-timeout` | `CLIENTS_INVENTORY_READTIMEOUT` |
| `server.port` | `SERVER_PORT` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |

For list elements, the index is placed between underscores; for example, `my.service[0].other` maps to `MY_SERVICE_0_OTHER`.

On Windows PowerShell, you can set environment variables for the current process:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:SERVER_PORT = "9090"
java -jar .\orders-service.jar
~~~

On Linux/macOS shells:

~~~bash
SPRING_PROFILES_ACTIVE=prod SERVER_PORT=9090 java -jar orders-service.jar
~~~

Environment variables are an external configuration source, but they do not automatically turn into a secret store. Avoid writing passwords into shell history, CI logs, or public manifests. On platforms such as Kubernetes, use Secret/ConfigMap mounts or an appropriate secret management solution.

## 9. Multiple Documents in One File

Spring Boot supports splitting a single physical file into multiple logical documents. Documents are processed in top-to-bottom order; later documents can override properties from earlier documents.

### 9.1. Multi-document YAML

Use three hyphens `---` to start a new document:

~~~yaml
spring:
  application:
    name: orders-service

clients:
  inventory:
    read-timeout: 500ms
---
spring:
  config:
    activate:
      on-profile: prod

clients:
  inventory:
    read-timeout: 900ms
~~~

The second document is activated only when the `prod` profile matches the `on-profile` expression. When running with other profiles, the shared `500ms` value continues to apply.

### 9.2. Multi-document properties

For `.properties`, use the special `#---` separator:

~~~properties
spring.application.name=orders-service
clients.inventory.read-timeout=500ms
#---
spring.config.activate.on-profile=prod
clients.inventory.read-timeout=900ms
~~~

The separator must start at the beginning of the line with no leading whitespace and have exactly three hyphens after the comment character. This special separator rule belongs to Spring Boot's multi-document mechanism, not standard Java properties syntax.

### 9.3. Document activation conditions

A document can use:

- `spring.config.activate.on-profile`: activates only when the profile expression matches.
- `spring.config.activate.on-cloud-platform`: activates only when Spring Boot detects the corresponding cloud platform.

Example:

~~~yaml
spring:
  application:
    name: orders-service
---
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes

clients:
  inventory:
    base-url: http://inventory.default.svc.cluster.local
~~~

The document above must satisfy both the profile and cloud platform conditions as configured. Multi-document files are useful for keeping small variations in one file, though when environments differ substantially, separate profile-specific files are usually easier to maintain.

## 10. `spring.config.import` and External Configuration Files

In addition to default files, Config Data lets you import extra configuration sources using `spring.config.import`.

Example importing a standalone properties file:

~~~yaml
spring:
  config:
    import: optional:file:./deploy-config/inventory.properties
~~~

Contents of the imported file:

~~~properties
clients.inventory.base-url=https://inventory.internal.example
clients.inventory.read-timeout=900ms
~~~

The `optional:` prefix lets the application continue if the location does not exist. Omit this prefix when the file is mandatory and the application must not run without it.

### 10.1. Distinguishing `location`, `additional-location`, and `import`

| Mechanism | Question it answers |
| --- | --- |
| `spring.config.location` | Which locations should Spring Boot search instead of the default locations? |
| `spring.config.additional-location` | Which directories/files should be added alongside the default locations? |
| `spring.config.import` | Which file or Config Data source should be imported from a configuration document? |

Do not use these three properties interchangeably. Choosing the wrong one can stop default classpath files from loading or prevent an imported source from being processed as intended.

### 10.2. Relationship with Spring Cloud Config

When centralized configuration is needed, an application can use Config Client to import Config Server in versions that support Config Data:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Include the Config Client starter compatible with the Spring Boot/Spring Cloud release train in use. The application name, active profiles, and label can all participate in determining the configuration set returned by the server.

Keep these distinctions clear:

- `application.yml` and `application.properties` are local Config Data sources.
- Config Server is a remote configuration source brought in via the corresponding integration.
- Loading configuration at startup does not automatically mean receiving all subsequent changes.
- Spring Cloud Context's `@RefreshScope` only participates when an appropriate refresh mechanism is triggered; modifying a file on disk does not automatically recreate every bean.

If remote configuration is mandatory for business logic, consider omitting `optional:` and configuring retry/fail-fast according to your version so the application does not start with an incomplete set of values.

## 11. Inspecting Loaded Configuration

### 11.1. Reading values via Environment

You can quickly inspect a key inside the application:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    public void printSelectedValues() {
        System.out.println("application="
                + environment.getProperty("spring.application.name"));
        System.out.println("inventory timeout="
                + environment.getProperty("clients.inventory.read-timeout"));
    }
}
~~~

`Environment.getProperty` returns the final resolved value after sources are combined by precedence. It does not necessarily indicate which specific file provided that value.

### 11.2. Inspecting sources via Actuator

If the application includes Spring Boot Actuator and exposes the appropriate endpoints, `env` and `configprops` can help trace value origins and inspect binding results.

Example exposure configuration in a local environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
~~~

Never expose configuration endpoints to public environments. They can leak property names, deployment details, or sensitive data if value sanitization and access controls are not properly configured. Expose only the minimum required endpoints, paired with authentication and network restrictions.

### 11.3. Enabling Config Data debug logging

When a file is not loaded as expected, enable debug logging for startup and inspect Config Data-related logs. Look for:

- Which file names/locations were considered.
- Which files were actually loaded.
- Which profiles are active.
- Which documents were activated or skipped.
- Whether there were YAML parse errors, missing locations, or failed imports.

Do not conclude a file was not loaded merely because a bean receives a default value; the file may have loaded and then been overridden by a higher-precedence property source.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Editing `application.yml` has no effect | An `application.properties` exists in the same location or a higher-precedence source overrides it | Check for duplicate files and inspect `Environment`/Actuator `env` |
| Profile file has no effect | Profile is not active, wrong file name, or wrong location | Check `SPRING_PROFILES_ACTIVE`, Config Data logs, and `application-{profile}` naming |
| Application cannot find external file | Unexpected working directory, wrong location, or missing read permissions | Check absolute paths, working directory, and startup logs |
| YAML parse error | Incorrect indentation, tabs used, quoting issues, or invalid list syntax | Check the reported error line, validate YAML, and verify nesting levels |
| Placeholder fails to resolve | Referenced key does not exist or is misspelled | Check spelling, property sources, and default value after `:` |
| Incorrect `Duration` binding | Incompatible value format or target type | Use explicit forms like `250ms`, `2s`, `1m`; inspect the bound bean |
| Profile list loses elements | A list in a higher-precedence source replaces the entire lower-precedence list | Check `@ConfigurationProperties` merge rules; do not assume lists append automatically |
| Missing imported file halts startup | Location lacks `optional:` and the file does not exist | Confirm whether the file is mandatory or optional |
| Configuration changed but bean still uses old value | Bean is already initialized and holds the value in its instance | Check bean lifecycle, refresh mechanism, and how the bean reads config |

### 12.1. Lists are not always appended

When binding a list across multiple sources, Spring Boot applies an override rule for lists; values in a higher-precedence source can replace the entire list bound from a lower-precedence source. Do not assume only matching indices are modified or that two lists are automatically concatenated.

Example shared file:

~~~yaml
clients:
  inventory:
    zones:
      - north
      - south
      - central
~~~

Profile-specific file:

~~~yaml
clients:
  inventory:
    zones:
      - production-a
~~~

The bound result for that profile may contain only `production-a`. If you want to merge lists for business requirements, design the configuration structure and explicit merging logic accordingly.

### 12.2. File configuration is not a hot-reload mechanism

Spring Boot loads Config Data during startup. Editing a file on disk after the application is already running does not mean every bean will re-read it. Certain developer tools can restart the application upon detecting changes, but that is a development tool behavior rather than a general production guarantee.

In Spring Cloud, refreshing requires a mechanism to update `Environment` and trigger an appropriate refresh. If a client or bean stores values in its constructor, redesign its lifecycle so updated values can take effect. Always verify each instance after refreshing in a multi-replica deployment.

## 13. Configuration Management Conventions for Spring Cloud Systems

For a service like `orders-service`, you can apply these principles:

1. Place non-sensitive default values in `src/main/resources/application.yml`.
2. Move deployment-specific URLs, timeouts, and profile-specific values outside the JAR or into environment variables.
3. Choose one primary format (`.properties` or YAML) per application.
4. Use feature-based prefixes, such as `clients.inventory` and `clients.pricing`, to prevent key collisions.
5. Use `@ConfigurationProperties` for structured configuration groups and validation for required values.
6. Never commit real passwords, tokens, private keys, or secrets.
7. Use profiles for intentional differences; avoid creating excessive overlapping profiles.
8. Make clear which configurations are mandatory; use `optional:` only for sources that may genuinely be absent.
9. Verify dependency versions and how Config Server is imported according to your compatible release train.
10. Observe final resolved values at runtime and test critical configurations during build/deploy.

## 14. Practice Exercises

**Exercise 1 — Format conversion.** Write the following group of properties in both `.properties` and YAML: application name, server port, Inventory URL, connect timeout, read timeout, and a list of three availability zones. Verify that both formats produce the same keys in `Environment`.

**Exercise 2 — Finding the winning value.** A file inside the JAR sets `server.port=8080`, an external file outside the JAR sets `server.port=8085`, an environment variable sets `SERVER_PORT=8090`, and the command line passes `--server.port=9090`. Determine the final value and describe how to verify it using `Environment`.

**Exercise 3 — Profiles.** Create an `application.yml` with a default timeout of `500ms` and an `application-prod.yml` with a timeout of `900ms`. Run with and without the `prod` profile, and record the results.

**Exercise 4 — YAML errors.** Intentionally introduce an indentation error in a `clients.inventory` group. Observe the parser message and fix the file. Explain why an incorrectly indented key can end up as a property at a different level.

**Exercise 5 — Imports.** Create an `inventory.properties` file outside the JAR and import it with `spring.config.import`. Test startup behavior with and without `optional:` when the file does not exist, and compare the results.

**Exercise 6 — Distributed system.** Declare `spring.application.name`, discovery endpoint, and downstream service timeouts. Separate defaults from production values; identify which values should be supplied via environment variables or Config Server and explain why.

## 15. Key Takeaways and Reference Sources

- `application.properties` and `application.yml` are two ways to represent Config Data; both feed values into the Spring `Environment`.
- Profile-specific files override shared values when the corresponding profile is active.
- External files can override files packaged in the JAR; environment variables and command-line arguments can override Config Data.
- `spring.config.location` replaces default locations; `spring.config.additional-location` adds to them; `spring.config.import` imports additional sources.
- YAML is readable for nested structures but sensitive to indentation and scalar types.
- Modifying a file while the application is running does not automatically mean beans are refreshed.
- When multiple configuration sources exist, always verify the final resolved value and which source supplied it.

Official references to consult for your project's Spring Boot/Spring Cloud version:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Working with YAML and Multi-document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files)
3. [Spring Boot Reference – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
4. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
5. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
