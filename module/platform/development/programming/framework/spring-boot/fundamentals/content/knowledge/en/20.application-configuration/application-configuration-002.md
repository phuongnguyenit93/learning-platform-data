# `application.properties`, `application.yml`, and Choosing a Format

In Spring Boot, **application configuration** consists of the values that allow the same program to run properly across multiple environments: HTTP port, database connection details, logging levels, timeouts, upload limits, or features turned on or off. Instead of hard-coding those values in Java, you can place them in configuration files and let Spring Boot load them through `Environment`.

Two common formats are **`application.properties`** and **`application.yml`**. They serve the same purpose but differ in representation:

- `application.properties` uses **key–value** pairs, typically written in `key=value` form.
- `application.yml` uses **YAML**, allowing values to be grouped into nested structures via indentation.
- Spring Boot reads both as **configuration properties**; most binding mechanisms and auto-configuration work with the loaded values rather than caring whether the original file was `.properties` or `.yml`.

Choosing a format does not make an application "stronger" or "faster." What matters is that **configuration is easy to understand, less error-prone, and loaded correctly from the sources you intend to use**.

## 1. Why separate configuration from source code?

Suppose a retail application runs in three environments:

| Environment | HTTP Port | Database | Logging |
| --- | --- | --- | --- |
| Local | 8080 | Development database | DEBUG on application package |
| Staging | 8081 | Testing database | INFO |
| Production | 8080 | Production database | WARN or INFO |

If every environment switch required editing constructors, Java constants, or committing passwords again, the program would be hard to deploy and maintain.

Spring Boot supports **externalized configuration**: a single artifact can receive configuration from files, profiles, environment variables, Java system properties, command-line arguments, and other sources.

```text
                Java application code
                        |
                        v
               Spring Boot startup
                        |
         +--------------+--------------+
         |              |              |
         v              v              v
   application.*    Environment     Command-line
   & profile files   variables       arguments
         |              |              |
         +--------------+--------------+
                        |
                        v
                Spring Environment
                        |
                        v
             @ConfigurationProperties
                   / @Value
                        |
                        v
              Beans and auto-configuration
```

For example, the application can run on port 8080 locally yet use port 9000 when passed `--server.port=9000`, without changing Java code.

## 2. Configuration file locations and names

In a typical Maven or Gradle project, configuration resides at:

```text
src/
└── main/
    ├── java/
    │   └── com/example/shop/ShopApplication.java
    └── resources/
        ├── application.properties
        └── application.yml
```

Usually **pick one of the two** files above as the base configuration. There is no need to create both `application.properties` and `application.yml` at the same time.

During the build, files under `src/main/resources` are placed on the classpath. Spring Boot uses the **Config Data** mechanism to locate and load configuration files with supported names and locations.

Beyond the classpath, Spring Boot also supports configuration locations outside the artifact, such as a file inside a config directory when running the application:

```text
shop-app.jar
config/
└── application.properties
```

This allows changing configuration values without repackaging the JAR.

### 2.1. What does the `application` name mean?

`application` is the default configuration name Spring Boot looks for. With profiles, filenames can include a suffix:

```text
application.properties
application-dev.properties
application-prod.properties
```

or:

```text
application.yml
application-dev.yml
application-prod.yml
```

You can change the default configuration name using appropriate parameters such as `spring.config.name`, though you should only do so when clearly required.

### 2.2. `.yaml` or `.yml`?

YAML can use either the `.yaml` or `.yml` extension; Spring Boot supports both in appropriate configuration locations. A team should pick **a single convention** to avoid scattered configuration.

In this lesson, the examples use `application.yml`.

## 3. Basic syntax of `application.properties`

A `.properties` file represents configuration line by line:

```properties
spring.application.name=shop-service
server.port=8081
logging.level.com.example.shop=DEBUG
app.catalog.currency=VND
app.catalog.page-size=20
app.catalog.enabled=true
```

The left side of `=` is the key; the right side is the value. A colon `:` can also act as a separator under Java properties rules, but projects should consistently use `=` for readability.

### 3.1. Dotted keys represent logical groups

For example:

```properties
app.email.enabled=true
app.email.sender=no-reply@example.com
app.email.retry.max-attempts=3
app.email.retry.delay=5s
```

You can visualize these keys as a tree:

```text
app
└── email
    ├── enabled
    ├── sender
    └── retry
        ├── max-attempts
        └── delay
```

The dots here are part of the configuration property naming convention. The `.properties` file itself remains a flat list of key–value pairs.

### 3.2. Comments

Use `#` or `!` at the start of a line for comments:

```properties
# Port used for the development environment
server.port=8081

! Limit for email send retry attempts
app.email.retry.max-attempts=3
```

Do not place data that needs to be used inside comments. Also avoid relying on "end-of-line comments" as general `.properties` syntax: a `#` after a value may be treated as part of the value, depending on how it is parsed.

### 3.3. Strings with spaces

For example:

```properties
app.company.display-name=Phuong Workspace
```

You do not need to wrap strings in quotation marks just because they contain spaces. If you write:

```properties
app.company.display-name="Phuong Workspace"
```

the quotation marks may be interpreted as literal characters in the value at the Java properties layer; this is a notable difference compared to YAML.

### 3.4. Basic values all start as text

For example:

```properties
app.feature.enabled=true
app.feature.limit=100
app.feature.timeout=15s
```

A properties file stores values as strings; when binding to Java, Spring Boot can convert `true` to `boolean`, `100` to `int`, and `15s` to `Duration` via the conversion system.

Successful conversion depends on the target Java type and valid value format. Do not assume any string can be coerced into any type.

## 4. Basic syntax of `application.yml`

YAML expresses structure through **indentation**, colons `:`, and lists:

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8081

logging:
  level:
    com.example.shop: DEBUG

app:
  catalog:
    currency: VND
    page-size: 20
    enabled: true
```

The configuration above has equivalent meaning to these flat keys:

```properties
spring.application.name=shop-service
server.port=8081
logging.level.com.example.shop=DEBUG
app.catalog.currency=VND
app.catalog.page-size=20
app.catalog.enabled=true
```

YAML makes parent–child relationships easy to see when many properties share a prefix.

### 4.1. Indentation determines structure

Correct:

```yaml
app:
  notification:
    enabled: true
    max-retries: 3
```

The two properties are:

```text
app.notification.enabled
app.notification.max-retries
```

Unintended:

```yaml
app:
  notification:
  enabled: true
  max-retries: 3
```

Here, `enabled` and `max-retries` are no longer child entries of `notification`. The YAML may still be syntactically valid, but the property structure is no longer what was intended.

**Use spaces for indentation; avoid tabs.** A common convention is two spaces per level. Do not mix different indentation styles within the same file.

### 4.2. Comments in YAML

```yaml
# Email sending feature configuration
app:
  email:
    enabled: true # Enable email in the current environment
```

The `#` character starts a comment when it appears in a valid YAML comment context. If a value genuinely contains `#`, `:`, or other special characters, use a quoted string to reduce the risk of misinterpretation.

### 4.3. When should strings be quoted?

For example:

```yaml
app:
  message: "Ready: accepting requests"
  code: "00123"
  label: "true"
  template: "${APP_TEMPLATE:default}"
```

In YAML, unquoted values may be parsed as booleans, numbers, or null instead of text, depending on the syntax and YAML version. If you need to preserve leading zeros in a code, the literal string `"true"`, or data containing special characters, quote it.

Compare:

```yaml
app:
  enabled: true
  enabled-label: "true"
  max-attempts: 3
  code: "0003"
```

`enabled` has a boolean meaning, `max-attempts` has a numeric meaning, while `enabled-label` and `code` are explicitly represented as strings.

## 5. Direct comparison of the two formats

Consider an application configuration with an HTTP server, an integration client, and retry settings:

**`application.properties`:**

```properties
server.port=8081
app.client.base-url=https://api.example.com
app.client.connect-timeout=2s
app.client.read-timeout=10s
app.client.retry.enabled=true
app.client.retry.max-attempts=3
app.client.retry.backoff=500ms
```

**`application.yml`:**

```yaml
server:
  port: 8081

app:
  client:
    base-url: https://api.example.com
    connect-timeout: 2s
    read-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      backoff: 500ms
```

| Criterion | `application.properties` | `application.yml` |
| --- | --- | --- |
| Structure | Flat key–value | Hierarchical via indentation |
| Finding a property by full name | Often convenient | Requires reading across levels |
| Grouping properties with a shared prefix | Repeats prefix across lines | Groups naturally |
| Complex lists/maps | Uses indices and full keys | More visual representation |
| Syntax risks | Escaping, whitespace, duplicate keys | Indentation, data types, and duplicate keys |
| Easy to copy into environment variables | Closer to flat key names | Requires key name conversion |
| Suitably sized for small projects | Very good | Also good |
| Suitable for large hierarchical configs | Works, though verbose | Often easier to scan |

Spring Boot can bind both to the same Java types. Choosing a format therefore mainly comes down to **readability, team conventions, and change management**.

## 6. Lists in both formats

Suppose an application needs a list of alert recipient email addresses.

### 6.1. Lists in `.properties`

You can use indices:

```properties
app.alert.recipients[0]=ops@example.com
app.alert.recipients[1]=oncall@example.com
app.alert.recipients[2]=security@example.com
```

### 6.2. Lists in YAML

```yaml
app:
  alert:
    recipients:
      - ops@example.com
      - oncall@example.com
      - security@example.com
```

YAML is usually easier to read when a list has many items.

### 6.3. Lists of objects

**Properties:**

```properties
app.integrations[0].name=billing
app.integrations[0].base-url=https://billing.example.com
app.integrations[0].timeout=3s
app.integrations[1].name=inventory
app.integrations[1].base-url=https://inventory.example.com
app.integrations[1].timeout=2s
```

**YAML:**

```yaml
app:
  integrations:
    - name: billing
      base-url: https://billing.example.com
      timeout: 3s
    - name: inventory
      base-url: https://inventory.example.com
      timeout: 2s
```

For structures like `List<IntegrationProperties>`, YAML tends to have less repetition and helps distinguish each item.

### 6.4. Lists across multiple property sources

One notable detail in Spring Boot: when **a list is configured in multiple sources with different precedence**, the list from the higher-precedence source normally **replaces** the list from the lower-precedence source; do not assume elements will be concatenated.

For example, if the shared file defines three recipients while a profile file defines only one recipient under the same key, the bound result may contain only the item from the higher-precedence profile.

If you want to merge across multiple sources, you must design and test that explicitly. Do not rely on intuition that a `List` merges like a `Map`.

## 7. Maps and special keys

Example of a map configuring prices by code:

**Properties:**

```properties
app.price-rules.standard=100
app.price-rules.premium=80
```

**YAML:**

```yaml
app:
  price-rules:
    standard: 100
    premium: 80
```

Both can bind into `Map<String, Integer>` when declared with appropriate `@ConfigurationProperties`.

### 7.1. Map keys containing dots or special characters

If the actual map key is `"region.hcm"` and you need to preserve the dot as part of the key, the configuration may require bracket notation depending on value type and binding behavior.

For example:

```properties
app.labels.[region.hcm]=Southern region
```

With YAML:

```yaml
app:
  labels:
    "[region.hcm]": "Southern region"
```

Spring Boot uses bracket notation to preserve characters that do not follow normal property-name rules in certain `Map` binding cases. If keys contain `/`, dots, or special characters, consult the map binding rules for your Spring Boot version and verify the actual result.

## 8. `@ConfigurationProperties`: one Java model for both files

An advantage of Spring Boot is that you can group related properties into a strongly typed Java object.

Client configuration example:

**`application.properties`:**

```properties
app.partner.base-url=https://partner.example.com
app.partner.timeout=5s
app.partner.max-attempts=3
app.partner.enabled=true
```

Or **`application.yml`:**

```yaml
app:
  partner:
    base-url: https://partner.example.com
    timeout: 5s
    max-attempts: 3
    enabled: true
```

With Spring Boot 3.x and Java supporting records:

```java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration timeout,
        int maxAttempts,
        boolean enabled
) {
}
```

Spring Boot can bind `base-url` to `baseUrl`, `max-attempts` to `maxAttempts`, `"5s"` to `Duration`, and the URL string to `URI` via its binding and conversion mechanism.

### 8.1. Registering the configuration properties class

A common approach is using `@ConfigurationPropertiesScan`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

When the `PartnerProperties` record is in a scanned subpackage, Spring Boot registers it as a configuration properties bean.

Another approach is specifying the class explicitly:

```java
@Configuration
@EnableConfigurationProperties(PartnerProperties.class)
class PartnerConfiguration {
}
```

You do not need to combine both approaches if they aim to register the same class.

### 8.2. Injecting into a service

```java
package com.example.shop.service;

import com.example.shop.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerProperties properties;

    public PartnerService(PartnerProperties properties) {
        this.properties = properties;
    }

    public void printConfiguration() {
        System.out.println(properties.baseUrl());
        System.out.println(properties.timeout());
        System.out.println(properties.maxAttempts());
    }
}
```

The service only cares about a bound object; it does not need to know whether the original values came from YAML, properties, environment variables, or the command line.

### 8.3. Configuration validation

You can combine Jakarta Bean Validation with configuration properties to catch invalid values at startup:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        boolean enabled
) {
}
```

This example assumes the project has a compatible validation dependency, usually the validation starter for the Spring Boot line in use. If `base-url` is missing or `max-attempts` is invalid, binding/validation can fail startup with details about the relevant property.

**Do not treat validation as a tool to mask runtime failures.** It verifies that initial configuration satisfies the contract; external services can still become unresponsive while running.

## 9. `@Value` and when to use it

For a simple value, you can inject it directly:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${app.greeting.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name;
    }
}
```

In the example above, the placeholder has a default value of `Hello` if the property is not found.

Comparison:

| Scenario | Usually appropriate choice |
| --- | --- |
| One or two simple, unrelated properties | `@Value` |
| Multiple properties sharing a prefix | `@ConfigurationProperties` |
| Configuration with lists, maps, or nested objects | `@ConfigurationProperties` |
| Model-level validation needed | `@ConfigurationProperties` with validation |
| Clear constructor injection and easy testing desired | Configuration properties object |

`@Value` supports property placeholders and SpEL; `@ConfigurationProperties` is designed for typed configuration binding and supports relaxed binding. Do not assume both mechanisms share identical key-naming and conversion rules.

## 10. Relaxed binding and property naming conventions

Spring Boot supports **relaxed binding** to map different ways of writing configuration names onto the same Java property.

Java example:

```java
public record StorageProperties(long maxFileSize) {
}
```

Compatible representations depending on configuration source may include:

```properties
app.storage.max-file-size=10485760
```

```yaml
app:
  storage:
    max-file-size: 10485760
```

or an environment variable following the name conversion rule:

```text
APP_STORAGE_MAXFILESIZE=10485760
```

For environment variables in Spring Boot's binding mechanism, canonical kebab-case property names are usually converted by replacing `.` with `_`, removing `-`, and converting to uppercase. Thus `app.storage.max-file-size` corresponds to `APP_STORAGE_MAXFILESIZE` under that rule.

Do not deduce that any custom environment variable with underscores between every word will always be interpreted as expected. To avoid confusion, use canonical key names and verify binding in your deployment environment.

### 10.1. Prefer kebab-case for canonical keys

Readable convention:

```properties
app.email.max-attempts=3
app.storage.max-file-size=10MB
```

Equivalent in YAML:

```yaml
app:
  email:
    max-attempts: 3
  storage:
    max-file-size: 10MB
```

Kebab-case keeps configuration consistent, clear in documentation, and friendly to `@ConfigurationProperties`.

## 11. Duration, DataSize, and useful types

Spring Boot supports binding many configuration values to Java types:

| Value | Example Java type | Meaning |
| --- | --- | --- |
| `true` | `boolean` | Feature flag |
| `42` | `int`, `long` | Number |
| `5s` | `Duration` | Five seconds |
| `250ms` | `Duration` | 250 milliseconds |
| `10MB` | `DataSize` | Data size |
| `https://example.com` | `URI` | URI address |
| `DEBUG` | `LogLevel` or matching enum | Log level |

For example:

```properties
app.http.connect-timeout=2s
app.http.read-timeout=750ms
app.upload.max-file-size=10MB
```

Or:

```yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 750ms
  upload:
    max-file-size: 10MB
```

With custom configuration properties, you can declare:

```java
@ConfigurationProperties(prefix = "app.http")
public record HttpClientProperties(
        Duration connectTimeout,
        Duration readTimeout
) {
}
```

For file sizes:

```java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxFileSize) {
}
```

`DataSize` lives in `org.springframework.util.unit.DataSize`. If `Duration` or `DataSize` is written without a unit, Spring Boot has default unit rules based on binding type and supporting annotations. When configuration needs to be readable, **write units explicitly** such as `2s`, `750ms`, or `10MB`.

## 12. Profile-specific configuration

Spring Boot lets you vary configuration by environment using profiles.

Example using properties:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

**`application.properties`:**

```properties
spring.application.name=shop-service
server.port=8080
app.mail.enabled=false
```

**`application-dev.properties`:**

```properties
server.port=8081
logging.level.com.example.shop=DEBUG
app.mail.enabled=true
```

**`application-prod.properties`:**

```properties
logging.level.root=INFO
app.mail.enabled=true
```

When the `dev` profile is active, profile-specific values can override shared values from lower-precedence sources.

### 12.1. Profiles in YAML work similarly

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

**`application.yml`:**

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8080

app:
  mail:
    enabled: false
```

**`application-dev.yml`:**

```yaml
server:
  port: 8081

logging:
  level:
    com.example.shop: DEBUG

app:
  mail:
    enabled: true
```

### 12.2. Activating a profile

Via command line:

```bash
java -jar shop-service.jar --spring.profiles.active=dev
```

Via environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

Or it can be set in configuration outside a profile-specific document:

```properties
spring.profiles.active=dev
```

For multi-environment deployments, the active profile is usually set outside the artifact so the same build can be used across dev, staging, and production.

### 12.3. Do not place `spring.profiles.active` in the wrong place

In modern Spring Boot Config Data, `spring.profiles.active` and `spring.profiles.default` should only be placed in **non-profile-specific documents**. Do not put them inside `application-dev.yml` or inside a document activated by `spring.config.activate.on-profile`.

Example you should not write in `application-dev.yml`:

```yaml
spring:
  profiles:
    active: prod
```

Because that configuration source is only loaded once the `dev` profile has already been selected, redeclaring active profiles there does not align with modern Config Data rules.

## 13. Multiple YAML documents in a single file

YAML lets you separate documents using the line:

```yaml
---
```

In Spring Boot, you can use `spring.config.activate.on-profile` to specify which document applies when the corresponding profile is active.

Example `application.yml`:

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8080

app:
  notification:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

app:
  notification:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
```

The first document applies in general. The second document is active only when the `dev` profile matches; the third is for `prod`.

### 13.1. When to use multi-document files?

Multi-document YAML is convenient when:

- Only a few values differ between profiles.
- You want to view multiple variants in the same file.
- The configuration is not overly long and document boundaries are clear.

If each environment has a large amount of environment-specific configuration, separate `application-dev.yml` and `application-prod.yml` files are usually easier to manage.

### 13.2. YAML is not the only format with document activation

Modern Spring Boot also supports multi-document `.properties` files using a specific marker syntax. However, multi-document configuration can become hard to follow as files grow; separate profile files are simpler in many projects.

Do not copy YAML's `---` separator line verbatim into `.properties` and expect it to work identically. The marker syntax differs between the two formats.

## 14. Precedence among configuration sources

A property can appear in multiple places:

```text
application.yml
application-prod.yml
Environment variables
Java system properties
Command-line arguments
```

Spring Boot combines `PropertySource`s according to a **precedence order**. A higher-precedence source determines the effective value when the same key appears in multiple sources.

For example:

**`application.properties`:**

```properties
server.port=8080
```

**Environment variable:**

```text
SERVER_PORT=8082
```

**Command line:**

```bash
java -jar shop-service.jar --server.port=9090
```

In Spring Boot's default setup, command-line properties normally take precedence over environment variables and configuration files, so the server will attempt to use port 9090.

### 14.1. Typical high-level order

Conceptually, from common lower-precedence sources to higher-precedence sources:

```text
Default properties
       |
       v
Config Data: application.*, profile files
       |
       v
OS environment / Java system properties
       |
       v
Command-line arguments
```

The full list also includes test properties, JSON application properties, `RandomValuePropertySource`, and other sources. Some sources have very specific positions in Spring Boot; when troubleshooting precedence issues, consult the property source ordering of the version you are running rather than treating a simplified diagram as a full specification.

### 14.2. Profile-specific files can override shared files

For example:

```properties
# application.properties
app.feature.enabled=false
```

```properties
# application-dev.properties
app.feature.enabled=true
```

If the `dev` profile is active and no higher-precedence source overrides it, the value used is `true`.

### 14.3. What if both `.properties` and YAML exist in the same location?

Spring Boot has a precedence rule when both `application.properties` and a YAML file with the same logical name sit in the **same configuration location**: `.properties` has higher precedence than YAML in that case.

For example:

```text
src/main/resources/
├── application.properties  # app.mode=SAFE
└── application.yml         # app.mode: FAST
```

Do not rely on mixing these two files to manage two versions of configuration. Pick one primary format and consolidate overlapping keys into one place to avoid confusion over where the actual value comes from.

### 14.4. How to verify the actual value

You can read `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationReporter {

    private final Environment environment;

    public ConfigurationReporter(Environment environment) {
        this.environment = environment;
    }

    public int configuredPort() {
        return environment.getProperty(
                "server.port",
                Integer.class,
                8080
        );
    }
}
```

This code returns the configured value resolved across property sources. It does not prove that the HTTP port was bound successfully and that the server is listening: to confirm that, check the web server logs or send an actual HTTP request.

## 15. Property placeholders and default values

Spring Boot supports placeholders referencing other properties:

**Properties:**

```properties
app.base-url=https://example.com
app.callback-url=${app.base-url}/callback
```

**YAML:**

```yaml
app:
  base-url: https://example.com
  callback-url: "${app.base-url}/callback"
```

Once resolved, `app.callback-url` uses the value of `app.base-url`.

### 15.1. Fallback values

```properties
app.greeting=${GREETING_TEXT:Hello}
```

Equivalent:

```yaml
app:
  greeting: "${GREETING_TEXT:Hello}"
```

If the `GREETING_TEXT` variable/property is present, the placeholder uses that value. Otherwise, it uses `Hello` via the fallback syntax.

### 15.2. Secrets from the deployment environment

Do not commit passwords directly:

```properties
# Avoid storing production passwords in Git
spring.datasource.password=production-secret-value
```

Instead:

```properties
spring.datasource.password=${DB_PASSWORD}
```

Or:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
```

The `DB_PASSWORD` variable is provided by the deployment environment or secret management system. If it is missing without a fallback value, startup can fail when the required property is resolved/bound; this is usually desirable behavior for a mandatory secret.

**Never place secrets in logs, diagnostic endpoints, or real connection examples.** Using placeholders does not protect a secret if application code intentionally prints that value.

## 16. `spring.config.import` and external configuration

Sometimes you want local or shared configuration separated from `application.yml`.

Spring Boot supports `spring.config.import` to import another Config Data source.

For example:

```properties
spring.config.import=optional:file:./config/local.properties
```

Or YAML:

```yaml
spring:
  config:
    import: "optional:file:./config/local.yml"
```

`optional:` indicates that a missing file is acceptable. If you omit `optional:` and the source does not exist, Spring Boot can fail at startup with an error related to the Config Data location.

### 16.1. When to use import?

Common cases include:

- Separating local machine configuration from files committed to Git.
- Importing an operational configuration file outside the JAR.
- Organizing configuration by module or environment under a clear contract.
- Reading data from framework-supported Config Data sources.

`spring.config.import` is a startup configuration mechanism. Do not treat it as a runtime watcher that automatically updates beans whenever the file is edited.

### 16.2. Distinguishing `spring.config.import`, `location`, and `additional-location`

| Property | General meaning |
| --- | --- |
| `spring.config.import` | Imports a Config Data source from the configuration currently being processed |
| `spring.config.location` | Specifies the configuration locations to search, potentially replacing default locations |
| `spring.config.additional-location` | Adds locations to the default search list |
| `spring.config.name` | Replaces the default logical name `application` |

Properties that control **where configuration files are found** must generally be provided early enough, such as via environment variables, Java system properties, or command-line arguments. Putting them inside a file that is only discovered after searching has already happened may not have the intended effect.

### 16.3. When external configuration outside the JAR is needed

A simple layout:

```text
deploy/
├── shop-service.jar
└── config/
    └── application-prod.yml
```

When run in the appropriate directory with the `prod` profile activated, Spring Boot can discover external configuration in supported default locations. If the location is non-standard, pass `spring.config.additional-location` or `spring.config.import` according to your application's design.

## 17. Common YAML pitfalls

YAML is concise for nested structures, but it is prone to subtle errors.

### 17.1. Wrong indentation

Incorrect:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
   username: shop_user
```

`username` is not at the same indentation level as `url`, which can cause a YAML parse error.

Correct:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
```

### 17.2. Using tabs

YAML uses spaces to represent indentation. Tabs in indentation can cause the parser to fail.

Configure your editor to use spaces and enable whitespace visibility if you edit YAML frequently.

### 17.3. Duplicate keys

For example:

```yaml
server:
  port: 8080

server:
  port: 8081
```

The `server` key is declared twice in the same mapping. Depending on the parser and configuration, duplicate keys may be rejected or result in unexpected values.

In Spring Boot, it is best **not to create duplicate keys within the same YAML document**. If you need environment-based overrides, use profile-specific documents or files.

### 17.4. Wrong type representation

Example partner code:

```yaml
app:
  partner-code: 0007
```

If you need to preserve `"0007"` exactly as text, write:

```yaml
app:
  partner-code: "0007"
```

Similarly, a value that looks like a boolean or null but is meant as a string label should also be quoted.

### 17.5. Strings containing `:` and `#`

To reduce parser ambiguity:

```yaml
app:
  message: "Status: ready"
  display-label: "Plan #1"
```

Quoted strings are preferable when values contain characters with syntactic meaning.

### 17.6. Confusing a YAML list with a map

List:

```yaml
app:
  servers:
    - host: api-1.example.com
      port: 8080
    - host: api-2.example.com
      port: 8080
```

Map:

```yaml
app:
  servers:
    primary:
      host: api-1.example.com
      port: 8080
    fallback:
      host: api-2.example.com
      port: 8080
```

Lists fit when order matters and multiple items share the same role; maps fit when you need lookup by keys such as `primary` and `fallback`.

## 18. Common `.properties` pitfalls

### 18.1. Duplicate keys

```properties
server.port=8080
server.port=8081
```

When two identical keys appear in the same file, one value may be overwritten during reading. Rather than relying on intra-file override behavior, keep **a single unique key** or move variant settings into profiles.

### 18.2. Misunderstanding quotation marks

Do not write:

```properties
app.title="My Shop"
```

if you expect Java properties to strip the quotes automatically. Use:

```properties
app.title=My Shop
```

YAML has its own quoting rules; do not copy string representations verbatim between the two formats without checking.

### 18.3. Escaping characters

Java `.properties` has escaping rules for backslashes, spaces, and certain characters. For example, a Windows path:

```properties
app.storage.directory=C:\\data\\shop
```

In YAML, if using a single-quoted string:

```yaml
app:
  storage:
    directory: 'C:\data\shop'
```

YAML single quotes do not interpret backslashes as escape sequences the way YAML double quotes do, so they are often easier for Windows paths. If you use double quotes, you must handle YAML escaping rules.

### 18.4. Long lists become hard to read

When `.properties` has dozens of keys with indices like `[0]`, `[1]`, `[2]`, the configuration remains valid but becomes harder to edit and review. This is a practical reason to consider YAML for multi-level lists of objects.

## 19. Logging configuration in both formats

**Properties:**

```properties
logging.level.root=INFO
logging.level.com.example.shop=DEBUG
logging.file.name=logs/shop-service.log
```

**YAML:**

```yaml
logging:
  level:
    root: INFO
    com.example.shop: DEBUG
  file:
    name: logs/shop-service.log
```

Both provide the properties that the Spring Boot logging system can read.

### 19.1. A specific note about YAML and logging

Log levels are configured by package name, such as `com.example.shop`, rather than a single Java class. YAML allows keeping `com.example.shop` as a single key in the mapping under `logging.level`, so you normally do not need to split the package name across multiple YAML levels.

### 19.2. Do not log sensitive information

When diagnosing configuration, you might be tempted to print the entire `Environment` or `@ConfigurationProperties`. However, those objects may contain passwords, tokens, or internal endpoints.

Use selective logging and masking mechanisms provided by your observability stack instead of printing every property value.

## 20. Datasource configuration and runtime environment

Example `application.properties`:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
spring.datasource.hikari.maximum-pool-size=10
```

Equivalent YAML:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
```

This is an example configuration for an application that has a JDBC driver and an appropriate datasource dependency. **Simply adding properties does not make Spring Boot supply the driver or create the database automatically.**

If the application lacks a JDBC driver, the database server is not running, or the credentials are wrong, startup or database operations can still fail.

### 20.1. Separating environments

For example:

```text
application.yml
application-dev.yml
application-prod.yml
```

The shared file holds non-sensitive configuration that is identical across environments. Profile files hold only the values that differ. Secrets should be supplied from the deployment environment's configuration/secret management system.

Do not copy an `application-prod.yml` containing real passwords into the repository for local runs.

## 21. Should you choose `application.properties` or `application.yml`?

There is no single format that is always right for every project. Consider the following criteria.

### 21.1. Choose `.properties` when

- Configuration is small and consists mostly of scalar key–value pairs.
- The team is familiar with full property names like `spring.datasource.url`.
- You need to edit a single key quickly or compare directly against framework documentation.
- You want to avoid indentation pitfalls.
- The project already uses `.properties` stably with no reason to switch.

For example:

```properties
spring.application.name=order-service
server.port=8080
management.endpoints.web.exposure.include=health,info
```

### 21.2. Choose YAML when

- Configuration has multiple hierarchical levels.
- There are many lists or lists of objects.
- You want to group each module's configuration into an easy-to-scan structure.
- The team has good YAML editor/lint tooling and is comfortable with indentation.
- You use profile documents or complex configurations that benefit from clear structure.

For example:

```yaml
app:
  payment:
    retries:
      enabled: true
      max-attempts: 3
      backoff: 500ms
    providers:
      - name: bank
        timeout: 3s
      - name: wallet
        timeout: 2s
```

### 21.3. Decision table

| Project characteristic | More suitable format |
| --- | --- |
| 10–20 scalar properties | `.properties` |
| Many keys sharing a prefix | YAML |
| Many lists of objects | YAML |
| Wanting to reduce indentation errors | `.properties` |
| Team already standardized on one format | Keep the current format |
| Deploying with environment variables | Both work well |
| Using `@ConfigurationProperties` and validation | Both work well |
| Needing profile-specific files | Both work well |

**Consistency within the same codebase is usually more important than minor gains from switching formats.** When both formats can express the configuration, pick the one your team can review and debug most easily.

## 22. Should you convert between the two formats?

You can migrate from `.properties` to YAML as configuration grows. However, converting is not merely changing the file extension.

Original example:

```properties
app.queue.max-attempts=5
app.queue.retry-delay=2s
app.queue.consumers[0].name=orders
app.queue.consumers[0].enabled=true
app.queue.consumers[1].name=payments
app.queue.consumers[1].enabled=false
```

After conversion:

```yaml
app:
  queue:
    max-attempts: 5
    retry-delay: 2s
    consumers:
      - name: orders
        enabled: true
      - name: payments
        enabled: false
```

When converting, preserve **configuration semantics**:

1. Property names after flattening still match.
2. Special string values such as `"0012"` do not change type.
3. Lists keep the exact same order and element count.
4. `${...}` placeholders still resolve properly.
5. Profile activation still applies to the right environments.
6. No old file with duplicate keys remains to accidentally override the new file.

These are the checks to verify in a real configuration migration. Performing a format migration does not change the underlying fact: Spring Boot receives property values from `Environment`.

## 23. Verifying that configuration loaded properly

### 23.1. Checking with `Environment`

Example of a startup reporter:

```java
package com.example.shop;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class SettingsReporter implements ApplicationRunner {

    private final Environment environment;

    public SettingsReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Application: " +
                environment.getProperty("spring.application.name")
        );
        System.out.println(
                "Catalog size: " +
                environment.getProperty("app.catalog.page-size")
        );
    }
}
```

This snippet observes non-sensitive properties after the context has refreshed. Do not print passwords or tokens.

### 23.2. Checking with `@ConfigurationProperties`

For `PartnerProperties`, you can write a test:

```java
@SpringBootTest(properties = {
    "app.partner.base-url=https://test.example.com",
    "app.partner.timeout=3s",
    "app.partner.max-attempts=2",
    "app.partner.enabled=true"
})
class PartnerPropertiesTest {

    @Autowired
    PartnerProperties properties;

    @Test
    void bindsPartnerProperties() {
        assertThat(properties.baseUrl())
                .isEqualTo(URI.create("https://test.example.com"));
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.maxAttempts()).isEqualTo(2);
    }
}
```

This example assumes the project has Spring Boot Test, JUnit 5, AssertJ, and `PartnerProperties` registered in the test context. The test verifies binding from property values to the Java model, independent of whether the original values came from `.properties` or YAML.

### 23.3. Using Actuator in appropriate environments

Spring Boot Actuator provides `/actuator/env` and `/actuator/configprops` endpoints when the dependency is added and they are enabled and exposed appropriately.

They are useful for checking:

- Which property sources were loaded.
- Which properties were bound into configuration properties beans.
- Why a value might differ from what you expected in a file.

These endpoints can expose sensitive metadata. Configure appropriate security and masking mechanisms; do not expose them openly to the public Internet for debugging.

### 23.4. Reading binding error messages

If Spring Boot cannot bind:

```properties
app.partner.max-attempts=abc
```

to `int maxAttempts`, startup can report a binding error showing the property name, value, target type, and configuration source location.

When an error occurs, check the **key, value, profile, Java type, and loaded file location** before rushing to alter the Java model.

## 24. Complete practical example: one application, two formats

Suppose an application needs operational configuration for a partner API.

### 24.1. Configuration in properties format

```properties
spring.application.name=partner-gateway
server.port=8081

app.partner.enabled=true
app.partner.base-url=https://partner.example.com
app.partner.timeout=5s
app.partner.max-attempts=3

logging.level.com.example.gateway=INFO
```

### 24.2. Equivalent configuration in YAML format

```yaml
spring:
  application:
    name: partner-gateway

server:
  port: 8081

app:
  partner:
    enabled: true
    base-url: https://partner.example.com
    timeout: 5s
    max-attempts: 3

logging:
  level:
    com.example.gateway: INFO
```

### 24.3. Binding to Java

```java
package com.example.gateway.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        boolean enabled,
        URI baseUrl,
        Duration timeout,
        int maxAttempts
) {
}
```

Application startup class:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

Service:

```java
package com.example.gateway.service;

import com.example.gateway.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {

    private final PartnerProperties properties;

    public PartnerGateway(PartnerProperties properties) {
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties.enabled();
    }

    public String targetHost() {
        return properties.baseUrl().getHost();
    }
}
```

If you use either one of the two files alongside the same other configuration sources, the service receives equivalent values. This clearly illustrates that **the file format is the input representation; the binding model and Java logic do not need to change with the format**.

### 24.4. Trying a command-line override

Suppose the file sets:

```properties
server.port=8081
```

Run:

```bash
java -jar partner-gateway.jar --server.port=9090
```

Unless higher-precedence configuration or other constraints exist, Spring Boot will use port 9090 for the web server. The exact same rule applies when the original file source is YAML.

## 25. Practice exercises

### Exercise 1 — Writing two equivalent files

Create configuration for a ticket-booking application including:

- `spring.application.name=booking-service`.
- `server.port=8085`.
- `app.booking.max-seats=8`.
- `app.booking.confirmation-timeout=30s`.
- `app.booking.enabled=true`.

Write one version in `.properties`, one in YAML, and explain the corresponding key paths. Keep only one active when running to avoid duplicate keys.

### Exercise 2 — Lists and maps

Configure three payment providers with `name`, `base-url`, and `timeout`. Write this in properties with `[0]`, `[1]`, `[2]`, then rewrite it as a YAML list.

Next, create a map `app.currency.decimals` with keys `VND`, `USD`, `JPY`. Propose an appropriate Java model for each structure.

### Exercise 3 — Binding data types

Create the record:

```java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        boolean enabled,
        DataSize maxFileSize,
        Duration timeout
) {
}
```

Configure `max-file-size=20MB` and `timeout=45s`. Inject the record into a service and print the non-sensitive values.

Explain how Spring Boot converts text into `DataSize` and `Duration`.

### Exercise 4 — Dev and prod profiles

Create `application.yml`, `application-dev.yml`, and `application-prod.yml`.

- Shared config: application name and default feature flag.
- Dev: port 8081, DEBUG logging for the application package.
- Prod: port 8080, INFO logging.

Run twice with `--spring.profiles.active=dev` and `--spring.profiles.active=prod`. Verify the loaded values.

### Exercise 5 — Multi-document YAML

Convert Exercise 4 into a single `application.yml` file with three documents: shared, dev, and prod. Use `spring.config.activate.on-profile`.

Explain why `spring.profiles.active` should not be placed inside a document activated by `on-profile`.

### Exercise 6 — Spotting YAML errors

Given the configuration:

```yaml
app:
  email:
    enabled: true
   retry:
      max-attempts: 3
```

Identify the indentation error, fix it, and list the resulting keys after flattening.

### Exercise 7 — Tracing the override source

Suppose:

```properties
# application.properties
server.port=8080
```

```properties
# application-dev.properties
server.port=8081
```

The runtime environment has `SERVER_PORT=8082`, and the command line has `--server.port=9090`.

Predict the port used when the `dev` profile is active under default settings, then verify via logs and an HTTP request.

### Exercise 8 — Replacing placeholders from the environment

Set:

```properties
app.partner.api-key=${PARTNER_API_KEY}
```

Pass the secret from your local environment variable or a secret manager used for the exercise. Confirm the application can bind the property without printing the secret to the console.

Explain why real API keys must not be committed to the repository.

### Exercise 9 — Controlled format migration

Choose a `.properties` file containing lists/maps and convert it completely to YAML. Delete or move the old file out of Spring Boot's auto-loaded locations, then verify:

- Key scalar properties retain their values.
- Lists preserve the exact element count and order.
- `@ConfigurationProperties` binds successfully.
- Profiles retain the same meaning as before.
- No duplicate properties remain across two files in the same location.

### Exercise 10 — Choosing a format for a team

One team has 15 simple properties, while another has dozens of integration objects and multiple profiles. Recommend a format for each team, explain your criteria, and propose naming/indentation conventions the team can maintain long-term.

## 26. Key takeaways

`application.properties` and `application.yml` are both **ways to declare configuration properties for Spring Boot**. `.properties` is simple, flat, and easy to search by full key name. YAML expresses nested structures, lists, and maps more visually, though it requires careful indentation and quoting.

Spring Boot loads configuration into `Environment`, combines property sources by precedence, and binds values into Java via `@ConfigurationProperties` or `@Value`. Both formats support profile-specific configuration, property placeholders, and overrides from the deployment environment.

When choosing a format, prioritize **consistency, reviewability, and ease of diagnostics**. Use one primary format across the project, keep canonical keys in kebab-case, use `@ConfigurationProperties` for structured configuration, avoid storing secrets in source code, and verify actual values after Spring Boot starts up.
