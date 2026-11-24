# How the Health Endpoint Represents Application Health

## 1. From "process is still running" to "is the application healthy?"

An application can still be listening on an HTTP port while being unable to connect to a data store, unable to send messages, or having actively stopped accepting new work. The fact that the Java process has not exited is not enough to conclude that the application can serve user requests.

Spring Boot Actuator's **Health endpoint** provides a structured representation of application status, based on the registered health checks. With the default path, callers send:

```http
GET /actuator/health
Accept: application/json
```

A minimal response can be:

```json
{"status":"UP"}
```

The correct way to read this is: **according to the checked components and the current aggregation policy, the aggregated status is UP**.

It should not be interpreted as "every business feature works correctly", "every external system is operational", or "the application will definitely handle every subsequent request". Health only knows what its checks actually observe.

This lesson moves from response structure to how statuses are produced and aggregated, and then uses a runnable application to verify it. The example uses **Java 21, Spring Boot 3.3.13, and Spring MVC**. The version is pinned to reproduce 3.3.x behavior; it does not imply this is the latest version or a current production deployment recommendation.

## 2. Three questions for reading a health response

When looking at health, separate three questions:

1. **Which components are being observed?**
2. **What status does each component return, and how are they aggregated?**
3. **Which parts of the response are shown to the caller, and with which HTTP status code?**

You can picture the processing flow as:

```text
Request GET /actuator/health
    -> Find registered health components
    -> Obtain check results at leaf components
    -> Aggregate statuses of branches and the entire tree
    -> Apply component/detail visibility policy
    -> Map health status to HTTP status code
    -> Return JSON response
```

This is a model explaining the core responsibilities, not a guarantee that every check runs concurrently or that every component is measured at the exact same instant.

## 3. status, components, and details have different roles

With Actuator's V3 response format, the key fields are:

| Field | Role when reading |
| --- | --- |
| Root `status` | Aggregated status for the requested scope |
| `components` | Child components, if allowed to be shown |
| `components.<name>.status` | Status of a component |
| `components.<name>.components` | Nested components inside a branch |
| `details` | Explanatory data provided by a component, if allowed to be shown |

Health can represent a nested tree, not just a flat list. The API also allows querying a component or sub-component via its corresponding path. [Actuator 3.3 Health Response Structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

Points to keep in mind:

- `components` describes structure.
- `details` provides supplementary information.
- `status` is the input data for the aggregation decision.

Spring Boot does not infer a status by reading the wording inside `details`. For example, the following API illustration still produces an UP status:

```java
Health.up()
        .withDetail("queueAvailable", false)
        .build();
```

This is an illustrative expression inside code using the `Health` API, not a standalone Java program. If a check condition fails, the check author must return the appropriate status rather than merely recording a detail whose wording implies an error.

The absence of `components` or `details` in JSON also does not prove that the application has no child checks. Those fields may have been hidden by the visibility policy.

## 4. Who produces health information?

### 4.1. HealthIndicator produces a result at a leaf component

`HealthIndicator` is the interface for a health check in the Servlet model used in this lesson. Its `health()` method returns `Health`, consisting of a status and optionally explanatory details. This interface is also a functional interface, so it can be implemented with a lambda. [HealthIndicator 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

A real check might verify a condition necessary for serving traffic, such as the ability to obtain a database connection or available disk space remaining above a chosen threshold.

Signal quality depends on the check condition:

- Merely verifying that a configuration object exists does not prove a remote service is still usable.
- A successful connection operation does not prove all business queries will succeed.
- Checks that are too broad, too slow, or mutate data can cause additional problems when the system is already degraded.

Health is the result of a scoped check, not a blanket guarantee.

### 4.2. HealthContributor represents a leaf or branch component

`HealthContributor` is the overarching concept:

- A `HealthIndicator` provides a result at a leaf.
- A `CompositeHealthContributor` groups multiple child components into a branch.

`CompositeHealthContributor.fromMap(...)` can create a branch from a map of component names to contributors. [CompositeHealthContributor 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

This allows modeling:

```text
Overall application health
├── heartbeat
└── orderFlow
    ├── storage
    └── queue
```

In this tree, `orderFlow` has a status aggregated from its two children. The root status further aggregates from `heartbeat` and `orderFlow`.

The actual component list depends on the registered contributors. Spring Boot provides auto-configured checks when appropriate library/configuration conditions are met; it does not automatically discover all business dependencies from application source code alone.

## 5. Meaning of statuses and how aggregation works

### 5.1. Common statuses

| Status | Platform-level interpretation |
| --- | --- |
| `UP` | Component meets the health condition defined by the check |
| `DOWN` | Check determined that the component has a problem |
| `OUT_OF_SERVICE` | Component is currently considered out of service |
| `UNKNOWN` | Status cannot be determined under the current result or policy |

The application decides which conditions lead to each status. The framework does not automatically know whether a maintenance window is OUT_OF_SERVICE without a component providing that information.

`Health.up()`, `Health.down()`, `Health.outOfService()`, `Health.unknown()`, and `Health.status(...)` are the ways to construct results using the API. [Health 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

### 5.2. Priority-based aggregation, not voting

With Spring Boot 3.3.13's default `SimpleStatusAggregator`, the priority order is:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

Among recognized statuses, the one appearing earliest in the list determines the aggregated result. [SimpleStatusAggregator 3.3.13 Source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Examples:

| Child statuses | Default aggregated result |
| --- | --- |
| UP, UP | UP |
| DOWN, UP, UP | DOWN |
| OUT_OF_SERVICE, UP | OUT_OF_SERVICE |
| DOWN, OUT_OF_SERVICE | DOWN |
| UNKNOWN, UP | UP |
| UNKNOWN | UNKNOWN |

One DOWN component is not "outvoted" by many UP components. This is not a vote ratio, an average score, or bean declaration order.

The case **UNKNOWN with UP yielding UP** is especially noteworthy. UNKNOWN is not inherently more severe than UP in this default policy. Therefore, seeing UP at the root alone is not enough to conclude that every leaf returned UP.

If a different policy is needed, you can configure the order or replace the aggregator. When doing so, responses must be read according to the new policy instead of mechanically applying the default table.

### 5.3. Custom statuses need a corresponding policy

A contributor can produce a custom code such as `DEGRADED`, but a severe-sounding name does not automatically place it ahead of UP.

If the default aggregator does not yet recognize that code, it does not become a new priority level simply by appearing in a result. When none of the statuses belong to the recognized list, the aggregated result is UNKNOWN.

Adding a new health code therefore requires considering both the aggregation policy and HTTP mapping. These two have distinct responsibilities.

## 6. Health status is distinct from HTTP status code

A health object does not inherently carry a mandatory HTTP status code. When accessed over the web, `HttpCodeStatusMapper` maps the health status to a response code; `SimpleHttpCodeStatusMapper` provides the default mapping. [HTTP Status Mapping 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

Under Spring Boot 3.3's default configuration:

| Status of queried scope | HTTP code |
| --- | --- |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UP | 200 |
| UNKNOWN | 200 |
| Other unmapped custom code | 200 |

Consequently:

- HTTP 503 with JSON `{"status":"DOWN"}` can be an actively returned health result; it does not mean the HTTP handler has crashed.
- HTTP 200 can accompany UNKNOWN, not only UP.
- Getting no response or failing to connect is a different situation from receiving a health response reporting DOWN.

A monitoring system must know whether it is evaluating the HTTP code, the status body, or both. Do not infer the entire health policy from a single HTTP number alone.

Customizing the HTTP mapping can change this table. When adding mappings in Spring Boot 3.3 configuration, you must re-declare the DOWN and OUT_OF_SERVICE mappings if you want to keep them; do not assume they are always preserved alongside custom configuration.

## 7. Visibility level does not alter check results

Two related properties:

```properties
management.endpoint.health.show-components=never
management.endpoint.health.show-details=never
```

- `show-components` controls showing the component tree.
- `show-details` controls showing explanatory data.
- Options include `never`, `when-authorized`, and `always`.

In the default configuration, the response usually shows only the aggregated status. You can allow authorized callers to see more information, but that is a data display decision, not a decision about whether a dependency is healthy. [Actuator 3.3 Health Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

For example, if a component is still DOWN, hiding it from the JSON does not turn the root status into UP. The response may simply be:

```json
{"status":"DOWN"}
```

The default HTTP code is still 503.

Details can contain file paths, resource names, error messages, or internal structure. Therefore, only enable detail visibility based on need and appropriate access permissions. Visibility policy does not replace network-layer endpoint protection and authentication/authorization.

## 8. Hands-on project: seeing the tree and status changes

The following example simulates a tree with two root components, `heartbeat` and `orderFlow`; the `orderFlow` branch contains `storage` and `queue`. All checks are **in-memory simulations**, not verifying a real database or queue.

We vary the status of `storage` using the `demo.storage-status` property to observe the representation and aggregation policy. We do not add a state-mutating endpoint and do not pretend that a real dependency has been checked.

Project structure:

```text
health-representation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/healthview/
    │   │   ├── HealthViewApplication.java
    │   │   └── DemoHealthConfiguration.java
    │   └── resources/application.yml
    └── test/java/com/example/healthview/
        └── HealthEndpointRepresentationTest.java
```

Use Maven with JDK 21; the first build needs to download libraries from the Maven repository. This is a Spring Boot project, not standalone files that can be run individually with `javac ClassName.java`.

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>health-representation-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 8.2. src/main/resources/application.yml

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-components: always
      show-details: always
  health:
    defaults:
      enabled: false

demo:
  storage-status: UP
```

Two choices specific to this lab:

- `show-components=always` and `show-details=always` make it possible to observe the full tree along with simulated data.
- `management.health.defaults.enabled=false` disables the default auto-configured checks so the example tree does not vary depending on the host machine environment. Our explicitly declared contributors are still used.

Do not copy disabling default checks to a real application without evaluating requirements. In a real environment, those checks may provide essential signals.

The application only listens on the loopback address `127.0.0.1` and only exposes health over HTTP. The project does not add Spring Security; publicly showing details in the example is solely to observe simulated data on a personal machine.

### 8.3. HealthViewApplication.java

Place at `src/main/java/com/example/healthview/HealthViewApplication.java`.

```java
package com.example.healthview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthViewApplication.class, args);
    }
}
```

### 8.4. DemoHealthConfiguration.java

Place at `src/main/java/com/example/healthview/DemoHealthConfiguration.java`.

```java
package com.example.healthview;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoHealthConfiguration {
    @Bean
    HealthIndicator heartbeatHealthIndicator() {
        return () -> Health.up()
                .withDetail("check", "simulated")
                .build();
    }

    @Bean(name = "orderFlow")
    CompositeHealthContributor orderFlow(
            @Value("${demo.storage-status}") String storageStatus) {
        HealthIndicator storage = () -> Health.status(storageStatus)
                .withDetail("check", "simulated")
                .build();
        HealthIndicator queue = () -> Health.up()
                .withDetail("check", "simulated")
                .build();

        Map<String, HealthContributor> children = new LinkedHashMap<>();
        children.put("storage", storage);
        children.put("queue", queue);
        return CompositeHealthContributor.fromMap(children);
    }
}
```

How to map the code to the response:

| In code | In the health tree |
| --- | --- |
| Bean `heartbeatHealthIndicator` | Component `heartbeat` |
| Bean explicitly named `orderFlow` | Branch `orderFlow` |
| Key `storage` in child map | Component `orderFlow/storage` |
| Key `queue` in child map | Component `orderFlow/queue` |
| `withDetail("check", "simulated")` | Data `details.check` at leaf |

The name of a HealthIndicator is derived from the bean name, stripping the `HealthIndicator` suffix if present. In the example, the bean `heartbeatHealthIndicator` therefore appears under the name `heartbeat`.

The functions here only return simulated results. In particular, the name `storage` does not make Spring automatically connect to a real storage system. To check a real dependency, the indicator author must choose and execute an appropriate check.

## 9. Observing results and explaining causes

### 9.1. All simulated components are UP

In the directory containing `pom.xml`, open PowerShell with `JAVA_HOME` pointing to JDK 21:

```powershell
mvn spring-boot:run
```

From a second terminal:

```powershell
curl.exe -s -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

The HTTP status code is 200. The JSON body has content equivalent to the following; field ordering and line breaks are not part of a contract to rely on:

```json
{
  "status": "UP",
  "components": {
    "heartbeat": {
      "status": "UP",
      "details": {
        "check": "simulated"
      }
    },
    "orderFlow": {
      "status": "UP",
      "components": {
        "storage": {
          "status": "UP",
          "details": {
            "check": "simulated"
          }
        },
        "queue": {
          "status": "UP",
          "details": {
            "check": "simulated"
          }
        }
      }
    }
  }
}
```

Reading bottom-up:

1. `storage` and `queue` are both UP, so `orderFlow` is UP.
2. `orderFlow` and `heartbeat` are both UP, so the root is UP.
3. The root status UP is mapped to HTTP 200.

Do not use `details.check` alone to evaluate status. It is merely a reminder that the data is simulated.

### 9.2. A DOWN leaf pulls its branch and root down to DOWN

Stop the application with Ctrl+C, then run again:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=DOWN"
```

Query health again. The parts that change are:

```text
components.orderFlow.components.storage.status = DOWN
components.orderFlow.status = DOWN
status = DOWN
HTTP = 503
```

`heartbeat` and `queue` remain UP, but they do not cancel out the DOWN status of `storage`.

HTTP 503 here proves the application is still able to handle the health request and is reporting an unhealthy status. It does not mean the JVM has stopped running.

### 9.3. Querying a branch or a leaf

During the run with `storage=DOWN`:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/heartbeat
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/orderFlow
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/orderFlow/storage
```

Results in order:

```text
503
200
503
503
```

Different paths query different scopes, so HTTP status codes can differ at the same point in time.

Inspecting the leaf alone:

```powershell
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health/orderFlow/storage
```

Equivalent JSON content:

```json
{
  "status": "DOWN",
  "details": {
    "check": "simulated"
  }
}
```

This is the result of the queried leaf, not the entire tree wrapped around it. Component paths only work when the contributor exists and the visibility/access policy allows it; do not assume everyone is allowed to view every sub-path.

With the current local configuration, `/actuator/health/notRegistered` returns 404 because no such contributor exists. This is a different situation from a contributor having an UNKNOWN status.

### 9.4. UNKNOWN at a leaf does not necessarily make the root UNKNOWN

Stop and restart the application:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=UNKNOWN"
```

Predict and verify:

| Scope | Status | Default HTTP |
| --- | --- | --- |
| `storage` | UNKNOWN | 200 |
| `orderFlow`, with storage UNKNOWN and queue UP | UP | 200 |
| Root, with heartbeat UP and orderFlow UP | UP | 200 |

If an important condition cannot be checked, the designer must consider the appropriate status and policy. Do not pick UNKNOWN just because the word sounds "safer than DOWN" and expect it to block traffic automatically.

### 9.5. Hiding the tree only changes representation

Stop and restart:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=DOWN --management.endpoint.health.show-components=never --management.endpoint.health.show-details=never"
```

Querying root health still returns HTTP 503, but the JSON is only:

```json
{"status":"DOWN"}
```

If you only want to show the structure without showing details, keep `show-components=always` and set `show-details=never`. Then the child statuses still appear, while `details.check` is not returned.

Each launch command in the sections above replaces the previous run; do not run multiple applications simultaneously on port 8080.

## 10. Tests to verify the representation behavior

Place the following file at `src/test/java/com/example/healthview/HealthEndpointRepresentationTest.java`.

The test creates a Spring context for each configuration and uses MockMvc to invoke the HTTP handling layer inside the application. No real network port needs to be opened. The test suite verifies JSON structure, status aggregation, HTTP status codes, information hiding, and the missing contributor case.

```java
package com.example.healthview;

import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class HealthEndpointRepresentationTest {
    private final ObjectMapper json = new ObjectMapper();

    private WebApplicationContextRunner application(String... properties) {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(HealthViewApplication.class)
                .withPropertyValues(properties);
    }

    @ParameterizedTest
    @CsvSource({
            "UP, UP, 200",
            "DOWN, DOWN, 503",
            "OUT_OF_SERVICE, OUT_OF_SERVICE, 503",
            "UNKNOWN, UP, 200"
    })
    void treeAndHttpStatusFollowAggregation(
            String storageStatus, String overallStatus, int httpStatus) {
        application("demo.storage-status=" + storageStatus).run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();

            var root = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(root.getStatus()).isEqualTo(httpStatus);
            JsonNode body = json.readTree(root.getContentAsString());
            assertThat(body.path("status").asText()).isEqualTo(overallStatus);
            assertThat(body.path("components").size()).isEqualTo(2);
            assertThat(body.at("/components/heartbeat/status").asText())
                    .isEqualTo("UP");
            assertThat(body.at("/components/orderFlow/status").asText())
                    .isEqualTo(overallStatus);
            assertThat(body.at("/components/orderFlow/components/storage/status")
                    .asText()).isEqualTo(storageStatus);
            assertThat(body.at("/components/orderFlow/components/queue/status")
                    .asText()).isEqualTo("UP");

            var leaf = mvc.perform(get("/actuator/health/orderFlow/storage"))
                    .andReturn().getResponse();
            assertThat(leaf.getStatus()).isEqualTo(
                    new SimpleHttpCodeStatusMapper()
                            .getStatusCode(new Status(storageStatus)));
            assertThat(json.readTree(leaf.getContentAsString())
                    .path("status").asText()).isEqualTo(storageStatus);
        });
    }

    @Test
    void hidingRepresentationDoesNotTurnDownIntoUp() {
        application(
                "demo.storage-status=DOWN",
                "management.endpoint.health.show-components=never",
                "management.endpoint.health.show-details=never").run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            var response = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(response.getStatus()).isEqualTo(503);
            JsonNode body = json.readTree(response.getContentAsString());
            assertThat(body.size()).isEqualTo(1);
            assertThat(body.path("status").asText()).isEqualTo("DOWN");
        });
    }

    @Test
    void componentTreeCanBeVisibleWithoutDetails() {
        application("management.endpoint.health.show-details=never")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .build();
                    var response = mvc.perform(get("/actuator/health"))
                            .andReturn().getResponse();
                    assertThat(response.getStatus()).isEqualTo(200);
                    JsonNode body = json.readTree(response.getContentAsString());
                    assertThat(body.has("components")).isTrue();
                    assertThat(body.at("/components/heartbeat")
                            .has("details")).isFalse();
                    assertThat(body.at("/components/orderFlow/components/storage")
                            .has("details")).isFalse();
                });
    }

    @Test
    void missingContributorIsNotUnknownHealth() {
        application().run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            assertThat(mvc.perform(get("/actuator/health/notRegistered"))
                    .andReturn().getResponse().getStatus()).isEqualTo(404);
        });
    }

    @Test
    void aggregatorHasKnownOrderAndUnknownFallback() {
        var aggregator = new SimpleStatusAggregator();
        assertThat(aggregator.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)))
                .isEqualTo(Status.UP);
        assertThat(aggregator.getAggregateStatus(Set.of(Status.UNKNOWN)))
                .isEqualTo(Status.UNKNOWN);
        assertThat(aggregator.getAggregateStatus(Set.of(
                Status.UP, new Status("DEGRADED")))).isEqualTo(Status.UP);
    }

    @Test
    void healthStatusIsMappedSeparatelyToHttp() {
        var mapper = new SimpleHttpCodeStatusMapper();
        assertThat(mapper.getStatusCode(Status.DOWN)).isEqualTo(503);
        assertThat(mapper.getStatusCode(Status.OUT_OF_SERVICE)).isEqualTo(503);
        assertThat(mapper.getStatusCode(Status.UP)).isEqualTo(200);
        assertThat(mapper.getStatusCode(Status.UNKNOWN)).isEqualTo(200);
        assertThat(mapper.getStatusCode(new Status("DEGRADED"))).isEqualTo(200);
    }
}
```

In the directory containing `pom.xml`:

```powershell
mvn test
```

The success output should contain:

```text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

The four parameter sets of the first test plus the remaining five tests make nine cases. Startup logs and execution times may vary.

Conclusions verified:

- DOWN and OUT_OF_SERVICE at a leaf affect its branch and root according to the default order.
- UNKNOWN at a leaf can coexist with UP at the root.
- A leaf's status and the root's status are two different scopes.
- Hiding the tree and details does not change DOWN into UP.
- Component statuses can be shown without showing detail data.
- Having no contributor at a path is not the same as a contributor reporting UNKNOWN.
- Status aggregation and HTTP mapping are two separate mechanisms.
- A custom code not yet included in the policy does not automatically gain a priority or an error HTTP code.

MockMvc tests do not prove that ports, network routes, TLS, or external monitoring tools are configured correctly. They prove representation behavior inside the application under the stated conditions.

## 11. What can health answer in operations?

### 11.1. A scoped, point-in-time result

A health response reflects the results of the checks obtained for that request. Components may be checked sequentially; a dependency can also change state immediately after being checked.

Therefore, do not treat the entire tree as an atomic transactional snapshot of every system. Freshness also depends on how checks are written and whether result caching is configured.

The health endpoint also does not become a historical store on its own. If you need to know how long a dependency has been DOWN or how flaky it has been, an appropriate time-series observability mechanism is needed.

### 11.2. Health signals do not replace other signals

| Operational question | Signal to use |
| --- | --- |
| Are the selected health conditions currently met? | Health |
| How are latency, throughput, or error rate changing over time? | Monitoring metrics |
| Which events or errors occurred? | Logs and appropriate execution traces |
| Does a specific business workflow execute correctly end-to-end? | Tests or synthetic checks suited to the workflow |

An UP health status does not refute a rising business error rate. Conversely, DOWN on a dependency must be read according to the check's scope to decide how to react.

In particular, do not equate the question "does the process need to be restarted?" with the question "are all dependencies currently usable?". A failing remote dependency is not automatically fixed by restarting the entire application.

### 11.3. Adding checks for meaningful needs

Before adding a real indicator, answer:

1. Which condition is being checked?
2. How does that condition relate to the ability to serve traffic?
3. Does the check have an appropriate timeout and cost?
4. If the condition cannot be determined, which status should be returned?
5. How will that status be aggregated and mapped to HTTP?
6. Which details are needed for diagnosis, and who is allowed to see them?

Do not add an always-UP check just to make the tree have more components. Simulated checks in this lesson only help understand the mechanics; an operational check must provide real signal.

## 12. Common reading and design mistakes

| Misconception or wrong choice | What to fix |
| --- | --- |
| Seeing an open HTTP port and assuming all features are healthy | Distinguish a running process from the serving conditions actually checked |
| Seeing UP at the root and assuming every leaf is UP | Check contributor scope and aggregation policy, especially with UNKNOWN |
| Assuming many UPs will override one DOWN | Default aggregation uses priority order, not voting |
| Assuming UNKNOWN is always more severe than UP | Check the actual order; 3.3.13 default places UP before UNKNOWN |
| Adding DEGRADED and expecting it to make HTTP 503 automatically | Design both aggregation and HTTP mapping for the new code |
| Putting an error string in details while still returning UP | Status must reflect the check condition; the framework does not read wording to infer failure |
| Treating missing components as having no contributors | The tree may have been hidden by the visibility policy |
| Hiding a component and thinking it no longer participates in aggregation | Data visibility and status calculation are separate responsibilities |
| Treating health HTTP 503 as proof the JVM has died | The application may be actively returning DOWN or OUT_OF_SERVICE |
| Treating every HTTP 200 as status UP | UNKNOWN and unmapped custom codes can also return 200 |
| Treating 404 on a sub-path as status UNKNOWN | Distinguish no contributor resource from a resource with an undetermined result |
| Using slow checks or checks that mutate business state | Choose checks with appropriate cost and avoid side effects |
| Exposing all details for convenient debugging | Limit information based on need and access permissions |
| Disabling default checks because the example disabled them | The lesson config creates a deterministic tree; real applications need to evaluate each signal |

## 13. Self-check on the mental model

With the default order:

```text
Application
├── A: UP
└── B
    ├── B1: OUT_OF_SERVICE
    └── B2: UNKNOWN
```

Predict before checking the answers:

1. What is the status of B?
2. What is the root status?
3. What is the HTTP status when querying the root?
4. If components and details are hidden, does the root status change?
5. If querying B2 alone, what are its status and default HTTP code?

Answers:

| Question | Result | Reason |
| --- | --- | --- |
| Status of B | OUT_OF_SERVICE | OUT_OF_SERVICE precedes UNKNOWN |
| Root status | OUT_OF_SERVICE | OUT_OF_SERVICE precedes UP |
| Root HTTP | 503 | Default mapping for OUT_OF_SERVICE |
| When hiding tree/details | Still OUT_OF_SERVICE and HTTP 503 | Only changes representation |
| Querying B2 alone | UNKNOWN, HTTP 200 | Scope is leaf B2 and uses default mapping |

Then change B1 to UP. Then B aggregates to UP, and the root also becomes UP, even though B2 is still UNKNOWN.

Learners should be able to explain each result using three layers: contributors provide statuses, the aggregator determines the status of the queried scope, and the web layer determines the representation and HTTP status code. That is the foundation for reading health accurately before designing more complex check policies.
