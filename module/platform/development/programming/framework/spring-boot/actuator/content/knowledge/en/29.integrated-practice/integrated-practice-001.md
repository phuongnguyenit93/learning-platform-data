# Build an application with health and info using a minimal exposed endpoint set

## 1. Practice goal and mental model

A service needs to tell operational tools at least two things: what the health checks are currently returning, and which version of the application this is. Spring Boot Actuator provides two suitable endpoints:

- **health** returns the aggregated health status from the configured health contributors.
- **info** returns descriptive application information provided by info contributors.

In this exercise, we build a web application that exposes only those two Actuator endpoints over HTTP. Health returns only the aggregated status; info returns only three selected descriptive fields. Endpoints such as env, beans, metrics, loggers, or heapdump are not part of the exposure contract.

“Minimal” must be demonstrated in both configuration and verification: being able to call health/info is only the first half; the other half is confirming that endpoints outside the list are not exposed.

Four decisions must be distinguished:

| Decision | Question it answers | Example in this lab |
| --- | --- | --- |
| Enable endpoint | Which endpoints are allowed to run? | Enable only health and info |
| Expose over channel | Which endpoints have an HTTP/JMX route? | HTTP includes health, info; export no endpoints over JMX |
| Access control | Who can call that route? | Lab listens only on loopback |
| Data minimization | What information may the response contain? | Health only has status, info only has app |

Enabling an endpoint and exposing it are separate steps. This mechanism is described in [Spring Boot 3.3 Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

The application in this lab uses Spring MVC, Java 21, and Gradle 8.5. The code is a standalone project with Spring Boot dependencies, not a single-file program to run with `javac`.

## 2. Output contract before writing code

With the application running on a development machine and keeping the configuration in this lab:

| HTTP Request | Expected Result |
| --- | --- |
| `GET /actuator/health` | HTTP 200 and `{"status":"UP"}` when existing checks are healthy |
| `GET /actuator/info` | HTTP 200 and an app object with name, version, description |
| `GET /actuator/env` | HTTP 404 |
| `GET /actuator/beans` | HTTP 404 |
| `GET /actuator/configprops` | HTTP 404 |
| `GET /actuator/metrics` | HTTP 404 |
| `GET /actuator/loggers` | HTTP 404 |
| `GET /actuator/heapdump` | HTTP 404 |
| `GET /actuator/threaddump` | HTTP 404 |
| `GET /actuator/shutdown` | HTTP 404 |
| `GET /actuator` | HTTP 404 because the endpoint discovery page is disabled |

This table applies specifically to the sample application, with no Spring Security, proxy, or additional controllers. If integrated into another system, a security layer may return 401/403 before the request reaches the router. In that case, you must also verify the set of registered endpoints rather than inferring solely from HTTP status codes.

The UP status depends on the active checks. The sample does not attach a database or external service yet; however, machine resources, such as disk space, can still affect the health result. Do not modify an endpoint to always return UP just to make the checklist pass.

## 3. Create the project structure

Prepare JDK 21 and a Gradle 8.5 installation to generate the wrapper for the first time. Verify the Java and Gradle versions in the terminal you will use to run the lab.

Create the `actuator-minimal` directory with the following structure:

```text
actuator-minimal/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/actuatorminimal/
    │   │   └── ActuatorMinimalApplication.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/actuatorminimal/
            └── ActuatorExposureTest.java
```

The files below are sufficient for the sample project. The wrapper will be generated using Gradle; do not write the wrapper JAR contents manually.

### 3.1. settings.gradle

```groovy
rootProject.name = 'actuator-minimal'
```

### 3.2. build.gradle

The example pins Spring Boot 3.3.0 to keep the lab reproducible within the 3.3.x line. Spring Boot dependencies share the BOM matching the plugin version.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Roles of the components:

- The `java` plugin provides compilation and testing tasks.
- The Spring Boot plugin provides `bootRun` and `bootJar`.
- The toolchain selects JDK 21 for compilation.
- The BOM provides a compatible set of dependency versions.
- `spring-boot-starter-web` provides Spring MVC and the embedded web server.
- `spring-boot-starter-actuator` provides the management endpoint infrastructure.
- `spring-boot-starter-test` and JUnit Platform support contract testing.

Using the BOM via `platform` is supported directly in the [Spring Boot Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html#managing-dependencies.gradle-bom-support). This project does not need another dependency-management plugin added simultaneously to do the same job.

### 3.3. Startup class

File `src/main/java/com/example/actuatorminimal/ActuatorMinimalApplication.java`:

```java
package com.example.actuatorminimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorMinimalApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorMinimalApplication.class, args);
    }
}
```

There is no need to write custom controllers for health or info. These endpoints belong to Actuator and are auto-configured when conditions are met.

Place the startup class in the parent package of the application code. The test class is also placed in the same package so the test runner can locate the Spring Boot configuration.

## 4. Allowlist configuration

File `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: actuator-minimal
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
      probes:
        enabled: false
    info:
      enabled: true
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: actuator-minimal
    version: "1.0.0"
    description: "Minimal Actuator practice application"
```

There is no separate management port configured in this lab; HTTP endpoints use port 8080 of the web server. The `127.0.0.1` address restricts the listener to the machine running the application. When running in a container, loopback is the container's loopback; this lab defaults to running directly on the development machine.

### 4.1. Two layers of endpoint selection

`management.endpoints.enabled-by-default: false` switches to per-endpoint opt-in. The two keys `management.endpoint.health.enabled` and `management.endpoint.info.enabled` re-enable exactly the required endpoints.

The `management.endpoints.web.exposure.include` list selects health and info for HTTP. Enabling and exposure configurations are intentionally identical in this lab; they guard two different decisions.

Key names must be read carefully:

- Plural `endpoints` is used for global policy.
- Singular `endpoint` is used to configure one specific endpoint.
- `info` under `management.endpoint` controls the info endpoint.
- `management.info` controls the data contributors for that endpoint.

There is no need to use `include: "*"` and then try to list everything to exclude. When the requirement is just two endpoints, explicitly listing both IDs makes the intent immediately clear to readers and tests.

### 4.2. HTTP and JMX are two separate channels

`spring.jmx.enabled: false` keeps Spring's MBean exporter disabled. The `management.endpoints.jmx.exposure.exclude: "*"` setting also proactively excludes Actuator endpoints from the JMX channel.

Do not assume the HTTP list automatically applies to JMX. Nor do these settings mean every third-party library in the JVM is prohibited from registering MBeans itself. The scope of Spring JMX is covered in [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 4.3. Disable the endpoint discovery page

`management.endpoints.web.discovery.enabled: false` turns off the links document at the `/actuator` root path. Thus, a 404 at `/actuator` is an intentional outcome of this lab, while the two child paths must still work.

Hiding the discovery page does not replace exposure or authentication. If another endpoint is exposed, lacking a link to it does not make its route disappear. Therefore, the lab still checks the set of endpoint IDs and unlisted paths.

### 4.4. Minimize returned health data

`show-details: never` omits check details. `show-components: never` omits the component list. Checks can still affect the aggregated status.

The lab disables automatic probe group activation with `probes.enabled: false` so the practice scope does not change based on whether the application detects it is running on Kubernetes. This exercise does not design a separate liveness/readiness contract yet.

Health and discovery properties can be cross-referenced in the [Spring Boot 3.3 configuration properties appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

## 5. Intentionally populate info data

Having the info endpoint active and having data in it are two different things. When the endpoint is enabled and exposed without an appropriate info contributor, it can still return HTTP 200 with `{}`.

The configuration in this lab selects one specific source:

```text
info.* properties
        ↓
EnvironmentInfoContributor
        ↓
info endpoint
        ↓
GET /actuator/info
```

`management.info.env.enabled: true` enables the info contributor that reads properties prefixed with `info.`. It does not enable the `/actuator/env` endpoint. Its data scope is described in [EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html).

`management.info.defaults.enabled: false` turns off the default contributors that are normally auto-enabled. Then the env contributor is explicitly re-enabled. This prevents the sample from automatically adding build or Git information just because a metadata file appears later. How contributors are created is shown in [InfoContributorAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html).

The three fields of this lab:

| Field | Purpose |
| --- | --- |
| `info.app.name` | Identifies the application being queried |
| `info.app.version` | Identifies the version per the lab convention |
| `info.app.description` | Short description to help operators understand the application |

Two boundaries must be kept clear:

1. The env contributor reads `info.*` properties; it does not automatically restrict itself to just the three app fields just declared. If `info.secret` is added, do not assume that secret will be automatically masked.
2. Disabling default contributors does not automatically remove a custom `InfoContributor` registered in application code.

Therefore, the list of exposed data must be maintained in configuration and tests. Do not put passwords, tokens, internal connection details, or the entire process environment into the `info` branch.

Version `1.0.0` in YAML is static lab data. It does not automatically stay in sync with `version` in Gradle if only one side is changed. When bumping the sample version, update the corresponding value and test expectations in the same change.

## 6. Run the application and test live

Open PowerShell in the `actuator-minimal` directory. Use the prepared Gradle 8.5 to generate the wrapper:

```powershell
gradle wrapper --gradle-version 8.5
```

Then use the wrapper for subsequent runs:

```powershell
.\gradlew.bat bootRun
```

The first run requires connectivity to the plugin/dependency repositories if they are not yet cached. Wait for logs confirming the application has started; port 8080 must be free.

Open a second terminal. On Windows, use `curl.exe` to avoid confusion with the PowerShell alias.

### 6.1. Check health

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health
```

When health contributors are healthy, the response has HTTP 200. The JSON body of the response:

```json
{
  "status": "UP"
}
```

Do not expect `components`, disk paths, or dependency details. Not seeing details is a configuration result, not a broken endpoint.

UP in the sample proves the current check set passed. It does not prove every business operation of a future application will succeed.

### 6.2. Check info

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/info
```

The response has HTTP 200 and equivalent content:

```json
{
  "app": {
    "name": "actuator-minimal",
    "version": "1.0.0",
    "description": "Minimal Actuator practice application"
  }
}
```

JSON examples are indented for readability. Whitespace, key ordering, and headers such as date may vary; check JSON structure and values rather than exact-string matching the entire HTTP response.

Info describes the application; health reflects check status. A valid info response does not replace a health check, and info does not normally change HTTP status codes just because a dependency is unhealthy.

### 6.3. Check unexposed endpoints

Run in PowerShell:

```powershell
$endpointIds = @(
    'env', 'beans', 'configprops', 'metrics',
    'loggers', 'heapdump', 'threaddump', 'shutdown'
)

foreach ($endpointId in $endpointIds) {
    $url = "http://127.0.0.1:8080/actuator/$endpointId"
    $statusCode = curl.exe -sS -o NUL -w '%{http_code}' $url
    "$endpointId=$statusCode"
}
```

Expected output of the loop:

```text
env=404
beans=404
configprops=404
metrics=404
loggers=404
heapdump=404
threaddump=404
shutdown=404
```

Also check the discovery page:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator
```

Expect HTTP 404. Do not use this 404 response to conclude all of Actuator is disabled; health and info above must still respond.

On Linux/macOS, use `curl`, `./gradlew`, and `/dev/null` instead of `curl.exe`, `.\gradlew.bat`, and `NUL` when running the corresponding commands.

## 7. Contract tests to keep the endpoint set small

Manually testing only the two successful URLs misses the case where someone accidentally exposes another endpoint. The test suite below checks both allowed data and disallowed data/routes.

File `src/test/java/com/example/actuatorminimal/ActuatorExposureTest.java`:

```java
package com.example.actuatorminimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorExposureTest {
    @Autowired
    private MockMvc http;

    @Autowired
    private WebEndpointsSupplier webEndpoints;

    @Test
    void healthReturnsOnlyStatus() throws Exception {
        http.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"UP\"}", true));
    }

    @Test
    void infoReturnsOnlyApprovedMetadata() throws Exception {
        http.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "app": {
                            "name": "actuator-minimal",
                            "version": "1.0.0",
                            "description": "Minimal Actuator practice application"
                          }
                        }
                        """, true));
    }

    @Test
    void unapprovedRoutesAreAbsent() throws Exception {
        String[] paths = {
                "/actuator",
                "/actuator/env",
                "/actuator/beans",
                "/actuator/configprops",
                "/actuator/metrics",
                "/actuator/loggers",
                "/actuator/heapdump",
                "/actuator/threaddump",
                "/actuator/shutdown"
        };

        for (String path : paths) {
            http.perform(get(path)).andExpect(status().isNotFound());
        }
    }

    @Test
    void onlyHealthAndInfoAreDiscoveredAsWebEndpoints() {
        assertThat(webEndpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .containsExactlyInAnyOrder("health", "info");
    }
}
```

Run:

```powershell
.\gradlew.bat test
```

Four things the test suite proves:

1. Health returns JSON containing only `status` with value UP under the sample's conditions.
2. Info returns the exact approved dataset, with no extra fields in the JSON.
3. Unlisted HTTP routes and the discovery page do not exist in the sample application.
4. The discovered Actuator web endpoint set is exactly `health` and `info`.

The `true` argument in `content().json(..., true)` enforces strict JSON matching, which catches added fields. This is a structural JSON comparison, independent of object key order.

`@SpringBootTest` loads the application configuration; `@AutoConfigureMockMvc` enables performing requests through the mocked Spring MVC layer. The test suite does not bind port 8080 and does not exercise out-of-process networking. Distinguish mock testing from testing with a real web server in [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

The `WebEndpointsSupplier` check complements the 404 requests: it catches even a newly added endpoint ID not listed in the test loop. Its scope is Actuator web endpoints, not every controller, static resource, or route created by an external proxy.

Do not record the entire Gradle log as a fixed stdout expectation for the lab. A zero exit code and test results are the primary evidence; execution times, report paths, and log line counts can vary.

### Package and test the JAR build

After tests pass, build the executable JAR:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/actuator-minimal-1.0.0.jar
```

Stop the previous `bootRun` session with Ctrl+C before running the JAR to avoid port conflicts. Re-verify health, info, and some excluded endpoints against the JAR build. This verifies the packaged configuration resources as well, not just test-class behavior.

## 8. Common errors and root-cause identification

| Symptom | Check in order | Scope-appropriate fix |
| --- | --- | --- |
| Health 404 | Actuator dependency, enablement, exposure, URL | Verify the right application and both configuration layers |
| Info 404 while health works | info.enabled and include list | Enable/expose specifically info, do not open all endpoints |
| Info returns `{}` | env contributor and info.* properties | Enable the appropriate data source; keep exposure to only two IDs |
| Health returns 503 | Health status and monitored resources/dependencies | Fix the unhealthy root cause, do not fake a 200 |
| Health leaks details | show-details, show-components, and overriding sources | Restore the minimal-data policy |
| Unlisted endpoint returns 200 | Effective config, profiles, env vars, custom controllers | Find the expansion source or custom route and fix at the source |
| Receives 401/403 | Is Spring Security or a proxy present beyond the sample? | Identify the rejecting layer and required permissions |
| Connection refused | Is the app running, on the right port and network address? | Check listener and process before editing exposure |

A value in `application.yml` can be overridden by an external configuration source. If an experiment behaves unexpectedly, check active profiles, startup arguments, and environment variables such as `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE`, instead of only re-reading the source file.

Adding `include: "*"` is not a default fix for every 404. It changes the lab's requirement without explaining the cause.

If Spring Security is integrated later, “exposed” still does not mean “accessible to everyone.” Keep the endpoint-set tests and add identity/authorization tests under the new contract.

## 9. Single-factor change-and-observe exercises

Apply each change on a local copy, observe the result, and restore the configuration before trying the next scenario.

### Scenario A: Disable the info contributor, keep the info endpoint

Change `management.info.env.enabled` to false, keeping other contributors disabled. Restart.

**Prediction:** `/actuator/info` still exists but returns `{}`. The info data test fails, while the endpoint ID set test can still pass.

**Takeaway:** route availability and content generation are controlled by two different mechanisms.

### Scenario B: Remove info from HTTP

Keep `management.endpoint.info.enabled: true` but remove info from the HTTP include list.

**Prediction:** HTTP requests to info return 404 in the sample. The discovered web endpoint set no longer contains both IDs from the original contract.

**Takeaway:** being enabled is not sufficient to have an HTTP route.

### Scenario C: Add an out-of-contract info field

Add a non-sensitive field `info.app.team: learning`, then run the tests.

**Prediction:** the info response includes the extra team field and the strict JSON test fails.

**Takeaway:** the test suite catches data expansion even when endpoint names do not change. Restore the field after observing.

### Scenario D: Disable only the discovery page

Keep `discovery.enabled: false`, call `/actuator` and then call `/actuator/health`.

**Prediction:** the root path returns 404, while health still works.

**Takeaway:** lacking a links page does not prove no endpoints exist.

### Scenario E: Try opening metrics with an incomplete change

Only add metrics to HTTP include, without changing `enabled-by-default: false` and without enabling metrics individually.

**Prediction:** metrics is still not exposed by the sample configuration. Making it available requires changing both the enablement policy and exposure; that would be a different contract requiring review and re-testing.

**Takeaway:** two selection layers prevent confusing the route list with the endpoint enablement decision.

## 10. Practice completion criteria

The application must start from the specified project structure. With the baseline configuration and healthy machine conditions, health returns the minimal status, info returns exactly the three descriptive fields, unlisted endpoints are not exposed over HTTP, and the Actuator web endpoint ID set equals health/info.

Keep both live checks on the running build and contract tests. One verifies the process and packaged configuration; the other catches future changes that expand the endpoint set or returned data.

When applying this approach to an application with real business logic, redefine health checks and access controls according to operational needs. This lab's small contract is a starting point for intentional decisions, not proof that two endpoints always suffice for every system.
