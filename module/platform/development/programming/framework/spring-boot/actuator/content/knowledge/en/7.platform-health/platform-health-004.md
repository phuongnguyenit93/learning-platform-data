# Meanings of UP, DOWN, OUT_OF_SERVICE, and UNKNOWN

## 1. Four statuses answer different questions

When reading `/actuator/health`, we often see a short code like `UP` or `DOWN`. However, application health is not just two possibilities: "still running" and "dead".

We need to distinguish:

- The check condition is being met as expected.
- The check has identified a failure.
- The component has been taken out of service and should not be used.
- The component's state has not been determined.

Spring Boot uses the corresponding standard statuses:

| Status | Core meaning | Question to help choose |
| --- | --- | --- |
| `UP` | Component is operating as expected per the checked condition | Is there evidence that the required condition is met? |
| `DOWN` | Component encountered an unexpected failure | Has the check determined that the required condition failed? |
| `OUT_OF_SERVICE` | Component has been taken out of service and should not be used | Even though the process is running, is the component excluded from serving? |
| `UNKNOWN` | Status has not been determined | Is there enough information to conclude the current state? |

These are the semantics of the standard constants of the `Status` class. [Spring Boot 3.3 Status API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html).

Status must be read according to the **scope of the check**. An UP component does not prove all business flows are working; a DOWN component does not prove the JVM has stopped running.

This lesson uses **Java 21, Spring Boot 3.3.13, and Spring MVC** to produce reproducible results. The version is pinned for the 3.3.x series example, without implying this is the latest version or a current production deployment recommendation.

## 2. Understanding each status accurately

### 2.1. UP: the condition being checked is met

A check may return UP when a test connection succeeds, capacity remains above a threshold, or an internal condition is ready.

The next question to ask is **what was checked**. For example, obtaining a database connection does not prove:

- every query executes correctly;
- business data is always valid;
- the application has enough capacity to handle upcoming traffic;
- services outside the check are also healthy.

UP is a positive result within the defined scope. Do not return UP simply because the check code is unfinished or to make alerts disappear.

### 2.2. DOWN: a failure condition has been determined

Suppose a check's contract is "can connect to the required dependency within the time limit". If that operation fails, returning DOWN can be the appropriate choice.

DOWN speaks about the **health check result**, not directly about process lifecycle. The application can still receive a health request, run checks, and return:

```json
{"status":"DOWN"}
```

In that case, receiving the response itself shows the health handling path is still functional enough to report the result. You must find the cause of the failure condition rather than merely concluding "Java is dead".

Nor should you automatically conclude that every DOWN is fixed by restarting the application. A remote dependency that is down is not recovered just by restarting the caller.

### 2.3. OUT_OF_SERVICE: this component should not be used to serve traffic

OUT_OF_SERVICE represents that a component is out of service. A common design scenario is actively stopping acceptance of new work during a maintenance window or a state transition phase.

The difference from DOWN lies in the **signal meaning**:

| Illustrative situation | Suitable status to consider |
| --- | --- |
| A critical check just detected an unexpected failure | DOWN |
| Component is actively taken out of service per operational policy | OUT_OF_SERVICE |

This is not a rule that only maintenance can use OUT_OF_SERVICE. The core meaning is that the component should not be used to serve traffic; specific conditions are decided by the system's design.

Constructing `Health.outOfService()` **only produces a health report**. It does not automatically close HTTP ports, drop all connections, stop accepting tasks, or make a load balancer redirect traffic. Those behaviors require separate mechanisms reading and enforcing the appropriate policy.

Spring Boot also has an application availability model for accepting traffic and a dedicated indicator for readiness state. Do not equate every health report with the entire traffic-control mechanism. [Application Availability Model](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability), [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html).

### 2.4. UNKNOWN: insufficient basis to determine state

UNKNOWN is a meaningful health result, not a missing value in JSON. For example, a check that does not yet have a result may be designed to return UNKNOWN.

Three cases must be distinguished:

| Observation | What can be concluded |
| --- | --- |
| Response has `status=UNKNOWN` | The component returned an undetermined status |
| No component at the queried path | No such contributor resource exists to return a result |
| Unable to connect to the application | No health response received to know the status |

Do not use UNKNOWN as a way to soften every error. If the check contract already defines a failed connection as a health failure, catching the error and always returning UNKNOWN hides that meaning.

For a timeout, clearly define the check contract: is timing out a failure condition, or does the measurement truly not allow a conclusion yet? Do not choose a status based solely on an exception's name or a desire to avoid alerts.

## 3. Leaf status and aggregated status are not the same

An indicator returns a status for its component. When multiple components participate together, the aggregator determines the status for the entire queried scope.

With the default `SimpleStatusAggregator` in Spring Boot 3.3.13, the priority order is:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

The recognized status appearing earliest in the list determines the result. [Default aggregation in version 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

| Component statuses | Default aggregated status |
| --- | --- |
| UP and UP | UP |
| DOWN and UP | DOWN |
| OUT_OF_SERVICE and UP | OUT_OF_SERVICE |
| DOWN and OUT_OF_SERVICE | DOWN |
| UNKNOWN and UP | UP |
| UNKNOWN and OUT_OF_SERVICE | OUT_OF_SERVICE |
| Only UNKNOWN | UNKNOWN |

Implications to understand:

- DOWN is not "outvoted" by many UPs.
- OUT_OF_SERVICE and DOWN still have distinct meanings even though both may render the root unserviceable.
- UNKNOWN does not rank above UP in the default order.
- An UP root status can coexist with an UNKNOWN component.

If you want UNKNOWN to outweigh UP, you must actively change the policy, not just change the verbal explanation. In the hands-on section, we will verify both the default order and a custom order.

## 4. Status meaning is not HTTP code meaning

In Spring Boot 3.3's default HTTP mapping:

| Health status of queried scope | Default HTTP |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

DOWN and OUT_OF_SERVICE share the same default HTTP code yet carry different operational information. Conversely, UP and UNKNOWN can both return 200, yet do not represent the same level of knowledge about component state. [Mapping health status to HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-healthindicators).

There are three independent decisions:

```text
Observed condition
    -> Indicator selects status
    -> Aggregator selects group/overall status
    -> Mapper selects HTTP code
```

Changing priority order so the root becomes UNKNOWN does not automatically change HTTP to 503. Nor should health HTTP 503 be interpreted as an HTTP handling exception or a stopped process.

In addition, 401/403 from access control, 404 from resource not found, or network connection errors are separate situations. You must read the HTTP code together with the response body and request context.

## 5. Representation in Java and JSON

In Java, `Status` is a value class, not an `enum` with strictly four elements. Standard constants help express common cases; the API also allows custom status codes.

Common ways to construct results:

```java
Health.up().build();
Health.down().build();
Health.outOfService().build();
Health.unknown().build();
```

These are illustrative expressions inside code using the `Health` API, not a standalone Java program.

When returned via the endpoint, a code like `OUT_OF_SERVICE` appears in the JSON `status` field. Accompanying `details` only adds explanatory information; it does not replace the status itself.

Do not use an `ordinal()`-style index to compare severity levels. Priority is governed by the aggregator, not by the declaration order of constants in the class.

If creating a custom code, define its semantics, aggregation order, and corresponding HTTP mapping. This lesson focuses on the four standard statuses to build a consistent way of reading them.

## 6. Runnable example: distinguishing dependency failure from work admission policy

The project has two independent **simulated** checks:

- `dependency`: simulated dependency check result is PASS, FAIL, or NOT_RUN.
- `admission`: reported state of work-admission policy is true or false.

Rules designed by this lesson:

| Simulated input | Indicator status |
| --- | --- |
| dependency PASS | UP |
| dependency FAIL | DOWN |
| dependency NOT_RUN | UNKNOWN |
| admission true | UP |
| admission false | OUT_OF_SERVICE |

PASS/FAIL/NOT_RUN are example-specific input values, not Spring Boot standard health codes.

There is no real database check and no real admission-control gate in the project. The goal is to observe the exact semantics and combinations of the four statuses without needing an external outage.

Structure:

```text
standard-health-status-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/statuslab/
    │   │   ├── StatusLabApplication.java
    │   │   └── DemoStatusIndicators.java
    │   └── resources/application.yml
    └── test/java/com/example/statuslab/
        └── StandardHealthStatusesTest.java
```

Use Maven with JDK 21; the first build needs to download libraries from the Maven repository. The classes require Spring Boot, so they cannot be run individually with `javac ClassName.java`.

### 6.1. pom.xml

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
    <artifactId>standard-health-status-lab</artifactId>
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

### 6.2. src/main/resources/application.yml

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
  probe-result: PASS
  accepting-work: true
```

The application only listens on `127.0.0.1` and only exposes health over HTTP. There is no Spring Security in this local project.

Two settings specific to learning:

- Show both components and details to compare each status.
- Disable default auto-configured checks so the response only contains the two simulated checks, independent of the host machine's disk or libraries.

Do not use disabling default checks as a general operational configuration. In a real application, you must choose valuable checks and restrict viewing permission for detail data.

### 6.3. StatusLabApplication.java

Place at `src/main/java/com/example/statuslab/StatusLabApplication.java`.

```java
package com.example.statuslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatusLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(StatusLabApplication.class, args);
    }
}
```

### 6.4. DemoStatusIndicators.java

Place at `src/main/java/com/example/statuslab/DemoStatusIndicators.java`.

```java
package com.example.statuslab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoStatusIndicators {
    public enum ProbeResult {
        PASS, FAIL, NOT_RUN
    }

    @Bean
    HealthIndicator dependencyHealthIndicator(
            @Value("${demo.probe-result}") ProbeResult result) {
        return () -> {
            Health.Builder builder = switch (result) {
                case PASS -> Health.up();
                case FAIL -> Health.down();
                case NOT_RUN -> Health.unknown();
            };
            return builder.withDetail("probeResult", result.name()).build();
        };
    }

    @Bean
    HealthIndicator admissionHealthIndicator(
            @Value("${demo.accepting-work}") boolean acceptingWork) {
        return () -> (acceptingWork ? Health.up() : Health.outOfService())
                .withDetail("acceptingWork", acceptingWork)
                .build();
    }
}
```

The two beans appear in JSON under the names `dependency` and `admission`: bean names have the `HealthIndicator` suffix stripped.

`ProbeResult` is an enum defined by the lesson to simulate input. It does not make Spring Boot's `Status` class an enum.

`details.probeResult` helps identify which input led to the result. `details.acceptingWork` explains the reported status of admission. These two fields do not cause service cessation on their own; the Java code itself chooses UP or OUT_OF_SERVICE.

## 7. Running and reading the four statuses in concrete scenarios

### 7.1. Initial state

In the directory containing `pom.xml`, use PowerShell with `JAVA_HOME` pointing to JDK 21:

```powershell
mvn spring-boot:run
```

From a second terminal:

```powershell
curl.exe -s -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

The HTTP status code is 200. Equivalent JSON content:

```json
{
  "status": "UP",
  "components": {
    "dependency": {
      "status": "UP",
      "details": {
        "probeResult": "PASS"
      }
    },
    "admission": {
      "status": "UP",
      "details": {
        "acceptingWork": true
      }
    }
  }
}
```

Do not rely on JSON field ordering or line breaks. What matters is comparing the status of each component and of the root.

### 7.2. FAIL leads to DOWN

Stop the application with Ctrl+C, then run again:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=FAIL"
```

Results:

| Scope | Status | Default HTTP |
| --- | --- | --- |
| dependency | DOWN | 503 |
| admission | UP | 200 |
| Root | DOWN | 503 |

Here, one check determined a failure. The other UP component does not erase the DOWN result.

### 7.3. Actively refusing work leads to OUT_OF_SERVICE

Stop and restart:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=PASS --demo.accepting-work=false"
```

Results:

| Scope | Status | Default HTTP |
| --- | --- | --- |
| dependency | UP | 200 |
| admission | OUT_OF_SERVICE | 503 |
| Root | OUT_OF_SERVICE | 503 |

Query each scope individually:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/dependency
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/admission
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
```

Results in order:

```text
200
503
503
```

The admission response has content equivalent to:

```json
{
  "status": "OUT_OF_SERVICE",
  "details": {
    "acceptingWork": false
  }
}
```

The application can still return health. In this example, the `accepting-work` flag is only read by the indicator for reporting; there is no code controlling a real task acceptor or load balancer.

### 7.4. Check not yet run leads to UNKNOWN

Stop and restart:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=NOT_RUN --demo.accepting-work=true"
```

Call:

```powershell
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health/dependency
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

At the dependency leaf:

```json
{
  "status": "UNKNOWN",
  "details": {
    "probeResult": "NOT_RUN"
  }
}
```

The leaf's HTTP code is still 200. At the root, the status is UP because admission UP precedes UNKNOWN in the default order.

This does not prove the dependency check succeeded. It proves **UNKNOWN was aggregated according to the default policy**.

If `accepting-work=false` is set at the same time, admission will be OUT_OF_SERVICE and the root status becomes OUT_OF_SERVICE.

### 7.5. Failure and out-of-service occurring together

Stop and restart:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=FAIL --demo.accepting-work=false"
```

Dependency is DOWN, admission is OUT_OF_SERVICE, and the root status is DOWN. Both signals are still preserved at the components; the root chooses DOWN due to default priority.

If you only view the root, you do not see all child conditions occurring simultaneously. When authorized to view them, components and details help distinguish causes. [Health API Root Scope and Component Scope](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 7.6. Placing UNKNOWN before UP is a policy change

You can try a different order:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=NOT_RUN --management.endpoint.health.status.order=down,out-of-service,unknown,up"
```

The root is now UNKNOWN instead of UP, yet HTTP is still 200 because the mapping for UNKNOWN has not been changed.

If a system needs to treat undetermined status as unfit to serve, it must thoroughly design and verify the aggregation policy, HTTP codes, and consumer reactions. Do not just change the order and assume every remaining layer automatically understands the same meaning.

All launch commands in the sections above are mutually exclusive runs. Stop the old session before reusing port 8080.

## 8. Testing semantics via observable results

Place the following file at `src/test/java/com/example/statuslab/StandardHealthStatusesTest.java`.

The test uses `WebApplicationContextRunner` to create a context for each input set and loads `application.yml`. MockMvc invokes Spring MVC's HTTP handling without opening a real network port.

```java
package com.example.statuslab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class StandardHealthStatusesTest {
    private final ObjectMapper json = new ObjectMapper();

    private WebApplicationContextRunner application(String... properties) {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(StatusLabApplication.class)
                .withPropertyValues(properties);
    }

    @ParameterizedTest
    @CsvSource({
            "PASS, true, UP, UP, 200",
            "FAIL, true, DOWN, DOWN, 503",
            "NOT_RUN, true, UNKNOWN, UP, 200",
            "PASS, false, UP, OUT_OF_SERVICE, 503",
            "FAIL, false, DOWN, DOWN, 503",
            "NOT_RUN, false, UNKNOWN, OUT_OF_SERVICE, 503"
    })
    void standardStatusesRemainDistinct(
            String probeResult, boolean acceptingWork, String dependencyStatus,
            String overallStatus, int overallHttp) {
        application(
                "demo.probe-result=" + probeResult,
                "demo.accepting-work=" + acceptingWork).run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();

            var root = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(root.getStatus()).isEqualTo(overallHttp);
            JsonNode body = json.readTree(root.getContentAsString());
            assertThat(body.path("status").asText()).isEqualTo(overallStatus);
            assertThat(body.at("/components/dependency/status").asText())
                    .isEqualTo(dependencyStatus);
            assertThat(body.at("/components/admission/status").asText())
                    .isEqualTo(acceptingWork ? "UP" : "OUT_OF_SERVICE");

            var dependency = mvc.perform(get("/actuator/health/dependency"))
                    .andReturn().getResponse();
            assertThat(dependency.getStatus())
                    .isEqualTo(dependencyStatus.equals("DOWN") ? 503 : 200);
            JsonNode dependencyBody = json.readTree(
                    dependency.getContentAsString());
            assertThat(dependencyBody.path("status").asText())
                    .isEqualTo(dependencyStatus);
            assertThat(dependencyBody.at("/details/probeResult").asText())
                    .isEqualTo(probeResult);

            var admission = mvc.perform(get("/actuator/health/admission"))
                    .andReturn().getResponse();
            assertThat(admission.getStatus()).isEqualTo(acceptingWork ? 200 : 503);
        });
    }

    @Test
    void unknownIsAResultAndNotAMissingEndpoint() {
        application("demo.probe-result=NOT_RUN").run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            var unknown = mvc.perform(get("/actuator/health/dependency"))
                    .andReturn().getResponse();
            assertThat(unknown.getStatus()).isEqualTo(200);
            assertThat(json.readTree(unknown.getContentAsString())
                    .path("status").asText()).isEqualTo("UNKNOWN");
            assertThat(mvc.perform(get("/actuator/health/missing"))
                    .andReturn().getResponse().getStatus()).isEqualTo(404);
        });
    }

    @Test
    void changingSeverityOrderDoesNotAutomaticallyChangeHttpMapping() {
        application(
                "demo.probe-result=NOT_RUN",
                "management.endpoint.health.status.order=down,out-of-service,unknown,up")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .build();
                    var response = mvc.perform(get("/actuator/health"))
                            .andReturn().getResponse();
                    assertThat(response.getStatus()).isEqualTo(200);
                    assertThat(json.readTree(response.getContentAsString())
                            .path("status").asText()).isEqualTo("UNKNOWN");
                });
    }
}
```

Run in the directory containing `pom.xml`:

```powershell
mvn test
```

The success output should contain:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Six parameter sets test combinations of the two indicators. The remaining two tests distinguish UNKNOWN from a non-existent resource and prove that changing aggregation order does not automatically change the HTTP code.

Key evidence:

- UP, DOWN, OUT_OF_SERVICE, and UNKNOWN remain accurate at each component.
- DOWN and OUT_OF_SERVICE are not merged into the same content merely because both return 503.
- UNKNOWN is not treated as UP on that component itself, even though the root status may be UP.
- UNKNOWN can be a valid response with HTTP 200; a missing resource is a different case.
- Custom policies must be evaluated across both root status and HTTP code.

Startup logs and execution times may differ across machines. Tests in this application do not verify TLS, firewalls, or how a real load balancer consumes health.

## 9. Choosing statuses soundly in real applications

A check contract should describe the observed condition, success evidence, failure evidence, and handling when undetermined or out of service.

Example for a dependency check:

| Item to define | Design example |
| --- | --- |
| Scope | Can execute the selected lightweight check operation on the dependency within the time limit |
| Success | Operation meets the defined condition |
| Failure | Condition is not met, including agreed error or timeout cases |
| Undetermined | No valid measurement yet to conclude, if the design genuinely has this status |
| Out of service | Component is currently excluded from serving per the applied policy |

An indicator is not required to use all four statuses. If the contract only has clear success or failure, forcing UNKNOWN into it can make the signal harder to interpret.

Besides each indicator's status, align with consumers:

- Does the monitor inspect HTTP, JSON, or both?
- Does it read root health or a specific group/scope?
- Is UNKNOWN accepted, warned on, or treated as unfit?
- Who controls taking a component out of or into service?
- What evidence helps explain state transitions?

Diagnostic details should be useful yet free of secrets or unnecessary business data. Do not put passwords, tokens, or entire sensitive dependency responses into details.

## 10. Common interpretation errors

| Misconception | Correct reading |
| --- | --- |
| UP means there cannot be business errors | UP only reflects the checked condition and scope |
| DOWN means the process has exited | A running process can still report DOWN |
| OUT_OF_SERVICE is just another name for DOWN | One status expresses out of service; the other expresses an identified failure |
| OUT_OF_SERVICE automatically closes ports or redirects traffic | It is a report; consumption and enforcement mechanisms must be designed separately |
| UNKNOWN means there is no endpoint | UNKNOWN is a component result; a non-existent resource is a different situation |
| UNKNOWN is inherently safe or inherently the most severe failure | You must read the check contract and aggregation policy |
| Many UPs will make the root UP despite a DOWN | The default aggregator uses priority order, not majority count |
| HTTP 200 always means UP | UNKNOWN can also return HTTP 200 by default |
| Two statuses sharing HTTP 503 have the same meaning | DOWN and OUT_OF_SERVICE still help distinguish situations |
| Changing aggregation order automatically changes HTTP | The two mechanisms are configured and verified separately |
| Changing text in details makes the framework change status | The indicator must pick the status; details only explain |
| Every indicator must use all four statuses | Only use statuses that the check contract can explain clearly |

## 11. Scenario classification practice

With default order and mapping, predict first:

1. The dependency check fails, while work-admission policy is still enabled.
2. The dependency responds, while the component has been taken out of service.
3. No dependency check result yet, while admission is UP.
4. No dependency check result yet, while admission is OUT_OF_SERVICE.
5. Both dependency failure and admission OUT_OF_SERVICE occur together.

Compare against the lab model:

| Scenario | dependency | admission | Root | Root HTTP |
| --- | --- | --- | --- | --- |
| 1 | DOWN | UP | DOWN | 503 |
| 2 | UP | OUT_OF_SERVICE | OUT_OF_SERVICE | 503 |
| 3 | UNKNOWN | UP | UP | 200 |
| 4 | UNKNOWN | OUT_OF_SERVICE | OUT_OF_SERVICE | 503 |
| 5 | DOWN | OUT_OF_SERVICE | DOWN | 503 |

Next question: if only the root HTTP code is stored while discarding the JSON body, what information is lost?

You cannot distinguish UP from UNKNOWN from HTTP 200 alone, nor can you distinguish DOWN from OUT_OF_SERVICE from HTTP 503 alone. And if you only store the root status, you may miss child statuses occurring simultaneously.

A sound way of reading follows the chain: **which condition was checked → which status the component returned → which policy aggregated it → which HTTP code was mapped → what the consumer will do**.
