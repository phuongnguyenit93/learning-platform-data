# Designing Shared Configuration with local, test, and prod Profiles in Spring Boot

## 1. Objectives of the Integrated Practice

When developing a Spring Boot application, we often need to run the **same codebase** in multiple contexts:

- **local**: developers running on personal machines, prioritizing fast feedback, simulated addresses, and observability.
- **test**: automated test suites running on CI or in an IDE, requiring repeatability, isolation from real services, and independence from local machine setup.
- **prod**: real deployment, prioritizing safety, deployment-supplied configuration, secret protection, and stable operation.

These three contexts differ in input data, yet they should not lead to three separate codebases or three separate Spring Boot applications.

A solid configuration design must answer:

1. Which properties are **identical** across all environments?
2. Which properties are allowed to **vary by profile**?
3. Which properties must be **supplied externally**, never appearing as real secrets in the repository?
4. How do we ensure tests never accidentally connect to production systems?
5. How do we tell which profile is active and which value is winning?
6. How do we verify values bound by the Binder into Java objects?
7. How do we add a new environment without copy-pasting hundreds of lines of YAML?
8. When a value is wrong, should we fix the common file, the profile file, or the deployment configuration?

This lab builds a simulated **Order Dispatch Configuration Lab** project. The application has a shared configuration group for dispatching orders to an external system, batch processing, and operational metadata. To stay focused on Externalized Configuration, the sample service only builds a processing plan and **never actually sends HTTP requests**.

Desired outcome:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-prod.yml

src/test/resources/
  application-test.yml

Java code:
  @ConfigurationProperties(prefix = "app")
  AppSettings
  DispatchPlanService

Runtime:
  local -> local app settings
  test  -> isolated app settings
  prod  -> production app settings + ENV/secret
```

**Principle:** one build, many deployment configurations. Shared values are defined in one place; profile files declare only intentional differences.

## 2. What Is a Spring Profile?

A Spring profile is a name representing a group of conditional settings within `Environment`.

Examples:

```text
local
test
prod
```

When the `local` profile is active, Spring Boot considers configuration sources targeting `local` and beans conditioned on that profile. The same applies to `test` and `prod`.

A profile has two common but distinct effects:

**A. Selecting Config Data by profile**

```text
application.yml
application-local.yml
application-test.yml
application-prod.yml
```

When the `prod` profile is active, Boot can load `application.yml` along with `application-prod.yml` from configured locations.

**B. Selecting beans conditionally by profile**

```java
@Profile("local")
@Bean
OutboundGateway localGateway() { ... }
```

`@Profile` controls bean registration; `application-local.yml` supplies property values. They are often used together, yet they are **not the same mechanism**.

In an application, you can activate a profile that has no corresponding file, or have a profile file with no `@Profile`-annotated beans.

### 2.1. The Default Profile

When no profile is active, Spring Boot uses its default profile mechanism. The standard default profile name is `default`. You can set `spring.profiles.default` in a **non-profile-specific** configuration document if truly needed.

Do not assume `local` turns on automatically just because `application-local.yml` exists. A file's presence does not imply activation.

### 2.2. "Environment" Does Not Necessarily Equal Profile

An organization may run multiple production clusters, each with different regions, namespaces, and secrets, all using the `prod` profile.

```text
prod + region=ap-southeast
prod + region=eu-west
prod + region=us-east
```

A profile describes a group of **behavioral/configuration traits**, while environment variables or external Config Data supply **deployment-specific values**.

Avoid creating hundreds of profiles per hostname, account, or customer when a stable set of profiles plus externalized configuration suffices.

## 3. Design Rule: Common + Overrides

A maintainable structure:

```text
application.yml
  Environment-independent values
  Safe defaults
  Shared baseline settings

application-local.yml
  Differences for dev machines only
  Fake URL / local logging
  Small batches, short timeouts
  No uncontrolled external connections

application-test.yml
  For test classpath
  Deterministic, stable inputs
  No real credentials
  Ensure tests do not call external systems

application-prod.yml
  Production operational differences
  Safety settings and conservative tuning
  References to env vars / secrets
  No hard-coded real tokens
```

For example, the common file declares:

```yaml
app:
  batch:
    size: 40
    flush-interval: 5s
```

`application-local.yml` overrides only:

```yaml
app:
  batch:
    size: 10
```

When `local` is active and no higher-precedence source intervenes, `size=10`, while `flushInterval=5s` comes from the common file.

For scalars and simple nested objects, this design reduces duplication. However, for a **List**, Spring Boot replaces the whole list across sources rather than always merging element by element. For a **Map**, entries can be merged/overridden by key. Never blindly assume "adding one List item" appends to the base list.

## 4. Configuration Blueprint for the Lab Project

We choose a dedicated application prefix `app`, separate from standard Spring Boot properties such as `server.*` and `management.*`.

Property groups:

| Property | Java type | Meaning |
| --- | --- | --- |
| `app.display-name` | `String` | Display label |
| `app.region` | `String` | Logical deployment region |
| `app.outbound.enabled` | `boolean` | Whether outbound integration is enabled |
| `app.outbound.endpoint` | `URI` | Integration target |
| `app.outbound.connect-timeout` | `Duration` | Time allowed to open connection |
| `app.outbound.max-attempts` | `int` | Total attempts, including initial try |
| `app.outbound.auth-token` | `String` | Sensitive credential, if present |
| `app.batch.size` | `int` | Maximum items per batch |
| `app.batch.flush-interval` | `Duration` | Interval between flushes |
| `app.diagnostics.verbose` | `boolean` | Enable safe diagnostic details |

This configuration spans three data categories:

1. **Common values:** application name, logical configuration structure, relatively safe defaults.
2. **Environment-specific values:** endpoint, timeout, batch size, logging.
3. **Deployment secrets:** tokens, API keys, passwords; never put real values into Git.

This design also highlights responsibility around `authToken`. Never log the entire properties object if the record holds this field, because `record.toString()` will leak the token. In our example, the service bean returns only **non-sensitive** fields.

## 5. Detailed Directory Structure

A typical Maven/Gradle project:

```text
order-config-lab/
├── build.gradle                 # or pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/
│   │   │       ├── OrdersApplication.java
│   │   │       ├── AppSettings.java
│   │   │       └── DispatchPlanService.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       └── application-prod.yml
│   └── test/
│       ├── java/
│       │   └── com/example/orders/
│       │       ├── CommonConfigTest.java
│       │       ├── LocalProfileTest.java
│       │       ├── TestProfileTest.java
│       │       └── ProdProfileTest.java
│       └── resources/
│           └── application-test.yml
└── README.md
```

Placing `application-test.yml` in `src/test/resources` is intentional:

- Test runners load this file on the **test classpath**.
- During standard application packaging, `src/test/resources` is excluded from main runtime resources.
- Test configuration is less likely to leak into production artifacts.
- Tests use `@ActiveProfiles("test")` to activate this profile.

If a project genuinely needs to run a JAR with the `test` profile outside the test suite, supply the test file via a dedicated deployment setup. Do not alter standard packaging rules for a scenario without a real need.

## 6. Preparing Dependencies

Examples target Spring Boot 3.x, Java 17+, and JUnit Jupiter. The Config Data and profile principles here also apply to newer Spring Boot releases, though when using Boot 4 you should verify package imports in certain test/Actuator parts.

### 6.1. Maven

Minimal dependency set:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If an actual HTTP server is needed, add `spring-boot-starter-web`. If Actuator diagnostics are needed, add `spring-boot-starter-actuator` and configure appropriate exposure and security. This lab can run as a console application without opening a port.

### 6.2. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 6.3. Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Assume the project uses the Spring Boot plugin, parent/BOM, or dependency management to align compatible versions. Never mix Spring Framework and Spring Boot versions manually without a clear reason and verification.

## 7. Writing `application.yml`: Shared Defaults

File `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: order-config-lab

app:
  display-name: Order Configuration Lab
  region: global

  outbound:
    enabled: false
    endpoint: https://sandbox.example.invalid/api
    connect-timeout: 2s
    max-attempts: 3

  batch:
    size: 40
    flush-interval: 5s

  diagnostics:
    verbose: false

logging:
  level:
    root: INFO
    com.example.orders: INFO
```

Analysis:

- `spring.application.name` is a standard Spring Boot property.
- `app.*` is the application-defined namespace.
- `outbound.enabled=false` prevents enabling external integrations before an appropriate environment is chosen.
- `endpoint` uses the `.invalid` domain strictly as dummy data.
- `connect-timeout=2s` and `flush-interval=5s` use explicit units.
- `app.outbound.auth-token` is omitted from the common file because the token is a deployment-specific secret.
- Default logging stays moderate; do not turn on DEBUG for the entire framework.
- `spring.profiles.active=local` is omitted from the common file so deployments choose profiles explicitly and tests do not accidentally inherit `local`.

A shared default does not mean it is safe for every environment when the feature is **enabled**. For example, `sandbox.example.invalid` cannot be a real production endpoint; the prod file must supply a proper endpoint.

### 7.1. When to Put Defaults in Java Instead of YAML?

You can use Java field initializers or `@DefaultValue` for constructor binding. Yet putting one default in Java and a different default in YAML forces maintainers to track two places.

For a new project, you can standardize as follows:

- Common runtime defaults: keep in `application.yml`.
- Required values or special constraints: enforce via validation.
- Defaults solely for objects bound outside a context: use Java defaults when there is a real reason.
- Documentation: state clearly whether defaults live in Java, YAML, or deployment.

Avoid duplicating defaults "just to be safe" when duplication creates conflicting sources.

## 8. Writing `application-local.yml`: Convenient Yet Guarded

File `src/main/resources/application-local.yml`:

```yaml
app:
  region: local

  outbound:
    enabled: false
    endpoint: http://127.0.0.1:18080/mock
    connect-timeout: 500ms
    max-attempts: 1

  batch:
    size: 10

  diagnostics:
    verbose: true

logging:
  level:
    com.example.orders: DEBUG
```

Local guidelines:

1. **Never call production services.** The endpoint points to loopback and `enabled=false`.
2. **Short timeouts** reveal unavailable connections quickly.
3. **Small batches** make debugging small datasets easy.
4. **Controlled verbose logging** scoped to our own module.
5. **No real tokens** in the file.
6. Override only differing keys; `display-name` and `batch.flush-interval` still come from the common file.

If the application contains networking code that ignores `outbound.enabled`, setting it to `false` **does not automatically block network calls**. Code must genuinely honor the flag or swap in a fake adapter. Configuration is data; it does not replace architectural isolation.

### 8.1. Should Actuator `env`/`configprops` Be Enabled Locally?

It can aid learning, yet even on a personal laptop there is a risk of exposing environment variables and secrets. If you really want it:

- Expose only on loopback or an isolated network.
- Use dummy values.
- Set `management.endpoint.env.show-values=never` and `configprops.show-values=never`.
- Disable the endpoints when finished.
- Never paste raw responses into tickets or chat.

This lab **does not enable** `env`/`configprops` by default in the local profile to avoid normalizing unnecessary management exposure.

## 9. Writing `application-test.yml`: Configuration for Automated Tests

File `src/test/resources/application-test.yml`:

```yaml
app:
  region: test

  outbound:
    enabled: false
    endpoint: http://127.0.0.1:1/unreachable
    connect-timeout: 100ms
    max-attempts: 1

  batch:
    size: 5
    flush-interval: 100ms

  diagnostics:
    verbose: false

logging:
  level:
    com.example.orders: WARN
```

Why pick `127.0.0.1:1`? It is a dummy address representing a destination that tests must never call. **Do not rely on port 1 alone as a security barrier**; a well-written test should never issue real requests when `enabled=false`, or should replace the adapter with a fake/mock.

Characteristics of the test profile:

- Needs no production credentials.
- Provides identical inputs on every run.
- Uses small batches and short durations.
- Fails fast if a client accidentally attempts a network call.
- Never affects standard deployment artifacts.
- Activated via Spring TestContext, typically `@ActiveProfiles("test")`.

### 9.1. The Test Profile Differs from the Local Profile

The local profile helps developers inspect a running app, often with DEBUG logs. The test profile serves automation, prioritizing clean output, determinism, and zero side effects. Do not let tests default to `local` just because developers run `local` on their laptops.

### 9.2. Test Fixtures Are Not a Secret Store

If a test needs a credential, use a dummy string with zero privileges on real systems, or supply a test secret through controlled CI mechanisms. Never copy a production token into `src/test/resources` just because that folder is excluded from the JAR.

## 10. Writing `application-prod.yml`: Enabling Integration Safely

File `src/main/resources/application-prod.yml`:

```yaml
app:
  region: ${DEPLOY_REGION:global}

  outbound:
    enabled: true
    endpoint: ${ORDER_OUTBOUND_ENDPOINT}
    auth-token: ${ORDER_OUTBOUND_TOKEN}
    connect-timeout: 3s
    max-attempts: 5

  batch:
    size: 200
    flush-interval: 2s

  diagnostics:
    verbose: false

logging:
  level:
    com.example.orders: INFO
```

Here:

- `enabled=true` indicates production intends to enable the integration.
- `endpoint` and `auth-token` come from **external sources** via placeholders.
- `DEPLOY_REGION` falls back to `global` in this example; a real project might make region required.
- No token is stored in Git.
- Timeouts/retries/batch sizes reflect distinct operational targets and must be measured and tuned for the real service.
- Logging must never automatically print tokens or objects containing tokens.

**Never treat illustrative values as tuned production settings.** Numbers like 3s/5/200/2s merely demonstrate overrides. Real systems must size them based on latency, SLAs, load, and idempotency.

### 10.1. Placeholders Do Not Replace Validation

Configuration:

```yaml
auth-token: ${ORDER_OUTBOUND_TOKEN}
```

expresses that the application expects an external value. Yet do not assume by syntax alone that *every version and every binding style will always fail immediately* if the token is missing. How unresolved placeholders behave depends on resolution mechanics, target types, and binding stages.

For required values, add **runtime validation or tested startup checks**. Never let a literal string like `${ORDER_OUTBOUND_TOKEN}` pass as a "non-blank" credential.

### 10.2. The Prod File Need Not Repeat Every Property

`app.display-name` is absent from the prod file. It continues to come from the common file. This is deliberate: profile files declare only differences, reducing configuration drift.

## 11. Expected Values Table by Profile

Assuming no additional environment or CLI overrides:

| Property | Common | local | test | prod |
| --- | --- | --- | --- | --- |
| `app.display-name` | Order Configuration Lab | Keeps common | Keeps common | Keeps common |
| `app.region` | global | local | test | `DEPLOY_REGION` or global |
| `outbound.enabled` | false | false | false | true |
| `outbound.endpoint` | sandbox URL | loopback mock | loopback unreachable | ENV `ORDER_OUTBOUND_ENDPOINT` |
| `outbound.connect-timeout` | 2s | 500ms | 100ms | 3s |
| `outbound.max-attempts` | 3 | 1 | 1 | 5 |
| `outbound.auth-token` | Unset | Unset | Unset | ENV `ORDER_OUTBOUND_TOKEN` |
| `batch.size` | 40 | 10 | 5 | 200 |
| `batch.flush-interval` | 5s | 5s | 100ms | 2s |
| `diagnostics.verbose` | false | true | false | false |
| `logging.level.com.example.orders` | INFO | DEBUG | WARN | INFO |

Cells marked "Keeps common" mean the profile source does not override that property—**not that higher-priority ENV/CLI/external Config Data sources cannot override it**.

This table shows expected lab results; verifying a real process requires inspecting `Environment` and bound beans.

## 12. Starting the Application and Selecting a Profile

### 12.1. Starting Locally via Command Line

With a built JAR:

```bash
java -jar app.jar --spring.profiles.active=local
```

Or with Gradle:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

Or Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

On Windows, use the `gradlew.bat`/`mvnw.cmd` wrappers. Quoting may need adjustment in PowerShell compared to Bash; with a JAR, `--spring.profiles.active=local` is straightforward and explicit.

### 12.2. Starting via Environment Variables

In Bash:

```bash
export SPRING_PROFILES_ACTIVE=local
java -jar app.jar
```

In PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar app.jar
```

These are two ways to **select the profile externally** without modifying `application.yml`.

### 12.3. Starting Production

Bash example using dummy values for illustration:

```bash
export SPRING_PROFILES_ACTIVE=prod
export DEPLOY_REGION=ap-southeast
export ORDER_OUTBOUND_ENDPOINT=https://orders.example.invalid/api

# ORDER_OUTBOUND_TOKEN must be provisioned by a secrets system.
# Never paste real values into docs, shell scripts, or logs.

java -jar app.jar
```

If you run this example for practice without a dummy token, production config checks will fail. That is exactly what should happen when an app requires a credential that deployment has not supplied.

In real deployments, a secret manager, CI/CD vault, Kubernetes Secret, or equivalent platform should supply the token. Never pass real tokens in startup commands that could end up in process listings or shell history.

### 12.4. Do Not Enable the Test Profile on Released JARs

In this layout, `application-test.yml` lives in test resources and is not expected in the production executable JAR. Activate `test` through the test runner; running the app with the test profile another way requires explicitly supplying the resources.

## 13. Creating the `@ConfigurationProperties` Record

File `src/main/java/com/example/orders/AppSettings.java`:

```java
package com.example.orders;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        @NotBlank String displayName,
        @NotBlank String region,
        @Valid @NotNull Outbound outbound,
        @Valid @NotNull Batch batch,
        @Valid @NotNull Diagnostics diagnostics
) {

    public record Outbound(
            boolean enabled,
            @NotNull URI endpoint,
            @NotNull Duration connectTimeout,
            @Min(1) int maxAttempts,
            String authToken
    ) {}

    public record Batch(
            @Min(1) int size,
            @NotNull Duration flushInterval
    ) {}

    public record Diagnostics(boolean verbose) {}
}
```

Key points:

- Prefix `app` maps the entire group into one object.
- `display-name` binds to `displayName`.
- `connect-timeout` and `flush-interval` convert to `Duration`.
- `endpoint` converts to `URI`.
- `@Validated` and Jakarta Validation annotations verify core constraints when a validation provider is present.
- `@Valid` cascades validation into nested objects per Bean Validation rules.
- `authToken` is declared as an optional `String` because local/test omit it; production enforces a dedicated guard conditioned on `enabled`.
- **Never log `AppSettings` directly** because the record's `toString()` can expose the token.

`@Min(1)` ensures attempts/batch sizes are at least 1, yet does not verify positive timeouts or HTTPS URLs. Those business rules require separate validation.

### 13.1. `@NotNull` Does Not Mean a Positive Timeout

`@NotNull Duration connectTimeout` only checks for a non-null object. `Duration.ZERO` or negative values are still non-null. If your contract requires `> 0`, add an appropriate validator or custom check.

Similarly, `@NotNull URI endpoint` does not guarantee an `https` scheme. Successful type conversion does not mean the URL is safe or meets operational policy.

## 14. Registering `AppSettings` in Spring Boot

File `OrdersApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppSettings.class)
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

`@EnableConfigurationProperties` tells the Binder to create a bean for `AppSettings`. For a record with a single constructor of matching types, Spring Boot 3.x supports constructor binding without needing `@ConstructorBinding` in this basic example.

In larger projects, `@ConfigurationPropertiesScan` also works well when package scanning is properly scoped.

### 14.1. Do Not Add `@Component` to a Record Just for Constructor Binding

Avoid slapping `@Component` onto a configuration properties record as a fix for registration issues when you intend the Binder to instantiate it via constructor binding. Regular component scanning and `@ConfigurationProperties` constructor binding follow different registration rules.

Choose one clear mechanism: `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan` for configuration groups bound as data.

## 15. Writing a Service That Consumes Properties Without Leaking Secrets

File `DispatchPlanService.java`:

```java
package com.example.orders;

import java.net.URI;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class DispatchPlanService {

    private final AppSettings settings;

    public DispatchPlanService(AppSettings settings) {
        this.settings = settings;
    }

    public DispatchPlan currentPlan() {
        return new DispatchPlan(
                settings.region(),
                settings.outbound().enabled(),
                settings.outbound().endpoint(),
                settings.outbound().connectTimeout(),
                settings.outbound().maxAttempts(),
                settings.batch().size(),
                settings.batch().flushInterval()
        );
    }

    public record DispatchPlan(
            String region,
            boolean outboundEnabled,
            URI outboundEndpoint,
            Duration connectTimeout,
            int maxAttempts,
            int batchSize,
            Duration flushInterval
    ) {}
}
```

The service **does not** return `authToken` inside `DispatchPlan`. The goal is a safe projection to verify that profiles bound non-sensitive fields properly.

In a real application, if the service uses the token to send requests, manage credentials separately and never expose them via `toString()`, logs, or public responses.

### 15.1. The `enabled` Flag Must Actually Be Enforced

When implementing an `OutboundGateway`, ensure code only instantiates/calls the real adapter when `enabled=true`, and uses a fake adapter or proper disable check in local/test.

A snippet:

```yaml
app:
  outbound:
    enabled: false
```

**does not automatically stop** a client that opens a socket inside its constructor. It only acts as a guardrail when code respects the flag properly.

## 16. Adding Mandatory Production Checks Without Logging the Token

In the `prod` profile, `enabled=true` and the token must be supplied. You can define a bean that validates settings after binding and before handling traffic, for example using `SmartInitializingSingleton`:

```java
package com.example.orders;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class ProductionConfigGuard {

    @Bean
    @Profile("prod")
    SmartInitializingSingleton verifyProdSettings(
            AppSettings settings) {

        return () -> {
            AppSettings.Outbound outbound = settings.outbound();

            if (!outbound.enabled()) {
                throw new IllegalStateException(
                    "Production outbound must be enabled"
                );
            }

            if (!"https".equalsIgnoreCase(
                    outbound.endpoint().getScheme())) {
                throw new IllegalStateException(
                    "Production outbound endpoint must use HTTPS"
                );
            }

            String token = outbound.authToken();

            if (token == null
                    || token.isBlank()
                    || token.startsWith("${")) {
                throw new IllegalStateException(
                    "Production outbound token must be supplied"
                );
            }
        };
    }
}
```

This is an illustrative guard for the lab:

- Annotated with `@Profile("prod")` so it only activates in the `prod` profile.
- Never includes the token in the exception.
- Checks that the token is neither missing/blank nor an unresolved placeholder literal.
- Checks that the production endpoint uses the HTTPS scheme.
- Does not verify whether the token is accepted by an external system—only its presence and shape.
- Runs during singleton initialization, not on live requests.

**Note:** `SmartInitializingSingleton` runs after singletons have been instantiated, so it cannot block side effects inside earlier constructors. If you need fail-fast guarantees before any client initializes, place validation directly on `@ConfigurationProperties` or model lifecycle dependencies accordingly. The guard here simply illustrates a profile-conditional check.

### 16.1. Never Put Secrets in Error Messages

Wrong:

```java
throw new IllegalStateException(
    "Invalid token: " + settings.outbound().authToken()
);
```

Better:

```java
throw new IllegalStateException(
    "Production outbound token is missing or invalid"
);
```

Exceptions can appear in CI logs, APM tools, or monitoring dashboards. Error messages should identify **which key failed**, never print the secret value.

## 17. Writing a Test for the `test` Profile with `@ActiveProfiles`

File `src/test/java/com/example/orders/TestProfileTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class TestProfileTest {

    @Autowired
    AppSettings settings;

    @Autowired
    Environment environment;

    @Autowired
    DispatchPlanService planService;

    @Test
    void loadsTestConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(settings.region()).isEqualTo("test");
        assertThat(settings.outbound().enabled()).isFalse();
        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofMillis(100));
        assertThat(settings.outbound().maxAttempts())
                .isEqualTo(1);

        assertThat(settings.batch().size()).isEqualTo(5);
        assertThat(settings.batch().flushInterval())
                .isEqualTo(Duration.ofMillis(100));

        assertThat(planService.currentPlan().batchSize())
                .isEqualTo(5);
    }
}
```

This test proves:

1. TestContext activates the `test` profile.
2. `application-test.yml` from the test classpath is picked up.
3. The Binder converts `100ms` to `Duration.ofMillis(100)`.
4. The service bean receives `batch.size=5`.
5. No production token or real external call is needed.

Do not run tests under an uncontrolled environment with stray global variables. If CI sets a property with higher precedence than test files, observed values may differ; pin values with `@SpringBootTest(properties=...)` or an appropriate test-specific source when needed.

## 18. Testing the `local` Profile

File `LocalProfileTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("local")
@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class LocalProfileTest {

    @Autowired
    AppSettings settings;

    @Test
    void loadsLocalOverridesAndKeepsCommonDefaults() {
        assertThat(settings.region()).isEqualTo("local");

        assertThat(settings.outbound().enabled()).isFalse();
        assertThat(settings.outbound().endpoint())
                .isEqualTo(
                    URI.create("http://127.0.0.1:18080/mock")
                );

        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofMillis(500));

        assertThat(settings.batch().size()).isEqualTo(10);

        // Not redeclared in application-local.yml:
        assertThat(settings.batch().flushInterval())
                .isEqualTo(Duration.ofSeconds(5));

        assertThat(settings.displayName())
                .isEqualTo("Order Configuration Lab");

        assertThat(settings.diagnostics().verbose()).isTrue();
    }
}
```

This test checks **both overrides and common fallbacks**. Testing only overridden values leaves common inheritance unproven.

### 18.1. Why Not Enable `local` by Default for All Tests?

A test with `@ActiveProfiles("local")` can pull in fake developer URLs and DEBUG logging intended for local machines. Automated test suites should use `test` to stay consistent between CI and developer laptops.

## 19. Testing Common Defaults with No Active Profile

File `CommonConfigTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CommonConfigTest {

    @Autowired
    AppSettings settings;

    @Test
    void usesCommonDefaultsWithoutActiveProfile() {
        assertThat(settings.region()).isEqualTo("global");

        assertThat(settings.outbound().enabled()).isFalse();

        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));

        assertThat(settings.outbound().maxAttempts())
                .isEqualTo(3);

        assertThat(settings.batch().size()).isEqualTo(40);
    }
}
```

Important condition: the test assumes no active profile comes from external sources; if CI sets `SPRING_PROFILES_ACTIVE=prod` globally for every process, the test could accidentally activate `prod`. A sound CI setup **never passes production profiles to the test JVM**.

If you want to pin the baseline explicitly, configure the test setup accordingly—never expect "no profile" while letting an external environment activate one.

## 20. Testing `prod` Without Real Secrets

To test the `prod` profile, supply **dummy yet valid** values via test overrides; never use production tokens.

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(
    classes = OrdersApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "ORDER_OUTBOUND_ENDPOINT=https://prod.example.invalid/api",
        "ORDER_OUTBOUND_TOKEN=FAKE_TEST_TOKEN",
        "DEPLOY_REGION=ap-southeast"
    }
)
class ProdProfileTest {

    @Autowired
    AppSettings settings;

    @Test
    void bindsProdSettingsFromTestSuppliedValues() {
        assertThat(settings.region()).isEqualTo("ap-southeast");

        assertThat(settings.outbound().enabled()).isTrue();

        assertThat(settings.outbound().endpoint()).isEqualTo(
            URI.create("https://prod.example.invalid/api")
        );

        assertThat(settings.outbound().connectTimeout())
            .isEqualTo(Duration.ofSeconds(3));

        assertThat(settings.outbound().maxAttempts())
            .isEqualTo(5);

        assertThat(settings.batch().size()).isEqualTo(200);

        // Never print or expose raw token in failure messages.
        assertThat(settings.outbound().authToken())
            .isNotBlank();
    }
}
```

The snippet supplies test properties matching the **placeholder variable names**: `ORDER_OUTBOUND_ENDPOINT`, `ORDER_OUTBOUND_TOKEN`, and `DEPLOY_REGION`. They resolve via the test `Environment`, giving the `prod` profile dummy values without relying on real CI secrets. Depending on source types, placeholder styles, or framework versions, you can also override canonical keys directly such as `app.outbound.endpoint` and `app.outbound.auth-token`; what matters is verifying the behavior on your target version.

**Do not use this test to claim real production has valid secrets.** It verifies only the production config structure, binding, and guard logic against dummy inputs. Secret permissions and real API connectivity must be verified in a proper integration environment.

## 21. When a Test Needs an Extra Property Override

`application-test.yml` specifies:

```yaml
app:
  batch:
    size: 5
```

Suppose one test needs to try a batch size of 12:

```java
@ActiveProfiles("test")
@SpringBootTest(
    classes = OrdersApplication.class,
    properties = {
        "app.batch.size=12"
    }
)
class LargerBatchTest {

    @Autowired
    AppSettings settings;

    @Test
    void overridesBatchSizeForThisContext() {
        assertThat(settings.batch().size()).isEqualTo(12);
    }
}
```

In this test context, inline `@SpringBootTest(properties=...)` has higher precedence than standard Config Data, so `size=12` overrides `5` from the test file.

Distinguish:

- **Test profile**: defines a baseline set of values for automated tests.
- **Inline test property**: defines a per-test-class exception.
- **`@DynamicPropertySource`**: best when values depend on random ports from Testcontainers or mock servers.
- **`@TestPropertySource`**: useful when loading a dedicated fixture properties file.
- **`ApplicationContextRunner`**: ideal for many small config combinations and expected startup failure cases.

Avoid defining the same key across too many test sources and guessing which wins. Keep one primary test source per key plus deliberate overrides.

## 22. Profiles and Precedence: Why a Value Can Still Differ from YAML

A value can pass through:

```text
application.yml
application-{profile}.yml
external application.yml / application-{profile}.yml
environment variables
Java system properties
command line arguments
test inline properties / dynamic properties
custom PropertySource
```

Do not memorize a Spring Boot 1.x precedence list and apply it blindly to modern projects. The Spring Boot Externalized Configuration documentation defines Config Data sources, ordering, location groups, and dedicated priority levels.

In typical setups:

1. Profile-specific files can override non-profile-specific files within Config Data.
2. Command-line options usually override values from Config Data files.
3. Environment variables usually take higher precedence than packaged Config Data.
4. Test properties can take high precedence to pin test inputs.
5. When multiple profiles are active, matching documents apply according to profile rules and ordering.

### 22.1. Same Key in Multiple Places

`application.yml`:

```yaml
app:
  batch:
    size: 40
```

`application-prod.yml`:

```yaml
app:
  batch:
    size: 200
```

Command:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.batch.size=300
```

In a standard setup with no higher source, the bean receives `300`. Editing the prod file from 200 to 250 has no effect until the CLI override is removed or changed.

If a deployment defines `APP_BATCH_SIZE`, check the active order and effective source before drawing conclusions. For real apps, use secured Actuator `env` or inspect `Environment` in tests.

### 22.2. A Source Added Later Is Not Necessarily Higher Priority

`MutablePropertySources` provides `addFirst`, `addLast`, `addBefore`, and `addAfter`. A custom source registered later yet appended with `addLast` acts only as a fallback. When troubleshooting, examine **source order**, not the chronological moment code executed.

## 23. Never Put `spring.profiles.active` Inside a Profile-Specific File

A mistake to avoid:

```yaml
# application-prod.yml - NOT INTENDED
spring:
  profiles:
    active: local
```

Modern Spring Boot documentation specifies that `spring.profiles.active` and `spring.profiles.default` may only be used in **non-profile-specific documents**. Never put them inside `application-prod.yml` or inside a document activated by `spring.config.activate.on-profile`.

Likewise, settings such as `spring.profiles.include` and `spring.profiles.group` have corresponding placement restrictions: put them in non-profile-specific documents per your Boot version's documentation.

Proper ways to select a profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or:

```text
SPRING_PROFILES_ACTIVE=prod
```

Or in tests:

```java
@ActiveProfiles("test")
```

When building a JAR, **never hard-code the `prod` profile inside `main`** if the same artifact needs to run locally, in tests, or across multiple environments.

## 24. Multi-Document YAML with `on-profile`: An Alternative to Separate Files

Spring Boot supports multiple YAML documents separated by `---`:

```yaml
app:
  region: global
  batch:
    size: 40

---
spring:
  config:
    activate:
      on-profile: local

app:
  region: local
  batch:
    size: 10

---
spring:
  config:
    activate:
      on-profile: prod

app:
  region: ${DEPLOY_REGION:global}
  batch:
    size: 200
```

Here:

- The first document always applies.
- The second document applies when `local` is active.
- The third document applies when `prod` is active.
- `spring.config.activate.on-profile` governs **document activation**; it does not turn on a profile by itself.

**This is an alternative to separate profile files, not something to mix simultaneously into the lab's file set.** If you define the same key in both `application-local.yml` and an `on-profile: local` document, maintainers must track extra precedence interactions.

### 24.1. Separate Files vs. Multi-Document YAML?

Use separate files when:

- Each profile has substantial differences.
- The team wants per-environment code review separation.
- You want separate permissions or want test resources excluded from main resources.
- Multiple teams edit configs and you want fewer merge conflicts.

Use multi-document YAML when:

- Only a few small differences exist.
- Keeping variants side by side helps comparison.
- The team clearly understands `on-profile` and document boundaries.

In a lab with separate test resources, **per-profile files** express release and test boundaries more clearly.

## 25. Multiple Active Profiles: Do Not Accidentally Mix `local` and `prod`

Spring Boot accepts multiple active profiles:

```bash
java -jar app.jar --spring.profiles.active=prod,metrics
```

This works well when `metrics` is a clear additive configuration group. However:

```bash
java -jar app.jar --spring.profiles.active=local,prod
```

can create a dangerous hybrid configuration: profile file values resolve by precedence order, while beans annotated `@Profile("local")` and `@Profile("prod")` may both be registered depending on conditions.

**Do not treat multiple profiles as harmless addition.** For mutually exclusive environment profiles like `local`, `test`, and `prod`, enforce a policy allowing only one primary environment profile per deployment.

When observability add-ons are needed, use clear additive profiles:

```text
prod + metrics
local + devtools
```

and test each combination's bean conditions and profile expressions.

### 25.1. Profile Order Affects Overrides

When multiple profiles exist within the same location group and define the same key, Spring Boot applies override rules where a profile listed later can win.

However, with complex location groups using commas and semicolons in `spring.config.location`, precedence also depends on the location group. Never assume "the last filename loaded always wins unconditionally."

In integrated practice, keeping a single primary environment profile minimizes surprises.

## 26. Profile Groups: Bundling Additive Profiles

Spring Boot supports profile groups so activating one logical name activates member profiles. For example, in a **non-profile-specific** file:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
```

Activating `production` enables its member profiles per Boot's rules.

This is an advanced feature—use it only when helpful. In this lab, profile groups are unnecessary to run `local`, `test`, and `prod`.

An essential rule: `spring.profiles.group` must be declared in a **non-profile-activated** document; do not place it inside `application-prod.yml` expecting the group to assemble itself after `prod` is already active.

When using groups, verify that no group accidentally activates conflicting environment profiles like `local` and `prod` together.

## 27. Production Secrets: Must Be Supplied Externally

The most dangerous mistake in multi-environment configuration is **committing real credentials to the repository**, even inside a file named `application-prod.yml`.

Wrong:

```yaml
app:
  outbound:
    auth-token: real-production-token-goes-here
```

Better in principle:

```yaml
app:
  outbound:
    auth-token: ${ORDER_OUTBOUND_TOKEN}
```

Acceptable token sources include:

- Kubernetes Secrets.
- Cloud platform secret managers.
- Internal Vault instances.
- Environment variables injected by a secure pipeline.
- Config Data imports from an approved secret integration.

**Never place real tokens in Git, logs, screenshots, test fixtures, or ticket comments.**

### 27.1. Are Tokens in Env Vars Completely Safe?

No. Environment variables carry risks too: they can be read by privileged processes, dumps, diagnostic tools, or accidental log statements. They simply decouple the secret from source code; access control, rotation, auditing, and TTLs still need to be managed.

### 27.2. Never Log a Record Containing `authToken`

With:

```java
log.info("Settings: {}", appSettings);
```

Java records emit every component via `toString()`. A bound token is not automatically redacted from application logs.

Better:

```java
log.info(
    "Order outbound enabled={}, region={}",
    appSettings.outbound().enabled(),
    appSettings.region()
);
```

Even logging endpoints and regions should follow your organization's data classification policy.

## 28. One JAR for All Environments

A core DevOps goal is:

```text
Build application once
          |
          v
      app.jar
          |
          +--> local: local profile + local settings
          |
          +--> test: test classpath / test fixtures
          |
          +--> prod: prod profile + deployment secrets
```

You should never recompile code just to change `app.batch.size` from 10 to 200. In principle, configuration belongs outside the artifact.

That said, `application-local.yml` and `application-prod.yml` in `src/main/resources` may be packaged inside the artifact. Their presence does not make them active; only explicitly activated profiles and properly loaded sources determine the outcome.

Some organizations choose **not to package prod files at all**, supplying all prod configuration from the deployment platform. That is equally valid for centralized configuration management. This lab keeps a prod file in resources to illustrate overrides while still requiring real secrets to come from outside.

## 29. External Config Outside the JAR: Decoupling Deployment from Source Code

Spring Boot allows specifying or adding Config Data locations. Example:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
```

The `./config/` directory can hold:

```text
config/
  application.yml
  application-prod.yml
```

Boot evaluates these configured sources according to location and profile rules. `optional:` permits a missing location/resource without failing startup on "location not found" in supported cases; it does not excuse invalid YAML syntax or missing credentials.

**Note:** `spring.config.location` and `spring.config.additional-location` are processed very early. Pass them via environment variables, system properties, or startup arguments per your version's docs—never inside a file that Boot would need those properties to find first.

### 29.1. Commas and Semicolons in Config Data Locations

In modern Spring Boot versions, commas and semicolons carry **location group** semantics. Two setups with the same paths but different grouping punctuation may not share identical precedence when combined with profile-specific files.

If your project only needs one extra folder, use a single clear location and verify source order in tests instead of chaining complex location groups needlessly.

## 30. Diagnosing Which Configuration Wins

If you edited `application-prod.yml` yet the bean still binds a different value:

1. Check the actual active profiles: `Environment.getActiveProfiles()`.
2. Identify the canonical key: `app.batch.size`, `app.outbound.connect-timeout`.
3. Inspect command-line arguments on the exact running process.
4. Check for overriding environment variables or system properties.
5. Check external Config Data files, imports, and origin metadata.
6. Confirm the `@ConfigurationProperties` class is registered.
7. Inspect the bean's bound typed value.
8. Check whether a service cached a snapshot or mutated values itself.

If Actuator is permitted and secured, you can query:

```text
GET /actuator/env/app.batch.size
GET /actuator/configprops/app
```

`env` shows the winning source and origin; `configprops` shows the `@ConfigurationProperties` object and bound inputs. **Never set `show-values=always` in production** just to check a batch size; use authorized metadata queries and allowlisted checks.

### 30.1. Bean Missing from `configprops`?

The class may be unregistered, the prefix mismatched, a profile-conditional bean inactive, or the endpoint unexposed. Having a property in `Environment` does not automatically mean the Binder created a target Java object.

### 30.2. Masked Values Are Not Literally Six Asterisks

When `env` returns `******`, that is Actuator sanitization, not proof that your token or batch size is literally `"******"`.

## 31. Reading `Environment` Directly in Java

To inspect **non-sensitive** keys at startup, you can register a runner for local/test environments:

```java
package com.example.orders;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class LocalDiagnosticsConfiguration {

    @Bean
    @Profile("local")
    ApplicationRunner inspectLocalConfig(
            Environment environment,
            AppSettings settings) {

        return args -> {
            System.out.println(
                "Profiles: " +
                String.join(",", environment.getActiveProfiles())
            );

            System.out.println(
                "Batch size: " + settings.batch().size()
            );

            System.out.println(
                "Outbound enabled: " +
                settings.outbound().enabled()
            );
        };
    }
}
```

This prints only profiles, batch size, and the `enabled` flag. Never print `authToken` or the entire `AppSettings` object.

In production, prefer controlled structured logging over ad-hoc `System.out.println`.

### 31.1. A Value in `Environment` Does Not Prove Bean Binding

`environment.getProperty("app.batch.size")` may return `"200"`, whereas `settings.batch().size()` is the bound `int`. If the bean was constructed improperly or initialized prior to a runtime change, the two observations can diverge.

Use tests and `configprops` to debug binding issues, not only raw `Environment` text lookups.

## 32. Profiles and Conditional Beans

You can separate local and production adapters:

```java
public interface OutboundGateway {
    String kind();
}
```

Bean configuration:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Profile({"local", "test"})
    OutboundGateway simulatedGateway() {
        return () -> "simulated";
    }

    @Bean
    @Profile("prod")
    OutboundGateway productionGateway() {
        return () -> "production";
    }
}
```

These beans simply return labels without network calls to demonstrate conditional bean creation.

**Pitfall:** if no profile is active, there may be no `OutboundGateway` bean at all. If both `local` and `prod` are active, two beans of the same interface exist, causing ambiguous type injection.

Therefore:

- Enforce mutually exclusive environment profile policies.
- Provide a fallback bean for the default profile if the app requires one.
- Avoid creating profile-activated production beans without config/secret checks.
- Write integration tests confirming each profile registers only its intended gateway.

### 32.1. `@Profile` Is Not a Feature Flag

A profile selects beans at startup. The `app.outbound.enabled` flag can determine a bean's behavior. They address different layers:

- `@Profile`: **which beans exist** in the context.
- Property flag: **which behavior a bean executes**.
- Configuration Properties: **what data is bound** into an object.
- Runtime validation: **whether that data is valid**.

Avoid duplicating the exact same intent with both a profile and a flag unless you have a clear reason for both.

## 33. Combining `@ConditionalOnProperty` Where Appropriate

An alternative to profiles for conditional bean creation:

```java
@Bean
@ConditionalOnProperty(
    prefix = "app.outbound",
    name = "enabled",
    havingValue = "true"
)
OutboundGateway enabledGateway() {
    return () -> "enabled";
}
```

When `app.outbound.enabled=false`, this bean is not registered. If another service injects `OutboundGateway`, you must also provide a fallback bean or make the dependency optional.

Use `@ConditionalOnProperty` when a **feature toggle** drives the condition; use `@Profile` when it is an **environment** selection. In practice they can be combined, provided you test to prevent missing or duplicate beans of the same type.

## 34. A Strategy for Blocking Invalid Profile Combinations

If `local`/`test`/`prod` must be mutually exclusive, you can enforce this in tests or a startup guard. Reasoning:

```text
active profiles = [local]        OK
active profiles = [test]         OK for test context
active profiles = [prod]         OK with valid secret
active profiles = [prod,metrics] OK if metrics is additive
active profiles = [local,prod]   Invalid by policy
active profiles = [test,prod]    Invalid by policy
```

You can check this with `Environment.acceptsProfiles(Profiles.of("prod & local"))` or inspecting active profile sets.

Sketch of a guard:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean localAndProd =
        environment.acceptsProfiles(Profiles.of("local & prod"));

boolean testAndProd =
        environment.acceptsProfiles(Profiles.of("test & prod"));

if (localAndProd || testAndProd) {
    throw new IllegalStateException(
        "Conflicting environment profiles"
    );
}
```

Place this check at an early startup point, never inside a request handler. To fail before dangerous side effects happen, enforce the guard early in configuration or in deployment policies rather than waiting until a background job starts running.

## 35. Never Use Profiles as an Authorization System

Values like `prod` or `local` can be supplied via command line or environment variables. They are not authenticated proof of caller identity.

Mistake:

```java
if (environment.acceptsProfiles(Profiles.of("prod"))) {
    // Skip authentication because this must be production
}
```

Profiles describe configuration context and must never bypass security controls. Even in the `local` profile, if an endpoint is exposed on a broader network or touches real data, enforce proper authentication and access controls.

Similarly, **the `test` profile does not guarantee tests lack network access**. Design fake clients, test isolation, and side-effect checks explicitly.

## 36. Avoid Mixing Configuration Sources Carelessly

Several sources can all supply `app.batch.size`:

```text
src/main/resources/application.yml
src/main/resources/application-prod.yml
file:./config/application-prod.yml
APP_BATCH_SIZE
-Dapp.batch.size=...
--app.batch.size=...
@SpringBootTest(properties=...)
@DynamicPropertySource
```

In a clean workflow:

- Common holds shared defaults.
- Profile files hold environment-character differences.
- Deployment holds cluster/instance-specific values.
- Tests hold fixtures and dynamic test sources.
- No two groups accidentally "own" the same key.
- Whenever a key is overridden, document why.

Be careful with Java system properties: calling `System.setProperty(...)` in one test can leak to other tests in the same JVM, especially under parallel execution. Prefer `@SpringBootTest(properties=...)` or context-scoped test sources to avoid side effects.

## 37. Rules for Collection Configuration

### 37.1. List

Common file:

```yaml
app:
  routes:
    - primary
    - backup
```

Prod file:

```yaml
app:
  routes:
    - prod-primary
```

Under Spring Boot's binding rules, a `List` is typically **replaced** when a profile or higher-precedence source defines a new list—it does not automatically append into `primary, backup, prod-primary`.

For a `List`, declare the complete list for an environment in a single clear source.

### 37.2. Map

Common file:

```yaml
app:
  channels:
    email: enabled
    push: disabled
```

Prod file:

```yaml
app:
  channels:
    push: enabled
```

A `Map` can merge entries across sources, overriding `push` from the higher-priority source while retaining `email` from the common file.

Do not assume every nested custom structure merges identically to a flat `Map<String, String>`. For nested objects, collections, and special map keys, test the actual Binder behavior.

## 38. Managing Environment Variable Names

Spring Boot supports relaxed binding between canonical property names and environment variable formats.

Example:

```text
app.outbound.connect-timeout
APP_OUTBOUND_CONNECTTIMEOUT
```

Typical canonical-to-env transformation rule: replace dots with underscores, remove dashes, and convert to uppercase. Thus `APP_OUTBOUND_CONNECTTIMEOUT` follows the Binder's standard convention.

Do not write `APP_OUTBOUND_CONNECT_TIMEOUT` assuming it will always bind identically just because it looks natural. Verify the actual convention and test on your Spring Boot version.

Properties involving List indices or Map keys have more involved mappings. For the secret in this lab, we use the placeholder `ORDER_OUTBOUND_TOKEN` so the variable name is **referenced directly** rather than derived from `app.outbound.auth-token`.

## 39. Common Defaults Can Mask Missing Prod Configuration

One risk of "common + overrides" is that a safe local default becomes an **unacceptable fallback in prod**.

Example in common:

```yaml
app:
  outbound:
    endpoint: https://sandbox.example.invalid/api
```

If the prod file forgets to override it or an env var is omitted, the app could pick up the sandbox endpoint and start in the wrong state.

To mitigate this:

1. Declare prod endpoints using required placeholders.
2. Enforce production guards on endpoints and credentials.
3. Test the `prod` profile with dummy values.
4. Check real prerequisites in deployment readiness probes.
5. Prevent outbound services from calling unapproved hosts.
6. Enforce host verification or allowlists matching the integration contract.

"Valid Java type conversion" does not equal "operationally safe default".

## 40. Avoid Port Conflicts in Local Configuration

A local file might set:

```yaml
server:
  port: 8081
```

Yet when multiple developers or multiple services run on the same host, fixed ports can collide. For HTTP integration tests, you can use:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
```

and configure test clients against the assigned port.

**Do not set `server.port=0` in every profile** just to avoid port conflicts if monitoring or deployment expects a fixed port. Give each environment an intentional port strategy.

Because this lab needs no HTTP server, we omit `server.port` to keep the web stack out of scope.

## 41. Production Should Not Keep Global DEBUG Logging

The local file has:

```yaml
logging:
  level:
    com.example.orders: DEBUG
```

The prod file keeps `INFO`. If an application logs objects containing tokens, overly broad DEBUG logging can leak sensitive data.

Never assume `INFO` is automatically safe either; `log.info("{}", settings)` still leaks secrets. **Logging discipline** must be enforced in code regardless of profile.

Best practices:

- Log only fields explicitly vetted as non-sensitive.
- Never dump the complete `Environment`.
- Never enable raw Actuator values in production.
- Use structured logging with controlled retention lifecycles.
- Review or test log output whenever adding new credentials.

## 42. Documenting Configuration for Deployers

A sample contract table in the project README:

| Property | Required when? | Default | Recommended source |
| --- | --- | --- | --- |
| `spring.profiles.active` | Selecting local/prod | Not forced to local | ENV/CLI/deployment |
| `app.display-name` | Always | Common YAML | Common |
| `app.region` | Always | global | Profile/ENV |
| `app.outbound.enabled` | Always | false | Common + prod |
| `app.outbound.endpoint` | When integration enabled | Dummy sandbox in common | Prod ENV |
| `app.outbound.auth-token` | When prod outbound enabled | None | Secret manager |
| `app.outbound.connect-timeout` | Always | 2s | Common/profile |
| `app.outbound.max-attempts` | Always | 3 | Common/profile |
| `app.batch.size` | Always | 40 | Common/profile/deploy |
| `app.batch.flush-interval` | Always | 5s | Common/profile |
| `app.diagnostics.verbose` | Always | false | Common/local |

A complete contract should also state:

- Data type and unit.
- Valid value range.
- Who owns provisioning the value.
- Whether changing it requires a restart.
- Whether the value may be logged or exposed.
- Which external services depend on it.
- Whether missing/invalid values fail startup or fall back.
- How the configuration path is tested.

## 43. Pre-Production Deployment Checklist

**Configuration:**

- [ ] Artifact built from the intended version.
- [ ] `SPRING_PROFILES_ACTIVE=prod` supplied properly.
- [ ] `local` or `test` not accidentally enabled alongside `prod`.
- [ ] Prod file and external Config Data loaded.
- [ ] Region, endpoint, timeouts, and batch size set appropriately.
- [ ] Tokens/credentials sourced from a secret store, never Git.
- [ ] Production guards and validation actively enforced.
- [ ] Sandbox endpoint cannot act as an unintended fallback.

**Security:**

- [ ] Settings records containing tokens are never logged.
- [ ] Actuator `env`/`configprops` are not publicly exposed.
- [ ] Management endpoints protected by auth and network policies.
- [ ] Secrets never appear on command lines exposed to shell history or process lists.
- [ ] Rotation and revocation procedures exist if a credential leaks.

**Operations:**

- [ ] Appropriate readiness/health checks configured.
- [ ] Timeouts and retries match SLAs and idempotency guarantees.
- [ ] Batch sizes stay within system capacity.
- [ ] Metrics and logs leak no sensitive data.
- [ ] Rollback does not depend on manual file edits after deploy.
- [ ] Tests/CI use an isolated profile and make zero production network calls.

## 44. Common Pitfall: Profile Not Activated

Symptom: `application-local.yml` declares batch size 10, yet the bean still binds 40.

Possible causes:

- The `local` profile is not active.
- `SPRING_PROFILES_ACTIVE` was exported in a different shell from the running process.
- The file is not on the runtime classpath.
- Typo in the filename, such as `application-lcoal.yml`.
- A higher-precedence source overrides `size`.
- You are inspecting a different instance from the one serving.

How to troubleshoot:

1. Check the process's active profiles.
2. Verify the file was packaged or loaded.
3. Confirm the canonical key `app.batch.size`.
4. Inspect `Environment` or secured Actuator `env`.
5. Verify `AppSettings` bean binding.
6. Do not blindly hack the common file to force the result.

## 45. Common Pitfall: Test Files Packaged into Production

If you place dummy-token fixtures or test configs inside `src/main/resources`, they get bundled into the JAR. Even when inactive, those files sit inside the deliverable artifact.

Putting `application-test.yml` in `src/test/resources` when only the test runner needs it lowers that risk. Verify artifact contents during release checks whenever security policies require it.

Never treat this as permission to store real secrets in test resources; test artifacts and logs are frequently shared too.

## 46. Common Pitfall: Putting `spring.profiles.active` in the Wrong Place

Never put `spring.profiles.active` inside `application-local.yml` or inside a document guarded by `spring.config.activate.on-profile`.

Correct: choose the profile via CLI, ENV, test annotations, or an appropriate non-profile-specific source.

Separating **profile selection** from **profile configuration** is a core principle of this design.

## 47. Common Pitfall: Missing Secret Yet Application Still Starts

Causes can include an unsafe default, a disabled guard, unexpected placeholder behavior, or code failing to enforce the token check when `enabled=true`.

Actions:

- Verify the `prod` profile is active.
- Verify the guard/validator bean is registered.
- Add tests with missing and blank tokens.
- Never print the token in error messages.
- Ensure no outbound calls are attempted when config is invalid.

If you want binding itself to fail immediately, model the constraint directly via `@ConfigurationProperties`/Bean Validation or a dedicated validator rather than waiting until the service sends its first request.

## 48. Common Pitfall: Unexpected List and Map Results

A `List` with two items in common and one in prod typically ends up with only the prod item. A `Map`, by contrast, merges and overrides keys.

Prevention: document collection semantics clearly and test bound typed objects. On large configuration changes, never guess final values by eyeballing isolated YAML snippets.

## 49. Common Pitfall: Prod Context Fails to Start in Tests

Because `application-prod.yml` contains required placeholders, a test with `@ActiveProfiles("prod")` that omits dummy endpoints/tokens will fail. That is a signal to **supply test fixtures**, not to put real secrets into tests.

Use `@SpringBootTest(properties=...)` with dummy values; verify the endpoint never opens real connections and that guards check only format/presence as intended.

When testing expected startup failures, `ApplicationContextRunner` is often better suited than `@SpringBootTest`, because `@SpringBootTest` test methods cannot run if the context fails during startup.

## 50. Exercise 1: Determine Effective Values Manually

Given:

```yaml
# application.yml
app:
  batch:
    size: 40
    flush-interval: 5s
```

```yaml
# application-local.yml
app:
  batch:
    size: 10
```

With profile `local`, answer:

1. `batch.size` is 10.
2. `batch.flush-interval` is 5s.
3. Why is there no need to repeat `flush-interval` in the local file?
4. If `--app.batch.size=15` is passed via CLI, which value normally wins?

## 51. Exercise 2: Separate Responsibilities Across Files

A teammate wants to put `display-name`, `max-attempts`, `batch.size`, `auth-token`, and `region` into all three files (`local`, `test`, and `prod`).

Redesign this so that:

- Shared properties live in `application.yml`.
- Environment differences live in profile files.
- Secrets come from protected external sources.
- Test fixtures live in `src/test/resources`.
- A table documents which values must be overridden in `prod`.

The goal is minimizing duplication while preventing unsafe defaults.

## 52. Exercise 3: Testing `@ConfigurationProperties`

Add:

```java
@ConfigurationProperties(prefix = "app")
public record AppSettings(
    String displayName,
    Batch batch
) {
    public record Batch(int size, Duration flushInterval) {}
}
```

Write a `@SpringBootTest` with `@ActiveProfiles("local")` and assert:

```java
assertThat(settings.batch().size()).isEqualTo(10);
assertThat(settings.batch().flushInterval())
    .isEqualTo(Duration.ofSeconds(5));
```

Explain the difference between `"5s"` in YAML and the `Duration` object in Java.

## 53. Exercise 4: Spotting Secret Risks

Given `application-prod.yml`:

```yaml
app:
  outbound:
    auth-token: "live-token-here"
```

Replace it with a placeholder, state where the token should be provisioned, and explain why you must never:

- Commit the token to Git.
- Print the entire `AppSettings` object.
- Expose raw Actuator values on a public port.
- Use production tokens in CI tests.

## 54. Exercise 5: Writing a Test for the `test` Profile

Requirements:

- `app.batch.size=5`.
- `app.outbound.enabled=false`.
- `app.outbound.connect-timeout=100ms`.
- `app.diagnostics.verbose=false`.

Write `application-test.yml` in `src/test/resources` and a test:

```java
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
```

Assert the typed bean and confirm the test needs no real API token.

## 55. Exercise 6: Guarding the `prod` Profile

Requirements for `prod`:

- Outbound must be enabled.
- Endpoint must use HTTPS.
- Token must be non-blank.
- Token must never be logged.
- Default sandbox address must not be used.

Write an appropriate startup check, test it with a dummy token, and explain why checking only inside `ApplicationRunner` can be too late to prevent side effects in bean constructors.

## 56. Exercise 7: Multiple Profiles

Run:

```bash
java -jar app.jar --spring.profiles.active=local,prod
```

Predict the risks:

- Some `prod` properties may override `local` ones.
- `@Profile("local")` and `@Profile("prod")` beans may coexist.
- Bean injection can become ambiguous.
- Simulated settings may mix with production credentials.

Propose a policy enforcing a single primary environment profile alongside clearly named, single-purpose additive profiles.

## 57. Exercise 8: Handling Deployment Overrides

The prod file has:

```yaml
app:
  batch:
    size: 200
```

Deployment sets:

```text
APP_BATCH_SIZE=300
```

Explain why the effective value can be 300 and how to confirm it via `Environment` or secured Actuator `env` on the right instance. If you want 200 from the prod file, remove or update the deployment override.

## 58. Exercise 9: Using External Sources Outside the JAR

Requirement: Cluster A and Cluster B run the exact same JAR and the same `prod` profile, yet need different endpoints and regions.

Design this so that:

- `application-prod.yml` holds shared production structure.
- Region and endpoint come from external Config Data or cluster ENV.
- Tokens come from dedicated secret stores.
- Tests verify each cluster reads only its own source.
- No per-pod profile names are created unnecessarily.

## 59. Exercise 10: Writing a Configuration Contract Table

Build a table for all 10 properties in the lab with columns:

```text
name | Java type | common default | local | test | prod |
required | source owner | sensitive | validation
```

State policies covering:

- No real secrets in the repository.
- Explicit time units.
- No unnecessary duplication of defaults.
- Runtime behavior must be verifiable via tests.
- Primary environment profiles must not be mixed unintentionally.

## 60. Summary

Designing shared configuration with three profiles moves you from "one application per environment" to "one application, multiple controlled value sets."

```text
               application.yml
               (common defaults)
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
 application-local  application-test  application-prod
    (local)            (test)             (prod)
          |           |           |
          +-----------+-----------+
                      |
              Externalized Configuration
                      |
               Environment / Binder
                      |
                @ConfigurationProperties
                      |
                Application services
```

Key rules to remember:

1. **Common holds only shared configuration and safe defaults.**
2. **Profile files hold only differences**; avoid copy-pasting entire YAML files.
3. **Local** prioritizes fake endpoints, small batches, good observability, and zero production calls.
4. **Test** prioritizes deterministic, isolated fixtures with no real secrets; when used only by test runners, place `application-test.yml` in `src/test/resources`.
5. **Prod** prioritizes external secrets, strict validation, HTTPS, and clear operational policies.
6. **Never put `spring.profiles.active` inside profile-specific files** or `on-profile` documents.
7. **Never expect `local` to activate automatically just because a local file exists**; select profiles via environment, CLI, or test annotations.
8. **Multiple active profiles can conflict**, especially `local` and `prod`; enforce clear policies for primary vs. additive profiles.
9. **`@ConfigurationProperties`** binds typed data; **Bean Validation** enforces the contract.
10. **Config Data precedence** decides what wins; profile files are not the sole source.
11. **Never log objects containing tokens**, and never treat environment variables as an unconditionally secure secret vault.
12. **Test both overrides and common fallbacks**, not just single properties in isolation.
13. **One artifact works across all environments** once configuration is decoupled from the build.
14. **Inspect the exact running instance** via `Environment` or secured Actuator when values diverge from expectations.
15. **Never assume `enabled=false` blocks side effects automatically**; code must actively enforce it.

### Official References

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestContext Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
