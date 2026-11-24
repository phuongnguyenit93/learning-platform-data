# Separating Test Configuration from Production Secrets and Services in Spring Boot

> **Module:** Spring Boot – testing  
> **Knowledge group:** Test environment configuration  
> **Focus:** Tests must use controllable configuration, dummy data, and isolated infrastructure. Never let a JUnit run accidentally call production APIs, modify a live database, or leak credentials.

## 1. Why is separating test environments a safety requirement, not merely convenience?

A test can pass "green" and still cause harm if it targets the wrong environment:

- `@SpringBootTest` loads the full `ApplicationContext` and initializes a client using a production URL inherited from a developer machine's environment variable.
- An integration test calls `repository.deleteAll()` against a live database because both share `spring.datasource.url`.
- A test sends payment emails/SMS to real customers because the gateway is constructed from active application settings.
- CI prints `API_TOKEN` or a JDBC password into test reports, assertion failures, HTTP logs, or build artifacts.
- Tests depend on production services, making them slow, flaky, rate-limited, or incurring real resource costs.
- A developer enables the `test` profile, yet a component reads `System.getenv("PROD_API_URL")` directly, bypassing all Spring configuration.

**The right goal:** tests must be **safe by default** (*fail closed*), running against isolated resources and dummy secrets or test-only credentials. When interaction with a real service is needed, that belongs in a separate test targeting **sandbox/staging** with dedicated permissions, accounts, and data—never use production as a testbed.

Three axes to separate simultaneously:

| Axis | Tests should use | Production uses | If unseparated |
| --- | --- | --- | --- |
| **Configuration** | `test` profile, properties in `src/test/resources`, explicit overrides | `prod` profile, dedicated external config | Tests load wrong URLs/timeouts/flags |
| **Secrets** | No real secrets, or test-only secrets with minimal scope and TTL | Secret store, IAM roles, vault/secret manager | Keys leak or tests hold production permissions |
| **Services and data** | Mockito fakes, mock HTTP, in-memory DB, Testcontainers, sandbox accounts | Live DB, payment/email/broker/live APIs | Tests create/modify/delete real data |

**Simply selecting `@ActiveProfiles("test")` is not enough to guarantee complete safety.** It helps pick profile-conditional beans and config, yet does not replace egress controls, least privilege, test-safe defaults, dependency injection, and assertions on target endpoints.

## 2. Understanding Spring Boot configuration layers

Spring Boot supports externalized configuration via `application.yml`, `application-{profile}.yml`, environment variables, JVM system properties, command-line arguments, and test property mechanisms.

Sensible layout example:

```text
src/
├── main/
│   ├── java/                          # Code packaged into the application
│   └── resources/
│       ├── application.yml            # Only safe/common defaults
│       └── application-prod.yml       # Property keys + secret placeholders
└── test/
    ├── java/                          # Tests, fakes, @TestConfiguration
    └── resources/
        └── application-test.yml       # Test-only, no production secrets
```

### 2.1. Role of each file

- **`application.yml`:** application name and non-sensitive shared defaults, with no production URLs or passwords. If a valid environment is not yet known, **do not put production as the default**.
- **`application-prod.yml`:** properties applied only when `prod` is active; should contain **references** to environment variables/secret managers, never real secret values.
- **`src/test/resources/application-test.yml`:** configuration for the test classpath; favor in-memory/ephemeral services, fake clients, or test-only endpoints. This file stays out of the main build artifact under standard Maven/Gradle setup.
- **`@ActiveProfiles("test")`:** activates the `test` profile when Spring TestContext loads the context for a test class.
- **`@TestConfiguration`, `@Import`, `@MockitoBean`:** replace external dependencies with explicit test doubles. `@ActiveProfiles` selects config; test doubles **actually prevent code from calling production adapters**.

**Point to remember:** Profiles decide **which configurations and beans are selected**; they do not decide whether the network is blocked. A bean can still call an external address if its configuration allows it.

### 2.2. Effect of `@ActiveProfiles`

```java
@SpringBootTest
@ActiveProfiles("test")
class ExampleIntegrationTest {
    // Context uses the test profile via Spring TestContext.
}
```

This snippet illustrates the annotation on a test class; it needs the corresponding imports and a valid Spring Boot application to run. With `@ActiveProfiles("test")`, Spring TestContext determines active profiles from the annotation (and its inheritance/resolver rules). **`SPRING_PROFILES_ACTIVE` does not automatically replace this annotation's value** under TestContext's default profile resolution; however, other config sources, profile includes/groups, and custom resolvers must still be checked in your app.

If someone **explicitly** activates multiple profiles—such as `test,prod`—beans annotated with `@Profile("prod")` can be instantiated. Never rely on a test filename as a barrier against combined profiles.

### 2.3. Avoid misunderstanding property precedence

Property sources follow precedence rules; **values from higher-priority sources override YAML files**. For instance, command-line arguments or test-specific configuration can override a property from `application.yml`. Therefore:

- Do not intentionally point `application.yml` to production hoping `application-test.yml` will always override it.
- In integration tests, use `@SpringBootTest(properties = "...")` or `@TestPropertySource` for local test-only values.
- `@DynamicPropertySource` fits when an address/port is only known after a container or mock server starts.
- Always check the **effective URL/bean type** in tests when connection safety is critical; do not rely solely on a file being named `application-test.yml`.
- Avoid putting `spring.profiles.active` inside `application-test.yml`/`application-prod.yml` itself: Spring Boot requires active/default profiles to be set only in **non-profile-specific** documents.

The next section builds a sample project where tests **have no knowledge of production tokens** and cannot call the production HTTP adapter through the business port.

## 3. Java 17 / Spring Boot 3.5 project: replacing the real adapter with a fake in tests

Scenario: `RegistrationService` registers an email and must send a welcome message via `NotificationGateway`.

- In production, an HTTP adapter sends requests with a bearer token.
- Locally, a no-op adapter makes no network calls.
- In integration tests, we import a **recording fake** from `src/test/java`.
- **There are no** production endpoints or tokens in default or test configs.
- Running the application **without selecting an appropriate profile** fails startup due to a missing `NotificationGateway`. This is an **intentional fail-closed choice**, not a configuration bug to "fix" by enabling `prod` in tests.

### 3.1. Directory layout

```text
safe-test-environment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safeconfig/
    │   │   ├── SafeConfigApplication.java
    │   │   ├── NotificationGateway.java
    │   │   ├── RegistrationService.java
    │   │   ├── RegistrationRequest.java
    │   │   ├── RegistrationResult.java
    │   │   ├── RegistrationController.java
    │   │   ├── LocalNotificationGateway.java
    │   │   └── HttpNotificationGateway.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/
        ├── java/com/example/safeconfig/
        │   ├── RecordingNotificationGateway.java
        │   ├── SafeTestConfiguration.java
        │   ├── RegistrationServiceTest.java
        │   ├── RegistrationIsolationTest.java
        │   └── HttpNotificationGatewayTest.java
        └── resources/
            └── application-test.yml
```

Every `package` in the example is `com.example.safeconfig`; place each `public class`/`public record`/`public interface` in its matching filename. Use **Java 17 or higher**, Maven, and Internet access only to fetch initial Maven dependencies. Tests call no external services.

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-test-environment</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-web` provides MVC/Jackson/`RestClient` for the adapter. `spring-boot-starter-test` in Maven `scope=test` supplies JUnit Jupiter, Mockito, Spring Test, and `MockRestServiceServer` for the tests. The parent BOM manages compatible versions.

### 3.3. Main application and internal contracts

```java
// src/main/java/com/example/safeconfig/SafeConfigApplication.java
package com.example.safeconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeConfigApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/safeconfig/NotificationGateway.java
package com.example.safeconfig;

public interface NotificationGateway {
    void send(String recipient, String message);
}
```

```java
// src/main/java/com/example/safeconfig/RegistrationService.java
package com.example.safeconfig;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationGateway gateway;

    public RegistrationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    public String register(String rawEmail) {
        if (rawEmail == null || rawEmail.isBlank()) {
            throw new IllegalArgumentException("Email must not be blank");
        }
        String email = rawEmail.trim().toLowerCase(Locale.ROOT);
        gateway.send(email, "Welcome!");
        return email;
    }
}
```

```java
// src/main/java/com/example/safeconfig/RegistrationRequest.java
package com.example.safeconfig;

public record RegistrationRequest(String email) {}
```

```java
// src/main/java/com/example/safeconfig/RegistrationResult.java
package com.example.safeconfig;

public record RegistrationResult(String email) {}
```

```java
// src/main/java/com/example/safeconfig/RegistrationController.java
package com.example.safeconfig;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {
    private final RegistrationService service;

    public RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @PostMapping("/register")
    public ResponseEntity<RegistrationResult> register(
            @RequestBody RegistrationRequest request) {
        String normalized = service.register(request.email());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new RegistrationResult(normalized));
    }
}
```

`RegistrationService` only knows the `NotificationGateway` port—not domains, tokens, URLs, or HTTP clients. That enables tests to swap adapters without reading secrets. This minimal example defines no HTTP exception handler for blank inputs; test invalid input at the service layer to avoid assuming an HTTP status code here.

### 3.4. Production adapter only appears when `prod` is explicitly chosen

```java
// src/main/java/com/example/safeconfig/HttpNotificationGateway.java
package com.example.safeconfig;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
@Profile("prod")
public class HttpNotificationGateway implements NotificationGateway {
    private final RestClient client;
    private final String token;

    public HttpNotificationGateway(
            RestClient.Builder builder,
            @Value("${app.notification.base-url}") String baseUrl,
            @Value("${app.notification.token}") String token) {
        URI uri = URI.create(baseUrl);

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                    "Production notification URL must use HTTPS");
        }
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException(
                    "Notification token must be configured");
        }

        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    @Override
    public void send(String recipient, String message) {
        client.post()
                .uri("/messages")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .body(new Payload(recipient, message))
                .retrieve()
                .toBodilessEntity();
    }

    public record Payload(String recipient, String message) {}
}
```

Two layers of protection:

1. `@Profile("prod")` excludes this adapter from contexts running only `test` or `local`.
2. URL and token are required, and the URL must use HTTPS when the bean is constructed. No default production URL or token exists in code or `application.yml`.

**Practical limitation:** requiring HTTPS **is not** a hostname allowlist; if runtime supplies the wrong HTTPS URL, the adapter could still call the wrong host. In critical systems, add DNS/network egress allowlists, separate IAM/service accounts, TLS trust policies, certificate pinning when required, and deployment controls. Never treat `@Profile` or scheme checks as the sole safeguard.

### 3.5. Safe adapter for local runs

```java
// src/main/java/com/example/safeconfig/LocalNotificationGateway.java
package com.example.safeconfig;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalNotificationGateway implements NotificationGateway {
    @Override
    public void send(String recipient, String message) {
        // Local-only: performs no HTTP/email/SMS calls.
    }
}
```

The `local` profile lets developers run the app manually with no secrets and no real notifications. Automated tests do not rely on the local adapter: they use their own recording fake. Do not turn a local no-op into a **fallback** for production: if the `prod` profile is misconfigured, startup should fail rather than silently dropping notifications.

### 3.6. Configuration files containing no real secrets

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: safe-test-environment
```

```yaml
# src/main/resources/application-prod.yml
app:
  notification:
    base-url: ${NOTIFICATION_BASE_URL}
    token: ${NOTIFICATION_TOKEN}
```

```yaml
# src/test/resources/application-test.yml
spring:
  main:
    banner-mode: "off"
app:
  safety:
    environment: isolated-test
```

When tests activate `test`:

- `application-test.yml` provides the marker `app.safety.environment=isolated-test` to confirm the profile-specific config loaded.
- No production URL or token is needed for `RegistrationService` because the production gateway **is not created**.
- The test fake is imported via `@TestConfiguration`, not toggled through a property enabling/disabling production sending.
- A test checking only `app.safety.environment` is not enough to guarantee zero outbound traffic; tests must also verify the gateway type and enforce network policies where needed.

Only when the app runs with `prod` does Spring Boot read `application-prod.yml` and require `NOTIFICATION_BASE_URL` and `NOTIFICATION_TOKEN` from the **official** runtime. Those two `${...}` strings are Spring Boot placeholders, not secret values. Never put real tokens in Git, unit tests, snapshots, or example commands.

## 4. Test-only fakes live in `src/test/java`

Instead of putting fakes in `src/main/java` and risking packaging them into the production artifact, define the **recording fake** in the test source set.

```java
// src/test/java/com/example/safeconfig/RecordingNotificationGateway.java
package com.example.safeconfig;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class RecordingNotificationGateway implements NotificationGateway {
    record Sent(String recipient, String message) {}

    private final List<Sent> messages = new CopyOnWriteArrayList<>();

    @Override
    public void send(String recipient, String message) {
        messages.add(new Sent(recipient, message));
    }

    List<Sent> messages() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}
```

```java
// src/test/java/com/example/safeconfig/SafeTestConfiguration.java
package com.example.safeconfig;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class SafeTestConfiguration {
    @Bean
    RecordingNotificationGateway recordingNotificationGateway() {
        return new RecordingNotificationGateway();
    }
}
```

`@TestConfiguration` marks this as test-specific configuration; we use `@Import(SafeTestConfiguration.class)` to **explicitly** declare that the test context needs this fake. Because the fake lives in `src/test/java`, standard `jar`/`bootJar` builds exclude it. Classpath isolation reduces the chance of test helpers becoming production beans.

Using a recording fake has advantages over `@Mock` in integration tests when you want to inspect the full recorded payload after a request. It sends no HTTP requests and depends on no external services. For pure unit tests, Mockito mocks remain ideal.

## 5. Two testing tiers: context-free unit tests and profile-isolated integration tests

### 5.1. JUnit + Mockito unit tests without touching the Spring context

```java
// src/test/java/com/example/safeconfig/RegistrationServiceTest.java
package com.example.safeconfig;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {
    @Mock
    NotificationGateway gateway;

    @InjectMocks
    RegistrationService service;

    @Test
    void normalizesEmailBeforeSending() {
        String registered = service.register(" Alice@Example.Test ");

        assertEquals("alice@example.test", registered);
        verify(gateway).send("alice@example.test", "Welcome!");
    }

    @Test
    void rejectsBlankInputWithoutSending() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.register("   "));
        verifyNoInteractions(gateway);
    }
}
```

The unit test runs the real `RegistrationService` with a Mockito gateway, so **it opens no Spring ApplicationContext**, resolves no `application-prod.yml`, and performs no network I/O. Mockito mocks also let you verify exact outbound arguments rather than merely asserting no errors occurred.

One gap to avoid: if business code instantiates `new RestClient(...)` itself or calls a static client driven by `System.getenv`, mocking `NotificationGateway` will not intercept calls outside the abstraction. Dependency injection is essential for test isolation.

### 5.2. Integration tests with `@ActiveProfiles("test")` and a fake

```java
// src/test/java/com/example/safeconfig/RegistrationIsolationTest.java
package com.example.safeconfig;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(SafeTestConfiguration.class)
class RegistrationIsolationTest {

    @Autowired
    Environment environment;

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RecordingNotificationGateway gateway;

    @BeforeEach
    void resetFake() {
        gateway.clear();
    }

    @Test
    void hasTestProfileAndNoProdProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertFalse(environment.acceptsProfiles(Profiles.of("prod")));
        assertEquals("isolated-test",
                environment.getProperty("app.safety.environment"));
    }

    @Test
    void postRequestUsesOnlyRecordingGateway() throws Exception {
        mockMvc.perform(post("/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":" Alice@Example.Test "}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email")
                        .value("alice@example.test"));

        assertEquals(
                List.of(new RecordingNotificationGateway.Sent(
                        "alice@example.test", "Welcome!")),
                gateway.messages());
    }
}
```

What is verified:

- The test context loads the `test` profile and the marker property from `application-test.yml`.
- The `prod` profile is absent from the inspected environment.
- The controller receives JSON via `MockMvc`, the real service normalizes the email, and dispatches to the **recording fake**.
- The fake records the outbound message without opening any network connection to the notification API.
- `MockMvc` tests Spring MVC **without opening an inbound HTTP socket**; it does not block outbound HTTP calls made by other beans on its own. Here outbound protection comes from replacing `NotificationGateway`.

Never assume a `!prod` assertion alone stops another bean from calling a production URL. A test context initializes before test method assertions execute. Thus production adapters must be **excluded from the bean graph before initialization**, and CI should block production networks/credentials independently.

### 5.3. Testing the HTTP adapter without sending real outbound requests

If we only mock `NotificationGateway`, we never test the JSON, headers, and HTTP method produced by the adapter. Spring Test offers `MockRestServiceServer` to intercept calls from `RestClient.Builder` and return mock responses **without a real HTTP server**.

```java
// src/test/java/com/example/safeconfig/HttpNotificationGatewayTest.java
package com.example.safeconfig;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class HttpNotificationGatewayTest {

    @Test
    void buildsCorrectHttpRequestWithoutRealNetwork() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(
                    "https://notify.example.test/messages"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header(HttpHeaders.AUTHORIZATION,
                        "Bearer fake-test-token"))
                .andExpect(content().json("""
                        {"recipient":"alice@example.test",
                         "message":"Welcome!"}
                        """))
                .andRespond(withSuccess());

        HttpNotificationGateway adapter =
                new HttpNotificationGateway(
                        builder,
                        "https://notify.example.test",
                        "fake-test-token");

        adapter.send("alice@example.test", "Welcome!");
        server.verify();
    }

    @Test
    void rejectsNonHttpsConfiguration() {
        assertThrows(IllegalArgumentException.class,
                () -> new HttpNotificationGateway(
                        RestClient.builder(),
                        "http://notify.example.test",
                        "fake-test-token"));
    }
}
```

When constructing the object directly with `new` in an adapter unit test, `@Profile("prod")` **is not evaluated by Spring**—which is expected, as the annotation only applies when Spring creates beans. This test loads no production properties and needs no real token. `MockRestServiceServer` swaps out the builder's request factory so requests are matched in memory instead of hitting `notify.example.test`.

`notify.example.test` is a reserved example domain for testing, not a production host. `fake-test-token` is a dummy string. This suite verifies the adapter constructs the right request; it **does not** test TLS handshakes, DNS, retries, proxies, timeouts, or real networking. When transport testing is required, use an HTTP stub server/WireMock/MockWebServer on loopback with a random port and explicit test-only setup.

### 5.4. Run commands

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=RegistrationServiceTest test
mvn -Dtest=RegistrationIsolationTest test
mvn -Dtest=HttpNotificationGatewayTest test
```

Requires JDK 17+, Maven, and permission to download dependencies on initial setup. Tests require no DB, broker, or Internet at runtime; Maven only needs network access if dependencies are not yet cached. Maven/Spring logs vary by environment, so **no fixed stdout is specified**; each assertion verifies concrete outcomes.

To run the application **safely locally** (without HTTP notifications):

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

When run by default **with no profile selected**, the app intentionally lacks a `NotificationGateway` and fails startup. The proper developer workflow is selecting `local`. **Do not select `prod` just "to get the app running"** and never supply production secrets on a test machine just to fix an injection error.

## 6. Protecting tests from the production database

An HTTP gateway is only one risk. Databases are even riskier because tests routinely insert, update, and delete many records.

**Do not do this:**

```yaml
# Misdirected configuration, illustrative example:
spring:
  datasource:
    url: jdbc:postgresql://production-db.internal:5432/app
```

If that lives in `application.yml`, a repository test that fails to override it could connect to the real DB. Running tests inside a transaction is also insufficient protection when DDL, out-of-transaction operations, listeners, async jobs, or custom rollback configurations are involved.

**Do this instead:** keep production URLs out of default config; let the test profile use a dedicated test DB with least-privilege credentials and self-cleanup, ideally ephemeral.

### 6.1. In-memory H2 for simple tests

This is an **additional recipe for projects using Spring Data JPA**, not part of the sample `pom.xml` in Section 3 since the notification example uses no database. In a JPA project, declare:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>test</scope>
</dependency>
```

And in the JPA project's `src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:isolatedtests;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

H2 stays on the test classpath, requires no production passwords, and runs inside the test process. Distinct database names can isolate separate test contexts from leaking data. `DB_CLOSE_DELAY=-1` keeps the DB alive until JVM exit, so it **does not automatically reset between test methods**; use transaction rollbacks, data cleanup, and separated contexts/DBs when needed.

**Limitation:** H2 differs from PostgreSQL/MySQL in SQL dialects, JSON types, locking, indexes, transaction isolation, migrations, and constraints. When those details are part of your contract, use the matching database engine in an isolated environment.

### 6.2. Testcontainers for a production-like yet isolated database

Another option: run PostgreSQL in an ephemeral Docker container, **never connecting to production PostgreSQL**. With Spring Boot 3.5 and matching Testcontainers libraries, use `@ServiceConnection` or `@DynamicPropertySource`.

Additional dependencies in a **JPA/PostgreSQL project**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Illustrative container integration test (requires real entity/repository in a JPA project and running Docker; **not a standalone test in the notification example**):

```java
@Testcontainers
@SpringBootTest
@ActiveProfiles("test")
class RepositoryContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CustomerRepository repository;

    @Test
    void writesOnlyToEphemeralDatabase() {
        Customer saved = repository.save(
                new Customer("alice@example.test"));
        assertEquals("alice@example.test",
                repository.findById(saved.getId())
                        .orElseThrow().getEmail());
    }
}
```

This snippet **illustrates the pattern**, assuming `CustomerRepository`/`Customer` and imports are defined in the JPA project. It requires Docker and a compatible PostgreSQL driver/dependency, plus Flyway/Liquibase/schema setup if applicable. `@ServiceConnection` lets Spring Boot discover the container's JDBC connection details automatically. The container itself uses ephemeral ports and credentials—never copy production URLs/usernames/passwords.

If using `@DynamicPropertySource` instead of `@ServiceConnection`, feed the container's URL/username/password into the context:

```java
@DynamicPropertySource
static void containerProps(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Use this only when `postgres` is a properly lifecycle-managed container, and avoid mixing both mechanisms on the same connection without good reason. **Never mix** testcontainer credentials with production secrets. Isolate networks/projects/containers, and never mount production backups containing real customer data into tests.

### 6.3. Safe habits with test data

- Prefer synthetic/dummy data; never use real customer data for functional testing.
- Use dedicated schemas/DBs and dedicated test users without `DROP DATABASE` or production privileges.
- Rely on explicit cleanup/rollbacks; know the limits of `@Transactional` rollbacks for requests executing on other threads/transactions.
- When parallel test execution is enabled, avoid sharing DB names/fixtures or apply an isolation strategy.
- If using a separately hosted test DB, verify the host belongs to your organization's allowlist and credentials hold test-only permissions.
- Never run destructive commands from CI if target URLs are unverified; pipelines should enforce guards before tests start.

## 7. Preventing email, SMS, payment, Kafka, and HTTP calls to production

Beyond datasources, many libraries open connections automatically via auto-configuration or lifecycle hooks:

| Resource | Safe testing | What not to do |
| --- | --- | --- |
| Email/SMTP | Fake `MailSender`, in-memory mailbox, SMTP test server | Sending emails to real customer mailboxes |
| SMS/push | Mock gateway, sandbox account, and fake phone numbers | Using production tokens/recipients |
| Payment gateway | Fake/contract tests with sandbox credentials | Charging/refunding on live accounts |
| Outbound REST/gRPC | Mockito ports, `MockRestServiceServer`, loopback WireMock/MockWebServer | Reading production base URLs directly |
| Kafka/RabbitMQ | Embedded/mock producers for unit; ephemeral brokers for integration | Publishing onto production topics/queues |
| Object storage | Local emulator, dedicated test buckets, and test object prefixes | Writing/deleting production buckets |
| Search/cache | Dedicated container or test service, isolated namespaces | Flushing/clearing production caches |
| OAuth/OIDC | Fake tokens/key pairs or local authorization server | Using production client secrets in tests |

When tests target a provider's **real sandbox**, sandboxes can still carry costs, quotas, and sensitive data. Tag such suites as external integration, use dedicated accounts/keys, enforce rate limits, timeouts, scoped data, and cleanup.

**Simply swapping `@ActiveProfiles` cannot stop a library that directly calls `System.getenv` or static singletons.** Prefer injected port interfaces, centralize client setup, and never call external endpoints inside constructors or `@PostConstruct`. Fewer side effects during bean initialization make contexts far easier to control.

## 8. Principles for managing secrets

### 8.1. Where must secrets never go?

Never place **real secret values** in:

- `application.yml`, `application-test.yml`, `application-prod.yml`, or any committed file.
- Test code, fixtures, snapshots, hard-coded `@Value`, or defaults like `${TOKEN:real-token}`.
- Raw strings inside GitHub Actions/GitLab CI YAML.
- Logs emitted during Spring property binding, HTTP request/response interceptors, exception stack traces, or test failure messages.
- Surefire artifacts, reports, screenshots, build scans, or caches that might capture secret payloads.
- CLI flags passing tokens directly in multi-user environments, where process lists and shell history retain them.

**Real test secrets** (if an external sandbox test truly requires them) must be **dedicated credentials**, minimally scoped, short-lived when possible, provisioned via a CI secret manager or workload identity, and never shared with production. Not every test needs secrets; unit tests and most mock HTTP tests should run with **zero secrets**.

### 8.2. Environment variables are delivery channels, not automatic security

Good example of **referencing** values (containing no real data):

```yaml
# application-prod.yml — never commit real values
app:
  notification:
    base-url: ${NOTIFICATION_BASE_URL}
    token: ${NOTIFICATION_TOKEN}
```

In production runtime, values come from a secret manager/CI/CD deployment and are scoped to the right app. Yet **an environment variable can still leak** if logs, test harnesses, process dumps, or other CI jobs read it. Never forward all production environment variables automatically into test jobs.

If a secret was ever committed, deleting the line in a later commit **does not erase Git history**. Immediately **revoke/rotate** the secret, audit for suspicious usage, and scrub repository history per security procedures—never just add it to `.gitignore` and call it done.

### 8.3. Local files and `.gitignore`

Optional local files like `.env.local` or `secrets.local.yml` should not be committed. You can configure:

```gitignore
.env
.env.*
!.env.example
secrets.local.yml
*.pem
```

Use `.env.example` only with **variable names and dummy values**, never production credentials. Remember `.gitignore` **does not untrack files already tracked by Git** and does not replace secret scanning. Some projects legitimately commit public certificates or dummy test keys; evaluate those case by case instead of blindly banning every `*.pem`.

### 8.4. Why are fake tokens in unit tests still useful?

In `HttpNotificationGatewayTest`, `fake-test-token` is just a deterministic string for comparing headers. It verifies the code formats requests properly without **granting access** to any live provider. Dummy tokens do not belong in a secret manager and must never be reused as active credentials in any real environment.

## 9. CI/CD: blocking accidental production access at the infrastructure layer

A sound pipeline never relies solely on Java annotations. Before running tests, enforce additional controls:

1. **Unit/slice jobs** receive no secrets, service accounts, or network routes to production—only dependency downloads.
2. **Integration jobs** use containers or isolated sandbox accounts; never mount production secrets.
3. **Staging/e2e jobs** run separately after staging deployment, with cleanup routines and least privilege.
4. **Production deployment jobs** require separate permissions/approvals; never let regular test jobs inherit production credentials.
5. Block outbound egress to production IP ranges/internal DNS if the CI platform supports it; use allowlists.
6. Validate targets before tests start; fail if config points to disallowed hosts/namespaces.
7. Never dump the environment (e.g., full `printenv`) or Maven debug logs containing `Authorization` headers.
8. Separate IAM roles, database users, buckets, queues, and network policies across test/staging/prod.

### 9.1. Example CI guard check (shell, not a complete secret scanner)

This example **only blocks one specific misconfiguration** and must not be treated as the sole security control:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "${SPRING_PROFILES_ACTIVE:-}" == *"prod"* ]]; then
  echo "Blocked: prod profile is not allowed in unit-test job" >&2
  exit 1
fi

if [[ -n "${NOTIFICATION_TOKEN:-}" ]]; then
  echo "Blocked: notification credential must not exist in unit tests" >&2
  exit 1
fi

mvn -B test
```

**Limitations:** substring matching `*prod*` can produce false positives/negatives with complex profile names or profile groups; other environment variables could still hold secrets; test annotations can override certain profile flags. Therefore use formal CI settings to **never provision production secrets** in the first place. A test framework must never be the sole boundary enforcing security.

If CI runs on shared runners, check permissions on masked/protected variables, fork PR handling, job artifacts, build caches, and retention. Do not leak secrets via HTTP client assertion failures that dump full request headers.

### 9.2. Separating stages by test goal

| Stage | Test type | Permissions / resources |
| --- | --- | --- |
| Pull request | Unit, MVC slice, contract tests with fakes | No production credentials, restricted egress |
| Merge/main | Integration with Testcontainers | Docker test runner, isolated network, test secrets if needed |
| Staging deploy | API/E2E smoke | Sandbox/staging account, test users, rate limits |
| Release/production deploy | Deploy and safe observability checks | Separate deploy permissions; never run destructive tests against prod |

Never run tests with `deleteAll`, schema resets, or synthetic transactions against production after deployment. If production health checks are needed, keep them non-destructive read probes with minimal privileges.

## 10. Complementary test configuration techniques

### 10.1. `@SpringBootTest(properties = ...)` for targeted overrides

When needing to test a specific feature flag or timeout in one class:

```java
@SpringBootTest(properties = {
        "app.retry.max-attempts=1",
        "app.client.read-timeout=250ms"
})
@ActiveProfiles("test")
class RetryPolicyIntegrationTest {
    // Illustration: real tests need the corresponding beans and assertions.
}
```

The snippet above is an **annotation pattern**, not a standalone runnable file. It works well for test-specific properties; never use it to overwrite a production secret inside a context already pointed at production. The safer design is **never creating the production client in test contexts**.

### 10.2. `@TestPropertySource`

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.feature.experimental=false"
})
class FeatureFlagTest {
    // Illustrates adding a local property for the test.
}
```

`@TestPropertySource` works with Spring TestContext to add properties for a test. If a property is common enough across many tests, put it in `application-test.yml` to avoid duplication and unnecessary context cache fragmentation.

### 10.3. `@DynamicPropertySource`

Used when endpoints/ports are assigned **at runtime** by Testcontainers or a mock HTTP server, for example:

```java
@DynamicPropertySource
static void externalServiceProperties(DynamicPropertyRegistry registry) {
    registry.add("app.remote.base-url", testServer::baseUrl);
}
```

This **illustrative pattern** is meaningful only when `testServer` has already started in the test lifecycle and `baseUrl()` returns that sandbox server's URL. `@DynamicPropertySource` adds no special security protection: if you register a production URL, it will gladly inject that production URL into your test context.

### 10.4. `@MockitoBean` to swap collaborators on context load

With Spring Framework 6.2/Spring Boot 3.5, you can declare:

```java
@SpringBootTest
@ActiveProfiles("test")
class MockedGatewayIntegrationTest {
    @MockitoBean
    NotificationGateway gateway;
}
```

This is an **illustrative snippet**: it needs imports for `SpringBootTest`, `ActiveProfiles`, `MockitoBean`, and a compatible application context. `@MockitoBean` creates/replaces a bean with a Mockito mock, differing from plain `@Mock` (which only creates a Java mock outside Spring). When multiple beans share a type/qualifier, handle selection precisely. Do not put `@MockitoBean` on a dependency you intend to test for real, or use it to claim the real adapter has no mapping bugs.

In the complete project in Sections 3–5, we chose `@TestConfiguration` + a recording fake to easily inspect sent events; `@MockitoBean` is not needed in that test.

### 10.5. One shared test profile or multiple profiles?

You can split `unit`, `integration`, and `staging` by purpose, though avoid creating an unpredictable tangle of profiles. If using multiple groups, document clearly which beans/services activate in each group. Grouping via JUnit `@Tag("integration")` **does not change** Spring profiles automatically; tag annotations are test-filtering metadata. Runners must configure stages and profiles/resources accordingly.

## 11. Common errors and how to fix them

### Error 1. Test uses a production URL from base config

**Symptom:** Test loads the Spring context, logs show calls to an internal production host, and live DB/tables are affected.

**Cause:** URL in `application.yml` or a high-precedence env var with no guard. **Fix:** remove production endpoints from base config, use `application-prod.yml` + runtime placeholders; move tests to fakes/containers, block egress, and restrict permissions. Do not merely add assertions after the Spring context has already booted.

### Error 2. Test profile is right, yet a bean still opens sockets

**Cause:** Bean is not profile-gated, builds a client inside its constructor/`@PostConstruct`, or calls a static client outside dependency injection.

**Fix:** place external calls behind an abstraction, keep client initialization free of side effects, gate the adapter clearly with `@Profile("prod")` or `@ConditionalOnProperty`, and swap in a fake in tests. Add CI network policy checks.

### Error 3. Copying production secrets into `application-test.yml` to make tests pass

**Cause:** Tests depend too tightly on production services or adapters, and someone "fixes" it with real credentials.

**Fix:** mock the dependency, use a container, or use least-privilege sandbox test credentials. If real credentials were ever committed, revoke/rotate them immediately per security policy and inspect logs/history/artifacts.

### Error 4. Changing only `server.port=0` and assuming all connections are isolated

`server.port=0` (or `webEnvironment=RANDOM_PORT`) only isolates the **inbound server port**. Outbound database/HTTP/Kafka calls still use their own URLs/credentials. Swapping outbound ports and controlling target URLs are the core of test isolation.

### Error 5. Using `localhost` inside a different runner or container

`localhost` inside a Docker/Kubernetes/CI container refers to **that process's own network namespace**, not necessarily the host machine or sibling containers. Use URLs provisioned by test infrastructure, container network hostnames/port mappings, or `@DynamicPropertySource`. Never fall back to production URLs when `localhost` fails to connect.

### Error 6. Putting fakes in `src/main/java` as a fallback for every profile

If production deploys with a missing environment variable, the app can silently pick up the fake and drop real events. Keep fakes strictly in the test source set, require `local` to be enabled explicitly, and make missing production config **fail startup** rather than falling back silently.

### Error 7. Re-running tests corrupts data from other tests

Sharing a fixed test DB, topic/bucket, or uncleaned fixture makes tests order-dependent and flaky. Partition namespaces, use isolated databases/containers, enforce rollbacks/cleanup, and watch out for parallel execution.

### Error 8. Forgetting that test reports/logs can retain secrets

HTTP interceptors or assertion failures can dump full `Authorization` headers. Log only safe status/codes/dummy IDs; redact tokens/passwords; configure logging appropriately. Never "debug" by dumping all properties/environment variables in CI.

### Error 9. Assuming `@ActiveProfiles("test")` is a complete sandbox

The annotation only selects active profiles for TestContext. It does not stop an SDK from reading env vars directly, block network access, or provision test credentials. Combine **fake/adapter isolation, sandbox data, network egress policies, and minimal IAM**.

### Error 10. Using `@DataJpaTest` while the test still hits an external DB

Repository slice tests can replace the datasource with an embedded database when applicable, depending on database dependencies and `@AutoConfigureTestDatabase` settings. If a test targets a specialized DB without an embedded replacement, it may connect to the configured URL. Always verify the effective datasource; pick H2 or Testcontainers explicitly rather than assuming every `@DataJpaTest` is automatically safe.

### Error 11. Turning on `prod` in the IDE to fix a missing bean

That signals unsafe defaults or a missing local adapter. Never run unit tests with production profiles or secrets. Provide an explicit `local` profile, fake adapters, and dev run instructions—or preserve fail-closed behavior as shown here.

### Error 12. Putting production hostnames into test expectations

When testing an adapter's path/method/body/headers, use reserved domains like `notify.example.test` with a mock request factory. If a fixed hostname is needed to test routing, use a **test-only** hostname incapable of resolving to production.

## 12. Review checklist and self-check questions

### 12.1. Pre-merge checklist

- [ ] `application.yml` contains no production endpoints, API keys, passwords, or dangerous fallbacks.
- [ ] Production properties only list keys/references to managed secret stores or env vars.
- [ ] Test contexts use `@ActiveProfiles("test")` (or an explicit equivalent) without unintentionally activating `prod`.
- [ ] Fakes/Mockito/HTTP stubs are injected **before** code can invoke outbound gateways.
- [ ] Integration tests verify no production adapters exist on the tested execution paths.
- [ ] HTTP client tests need no real DNS/network; transport tests use loopback stub servers.
- [ ] Test databases use H2 or dedicated PostgreSQL/MySQL Testcontainers/sandboxes, never production URLs.
- [ ] Test accounts/fixtures contain no real customer data; cleanup/rollback and parallel execution are planned.
- [ ] CI test jobs **do not receive** production secrets and lack network/database access to production.
- [ ] No tokens are printed to logs, assertion failures, build scans, or test artifacts.
- [ ] Exposed secrets are revoked/rotated rather than merely deleted from Git HEAD.
- [ ] If tests hit a real external sandbox, they run in a dedicated stage with test-only credentials and cost/resource caps.
- [ ] When test dependencies are missing, builds **fail clearly** instead of falling back to production.

### 12.2. Self-check questions

**Question 1.** If `@ActiveProfiles("test")` is present, is `@SpringBootTest` guaranteed not to make production HTTP calls?

**Answer:** No. It selects profiles/config, yet an unisolated bean or an SDK reading env vars directly can still reach production. You need fakes/conditional beans, test-only URLs, and network policies.

**Question 2.** Why should real API tokens never go in `application-test.yml`, even in a private repository?

**Answer:** Tokens can leak via Git history, forks, CI artifacts, backups, copy/paste, or logs. Unit tests need no production tokens. When sandbox tests require auth, use least-privilege test-only credentials from a secret manager.

**Question 3.** How does `@Profile("prod")` on an HTTP gateway differ from `@ActiveProfiles("test")` on a test?

**Answer:** `@Profile` sets a condition for Spring to **register a bean** when the matching profile is active; `@ActiveProfiles` tells TestContext to **activate profiles** when loading the context. Together they keep the production adapter out of test contexts.

**Question 4.** In the example, why didn't the MockMvc request send a real email?

**Answer:** The test context imported `RecordingNotificationGateway` instead of the production adapter. `MockMvc` only handles inbound requests inside Spring MVC test infrastructure; outbound delivery was blocked at the `NotificationGateway` port, not by MockMvc itself.

**Question 5.** Why can the HTTP adapter test verify the `Authorization` header without a real token?

**Answer:** Using `fake-test-token` and `MockRestServiceServer` inspects the request in memory. It verifies header/body/path formatting without authenticating against a live provider.

**Question 6.** When is H2 not enough?

**Answer:** When tests depend on SQL dialects, constraints, transactions, locking, or engine-specific types of the production database. In those cases, use a container running the same engine or a separately permissioned sandbox DB.

**Question 7.** If a production secret was committed and then deleted, is it safe now?

**Answer:** No. Secrets remain in Git history, clones, caches, and logs. Revoke/rotate it immediately and investigate exposure scope.

**Question 8.** If `mvn test` on CI still has access to the production DB, is that an issue even while tests use fakes?

**Answer:** Yes—risk remains whenever tests are added/edited or configuration gets overridden. By defense in depth, test jobs should have zero permissions or network routes to production from the start.

## 13. Official references

- Spring Boot 3.5 – [Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html): profile-specific files, `@Profile`, `spring.profiles.active`, profile groups.
- Spring Boot 3.5 – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): external configuration, property sources, and precedence.
- Spring Framework – [`@ActiveProfiles`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html): active profiles in Spring TestContext.
- Spring Boot 3.5 – [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, MockMvc, and test properties.
- Spring Framework 6.2 – [Testing Client Applications](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html): `MockRestServiceServer`, mocking HTTP clients, and limits compared to HTTP mock servers.
- Spring Boot 3.5 – [Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` and connecting to containers.
- OWASP – [Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lifecycles, access control, rotation, and secret management practices.

**Conclusion:** The objective is not "tests read a different config file" but "tests **cannot impact production systems under foreseeable failure scenarios**." Achieving that requires combining **explicit profiles + test-only beans/clients + separated secrets + isolated databases/services + CI/network guards + assertions verifying effective configuration**.