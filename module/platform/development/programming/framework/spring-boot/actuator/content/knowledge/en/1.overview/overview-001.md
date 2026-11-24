# What Is Actuator and How Does It Solve Application Operations Challenges?

## 1. From “Running” to “Operable”

Suppose you write an order service, run the application successfully, and call the order-creation API to test it. A correct result from that test is good evidence for the feature you just wrote. After deployment, however, operators must answer other questions:

- The process is still alive, but is the application responding to requests?
- When users report slowness, is latency increasing for every request or only a subset?
- Is memory usage growing, or is request volume growing?
- Is the running deployment actually the build the development team just released?
- Which component is reporting an abnormal state?
- Which logs should be inspected next to find the root cause?

A startup success message cannot answer all of those questions. Nor are they easily solved by repeatedly adding ad-hoc custom APIs such as `/check-server`, `/memory`, or `/debug-config` to every project. Different teams may use different names, return different payloads, and accidentally expose internal details.

**Spring Boot Actuator adds capabilities for observing and managing a running application.** It provides management endpoints and integrates with Spring Boot’s auto-configuration mechanism. Operators and monitoring tools gain a more consistent way to retrieve operational information. The recommended way to add this capability in Spring Boot is `spring-boot-starter-actuator`. [Enabling Spring Boot Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

You can think of a service like a car: the order-taking feature is the ability to move and carry cargo; operational data is like the speedometer, fuel gauge, and warning lights. The gauges help the driver recognize the vehicle’s condition. Fixing issues and deciding how to proceed still require a human or an appropriate control mechanism.

This lesson uses Spring Boot **3.3.13** and Java **21** to keep examples concrete. Default values are presented within the scope of the 3.3 line; when using another version, consult the corresponding documentation.

## 2. Key Terms to Understand First

### Management Access Point — endpoint

An Actuator endpoint is an identified management capability, such as `health` or `metrics`. For web applications under standard configuration, they are accessed via paths like `/actuator/health`.

Distinguish between an **endpoint ID** and an **HTTP address**. `health` is the ID; `/actuator/health` is the path under a specific exposure mechanism. The path prefix and management port can be configured. HTTP is not the only transport either: Actuator also supports exposing endpoints over JMX, Java’s application management mechanism. [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Application Status — health

Health is an evaluation result based on the checks registered in the system. A `HealthIndicator` contributes the result of a single check; `HealthEndpoint` aggregates that information to expose to callers.

Conceptually, a check answers “is the resource I am responsible for usable?”, and that result is incorporated into the overall picture. Only what is actually checked can contribute evidence. Actuator does not automatically know every ordering rule or every external service your system uses. [HealthIndicator contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html), [HealthEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

### Operational Measurements — metrics

Metrics represent activity numerically: request counts, processing duration, memory usage, or other recorded quantities. A single read tells you the current value; multiple reads over time reveal trends.

Micrometer is the instrumentation library that Spring Boot integrates. `MeterRegistry` manages meter objects. Tags distinguish groups of measurements, such as by HTTP method or URI path. An external system can scrape and store these metrics for long-term analysis.

### Observability

Observability is the ability to reason about internal state from the signals collected. Three signal types are commonly used together:

| Signal | Suitable question | Example |
| --- | --- | --- |
| Metrics | At what scale is there a problem, and when did it appear? | Error rate spikes over a 5-minute window |
| Logs | What event occurred and with what details? | A call to the payment provider was rejected |
| Distributed traces | Where did a request travel and where was time spent? | A request flowed through the order service and then to the payment service |

This table describes how signals are used for reasoning, not a claim that every application already has all three. Spring Boot uses Micrometer Observation for metrics and tracing; exporting traces to a storage backend also requires the appropriate integration components. [Observability documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html), [Tracing documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

## 3. Where Does Actuator Fit in the System?

Separate two lines of thinking:

~~~text
User
    -> business API
    -> business processing
    -> business outcome

Operator / tool
    -> management info and operational signals
    -> health assessment
    -> alerts or procedural action
~~~

The business API answers “what does the user want to do?”. The management interface answers “how is the system behaving and what can be managed?”.

For example:

- `POST /orders` creates an order according to the customer’s permissions.
- `GET /actuator/health` returns status information based on the configured checks.
- `GET /actuator/metrics` lets you inspect the names of available metrics when that endpoint is exposed.

Separating these two flows clarifies access-control design and intended consumers. Someone permitted to place orders should not necessarily be permitted to inspect internal application configuration.

A common monitoring deployment looks like this:

~~~text
Application records metrics
    -> appropriate registry / exporter
    -> collection and storage system
    -> queries / dashboards / alert rules
    -> on-call operator
~~~

Here, Actuator and Micrometer sit on the producer side, recording and exposing signals. Historical storage, dashboards, and alerting policies are parts that must be designed separately.

For instance, when choosing Prometheus, you need the appropriate registry and scrape configuration for the collector to read. When choosing Grafana for visualization, you need a data source and dashboards. Simply adding the starter to the application does not build that entire pipeline. [Metrics integration documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 4. From an Incident to the Evidence Needed

Suppose users report “creating orders is very slow”. If the operations team only knows that the Java process is still alive, they lack enough data to choose an action.

You can start with three layers of questions:

1. **Is it reachable?** Check the access path, HTTP status code, and ability to receive responses.
2. **How wide is the impact?** Check request counts, error rates, and processing duration by group.
3. **Why is it happening?** Cross-check relevant logs, traces, or diagnostic data.

This is an illustrative reasoning workflow, not an algorithm that Actuator runs automatically.

| Observation | Grounded conclusion | Next investigation step |
| --- | --- | --- |
| Cannot connect to the management address | From the current check location, no response has been obtained | Check address, network, port, and process |
| Health returns `UP` but users still experience slowness | Existing health checks do not indicate an unhealthy state | Inspect latency and errors in the user flow |
| Memory grows alongside request volume | Both variables are increasing in the same observation window | Compare further over time, load, and garbage collection |
| Only one API group sees rising errors | Impact appears concentrated in that group | Inspect logs and dependencies used by that API group |

Do not turn a correlation into a cause. Rising memory alone does not prove a memory leak. An endpoint returning `200` does not prove customers can complete transactions.

The practical value of Actuator is helping gather evidence systematically. The quality of conclusions still depends on asking the right questions and understanding each signal’s scope.

## 5. Capabilities to Recognize at an Overview Level

A few common endpoint IDs:

| Endpoint | Primary role |
| --- | --- |
| `health` | Status information |
| `info` | Application information provided by contributors |
| `metrics` | Query metrics for diagnostics |
| `loggers` | View or modify logging levels |
| `conditions` | View auto-configuration condition evaluation results |
| `threaddump` | Capture thread information for investigation |

Not every endpoint has useful data as soon as the application starts. Specific capabilities depend on libraries, configuration, and beans created. [Spring Boot 3.3 Endpoint catalog](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

In an introductory lesson, the goal is to pick the right kind of information for an operational question. Memorizing every endpoint or exposing all of them will not help you understand problems faster.

In particular, recognize that some management operations **can mutate state**. A request to read health and a request to change a logging level have different consequences. Authorization rules must reflect that difference.

## 6. What Layers Must Be Passed to Access an Endpoint?

With Spring Boot 3.3 configuration, verify each layer separately:

1. **Do the required components exist?** For example, the library and matching auto-configuration conditions must be met.
2. **Is the endpoint enabled?** Properties of the form `management.endpoint.<id>.enabled` control whether an endpoint is enabled.
3. **Is the endpoint exposed over HTTP?** `management.endpoints.web.exposure.include` selects the IDs exposed over the web.
4. **Is the request allowed through?** Network rules, authentication, and authorization can still block access.

In the 3.3 line, only `health` is exposed over HTTP by default. Configuring `include` does not grant security permissions to callers. [Endpoint enabling and exposure rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

The example below uses an explicit list:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

This list states that the exercise needs those three endpoints exposed. It lets the reader clearly see what is open without guessing the effect of wildcards.

Unreachable paths must also be interpreted in context:

- `404`: check the address, prefix, and endpoint exposure.
- `401` or `403`: check security configuration and request permissions.
- Connection errors or timeouts: first verify reachability to the target address.

These are investigation leads, not absolute reverse-mappings: proxies and custom security rules can alter responses.

## 7. Hands-On: A Minimal Application with a Business API and Actuator

The example is **a standalone project**. You need JDK 21, Maven, and connectivity to the artifact repository on the first build. No database, Docker, or external monitoring system is required.

Use the following structure:

~~~text
actuator-intro/
├── pom.xml
└── src/main/
    ├── java/example/actuator/ActuatorIntroApplication.java
    └── resources/application.yml
~~~

### 7.1. Declare Dependencies

File `pom.xml`:

~~~xml
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

    <groupId>example</groupId>
    <artifactId>actuator-intro</artifactId>
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
~~~

The web starter provides the foundation for the HTTP example; the Actuator starter adds management capabilities. The parent manages versions of related libraries, so you do not need to specify separate versions for each starter.

### 7.2. Write a Simple API

File `src/main/java/example/actuator/ActuatorIntroApplication.java`:

~~~java
package example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorIntroApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorIntroApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Xin chao Actuator";
    }
}
~~~

`/hello` represents the user-facing API in the example. There is no custom controller for `/actuator/health` or `/actuator/metrics`: those capabilities are provided by Actuator according to configuration.

### 7.3. Configure the Practice Scope

File `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: actuator-intro

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
~~~

The example listens only on the loopback address `127.0.0.1` for local practice on the same machine. It does not include Spring Security and has no login mechanism configured. In a typical environment, other processes able to reach this address can also call the exposed paths; account for proxies, port forwarding, and deployment layout if you change the environment.

`show-details: never` instructs Actuator not to include health details in the response. Reducing response detail does not replace access control.

### 7.4. Build and Run

Open a terminal in the directory containing `pom.xml`:

~~~powershell
mvn clean package
java -jar target/actuator-intro-1.0.0.jar
~~~

The first command builds an executable JAR. The second keeps the application running in the terminal; wait for startup to complete, then open a second terminal to send test requests. If port `8080` is already in use, stop the application occupying it or change `server.port` and adjust the test URLs accordingly.

Because the program uses Spring Boot libraries and must be packaged with its dependencies, running `javac` directly on the source file is not enough. Maven handles compilation and packaging; `java -jar` executes the resulting artifact.

## 8. Reading Results and Limits of Each Check

The commands below use PowerShell on Windows. `curl.exe` invokes the cURL executable, avoiding confusion with the `curl` alias in some PowerShell versions. On Linux or macOS, use the corresponding `curl` command.

### 8.1. What Does the User API Return?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/hello
~~~

Response body:

~~~text
Xin chao Actuator
~~~

This result proves that the request just sent to `/hello` was handled by the example code. It does not prove every API in a large application works.

### 8.2. What Does Health Tell Us?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/health
~~~

With default checks passing, the response body is:

~~~json
{"status":"UP"}
~~~

Do not read `UP` as “every business transaction is guaranteed to succeed”. The example has no database connection, so this result provides no evidence about any database. Nor has any payment provider been evaluated just because the health endpoint returns `UP`.

If the environment causes a check to return another status, investigate that check instead of changing expectations just to always see `UP`. Health status is meaningful when you understand what it is checking.

### 8.3. Why Can Info Be Empty?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/info
~~~

With this exact minimal project, the response body is:

~~~json
{}
~~~

This is a concrete example showing that **exposing an endpoint** and **providing content for an endpoint** are two separate steps. Declaring `spring.application.name` does not automatically turn that value into `/actuator/info` content.

To use `info` to identify a deployed build, you must actively choose and provide appropriate information sources. This lesson keeps the response empty so you can clearly observe the limits of the baseline configuration.

### 8.4. Was the Request Just Called Measured?

Spring MVC has built-in request timing under the default name `http.server.requests`. You can query that metric after calling `/hello`:

~~~powershell
curl.exe --silent "http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=uri:/hello&tag=method:GET"
~~~

The returned data contains measurements and associated tags. Processing duration depends on the machine, run, and load; do not copy a fixed timing number as a required result.

To extract only the call count in the selected group:

~~~powershell
$metric = Invoke-RestMethod -Uri "http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=uri:/hello&tag=method:GET"
$count = $metric.measurements | Where-Object { $_.statistic -eq "COUNT" }
[int]$count.value
~~~

If the application was just started and only one `GET /hello` request has completed, the output line is:

~~~text
1
~~~

Call `/hello` once more, wait for the request to finish, and rerun the metric query snippet. The output is then `2`. Calls to `health` or `metrics` do not belong to the filtered `uri:/hello` group.

Counters belong to the running process; restarting the example begins a new recording cycle. Retaining history across restarts belongs to external collection design. [HTTP metric names and tag query documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 8.5. Unexposed Endpoint

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator/beans
~~~

With the minimal project’s exact configuration, the printed HTTP code is:

~~~text
404
~~~

`beans` is not in the example’s exposure list. This experiment distinguishes “the starter is in the project” from “every endpoint is accessible over the web”.

`NUL` is the null device for discarding response bodies on Windows; on Linux or macOS use `/dev/null`.

## 9. From Hands-On Practice to Real Operations

From these checks, you can build a needs-based approach:

| Need | Design addition needed |
| --- | --- |
| Detect loss of serving capability | Choose suitable checks and how external systems evaluate results |
| Detect performance degradation | Collect latency, retain history, set thresholds, and inspect distributions |
| Detect critical business errors | Choose signals that accurately reflect business outcomes |
| Identify running deployment | Supply version info from a clear source |
| Investigate multi-service requests | Set up context propagation, recording, and trace storage |
| Notify on-call staff | Configure alert rules, notification targets, and response procedures |

These are design decisions to make for a specific system, not a promise that the starter will complete them for you.

For example, if “order creation failed” still returns HTTP `200` with an error code in the body, counting only HTTP `5xx` codes will miss that failure mode. The development team must agree on how outcomes are represented and choose metrics meaningful to the business.

Likewise, an average latency chart can hide a small group of users waiting much longer. When evaluating user experience, choose measurements and aggregations that reflect real goals; never treat a single average as the whole story.

## 10. Access Control Is Also Part of Operational Design

Management data can reveal internal structure and characteristics. Operations that modify configuration can also affect a running application. Therefore, before deployment, define **who can read what, who can change what, and from where they can access it**.

In the Spring Boot 3.3 line, when Spring Security is present and no custom `SecurityFilterChain` is declared, Boot’s security auto-configuration protects Actuator endpoints other than `health`. If the application declares its own security filter chain, the development team is responsible for configuring full access rules. [Endpoint security documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

For this exercise, keep the configured local scope. When applying this to a deployed system, include endpoints in the real management access design. Changing the prefix or separating the port helps organize access paths; doing so alone does not authenticate caller identity.

Also set data boundaries: a health check should not carelessly return passwords, access tokens, or customer data in its details. Check authors understand the business data and must decide what is appropriate to expose.

## 11. Misconceptions That Easily Lead to Wrong Conclusions

### “Having Actuator means you have a complete monitoring system”

The starter only builds the foundation inside the application. You still must choose how to collect, store, visualize, and respond. Trace the signal flow all the way to where on-call engineers receive actionable information.

### “If Health is UP, there is no need to test user flows”

Health reflects what was checked. A synthetic transaction from the user’s perspective provides a different kind of evidence. Choose both according to the service’s criticality.

### “The metrics endpoint is a historical store”

In the example, you are asking one process about the meters it manages. To compare today with yesterday or before and after a deployment, you need a suitable historical storage system.

### “Enabling exposure solves access control”

Exposing an access path and authorizing a principal to use it are two separate decisions. Always verify with real requests from the intended source location and identity.

### “Having metrics means you know the root cause”

Metrics help narrow hypotheses. Root cause requires further evidence. If latency rises alongside external service call errors, correlate timestamps, logs, and traces before concluding.

### “The more endpoints you practice with, the better”

At the introductory stage, pick one question and one verifiable piece of evidence. Expand once you understand which operational question new data will help answer.

## 12. Self-Check with Three Scenarios

**Scenario 1:** The application returns `UP` but the payment feature fails. Is that a contradiction?

Suggested answer: there is not enough basis to call it a contradiction. Check whether current health checks evaluate payment capability, then inspect the actual transaction flow. The health signal can be accurate within its narrow scope.

**Scenario 2:** You added the starter, called `/actuator/metrics`, and got `404`. What is the first thing to verify?

Suggested answer: verify the right application, path, and web exposure configuration. In the 3.3 line, metrics are not exposed over HTTP by default. Only after that check component creation conditions, security, and intermediary layers.

**Scenario 3:** An operator wants to know how many times `/hello` was called yesterday, but the application restarted this morning. Is reading the current counter enough?

Suggested answer: no. You need historical data collected and stored externally, along with query logic that handles process restarts.

After completing this lesson, you should be able to explain three relationships in your own words: **business APIs vs. management interfaces; health vs. check scope; in-application metrics vs. external monitoring systems**. That is the foundation for studying each Actuator capability while keeping clear which operational problem it serves.
