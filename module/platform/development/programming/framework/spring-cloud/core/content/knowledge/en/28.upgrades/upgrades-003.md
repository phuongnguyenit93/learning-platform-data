# Migrating Legacy Bootstrap to Config Data When Appropriate

> **Chapter:** Upgrades  
> **Module:** SPRING_CLOUD_CORE

In older Spring Cloud applications, `bootstrap.yml` was commonly used to load configuration needed before the main `ApplicationContext` initialized, especially the address of the Spring Cloud Config Server. The bootstrap mechanism creates a parent context, loads remote property sources, and then transfers those property sources to the application context. While this approach can still be needed for some systems for backward compatibility, starting with Spring Cloud 2020.0, bootstrap is no longer enabled by default.

Spring Boot 2.4 introduced the **Config Data API** with the `spring.config.import` property. Spring Cloud Config Client now uses this mechanism as the default way to connect to Config Server. Instead of needing a separate bootstrap context, the application declares the configuration sources to import in `application.yml` or `application.properties`. Spring Boot orchestrates configuration loading, profiles, and property source ordering within the same Config Data pipeline.

This lesson guides a controlled migration in the **SPRING_CLOUD_CORE** module: determining when to use Config Data, mapping legacy configuration to the new configuration, handling optional/fail-fast/retry, discovery-first lookup, profiles, custom configuration sources, testing, and rollback planning. The goal is to simplify the startup lifecycle while preserving the configuration behavior the application needs.

## 1. What Problem Did Legacy Bootstrap Solve?

Before Config Data, Spring Cloud used a bootstrap phase to load properties required before the main application context started. The mechanism was typically activated by `spring-cloud-starter-bootstrap` or the property `spring.cloud.bootstrap.enabled=true`.

An application using Spring Cloud Config in the legacy style might look like:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: https://config.internal:8888
      name: order-service
      label: main
      fail-fast: true
~~~

Username and password are provided via environment variables `SPRING_CLOUD_CONFIG_USERNAME` and `SPRING_CLOUD_CONFIG_PASSWORD`, rather than storing them directly in the file.

The bootstrap context reads these properties to connect to Config Server and add remote property sources to the application's `Environment`. Other modules could also use bootstrap to register custom `PropertySourceLocator` or `ApplicationContextInitializer` beans.

### 1.1. Bootstrap Lifecycle

~~~mermaid
flowchart TB
    A["Start SpringApplication"]
    A --> B["Create bootstrap context"]
    B --> C["Read bootstrap.yml / bootstrap.properties"]
    C --> D["Connect to Config Server or custom source"]
    D --> E["Create remote PropertySource"]
    E --> F["Create main ApplicationContext"]
    F --> G["Inherit property sources from bootstrap"]
    G --> H["Create application beans"]
~~~

This approach is useful when a separate configuration phase is needed before the main context. However, it introduces an extra context and separate precedence rules that must be understood when troubleshooting. For applications that only need to import external configuration from Config Server, Config Data is usually the simpler choice.

### 1.2. Why Migrate?

Starting with Spring Cloud 2020.0, bootstrap is no longer enabled by default. If you need to retain legacy behavior, you can add `spring-cloud-starter-bootstrap` or set `spring.cloud.bootstrap.enabled=true` via an environment variable, JVM system property, or command-line argument before the application starts. Around the same time, Spring Cloud added Config Data integrations for Config Server, Consul, Zookeeper, and Vault.

Config Data provides several benefits:

- Uses Spring Boot's unified configuration loading mechanism.
- Declares imported configuration sources explicitly inside application configuration.
- Integrates naturally with profiles and other Config Data sources.
- Eliminates the need for a bootstrap context just to fetch remote property sources.
- Supports optional or required import syntax to express startup policy.

Migrating does not mean removing every trace of bootstrap across all systems. First, you must check the versions and extension points the application is using.

## 2. When to Use Config Data vs. Keeping Bootstrap

`spring.config.import` fits when the application uses integrations that support Config Data and does not depend on behaviors specific to the bootstrap context.

| Situation | Recommended approach |
| --- | --- |
| Spring Boot 2.4+ and compatible Spring Cloud Config Client | Prefer Config Data import |
| Using Config Server with standard configuration, no custom bootstrap | Migrate to `spring.config.import` |
| Using Consul, Zookeeper, or Vault with Config Data integration in the active release | Use the import scheme provided by the integration |
| Spring Boot older than 2.4 | Keep the mechanism supported by that version or upgrade Boot first |
| Spring Cloud release train lacks the required Config Data integration | Keep bootstrap temporarily or upgrade the release train |
| Custom `BootstrapConfiguration`, `PropertySourceLocator`, or initializer depending on bootstrap lifecycle | Evaluate and migrate each extension point; keep bootstrap until replaced |
| Third-party library requires the bootstrap context | Check library documentation and test before removing the bootstrap starter |
| Application requires a context hierarchy or property sources created specifically during bootstrap | Keep the legacy mechanism if no equivalent design exists |

### 2.1. Version Prerequisites

Spring Boot 2.4 introduced the Config Data API. Spring Cloud 2020.0 added import syntax for Config Server, Consul, Zookeeper, and Vault; starting from this release train, bootstrap is no longer enabled automatically by default.

During an actual upgrade:

1. Identify the running Spring Boot version.
2. Identify the Spring Cloud release train compatible with that Boot version.
3. Use the Spring Cloud BOM to manage module versions within the same train.
4. Check whether the Config Client/provider in use supports the required import scheme.
5. Run the application with the target dependency graph before changing configuration files.

Do not pick the latest Config Client version on its own and pair it arbitrarily with Spring Boot. Compatibility depends on the release train and BOM. Use the Spring Cloud compatibility verifier alongside the official compatibility matrix to detect unsupported combinations.

### 2.2. When to Keep Bootstrap During a Transition Period

You can retain `spring-cloud-starter-bootstrap` when the application still relies on an extension point loaded in the bootstrap context, or when an integration library does not yet support Config Data. In that case, document the reason for keeping bootstrap and the scope of dependencies so it can be removed later.

Do not enable both legacy bootstrap and Config Data import mechanically. If the same remote source is loaded through both mechanisms, the application may send duplicate requests, end up with multiple similar property sources, and produce hard-to-predict winning values. Run both in parallel only when you have clearly determined they serve two distinct purposes and have tested precedence.

## 3. Configuring Config Data for Spring Cloud Config

With Config Data, place `spring.config.import` in `application.yml` or `application.properties`. Example using Config Server at the default address:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:
~~~

Config Client connects to `http://localhost:8888` by default if no other address is configured.

If Config Server is at a specific address:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:https://config.internal:8888
~~~

You can use `spring.cloud.config.uri` to set a separate URI, but if the URI is specified directly inside `spring.config.import`, the URI in the import takes precedence over `spring.cloud.config.uri`.

Example using the URI property:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:
  cloud:
    config:
      uri: https://config.internal:8888
~~~

Username/password should come from a secret manager or protected environment variables. With Spring Boot relaxed binding, you can provide `SPRING_CLOUD_CONFIG_USERNAME` and `SPRING_CLOUD_CONFIG_PASSWORD` without writing credentials into configuration files.

Do not commit real credentials to the repository. If Config Server uses OAuth, mTLS, or a custom authentication mechanism, configure it according to the Config Client and deployment platform guidelines.

### 3.1. Optional vs. Required

The two import forms express two different startup policies:

~~~yaml
spring:
  config:
    import: optional:configserver:https://config.internal:8888
~~~

With the `optional:` prefix: the application can continue starting if Config Server is unavailable and the config source is marked optional. This is typically useful for local environments or applications with safe default configurations.

~~~yaml
spring:
  config:
    import: configserver:https://config.internal:8888
~~~

Without `optional:`: Config Server becomes a required configuration source. If the configuration source cannot be loaded, the application will not start successfully. This is the right choice when missing remote configuration could cause the application to behave incorrectly or unsafely.

Do not choose `optional:` just to avoid startup failures. If the remote source holds database endpoints, credentials, or critical feature flags, running with default values can cause hard-to-detect bugs. Conversely, if local development does not need Config Server, `optional:` can make the development workflow smoother.

### 3.2. Fail-Fast and Retry

With Config Data, omitting the `optional:` prefix expresses the fail-fast requirement when Config Server cannot be reached. If the server might be temporarily unavailable when the application starts, you can configure retry.

Config Client retry requires the appropriate Spring Retry and Spring AOP dependencies. Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Retry configuration example:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
~~~

These values are examples to illustrate retry policy. Choose retry counts and backoff based on your startup budget, SLA, and Config Server recovery characteristics. Retry will not fix authentication failures, wrong URIs, or invalid server configuration; those errors must be diagnosed rather than retried indefinitely.

If `spring.config.import` is declared in a profile-specific file such as `application-prod.yml`, the Config Client documentation instructs placing retry parameters on the import URL. Example:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&max-interval=5000&multiplier=1.5&initial-interval=1000"
~~~

Query parameters are mapped to the corresponding fail-fast/retry properties. When using this approach, properly encode the URL and verify that credentials are not leaked through process arguments or startup logs.

## 4. Mapping bootstrap.yml to application.yml

Do not just rename `bootstrap.yml` to `application.yml` and keep all contents untouched. Categorize each property by its role.

| Legacy property | How to handle with Config Data |
| --- | --- |
| `spring.application.name` | Place in application config or environment variable |
| `spring.cloud.config.uri` | Can remain in application config or put URI in import |
| `spring.cloud.config.name` | Keep if Config Server uses a different application name |
| `spring.cloud.config.profile` | Keep when needing a remote profile different from local profiles |
| `spring.cloud.config.label` | Keep to select the config repository branch/tag/commit |
| `spring.cloud.config.username/password` | Move to a secret manager or environment variables |
| `spring.cloud.config.fail-fast` | Use required import by removing `optional:`; review retry settings |
| `spring.cloud.bootstrap.enabled` | No need to enable when migrating completely to Config Data |
| `spring.cloud.config.discovery.enabled` | Can still be used if choosing discovery-first lookup and supported by provider |
| Custom `BootstrapConfiguration` | Must re-evaluate lifecycle and extension points; not migrated by renaming a file |

Example before migration:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: inventory-service
  cloud:
    config:
      uri: https://config.internal:8888
      name: inventory-service
      profile: production
      label: release-2026
      fail-fast: true
~~~

Username/password are supplied via environment variables `SPRING_CLOUD_CONFIG_USERNAME` and `SPRING_CLOUD_CONFIG_PASSWORD`.

After migration:

~~~yaml
# application.yml
spring:
  application:
    name: inventory-service
  config:
    import: configserver:https://config.internal:8888
  cloud:
    config:
      name: inventory-service
      profile: production
      label: release-2026
~~~

In this example, the import does not have `optional:`, so the application requires Config Server to be available at startup. The name/profile/label properties retain their purpose of selecting remote configuration. Check the application's actual active profile; do not hardcode the production profile in a shared file if deployments decide the profile via the environment.

### 4.1. Set spring.application.name Early Enough

Config Server uses the application name, profile, and label to look up configuration in the form:

~~~text
/{application}/{profile}/{label}
~~~

By default, the application name comes from `spring.application.name`, the profile comes from active profiles, and Config Server's default label is `master` unless the server configures another default label. When renaming files or moving properties, ensure `spring.application.name` is available before Config Data import needs it.

Do not place the application name only inside Config Server's own remote configuration if the client needs that name to look up remote configuration. Provide minimal bootstrap identity such as the application name from local config, environment variables, or command-line arguments.

### 4.2. Do Not Confuse spring.cloud.config.profile with Active Profiles

`spring.cloud.config.profile` specifies the profile that Config Client requests from Config Server. `spring.profiles.active` controls the active profile of the Spring Boot application. The two properties are related but not synonymous.

If you want Spring Boot to run the `production` profile:

~~~yaml
spring:
  profiles:
    active: production
~~~

Or pass it from the environment:

~~~bash
SPRING_PROFILES_ACTIVE=production
~~~

Do not place `spring.profiles.active` inside a document activated only by that same profile. Spring Boot only allows active/default profile properties in non-profile-specific documents.

## 5. Profiles and the Config Data Loading Flow

Spring Boot's Config Data can load configuration in multiple steps. With Config Server, the client first fetches configuration for the `default` profile to see whether remote configuration activates additional profiles. Afterward, the client fetches configuration for the active profiles.

Therefore, when using `spring.config.import`, you may see multiple requests to Config Server during startup. This is normal behavior of the two-step flow, not necessarily an error or unintended duplicate requests.

### 5.1. Profile Configuration Example

Local application config:

~~~yaml
spring:
  application:
    name: inventory-service
  config:
    import: optional:configserver:
  profiles:
    active: production
~~~

Config Server can return shared configuration and profile-specific configuration. The client proceeds to load the appropriate sources for activated profiles.

If a remote property source activates an additional profile, Config Data can issue a follow-up request to fetch configuration for that profile. This is an important difference compared to some legacy bootstrap behaviors that only performed a single query.

### 5.2. Where to Place the Import?

Usually, placing `spring.config.import` in the shared `application.yml` ensures every profile knows to import from Config Server.

If you put the import only in `application-prod.yml`, that file is loaded only when the `production` profile has already been activated from another source. This is a common mistake when authors expect Config Server to activate the profile itself, yet the import sits in a file loaded only after the profile is already active.

Only place the import in a profile-specific file when intentional—for instance, when local environments do not use Config Server while production does. Verify the active profile before testing connectivity.

### 5.3. Profile-Specific Config Data and Precedence

Spring Boot applies Config Data and property source precedence rules. Profile-specific files can override shared configuration depending on position and import order. When multiple sources exist, clearly identify which source takes priority and check the final resolved value instead of guessing from a single file.

You can use Actuator:

~~~text
GET /actuator/env/spring.application.name
GET /actuator/env/spring.profiles.active
GET /actuator/env/spring.cloud.config.uri
~~~

If you need to confirm a bean received the right configuration, inspect `/actuator/configprops`. Always secure these endpoints and do not expose secrets in production responses.

## 6. Discovery-First Lookup for Finding Config Server

By default, the client can connect directly to the Config Server URL. If your infrastructure uses Eureka or Consul and you want to locate Config Server via `DiscoveryClient`, you can enable discovery-first lookup:

~~~yaml
spring:
  config:
    import: optional:configserver:
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
~~~

In this case, the application must configure the discovery client early enough to locate Config Server. For Eureka, an example registry address:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

Discovery-first lookup adds a network round trip at startup to locate Config Server's service registration. The benefit is that Config Server's actual address can change without the client needing a fixed URL, as long as the Discovery Service remains a stable access point.

Do not enable discovery-first simply because the application already uses Eureka. If Config Server has a stable URL and looking it up via the registry adds no operational benefit, a direct URL is simpler.

If Config Server is protected by HTTP Basic or has a context path, the discovery provider may require corresponding metadata so the client knows the connection details. Do not put real passwords into public metadata; use secret mechanisms and secure the registry properly.

## 7. Config Data for Sources Outside Config Server

Spring Cloud release trains have added Config Data integration for several other external sources. For example, import schemes supported in Spring Cloud 2020.0 included:

| Source | Illustrative import scheme |
| --- | --- |
| Spring Cloud Config Server | `configserver:` |
| Consul | `consul:` |
| Zookeeper | `zookeeper:` |
| Vault | `vault:` |

Exact syntax, required starters, and connection properties depend on the module/provider and release train. General example:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal:8888,optional:consul:"
~~~

Do not copy the import list above into an application without the corresponding dependencies and servers. Each integration has its own way of specifying addresses, prefixes, authentication, and profiles. Use the documentation for the exact module you are running.

Config Data allows combining multiple sources, but import order affects precedence. When two sources declare the same key, clearly determine which source takes priority and inspect the final value in `Environment`.

## 8. Retry and Multiple Config Server URLs

You can declare multiple locations in `spring.config.import`. Locations are processed in order; later imports can have higher precedence. Behavior when one URL fails also depends on fail-fast and the multiple-URI configuration of your Config Client version.

Example:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config-a.internal:8888,optional:configserver:https://config-b.internal:8888"
~~~

Do not treat a list of multiple URLs as automatic load balancing. Verify the fallback semantics of the version in use, especially when the server returns HTTP 401, 500, or a configuration error rather than a connection error.

### 8.1. Retry When the Import Is in a Profile-Specific File

If the import resides in `application-prod.yml`, Config Client documentation requires passing retry parameters on the import URL. Example:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&max-interval=5000&multiplier=1.5&initial-interval=1000"
~~~

Query parameters are mapped to the corresponding fail-fast/retry properties. When using this approach, properly encode the URL and verify that authentication details are not exposed through process arguments or startup logs.

## 9. Handling Custom Bootstrap Extensions

This is the area requiring the greatest care when upgrading a heavily customized system.

Legacy bootstrap allowed registering classes via `BootstrapConfiguration` in `spring.factories`. One common extension point is `PropertySourceLocator`, used to fetch property sources from a custom system. `ApplicationContextInitializer` beans could also be registered to influence the startup sequence.

### 9.1. Do Not Just Rename the File

If the application has a custom `PropertySourceLocator`, renaming `bootstrap.yml` to `application.yml` and adding `spring.config.import` does not automatically migrate that locator to Config Data. The locator depends on the lifecycle and context in which it is created.

Before migrating, determine:

- Does the locator need to run before profiles are determined?
- Does it depend on beans that exist only in the bootstrap context?
- Does it require special property source precedence?
- Is it registered via `spring.factories`?
- Does it use a context hierarchy or custom initializer?
- Is there an official Config Data integration that replaces it?

### 9.2. Choosing a Replacement Strategy

If a custom configuration source needs to participate directly in the Config Data pipeline, consider implementing Config Data extensions such as `ConfigDataLocationResolver` and `ConfigDataLoader` according to the Spring Boot API supported by your application. If the source already has an official integration, prefer that integration.

If it cannot yet be safely replaced, you can keep legacy bootstrap during the transition period. Document the module, extension point, and reason for retaining it; do not remove `spring-cloud-starter-bootstrap` until tests confirm the custom configuration source still works.

### 9.3. Checking Property Source Precedence

The legacy bootstrap context may create remote property sources with different precedence than Config Data import. After migration, the same property may receive its value from another source if import order or profile-specific files changed.

Create a table of critical properties before and after migration:

| Property | Old source | Old value | New source | New value |
| --- | --- | --- | --- | --- |
| `spring.datasource.url` | Config Server | Production URL | Config Server import | Must match |
| `catalog.client.timeout` | bootstrap remote source | 2s | Config Data remote source | Must match |
| `logging.level.root` | application.yml | INFO | application.yml | Must follow policy |
| `feature.catalog.enabled` | profile-specific source | true | profile-specific Config Data | Must match |

Do not compare YAML contents alone. Compare `Environment` after startup, because that is the result of all property sources, profiles, and overrides.

## 10. Step-by-Step Migration Process

A safe migration should proceed in small, rollback-friendly steps.

1. **Capture baseline:** record the Spring Boot version, Spring Cloud release train, dependency graph, active profiles, and current property sources.
2. **Inventory bootstrap:** list all keys in `bootstrap.yml`, related environment variables, and JVM arguments.
3. **Locate extension points:** search for `BootstrapConfiguration`, `PropertySourceLocator`, `ApplicationContextInitializer`, and the bootstrap starter in the dependency tree.
4. **Confirm support:** verify the Config Client/provider version has Config Data integration.
5. **Move minimal configuration:** move `spring.application.name`, Config Server location, name/profile/label, and authentication references to application config.
6. **Add import:** use `spring.config.import` with `optional:` or required according to startup policy.
7. **Migrate retry:** check Spring Retry/AOP dependencies and how retry is declared when importing inside a profile-specific file.
8. **Migrate discovery lookup:** enable only if Config Server is actually discovered via `DiscoveryClient`.
9. **Handle custom sources:** replace extension points or retain bootstrap if no equivalent exists yet.
10. **Run locally:** test both when Config Server is available and when the server is stopped.
11. **Compare Environment:** use `env` and `configprops` to confirm property sources and bean binding.
12. **Test profiles:** test default, dev, staging, production, and profiles activated from remote config.
13. **Deploy canary:** switch a single service or small group of instances first, monitoring startup errors and effective configuration.
14. **Remove bootstrap starter:** delete the legacy dependency and files only after all consumers use Config Data.
15. **Monitor post-migration:** check Config Server request counts, startup time, retries, authentication, and refresh behavior.

## 11. Post-Migration Testing

Do not just verify that the application starts. Verify critical configuration behaviors.

### 11.1. Test Matrix

| Case | Expected outcome to verify |
| --- | --- |
| Config Server available | Application loads the expected remote property sources |
| Config Server unavailable, optional import | Application starts using the designed fallback |
| Config Server unavailable, required import | Startup fails clearly |
| Invalid credentials | Authentication error is surfaced; not masked by unintended fallback |
| Default profile | Shared configuration is loaded |
| Production profile | Profile-specific configuration is loaded and overrides properly |
| Remote config activates profile | Client fetches additional configuration for the activated profile |
| Discovery-first Config Server | Client resolves the right service ID and URL/context path |
| Custom property source | Values and precedence do not shift unexpectedly |
| Retry | Retry count/backoff stays within startup budget |
| Config label changed | Correct branch/tag/commit is used |

### 11.2. Inspecting Values via Actuator

In a protected test environment, you can query:

~~~text
GET /actuator/env/spring.application.name
GET /actuator/env/spring.profiles.active
GET /actuator/env/spring.cloud.config.uri
~~~

`env` shows which property source supplies the effective value and its origin if available. `configprops` shows how `@ConfigurationProperties` beans bound those values. These two endpoints help detect cases where remote config loaded but beans did not receive the expected values.

Do not expose these endpoints publicly and do not enable showing secrets in production just to compare configuration.

### 11.3. Checking Startup Request Counts

Config Data can generate multiple Config Server requests because of the `default` profile load step and the active profile load step. This is normal behavior. When inspecting logs, do not immediately conclude there is a loop or retry storm just because multiple requests appear.

Distinguish between:

- Requests from profile discovery phases.
- Retries due to Config Server being temporarily unavailable.
- Multiple fallback URLs.
- Duplicate requests caused by enabling both legacy bootstrap and Config Data import simultaneously.

## 12. Common Mistakes and How to Avoid Them

1. **Merely renaming bootstrap.yml to application.yml:** you must switch to `spring.config.import` and verify the lifecycle.
2. **Forgetting to remove spring-cloud-starter-bootstrap:** legacy bootstrap may remain active even after adding Config Data.
3. **Using optional in production without a safe fallback:** the application may run with missing or wrong default configuration.
4. **Omitting optional in local environments that need to run standalone:** startup may fail when Config Server is not running.
5. **Putting import in application-prod.yml before the profile is active:** Config Data import will not be loaded at the right time.
6. **Confusing spring.cloud.config.profile with spring.profiles.active:** the two properties have different roles.
7. **Forgetting spring.application.name:** Config Server looks up the wrong application configuration.
8. **Assuming Config Data sends only one request:** the profile resolution flow can require multiple fetches.
9. **Keeping both bootstrap and Config Data for the same remote source:** increases complexity and makes precedence unpredictable.
10. **Failing to migrate a custom PropertySourceLocator:** custom configuration sources may disappear or run at a different lifecycle phase.
11. **Too many retries:** prolongs startup and can overload Config Server during an outage.
12. **Using multiple URLs without understanding fallback:** authentication or configuration errors are not necessarily treated the same as connection errors.
13. **Putting credentials in URLs/config files:** risks exposure via repositories, process lists, or logs.
14. **Upgrading Spring Boot without aligning the Spring Cloud BOM:** can cause compatibility verifier failures or runtime errors.
15. **Removing the bootstrap starter too early:** another integration may still require the bootstrap context.

## 13. Migration Completion Checklist

Before concluding the migration, verify:

- [ ] Spring Boot and the Spring Cloud release train are in the compatibility matrix.
- [ ] Config Client/provider has the required Config Data integration.
- [ ] `spring.config.import` is placed in a file loaded at the appropriate phase.
- [ ] Optional/required policy matches each environment.
- [ ] `spring.application.name`, profile, config name, and label are correct.
- [ ] Credentials come from a secure secret source.
- [ ] Retry and timeout fit within the startup budget.
- [ ] Discovery-first lookup is enabled only when truly needed.
- [ ] Custom bootstrap extensions have been replaced or have a documented reason to remain.
- [ ] Property precedence before and after has been compared.
- [ ] Profiles and remote profile activation have been tested.
- [ ] Config Server outages and authentication failures have been tested.
- [ ] Actuator `env`/`configprops` are secured.
- [ ] No remote source is unintentionally loaded twice.
- [ ] A rollback plan exists and has been tested on a canary.
- [ ] The bootstrap starter is removed only after all integrations are verified.

**Key takeaway:** Config Data with `spring.config.import` is the current standard way to load configuration from Config Server and supported Spring Cloud integrations. Migration must preserve optional/fail-fast policy, profiles, property precedence, and retries; custom bootstrap extensions must be evaluated separately. Remove legacy bootstrap only when the application no longer depends on the bootstrap lifecycle and tests confirm equivalent before/after configuration behavior in **SPRING_CLOUD_CORE**.

## References

- [Spring Cloud Config Client — Spring Boot Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration and Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud 2020.0 Release Notes — Bootstrap and Config Data Changes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2020.0-Release-Notes)
- [Spring Cloud Commons — Application Context Services and Bootstrap Property Sources](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
