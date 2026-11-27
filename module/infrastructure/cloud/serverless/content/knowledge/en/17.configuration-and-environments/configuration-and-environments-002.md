# Separating Configuration from Code and Validating Configuration at Startup

A Java function may be deployed to development, staging, and production from the same artifact, yet each environment uses different databases, queues, endpoints, load limits, and secrets. If these values are scattered throughout source code or edited manually after the build, every environment change risks producing a different application build that is hard to reproduce.

**Separating configuration from code** means keeping logic and artifacts independent of values that vary by environment. When a function starts, the application reads configuration from its provisioned sources, parses it into explicit data types, validates it, and only begins accepting work once required values satisfy the contract.

In serverless, this step is especially important because multiple instances can start concurrently. A misconfiguration can cause every new instance to fail simultaneously, trigger a retry storm, or send requests to the wrong resources. This lesson covers how to organize configuration, distinguish regular configuration from secrets, validate early with Java and Spring Boot, and manage changes safely across the function lifecycle.

## Learning objectives

After this lesson, you will be able to:

- Explain why environment-specific configuration must be separated from code and artifacts.
- Choose appropriate sources for environment variables, config files, parameter stores, and secret managers.
- Design configuration names, data types, defaults, and precedence rules.
- Bind configuration into immutable, strongly typed objects in Java.
- Validate required values, ranges, formats, and cross-property relationships at startup.
- Use Spring Boot `@ConfigurationProperties` and Bean Validation to fail fast.
- Distinguish instance-static configuration from dynamic configuration that needs updates while functions are running.
- Handle configuration in serverless environments with cold starts, warm reuse, revisions, and retries.
- Test valid, missing, malformed, and incompatible configurations before deployment.

## 1. Why separate configuration from code?

The same Java application may need to run with many different values:

| Value | Development | Staging | Production |
|---|---|---|---|
| Database endpoint | Local/test database | Staging database | Production database |
| Queue/topic | orders-dev | orders-staging | orders-prod |
| External API | Sandbox URL | Staging URL | Production URL |
| Log level | DEBUG | INFO | INFO/WARN |
| Request timeout | Test-appropriate values | Near-production | Per SLA |
| Feature flag | Enabled for experimentation | Controlled rollout | Per release decision |
| Secret | Test credentials | Staging credentials | Production credentials |

Hardcoding these values in code means each environment may require building a separate artifact. That reduces reproducibility, causes confusion during rollbacks, and increases the risk of shipping production endpoints or credentials into test builds.

A useful rule is: **build one tested artifact, then promote that artifact across environments with different configurations and permissions**. Non-sensitive configuration can be passed via environment variables or mounted files. Credentials and API keys should be retrieved from a secret manager or the platform's secret injection mechanism.

### Configuration is not business data

Configuration describes how the application operates in an environment, such as a queue name, timeout, or endpoint. Business data such as orders, balances, inventory, and workflow state must be stored in an appropriate data store.

Do not use environment variables to store state that changes per request. Environment variables belong to process/instance configuration and are not meant for atomic business updates.

## 2. Classify configuration before choosing a source

Not every value belongs in the same place. Classify values by sensitivity, change frequency, scope, and when they need to be read.

| Type | Examples | Appropriate source | Characteristics |
|---|---|---|---|
| Runtime/platform | Port, region, memory limit | Serverless platform | Provided by the execution environment |
| Deployment config | Queue name, database host, feature mode | Environment variables, deployment manifest, config store | Typically fixed for a revision/version |
| Secret | Password, API key, signing key | Secret Manager, Secrets Manager, Parameter Store SecureString | Requires IAM, auditing, and rotation |
| Dynamic config | Feature flag, rollout percentage, fast-changing thresholds | Config service or parameter store | May need refreshing while instances are running |
| Business data | Order status, customer preference, inventory | Database or event store | Has business lifecycle and transactions |

Define an authoritative source for each value. If the same timeout is declared in YAML, an environment variable, and remote config without precedence rules, operators will struggle to know which value the function actually uses.

### Regular configuration vs. secrets

Regular configuration can appear in deployment metadata, controlled logs, or operational dashboards. Secrets must be protected separately.

Do not assume a value is safe simply because it sits in an environment variable. Environment variables can show up in deployment configurations, diagnostic dumps, or application-written logs. Use a secret manager or platform secret integration for credentials, and grant read access to only the specific secret needed by the runtime identity.

Never place secrets in:

- Git repositories, Dockerfiles, or image layers.
- Build arguments or command lines that may be persisted in logs.
- Event payloads, URL query strings, or exception messages.
- Logs, trace attributes, metric labels, or dashboards.
- Shared test fixtures or onboarding documentation.

## 3. Naming and designing the configuration contract

Good configuration has names that convey meaning, data type, units, and requiredness.

For example:

~~~text
APP_DATABASE_URL=jdbc:postgresql://db.internal:5432/orders
APP_DATABASE_POOL_MAX_SIZE=12
APP_ORDER_QUEUE=orders-prod
APP_REQUEST_TIMEOUT=PT3S
APP_FEATURE_NEW_CHECKOUT=false
APP_ALLOWED_ORIGINS=https://shop.example.com,https://admin.example.com
~~~

Avoid vague names like `TIMEOUT`, `URL`, or `MODE` when an application has multiple dependencies. A name like `APP_PAYMENT_CONNECT_TIMEOUT_MS` is clearer because it communicates scope, purpose, and unit.

### Recommended conventions

- Use an application-specific prefix, such as `APP_`, to reduce naming collisions.
- Include units in the name or format, such as `_MS`, `_SECONDS`, or ISO-8601 duration `PT3S` (when using standard Java parsers).
- Use module-hierarchical names: `APP_DATABASE_URL`, `APP_QUEUE_ORDERS`.
- Explicitly distinguish required and optional fields.
- Only provide defaults when the default is safe across all intended environments.
- Specify formats for URLs, regions, enums, lists, and durations.
- Record a schema/version for configuration whose structure may evolve.

A bad default can be more dangerous than a startup failure. For example, if `PAYMENT_API_URL` is missing and the application silently falls back to a sandbox URL in production, requests may go to the wrong system. For required values, failing fast is usually safer than guessing a default.

### Example configuration catalog

| Key | Type | Required | Rules |
|---|---|---:|---|
| `APP_DATABASE_URL` | JDBC URL | Yes | Supported scheme, valid host and database |
| `APP_ORDER_QUEUE` | String | Yes | Non-empty, matches the environment's queue |
| `APP_REQUEST_TIMEOUT` | Duration | Yes | Greater than 0 and below the platform limit |
| `APP_DATABASE_POOL_MAX_SIZE` | Integer | Yes | Within load-tested range |
| `APP_FEATURE_NEW_CHECKOUT` | Boolean | No | Defaults to false if safe |
| `APP_PAYMENT_SECRET_ID` | Secret reference | Yes | Permitted ARN or secret name |
| `APP_ALLOWED_ORIGINS` | List<URI> | API-dependent | Valid origins only, no unintended wildcards |

This catalog can live in operational documentation or the application's configuration schema. Never put secret values in the catalog; document only the reference name and required permissions.

## 4. Configuration sources and precedence

Common configuration sources:

1. In-application defaults for optional fields.
2. Config files packaged inside the artifact, used for non-sensitive defaults.
3. Files or environment variables supplied at deployment time.
4. Secrets/parameters read from a configuration management service.
5. Explicit overrides for testing or local development environments.

Exact precedence depends on the framework and deployment method. Never assume a secret manager always overrides an environment variable or command-line argument. Define a single precedence order, verify it with integration tests, and log each value's source without logging sensitive values.

### Spring Boot configuration

Spring Boot supports multiple property sources and relaxed binding rules. The names below are canonical property names corresponding to the components of `AppProperties`:

~~~text
app.database-url
app.order-queue
app.request-timeout
app.database-pool-max-size
app.new-checkout-enabled
~~~

which can be bound from environment variables:

~~~text
APP_DATABASEURL
APP_ORDERQUEUE
APP_REQUESTTIMEOUT
APP_DATABASEPOOLMAXSIZE
APP_NEWCHECKOUTENABLED
~~~

For hyphenated property names, Spring Boot's environment variable binding rules convert dots to underscores, remove hyphens, and uppercase the name. Always verify exact variable names against actual properties; do not guess names from how they appear in documentation.

For applications not using Spring, build a single loader class that reads environment variables or config files, parses them into typed values, and returns a validated object. Avoid scattering `System.getenv()` calls across every service, as that makes testing harder and hides the configuration contract.

## 5. Validating configuration at startup

Configuration should be read and validated before the application accepts requests or processes messages. General flow:

~~~mermaid
flowchart TD
    A["Process / function starts"] --> B["Read config sources"]
    B --> C["Parse into typed values"]
    C --> D["Validate required fields"]
    D --> E["Validate ranges and relationships"]
    E --> F{"Configuration valid?"}
    F -->|Yes| G["Initialize clients and handlers"]
    G --> H["Become ready"]
    F -->|No| I["Fail startup with safe diagnostic"]
~~~

Validation should cover:

- **Presence:** required values exist and are non-empty.
- **Format:** URL, URI, ARN, enum, duration, or JSON is well-formed.
- **Range:** counts, timeouts, pool sizes, and ratios fall within bounds.
- **Relationship:** dependency timeouts are smaller than overall timeouts; pool size does not exceed chosen limits; queue name matches the environment.
- **Compatibility:** schema version is supported; feature flag names and modes are valid.
- **Security assumptions:** debug mode or public access is not unintentionally enabled in production.

Do not merely check for non-empty strings. `APP_REQUEST_TIMEOUT=abc` may be present but unparseable as a duration; `APP_DATABASE_POOL_MAX_SIZE=-5` may parse as an integer yet be invalid.

### Fail fast

If required configuration is invalid, abort startup and report an actionable error. Do not let a function begin serving requests only to discover later that a database URL or queue name is missing.

Error messages should state clearly which key failed and why, without printing secret values. For example:

~~~text
Invalid configuration: APP_REQUEST_TIMEOUT must be between 100ms and 30s
~~~

Never log:

~~~text
Database password rejected: <secret-value>
~~~

In serverless environments, the platform may attempt to spawn replacement instances or trigger retries after a startup failure. If the misconfiguration is a permanent error, endless retries only inflate logs and costs. Alert clearly on startup errors, bound caller retries, and fix the configuration before resuming traffic.

## 6. Plain Java: parsing and validating into an immutable object

The following example uses Java 17, reads configuration from environment variables, and constructs an immutable record. All validation is centralized in one place.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record AppConfig(
        URI databaseUrl,
        String orderQueue,
        Duration requestTimeout,
        int databasePoolMaxSize,
        boolean newCheckoutEnabled) {

    public static AppConfig from(Map<String, String> env) {
        URI databaseUrl = requiredUri(env, "APP_DATABASE_URL");
        String orderQueue = required(env, "APP_ORDER_QUEUE");
        Duration timeout = requiredDuration(
                env, "APP_REQUEST_TIMEOUT");
        int poolSize = requiredInt(
                env, "APP_DATABASE_POOL_MAX_SIZE");
        boolean newCheckout = optionalBoolean(
                env, "APP_FEATURE_NEW_CHECKOUT", false);

        if (!"jdbc".equalsIgnoreCase(databaseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "APP_DATABASE_URL must use a JDBC URL");
        }
        if (timeout.compareTo(Duration.ofMillis(100)) < 0
                || timeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException(
                    "APP_REQUEST_TIMEOUT must be between 100ms and 30s");
        }
        if (poolSize < 1 || poolSize > 50) {
            throw new IllegalArgumentException(
                    "APP_DATABASE_POOL_MAX_SIZE must be between 1 and 50");
        }

        return new AppConfig(
                databaseUrl,
                orderQueue,
                timeout,
                poolSize,
                newCheckout);
    }

    private static String required(
            Map<String, String> env, String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }
        return value.trim();
    }

    private static URI requiredUri(
            Map<String, String> env, String key) {
        String raw = required(env, key);
        try {
            return URI.create(raw);
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    key + " must be a valid URI");
        }
    }

    private static Duration requiredDuration(
            Map<String, String> env, String key) {
        String raw = required(env, key);
        try {
            return Duration.parse(raw);
        } catch (RuntimeException ignored) {
            // The example contract uses ISO-8601, such as PT3S.
            throw new IllegalArgumentException(
                    key + " must use ISO-8601 duration, for example PT3S");
        }
    }

    private static int requiredInt(
            Map<String, String> env, String key) {
        try {
            return Integer.parseInt(required(env, key));
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    key + " must be an integer");
        }
    }

    private static boolean optionalBoolean(
            Map<String, String> env,
            String key,
            boolean defaultValue) {
        String raw = env.get(key);
        if (raw == null || raw.isBlank()) {
            return defaultValue;
        }
        if ("true".equalsIgnoreCase(raw.trim())) {
            return true;
        }
        if ("false".equalsIgnoreCase(raw.trim())) {
            return false;
        }
        throw new IllegalArgumentException(
                key + " must be true or false");
    }
}
~~~

In this example, the timeout uses ISO-8601 format such as `PT3S`. If you want to accept `3s`, use a duration parser that supports that syntax or write a dedicated parser; do not mix two formats in the same contract.

`AppConfig.from(System.getenv())` can be called once during initialization. In unit tests, pass a synthetic `Map` to test many cases without mutating process environment variables.

### Why use an immutable record?

A record represents a validated configuration snapshot. After startup, services receive the same object instead of reading environment variables in multiple places. This reduces the chance of a request seeing half old configuration and half new configuration.

If configuration needs dynamic updates, use a dedicated snapshot/version mechanism and swap the entire validated object atomically. Never mutate individual fields while requests are reading them.

## 7. Spring Boot: @ConfigurationProperties and Bean Validation

Spring Boot can bind properties into a class or record and validate them using Jakarta Bean Validation. The following example uses Spring Boot 3 and Java 17 or later.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;
import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull URI databaseUrl,
        @NotBlank String orderQueue,
        @NotNull Duration requestTimeout,
        @Min(1) @Max(50) int databasePoolMaxSize,
        boolean newCheckoutEnabled) {

    public AppProperties {
        if (databaseUrl != null
                && !"jdbc".equalsIgnoreCase(databaseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "app.database-url must use a JDBC URL");
        }
        if (requestTimeout != null
                && (requestTimeout.compareTo(Duration.ofMillis(100)) < 0
                || requestTimeout.compareTo(Duration.ofSeconds(30)) > 0)) {
            throw new IllegalArgumentException(
                    "app.request-timeout must be between 100ms and 30s");
        }
    }
}
~~~

Register configuration properties via `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(AppProperties.class)` in configuration.

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Declare the corresponding validation dependency, such as `spring-boot-starter-validation`, so annotations like `@NotBlank`, `@Min`, and `@Max` are enforced. Constructor validation in the record above adds relational rules for `Duration`; this can be moved into a custom constraint when the application has many complex rules.

Non-sensitive defaults in `application.yaml` (the properties below match the record components directly):

~~~yaml
app:
  request-timeout: 3s
  database-pool-max-size: 12
  new-checkout-enabled: false
~~~

Environment-specific values are overridden via environment variables or the deployed config source. For example:

~~~text
APP_DATABASEURL=jdbc:postgresql://db.internal:5432/orders
APP_ORDERQUEUE=orders-prod
APP_REQUESTTIMEOUT=3s
APP_DATABASEPOOLMAXSIZE=12
APP_NEWCHECKOUTENABLED=false
~~~

Spring Boot converts `Duration` from strings like `3s`. Verify variable names and binding results with a startup test or safe metadata logging. Never log the entire object if it contains secrets or sensitive connection details.

### Cross-property validation

Bean Validation handles single-property checks well, but interdependent rules should be checked in a constructor, custom validator, or dedicated startup step. For example:

- Connect timeout must be smaller than request timeout.
- Database pool size must align with concurrency and total connection limits.
- Batch size must be compatible with timeout and memory.
- Retry count must be non-negative and total retry duration must stay within SLA.
- If a new feature is enabled, its required endpoint or secret reference must be present.

Do not place these checks inside controllers, because controllers only execute after the application has started accepting traffic.

## 8. Serverless configuration: values requiring special attention

In addition to standard application settings, Java functions often need settings related to triggers, concurrency, and execution deadlines.

| Group | Examples | Recommended checks |
|---|---|---|
| HTTP | Port, allowed origins, request timeout | Valid port; well-formed origins; timeout below platform limit |
| Queue | Queue name, batch size, visibility/ack deadline | Queue exists; positive batch size; timeout compatible with delivery semantics |
| Event | Schema version, event type allowlist | Supported version; non-empty event types |
| Database | JDBC URL, pool size, connect timeout | Valid URL; pool does not exceed total connection budget |
| Retry | Max attempts, backoff, DLQ | Positive values; no infinite retries on permanent errors |
| Idempotency | Key namespace, retention TTL | TTL long enough for expected retry/replay window |
| Security | Secret reference, allowed issuer/audience | References right environment; auth not unintentionally disabled |
| Observability | Log level, trace sampling | Value in allowed set; no sensitive debug logging in production |

Some values belong to platform configuration rather than application environment variables. For example, batch size or max instances may be set on the event source mapping or service deployment. Avoid creating two sources of truth for the same limit.

### Timeout constraints across layers

Suppose an HTTP request has a total timeout of 10 seconds. Database connect timeout is 2 seconds, query timeout is 5 seconds, and the remaining processing needs time to return a response. The sum of dependency timeouts must not exceed the request timeout.

For queues, visibility timeout or acknowledgment deadline must align with processing time and the source's retry semantics. If a message is redelivered before the previous invocation finishes, two consumers may process the same message concurrently. Configuration must be verified alongside idempotency, not just as isolated numbers.

## 9. Secrets and sensitive configuration

Environment variables are convenient for deployment-level configuration, but they are not the default choice for every secret. Use a secret manager or platform secret integration to keep credentials outside source code and images.

A configuration might contain references like:

~~~text
APP_DATABASE_SECRET_ID=projects/example/secrets/orders-db/versions/latest
APP_PAYMENT_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:payment-key
~~~

These values merely illustrate two different platform reference styles. Do not mix Google Secret Manager and AWS Secrets Manager syntax in the same deployment. Each environment must use its own provider, region/project, and IAM identity.

### When should secrets be read?

There are two common approaches:

- **Startup snapshot:** read the secret at startup, parse it, and build the client. Subsequent requests reuse the configured client. This reduces API calls, though the secret may stay stale until the instance is replaced or refreshed.
- **TTL cache:** read the secret through a caching provider with an expiration TTL. This supports rotation without calling the secret store on every request.

Avoid fetching secrets from a remote store on every request unless strictly required; doing so increases latency, cost, and dependency on secret service availability.

### Rotation and running instances

When a secret is rotated, warm instances may still hold old credentials in memory or connection pools. Determine:

- Whether the secret reference points to a specific version or the current version.
- The cache refresh mechanism and TTL.
- How connection pools recycle connections when credentials change.
- Behavior when the secret service is temporarily unavailable.
- How new instances roll out and old-config instances drain out.

Do not assume updating a secret automatically updates environment variables or already-initialized Java objects. Update behavior depends on the platform and how secrets are mounted or injected.

## 10. Static configuration vs. dynamic configuration

**Instance-static configuration** is read when the process/function starts and generally stays fixed for the lifetime of the instance. Examples include database endpoints, queue names, pool sizes, and regions. Changing them typically requires creating a new revision/version or starting new instances.

**Dynamic configuration** can change while the service is running without redeploying, such as feature flags or rollout percentages. Use dynamic config only when genuinely needed, and define refresh, caching, versioning, rollback, and config-service failure behavior.

| Criterion | Startup/static config | Dynamic config |
|---|---|---|
| Read timing | At startup | On controlled refresh/poll/event or request |
| Consistency | Stable snapshot within an instance | May differ temporarily across instances |
| Complexity | Lower | Requires versioning, refresh, and error handling |
| Best suited for | Endpoints, pool sizes, queues, timeouts | Feature flags, rollout percentages, fast-changing policies |
| When source fails | New instances may fail startup if required values are unreadable | Must decide whether to keep old snapshot or disable the feature |

For dynamic configuration, never mutate individual fields piecemeal. Fetch a complete configuration set, validate the whole set, and publish a new immutable snapshot via an atomic reference. In-flight requests can continue using the old snapshot; subsequent requests use the new one. This avoids half-old, half-new state.

If refreshing fails, retain the old snapshot for an allowed grace window and raise an alert. For security settings or policies requiring immediate revocation, failing closed may be necessary instead of continuing with stale values. The decision depends on the impact of stale configuration.

## 11. Configuration lifecycle in serverless

Serverless instances can be newly created, reused, and reclaimed. That affects when configuration is read and how long it remains in effect.

### Cold start

When a new instance is created, the application reads configuration, validates it, and initializes SDK clients, connection pools, and framework contexts. If startup has to call multiple remote services, cold starts can increase significantly.

Read only the configuration needed to be ready for requests. Initialization of dependencies not required by every request can be deferred, but do not defer validating critical configuration until the first production request reveals an error.

### Warm reuse

An instance may retain configuration objects across many invocations. Treat loaded configuration as an immutable snapshot. Never store tenant-, user-, or request-specific overrides in shared configuration objects.

Static fields can hold a validated `AppConfig` within a single JVM, but they are not shared across instances and are lost when the execution environment is reclaimed. Do not use static fields as a system-wide dynamic configuration store.

### Revisions and versions

When deploying a new revision/version with updated environment variables or secret references, new instances run with the new revision/version's configuration. Older instances or in-flight executions may continue running during rollout depending on platform semantics.

Therefore, configuration must remain compatible across revisions running concurrently during transitions. For example, if renaming a queue, ensure producers, consumers, and IAM permissions transition in an order that does not drop messages. Do not delete old resources immediately upon deploying a new version.

## 12. Testing configuration

Configuration is part of the application contract and must be tested like code.

### Unit tests

For plain Java `AppConfig`, pass a `Map` to test:

- All required fields present.
- Each required field missing.
- Empty or whitespace-only strings.
- Malformed URLs/URIs.
- Unparseable or out-of-range durations.
- Negative, zero, or out-of-bounds integers.
- Booleans other than true/false.
- Conflicting configuration combinations.

JUnit example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AppConfigTest {

    @Test
    void rejectsMissingDatabaseUrl() {
        Map<String, String> env = Map.of(
                "APP_ORDER_QUEUE", "orders-test",
                "APP_REQUEST_TIMEOUT", "PT3S",
                "APP_DATABASE_POOL_MAX_SIZE", "8");

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> AppConfig.from(env));

        assertTrue(error.getMessage().contains("APP_DATABASE_URL"));
    }

    @Test
    void rejectsPoolSizeOutsideRange() {
        Map<String, String> env = Map.of(
                "APP_DATABASE_URL",
                "jdbc:postgresql://localhost:5432/orders",
                "APP_ORDER_QUEUE", "orders-test",
                "APP_REQUEST_TIMEOUT", "PT3S",
                "APP_DATABASE_POOL_MAX_SIZE", "0");

        assertThrows(
                IllegalArgumentException.class,
                () -> AppConfig.from(env));
    }
}
~~~

### Startup/integration tests

Start the application with test configuration and verify:

- The application context initializes successfully with valid configuration.
- The context fails when a required property is missing or invalid.
- The intended profile/environment is selected.
- Secret references can be read using the test environment's identity.
- Secret values are not logged on startup failures.
- Health/readiness only reports ready after configuration and essential dependencies are initialized.

Do not use production secrets in tests. Use fake providers, local emulators, or dedicated test-environment secrets.

### Deployment validation

The pipeline can validate manifests or deployment parameters before creating a revision:

1. Verify required keys and data types.
2. Verify URLs, regions, queues/topics, and secret references.
3. Verify the IAM role/service account has the necessary permissions.
4. Verify limits for concurrency, pool size, timeout, and batch size.
5. Deploy to staging and run smoke tests.
6. Promote only approved artifacts and configurations.

Pipeline validation does not replace in-application validation. Configuration can change after build or be modified manually; the application still needs to validate before accepting traffic.

## 13. Handling invalid configuration or config source failures

Distinguish permanent configuration errors from transient failures when reading remote configuration.

| Scenario | Recommended response |
|---|---|
| Missing required database URL | Fail startup, report the missing key |
| Unparseable timeout | Fail startup, report the expected format |
| Invalid secret reference or missing permission | Fail startup if secret is essential; alert and fix IAM/config |
| Config service transient timeout | Bounded startup retries or use valid snapshot per policy |
| Dynamic config refresh failure | Retain old snapshot within allowed window or fail closed for sensitive policies |
| Unsupported config version | Fail fast; do not silently ignore important fields |
| New configuration causes errors after rollout | Roll back revision/alias and keep data compatible |

Never retry infinitely during startup. For transient errors, use exponential backoff with jitter and an overall time cap. When startup fails, log the failing key/source, exception type, and correlation ID; never log credentials or sensitive configuration values.

### Readiness and liveness

Readiness answers whether the application is ready to receive traffic. Liveness answers whether the process is alive and able to keep running. Do not use liveness probes to check every external dependency on each cycle, because a flaky database can cause continuous instance restarts. Cloud Run and container platforms support startup/readiness/liveness probes; AWS Lambda lacks an equivalent HTTP readiness probe, so configuration errors during initialization typically surface as init/invocation failures and must be tracked via logs, metrics, and deployment status.

Required configuration checks should occur before readiness. A health endpoint can report not-ready if the service has not completed startup. For optional dependencies, define clearly whether the service can serve degraded functionality or must fail completely.

## 14. Configuration checklist for Java serverless

- [ ] Artifacts contain no production-specific endpoints, queue names, or credentials.
- [ ] Every key has a clear name, data type, unit, and description.
- [ ] A catalog distinguishes required, optional, secret, and dynamic configuration.
- [ ] Each value has an authoritative source and clear precedence order.
- [ ] Configuration is bound into typed, immutable objects.
- [ ] Required fields, formats, ranges, and cross-field rules are validated at startup.
- [ ] Defaults are used only when safe; missing required values fail fast.
- [ ] Secrets live in a secret manager or secret integration, never in source/images/logs.
- [ ] Runtime identities can read only the specific secrets/parameters they need.
- [ ] Trigger, timeout, retry, concurrency, and connection pool settings are compatible.
- [ ] Startup does not depend on unnecessary remote calls.
- [ ] Warm instances use validated snapshots and never store request state in configuration.
- [ ] Dynamic config defines versioning, refresh, atomic snapshots, and source-failure behavior.
- [ ] Rotation includes plans to refresh caches and recycle connection pools.
- [ ] Unit tests cover missing, malformed, out-of-range, and conflicting values.
- [ ] Integration/deployment tests verify IAM, secret references, and readiness.
- [ ] Configuration error logs never expose secrets or sensitive data.

## Self-check questions

1. Why should the same Java artifact be reused across multiple environments with different configurations?
2. Which types of data belong in a secret manager rather than config files or environment variables?
3. Why can a default cause an application to run against the wrong environment without immediate detection?
4. What should startup validation check beyond whether a property is present?
5. Why should configuration be bound into an immutable object instead of calling `System.getenv()` across multiple services?
6. How does dynamic configuration differ from startup/static configuration in read timing and consistency requirements?
7. When a secret is rotated, why might warm instances still use the old credentials?
8. How does readiness differ from liveness, and why shouldn't liveness check every dependency?
9. If a misconfiguration causes all new instances to fail startup, what impact can infinite retries have?
10. Which scenarios should be tested before promoting a revision to production?

Separating configuration from code enables a single Java artifact to be deployed consistently across environments. Validating configuration immediately at startup catches mistakes before functions accept requests or messages. When configuration is properly classified, bound into typed objects, validated for both values and cross-field relationships, and managed intentionally for secrets and dynamic updates, serverless systems become easier to deploy, test, and recover.
