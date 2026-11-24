# Converting Canonical Property Names to Environment Variable Names in Spring Boot

## 1. Why do property names need to be converted when using environment variables?

Spring Boot supports **Externalized Configuration**: the same application can receive configuration from `application.yml`, `application.properties`, operating system environment variables, Java system properties, command-line arguments, and other sources. As a result, development teams can build a single JAR or container image and deploy it across multiple environments without modifying source code every time a service URL, HTTP port, or timeout threshold changes.

Property names in Spring Boot configuration files typically follow the format **lowercase, with levels separated by dots, and words within a level separated by hyphens**:

~~~properties
server.port=8080
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
app.gateway.connect-timeout=5s
app.retry.max-attempts=3
~~~

However, environment variables in a shell, Docker, or Kubernetes are usually named using uppercase letters and underscores:

~~~text
SERVER_PORT
SPRING_DATASOURCE_URL
APP_GATEWAY_CONNECTTIMEOUT
APP_RETRY_MAXATTEMPTS
~~~

Spring Boot provides a **relaxed binding** mechanism that maps these environment variable names to structured properties. To avoid confusion, you need to understand a consistent set of conversion rules.

This lesson focuses on three topics: **name conversion**, **passing values when running the application**, and **understanding how Spring Boot uses those values**. Just because an application can read an environment variable does not mean that variable is always the highest-priority source: command-line arguments or test configurations can override it further.

## 2. Official conversion rules

For a property name in canonical form (canonical property name), the rule to convert it into an environment variable name for Spring Boot relaxed binding consists of three steps:

1. **Replace every dot (`.`) with an underscore (`_`).**
2. **Remove every hyphen (`-`).** Do not replace hyphens with underscores.
3. **Convert all letters to uppercase.**

For example, with the property:

~~~properties
spring.main.log-startup-info=true
~~~

We perform:

~~~text
Canonical name:        spring.main.log-startup-info
Replace dots:          spring_main_log-startup-info
Remove hyphens:        spring_main_logstartupinfo
Uppercase:             SPRING_MAIN_LOGSTARTUPINFO
~~~

The resulting environment variable name according to the rule is:

~~~bash
SPRING_MAIN_LOGSTARTUPINFO=true
~~~

The key point to remember is that **dots and hyphens are not treated the same way**:

- `.` describes the boundary between property levels, so it becomes `_`.
- `-` joins words within the same property name segment, so it is **removed**.

Therefore, `app.client.read-timeout` becomes `APP_CLIENT_READTIMEOUT`, whereas `app.client.read.timeout` becomes `APP_CLIENT_READ_TIMEOUT`. The latter represents a different structure.

### Common conversion table

| Canonical property name | Environment variable name |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.hikari.maximum-pool-size` | `SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `app.cache.expire-after-write` | `APP_CACHE_EXPIREAFTERWRITE` |
| `app.security.token-ttl` | `APP_SECURITY_TOKENTTL` |

These examples illustrate the **name formation rules**. For a variable to take effect, the application must also consume the corresponding property, or Spring Boot must have an auto-configuration component that reads that property.

## 3. Distinguishing dots and hyphens through YAML structure

A YAML file can express hierarchy using indentation:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 5s
  retry:
    max-attempts: 3
~~~

When loaded as Config Data, the property names are:

~~~properties
app.client.base-url=https://api.example.org
app.client.connect-timeout=5s
app.retry.max-attempts=3
~~~

Corresponding environment variable names:

~~~bash
APP_CLIENT_BASEURL=https://api.example.org
APP_CLIENT_CONNECTTIMEOUT=5s
APP_RETRY_MAXATTEMPTS=3
~~~

You do not need to arbitrarily "translate" YAML indentation into underscores. First, find the **flattened property name** by joining YAML levels with dots, then apply the three steps in the previous section.

For example, compare two structures:

~~~yaml
# Structure A
app:
  retry:
    max-attempts: 3
~~~

~~~yaml
# Structure B (a separate example file)
app:
  retry:
    max:
      attempts: 3
~~~

The canonical name of structure A is `app.retry.max-attempts`, corresponding to `APP_RETRY_MAXATTEMPTS`.

The canonical name of structure B is `app.retry.max.attempts`, corresponding to `APP_RETRY_MAX_ATTEMPTS`.

**Do not manually insert underscores at every English word boundary.** In canonical conversion, `_` marks a **property level boundary**, while word boundaries within a kebab-case segment are removed.

## 4. Expressing lists using indices

A Spring Boot property name can refer to a list element using the `[index]` syntax, with indices starting at 0.

YAML example:

~~~yaml
app:
  regions:
    - vn
    - sg
    - jp
~~~

Flattened property names:

~~~properties
app.regions[0]=vn
app.regions[1]=sg
app.regions[2]=jp
~~~

To convert to environment variables, Spring Boot requires **surrounding the index with underscores** instead of square brackets:

~~~bash
APP_REGIONS_0=vn
APP_REGIONS_1=sg
APP_REGIONS_2=jp
~~~

The general pattern is:

~~~text
my.service[0].other
           ↓
MY_SERVICE_0_OTHER
~~~

The underscores surrounding the number `0` indicate that this is a **list index**, not a nested property name containing a digit.

### Lists of objects

Suppose:

~~~yaml
app:
  backends:
    - name: primary
      base-url: "https://primary.example.org"
      max-connections: 20
    - name: backup
      base-url: "https://backup.example.org"
      max-connections: 10
~~~

Flattened form:

~~~properties
app.backends[0].name=primary
app.backends[0].base-url=https://primary.example.org
app.backends[0].max-connections=20
app.backends[1].name=backup
app.backends[1].base-url=https://backup.example.org
app.backends[1].max-connections=10
~~~

Environment variable names according to the rule:

~~~bash
APP_BACKENDS_0_NAME=primary
APP_BACKENDS_0_BASEURL=https://primary.example.org
APP_BACKENDS_0_MAXCONNECTIONS=20
APP_BACKENDS_1_NAME=backup
APP_BACKENDS_1_BASEURL=https://backup.example.org
APP_BACKENDS_1_MAXCONNECTIONS=10
~~~

The way to read `APP_BACKENDS_1_MAXCONNECTIONS` is: `app` → `backends` → second element of the list → `max-connections` property.

With nested lists, each list level has its own index. For example, the flattened name `app.teams[0].members[1].name` converts to `APP_TEAMS_0_MEMBERS_1_NAME`.

## 5. Environment variable names and relaxed binding are not completely separate mechanisms

Spring Boot often uses `@ConfigurationProperties` to bind canonical property names to Java fields. Suppose Java has a record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

A configuration file might be written as:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 5s
    max-retries: 3
~~~

At deployment time, instead of editing the YAML, you can pass:

~~~bash
APP_CLIENT_BASEURL=https://prod-api.example.org
APP_CLIENT_CONNECTTIMEOUT=2s
APP_CLIENT_MAXRETRIES=6
~~~

The Binder understands that `base-url` can map to the Java field `baseUrl`, `connect-timeout` to `connectTimeout`, and `max-retries` to `maxRetries`.

Here, three steps should be distinguished:

1. **YAML flattening:** `app.client.connect-timeout` is the property path name.
2. **Converting to an environment variable:** `APP_CLIENT_CONNECTTIMEOUT` is the canonical name used for the OS environment.
3. **Binding into Java:** `connectTimeout` is the field/record component name to which Spring Boot assigns a `Duration` value.

An environment variable name is not a Java field name; nor is a Java field name always the canonical property name in configuration.

In Java, enable scanning for `@ConfigurationProperties`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

If no higher-priority source overrides them, `ClientProperties` will receive the production base URL, a 2-second timeout, and a retry count of 6.

## 6. Complete example: base configuration and overriding with environment variables

Suppose an order-processing application has `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  checkout:
    enabled: false
    request-timeout: 5s
  retry:
    max-attempts: 2
  alerts:
    channels:
      - email
      - log
~~~

Corresponding environment variables:

| Property | Environment variable |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `server.port` | `SERVER_PORT` |
| `app.checkout.enabled` | `APP_CHECKOUT_ENABLED` |
| `app.checkout.request-timeout` | `APP_CHECKOUT_REQUESTTIMEOUT` |
| `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `app.alerts.channels[0]` | `APP_ALERTS_CHANNELS_0` |
| `app.alerts.channels[1]` | `APP_ALERTS_CHANNELS_1` |

Example running on Linux/macOS:

~~~bash
export SERVER_PORT=9090
export APP_CHECKOUT_ENABLED=true
export APP_CHECKOUT_REQUESTTIMEOUT=12s
export APP_RETRY_MAXATTEMPTS=5

java -jar order-service.jar
~~~

Provided there is no higher-priority source, the effective values will be:

~~~properties
spring.application.name=order-service
server.port=9090
app.checkout.enabled=true
app.checkout.request-timeout=12s
app.retry.max-attempts=5
~~~

Unchanged keys, such as `app.alerts.channels`, can still come from the base file packaged inside the JAR.

**Operational note:** changing environment variables in a terminal after the Java process has already started does not automatically update Config Data or bound beans. Usually the application must be restarted to pick up configuration from the new environment, unless a dedicated refresh mechanism is designed.

## 7. Setting environment variables across operating systems and runtime tools

### 7.1. Linux and macOS

A common way in a shell is `export`:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
export SERVER_PORT=9090
export APP_CLIENT_CONNECTTIMEOUT=3s

java -jar app.jar
~~~

You can also set variables for **a single command**:

~~~bash
SERVER_PORT=9090 APP_CLIENT_CONNECTTIMEOUT=3s java -jar app.jar
~~~

The second approach scopes the variables to the process launched by that command. Variable names must follow shell rules; uppercase letters and underscores are generally the most compatible.

### 7.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:SERVER_PORT = "8082"
$env:APP_CLIENT_CONNECTTIMEOUT = "4s"

java -jar app.jar
~~~

Do not use Bash's `export ...` syntax directly in PowerShell. PowerShell environment variables are set through the `$env:` namespace.

### 7.3. Windows Command Prompt

~~~bat
set SPRING_PROFILES_ACTIVE=dev
set SERVER_PORT=8082
set APP_CLIENT_CONNECTTIMEOUT=4s

java -jar app.jar
~~~

In batch scripts, `setlocal` and `endlocal` can be used to limit environment variable changes to the script scope. Note that values do not need surrounding quotes unless there is a specific reason; with `set "NAME=value"`, quotes help avoid introducing trailing spaces into the value.

### 7.4. Docker

Docker allows supplying environment variables when running a container:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=9090 \
  -e APP_CLIENT_CONNECTTIMEOUT=3s \
  -p 9090:9090 \
  example/order-service:latest
~~~

Here:

- `SPRING_PROFILES_ACTIVE` selects the profile.
- `SERVER_PORT` can change the web server port inside the container.
- `-p 9090:9090` maps the host port to the container port, which is a Docker operation **separate** from Spring Boot property configuration.

If you change `SERVER_PORT` to 8085 while keeping the `-p 9090:9090` mapping, the host may reach the wrong port. When changing the application port, update the network configuration accordingly.

### 7.5. Docker Compose

~~~yaml
services:
  order-service:
    image: example/order-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SERVER_PORT: "9090"
      APP_CLIENT_CONNECTTIMEOUT: "3s"
      APP_RETRY_MAXATTEMPTS: "5"
    ports:
      - "9090:9090"
~~~

Values that look like numbers or booleans should be placed in quotes in Compose YAML to clearly express the intent of passing environment variable strings.

### 7.6. Kubernetes

In a Deployment manifest, Kubernetes provides an `env` field:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:latest
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SERVER_PORT
              value: "9090"
            - name: APP_CLIENT_CONNECTTIMEOUT
              value: "3s"
          ports:
            - containerPort: 9090
~~~

Kubernetes supplies these variables to the process inside the container. Spring Boot reads them through the operating system environment configuration source at startup.

For sensitive data, use the deployment environment's secret-provisioning mechanism instead of writing real values into public manifests.

## 8. Canonical names, variable names, and Java property names: comparison table

Suppose the application has a Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Api api,
        Retry retry,
        boolean auditEnabled
) {
    public record Api(
            String baseUrl,
            Duration readTimeout
    ) {}

    public record Retry(int maxAttempts) {}
}
~~~

Corresponding naming:

| Java path | Canonical property name | Environment variable |
| --- | --- | --- |
| `api().baseUrl()` | `app.api.base-url` | `APP_API_BASEURL` |
| `api().readTimeout()` | `app.api.read-timeout` | `APP_API_READTIMEOUT` |
| `retry().maxAttempts()` | `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `auditEnabled()` | `app.audit-enabled` | `APP_AUDITENABLED` |

When reading the table, do not invent the name `APP_API_BASE_URL` just because the record component is `baseUrl`. According to Spring Boot's standard environment variable rule, `app.api.base-url` produces `APP_API_BASEURL`.

Spring Boot may support flexible name normalization in certain contexts, but **when designing configuration, follow the documented conversion** so results are predictable and every environment uses a single naming convention.

## 9. Multiple environment variables for lists: how they bind to Java

Suppose the application receives a list of service addresses:

~~~yaml
app:
  services:
    - name: catalog
      url: "https://catalog-dev.example.org"
    - name: payment
      url: "https://payment-dev.example.org"
~~~

Typed configuration:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServicesProperties(List<ServiceEndpoint> services) {
    public record ServiceEndpoint(String name, String url) {}
}
~~~

When converted to environment variables:

~~~bash
APP_SERVICES_0_NAME=catalog
APP_SERVICES_0_URL=https://catalog.example.org
APP_SERVICES_1_NAME=payment
APP_SERVICES_1_URL=https://payment.example.org
~~~

The Binder can construct `List<ServiceEndpoint>` from names containing the indices `_0_` and `_1_`.

If a list comes from multiple sources with different priorities, **do not assume Spring Boot will merge elements across sources index by index**. When binding to a `List`, the list from the higher-priority source typically replaces the older list. When overriding a list in a deployment environment, provide **all desired elements** to avoid incomplete configuration.

For individual environment variables, the clearest approach is giving each element its own variable with the exact index. Do not put an entire list of objects into a single comma-separated string and assume Spring Boot will parse it into nested objects.

## 10. Environment variable values and type conversion

Environment variables from the operating system are passed to the process as **strings**. When binding into Java objects, Spring Boot can convert strings to target types using supported converters.

For example:

~~~yaml
# application.yml — default values
app:
  worker:
    enabled: false
    count: 2
    timeout: 5s
    ratio: 0.25
~~~

Override variables:

~~~bash
APP_WORKER_ENABLED=true
APP_WORKER_COUNT=6
APP_WORKER_TIMEOUT=12s
APP_WORKER_RATIO=0.75
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        boolean enabled,
        int count,
        Duration timeout,
        double ratio
) {}
~~~

The strings `true`, `6`, `12s`, and `0.75` are converted into `boolean`, `int`, `Duration`, and `double` when binding succeeds.

However, if you pass:

~~~bash
APP_WORKER_COUNT=not-a-number
~~~

then conversion to `int` can fail when the application creates the configuration/bean. **Having the right variable name does not guarantee that the value has a valid type.**

For required properties, add validation on the configuration class or a check at startup. For secrets, do not put real values into logs or screenshots.

## 11. Precedence order: environment variables can beat profile-specific files

Suppose you have a base file:

~~~yaml
# application.yml
server:
  port: 8080
app:
  client:
    read-timeout: 5s
~~~

A profile file:

~~~yaml
# application-prod.yml
server:
  port: 9090
app:
  client:
    read-timeout: 10s
~~~

And the deployment environment passes:

~~~bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=7070
APP_CLIENT_READTIMEOUT=3s
~~~

Considering only these sources, the final values are:

| Property | Base file | Prod file | Environment variable | Result |
| --- | --- | --- | --- | --- |
| `server.port` | 8080 | 9090 | 7070 | **7070** |
| `app.client.read-timeout` | 5s | 10s | 3s | **3s** |

OS environment variables have higher precedence than Config Data in Spring Boot's default configuration source order.

However, command-line arguments can take higher precedence than environment variables:

~~~bash
SERVER_PORT=7070 java -jar app.jar --server.port=6060
~~~

If no other special source intervenes, the application uses port **6060**, because `--server.port=6060` is a Spring Boot configuration argument.

Therefore, distinguish two questions:

1. **Which variable name maps to the property?** For example, `SERVER_PORT` → `server.port`.
2. **Where does the final value come from?** It may come from an environment variable, or from a higher-priority source.

Getting the name right only solves the first question.

## 12. \`@Value\`, \`Environment\`, and \`@ConfigurationProperties\`

Spring Boot offers multiple ways to read properties. Three common approaches are:

### 12.1. \`@ConfigurationProperties\`

Suitable for a structured, strongly typed group of properties:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, int maxRetries) {}
~~~

If the system provides `APP_CLIENT_BASEURL` and `APP_CLIENT_MAXRETRIES`, the Binder can map the values into the record.

This approach explicitly leverages **relaxed binding** and is well suited when configuration has multiple fields.

### 12.2. \`@Value\`

Suitable for simple individual properties:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ServiceMode {
    private final String mode;

    public ServiceMode(@Value("${app.service-mode:default}") String mode) {
        this.mode = mode;
    }

    public String currentMode() {
        return mode;
    }
}
~~~

Here, the placeholder uses the **canonical kebab-case property name** `app.service-mode`. The corresponding variable name is `APP_SERVICEMODE`. Using the canonical form in placeholders helps Spring Boot apply flexible name lookup properly.

The `:default` part is the placeholder's default value if the property is not found. It is not part of the environment variable name.

### 12.3. \`Environment\`

Properties can be retrieved directly:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServerConfigReader {
    private final Environment environment;

    public ServerConfigReader(Environment environment) {
        this.environment = environment;
    }

    public Integer serverPort() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

`Environment` returns the value resolved from the property sources, though direct name lookup should not be assumed to behave identically to the `@ConfigurationProperties` Binder in every case involving special characters or complex structures. Use canonical names consistently and prefer `@ConfigurationProperties` for groups of properties.

## 13. Special cases: Maps, loggers, and unusual characters

Environment variable naming rules work most predictably with **canonical property names** made of alphanumeric segments, dots, and hyphens.

Some configurations use special key names, such as a Map whose keys are paths:

~~~yaml
app:
  rules:
    "[/public/api]": allow
    "[user.role]": admin
~~~

When binding into `Map<String, String>`, bracket syntax in configuration files preserves special characters in keys. Mechanically turning every dot into `_` and stripping special characters in an environment variable name can **lose information about the original key**.

Similarly, package/class logger names may contain dots, uppercase letters, or characters with specific meaning. Do not assume every logger name or every complex Map key can be accurately represented by a single environment variable using the usual rule.

For these cases, you can:

- Put structured configuration in an appropriate YAML/properties file.
- Use environment variables for simple, clear configuration keys.
- Consider Spring Boot's JSON configuration source (`SPRING_APPLICATION_JSON`) when you need to express structures that plain environment variable names cannot easily preserve.

Example of a variable containing JSON:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"client":{"base-url":"https://api.example.org"}}}'
java -jar app.jar
~~~

`SPRING_APPLICATION_JSON` is a way to supply JSON-formatted configuration to Spring Boot, **different from converting each key name into an individual environment variable**. Also keep in mind it has its own precedence position in the property source order and should not hold secrets if the environment could expose variable contents or arguments.

For Map keys that require preserving exact uppercase letters, dots, or slashes, verify how the Binder handles the target Map type rather than guessing the outcome from OS variable names alone.

## 14. Avoiding name collisions when removing hyphens

Because the canonical rule **removes hyphens**, certain pairs of names that differ only in word separation convert to the exact same environment variable:

~~~text
app.feature-mode      → APP_FEATUREMODE
app.featuremode       → APP_FEATUREMODE
~~~

If you intentionally define two properties with different meanings under such names, accessing them via environment variables becomes ambiguous.

Similarly:

~~~text
app.client.read-timeout   → APP_CLIENT_READTIMEOUT
app.client.readtimeout    → APP_CLIENT_READTIMEOUT
~~~

Configuration naming should follow **one consistent canonical convention**, typically lowercase kebab-case. Avoid creating two keys that differ only by a hyphen yet represent two independent values.

Another common confusion is mixing up dotted names and hyphenated names:

~~~text
app.retry.max-attempts  → APP_RETRY_MAXATTEMPTS
app.retry.max.attempts  → APP_RETRY_MAX_ATTEMPTS
~~~

These two paths have different structures. When the same group of properties is represented by a Java class, confusing nested objects with camelCase fields leads to unintended environment variable names.

## 15. Configuring profiles via environment variables

One of the most common examples is `spring.profiles.active`:

~~~properties
spring.profiles.active=prod
~~~

Canonical environment variable name:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Setting multiple profiles at once:

~~~bash
SPRING_PROFILES_ACTIVE=prod,metrics
~~~

Spring Boot uses the active profile list to decide which `application-{profile}.yml` files or `spring.config.activate.on-profile` documents to consider.

Crucially, **environment variables can influence Config Data file selection**, not merely override properties after files are loaded. Properties controlling how files are located, such as `spring.config.name`, `spring.config.location`, and `spring.config.additional-location`, are processed early during startup. They should be passed via a source available at that stage, such as command-line arguments, Java system properties, or environment variables.

When converting these property names to environment variables, the same general rule applies. For example:

~~~text
spring.config.name                 → SPRING_CONFIG_NAME
spring.config.location             → SPRING_CONFIG_LOCATION
spring.config.additional-location  → SPRING_CONFIG_ADDITIONALLOCATION
~~~

Do not rely on manually adding an underscore between `ADDITIONAL` and `LOCATION` to infer the official rule: in the canonical name, these two words are joined by a hyphen, so the canonical transformation **removes** the hyphen.

## 16. Relationship with \`.env\` files

In practice, developers often have a file named `.env`:

~~~dotenv
SPRING_PROFILES_ACTIVE=dev
SERVER_PORT=8085
APP_CLIENT_CONNECTTIMEOUT=3s
~~~

You should distinguish between:

- **Real environment variables:** name/value pairs passed by the operating system to the Java process.
- **`.env` file:** a text file read by some tool or library and used to supply variables.

Spring Boot itself **does not automatically read arbitrary `.env` files on the filesystem as a default Config Data file**. A tool like Docker Compose has its own use of `.env` files for variable substitution in Compose configurations; for variables to reach the container, you still need `environment`, `env_file`, or an appropriate environment-provisioning mechanism.

Compose example:

~~~yaml
services:
  app:
    image: example/app:latest
    env_file:
      - .env
    ports:
      - "8085:8085"
~~~

Here, Docker Compose passes variables from `.env` into the container's environment. Spring Boot simply reads the variables that were supplied to the process.

Do not commit `.env` files containing real passwords or tokens. When storing a template, you can use `.env.example` with dummy values and instruct deployers to supply real values through a secure channel.

## 17. Diagnosing when an environment variable has no effect

A variable named similarly to a property whose final value does not change may be caused by **wrong renaming rules**, **the variable never actually reaching the process**, or **a higher-priority source overriding it**.

You can check in the following order:

1. **Write down the canonical property name** from YAML, metadata, or the `@ConfigurationProperties` record. For example, `app.payment.retry-delay`.
2. **Replace dots with `_`**, remove `-`, and convert to uppercase: `APP_PAYMENT_RETRYDELAY`.
3. **Verify how the variable is supplied** in the shell, IDE Run Configuration, Docker Compose, Kubernetes, or deployment system.
4. **Verify timing:** the Java process must be started after the variable is set.
5. **Verify the value is valid for the Java type**, such as number, boolean, or `Duration`.
6. **Check which source wins:** profile files, environment variables, system properties, CLI arguments, or test configuration.
7. **If it is a list**, check the indices and all elements supplied by the higher-priority source.
8. **If it is a special Map key**, consider using YAML/JSON instead of forcing it into a plain variable name.

For example, canonical property:

~~~properties
app.api.request-timeout=5s
~~~

Then the rule-compliant variable is:

~~~bash
APP_API_REQUESTTIMEOUT=10s
~~~

The name `APP_API_REQUEST_TIMEOUT` adds an extra `_` boundary between `REQUEST` and `TIMEOUT`, so it is **not the canonical conversion** of `app.api.request-timeout`. Avoid relying on the system's flexible interpretation of non-standard names in production configuration.

For sensitive data, do not run commands that print all environment variables or dump the entire `Environment` to logs. If observation is needed, print only **non-sensitive key names**, existence status, and the providing source with values masked. Diagnostic endpoints such as Spring Boot Actuator `env`/`configprops` must be properly secured.

## 18. Practice exercises

### Exercise 1 — Basic name conversion

Convert the following properties to environment variable names:

~~~text
server.port
spring.application.name
app.client.base-url
app.cache.max-entries
~~~

**Answer:**

~~~text
SERVER_PORT
SPRING_APPLICATION_NAME
APP_CLIENT_BASEURL
APP_CACHE_MAXENTRIES
~~~

Dots become underscores, and hyphens are removed.

### Exercise 2 — Distinguishing nested objects from kebab-case

Convert the two names:

~~~text
app.file.max-size
app.file.max.size
~~~

**Answer:**

~~~text
APP_FILE_MAXSIZE
APP_FILE_MAX_SIZE
~~~

The first has one property `max-size`; the second has two levels `max` and `size`.

### Exercise 3 — Lists of objects

Given YAML:

~~~yaml
app:
  endpoints:
    - name: alpha
      read-timeout: 2s
    - name: beta
      read-timeout: 4s
~~~

Write the environment variable name for `read-timeout` of the second element.

**Answer:** `APP_ENDPOINTS_1_READTIMEOUT`. The number `1` corresponds to the second element because list indices start at 0.

### Exercise 4 — Determining the final value

File `application-prod.yml` sets:

~~~yaml
server:
  port: 9090
~~~

Environment variable sets:

~~~bash
SERVER_PORT=7070
~~~

Command to run the application:

~~~bash
java -jar app.jar --spring.profiles.active=prod --server.port=6060
~~~

Which port does the application use, assuming no special higher-priority source?

**Answer:** `6060`. The profile file provides 9090, the environment variable overrides it to 7070, and the command-line argument overrides it further to 6060.

### Exercise 5 — Binding to a Java record

Given the record:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        int maxAttempts,
        java.time.Duration retryDelay
) {}
~~~

Write the three corresponding environment variable names.

**Answer:**

~~~text
APP_NOTIFICATION_ENABLED
APP_NOTIFICATION_MAXATTEMPTS
APP_NOTIFICATION_RETRYDELAY
~~~

The canonical property names are `app.notification.enabled`, `app.notification.max-attempts`, and `app.notification.retry-delay`, respectively.

### Exercise 6 — Distinguishing files from environment variables

A `.env` file contains:

~~~dotenv
SERVER_PORT=9191
~~~

However, starting the application with `java -jar app.jar` does not pick up `9191`. Can we conclude that Spring Boot converted `SERVER_PORT` incorrectly?

**Answer:** Not yet. `SERVER_PORT` is the correct name for `server.port`. You must verify whether the `.env` file was read by a shell, IDE, or deployment tool and passed as a real environment variable to the Java process.

## 19. Key takeaways

- The rule for converting a canonical property name to an environment variable is **dot → underscore, remove hyphens, uppercase**.
- `spring.main.log-startup-info` converts to **`SPRING_MAIN_LOGSTARTUPINFO`**, not by inserting `_` between every word.
- Lists use indices surrounded by underscores, for example `app.targets[0].url` → `APP_TARGETS_0_URL`.
- `@ConfigurationProperties` is the right mechanism to bind structured properties into Java records/classes; relaxed binding supports canonical configuration names.
- Environment variables typically have **higher priority than Config Data**, but can be overridden by CLI arguments or other special sources.
- Supply variables to the **Java process** via shell, Docker, Compose, Kubernetes, or IDE. A standalone `.env` file does not guarantee environment variables have been created.
- Avoid arbitrarily inserting `_` into kebab-case segments; avoid naming configurations in ways that collide after removing hyphens.
- For complex Map keys, sensitive values, or nested JSON structures, choose an appropriate configuration mechanism instead of trying to encode everything into environment variable names.

References:

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
