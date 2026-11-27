# Identifying Duplicate Loading Caused by Enabling Both Bootstrap and Config Data

> **Chapter:** Bootstrap  
> **Module:** SPRING_CLOUD_CORE

When a Spring Boot application uses Spring Cloud Config, remote configuration can be loaded through two mechanisms: the **legacy bootstrap context** and Spring Boot's **Config Data API**. Each mechanism has its own lifecycle and integration path. If a project accidentally enables both, Config Client may query Config Server through two separate paths, causing multiple fetches of the same configuration set, duplicate property sources, or unpredictable override ordering.

This is a common issue when upgrading older Spring Cloud applications. A project might still retain the `spring-cloud-starter-bootstrap` dependency or the `spring.cloud.bootstrap.enabled` flag, while also adding `spring.config.import=configserver:` following the modern configuration style. To resolve this properly, you must recognize both mechanisms, determine which paths are active, and choose one loading approach suited to your Spring Boot/Spring Cloud versions.

## 1. Two remote configuration loading mechanisms

### 1.1. Legacy bootstrap context

In the traditional bootstrap mechanism, Spring Cloud creates a **bootstrap context** before the application's main ApplicationContext. This context is responsible for initializing certain shared components and configuration sources early, such as Spring Cloud Config Client's `PropertySourceLocator`.

Configuration is typically placed in `bootstrap.yml` or `bootstrap.properties`. Example:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://config-server:8888
      name: order-service
      profile: production
~~~

When bootstrap is enabled and Config Client is configured in legacy mode, the bootstrap context can call Config Server to fetch property sources before the main application context finishes initialization.

The legacy mechanism is typically enabled via the `spring-cloud-starter-bootstrap` dependency or the `spring.cloud.bootstrap.enabled=true` flag supplied early enough, for instance via a system property or environment variable on supported versions. Simply creating a `bootstrap.yml` file does not guarantee it is loaded in modern configurations/versions; bootstrap must actually be activated.

### 1.2. Config Data API

Since Spring Boot 2.4, Spring Boot has provided the Config Data mechanism to load configuration early through a unified workflow. Spring Cloud Config Client integrates with this mechanism via `spring.config.import`.

Example:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

With a compatible Config Client dependency, Spring Boot recognizes the `configserver:` location and delegates to Config Client to load configuration from Config Server during Config Data processing.

If Config Server is a mandatory source for the application to function properly, omit the `optional:` prefix:

~~~yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
~~~

When the location omits `optional:`, failing to load a required configuration source can fail application startup. `optional:` only adjusts handling when the source is unreachable; it does **not** disable legacy bootstrap and does not prevent Config Client from being invoked through another loading path.

### 1.3. Comparing the two mechanisms

| Criterion | Legacy bootstrap | Config Data |
| --- | --- | --- |
| Initialization point | Spring Cloud's bootstrap context | Spring Boot's Config Data processing |
| Typical config files | `bootstrap.yml`, `bootstrap.properties` | `application.yml` with `spring.config.import` |
| How it is enabled | `spring-cloud-starter-bootstrap` or early bootstrap flag | `spring.config.import=configserver:` |
| Remote config loading integration | `PropertySourceLocator` in the bootstrap flow | Config Client's Config Data resolver/loader |
| Goal | Compatibility with earlier Spring Cloud configuration models | Integrating external sources into Boot's modern config loading mechanism |
| Separate context | Has a bootstrap context preceding the application context | Does not need a legacy bootstrap context solely to load Config Data |
| Guidance for new development | Use only for specific compatibility reasons | Usually the preferred option with Boot 2.4+ and supporting Cloud trains |

Both mechanisms can load configuration from the same Config Server, but they should not be enabled simultaneously for the same purpose without a deliberate design.

## 2. How does duplicate loading happen?

Suppose a legacy application has:

- The `spring-cloud-starter-bootstrap` dependency.
- `bootstrap.yml` configuring Config Server.
- `spring.cloud.bootstrap.enabled=true` passed from the runtime environment.

Later the project is upgraded and adds to `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

If both legacy bootstrap and Config Data are active, two flows can simultaneously request remote configuration:

~~~mermaid
flowchart TB
    A["Start order-service"]
    A --> B["Legacy bootstrap is enabled"]
    A --> C["Spring Boot Config Data processes import"]
    B --> D["Bootstrap context"]
    D --> E["Config Client: PropertySourceLocator"]
    C --> F["Config Client: Config Data resolver/loader"]
    E --> G["Request Config Server"]
    F --> H["Request Config Server"]
    G --> I["Remote property sources"]
    H --> I
    I --> J["Environment and configuration sources"]
~~~

The diagram illustrates two **independent initialization paths**. Depending on the version, dependencies, configuration, and specific integrations, they can produce multiple requests for the same application/profile/label. As a result, the same set of remote properties can be introduced into the environment via different property sources.

### 2.1. What can be duplicated?

Common symptoms:

- Config Server logs closely spaced requests from the same client instance for the same application/profile/label.
- Application logs show the bootstrap context initializing while Config Data simultaneously processes `configserver:`.
- Environment contains multiple property sources related to remote configuration or bootstrap sources.
- Startup duration increases because the application makes extra network calls.
- A key appears in multiple property sources, with the final value depending on precedence order.
- If configuration on Config Server changes between the two reads, the two loading paths may observe different states.

Exact property source names, log formats, and request counts can vary across Spring Boot/Spring Cloud versions. Therefore, do not rely on a single property source name alone to reach a conclusion.

### 2.2. Duplicate loading does not automatically mean application beans are created twice

Distinguish **property source loading** from **bean registration**. Config Client fetching the same data twice does not automatically prove every business bean is initialized twice. The bootstrap context is a separate context for early initialization; Config Data is a configuration loading workflow. The direct effect typically observed is remote property sources being fetched or added to the environment through multiple paths, while which beans get created depends on context structure and application configuration.

When investigating, record clearly which phenomenon you are observing:

1. Two HTTP requests to Config Server.
2. Two property sources containing the same key.
3. Final property value differing from expectations.
4. Beans or auto-configurations actually being created redundantly.

Do not merge these four phenomena into a single conclusion without evidence.

## 3. Signs to look for in a project

### 3.1. Checking the bootstrap dependency

Look for the `spring-cloud-starter-bootstrap` dependency in direct declarations or transitive dependencies. If the project uses Maven, inspect the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-bootstrap
~~~

With Gradle, inspect the runtime classpath:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-bootstrap \
  --configuration runtimeClasspath
~~~

If the dependency appears transitively, identify which library pulls it in. Do not blindly exclude a transitive dependency; first check whether another integration still requires legacy bootstrap.

### 3.2. Checking the bootstrap activation flag

Search sources that could supply:

- `spring.cloud.bootstrap.enabled=true`
- `SPRING_CLOUD_BOOTSTRAP_ENABLED=true`
- `-Dspring.cloud.bootstrap.enabled=true`

Check deployment manifests, environment variables, JVM arguments, launch scripts, and IDE configurations. This flag must be supplied early enough for the bootstrap process; declaring it late in a source loaded only after bootstrap may not take effect as expected.

### 3.3. Checking Config Data import

Search for declarations:

~~~yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
~~~

`spring.config.import` can reside in `application.yml`, an external configuration file, or another early-loaded source. Check active profiles and loaded files so you do not miss an import that appears only in one environment.

### 3.4. Checking bootstrap config and application config

An easy-to-spot sign is the same application having both Config Server settings in `bootstrap.yml` and `spring.config.import=configserver:` in `application.yml`.

Confusing configuration example:

`bootstrap.yml`:

~~~yaml
spring:
  cloud:
    config:
      uri: http://config-server:8888
~~~

`application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

If legacy bootstrap is activated, both blocks can participate in two loading mechanisms. Identify which mechanism is intentional and remove the redundant configuration after migrating.

## 4. Diagnosing with logs and property sources

Do not conclude duplicate loading merely because you see two log lines containing `config`. A single startup can legitimately query multiple profiles, labels, or application names. Cross-check the **timestamp, client instance, application, profile, label, and endpoint** of each request.

### 4.1. Increasing log levels selectively

You can temporarily enable detailed logging in a development environment:

~~~yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
    org.springframework.cloud.config.client: DEBUG
    org.springframework.cloud.bootstrap: DEBUG
~~~

These loggers help observe Config Data, Config Client, and bootstrap across many versions. Logger names or detail levels may vary by release; if a logger produces no useful output, check the package loggers for the version running.

Do not keep TRACE/DEBUG enabled for long in production because logs can grow large and occasionally include sensitive details in configuration metadata. Never enable payload logging containing secrets.

### 4.2. Cross-checking Config Server logs

If you have access to server logs, group requests by:

- Timestamp and interval between requests.
- Application name, such as `order-service`.
- Profile, such as `production`.
- Requested label/branch.
- Source address or client instance identifier.
- Response status and processing duration.

For example, one request for `order-service/production` and another for `order-service/production,observability` are not necessarily duplicate loading; they may represent different profile sets. Likewise, retries on network errors or Config Server failover also generate legitimate additional requests.

Suspect duplicate loading more strongly when the same client during the same startup sends two equivalent requests across both the bootstrap phase and Config Data phase with no profile, label, retry, or refresh reason.

### 4.3. Inspecting Environment and Actuator

If the application has Spring Boot Actuator and endpoints are securely configured, the `env` endpoint shows which property source supplies a key. The `configprops` endpoint shows how configuration bound into `@ConfigurationProperties`.

When checking:

- Compare property source names and origins if the version provides them.
- See if the same key appears in multiple sources.
- Identify which value actually bound into beans.
- Expose endpoints only within the needed administrative scope; enable sanitization and protect with authentication/authorization.
- Never share or store secret values when sharing logs or reports.

Duplicate property source names or shared keys do not by themselves prove two calls to Config Server; cross-reference with request logs and how sources were created.

## 5. Choosing one loading mechanism as the primary path

For modern applications using Spring Boot 2.4+ and a compatible Spring Cloud release train, **Config Data is usually the recommended path**. Legacy bootstrap should only be retained when an application has compatibility requirements or a specific integration that depends on the bootstrap context.

### 5.1. Option A: use Config Data

Keep the compatible Config Client dependency and configure the import in `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

If Config Server is mandatory, omit `optional:` so connection failures are caught immediately at startup.

When moving to this option, review and remove legacy artifacts that are no longer needed:

- Remove `spring-cloud-starter-bootstrap` if no integration still requires the bootstrap context.
- Remove `spring.cloud.bootstrap.enabled=true` from environment variables/JVM arguments.
- Remove duplicate Config Server configuration in `bootstrap.yml` if that file only served the legacy loading path.
- Keep appropriate application and profile properties in `application.yml` or other Config Data sources.
- Re-verify the Config Client version via the Spring Cloud BOM compatible with Spring Boot.

Do not delete `bootstrap.yml` solely based on its filename if it still holds configuration for another legacy integration. Check the owner and purpose of every property before cleaning up.

### 5.2. Option B: keep legacy bootstrap intentionally

If a project must use an integration that only supports legacy bootstrap in the current version, you can keep the bootstrap context:

- Use `spring-cloud-starter-bootstrap` or the bootstrap activation method supported by the version.
- Place required bootstrap configuration in `bootstrap.yml`/`bootstrap.properties`.
- Keep Config Client using the legacy mechanism the project relies on.
- Remove `spring.config.import=configserver:` if that import is re-calling the same Config Server for the same purpose.
- Document why legacy is retained and a plan to migrate once the integration supports Config Data.

Do not enable both `spring-cloud-starter-bootstrap` and `spring.config.import=configserver:` just to "make sure" configuration is loaded. That can cause the same remote source to be called across two flows.

### 5.3. Decision table

| Situation | Appropriate choice |
| --- | --- |
| New application, Spring Boot 2.4+ and Cloud train supporting Config Data | Prefer `spring.config.import=configserver:` |
| Application already uses Config Data, no legacy integrations remain | Remove legacy bootstrap starter/flag |
| Legacy integration strictly requires bootstrap context | Keep legacy, avoid importing Config Server a second time |
| Both bootstrap and Config Data present from an incomplete migration | Pick one primary path, remove redundant config after verification |
| Unclear which dependency activates bootstrap | Inspect dependency tree and startup logs before making changes |

## 6. Process for migrating from legacy bootstrap to Config Data

Perform the migration step by step so results are easy to compare:

1. **Record the current state:** Spring Boot version, Spring Cloud release train, Config Client dependency, bootstrap dependency, and active configuration sources.
2. **Identify the purpose of bootstrap:** inspect `bootstrap.yml`, `spring.cloud.bootstrap.enabled`, and integrations using `PropertySourceLocator`.
3. **Choose the target loading path:** for standard Config Server on a supported platform, choose Config Data; if an integration strictly requires legacy, document the reason for keeping bootstrap.
4. **Move configuration:** place `spring.config.import=configserver:` into configuration loaded at the right time; verify application name, profiles, label, and URI.
5. **Remove the duplicate path:** remove the bootstrap starter/flag or Config Data import according to your choice, ensuring both paths do not query the same Config Server.
6. **Test in local/test:** verify the application retrieves expected properties with no redundant requests.
7. **Test profiles:** confirm remote config matches the environment's `application/profile/label`.
8. **Controlled rollout:** check startup time, logs, property sources, and bean values after startup.
9. **Clean up legacy config:** remove unused files and dependencies only after confirming no other integration depends on them.

Do not change multiple factors simultaneously—such as Boot version, Cloud version, Config Server, and bootstrap mechanism—without corresponding tests. During major upgrades, separate dependency changes and loading mechanism changes into comparable steps.

## 7. Things that may look like duplicate loading but are normal

An application can send multiple requests to Config Server without having both bootstrap and Config Data enabled:

- Multiple profiles are active and Config Client needs to fetch corresponding configuration parts.
- The application requests multiple labels or uses branch-based configuration.
- Config Client retries on connection errors or uses multiple addresses/failover.
- A refresh event requests updated configuration after the application has already started.
- Multiple application instances start concurrently; each instance makes its own requests.
- Another integration also queries a remote configuration source.
- A test suite creates multiple ApplicationContexts.

Therefore, total request count alone is insufficient to diagnose an error. Group requests by instance and startup attempt, compare application/profile/label, and correlate with bootstrap and Config Data logs.

### 7.1. Classification examples

| Observation | Initial assessment |
| --- | --- |
| One instance sends two requests with the same application/profile/label: one in bootstrap phase, one in Config Data phase | Suspect both mechanisms running simultaneously |
| One instance sends requests for `production` and `production,observability` | Likely different profile/config sets |
| Two different pods both fetch `order-service/production` | Likely normal startup of each instance |
| One initial request and one request after a refresh event | Likely expected refresh behavior |
| Multiple requests after connection errors, with backoff | Likely retries |
| Same key appears in two property sources | Check source origins and ordering; insufficient alone to conclude duplicate requests |

## 8. Post-fix verification testing

After choosing one mechanism, test both the loading process and the final outcome.

### 8.1. Verifying actual configuration

Example expected configuration:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Config Server returns `catalog.client.base-url` for profile `local`. A test can verify the bean receives the right value:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("local")
class RemoteConfigurationTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsRemoteCatalogConfiguration() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:8090");
    }
}
~~~

This test requires a Config Server environment or corresponding test configuration. If you want pure unit-style tests independent of a server, you can use property overrides or mock property sources; however, those tests do not prove Config Server connectivity works.

### 8.2. Checklist to confirm two loading paths are no longer active

- [ ] Clearly identified whether the application uses Config Data or legacy bootstrap.
- [ ] No unintended bootstrap dependency/flag remains.
- [ ] No duplicate Config Data import targeting Config Server remains if keeping legacy.
- [ ] Startup logs show a single expected flow fetching remote config.
- [ ] Server requests are correlated by instance, application, profile, and label.
- [ ] Final values in Environment/beans match the environment.
- [ ] Profile-specific configuration still works.
- [ ] Behavior when Config Server is unreachable matches `optional:` or required.
- [ ] Boot/Cloud dependencies are compatible under the release train in use.

## 9. Common mistakes and how to avoid them

1. **Keeping `spring-cloud-starter-bootstrap` after moving to Config Data:** check whether the starter is still needed; if not, remove it to avoid initializing legacy bootstrap.
2. **Setting `spring.config.import=configserver:` while keeping Config Client bootstrap enabled:** two flows can query remote config simultaneously.
3. **Assuming `optional:` disables Config Server:** `optional:` only changes behavior when a source is unreachable; it does not disable another loading path.
4. **Deleting all of `bootstrap.yml` without checking:** the file may still contain legacy configuration for another integration.
5. **Concluding duplicate loading from request count alone:** rule out multiple profiles, retries, labels, refreshes, and multiple instances.
6. **Assuming duplicate property sources mean duplicate beans:** inspect context/bean registration separately if you suspect a bean lifecycle issue.
7. **Switching mechanisms without checking compatibility:** use a Spring Cloud BOM/release train supported for your Spring Boot version.
8. **Failing to test profiles during migration:** Config Server returns configuration by application/profile/label; a wrong profile can cause the application to receive a different value set.
9. **Leaving TRACE logging enabled long-term in production:** use controlled diagnostics only to avoid leaking sensitive details and inflating log volume.

## 10. Conclusion

Legacy bootstrap and Config Data are both ways to bring remote configuration into an application, yet they participate in two different initialization phases. If an application both enables the bootstrap context and declares `spring.config.import=configserver:` for the same Config Server, there is a risk of loading remote config through two paths, causing redundant requests or duplicate property sources.

To diagnose accurately, inspect dependencies, bootstrap flags, `bootstrap.yml`, Config Data imports, and logs on both the client and Config Server, while cross-checking application/profile/label. For new applications on supported versions, prefer Config Data; keep legacy bootstrap only when there is a specific compatibility requirement. **The goal is a clear, observable, and testable remote configuration loading path**, while ensuring profiles, precedence order, and failure behavior when Config Server errors continue to meet operational requirements.
