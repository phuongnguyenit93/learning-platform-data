# Trade-offs Between Failing Fast and Using Fallback Configuration

> **Chapter:** Operations
> **Module:** `SPRING_CLOUD_CORE` — understand the core foundations of Spring Cloud in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, and version compatibility with Spring Boot. Learners explore refresh scope, discovery, service registry, service-to-service communication, and how to test and operate common abstractions.
> **Focus:** When an application fetches configuration from Spring Cloud Config Server, a connection error at startup poses a choice: stop the application to avoid running with missing configuration, or continue using fallback configuration. This lesson analyzes the criteria for choosing fail-fast versus optional imports, combining retries and multiple Config Servers, designing safe local fallbacks, and verifying configuration state before admitting traffic.

## 1. Why Choose Between Fail-Fast and Fallback?

Spring Cloud applications typically retrieve configuration from multiple sources: files packaged with the application, environment variables, launch arguments, Config Server, configuration trees, or secret stores. Externalized configuration allows behavior changes per environment without repackaging the application. In return, startup may depend on another network service.

Suppose a service requires the following values:

- downstream addresses and timeouts;
- topic or queue names;
- retry limits;
- feature flags;
- database connection configuration;
- credentials supplied from a secret store.

If Config Server is temporarily unreachable, the service has two options.

**Fail-fast:** if required configuration cannot be retrieved, do not start. This prevents an instance from running with missing, default, or wrong-environment values. It is appropriate when configuration is a prerequisite for safe operation.

**Fallback:** allow startup using local configuration or a backup source when Config Server is unavailable. This can maintain partial functionality during an outage, but is only safe if the fallback configuration set is sufficient and does not weaken security or business correctness.

Neither choice is universally best for every application. You must evaluate the impact of missing each configuration group, whether degraded-mode operation is viable, and how to verify the service is ready to receive traffic.

### Learning Outcomes

After this lesson, learners can:

1. distinguish fail-fast, optional import, retry, and fallback;
2. configure Config Client using `spring.config.import`;
3. classify required versus optional configuration by criticality;
4. design safe local default values and understand property source precedence;
5. combine fail-fast with retry/backoff;
6. use multiple Config Servers and understand backup server selection;
7. distinguish connection failures, timeouts, authentication errors, server errors, and empty configuration;
8. validate required configuration before a service admits traffic;
9. test Config Server outage scenarios;
10. build rollback and operations procedures when external configuration is unavailable.

## 2. Understanding the Terms Correctly

### 2.1. Fail-Fast

Fail-fast means the application aborts startup when required configuration cannot be fetched from Config Server. With the modern Config Data mechanism, the simplest approach is declaring the import without the `optional:` prefix.

```properties
spring.config.import=configserver:http://config.internal:8888
```

If Config Server cannot supply configuration, Config Client fails startup instead of skipping the source.

In the legacy bootstrap mechanism, `spring.cloud.config.fail-fast=true` instructed Config Client to throw an exception when unable to connect to Config Server. With Config Data import, omitting `optional:` is the equivalent approach recommended in current documentation.

### 2.2. Optional Import

An optional import allows the application to continue starting up if a configuration source marked optional fails to load:

```properties
spring.config.import=optional:configserver:http://config.internal:8888
```

When Config Server is unreachable, local configuration sources and other sources can still supply values. This mechanism merely permits skipping a failed import source; it does not automatically create a snapshot of the most recent configuration, nor does it guarantee all required properties are present.

### 2.3. Retry

Retry re-attempts a failed operation before concluding configuration cannot be retrieved. It handles transient failures such as Config Server still starting up, intermittent network glitches, or brief connection timeouts.

Retry does not replace fail-fast or fallback:

- fail-fast decides whether the application is permitted to start when configuration cannot be retrieved;
- retry decides whether to try again before reaching that conclusion;
- fallback decides which source is used when the preferred source is unavailable.

### 2.4. Fallback Configuration

A fallback is a backup configuration source that can be used when the primary source is unavailable or does not supply a needed value. For example, the application defines safe timeout values in a local file, and Config Server overrides them when connected successfully.

Fallback must be designed explicitly. A property absent from Config Server can be resolved from a lower-precedence source, but that does not mean the entire remote configuration loaded completely.

### 2.5. Last-Known-Good Configuration

Last-known-good is the most recent valid configuration that the application or platform persisted durably and can restore when the current configuration source fails.

`optional:configserver:` does not automatically create last-known-good state. It simply skips an import that failed to load. If a known-good configuration copy is needed, you must explicitly design its storage, versioning, integrity checks, expiration window, and selection process.

## 3. Config Data Import and Configuration Precedence

### 3.1. Declaring Config Server via spring.config.import

Spring Boot Config Data is the current default way for Config Client to connect to Config Server. Applications typically declare in `application.yml`:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://config.internal:8888"

app:
  downstream:
    timeout: 2s
  retry:
    max-attempts: 3
```

The configuration above requires Config Server. To make the remote source optional:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:http://config.internal:8888"

app:
  downstream:
    timeout: 2s
  retry:
    max-attempts: 3
```

If Config Server is reached successfully, properties from Config Server can override local values according to Config Data precedence order. If an optional import fails to load, local values remain available.

### 3.2. Import Location and spring.cloud.config.uri

You can specify the URL directly inside the import or use `spring.cloud.config.uri` to set the Config Server address.

Example:

```yaml
spring:
  config:
    import: "optional:configserver:"
  cloud:
    config:
      uri: http://config.internal:8888
```

If a URL is specified directly in `spring.config.import`, that URL takes precedence over `spring.cloud.config.uri`. Avoid configuring different addresses in both places unintentionally, as it makes diagnosing the actual target endpoint difficult.

### 3.3. How Remote Property Sources Override Local Ones

Imported locations are processed as additional config data. Properties from an imported location can take higher precedence than the document declaring the import. For example, if Config Server returns `app.downstream.timeout=5s`, that value can override `2s` in the local file.

Overall ordering is also affected by other Spring Boot property sources, such as command-line arguments, system properties, and environment variables. When conflicts arise, inspect the effective `Environment` instead of assuming which YAML file always wins.

Example table:

| Source | Timeout Value | Role |
| --- | --- | --- |
| Local application.yml | 2s | Fallback default value |
| Config Server | 5s | Centralized config by application/profile |
| Environment variable | 7s | Deployment environment override |
| Command-line argument | 9s | Explicit launch-time override |

This illustrates multiple sources declaring the same key. Actual precedence must be verified against Spring Boot's property source rules and how your application loads Config Data.

### 3.4. Profiles and Multiple Startup Requests

Config Data may call Config Server multiple times. Spring Boot first loads configuration with the default profile to discover additional profiles that might be activated from configuration. After resolving active profiles, it may call again to load profile-specific configuration.

Therefore, seeing multiple requests to Config Server during startup is not necessarily an error or a retry. Distinguish requests from the profile-resolution phase from retry requests caused by connection failures.

## 4. Deciding Which Configuration Is Mandatory

### 4.1. Classifying Configuration by Criticality

Do not mark every property as mandatory or assume every property can use defaults. Classify by the impact when missing or wrong:

| Configuration Group | Examples | Typically Suitable Handling |
| --- | --- | --- |
| Mandatory for safety/security | TLS trust material, credentials, authorization policy | Fail-fast if no valid source exists |
| Mandatory for core service connectivity | Database URL, schema, broker endpoint | Fail-fast or use a verified backup source |
| Business-critical | Payment processing topic, tenant routing | Fail-fast if missing |
| Safe to default | Internal timeout, bounded retry count | Bounded local fallback |
| Non-essential | Telemetry sampling rate, display labels | Can use defaults or disable feature |
| Development-only | Mock endpoints, debug flags | Place only in appropriate profiles |

For example, without valid credentials, starting a service with a default password or overly broad permissions is dangerous. If telemetry sampling config cannot be fetched, the service may continue with a low sampling rate or disable telemetry depending on operational requirements.

### 4.2. Using Validation to Catch Missing Configuration

An optional import only allows continuing past a failed optional source load. It does not verify whether remaining configuration is complete.

Validate required properties when binding configuration:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    @NotBlank
    private String endpoint;

    @NotBlank
    private String merchantId;

    // getters and setters
}
```

When validation is enabled and the configuration class is properly registered, the application will refuse to create a valid configuration bean if required properties are missing. This ensures fallback only works when local values genuinely satisfy the service's contract.

Ensure the application includes an appropriate Jakarta Bean Validation implementation—typically added via `spring-boot-starter-validation`—and that the configuration class is registered via configuration properties scanning or `@EnableConfigurationProperties`.

Do not check mere property existence alone. Validate formats, ranges, schemes, hostnames, timeouts, and relationships between values.

### 4.3. Fallbacks Must Be Business-Safe

A safe fallback is not merely a value that lets the application boot. It must ensure the service does not perform wrong actions.

Examples:

- timeouts can use small, bounded defaults;
- retries must be bounded with backoff, avoiding retry storms;
- downstream endpoints should have no fallback if calling the wrong environment risks corrupting data;
- credentials must never fall back to default passwords;
- feature flags for payment or authorization should default conservatively;
- when tenant mapping is missing, rejecting requests can be safer than picking a default tenant.

Evaluate every fallback against the consequences of running in that mode for several hours.

## 5. Combining Fail-Fast with Retry and Backoff

### 5.1. Why Retry Before Failing?

Config Server may still be initializing right when a service starts. If the service stops immediately on the first connection attempt, a few-second blip can cause many instances to fail startup together.

Retries allow waiting for the dependent system to recover. Once attempts are exhausted, fail-fast upholds the core principle: if required configuration cannot be retrieved, the service does not start.

### 5.2. Required Dependencies

According to current Spring Cloud Config Client documentation, Config Client retries require:

- `spring.cloud.config.fail-fast=true` in the legacy bootstrap mechanism or the corresponding required import;
- the `spring-retry` dependency;
- the `spring-boot-starter-aop` dependency.

With Config Data import, you can omit `optional:` and specify retry parameters on the import URL. Use dependency versions compatible with your project's Spring Cloud release train.

### 5.3. Configuring Retries for Config Data Import

Example when the import is declared directly:

```properties
spring.config.import=configserver:http://config.internal:8888?fail-fast=true&max-attempts=8&initial-interval=1000&max-interval=5000&multiplier=1.5
```

Illustrated parameters:

| Parameter | Meaning |
| --- | --- |
| `fail-fast` | Requires config loading errors to fail startup after retries |
| `max-attempts` | Maximum number of attempts |
| `initial-interval` | Initial wait interval |
| `max-interval` | Cap on backoff interval |
| `multiplier` | Multiplier applied between consecutive attempts |

Current Spring Cloud Config documentation describes defaults of six retries, an initial interval of 1000 ms, and a multiplier of 1.1. These values can vary by version and configuration; specify explicit thresholds instead of relying on defaults.

If the import is placed inside a profile-specific file such as `application-prod.yml`, retry configuration must be set as query parameters on the import URL per Config Client guidelines.

### 5.4. Calculating the Startup Time Budget

Retries increase maximum startup duration. When designing, account for:

- connection timeout per call;
- read timeout;
- number of attempts;
- backoff intervals;
- profile resolution time and other Config Data requests;
- the startup timeout enforced by the orchestrator or deployment platform.

If the startup probe deadline is shorter than the retry budget, the platform may kill the process before retries finish. Align startup probes with the expected startup budget.

Spring Cloud Config Client provides `spring.cloud.config.request-connect-timeout` and `spring.cloud.config.request-read-timeout` to tune connection and response read wait times. Check the value types and units for both properties in your active version.

### 5.5. Backoff and Jitter

Exponential backoff increases the delay after each failure to avoid hammering the server continuously. Random backoff (jitter) prevents many instances from retrying at the exact same instant after an outage.

When hundreds of replicas start simultaneously, synchronized retries can create a traffic spike against a recovering Config Server. Use suitable backoff and random policies where supported by your version.

## 6. Multiple Config Servers and Backup Server Selection

### 6.1. Multiple URIs with spring.cloud.config.uri

You can declare a comma-separated list of URIs:

```yaml
spring:
  cloud:
    config:
      uri: "http://config-a:8888,http://config-b:8888"
```

Config Client tries URLs in order until configuration retrieval succeeds according to the configured strategy. This improves fault tolerance when one Config Server instance is down or unresponsive.

Current documentation notes `spring.cloud.config.multiple-uri-strategy` defaults to `always`. You can set `connection-timeout-only` if you only want to fail over to another URL when the server is unreachable or connection times out.

### 6.2. Not Every Error Is an Availability Error

An HTTP 401 may indicate wrong credentials. HTTP 500 may indicate a server or Git backend failure. HTTP 400 usually signals an invalid request/configuration. These differ from connection refused or connection timeout.

When using `connection-timeout-only`, the client does not try the next URL for certain HTTP errors like 401 or 500 because they may reflect configuration or server-side errors rather than an unreachable server. Understand the exact strategy semantics instead of treating every error response as a failover trigger.

### 6.3. Multiple Import Locations in spring.config.import

You can declare multiple Config Server locations in a single import:

```yaml
spring:
  config:
    import: "configserver:http://config-a:8888,configserver:http://config-b:8888"
```

With multiple import locations, location ordering and error handling matter. According to Config Client documentation, if fail-fast is true, the client may fail immediately when the first Config Server call fails; if fail-fast is false, the client tries URLs until one succeeds. `multiple-uri-strategy` does not apply to URL lists declared in this manner.

Do not combine multiple fallback mechanisms simultaneously without understanding precedence order. A succeeding import returning different configuration can override values from an earlier import.

### 6.4. Discovery-First Lookup

If Config Server registers with a service registry, clients can use `DiscoveryClient` to locate the server. This allows Config Server addresses to change without clients hard-coding fixed URLs.

In return, startup incurs an extra network round trip to query the registry. The registry becomes a new startup dependency. If both the registry and Config Server are unavailable, discovery-first does not solve the mandatory configuration problem.

Choose among static URI, multiple URIs, and discovery-first based on topology, availability requirements, and acceptable startup dependencies.

## 7. Designing Controlled Local Fallbacks

### 7.1. Placing Default Values in application.yml

A common pattern is declaring safe defaults in a local file, then letting Config Server override them:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: "optional:configserver:http://config.internal:8888"

app:
  inventory:
    lookup-timeout: 1500ms
    max-retries: 2
    allow-stale-read: false
```

When Config Server is reachable, it supplies environment-specific values. When Config Server is unreachable, the service can use local values if they are safe enough.

Do not place dummy credentials or default production endpoints in local files. An unsafe local fallback can turn a configuration outage into a security incident or write data to the wrong environment.

### 7.2. Splitting Fallbacks by Profile

You can separate profiles for local/test and production. For instance, local may use mock endpoints, whereas production requires fetching configuration from Config Server.

Do not set `optional:` globally across all environments if production is not permitted to run without remote config. You can declare a required import in the production profile and optional in development profiles, while verifying the exact active profiles before startup.

Example illustrating split files:

```yaml
# application.yml
spring:
  application:
    name: billing-service
app:
  downstream:
    timeout: 2s
```

```yaml
# application-dev.yml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

```yaml
# application-prod.yml
spring:
  config:
    import: "configserver:https://config.internal"
```

Ensure imports are not duplicated in ways that trigger extra requests or unexpectedly alter precedence. Test each profile using the exact command line and environment of the target deployment.

### 7.3. Fallbacks for Secrets

Do not use a default password in `application.yml` as a fallback for production secrets. If Config Server is unreachable, obtain secrets from an independent protected source, such as a secret manager or a platform-mounted configuration tree.

Spring Boot supports `configtree:` to read files in a mounted directory as properties. Example:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

If a secret is required and the directory or file does not exist, validation must fail startup. Never mark a secret source optional and continue with empty or default credentials.

### 7.4. Do Not Confuse Fallback with Stale Config

Local defaults are backup configuration packaged with the application. Stale config is old configuration from a prior fetch. They differ in origin and freshness.

If continuing with previously verified configuration is required, persist a versioned last-known-good bundle with integrity verification. Define the maximum age allowed for stale config, rollback procedures, and safeguards preventing an instance from using config incompatible with the current code version.

## 8. Distinguishing Connection Errors from Configuration Content Errors

### 8.1. Connection Refused or Timeout

These are typically availability errors: Config Server is not running, wrong DNS, firewall, network policy, routing, or inappropriate timeouts.

Troubleshooting steps:

- check DNS and routing from inside the service's container/host;
- check Config Server health and port;
- check connection/read timeouts;
- check retry/backoff settings;
- test backup URIs if configured.

### 8.2. HTTP 401 or 403

These are typically authentication or authorization issues. Do not automatically treat them as transient server errors.

Check credentials, tokens, certificates, scopes/roles, clock skew, and read permissions on the repository/configuration label. Never log passwords or bearer tokens while diagnosing.

### 8.3. HTTP 404 or Empty Configuration

Config Server may return an empty configuration when the application/profile does not exist, depending on server settings. Config Server documentation describes `spring.cloud.config.server.accept-empty`; when set to `false`, the server can return 404 if the application is not found.

This distinction is critical: a successful connection does not mean the server supplied all properties the service needs. Inspect the application name, profile, label, and property sources in the response. Client-side validation must catch missing required keys.

### 8.4. HTTP 500

HTTP 500 can originate from Config Server or a backend repository such as Git/Vault/database. Inspect server-side logs and repository health. When using multiple URIs, whether another endpoint is tried depends on `multiple-uri-strategy` or import list semantics.

### 8.5. Syntactically Valid but Semantically Wrong Configuration

A property may exist yet carry a dangerous value, such as zero timeout, unbounded retries, or an endpoint pointing to another environment. Validation should cover ranges, patterns, URI schemes, and cross-property relationships.

Do not use HTTP 200 from Config Server as sole proof that the service received valid configuration.

## 9. Determining Readiness When Using Fallback

### 9.1. Successful Startup Does Not Mean Ready

When an optional import is skipped, Spring Boot may finish startup using local configuration. However, the service should only accept traffic if the local fallback satisfies business requirements.

Separate three states:

- **Process started:** JVM and `ApplicationContext` have initialized.
- **Application ready:** beans and required configuration are valid.
- **Operationally degraded:** the service is running on fallback or with certain features disabled.

You can surface degraded status in health details or internal metrics without exposing secrets or sensitive configuration details.

### 9.2. Verifying Configuration Before Accepting Traffic

A readiness check should verify:

1. required properties are bound;
2. downstream endpoints have valid URIs;
3. credentials and TLS material are ready;
4. feature flags do not create conflicting states;
5. the service can connect to required dependencies;
6. fallback mode is permitted in the current environment.

If fallback is not safe enough, do not mark the instance ready. This stops load balancers from routing traffic to a service that merely booted without being able to handle requests properly.

### 9.3. Recording Configuration Mode

Emit controlled metrics or startup logs indicating whether the service is running on remote config or local fallback, along with application name, active profiles, and label/version if available. Never log secret values.

This visibility helps operators notice when a service is in degraded mode instead of assuming it is running the latest configuration.

## 10. Testing Fail-Fast and Fallback

### 10.1. Scenario Matrix Testing

Write tests for each scenario:

| Scenario | Expected Configuration | Outcome to Verify |
| --- | --- | --- |
| Config Server returns valid config | Required or optional | Remote properties are applied |
| Config Server unreachable, required import | Required | Startup fails |
| Config Server unreachable, optional import | Optional | Startup continues if local config suffices |
| Config Server times out then recovers | Required + retry | Startup waits through retries and succeeds |
| Wrong credentials | Required or optional per policy | Does not silently fall back unsafely |
| Remote config misses required property | Optional or required | Validation catches missing property |
| Config Server returns out-of-range config | Any | Validation rejects configuration |
| Config Server A fails, B healthy | Multi-server | Client switches servers per strategy |
| Production profile without remote config | Required | Instance not ready or startup fails |

### 10.2. Testing with ApplicationContextRunner

For configuration beans and validation, use `ApplicationContextRunner` to verify local fallback behavior:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FallbackConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(InventoryConfiguration.class);

    @Test
    void usesLocalDefaultWhenNoRemotePropertyIsProvided() {
        runner.withPropertyValues("app.inventory.lookup-timeout=1500ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(InventoryProperties.class)
                            .getLookupTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Test
    void rejectsMissingRequiredEndpoint() {
        runner.run(context ->
                assertThat(context).hasFailed()
        );
    }
}
```

The runner is well suited for testing binding and validation. It does not simulate an HTTP Config Server on its own. For Config Client, write integration tests using a mock server or test Config Server environment to verify real imports, status codes, retries, and failover.

### 10.3. Testing Retries and Failover

In integration tests, configure the mock server to:

- refuse connections initially, then return configuration successfully;
- delay responses to trigger timeouts;
- return 401 or 500;
- return 404 or an empty property source;
- fail server A while server B succeeds;
- verify attempt counts and retry intervals remain within bounds.

Avoid testing retries using long fixed sleeps when you can observe request counts or use an appropriate clock/test harness. Keep test timeouts large enough for the retry budget yet bounded so infinite loops are caught.

### 10.4. Testing Profiles and Property Precedence

Run integration tests with different profiles and overlapping keys across local and remote sources. Confirm:

- imports use the right profile;
- remote properties override local ones as expected;
- environment variables or command-line arguments do not override unexpectedly;
- fallback is used only when Config Server fails to load;
- validation fails when remote config misses a required key.

## 11. Troubleshooting and Operations

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| App fails immediately when Config Server is down | Required import or fail-fast enabled | Decide if config is truly mandatory; if not, design optional fallback |
| App starts but misses properties | Optional import skipped or empty remote response | Inspect property sources and validation |
| App takes a long time to start | Many retries, large timeouts, or multiple profile requests | Recalculate startup budget and probe timeouts |
| App calls Config Server multiple times | Config Data resolving default/profiles or retrying | Distinguish profile requests from retries in logs |
| Does not fail over to Config Server B | Strategy disallows failover for that error or import is fail-fast | Check URI strategy, status code, and import syntax |
| App uses local values even though remote is up | Wrong URL, application/profile/label, or property not returned | Check Config Server response and `Environment` |
| App uses stale config after deploy | Wrong label or repository revision | Check label, commit, and config version |
| Retries cause heavy load during outage | Many replicas retrying in sync | Use backoff/jitter, cap attempts, and control rollout rate |
| Production runs with unwanted fallback | Shared optional profile/import across environments | Separate profiles and verify startup policies |
| All keys present yet service fails | Semantically wrong values or version incompatibility | Add range/format validation and contract checks |

### Incident Handling Procedure

1. Determine whether the service uses a required or optional import.
2. Identify the actual config source: Config Server URI, discovery, or local.
3. Check DNS, TCP, TLS, and timeouts from the service's runtime environment.
4. Read HTTP statuses and Config Server logs.
5. Confirm application name, active profile, and label.
6. Verify whether remote property sources loaded.
7. Check required properties and validation.
8. Determine whether the service is using remote, local fallback, or last-known-good config.
9. Check readiness and whether traffic is allowed into the instance.
10. When Config Server recovers, apply tested refresh/restart procedures; do not assume optional imports automatically reload configuration after startup.

## 12. Checklist for Choosing Fail-Fast vs. Fallback

Before deploying, answer:

- [ ] Which properties are genuinely mandatory for safe operation?
- [ ] Which missing properties must fail startup?
- [ ] Is the local fallback complete and safe for the target environment?
- [ ] Is production allowed to run in degraded mode?
- [ ] Do secrets have an independent source without default credentials?
- [ ] Is remote config validated for schema, range, and version?
- [ ] Are retries bounded in attempts, backoff, and timeouts?
- [ ] Does the startup probe allow enough time for the retry budget?
- [ ] If multiple Config Servers exist, is the failover strategy defined?
- [ ] Are connection failures distinguished from 401, 404, and 500?
- [ ] Do metrics/logs indicate when the service is running on fallback?
- [ ] Does readiness block traffic when configuration is not safe?
- [ ] Are there tests for outages, empty config, invalid config, and recovery?
- [ ] Is there a rollback procedure to a known-good config label/version?

## 13. Practice Exercises

### Exercise 1 — Config Server Outage in Production

An order processing service requires a database URL, credentials, and a payment gateway timeout. Config Server is unreachable when the pod starts.

Classify which properties are mandatory and which can use defaults. Propose required/optional imports and readiness conditions.

### Exercise 2 — Unsafe Local Fallback

An application has a local fallback with database username `admin` and a default password. The team enables optional Config Server so the service always starts.

Analyze the risks and propose an independent secret source using a secret manager or config tree, along with validation when secrets are missing.

### Exercise 3 — Retries Exceeding Startup Probe Deadline

A Deployment has a 30-second startup probe timeout. Config Client retries 10 times, each with a 5-second read timeout and increasing backoff.

Explain why the probe might kill the process before retries finish. Propose an aligned timeout budget, retry count, and rollout plan.

### Exercise 4 — Config Server A Returns 401, B Is Healthy

A client has two URIs and `multiple-uri-strategy=connection-timeout-only`. Server A returns 401 due to bad credentials; server B is healthy.

Explain why the client may not try B and how to distinguish credential failures from availability failures.

### Exercise 5 — Remote Config Returns Empty

Config Server returns a successful response missing `app.payment.endpoint`. The application uses an optional import and boots with incomplete local values.

Propose validation and readiness checks so the service does not admit traffic while a required property is missing.

### Exercise 6 — Config Server Recovers After Fallback Startup

A service booted using local fallback. A few minutes later, Config Server becomes available again.

Explain why optional import does not automatically guarantee configuration reloads. Propose a refresh or restart procedure, verification of new properties, and rollback if the new configuration is invalid.

## 14. Quick Self-Check

1. What does fail-fast mean? **Do not start if required configuration fails to load.**
2. With Config Data import, how do you require Config Server? **Omit the `optional:` prefix.**
3. Does optional import automatically store last-known-good config? **No.**
4. What problem does retry solve? **Transient errors before concluding the config source is unavailable.**
5. Does retry replace validation? **No.**
6. Which dependencies does Config Client retry require per current documentation? **Spring Retry and Spring Boot Starter AOP.**
7. What is the current default multiple URI strategy? **`always`.**
8. What does `connection-timeout-only` do? **Fails over only when a server is not running or connection times out according to client semantics.**
9. Is an HTTP 401 from Config Server the same as a connection timeout? **No; it usually requires fixing credentials or authorization.**
10. Does HTTP 200 prove all required properties are present? **No, you must inspect the response and validate configuration.**
11. Why is a readiness check needed when using fallback? **To avoid routing traffic to an instance that started up but cannot process business requests safely.**
12. Does optional import automatically reload remote config when the server recovers? **Do not assume so; an appropriate refresh or restart mechanism is needed.**

**Core message:** Fail-fast protects services from running with missing required configuration; optional imports and fallbacks help preserve partial operation during config source outages. Classify properties by criticality, combine bounded retries/backoff, understand exact multi-Config-Server failover behavior, and validate configuration before admitting traffic. A service should run in fallback mode only when the backup values are proven safe for that environment.

**References:**

- [Spring Cloud Config 5.0 — Config Client, Fail Fast and Retry](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Multiple Config Server URLs and Timeout Configuration](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration and Optional Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Configuration Trees for Mounted Secrets](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Environment Repository and accept-empty](https://docs.spring.io/spring-cloud-config/docs/current/reference/html/)

Config Data behavior, retry properties, and multiple-server strategies can change across releases. Verify against the documentation for your Spring Boot/Spring Cloud release train before deployment.
