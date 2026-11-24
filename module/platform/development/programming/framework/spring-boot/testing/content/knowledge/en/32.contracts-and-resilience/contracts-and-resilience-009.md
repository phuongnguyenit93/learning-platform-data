# Testing Startup with Missing Configuration or Unavailable Resources

## 1. Goal: startup contracts and resilience

Within the **Contracts and Resilience** group of **Spring Boot - testing**, a good startup test must answer: **what does the application do when required configuration is missing, configuration has the wrong type, an external dependency is not ready, or an optional feature is disabled?**

Three contracts can be valid depending on the system:

- **Fail fast:** The application refuses to start when a required secret is missing, the database schema is invalid, or a critical remote dependency is unusable. The exception must be clear enough to remediate and must never contain secrets.
- **Degraded readiness:** The context may start, while readiness signals it should not receive traffic yet or a feature degrades via fallback/circuit breaker with transparent semantics.
- **Feature disabled:** A disabled feature's dependency **must not block startup** just because its host/port is missing or its external server is offline.

No Spring Boot rule guarantees that every `DataSource`/`KafkaTemplate`/`RestClient` bean **actually connects at bean creation time**. Many clients are lazy; therefore **a passing `contextLoads` test does not prove external services are ready**.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, `ApplicationContextRunner`, and Bean Validation**. The complete example creates a remote catalog gateway: when **`app.remote.enabled=true`**, host/port are required, and **`StartupDependencyProbe`** checks TCP connectivity during initialization; if the connection fails, the context fails to start. When `enabled=false`, neither the remote gateway nor the probe is created. Tests use a **fake `DependencyDialer`** to simulate `Connection refused` deterministically, and a separate **loopback `ServerSocket`** test verifies the real TCP connection adapter.

All stated results are **expected from the code**, not observed stdout from a Gradle or Docker run.

## 2. Distinguishing types of evidence

| Scenario | What to test | Evidence |
| --- | --- | --- |
| `enabled` omitted | Optional disabled | Context starts, zero remote beans |
| `enabled=false` | No connection made | No `StartupDependencyProbe` bean |
| `enabled=true`, host missing | Required config | Startup failure |
| `enabled=true`, port missing | Required config | Startup failure |
| Whitespace-only host | `@NotBlank` | Startup failure |
| `port=abc` | Type conversion | Startup failure |
| `port=70000` | `@Max(65535)` | Startup failure |
| `connect-timeout=0ms` | Timeout contract | Startup failure |
| Connection refused | Resource unavailable | Startup failure, root cause `ConnectException` |
| Fake connection succeeds | Startup policy | Context starts, properties and arguments accurate |
| Real `ServerSocket` listening | TCP adapter | `Socket.connect` succeeds |
| TCP open, HTTP API returns 503 | Protocol not ready | HTTP/protocol integration test |
| DB lost after app is READY | Runtime outage | Readiness, fallback, and recovery tests |

**Missing configuration** rarely heals via retries: environment/secrets must be fixed. **Temporary external outages** may retry, bounded by a deadline and backoff. Never catch `Exception` broadly and proceed to READY if the dependency is critical.

### Evidence layers must not be conflated

1. Environment contains the key.
2. `@ConfigurationProperties` bound and validated.
3. Bean instantiated.
4. TCP connection succeeded.
5. HTTP/TLS/DB/Kafka protocol health succeeded.
6. `ApplicationReadyEvent`/`ReadinessState` reached the intended state.
7. Business use case actually works.
8. Post-outage recovery works.

An assertion at layer 2 does not automatically prove layers 5–8.

## 3. Startup phases and test scope

~~~text
ConfigData / Environment
       |
       v
Auto-configuration conditions / bean definitions
       |
       v
@ConfigurationProperties binding + validation
       |
       v
Bean creation / InitializingBean / @PostConstruct
       |
       v
Context refresh
       |
       v
ApplicationStartedEvent
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent / readiness
~~~

This diagram is conceptual. Failures in properties binding, bean initialization, Flyway migrations, runners, or web-server binding can all block READY, yet occur in different phases.

**`ApplicationContextRunner`** spins up an isolated context and exposes any startup failure to test assertions. It fits **conditional registration, properties binding, and bean initialization**. It does not run full `SpringApplication.run` or application `ApplicationRunner`/`CommandLineRunner` beans. If failures occur only inside runners, migrations, or HTTP server binding, test at that higher phase.

In this example, `StartupDependencyProbe` **implements `InitializingBean`**. Spring invokes `afterPropertiesSet` during bean creation; if the remote dependency is unavailable, bean initialization fails and context startup fails. This is an **explicitly designed application policy**, not the default behavior of arbitrary network clients.

## 4. Boundary: real policy, fake dependency

~~~text
RemoteServiceAutoConfiguration
    |
    +-- @ConditionalOnProperty(enabled=true)
    |
    +-- RemoteEndpointProperties (@Validated)
    |       host, port, connectTimeout
    |
    +-- StartupDependencyProbe (real)
    |       |
    |       +-- DependencyDialer (port)
    |                |
    |                +-- SocketDependencyDialer (runtime)
    |                +-- RecordingDialer (fake success)
    |                +-- RefusingDialer (fake ConnectException)
    |
    +-- RemoteCatalogGateway (only after probe)
~~~

**Never mock `StartupDependencyProbe`**, because its fail-fast logic is the subject under test. Fake only `DependencyDialer` to control network outcomes independent of CI environments. Use **`@ConditionalOnMissingBean(DependencyDialer.class)`** so test fakes replace the default adapter cleanly.

Keep three separate test paths:
- **Invalid config:** real Binder and Bean Validation; zero network calls.
- **Resource unavailable:** fake throws `ConnectException`; real probe must fail startup.
- **Actual TCP adapter success:** a test-owned `ServerSocket` on `127.0.0.1`, port `0` so the OS assigns a free port; zero reliance on external servers.

## 5. Complete project: Java 17 / Spring Boot 3.4.5

### 5.1. File tree

~~~text
settings.gradle
build.gradle
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/main/java/com/example/startupchecks/StartupChecksApplication.java
src/main/java/com/example/remoteconfig/RemoteEndpointProperties.java
src/main/java/com/example/remoteconfig/DependencyDialer.java
src/main/java/com/example/remoteconfig/SocketDependencyDialer.java
src/main/java/com/example/remoteconfig/StartupDependencyProbe.java
src/main/java/com/example/remoteconfig/RemoteCatalogGateway.java
src/main/java/com/example/remoteconfig/RemoteServiceAutoConfiguration.java
src/test/java/com/example/remoteconfig/RemoteServiceAutoConfigurationTest.java
src/test/java/com/example/startupchecks/DiscoveryWithFakeDialerTest.java
~~~

Auto-configuration lives in **`com.example.remoteconfig`**, and the application lives in **`com.example.startupchecks`** (sibling packages). Keep the application from component-scanning the auto-config class; the discovery test verifies Boot finds it via the imports resource.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'startup-contract-testing'
~~~

### 5.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**`starter-validation`** supplies the Bean Validation implementation for `@NotBlank`/`@NotNull`/`@Min`/`@Max`. **`spring-boot-configuration-processor`** generates IDE metadata and does not replace the Binder. **`starter-test`** brings JUnit Jupiter and `ApplicationContextRunner`. No Spring MVC/JPA/Kafka is needed for these core tests; add them when testing resource-specific integrations.

### 5.4. `StartupChecksApplication.java`

~~~java
package com.example.startupchecks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupChecksApplication {
    public static void main(String[] args) {
        SpringApplication.run(StartupChecksApplication.class, args);
    }
}
~~~

### 5.5. `RemoteEndpointProperties.java`

~~~java
package com.example.remoteconfig;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public class RemoteEndpointProperties {

    @NotBlank
    private String host;

    @NotNull
    @Min(1)
    @Max(65535)
    private Integer port;

    @NotNull
    private Duration connectTimeout = Duration.ofMillis(250);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Integer getPort() {
        return port;
    }

    public void setPort(Integer port) {
        this.port = port;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration timeout) {
        this.connectTimeout = timeout;
    }
}
~~~

**Do not default `host` or `port`** so missing configuration is never masked when the feature is enabled. Using **`Integer`** distinguishes an unconfigured port (`null`) from `0`. The 250 ms default `Duration` can be overridden with **`app.remote.connect-timeout=750ms`**; positive-range checks run inside `StartupDependencyProbe`.

Spring Boot 3.4 applies Bean Validation to `@ConfigurationProperties` annotated with `@Validated`. For nested config objects, add **`@Valid`** to cascade Bean Validation when needed. **Relaxed binding** supports valid naming variations yet never fixes misspelled keys.

### 5.6. `DependencyDialer.java`

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.time.Duration;

public interface DependencyDialer {
    void verifyConnectivity(
        String host, int port, Duration timeout) throws IOException;
}
~~~

This is the sole outbound port for the startup network check. Unit tests swap in a fake that succeeds or throws `IOException` without touching DNS or firewalls.

### 5.7. `SocketDependencyDialer.java`

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.time.Duration;

public final class SocketDependencyDialer
        implements DependencyDialer {

    @Override
    public void verifyConnectivity(
            String host, int port, Duration timeout)
            throws IOException {

        int timeoutMillis =
            Math.toIntExact(timeout.toMillis());

        try (Socket socket = new Socket()) {
            socket.connect(
                new InetSocketAddress(host, port),
                timeoutMillis);
        }
    }
}
~~~

A successful TCP handshake does not prove HTTP 200, TLS, auth, database schemas, or broker leadership. Connect timeouts also do not necessarily bound DNS lookup time. When the requirement is protocol readiness, replace the dialer with a protocol-specific health/handshake check and write matching integration tests.

### 5.8. `StartupDependencyProbe.java`

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.time.Duration;
import java.util.Objects;

import org.springframework.beans.factory.InitializingBean;

public final class StartupDependencyProbe
        implements InitializingBean {

    private final RemoteEndpointProperties properties;
    private final DependencyDialer dialer;

    public StartupDependencyProbe(
            RemoteEndpointProperties properties,
            DependencyDialer dialer) {
        this.properties = Objects.requireNonNull(properties);
        this.dialer = Objects.requireNonNull(dialer);
    }

    @Override
    public void afterPropertiesSet() {
        Duration timeout = properties.getConnectTimeout();

        if (timeout == null
                || timeout.compareTo(Duration.ofMillis(1)) < 0
                || timeout.compareTo(
                    Duration.ofMillis(Integer.MAX_VALUE)) > 0) {
            throw new IllegalArgumentException(
                "app.remote.connect-timeout must be "
                + "between 1ms and Integer.MAX_VALUE ms");
        }

        try {
            dialer.verifyConnectivity(
                properties.getHost(),
                properties.getPort(),
                timeout);
        } catch (IOException ex) {
            throw new IllegalStateException(
                "required remote catalog unavailable at startup",
                ex);
        }
    }
}
~~~

Real bean initialization validates the timeout and calls the dialer. When refused, `IOException` is preserved as the cause; Spring container startup failures may wrap it in `BeanCreationException`. Inspect **`rootCause`** in tests instead of asserting fragile full stack traces that vary across patch versions.

**`timeout=0`** in Java `Socket.connect` can mean waiting indefinitely; validating a positive duration is part of the startup contract. The demo probes once without **retrying**. Production services may add bounded retries with deadlines if a remote dependency boots slowly, tested separately.

### 5.9. `RemoteCatalogGateway.java`

~~~java
package com.example.remoteconfig;

import java.util.Objects;

public final class RemoteCatalogGateway {
    private final RemoteEndpointProperties properties;
    private final StartupDependencyProbe checkedAtStartup;

    public RemoteCatalogGateway(
            RemoteEndpointProperties properties,
            StartupDependencyProbe checkedAtStartup) {
        this.properties = Objects.requireNonNull(properties);
        this.checkedAtStartup =
            Objects.requireNonNull(checkedAtStartup);
    }

    public String endpoint() {
        return properties.getHost() + ":" + properties.getPort();
    }
}
~~~

The gateway constructor depends on `StartupDependencyProbe` so **the probe initializes before the gateway**. This sample gateway exposes only an endpoint string rather than a full HTTP client, keeping the focus on the startup contract.

### 5.10. `RemoteServiceAutoConfiguration.java`

~~~java
package com.example.remoteconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "app.remote",
    name = "enabled",
    havingValue = "true")
@EnableConfigurationProperties(RemoteEndpointProperties.class)
public class RemoteServiceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DependencyDialer.class)
    DependencyDialer socketDependencyDialer() {
        return new SocketDependencyDialer();
    }

    @Bean
    StartupDependencyProbe startupDependencyProbe(
            RemoteEndpointProperties properties,
            DependencyDialer dialer) {
        return new StartupDependencyProbe(properties, dialer);
    }

    @Bean
    RemoteCatalogGateway remoteCatalogGateway(
            RemoteEndpointProperties properties,
            StartupDependencyProbe probe) {
        return new RemoteCatalogGateway(properties, probe);
    }
}
~~~

**`@ConditionalOnProperty`** sits at the class level so when `enabled` is missing or false, none of the properties bean, probe, or gateway register. When `enabled=true`, missing host/port must fail startup. **`@ConditionalOnMissingBean`** lets users or tests supply their own dialer while default `SocketDependencyDialer` backs off.

### 5.11. `AutoConfiguration.imports`

Create the exact file **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**:

~~~text
com.example.remoteconfig.RemoteServiceAutoConfiguration
~~~

Spring Boot 3.x discovers auto-configuration candidates from this imports file. Using `ApplicationContextRunner` with `AutoConfigurations.of(...)` **does not prove** the imports path is right; a dedicated `@SpringBootTest` discovery test verifies that.

## 6. `ApplicationContextRunner` tests: missing config and unavailable dependencies

**src/test/java/com/example/remoteconfig/RemoteServiceAutoConfigurationTest.java**

~~~java
package com.example.remoteconfig;

import java.net.ConnectException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class RemoteServiceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                RemoteServiceAutoConfiguration.class));

    @Test
    void missingFeatureFlagDisablesRemoteGateway() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(0, context
                .getBeanNamesForType(RemoteCatalogGateway.class).length);
            assertEquals(0, context
                .getBeanNamesForType(StartupDependencyProbe.class).length);
            assertEquals(0, context
                .getBeanNamesForType(RemoteEndpointProperties.class).length);
        });
    }

    @Test
    void disabledFeatureNeverProbesResource() {
        runner.withUserConfiguration(RefusingDialerConfig.class)
            .withPropertyValues("app.remote.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(0, context
                    .getBeanNamesForType(
                        StartupDependencyProbe.class).length);
            });
    }

    @Test
    void missingHostFailsStartup() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.port=8443")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void missingPortFailsStartup() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void malformedPortFailsBinding() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=not-a-number")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void invalidPortRangeFailsValidation() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=70000")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void zeroTimeoutFailsBeforeNetworkCall() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=8443",
                "app.remote.connect-timeout=0ms")
            .run(context -> {
                Throwable failure = context.getStartupFailure();
                assertNotNull(failure);
                assertInstanceOf(
                    IllegalArgumentException.class,
                    rootCause(failure));
            });
    }

    @Test
    void validPropertiesReachRealStartupProbe() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=catalog.internal",
                "app.remote.port=8443",
                "app.remote.connect-timeout=750ms")
            .run(context -> {
                assertNull(context.getStartupFailure());

                RemoteEndpointProperties props =
                    context.getBean(RemoteEndpointProperties.class);
                assertEquals("catalog.internal", props.getHost());
                assertEquals(Integer.valueOf(8443), props.getPort());
                assertEquals(Duration.ofMillis(750),
                    props.getConnectTimeout());

                RecordingDialer fake =
                    context.getBean(RecordingDialer.class);
                assertEquals(1, fake.calls);
                assertEquals("catalog.internal", fake.host);
                assertEquals(8443, fake.port);
                assertEquals(Duration.ofMillis(750), fake.timeout);
                assertEquals("catalog.internal:8443",
                    context.getBean(
                        RemoteCatalogGateway.class).endpoint());
            });
    }

    @Test
    void missingTimeoutUses250msDefault() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=8443")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(Duration.ofMillis(250),
                    context.getBean(RecordingDialer.class).timeout);
            });
    }

    @Test
    void refusedResourceFailsStartupAndPreservesCause() {
        runner.withUserConfiguration(RefusingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=catalog.internal",
                "app.remote.port=8443")
            .run(context -> {
                Throwable failure = context.getStartupFailure();
                assertNotNull(failure);
                assertInstanceOf(
                    ConnectException.class,
                    rootCause(failure));
            });
    }

    @Test
    void realTcpDialerConnectsToTestOwnedServer()
            throws Exception {

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            runner.withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=" + server.getLocalPort(),
                "app.remote.connect-timeout=1s")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertInstanceOf(SocketDependencyDialer.class,
                    context.getBean(DependencyDialer.class));
                assertEquals(
                    "127.0.0.1:" + server.getLocalPort(),
                    context.getBean(
                        RemoteCatalogGateway.class).endpoint());
            });
        }
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    static final class RecordingDialer
            implements DependencyDialer {
        int calls;
        String host;
        int port;
        Duration timeout;

        @Override
        public void verifyConnectivity(
                String host, int port, Duration timeout) {
            calls++;
            this.host = host;
            this.port = port;
            this.timeout = timeout;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class RecordingDialerConfig {
        @Bean
        RecordingDialer recordingDialer() {
            return new RecordingDialer();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class RefusingDialerConfig {
        @Bean
        DependencyDialer refusingDialer() {
            return (host, port, timeout) -> {
                throw new ConnectException(
                    "simulated connection refused");
            };
        }
    }
}
~~~

**What each test verifies:**
- Missing flag / false: no probe, context starts.
- Missing host/port and invalid port: context fails before the gateway becomes ready.
- `timeout=0`: real `StartupDependencyProbe` rejects it.
- `RecordingDialer`: config binds to the properties bean and forwards exact host/port/timeout into the startup check; fake called once, zero network calls.
- `RefusingDialer`: simulates `ConnectException`, root cause preserved and context fails.
- Real TCP: `ServerSocket` listening on an OS-assigned port, real `SocketDependencyDialer` connects.

**Do not assume every failed test failed because of the exact property under test.** Basic negative config tests assert startup failure; in production CI suites, add cause-chain or constraint-field assertions verified against your Spring Boot patch version, alongside positive control cases to avoid false positives from unrelated beans.

### Why not use port 9999 expecting connection refused?

Another process might bind port 9999 on CI; DNS and firewalls also vary by machine. Throwing `ConnectException` from a fake is deterministic for testing fail-fast policy. When testing the TCP adapter itself, open `ServerSocket(0)` **before** starting the context. Never shut down another test's shared database/container just to provoke a failure.

## 7. `@SpringBootTest` verifying discovery from the imports file

**src/test/java/com/example/startupchecks/DiscoveryWithFakeDialerTest.java**

~~~java
package com.example.startupchecks;

import java.time.Duration;

import com.example.remoteconfig.DependencyDialer;
import com.example.remoteconfig.RemoteCatalogGateway;
import com.example.remoteconfig.RemoteEndpointProperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    classes = StartupChecksApplication.class,
    properties = {
        "app.remote.enabled=true",
        "app.remote.host=catalog.test",
        "app.remote.port=9443",
        "app.remote.connect-timeout=500ms"
    })
@Import(DiscoveryWithFakeDialerTest.NoNetworkConfig.class)
class DiscoveryWithFakeDialerTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void autoConfigIsDiscoveredFromImports() {
        RemoteCatalogGateway gateway =
            context.getBean(RemoteCatalogGateway.class);
        assertNotNull(gateway);
        assertEquals("catalog.test:9443", gateway.endpoint());
        assertEquals(1, context
            .getBeanNamesForType(
                RemoteCatalogGateway.class).length);

        RemoteEndpointProperties properties =
            context.getBean(RemoteEndpointProperties.class);
        assertEquals(Duration.ofMillis(500),
            properties.getConnectTimeout());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class NoNetworkConfig {
        @Bean
        DependencyDialer fakeDialer() {
            return (host, port, timeout) -> {
                // Send no network traffic in the discovery test.
            };
        }
    }
}
~~~

**`@Import` here imports only the fake test configuration**, not `RemoteServiceAutoConfiguration`. If `AutoConfiguration.imports` is deleted and the app does not scan the sibling package, the gateway is absent and the test fails. Because the dialer is fake, `catalog.test` needs no DNS resolution; the test **does not** prove an external catalog is reachable.

## 8. Why use `ApplicationContextRunner` for expected startup failures?

A `@SpringBootTest` class with intentionally broken config fails with **Failed to load ApplicationContext** before JUnit even enters the `@Test` method. Therefore `assertThrows` inside the test method cannot verify expected startup failures. With `ApplicationContextRunner`:

~~~java
runner.withPropertyValues(
        "app.remote.enabled=true",
        "app.remote.port=8443")
    .run(context -> {
        assertNotNull(context.getStartupFailure());
    });
~~~

The runner passes the failed context into the callback for inspection. **Do not call `getBean` on a failed context** and obscure the root cause. Inspect `getStartupFailure()`, root causes, and the condition evaluation report. For failures triggered only in **`CommandLineRunner`/`ApplicationRunner`** or web-server binding, test the real `SpringApplication` lifecycle because `ApplicationContextRunner` does not run those.

**Context cache / failure threshold:** Spring TestContext caches contexts and caps repeated failures on identical broken configs, making multiple `@SpringBootTest` expected-failure tests awkward. `ApplicationContextRunner` fits an invalid-config matrix cleanly.

## 9. Fail-fast vs. degraded readiness

**Fail fast** when a critical dependency must be available before serving requests and has no safe fallback. Use **degraded mode** when a feature is optional, has a safe fallback, or core APIs can continue operating. Never weaken fail-fast into swallowing `IOException` just to pass a test.

| Policy | How to implement | How to test |
| --- | --- | --- |
| Required config fails | `@ConfigurationProperties` + `@Validated` | Runner failure + cause |
| Required remote unavailable | `InitializingBean`/probe | Fake `DependencyDialer` refused |
| Optional disabled | `@ConditionalOnProperty` | Runner starts without probe |
| Degraded service | `HealthIndicator`/`ReadinessState` + fallback | Actuator/API integration |
| Resource arrives late | Bounded retry/backoff | Fake clock/scheduler + latches |
| Resource drops after READY | Circuit breaker/reconnect | Runtime outage integration |

**Never infinitely retry missing credentials or bad configuration.** For transient I/O errors, retries require max attempts, per-attempt timeouts, a total startup budget, and jitter. A timeout on `Socket.connect` does not automatically cover DNS resolution, TLS handshakes, or the total retry budget.

### Liveness differs from readiness

**Liveness** asks whether the process must be restarted. Tying every external DB/API health check to liveness lets one shared outage restart all pods simultaneously, triggering cascading failure. **Readiness** asks whether the instance should receive traffic; it can include critical dependency health, though Spring Boot **does not automatically add all external indicators to the readiness group**.

Actuator configuration example outside the runnable project:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: "readinessState,remoteCatalog"
~~~

This requires `starter-actuator`, web/management endpoints, and a **real `HealthIndicator` named `remoteCatalog`**. Including a nonexistent indicator in a group can fail Boot startup validation. Do not copy this snippet until that indicator exists.

If a shared external dependency outage marks every pod unready, the service stops serving traffic even if it has a fallback. Base policies on dependency criticality rather than framework defaults.

## 10. DB, Kafka, Redis, and HTTP clients at startup

**Database:** A `DataSource` bean may not have opened a connection yet. Flyway/Liquibase migrations, Hibernate metadata/schema validation, or a custom probe can force real DB usage at startup. Hikari `connection-timeout`/`initialization-fail-timeout` apply during pool init/acquisition per configuration. Test the **real connection/migration path**, not just bean presence.

**Kafka:** A `KafkaTemplate` bean does not mean the broker is healthy; producer send futures fail asynchronously, and `@KafkaListener` containers follow their own reconnect/startup policies. To fail fast, add an explicit broker/admin health probe or readiness contract and test it.

**Redis:** `RedisConnectionFactory`/`RedisTemplate` is not a passing `PING`. When caching falls back to the DB, degraded startup can be desirable; when Redis holds critical security sessions or distributed locks, a stricter policy applies.

**External HTTP APIs:** TCP connect success is insufficient if TLS/certificates, HTTP statuses, token auth, or API schemas fail. Use MockWebServer/WireMock/Testcontainers HTTP services with the real client to verify 200/503/timeouts/TLS when required.

**Database migrations:** SQL initialization scripts and Flyway/Liquibase provide fail-fast behavior when active; never assume they run if dependencies or modes/configs are disabled. Test against the real SQL dialect when production uses PostgreSQL rather than H2 alone.

## 11. Testcontainers and dynamic endpoints

Spring Boot 3.4 supports **`@ServiceConnection`** with Testcontainers for JDBC, Redis, Kafka, and other services with matching `ConnectionDetails` factories. Sketch of a DB integration test, **not part of the runnable project**:

~~~java
@Testcontainers
@SpringBootTest
class PostgresStartupExample {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16");

    @Autowired
    DataSource dataSource;

    @Test
    void connectionWorks() throws Exception {
        try (Connection c = dataSource.getConnection()) {
            assertTrue(c.isValid(2));
        }
    }
}
~~~

This requires **`spring-boot-starter-jdbc`**, PostgreSQL driver, **`spring-boot-testcontainers`**, Testcontainers `junit-jupiter`/`postgresql`, a Docker daemon, and Java/Spring imports. **`@ServiceConnection`** supplies `ConnectionDetails` taking precedence over connection properties. Passing with Testcontainers **does not** prove production JDBC URLs/passwords are valid if the test overrode them.

Alternatively, **`@DynamicPropertySource`** registers URL/username/password via a static method at runtime:

~~~java
@DynamicPropertySource
static void dbProps(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", db::getJdbcUrl);
    registry.add("spring.datasource.username", db::getUsername);
    registry.add("spring.datasource.password", db::getPassword);
}
~~~

This snippet assumes a static container `db` exists; dynamic properties have high precedence. Never hardcode mapped ports. To test real unavailability, use container/network isolation; **never stop a shared static container while other tests are still running**.

## 12. Never use `Thread.sleep` to simulate startup races

When a resource should appear after a few attempts, write a **bounded retry policy** separating `Clock`/`Sleeper`/`RetryScheduler` to fake time and throw I/O errors per attempt. Integration tests can use `CountDownLatch`/Awaitility with finite timeouts instead of fixed multi-second sleeps hoping a container is ready.

~~~text
attempts < maximum AND elapsed < startup budget
    try required protocol check with timeout
    success -> finish startup
    transient IO error -> backoff + jitter, retry
    config/auth permanent error -> fail immediately
    exhausted budget -> fail startup with last cause
~~~

This is **pseudocode**, outside the runnable code; this project probes once and fails fast. When a dependency drops after READY, startup-only probes do not detect it. Add separate health/readiness, client timeout, fallback, and runtime recovery tests.

## 13. Security, logging, and error root causes

A helpful startup error should identify:
- which dependency (remote catalog, PostgreSQL, Redis...);
- which phase (properties validation, bean init, migration, network probe);
- which config key is missing, if safe to reveal;
- exception type and root cause;
- whether it is retryable or requires operator deployment fixes.

**Never log passwords, Basic/Bearer tokens, full secret URLs, raw `Environment`, or security cookies.** Output only property names and redacted causes. Never catch `Exception` and log only a warning when the app cannot serve safely. Conversely, never kill the app over an optional disabled feature.

### Test the cause, not merely the presence of an error

`getStartupFailure()!=null` can PASS because an unrelated bean blew up. Keep a **positive control** (valid properties + `RecordingDialer`) and inspect the cause chain when needed: `ConnectException` or `BindValidationException`/`BindException` matching your version. Never assert verbatim full stack traces, generated bean names, or line numbers that create brittle tests.

## 14. Real-world mistake table

| Mistake | Why it's wrong | Fix |
| --- | --- | --- |
| `contextLoads` = DB ready | Connections may be lazy | Real query/migration/health test |
| Mocking `StartupDependencyProbe` itself | Bypasses fail-fast logic | Fake `DependencyDialer` |
| Using `localhost:9999` assuming refused | Another process might listen there | Deterministic refused fake |
| `@SpringBootTest` expected failure inside `@Test` body | Context fails before method runs | `ApplicationContextRunner` |
| Disabling all dependencies in tests and claiming prod-ready | Masks production policy | Test disabled + enabled negative/positive |
| Omitting `@Validated` | Invalid properties slip through | Typed config + validation |
| Defaulting required endpoint to `localhost` | Hides missing config | `@NotBlank` host, `@NotNull` port |
| Socket timeout=0 | Can wait forever | Validate >= 1 ms |
| Retrying missing secrets forever | Deployment hangs | Fail fast on permanent errors |
| `Thread.sleep` waiting for DB ready | Flaky and slow | Testcontainers readiness/latches |
| Putting all external health in liveness | Restart storms | Selective readiness and fallbacks |
| `@ServiceConnection` pass proves prod URL right | Test URLs were overridden | Separate prod config checks |
| Health 200 means every request works | Indicators may be incomplete | Real business/health assertions |
| Logging full connection strings | Leaks credentials | Redacted diagnostics |
| Slapping `@DirtiesContext` on every flake | Slow and hides shared state | Lifecycle isolation |
| Asserting any arbitrary exception | Unrelated errors pass too | Root cause + control case |
| Testing with H2 and declaring Postgres ready | Dialects differ | Postgres Testcontainers |

## 15. Running the suite and expected results

~~~bash
./gradlew clean test
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest
./gradlew test --tests com.example.startupchecks.DiscoveryWithFakeDialerTest
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest.refusedResourceFailsStartupAndPreservesCause
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest.realTcpDialerConnectsToTestOwnedServer
~~~

On Windows use **`gradlew.bat`**. If Gradle Wrapper scripts have not been generated yet, use an installed Gradle or generate the wrapper first; having only `build.gradle` does not create `./gradlew`. The results below are expected assertions, **not observed runtime output**.

| Test | Expectation |
| --- | --- |
| `missingFeatureFlagDisablesRemoteGateway` | Context succeeds, 0 remote beans |
| `disabledFeatureNeverProbesResource` | Context succeeds, 0 probes |
| `missingHostFailsStartup` | Startup failure |
| `missingPortFailsStartup` | Startup failure |
| `malformedPortFailsBinding` | Startup failure |
| `invalidPortRangeFailsValidation` | Startup failure |
| `zeroTimeoutFailsBeforeNetworkCall` | Root cause `IllegalArgumentException` |
| `validPropertiesReachRealStartupProbe` | host/port/750ms accurate, `fake.calls=1` |
| `missingTimeoutUses250msDefault` | Default timeout 250ms |
| `refusedResourceFailsStartupAndPreservesCause` | Root cause `ConnectException` |
| `realTcpDialerConnectsToTestOwnedServer` | TCP succeeds on loopback port |
| `autoConfigIsDiscoveredFromImports` | Full Boot discovers remote gateway via imports |

**Stated limitations:** a TCP handshake is not protocol readiness; fake unavailability proves policy without generating real packets; `@SpringBootTest` discovery with a fake does not prove external hosts are reachable. Add deeper integration tests when operational requirements demand them.

## 16. Knowledge self-check

**1.** What happens if `enabled=false` and host/port are missing? **Starts fine**, because the optional feature is disabled.

**2.** What if `enabled=true` and host is missing? **Startup fails** due to `@NotBlank`.

**3.** Why use `Integer` for `port` instead of `int`? **`@NotNull` detects missing config explicitly**.

**4.** Should `port=abc` fall back to 8080? **No**, the Binder must reject invalid types.

**5.** To test `Connection refused` without opening the network, which class do you fake? **`DependencyDialer`**.

**6.** Why keep `StartupDependencyProbe` real? Because the **fail-fast policy** lives there.

**7.** Does `ApplicationContextRunner` with `AutoConfigurations.of` prove `AutoConfiguration.imports` is right? **No**, use a discovery test.

**8.** Why is `@SpringBootTest` failed startup hard to assert inside a `@Test` method? Because context loading fails **before JUnit runs the method**.

**9.** Do `DataSource`/`KafkaTemplate` beans prove servers are available? **No**.

**10.** Does a succeeding `Socket.connect` prove HTTP 200? **No**.

**11.** Why use `ServerSocket(0)`? The OS picks a free port at test runtime.

**12.** What can `timeout=0` cause? It can wait infinitely, so validate positive timeouts.

**13.** What does disabling class-level `@ConditionalOnProperty` affect? Neither the auto-config beans nor the feature's properties register.

**14.** What does `@ConditionalOnMissingBean` enable? User/test beans cause the default dialer to back off.

**15.** Does a startup-only test catch a dependency dropping after READY? **No**, runtime health checks are required.

**16.** Should liveness depend on every external API? **No**, to avoid restart storms.

**17.** Does default readiness include every external health indicator? **No**, groups must be configured deliberately.

**18.** Does `@ServiceConnection` with Testcontainers override datasource config? **Yes** for supported `ConnectionDetails`.

**19.** What does `@DynamicPropertySource` require? A static method taking `DynamicPropertyRegistry`.

**20.** Core rule? **Bad config must fail clearly; critical dependencies need fail-fast/readiness policies; disabled optional features must never block startup.**

### QA checklist

- Is each dependency's startup contract clearly fail-fast, degraded, or optional-disabled?
- Are missing/false `enabled` flags and `enabled=true` both tested?
- Are missing host/port, invalid types, out-of-range ports, and `timeout=0` tested?
- Is there a positive control with valid config + reachable fake?
- Is unavailability tested with root cause `ConnectException`?
- Have you avoided guessed ports and `Thread.sleep` in unit/context tests?
- Is the policy probe the real implementation with only the network boundary faked?
- Is the real `SocketDependencyDialer` tested against a test-owned loopback port?
- Are `ApplicationContextRunner` tests separated from full `SpringApplication` startup lifecycles?
- Is `AutoConfiguration.imports` discovery tested independently?
- Have you avoided mistaking `contextLoads` for DB/Kafka/Redis readiness?
- Are liveness vs. readiness and distributed-outage impacts accounted for?
- When real DBs are required, are Testcontainers/service connections/SQL checks in place?
- Are retries/deadlines bounded and retryable vs. permanent errors classified?
- Are property precedence, profiles, and secret configs tested where needed?
- Are passwords, API keys, tokens, and raw secret URLs kept out of logs?
- Are resources cleaned up and isolated so parallel CI never flakes?
- Have you avoided claiming Gradle/Docker passed without real execution evidence?

**Conclusion:** Spring Boot startup testing requires **explicit contracts**: required config binds and validates, critical external dependencies are probed per policy, disabled optional features cause no side effects, and readiness accurately reflects ability to serve. **`ApplicationContextRunner`** tests config failures and bean init cleanly; a **fake `DependencyDialer`** gives deterministic errors; **loopback/Testcontainers** supply real infrastructure evidence when needed. Never equate a booting context with full system readiness.

## Official references

- Spring Boot 3.4 — Testing Auto-configuration / `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html
- Spring Boot 3.4 — External Configuration and Validation: https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html
- Spring Boot 3.4 — Testcontainers / `@ServiceConnection`: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Boot 3.4 — Actuator Liveness/Readiness: https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html
- Spring Boot 3.4 — Database Initialization and Migration: https://docs.spring.io/spring-boot/3.4/how-to/data-initialization.html
- Spring Framework 6.2 — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Java 17 — `Socket.connect`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
