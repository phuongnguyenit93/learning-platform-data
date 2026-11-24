# Protecting Secrets, Real Data, and Connection Targets in CI Environments

A single `mvn test` command does more than evaluate assertions. When `@SpringBootTest` boots an `ApplicationContext`, Spring Boot can initialize a `DataSource`, HTTP clients, Kafka/Redis connections, cloud SDKs, schedulers, listeners, and run SQL scripts or migrations. If the CI environment accidentally inherits a real `SPRING_DATASOURCE_URL`, API key, or cloud identity, tests can **read customer records, trigger real payments or emails, write to a production database, or corrupt schemas**. A green build does not prove the environment was safe.

This topic—**Protecting Secrets, Real Data, and Connection Targets in CI Environments**—belongs to **Build and CI** under **Spring Boot - testing**. It guides you through separating trust boundaries, using synthetic data and test-only credentials, understanding Spring configuration precedence, designing a **fail-closed connection allowlist**, verifying actual connection targets, isolating outbound gateways, locking down GitHub Actions permissions, and writing negative tests. The complete **Java 17 + Spring Boot 3.5.0 + Maven + H2 + JUnit Jupiter** example contains **20 `@Test` cases** and needs no Docker, network, or real secrets.

**Core principle:** never grant a test runner permissions or targets it does not need. A `ci` profile is a configuration layer, **not** a sandbox blocking arbitrary connections. Safe CI requires **runner isolation, least privilege, data minimization, endpoint allowlists, network egress controls, and runtime verification** working together.

## 1. Threat Model: Assets and Behaviors to Prevent

| Asset Type | Examples | Risk in CI |
|---|---|---|
| **Secrets** | DB passwords, OAuth tokens, API keys, signing keys, cloud secrets, private certs | Leaked in repo, logs, test reports, artifacts, caches, stack traces, HTTP captures |
| **Real data** | PII, payment transactions, production orders, attachments, customer logs | Copied into fixtures or read/mutated by tests, violating privacy |
| **Connection targets** | JDBC/R2DBC URLs, Redis hosts, Kafka bootstrap servers, HTTP base URLs, SMTP, S3 buckets | Misconfigured tests hit and mutate live systems |
| **Runner identity** | `GITHUB_TOKEN`, OIDC credentials, IAM roles, VPC access, service accounts | Unreviewed PR code abuses elevated privileges |
| **Build pipeline** | Maven plugins, GitHub Actions, downloaded dependencies, caches | Untrusted code/scripts exfiltrate secrets or connect outbound |

Common mistakes:
- Setting `@ActiveProfiles("ci")` while letting a CI runner's `SPRING_DATASOURCE_URL` override `application-ci.properties`.
- Using `@SpringBootTest` where a custom `@Bean` constructs a `DataSource`/`HttpClient` ignoring test config.
- Running `spring.sql.init.mode=always` or Flyway against an unverified DB target.
- Checking out and executing untrusted PR code inside `pull_request_target` with write tokens or secrets.
- Calling real payment APIs in tests and treating HTTP 200 as "success".
- Copying production data into a staging server; a different hostname does not make sensitive data safe.
- Printing `System.getenv()`, full HTTP headers, or JDBC URLs to logs while debugging CI errors.
- Pointing tests at H2 while a Kafka producer or email sender still targets production.

### Separating Trust Boundaries

```text
PR source code (untrusted)
        |
        v
CI job (read-only token; no cloud/prod secrets)
        |
        +-- Spring TestContext with ci profile
        |       |
        |       +-- effective target/credential policy
        |       +-- DataSource: disposable in-memory H2
        |       +-- PartnerGateway: in-memory fake
        |
        +-- JUnit asserts actual beans and JDBC metadata
        +-- synthetic fixtures + scoped cleanup
        |
        v
Network policy: deny production network/metadata/egress
        |
        v
No direct path to production data or credentials
```

**Defense in depth:** a Java guard checks **the properties it knows about**, yet a new dependency can still open a connection through another property or client; network ACLs and absent credentials must exist **independently** of Spring code.

## 2. Managing Secrets in Builds and Tests

### 2.1. Never Store Real Secrets in the Repository

Never put passwords or API keys into:
- `src/test/resources/application-test.yml` / `application-ci.properties`.
- `pom.xml`, committed Maven `settings.xml`, Dockerfiles, Compose files, Gradle properties.
- `.github/workflows/*.yml`, hardcoded Java constants, comments, or test snapshots.
- Fake customer records, JSON payloads, SQL fixtures, or HTTP recordings.
- CLI commands embedding real tokens (visible in process listings and CI logs).
- `System.out.println(System.getenv())`, `--debug` logs, or exception messages.

Base64-encoding a secret or splitting it across string literals does not make it safe. `.gitignore` only stops untracked files; any credential committed to Git history must be **rotated/revoked**, followed by reviewing logs, artifacts, forks, and handling the incident. Once artifacts or clones exist, deleting a file in a later commit does not erase it elsewhere.

### 2.2. Different Jobs Have Different Trust Levels

| Job | Is Code Trusted? | Appropriate Permissions |
|---|---|---|
| Forked PR | No | Zero repo/cloud/prod secrets; minimal read-only `GITHUB_TOKEN` |
| Internal branch PR | Still needs review—PRs can edit tests/plugins | Zero production secrets; network isolated |
| Push to protected branch | Per review policy | Dedicated credentials strictly for tasks requiring them |
| Approved deployment environment | Trusted post-approval | Short-lived OIDC/cloud identity scoped to that target |
| Approved sandbox integration | Trusted job, isolated environment | Test-only credentials with TTL, quotas, and auditing |

GitHub Actions `pull_request` from forks omits repository secrets by default, yet never assume every PR in every repository is secret-free because events and permission settings vary. **Avoid checking out and running untrusted PR heads inside `pull_request_target` with secrets or write tokens**: even `mvn test` executes PR-modified code, plugins, and scripts. Separate unreviewed code execution from privileged workflows.

### 2.3. Inject Credentials Only When Genuinely Needed

When hitting an isolated external sandbox (containing zero production data), enforce:
1. A dedicated **least-privilege** service account / test tenant;
2. Short-lived OIDC/workload identity bound to repo/ref/environment and audience;
3. Approval/protected environments for jobs accessing credentials;
4. Token expiry/rotation and job identity auditing;
5. Network policies allowing only approved hosts and ports;
6. Synthetic inputs and cleanup scoped by test-run ID;
7. Strictly forbidding tokens inside artifacts or caches.

Masking is only **display mitigation**: GitHub Actions log masking does not protect secrets that are split, encoded, hashed, or transformed. Never expose secrets to untrusted code and rely on masking to stop exfiltration.

## 3. Spring Boot Externalized Configuration: Why a Profile Does Not Lock Targets

Spring Boot reads configuration from many sources: `application.properties`/`yaml`, profile-specific files, JVM `-D` system properties, OS environment variables, `SPRING_APPLICATION_JSON`, command-line args, `@TestPropertySource`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, and custom property sources.

Example:

```properties
# src/test/resources/application-ci.properties
spring.datasource.url=jdbc:h2:mem:ci_safety;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
app.partner.base-url=http://127.0.0.1:9
```

Yet a runner might export:

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://db.example.invalid:5432/production
```

**OS environment variables normally take precedence over Config Data.** Activating `@ActiveProfiles("ci")` does not stop overrides. You must also account for `spring.datasource.hikari.jdbc-url`, custom `DataSource` beans, `spring.r2dbc.url`, `spring.kafka.bootstrap-servers`, `spring.data.redis.host`, HTTP client configs, and cloud SDK configurations. **No single property governs every network destination.**

### 3.1. Test Mechanisms That Can Alter Context Targets

| Mechanism | Purpose | What to Check |
|---|---|---|
| `@ActiveProfiles("ci")` | Selects profile | Does not block higher-precedence sources overriding URLs |
| `@SpringBootTest(properties=...)` | Sets test-specific properties | Can override file settings; inspect actual context |
| `@TestPropertySource` | Adds/overrides test properties | Never point to real URLs for convenience |
| `@DynamicPropertySource` | Injects dynamic ports/URLs (e.g., Testcontainers) | Verify container lifecycle and real URL source |
| `@ServiceConnection` | Supplies `ConnectionDetails` from containers | `ConnectionDetails` can override connection properties |
| `@MockitoBean` / test fake | Replaces outbound dependency bean | Does not stop other code instantiating raw HTTP clients |
| `@Profile("ci")` | Selects beans by environment | Verify the real injected bean type |
| `@ConditionalOnProperty` | Toggles components | Do not assume a disabled bean prevents outbound calls elsewhere |

Spring Boot 3.5 supports `@ServiceConnection` for Testcontainers: per documentation, its `ConnectionDetails` **take precedence over** connection-related properties. A guard checking only `spring.datasource.url` **is insufficient** when apps connect through another path. For custom `DataSource` beans or multiple clients, verify the actual datasource/container/broker identity and block outbound egress at the runner level.

### 3.2. Policy Error Logs Must Be Sanitized

Never do this:

```java
System.out.println(
    "DB password: " + environment.getProperty(
        "spring.datasource.password"));
```

That is an anti-pattern snippet, absent from the runnable project. Instead, enforce the policy and throw a fixed error:

```java
if (unsafe) {
    throw new IllegalStateException(
            "CI database target rejected");
}
```

Never embed raw JDBC URLs, usernames/passwords, tokens, or `Authorization` headers in failure messages. For incident triage, log only the **rejected config category**, job identifier, and policy version—never the secret value. Assertion failures can also print actual values in diffs, so avoid asserting directly on sensitive raw strings.

## 4. Protecting Real Data

### 4.1. Use Synthetic Fixtures Exclusively

Generate data that is unmistakably synthetic:
- `FAKE-...` as markers/test-run IDs; `UUID`s to avoid collisions.
- Reserved domains `example.invalid`/`example.test`; never send real emails.
- `Clock.fixed(...)`, seeded randomness, or factories for deterministic results.
- In-memory H2 or fresh isolated Testcontainers databases.
- Dedicated test tenants/accounts/sandboxes and test-only schemas/buckets/topics.
- Keep real PII out of Surefire XML, snapshots, and traces.

**Pseudonymization is not anonymization.** Swapping display names while keeping real emails, phone numbers, addresses, free-text fields, internal account IDs, or transaction links still allows re-identification. A staging server cloned from production remains sensitive data. If production-like data is ever strictly required, enforce formal approval, minimization, audited redaction, TTL/retention limits, and strict access controls.

### 4.2. Startup Scripts and Migrations Can Corrupt Real Data Too

Dangerous settings if aimed at the wrong target:
- Hibernate `spring.jpa.hibernate.ddl-auto=create`, `create-drop`, or `update`.
- `spring.sql.init.mode=always` with `schema.sql`/`data.sql`.
- Flyway or Liquibase applying migrations during `ApplicationContext` refresh.
- Seed/cleanup scripts running `TRUNCATE` or `DELETE` without `WHERE`.
- Startup schedulers or listeners causing external side effects.

**`spring.sql.init.mode=never` disables only Spring Boot's script initialization**, not Hibernate schema generation, Flyway, Liquibase, or business SQL. Never rely on that single switch to protect a real DB. Always provision a disposable database first, verify the target, and only then run migrations/test writes.

### 4.3. Properly Scoped Cleanup

Tests inserting rows should tag them with the current invocation's `run_id`, synthetic `reference`, or tenant key. Query and delete with `WHERE run_id = ?` inside `finally`/`@AfterEach` without swallowing cleanup failures silently. `@Transactional` rolls back within the same transaction/thread, whereas `REQUIRES_NEW`, `@Async`, server threads, and external side effects commit independently. `@DirtiesContext` never deletes data committed to an external DB.

## 5. Protecting Connection Targets

| System | Target That Could Leak | CI-Safe Replacement |
|---|---|---|
| JDBC | `spring.datasource.url` | In-memory H2 `jdbc:h2:mem` or disposable DB container |
| R2DBC | `spring.r2dbc.url` | Dedicated reactive DB container or fake adapter |
| Redis | `spring.data.redis.host/port` | Isolated Redis container/fake |
| Kafka | `spring.kafka.bootstrap-servers` | Testcontainers/embedded broker or fake producer |
| RabbitMQ | `spring.rabbitmq.addresses` | Disposable RabbitMQ/fake |
| SMTP | `spring.mail.host` | Mail capture server or fake sender |
| HTTP APIs | `app.partner.base-url` | In-process fake or loopback mock server |
| Cloud SDK | Bucket/account/region/endpoint | Test-only account and short-lived identity |

**Never treat `localhost` as automatically sandboxed**: it can point to another service on a shared runner or container namespace. When using network mocks, boot the mock server explicitly and inject its exact port/identity. In the sample project below, `http://127.0.0.1:9` is merely an **uninvoked sentinel**; the `ci` profile uses a fake bean with no HTTP client. Never rely on port 9 being closed as your system's security boundary.

## 6. Runnable Project: Java 17 + Spring Boot 3.5 + JUnit

Sample design:
1. `application-ci.properties` sits only in `src/test/resources`, connecting to in-memory H2.
2. `CiDestinationPolicy` inspects **resolved values** and enforces an exact allowlist for DB, partner URL, and credentials.
3. `CiStartupGuard` is a `BeanFactoryPostProcessor` active under the `ci` profile, failing closed **before regular singleton DataSource creation** in the sample.
4. `FakePartnerGateway` is active in CI; `HttpPartnerGateway` is registered only under `!ci`.
5. `CiProbeService` accepts only `FAKE-...` markers and writes to test table `ci_probe`.
6. Pure unit tests check negative policy cases; integration tests verify **actual JDBC metadata**, bean selection, synthetic writes, and cleanup.

### 6.1. Directory Tree

```text
ci-safety-demo/
├── pom.xml
├── .github/workflows/safe-ci.yml
└── src/
    ├── main/java/com/example/cisafety/
    │   ├── CiSafetyApplication.java
    │   ├── CiDestinationPolicy.java
    │   ├── CiStartupGuard.java
    │   ├── PartnerGateway.java
    │   ├── FakePartnerGateway.java
    │   ├── HttpPartnerGateway.java
    │   ├── ProbeReceipt.java
    │   └── CiProbeService.java
    └── test/
        ├── java/com/example/cisafety/
        │   ├── CiDestinationPolicyTest.java
        │   └── CiSafetyIntegrationTest.java
        └── resources/
            ├── application-ci.properties
            └── schema-ci.sql
```

Outside the `ci` profile, real deployments must provide production credentials and datasources externally, with zero real passwords/hosts in source. `HttpPartnerGateway` compiles cleanly yet is never instantiated during CI tests.

### 6.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ci-safety-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <!-- H2 used in tests; never packaged into production runtime. -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-jdbc` supplies `JdbcTemplate`, `DataSource`, and HikariCP; `test`-scoped H2 stays strictly on the test classpath. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring TestContext. The Spring Boot parent manages compatible versions. The sample needs neither Docker nor Internet access once Maven dependencies are cached.

### 6.3. Boot Application

File **`src/main/java/com/example/cisafety/CiSafetyApplication.java`**:

```java
package com.example.cisafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiSafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiSafetyApplication.class, args);
    }
}
```

### 6.4. Destination Policy with Redacted Errors

File **`src/main/java/com/example/cisafety/CiDestinationPolicy.java`**:

```java
package com.example.cisafety;

public final class CiDestinationPolicy {

    public static final String CI_DB_URL =
            "jdbc:h2:mem:ci_safety;"
            + "DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE";

    public static final String CI_PARTNER_URL =
            "http://127.0.0.1:9";

    private CiDestinationPolicy() {
    }

    public static void verify(
            String jdbcUrl,
            String username,
            String password,
            String partnerUrl,
            String partnerApiKey) {

        if (!CI_DB_URL.equals(jdbcUrl)) {
            throw new IllegalStateException(
                    "CI database target rejected");
        }

        if (!"sa".equals(username)
                || password == null
                || !password.isEmpty()) {
            throw new IllegalStateException(
                    "CI database credentials rejected");
        }

        if (!CI_PARTNER_URL.equals(partnerUrl)) {
            throw new IllegalStateException(
                    "CI outbound target rejected");
        }

        if (partnerApiKey != null
                && !partnerApiKey.isBlank()) {
            throw new IllegalStateException(
                    "CI external credential rejected");
        }
    }
}
```

**Why an exact allowlist?** Checking only `jdbcUrl.startsWith("jdbc:h2:mem:")` misses H2 URLs carrying `INIT` clauses. The sample permits one exact JDBC URL, `sa` with an empty password, the partner sentinel, and **no** API key. PostgreSQL/MySQL, file/TCP H2, and any unapproved variation are rejected. In apps with multiple valid containers/DBs, define an explicit **approved target set** rather than hardcoding one URL, while remaining fail-closed.

Policy exception messages name only the **config category**, never echoing the supplied URL, username, password, or token. That is a practical security-logging requirement.

### 6.5. Validating Effective Properties Before Singleton DataSource Creation

File **`src/main/java/com/example/cisafety/CiStartupGuard.java`**:

```java
package com.example.cisafety;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
@Profile("ci")
public class CiStartupGuard {

    @Bean
    static BeanFactoryPostProcessor requireSafeCiTargets() {
        return beanFactory -> {
            Environment env = beanFactory.getBean(Environment.class);

            CiDestinationPolicy.verify(
                    env.getProperty("spring.datasource.url"),
                    env.getProperty("spring.datasource.username"),
                    env.getProperty("spring.datasource.password"),
                    env.getProperty("app.partner.base-url"),
                    env.getProperty("app.partner.api-key"));
        };
    }
}
```

Spring executes `BeanFactoryPostProcessor` during bean-definition processing prior to instantiating normal application singletons. A `static` `@Bean` avoids instantiating the configuration class early. If the CI environment supplies a rogue `SPRING_DATASOURCE_URL` or non-empty `APP_PARTNER_APIKEY`, context startup **FAILS** before creating the sample's `DataSource`.

**Clear limitations:** another `BeanFactoryPostProcessor`, a manually constructed `DataSource`, Testcontainers `@ServiceConnection`, or an earlier outbound call can bypass this guard. Never treat it as a sandbox for arbitrary Spring applications; enforce egress blocks and strip production secrets at the runner level. Integration tests must also verify the **actual connection** to catch overridden configs.

### 6.6. Gateway Interface and Fake Implementation

File **`src/main/java/com/example/cisafety/PartnerGateway.java`**:

```java
package com.example.cisafety;

public interface PartnerGateway {
    String acknowledge(String marker);
}
```

File **`src/main/java/com/example/cisafety/FakePartnerGateway.java`**:

```java
package com.example.cisafety;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("ci")
public class FakePartnerGateway implements PartnerGateway {

    @Override
    public String acknowledge(String marker) {
        return "SIMULATED:" + marker;
    }
}
```

The `@Profile("ci")` fake **contains no HTTP client**. When unit/integration tests invoke the business service, responses stay inside the JVM with no code path capable of sending external requests. This is safer than instantiating the production client aimed at a dummy host, since production clients can redirect, retry, or perform unwanted DNS lookups.

### 6.7. HTTP Gateway Outside CI

File **`src/main/java/com/example/cisafety/HttpPartnerGateway.java`**:

```java
package com.example.cisafety;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("!ci")
public class HttpPartnerGateway implements PartnerGateway {

    private final HttpClient client = HttpClient.newHttpClient();
    private final URI endpoint;
    private final String apiKey;

    public HttpPartnerGateway(
            @Value("${app.partner.base-url}") String baseUrl,
            @Value("${app.partner.api-key}") String apiKey) {
        this.endpoint = URI.create(baseUrl);
        this.apiKey = apiKey;

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null
                || endpoint.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Partner endpoint must use HTTPS host");
        }
    }

    @Override
    public String acknowledge(String marker) {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(3))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "text/plain")
                .POST(HttpRequest.BodyPublishers.ofString(
                        marker, StandardCharsets.UTF_8))
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                        "Partner returned non-success status");
            }
            return response.body();
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Partner request failed", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Partner request interrupted", ex);
        }
    }
}
```

This class is registered only when **the `ci` profile is inactive**. It illustrates that secrets must come from **external configuration**, never hardcoded; when `app.partner.api-key` is absent, non-CI startups should fail rather than falling back to a default key. Production code must also enforce TLS/server identity, host allowlists, DNS/redirect/SSRF protections, retries, and proper token management; checking `https` here **is not enough** to permit arbitrary hosts. CI tests assert this bean is **never registered**.

### 6.8. Test-Only Probe and Receipt

File **`src/main/java/com/example/cisafety/ProbeReceipt.java`**:

```java
package com.example.cisafety;

public record ProbeReceipt(String id, String acknowledgment) {
}
```

File **`src/main/java/com/example/cisafety/CiProbeService.java`**:

```java
package com.example.cisafety;

import java.util.UUID;

import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
@Profile("ci")
public class CiProbeService {

    private final JdbcTemplate jdbc;
    private final PartnerGateway partner;

    public CiProbeService(
            JdbcTemplate jdbc, PartnerGateway partner) {
        this.jdbc = jdbc;
        this.partner = partner;
    }

    public ProbeReceipt recordSynthetic(String marker) {
        if (marker == null
                || !marker.matches("FAKE-[A-Z0-9-]{1,40}")) {
            throw new IllegalArgumentException(
                    "Synthetic marker required");
        }

        String id = "ci-" + UUID.randomUUID();
        jdbc.update(
                "INSERT INTO ci_probe (id, marker) VALUES (?, ?)",
                id, marker);

        return new ProbeReceipt(id, partner.acknowledge(marker));
    }
}
```

This service exists only under the `ci` profile; inputs must start with `FAKE-`. It inserts into `ci_probe` and calls the fake `PartnerGateway`. It exists strictly to demonstrate **synthetic data + scoped cleanup**, not production transaction logic.

### 6.9. Test-Only Properties and Schema

File **`src/test/resources/application-ci.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:ci_safety;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema-ci.sql

# Sentinel only; FakePartnerGateway makes no network calls.
app.partner.base-url=http://127.0.0.1:9
```

File **`src/test/resources/schema-ci.sql`**:

```sql
CREATE TABLE ci_probe (
    id VARCHAR(80) PRIMARY KEY,
    marker VARCHAR(80) NOT NULL
);

CREATE INDEX idx_ci_probe_marker
    ON ci_probe(marker);
```

These properties and scripts sit on the test classpath only. `spring.sql.init.mode=always` is safe **in this sample protected by the H2 target guard**, yet that very property is dangerous if copied into a context pointing to a real DB. Never use `@DirtiesContext` to clean up external databases. When multiple tests/contexts share an H2 database name, manage lifecycles and isolate DB names or use disposable Testcontainers.

### 6.10. Pure Unit Tests: Rejecting Unexpected URLs and Credentials

File **`src/test/java/com/example/cisafety/CiDestinationPolicyTest.java`**:

```java
package com.example.cisafety;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CiDestinationPolicyTest {

    private static void check(
            String db, String user, String password,
            String partner, String apiKey) {
        CiDestinationPolicy.verify(
                db, user, password, partner, apiKey);
    }

    @Test
    void exactCiTargetsWithoutSecretAreAccepted() {
        assertThatCode(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .doesNotThrowAnyException();
    }

    @Test
    void missingDatabaseUrlIsRejected() {
        assertThatThrownBy(() -> check(
                null, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected");
    }

    @Test
    void postgresUrlIsRejectedBeforeConnecting() {
        assertThatThrownBy(() -> check(
                "jdbc:postgresql://db.example.invalid:5432/prod",
                "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected");
    }

    @Test
    void fileBasedH2IsRejected() {
        assertThatThrownBy(() -> check(
                "jdbc:h2:file:./test-db",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void tcpH2ServerIsRejected() {
        assertThatThrownBy(() -> check(
                "jdbc:h2:tcp://127.0.0.1:9092/testdb",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void additionalH2InitOptionsAreRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL
                    + ";INIT=CREATE SCHEMA X",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void unexpectedDatabaseUsernameIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "not-sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database credentials rejected");
    }

    @Test
    void nonemptyDatabasePasswordIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "dummy-secret",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database credentials rejected");
    }

    @Test
    void remotePartnerUrlIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                "https://api.example.invalid", null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI outbound target rejected");
    }

    @Test
    void differentLoopbackPortIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                "http://127.0.0.1:8080", null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void unexpectedPartnerApiKeyIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL,
                "synthetic-token"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI external credential rejected");
    }

    @Test
    void errorDoesNotPrintConnectionString() {
        String suspicious =
                "jdbc:postgresql://db.example.invalid/sensitive";
        assertThatThrownBy(() -> check(
                suspicious, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected")
                .hasMessageNotContaining("sensitive");
    }
}
```

**12 `@Test` cases**: one happy path plus negative tests for missing URL, Postgres/file-H2/TCP-H2 URLs, extra H2 init options, unexpected username/password, remote endpoint, different port, injected token, and sanitized error messages. All URLs and keys are synthetic with zero real hosts or credentials.

### 6.11. Spring Integration Tests: Actual DataSource, Fake, and Cleanup

File **`src/test/java/com/example/cisafety/CiSafetyIntegrationTest.java`**:

```java
package com.example.cisafety;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.Locale;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("ci")
class CiSafetyIntegrationTest {

    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private PartnerGateway partner;

    @Autowired
    private CiProbeService probe;

    @Test
    void ciProfileIsActive() {
        assertThat(environment.acceptsProfiles(
                Profiles.of("ci"))).isTrue();
    }

    @Test
    void actualConnectionPointsToH2Memory()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .startsWith("jdbc:h2:mem:ci_safety");
            assertThat(connection.getMetaData()
                    .getDatabaseProductName()).isEqualTo("H2");
        }
    }

    @Test
    void fakeGatewayIsTheOnlySelectedImplementation() {
        assertThat(partner)
                .isInstanceOf(FakePartnerGateway.class);
        assertThat(partner.acknowledge("FAKE-OK"))
                .isEqualTo("SIMULATED:FAKE-OK");
    }

    @Test
    void productionHttpGatewayIsAbsent() {
        assertThat(context.getBeansOfType(
                HttpPartnerGateway.class)).isEmpty();
    }

    @Test
    void resolvedSettingsAreVerified() {
        CiDestinationPolicy.verify(
                environment.getProperty("spring.datasource.url"),
                environment.getProperty("spring.datasource.username"),
                environment.getProperty("spring.datasource.password"),
                environment.getProperty("app.partner.base-url"),
                environment.getProperty("app.partner.api-key"));
    }

    @Test
    void syntheticRowIsInsertedAndCleaned() {
        String marker = "FAKE-"
                + UUID.randomUUID().toString()
                    .replace("-", "")
                    .substring(0, 12)
                    .toUpperCase(Locale.ROOT);
        try {
            ProbeReceipt receipt = probe.recordSynthetic(marker);
            assertThat(receipt.id()).startsWith("ci-");
            assertThat(receipt.acknowledgment())
                    .isEqualTo("SIMULATED:" + marker);

            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker);
            assertThat(count).isEqualTo(1L);
        } finally {
            jdbc.update(
                "DELETE FROM ci_probe WHERE marker = ?",
                marker);
        }
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker)).isZero();
    }

    @Test
    void nonSyntheticMarkerCannotInsert() {
        String marker = "person@example.invalid";
        assertThatThrownBy(() ->
                probe.recordSynthetic(marker))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker)).isZero();
    }

    @Test
    void apiKeyIsAbsentFromCiEnvironment() {
        assertThat(environment.getProperty(
                "app.partner.api-key")).isNull();
    }
}
```

**8 `@Test` cases**: active profile, actual JDBC URL + DB engine, fake bean, absence of production HTTP bean, resolved settings verification, synthetic insert/cleanup, non-synthetic marker rejection, and API key absence. **12 unit + 8 integration = 20 tests.**

In the demo, the actual JDBC URL is synthetic H2, so the test asserts it directly. In real projects with sensitive hostnames or secrets, assertion frameworks can print actual values on failure: write a boolean helper returning a **sanitized failure reason** instead of exposing URLs or credentials in CI logs. **Inspect actual connections only inside isolated runners already cleared by the guard**; never connect out to production just to prove it was production.

### 6.12. GitHub Actions Workflow Receiving Zero Production Secrets

File **`.github/workflows/safe-ci.yml`**:

```yaml
name: Isolated Spring tests

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SPRING_PROFILES_ACTIVE: ci
      MAVEN_OPTS: -Dfile.encoding=UTF-8

    steps:
      - name: Checkout without persistent credentials
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run isolated tests
        run: mvn --batch-mode --no-transfer-progress test
```

The job references no `secrets.*`, requests no `id-token: write`, never uses `pull_request_target`, performs no deployments, and executes no migrations against real databases. `GITHUB_TOKEN` stays at `contents: read`. **YAML alone does not create a network sandbox**: GitHub-hosted runners generally have Internet access; block production networks and identities independently. Self-hosted runners especially require ephemeral isolation, no lingering credentials/containers across jobs, and must never sit directly inside a production VPC when running untrusted PRs.

`actions/checkout@v4` and `actions/setup-java@v4` are major-version tags for illustration, not commit SHA pinning. Production CI should stay on maintained versions, pin actions to reviewed commit SHAs when policy requires, and audit Maven plugins/dependencies.

### 6.13. Running Maven and Expected Outcomes

From the POM directory with JDK 17+ and Maven:

```bash
mvn --batch-mode --no-transfer-progress test
mvn -Dtest=CiDestinationPolicyTest test
mvn -Dtest=CiSafetyIntegrationTest test
```

Expected: **20 JUnit tests PASS** in an environment free of unintended overrides. No Docker or HTTP endpoints needed. If a CI runner injects unexpected `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_PASSWORD`, `APP_PARTNER_BASEURL`, or `APP_PARTNER_APIKEY`, the guard **intentionally aborts startup**; fix the runner's config/permissions instead of deleting the guard to make the build green.

This example was reviewed against Spring Boot 3.5 and Java 17, **not executed with Maven during authoring**. Exact stdout is omitted because Maven/Spring logs vary by environment. When adapting to a real system, extend the policy to every datasource, cloud SDK, Kafka/Redis, and HTTP/SMTP destination, and test on a runner stripped of production network access and credentials.

## 7. Additional Protections Outside the Sample

### 7.1. Production Credentials Never Present on the Runner

Never check only `app.partner.api-key` and assume all secrets are gone. Other leaks include `AWS_SECRET_ACCESS_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, kubeconfigs, Maven registry tokens, credential files, and cloud instance metadata endpoints. Runner policies must **attach zero secret mounts/roles** to PR jobs, block access to metadata endpoints, and lock down cloud IAM permissions.

### 7.2. Checking External Data Stores and Brokers

If the application uses:
- Kafka producers: use fake/embedded brokers/Testcontainers; verify `bootstrap.servers`, topic prefixes, and credentials.
- Redis: test-only Redis container, namespace keys by run ID, set TTLs, and clean up.
- Email: fake `JavaMailSender` or mail capture server; never email real customers.
- HTTP: WireMock/MockWebServer or fake gateway; assert payloads and **zero outbound calls to real hosts**.
- R2DBC: verify `ConnectionFactory` points to the test container / reactive H2 target.
- Object storage: disposable test bucket/account, denying production bucket delete/list permissions.
- Scheduled jobs: disable in CI unless under test, since they can fire **at context startup** before any JUnit test body runs.

`@MockitoBean` swaps **one specific Spring bean**: it does not stop other classes from calling `HttpClient` or `new KafkaProducer`. Back it with OS/network egress denial outside the JVM.

### 7.3. Testcontainers and @ServiceConnection

When real PostgreSQL SQL semantics are needed, use a disposable container:

```java
// Design snippet: requires Testcontainers dependencies, Docker,
// proper imports, and assertions; not part of the runnable demo.
@Testcontainers
@SpringBootTest
class PostgresSandboxTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot 3.5 requires `spring-boot-testcontainers` for `@ServiceConnection`, plus the Testcontainers PostgreSQL, JUnit integration, and PostgreSQL JDBC driver modules. Never fall back to production URLs/credentials for convenience. `@ServiceConnection` can override connection-related properties, so verify **container identity and actual connection**. If the container fails to start or uses the wrong image/tag, the test must fail rather than falling back to an external DB.

Container lifecycles must align with the Spring TestContext cache so cached DataSources never point to stopped containers. Pin image versions/digests per supply-chain policy in CI.

### 7.4. Never Let Test Reports Become a Leak Channel

Files that can leak secrets or real data: Maven Surefire XML, screenshots, logs, request/response snapshots, heap dumps, HTTP recordings, SQL debug logs, and cloud traces. Use synthetic data, curb verbose logging, never upload artifacts carrying secrets, enforce short retention, audit artifact download permissions, and never rely on GitHub masking alone when assertion failures print transformed or encoded strings.

## 8. When Integration Requires an External Sandbox

Some behaviors cannot be simulated by H2 or mocks: PostgreSQL lock/index mechanics, TLS/mTLS, IAM policies, Kafka partition ordering, or provider-specific APIs. Even then, **you still need zero production data or secrets** when designed properly:

1. Dedicated sandbox/test accounts containing zero customer data.
2. Resource names scoped by `test-run-id`/namespace with TTLs.
3. Jobs run only from reviewed code behind protected environments/approvals when credentials are required.
4. Short-lived OIDC credentials, least privilege, and network allowlists for the sandbox.
5. Synthetic inputs and test accounts; never send real emails or money.
6. Bounded timeouts, retry limits, idempotency keys, explicit cleanup, and auditing.
7. Verify targets not only by URL, but by **account/project/tenant/namespace identity**.
8. Never run destructive migrations on a shared staging DB holding a production snapshot.
9. Enforce quotas and rate limits to prevent runaway load or bills.
10. Separate read-only smoke probes from data-mutating contract tests.

"Staging" is **an environment name**, not a guarantee its data is anonymized. A staging host may still contain production PII, backups, or copied tokens.

## 9. Failure and Action Matrix

| Scenario | Symptom | Action |
|---|---|---|
| Unexpected `SPRING_DATASOURCE_URL` in CI | Guard reports `database target rejected` | Remove override, inspect secret injection, never connect |
| File/TCP H2 instead of mem H2 | URL fails exact allowlist | Switch to disposable in-memory or container DB |
| Test SQL startup runs against real DB | DDL/migrations hit wrong DB | Verify before init, enforce network/permission deny, isolate DB |
| Partner API key injected into PR job | Guard reports `credential rejected` | Revoke secret access on untrusted jobs |
| `HttpPartnerGateway` loaded under `ci` profile | Bean-selection test FAILS | Check profiles/component scans/fake config |
| H2 configured yet Kafka still sends outbound | Broker config outside policy | Use fake/isolated broker and egress deny |
| `@ServiceConnection` swaps actual `DataSource` | Property check PASSES yet metadata differs | Verify `ConnectionDetails`/actual engine/identity |
| Test only PASSES with production network | Broken unit fixtures / missing fake | Replace with sandbox/test double |
| JDBC rollback fails to clear data | `REQUIRES_NEW`, async, or server thread | Scoped cleanup / isolated DB |
| Surefire logs contain headers/tokens | CI artifact leak | Sanitize, revoke exposed tokens, restrict uploads |
| PR job uses `pull_request_target` + untrusted checkout | Privilege boundary breached | Switch to `pull_request`; separate privileged jobs |
| Self-hosted runner retains credentials | Untrusted code reads host identity | Ephemeral isolation, remove mounts, no prod VPC |
| Secret removed from HEAD yet still in Git history | Credential remains usable | Rotate/revoke and run incident review |
| Production JDBC URL printed in assertion diff | Exposes hostname/DB name | Emit sanitized policy codes only |
| Enabling all Actuator endpoints in CI to debug | Exposes env/credentials | Allowlist exposure and roles |
| Unpinned Docker `latest` tags | Non-reproducible / supply-chain risk | Pin version/digest and review |
| `@DirtiesContext` on every test | Slow builds, never cleans external DBs | Clean up by run ID, fix fixture lifecycle |

## 10. CI Protection Checklist

- [ ] Inventoried all secrets, real-data sources, and network destinations used by the app.
- [ ] Jobs running PR code receive zero production secrets, write tokens, or cloud identities.
- [ ] CI workflows enforce least-privilege permissions and never run untrusted code in privileged `pull_request_target` workflows.
- [ ] Zero hardcoded production credentials or hostnames in Java, YAML, POM, or test resources.
- [ ] Zero production data copied into snapshots, fixtures, or traces.
- [ ] `application-ci.properties` contains only synthetic H2 and a sentinel endpoint.
- [ ] Understood Spring configuration precedence: env/system/test/dynamic sources can override files.
- [ ] Guard executes before normal `DataSource` creation and fails closed on unexpected URLs/credentials.
- [ ] Exception/failure messages never echo secrets or raw URLs.
- [ ] Tests verify actual JDBC engine/URL **only inside an isolated environment**.
- [ ] Tests verify the fake gateway bean is injected and the production outbound gateway is absent in CI.
- [ ] Accounted for Kafka, Redis, R2DBC, email, cloud SDKs, and startup schedulers.
- [ ] H2 never uses file/TCP/`INIT` options unless explicitly allowed by policy.
- [ ] Flyway/Liquibase/JPA DDL and SQL scripts run solely against disposable DBs.
- [ ] Test inputs/rows are synthetic; cleanup deletes only test-owned data.
- [ ] Parallel tests avoid global truncates and shared mutable state.
- [ ] `@Transactional` is never assumed to roll back all external operations.
- [ ] Testcontainers use test-only resources and never fall back to production credentials.
- [ ] `@ServiceConnection`, custom `DataSource`, and `ConnectionFactory` verify actual endpoints/identities.
- [ ] Network egress firewalls and runner isolation block production access independently of Java guards.
- [ ] Logs and masking are never relied upon as the sole credential protection.
- [ ] CI artifacts, Surefire XML, caches, and captures are audited for sensitive data and retention.
- [ ] Privileged sandbox integrations run separately with approvals, short-lived OIDC identities, and auditing.
- [ ] Repeated test runs leave zero residue or external side effects.
- [ ] When a guard fails, fix config/secret scoping rather than deleting tests or bypassing policy.

**Conclusion:** protecting CI requires guarding **secrets**, **real data**, and **connection targets** together. Use synthetic data, disposable DBs/containers, fake outbound services, policies validating resolved configuration, integration assertions over actual clients, and runners/networks with no path to production. **A test that FAILS before connecting to the wrong target is a successful defense.** Never trade away these safeguards for a false green build.

### Official References

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — Testcontainers and @ServiceConnection](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [GitHub Actions — Secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [GitHub Actions — Compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners)