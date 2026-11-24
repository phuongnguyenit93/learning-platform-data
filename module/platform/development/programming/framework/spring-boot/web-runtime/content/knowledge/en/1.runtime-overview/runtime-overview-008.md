# Prerequisites and learning progression from application startup to operations

This lesson provides a learning roadmap for the **Spring Boot web runtime**: from prerequisites, creating and starting the Java process, tracing an HTTP request, to testing, deployment, observability, and troubleshooting. The goal is to understand **why the application runs and how to know it is serving properly**, rather than merely getting the startup command to run.

## 1. What should you be able to do after this lesson?

1. State the minimal Java, HTTP, and Spring prerequisites needed to follow the web runtime.
2. Explain the roles of the JVM, **SpringApplication**, **ApplicationContext**, beans, auto-configuration, and the embedded HTTP server.
3. Describe the request/response path in a Spring MVC application; recognize how WebFlux differs.
4. Run a small application yourself, invoke endpoints, read configuration/startup errors, and test the HTTP flow.
5. Identify operational signals to monitor: health, readiness/liveness, logs, metrics, graceful shutdown, and environment configuration.
6. Study topics in dependency order, with verifiable output evidence at each stage.

**Scope boundary:** focuses on the lifecycle and operational readiness of a Spring Boot web application. Authentication/authorization mechanisms, database optimization, advanced cloud deployment, and distributed systems design are follow-up tracks once the core runtime is understood.

## 2. Prerequisites

### 2.1. Java and JVM

- **Java 17 or later:** classes, methods, interfaces, records, generics, collections, exceptions; ability to read stack traces to locate root causes.
- **Compilation and execution:** distinguish `.java` source code, `.class` bytecode, JARs, and the JVM; understand the classpath, dependencies, and the JDK version running the program.
- **Threads and resources:** understand threads executing work, blocking I/O, timeouts, and heap/GC conceptually. Deep tuning is not yet required, but recognize that each request consumes runtime resources.
- **Annotations and reflection:** understand that annotations provide metadata for the framework to discover configuration, web mappings, and injection; annotations do not execute business logic by themselves.

If you are unfamiliar with `record` syntax, simply think of a **record** as a concise way to declare an immutable data type for payloads; the hands-on example uses a record as a JSON response.

### 2.2. HTTP, JSON, and basic networking

- **Client/server:** browsers or `curl` send requests to the host address and port the server listens on; DNS, TCP, TLS/HTTPS, and reverse proxies are involved layers in real deployments.
- **Request:** method (GET, POST, PUT, PATCH, DELETE), path, query, headers, body, and Content-Type; **response:** status, headers, and body.
- **Status:** 2xx success; 400 usually invalid request; 401 unauthenticated; 403 insufficient permissions; 404 route/resource not found; 5xx server-side error.
- **JSON:** objects, arrays, strings, numbers, booleans, null; understand mapping between JSON and Java DTOs. Be able to read HTTP logs and use `curl` or an HTTP client to reproduce issues.
- **Statelessness:** requests may be served by different instances; avoid relying on controller fields to hold per-user data.

For example, **GET /api/ping** requests checking a path; the server returns **200 OK** with JSON upon success. A 200 endpoint alone does not prove the entire business system is ready.

### 2.3. Essential Spring Framework concepts

- **IoC/Dependency Injection:** Spring creates, manages, and wires beans; prefer constructor injection to expose dependencies explicitly and facilitate testing.
- **ApplicationContext:** stores beans and manages configuration, events, and lifecycle; do not conflate it with the servlet container or JVM.
- **Component scanning:** components usually live in the main application class's package and subpackages; package placement affects controller/service discovery.
- **Conditional configuration:** starters provide dependencies; auto-configuration can create beans based on classpath, properties, and existing beans. Adding a starter does not mean every feature enables unconditionally.
- **Web mapping:** annotations such as `@RestController`, `@GetMapping`, `@RequestBody` connect URLs, HTTP data, and Java methods.

### 2.4. Practical tooling

JDK 17+ along with a Gradle wrapper or Maven wrapper in the project, an IDE, terminal, `curl` (or equivalent HTTP tool), Git, and the ability to inspect environment variables/logs. Know how to run **java -version** and **./gradlew --version** (on Windows, use **gradlew.bat --version**) to verify the environment. No separate Tomcat installation is required if the project uses an embedded server via the appropriate starter.

## 3. Runtime map: from main() to HTTP response

### 3.1. Startup flow

~~~text
Run command / java -jar
       |
       v
JVM loads classes and invokes main()
       |
       v
SpringApplication.run(...)
       |
       +--> prepare Environment, profiles, and configuration
       +--> create/refresh ApplicationContext
       +--> scan components, process auto-configuration, instantiate beans
       +--> build web application context and embedded web server
       +--> execute registered runners, emit ready signal
       |
       v
Application ready to serve traffic once readiness conditions are met
~~~

**@SpringBootApplication** combines Spring Boot configuration, enabling auto-configuration, and component scanning. **SpringApplication.run(...)** orchestrates context creation. The embedded server (typically Tomcat for Spring MVC; Reactor Netty commonly for WebFlux) opens a port to accept HTTP connections. Exact ordering among callbacks depends on context lifecycle, so rely on actual events/logs rather than assuming all beans run in an arbitrary fixed order.

**ApplicationStartedEvent** and **ApplicationReadyEvent** do not mean the same thing: after context refresh, runners may still be executing; ready indicates initialization for receiving traffic has reached its final stage. If bean creation fails, the port is occupied, required configuration is missing, or a runner throws an error, startup can fail. Startup errors typically surface in the deepest meaningful **Caused by** clause in the stack trace and Spring Boot's Failure Analysis when provided.

### 3.2. Request flow with Spring MVC (Servlet)

~~~text
HTTP client
   |
   v
Embedded Servlet container (e.g., Tomcat)
   |
   v
Servlet Filter chain (may include Spring Security)
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping selects endpoint
   +--> argument resolvers / HTTP message converters read data
   +--> @RestController calls service and needed dependencies
   +--> converts Java result to JSON / response
   +--> handles exceptions via MVC mechanism on error
   |
   v
HTTP status + headers + body returned to client
~~~

In the standard Servlet model, requests are handled by threads from the container pool; calling slow services or blocking I/O holds a thread's resources during the wait. Controllers should receive/validate requests and coordinate, services should hold business logic, and repositories or clients should communicate with external dependencies. Do not put all logic in controllers just because a simple example runs.

**Spring WebFlux** has a reactive pipeline (`WebFilter`/`DispatcherHandler`) and types such as `Mono`/`Flux`; when running on an event loop, carelessly calling blocking I/O can stall many requests. WebFlux and MVC have different execution models; learn HTTP and bean fundamentals before comparing them. A project with both starters may apply web-application-type selection rules differently than guessed; include only the stack matching your goal.

## 4. End-to-end hands-on exercise: create, run, call, and test a web application

This example uses **Spring Boot 3.x, Java 17+**, and Spring MVC. Generate a project from **https://start.spring.io** using Gradle (Groovy), group **com.example**, artifact **runtime-demo**, package **com.example.runtimedemo**; select **Spring Web**, **Spring Boot Actuator**, and **Spring Boot Starter Test**. Use the Gradle wrapper generated with the project. If choosing another Boot version, ensure compatible dependencies and JDK version.

### 4.1. Application entry point

Create **src/main/java/com/example/runtimedemo/RuntimeDemoApplication.java**:

~~~java
package com.example.runtimedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }
}
~~~

This class sits in the parent package so component scanning detects controllers in the same package. The `main` method is where the JVM starts; Spring Boot handles building the context and server.

### 4.2. Endpoint and JSON payload

Create **src/main/java/com/example/runtimedemo/PingResponse.java**:

~~~java
package com.example.runtimedemo;

public record PingResponse(String status) {
}
~~~

Create **src/main/java/com/example/runtimedemo/PingController.java**:

~~~java
package com.example.runtimedemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public PingResponse ping() {
        return new PingResponse("ok");
    }
}
~~~

**@RestController** registers a handler returning response content directly; **@GetMapping** maps GET to the path; Jackson from Spring Web converts **PingResponse** to JSON. This sample uses no database, making the HTTP lifecycle clear before adding external dependencies.

### 4.3. Runtime configuration

Put the following in **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: runtime-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**server.port** selects the default port; **server.shutdown=graceful** gives the runtime time to finish in-flight requests upon an appropriate stop signal; the timeout caps how long each phase waits. Actuator provides health signals and probes. The example exposes only **health,info** over the web; do not expose all management endpoints to the Internet. When security is enabled, restrict access and network reachability to operational endpoints.

Spring Boot configuration can come from files, profiles, environment variables, system properties, and command-line arguments. For the simple property in the example, **SERVER_PORT=9090** is one way to override the port via environment variable; command-line argument **--server.port=9091** has higher precedence by default. Never hardcode passwords/tokens in the repository; supply secrets via your deployment environment's secure configuration mechanism.

### 4.4. Running and observing results

From the project root directory, on Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell or Command Prompt:

~~~text
gradlew.bat bootRun
~~~

In another terminal, call:

~~~bash
curl -s http://localhost:8080/api/ping
~~~

Exact response body of the example:

~~~json
{"status":"ok"}
~~~

With a healthy server and no failing health contributors, the command:

~~~bash
curl -s http://localhost:8080/actuator/health
~~~

typically returns JSON with **status=UP**, such as:

~~~json
{"status":"UP"}
~~~

Health values may vary if the application adds dependencies, health indicators, or detailed response configuration. You can also check **/actuator/health/liveness** and **/actuator/health/readiness** because the example enables health probes. **Liveness** reflects whether the process is alive; **readiness** reflects whether it is ready to receive traffic. By default, readiness does not automatically check every external dependency; if you need to evaluate a DB or message broker, design and configure appropriate health groups/indicators.

When seeing a 404 error, check the method and path first; on connection refused, check if the process is running, the actual port, and binding/networking. If 8080 is occupied, stop the conflicting process or change the port intentionally via configuration.

### 4.5. Testing over real HTTP on a random port

Create **src/test/java/com/example/runtimedemo/PingIntegrationTest.java**:

~~~java
package com.example.runtimedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingIntegrationTest {
    @Autowired
    private TestRestTemplate client;

    @Test
    void pingReturnsOk() {
        ResponseEntity<PingResponse> response =
                client.getForEntity("/api/ping", PingResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("ok", response.getBody().status());
    }
}
~~~

The test launches Spring Boot on a random port, sends an HTTP request, and asserts status/payload. Run the commands:

~~~bash
./gradlew test
./gradlew bootJar
java -jar build/libs/runtime-demo-0.0.1-SNAPSHOT.jar
~~~

The illustrated JAR name matches the default artifact and **0.0.1-SNAPSHOT** version of the newly created project; if you change the version, use the actual artifact name. **bootRun** runs via Gradle for development, whereas **java -jar** runs the executable Boot JAR for deployment. Do not equate basic HTTP tests with full verification of functionality, security, databases, and system load.

## 5. Recommended learning sequence: evidence-based progression

| Stage | Study in order | Verifiable exercise |
| --- | --- | --- |
| 0. Foundations | Java/JVM, Gradle/Maven, HTTP/JSON, ports and logs, IoC/DI | Explain an HTTP request/response and how a bean is injected |
| 1. Creation & startup | Starters, main(), @SpringBootApplication, SpringApplication, auto-configuration, context, and embedded server | Run bootRun, identify the log line showing the listening port and cause if startup fails |
| 2. Web flow | MVC, DispatcherServlet, controllers, mappings, JSON, status codes, filters, and exception handling | Call GET /api/ping, read JSON, and distinguish 200/404/500 |
| 3. Configuration | application.yml, profiles, environment, overrides, separating secrets | Change port via environment variable; explain which value wins and why |
| 4. Request quality | DTOs, validation with suitable starter, structured API errors, service boundaries | Have both passing tests and clear error-response tests without leaking stack traces |
| 5. Runtime testing | Unit tests, web-slice tests, integration tests, random port, stubbing dependencies | ./gradlew test passes and catches an intentional regression |
| 6. Observability & protection | Actuator health, liveness/readiness, logs, metrics, timeouts, graceful shutdown | Analyze a scenario where the process is alive but should not receive traffic |
| 7. Packaging & operations | bootJar, environment profiles, external config, deploy/restart/rollback, capacity | Run JAR, inspect logs/health, and describe safe stop or rollback |

**How to study:** at each stage, preserve a runnable version of the code, the commands executed, and concrete evidence (HTTP responses, test results, or logs). Only add databases, security, async, or external APIs after confirming the basic web lifecycle; whenever adding a dependency, update both tests and error observability.

## 6. From development machine to running application in operations

### 6.1. Successful startup differs from stable serving

A live JVM can still experience exhausted connection pools, slow downstreams, full queues, or business logic errors. Therefore, distinguish **liveness** (not hung/broken per defined criteria), **readiness** (able to accept more traffic), **overall health**, and **actual API success rate/latency**. Never use a single `UP` result to claim all functionality is working.

When using an orchestrator like Kubernetes, configure probe paths and timings appropriately; avoid putting flaky dependencies into liveness checks as that can trigger restart loops. Readiness should accurately reflect whether the service can handle traffic under the real architecture, including warm-up time if applicable.

### 6.2. Configuration, security, and dependencies

- Separate development/staging/production configurations, use profiles intentionally, and verify active profiles in logs/`Environment` when debugging. Environment variables are one override source, not the sole place to store secrets.
- Do not commit credentials; configure timeouts for HTTP clients, databases, and downstreams; use proper connection pools whenever the app performs external I/O.
- Configure authentication, authorization, TLS, CORS, proxy headers, and payload limits per system requirements. Security filters can change status/path before requests reach controllers.
- Ensure hostnames and networking match the environment: **localhost** inside a container refers to the container itself, not automatically to a database or service on the host machine.
- For stateful applications, store sessions/data appropriately if scaling across multiple instances; avoid mutable fields shared across requests in singleton beans.

### 6.3. Observe before optimizing

**Logs:** record startup events, errors with server-side stack traces, and request identifiers/correlation when needed; classify log levels; never log tokens, passwords, or sensitive data carelessly. In containers, typically write logs to stdout/stderr for log collection.

**Metrics:** at minimum track request rate, error rate, latency (e.g., p95/p99), CPU, memory/heap, GC, threads, connection pools, and external dependencies when present. Micrometer/Actuator support exporting metrics when configured; do not assume all metrics are exposed over HTTP by default.

**Traces:** when multiple services are involved, use trace IDs to correlate calls across steps; distinguish traces from logs and metrics. Read evidence before increasing threads, heap, or replica counts; adding resources does not fix blocking logic or poor queries.

### 6.4. Deploy and shutdown lifecycle

~~~text
Update code + config
   -> test + build artifact
   -> deploy with right env vars/secrets
   -> JVM starts, context/server created
   -> readiness allows traffic
   -> monitor logs, metrics, errors, and latency
   -> stop needed: drain new traffic, graceful shutdown
   -> verify new instance healthy or rollback if needed
~~~

In production, account for ports, health/readiness probes, CPU/RAM limits, stop signals (such as SIGTERM), load balancer/orchestrator timeouts, open resources, startup time, and rollback mechanisms. **Graceful shutdown** is only effective within its timeout and depending on how clients/downstreams behave; it does not guarantee every long request will finish. Test restart scenarios under moderate load to observe real behavior.

## 7. Common incidents: symptom → where to check → resolution

| Symptom | Check first | Resolution |
| --- | --- | --- |
| Cannot bind port, Address already in use | Startup logs, server.port, listening processes | Stop conflicting process or assign appropriate port for the environment |
| No qualifying bean / Unsatisfied dependency | Exception root cause, package scan, auto-config conditions | Fix dependency/bean/config; do not add overly broad component scans arbitrarily |
| GET returns 404 | Host, port, context path, method, @GetMapping, component scan | Fix path or registered handler |
| POST returns 400 or 415 | Content-Type, JSON syntax, DTO, validation, converter | Align request and contract; return helpful error messages |
| Request returns 500 | Server logs, root exception, downstream timeout | Fix root cause; apply uniform error handling and avoid leaking stack traces to clients |
| Health UP but users hit errors | API latency/error rate, readiness group, dependencies, business checks | Add appropriate signals, investigate downstreams and business flows |
| Actuator endpoint unreachable | Dependency, exposure, base path, security, management port | Configure exposure and access controls accurately |
| Works locally, fails in container | Port binding, env/profile, host DNS, filesystem, secrets | Compare config and logs across environments, verify actual networking |

When debugging, reproduce with a specific request, record **timestamp, URL/method, status, request ID, and logs at that exact moment**, and distinguish startup failures from request-time errors. If an issue only appears under load, inspect threads/blocking, pools, timeouts, and metrics before making random edits.

## 8. Readiness checklist before moving to advanced modules

- [ ] I can explain **JVM → SpringApplication → ApplicationContext → embedded server** in my own words.
- [ ] I know how requests pass through filters/`DispatcherServlet`/controllers and how responses are serialized in MVC.
- [ ] I can run the example, receive **{"status":"ok"}**, and explain the HTTP status and JSON.
- [ ] I can run at least one HTTP integration test and executable JAR.
- [ ] I know where profiles/configs come from, how to change ports, and how to keep secrets out of code.
- [ ] I distinguish health, liveness, and readiness from actual user API experience, and know the limits of each signal.
- [ ] I know how to read startup errors, failed-request logs, and follow a basic stop/restart/rollback plan.

### Quick self-check

**1. Why can `main()` run yet still fail to serve HTTP?** Because context/bean creation, configuration, server port binding, or runners can fail; process liveness and readiness state must be observed separately.

**2. Are starters and auto-configuration the same thing?** No. Starters bundle convenient dependencies; auto-configuration applies configuration based on runtime/classpath/property conditions.

**3. Why is a test returning 200 not enough to deploy?** That test verifies only one path; production also requires readiness, configuration, security, dependencies, load handling, observability, and recoverability.

**4. Should I learn MVC or WebFlux first?** Learn request/response basics, IoC/DI, lifecycle, and MVC first to grasp the fundamentals, then learn WebFlux when non-blocking/reactive requirements arise and you understand managing blocking I/O.

After completing these verifiable exercises, you have the foundation to dive deeper into Servlet filters/Spring Security, WebFlux, data access, resilience, Actuator/observability, and production deployments tailored to your system's needs.