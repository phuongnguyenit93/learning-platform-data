# Identifying Conditions for Built-In Endpoints to Appear

## 1. Built-In Endpoints Reflect a Capability Present in the Application

In Actuator, a built-in endpoint is a ready-made endpoint tied to a library or application component, such as Flyway, Liquibase, or Prometheus. To read information from that component, Actuator needs to find the corresponding conditions in the running application.

Think of an endpoint as an observation window: there must be a component to observe, an object supplying the data, and only then do you consider opening the window over HTTP/JMX and granting permission to pass through. Therefore, adding an endpoint name to the exposure list is not enough to create the integration capability.

This lesson uses Spring Boot 3.3.x, referencing the 3.3.13 documentation; examples use JDK 21. The goal is to identify the missing condition when a built-in endpoint does not appear, without going deep into business configuration of each library.

## 2. Distinguish Questions Before Changing Configuration

| Question | Diagnostic meaning |
| --- | --- |
| Is the library on the runtime classpath? | Are the classes required by the integration available yet? |
| Is the underlying bean in the ApplicationContext? | Is the component to observe managed by Spring yet? |
| Is the endpoint enabled? | What is the effective value of `management.endpoint.<id>.enabled`? |
| Is the endpoint exposed over the channel being tested? | HTTP and JMX have separate exposure lists. |
| Are the address and access permissions right? | Are you calling the right port, path, and with an authorized identity? |
| Does the endpoint have data? | Is there a data source and has activity occurred to observe yet? |

This is a diagnostic reasoning order, not the internal method invocation sequence inside Spring Boot.

In Boot 3.3, `@ConditionalOnAvailableEndpoint` checks that the endpoint is both enabled and exposed over an appropriate technology. Thus, exposure conditions can directly affect whether the endpoint bean is auto-configured; do not assume every endpoint is created first and only has its URL hidden. [Javadoc for endpoint availability condition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

## 3. Read Conditions on Both Configuration Classes and Bean Factory Methods

Commonly encountered annotations:

- `@ConditionalOnClass`: applies only when the required class is on the classpath.
- `@ConditionalOnBean`: requires a matching bean in the ApplicationContext scope evaluated by the condition.
- `@ConditionalOnMissingBean`: auto-configuration backs off when the application already defines a matching bean; a non-match here does not mean the feature is missing.
- `@ConditionalOnProperty`: evaluates configuration property values.

You must read conditions on the configuration class, nested classes, and `@Bean` methods. A configuration class being selected does not prove every bean inside it is created. [Auto-configuration condition annotations](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

### Example Reading Flyway Conditions

`FlywayEndpointAutoConfiguration` in Boot 3.3.13 has conditions that the `Flyway` class exists and the endpoint is available. The method creating `FlywayEndpoint` also requires a `Flyway` bean and backs off if a corresponding endpoint bean already exists.

From these conditions, you can deduce: having only the `flyway-core` dependency does not prove the application has a `Flyway` bean; having only a `DataSource` bean also does not prove there is a `Flyway` bean. You need to check the actual integration bean configuration. [Javadoc FlywayEndpointAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/flyway/FlywayEndpointAutoConfiguration.html).

## 4. Some Endpoints with Easily Identifiable Integration Conditions

| Endpoint ID | Integration condition worth checking | Cannot be inferred solely from |
| --- | --- | --- |
| `flyway` | `Flyway` class and at least one `Flyway` bean | Having a database or having a `DataSource` |
| `liquibase` | `SpringLiquibase` class and bean in Spring integration config | Having changelog files in resources |
| `httpexchanges` | `HttpExchangeRepository` bean to supply HTTP exchange history | Having a web server or the Actuator starter |
| `prometheus` | Prometheus registry, registry auto-configuration conditions, and scrape endpoint | `metrics` endpoint already returning data |

For Liquibase, check the specific bean type `liquibase.integration.spring.SpringLiquibase`, rather than looking for any object with a name similar to Liquibase. The endpoint is not created just because there is a changelog on disk. [Javadoc LiquibaseEndpointAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/liquibase/LiquibaseEndpointAutoConfiguration.html).

With `httpexchanges`, Spring Boot provides `InMemoryHttpExchangeRepository` for development use, keeping the latest 100 exchanges by default. Having the endpoint and recording additional data are two separate checks: `management.httpexchanges.recording.enabled=false` turns off recording. [Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

### The Prometheus Case

The common dependency is `io.micrometer:micrometer-registry-prometheus`. In Boot 3.3.13 auto-configuration, there are also conditions on `Clock`, the `PrometheusMeterRegistry` class, and the property allowing Prometheus metrics export. The nested configuration creating the endpoint further checks availability of the scrape endpoint and existing beans.

Therefore, distinguish three things: having the registry library, having the registry configured, and having the scrape endpoint exposed. [PrometheusMetricsExportAutoConfiguration 3.3.13 source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.java).

`/actuator/metrics` serves viewing metrics via the Actuator API; `/actuator/prometheus` serves the format for Prometheus scraping. Having metrics in the first endpoint is not enough to prove the second endpoint is ready. The `management.prometheus.metrics.export.enabled` property controls Prometheus metrics export auto-configuration, which is different from `management.endpoint.prometheus.enabled` controlling the endpoint. [Metrics and Prometheus documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 5. Enabling, Exposing, and Securing Endpoints Are Different Configurations

HTTP configuration example:

```properties
management.endpoint.httpexchanges.enabled=true
management.endpoints.web.exposure.include=health,httpexchanges
```

In Boot 3.3, built-in endpoints are enabled by default except `shutdown`; by default only `health` is exposed over HTTP and included in the JMX exposure list. `exclude` takes precedence over `include`. Disabling an endpoint with `enabled=false` differs from merely omitting it from one exposure channel.

If Spring Security is present and the application has not declared a `SecurityFilterChain`, Boot protects Actuator endpoints other than `health`. When the application declares its own security chain, you must read the actual policy of the application. The exposure list does not grant access permissions. [Enabling, exposing, and securing endpoints in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

The following example excludes `httpexchanges` from HTTP even though it remains in `include`: 

```properties
management.endpoints.web.exposure.include=health,httpexchanges
management.endpoints.web.exposure.exclude=httpexchanges
```

Expanding `include` to `*` does not supply missing beans or dependencies. While learning, expose only the endpoint being verified.

JMX has separate configuration, for example:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,httpexchanges
```

This configuration still requires the repository bean and other endpoint conditions. Seeing an MBean does not prove the endpoint has an HTTP URL. [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 6. Experiment: Keep Exposure Unchanged, Change the Underlying Bean

### 6.1. Preparing a Standalone Project

This example is for a separate test directory with Gradle Wrapper 8.5 and JDK 21. Network access is needed for downloading plugins/dependencies the first time. Do not add Spring Security or other management configurations to this experiment so the results below depend only on the changes under test.

Structure of files to create:

```text
actuator-conditions/
  settings.gradle
  build.gradle
  gradlew.bat
  gradle/wrapper/...
  src/main/java/demo/ActuatorConditionsApplication.java
  src/main/resources/application.properties
```

`settings.gradle`: 

```groovy
rootProject.name = 'actuator-conditions'
```

`build.gradle`: 

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`src/main/java/demo/ActuatorConditionsApplication.java`: 

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorConditionsApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @Bean
    @ConditionalOnProperty(name = "demo.exchanges.repository", havingValue = "true")
    public HttpExchangeRepository httpExchangeRepository() {
        return new InMemoryHttpExchangeRepository();
    }
}
```

`src/main/resources/application.properties`: 

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,httpexchanges
```

`demo.exchanges.repository` is a custom property defined for this example, not a built-in Actuator property. When its value is `true`, the `@Bean` method provides the repository. When undeclared, this condition does not match.

This is a complete Spring Boot application when accompanied by the files and Wrapper mentioned above; do not run the Java file with a `javac` command lacking dependency classpath.

### 6.2. Run A: Included Yet No Repository

In PowerShell, start:

```powershell
.\gradlew.bat bootRun
```

Wait for the application to start successfully. In another PowerShell window:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/httpexchanges
```

Two expected stdout lines, in order:

```text
200
404
```

Conclusion of Run A: the HTTP server and Actuator are running; `httpexchanges` is in exposure, yet the bean supplying HTTP history is still missing.

### 6.3. Run B: Provide the Repository, Keep Exposure Unchanged

Stop the application with Ctrl+C, wait for the process to exit, then run again:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true"
```

Call in order:

```powershell
curl.exe -s http://127.0.0.1:8080/ping
```

The exact response body of `/ping` is `pong` (the command above does not append a newline). Then check the HTTP status code:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/httpexchanges
```

Expected stdout:

```text
200
```

To inspect the data, call the same URL again without `-o NUL -w ...`. The JSON content has information about recorded exchanges; timestamps, durations, and item counts depend on actual activity, so there is no fixed JSON string for every run.

Conclusion of Run B: the decisive change was having the repository bean; there was no need to open up all endpoints.

### 6.4. Run C: Repository Present but Endpoint Disabled

Stop Run B, then run:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true --management.endpoint.httpexchanges.enabled=false"
```

Repeat the command to get the HTTP status code of `httpexchanges`: expected `404`. The underlying bean is still declared, yet the endpoint is disabled.

Proceed with an independent run, replacing the disable flag with the HTTP exclusion flag:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true --management.endpoints.web.exposure.exclude=httpexchanges"
```

Also expected `404`, yet for a different configuration reason. These two runs show that you cannot distinguish a missing bean, disabled state, and unexposed state from a single status code.

The results above assume the exact sample project, a free port, and no proxy, environment variables, or external config files overriding values; they are not a claim that every customized application returns the same codes.

## 7. Diagnosing with Evidence in a Real Application

### Check the Address First

Confirm the application has started and is listening. For HTTP, verify `management.server.port`, `management.endpoints.web.base-path`, `management.endpoints.web.path-mapping`, and the application's context path. The management port can differ from the business port; `management.server.port=-1` disables management HTTP. [Configuring management port and paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Read the Condition Evaluation Report

Start the actual JAR with `--debug` to view the condition evaluation report in logs:

```powershell
java -jar .\app.jar --debug
```

`app.jar` here is an illustrative name; replace it with the actual artifact name. Find the endpoint configuration and the underlying bean's configuration. Read the non-match reasons, rather than merely counting entries under negative matches. Check excluded configurations as well as cases where auto-configuration backed off for an application-declared bean. [Auto-configuration report and back-off mechanism](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

Example of how to record a verifiable finding:

```text
Observation: GET /actuator/httpexchanges returned 404.
Additional evidence: no HttpExchangeRepository bean present.
Hypothesis: missing data source for the endpoint.
Experiment: add only the repository in development config, restart.
Re-verify: check conditions and call the same URL again.
```

This is a reasoning template, not a verbatim excerpt of Spring Boot logs. If you choose to use `/actuator/conditions` to view the report, that endpoint itself must be enabled, exposed, and accessed with proper permissions.

### Categorizing Symptoms

| Symptom | Next check |
| --- | --- |
| Cannot connect | Process, address, port, protocol, network |
| `404` | Path, bean, enablement, exposure; also check proxy/custom policies |
| `401`, `403`, or login redirect | Authentication, authorization, actual security chain; not enough to conclude endpoint exists |
| `200` but empty data | Data source, recording config, activity generated |
| `5xx` | Execution error, integration component failure, exception logs |

This table is a narrowing guide, not a guaranteed reverse inference from HTTP status codes. Security filters may block a request before handler lookup; proxies can also alter responses.

## 8. Common Mistakes and Self-Checks

- **Only adding exposure:** verify runtime dependencies and the underlying bean first.
- **Library present yet no bean:** check integration configuration, active profiles, and excluded configurations.
- **Seeing a negative match and deleting your own declared bean:** check whether that is an `@ConditionalOnMissingBean` branch backing off by design.
- **Seeing an endpoint return an empty list and trying to re-enable it:** check data generation and storage; do not equate empty data with an absent endpoint.
- **Editing a config file without knowing effective values:** check command-line arguments, environment variables, and active profiles overriding them.

Practice: for each situation, state which condition needs checking and what evidence you will collect.

1. `flyway` is in HTTP `include`; the application has a `DataSource` but no `Flyway` bean.
2. `metrics` returns measurements; the project has no Prometheus registry.
3. `httpexchanges` has a repository and is included, yet is also in HTTP `exclude`.
4. `httpexchanges` returns `200`, the repository is empty after startup, and HTTP recording is disabled.

Reference: (1) missing Flyway integration bean; (2) missing registry integration for Prometheus; (3) excluded from HTTP; (4) endpoint is reachable, need to check data recording. In each case, change only the condition under verification and measure again, rather than changing dependency, exposure, and security simultaneously.
