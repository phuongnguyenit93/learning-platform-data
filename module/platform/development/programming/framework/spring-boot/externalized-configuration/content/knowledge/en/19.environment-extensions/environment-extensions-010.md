# Boundaries Between Plain Spring Boot, Spring Cloud Config, Consul, and Vault

## 1. Objectives and design questions

A Spring Boot application can run well using only `application.yaml`, environment variables, command-line arguments, and files mounted into the container. However, as the number of applications, environments, development teams, and sensitive data items grows, requirements such as these commonly arise:

- Multiple services read from a centralized configuration set with change control and versioning.
- A service needs to fetch configuration by **application name, profile, and version** without bundling all files inside the JAR.
- Key/value pairs need to be read from infrastructure that provides service discovery and change-watch capabilities.
- Secrets must not be packaged in source code or container images; credentials require ACLs, auditing, lifecycle management, and dynamic provisioning.
- Operators want to know which instances received a configuration change, when a restart is required, and what happens if connectivity to the configuration source is lost.

Three products frequently mentioned are **Spring Cloud Config**, **HashiCorp Consul**, and **HashiCorp Vault**. They can all surface data into the same Spring abstraction, `Environment`, but **they do not share the same purpose, governance model, or security capabilities**.

This lesson belongs to the **Environment Extensions** group in the **Spring Boot Externalized Configuration** topic. Your goal is to identify **responsibility boundaries**, not merely memorize `spring.config.import` syntax.

After this lesson, you will be able to:

1. State what **plain** Spring Boot already supports for externalized configuration.
2. Explain the roles of `Environment`, `PropertySource`, the Config Data API, placeholders, and `@ConfigurationProperties`.
3. Identify what plain Spring Boot **does not provide out of the box**: a centralized Config Server, Consul agent/KV, or Vault secret store.
4. Distinguish Spring Cloud Config Server/Client from Spring Cloud Consul Config and Spring Cloud Vault Config.
5. Configure imports for all three integrations using the modern Config Data approach.
6. Distinguish **loading configuration at startup** from **runtime refresh**, watch, bus, and secret rotation.
7. Deliberately choose policies for fail-fast, fallback, retry, and readiness.
8. Understand the security boundary between regular configuration, sensitive data, and dynamic credentials.
9. Run a plain Spring Boot example; know how to extend it into each standalone Cloud variant.
10. Design tests and runbooks for local, Docker/Kubernetes, and production environments.

**Illustrative environment:** Java 21, Spring Boot 3.3.13, and when Spring Cloud is included, release train **2023.0.6**, which is compatible with this Boot version according to the official compatibility documentation. Examples use dummy hosts, keys, and tokens; never supply production passwords or credentials.

## 2. Overview map: same `Environment` destination, different sources and responsibilities

A mental model:

```text
                         SPRING BOOT APPLICATION
                       +--------------------------+
                       |       Environment        |
                       |       PropertySources    |
                       |       ConfigData API     |
                       +------------+-------------+
                                    |
                           Resolution / Binding
                                    |
                 +------------------+------------------+
                 |                                     |
            @Value, ${...}                  @ConfigurationProperties
                 |                                     |
                 +------------------+------------------+
                                    |
                         Beans / Services

              Property sources fed into Environment:
    +-----------------+----------------+--------------------+
    | Spring Boot core| Cloud Config   | Consul Config      |
    | file/YAML/env   | remote Config  | Consul KV          |
    | CLI/configtree  | Server         |                    |
    +-----------------+----------------+--------------------+
                \             |                 /
                 \            |                /
                  \      imports / plugins    /
                   \          |              /
                    +---------+-------------+
                              |
                       Spring Cloud Vault
                         secret backends
```

All sources can ultimately supply keys such as:

```text
demo.display-label
demo.retry-delay
spring.datasource.username
spring.datasource.password
```

Yet where the data is stored, who is permitted to read it, who reviews changes, and whether network connectivity is required at startup **are not solved by `Environment` alone**.

A very brief summary:

- **Plain Boot:** consumes, prioritizes, converts, and binds configuration.
- **Cloud Config:** distributes centralized configuration to many applications, commonly from Git or another backend.
- **Consul Config:** reads configuration from Consul's KV store; Consul also provides discovery/health as a separate functional area.
- **Vault:** manages secrets, identity/authentication, policies, and secret lifecycles; Spring Cloud Vault lets an application consume secrets as property sources.

No single product by default solves every requirement around rollout, access control, safe refresh, and operations. Those requirements must be designed end-to-end.

## 3. What capabilities does plain Spring Boot already provide?

Spring Boot includes an **Externalized Configuration** system powerful enough that many applications do not need any Spring Cloud component at all.

### 3.1. `Environment` and `PropertySource` instances

`Environment` provides an interface to look up properties by name:

```java
String mode = environment.getProperty("demo.mode");
```

Underneath, Spring aggregates `PropertySource` instances from multiple sources. When the same key appears in multiple places, **precedence order** determines the effective value. Boot adds many common sources along with profile-handling rules.

A plain Spring Boot project can receive data from:

- `application.properties` or `application.yaml` on the classpath.
- External files outside the JAR at default or application-specified locations.
- Profile-specific files such as `application-dev.yaml`.
- Environment variables and Java system properties.
- Command-line arguments such as `--demo.mode=from-cli`.
- `SPRING_APPLICATION_JSON` in supported contexts.
- Imported Config Data: files, `configtree:` directories, and other built-in Boot locations.
- Custom `PropertySource`, `EnvironmentPostProcessor`, or Config Data SPI implementations provided by the application/library itself.

Example:

```yaml
# application.yaml
demo:
  display-label: "Boot-only"
  retry-delay: 500ms
```

Override via CLI:

```bash
java -jar app.jar --demo.display-label=from-cli
```

No Config Server, Consul, or Vault is needed for this behavior.

### 3.2. Placeholders and type-safe binding

Configuration can reference values with placeholders:

```yaml
demo:
  service-name: billing
  display-label: "${demo.service-name:unknown}-worker"
```

In Java:

```java
@Value("${demo.display-label}")
String label;
```

Or bind an entire group:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoSettings(
        String displayLabel,
        Duration retryDelay
) {}
```

`@ConfigurationProperties` supports relaxed binding, conversion for `Duration`, `DataSize`, `URI`, nested records, collections, and appropriate validation.

These capabilities **do not require** Spring Cloud. When you add Config Server/Consul/Vault, the main addition is usually **supplying another data source to the existing Binder**, rather than replacing the Binder with an entirely new one.

### 3.3. Config Data and `spring.config.import`

Spring Boot lets you import additional data:

```yaml
spring:
  config:
    import: "optional:file:./local-overrides.yaml"
```

Or import a directory containing files where each file contributes one property:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

Example mount:

```text
/run/config/
  demo.display-label
  demo.retry-delay
```

The contents of each file become the value of the corresponding property. A Kubernetes Secret or ConfigMap mounted as files can be read using this config tree style.

Important to remember:

> **The Config Data API is a mechanism for importing and processing locations. It does not by itself create a centralized configuration server, Vault ACLs, or Consul watches.**

Integration-provided prefixes such as `configserver:`, `consul:`, and `vault://` require the corresponding integration library on the classpath.

### 3.4. Extending plain Boot via SPI

For specialized requirements, you can create:

- `EnvironmentPostProcessor`: adds/modifies sources before most beans are created.
- `PropertySource`: represents a key/value source.
- `ConfigDataLocationResolver`: recognizes and resolves an import location type.
- `ConfigDataLoader`: loads data from a resolved location.
- `ApplicationContextInitializer`: customizes the context during initialization.

These are **extension points** of Boot/Framework. However, writing a custom remote provider yourself often means implementing TLS, auth, retries, caching, precedence, profiles, logging, and error handling on your own. For common infrastructure, Spring Cloud libraries already provide much of that integration.

### 3.5. What does plain Spring Boot not do by itself?

It does not provide out of the box:

1. A standalone service serving configuration from Git to all microservices.
2. Spring Cloud Config Server's `{application}/{profile}/{label}` configuration lookup protocol.
3. A Consul agent, Consul KV, service discovery catalog, or Consul watch.
4. Vault secret backends, Vault authentication mechanisms, audit logs, or leases for dynamic credentials.
5. An automatic fan-out pipeline so every instance updates its configuration whenever Git changes.
6. Any guarantee that `@Value` or running singleton beans are automatically re-injected merely because a source file changed.

Boot enables **integration and extension**, but remote coordination and secret management systems do not come built in.

## 4. Comparing the four options before designing

| Criterion | Plain Boot | Spring Cloud Config | Consul Config | Spring Cloud Vault |
| --- | --- | --- | --- | --- |
| Primary data source | Files/YAML/env/CLI/config tree | Config Server and server backend, usually Git | Consul KV | Vault secrets backends |
| Extra infrastructure required? | Not required | Config Server | Consul agent/server | Vault server/cluster |
| Primary purpose | Reading/binding config in the application | Centralized config by app/profile/label | Config KV and Consul ecosystem integration | Secrets, policies, auth, leases, rotation |
| Git-versioned config | Managed by pipeline/files | Available via Git backend | Not a Git workflow by default | Not the default goal |
| Dedicated secret management | No | Does not replace Vault | KV does not replace Vault | Yes |
| Service discovery | Not built-in | Not Config Server's role | Consul Discovery is a separate module | Not its primary role |
| Modern import | Files, configtree, etc. | `configserver:` | `consul:` | `vault://` |
| Runtime changes | Not automatic | Requires designed refresh/bus or restart | Watch/refresh depending on setup | Secret lifecycle needs dedicated design |
| Network dependency at startup | None, if local only | Typically yes | Typically yes | Typically yes |
| Required security | File/env permissions and deployment governance | TLS, auth to server, Git/backend access control | ACLs, TLS, KV policies, agent security | Auth methods, policies, TLS, token/lease lifecycle |

These cells describe **product capabilities**; adding a single dependency does not automatically enable every feature.

For example, having `spring-cloud-starter-consul-config` in a project does not turn it into a service discovery application. Consul discovery uses a separate module and configuration, typically `spring-cloud-starter-consul-discovery`.

## 5. Spring Cloud Config: centralized configuration by application/profile/label

### 5.1. Two roles to keep separate

The Spring Cloud Config ecosystem has two main parts:

**Config Server:** a server application exposing an HTTP API for clients to fetch configuration. It reads data from an `EnvironmentRepository`, typically Git, though other backends exist depending on the integration.

**Config Client:** a library inside a business application that reads remote configuration from Config Server and adds properties to `Environment` at startup.

Diagram:

```text
 Git config repository
       |
       | branch/tag/commit, app config, profiles
       v
 +----------------------+
 | Spring Cloud Config  |
 |       Server         |
 |  HTTP API / configs  |
 +----------+-----------+
            |
       HTTP(S) requests
            |
      +-----+-------------+----------------+
      |                   |                |
      v                   v                v
 service-a           service-b        service-c
 Config Client       Config Client    Config Client
      |                   |                |
   Environment        Environment     Environment
```

Config Server does not necessarily store all values in Git. It is a **configuration-serving layer** plus a backend provider; Git is simply a very common choice. Choosing Git gives you change history and review workflows that fit standard processes, though you still must manage repository permissions and server deployment pipelines.

### 5.2. Application name, profile, label

A client typically has:

```yaml
spring:
  application:
    name: payment-service
  profiles:
    active: dev
```

Config Server exposes an API in the form:

```text
/{application}/{profile}/{label}
```

Where:

- `application`: usually `spring.application.name`.
- `profile`: application profile, e.g., `default`, `dev`, `prod`.
- `label`: typically maps to a branch/tag/commit in a Git backend; exact interpretation depends on the backend.

Example request reading remote metadata/config:

```text
GET http://localhost:8888/payment-service/dev
```

or:

```text
GET http://localhost:8888/payment-service/dev/main
```

The response returns a set of property sources by app/profile/label. Whether `label` should be `main` or another branch must align with the actual repository.

**Do not** assume that every new Git commit immediately causes all running clients to apply the new configuration. The server reading updated data and clients refreshing their state are **two distinct processes**.

### 5.3. Config Client import syntax

Client example:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "configserver:http://config-server.internal:8888"
```

The corresponding **Spring Cloud Config Client** dependency must be on the classpath. Plain Boot does not understand the `configserver:` prefix.

A variant for dev when the server might be absent:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

In the Config Client model, omitting `optional:` makes startup fail if Config Server is unreachable. Adding `optional:` handles server unavailability according to client behavior; the application must have safe local defaults if you allow startup in that situation.

**Warning:** `optional:` is not a universal promise that every HTTP, auth, format, secret, or integration error will be ignored. Each provider has its own error-handling rules.

### 5.4. Legacy `bootstrap.yml` and Config Data

Older Spring Cloud versions used a **Bootstrap Context** model with `bootstrap.yml`. Since Spring Boot 2.4, the Config Data API is the modern import approach, and Spring Cloud Config Client uses:

```properties
spring.config.import=optional:configserver:
```

With this approach, **there is no need to create `bootstrap.yml` solely to connect to Config Server**.

Only use the legacy Bootstrap Context if you have a specific reason and understand properties like `spring.cloud.bootstrap.enabled` or the `spring-cloud-starter-bootstrap` dependency. Do not mix both models and assume they behave identically regarding precedence, startup, and refresh.

### 5.5. Config Server does not replace Vault by itself

Git can manage regular configuration in a reviewable way, but you should not push plaintext production passwords, access tokens, or private keys to Git and treat that as secret management.

Even when Config Server supports encryption/decryption or backend integrations, repository read access, server access control, transport security, secret rotation, and auditing still require explicit design. If the core requirement is **secret lifecycle management**, Vault or a dedicated secret manager is a better fit.

## 6. Consul: KV config and service discovery are two separate capabilities

HashiCorp Consul can serve multiple roles:

1. **Consul KV:** storing key/value data.
2. **Service Catalog/Discovery:** service registration, lookup, and health checks.
3. Other networking and operational capabilities of the Consul platform.

In Spring Cloud:

- `spring-cloud-starter-consul-config` integrates **configuration from Consul KV**.
- `spring-cloud-starter-consul-discovery` integrates **discovery and registration**.

Do not use the word "Consul" as if these modules were a single feature. An application may use Consul Config without registering as a service, or use Discovery without reading KV for application configuration.

### 6.1. Consul Config feeds KV into Environment

Example:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "consul:localhost:8500"
```

You can use:

```yaml
spring:
  config:
    import: "optional:consul:"
```

with a Consul agent on `localhost:8500` in dev environments. Spring Cloud Consul builds property sources by application name/profile and shared contexts. By default, keys may live under:

```text
config/payment-service,dev/
config/payment-service/
config/application,dev/
config/application/
```

Specific contexts and priority order can be adjusted via `spring.cloud.consul.config.*`.

A source like `config/application` can be shared; `config/payment-service` is dedicated to one application. However, this is the **integration's KV organization convention**, not a mandatory layout for all Consul users.

### 6.2. KV, YAML, and PROPERTIES formats

Consul KV stores key/value pairs. Spring Cloud Consul Config can interpret:

- Individual key/value entries matching the configured layout.
- A YAML blob in the `data` key when format is configured as `YAML`.
- A `.properties` blob in the `data` key when format is configured as `PROPERTIES`.
- Certain file-style representations depending on configuration and version.

Example:

```yaml
spring:
  cloud:
    consul:
      config:
        format: PROPERTIES
```

Then a key such as:

```text
config/payment-service/data
```

can contain:

```properties
demo.display-label=from-consul
demo.retry-delay=750ms
```

This is convenient for demos or a small configuration group, but across many services you must define KV write permissions, review workflows, backups, and auditing. Consul KV does not inherently provide a Git pull-request workflow.

### 6.3. Consul Watch does not mean every bean updates automatically

Spring Cloud Consul includes Config Watch to monitor changes to key prefixes (via the Consul API) and can publish a `RefreshEvent` when relevant data changes.

However, you must distinguish:

```text
KV changes
   -> watch detects change
      -> Spring receives refresh event
         -> beans/configs must refresh via a supported mechanism
            -> service actually uses the new value
```

If a service holds a `final String` injected at startup or a stateful object not designed for refresh, you should not assume it updates immediately on its own.

**Watch is an event-coordination capability**, not magic that mutates every object inside the JVM.

### 6.4. Consul Discovery is not Config Server

If the goal is solely "find the current endpoint of service X", service discovery may be appropriate. Do not stuff dynamic hosts/IPs into a Git config file and treat it as a discovery solution when a service catalog or Kubernetes Service DNS already exists.

Conversely, if the goal is "timeout property of payment-service in the dev profile", Consul Config or Config Server are the configuration options to evaluate.

## 7. Vault: secret management, not just another KV store

HashiCorp Vault has dedicated systems for:

- Authentication: applications prove their identity before reading secrets.
- Authorization/policies: restricting secret paths and allowed operations.
- Audit: recording access events according to Vault configuration.
- Secret engines: KV, dynamic credentials, PKI, and other backends.
- Leases, renewal, revocation, and rotation depending on the secret engine.
- TLS and dedicated operational models for security infrastructure.

Spring Cloud Vault lets applications fetch secrets and expose them in `Environment` as property sources. Yet putting secrets into `Environment` **does not turn the entire application into a complete self-rotating system**.

### 7.1. Vault import syntax

In Spring Cloud Vault:

```yaml
spring:
  application:
    name: payment-service
  config:
    import: "vault://"
```

`vault://` can import default contexts from enabled secret backends, such as the KV backend based on application name and profile. For a specific context, the documentation supports:

```yaml
spring:
  config:
    import: "vault:///my/context/path"
```

Backend policies, mounts, paths, profiles, and read permissions must match the Vault system in use.

`vault://` is **not** a filesystem path and **not** a Config Server URI. It is a Config Data location resolver provided by Spring Cloud Vault.

### 7.2. Authentication and workload identity

In production, applications should use an authentication method tied to workload identity or approved by the security team, such as Kubernetes authentication, AppRole, or Vault Agent depending on infrastructure.

In a lab, a **static token** may be supplied via an environment variable for testing, but real tokens must never be committed into YAML/Git/images. A leaked static token can be used with its privileges until revoked or expired.

Key rules:

- Use TLS and verify certificates.
- Apply least-privilege policies.
- Restrict which KV/secret-engine paths each application can read.
- Manage bootstrap credentials separately; do not store them inside the very location requiring permission to read.
- Never log tokens, passwords, or secret values.
- Restrict health and actuator endpoints to prevent exposing values.

### 7.3. Static secrets vs. dynamic secrets

A **KV secret** can hold a pre-populated API key or password. You can change the value in Vault, yet running applications will not necessarily pick up the new value immediately.

A **dynamic secret** can be generated per role with a TTL/lease and revocation support. For example, database credentials can be issued temporarily.

However, if a JDBC connection pool already opened connections with old credentials, Vault issuing new credentials **does not automatically change the identity of existing live connections**. You must design pool lifecycles, lease renewal, recreation, retries, and handling of revoked access.

### 7.4. Vault does not replace an entire Config Server

Vault can also store regular configuration values via KV, though that does not automatically make it the best choice for thousands of non-sensitive parameters. Consider:

- Access permissions and operational overhead of secret engines.
- Review/diff workflows needed for everyday parameters.
- Frequency of changes and rollout policies.
- Friction between security controls and development teams.
- Availability and startup dependencies.
- Versioning and change-history documentation.

A common design uses **Git/Config Server or ConfigMap for non-secret config**, and **Vault or a secret manager for sensitive data**.

## 8. Further distinction from Kubernetes ConfigMap and Secret

In Kubernetes:

- `ConfigMap` is used for non-sensitive configuration.
- `Secret` is an API object intended for sensitive data; actual security depends on RBAC, encryption-at-rest, node access, and how it is mounted/used.
- Both can be passed to containers via environment variables or mounted files.

Plain Spring Boot can read values already injected into the process by kubelet:

```text
Kubernetes ConfigMap/Secret
              |
         env or volume
              |
      Spring Boot Environment
              |
       @ConfigurationProperties
```

Example using a config tree mount:

```yaml
spring:
  config:
    import: "optional:configtree:/run/app-config/"
```

If the volume contains the file:

```text
/run/app-config/demo.display-label
```

then Boot can read the file's contents as the value of `demo.display-label`.

This is **plain Boot plus Kubernetes mounting**, not equivalent to deploying Spring Cloud Config or Vault.

### 8.1. Are "Kubernetes Secret" and "Vault secret" the same?

No. A Kubernetes Secret is an object in the Kubernetes API with its own permission and storage model; Vault is a dedicated secret management system with its own authentication, policies, and secret engines.

An operator or CSI driver can sync/mount secrets from Vault into a pod so Boot reads them as files. In that model:

```text
Vault -> operator/CSI/agent -> files in pod -> Boot configtree
```

The Spring Boot app **may not need the Spring Cloud Vault dependency at all** because Vault retrieval is performed outside the application process. This is a valid architecture when decoupling the app from the Vault API, though you still must define refresh behavior and when files are updated.

### 8.2. Do mounted files automatically refresh beans?

Updating files in a volume does not mean Spring Boot automatically rebinds `@ConfigurationProperties` or replaces stored `@Value` fields.

For applications that read configuration only at startup, a **controlled rollout/restart** strategy is often clearer. If live updates are needed, there must be an explicit refresh path, tested for both data consistency and service lifecycle.

## 9. Shared responsibilities of Config Data API and provider libraries

Why does the exact same property:

```yaml
spring:
  config:
    import: "configserver:http://localhost:8888"
```

work when Cloud Config Client is present, yet fail on a Boot-only application?

Because:

```text
Spring Boot core:
  - manages spring.config.import
  - finds a resolver by location type
  - loads ConfigData when a matching loader exists
  - combines PropertySources and precedence
  - makes data available to Binder

Provider library:
  - recognizes prefix configserver:/consul:/vault://
  - implements the corresponding resolver/loader
  - connects to the backend
  - handles auth, retries, error mapping, context resolution
```

Without the provider library, Boot has no idea what `"configserver:"` or `"vault://"` means. Conversely, adding the provider without the URL, import declaration, or auth configuration can fail right at startup.

**A URL does not install a plugin by itself.** Verify both the **dependency on the classpath** and the **import location**.

## 10. Version alignment: Boot 3.3.13 and Spring Cloud 2023.0.6

When integrating Spring Cloud, do not pick arbitrary individual versions of Config Client, Consul, or Vault from Maven Central.

Lab stack:

```text
Java:             21
Spring Boot:      3.3.13
Spring Cloud:     2023.0.6 (release train)
Gradle:           a version supported by Boot 3.3
```

The 2023.0.6 release train documentation lists Spring Boot 3.3.13 as supported for that train. Another project using a newer Boot version should check the **compatibility matrix at upgrade time**, rather than keeping the 2023.0.6 BOM unchanged.

In Gradle, example adding the Spring Cloud BOM:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

Then declare the starter without specifying an individual version:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-config'
```

Or:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-consul-config'
```

Or:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-vault-config'
```

In this lab, **pick one integration per variant**, rather than adding every starter at once and losing track of which library is actively loading properties at startup.

The build files below use Spring Boot 3.3.13 as a pinned, reproducible example; this is not a claim that it is the latest Spring Boot release at all times.

## 11. Lab A: Plain Spring Boot, no remote infrastructure

First, build a working console application with **no network dependency and none of the three external integrations**.

Structure:

```text
external-config-boundaries/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/boundary/
    │   │   ├── BoundaryApplication.java
    │   │   └── DemoSettings.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/boundary/
            └── DemoSettingsTest.java
```

Use Spring Initializr with Java 21, Gradle, Spring Boot 3.3.x, and no web dependency needed. Take the Gradle Wrapper files (`gradlew`, `gradlew.bat`) from the generated project rather than writing them by hand.

### 11.1. Plain Gradle

`settings.gradle`:

```groovy
rootProject.name = 'external-config-boundaries'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

There is no Spring Cloud dependency whatsoever. This is the baseline proving Boot can load and bind local configuration without calling any Config Server.

### 11.2. Configuration record

`src/main/java/dev/example/boundary/DemoSettings.java`:

```java
package dev.example.boundary;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(
        String displayLabel,
        Duration retryDelay,
        boolean featureEnabled
) {}
```

YAML uses kebab-case; record components use camelCase. Spring Boot's Binder performs relaxed binding and `Duration` conversion.

### 11.3. Main class

`src/main/java/dev/example/boundary/BoundaryApplication.java`:

```java
package dev.example.boundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner printSettings(
            DemoSettings settings,
            Environment environment) {
        return args -> {
            System.out.println("=== CONFIG BOUNDARIES ===");
            System.out.println("displayLabel = "
                    + settings.displayLabel());
            System.out.println("retryDelay = "
                    + settings.retryDelay());
            System.out.println("featureEnabled = "
                    + settings.featureEnabled());
            System.out.println("activeProfiles = "
                    + String.join(",", environment.getActiveProfiles()));
        };
    }
}
```

`@ConfigurationPropertiesScan` registers the record so Binder creates the bean. `ApplicationRunner` runs after the context has prepared the required beans, allowing you to inspect the bound values.

### 11.4. Base YAML

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none

demo:
  display-label: "boot-local"
  retry-delay: 500ms
  feature-enabled: false
```

All `demo.*` keys have local values. There are no network calls to Config Server, Consul, or Vault.

### 11.5. Dev profile

`src/main/resources/application-dev.yaml`:

```yaml
demo:
  display-label: "boot-dev"
  feature-enabled: true
```

Run on macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Primary output:

```text
=== CONFIG BOUNDARIES ===
displayLabel = boot-local
retryDelay = PT0.5S
featureEnabled = false
activeProfiles =
```

With dev enabled:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Expected:

```text
displayLabel = boot-dev
retryDelay = PT0.5S
featureEnabled = true
activeProfiles = dev
```

Thus, profiles, default values, and type conversion work **without Spring Cloud**.

### 11.6. CLI and environment variables

Run:

```bash
./gradlew bootRun --args='--demo.display-label=from-cli --demo.retry-delay=2s'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.display-label=from-cli --demo.retry-delay=2s"
```

Or from environment variables:

Bash:

```bash
DEMO_DISPLAYLABEL=from-env ./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_DISPLAYLABEL = 'from-env'
.\gradlew.bat bootRun
Remove-Item Env:DEMO_DISPLAYLABEL
```

These sources are handled by Spring Boot's standard mechanism. No centralized server is involved.

### 11.7. Integration test for Boot-only

`src/test/java/dev/example/boundary/DemoSettingsTest.java`:

```java
package dev.example.boundary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.display-label=from-test",
        "demo.retry-delay=750ms",
        "demo.feature-enabled=true"
})
class DemoSettingsTest {

    @Autowired
    DemoSettings settings;

    @Test
    void bindsWithoutAnyCloudProvider() {
        assertEquals("from-test", settings.displayLabel());
        assertEquals(Duration.ofMillis(750), settings.retryDelay());
        assertTrue(settings.featureEnabled());
    }
}
```

Run:

```bash
./gradlew test
```

or:

```powershell
.\gradlew.bat test
```

The test confirms Binder works without Config Server, Consul, or Vault. This is the **baseline**, crucial so that when adding a provider you can tell which issues come from the remote integration versus application code itself.

## 12. Lab B: Spring Cloud Config Client variant

From the Boot-only project, create a **practice branch or experimental copy** for Config Client. Do not add all integrations into the base build and keep swapping imports if you want clean error isolation.

### 12.1. Add BOM and starter

Keep the plugins, Java toolchain, and test dependencies of `build.gradle`, and add:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a **complete replacement for the `dependencies` block**, not a snippet to copy alongside an existing duplicate block in the same file.

### 12.2. Declare import in application.yaml

Replace the configuration with:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "configserver:http://localhost:8888"

demo:
  display-label: "local-fallback"
  retry-delay: 500ms
  feature-enabled: false
```

When Config Server is unavailable, importing without `optional:` causes the client to fail to start. This is an intentional **fail-fast decision** in the lab to demonstrate that an external dependency has been added to the startup path.

To test fallback in dev:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

When the server is absent and treated as optional, the client can use local values. In production, explicitly define whether missing remote config is permitted to continue or must fail startup.

### 12.3. Create a standalone Config Server for learning

Create **another project** named `demo-config-server` with Spring Boot 3.3.13, Java 21, Spring Cloud BOM 2023.0.6, and the dependency:

```groovy
implementation 'org.springframework.cloud:spring-cloud-config-server'
```

Main class:

```java
package dev.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

To avoid needing a Git server in the local lab, use the **native filesystem backend** in Config Server:

```yaml
server:
  port: 8888

spring:
  application:
    name: demo-config-server
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations: "file:./config-repo"
```

Create a `config-repo` directory in the **working directory of Config Server**:

```text
demo-config-server/
  config-repo/
    demo-client.yaml
    demo-client-dev.yaml
```

`config-repo/demo-client.yaml`:

```yaml
demo:
  display-label: "from-config-server"
  retry-delay: 1s
  feature-enabled: true
```

`config-repo/demo-client-dev.yaml`:

```yaml
demo:
  display-label: "from-config-server-dev"
```

The `file:./config-repo` path depends on the working directory where the server process runs. That path is for lab use only; production should use a properly governed, authenticated, and secured backend.

### 12.4. Run both processes

1. In the server project, run `./gradlew bootRun` or `.\gradlew.bat bootRun`.
2. Verify the server can serve configuration:

```bash
curl http://localhost:8888/demo-client/default
```

When curl is unavailable on Windows PowerShell:

```powershell
Invoke-RestMethod 'http://localhost:8888/demo-client/default'
```

3. In the client project, run `bootRun`.
4. Observe `DemoSettings` bound from the active remote source.

With the example server, expected values from Config Server are:

```text
displayLabel = from-config-server
retryDelay = PT1S
featureEnabled = true
```

In a complex setup with many property sources, the final value also depends on precedence and overrides such as CLI/test/env. A clean way to test is to avoid declaring the same key in too many places in the lab.

### 12.5. Run with the dev profile

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

The server can return configuration for `demo-client/dev`, using `demo-client-dev.yaml` as a profile-specific source. Expect `displayLabel` to come from the dev configuration, while `retryDelay` retains the base remote value if no higher-priority source overrides it.

Spring Config Data may issue multiple requests in different phases to resolve profiles and load profile-specific configuration. Seeing more than one request hit Config Server **does not automatically mean** the client is broken or stuck in an infinite loop.

### 12.6. Does editing server files automatically update the client?

Do not assume so. Editing `demo-client.yaml` on the server only modifies the **server-side configuration source**. A running client can still keep the values bound at startup.

To apply changes, you can:

- Perform a controlled client restart.
- Use Spring Cloud Context/Actuator refresh if your deployment supports and properly secures it.
- Use Spring Cloud Bus to broadcast refresh signals to multiple instances, alongside a rollout policy.
- Redesign beans with an appropriate refresh mechanism rather than keeping immutable state while expecting mutation.

Refresh is a separate topic, analyzed in section 15.

## 13. Lab C: Consul Config variant

Create another variant from the **Boot-only project**, without mixing Config Client or Vault dependencies during initial testing.

### 13.1. Dependencies and import

Keep the BOM:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

In `dependencies`, use:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
implementation 'org.springframework.cloud:spring-cloud-starter-consul-config'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

In `application.yaml`:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "consul:localhost:8500"
  cloud:
    consul:
      config:
        format: PROPERTIES

demo:
  display-label: "local-fallback"
  retry-delay: 500ms
  feature-enabled: false
```

`consul:` is a location supported by Spring Cloud Consul Config, not by Boot-only. With `optional:consul:`, a client can test dev environments when the Consul agent is unavailable, though production policies should be chosen explicitly.

### 13.2. Prepare a Consul dev agent

If the Consul CLI is installed, you can run a standalone dev agent:

```bash
consul agent -dev
```

This mode is **for learning only**: it lacks the HA, ACL, and TLS guarantees required for production.

With `format: PROPERTIES`, create a KV entry at the path:

```text
config/demo-client/data
```

with the text value:

```properties
demo.display-label=from-consul
demo.retry-delay=900ms
demo.feature-enabled=true
```

You can create it via the Consul HTTP UI, CLI, or appropriate API. On Bash with the Consul API:

```bash
curl -X PUT --data-binary \
  'demo.display-label=from-consul
demo.retry-delay=900ms
demo.feature-enabled=true' \
  http://localhost:8500/v1/kv/config/demo-client/data
```

Only use the localhost dev-agent endpoint in this lesson. Production Consul should enable ACLs, TLS, and infrastructure-appropriate token/permission management.

### 13.3. Run the client and observe

Run the client:

```bash
./gradlew bootRun
```

or PowerShell:

```powershell
.\gradlew.bat bootRun
```

When the import and KV context match, the bound values should look like:

```text
displayLabel = from-consul
retryDelay = PT0.9S
featureEnabled = true
```

There is no new KV parsing logic inside `DemoSettings`: it is still the exact same Spring Boot bean. The difference is that **the property source comes from Consul**.

### 13.4. Updating KV: startup load and Config Watch

Change `demo.display-label` in KV and observe the running client. Do not assume changing a file or KV automatically rebinds every bean.

Spring Cloud Consul Config provides Config Watch to monitor prefix changes and emit refresh events. Depending on configuration and bean types, applying changes may require `@RefreshScope`, Spring Cloud rebinding, or a restart. For a constructor-bound record, do not expect it to be mutated in place like a mutable JavaBean.

### 13.5. If you only need Discovery

If a project only needs to locate instances of `payment-service` to make HTTP calls, the **Consul Discovery starter** and load balancing fit better than `consul-config` alone. That is a different problem from fetching `demo.retry-delay` from Consul KV.

Do not add `spring-cloud-starter-consul-discovery` to this lab unless your actual goal is the service catalog.

## 14. Lab D: Spring Cloud Vault variant

The Vault variant must be tested in an isolated environment and never with real secrets.

### 14.1. Dependencies and import

From the Boot-only project, keep the Spring Cloud BOM and add:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
implementation 'org.springframework.cloud:spring-cloud-starter-vault-config'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

In a minimal lab configuration:

```yaml
spring:
  application:
    name: demo-client
  main:
    web-application-type: none
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "http://127.0.0.1:8200"
      authentication: TOKEN
      token: "${VAULT_TOKEN}"
      kv:
        enabled: true
        backend: secret
```

Notes:

- The HTTP URI is only for a **localhost Vault dev server**; production must use TLS.
- `${VAULT_TOKEN}` reads the value from the environment; never hardcode real tokens in source files.
- `vault://` imports default KV contexts based on backend configuration, application name, and profile.
- All authentication, policies, and secret paths in real systems must follow that Vault environment's rules.

### 14.2. Start the Vault dev server

If the Vault CLI is installed, in a private local environment:

```bash
vault server -dev
```

Vault dev mode prints a test token and localhost endpoint. Never copy that token into Git, persistent logs, or public channels. Configure `VAULT_ADDR` and `VAULT_TOKEN` in your shell according to the dev server instructions **for this lesson only**.

Once the dev server is ready and the CLI is authenticated, write dummy data:

```bash
vault kv put secret/demo-client \
  demo.display-label=from-vault \
  demo.retry-delay=1500ms \
  demo.feature-enabled=true
```

Actual secret paths may depend on KV v1/v2, mount paths, and Vault configuration. This lesson uses the default KV backend in dev mode for illustration.

### 14.3. Do not print secrets in the runner

In this lab, we put **non-sensitive** `demo.*` keys into Vault to observe binding. In production, Vault should serve secrets such as:

```text
payment.api-token
spring.datasource.password
```

Do not add `System.out.println(settings.apiToken())`, do not log an entire record containing tokens, and do not expose `/actuator/env` to everyone. When verification is needed, only confirm whether configuration loaded and inspect non-sensitive parts such as `present/absent` status.

### 14.4. Understanding `optional:vault://` through Vault semantics

Providers handle `optional:` differently. According to Spring Cloud Vault documentation, an optional Vault location specifically applies when Vault support has been disabled via `spring.cloud.vault.enabled=false`; secret contexts returning 404 follow dedicated rules and depend on `fail-fast`.

Therefore, **do not assume** that:

```yaml
spring:
  config:
    import: "optional:vault://"
```

always means "if Vault is down, silently use defaults" identically to an optional file or optional Config Server. You must test your exact Spring Cloud Vault version across connectivity loss, auth errors (401/403), missing secret paths, and fail-fast options.

For configuration depending on mandatory secrets, the safe approach is usually to **prevent the application from becoming ready if secrets cannot be retrieved or are invalid**.

## 15. Runtime changes: startup load, refresh, watch, bus, restart

A very common misconception:

> "I put configuration into a centralized server, so editing the server means every application picks it up right away."

In reality there are at least four stages:

```text
A. Source changed
   Git commit / Consul KV update / Vault secret rotation
                       |
                       v
B. Change detected
   manual poll / webhook / watch / bus / restart
                       |
                       v
C. Environment updated
   property sources reloaded via a supported mechanism
                       |
                       v
D. Application components apply change
   bean rebind, @RefreshScope, recreate resource, restart...
```

If a system performs A and B without D, business logic can continue using old values.

### 15.1. `@Value` is a snapshot at injection time

A field:

```java
@Value("${demo.display-label}")
private String displayLabel;
```

is typically assigned when the bean is created. When the remote backend changes, this field does not automatically subscribe to a topic or file watcher. A refresh mechanism may help recreate or re-inject beans depending on scope, but you must not assume all fields live-update.

### 15.2. `@ConfigurationProperties` also needs a refresh strategy

Spring Cloud has mechanisms to rebind certain `@ConfigurationProperties` beans, though behavior depends on type and setup:

- Mutable JavaBeans can be rebound in some refresh flows.
- Records and immutable constructor-bound objects **are not automatically rebound like mutable JavaBeans**.
- A service that holds a reference or copied value from startup can keep using old state.
- Resources such as `DataSource`, HTTP clients, schedulers, and connection pools need lifecycle management rather than just swapping a String.

For configuration affecting system invariants, a rolling restart can be easier to govern and test than partial live refresh.

### 15.3. `@RefreshScope` has limitations

`@RefreshScope` in Spring Cloud allows target beans to be recreated when the scope cache is invalidated. It enables a bean to be rebuilt with new values in supported scenarios.

However:

- Not every bean type refreshes safely.
- Shared resources may require graceful shutdown/recreation handling.
- Constructor-bound configuration records do not magically become mutable.
- Beans depending on a refreshed bean are not necessarily all recreated.
- Spring Cloud refresh scope **is not supported the same way in AOT/native images**; documentation recommends disabling refresh when native compilation is needed.

Do not slap `@RefreshScope` onto every class and assume you have a zero-downtime rollout mechanism.

### 15.4. `/actuator/refresh` is a sensitive management endpoint

Spring Cloud Context can expose `/actuator/refresh` when the appropriate dependency and configuration are present. The endpoint must not be exposed publicly to the Internet.

If enabled:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: refresh
```

it must have authentication, authorization, network policies, and auditing. In real systems, prefer a controlled deployment workflow over allowing arbitrary callers to force instance refreshes.

### 15.5. Consul Watch, Cloud Bus, and refresh are different

- **Consul Watch:** detects KV changes and emits integration-specific events.
- **Spring Cloud Bus:** broadcasts coordination events across multiple instances when paired with a message broker and configuration.
- **Actuator refresh:** a mechanism to trigger reloading a portion of context/configuration for an instance.
- **Restart/rolling deployment:** builds a fresh process/bean graph from the effective configuration.

These are **complementary** mechanisms, not different names for the same feature. Choose among them based on consistency requirements, propagation speed, and rollback needs.

## 16. `optional`, fail-fast, and connection-loss behavior

When configuration sources are remote, infrastructure outages can turn into application startup failures.

Classify your data:

**Group A — critical configuration that must never run wrong:** database credentials, security policies, mandatory production endpoints, encryption material.

**Group B — configuration with valid fallbacks:** display labels, timeouts with safe defaults, feature flags with clear and tested defaults.

Policies should differ accordingly.

| Case | Appropriate behavior to consider |
| --- | --- |
| Missing optional local file | `optional:file:` with tested defaults |
| Config Server down, mandatory config is remote | Fail startup, bounded retries, appropriate health/readiness |
| Config Server down, remote only supplements a non-critical feature | Optional with safe local fallback |
| Consul KV down while data holds critical policies | Fail-fast or an approved cache/restart mechanism |
| Vault authentication fails | Never fall back to dummy credentials; fail and do not take traffic |
| Vault secret does not exist | Verify backend path, role, policy, and fail-fast |
| Server returns schema-invalid data | Conversion/validation must reject invalid values |
| Remote source changes while serving | Refresh/restart with designed consistency |

**Do not apply one blanket `optional:` policy to every provider and assume the whole system is safe.**

### 16.1. Retries do not replace validation

Some errors are worth retrying: transient network timeouts, a backend still starting up. Other errors will not be fixed by retrying: wrong token, wrong ACL, invalid URL, configuration missing required fields.

A solid retry policy needs:

- Bounded attempt count and total duration limit.
- Reasonable backoff, with jitter when many clients start together.
- Distinction between recoverable and non-recoverable errors.
- No sensitive details printed in logs.
- Readiness set appropriately when mandatory configuration is missing.
- Alerts and metrics so operations knows when a backend is degraded.

### 16.2. Caching and fallback carry risks

A client or Config Server may retain previously loaded data, or a backend may employ caching. When the upstream source is temporarily unavailable, caches can keep things running.

Yet you must ask:

- How long is the cache valid?
- Does it belong to the server, the client, or a sidecar?
- Are stale values acceptable?
- Could it contain revoked secrets?
- Upon recovery, how does the system know which version is active?
- Is there a way to flag stale configuration?

Do not treat a cache as proof that data is current or safe.

## 17. Source precedence: "remote" is not absolute by default

When multiple sources define the same key:

```text
demo.display-label
```

the final value depends on **PropertySource precedence** and how each provider inserts sources into `Environment`.

For example, all of these can exist simultaneously:

```text
application.yaml
application-dev.yaml
Consul KV
Config Server
Vault KV
Java system properties
environment variables
command-line arguments
```

Do not take one static ordering from a single project and assume it applies to every configuration setup. Some integrations also have their own remote overrides, profile contexts, and import ordering behavior.

Establish explicit conventions:

1. Which keys are managed exclusively by the platform?
2. Which keys permit local overrides?
3. Which keys are secrets that must never fall back to plaintext files?
4. When keys collide, which source has authority?
5. With multiple imports, is the declaration order intentional?
6. When profiles change, how is the remote context selected?

In labs, use **non-overlapping** keys between local and remote first to prove imports work, and only then run controlled key-collision tests. This separates connectivity issues from precedence issues.

### 17.1. Boot Config Data follows import order

`spring.config.import` can accept multiple locations. Following Boot's rules, imported documents are processed in order and follow precedence rules relative to the document declaring the import.

However, each provider can resolve across multiple profiles/contexts in its own way. When combining Config Server, Consul, and Vault in one app, read the documentation for your **exact provider versions** and write integration tests for colliding keys rather than relying on a generic diagram.

### 17.2. Avoid declaring the same secret in multiple places

An ambiguous design:

```text
spring.datasource.password:
  application.yaml = dev-password
  Config Server = another-password
  Vault = production-password
  environment = password-from-ci
```

The result is hard to audit, and an override can cause the application to use an unintended credential. For production secrets, establish **one clear owner**, a governed auth/policy path, and tests verifying the active source.

## 18. Permissions: who can edit, who can read, who can deploy?

Product boundaries mirror organizational boundaries.

### 18.1. Boot-only file/configtree

Anyone who can alter the container image, environment variables, or mounted files can affect configuration. Controls primarily reside in CI/CD, image registries, filesystem/container security, and Kubernetes RBAC.

### 18.2. Spring Cloud Config

Typically involves at least two permission sets:

- Permission to modify the backend repository (e.g., Git).
- Permission for clients to read Config Server and for Config Server to read the backend.

You can add pull-request approvals, release branches/tags, signed commits, and Config Server access controls. Do not assume that because Git has commit history, Config Server's HTTP endpoints are automatically protected from unauthorized clients.

### 18.3. Consul

Define:

- Which KV prefixes an ACL token is permitted to read.
- Who can write KV entries.
- Whether Consul agents/servers enforce TLS properly.
- Whether service discovery permissions are separated from KV config permissions.
- How watches are monitored and whether they could trigger a reload storm.

### 18.4. Vault

Define:

- Workload identity and authentication method.
- Policies per secret path and role.
- TTLs, lease renewal, and revocation.
- Auditing, seal/unseal, HA, and backups at the infrastructure layer.
- How applications and sidecars receive secrets without exposing tokens.
- How expired credentials in open resources are handled.

A system using Vault while hardcoding a root token in a repository is not a secure design simply because the product name includes "Vault".

## 19. Choosing technology based on real needs

### 19.1. Small application, few environments

Use:

```text
Spring Boot Config Data + profiles + env vars
```

along with an appropriate secret-management pipeline. You do not need to deploy a dedicated Config Server if operating that server costs more than the benefit it delivers.

### 19.2. Many microservices needing GitOps/reviewed config rollouts

Consider:

```text
Spring Cloud Config Server + Config Client
```

if you want a centralized configuration API keyed by application/profile/label backed by Git. Explicitly specify HA, ACLs, TLS, caching, and refresh requirements.

### 19.3. Organizations already running Consul

If Consul is already used for the service catalog and KV is well-governed:

```text
Spring Cloud Consul Config
```

can work well for shared and service-specific KV. Determine whether the app truly needs Consul Discovery or only Consul Config.

### 19.4. Sensitive secrets, short-lived credentials, rotation

Consider:

```text
Vault + Spring Cloud Vault
```

or:

```text
Vault Agent/CSI -> files -> Spring Boot configtree
```

The choice depends on whether the application should interact with the Vault API directly or infrastructure already handles mounting secrets.

### 19.5. Kubernetes with existing ConfigMap/Secret workflows

You can use:

```text
Kubernetes volume/env -> Spring Boot
```

without Cloud Config or Consul, if requirements allow. Just do not confuse Kubernetes Secrets with Vault's secret lifecycle; evaluate concrete security and rotation needs.

### 19.6. Combining two or three systems

Example:

```text
Config Server: feature flags and operational settings
Vault: credentials and keys
Consul Discovery: locating service endpoints
```

This is a valid architecture, though it introduces multiple dependency paths and increases operational overhead. Combine them only when each system has a distinct responsibility. Do not use all three to manage the same property without ownership rules.

## 20. Designing fallbacks for a payment service

Suppose a service requires:

```yaml
payment:
  retry:
    max-attempts: 3
  display-label: "Payments"
```

and these secrets:

```text
payment.gateway-token
spring.datasource.password
```

One way to divide responsibilities:

| Property | Suggested source | Reason |
| --- | --- | --- |
| `payment.retry.max-attempts` | Config Server or Boot file | Non-secret, reviewable, and easy to roll back |
| `payment.display-label` | Boot file/profile | No remote lookup needed if rarely changed |
| `payment.gateway-token` | Vault | Secret requiring policies and rotation |
| `spring.datasource.password` | Vault or equivalent secret manager | Avoid plaintext in Git/JAR |
| Current service addresses in cluster | DNS or service discovery | Typically not static config reviewed in Git |

If Config Server loses connectivity and only the fallback label remains, the app may still run safely. But if Vault fails to issue the gateway token, the app must not pretend to process payments normally with a dummy value.

**Startup behavior must reflect the criticality of each configuration item**, not just whether a plugin supports `optional:`.

## 21. Integration testing: test boundaries instead of everything at once

A practical test suite should be layered.

### 21.1. Unit testing application code

Instantiate `DemoSettings` with fake values to test service logic. No Config Server, Consul, or Vault needed.

Example:

```java
DemoSettings settings = new DemoSettings(
        "unit", Duration.ofMillis(500), true);
```

This is a pure Java test; it does not verify any remote integration.

### 21.2. Spring Boot-only integration tests

Use `@SpringBootTest(properties = ...)` to confirm Binder and records work without Cloud dependencies. Lab A showed an example.

### 21.3. Contract tests with Config Server

Run a test Config Server instance returning config for a specific app/profile/label and verify the client receives expected keys. Also test server-down scenarios and fail-fast/optional policies.

### 21.4. Contract tests with Consul KV

Use a CI-managed Consul test agent/container, populate the agreed key prefix and format, and verify the data appears in Environment. If watch is used, update keys and verify refresh behavior **on the appropriate bean type**.

### 21.5. Contract tests with Vault

Use an isolated Vault dev/test cluster with least-privilege auth policies and dummy secrets. Verify:

- Authentication works and invalid tokens are rejected.
- Correct secret paths and profiles are loaded.
- No secrets are printed in logs.
- Missing secrets follow the expected fail-fast policy.
- Refresh/rotation/lease lifecycles work if required by the product.
- Tests never use production root credentials in CI.

### 21.6. Resilience tests

Simulate:

```text
Config Server down
Consul agent down
Vault returns 403
Vault returns 404 for path
DNS failure
Network timeout
Stale config present when fresh config is unavailable
```

Measure whether the app **fails to start, falls back, becomes unready, or restarts** according to its actual policy. One successful startup against a healthy backend does not prove the app behaves safely when remote sources fail.

## 22. Common errors and how to classify them

### 22.1. `Unable to load config data from 'configserver:'`

Check:

- Is `spring-cloud-starter-config` present at the right version?
- Does `spring.config.import` have the right URL/format?
- Is Config Server started and reachable from the client's network?
- Are there TLS, DNS, auth, or timeout issues?
- Is legacy bootstrap enabled, causing config resolution to behave differently than expected?

### 22.2. Added Config Client starter but forgot the import

In the modern Config Data model, an entry such as:

```properties
spring.config.import=optional:configserver:
```

or a non-optional import is required. If Config Client is on the classpath without an import, the application may warn or fail to start depending on that version's validation check. Do not blindly disable the import check; decide explicitly whether the app is meant to pull config from Config Server.

### 22.3. Config Server returns data, yet the service still uses local values

Possible causes:

- Wrong `spring.application.name`, profile, or label.
- Wrong filename in the config repository.
- Unexpected import precedence or remote override behavior.
- CLI arguments or env vars overriding it.
- Client has not restarted/refreshed after the server changed.
- A bean copied the old value into another field.

Separate **what the server returns** from **what the client receives** and **what the bean actually uses**.

### 22.4. Consul agent is running, yet the app finds no keys

Check:

- Is the Consul KV path properly `config/<application>/...`?
- Is the application name right?
- Which active profile is enabled?
- Does `format` match the KV layout?
- For YAML/PROPERTIES formats, is the `data` key correct?
- Does the ACL token have `read` permission on that prefix?
- Is another Consul agent running on the configured host/port?

Do not change key prefixes, profiles, imports, and formats all at once; change one factor at a time to isolate the cause.

### 22.5. Consul Watch emits events, yet service values stay unchanged

Verify whether the bean is actually rebound/refreshed via a supported mechanism. `@Value` and constructor-bound records do not turn into live properties merely because an event was emitted.

### 22.6. Vault returns 403

This is usually an auth/policy/path issue. Verify identity, token lease, Vault namespace (if used), mount path, and policies. **Never** disable TLS, log tokens, or hand production a root token as a "quick fix".

### 22.7. Vault path returns 404

Distinguish between:

- The secret path does not exist.
- Wrong KV v1/v2 mount or path.
- Wrong `spring.application.name` or profile context.
- Wrong contextual location.
- Fail-fast policy mismatch with expectations.

Vault optionality has specific semantics; do not infer them from how `optional:file:` behaves.

### 22.8. `@ConfigurationProperties` has `null` while Environment has the key

Could be a property name mismatch, constructor binding issue, validation, wrong bean instance, reading too early, or updated config before bean refresh. This is a **binding/lifecycle** issue that can occur with any of the four sources, not necessarily a provider bug.

### 22.9. Secret tokens appear in Actuator or logs

Stop printing raw properties, review endpoint exposure/roles, configure sanitization/masking, audit trails, and rotation procedures. Do not rely on default masking across versions to assume exposing `/actuator/env` or `configprops` to all callers is safe.

### 22.10. Multiple providers override the same key

Define a single owner. Do not rely on implicit ordering to resolve long-term conflicts. Establish clear namespaces, write precedence tests, and document ownership in an auditable runbook.

## 23. Step-by-step migration from Boot-only to centralized config

A migration should proceed incrementally:

**Step 1 — Inventory existing keys.** Classify non-secrets, secrets, feature flags, connection settings, and build-time-only settings.

**Step 2 — Assign an owner per group.** For instance, Config Server for non-sensitive policies, Vault for credentials.

**Step 3 — Standardize names.** Use canonical kebab-case and clear prefixes to avoid colliding with framework properties.

**Step 4 — Set safe defaults for non-secrets.** Identify which keys are mandatory and which have fallbacks.

**Step 5 — Pick the matching integration starter and release train.** Never mix Spring Cloud versions uncontrollably.

**Step 6 — Migrate a small group of keys first.** Keep binding tests, inspect Environment after import, and keep secrets out of logs.

**Step 7 — Test fail-fast/optional behavior.** Simulate the remote backend being offline and document the application's readiness decision.

**Step 8 — Choose between refresh and restart.** For settings affecting bean structure or core resources, prefer controlled rollout/restart where appropriate.

**Step 9 — Enable security and operational controls.** TLS, ACLs/policies, auditing, backups, HA, monitoring, and alerting.

**Step 10 — Test rollback.** Ensure you can revert to an earlier configuration version or turn off a change without accidentally reverting to revoked credentials.

Never simultaneously migrate all keys, introduce a remote provider, alter `@ConfigurationProperties` schemas, switch profiles, and enable dynamic refresh in a single release. Doing so makes root-cause analysis very difficult.

## 24. Decision matrix for architects

| Question | If "yes", consider |
| --- | --- |
| Only need files + env vars, managed via CI/CD? | Plain Boot |
| Multiple apps share non-secret config by app/profile/label, wanting Git history? | Config Server |
| Already run Consul and need KV contexts by app/profile? | Consul Config |
| Need service registration/health/discovery? | Consul Discovery or DNS equivalent; do not confuse with KV Config |
| Need tokens/passwords with dedicated policies and auditing? | Vault/secret manager |
| Need dynamic DB credentials with leases? | Vault backend and rotation design |
| Kubernetes already mounts ConfigMap/Secret into pods? | Boot env/configtree may suffice |
| Need runtime refresh? | Evaluate Spring Cloud refresh, watch, bus, or rollout |
| Need HA and zero network dependency at startup? | Evaluate caching/fallback, local mounts, operational strategy |
| Using native image/AOT? | Check provider support and refresh limitations |

There is no single "best option for every project". What matters is choosing the **fewest components** that still meet operational, security, and change-management requirements.

## 25. Practice exercises

### Exercise A — Identify boundaries

Given the following requirements:

1. Read `application.yaml` by profile.
2. Bind timeout `250ms` to a `Duration`.
3. Serve Git config by app name and profile.
4. Look up the current IP of a Consul-registered service.
5. Read dynamic tokens from a secret backend.
6. Read values from a secret file mounted into a container.
7. Refresh a bean when Consul KV changes.
8. Audit every time a service reads a secret.

Classify each under: Boot core, Cloud Config, Consul Config/Discovery, Vault, or a refresh coordination mechanism.

### Exercise B — Fail-fast design

An application has two groups:

```text
feature.banner-title
payment.gateway-token
```

For each, choose `optional` or required for the import and explain why a fallback acceptable for a banner may be unacceptable for a gateway token.

### Exercise C — Config Server profiles

Create:

```text
demo-client.yaml
demo-client-dev.yaml
```

in Lab B's local config repository. Start the server, GET `/demo-client/default` and `/demo-client/dev`, then run the client with `--spring.profiles.active=dev`. Record the value of `demo.display-label` and explain the relationship between application name, profile, and server files.

### Exercise D — Consul KV

Create the `config/demo-client/data` key containing properties. Verify whether the Consul client binds `demo.retry-delay` to `Duration`. Then update the key and observe whether a running instance updates automatically.

### Exercise E — Never log Vault secrets

Add `payment.gateway-token` in Vault dev. Write Java code that prints only:

```text
gatewayTokenPresent = true
```

when a token exists, never printing the value itself. Explain why a record's `toString()` can leak a secret if you add the token to a configuration record and log the whole record.

### Exercise F — Kubernetes without Spring Cloud

Suppose a pod mounts the file:

```text
/run/secrets/payment.gateway-token
```

Write the `configtree:` import so Boot reads that key, and describe the boundary between Kubernetes Secret, CSI driver, Vault, and Spring Boot.

### Exercise G — Refresh and consistency

Config Server changes a timeout, yet a singleton service copied the timeout into a `final Duration` inside its constructor. List the conditions required for the service to actually adopt the new value. When should you use a rolling restart instead?

### Exercise H — Version alignment

A project uses Spring Boot 3.3.13 but adds a Spring Cloud starter from an incompatible release train. Explain why a compatible BOM matters and how to check the version matrix before upgrading.

### Exercise I — Connection loss

Test three scenarios in a lab environment:

1. Stop Config Server before starting the client.
2. Stop the Consul agent before starting the client.
3. Access Vault using an under-privileged token.

Compare the error messages and fail-fast/optional policies. Never include real tokens or stack traces containing secrets in your report.

### Exercise J — Who owns a property?

Two teams both want to manage `demo.feature-enabled`: the app team puts it in YAML, while the platform team puts it in Consul KV. Propose a clear ownership rule and an integration test to prevent source conflicts.

## 26. Self-check questions

**1.** Does plain Spring Boot support external files outside the JAR, profiles, and `configtree:`?

**2.** Does plain Spring Boot automatically provide an HTTP Config Server to read a Git repository?

**3.** How do Config Server and Config Client differ in role?

**4.** Is the `configserver:` prefix recognized by Boot core or by the Spring Cloud Config integration?

**5.** When is `spring.config.import=optional:configserver:` typically used?

**6.** In Consul, are KV Config and service discovery the same API/starter?

**7.** Why does Consul KV not replace a Git review workflow by default?

**8.** What capabilities does Vault offer that `application.yaml` does not provide?

**9.** Is `vault://` a local file path that can be opened with Java NIO?

**10.** Does `optional:vault://` guarantee ignoring every Vault outage error?

**11.** Why might updating Git/Consul/Vault still require restarting or refreshing the client?

**12.** Does `@RefreshScope` automatically make all singletons and constructor-bound records refresh safely?

**13.** When running native images, what limitation of Spring Cloud refresh should you check?

**14.** By what mechanism can plain Boot read a Kubernetes Secret mounted as a file?

**15.** Do `ConfigMap` and `Vault` share the same secret lifecycle model?

**16.** Why must you check Spring Boot/Spring Cloud version compatibility?

**17.** Why should you never commit a root Vault token into `application.yaml` even in a private repo?

**18.** Which configuration should fail-fast if missing: banner title or database password?

**19.** If a service is using credentials that Vault just revoked, what besides the property value may need handling?

**20.** When multiple providers declare the same key, what must you check?

### Suggested answers

1. Yes.
2. No; you need Spring Cloud Config Server or an equivalent solution.
3. Server exposes the API and reads backends; client feeds remote properties into Environment.
4. Spring Cloud Config integration.
5. When the application permits handling an absent server with safe local fallbacks.
6. No; they are separate capabilities and starters.
7. KV has its own management API and does not inherently provide a pull-request workflow.
8. Auth, policies, auditing, secrets engines, and leases/rotation depending on the backend.
9. No; it is a Config Data location provided by Spring Cloud Vault.
10. No; semantics depend on the provider and error category.
11. Because updating the source, detecting events, and applying state to beans are separate stages.
12. No; refresh has specific scopes, types, and lifecycles.
13. RefreshScope is not supported the same way as on JVM in AOT/native per Spring Cloud Context docs.
14. `configtree:`, or environment variables if secrets are injected into the process.
15. No; permissions, storage, policies, and rotation must be evaluated specifically.
16. To avoid API/dependency incompatibilities and unnecessary startup failures.
17. Because repos, images, logs, and backups can expose an overly privileged token.
18. Database password, unless another approved credential mechanism is used.
19. Connection pools, sessions, leases, resource recreation, and retries.
20. Precedence, profiles, location/import ordering, ownership, override policies, and tests.

## 27. Production and operations checklist

Before approving an externalized configuration solution:

- [ ] Ownership is documented for every prefix and each source system.
- [ ] No production secrets are hardcoded in code, JARs, or plaintext Git.
- [ ] Spring Cloud BOM matches the Spring Boot version in use.
- [ ] Config Server/Consul/Vault are configured with appropriate TLS and auth.
- [ ] Read/write permissions on KV, config repos, or secrets follow least privilege.
- [ ] Health checks, metrics, and logs exist for config-loading failures (without leaking secrets).
- [ ] Policies exist for when remote sources are down or return invalid data.
- [ ] Bounded retries/backoff with jitter are configured to avoid thundering herds.
- [ ] A rollback mechanism exists for non-secret config.
- [ ] A plan exists to rotate/revoke secrets and handle connection pools.
- [ ] Precedence tests exist where multiple sources define important properties.
- [ ] Refresh vs. rolling restart decisions are defined for each configuration group.
- [ ] Management Actuator endpoints are secured and not exposed indiscriminately.
- [ ] Tested across local, staging, and production-like environments.
- [ ] Runbooks exist for startup failures caused by Config Server, Consul, or Vault.
- [ ] AOT/native build rules are documented if the project uses native images.
- [ ] Auditing exists for who changed configuration and who is authorized to read secrets.

A technology choice is only good if the operations team can explain the **current source of every value**, how a change is rolled out, and how the system responds when that source becomes unavailable.

## 28. Conclusion

Spring Boot Externalized Configuration already provides a **powerful engine for reading, prioritizing, and binding configuration**. Cloud integrations do not replace that engine; they **add different data sources and operational capabilities**.

```text
Boot core
    = Environment + Config Data + Binder + Profiles + PropertySources

Spring Cloud Config
    = Config Server/Client + remote configuration distribution

Spring Cloud Consul Config
    = Consul KV -> Spring Environment

Spring Cloud Consul Discovery
    = service registration / discovery (distinct from KV config)

Spring Cloud Vault
    = Vault secret backends -> Spring Environment
      + Vault auth/secret lifecycle policies

Kubernetes volume/env
    = a path feeding config into Boot, potentially without Cloud plugins
```

The single most important takeaway: **"Configuration is stored centrally" does not mean "every instance immediately receives and applies new data"; "a key is fetched from Vault" does not mean "every resource using that secret rotates automatically"; and "having a Spring Cloud dependency" does not mean "you already have complete security and HA."**

Choose technologies by responsibility: regular configuration, centralized distribution, service discovery, secret management, or refresh. Then clearly design versioning, auth, permissions, precedence, fail-fast behavior, refresh/restart, and testing.

### Official references

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, property precedence, Config Data imports, config trees, and type-safe binding.
2. [Spring Cloud Release Train 2023.0](https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html): compatible Spring Cloud and Boot versions.
3. [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/4.1/client.html): `configserver:` import, profiles, fail-fast, retry, and bootstrap.
4. [Spring Cloud Config — Server](https://docs.spring.io/spring-cloud-config/reference/4.1/server.html): server configuration and `@EnableConfigServer`.
5. [Spring Cloud Consul — Distributed Configuration](https://docs.spring.io/spring-cloud-consul/reference/config.html): Consul KV, `consul:` import, contexts, watch, and formats.
6. [Spring Cloud Vault — ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): `vault://`, contextual locations, optionality, and backend integration.
7. [Spring Cloud Vault — Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html): supported Vault authentication methods.
8. [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): refresh scope, rebinding, and limitations.
9. [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): Git repositories, labels, and server operations.
