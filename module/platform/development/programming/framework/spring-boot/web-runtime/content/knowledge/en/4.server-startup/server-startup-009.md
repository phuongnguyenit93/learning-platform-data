# Distinguishing `server.port=0`, `server.port=-1`, and Applications Without a Web Server in Spring Boot

## 1. Core of the Problem: Configuring the **Port** Differs from Configuring the **Application Type**

When a Spring Boot application starts up, **two independent questions** must be answered:

1. **Which kind of `ApplicationContext` does Spring Boot create?** This is decided by `WebApplicationType`: `SERVLET`, `REACTIVE`, or `NONE`. For a web application, Spring Boot prepares the request-handling infrastructure corresponding to Spring MVC or WebFlux.
2. **Does the web application accept HTTP over a network port?** This is governed by `server.port`. A value of `0` asks the operating system to allocate an actual port; a value of `-1` disables the main web server's HTTP endpoints while keeping the web application context.

Therefore, **`server.port=-1` is not synonymous with `WebApplicationType.NONE`**. Both provide no HTTP endpoint on the main port, yet they create different contexts and load different infrastructure. Conversely, `server.port=0` definitely **does not mean disabling the port**.

Scope: standalone Spring Boot 3.x applications with an embedded web server (Tomcat by default for `spring-boot-starter-web`, or the corresponding reactive runtime). For WAR deployments running inside an external servlet container, the listening port is determined by the external container; embedded server `server.port` rules do not apply mechanically.

## 2. Direct Comparison of the Three Modes

| Configuration | Typical Context Type with `spring-boot-starter-web` | Main App HTTP Listener | Reachable via `GET /ping` over Network? | Common Purpose |
| --- | --- | --- | --- | --- |
| `server.port=0` | `ServletWebServerApplicationContext` (web) | **Yes**, actual port chosen by OS, > 0 | **Yes**, if the assigned port is known | Integration tests with real HTTP; running multiple instances without port collisions |
| `server.port=-1` | Still a web application context | **No** main HTTP port opened to serve endpoints | **No** via the main port | Initializing web context/beans for testing or special tasks without exposing HTTP |
| `spring.main.web-application-type=none` | `AnnotationConfigApplicationContext` (non-web) | **No** web server created for this app | **No** | CLI, batch jobs, migrations, workers, background processing apps |

The table assumes **only one main HTTP server is configured**. If Actuator is enabled on a **separate management port**, or the app opens other sockets/servers itself, inspect those listeners independently; `server.port=-1` does not guarantee the entire process has zero network ports open.

For comparison, with a web starter and default configuration, a standalone app normally listens for HTTP on **8080**. `server.port=8081` is a fixed port; `0` and `-1` are two values with special meanings.

## 3. Case A — `server.port=0`: Web Server Exists, Port Chosen at Runtime

### Mechanism

~~~properties
# src/main/resources/application.properties
server.port=0
~~~

Spring Boot creates a **web application context** and starts the embedded server. Instead of binding the listener to port 8080, the application asks the operating system to pick an available TCP port. For instance, one run might be assigned `49176` and another `50231`; **these numbers are illustrative only**, not default values or fixed guarantees.

Startup flow:

~~~text
SpringApplication.run(...)
        |
        v
Select WebApplicationType.SERVLET/REACTIVE
        |
        v
Create web ApplicationContext and initialize embedded server
        |
        v
server.port = 0 --> OS allocates actual port, e.g. 49176
        |
        v
WebServerInitializedEvent --> bound port known
        |
        v
Client calls http://localhost:49176/...
~~~

**Do not access `http://localhost:0`.** The value `0` is a dynamic port allocation request when the server **binds**, not a port for clients to connect to. The actual port must be read **after** server initialization via logs, `WebServerApplicationContext.getWebServer().getPort()`, or `WebServerInitializedEvent`.

In application code, prefer listening to the server initialization event. Do not rely on `@Value` for the `local.server.port` property inside beans created too early: the actual port property is only populated after the server initializes. In **integration tests** with `RANDOM_PORT`, `@LocalServerPort` can be used.

### When Should It Be Used?

- Integration tests needing real HTTP without competing for port 8080 with other apps.
- Multiple local/container instances on the same host, each choosing its own port.
- Local/embedded tools that register or pass their actual port back to clients.

### Points to Note

- The port changes between runs; do not hardcode it in clients, docs, or automation.
- The auto-assigned port still **serves live HTTP endpoints**; unless interface binding is restricted, it can accept connections on interfaces matching `server.address` and network settings. Never treat dynamic ports as a security mechanism.
- `server.port=0` reduces **bind-time port collisions** via the OS, but other resources (databases, files, remote services) can still conflict.
- With `spring.main.web-application-type=none`, `server.port=0` cannot enable a web server because the app has chosen a non-web context type.

## 4. Case B — `server.port=-1`: Keeps Web Context, Disables Main HTTP Endpoints

~~~properties
# src/main/resources/application.properties
server.port=-1
~~~

Spring Boot may still detect web application type `SERVLET` or `REACTIVE` from the classpath/configuration and **still creates a `WebApplicationContext`**. However, under Spring Boot's configuration contract, `server.port=-1` **disables the main HTTP endpoints**: clients cannot use a main HTTP port to call controllers. Spring Boot documentation mentions this mode as an option for certain testing scenarios.

Important distinctions:

- `@RestController`, `@GetMapping`, and web support beans may still be scanned/initialized depending on configuration because the app remains a **web application context**; that **does not mean** controllers have public HTTP URLs.
- `server.port=-1` configures the **main web server's HTTP listening path**. Do not describe it as "creating no web server" or "having no web context."
- Because no main HTTP port is bound, there is no "actual port" to query as with `server.port=0`. Never use `-1` in a URL to send requests.
- Do not infer from HTTP being unreachable that all beans, schedulers, database connections, or background tasks stop running.
- Whether the Java process exits automatically after startup depends on running threads and other components; **do not rely solely on `-1` to control batch job lifecycles**.

Suitable scenario: you need the beans and infrastructure of a web application context to verify configuration, without opening a main HTTP port. If the goal is **only running tasks with no web infrastructure**, using `WebApplicationType.NONE` is more accurate.

**Note on Actuator:** if `spring-boot-starter-actuator` is installed and `management.server.port` differs from the main port, management HTTP has its own listener configuration. To disable management HTTP, handle it independently—for example, `management.server.port=-1` or disabling appropriate web exposure. Never claim "zero HTTP listeners remain" based solely on `server.port=-1`.

## 5. Case C — Application **Without a Web Server**: `WebApplicationType.NONE`

~~~properties
# src/main/resources/application.properties
spring.main.web-application-type=none
~~~

This instructs `SpringApplication` **not to create a web application context**. The typical context is `AnnotationConfigApplicationContext`, not `ServletWebServerApplicationContext` or `ReactiveWebServerApplicationContext`. Spring still provides dependency injection, configuration, beans, `ApplicationRunner` / `CommandLineRunner`, and other services, without starting an embedded HTTP web server. Declaring `@RestController` does not turn the app into an HTTP server once `none` is selected.

It can be configured in Java **before calling `run`**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class Main {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(Main.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
~~~

This snippet illustrates the API for setting the application type, **not a complete standalone program**: to actually run, `Main` needs appropriate bean configuration (usually `@SpringBootApplication`), Spring Boot dependencies, and project structure. You can use `spring.main.web-application-type=none` instead of programmatic configuration.

### Does Having No Web Starter Always Mean `NONE`?

When `spring.main.web-application-type` is not specified, Spring Boot **auto-detects** the application type from the classpath:

- If Spring MVC is present, defaults to **`SERVLET`**.
- If MVC is absent and Spring WebFlux is present, typically selects **`REACTIVE`**.
- If neither web stack indicator is present, selects **`NONE`**.
- If both MVC and WebFlux are present, MVC usually takes precedence. To force WebFlux, use `spring.main.web-application-type=reactive` when the architecture fits.

Therefore, there are **two common ways** to obtain a non-web application: (1) use non-web starters so Boot auto-detects `NONE`; (2) keep web dependencies while **explicitly** setting `spring.main.web-application-type=none`. Approach (2) still keeps web libraries on the classpath, yet **does not** establish a web context or HTTP server.

### Non-Web Lifecycle

The application can perform work inside `ApplicationRunner`/`CommandLineRunner` and then **exit automatically** if no non-daemon threads or active tasks keep the JVM alive. If `@Scheduled` tasks, message listeners, background threads, or long-running tasks are configured, a non-web app can keep running. **Having no web server does not force the application to exit immediately.**

When both `spring.main.web-application-type=none` and `server.port=0` (or `-1`) are present, `NONE` determines that no web server is created; `server.port` creates neither a listener nor a web context.

## 6. Runnable Java 17+ Example: Same Program, Three Ways to Start

The example uses **Spring Boot 3.x + Java 17+** with runtime dependency `spring-boot-starter-web`. With Gradle, the project must have the Spring Boot Gradle plugin and `bootRun` configured. Place the complete Java code below in the exact file:

`src/main/java/demo/ports/PortModesApplication.java`

~~~java
package demo.ports;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PortModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortModesApplication.class, args);
    }

    @Bean
    ApplicationRunner describeContext(ConfigurableApplicationContext context) {
        return args -> System.out.println(
                "WEB_CONTEXT=" + (context instanceof WebServerApplicationContext));
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> reportHttpPort() {
        return event -> {
            int actualPort = event.getWebServer().getPort();
            if (actualPort > 0) {
                System.out.println("BOUND_HTTP_PORT=" + actualPort);
            }
        };
    }
}

@RestController
class PingController {
    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
~~~

In this code:

1. `@SpringBootApplication` initializes the app. Since the web dependency is present, Boot defaults to recognizing a **web application** unless `none` is configured.
2. `ApplicationRunner` prints `WEB_CONTEXT=true` if the context is a `WebServerApplicationContext`, otherwise `false`. It runs after context refresh.
3. `ApplicationListener<WebServerInitializedEvent>` receives the event when the web server initializes; when the actual port is greater than 0, it prints `BOUND_HTTP_PORT=<port_number>`. This guard avoids falsely reporting an active HTTP listener when no positive port exists. If a separate management server exists, the event may fire multiple times and production apps should filter by context/namespace.
4. `PingController` maps GET `/ping` to the text `pong` **only when an active HTTP endpoint exists**. The presence of the controller bean does not make `-1` or `NONE` accept requests.
5. The example requires no database or Actuator; run the three modes **separately**, stopping the previous process before starting the next mode.

### 6.1 Running with a Dynamic Port (`server.port=0`)

On bash/macOS/Linux:

~~~bash
./gradlew bootRun --args='--server.port=0'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--server.port=0"
~~~

Suppose the application prints (excerpting only lines emitted by the sample code):

~~~text
BOUND_HTTP_PORT=49176
WEB_CONTEXT=true
~~~

Port `49176` is an **example**; use the actual port from your `BOUND_HTTP_PORT` line—for instance, in that illustrative run:

~~~bash
curl -i http://localhost:49176/ping
~~~

Expect HTTP status **200 OK** and body `pong` (along with headers generated by the embedded server). Accessing `localhost:8080` would only succeed if another service happened to be listening there; it is **not** this `server.port=0` run's port.

### 6.2 Running with Main HTTP Disabled (`server.port=-1`)

~~~bash
./gradlew bootRun --args='--server.port=-1'
~~~

For this simple example, you can observe:

~~~text
WEB_CONTEXT=true
~~~

No positive main HTTP port is printed by the listener, and `/ping` cannot be reached over a main HTTP listener. **Never try `curl http://localhost:-1/ping`**; `-1` is only a Spring Boot configuration value, not a valid TCP port. Seeing `WEB_CONTEXT=true` is the clearest evidence distinguishing this mode from non-web.

### 6.3 Running as a Non-Web Application (`none`)

~~~bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
~~~

The sample code is expected to print:

~~~text
WEB_CONTEXT=false
~~~

There is no web server event to print a port and no `/ping` HTTP endpoint. Because the example has no long-running background tasks, the JVM can exit after startup; that is normal lifecycle behavior, **not** a port-binding error. The program still executes `ApplicationRunner` to print the result.

### 6.4 Equivalent Configuration

Each option below should be used in a separate run:

~~~properties
# application.properties: mode A
server.port=0
~~~

~~~properties
# application.properties: mode B
server.port=-1
~~~

~~~properties
# application.properties: mode C
spring.main.web-application-type=none
~~~

YAML equivalents (pick **one** configuration per run):

~~~yaml
server:
  port: 0
~~~

~~~yaml
server:
  port: -1
~~~

~~~yaml
spring:
  main:
    web-application-type: none
~~~

You can also configure the port via the `SERVER_PORT` environment variable through relaxed binding, such as `SERVER_PORT=0`. If values from command line, environment variables, profiles, and config files differ, check **property source precedence** to determine the effective value; never assume `application.properties` always wins.

## 7. Testing: Avoid Confusing `@SpringBootTest` with Production Configuration

Spring Boot provides `@SpringBootTest(webEnvironment = ...)` to define the test environment; this choice is **different in scope** from setting `server.port` in normal app execution.

| `WebEnvironment` | Context in Test | Real HTTP Listener? | Meaning |
| --- | --- | --- | --- |
| `MOCK` (default) | Mock web context if web stack exists; otherwise non-web | **No** | Testing web layer with `MockMvc` or equivalent tools |
| `RANDOM_PORT` | Web context with embedded server | **Yes**, dynamic port | End-to-end HTTP testing at the web server layer |
| `DEFINED_PORT` | Web context with embedded server and configured port, default 8080 | **Yes**, unless configured to disable main HTTP port, e.g., `server.port=-1` | Testing HTTP calls on a predefined port |
| `NONE` | Non-web context | **No** | Testing beans/logic without web infrastructure |

**Important pitfall:** `@SpringBootTest` by default **does not** open an HTTP port, yet when MVC is present it uses a **mock web environment**; therefore, never treat default test results as proof that the production app has `WebApplicationType.NONE`. Also, `MockMvc` can invoke controllers **in memory** without needing a TCP listener.

### Dynamic-Port Integration Test Example

With the `spring-boot-starter-test` test dependency, file `src/test/java/demo/ports/RandomPortTest.java`:

~~~java
package demo.ports;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomPortTest {
    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void servesHttpOnAssignedPort() {
        assertThat(port).isGreaterThan(0);
        assertThat(restTemplate.getForObject("/ping", String.class))
                .isEqualTo("pong");
    }
}
~~~

The test uses `RANDOM_PORT` to **start a real server**, retrieves the bound port with `@LocalServerPort`, and asserts the endpoint response body. With `TestRestTemplate` auto-configured by Spring Boot test in an appropriate setup, you can call the relative path `/ping`. Gradle command (when JUnit 5 tests are configured):

~~~bash
./gradlew test --tests demo.ports.RandomPortTest
~~~

Do not copy `@LocalServerPort` into beans created during regular application startup: this annotation belongs to test contexts that have initialized a real port. When you want to guarantee **no web environment in tests**, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)`. When you want a **web context without listening on HTTP**, consider testing with `server.port=-1` if appropriate, or mock web tests if only controller mappings are needed.

## 8. Diagnostic Approach When Startup Does Not Match Expectations

### Scenario 1: Set `server.port=0` Yet Do Not Know Which Address to Call

**Cause:** confusing configured value `0` with the actual port. **How to check:** inspect server logs, use `WebServerInitializedEvent`, or call `WebServerApplicationContext.getWebServer().getPort()` **after** initialization. In tests, use `@LocalServerPort` with `RANDOM_PORT`. Confirm the listener with network tools and the printed port; never call 0.

### Scenario 2: Set `server.port=-1`, Yet Web Context Still Initializes

**This is intentional behavior.** `-1` does not remove web infrastructure. If building a batch/CLI app and wanting to avoid web auto-configuration/context, use `spring.main.web-application-type=none`. If a test needs web beans without listening on HTTP, `-1` may fit.

### Scenario 3: Set `server.port=8080` or `0`, Yet Still No HTTP Server

Check whether `spring.main.web-application-type=none` is set (including via command line, profiles, or environment variables). `server.port` cannot turn `WebApplicationType.NONE` into `SERVLET`. Additionally, missing web dependencies or custom application context setups also result in no embedded web server.

### Scenario 4: Cannot Reach Endpoint Despite Successful Startup Message

Separate the causes:

1. **No listener:** `-1` or `NONE`; no main port to call.
2. **Wrong port:** `0` picked another dynamic port; 8080 may not be the active one.
3. **Different bind address:** check `server.address`, container networking, and port mapping; successful server binding does not guarantee routing from every client machine.
4. **Wrong endpoint:** path/method mismatch can return 404/405.
5. **Security or Actuator:** security filters, management port, and endpoint exposure produce different behavior; these are separate configuration layers, not substitutes for the three modes above.

### Scenario 5: Application "Without a Web Server" Keeps Running Indefinitely

`NONE` only controls web infrastructure. Schedulers, message listeners, background threads, or long-running tasks can keep the JVM alive. Conversely, `server.port=-1` can still have web beans; do not use it as a switch guaranteeing process termination.

## 9. Common Conceptual Mistakes

- **"`server.port=0` means disabling HTTP."** False: `0` asks the OS for **an actual HTTP port**. To disable main endpoints: `-1`; to disable the web server completely: `NONE`.
- **"`server.port=-1` is equivalent to `spring.main.web-application-type=none`."** False: `-1` keeps the web context; `NONE` creates a non-web context.
- **"No web listener means no Spring application."** False: beans, DI, runners, schedulers, and business logic can still run.
- **"`@SpringBootTest` starts an HTTP server by default."** False: the default `MOCK` does not open a real TCP listener.
- **"The actual port must equal the `server.port` property value."** False for `0`: the property requests port allocation; the real port is known only after binding.
- **"If the main port is disabled, no network listeners exist."** False if Actuator management uses a separate port or the program opens other sockets itself.
- **"Adding `server.port` forces a `NONE` app to become a web app."** False: a web context and matching web runtime are required.

## 10. Choosing a Mode Based on Real Requirements

~~~text
Does the app need to serve real HTTP?
  |
  +-- Yes --> Is a fixed port required?
  |             |
  |             +-- Yes --> server.port=8080 (or predefined port)
  |             |
  |             +-- No  --> server.port=0
  |                          Read actual port after server binds
  |
  +-- No  --> Does the web ApplicationContext need to be kept?
                  |
                  +-- Yes --> server.port=-1
                  |            Keep web context, disable main HTTP
                  |
                  +-- No  --> spring.main.web-application-type=none
                               Run as a non-web application
~~~

A quick decision example: (a) parallel integration tests for an HTTP service → `server.port=0`; (b) validating web app beans/config without exposing endpoints → `server.port=-1` or mock web tests depending on scope; (c) nightly data-import job needing neither MVC nor WebFlux → `spring.main.web-application-type=none`.

### Self-Check Questions

1. **If `WEB_CONTEXT=true` and `BOUND_HTTP_PORT=51324`, which mode applies?** → `server.port=0` or fixed port 51324; check configuration to distinguish. An HTTP listener definitely bound port 51324.
2. **If `WEB_CONTEXT=true` yet controllers cannot be reached over the network, can you conclude the app is `NONE`?** → No. It could be `server.port=-1` or a network/security issue; check properties and listeners.
3. **If `spring-boot-starter-web` is present yet `spring.main.web-application-type=none` is configured, will controllers be served?** → No. Having the library present does not override `NONE`.
4. **If you only want to test a controller via `MockMvc`, do you need `RANDOM_PORT`?** → No. Mock web tests typically need no TCP server; `RANDOM_PORT` is for real HTTP flow checks.
5. **Can two independent tests using `server.port=0` run concurrently?** → Usually yes: the OS assigns a free port for each bind, avoiding main-port collisions. However, it does not guarantee other shared resources are isolated.

## 11. Official References

- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): guides on `server.port=0`, `server.port=-1`, disabling the web server, and discovering the runtime port.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): differences among `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`.
- [Spring Boot 3.4 — SpringApplication / Web Environment](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html): `WebApplicationType` detection and overriding via `setWebApplicationType`.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management port and independent control of Actuator HTTP.

**Key takeaway:** `0` = **HTTP active on an OS-assigned port**; `-1` = **web context retained, main HTTP endpoints disabled**; `NONE` = **no web application context created and no web server started**.