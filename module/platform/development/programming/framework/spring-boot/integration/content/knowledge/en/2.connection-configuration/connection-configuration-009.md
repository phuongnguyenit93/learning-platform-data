# Never Hard-Code URLs, Credentials, or Secret Keys in Source Code

## 1. Context and objectives

In the **SPRING_BOOT_INTEGRATION** module, a Spring Boot application commonly connects simultaneously to HTTP APIs, databases, caches, message brokers, and Spring Integration adapters. To operate safely, each connection requires endpoints, accounts, credentials, certificates, and tuning parameters such as timeouts, pool sizes, and retries. The module also emphasizes data contracts, transactions, error handling, deduplication, testing, and observability across real integration flows.

Problems arise when connection values are written directly inside Java classes, YAML files committed to source control, Docker images, or deployment scripts. For instance, moving a database host requires editing code and rebuilding, while leaking a token on Git grants live access to unauthorized parties.

**Principle:** source code describes **how to connect**, while the deployment environment supplies **where to connect** and **which identity/permissions to authenticate with**. Sensitive values require a protected secrets management mechanism with access controls, auditing, and rotation capabilities.

After this lesson, you will be able to:

1. Distinguish endpoints, usernames, passwords, API tokens, private keys, certificates, and non-sensitive settings.
2. Use **Spring Boot Externalized Configuration** instead of literals in Java and committed configs.
3. Map settings using **@ConfigurationProperties**, placeholders, and fail-fast validation.
4. Choose among environment variables, **config trees**, Kubernetes Secrets, or a secret manager per environment.
5. Pass configuration securely to `WebClient`, `DataSource`, Redis, and message brokers.
6. Govern access control, logging, Actuator, CI/CD, rotation, and incident recovery if credentials leak.
7. Test the application without real credentials or reliance on production endpoints.

## 2. Classifying connection data before configuring

Not every URL is a secret; however, a hard-coded URL still couples the build to one environment, complicating transitions across local, test, staging, and production. Conversely, **a URL embedding a username/password or query-string token** must be treated as a secret.

| Value | Example role | Sensitivity | Management approach |
| --- | --- | --- | --- |
| **Base URL, hostname, port** | Partner API address, DB host, broker bootstrap servers | Usually config; may disclose internal topology | Externalized config with environment access controls |
| **Username / client ID** | Technical account identifier | Not always secret, yet often worth protecting | Environment-specific config, never embedded in code |
| **Password, API key, bearer token** | Client/consumer authentication | **Secret** | Vault / Kubernetes Secret / secret manager, least privilege |
| **OAuth client secret / refresh token** | Acquiring or renewing access tokens | **Secret** | Secret manager with rotation policy |
| **Private key, keystore password** | TLS client authentication, signing | **Highly sensitive secret** | File/secret manager, restricted read permissions, audited |
| **Public certificate / CA trust bundle** | Verifying server TLS | Typically non-secret, yet integrity is critical | Versioned and provenance-controlled artifact/config |
| **Database name, schema, virtual host, topic** | Connection routing and data partitioning | Config; may expose internal structure | Externalized config |
| **Timeout, pool size, retry budget** | Resource bounds and failure behavior | Non-secret | Environment-specific config, tested and monitored |

The core point is to **separate secrecy requirements from configuration variability**. Moving a URL to an environment variable solves deployability; moving a token to an environment variable only removes the literal from source code—it **does not automatically provide encryption, auditing, TTLs, or rotation**.

### Anti-pattern to avoid

~~~java
// ANTI-PATTERN: never hard-code accounts or secrets in classes.
public final class PartnerClient {
    private static final String BASE_URL =
            "https://partner-production.example.internal";
    private static final String USERNAME = "service-prod";
    private static final String PASSWORD = "production-password";
    private static final String API_TOKEN = "replace-with-real-token";
}
~~~

These strings illustrate **what not to do**; none are valid credentials. Even if removed in a later commit, real secrets persist in Git history, image layers, build logs, CI clones, and code search indexes.

**Avoid hard-coding beyond Java literals too.** Guard every place credentials could slip in:

- **application.yml / application.properties** committed with the project;
- **.env** files accidentally pushed to Git;
- Dockerfile **ENV/ARG** directives or build commands carrying secrets;
- Kubernetes manifests or Helm values containing live tokens;
- shell scripts, Gradle/Maven settings, sample docs, and test logs;
- URLs with query-string keys or connection strings embedding passwords;
- screenshots, issue trackers, chats, and debug config dumps.

## 3. Architecture of code separated from environment config

~~~mermaid
flowchart TD
    A["Application code + immutable artifact"] --> B["Spring Boot Environment / Binder"]
    C["Shared config: versioned YAML"] --> B
    D["Deployment variables / ConfigMap"] --> B
    E["Secret manager / configtree / workload identity"] --> B
    B --> F["Validated @ConfigurationProperties"]
    B --> G["Credential provider"]
    F --> H["WebClient / DataSource / Redis / Broker clients"]
    G --> H
    H --> I["Downstream services"]
    J["Controlled observability + audit"] -.-> H
~~~

Operational principles:

1. **One artifact** runs across multiple environments without modifying source code.
2. Endpoints are assigned per controlled environment or tenant; never read blindly from unverified input.
3. Credentials are supplied at runtime over a secure channel, scoped strictly to the running service.
4. Required configuration is **validated at startup** or before opening consumer traffic.
5. When a secret changes, the app has an explicit **refresh/reconnect** process rather than assuming beans auto-update.
6. Logs, traces, and metrics surface safe configuration state, **never raw credentials**.

## 4. Spring Boot Externalized Configuration

Spring Boot loads properties from many sources: packaged configs, external config files, environment variables, Java system properties, command-line arguments, **config trees**, and integrated providers like Vault or Config Server. Exact precedence varies by version; when the same property key appears in multiple sources, **the higher-precedence source** determines the final value.

Never guess "the final value must be what's in application.yml." Verify against the `Environment`/ConfigData rules of your Boot version and avoid scattering the same secret across conflicting sources.

### 4.1. application.yml contains only property keys and placeholders

Example for a service integrating multiple connection types:

~~~yaml
app:
  integration:
    partner:
      base-url: ${PARTNER_API_BASE_URL}
      request-timeout: ${PARTNER_API_TIMEOUT:3s}
      token: ${PARTNER_API_TOKEN}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_APP_USERNAME}
    password: ${DB_APP_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX_SIZE:12}
      connection-timeout: 2s

  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD}

  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST}
~~~

**Conditions of this example:** the application actually uses those starters (JDBC, Redis, AMQP, WebClient). Never copy every block into an HTTP-only service; configure only connections in active use. Placeholders without defaults such as **PARTNER_API_TOKEN** must be supplied by the runtime environment or an approved secret source.

- **PARTNER_API_BASE_URL** holds an endpoint, not a credential.
- **PARTNER_API_TOKEN** is a secret; never write a real value into YAML.
- Defaults like **3s**, **12**, or **6379** illustrate non-sensitive parameters. Tune them to real traffic, SLOs, TLS, and architecture.
- **DB_JDBC_URL** must not embed username/password in the URL or query string when the driver accepts separate properties. A JDBC URL containing credentials must be treated as a secret.
- **spring.data.redis.password** and **spring.rabbitmq.password** illustrate password-based sources. With IAM, mTLS, OAuth, or modern SASL, configure the proper authentication mechanism rather than defaulting to username/password.

### 4.2. Placeholders, defaults, and fail-fast behavior

Spring supports placeholder syntax:

~~~yaml
# No default: deployment must provide it.
app.integration.partner.base-url: ${PARTNER_API_BASE_URL}

# Default for non-sensitive parameter:
app.integration.partner.request-timeout: ${PARTNER_API_TIMEOUT:3s}
~~~

**Never set fake defaults for production secrets**, such as an easily guessed password or static token. That allows the app to run silently with wrong permissions and masks misconfiguration.

For required fields, when a placeholder is unresolved or mistyped, the application should fail early during binding/validation rather than firing requests at an undefined endpoint. Note that **an unused/unbound property** may not trigger fail-fast behavior; to enforce all critical settings, register and validate properties explicitly.

### 4.3. Profiles: select policies, never store real secrets

~~~yaml
# application-dev.yml, not a place for real credentials.
app:
  integration:
    partner:
      request-timeout: 5s
~~~

~~~yaml
# application-prod.yml, still strictly non-secret configuration.
app:
  integration:
    partner:
      request-timeout: 2s
~~~

Profiles can be activated via **SPRING_PROFILES_ACTIVE** in the runtime environment. Never use profiles as a "secret vault" by committing **application-prod.yml** with passwords. Profile files are still packaged inside JARs and container images.

## 5. @ConfigurationProperties and pre-connection validation

**@ConfigurationProperties** models configuration contracts as Java types, supporting URI/Duration conversion and validation. It scales far better than scattering dozens of **@Value** annotations across classes.

### 5.1. Typed properties containing only non-sensitive settings

~~~java
import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration.partner")
public record PartnerClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration requestTimeout) {
}
~~~

Registering properties in the application:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
~~~

For **@NotNull** and configuration property validation to execute, the project needs a Bean Validation provider, typically added via **spring-boot-starter-validation**. Verify module and package names for your Boot version (e.g. Boot 3.x uses **jakarta.validation**).

**The token is omitted from the record** here because default **record.toString()** prints all component values, risking secret leaks. If a configuration class must carry a secret, never log that object and consider a **masked `toString()`** or an abstraction that fetches credentials only at point of use.

### 5.2. Validating endpoints and rejecting invalid config

**@NotNull** alone is insufficient if a URI targets the wrong host, uses an insecure scheme, or embeds credentials.

~~~java
import java.net.URI;

public final class PartnerEndpointPolicy {
    private PartnerEndpointPolicy() {}

    public static void verify(PartnerClientProperties properties) {
        URI uri = properties.baseUrl();
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalStateException(
                    "Partner base URL must be HTTPS without user-info");
        }
        if (properties.requestTimeout().isZero()
                || properties.requestTimeout().isNegative()) {
            throw new IllegalStateException(
                    "Partner timeout must be positive");
        }
    }
}
~~~

**verify** checks bound data and runs when building the `WebClient` below; do not register an extra **PartnerClientProperties** bean alongside the one scanned by **@ConfigurationPropertiesScan**. In real applications, turn these checks into a **Bean Validation custom constraint** or constructor invariant. Enforce **HTTPS** rules appropriately per environment; if tests allow HTTP **localhost**, apply a tight test-only exception rather than allowing arbitrary HTTP URLs in production.

### 5.3. A WebClient configuration consuming injected values

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            PartnerClientProperties properties,
            @Value("${app.integration.partner.token}") String token) {

        PartnerEndpointPolicy.verify(properties);
        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeaders(headers -> headers.setBearerAuth(token))
                .build();
    }
}
~~~

**@Value** here shows injecting a secret from an existing placeholder; production code can swap in a **TokenProvider/SecretProvider** to support rotation. Never print the **token**, the **Authorization header**, **WebClient.Builder**, or configuration objects that could hold credentials. **defaultHeaders(setBearerAuth)** captures the token at bean creation time: if the secret rotates later, this bean **does not auto-update**.

If a partner uses OAuth client credentials, prefer an **OAuth2AuthorizedClientManager** or matching auth provider to obtain short-lived access tokens, cache within bounds, and refresh per protocol—rather than duplicating client secrets across multiple WebClient beans.

### 5.4. Avoid manual DataSource beans when Boot supports auto-config

For standard JDBC connections, let **Spring Boot auto-configure DataSource** from **spring.datasource.\***:

~~~java
@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int markReady(String orderId) {
        return jdbc.update(
                "UPDATE orders SET ready = true WHERE id = ?",
                orderId);
    }
}
~~~

The repository knows nothing about hostnames, database usernames, or passwords. The pool reads credentials from environment config; the transaction manager shares that `DataSource` via Spring wiring.

When multiple datasources or custom drivers require explicit code configuration, still inject credentials via properties or providers—never embed literals in **DataSourceBuilder**, **DriverManager.getConnection(...)**, or SQL statements.

## 6. Environment variables: useful, yet not a secret manager

Environment variables are a standard delivery channel, with notable limitations:

- Readable by the process, debuggers, or users with runtime inspection privileges.
- Can leak via support tooling, crash dumps, thread dumps including env, shell history, or diagnostic commands.
- Lack native versioning, rotation, expiration, and auditing.
- Usually read once at process start; updating OS env vars does not automatically update already-bound beans.

**Never pass credentials on the command line** as **--password=...** or Java **-D...password=...** when safer alternatives exist. Command lines appear in process listings, logs, and deployment histories.

### Local development

Local setup scripts should fetch developer-scoped secrets from your team's management tooling rather than copying real passwords into files:

~~~text
Local environment
  → Developer secret manager / access tool
  → Export temporary env vars for the Java process
  → Spring Boot resolves placeholders
  → Connects to test/dev endpoints
~~~

A **.env** file is a convention of Docker Compose or shell utilities. **Spring Boot does not automatically read arbitrary .env files** just because they sit in the project root; configure your launch tooling or an explicit config import to supply those variables.

If using an untracked local file during development, ensure `.gitignore` covers it, restrict file permissions, and never store production credentials. **.gitignore never remediates a secret that has already been committed.**

## 7. Config trees and secrets mounted as files

Spring Boot supports **config trees**: filenames map to property names, and file contents supply the values. This works well when an orchestrator mounts secrets as files without placing values in source code or environment variables.

Suppose the runtime container contains:

~~~text
/run/secrets/
    partner.token
    database.password
~~~

Those paths are **files inside the container runtime**, never committed to Git. In **application.yml**:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    password: ${database.password}

app:
  integration:
    partner:
      token: ${partner.token}
~~~

This configuration can replace the corresponding environment-variable placeholders from section 4; **do not configure both simultaneously without clear intent**, as property-source precedence could shadow the intended source. **configtree:** and **optional:configtree:** have different semantics: in production, avoid **optional:** just so the app starts silently when a secret mount is missing.

In Kubernetes, mount a Secret as a volume:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: integration-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: integration-service
  template:
    metadata:
      labels:
        app: integration-service
    spec:
      containers:
        - name: app
          image: registry.example.invalid/integration-service:stable
          volumeMounts:
            - name: credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: credentials
          secret:
            secretName: integration-credentials
~~~

This manifest only **references the Secret by name**; it contains no secret payload and does not create the Secret. Operators must enforce RBAC, protect the Kubernetes API/etcd, restrict volume permissions, and govern secret distribution. Kubernetes Secrets are typically **Base64-encoded in manifests/APIs**, which **is not end-to-end encryption**. Enable encryption at rest, RBAC, and cluster auditing.

**Rotation note:** when a mounted Secret volume updates, files on disk may change via the orchestrator, yet values already bound into Strings or held by WebClient/connection pools in memory **do not auto-refresh**. Plan safe reload/reconnect hooks or rolling restarts.

## 8. Secret managers and workload identity

In production, secret management options include:

- **HashiCorp Vault**;
- your platform's **cloud secret manager**;
- **Kubernetes Secrets** paired with hardened sync and access controls;
- **Spring Cloud Vault** or matching **spring.config.import**/**ConfigData** integrations to load external properties;
- workload identity/IAM or **mTLS** instead of static passwords when supported downstream.

### Benefits and boundaries

| Capability | Benefit |
| --- | --- |
| **RBAC, namespaces, policies** | Each service reads only its required secrets |
| **Auditing** | Tracks which identity requested which secret and when |
| **Versioning, rotation** | Rotate credentials without modifying source code |
| **Leases, TTLs** | Limits how long a leaked credential remains valid |
| **Workload identity** | Avoids baking a "secret to fetch secrets" into images |
| **Encryption at rest / in transit** | Protects secrets in storage and during delivery |
| **High availability** | Prevents the secret manager from becoming a single point of failure |

Even a secret manager can be misconfigured with overly broad permissions. **Never grant wildcard list/read on all secrets**, never let one consumer read credentials for unrelated systems, and never share production accounts with local developers or CI tests.

### Short-lived tokens

Instead of freezing a static token in **@ConfigurationProperties**, inject a **CredentialProvider**:

~~~java
public interface PartnerTokenProvider {
    String currentAccessToken();
}

@Bean
WebClient partnerWebClient(
        WebClient.Builder builder,
        PartnerClientProperties properties,
        PartnerTokenProvider tokenProvider) {

    ExchangeFilterFunction bearerAuthentication =
            (request, next) -> {
                ClientRequest authenticated = ClientRequest
                        .from(request)
                        .headers(headers -> headers.setBearerAuth(
                                tokenProvider.currentAccessToken()))
                        .build();
                return next.exchange(authenticated);
            };

    return builder
            .baseUrl(properties.baseUrl().toString())
            .filter(bearerAuthentication)
            .build();
}
~~~

**PartnerTokenProvider is an application-defined interface**, not a built-in Spring Boot implementation. Implementations must manage expiry caching, refresh, authorization, thundering-herd prevention, and secret-manager failures. A provider making **blocking** network calls inside a reactive WebClient filter can block the event loop: use an async/reactive mechanism or safely cache tokens refreshed on a dedicated background path. This example shows where tokens are attached; it **does not** solve all OAuth/refresh mechanics.

## 9. TLS and certificates are also connection configuration

Avoiding hard-coded URLs and passwords while **disabling TLS verification** is a critical flaw. In integration apps, addresses and secrets must pair with server identity verification.

### 9.1. Essential practices

1. Use HTTPS/TLS over networks as required by environment policy.
2. Verify hostnames and certificate trust chains; never disable certificate validation in production.
3. For **mTLS**, protect private keys and keystore passwords in secret storage.
4. Establish certificate rotation ahead of expiry and monitor handshake errors.
5. Use trusted CA/truststore sources; never auto-trust arbitrary certificates to "fix" config errors.
6. When using Spring Boot SSL bundles, supply paths, contents, and passwords externally. Live bundle reloading depends on connector and version, so test it explicitly.

### 9.2. URIs must never embed passwords

Never construct requests like:

~~~text
https://user:password@partner.example.invalid/api
https://partner.example.invalid/api?access_token=SECRET
jdbc:postgresql://host/shop?user=admin&password=SECRET
~~~

These illustrate risky formats, not real credentials. URLs easily leak into access logs, proxy logs, tracing tags, monitoring, exception messages, and browser histories. Prefer protocol headers or credential providers configured externally per environment.

**SSRF warning:** externalizing an endpoint to configuration does not make it safe if external users control the target URL. For APIs accepting dynamic destinations, enforce destination allowlists, restrict schemes/hosts, guard egress networking, and validate DNS/redirects per your threat model. Never let unverified requests override a configured **base-url**.

## 10. Rotation: replacing secrets without service downtime

Removing secrets from source code is only step one. When a password leaks, expires, or rotates on schedule, services must adopt the new secret without cascading connection failures.

~~~mermaid
flowchart TD
    A["Old secret in use by application"] --> B["Provision new credential in backend/secret manager"]
    B --> C["Allow old and new credentials concurrently during overlap if supported"]
    C --> D["Update runtime config / token provider"]
    D --> E["Refresh or rolling-restart client/connection pool"]
    E --> F["Verify health, auth failures, metrics"]
    F --> G["Revoke old credential"]
    G --> H["Audit rotation outcome"]
~~~

### 10.1. HTTP API tokens

- For short-lived tokens, use a token provider that refreshes ahead of expiration.
- Distinguish **401** (expired token) from **403** (insufficient permissions); unbounded retries on every 401 can cause loops and rate-limit lockouts.
- If `WebClient` binds a static **defaultHeaders(setBearerAuth(token))** at startup, the value never changes until the client rebuilds or the process restarts.

### 10.2. Database accounts

- **HikariCP** retains already-authenticated JDBC connections and does not re-authenticate open connections when a secret store updates.
- Once a DB password changes, existing connections may linger briefly while new connections fail if the pool still holds the old password.
- Plan **DataSource/connection pool** updates using overlapping DB credentials during transition when supported, and monitor connection acquisition/auth errors.
- Never include passwords in exception logs when troubleshooting pools.

### 10.3. Brokers and caches

- RabbitMQ, JMS, Redis, and Kafka clients keep long-lived connections with varied reconnect policies.
- Credential changes may surface only upon reconnect; a "healthy" running container does not prove the new credentials work.
- For SASL/OAuth or mTLS client certificates, coordinate rotation across consumer/producer configs, bootstrap/reconnect paths, and topic/queue permissions.
- Roll out via canary or rolling deployments so all consumers do not drop connections simultaneously.

### 10.4. Credential exposure response

If a real secret was ever committed:

1. **Immediately revoke and rotate the credential** at the issuing authority; deleting the line from code is never enough.
2. Tighten or disable unnecessary permissions.
3. Audit access logs across the credential's lifetime.
4. Identify every copy (Git history, CI artifacts, images, logs, developer machines).
5. Scrub history/copies per organizational policy after revocation; avoid breaking team workflows with uncoordinated Git history rewrites.
6. Add pre-commit/CI secret scanning to prevent recurrence.

Never paste the exposed secret value into tickets, chats, or incident reports.

## 11. CI/CD, container images, and deployment permissions

### 11.1. Pipelines must not become secret leaks

Practical controls:

- Scope secrets strictly to the **jobs, environments, and service accounts** that need them.
- Prefer **short-lived identities/credentials** (e.g. OIDC federation) when supported.
- Never echo secret env vars or enable verbose shell tracing printing commands and values.
- Never pass credentials in Maven/Gradle CLI args, artifact metadata, test reports, or build caches.
- Run **secret scanning** on commits/PRs and inspect files entering Docker build contexts.
- Run CI tests against isolated test databases/brokers/containers and test-only credentials, never production secrets.
- Separate **deploy**, **read secret**, **rotate secret**, and **audit** permissions under least privilege.

### 11.2. Docker build time vs. runtime

~~~text
Build:
  source + dependencies
  → JAR / container image
  → ZERO production secrets

Deploy:
  immutable image
  + environment configuration
  + authorized runtime secrets
  → Spring Boot process
~~~

**Dockerfile ARG/ENV is not a vault.** Values persist in image layers, build history, caches, and metadata. If a build requires private registry credentials to fetch dependencies, use **builder-supported build secret mounts or short-lived identities**, never copy tokens into a layer and delete them afterward.

### 11.3. GitOps and manifests

GitOps repositories safely store Secret names, ConfigMap references, policies, and non-secret configs. Never commit **Secret data** in cleartext or plain Base64. When using Sealed Secrets, SOPS, or encrypted manifests, govern **key management**, decryption privileges, rotation, and plaintext handling carefully.

## 12. Preventing secret leaks via Actuator, logs, and exceptions

### 12.1. Spring Boot Actuator

Actuator exposes operational endpoints such as **env**, **configprops**, **beans**, **loggers**, and **heapdump**. Sanitization masks some keys, yet **sanitization alone is not a sufficient security barrier**: custom settings, custom endpoints, logs, or heap dumps can still expose sensitive data.

Expose only required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

Beyond the exposure list, enforce **network isolation, authentication, authorization**, and telemetry scrubbing policies. Never expose **/actuator/env**, **/actuator/configprops**, or **/actuator/heapdump** publicly just to "inspect config."

### 12.2. Safe logging

Avoid:

~~~java
// Do NOT do this: can log internal URLs or secrets.
log.info("Partner config: {}", properties);
log.debug("Authorization: {}", request.headers().get("Authorization"));
log.error("Environment: {}", System.getenv());
~~~

Log **status** instead of raw values:

~~~java
log.info(
        "Partner client configured: operation={}, authConfigured={}, " +
        "requestTimeoutMs={}",
        "customer-lookup",
        tokenProvider != null,
        properties.requestTimeout().toMillis());
~~~

Even **authConfigured=true** only reports that a provider exists, not that the token is valid. Never use health checks to return secrets or log `Authorization` headers; health checks should run with minimal privileges without side effects or overloading downstreams.

### 12.3. Metrics and distributed tracing

With Micrometer/OpenTelemetry:

- Never attach tokens, usernames, sensitive tenant IDs, or credentialed URLs as metric labels.
- HTTP client metrics should record **operation/route templates**, not raw URLs with dynamic query parameters.
- Span attributes often capture server addresses and paths; scrub query parameters, `Authorization`/`Cookie` headers, and payloads.
- Classify DNS, TLS, authentication, rate-limiting, and application-level rejections distinctly.

To debug configuration values safely, log **property names, verified config sources, or non-reversible hashes** of non-sensitive identifiers; avoid unsalted hashes of low-entropy passwords, which remain sensitive.

## 13. Testing without production secrets

For integration tests, use **MockWebServer/WireMock**, **Testcontainers**, or dedicated test databases/brokers with dynamically assigned endpoints.

### 13.1. Supplying dynamic endpoints via @DynamicPropertySource

Example HTTP client test using **MockWebServer** started before the Spring test context initializes:

~~~java
@SpringBootTest
class PartnerClientIntegrationTest {

    static final MockWebServer server = startTestServer();

    @DynamicPropertySource
    static void partnerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "app.integration.partner.base-url",
                () -> server.url("/").toString());
        registry.add(
                "app.integration.partner.request-timeout",
                () -> "1s");
        registry.add(
                "app.integration.partner.token",
                () -> UUID.randomUUID().toString());
    }

    // Enqueue mock responses and assert requests hit the right endpoint,
    // carry the Authorization header, and never leak tokens in logs.
}
~~~

**startTestServer()** is a test helper you implement, ensuring the server starts before context resolution and shuts down after tests. The random UUID token is a **dummy test-only value**, never a production secret. When production requires HTTPS, use test TLS certificates or a test-only HTTP policy without disabling TLS verification in production builds.

### 13.2. Testing missing required configuration

Verify the application **refuses to start** when:

- **PARTNER_API_BASE_URL** is missing;
- the URI is malformed or uses a disallowed scheme;
- **PARTNER_API_TOKEN** is missing or blank;
- DB password is absent from required sources;
- mTLS config is missing a private key or trust material;
- timeouts are negative, pool size is 0, or values fail type conversion.

With **ApplicationContextRunner** (from Spring Boot Test), assert minimal contexts fail binding/validation without starting brokers or databases. Always test with dummy configs, never against live external services.

### 13.3. Testing one artifact across multiple environments

An essential deployment test:

~~~text
Same JAR / container image
   + environment A → mock endpoint / database A
   + environment B → mock endpoint / database B

No source code rebuild.
No production credentials or addresses in tests.
No renaming properties across environments.
~~~

Beyond property binding, test **fail-fast timing**, connection error metrics, startup/readiness health, and resilience when the secret manager is briefly unavailable.

## 14. Troubleshooting by root cause without printing config

When errors occur:

| Symptom | Possible cause | Safe verification step |
| --- | --- | --- |
| Could not resolve placeholder | Missing env var / secret file | Check property name and source; log presence (`true/false`) only |
| `BindException` / validation fail | Malformed URI, Duration, port, or pool size | Check schema and types; never dump the full `Environment` |
| `Connection refused` / DNS failure | Endpoint/port, service discovery, or network | Check egress rules, DNS, and approved host/port |
| TLS handshake error | CA, hostname, expired cert, or keystore | Inspect certificate chain and clock; never disable verification |
| HTTP 401/403 | Expired token or insufficient permissions | Check auth provider, scopes, and audit logs; never log tokens |
| DB authentication error | Wrong username/password/role or rotated secret | Verify secret version, pool lifecycle, and grants |
| Pool acquisition timeout | Slow downstream or exhausted pool | Inspect active/idle/pending counts and transaction durations |
| Broker reconnect loop | SASL/TLS/ACL, host, or un-reloaded credentials | Compare secret versions, broker audits, and client metrics |
| Fails only in production | Different profile, mount path, precedence, IAM, or egress | Check config provenance metadata |
| Still fails after rotation | Bean, socket, or pool still holds old credential | Verify reload/rolling restart and fresh connections |

**Never "fix" an error by temporarily pasting a username/password into code "to delete later."** Instead, set up proper test credential delivery, verify IAM/RBAC, and standardize startup validation.

### Short runbook for connection failures

~~~mermaid
flowchart TD
    A["Application cannot connect"] --> B{"Required config present?"}
    B -->|"No"| C["Fix config source, fail-fast"]
    B -->|"Yes"| D{"Endpoint/DNS/TLS valid?"}
    D -->|"No"| E["Fix endpoint, CA, network/egress"]
    D -->|"Yes"| F{"Credentials valid and authorized?"}
    F -->|"No"| G["Rotate/grant permissions, inspect audit"]
    F -->|"Yes"| H["Check pools, timeouts, retries, downstream health"]
    H --> I["Remediate and verify via metrics without printing secrets"]
~~~

## 15. Pre-release checklist

1. **Zero environment-specific URLs, real usernames, passwords, API keys, or private keys** hard-coded in Java, committed YAML, Dockerfiles, or pipelines.
2. Configuration separated into endpoints, operational parameters, and credentials; sensitive values supplied by approved secure stores.
3. Property names standardized; **@ConfigurationProperties** or config beans validate all required fields.
4. No weak default passwords/tokens in production; missing secrets fail fast in a controlled way.
5. Accounts provisioned under **least privilege**, isolated per environment, service, and resource type.
6. TLS and hostname verification enabled; keystores and private keys excluded from images, logs, and repos.
7. HTTP/JDBC/Redis/Kafka/JMS endpoints configured with bounded timeouts, pools/concurrency, and retry budgets.
8. Secret manager enforces auditing, rotation policies, TTLs, and tested readiness/failure modes.
9. After secret rotation, clients, pools, and brokers are verified to reconnect/rebuild cleanly instead of clinging to old credentials.
10. Actuator `env`/`configprops`/`heapdump` locked down; logs, traces, and metrics scrub `Authorization` headers, raw tokens, and sensitive connection strings.
11. CI/CD runs secret scanning, suppresses secret env output, keeps secrets out of Docker layers, and validates workload identity/RBAC.
12. Tests run exclusively against mock/ephemeral infrastructure, never production endpoints or accounts.
13. Runbooks cover credential revocation and post-incident reconciliation.
14. Early alerts exist for authentication failures, TLS expiry, connect timeouts, and secret-manager errors without exposing secret values.

**Conclusion:** keeping connection details out of source code lets a single Spring Boot application run across environments and reduces credential exposure risks. Protecting a real integration flow, however, goes beyond moving passwords to environment variables: **centralized secrets management, configuration validation, least-privilege access, TLS, rotation, testing, observability, and incident response** must be engineered as a unified system.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, placeholders, precedence, config trees, and property binding.
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): separating configuration by environment.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties` and constructor binding.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): Bean Validation and configuration validation.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, security, and management data.
- [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/): secret management with Vault via Spring.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret objects, volumes, RBAC, and security considerations.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): credential lifecycles, least privilege, rotation, and auditing.
- [The Twelve-Factor App — Config](https://12factor.net/config): separating deployment configuration from code.
