# Support Scope Across Servlet, Reactive, and Non-Web Applications

## 1. Separating Operational Capabilities from Access Mechanisms

Suppose you have three Spring Boot applications:

- An API using Spring MVC to serve HTTP requests.
- A service using Spring WebFlux.
- A batch import program that runs a job and exits.

All three may need memory metrics, task counters, or resource health checks. However, only the first two have a web server under the configurations considered here.

**Actuator is not limited to HTTP applications.** Actual support should be understood through two separate questions:

1. Which components does the application have to produce operational data?
2. Through which mechanism is that data exposed or exported?

For instance, a business counter updated via `MeterRegistry` does not need an HTTP request to function. Conversely, calling `GET /actuator/health` requires an appropriate web infrastructure together with endpoint configuration.

This lesson uses Spring Boot **3.3.13** and Java **21**. The examples are designed to compare the three environments using the same minimal business logic.

## 2. What Are the Three Application Types?

### 2.1. Servlet

A Servlet application uses Servlet infrastructure to receive and handle web requests. In typical Boot setups, `spring-boot-starter-web` provides Spring MVC and a suitable embedded server by default.

Here, Servlet is a web-serving infrastructure type. It is not synonymous with an Actuator-specific instrumentation technology.

### 2.2. Reactive

A Reactive application within this lesson’s scope is a web application using Spring WebFlux. The standard starter setup uses `spring-boot-starter-webflux`.

WebFlux builds on asynchronous processing and Reactive Streams, without requiring the Servlet API as the framework’s foundation. Although Reactor Netty is the common default with that starter, do not define “Reactive” simply as “another name for Netty”. [Spring Boot: Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html).

### 2.3. Non-Web

In Boot, `WebApplicationType.NONE` indicates an application that does not run as a web application and does not start an embedded web server in that mode. It can still have a Spring ApplicationContext, beans, scheduled tasks, message consumers, or command-line runners. [WebApplicationType API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html).

“Non-web” does not mean “no network”. An import job can still call an HTTP client or connect to a database. What is meant is **the absence of Boot’s web server infrastructure in NONE mode**.

Nor should you equate “no business controllers written” with NONE. A web application can expose only management endpoints and still run a web server.

## 3. Support Model: Three Layers to Inspect

Trace these three layers:

~~~text
Libraries and beans in the application
    -> ability to produce or supply operational data
    -> exposure / export mechanism
~~~

For example:

~~~text
HealthIndicator bean
    -> health check result
    -> health endpoint via matching HTTP or JMX

MeterRegistry + meter
    -> JVM / library / business metrics
    -> endpoint query or configured metric exporter
~~~

Thus, “Actuator supports environment X” does not mean every endpoint, every metric, and every access mechanism exists in that environment.

An orientation table:

| Capability | Servlet | Reactive | Non-web |
| --- | --- | --- | --- |
| Record business counters and timers via Micrometer | Possible | Possible | Possible |
| Contribute health information | Possible | Possible, has reactive contract | Possible |
| Expose management endpoints over HTTP | Via matching web stack | Via matching WebFlux stack | No HTTP server solely from Actuator |
| Expose compatible endpoints over JMX | Possible when configured | Possible when configured | Possible when configured |
| Server-side HTTP request metrics | Available when integrated | Available when integrated | No server requests to measure in NONE mode |
| Metrics tied to a specific library | Requires matching library/bean | Requires matching library/bean | Requires matching library/bean |

“Possible” in this table indicates capability scope, not a claim that all of them are enabled by default. You must also inspect auto-configuration conditions, exposure lists, and access permissions.

## 4. How Does Boot Choose the Application Type?

Among the common starter combinations considered:

| Server-side libraries | Type Boot typically selects |
| --- | --- |
| Spring MVC from web starter | Servlet |
| WebFlux, without Spring MVC | Reactive |
| No matching web infrastructure | Non-web |

When both Spring MVC and WebFlux are present, Boot defaults to Servlet. Thus, adding WebFlux solely to use `WebClient` does not automatically switch an existing server to Reactive. [SpringApplication: Web Environment](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.web-environment).

You can specify the type explicitly:

~~~properties
spring.main.web-application-type=none
~~~

Or pass the corresponding property at runtime:

~~~powershell
java -jar app.jar --spring.main.web-application-type=none
~~~

The type-selection property does not add libraries. Forcing a web type when the project lacks required components can cause startup failure or missing capabilities you expected.

What must be verified is **the actual ApplicationContext type and created beans**, not merely one line in a config file.

## 5. Scope in Servlet Applications

### 5.1. HTTP Management Uses the Web Infrastructure

In a standard Servlet application, management endpoints attach to the HTTP serving stack. Operators can read paths like `/actuator/health` once exposed.

Path, port, and prefix are configurable. Actuator supports HTTP with Spring MVC, Spring WebFlux, and Jersey; there is no need to write custom controllers for standard endpoints. [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

One application can serve both business APIs and management endpoints. Using a separate management port is still part of a web application design, not proof that Actuator turns every NONE program into a server.

### 5.2. Capabilities Tied Specifically to Servlet Environments

Some capabilities carry specific conditions. For example, the `sessions` endpoint requires a Servlet-based web application and Spring Session. An endpoint name appearing in documentation does not guarantee it exists in every project. [Endpoint conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Similarly, container metrics depend on the active container and configuration. Do not take a Tomcat metric name and expect it to appear in an application running on a different stack.

When designing extensions, keep shared management logic separate from Servlet-API-dependent code. An operation requiring `HttpServletRequest` carries a technology coupling that a plain metric-reading operation may not need.

## 6. Scope in Reactive Applications

### 6.1. HTTP Endpoints and Shared Capabilities Still Exist

A WebFlux application can expose `health`, `metrics`, and compatible endpoints over HTTP. Calling the same URL does not mean Spring MVC handles it under the hood: the web stack and endpoint integration layer govern execution.

Business meters still use the Micrometer API. You do not convert a counter into a “reactive counter” just because business logic lives inside a Reactor pipeline.

However, the moment a measurement is updated must match actual execution. Creating a publisher does not necessarily execute work; measuring at publisher assembly time can mean something very different from measuring when work completes.

### 6.2. Health Has a Reactive Contract

`ReactiveHealthIndicator` returns `Mono<Health>` and is designed for non-blocking checks in reactive applications. This contract differs from traditional `HealthIndicator`, which returns `Health` directly. [ReactiveHealthIndicator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html).

Boot adapts traditional health contributors in reactive systems; the documentation notes executing non-reactive contributors on an elastic scheduler. This helps integrate legacy checks, yet does not turn all blocking calls across the application into non-blocking ones. [Reactive Health Indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive).

A sound mental model is:

~~~text
Reactive contract
    -> describes when the result becomes available
    -> requires an implementation suited to that execution model

Wrapping a blocking call in a reactive return type
    -> not enough to prove the work is non-blocking
~~~

The complete example in this lesson uses a synchronous indicator returning immediately to keep the comparison concise. It performs no I/O, so it does not illustrate calling a blocking database on an event loop.

### 6.3. Observation Context Must Travel with the Pipeline

When using observation or tracing in reactive flows, current context must not be assumed from a `ThreadLocal` alone. Work can resume at different times or on different threads. Use the integration and context propagation mechanisms suited to your version. [Observability and context propagation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This concerns signal accuracy, not a reason to treat Actuator as unsupported in Reactive.

## 7. Scope in Non-Web Applications

### 7.1. No HTTP Does Not Eliminate All Operational Capabilities

A command-line job can still:

- Record counters for processed records.
- Time a processing stage.
- Read component health via the chosen contract.
- Expose compatible endpoints over JMX when configured.
- Use a suitable metric exporter if required libraries and config are present.

Boot integrates Micrometer and auto-configures registries based on discovered components. Recording metrics into a registry does not require a business controller. [Metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Yet in NONE mode, Boot creates no web server to serve `GET /actuator/health`. Simply adding web exposure properties or setting `management.server.port` does not substitute for having web application infrastructure.

### 7.2. JMX Is a Management Path Independent of HTTP

Spring’s JMX support can be enabled with:

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,metrics
~~~

With default domain and naming config, `health` can be registered under ObjectName:

~~~text
org.springframework.boot:type=Endpoint,name=Health
~~~

Spring Boot JMX is disabled by default; therefore distinguish “capable of JMX support” from “MBean actually registered”. [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Furthermore, `spring.jmx.enabled=true` does not automatically open a remote management port for any host to connect. Registering MBeans, attaching a local management tool, and configuring a remote connector are separate concerns. [JDK 21: JMX management](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html).

### 7.3. Process Lifetime Affects Observability

A program finishing in a few seconds may exit before an external scraper arrives to read data. The demo below deliberately captures info inside an `ApplicationRunner` and then closes the context in non-web mode.

For a short-lived job, choose an appropriate way to persist results and export data. If an exporter’s flush interval is longer than the job’s runtime, inspect the exporter’s own flush, send, and shutdown rules. Reading a counter in-process does not prove an external system received the data.

For a long-running message consumer, lifetime is governed by its actual workload. There is no need to add fake business APIs just to have a counter or a health check.

## 8. Capabilities That Must Not Be Assumed Identical Across All Three Environments

### 8.1. Shared Endpoints vs. Technology-Specific Endpoints

`@Endpoint` defines a management capability that can be adapted to supported exposure technologies. Conversely:

- `@WebEndpoint` restricts the endpoint to HTTP.
- `@JmxEndpoint` restricts the endpoint to JMX.

Consequently, you cannot take a web-only endpoint and expect it to appear over JMX in a NONE program. [WebEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html), [JmxEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html).

Capabilities such as reading log files, capturing heap dumps, or serving Prometheus format each have their own exposure rules and conditions. Do not treat an endpoint table as universally available regardless of web type and libraries.

### 8.2. Exposing Endpoints Differs from Exporting Metrics

These three actions are distinct:

~~~text
Record a meter into a registry
Read the registry through the metrics endpoint
Export metrics via a registry integrated with an external system
~~~

Similarly, exposing Actuator endpoints as MBeans does not mean Micrometer is configured to expose every individual meter as a separate MBean. Check which component handles that.

When an application has no web layer, choose a collection design matching how it actually delivers data. A tool that only scrapes HTTP URLs cannot pull data from a server-less program merely because the program increments a counter.

### 8.3. Security Must Match the Active Access Mechanism

HTTP access rules for Servlet and Reactive belong to their respective security stacks. HTTP rules do not automatically protect a remote JMX connection either.

In this exercise, the web server binds only to loopback and adds no Spring Security library. When moving management capabilities into a deployed environment, integrate them with that environment’s management access control.

## 9. Complete Example: Same Code, Swapping Web Library Sets

The example uses one standalone project with three **Maven profiles**:

- `nonweb`: uses only common dependencies, adding no web starter.
- `servlet`: adds the web starter.
- `reactive`: adds the WebFlux starter.

These are Maven build profiles, not Spring profiles from `spring.profiles.active`. Select only **one** Maven profile per run and run a clean build to avoid picking up a JAR from a previous run.

Structure:

~~~text
actuator-scope/
├── pom.xml
└── src/main/
    ├── java/example/actuatorscope/ActuatorScopeApplication.java
    └── resources/application.yml
~~~

You need JDK 21, Maven, and dependency download access on the first build.

### 9.1. The pom.xml File

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
    <artifactId>actuator-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <profiles>
        <profile>
            <id>nonweb</id>
        </profile>
        <profile>
            <id>servlet</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-web</artifactId>
                </dependency>
            </dependencies>
        </profile>
        <profile>
            <id>reactive</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-webflux</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
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

The shared code does not import Servlet or Reactor types. Thus it compiles against all three dependency sets.

### 9.2. The Java File

File `src/main/java/example/actuatorscope/ActuatorScopeApplication.java`:

~~~java
package example.actuatorscope;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorScopeApplication {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(ActuatorScopeApplication.class, args);
        if (!(context instanceof WebServerApplicationContext)) {
            context.close();
        }
    }

    @Bean
    HealthIndicator demoHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    ApplicationRunner probe(ApplicationContext context,
                            MeterRegistry meters, MBeanServer mbeans) {
        return args -> {
            Counter work = meters.counter("demo.work.units", "source", "probe");
            work.increment();
            HealthIndicator demo =
                context.getBean("demoHealthIndicator", HealthIndicator.class);

            System.out.println("context=" + context.getClass().getSimpleName());
            System.out.println("web.server=" + (context instanceof WebServerApplicationContext));
            System.out.println("demo.health=" + demo.health().getStatus().getCode());
            System.out.println("work.units=" + (long) work.count());
            System.out.println("jmx.health=" + mbeans.isRegistered(
                new ObjectName("org.springframework.boot:type=Endpoint,name=Health")));
        };
    }
}
~~~

`demoHealthIndicator` always returns `UP` to illustrate a health contributor. It checks no external resource and is not a complete check for a real system.

The runner increments a counter once, reads the indicator, and checks whether the health MBean is registered. It does not rely on an HTTP request to perform these actions.

At the end of `main`, the program closes the context when it is not a web application context. In the two web modes, the context stays open so you can make HTTP calls from another terminal.

### 9.3. The Configuration File

File `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    banner-mode: "off"
  jmx:
    enabled: true

logging:
  level:
    root: "OFF"

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
    jmx:
      exposure:
        include: health,metrics
  endpoint:
    health:
      show-details: never
~~~

JMX configuration is explicit so all three runs can verify the MBean. The HTTP exposure list takes effect only when suitable web infrastructure is present.

Logging and the banner are disabled so comparison output stays easy to read. That is a choice for this lab exercise, not advice to turn off logging in deployed applications.

### 9.4. Non-Web Run

In the directory containing `pom.xml`:

~~~powershell
mvn -q -Pnonweb clean package
java -jar target/actuator-scope-1.0.0.jar --spring.main.web-application-type=none
~~~

Program output:

~~~text
context=AnnotationConfigApplicationContext
web.server=false
demo.health=UP
work.units=1
jmx.health=true
~~~

The program exits after printing and closing the context. The example has no web server to accept HTTP requests.

This output proves three things in the same runtime: the indicator can be invoked, the meter can be updated, and the health MBean can be registered without a web server.

You cannot open JConsole after the process has exited and expect to manage that process’s MBeans. `jmx.health=true` is a registration check performed **while the context is still active**.

### 9.5. Servlet Run

~~~powershell
mvn -q -Pservlet clean package
java -jar target/actuator-scope-1.0.0.jar
~~~

Output:

~~~text
context=AnnotationConfigServletWebServerApplicationContext
web.server=true
demo.health=UP
work.units=1
jmx.health=true
~~~

Keep this terminal running, open a second terminal, and call:

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/health
~~~

In an environment where default health checks pass, the response body is:

~~~json
{"status":"UP"}
~~~

To check the counter incremented by the runner:

~~~powershell
$metric = Invoke-RestMethod -Uri "http://127.0.0.1:8080/actuator/metrics/demo.work.units"
$count = $metric.measurements | Where-Object { $_.statistic -eq "COUNT" }
[int]$count.value
~~~

Result:

~~~text
1
~~~

Reading the counter does not increment `demo.work.units`. The increment code sits in the runner, which executes once per sample startup.

Stop the application with `Ctrl+C` before moving to the next run to release the port and JAR file in use.

### 9.6. Reactive Run

~~~powershell
mvn -q -Preactive clean package
java -jar target/actuator-scope-1.0.0.jar
~~~

Output:

~~~text
context=AnnotationConfigReactiveWebServerApplicationContext
web.server=true
demo.health=UP
work.units=1
jmx.health=true
~~~

Reuse the two HTTP checks from the Servlet run. Under the same health conditions, you receive health `UP` and a counter value of `1`.

The management HTTP API uses the same paths in the sample configuration. The key difference is that the running context and server infrastructure belong to a Reactive application.

`curl.exe` invokes the cURL program on Windows to avoid aliases in some PowerShell versions. On Linux or macOS, use `curl`. The `Invoke-RestMethod` snippet is written for PowerShell.

### 9.7. Why Not Run `javac` Directly on One File?

The Java file needs Spring Boot, Actuator, Micrometer, and the dependencies of each Maven profile. A `javac` command without that classpath will fail to compile.

In the example, `mvn clean package` resolves dependencies, compiles with the configured JDK, and packages an executable JAR. `java -jar` then runs the exact artifact from each build.

If port `8080` is already occupied, change `server.port` or pass `--server.port=<available port>` when launching the two web builds, and update the test URLs accordingly.

## 10. Reading Evidence Within Its True Scope

| Observation in example | Can be concluded | Cannot be concluded |
| --- | --- | --- |
| NONE still prints `work.units=1` | Counters work without HTTP requests | An external system has stored the metric |
| NONE prints `jmx.health=true` | Health MBean was registered during runtime | A remote JMX connector was opened |
| Both Servlet and Reactive serve health over HTTP | Both stacks support exposing this endpoint in the sample config | Every endpoint exists in both |
| All three runs print `demo.health=UP` | The sample indicator returns per its definition | All external resources are working |
| Both web builds share the same URL | Caller-facing view is consistent in this config | Same framework or internal execution model |

Separating these conclusions keeps you from adding a web starter merely to solve a metric-recording need that never required HTTP.

## 11. Common Confusions and How to Diagnose

### “Adding the Actuator starter automatically opens port 8080”

Inspect server dependencies and application type. The Actuator starter does not replace a web starter. The `nonweb` run in the example is a direct way to verify this.

### “I configured web exposure, so the NONE program must have URLs”

The exposure list selects endpoints for an exposure mechanism whose prerequisites are active. It does not create a web server inside an application running in NONE mode.

When no server is listening, a connection error is not the same situation as a `404` returned by a server that received the request.

### “Having WebFlux in dependencies guarantees a Reactive server”

Check whether Spring MVC is on the classpath, whether a property forces the web type, and which context is actually created. The app might only pull in WebFlux for an HTTP client while the server remains Servlet.

### “Setting management port to -1 is equivalent to NONE”

`management.server.port=-1` disables management HTTP exposure under that configuration. It does not declare the entire application non-web: business APIs of a Servlet/Reactive application are still separate. [Disabling HTTP management](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

### “Reactive support means every check is non-blocking”

Inspect the contract and implementation of each check. A method returning a reactive type that executes blocking I/O right before returning still requires proper handling.

### “No MBean means Actuator does not support this application”

Check `spring.jmx.enabled`, the JMX exposure list, whether the endpoint is enabled, and bean creation conditions. Do not infer an architectural limitation from a config that has not enabled the exposure mechanism.

### “Short-lived job metrics will surely be collected automatically”

Check process lifetime, exporter, and receiver. For work that exits quickly, pick a suitable storage/export strategy rather than expecting an HTTP scrape against a process that is no longer running.

## 12. Choosing How to Apply and Self-Check

Decision guide by need:

| Application | Actual need | Design direction |
| --- | --- | --- |
| Existing Spring MVC API | Read health and metrics over HTTP | Use Actuator integration on the existing Servlet stack |
| WebFlux service | Expose management while keeping checks reactive-friendly | Use WebFlux integration; review health contracts and context propagation |
| Short-lived import job | Know processed counts and outcome after completion | Record metrics/results, choose lifecycle-appropriate storage or export |
| Long-running message consumer without HTTP | Monitor activity and resources | Choose JMX or an appropriate metric exporter; add HTTP only when specifically required operationally |

**Exercise 1:** Using the `servlet` build, run with `--spring.main.web-application-type=none`. Predict `web.server` and HTTP reachability.

Key explanation: the web library is still inside the JAR, yet forcing NONE mode prevents the app from starting as a web application. Having a library present and using that web stack are two different things.

**Exercise 2:** Disable `spring.jmx.enabled` in the example and observe what happens.

The sample code injects an `MBeanServer` bean into the runner. Therefore, disabling JMX can cause the example to fail dependency injection rather than simply printing `false`. That is a constraint of the verification code, not proof that counters require JMX. Remove the JMX check before reusing the sample to test meters alone.

**Exercise 3:** A WebFlux application serves `/actuator/health` yet has no metric whose name starts with `tomcat.`. What should you verify?

Verify the actual server in use and conditions for that metric. Supporting Actuator over HTTP does not produce the exact same server-specific metric set across every server.

**Exercise 4:** A NONE program increments a counter properly, yet a collector that only scrapes HTTP URLs cannot retrieve the metric. What must change?

Re-evaluate how data is delivered to that collector or pick a different collection mechanism. Never ignore the boundary between recording metrics in-process and exposing metrics over a specific protocol.

After this lesson, whenever evaluating an Actuator capability, identify **the actual web type, component conditions, and exposure mechanism**. Only those three facts together tell you how a capability can be used in your application.
