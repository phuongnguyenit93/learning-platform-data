# Required Configuration Errors, Validation, and External Services During Spring Boot Startup

## 1. Distinguishing configuration errors from external connectivity failures

A Spring Boot JAR can build cleanly and still fail to start. Common causes include:

- **Failure to load a configuration source:** a required file specified in `spring.config.import` is missing, YAML is invalid, or Config Server is unreachable.
- **Missing required values:** database URL, health URL, bucket name, or security settings are absent from the Environment.
- **Invalid values:** negative timeout, blank string, unparseable numeric type, wrong enum, or contract-violating URL.
- **External service unavailability:** DNS, TCP, TLS, authentication, or HTTP check fails when the application actively connects.
- **Inappropriate startup policy:** the application reports ready while a core dependency is down, or the entire system fails startup because an optional service had a transient glitch.

The first three groups are usually **static configuration errors**. The fourth is the **dynamic state of a remote dependency**: a backend might be online at startup and offline five minutes later. Inspect and remediate according to the right failure layer.

~~~text
java -jar app.jar
      |
      v
[1] Prepare Environment / Config Data
      |  required import file missing
      |  invalid YAML syntax
      +----> Early startup failure
      |
      v
[2] Build ApplicationContext, BeanDefinitions
      |
      v
[3] Bind & validate @ConfigurationProperties
      |  required property null/blank
      |  wrong data type
      |  @Validated constraints violated
      +----> Bean/binding/validation failure
      |
      v
[4] Context refresh completes
      |
      v
[5] ApplicationRunner / CommandLineRunner
      |  policy-dependent: probe remote with timeout
      |  network/TLS/HTTP check fails
      +----> Runner failure -> run() fails
      |
      v
[6] ApplicationReadyEvent
      |
      v
[7] Runtime traffic / jobs
      |  remote may fail at any time
      +----> Timeout, retry, circuit breaker, fallback
~~~

**Goal of this article:** learn how to define required configuration, bind and validate early, decide whether to probe remotes at startup, separate startup failures from runtime failures, and build reproducible tests.

This article follows **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+**. Command-line examples use **Maven** and do not require any live Internet service.

## 2. Failure classification table and what to inspect

| Group | Example | Typical phase | Resolution approach |
| --- | --- | --- | --- |
| Config Data | Missing required import file | Environment preparation | Check location, mount, optional policy |
| Missing property | Missing demo.remote.health-url | Binding/bean creation | Place config in the right source and profile |
| Type conversion | timeout-ms=abc for long | Binder | Fix type and representation |
| Constraint validation | timeout-ms=50 violates @Min(100) | Bean validation | Fix value or constraint |
| Bean dependency | Constructor missing bean | Dependency injection | Check component scan, @Bean, conditions |
| Remote unreachable | Connection refused, DNS error | Startup probe or runtime call | Timeout, bounded retry, critical/optional policy |
| TLS/auth failure | Untrusted certificate, HTTP 401/403 | When calling remote | Certificates/credentials/permissions |
| Runtime outage | Remote was online then failed after ready | Runtime | Bounded retry, circuit breaker, monitoring |

**Do not draw conclusions from the APPLICATION FAILED TO START line alone.** Check the underlying exception, bean/property name, failure timing, and external service state.

A failure while parsing Config Data is **different** from a failure after `ApplicationRunner` begins. To fix issues quickly, knowing the exact milestone directs you to the right cause.

### 2.1. Three diagnostic questions

1. **Does the configuration source exist and get loaded?** Check `spring.config.import`, application properties, active profiles, and file mounts.
2. **Did values bind and validate into the right types?** Check `@ConfigurationProperties`, Jakarta constraints, and default values.
3. **Does the application genuinely require the remote online before accepting traffic?** If yes, check fail-fast with a deadline. If not, accept a degraded mode with observability and safe runtime handling.

Do not apply one solution to all three: adding empty placeholder defaults to hide missing keys or retrying network calls forever in a constructor usually makes incidents harder to diagnose.

## 3. Configuration sources, active profiles, and precedence

Spring Boot supports many configuration sources:

- `application.properties` and `application.yaml` inside the JAR or from external locations.
- Config Data imported via `spring.config.import`.
- OS environment variables and Kubernetes/Docker config mounts.
- Java system properties via `-D`.
- Program arguments like `--name=value`.
- Configuration trees for reading file-based secrets.
- Integrations such as Spring Cloud Config once the corresponding client and config are added.

A key can appear in multiple sources. **The Environment applies precedence rules**, so seeing the right key in a file does not prove it is the effective value.

For example, a file has:

~~~properties
demo.remote.timeout-ms=2000
~~~

but the launch command runs:

~~~bash
java -jar app.jar --demo.remote.timeout-ms=5000
~~~

With Boot defaults, the command-line property source overrides the Config Data value, so the effective timeout is **5000**. If the code calls `SpringApplication.setAddCommandLineProperties(false)`, CLI precedence into the Environment changes.

### 3.1. Missing key vs empty value

~~~properties
demo.remote.health-url=
~~~

Here the key exists, but its value is empty. If the property binds to a `String`:

- **@NotNull** rejects null, yet still accepts an empty string or whitespace.
- **@NotBlank** rejects null, empty strings, and whitespace-only strings.
- **@NotEmpty** rejects empty strings, yet does not forbid whitespace-only strings.

Therefore, for a required URL, **@NotBlank** is usually more accurate than **@NotNull** alone. Still, `@NotBlank` **does not prove the string is a valid URI**; add syntax/semantics checks as needed.

### 3.2. Required Config Data imports

~~~properties
spring.config.import=file:./runtime/remote.properties
~~~

If a required file is absent, Spring Boot typically reports **ConfigDataLocationNotFoundException** while loading Config Data. This failure can occur before any application bean is created.

If that location is genuinely optional:

~~~properties
spring.config.import=optional:file:./runtime/remote.properties
~~~

The **optional:** prefix drops the requirement that the location must exist. It does **not** exempt required properties on `@ConfigurationProperties`. If the app still needs a key from the missing file, validation will still catch the error during bean creation.

**Do not add `optional:` just to mask a missing secret/config mount** that is a mandatory deployment prerequisite.

### 3.3. Profiles and environment-specific config

If configuration lives in:

~~~properties
# application-dev.properties
demo.remote.health-url=http://127.0.0.1:8765/health
~~~

then a deployment running only the **prod** profile will not necessarily receive that key. Always verify **spring.profiles.active** and environment-specific sources rather than assuming every `application-*.properties` file is loaded.

A dev environment may start thanks to a local profile while production fails due to a missing ConfigMap/Secret. That is a **deployment configuration** failure, not a reason to weaken mandatory constraints.

### 3.4. Spring Cloud Config is a separate integration

Spring Cloud Config can use forms such as:

~~~properties
spring.config.import=configserver:
~~~

but **core Spring Boot does not provide Config Server integration by itself** unless the project includes a compatible Spring Cloud Config Client. Spring Cloud has its own fail-fast and retry policies; distinguish **Config Server unreachable during configuration preparation** from **remote business API errors** at runtime.

## 4. @Value and @ConfigurationProperties

### 4.1. @Value suits small, simple values

A bean can inject a property via **@Value**. If a required placeholder cannot be resolved, the bean may fail to instantiate.

However:

- Keys easily scatter across many constructors.
- Cross-field group validation is hard to centralize.
- An empty default hides missing-key errors.
- If the bean is lazy, placeholder failures may be deferred until first bean creation.

For a cohesive configuration group with an explicit contract, **@ConfigurationProperties** is usually easier to test and maintain.

### 4.2. @ConfigurationProperties record for Java 17+

~~~java
@ConfigurationProperties(prefix = "demo.remote")
@Validated
public record RemoteSettings(
        @NotBlank String healthUrl,
        @Min(100) @Max(30_000) long timeoutMs,
        boolean verifyOnStartup) {
}
~~~

This is a snippet requiring imports and configuration bean registration. Meaning:

- **healthUrl** is a required non-blank string.
- **timeoutMs** is a `long` between 100 and 30,000.
- **verifyOnStartup** determines whether a network probe is sent at startup.
- Boot 3.3 constructor-binds records when registered via **@EnableConfigurationProperties** or **@ConfigurationPropertiesScan**.

Do not mistake **@ConfigurationProperties** for a command that calls the remote automatically: the binder only reads and converts Environment values into a Java object.

### 4.3. Jakarta Validation is required

Spring Boot 3 uses the **jakarta.validation** namespace, not the legacy **javax.validation** namespace found in many Boot 2 examples.

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

**@Validated** causes Boot to validate the configuration properties bean. A Jakarta Bean Validation provider is required on the classpath; the validation starter supplies an appropriate implementation.

### 4.4. Matching constraints to data types

| Constraint | Purpose | Common pitfall |
| --- | --- | --- |
| **@NotNull** | Rejects null | Empty strings still pass |
| **@NotBlank** | String contains non-whitespace characters | Does not validate URL syntax by itself |
| **@NotEmpty** | Non-empty string/collection/map/array | Space-only strings can pass |
| **@Min/@Max** | Number within bounds | Does not replace type conversion |
| **@Positive** | Number must be > 0 | Zero is rejected |
| **@Pattern** | Regex for String | Does not replace a full URI parser |
| **@Valid** | Cascades validation into nested objects | Must be applied properly on nested properties |
| **Custom Validator** | Custom semantic rules | Should not perform network I/O in pure validators |

Nested object example:

~~~java
@ConfigurationProperties("demo")
@Validated
record DemoProperties(@Valid Security security) {
    record Security(@NotBlank String audience) {
    }
}
~~~

This is a snippet requiring **@Valid**, **@NotBlank**, **@Validated** imports and bean registration. For nested groups, you may need default nested object instantiation or proper `@Valid` placement so validation triggers even when no properties are supplied in the nested group, depending on the class contract.

**Do not assume `@NotBlank` inside a nested class automatically cascades**; write a test with missing nested config.

### 4.5. Type conversion vs validation

~~~properties
demo.remote.timeout-ms=abc
~~~

is a binder error failing to convert `String` to `long`.

~~~properties
demo.remote.timeout-ms=50
~~~

binds as `long` successfully, then violates **@Min(100)**.

If a boxed **Long** property can be null, add **@NotNull** when presence is required. A constraint like `@Min` does not necessarily catch null values.

### 4.6. Watch out for lazy initialization

Beans marked `@Lazy`, or when enabling:

~~~properties
spring.main.lazy-initialization=true
~~~

may be created late. Validation tied to binding/initializing that bean may also be delayed if nothing requests the bean before ready.

For core configuration, use an eager bean, **@Lazy(false)**, or a small startup validator so failures surface before readiness. Do not make the first user hitting an endpoint discover a missing required config error.

**Lazy does not defer every error:** Config Data parsing, BeanDefinition registration, and many infrastructure components still run at startup.

## 5. External dependencies: valid config does not mean reachable

Properties like:

~~~properties
demo.remote.health-url=https://service.example.internal/health
demo.remote.timeout-ms=2000
~~~

can bind and validate cleanly even while the service:

- Fails DNS resolution.
- Has no open TCP port.
- Is blocked by a firewall or service mesh.
- Has an invalid or expired TLS certificate.
- Rejects credentials with 401/403.
- Returns HTTP 503 because it is not ready.
- Returns HTTP 200 on basic health yet fails a real business operation.
- Works at startup and goes down a few minutes later.

**Static configuration** and **dynamic network state** need separate checks. Never put an HTTP GET inside a Jakarta Validator or a record getter just to "validate automatically".

### 5.1. Levels of external checks

| Probe type | What it tells you | What it does not tell you |
| --- | --- | --- |
| DNS lookup | Hostname resolves | Remote API is ready |
| TCP connect | Port accepts connections | Auth/business API works |
| TLS handshake | TLS connection established/trusted | HTTP response succeeds |
| HTTP GET health | Endpoint returns defined status | Full business workflow is healthy |
| Authenticated read | Credentials are permitted to read | Permissions cover all operations |
| Business transaction | A specific operation executes | Safety if the probe causes side effects |

**Health probes should not cause side effects** such as charging money, creating orders, or executing real write transactions. Pick GET/HEAD or a read-only operation whose semantics the remote provider endorses.

### 5.2. When is fail-fast appropriate?

Fail-fast when a remote is missing makes sense if **the application cannot serve any core functionality without it** and accepting traffic would only cause more failures. A bounded-timeout startup check helps rollouts catch unviable instances early.

Fail-fast is not necessarily right if the remote is an **optional feature** or the outage is transient while the application can still serve other endpoints. In that case, degraded startup plus runtime resilience may be better.

**Consequence to weigh:** dozens of replicas starting simultaneously and probing an overloaded backend can worsen an outage. There is no single fail-fast/degraded choice that fits every product.

## 6. Which lifecycle phase should run the check?

### 6.1. Constructor and @PostConstruct

Bean initialization code is suitable for validating **static values**, whereas network calls in constructors or `@PostConstruct` easily cause problems:

- Slow bean creation and confusion between remote errors and DI errors.
- Network timeouts stall the entire context refresh.
- Lazy beans defer connection attempts until the first request.
- Callbacks are awkward to retry cleanly or measure independently.
- An external outage can make bean creation fail wholesale.

If an early network check is needed, isolate it in a dedicated component with clear responsibilities.

### 6.2. ApplicationRunner/CommandLineRunner

Spring Boot runs runners after context refresh, yet before **ApplicationReadyEvent**. A runner can call the health endpoint, require HTTP 2xx, and throw an exception if a critical dependency is unready.

Advantages:

- Configuration is already bound and injected.
- A standalone `RemoteHealthProbe` can be cleanly separated.
- Explicit timeout/retry deadlines are straightforward.
- Uncaught exceptions cause **SpringApplication.run(...)** to fail.
- `ApplicationReadyEvent` is not published on the normal startup path when a runner fails.

**Limitation:** for web apps, the embedded server may already have opened its port during refresh before runners execute. You still need readiness probes/load balancing to prevent premature traffic; a runner is not a firewall.

### 6.3. Readiness and liveness

**Liveness** should reflect whether the process itself is alive and unstuck. Do not tie liveness blindly to every external backend; a shared outage could trigger pointless pod restarts across the cluster.

**Readiness** reflects whether the instance can accept current traffic. It may depend on a critical backend if the entire workload cannot function without it. For optional features, do not wire them into service-wide readiness without evaluating the blast radius.

Health checks should have:

- Timeouts and cost bounds.
- Appropriate frequency, optionally caching status.
- Clear separation between critical and optional dependencies.
- Clear monitoring signals when the service is degraded.
- Policies preventing cluster-wide unready states if only an auxiliary route fails.

### 6.4. Runtime must still handle errors

A remote can fail **after** startup. Runtime still needs connection/request timeouts, bounded retries, exponential backoff, jitter, circuit breakers/bulkheads, idempotency, and fallbacks where business rules allow.

A single passing startup probe **never guarantees the remote stays up forever**.

## 7. Runnable Java 17+ demo: validate first, probe remote second

This example builds a small Spring Boot CLI to observe four cases:

1. Missing `health-url` -> binding/validation failure.
2. `timeout-ms=50` -> `@Min` validation failure.
3. Valid config and `verify-on-startup=false` -> startup succeeds even while the remote is offline.
4. `verify-on-startup=true` -> HTTP check; 2xx succeeds, network errors or non-2xx cause the runner to fail.

The app uses **WebApplicationType.NONE** to observe startup without opening an embedded HTTP server. For web services, validation/probing principles are similar, alongside readiness/routing.

### 7.1. Project structure

~~~text
startup-config-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/startup/StartupFailureDemo.java
  src/test/java/com/example/startup/RemoteSettingsTest.java
  LocalHealthServer.java
~~~

**LocalHealthServer.java** is a standalone Java program at the root, kept outside the Maven app's `src/main/java` so it does not introduce a second `main` class into the executable JAR.

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>startup-config-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The validation starter is required for Jakarta constraints to actually execute. The test starter provides JUnit 5 and AssertJ.

### 7.3. application.properties

~~~properties
demo.remote.timeout-ms=2000
demo.remote.verify-on-startup=false

# Do not set demo.remote.health-url.
# Each scenario passes it via the command line.
~~~

Omitting `health-url` is intentional so we can test fail-fast when the required parameter is not supplied.

### 7.4. Complete Java application

**src/main/java/com/example/startup/StartupFailureDemo.java**:

~~~java
package com.example.startup;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication(proxyBeanMethods = false)
@EnableConfigurationProperties(StartupFailureDemo.RemoteSettings.class)
public class StartupFailureDemo {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupFailureDemo.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.run(args);
    }

    @Bean
    RemoteHealthProbe remoteHealthProbe() {
        return new RemoteHealthProbe();
    }

    @Bean
    ApplicationRunner startupProbe(
            RemoteSettings settings,
            RemoteHealthProbe probe) {

        return args -> {
            System.out.println("RUNNER | configuration valid");

            if (!settings.verifyOnStartup()) {
                System.out.println("RUNNER | remote probe skipped");
                return;
            }

            int status = probe.getHttpStatus(settings);

            if (status < 200 || status >= 300) {
                throw new IllegalStateException(
                        "Remote health returned HTTP " + status);
            }

            System.out.println(
                    "RUNNER | remote healthy, HTTP " + status);
        };
    }

    @Validated
    @ConfigurationProperties(prefix = "demo.remote")
    public record RemoteSettings(
            @NotBlank String healthUrl,
            @Min(100) @Max(30_000) long timeoutMs,
            boolean verifyOnStartup) {
    }

    static final class RemoteHealthProbe {

        int getHttpStatus(RemoteSettings settings)
                throws Exception {

            URI uri = URI.create(settings.healthUrl());
            String scheme = uri.getScheme();

            boolean supported =
                    "http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme);

            if (!supported || uri.getHost() == null) {
                throw new IllegalArgumentException(
                        "demo.remote.health-url must be an absolute HTTP URL");
            }

            Duration timeout =
                    Duration.ofMillis(settings.timeoutMs());

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(timeout)
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(timeout)
                    .GET()
                    .build();

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding());

                return response.statusCode();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }
        }
    }
}
~~~

**Key points to understand:**

- **@EnableConfigurationProperties** registers `RemoteSettings`. Because the runner injects `RemoteSettings`, the bean is bound and validated before the runner executes in this example.
- **@Validated/@NotBlank/@Min/@Max** validate only configuration values; they send no HTTP requests.
- **RemoteHealthProbe** builds an `HttpClient` and sends a request **only when called by the runner**.
- When `verifyOnStartup=false`, the runner performs no network call yet still enforces that `healthUrl` is valid at least as **non-blank**.
- When the check is enabled, the URI must have an **http/https** scheme and a host. This is a preliminary syntax check inside the probe; if you want to enforce URI syntax regardless of whether probing is enabled, move it into a standalone static validator.
- **connectTimeout** and **request.timeout** bound the network attempt, preventing startup from hanging indefinitely.
- HTTP 2xx is the **demo's definition of healthy**. Real remote APIs may require a different contract; do not blindly treat every HTTP 3xx or arbitrary body as healthy.
- If the HTTP request fails, the exception propagates out of `ApplicationRunner` and fails `SpringApplication.run`.
- When the thread is interrupted, the code restores the interrupt flag before rethrowing.
- Non-web mode keeps runner testing clean. With a web app, the server may already have opened its port before runners execute, so a readiness gate is needed.

### 7.5. LocalHealthServer.java: standalone JDK HTTP stub

To test HTTP 200 and HTTP 503 without relying on the Internet, create **LocalHealthServer.java** at the root:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;

public class LocalHealthServer {

    public static void main(String[] args) throws Exception {
        int status = args.length == 0
                ? 200
                : Integer.parseInt(args[0]);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8765),
                0);

        server.createContext("/health", exchange -> {
            byte[] body =
                    "local-health".getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, body.length);

            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println("STUB | HTTP " + status + " on port 8765");

        new CountDownLatch(1).await();
    }
}
~~~

This server uses the **jdk.httpserver** module included in JDK 17+. Run in Java source-file mode:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java
~~~

Expected stdout from the stub:

~~~text
STUB | HTTP 200 on port 8765
~~~

Or restart with:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java 503
~~~

Expected stdout:

~~~text
STUB | HTTP 503 on port 8765
~~~

The stub needs port 8765 free; if occupied, change the port in the code and matching URL configuration. The stub process waits until you stop it and is for practice only.

### 7.6. Build the demo

~~~bash
java -version
mvn -q -DskipTests package
~~~

Requires Java 17+ and Maven 3.9+. Built JAR:

~~~text
target/startup-config-demo-1.0.0.jar
~~~

### 7.7. Case A: missing required health-url

~~~bash
java -jar target/startup-config-demo-1.0.0.jar
~~~

**Expected:** Spring Boot fails while binding/validating `RemoteSettings` due to `@NotBlank` on `healthUrl`. The program **does not print**:

~~~text
RUNNER | configuration valid
~~~

because the runner never runs. Boot may display a failure analysis or exception chain; do not expect an identical verbatim stack trace across runs.

### 7.8. Case B: valid configuration, probe disabled

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health
~~~

Lines **explicitly printed by the demo code**:

~~~text
RUNNER | configuration valid
RUNNER | remote probe skipped
~~~

**No running stub is needed** because `verify-on-startup` defaults to false. Static configuration is valid, with no conclusion made about remote connectivity.

### 7.9. Case C: invalid timeout

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.timeout-ms=50
~~~

**Expected:** validation fails on `@Min(100)` before the runner. If you replace `50` with **abc**, the failure is a `long` **binding/type conversion** error, distinct from the `@Min` failure.

### 7.10. Case D: remote offline, probe required

Ensure nothing is listening on port 8765, then run:

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.verify-on-startup=true
~~~

The app prints:

~~~text
RUNNER | configuration valid
~~~

Then network connection fails since no service is on that port; **SpringApplication.run** fails inside `ApplicationRunner` and never prints the remote healthy line.

### 7.11. Case E: remote HTTP 200

Terminal A:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java
~~~

Terminal B:

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.verify-on-startup=true
~~~

Lines printed by the demo code:

~~~text
RUNNER | configuration valid
RUNNER | remote healthy, HTTP 200
~~~

The startup probe succeeded, yet the remote can still fail later; do not treat one GET as a lifetime availability guarantee.

### 7.12. Case F: remote HTTP 503

Stop the previous stub and run:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java 503
~~~

Rerun the app with `verify-on-startup=true`. The runner prints the valid configuration line, then **throws IllegalStateException** with message:

~~~text
Remote health returned HTTP 503
~~~

Boot treats startup as failed. Do not assert exact full stack traces or log ordering.

## 8. Unit testing configuration with ApplicationContextRunner

**ApplicationContextRunner** creates a lightweight Spring context to test binding/validation without a web server or remote network.

Create **src/test/java/com/example/startup/RemoteSettingsTest.java**:

~~~java
package com.example.startup;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RemoteSettingsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesOnly.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(
            StartupFailureDemo.RemoteSettings.class)
    static class PropertiesOnly {
    }

    @Test
    void missingRequiredUrlFailsValidation() {
        runner.withPropertyValues(
                "demo.remote.timeout-ms=2000")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void outOfRangeTimeoutFailsValidation() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=50")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void invalidNumberFailsBinding() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=abc")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void validConfigurationBindsWithoutNetwork() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=2000",
                "demo.remote.verify-on-startup=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    var settings = context.getBean(
                            StartupFailureDemo.RemoteSettings.class);

                    assertThat(settings.healthUrl()).isEqualTo(
                            "http://127.0.0.1:8765/health");
                    assertThat(settings.timeoutMs()).isEqualTo(2000);
                    assertThat(settings.verifyOnStartup()).isFalse();
                });
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This test suite proves:

- Missing required keys fail validation.
- Out-of-range timeouts violate constraints.
- Strings unparseable as `long` fail binding.
- Valid properties bind without needing the remote online.

**Testing limitation:** the `ApplicationContextRunner` above registers only `RemoteSettings`, not the runner or `RemoteHealthProbe`. Therefore it **does not test the HTTP startup check**. To test the probe, use a local HTTP stub on a random port or a fake client; to test the full lifecycle, run a real `SpringApplication` in an integration test.

### 8.1. Why shouldn't unit tests depend on the Internet?

A public API can change behavior, rate-limit requests, or go down, turning CI red even when application code is correct. Separate binding/validation tests from networking; test remote calls using controlled stubs and timeouts.

## 9. What happens when ApplicationRunner fails?

In the normal `SpringApplication` sequence:

~~~text
Context refresh success
        |
ApplicationStartedEvent
        |
ApplicationRunner / CommandLineRunner
        |-- FAIL --> startup failure
        |            ApplicationFailedEvent
        |            context cleanup
        |
        +-- PASS --> ApplicationReadyEvent
                       readiness transitions to accepting
                       per standard lifecycle
~~~

An **unhandled runner exception** causes **SpringApplication.run(...) to fail**, even though the context refreshed earlier.

**Subtle point:** in a web app, the embedded server may have already opened its socket before runners execute. Do not treat a runner check as an absolute barrier blocking requests at startup; readiness probes and load balancers must route traffic only to ready instances.

### 9.1. Do not swallow failures of critical dependencies

The following is an anti-pattern if the remote is truly mandatory:

~~~java
try {
    remoteProbe.verify();
} catch (Exception ignored) {
    // Startup continues and may report a false ready state.
}
~~~

This is an illustrative snippet, not a standalone program. If a critical dependency is down, the server still receives traffic and returns business errors. For optional dependencies, degraded startup can be valid, provided there are **clear logs/metrics/status and runtime handling**; never use silent catch-all blocks.

### 9.2. Startup retries must be bounded

Do not do:

~~~java
while (true) {
    tryConnect();
}
~~~

This is an anti-pattern snippet. Infinite retries can stall startup forever, prevent `ApplicationReadyEvent`, and leave rollouts stuck.

Instead:

- Give each probe attempt a connect/request timeout.
- Cap total retry time with a deadline.
- Use bounded backoff and jitter when needed.
- Distinguish retryable 5xx/network failures from non-retryable config/401/403 errors.
- Once the deadline expires, decide to fail startup or run degraded based on the contract.
- Respect interrupt signals and shutdown hooks.

## 10. Readiness and liveness must not be conflated

| Mechanism | Question answered | Guidance |
| --- | --- | --- |
| **Liveness** | Is the process itself still functioning properly? | Do not couple blindly to remote outages |
| **Readiness** | Can the instance accept current workload? | Can factor in critical dependencies |
| **Startup validation** | Is static config valid? | Fail-fast on missing/invalid |
| **Startup remote probe** | Is the remote responding at startup? | Clearly choose critical vs optional |
| **Runtime resilience** | What if the remote breaks after ready? | Timeouts/retries/circuit breakers/fallbacks |

A shared backend outage should not automatically restart every API pod. If liveness depends on that backend, the whole cluster can enter a restart storm.

Conversely, if the entire API cannot perform its primary function when a remote is down, readiness must reflect that state in a controlled manner.

### 10.1. Cost of a readiness probe

If every pod probes a remote every few seconds across hundreds of pods, checking itself can generate heavy load on the backend. Consider:

- Caching/intervals and result TTLs.
- Limiting concurrent probes.
- Reading state from a background monitor rather than making network calls on every HTTP probe.
- Distinguishing optional from critical remotes.
- Avoiding cluster-wide unready states when an error affects only an auxiliary route.

## 11. Configuration and secrets in containers

### 11.1. Environment variables and relaxed binding

Spring Boot uses relaxed binding. For canonical property names, the environment variable rule generally **replaces dots with underscores, drops hyphens, and uppercases**.

For example, **demo.remote.timeout-ms** maps to an environment variable like **DEMO_REMOTE_TIMEOUTMS**. Do not assume every variant with extra underscores means the same thing; verify against Boot documentation and effective values.

### 11.2. Config trees

If the platform mounts secrets as files:

~~~text
/etc/secrets/
    remote.username
    remote.password
~~~

you can use:

~~~properties
spring.config.import=configtree:/etc/secrets/
~~~

If the directory is required, do not add `optional:`. If a secret is not mounted, failing fast signals a deployment issue that must be fixed.

**Never print the full Environment or passwords/tokens into logs** when debugging errors. Log only key names, constraint types, bean names, and secret-free messages.

### 11.3. Actuator /env and /configprops

These endpoints aid property inspection, yet risk leaking sensitive values if exposed publicly. Enforce authentication/authorization, value masking, and restrict exposed endpoints. Never expose management endpoints publicly just to debug startup.

## 12. @Lazy can defer configuration errors until first use

Example:

~~~java
@Bean
@Lazy
RemoteClient remoteClient(Environment environment) {
    String url = environment.getRequiredProperty(
            "demo.remote.health-url");
    return new RemoteClient(url);
}
~~~

This snippet requires imports and a `RemoteClient` class. If the bean has not been requested yet, executing its factory method can be deferred. Property errors may then surface on the first **getBean(...)** call rather than during context refresh.

Enabling:

~~~properties
spring.main.lazy-initialization=true
~~~

also defers creation of many beans. For critical configuration, consider:

- An eager validator bean or **@Lazy(false)** for critical components.
- An `ApplicationRunner` performing static checks before ready.
- Tests verifying that missing/invalid keys fail startup.
- Not putting network checks into constructors solely to force fail-fast.

**Not all errors are lazy:** Config Data, the bean registry, and infrastructure can still fail at startup.

## 13. Reading the exception chain and FailureAnalyzer

Configuration property failures may show up as:

~~~text
ConfigurationPropertiesBindException
    |
    +-- BindException / BindValidationException
            |
            +-- healthUrl must not be blank
            +-- timeoutMs must be >= 100
~~~

Remote probe failures may show up as:

~~~text
ApplicationRunner invocation
    |
    +-- ConnectException / HttpTimeoutException
         or IllegalStateException: HTTP 503
    |
    +-- SpringApplication startup failure
~~~

These are **typical diagrams**, not exact stack traces for every run. Exception wrappers vary by implementation and version.

To debug systematically:

1. Identify the failure milestone: Config Data, bean creation, runner, or runtime.
2. Read the root cause and property/bean name.
3. For binding: inspect expected type, source, active profile, and rejected value (with secrets masked).
4. For remotes: distinguish DNS, TCP, TLS, HTTP auth, status code, and timeout.
5. Compare effective configuration between dev and deployment.
6. If Boot provides a **FailureAnalyzer**, read its Description/Action.
7. When needed, use debug/conditions reports in a controlled diagnostic environment.

**Never "fix" issues by disabling all validation or logging passwords.**

## 14. Common design mistakes

### 14.1. Using @NotNull for required Strings

Empty strings still pass `@NotNull`. Use `@NotBlank` when blank values are disallowed.

### 14.2. Forgetting the validation starter

`@Validated` and Jakarta constraints require a provider. Add `spring-boot-starter-validation` and test actual failure cases.

### 14.3. Mixing up javax and jakarta in Boot 3

Boot 3 uses `jakarta.validation`. Check imports and dependencies.

### 14.4. Hiding missing keys with empty defaults

If an endpoint is required, an empty default merely pushes the failure to runtime.

### 14.5. Making network calls in constructors or getters

Slows bean creation and blurs error classification; use a separate probe component with timeouts.

### 14.6. Assuming a valid URL means the remote is online

A URL is static data; network availability is dynamic state. Validate them separately.

### 14.7. Using side-effecting POST requests as health checks

Can create real transactions, especially on retries. Choose read-only health endpoints.

### 14.8. Infinite retries inside runners

Startup can hang indefinitely. Use bounded retries with a deadline and clear failure policy.

### 14.9. Swallowing critical dependency failures and still reporting ready

Turns live traffic into your error detector. Use fail-fast or readiness gates.

### 14.10. Failing every instance because of an optional remote

Reduces availability of unrelated features. Design properly scoped degraded modes.

### 14.11. Putting remote health into liveness

Can cause restart storms during backend outages. Liveness should reflect process health only.

### 14.12. Thinking a passing startup probe is enough

Remotes can fail later. Runtime needs resilience and observability.

### 14.13. Not testing profiles and secret mounting

Dev has the property while production lacks the file or secret. Test deployment/config contracts.

### 14.14. Lazy critical beans failing only on the first request

Keep static validation eager before ready on critical paths.

### 14.15. Logging the full Environment and secrets

Exposes credentials via logs and monitoring. Mask values and log only safe diagnostic details.

## 15. Testing matrix

| Scenario | Expected outcome |
| --- | --- |
| Missing health-url | Binding/validation fails before runner |
| Empty or whitespace health-url | `@NotBlank` fails |
| timeout-ms=abc | Type conversion/binding fails |
| timeout-ms=50 | `@Min` fails |
| Valid config, probe false | App starts without needing backend |
| Probe true, port not listening | Runner fails with network cause |
| Probe true, stub HTTP 200 | Runner succeeds |
| Probe true, stub HTTP 503 | Runner fails with HTTP status |
| Invalid URI scheme, probe true | Probe preflight fails clearly |
| Wrong active profile | Missing config is caught |
| Missing required import location | Config Data failure |
| Missing optional import location | Does not fail solely because location is absent |
| Remote outage after ready | Runtime timeout/retry/degraded handling |
| Global lazy enabled | Critical validation still enforced before ready via tests |
| Many replicas starting | No retry/probe storm triggered |

Not every system must hard-fail when a remote is offline. Your matrix should reflect actual critical/optional policies.

## 16. Pre-deployment checklist

- [ ] Separate Config Data, binding, validation, and remote availability errors.
- [ ] Clearly document required properties and their sources.
- [ ] Use the `jakarta.validation` namespace and include the validation starter.
- [ ] Register `@ConfigurationProperties` beans properly.
- [ ] Match constraints to types: `@NotBlank`, `@NotNull`, `@Min`, `@Valid`.
- [ ] Test missing, blank, wrong-type, and out-of-range values.
- [ ] Verify active profiles, CLI overrides, and environment variables.
- [ ] Do not use `optional:` for mandatory config/secrets.
- [ ] Do not log secrets or expose `/env`, `/configprops` publicly.
- [ ] Separate static config validation from HTTP/TCP I/O.
- [ ] Explicitly classify remotes as critical or optional.
- [ ] Configure startup probes with connect/request timeouts and bounded retries.
- [ ] Do not swallow runner failures for critical dependencies.
- [ ] Align readiness with workload and avoid tying liveness blindly to remotes.
- [ ] Implement runtime retries/circuit breakers/fallbacks as needed.
- [ ] Add integration tests for HTTP 200/503/unreachable cases.
- [ ] Do not depend on public Internet APIs in unit tests.
- [ ] If lazy is enabled, ensure critical config is still validated before ready.
- [ ] Emit metrics/logs by phase, bean/property key, and root cause.
- [ ] Do not invoke health checks that trigger business side effects.

## 17. Self-check questions

**Q1.** How does a missing Config Data import differ from a missing `@NotBlank` property?

**Answer:** A missing import can fail while preparing the Environment; `@NotBlank` is checked when the configuration properties bean binds/validates.

**Q2.** Why is `@NotNull` insufficient for a URL String?

**Answer:** It does not reject empty or whitespace strings. Use `@NotBlank` plus syntax validation when needed.

**Q3.** Does Spring Boot 3 use `javax.validation` or `jakarta.validation`?

**Answer:** `jakarta.validation`.

**Q4.** Are `timeout-ms=abc` and `timeout-ms=50` against `@Min(100)` the same type of failure?

**Answer:** No. `abc` fails numeric conversion; `50` binds successfully but violates the constraint.

**Q5.** Does `@ConfigurationProperties` connect to external services on its own?

**Answer:** No, it binds and validates data; network checks are separate logic.

**Q6.** When `ApplicationRunner` throws an exception, is the ready milestone published as successful?

**Answer:** Not in normal startup; `run` fails and enters startup failure handling.

**Q7.** If a runner fails, does that mean the web server has not opened its port yet?

**Answer:** No. The context may already be refreshed and the server socket open; readiness and routing still matter.

**Q8.** Does a startup HTTP 200 check guarantee the remote will stay up forever?

**Answer:** No. The remote can fail immediately afterward; runtime resilience is required.

**Q9.** Why shouldn't every remote dependency be included in liveness?

**Answer:** A shared outage can cause unnecessary restarts across the entire cluster.

**Q10.** Why shouldn't a health check perform a transaction-creating POST?

**Answer:** It can mutate data and cause duplicate side effects on retries.

**Q11.** Does global lazy initialization affect when beans are validated?

**Answer:** Potentially yes, if the bean is created late. Critical config needs an eager validator or explicit startup step.

**Q12.** When an optional remote is offline, what is a reasonable strategy?

**Answer:** Degraded startup with observability and runtime timeouts/retries/fallbacks, provided business logic can still operate without that remote.

## 18. Summary

To handle startup failures accurately, divide them into three layers:

1. **Configuration sources:** do files, profiles, environment variables, and imports exist and load properly?
2. **Binding and validation:** do values have the right types, non-missing content, and satisfy required constraints?
3. **Remote dependencies:** do we need to verify external state before accepting traffic, and how do we check with bounded timeouts and zero side effects?

**@ConfigurationProperties + @Validated + Jakarta Validation** suit failing fast on static configuration errors. **ApplicationRunner** can run deliberate fail-fast remote probes before `ApplicationReadyEvent`. When a remote is non-critical, use an explicit degraded mode instead of forcing every instance to fail.

A single successful startup does not replace runtime resilience. Do not mask failures behind empty defaults, infinite retries, accidental lazy validation, or secret-leaking logs; classify the phase accurately, inspect root causes, and test each failure type independently.

## 19. Official documentation

- Spring Boot 3.3 — Externalized Configuration, Config Data and @ConfigurationProperties Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — SpringApplication, startup failure and runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — ConfigurationProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — Actuator Health and Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Cloud Config — Config Data Import, Fail Fast: https://docs.spring.io/spring-cloud-config/reference/client.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/