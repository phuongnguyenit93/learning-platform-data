# Mapping Health Statuses to HTTP Status Codes with HttpCodeStatusMapper

## 1. Two results to read when calling health

When calling `/actuator/health`, you simultaneously receive **the health status in the JSON body** and **the HTTP status code of the response**. These two values serve two different consumers:

- Humans or programs parsing JSON use `UP`, `DOWN`, or a custom status to understand application condition.
- Monitors or load balancers may inspect only the HTTP status code to decide whether the check succeeded.

For example, an application reporting `{"status":"DOWN"}` while returning HTTP `200` might still be treated as successful by a system that only checks the HTTP code. To understand and configure this behavior properly, you need to know the step converting `Status` to an HTTP code.

In Spring Boot Actuator, `HttpCodeStatusMapper` handles that conversion step. This lesson uses the Spring Boot **3.3.x** API, with the example running on **JDK 21** and dependency **3.3.0** for reproducible results; this is an illustrative version, not a requirement to upgrade or downgrade your existing project version.

### 1.1. Position of the mapper in the processing flow

For a valid health response at the root path or a group path, you can picture:

```text
HealthIndicator
    -> Health contains Status of each component
    -> StatusAggregator selects aggregated Status
    -> HttpCodeStatusMapper converts that Status into an HTTP code
    -> response: HTTP code + Health data
```

| Component | Question to answer | Example result |
| --- | --- | --- |
| `HealthIndicator` | What status is the checked component in? | `Health` with `Status.DOWN` |
| `StatusAggregator` | When multiple components have different statuses, what is the overall status? | `DOWN` |
| `HttpCodeStatusMapper` | For the selected status, which HTTP code should be returned? | `503` |

The mapper does not check databases, does not select which components belong to a group, and does not alter the aggregated status. In the HTTP web extension for health, Spring Boot retrieves the corresponding group's mapper, passes in `health.getStatus()`, and uses the returned integer as the HTTP status code. [HealthEndpointWebExtension 3.3.13 Source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java)

**Consequence when troubleshooting:** if the JSON says `UP` when you expected `DEGRADED`, check indicator results and aggregation first. Adding a `DEGRADED -> 503` mapping will not help if the mapper actually only receives `UP`.

## 2. Contract of HttpCodeStatusMapper and defaults

### 2.1. Input is Status, output is int

The method signature to focus on:

```java
int getStatusCode(Status status);
```

`Status` is an object of the health system, not `org.springframework.http.HttpStatus`. You retrieve the health code via `status.getCode()`, such as `"DOWN"`. The return value is an integer like `200` or `503`.

The types used in this lesson all belong to the package:

```java
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.Status;
```

A mapper can be implemented with a lambda. `HttpCodeStatusMapper.DEFAULT` provides the default mapper, while `SimpleHttpCodeStatusMapper` implements mapping based on a lookup map. [HttpCodeStatusMapper 3.3.13 API and Uses](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/class-use/HttpCodeStatusMapper.html)

### 2.2. Default table

| Status passed to default mapper | Returned HTTP |
| --- | --- |
| `DOWN` | `503` |
| `OUT_OF_SERVICE` | `503` |
| `UP` | `200` |
| `UNKNOWN` | `200` |
| Other unmapped status | `200` |

`UNKNOWN` means the status has not been determined; it is not synonymous with `UP` even though both receive HTTP `200` by default. [Meaning of Status Constants](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html)

The fallback rule to `200` is a mapping policy, not evidence that the application is healthy. If your operational system requires `UNKNOWN` to be treated as unavailable, you must declare that policy explicitly.

## 3. Configuring the mapping table via properties

For requirements that depend only on the health code, configuration is usually easier to read and maintain than writing a bean. For example, suppose a system defines `DEGRADED` as still running yet not meeting the quality required to receive traffic.

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=503
```

If you want `UNKNOWN` to return `503` as well, add:

```properties
management.endpoint.health.status.http-mapping.unknown=503
```

Use lowercase and hyphenated configuration keys as shown, while the Java constant remains `Status.OUT_OF_SERVICE` and the JSON code is `"OUT_OF_SERVICE"`.

### 3.1. Pitfall: custom table replaces the default table

The following configuration is **not enough** to preserve `DOWN -> 503` behavior:

```properties
management.endpoint.health.status.http-mapping.degraded=503
```

When a custom table is supplied, do not assume Spring Boot automatically merges each entry into the default table. To keep `DOWN` and `OUT_OF_SERVICE` returning `503`, both must be re-declared. Codes absent from the custom table continue using the `200` fallback. This behavior is clearly documented in Spring Boot 3.3. [Health HTTP Mapping Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Compare directly on `SimpleHttpCodeStatusMapper`:

```java
HttpCodeStatusMapper mapper =
        new SimpleHttpCodeStatusMapper(Map.of("degraded", 503));

System.out.println(mapper.getStatusCode(Status.DOWN)); // 200
System.out.println(mapper.getStatusCode(new Status("DEGRADED"))); // 503
```

This is an excerpt; it requires importing `java.util.Map` and the health types. The constructor accepting a map does not automatically add default entries into that map; the no-arg constructor creates a mapper using the defaults. [SimpleHttpCodeStatusMapper 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html)

### 3.2. Mapping and severity order are two independent configurations

For a custom status to participate in aggregation as intended, you must configure an appropriate order, for example:

```properties
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
```

In this order, `DEGRADED` is selected before `UP` if both appear. Placing `UNKNOWN` after `UP` is the example's choice; if undetermined status should take priority, place it before `UP`.

This is the **complete order you intend to use**, not an item appended to the default list. Keep all standard statuses that the application needs to aggregate.

If the default aggregator encounters the set `{UP, DEGRADED}`, `DEGRADED` is not in the default order and therefore cannot beat `UP`. When only statuses unrecognized by the order are present, the aggregated result can be `UNKNOWN`. Hence, verify the actual status reaching the mapper, rather than only looking at the status name produced by an indicator. [SimpleStatusAggregator 3.3.13 Source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java)

## 4. When do you need an HttpCodeStatusMapper bean?

A bean is suitable when the policy is best expressed in code, such as handling a few custom statuses while explicitly delegating the rest to the default mapper.

```java
@Bean
HttpCodeStatusMapper applicationHttpCodeStatusMapper() {
    return status -> {
        if ("DEGRADED".equals(status.getCode())
                || Status.UNKNOWN.equals(status)) {
            return 503;
        }
        return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
    };
}
```

This is a declaration snippet inside a Spring configuration class; it requires importing `org.springframework.context.annotation.Bean`. Its policy is:

- `DEGRADED` and `UNKNOWN` return `503`.
- `DOWN` and `OUT_OF_SERVICE` are handled by the default mapper and therefore still return `503`.
- `UP` and other unhandled statuses receive the default mapper's fallback behavior.

Compare using `equals` or comparing `getCode()`; avoid `status == Status.DOWN` because you may receive another `Status` instance carrying the same code. Custom status objects are created with `new Status("DEGRADED")`. With the lambda above, Java string comparison is case-sensitive; keep the codes emitted by indicators consistent.

### 4.1. Bean and properties do not automatically merge policies

In Spring Boot 3.3's standard auto-configuration, the primary health group picks an unqualified `HttpCodeStatusMapper` bean if present. Only when no matching bean exists does it create `SimpleHttpCodeStatusMapper` from the properties table.

Therefore, a bean like the one above **does not automatically read or merge** `management.endpoint.health.status.http-mapping`. If you want to use both the configuration table and additional code, you must design that combination inside the bean. Do not just add properties and assume an existing bean will use them.

Keep a single clear primary mapper policy to avoid having multiple beans in the same role where Spring cannot choose one. [How Spring Boot Selects Primary and Group Mappers](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java)

### 4.2. Keep the mapper small and pure about mapping

The mapper only needs to turn a status into an HTTP code. Do not call health over HTTP again from the mapper, do not re-query the database, and do not mutate shared state on each mapping call. Those actions make results unpredictable or can create call cycles.

If you need to know whether a dependency is failing, that information should be expressed in indicators and health statuses before reaching the mapper.

## 5. Complete HTTP experiment

The following example creates a standalone application without requiring a database or external service. The status is passed at startup so each trial has reproducible results. In a real application, indicators must check a meaningful condition instead of always returning a simulated status.

### 5.1. File structure

```text
health-mapper-demo/
├── pom.xml
├── src/main/java/example/health/HealthMapperApplication.java
├── src/main/resources/application.properties
└── src/main/resources/application-mapping.properties
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>health-mapper-demo</artifactId>
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

`src/main/java/example/health/HealthMapperApplication.java`:

```java
package example.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.Status;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class HealthMapperApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthMapperApplication.class, args);
    }

    @Bean
    HealthIndicator demoHealthIndicator(
            @Value("${demo.health-status:UP}") String code) {
        Status simulatedStatus = new Status(code);
        return () -> Health.status(simulatedStatus).build();
    }

    @Bean
    @Profile("mapper")
    HttpCodeStatusMapper applicationHttpCodeStatusMapper() {
        return status -> {
            if ("DEGRADED".equals(status.getCode())
                    || Status.UNKNOWN.equals(status)) {
                return 503;
            }
            return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
        };
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=health-mapper-demo
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
demo.health-status=UP
```

In the experiment, `management.health.defaults.enabled=false` excludes auto-configured indicators from the test; the `demoHealthIndicator` bean declared by the application still remains. The two `show-...=never` settings help observe only the overall status without putting details into JSON. They do not decide the HTTP status code.

The order containing `DEGRADED` is declared from the start to isolate the effect of the mapper. Keep the uppercase spelling of values passed to `demo.health-status` as shown in the commands below.

`src/main/resources/application-mapping.properties`:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=503
```

The two profiles represent two ways of choosing a policy:

| Active profile | Mapper in example |
| --- | --- |
| No active profile | Default mapper |
| `mapping` | Properties table, keeping two standard mappings and adding `DEGRADED` |
| `mapper` | Java bean, handling `DEGRADED`/`UNKNOWN` explicitly and delegating defaults |

### 5.2. Packaging and starting

In the directory containing `pom.xml`, Maven and JDK 21 are required:

```powershell
mvn -q package
java -jar target/health-mapper-demo-1.0.0.jar --demo.health-status=DOWN
```

Wait for the application to start successfully, then open another terminal. Each time you switch scenarios, stop the process with `Ctrl+C` before running the new command so port `8080` does not collide.

The check commands below are for PowerShell on Windows, invoking `curl.exe` to avoid the `curl` alias in some PowerShell versions. Check the HTTP code alone:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

For the `DOWN` run, stdout:

```text
503
```

Read the body:

```powershell
curl.exe -sS http://localhost:8080/actuator/health
```

JSON content:

```json
{"status":"DOWN"}
```

`NUL` is the destination to discard the body on Windows. When using Bash on Linux/macOS, the corresponding command to get the code is:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health
```

Do not add `--fail` when the goal is to observe both the `503` response and the body; an HTTP-level error is an expected result to verify in the experiment.

### 5.3. Comparing the runs

Each line is a separate launch, followed by re-running the two check commands above.

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --demo.health-status=DEGRADED
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapping --demo.health-status=DEGRADED
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapping --demo.health-status=DOWN
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapper --demo.health-status=UNKNOWN
```

| Run | Expected JSON status | Expected HTTP | What to observe |
| --- | --- | --- | --- |
| No profile, `DEGRADED` | `DEGRADED` | `200` | Aggregator recognized the status, default mapper has not mapped it |
| `mapping`, `DEGRADED` | `DEGRADED` | `503` | Properties change how the status is represented over HTTP |
| `mapping`, `DOWN` | `DOWN` | `503` | Custom table still preserves standard failure mapping |
| `mapper`, `UNKNOWN` | `UNKNOWN` | `503` | Bean applies a policy different from default `UNKNOWN -> 200` |

HTTP results in the table assume direct calls to the example application, without Spring Security, a reverse proxy, or other configuration intercepting requests. Do not infer the application's status code from a code generated by a proxy.

**Testing the configuration pitfall:** in the lab project, remove the `down` and `out-of-service` lines from `application-mapping.properties`, repackage, and run the `mapping` profile with `DOWN`. The body still reports `DOWN`, yet the HTTP code will be `200`. Restore those two lines after observing.

## 6. Running the mapper directly to verify precision

You do not need to start a web server to test a mapping function. The following program compares four mappers against the same inputs, while also demonstrating the independence of the aggregation step.

Save as `experiments/MapperDemo.java`, outside `src/main/java` of the project in section 5 so it does not add another main class to the Spring Boot JAR.

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

public class MapperDemo {
    public static void main(String[] args) {
        Status degraded = new Status("DEGRADED");
        HttpCodeStatusMapper defaults = HttpCodeStatusMapper.DEFAULT;
        HttpCodeStatusMapper partial =
                new SimpleHttpCodeStatusMapper(Map.of("degraded", 503));
        HttpCodeStatusMapper complete = new SimpleHttpCodeStatusMapper(
                Map.of("down", 503, "out-of-service", 503, "degraded", 503));
        HttpCodeStatusMapper policy = status -> {
            if ("DEGRADED".equals(status.getCode())
                    || Status.UNKNOWN.equals(status)) {
                return 503;
            }
            return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
        };

        for (Status status : List.of(Status.UP, Status.DOWN,
                Status.OUT_OF_SERVICE, Status.UNKNOWN, degraded)) {
            System.out.println(status.getCode()
                    + " | default=" + defaults.getStatusCode(status)
                    + " | partial=" + partial.getStatusCode(status)
                    + " | complete=" + complete.getStatusCode(status)
                    + " | policy=" + policy.getStatusCode(status));
        }

        Set<Status> components = Set.of(Status.UP, degraded);
        System.out.println("aggregate-default="
                + new SimpleStatusAggregator()
                        .getAggregateStatus(components).getCode());
        System.out.println("aggregate-custom="
                + new SimpleStatusAggregator("DOWN", "OUT_OF_SERVICE",
                        "DEGRADED", "UP", "UNKNOWN")
                        .getAggregateStatus(components).getCode());
    }
}
```

Once the `experiments` directory and source file exist, run in the directory containing `pom.xml`:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$healthDemoClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $healthDemoClasspath experiments/MapperDemo.java
java -cp "$healthDemoClasspath;experiments" MapperDemo
```

The `;` in the classpath is Windows syntax. If running on Linux/macOS, use `:` as the separator and read the classpath from the file using the corresponding shell syntax.

Stdout of `MapperDemo`:

```text
UP | default=200 | partial=200 | complete=200 | policy=200
DOWN | default=503 | partial=200 | complete=503 | policy=503
OUT_OF_SERVICE | default=503 | partial=200 | complete=503 | policy=503
UNKNOWN | default=200 | partial=200 | complete=200 | policy=503
DEGRADED | default=200 | partial=503 | complete=503 | policy=503
aggregate-default=UP
aggregate-custom=DEGRADED
```

Reading the results experiment by experiment:

1. `default` proves the built-in mappings and the `200` fallback value.
2. `partial` proves a table with only `degraded` does not preserve `DOWN`/`OUT_OF_SERVICE`.
3. `complete` proves declaring all three entries preserves the intended behavior.
4. `policy` handles `UNKNOWN` specially while keeping `DOWN`/`OUT_OF_SERVICE` by calling the default mapper.
5. Both `aggregate-...` lines use the same `{UP, DEGRADED}` set. Changing aggregation order changes the input the mapper will receive; changing the mapper does not do that automatically.

This is a Java API-level verification; it does not replace an HTTP test when the application has profiles, health groups, security filters, or proxies.

## 7. Scoping by health group

An application may have multiple health consumers with different requirements. Health groups allow selecting a set of indicators and having a dedicated mapper.

To continue experimenting in the section 5 application, **without activating the `mapper` profile**, keep the common configuration and append these lines to `application.properties`:

```properties
management.endpoint.health.group.routing.include=demo
management.endpoint.health.group.routing.status.http-mapping.down=503
management.endpoint.health.group.routing.status.http-mapping.out-of-service=503
management.endpoint.health.group.routing.status.http-mapping.degraded=503
```

Start with `--demo.health-status=DEGRADED` and test:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/routing
```

Status code results in order:

```text
200
503
```

Both paths look at the same `demo` indicator, yet the `routing` group uses its own HTTP table. The name `demo` comes from the `demoHealthIndicator` bean after stripping the `HealthIndicator` suffix.

If no dedicated mapper is configured, a group inherits the primary mapper. When a group mapping table exists, it is that group's own table; do not assume it automatically merges missing entries from the primary table. The example explicitly declared both `DOWN` and `OUT_OF_SERVICE` for the group.

You can declare a bean annotated with `@Qualifier("routing")` to select a mapper for the group of the same name. Clearly specify the primary role and group roles, avoiding creating multiple indistinguishable beans. How mappers are selected by qualifier and how the primary mapper is used as fallback can be seen in [Spring Boot 3.3.13 HealthEndpointGroups configuration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

If applying this to readiness/liveness, you must accurately define each group's check meaning and policy. Changing a health code does not automatically change the meaning of application lifecycle states; whether a code is treated as success or failure by a monitor also depends on that monitor's contract.

## 8. Limitations and common mistakes

| Symptom | What to inspect | How to address |
| --- | --- | --- |
| JSON `DOWN` yet HTTP `200` after adding a custom status | Custom table is missing `down` | Re-declare the standard statuses you want to keep |
| Indicator reports `DEGRADED` yet overall JSON is `UP` or `UNKNOWN` | Aggregation order does not recognize that status yet | Inspect `status.order` or `StatusAggregator` |
| Edited `http-mapping` yet HTTP did not change | A Java bean is active; or the config profile is not enabled | Identify the active mapper and effective configuration source |
| Overall health and group return different codes | Two paths may use different mappers or indicator sets | Inspect the configuration of the specific group |
| Receiving `401`/`403` or `404` | Security, endpoint exposure, path/port, component visibility | Check request-handling layers before blaming the mapper |
| Receiving `502` from proxy | Proxy may not have received a valid response from the application | Call the application port directly and check logs |
| JSON hides details yet HTTP still returns an error code | `show-details`/`show-components` only control display | Verify status and code policy independently |

`HttpCodeStatusMapper` is not a handler for all HTTP errors in an application. It does not alter status codes for controllers, does not establish authentication policies, and does not govern JMX results since JMX has no HTTP status codes.

The mapping table only handles **how an already-computed status is represented**. If the database has recovered yet the indicator still reports `DOWN` due to a bug in the check, changing `DOWN -> 200` only blinds operators to the signal.

## 9. Self-check practice

1. Using `MapperDemo`, add `new Status("MAINTENANCE")` to the input list. Before running, predict all four codes. Because no mapper handles that status explicitly, all four return `200`.
2. Add `maintenance=503` to a new table. Test `DOWN` again to verify whether you intentionally preserved or replaced standard behavior rather than losing it accidentally.
3. In the HTTP app, run `UNKNOWN` with no profile, the `mapping` profile, and then the `mapper` profile. With the sample configuration, the codes are `200`, `200`, `503` respectively; the body stays `UNKNOWN`.
4. Explain why `DEGRADED -> 503` does not make `{UP, DEGRADED}` aggregate to `DEGRADED` automatically without configuring order.
5. Write down the operational contract for a custom status: what condition it represents, whether traffic is allowed, where it sits in aggregation order, what HTTP code to return, and what monitoring systems will do with that code.

When verifying a change, trace the full chain **component status → overall/group status → active mapper → received HTTP code**. This chain helps separate health-check bugs, aggregation bugs, and mapping-configuration bugs.
