# Application Selects Wrong Web Type, Missing Server, or Port Already in Use

When running a Spring Boot application, three situations are often mistaken for the same error: the application starts without opening an HTTP port; the application needs to expose a REST API yet startup fails because no web server can be created; or the embedded server stops because the port is already used by another process. To diagnose accurately, separate three layers of causes:

1. **Web application type**: Is Spring Boot creating a Servlet, Reactive, or Non-web application?
2. **Server dependency and auto-configuration**: Does the runtime classpath contain an appropriate embedded server?
3. **Network binding**: Can the server bind to the configured address and port?

Choosing `WebApplicationType.SERVLET` does not automatically install Tomcat. Having Tomcat on the classpath does not allow binding if the port is occupied. Changing the port only resolves an address conflict; it does not fix an application accidentally initialized as non-web.

This lesson uses Spring Boot 3.x and Java 17/21 to show how to identify `NONE`, `SERVLET`, and `REACTIVE`, inspect starters and embedded servers, handle port conflicts on Windows/Linux, distinguish container ports from host ports, and write tests without hardcoding fixed ports.

## 1. Three layers to check

~~~mermaid
flowchart TD
    A["SpringApplication.run(...)"] --> B["Determine WebApplicationType"]
    B --> C{"Web type"}
    C -->|NONE| D["Non-web context; no HTTP listener opened"]
    C -->|SERVLET| E["Look up ServletWebServerFactory"]
    C -->|REACTIVE| F["Look up ReactiveWebServerFactory"]
    E --> G{"Servlet server present?"}
    F --> H{"Reactive server present?"}
    G -->|No| I["Missing server or misconfigured WAR"]
    H -->|No| I
    G -->|Yes| J["Create web server"]
    H -->|Yes| J
    J --> K["Read server.address and server.port"]
    K --> L{"Bind succeeds?"}
    L -->|No| M["Port/address conflict or permission error"]
    L -->|Yes| N["HTTP listener active"]
~~~

A sound diagnostic workflow is to verify whether the application is intended to be web or non-web, check the web type, confirm server dependencies, read the effective port/address, identify the process holding the port, and finally inspect the host/container network topology.

Do not change multiple configurations at once. If the application does not open a port because its web type is `NONE`, changing the port from 8080 to 9090 will not fix the root cause.

## 2. What is WebApplicationType?

Spring Boot uses `WebApplicationType` to decide what kind of application context and web infrastructure to initialize.

| Value | Model | Behavior |
| --- | --- | --- |
| `SERVLET` | Servlet-based web application | Uses the Servlet API and corresponding web server, typically embedded Tomcat |
| `REACTIVE` | Reactive web application | Uses the reactive web stack, typically WebFlux and Reactor Netty |
| `NONE` | Non-web application | Does not create a web application context and does not open an HTTP listener |

### 2.1. SERVLET

A typical Spring MVC application uses the Servlet stack:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

When the runtime classpath has Spring MVC and an appropriate embedded Servlet server, Spring Boot can initialize a Servlet web application context, create the server, and bind the port.

Controller example:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public Map<String, String> find(@PathVariable String id) {
        return Map.of("id", id, "status", "ACCEPTED");
    }
}
~~~

Having `@RestController` does not equate to the server having opened a port. Controllers are only served over HTTP when the web context and server are actually initialized.

### 2.2. REACTIVE

An application using Spring WebFlux can initialize a Reactive web application:

~~~java
@RestController
@RequestMapping("/reactive/orders")
public class ReactiveOrderController {

    @GetMapping("/{id}")
    public Mono<Map<String, String>> find(@PathVariable String id) {
        return Mono.just(Map.of("id", id, "status", "ACCEPTED"));
    }
}
~~~

In a common setup, `spring-boot-starter-webflux` pulls in Reactor Netty as the embedded server. WebFlux can also run on certain compatible Servlet containers; server selection depends on dependencies and runtime configuration.

Do not assume WebFlux strictly requires Netty alone. What must be verified is the presence of a server implementation compatible with the reactive application context.

### 2.3. NONE

Batch jobs, CLI tools, schedulers, or background workers may not need an HTTP listener:

~~~java
@SpringBootApplication
public class ImportJobApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ImportJobApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
~~~

A `NONE` application can still use dependency injection, configuration properties, scheduling, databases, or Spring events. It simply does not create a web application context to open an HTTP server.

A process not opening a port is not necessarily broken. It may be the intended behavior by design.

## 3. How does Spring Boot deduce web type automatically?

When calling:

~~~java
SpringApplication.run(ShopApplication.class, args);
~~~

Spring Boot can deduce the web application type from classes present on the runtime classpath. At a high level:

- Suitable Spring MVC/Servlet stack present: typically selects `SERVLET`.
- Suitable reactive web stack present without a prioritized MVC stack: may select `REACTIVE`.
- No web stack indicators present: may select `NONE`.

Deduction relies on the classpath and rules of the Spring Boot version, not solely on annotations on controllers.

### 3.1. When both Spring MVC and WebFlux are present

A project may include both starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

In standard Spring Boot setups, when both Spring MVC and WebFlux are present, Boot picks the **Servlet/MVC application type by default**. A project may only add WebFlux to use `WebClient` for outbound HTTP calls; that does not mean the inbound server must switch to reactive.

If you genuinely want a reactive application, you can configure:

~~~properties
spring.main.web-application-type=reactive
~~~

However, you must ensure the runtime classpath has a reactive server implementation. Forcing the web type without a suitable server can cause startup to fail.

### 3.2. Using WebClient does not mean the application is a Reactive server

`WebClient` is an HTTP client API that can be used inside a Servlet/MVC application. A valid architecture can use Spring MVC for inbound HTTP requests, `WebClient` for outbound HTTP requests, and an embedded Servlet server like Tomcat to accept requests.

You do not need to force the entire application to `REACTIVE` merely because `WebClient` is in the dependencies.

### 3.3. Controller annotations do not determine the server

`@RestController` and `@RequestMapping` provide metadata for the web framework. If the application type is `NONE` or lacks a web server factory, those controllers will not be served as normal HTTP endpoints.

## 4. Configuring web application type explicitly

You can set the type via a property:

~~~properties
spring.main.web-application-type=servlet
~~~

Common values:

~~~properties
spring.main.web-application-type=servlet
spring.main.web-application-type=reactive
spring.main.web-application-type=none
~~~

In YAML:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Or configure via Java:

~~~java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
~~~

With the builder:

~~~java
new SpringApplicationBuilder(ShopApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

### 4.1. When should it be set explicitly?

- An application module has a complex dependency tree and needs fixed Servlet/Reactive semantics.
- A batch application uses some web dependencies but must not open a server.
- A test context needs non-web behavior.
- The application includes both MVC and WebFlux with an explicitly decided runtime intent.

If auto-detection works properly, there is no need to add configuration merely to repeat the default.

### 4.2. NONE is not a fix for a missing server

If the application needs a REST API yet runtime lacks Tomcat, setting `spring.main.web-application-type=none` may let the context start without creating a server. However, HTTP endpoints will not work either.

That changes the application type rather than installing a server. If the goal is to run an API, fix the dependency/runtime configuration to supply an appropriate web server.

## 5. Where does the embedded server come from?

Spring Boot starters typically pull in an appropriate embedded server.

Servlet web application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

In the default configuration, the web starter brings embedded Tomcat into the runtime dependency graph.

Common reactive web application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

The WebFlux starter typically pulls in Reactor Netty as the reactive embedded server.

### 5.1. Starters and server implementations are different

A starter aggregates dependencies for a capability. A server implementation is the component that actually opens the network listener.

With MVC, `spring-boot-starter-web` provides Spring MVC and common web dependencies; `spring-boot-starter-tomcat` provides embedded Tomcat in the default configuration. You can replace Tomcat with another Servlet container supported by Spring Boot.

If you exclude the embedded server from the runtime classpath without replacing it with another server, the application may fail to create a Servlet web server.

### 5.2. Inspecting Gradle runtime dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To see why Tomcat is pulled in:

~~~bash
./gradlew dependencyInsight --dependency tomcat --configuration runtimeClasspath
~~~

For the reactive server:

~~~bash
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

Read the output to see which dependencies are included/excluded, which version resolves, and whether the server is present in `runtimeClasspath` or only appears in another configuration.

### 5.3. Inspecting the Maven dependency tree

~~~bash
mvn dependency:tree
~~~

Filter for the Tomcat starter:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Or embedded Tomcat artifacts:

~~~bash
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

If the server is excluded, find the dependency declaring the exclusion and determine whether a replacement server exists.

### 5.4. Compiling succeeds yet runtime lacks a server

The compiler can compile controllers because Spring MVC APIs are on the compile classpath. However, at runtime, if the embedded server is absent from the runtime classpath, Spring Boot may fail to find a suitable `ServletWebServerFactory`.

This is the difference between the compile classpath and the runtime classpath.

## 6. Replacing Tomcat with Jetty or Undertow

An application may want to use a Servlet server other than Tomcat. For example, excluding Tomcat from the starter and adding Jetty in Gradle:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

Use the version managed by Spring Boot dependency management and confirm the server is compatible with the Boot version in use.

If the runtime classpath has multiple Servlet server implementations due to a complex dependency graph, inspect auto-configuration and the actual server factory. Do not add Jetty while forgetting to exclude Tomcat when the goal is replacement.

Tomcat/Jetty/Undertow are Servlet server options within their respective integrations. Reactor Netty is a common reactive server option. Adding a Servlet server does not automatically resolve a missing reactive server error when the application type is `REACTIVE`.

## 7. WAR deployed on an external Servlet container

A Spring Boot application can also be packaged as a WAR and deployed into a Servlet container provided by the environment. In that case, an embedded server does not necessarily get packaged as in an executable JAR.

Initializer class example:

~~~java
@SpringBootApplication
public class ShopApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ShopApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

A WAR project requires appropriate plugins, packaging, and dependency scopes. The external container is responsible for providing the Servlet implementation.

If you attempt to run a WAR as an executable archive, ensure the Spring Boot plugin has configured an executable WAR according to the deployment target. Do not conclude the embedded server is missing when the application is designed for an external container.

## 8. Identifying the actual application context

You can observe the created context:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(ShopApplication.class, args);

System.out.println(context.getClass().getName());
~~~

Common context classes:

| Application type | Typical context class |
| --- | --- |
| Servlet | `ServletWebServerApplicationContext` |
| Reactive | `ReactiveWebServerApplicationContext` |
| Non-web | Non-web context, e.g., `AnnotationConfigApplicationContext` |

Specific class names are implementation details that can change across versions/bootstrap modes. Use them for diagnosis; do not write business logic that depends on class names.

### 8.1. Reading startup logs

A web application typically logs confirmation that the server started and its actual port, such as Tomcat or Netty starting to listen. If the context finishes without server startup messages, check the web type and server factory.

Do not look solely at the `Started ...` line. A non-web application can still print that message successfully.

### 8.2. Condition evaluation report

In development, you can run:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can print the condition evaluation report to help identify which auto-configurations were applied or excluded.

This is a diagnostic tool. An auto-configuration can back off because of a missing class on the classpath, a user-defined bean, or a controlling property. Do not enable debug reports broadly in production if the output could reveal internal structure.

## 9. Embedded server not created: common causes

| Cause | Symptom | How to fix |
| --- | --- | --- |
| Web type is `NONE` | Non-web context, no server startup log | Check `spring.main.web-application-type` |
| Missing MVC/WebFlux dependency | No suitable web stack detected | Check starter/runtime classpath |
| Embedded server excluded | Missing server factory | Restore dependency or add replacement server |
| Dependency only in compileOnly/provided by mistake | Compiles yet runtime lacks server | Adjust dependency scope |
| Running library module instead of app module | Missing proper bootstrap/application | Run the right application module |
| WAR built for external container but run the wrong way | Incorrect deployment mode | Deploy to external container or build executable archive |
| Custom configuration alters auto-configuration | Factory not created as expected | Inspect bean definitions and condition report |
| Profile/CLI overrides web type | Local and deployment differ | Check effective property sources |

### 9.1. Missing ServletWebServerFactory error

An exception may read similarly to:

~~~text
ApplicationContextException: Unable to start web server
...
No qualifying bean of type
'org.springframework.boot.web.servlet.server.ServletWebServerFactory'
available
~~~

This usually indicates Spring is creating a Servlet web application context but cannot find a factory to build the embedded server.

Investigation steps:

1. Check whether the application type is SERVLET.
2. Check whether the starter/server dependency is on the runtime classpath.
3. Check exclusions and `provided`/`compileOnly` scopes.
4. Check that you are running the right module/artifact.
5. Check whether custom configuration interferes with auto-configuration.

### 9.2. Missing ReactiveWebServerFactory error

If the application type is REACTIVE yet no compatible server implementation exists, the context may report no `ReactiveWebServerFactory` found or fail to create the reactive web server.

Inspect the WebFlux starter and reactive server dependencies, not just Servlet Tomcat.

## 10. Configuring server.port

The default HTTP port for a Spring Boot web application is typically `8080`.

In properties:

~~~properties
server.port=9090
~~~

In YAML:

~~~yaml
server:
  port: 9090
~~~

Command line:

~~~bash
java -jar app.jar --server.port=9090
~~~

JVM system property:

~~~bash
java -Dserver.port=9090 -jar app.jar
~~~

Environment variable:

~~~text
SERVER_PORT=9090
~~~

### 10.1. Port can be overridden

Suppose `application.yml` sets 8080, yet deployment passes:

~~~bash
java -jar app.jar --server.port=9090
~~~

In typical Spring Boot setups, command-line properties take higher precedence than config files, so the effective port can be 9090.

Profile-specific configuration can also change the port:

~~~yaml
# application-dev.yml
server:
  port: 8081
~~~

When the `dev` profile is active, the application can use 8081 unless a higher-precedence property source overrides it.

When diagnosing, do not read only YAML. Check profiles, environment variables, JVM properties, command-line arguments, and external config sources.

### 10.2. Verifying the actual port

Check the startup log or inspect the process listener. When using a random port, the server can bind a port different from the initial configured value `0`.

## 11. Port 0 and port -1

### 11.1. Port 0: OS selects an available port

In tests or environments running multiple instances, you can use:

~~~properties
server.port=0
~~~

Port `0` asks the operating system to choose an available port when binding.

Integration test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void serverStartsOnRandomPort() {
        assertThat(port).isBetween(1, 65535);
    }
}
~~~

`RANDOM_PORT` starts the server on a random port and `@LocalServerPort` supplies the actual port to the test.

Clients must not call `http://localhost:0`. Use the port actually bound by the server.

### 11.2. RANDOM_PORT differs from MOCK

`@SpringBootTest(webEnvironment = MOCK)` is not equivalent to starting an embedded server on a real TCP port. If you want to catch port conflicts, use `RANDOM_PORT` or a runtime smoke test.

### 11.3. Port -1: do not open an HTTP listener

Spring Boot supports `server.port=-1` in certain web applications to avoid opening an HTTP listener while still keeping the web application context.

| Value | Meaning |
| --- | --- |
| `server.port=8080` | Bind port 8080 |
| `server.port=0` | Operating system selects an available port |
| `server.port=-1` | Do not open an HTTP listener |

If you expect HTTP APIs to work while configured to `-1`, this is the direct cause of having no listener.

## 12. Port in use: recognizing BindException

Common startup error:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

Or:

~~~text
java.net.BindException: Address already in use
~~~

The server cannot bind the port because another process is already using that address/port or the operating system denies the bind.

Common causes:

- An old Spring Boot instance is still running.
- Clicking Run twice in the IDE.
- Another application is using 8080.
- Tests run the server on a fixed port while multiple processes run concurrently.
- Another Docker container already published the same host port.
- The management server is using the port you picked.
- A process outside the project holds the port.

### 12.1. Distinguishing from other network errors

| Message | Likely cause |
| --- | --- |
| `Address already in use` | Port is already in use |
| `Permission denied` | Bind privileges or OS policy |
| `Cannot assign requested address` | Bind address does not exist/does not match interface |
| `Connection refused` | No listener at destination or network path refused |
| HTTP 404 | Server received request yet route does not exist |
| Timeout | Firewall, routing, overloaded server, or unresponsive service |

Read the root exception before changing the port. Not every connection error is a port conflict.

## 13. Finding the process holding a port on Windows

Open PowerShell:

~~~powershell
netstat -ano | findstr :8080
~~~

Sample output:

~~~text
TCP    0.0.0.0:8080    0.0.0.0:0    LISTENING    14520
~~~

The last column is the PID. Inspect the process:

~~~powershell
Get-Process -Id 14520
~~~

Or:

~~~powershell
tasklist /FI "PID eq 14520"
~~~

You can use the dedicated cmdlet:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
~~~

Then inspect the process by the returned PID.

### 13.1. Stopping the process gracefully

Prefer stopping the application through its own management mechanism:

- Stop in the IDE.
- Stop the terminal session running `bootRun`.
- Stop the service via the service manager.
- Stop the container via Docker.
- Send an appropriate shutdown signal.

Only after confirming the right process and only when necessary should you stop it via:

~~~powershell
Stop-Process -Id 14520
~~~

Do not default to force-killing immediately. Abrupt termination can skip shutdown hooks, interrupt data writes, or leave external systems in an inconsistent state. PIDs can be reused, so verify the process immediately before acting.

## 14. Finding the process holding a port on Linux/macOS

On Linux, use `ss`:

~~~bash
sudo ss -ltnp 'sport = :8080'
~~~

Use `lsof`:

~~~bash
sudo lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Or `fuser`:

~~~bash
sudo fuser -v 8080/tcp
~~~

These commands help identify the process and PID. Appropriate privileges are required to see complete owner information.

If the process is managed by systemd, prefer stopping the service with systemctl. If the process belongs to a container, stop the container. For a process running in a terminal, use the corresponding stop mechanism.

If you need to send a signal to a PID, start with a soft signal:

~~~bash
kill <PID>
~~~

Only use a force signal once you understand the impact and the process cannot stop normally:

~~~bash
kill -9 <PID>
~~~

Do not act on an unverified PID.

## 15. Stop the old process or change the port?

Stopping the process holding the port makes sense when it is an old instance of the same application, a leftover test process, or a local service no longer needed. Confirm the process owner and prefer an orderly shutdown.

Changing the port makes sense when multiple applications must run concurrently or the current port belongs to another service:

~~~bash
./gradlew bootRun --args='--server.port=8081'
~~~

Or:

~~~bash
java -jar app.jar --server.port=8081
~~~

Do not pick a new port merely by guessing it is free. In tests, port 0 is usually better; in production, port allocation should be managed by the platform.

## 16. Bind address: localhost, 127.0.0.1, and 0.0.0.0

Even with the right port, a server can be unreachable from other machines if it binds only to loopback.

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

This configuration typically accepts connections only on the loopback interface of the host/container.

To listen on all IPv4 network interfaces:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

`0.0.0.0` is a wildcard bind address, not an address clients should call. Clients must use the host's real address, DNS name, container/service name, or platform-assigned address.

Do not bind every interface unconditionally. Doing so can expose the service to more networks than intended. Combine firewalls, security groups, network policies, reverse proxies, and Spring Security appropriately.

If an IP not present on the host is configured, the server may report `Cannot assign requested address`. Inspect interfaces with:

Windows:

~~~powershell
Get-NetIPAddress
~~~

Linux:

~~~bash
ip address
~~~

Only bind to an address existing inside the network namespace where the process runs.

## 17. Ports in Docker: host and container are two layers

An application in a container usually binds to an internal port, such as 8080:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Docker publishes host port 18080 to container port 8080:

~~~bash
docker run -p 18080:8080 my-shop-app:latest
~~~

A client on the host calls `http://localhost:18080`. Docker forwards traffic to container port 8080; Spring Boot inside the container still listens on port 8080.

### 17.1. EXPOSE does not open or publish a port automatically

Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

`EXPOSE` is metadata describing the intended port. It does not open a listener automatically, does not change `server.port`, and does not publish a host port. The application still must bind the port inside the container; when running the container, you must publish it or connect over an appropriate network.

### 17.2. Container port conflict and host port conflict

Two containers can both listen on port 8080 in their own network namespaces. That is normal.

However, if both publish host port 18080 on the same host/interface, Docker can report a port mapping conflict:

~~~bash
docker run -p 18080:8080 app-a
docker run -p 18080:8080 app-b
~~~

The second command can fail because host port 18080 is already used by the first container.

The fix is to choose a different host port or use appropriate service routing. You do not necessarily need to change `server.port` inside each container.

### 17.3. Docker Compose

~~~yaml
services:
  shop-api:
    image: my-shop-app:latest
    ports:
      - "18080:8080"
    environment:
      SERVER_PORT: "8080"
~~~

`SERVER_PORT` configures the port inside the container; the `18080:8080` mapping controls host-to-container forwarding.

If the application switches to port 9090 while Compose still maps `18080:8080`, traffic gets sent to 8080 and never reaches the server listening on 9090.

## 18. Kubernetes: container port, Service port, and targetPort

A typical path:

~~~text
Client
  |
  v
Ingress / Gateway
  |
  v
Service port (e.g., 80)
  |
  v
Pod targetPort (e.g., 8080)
  |
  v
Spring Boot server.port=8080
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: app
          image: my-shop-app:latest
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_PORT
              value: "8080"
~~~

Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: shop-api
spec:
  selector:
    app: shop-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

`containerPort` mainly declares/documents the container's port. Service `targetPort` must point to the port the process is actually listening on.

### 18.1. Probes must call the right port/path

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 15
~~~

Probe endpoints must be enabled/configured according to the application. If Actuator runs on a separate management port, probes must point to that port.

If Spring Boot binds `127.0.0.1` inside a Pod, kubelet or clients from the Pod network may not be able to reach it via Pod IP. Configure a bind address suited to the topology and control access with network/security policies.

## 19. The management port can also be occupied

Actuator can run management endpoints on a separate port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
~~~

Both the application server and management server must bind their respective ports. If port 9001 is already occupied, the application can fail while initializing the management web server even though port 8080 is free.

Check `server.port`, `management.server.port`, management address, container mappings, and other processes.

## 20. Tests independent of fixed ports

### 20.1. Random-port integration test

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HealthHttpTest {

    @LocalServerPort
    int port;

    @Test
    void serverBindsToAvailablePort() {
        assertThat(port).isBetween(1, 65535);
    }
}
~~~

You can inject `TestRestTemplate` or `WebTestClient` appropriately to send HTTP requests to the running server.

### 20.2. MOCK does not test TCP binding

`@SpringBootTest(webEnvironment = MOCK)` is not equivalent to starting an embedded server on a real TCP port. If you want to catch port conflicts, use `RANDOM_PORT` or a runtime smoke test.

### 20.3. Non-web test

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.main.web-application-type=none"
)
class ImportJobContextTest {
}
~~~

This test does not require a server to bind a port. Do not use it to conclude that a REST API has a listener.

### 20.4. Checking the context type

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WebApplicationStartupTest {

    @Autowired
    ApplicationContext context;

    @Test
    void startsAsServletWebApplication() {
        assertThat(context)
                .isInstanceOf(ServletWebServerApplicationContext.class);
    }
}
~~~

This assertion is only suitable if the application is designed as a Servlet application. For WebFlux, assert the corresponding reactive context. Avoid locking down implementation details if the application intentionally supports multiple modes.

## 21. Diagnosing from logs and exceptions

### 21.1. App logs Started yet has no port

Check:

1. Is `spring.main.web-application-type=none` configured?
2. Did auto-detection select Non-web due to the runtime classpath?
3. Are you running a batch/worker module instead of the API module?
4. Is `server.port=-1` configured?
5. Are there logs confirming the embedded server started?

A non-web application can still print `Started ...` successfully.

### 21.2. Unable to start web server

Read the root cause in the stack trace:

- Missing `ServletWebServerFactory` or `ReactiveWebServerFactory`.
- Embedded server dependency absent from the runtime classpath.
- Invalid server/connector/SSL configuration.
- Port/address bind failure.
- Buggy custom factory or server customizer.

Do not stop at the wrapper exception `ApplicationContextException`. Locate the root exception and related configuration.

### 21.3. Port already in use

Confirm the listening process and PID/owner. Then decide whether to stop the old instance, choose another port, use a random port in tests, adjust host-port mappings, or check a separate management port.

### 21.4. App runs yet clients cannot connect

Check the process, listener, client host/port, bind address, firewall/security group, Docker publish mapping, Kubernetes Service `targetPort`, TLS scheme/certificate, and context path/reverse proxy prefix.

## 22. Symptom and remediation table

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| App starts without opening HTTP | Web type `NONE` | Check `spring.main.web-application-type` |
| MVC and WebFlux present yet runs Servlet | Boot prioritizes MVC when both exist | Confirm dependencies and set reactive explicitly if intended |
| `No ServletWebServerFactory` | Missing embedded Servlet server at runtime | Check starters/exclusions/scopes |
| `No ReactiveWebServerFactory` | Missing reactive server implementation | Check WebFlux/server dependencies |
| Compiles yet startup lacks server | Dependency only at compile or excluded at runtime | Fix runtime dependency configuration |
| `Port 8080 already in use` | Another process is listening | Identify PID, stop gracefully, or change port |
| Port 0 yet client calls localhost:0 | Confusing requested port with actual port | Read the actually bound port |
| App binds 127.0.0.1 in container | Loopback-only listener | Bind an appropriate interface, check network policy |
| Docker publish conflict | Host port used by another process/container | Change host mapping or stop owner |
| Wrong Docker mapping | Host port maps to wrong container port | Fix `-p`/Compose `ports` |
| Kubernetes probe fails | Wrong port/path or bind address | Check listener, management port, and probe config |
| Management endpoint fails to come up | `management.server.port` occupied | Check the separate management port |
| `Cannot assign requested address` | Bind address absent on host/container | Pick a valid interface address |
| `Permission denied` | Bind permissions or network policy | Check privileges/capabilities |
| Works locally, fails to open port in production | Different profile/env/CLI/network | Compare runtime config and deployment topology |

## 23. Quick diagnostic commands

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Windows PowerShell:

~~~powershell
netstat -ano | findstr :8080
Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-Process -Id <PID>
~~~

Linux:

~~~bash
ss -ltnp 'sport = :8080'
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

HTTP check:

~~~bash
curl -v http://localhost:8080/actuator/health
~~~

If Actuator is absent or health is not exposed, call an actual endpoint. `Connection refused` differs from HTTP 404: 404 shows an HTTP server received the request yet found no matching route.

## 24. Practice exercises

### Exercise 1 — Identify the three web types

Create three small applications: Servlet MVC, WebFlux, and non-web command-line. Record the context type, startup log, and presence/absence of an HTTP listener.

### Exercise 2 — Intentionally select NONE

Set `spring.main.web-application-type=none` in an application with a controller. Run the application and verify the process can start while HTTP URLs are not served. Then switch back to servlet.

### Exercise 3 — Dependency missing server

Create a Servlet project and exclude embedded Tomcat from runtime dependencies without adding a replacement server. Observe the startup error. Use Gradle dependencyInsight or Maven dependency tree to find the cause.

### Exercise 4 — MVC and WebFlux on the same classpath

Add both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Observe the default application type. Then try `spring.main.web-application-type=reactive` and confirm a reactive server dependency is available.

### Exercise 5 — Port conflict

Run a first application on 8080. Start a second instance also on 8080. Observe the BindException. Identify the PID of the first process and stop it gracefully.

### Exercise 6 — Random port test

Write `@SpringBootTest(webEnvironment = RANDOM_PORT)` and inject `@LocalServerPort`. Run multiple tests or projects in parallel, confirming there is no need to hardcode 8080.

### Exercise 7 — Bind address

Run the application with `server.address=127.0.0.1` and try accessing it from another machine/namespace. Switch to an appropriate address and explain the security impact of wildcard binding.

### Exercise 8 — Docker port mapping

Run a container with `server.port=8080` and mapping `18080:8080`. Call host port 18080. Then intentionally mis-map `18080:9090` to observe the connection error.

### Exercise 9 — Management port conflict

Set app port 8080 and management port 9001. Occupy 9001 with another listener, then start the application. Analyze why the app port is free yet the management server still fails.

### Exercise 10 — Property precedence

Set `server.port=8080` in YAML, `SERVER_PORT=9090` in environment, and `--server.port=10080` on the command line. Determine the effective port, then remove each override one by one.

### Exercise 11 — Kubernetes probe

Create a Deployment with `containerPort`, a Service `targetPort`, and readiness/liveness probes. Change the Spring Boot port without updating probes, observe the unready state, and then fix the mapping.

### Exercise 12 — Classify network errors

Compare Address already in use, Cannot assign requested address, Permission denied, Connection refused, and HTTP 404. Note which errors belong to binding, which belong to routing/client, and which prove the server received the HTTP request.

## 25. Key takeaways

When a Spring Boot application does not open a port, separate **web application type**, **embedded server runtime dependency**, and **network binding**. `WebApplicationType.SERVLET` is for the Servlet stack, `REACTIVE` is for the reactive stack, and `NONE` creates a non-web application with no HTTP listener. When both MVC and WebFlux are present, Boot normally prioritizes MVC/Servlet; using `WebClient` does not mean the server must be reactive.

An application needing a server must have the proper server implementation on the runtime classpath. `spring-boot-starter-web` typically supplies embedded Tomcat; `spring-boot-starter-webflux` typically supplies Reactor Netty. If the server is excluded or only on the compile classpath, code may compile yet fail to create a web server.

The default port is typically 8080 and can be changed with `server.port`, environment variable `SERVER_PORT`, or command-line `--server.port`. When a port is occupied, identify the PID/process before stopping; use port 0 for tests to avoid contention. If the server runs yet other machines cannot connect, check `server.address`, firewalls, and port mappings.

In Docker/Kubernetes, distinguish **host port**, **container port**, **Service port**, and `targetPort`. `EXPOSE` does not automatically open a listener; the application must bind the port inside the container, and network mappings must target that exact port. After every change, check startup logs, the actual listener, and HTTP requests against the right artifact/environment.
