# Role of `bootstrap.yml` Compared to `application.yml`

In a Spring Boot application integrated with Spring Cloud, the two filenames **`bootstrap.yml`** and **`application.yml`** correspond to two different configuration phases. `application.yml` is Spring Boot's standard configuration file. `bootstrap.yml` belongs to Spring Cloud's bootstrap context mechanism in the legacy integration approach; it is only loaded when that bootstrap mechanism is enabled.

This distinction is critical when using Spring Cloud Config. Since Spring Boot 2.4, the recommended default way to integrate Config Server is **Config Data import** via `spring.config.import`. With this approach, the application declares the Config Server source in `application.yml` or `application.properties`, and **does not need `bootstrap.yml`**. The old bootstrap context approach can still be used when a project explicitly enables it, typically via `spring-cloud-starter-bootstrap` or a bootstrap property supplied through a system property/environment variable.

This lesson belongs to the **Bootstrap** chapter of the **SPRING_CLOUD_CORE** module, helping learners distinguish configuration files from the initialization context, understand how remote configuration enters `Environment`, how profiles and property sources are processed, as well as how to test and operate both models.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish `bootstrap.yml`, `application.yml`, and the bootstrap application context.
2. Explain why `bootstrap.yml` is not automatically loaded in every Spring Cloud application.
3. Describe the legacy bootstrap context model and the parent-child relationship with the main application context.
4. Configure Spring Cloud Config using Config Data import in `application.yml`.
5. Enable and configure legacy bootstrap when an application genuinely needs this mechanism.
6. Compare the position and precedence of property sources across both integration approaches.
7. Distinguish startup configuration loading from runtime configuration refresh.
8. Plan testing, observability, and migration from legacy bootstrap to Config Data.

## 2. Distinguishing three commonly confused concepts

| Concept | Meaning | When does it appear? |
| --- | --- | --- |
| `application.yml` | Standard configuration file loaded by Spring Boot via Config Data | During `Environment` preparation for the Boot application |
| `bootstrap.yml` | Configuration file by convention for the Spring Cloud bootstrap context | When the legacy bootstrap mechanism is enabled |
| Bootstrap application context | A separate `ApplicationContext`, usually the parent context of the main context, used to prepare configuration and bootstrap integrations | In the legacy Spring Cloud bootstrap model |

**A filename is not synonymous with an initialization phase.** A file named `bootstrap.yml` sitting in `src/main/resources` does not automatically create a bootstrap context. The bootstrap mechanism must be enabled and the appropriate dependencies must be present.

Similarly, some documentation uses the phrase *bootstrap properties* to refer to properties loaded during the bootstrap phase. That phrase does not refer only to keys located inside a file named `bootstrap.yml`; for instance, a remote property source returned by Config Server can also be a bootstrap property source.

## 3. `application.yml`: Spring Boot's primary configuration

Spring Boot searches for and loads `application.properties`, `application.yml`, or `application.yaml` from the defined Config Data locations. This file can contain shared configuration, profile-specific configuration, and import declarations for other sources.

Example:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: dev

server:
  port: 8080

clients:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 200ms
    read-timeout: 700ms
~~~

Property groups can be read through `Environment` or bound into beans using `@ConfigurationProperties`. In a Spring Cloud application, `application.yml` typically contains:

- Application name and profiles.
- HTTP client, timeout, and downstream endpoint configurations.
- Discovery or service registry options.
- Actuator, logging, and health configurations.
- `spring.config.import` to load Config Server or other Config Data sources.

`application.yml` is not a file "only read after all beans are created". Spring Boot loads Config Data during `Environment` preparation, before the normal bean creation phase. Therefore, properties in this file can participate in determining profiles, configuration, and application auto-configuration.

## 4. The bootstrap application context in the legacy model

### 4.1. Why is a separate bootstrap context needed?

In the legacy bootstrap model, Spring Cloud creates a **bootstrap context** as the parent context of the main application. This context prepares required components before the main application context is initialized, especially external configuration sources.

Overview flow:

~~~mermaid
flowchart TD
    A[Start SpringApplication] --> B[Enable legacy bootstrap]
    B --> C[Create bootstrap ApplicationContext]
    C --> D[Read bootstrap.yml and bootstrap profiles]
    D --> E[Run PropertySourceLocator / Config Client]
    E --> F[Receive remote PropertySource]
    F --> G[Create main ApplicationContext]
    G --> H[Load application.yml and local configuration]
    H --> I[Register beans and auto-configuration]
    I --> J[Application ready]
~~~

The bootstrap context can create beans needed for the bootstrap phase, such as `PropertySourceLocator` or integrations for configuration loading. The resulting property sources are then fed into the main application's configuration according to the context hierarchy mechanism.

The historical goal of this model was to allow an application to fetch remote configuration before initializing beans that depend on that configuration. For example, Config Server might supply the database endpoint, connection details, or properties used to configure clients.

### 4.2. Parent-child relationship between the two contexts

In the legacy model:

- The bootstrap context is the **parent** of the main application context.
- The main context is the **child**.
- Contexts can inherit property sources and profiles according to Spring's hierarchy rules.
- The main context can have its own property sources, and child values can override corresponding parent values according to resolution rules.
- Each context can have its own `Environment`; sharing the same `Environment` across a context hierarchy is not the default.

Diagram:

~~~mermaid
flowchart TB
    subgraph Parent["Bootstrap ApplicationContext"]
      P1[bootstrap.yml PropertySource]
      P2[BootstrapConfiguration beans]
      P3[Remote PropertySource from Config Server]
    end
    subgraph Child["Main ApplicationContext"]
      C1[application.yml PropertySource]
      C2[Application @Configuration]
      C3[Business beans]
    end
    Parent --> Child
    P3 -. property source added to application .-> C3
~~~

The diagram is conceptual. How property sources are attached to the child and their precedence order depend on the implementation, Spring Cloud version, and override settings.

### 4.3. The bootstrap context is not a separate service

The bootstrap context is an `ApplicationContext` inside the same application process. It is not Config Server, not a service registry, and not an independently running microservice.

Config Server is an external system serving configuration over HTTP. The bootstrap context is merely a client-side mechanism to prepare the `Environment` and connect to configuration sources before the main application initializes.

## 5. What is the role of `bootstrap.yml`?

When legacy bootstrap is enabled, Spring Cloud uses the `bootstrap.yml` or `bootstrap.properties` convention for the bootstrap context. This file is suited for values required by the bootstrap process, such as:

- Config Server address (`spring.cloud.config.uri`).
- Application name or profiles needed when bootstrap queries remote configuration.
- External bootstrap source configuration.
- Certain logging properties that need to take effect early, according to the documentation of the version in use.

Example `bootstrap.yml` for legacy Config Client:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: ${SPRING_CONFIG_URI:http://localhost:8888}
      fail-fast: true
~~~

This configuration only takes effect under the legacy bootstrap model when:

1. The application has a compatible Config Client on the classpath.
2. The bootstrap mechanism has been enabled.
3. `bootstrap.yml` is placed where the bootstrap context can locate it.
4. Config Server is reachable and returns the corresponding configuration, if policy requires a successful connection.

`bootstrap.yml` does not fetch data from Config Server on its own if only the file exists without Config Client and the corresponding bootstrap mechanism.

### 5.1. Profile-specific bootstrap files

Similar to `application-{profile}.yml`, the bootstrap context can load profile-specific files such as:

~~~text
bootstrap.yml
bootstrap-dev.yml
bootstrap-prod.yml
~~~

Once a profile is determined during the bootstrap phase, the corresponding file can supply properties to the bootstrap context. If Config Client needs to request a configuration set for a specific profile, the profile must be configured early enough using the mechanism appropriate for the version in use.

### 5.2. Changing the bootstrap file location

In the legacy model, there are dedicated properties:

| Property | Role |
| --- | --- |
| `spring.cloud.bootstrap.name` | Changes the base name, defaulting to `bootstrap` |
| `spring.cloud.bootstrap.location` | Replaces the default location searched for bootstrap properties |
| `spring.cloud.bootstrap.additional-location` | Adds additional bootstrap properties locations |

Properties controlling bootstrap file discovery must be supplied early enough, typically via a system property or environment variable. They are not Config Data's `spring.config.*` properties.

## 6. Why is `bootstrap.yml` no longer the default for Config Server?

Spring Boot 2.4 introduced the **Config Data API**, and Spring Cloud Config uses this mechanism as the default way to connect to Config Server in current documentation. With this approach, the application declares `spring.config.import` in its main configuration.

Example `application.yml`:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

The application needs a compatible Config Client starter. On startup, Config Client's Config Data loader fetches configuration from Config Server and feeds the result into `Environment` preparation.

**`bootstrap.yml` is not needed for this Config Data import approach.** If a modern project adds `spring-cloud-starter-bootstrap` without needing legacy compatibility, it may unintentionally activate a different initialization mechanism and complicate diagnostics.

### 6.1. `optional:` and required configuration sources

The two declarations carry different meanings:

~~~yaml
spring:
  config:
    import: optional:configserver:http://localhost:8888
~~~

Allows the application to continue if Config Server is unreachable during import, according to Config Data's optional mechanism.

~~~yaml
spring:
  config:
    import: configserver:http://localhost:8888
~~~

Marks Config Server as a required source. If configuration cannot be fetched, startup can fail.

Choose the policy based on business requirements:

- If remote configuration only supplements non-mandatory values, `optional:` may be appropriate.
- If missing configuration prevents the application from connecting to the database or operating safely, treat the source as required and fail startup cleanly.
- Do not use `optional:` merely to hide Config Server connection errors in production.

### 6.2. Config Data may call Config Server multiple times

The Config Data loader can execute a two-step process: first fetching configuration with the `default` profile, then determining activated profiles and fetching additional configuration for the matching profiles. Thus, logs may show multiple requests to Config Server during a single startup. This is normal behavior of the import mechanism, not necessarily a retry or an error.

This handling allows remote configuration to participate in activating profiles. When inspecting startup, distinguish requests across Config Data phases from retry requests caused by network failures.

## 7. Comparing `bootstrap.yml` and `application.yml`

| Criterion | `bootstrap.yml` (legacy) | `application.yml` |
| --- | --- | --- |
| Mechanism owner | Spring Cloud bootstrap | Spring Boot Config Data |
| Context reading the file | Bootstrap context | Main application context / Config Data processing |
| Automatically read in every application? | No; requires enabling legacy bootstrap | Standard configuration file searched by Boot convention |
| Typical purpose | Configuration needed for bootstrap, e.g., Config Server URI in legacy mode | Application configuration, profiles, and `spring.config.import` |
| Modern Config Server connection | Not needed for Config Data import | Declare `spring.config.import` |
| Related dependencies | Config Client and bootstrap mechanism enabled | Compatible Config Client starter |
| Profile-specific files | `bootstrap-{profile}.yml` | `application-{profile}.yml` |
| Lifecycle | Before main context in the bootstrap hierarchy | Config Data processed while preparing the main Environment |
| When to use? | Legacy projects or integrations requiring a bootstrap context | Default choice for modern Boot/Cloud projects using Config Data |

**Rule of thumb:** If a new project only needs to fetch configuration from Spring Cloud Config Server, start with `application.yml` and `spring.config.import`. Use `bootstrap.yml` only when the project intentionally uses legacy bootstrap or an integration requires a bootstrap context.

## 8. Configuring dependencies for the two models

### 8.1. Config Data import

With Maven, the Config Client dependency can be declared as follows once the project imports a compatible Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

There is no need to add `spring-cloud-starter-bootstrap` just to use `spring.config.import`.

Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.cloud:spring-cloud-starter-config"
}
~~~

Starter versions should be managed via the `spring-cloud-dependencies` BOM compatible with Spring Boot; do not manually mix versions of Commons, Context, and Config Client.

### 8.2. Legacy bootstrap

If you need to enable the bootstrap context, you can add the starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
~~~

Or enable it via property:

~~~text
spring.cloud.bootstrap.enabled=true
~~~

According to current Spring Cloud Config documentation, this property must be set as a **system property or environment variable** to take effect early enough, for example:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar orders-service.jar
~~~

On PowerShell:

~~~powershell
$env:SPRING_CLOUD_BOOTSTRAP_ENABLED = "true"
java -jar .\orders-service.jar
~~~

The Config Client starter is required if the goal is to connect to Config Server. `spring-cloud-starter-bootstrap` enables the bootstrap mechanism; it does not replace `spring-cloud-starter-config`.

**Do not enable both mechanisms just to "make sure configuration gets loaded".** First decide whether the project uses Config Data or legacy bootstrap, then keep one model intentionally and verify the property source order.

## 9. Property sources and precedence order in legacy bootstrap

One of the key differences is how property sources from the bootstrap context are fed into the application.

### 9.1. The bootstrap file and remote property sources are two distinct sources

In the legacy model:

- `bootstrap.yml` creates a property source used to configure the bootstrap context.
- Config Client can fetch configuration from Config Server and produce a remote property source, often grouped under a source named `bootstrap`.
- These two sources are not synonymous and can have different precedence levels.

According to Spring Cloud Context documentation, the property source containing remote data from the bootstrap context usually has high precedence. Meanwhile, the property source read directly from `bootstrap.yml` can have lower precedence than the child context's `application.yml` configuration.

Therefore, do not assume that **every key in `bootstrap.yml` always overrides every key in `application.yml`**. Distinguish the local configuration source of the bootstrap file from the remote property source produced during the bootstrap phase.

### 9.2. Allowing local overrides of remote properties

With legacy bootstrap, remote property sources usually do not allow local config to override them by default. Config Server can grant override permission via server-side properties:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          # Example solely illustrating server override configuration
          banner: "Managed by platform"
~~~

In addition, Spring Cloud Context documentation describes properties controlling overrides for remote property sources:

- `spring.cloud.config.allowOverride=true`: override permission must be granted from the remote/server source; setting it locally does not substitute for this permission.
- `spring.cloud.config.overrideNone=true`: allows local sources to override remote values.
- `spring.cloud.config.overrideSystemProperties=false`: restricts which source types can override according to bootstrap rules.

Read the documentation for your exact release train and Config Server configuration before applying these. These options belong to the legacy property source model; do not copy them verbatim to Config Data import without verifying the behavior of the version in use.

### 9.3. Checking the actual order

You can use Actuator `env` in a secured environment or list `PropertySource` entries from `ConfigurableEnvironment` to determine:

1. The names of present sources.
2. Their order.
3. Which source supplies a key.
4. The final resolved value.
5. Whether remote values are overridden locally.

Do not look solely at `bootstrap.yml` and assume the runtime value. Command-line configuration, environment variables, Config Data, and remote sources can all participate in the same `Environment`.

## 10. Discovery First Lookup for Config Server

Spring Cloud Config Client can locate Config Server through a discovery service instead of using a fixed URI. This approach is called **Discovery First Lookup**.

In Config Data mode, an example configuration:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
~~~

The application needs a compatible discovery implementation, such as Eureka or Consul, along with configuration to locate the registry. Config Server must register with the discovery service under the service ID used by the client.

In return, the client incurs an extra network round trip on startup to resolve the Config Server address. The benefit is that Config Server coordinates can change without clients needing to keep a fixed URI, provided the discovery service remains a stable access point.

Discovery First Lookup does not work automatically just by declaring `spring.cloud.config.discovery.enabled=true`. You must verify:

- The discovery provider dependency is on the runtime classpath.
- An appropriate `DiscoveryClient` bean has been created.
- The registry endpoint and credentials are accurate.
- Config Server has registered under the matching service ID.
- Networking and timeouts for the lookup step work properly.
- Config Data import or bootstrap mode is configured accordingly.

If using legacy bootstrap, properties needed to locate the discovery service must be ready in the bootstrap phase. If using Config Data, ensure configuration is available early enough for the Config Data loader to locate Config Server; exact organization depends on the integration and version.

## 11. Bootstrap and refresh are two separate phases

Bootstrap handles **preparing configuration before the main application initializes**. Refresh handles **updating configuration after the application is already running**.

| Topic | Bootstrap | Refresh |
| --- | --- | --- |
| Timing | Before the main context initializes (legacy) | After the application is already running |
| Goal | Load configuration sources required for startup | Update Environment and relevant beans |
| Mechanism | Bootstrap context / Config Data import | Environment change event, refresh scope, actuator/bus depending on config |
| Related file | `bootstrap.yml` in legacy or `application.yml` in Config Data | Does not depend on whether the file is named bootstrap or application |
| Auto-polls Config Server? | Not by default | Config Client does not auto-poll by default |
| Impact on beans | Configuration is present before beans are created | Only beans with an appropriate rebind/refresh mechanism receive changes |

### 11.1. `@RefreshScope`

A bean that needs to be recreated after refresh can use `@RefreshScope`:

~~~java
@Component
@RefreshScope
public class CatalogBanner {
    @Value("${catalog.banner:Welcome}")
    private String banner;

    public String getBanner() {
        return banner;
    }
}
~~~

When the Environment changes and a refresh is properly triggered, the refresh scope proxy can recreate the target bean on the next access. Simply editing `bootstrap.yml` or `application.yml` on disk does not automatically update running beans.

### 11.2. Propagating changes across multiple instances

In a system with multiple replicas, calling refresh on one instance does not automatically update the remaining instances. You can use Spring Cloud Bus or a custom orchestration mechanism to broadcast events to instances, then observe each instance's refresh status.

Do not use the bootstrap context to solve runtime configuration synchronization. Choose refresh and broadcast mechanisms appropriate for the architecture.

## 12. Migrating from legacy bootstrap to Config Data

If an application currently has `bootstrap.yml`, do not delete the file immediately. First determine which mechanism is loading the file.

### 12.1. Inventory current state

Check:

- Is the `spring-cloud-starter-bootstrap` dependency present?
- Is `spring.cloud.bootstrap.enabled=true` set in system properties/environment variables?
- Is `spring-cloud-starter-config` present?
- Does `bootstrap.yml` contain the Config Server URI, application name, profiles, or other properties?
- Are there any `BootstrapConfiguration`, `PropertySourceLocator`, or custom initializers depending on the bootstrap context?
- Are there remote override settings or code relying on context hierarchy?
- Are there tests initializing the bootstrap context using the old mechanism?

### 12.2. Migrating basic Config Client settings

A legacy configuration:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal.example
      fail-fast: true
~~~

Can be migrated to Config Data:

~~~yaml
# application.yml
spring:
  application:
    name: orders-service
  config:
    import: configserver:https://config.internal.example
~~~

Omitting `optional:` indicates Config Server is required. If you want to allow startup when the server is temporarily unavailable, use `optional:configserver:...` and assess the risk of missing configuration.

Then:

1. Keep the Config Client starter.
2. Verify the profiles and application name sent to Config Server.
3. Verify the values received in `Environment`.
4. Test precedence order between remote and local property sources.
5. Check whether custom bootstrap code can be replaced by Config Data or another mechanism.
6. Only remove the bootstrap starter and legacy file when no remaining components depend on them.

### 12.3. Differences that can break migration

| Difference | Risk | How to handle |
| --- | --- | --- |
| Remote property source precedence | Local/remote values may win differently than before | Compare `env` and actual effective values |
| Custom bootstrap `PropertySourceLocator` | Integration may not run in Config Data mode | Evaluate a Config Data extension or corresponding import mechanism |
| Profiles activated from remote config | Fetch count and loading timing may differ | Inspect Config Data logs and per-profile requests |
| `spring.application.name` | Config Server returns the wrong configuration set if the name differs | Verify the `{application}/{profile}/{label}` endpoint |
| Fail-fast / optional | Startup policy changes | Test when Config Server is disconnected |
| Discovery First Lookup | Registry not ready at import time | Check dependencies and registry readiness order |
| Bootstrap context hierarchy | Legacy beans/initializers may depend on the parent context | Write integration tests for the actual context |

## 13. Testing and diagnostics

### 13.1. Checking which files are actually loaded

In a local environment, you can enable debug mode when running:

~~~bash
java -jar orders-service.jar --debug
~~~

Combine with Config Data logs to inspect:

- File locations considered.
- Whether `bootstrap.yml` was loaded.
- Which profiles are active.
- Whether Config Server was called.
- Whether the import is optional or required.
- Which property sources were added to the Environment.

`--debug` mainly helps view the condition evaluation report; to diagnose Config Data, also watch logs related to config loading. Do not leave overly verbose debug logging enabled in production if there is a risk of logging sensitive information.

### 13.2. Checking with Actuator

Useful endpoints:

| Endpoint | What to inspect |
| --- | --- |
| `/actuator/env` | Property sources, active profiles, and resolved values |
| `/actuator/conditions` | Which auto-configurations matched or did not match |
| `/actuator/beans` | Which beans were registered in the context |
| `/actuator/health` | Status of health contributors and Config Client if enabled |

Expose only necessary endpoints and protect them with authentication/authorization and network policies. Do not open `/env`, `/beans`, or `/conditions` publicly for debugging convenience.

### 13.3. Required test scenarios

| Scenario | Setup | Expected outcome |
| --- | --- | --- |
| Config Server available | Server returns configuration matching application/profile | Environment contains remote properties |
| Config Server unavailable, optional import | Use `optional:configserver:` | Startup can continue with remaining configuration |
| Config Server unavailable, required import | Omit `optional:` | Startup fails cleanly |
| Legacy bootstrap not enabled | `bootstrap.yml` exists without bootstrap starter/property | Do not assume the bootstrap file is loaded |
| Legacy bootstrap enabled | Config Client and bootstrap starter present | Bootstrap context is created and Config Client uses bootstrap properties |
| Different profiles | `dev`, `prod` | Client receives configuration matching the profile |
| Remote and local share the same key | Declare overrides in both sources | Final value obeys the rules of the active model |
| Post-startup refresh | Update remote config and trigger refresh event | Eligible beans receive new values; other beans may retain old values |

### 13.4. Checking bootstrap mode in the dependency tree

When an application exhibits unexpected bootstrap behavior, check the dependency tree for `spring-cloud-starter-bootstrap`. Then locate where `spring.cloud.bootstrap.enabled` is set in system properties, environment variables, or deployment scripts.

Do not inspect only `application.yml`: the bootstrap activation property must be present early enough. A key placed in a file that is only read after the bootstrap context would have been created cannot activate that process itself.

## 14. Common mistakes

| Symptom | Possible cause | Investigation approach |
| --- | --- | --- |
| `bootstrap.yml` has no effect | Legacy bootstrap is not enabled | Check bootstrap starter or system/environment property |
| Config Client present, but does not call Config Server | Neither `spring.config.import` nor legacy bootstrap is enabled | Identify which integration model is in use |
| `spring-cloud-starter-bootstrap` present, but remote config is missing | Missing Config Client, wrong URI, profile, or connectivity | Check dependencies, bootstrap properties, and startup logs |
| `spring.cloud.bootstrap.enabled=true` placed in `application.yml`, but bootstrap doesn't run | Property is read too late | Move to a system property or environment variable |
| Remote config overridden locally or vice versa | Property source precedence/override difference | Inspect `Environment` and server configuration |
| Startup calls Config Server multiple times | Config Data fetches default profile then active profiles | Cross-check profile logs; do not assume it is a retry |
| Refresh does not update beans | Only edited file or didn't emit refresh event | Check Environment update, scope, and broadcast mechanism |
| Discovery First Lookup cannot find Config Server | Missing registry provider or registration | Check `DiscoveryClient`, service ID, and registry |
| Migration changes configuration values | Two loading mechanisms have different ordering | Compare property sources and write tests for critical keys |

## 15. Practice exercises

**Exercise 1 — Distinguishing file and context.** Explain why a `bootstrap.yml` file in `src/main/resources` is not read when an application runs using Config Data import. State the conditions required to enable legacy bootstrap.

**Exercise 2 — Configuring Config Server both ways.** Write a configuration using `spring.config.import` in `application.yml`, then write the equivalent configuration using legacy bootstrap with `bootstrap.yml`. List the required dependencies for each approach.

**Exercise 3 — Precedence order.** Config Server returns `clients.inventory.read-timeout=900ms`, while `application.yml` sets `700ms`. Check the final value under both models and explain why you should not assume the same outcome.

**Exercise 4 — Optional and fail-fast.** Try starting the application while Config Server is stopped. Compare `optional:configserver:` with `configserver:` and explain which model fits when database configuration is mandatory.

**Exercise 5 — Discovery First Lookup.** Register Config Server with Eureka or Consul. Configure the client to look up service ID `configserver`; observe the number of network calls at startup and handle the case where the registry is not yet ready.

**Exercise 6 — Migration.** An application currently uses `spring-cloud-starter-bootstrap`, `bootstrap.yml`, and a custom `PropertySourceLocator`. Plan the migration to Config Data, indicating which parts can be replaced with `spring.config.import` and which parts require redesign.

## 16. Key takeaways and references

- `application.yml` is Spring Boot's standard configuration file, loaded via Config Data.
- `bootstrap.yml` belongs to the legacy bootstrap context convention and **is not automatically loaded in every application**.
- The bootstrap context is a parent `ApplicationContext` in the legacy model; it is not Config Server or a standalone service.
- For modern Config Client, `spring.config.import` is the default approach; `bootstrap.yml` is not needed.
- To use legacy bootstrap, enable it with `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true` supplied early enough via system property/environment variable.
- The local bootstrap file and remote property sources are two distinct sources and can have different precedence levels.
- Bootstrap handles configuration before startup; refresh handles updating configuration while the application is running.
- When migrating, check dependencies, profiles, property source precedence, custom bootstrap code, and behavior when Config Server is unavailable.

Official sources to cross-check against your project's Spring Boot/Spring Cloud versions:

1. [Spring Cloud Config Client – Spring Boot Config Data Import and Config First Bootstrap](https://docs.spring.io/spring-cloud-config/reference/client.html)
2. [Spring Cloud Context – The Bootstrap Application Context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
3. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
4. [Spring Cloud Config – Client Quickstart](https://docs.spring.io/spring-cloud-config/reference/quickstart.html)
5. [Spring Cloud – release trains and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
