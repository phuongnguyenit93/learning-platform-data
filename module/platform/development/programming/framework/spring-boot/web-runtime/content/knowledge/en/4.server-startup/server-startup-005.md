# WebServerInitializedEvent and Retrieving the Actual Port After Startup

## 1. The Problem: The Configured Port May Differ from the Listening Port

When a Spring Boot web application starts, the embedded HTTP server (such as Tomcat in Spring MVC or Reactor Netty in Spring WebFlux) must bind to an address/port to accept connections.

Distinguish three values:

- **Configured port:** the `server.port` value in `application.properties`/`application.yml`, environment variables, or startup arguments. When uncustomized, a Spring Boot application's HTTP port is typically **8080**.
- **Actual port:** the port number that the embedded web server actually binds to successfully on the machine running the application.
- **Public port:** the port external clients access through Docker port mapping, a reverse proxy, a load balancer, Kubernetes Service/Ingress, or NAT. This value can differ from the internal port.

For example, `server.port=8080` typically results in actual port 8080 if the application starts successfully. However, `server.port=0` means **asking the operating system to pick an available port**: the actual port will be a positive number assigned by the operating system, varying across runs.

Reading `server.port` from configuration in that case yields only **0**, not telling you which port clients need to call. Spring Boot solves this with **`WebServerInitializedEvent`**, published once the embedded web server is ready. From the event, you directly read the port being used by the server.

## 2. What Is `WebServerInitializedEvent`?

In Spring Boot 3.3.x, `org.springframework.boot.web.context.WebServerInitializedEvent` is the common event class published when a `WebServer` is ready. Its typical purpose is to let code discover the server's actual local port after initialization.

Key APIs:

| API | Meaning |
|---|---|
| `WebServerInitializedEvent` | Lifecycle event when an embedded web server has initialized |
| `event.getWebServer()` | Retrieves the `WebServer` that emitted the event |
| `event.getWebServer().getPort()` | Retrieves that server's actual port |
| `event.getApplicationContext()` | Retrieves the `WebServerApplicationContext` that created the server |
| `event.getApplicationContext().getServerNamespace()` | Identifies the namespace, helping distinguish the main server from the management server |
| `ApplicationListener<WebServerInitializedEvent>` | Way to register a listener as a Spring bean |
| `@EventListener` | Annotation-based way to write an event-receiving callback |

Common subclasses:

- **`ServletWebServerInitializedEvent`** for the Servlet stack / Spring MVC.
- **`ReactiveWebServerInitializedEvent`** for the reactive stack / Spring WebFlux.

Both are `WebServerInitializedEvent`, so a listener that only calls `getWebServer().getPort()` typically does not need to depend directly on Tomcat, Netty, or the Servlet/Reactive subclass.

**This is not an HTTP request event.** It is published during startup, without any user calling an endpoint.

## 3. Where Does the Event Occur in Startup?

```text
main() → SpringApplication.run(...)
       │
       ├── Create and refresh ApplicationContext
       ├── Create/configure beans and web infrastructure
       ├── Prepare embedded web server
       │
       ├── Embedded web server begins listening
       │       │
       │       └── Publish WebServerInitializedEvent
       │                   │
       │                   └── Listener reads event.getWebServer().getPort()
       │
       ├── Complete remaining startup steps
       ├── ApplicationStartedEvent / ApplicationRunner / CommandLineRunner
       ├── ApplicationReadyEvent
       └── SpringApplication.run(...) returns
```

The diagram shows the conceptual path of a typical Spring Boot startup. `WebServerInitializedEvent` indicates that the web server has initialized so its port can be read; **it does not guarantee the entire application and external dependencies are ready to serve business traffic**. For instance, runners may still be executing, the database may not be reachable yet, or health/readiness checks may not pass yet.

`ApplicationReadyEvent` signifies that SpringApplication has completed startup and application/command-line runners, but it still does not replace actual readiness checks.

If port binding fails (for example, a fixed port is occupied by another application), the server does not initialize successfully, so you should not expect a success event to yield a port. If `spring.main.web-application-type=none` is configured, there is no application embedded HTTP server to publish this event.

## 4. Complete Example: An App That Picks a Port and Prints the Actual Port

The example uses Java 17, Spring Boot 3.3.13, and Spring MVC (`spring-boot-starter-web`). The application uses `server.port=0` and provides a `GET /ping` endpoint. No database or Actuator is required to run the basic example.

Structure:

```text
web-port-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/webport/WebPortApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/webport/WebPortApplicationTests.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
# The operating system will choose an available port.
server.port=0
```

**`src/main/java/com/example/webport/WebPortApplication.java`:**

```java
package com.example.webport;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebPortApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebPortApplication.class, args);
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> logApplicationPort() {
        return event -> {
            // In typical setups, null is the main app server's namespace.
            // A separate management server usually has namespace "management".
            if (event.getApplicationContext().getServerNamespace() != null) {
                return;
            }

            int port = event.getWebServer().getPort();
            System.out.println("APP_PORT=" + port);
        };
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

This is a **valid single Java file**: only `WebPortApplication` is a top-level public class, while `PingController` is a top-level package-private class in the same package. `@SpringBootApplication` enables auto-configuration and component scanning; `@RestController` registers the endpoint and the `@Bean` method registers the listener.

The key line is:

```java
int port = event.getWebServer().getPort();
```

`getPort()` retrieves the port from the server that actually emitted the event. Checking the namespace ensures the example only logs the main server's port in a standard Boot app; secondary servers are explained in section 8.

**Run the application:**

```bash
gradle bootRun
```

Use a Gradle version compatible with Boot 3.3 and JDK 17+, or the Gradle Wrapper if your project has one: `./gradlew bootRun` (macOS/Linux), `.\gradlew.bat bootRun` (Windows PowerShell).

Logs may contain lines like:

```text
... Tomcat started on port 53147 (http) ...
APP_PORT=53147
... Started WebPortApplication ...
```

**53147 is only an illustrative number; do not expect it as a fixed result.** Spring/Tomcat log content and order can also vary by configuration. What matters is that the listener prints `APP_PORT=...` with the newly assigned port once the web server initializes.

Using the printed port (suppose 53147), call:

```bash
curl -i http://localhost:53147/ping
```

Expected response: **HTTP 200** and JSON body:

```json
{"message":"pong"}
```

If a different port is printed, substitute that number in the URL. The example does not automatically expose a public port through a firewall/container; it only demonstrates that the internal web server is listening.

## 5. Writing a Listener with `@EventListener`

A Spring bean can listen for the event via annotation, without writing a `@Bean ApplicationListener`:

```java
package com.example.webport;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class PortObserver {

    @EventListener
    void onWebServerInitialized(WebServerInitializedEvent event) {
        if (event.getApplicationContext().getServerNamespace() == null) {
            int actualPort = event.getWebServer().getPort();
            System.out.println("OBSERVED_PORT=" + actualPort);
        }
    }
}
```

This is an **alternative approach**; do not keep both listeners in the example app simultaneously unless you want two lines printed. To run this approach alone, save `PortObserver.java` in the same package and remove the `logApplicationPort()` method from `WebPortApplication`.

With Spring's default event multicaster configuration, callbacks normally execute synchronously on the event-publishing thread. Do not perform long-running network calls, wait loops, or heavy blocking tasks inside the listener, as that can slow down startup. Asynchronous listeners/multicasters can change thread behavior, but must be configured intentionally.

## 6. Three Ways to Read the Port and Their Timing

### 6.1. Reading from the `server.port` Property

For example, a bean uses:

```java
@Value("${server.port:8080}")
private int configuredPort;
```

With `server.port=0`, this variable equals **0**, not the actual port. With a fixed value of 8080, the bean knows the intended value, which does not prove binding succeeded. Reading the property is appropriate when you need the configured setting, not for discovering a dynamic port after startup.

### 6.2. Reading from `WebServerApplicationContext` After `SpringApplication.run`

After calling `SpringApplication.run`, code holding the context can also query the server:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

// Replaces the body of main() in the example:
ConfigurableApplicationContext context =
        SpringApplication.run(WebPortApplication.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    int port = webContext.getWebServer().getPort();
    System.out.println("PORT_AFTER_RUN=" + port);
}
```

This is an **illustrative snippet placed inside `main`**, not a standalone Java file. It works because `run` returns only after startup has finished. If you want a callback right when the web server becomes ready, a `WebServerInitializedEvent` listener expresses the intent more clearly. Do not call `getWebServer().getPort()` while a bean is still being created without knowing whether the server exists yet, because `getWebServer()` may not return a server yet.

### 6.3. In Integration Tests: Use `@LocalServerPort`

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot provides a dedicated annotation to inject the actual port into a **test**:

```java
package com.example.webport;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebPortApplicationTests {

    @LocalServerPort
    int port;

    @Test
    void serverUsesAnAssignedPort() {
        assertTrue(port > 0);
    }
}
```

Save the file at `src/test/java/com/example/webport/WebPortApplicationTests.java`. Run `gradle test` or the corresponding command via the Gradle Wrapper. The test starts a real HTTP server on an OS-assigned port and verifies the port is positive.

**Note:** the Boot 3.3 import is `org.springframework.boot.test.web.server.LocalServerPort`. This annotation relates to the `local.server.port` property, which is only available **after** the server is initialized. Do not inject `@LocalServerPort` or `@Value("${local.server.port}")` into a regular application bean during bean initialization; the property may not exist at that time. Use an event listener for runtime code, and `@LocalServerPort` for tests with a real server.

`@SpringBootTest(webEnvironment = MOCK)` does not start a network server and therefore has no real port to inject.

## 7. Using the Actual Port: What Makes Sense and What Causes Confusion?

Practical use cases:

1. **Logging/debugging:** displaying the listening port of an instance in local/dev environments when using `server.port=0`.
2. **Integration tests:** constructing an internal base URL from each test run's runtime port; avoiding hardcoded 8080 and port collisions.
3. **Controlled internal service discovery:** registering the listening server endpoint after it initializes, while ensuring deregistration/health/lifecycle are properly designed.
4. **Multiple web servers/contexts:** distinguishing the main port from the Actuator management port to send requests to the right endpoint.

Limitations:

- **Web server port ≠ public address.** For instance, in Docker, the app listens on port 8080 inside the container while the host maps `9090:8080`; `getPort()` still reports 8080. In Kubernetes, Service/Ingress may expose a completely different address/port.
- **Having a port ≠ business readiness.** If the goal is to receive traffic after all startup steps complete, use appropriate readiness/health checks and lifecycle hooks, potentially combined with `ApplicationReadyEvent`.
- **`server.port=-1` differs from `server.port=0`.** `0` requests allocating a port to run the server; `-1` disables HTTP endpoints even though a web application context still exists. Do not assume an accessible HTTP port exists under `-1`.
- **The server may bind to a specific interface:** `server.address` or network policy determines from where connections are allowed; knowing only the port is not enough to conclude remote clients can connect.
- **If the server fails to bind**, there is no active port for the event to provide; resolve the startup failure first.

## 8. When Actuator Management Server Runs on a Separate Port

If you add `spring-boot-starter-actuator` and configure the management server separately from the app server, there may be **multiple `WebServerInitializedEvent` instances** corresponding to different contexts/servers. For example:

```properties
server.port=0
management.server.port=0
```

When running in an environment supporting two separate servers, the operating system may assign **two different ports**. If a listener simply overwrites a `lastPort` variable on each event, that variable might accidentally hold the management port instead of the business port.

Spring Boot provides `getServerNamespace()` to distinguish them. By Boot's standard convention, the main app server's namespace is `null`, whereas a separate management server's namespace is `management`. You can observe this:

```java
@EventListener
void observe(WebServerInitializedEvent event) {
    String namespace = event.getApplicationContext().getServerNamespace();
    int port = event.getWebServer().getPort();

    if (namespace == null) {
        System.out.println("APP_PORT=" + port);
    } else if ("management".equals(namespace)) {
        System.out.println("MANAGEMENT_PORT=" + port);
    } else {
        System.out.println("OTHER_PORT[" + namespace + "]=" + port);
    }
}
```

This is a **condensed method** to place inside a Spring bean (such as `@Component`), not a standalone program. If you only need the app port in a regular Boot application, checking for a `null` namespace as in the runnable example is sufficient. If you create custom contexts/servers with custom namespaces, match `event.getApplicationContext()` against the desired context instead of assuming every non-management event is the app server.

Not every application using Actuator creates a separate server. When `management.server.port` is not separated from `server.port`, Actuator typically shares the same port as application endpoints.

## 9. Can This Event Be Used with WebFlux?

Yes. `WebServerInitializedEvent` is the common base class; WebFlux can publish `ReactiveWebServerInitializedEvent` from the embedded reactive web server (commonly Reactor Netty). A listener using `WebServerInitializedEvent` and `getWebServer().getPort()` still works. You do not need to cast to `ServletWebServerInitializedEvent` if the code should work for both MVC and WebFlux.

Although both stacks can use `@RestController`, they differ in HTTP pipeline and execution model; that difference does not change the meaning of **reading the bound port from the web server in the event**. Note that if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot typically defaults to the Servlet web application type.

## 10. Common Errors and How to Pinpoint Their Cause

| Symptom | Cause / What to Check |
|---|---|
| `server.port=0` yet code reads 0 | Reading configuration instead of `event.getWebServer().getPort()` |
| Listener is never invoked | `@Bean`/`@Component` not registered in package scan, no web server running, or startup failed |
| Port log appears twice | Two listeners for the same purpose or multiple web servers/contexts; check namespace |
| Test `@LocalServerPort` receives no port | Using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and the right import? Does the test actually start a web server? |
| Injecting port into constructor/`@PostConstruct` fails | Bean initialization may occur before the server binds; switch to `WebServerInitializedEvent` |
| Port is available yet `curl` fails | Check HTTP/HTTPS, host/interface, printed port, container port mapping, proxy, firewall, and startup timing |
| Fixed port 8080 reports already in use | Another process is listening; pick another port, free the port, or use `server.port=0` for test/dev |

## 11. Knowledge Self-Check

**Question 1:** With `server.port=0`, is 0 the final HTTP port?  
**Answer:** No. 0 is a request to choose an available port; the final port number is read from `WebServerInitializedEvent.getWebServer().getPort()`.

**Question 2:** Is this event synonymous with `ApplicationReadyEvent`?  
**Answer:** No. One reports that the web server has initialized; the other reports that SpringApplication has completed startup steps/runners in the normal lifecycle. Neither replaces health/readiness checks.

**Question 3:** When a separate management server exists, why check `getServerNamespace()`?  
**Answer:** To avoid confusing the main server port with the Actuator management port or a server from another context.

**Question 4:** Can reading `server.port` in a bean replace the event?  
**Answer:** Not when you need the actual port, especially with `server.port=0`; the property only reflects configuration.

**Question 5:** Where is `@LocalServerPort` most appropriate?  
**Answer:** In Spring Boot integration tests that start a real web server, such as `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

## 12. Further Official Reading

- Spring Boot 3.3.13, *Embedded Web Servers*, sections *Use a Random Unassigned HTTP Port* and *Discover the HTTP Port at Runtime*: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 API, `WebServerApplicationContext` and `getServerNamespace()`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- Spring Boot API, `WebServerInitializedEvent`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html

**Remember:** configuring `server.port` specifies the **desired port**; `WebServerInitializedEvent` tells you the **actual bound port** at the moment the web server is ready. When multiple servers or proxies are involved, distinguish the context and internal/public ports properly.