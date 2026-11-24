# Choosing Deployment Values When File Config and Environment Variables Coexist in Spring Boot 3.3

## 1. The Problem to Solve

In real-world Spring Boot deployments, the same setting can appear simultaneously across multiple sources: `application.properties` or `application.yaml` inside the JAR; an external file mounted outside the JAR; `application-prod.yaml`; container environment variables; Java system properties `-D`; command-line arguments `--key=value`; and additional sources such as `SPRING_APPLICATION_JSON`.

For example, the application has:

```yaml
# application.yaml
app:
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
```

Meanwhile, Docker or Kubernetes provides:

```bash
APP_REQUESTTIMEOUT=10s
APP_MAXRETRIES=0
APP_FEATUREENABLED=false
```

**Main conclusion:** under the default `PropertySource` order of **Spring Boot 3.3**, operating system environment variables (**OS environment**) have **higher precedence than Config Data**, including `application.*` files. When variable names map to the right properties and no higher-precedence source overrides them, Spring Boot selects:

```text
app.request-timeout = 10s
app.max-retries     = 0
app.feature-enabled = false
```

This **does not mean environment variables beat every source**. Java system properties, `SPRING_APPLICATION_JSON`, and command-line properties typically have higher precedence than the OS environment. Furthermore, selecting a value does not guarantee the Binder can convert its type or that validation accepts it.

This article explains source selection mechanics, key renaming between files and environment, profile-specific Config Data, Docker Compose, Kubernetes, collections/Maps, missing/empty/zero/false cases, diagnostics, and testing.

## 2. Environment and PropertySource: Per-Key Value Selection

Spring Boot manages configuration through Spring `Environment` backed by an ordered list of `PropertySource`s. Each source can provide a subset of properties; not every source has to contain the full key set.

```text
    app.request-timeout
             |
             v
     Spring Environment
             |
       PropertySources
             |
    +--------+---------+----------------+
    |                  |                |
    v                  v                v
 Config Data        OS environment    CLI/-D/JSON
 5s                 10s               depends on deployment
    |                  |                |
    +------------------+----------------+
             |
             v
  Value from highest-precedence source
             |
             v
      Binder / @Value
             |
             v
      Duration or other Java type
```

Three distinct stages:

1. **Name resolution**: `app.request-timeout` in a file and `APP_REQUESTTIMEOUT` in the environment can correspond to the same Java property `requestTimeout`.
2. **Precedence selection**: the highest-precedence source with a value for the same property wins.
3. **Type conversion and validation**: `10s` converts to `Duration`; if validation enforces bounds, those are checked separately.

If a file also declares `app.service-name=Catalog` while the environment has no corresponding variable, the service name is still taken from the file. Spring Boot does not discard the entire `app` namespace from a lower source just because a higher source supplies one key.

### Per-key override example

```properties
app.name=Catalog
app.request-timeout=5s
app.retries=3
```

Environment:

```bash
APP_REQUESTTIMEOUT=10s
```

Typical result:

| Property | Effective value | Source |
| --- | --- | --- |
| `app.name` | `Catalog` | File |
| `app.request-timeout` | `10s` | Environment |
| `app.retries` | `3` | File |

This applies to scalar properties. `List`, `Map`, and nested structures follow separate merge rules discussed later.

## 3. Precedence Order in Spring Boot 3.3

Spring Boot 3.3 documentation lists configuration sources in **ascending order of precedence**. For typical deployments, the key sources are:

```text
LOW PRECEDENCE
  SpringApplication default properties
           <
  Standard @PropertySource
           <
  Config Data (application.properties / YAML /
               profile-specific / external / imports)
           <
  RandomValuePropertySource
           <
  OS environment variables
           <
  Java system properties (-D...)
           <
  JNDI / ServletContext / ServletConfig (if present)
           <
  SPRING_APPLICATION_JSON
           <
  Command-line arguments (--key=value)
           <
  Certain test / DevTools sources in their respective contexts
HIGH PRECEDENCE
```

Not all sources exist in every application. Some frameworks or apps register an `EnvironmentPostProcessor`, custom `PropertySource`, or custom bootstrap logic, so **the actual runtime order can vary**. The diagram above represents the default behavior to understand first.

### Comparison table

| Source | Example `app.mode` | Usually beats Config Data files? |
| --- | --- | --- |
| Application default properties | `setDefaultProperties(...)` | No |
| `@PropertySource` | `custom.properties` | No |
| `application.yaml` file | `file` | Baseline source |
| External/profile Config Data | `prod` | Depends on Config Data order |
| OS environment | `APP_MODE=environment` | **Yes** |
| JVM system property | `-Dapp.mode=system` | **Yes**, also beats OS env |
| `SPRING_APPLICATION_JSON` | `{"app":{"mode":"json"}}` | **Yes**, usually beats `-D` |
| Command line | `--app.mode=cli` | **Yes**, usually beats all sources above |

Note that test-environment properties such as `@SpringBootTest(properties=...)`, `@TestPropertySource`, or `@DynamicPropertySource` can take higher precedence inside a test context. Do not use customized test context results to draw unfounded conclusions about a production JAR run.

### 3.1. Example with multiple sources for the same key

```properties
# application.properties
app.mode=file
```

```bash
APP_MODE=env java -Dapp.mode=system -jar app.jar --app.mode=cli
```

Default Boot result:

```text
app.mode = cli
```

Omit `--app.mode=cli`, and `system` wins. Omit `-Dapp.mode=system` as well, and `env` wins. Omit env, and `file` is used.

### 3.2. Distinguishing -D and --app

```bash
java -Dapp.mode=system -jar app.jar
```

is a **Java system property**; the `-D` option must appear before `-jar`.

```bash
java -jar app.jar --app.mode=cli
```

is a **Spring Boot command-line argument**, normally placed after the JAR name and converted into a command-line property when `SpringApplication.run(args)` processes arguments.

An application can disable adding command-line properties via `SpringApplication#setAddCommandLineProperties(false)`. When customized, never assume `--...` arguments automatically keep the precedence shown above.

## 4. Environment Variable Naming Rules: Dots, Hyphens, and Uppercase

Filenames/keys should use canonical **lowercase kebab-case**. To convert to an OS environment variable in Spring Boot 3.3:

1. Replace dots `.` with underscores `_`.
2. **Remove hyphens `-`**.
3. Convert everything to uppercase.

Example:

```text
spring.main.log-startup-info
 -> spring_main_log-startup-info
 -> spring_main_logstartupinfo
 -> SPRING_MAIN_LOGSTARTUPINFO
```

Reference table:

| Canonical property | Canonical environment variable |
| --- | --- |
| `app.name` | `APP_NAME` |
| `app.request-timeout` | `APP_REQUESTTIMEOUT` |
| `app.max-retries` | `APP_MAXRETRIES` |
| `app.feature-enabled` | `APP_FEATUREENABLED` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |

**Common pitfall:** `app.max-retries` maps canonically to `APP_MAXRETRIES`, **not** `APP_MAX_RETRIES`. Underscores normally represent hierarchy boundaries `.`, whereas hyphens inside a property segment are stripped.

Similarly, `app.client.connect-timeout` becomes `APP_CLIENT_CONNECTTIMEOUT`. `APP_CLIENT_CONNECT_TIMEOUT` may be interpreted as a different hierarchical property name and must not be relied upon to override `connectTimeout`.

### 4.1. Java uses camelCase, files use kebab-case

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private Duration requestTimeout = Duration.ofSeconds(5);

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
```

The same Java field `requestTimeout` accepts values from:

```properties
app.request-timeout=5s
```

or:

```bash
APP_REQUESTTIMEOUT=10s
```

via **relaxed binding**, without naming the Java field `request_timeout`.

### 4.2. @Value differs from @ConfigurationProperties

`@ConfigurationProperties` has a dedicated Binder supporting nested objects, lists/maps, conversion, validation, and relaxed binding. With `@Value`, write placeholders in **canonical form** to benefit from variant name lookup:

```java
@Value("${app.request-timeout:5s}")
private Duration requestTimeout;
```

Writing:

```java
@Value("${app.requestTimeout:5s}")
private Duration requestTimeout;
```

may not resolve all aliases like the canonical form in some cases. If you have a group of related properties, prefer `@ConfigurationProperties` over many `@Value` fields.

## 5. A Complete JavaBean Example

`AppProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String displayName = "Catalog";
    private Duration requestTimeout = Duration.ofSeconds(5);
    private int maxRetries = 3;
    private boolean featureEnabled = true;
    private Map<String, String> labels = new LinkedHashMap<>();

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int value) { maxRetries = value; }

    public boolean isFeatureEnabled() { return featureEnabled; }
    public void setFeatureEnabled(boolean value) {
        featureEnabled = value;
    }

    public Map<String, String> getLabels() { return labels; }
    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
```

Registering the bean in Spring Boot:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/resources/application.yaml`:

```yaml
app:
  display-name: "Catalog"
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
  labels:
    owner: platform
    stage: default
```

Environment when running production:

```bash
APP_DISPLAYNAME="Catalog Production" \
APP_REQUESTTIMEOUT=10s \
APP_MAXRETRIES=0 \
APP_FEATUREENABLED=false \
APP_LABELS_STAGE=production \
java -jar app.jar
```

Result:

| Java property | File | Env | Final value |
| --- | --- | --- | --- |
| `displayName` | `Catalog` | `Catalog Production` | `Catalog Production` |
| `requestTimeout` | `5s` | `10s` | `Duration.ofSeconds(10)` |
| `maxRetries` | `3` | `0` | `0` |
| `featureEnabled` | `true` | `false` | `false` |
| `labels.owner` | `platform` | Absent | `platform` |
| `labels.stage` | `default` | `production` | `production` |

Conditions: the bean is registered, env names map accurately, OS env is passed to the right JVM, and no higher-precedence source overrides them.

**Two notable values:** `0` and `false` are explicit values. Spring Boot does not treat them as "unset"; they override the defaults `3` and `true`.

### Service using the bound bean

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final AppProperties properties;

    public CatalogService(AppProperties properties) {
        this.properties = properties;
    }

    public String describeSafeSettings() {
        return properties.getDisplayName()
                + " / timeout=" + properties.getRequestTimeout()
                + " / retries=" + properties.getMaxRetries();
    }
}
```

Do not write extra boilerplate calling `System.getenv("APP_REQUESTTIMEOUT")` manually to override things when the Binder is already handling it, unless business logic genuinely requires a different policy.

## 6. Levels of Config Data: Packaged Files, External Files, Profiles

Within Config Data itself, Spring Boot follows its own precedence order. In basic ascending order across default locations:

1. Packaged `application.properties` or `application.yaml` inside the JAR.
2. Packaged `application-{profile}.properties`/YAML.
3. External `application.properties`/YAML outside the JAR.
4. External `application-{profile}.properties`/YAML.

Example:

```yaml
# application.yaml
app:
  request-timeout: 5s
  mode: safe
```

```yaml
# application-prod.yaml
app:
  request-timeout: 8s
```

```yaml
# /app/config/application-prod.yaml
app:
  mode: batch
```

With `SPRING_PROFILES_ACTIVE=prod` and external locations loaded by Spring Boot, if no env override exists, `app.request-timeout` can be `8s` and `app.mode` can be `batch`.

Add env:

```bash
APP_REQUESTTIMEOUT=12s
APP_MODE=live
```

and the typical effective result becomes:

```text
app.request-timeout = 12s
app.mode            = live
```

**An active profile does not make profile-specific Config Data beat OS environment.** Profiles only determine which Config Data documents are included, while OS environment still ranks higher by default.

### 6.1. Profile-specific ordering

When multiple profiles are active, profile-specific files participate per Config Data rules and profile order; a later-declared profile can override an earlier one at the corresponding location. Do not guess solely from alphabetical filenames while ignoring active profiles and location groups.

### 6.2. .properties and YAML in the same location

If the same location has both `application.properties` and `application.yaml` with the same basename, Spring Boot prioritizes `.properties` over YAML. Keep a single consistent format or avoid declaring the same property in both files at the same level.

### 6.3. spring.profiles.active is a startup property

`SPRING_PROFILES_ACTIVE=prod` can override `spring.profiles.active` in a non-profile-specific file following standard precedence. However, Spring Boot restricts where `spring.profiles.active` may be declared: do not put it inside a profile-specific document or a document activated via `spring.config.activate.on-profile` under Boot 3.3 rules.

## 7. External Config Data Files Outside the JAR

Deployments do not need to rebuild the image to change most config. One option is mounting external files:

```text
/app/app.jar
/etc/catalog/application.yaml
```

Supply at startup:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=file:/etc/catalog/ \
java -jar /app/app.jar
```

Distinguish:

- `spring.config.location`: replaces default search locations with the declared locations per Boot rules.
- `spring.config.additional-location`: adds locations beyond default locations.

If you want to preserve defaults inside the JAR and overlay external values, `additional-location` is usually the better choice.

Example:

```yaml
# file inside JAR
app:
  request-timeout: 5s
  max-retries: 3
```

```yaml
# /etc/catalog/application.yaml
app:
  request-timeout: 8s
```

Env:

```bash
APP_REQUESTTIMEOUT=12s
```

Once the external file loads, `app.request-timeout` can be `12s` because env outranks Config Data. `app.max-retries` still comes from the file inside the JAR unless overridden elsewhere.

### 7.1. Declare locations early enough

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` affect the very early Config Data discovery/loading stage. Supply them via OS env, JVM system property, or CLI at startup—do not set them in an `ApplicationRunner` expecting the system to go back and load files.

### 7.2. Location groups affect file order

Commas and semicolons in `spring.config.location` have different grouping semantics. If a project uses multiple profiles and locations, test the actual precedence instead of assuming file path string order always decides who wins.

### 7.3. optional: does not mean fixing config errors

`optional:file:/etc/catalog/` allows a missing location to be skipped. Yet a file that exists with invalid syntax or unconvertible values will still fail. For required production locations, do not carelessly use `optional:` to hide a missing mount.

## 8. spring.config.import and Configuration Trees

A file can import additional Config Data:

```properties
spring.config.import=file:/etc/catalog/extra.properties
```

Or import a secret volume formatted as one key per file:

```properties
spring.config.import=configtree:/run/secrets/
```

In Config Data, imported files follow precedence rules relative to the importing document. However, an imported source is still **Config Data**; it does not become OS environment merely because it lives inside a container.

### Secret example

Container:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Import:

```properties
spring.config.import=configtree:/run/secrets/
```

These files supply `spring.datasource.username` and `spring.datasource.password` to `Environment`. If `SPRING_DATASOURCE_PASSWORD` is also passed via OS env, env normally takes precedence over the imported configtree.

**Recommendation:** avoid placing the same credential in multiple competing sources. Having env outrank a secret file can cause the application to use an old, wrong, or someone else's value. Precedence is a technical rule; the "source of truth" must be organizationally defined and write-protected.

## 9. Docker Compose: Separating Default Files and Per-Deployment Environment

Suppose the JAR contains:

```yaml
# packaged application.yaml
server:
  port: 8080
app:
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
```

`compose.yaml`:

```yaml
services:
  catalog:
    image: example/order-service:1.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      APP_REQUESTTIMEOUT: "12s"
      APP_MAXRETRIES: "0"
      APP_FEATUREENABLED: "false"
```

When the container runs, the JVM's OS environment holds those values. Absent higher-precedence `-D`/CLI/JSON/custom sources, the bound results are `12s`, `0`, and `false`. `server.port` still comes from Config Data as `8080`.

### 9.1. Compose .env and container env are different

A `.env` file placed next to Compose:

```dotenv
APP_REQUESTTIMEOUT=12s
```

normally serves Compose **interpolation**; it **does not automatically inject all variables in that file into containers**.

To pass it to the service:

```yaml
services:
  catalog:
    image: example/order-service:1.0
    environment:
      APP_REQUESTTIMEOUT: "${APP_REQUESTTIMEOUT:-5s}"
```

or use:

```yaml
services:
  catalog:
    image: example/order-service:1.0
    env_file:
      - ./catalog.env
```

In the first example, `${APP_REQUESTTIMEOUT:-5s}` is a **Docker Compose placeholder** resolved by Compose before creating the container, not a Spring `@Value` placeholder. `env_file` passes listed variables into the container per Compose rules.

### 9.2. Two separate precedence layers

If `environment`, `env_file`, Compose interpolation, and Compose CLI flags set the same variable, **Docker Compose** determines the final variable value inside the container. Only then does **Spring Boot** arbitrate between process environment and Config Data/JVM/CLI.

Do not merge the two precedence orders into one. When suspecting a wrong env value, first verify what Compose actually passed into **the container's JVM**, then inspect the Spring Binder.

### 9.3. Do not duplicate secrets unnecessarily

If you use `secrets:` to mount files at `/run/secrets/`, you do not also need to put plaintext secrets in `environment:` just for Spring Boot. You can import with `spring.config.import=configtree:/run/secrets/`. Secure host files, mount permissions, logs, and secret access according to your real environment.

## 10. Kubernetes: ConfigMap, Secret, Environment, and Volumes

Kubernetes has multiple ways to deliver data into a container, which for Spring Boot boil down to two main forms:

1. **Process environment**: `env`, `envFrom`, `configMapKeyRef`, `secretKeyRef`.
2. **Config Data files**: ConfigMap/Secret/projected volumes mounted into the filesystem and read by Boot via `file:` or `configtree:`.

### 10.1. Deployment with env

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: example/catalog:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: APP_REQUESTTIMEOUT
              value: "15s"
            - name: APP_MAXRETRIES
              value: "0"
            - name: APP_FEATUREENABLED
              value: "false"
```

If the file inside the JAR sets `app.request-timeout=5s`, the OS environment supplied by Kubernetes overrides it to `15s`.

### 10.2. Reading values from a ConfigMap

```yaml
env:
  - name: APP_REQUESTTIMEOUT
    valueFrom:
      configMapKeyRef:
        name: catalog-settings
        key: request-timeout
```

Kubernetes reads `request-timeout` from the ConfigMap and exposes it as env var `APP_REQUESTTIMEOUT`. Spring Boot sees the **variable name delivered to the container**, without directly referencing the ConfigMap object name during property lookup.

ConfigMaps are for non-sensitive configuration. For passwords or tokens, use Kubernetes Secrets or an approved secret management solution.

### 10.3. Mounting a ConfigMap as a file

```yaml
volumeMounts:
  - name: external-config
    mountPath: /etc/catalog
    readOnly: true
volumes:
  - name: external-config
    configMap:
      name: catalog-application-config
```

Suppose it creates:

```text
/etc/catalog/application.yaml
```

Boot can import:

```properties
spring.config.import=file:/etc/catalog/application.yaml
```

If env `APP_REQUESTTIMEOUT=20s` is also present, env still normally beats `app.request-timeout` in the mounted file.

### 10.4. Mounting a Secret via configtree

```text
/etc/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

```properties
spring.config.import=configtree:/etc/secrets/
```

Values enter Config Data. If `SPRING_DATASOURCE_PASSWORD` also exists in the container environment, the environment source normally outranks configtree. Avoid duplicating credentials across competing sources unnecessarily.

### 10.5. Do not overlook precedence before Spring Boot

Kubernetes has its own rules when multiple `env` and `envFrom` entries define the same environment variable. Spring Boot does not see the original ConfigMap/Secret objects after Kubernetes constructs the final process environment; it only sees the variables the JVM receives.

Check twice: first which variable Kubernetes selected, then which value Spring Boot selected between env and other `PropertySource`s.

## 11. SPRING_APPLICATION_JSON Outranks OS Environment

Spring Boot 3.3 can accept a JSON object via `SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"app":{"request-timeout":"20s"}}' \
java -jar app.jar
```

The JSON data is added as a dedicated `PropertySource`, normally with **higher precedence than OS environment and Java system properties**, though lower than command-line arguments.

Simultaneous example:

```text
application.yaml         -> app.request-timeout=5s
APP_REQUESTTIMEOUT       -> app.request-timeout=10s
-Dapp.request-timeout    -> app.request-timeout=15s
SPRING_APPLICATION_JSON  -> app.request-timeout=20s
--app.request-timeout    -> app.request-timeout=30s
```

Default result:

```text
app.request-timeout=30s
```

Remove CLI, and JSON wins with 20s. Remove JSON, and `-D` wins with 15s. Remove `-D`, and env wins with 10s.

### 11.1. JSON null does not erase lower-source properties

Example:

```json
{"app":{"mode":null}}
```

A JSON `null` value is treated by Spring's `PropertySource` resolver as an absent property during resolution, so do not use JSON `null` to "delete" a property already present in a lower source. To turn off a feature, use boolean `false` per the contract or edit the configuration source.

### 11.2. Securing JSON env

Do not use `SPRING_APPLICATION_JSON` as a default secret store. It can dump multiple credentials into the process environment, raising exposure risk during config dumps or log captures. For secrets, prefer secret mounts or your organization's secret manager.

## 12. Missing, Empty Strings, 0, false, and Malformed Values

These cases have different semantics:

| Case | Meaning during source selection |
| --- | --- |
| Env var absent | Can fall back to property from lower Config Data |
| Env var contains `""` | Empty string can count as a present value; depends on target type |
| Env var contains `0` | An explicit numeric value |
| Env var contains `false` | An explicit boolean value |
| Env var contains `abc` for an `int` target | May fail conversion instead of falling back |
| Env var has wrong name | Does not override the intended property |
| Env var never reaches JVM | Environment source lacks that property |

Example:

```properties
app.name=Catalog
app.retries=3
app.enabled=true
```

Environment:

```bash
APP_NAME=""
APP_RETRIES=0
APP_ENABLED=false
```

After binding:

- `app.name` targeting `String` can become an empty string, overriding `Catalog`.
- `app.retries` becomes `0`, not `3`.
- `app.enabled` becomes `false`, not `true`.

Different target typed properties handle empty strings differently; do not assume empty automatically turns into missing/zero/false. For required `String`s, use `@NotBlank` to reject empty strings.

### 12.1. Unexported shell variables

On Linux:

```bash
APP_REQUESTTIMEOUT=10s
java -jar app.jar
```

An unexported shell variable may not be passed to the JVM process. To ensure it is passed:

```bash
export APP_REQUESTTIMEOUT=10s
java -jar app.jar
```

or:

```bash
APP_REQUESTTIMEOUT=10s java -jar app.jar
```

A variable set in an admin terminal does not prove it exists inside a JVM process spawned by systemd, Docker, or Kubernetes.

## 13. Conversion: Env Can Win Yet Have the Wrong Unit

Suppose the file has:

```properties
app.request-timeout=5s
app.cache-size=32MB
```

Environment:

```bash
APP_REQUESTTIMEOUT=10
APP_CACHESIZE=64
```

When Java targets are `Duration` and `DataSize`, with no unit-changing annotation:

- A bare `Duration` number defaults to **milliseconds**: `10` = 10ms.
- A bare `DataSize` number defaults to **bytes**: `64` = 64B.

These are two properly named env overrides that bind without error, yet are **semantically wrong** if the operator meant 10 seconds and 64MB.

Write explicitly:

```bash
APP_REQUESTTIMEOUT=10s
APP_CACHESIZE=64MB
```

### 13.1. Do not auto-fallback when env has the wrong type

File:

```properties
app.max-retries=3
```

Env:

```bash
APP_MAXRETRIES=abc
```

Targeting `int`, the Binder selects `abc` from the higher source and fails type conversion. **There is no general rule "if env is invalid, fall back to 3 from the file."** Fail-fast is usually safer when critical configuration is broken.

### 13.2. Bean Validation is an independent step

```java
@Min(1)
@Max(50)
private int workerCount = 4;
```

`APP_WORKERCOUNT=0` parses to `int` `0` and then violates `@Min(1)`. `APP_WORKERCOUNT=abc` fails conversion before validation runs. Distinguish source precedence errors, type conversion errors, and domain policy errors.

## 14. Lists and Maps Have Different Semantics

Do not mechanically apply "env beats file" to all nested structures.

### 14.1. Lists are usually replaced

File:

```yaml
app:
  servers:
    - https://a.example.test
    - https://b.example.test
```

Higher source has:

```properties
app.servers[0]=https://prod.example.test
```

After binding, the list may contain only:

```text
["https://prod.example.test"]
```

It **does not automatically append** `b.example.test` from the lower source. To define a two-element List in env, supply the corresponding variables:

```bash
APP_SERVERS_0_=https://prod.example.test
APP_SERVERS_1_=https://backup.example.test
```

Environment rule: list indices are surrounded by `_`. For nested objects `app.clients[0].base-url`, the canonical env name is `APP_CLIENTS_0_BASEURL`.

### 14.2. Maps can merge keys

File:

```yaml
app:
  labels:
    team: platform
    stage: default
```

Env:

```bash
APP_LABELS_STAGE=production
APP_LABELS_OWNER=catalog
```

With `Map<String,String> labels`, the usual result is:

```text
team  -> platform
stage -> production
owner -> catalog
```

The `team` key is not erased merely because env supplied two Map entries.

### 14.3. Maps with object values

File:

```yaml
app:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
      enabled: true
```

Env:

```bash
APP_CLIENTS_BILLING_CONNECTTIMEOUT=5s
APP_CLIENTS_BILLING_ENABLED=false
```

With `Map<String,ClientProperties>`, the Binder can combine them:

```text
billing.baseUrl        = https://billing.example.test
billing.connectTimeout = 5s
billing.enabled        = false
```

Independent child properties can come from different sources. However, a `List` inside a map value object still follows list replacement rules.

### 14.4. Special Map keys

Map keys containing slashes or dots require bracket notation to preserve them accurately in files:

```properties
app.routes.[/api/v1]=billing
```

YAML:

```yaml
app:
  routes:
    "[/api/v1]": billing
```

Environment variables cannot always express Map keys with special characters or case sensitivity. When exact keys are needed, Config Data with bracket notation is usually clearer.

## 15. Identifying the Effective Source When Debugging

A straightforward approach is inspecting non-sensitive values from `Environment` and the bound bean:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner showConfig(
            Environment env, AppProperties props) {
        return args -> {
            System.out.println("Resolved app.request-timeout: "
                    + env.getProperty("app.request-timeout"));
            System.out.println("Bound timeout: "
                    + props.getRequestTimeout());
        };
    }
}
```

With file `5s`, env `10s`, and no higher source, output can be:

```text
Resolved app.request-timeout: 10s
Bound timeout: PT10S
```

**Do not apply to secrets:** never print passwords, API tokens, the full `Environment`, or objects containing credentials. Check presence/source rather than values.

### 15.1. Listing PropertySource names

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void showSourceNames(ConfigurableEnvironment env) {
    for (PropertySource<?> source : env.getPropertySources()) {
        System.out.println(source.getName());
    }
}
```

This reveals the list of sources and their relative order; it is not standalone proof of where a specific property value was bound from. Env variable names and canonical file names can be handled differently by adapters and relaxed binding.

### 15.2. Origin from Config Data

When binding fails, failure analysis can report `Property`, `Value`, `Origin`, and `Reason`. Illustrative format:

```text
Property: app.max-retries
Value: "bad-value"
Origin: systemEnvironment
Reason: failed to convert String to int
```

For files, `Origin` can include the filename and line number. For environment variables, there may be no line/column. Lack of a line number does not mean the property was absent.

### 15.3. Actuator

`/actuator/env` and `/actuator/configprops` can aid diagnostics of `PropertySource`s and `@ConfigurationProperties` beans. Both endpoints must be secured and configured with masking/sanitization. Never expose them publicly or paste sensitive raw output into tickets.

## 16. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Env is set, yet file still wins | Wrong env name or never reached JVM process | Check naming/variable delivery |
| `APP_MAX_RETRIES` does not work like `app.max-retries` | Underscore creates different hierarchy | Use `APP_MAXRETRIES` |
| Docker Compose `.env` has value, yet container lacks it | `.env` is for interpolation, missing `environment`/`env_file` | Pass env to the service |
| Kubernetes ConfigMap has key, yet Spring misses it | Pod does not consume key via env/mount | Add `env`/`envFrom`/volume mount |
| JVM `-D` beats env | Default order | Edit/remove `-D` if unintended |
| CLI beats env | Command-line source has high precedence | Check entrypoint and args |
| `application-prod.yaml` does not beat env | Profile files are still Config Data | Adjust env or remove override |
| Env containing `false`/`0` still overrides | These are explicit values | Do not treat as missing |
| Empty env overrides String default | Empty differs from missing | Add validation or unset env |
| Env has `10`, yet timeout is tiny | `Duration` defaults to ms | Write `10s` |
| Env has `64`, yet cache is tiny | `DataSize` defaults to B | Write `64MB` |
| Mistyped env prevents app startup | Conversion error on higher-precedence value | Fix value; do not expect fallback |
| Env overriding a List drops items from file | List replacement | Supply entire List in the higher source |
| Map keeps keys from file | Map merge | Usually expected behavior |
| Bean misses key despite `Environment` having it | Bean unregistered or missing setter/constructor | Fix `@ConfigurationProperties` |
| File changed, yet JVM keeps old value | Config Data/beans do not auto-reload | Rollout/restart/dedicated refresh |
| Custom source beats env | Custom `PropertySource` priority | Inspect actual `Environment` order |
| camelCase `@Value` placeholder misses aliases | Non-canonical placeholder | Use kebab-case |
| App only fails in prod | Profile, mount, CLI, or env differs from dev | Compare runtime sources |

### Technical errors that are not precedence errors

If a JavaBean only has a scalar getter and lacks a setter, the Binder may fail to update the target even though env was selected properly. If the `@ConfigurationProperties` class is not registered, there is no Spring bean to inject. If a service manually instantiates `new AppProperties()`, that Java object has never gone through binding. Distinguish **wrong source**, **wrong type**, **wrong bean registration**, and **wrong usage site**.

## 17. Testing Precedence Order

### 17.1. Basic binding test with ApplicationContextRunner

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.config.AppProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class AppPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void canBindExplicitValues() {
        runner.withPropertyValues(
            "app.request-timeout=10s",
            "app.max-retries=0",
            "app.feature-enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();
            AppProperties props =
                    context.getBean(AppProperties.class);

            assertThat(props.getRequestTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
            assertThat(props.getMaxRetries()).isZero();
            assertThat(props.isFeatureEnabled()).isFalse();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class Config { }
}
```

This test verifies binding into the model. It **does not automatically reproduce all steps** of Config Data, profile, and OS environment loading of a production `SpringApplication`.

### 17.2. Integration/smoke test for file vs. env

To verify actual precedence:

1. Build the JAR with `application.yaml` setting `app.request-timeout=5s`.
2. Run once **without** `APP_REQUESTTIMEOUT`; confirm `5s`.
3. Rerun with `APP_REQUESTTIMEOUT=10s`; confirm `10s`.
4. Rerun adding `-Dapp.request-timeout=12s`; confirm `12s`.
5. Rerun adding `--app.request-timeout=15s`; confirm `15s`.
6. Test `APP_REQUESTTIMEOUT=bad`; confirm conversion/validation matches policy.
7. Never run tests using real production credentials.

Default result matrix:

| File | Env | `-D` | CLI | Result |
| --- | --- | --- | --- | --- |
| `5s` | Absent | Absent | Absent | `5s` |
| `5s` | `10s` | Absent | Absent | `10s` |
| `5s` | `10s` | `12s` | Absent | `12s` |
| `5s` | `10s` | `12s` | `15s` | `15s` |
| `5s` | `invalid` | Absent | Absent | Likely conversion error |
| `5s` | `0ms` | Absent | Absent | `0ms` if type/validation permits |

A test that merely asserts the context starts cannot detect that bare `10` was parsed as 10ms instead of 10s. Assert **typed values and units**.

## 18. Early Configuration, File Edits, and Restarts

Some properties govern the startup process:

```text
spring.config.name
spring.config.location
spring.config.additional-location
spring.profiles.active
spring.main.*
logging.*
```

They can be consumed before the `ApplicationContext` finishes initializing. To change config file locations or active profiles, supply those details early enough in startup.

### 18.1. Changing deployment environment does not change a running JVM

Env vars are typically supplied when the JVM/container process is created. Editing a Kubernetes Deployment/ConfigMap or Compose YAML does not automatically update a running JVM's environment. Typically a new Pod/container must be created via rollout/restart.

### 18.2. Mounted file changes do not mean beans auto-rebind

Although a ConfigMap/Secret volume can be updated by Kubernetes volume projection, Spring Boot 3.3 does not automatically reload all Config Data and refresh `@ConfigurationProperties` beans/connection pools just because files on disk changed. If hot refresh is needed, build dedicated infrastructure with validation, concurrency control, and client/resource recreation.

The effective value at startup is a **real-world snapshot** of the application, not necessarily matching file contents seen hours later.

## 19. @PropertySource and Custom Precedence

`@PropertySource` can add a file to `Environment`:

```java
@Configuration
@PropertySource("classpath:custom.properties")
public class LegacyConfig {
}
```

However, in Boot's default order, this source ranks below Config Data and OS environment, and is added during context refresh. It is not a reliable way to "force a file to beat env," especially for early startup properties.

Precedence can be customized via an `EnvironmentPostProcessor` or custom infrastructure, though that is a broad policy change:

- Diverges from standard behavior operators expect.
- Can break env overrides in Docker/Kubernetes.
- Makes tracing sources harder during diagnostics.
- Requires testing source ordering and bootstrap timing.

In most cases, keep standard defaults/precedence and establish **source governance procedures** instead of implicitly reversing the order.

## 20. Investigation Workflow When Env Does Not Beat File

1. Identify the canonical property, e.g., `app.request-timeout`.
2. Convert to the canonical env name: `APP_REQUESTTIMEOUT`.
3. Confirm the variable actually exists in the **exact JVM process**.
4. Check which files loaded: packaged/external, profiles, Config Data imports.
5. Check active profiles `spring.profiles.active`.
6. Check whether `-D`, `SPRING_APPLICATION_JSON`, or CLI has the corresponding key.
7. If using custom bootstrap logic, inspect actual `PropertySources`.
8. Check that the `@ConfigurationProperties` bean is registered and has proper setters/constructors.
9. Check the raw effective value on a **non-sensitive** key.
10. Check the converted type, unit annotations, and Bean Validation constraints.
11. Check whether the client/service actually uses the bound bean or hard-codes a value elsewhere.
12. Fix the winning source, then rerun smoke tests/rollout.

Short diagram:

```text
Runtime value differs from file?
      |
      v
Matching env present?
  |            |
 No           Yes
  |            |
  v            v
Check Config  Env name right?
Data/profile  |          |
/import      No         Yes
              |          |
              v          v
           Fix name   Higher source than env?
                         |          |
                        Yes         No
                         |          |
                         v          v
                    Check          Check bind,
                    -D/JSON/CLI    conversion,
                                   validation,
                                   usage
```

## 21. Recommended Deployment Configuration Strategy

| Goal | Recommended source | Reason |
| --- | --- | --- |
| Non-sensitive defaults | `application.yaml` in JAR | Keeps contract close to code |
| Profile-based defaults | `application-prod.yaml` | Environment-group configuration |
| Per-namespace overrides of a few keys | OS environment | Easy to change across deployments |
| Large external configuration outside image | External Config Data file | Can be mounted and versioned separately |
| Sensitive credentials | Docker/Kubernetes Secret volume, `configtree`, or secret manager | Avoids committing or baking plaintext into images |
| Controlled emergency overrides | JVM `-D` or CLI | High precedence; requires auditing |
| Nested objects and validation | `@ConfigurationProperties` | Type-safe binding |
| Map keys requiring merging | Map binding | Merges by key |
| Lists requiring consistency | Supply complete List from one source | Avoids replacement surprises |
| Knowing what actually runs | Safe diagnostics, integration tests | Do not rely on a single file |

A higher-precedence source does not mean it is **authorized** to be modified casually under governance rules. Define who can modify deployment env, JVM args, Config Data mounts, and secret sources.

## 22. Release Checklist

- [ ] All properties are documented in lowercase kebab-case.
- [ ] OS env variables follow dot → underscore, hyphen → remove, uppercase.
- [ ] Env actually reaches the container/JVM process, not just Compose project-level `.env`.
- [ ] No duplicate aliases with confusing alternate property names.
- [ ] Config Data/profile/import files load from the intended locations.
- [ ] Higher-precedence sources such as `-D`, JSON, and CLI have been checked.
- [ ] `@ConfigurationProperties` beans are registered and bind cleanly.
- [ ] `0`, `false`, and empty strings have clear contract meanings.
- [ ] `Duration`/`DataSize` use explicit unit suffixes.
- [ ] Bean Validation or checks exist for critical constraints.
- [ ] Lists and Maps are tested according to replacement/merge semantics.
- [ ] Secrets are not unnecessarily duplicated between files and env.
- [ ] Actuator/logs do not leak credentials.
- [ ] Non-sensitive effective values are verified at startup.
- [ ] Smoke tests run in a container with real file/default/env overrides.
- [ ] Env/file changes have a restart/rollout or dedicated refresh plan.
- [ ] A rollback path exists if new config fails startup.
- [ ] Runbook identifies where each config category lives and who owns it.

## 23. References

- **Spring Boot 3.3 — Externalized Configuration** (PropertySource Order, Config Data, profile files, imports, configuration trees, relaxed binding): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 — Binding From Environment Variables** (canonical name → OS env): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables
- **Spring Boot 3.3 — Merging Complex Types** (List replacement, Map merge): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types
- **Spring Boot 3.3 — @ConfigurationProperties API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Framework — Environment Abstraction**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Docker Compose — Environment Variables Precedence**: https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- **Kubernetes — Define Environment Variables for a Container**: https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/
- **Kubernetes — ConfigMaps / Secrets**: https://kubernetes.io/docs/concepts/configuration/configmap/ and https://kubernetes.io/docs/concepts/configuration/secret/

## 24. Final Takeaway

When **the same canonical property** is supplied in both a configuration file and the JVM's environment, Spring Boot 3.3 by default selects in this order:

```text
Config Data file
      <
OS environment
      <
Java -D system properties
      <
SPRING_APPLICATION_JSON
      <
Command-line --key=value
```

**Files set defaults, env sets per-deployment overrides, and higher-precedence sources can still beat env.** For the application to behave correctly, ensure env names map to the right properties, values convert cleanly to Java types, beans bind properly, validation is active, and runtime code actually uses the bound results. With Docker/Kubernetes, remember the extra platform configuration layer before the JVM ever sees its process environment.
