# Customizing TomcatServletWebServerFactory and Connectors

## 1. Context: How Does Spring Boot Manage Embedded Tomcat?

In a Spring Boot application running on the Servlet model, the HTTP server can be packaged directly inside the application rather than deploying a WAR file to a standalone Tomcat. With spring-boot-starter-web and the default Tomcat dependency, Spring Boot creates an embedded Tomcat, configures the required components, and starts it alongside the ApplicationContext.

The key component is **TomcatServletWebServerFactory**, a Tomcat-specific implementation of ServletWebServerFactory. The factory receives settings such as HTTP port, context path, SSL, connector customizers, context customizers, and Tomcat options before creating TomcatWebServer. In standard scenarios, Spring Boot auto-configures the factory; the application only supplies matching properties or customizers.

A **Connector** is the Tomcat component that accepts network connections over a given protocol, such as HTTP/1.1. It manages the listening port, protocol settings, connection timeouts, connection counts, and passing valid requests into Tomcat's processing engine. A Connector is not a Spring MVC controller, not a REST endpoint, and not equivalent to an ApplicationContext.

A conceptual diagram:

~~~text
Spring Boot application
  |
  +-- ServletWebServerApplicationContext
  |     |
  |     +-- TomcatServletWebServerFactory (configured before start)
  |             |
  |             +-- TomcatWebServer / Tomcat runtime
  |                     |
  |                     +-- Service
  |                     |     +-- Connector :8080 -> HTTP/1.1
  |                     |     +-- Connector :8081 -> HTTP/1.1 (if added manually)
  |                     |     |
  |                     |     +-- Engine -> Host -> Web Context
  |                     |
  |                     +-- Servlet filters / DispatcherServlet
  |                                       |
  |                                       +-- Spring MVC controller
  |                                               |
  |                                               +-- service/repository
  |
  +-- WebServerFactoryCustomizer bean(s)
        |
        +-- Adjust factory/connector before creating server
~~~

The actual path also includes sockets, protocol handlers, adapters, security filters, valves, async servlet processing, and other infrastructure layers. The diagram simply highlights the boundary: **the factory creates/configures the server; the connector handles the network protocol; Servlet and Spring MVC process requests**.

### 1.1. Classes to Distinguish

| Component | Role | When to care |
|---|---|---|
| ServletWebServerFactory | Contract for creating an embedded Servlet web server | Understanding how Boot selects Tomcat/Jetty/Undertow |
| TomcatServletWebServerFactory | Factory dedicated to embedded Tomcat | Adding connectors or using Tomcat-specific hooks |
| WebServerFactoryCustomizer<T> | Callback mutating the factory before server startup | Preferred extension mechanism for programmatic configuration |
| TomcatConnectorCustomizer | Callback modifying the Connector created by the factory | Tuning primary HTTP connector settings |
| TomcatProtocolHandlerCustomizer | Callback customizing the protocol handler | Accessing protocol settings underneath Connector |
| org.apache.catalina.connector.Connector | An actual Tomcat connector instance | Adding a second HTTP listener, configuring scheme/port |
| TomcatContextCustomizer | Callback customizing the web Context | Setting specialized Servlet context attributes |
| TomcatWebServer | Lifecycle controller for the created server | Startup, stop, actual port, and Boot integration |

TomcatServletWebServerFactory applies to the **Servlet stack**, typically Spring MVC. When running WebFlux on the reactive model, factory types and web server lifecycles can differ; do not copy Servlet configuration blindly to a reactive app merely because Tomcat is on the classpath.

### 1.2. Prerequisites Before Customizing

- The application must actually run on embedded Tomcat Servlet. If the Tomcat starter was replaced with Jetty/Undertow, Tomcat-specific customizers have no matching factory to apply to.
- In a standard Servlet application, avoid declaring a second factory bean. Spring Boot already creates the default factory, and the customizer ecosystem is designed to adjust it.
- If deploying a WAR to an external Tomcat, connector configuration belongs to the external Tomcat. An embedded factory inside the app does not control that container's ports.
- Configuration must happen before the connector starts. Changing properties or mutating the factory object after the server is running does not make Tomcat switch listeners immediately.
- Factory/protocol class APIs can change across Spring Boot and Tomcat versions. Check documentation for your exact running version when using advanced options.

## 2. Choosing the Configuration Approach by Need

In most applications, start with application.yml or application.properties. Spring Boot already provides numerous properties for server.port, server.address, SSL, Servlet sessions, thread pools, timeouts, connection limits, and access logs. When a suitable property exists, that approach is easier to operate: values can vary per environment and be read centrally without recompiling code.

| Need | Appropriate approach | Reason |
|---|---|---|
| Change primary HTTP port | server.port | Concise, supports profiles/environments |
| Select network interface | server.address | Avoids hardcoding in Java |
| Change context path | server.servlet.context-path | A Servlet application property |
| Max threads, max connections, accept queue | server.tomcat.* | Boot already supports binding and customizers |
| Configure primary SSL/TLS listener | server.ssl.* or SSL bundles | Uses Boot's official SSL mechanism |
| Tune a Connector attribute lacking a property | WebServerFactoryCustomizer<TomcatServletWebServerFactory> | Calls Tomcat API directly, narrow scope |
| Modify primary connector's protocol handler | TomcatConnectorCustomizer or TomcatProtocolHandlerCustomizer | Targets the right protocol layer |
| Open another HTTP/HTTPS port on the same Tomcat | addAdditionalTomcatConnectors | Adds and configures a new Connector |
| Customize web Context, Valve | Corresponding factory hooks | When Tomcat-specific behavior is truly required |
| Take full control of creating Tomcat factory | Declare custom ServletWebServerFactory bean | Advanced option; must check auto-customizers |

Avoid turning every property into a Java customizer. A bean hardcoding setPort(9000) can unintentionally override an environment-configured server.port; customizer execution order also becomes something you must track.

## 3. Common Tomcat Configuration via application.yml

Example for a Spring MVC application that already has the web starter:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
  servlet:
    context-path: /api
  tomcat:
    threads:
      max: 200
      min-spare: 10
    max-connections: 8192
    accept-count: 100
    connection-timeout: 20s
    keep-alive-timeout: 20s
    max-keep-alive-requests: 100
~~~

Values here only illustrate the properties; they are not recommended defaults for every production workload. Different Boot versions may change the property list and defaults. Before tuning, measure real resources, traffic, latency, and connection limits.

Explanation of each group:

- **server.port**: primary HTTP port created by the factory. If set to 0, the OS selects an available port at startup, useful in integration tests.
- **server.address**: network address the server binds to. 0.0.0.0 listens on matching IPv4 interfaces; use 127.0.0.1 to restrict access to localhost. Consider IPv6 and real environment setups separately.
- **server.servlet.context-path**: URL prefix of the Servlet application. With /api, a controller mapped to /hello is reached at /api/hello.
- **server.tomcat.threads.max**: maximum worker threads in the corresponding thread pool configuration. Not equivalent to max connections or requests per second. With virtual threads, some traditional pool options may no longer behave as before.
- **server.tomcat.threads.min-spare**: minimum idle worker threads Tomcat maintains in the standard thread pool model.
- **server.tomcat.max-connections**: connection limit accepted and handled concurrently by Tomcat. Do not treat this as business concurrency or DB connection pool size.
- **server.tomcat.accept-count**: queue length limit for incoming connections waiting when server acceptance capacity is reached; the OS may enforce a different actual backlog.
- **server.tomcat.connection-timeout**: timeout during request reading on a new connection. Not the total timeout of a controller or database query.
- **server.tomcat.keep-alive-timeout**: wait duration for the next HTTP request on a keep-alive connection.
- **server.tomcat.max-keep-alive-requests**: maximum requests served before a keep-alive connection must close, per Tomcat semantics.

Do not blindly raise max-connections, threads.max, and accept-count together just because you see 5xx errors. If the bottleneck is a DB connection pool, slow queries, or downstream client timeouts, enlarging queues may only cause requests to queue longer and consume more memory.

## 4. Customizing the Primary Connector via WebServerFactoryCustomizer

When you need to tune an attribute without a matching Boot property, register a WebServerFactoryCustomizer for TomcatServletWebServerFactory. This lets Spring Boot keep ownership of factory creation and default settings.

The example below configures the Servlet async processing timeout on the connector created by the factory. File src/main/java/dev/example/web/TomcatConnectorConfig.java:

~~~java
package dev.example.web;

import java.time.Duration;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TomcatConnectorConfig {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            primaryConnectorCustomizer() {

        return factory -> factory.addConnectorCustomizers(connector -> {
            connector.setAsyncTimeout(Duration.ofSeconds(20).toMillis());
        });
    }
}
~~~

This is a complete class to place in a Spring Boot Servlet application with embedded Tomcat. Java 17+ works. Here, the code does not create a new ServletWebServerFactory; the callback simply registers a customizer for the default connector.

Call flow explanation:

1. Spring Boot finds the WebServerFactoryCustomizer bean.
2. When preparing embedded Tomcat, the customize callback receives TomcatServletWebServerFactory.
3. addConnectorCustomizers registers a callback applied to the Connector created by the factory.
4. Before Tomcat serves traffic, the callback configures the Connector's properties.
5. Tomcat then starts according to the ApplicationContext lifecycle.

A connector's **async timeout** relates to asynchronous Servlet processing, not a guarantee that every endpoint always returns within 20 seconds. A blocking controller, JDBC query, or HTTP client call has its own timeouts. Configure and handle timeouts at the appropriate layer.

### 4.1. Customizing the Protocol Handler Type-Safely

When deeper HTTP protocol tuning is needed, Connector exposes getProtocolHandler(). In typical embedded Tomcat HTTP/1.1 configurations, the handler can be an implementation of AbstractHttp11Protocol.

Illustrative snippet, which can be placed inside the addConnectorCustomizers callback from the previous example:

~~~java
factory.addConnectorCustomizers(connector -> {
    if (connector.getProtocolHandler()
            instanceof org.apache.coyote.http11.AbstractHttp11Protocol<?> http) {
        http.setMaxKeepAliveRequests(120);
        http.setConnectionTimeout(15_000);
    }
});
~~~

This snippet requires a factory variable of type TomcatServletWebServerFactory provided by an enclosing customizer. It is not a standalone runnable Java class.

Use an instanceof check to avoid casting an incompatible handler to AbstractHttp11Protocol. If the application strictly requires HTTP/1.1, fail explicitly when the handler type is unexpected instead of silently skipping. If a matching property already exists, prefer setting the property rather than calling protocol handler setters manually.

TomcatServletWebServerFactory also has addProtocolHandlerCustomizers for directly registering a TomcatProtocolHandlerCustomizer. Choose the connector-level or protocol-level hook matching what you are tuning; avoid setting the same parameter through multiple channels at once, which makes the final value hard to trace.

### 4.2. Do Not Confuse with Replacing the Factory via a New Bean

You can declare your own TomcatServletWebServerFactory or ServletWebServerFactory bean, though that is an advanced path. Spring Boot will skip creating the default factory of the same type when a suitable bean already exists, and you must understand how remaining auto-customizers apply to the new factory.

Declaring a new factory merely to change the port is usually unnecessary:

~~~java
// Unnecessary if the goal is only to change server.port:
@Bean
TomcatServletWebServerFactory customFactory() {
    return new TomcatServletWebServerFactory(9000);
}
~~~

This snippet only illustrates the object, not a complete configuration to put into production. A custom @Bean can alter web server selection and active extension points. Use server.port or WebServerFactoryCustomizer first, and only replace the factory for a specific architectural requirement.

## 5. Adding an HTTP Connector on a Second Port

A single Tomcat Service can hold multiple Connectors. For example, the primary application uses port 8080 and needs an extra port 8081 for internal testing. Spring Boot 3.3 supports factory.addAdditionalTomcatConnectors(Connector...).

File src/main/java/dev/example/web/ExtraTomcatConnectorConfig.java:

~~~java
package dev.example.web;

import java.time.Duration;

import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExtraTomcatConnectorConfig {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            additionalHttpConnectorCustomizer() {

        return factory -> {
            Connector additional =
                    new Connector("org.apache.coyote.http11.Http11NioProtocol");

            additional.setPort(8081);
            additional.setScheme("http");
            additional.setSecure(false);
            additional.setURIEncoding("UTF-8");
            additional.setAsyncTimeout(Duration.ofSeconds(20).toMillis());

            factory.addAdditionalTomcatConnectors(additional);
        };
    }
}
~~~

This is a complete class to place in a Spring Boot MVC application with embedded Tomcat. You do not need to declare another Tomcat or DispatcherServlet. Both ports belong to the same Tomcat/web application, so they generally reach the same Servlet mappings, filter chains, and controllers. For example, a GET /hello controller can be reached via both localhost:8080/hello and localhost:8081/hello when there is no context path and both ports are accessible.

**Very easy-to-miss detail:** TomcatConnectorCustomizer callbacks registered via addConnectorCustomizers **do not automatically apply to additional connectors** added with addAdditionalTomcatConnectors. If connector 8081 needs custom timeouts, URI encoding, protocol limits, or SSL, configure them directly on that Connector/protocol handler object. Do not assume the primary port's policies are copied onto the secondary port.

### 5.1. Configuring the Additional Port via Application Properties

Hardcoding 8081 is convenient for an example, yet can cause collisions in container or multi-instance setups. In real projects, move the port into a dedicated property:

~~~yaml
server:
  port: 8080

app:
  server:
    extra-http-port: 8081
~~~

Then use @Value or @ConfigurationProperties to read the value and decide whether to enable the secondary connector per environment. Validate the port range (typically 1–65535), detect collisions with server.port, control the bind address, and only expose the port on network infrastructure when explicitly required.

If your only goal is separating the Actuator/health port, inspect management.server.port and management.endpoints.web.* before adding a Connector manually. The management port may need different security, routing, and network policies than the business port.

### 5.2. An Extra Connector Does Not Create a Second Application

Adding a Connector adds another network entry point to **the same Tomcat service/web context**. It does not spawn an extra ApplicationContext, create a second set of controllers, or isolate resource pools per port.

If you need an internal API with a completely separate endpoint set, access permissions, or lifecycle, an extra Connector alone does not establish a security boundary or independent deployment. Consider an appropriate architecture: Boot's management port, suitable security filter chains, reverse proxy policies, or a separate service.

### 5.3. Why Adding a Connector Does Not Automatically Switch HTTP to HTTPS

setScheme("http") and setSecure(false) describe request semantics on that connector; they do not enable TLS or redirects. When the primary port enables TLS via server.ssl.*, an extra HTTP connector remains plain HTTP unless SSL is configured on it explicitly. Both ports can route into the application, yet transport and security policies differ.

Do not expose an extra plain HTTP connector to the Internet when business rules require TLS. In production, prefer Boot's official TLS/SSL mechanism or TLS termination at a trusted reverse proxy/load balancer; if you must configure an extra HTTPS connector, configure SSLHostConfig, certificates, private keys, protocols/ciphers, and test the handshake on that connector specifically.

## 6. Runnable Two-Port Spring Boot Example

To verify in practice, assume a Spring Boot 3.x project with Java 17+ and Gradle declaring:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

In the same package or a subpackage of the @SpringBootApplication class, add ExtraTomcatConnectorConfig from section 5. Create controller src/main/java/dev/example/web/HelloController.java:

~~~java
package dev.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello from embedded Tomcat";
    }
}
~~~

If the application already has a @SpringBootApplication main class scanning package dev.example.web, just add the configuration and controller files to the project. If creating a new project, you can use this main class:

~~~java
package dev.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

The file must be named DemoApplication.java and sit in the matching package. The example assumes build.gradle already has the Spring Boot plugin and a suitable Maven repository; the dependency snippet above does not form a complete Gradle build by itself.

Set application.yml:

~~~yaml
server:
  port: 8080
~~~

Run the application from the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows use gradlew.bat bootRun. In another terminal, verify:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8081/hello
~~~

Under normal execution, both requests return HTTP 200 and body:

~~~text
hello from embedded Tomcat
~~~

The example does not require identical output headers across environments. If the controller has a context path like /api, request /api/hello on both ports. If Spring Security is present, security filters and authorization rules may turn the result into 401/403; that does not mean the connector failed to open.

To check listening sockets on Linux:

~~~bash
ss -ltn
~~~

Or on Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName localhost -Port 8080
Test-NetConnection -ComputerName localhost -Port 8081
~~~

A successful TCP connect only proves the port accepts connections. Curling the endpoint further checks the HTTP/Servlet/controller path. To conclude an application is ready to serve traffic, evaluate readiness and required dependencies separately.

### 6.1. Testing Port Conflicts

If another process already occupies 8081, the additional connector may fail to start. Do not ignore startup errors and assume the app is serving on both ports. Inspect logs and port ownership, confirm whether the container threw an error or which port stayed active, and then adjust ports per environment config.

In a multi-port container, you must also configure Docker port publishing, Kubernetes containerPort/Service targetPort, security groups, or firewalls. Tomcat opening a port inside the container does not automatically make it reachable from outside.

## 7. Understanding Connection and Thread Limits Carefully

Connector tuning often involves performance, so distinguish these limits:

| Setting | What does it limit? | Not equivalent to |
|---|---|---|
| threads.max | Worker threads under the corresponding thread pool mechanism | TCP connections or requests per second |
| max-connections | Connections Tomcat accepts/handles concurrently | JDBC connections or active controller executions |
| accept-count | Connection queue length once acceptance limit is reached | Queue of all requests in Spring MVC |
| connection-timeout | Wait time reading a request on a connection at the connector layer | Database or total transaction timeout |
| keep-alive-timeout | Duration an idle connection stays open waiting for the next request | Execution timeout of an active business request |
| max-keep-alive-requests | Maximum requests served on a single keep-alive connection | Total requests across the application |
| async timeout | Wait time for asynchronous Servlet processing where applicable | Covering all blocking timeouts |
| DB connection pool max | DB connections granted by the pool | TCP connections to Tomcat |

Suppose a service receives 500 requests/second and each synchronous request holds a thread for ~0.4 seconds. An initial concurrency estimate is 500 × 0.4 = 200 requests in flight/waiting (assuming steady state, ignoring bursts). This illustrates pressure on worker threads, yet cannot alone determine threads.max. Measure p95/p99 latency, blocking I/O, DB pool, CPU, and peak load.

If too many threads concurrently call a database with a small pool, threads queue on the pool; raising worker threads indefinitely adds zero DB capacity. If max-connections is too high, sockets, buffers, and file descriptors consume resources. If accept-count is too small under bursty load, clients see connection errors; if too large, requests wait longer and exceed client timeouts.

In Java 21 environments supporting virtual threads, verify Spring Boot/Tomcat versions, virtual thread enablement, and relevant metrics before applying platform-thread pool assumptions directly. Connection limits, DB pools, CPU, and timeouts still exist regardless of thread model.

### 7.1. Keep-Alive Is an Optimization with a Cost

HTTP keep-alive reuses TCP connections, reducing new connections and potentially cutting handshake overhead. However, idle connections still consume resources; an overly long keep-alive timeout with many clients increases resident sockets.

Traffic behind a reverse proxy involves two connection hops: client ↔ proxy and proxy ↔ Tomcat. Check timeouts, idle settings, and connection reuse on both. If the proxy keeps connections open longer than Tomcat, connection-reset errors can occur when the proxy tries to reuse a connection Tomcat already closed.

Do not blindly raise keep-alive timeout to fix slow controllers; the two timeouts serve different purposes.

## 8. SSL/TLS, Reverse Proxies, and Forwarded Headers

A common operational bug is running plain HTTP behind a TLS proxy while generating redirect URLs or cookie security flags that do not match the external URL. A connector receiving HTTP from a proxy sees scheme=http and local port 8080, while the browser accesses https://example.com. Spring Boot provides forwarded-header handling and container integration settings.

Depending on your environment, you can use:

~~~yaml
server:
  forward-headers-strategy: native
~~~

Or pick the framework strategy when appropriate. Configuration must restrict **trusted proxies** so external clients cannot spoof X-Forwarded-* headers to falsify scheme, host, IP address, or redirects. When using Tomcat native, understand RemoteIpValve and corresponding proxy trust settings.

Notes:

- server.ssl.* configures TLS on the Boot-managed primary connector; a manually added connector does not automatically inherit all TLS settings of the primary port.
- If TLS termination happens at ingress/load balancer, traffic to the application may be HTTP inside the internal network; clear network and forwarded-header policies are still needed.
- If both HTTP and HTTPS listeners exist, deciding whether to redirect or block HTTP must be configured and tested. Having an HTTPS port does not automatically redirect HTTP.
- Use server.servlet.session.cookie.secure, SameSite, and appropriate cookie policies when managing sessions; do not rely on setSecure on Connector as a replacement for complete session policy.
- Do not expose AJP or administrative connectors to public networks without clear justification and protection.

### 8.1. Adding an Internal Connector Can Alter the Attack Surface

A second connector is a new network listener and may inadvertently expose every controller and filter chain in the application. Review:

- Bind address and firewall/network policy for each port.
- Required TLS and authentication on each entry path.
- Potential bypassing of a reverse proxy responsible for rate limiting, WAF, authentication, or request-size limits.
- Per-port logs, metrics, and monitoring to detect unexpected traffic.
- Access permissions for health, Actuator, and internal endpoints.

Spring Security in the Servlet filter chain generally still applies to requests entering the same web context, whereas protections enforced at the reverse proxy will not apply if clients connect directly to the secondary port. Design around actual request paths.

## 9. How Do Factory Hooks Differ from Connector Hooks?

TomcatServletWebServerFactory offers specialized extension points:

| Hook | Target object | Scenario |
|---|---|---|
| addConnectorCustomizers | Connector configured by the factory | Primary listener attributes, URI/async timeout |
| addProtocolHandlerCustomizers | ProtocolHandler of the factory-configured connector | Detailed HTTP/1.1 protocol tuning |
| addAdditionalTomcatConnectors | New Connector added to Tomcat | Opening an extra HTTP/TLS listener |
| addContextCustomizers | Tomcat Context | Web application context configuration |
| addContextValves | Tomcat Context Valve | Context-pipeline-level processing |
| addEngineValves | Tomcat Engine Valve | Processing before dispatching down to host/context in pipeline |
| addContextLifecycleListeners | Context lifecycle listener | Observing/customizing specific lifecycle events |

A **Valve** belongs to Tomcat's pipeline; a **Servlet Filter** belongs to the Servlet API; a Spring MVC HandlerInterceptor sits deeper inside DispatcherServlet. These three differ in lifecycle, interception points, and configurability. For authentication, validation, header handling, logging, or common application policies, prefer Spring Security, Filters, HandlerInterceptors, or framework-level facilities if they meet requirements, and only reach for Tomcat-specific Valves when needed.

For instance, do not implement CORS handling with a Valve just to touch the connector. Spring MVC/Spring Security already provide CORS and security configuration. Likewise, upload size limits span reverse proxies, Servlet multipart resolvers, and server limits—do not try to solve them by tweaking a single HTTP connector parameter.

## 10. Customizer Execution Order and Avoiding Conflicts

Spring Boot includes auto-configured customizers (such as binding ServerProperties) and may also have application-declared customizers. If multiple customizers modify the same value, execution order shapes the final configuration. Do not rely on accidental ordering or inspect only application.yml while ignoring Java overrides.

A safe workflow:

1. Inventory all server configuration sources: application.yml/properties, profiles, environment variables, Spring Cloud config if present, WebServerFactoryCustomizers, Connector customizers, and protocol customizers.
2. Pick a single source of truth for each parameter and document why any override exists.
3. With multiple customizers, use explicit ordering when truly needed and avoid overriding the same property from two places.
4. Start the application with the target profile/deployment config.
5. Verify listening sockets, HTTP responses, metrics, and actual runtime values.
6. Re-test whenever upgrading Spring Boot or Tomcat.

If a newly added starter/library also registers a WebServerFactoryCustomizer, inspect the final runtime behavior before blaming Tomcat. Ordering and configuration sources are common reasons runtime values diverge from YAML files.

## 11. Observing, Load Testing, and Verifying Tuning Results

An application starting cleanly does not prove connector tuning worked. Verify each category of evidence:

**Configuration and endpoints:** check logged ports, confirm listening interfaces with ss/netstat, run curl on each port, and inspect status codes, redirects, HTTP schemes, and TLS handshakes if enabled. If a context path is configured, every request must include the prefix.

**Timeout behavior:** simulate slow clients, idle connections, and async endpoints in a test environment. Do not use one quick curl call to conclude connection timeout or keep-alive timeout works properly.

**Load and resources:** run load tests matching production connection counts, keep-alive, concurrency, and latency. Track CPU, heap, GC pauses, thread counts, open file descriptors, connection counts, error rates, and p50/p95/p99 latency.

**Downstream:** watch DB connection pools, HTTP client pools, queue lengths, network errors, and timeouts. Raising max-connections in Tomcat does not cure downstream service pool exhaustion.

**Spring Boot Actuator/Micrometer:** use /actuator/health and /actuator/metrics when enabled and properly secured. Exact metric names and availability depend on version, registry, and Tomcat MBean registry configuration. Avoid assuming a metric is always present on every setup.

**Deployment:** test rolling updates, graceful shutdown, readiness, connector counts after startup, and port reclamation when the JVM stops. Secondary ports must be accounted for in manifests, firewalls, and monitoring if present.

### 11.1. Testing Requests with Host or Forwarded Headers

In proxied environments, you can test further:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8081/hello
curl -i -H 'X-Forwarded-Proto: https' http://localhost:8080/hello
~~~

The third command is only for verifying once proxy trust policy is configured; never trust arbitrary forwarded headers and test against a public endpoint. For redirects, check the Location header; for sessions check Secure/SameSite; for authentication check policies on every entry path.

## 12. Common Errors and Diagnostic Steps

### 12.1. Customizer Does Not Run

**Symptom:** the application still uses defaults despite having a WebServerFactoryCustomizer<TomcatServletWebServerFactory> bean.

**Check:** whether the app actually runs embedded Servlet Tomcat rather than Jetty/Undertow; whether the bean is within component scan; whether conditional config is active; whether a different profile started; whether later customizers overwrite the value. For WebFlux apps, Servlet factory logic does not apply by default.

### 12.2. Secondary Port Does Not Open

**Symptom:** port 8080 works, yet 8081 is not LISTENing.

**Check:** whether addAdditionalTomcatConnectors ran during factory creation; whether the Connector has a valid port; whether the port is already occupied; bind address, firewall, container port publishing, and startup logs. Do not look only at the /hello route and miss that the port was never published to the host.

### 12.3. Secondary Connector Has Different Timeouts from Primary Port

**Common cause:** addConnectorCustomizers applies to factory-created connectors, not automatically to connectors added via addAdditionalTomcatConnectors. Configure the extra Connector and its protocol handler directly. Test each listener with an appropriate request/connection.

### 12.4. Server Logs Started, Yet API Is Not Ready

An open port proves the listener is active, not that ApplicationRunners finished, critical dependencies are ready, or the readiness probe is UP. Check /actuator/health/readiness, lifecycle logs, database, and downstream services. Do not treat "Tomcat started on port" as the sole signal to route load balancer traffic.

### 12.5. Adding an HTTP Port Exposes Internal APIs

When adding a port, all handlers in the same Servlet web context become reachable through it. If authentication, rate limiting, or TLS lived only on the reverse proxy in front of the primary port, the secondary port can create a bypass. Restrict network access, enforce per-connector security, and audit every exposed endpoint.

### 12.6. Increasing threads.max Yet Timeouts Persist

Timeouts may stem from database pools, locks, external HTTP clients, synchronous processing, or CPU. Inspect thread dumps, DB pool waits, request queues, GC, and latency. If using Java 21 virtual threads, verify the active thread model config to avoid misinterpreting threads.max.

### 12.7. Connections Reset Under Keep-Alive

A proxy or client may attempt to reuse a connection Tomcat already closed. Compare keep-alive/idle timeouts across client, proxy, and Tomcat; inspect retry idempotency and connection pooling. Avoid setting timeouts to infinity due to the risk of accumulating idle sockets.

### 12.8. HTTP 400/431/413 on Large Requests

Errors may involve header size, body size, parameter count, URL length, multipart limits, or proxy limits. Identify which layer rejects the request before raising max header size or connector limits. Raising limits requires considering memory, denial-of-service risk, and API contracts.

### 12.9. Secondary Port Redirects to HTTP Despite External HTTPS

Causes can include missing proxy forwarding configuration, differing SSL/secure/scheme settings across connectors, or improper proxy trust. Inspect Host, X-Forwarded-Proto, Location, cookies, and security chains directly per listener. Never trust all clients globally just to fix redirects.

### 12.10. Trying to Replace Embedded Tomcat with a Manually Constructed Instance

Manually creating a Tomcat object that does not integrate properly with Spring Boot's Servlet context can break auto-registration of Servlets, Filters, listeners, or Boot settings. Before writing a new factory, confirm whether properties, WebServerFactoryCustomizer, or factory hooks already solve the requirement.

## 13. Scenarios for Choosing the Right Customization Approach

**Scenario A — Only want to run on port 9090.** Use server.port=9090 or the corresponding environment variable. No TomcatServletWebServerFactory bean, addConnectorCustomizers, or new Connector is needed.

**Scenario B — Want to increase worker threads in an app handling blocking requests.** Start with server.tomcat.threads.max, measure real load, DB pool, and latency. If using virtual threads, verify the setting's effect first. Do not raise indefinitely.

**Scenario C — A product needs an internal HTTP port 8081.** Use WebServerFactoryCustomizer and addAdditionalTomcatConnectors, configure the new connector explicitly, and block external network access. Check endpoints, security, logs, and health on both ports.

**Scenario D — Want both HTTP and HTTPS on a single Tomcat.** Typically use server.ssl.* for the primary listener, then add another explicitly configured connector if needed. Having two connectors does not automatically redirect HTTP to HTTPS. Verify TLS, redirect policy, cookies, and forwarded headers.

**Scenario E — Want access logs and request diagnostics.** Check server.tomcat.accesslog.* and Spring Boot logging/Micrometer first. If the requirement sits at the HTTP controller layer, an interceptor/filter is usually easier to test and less coupled to Tomcat than a Valve.

**Scenario F — Want health/metrics served on a different port.** Look at management.server.port and Actuator settings. Only add an extra application Connector when you genuinely need to share the same Servlet context across multiple ports.

**Scenario G — Need specific URI encoding or async timeout limits.** Check server.tomcat.uri-encoding and timeout properties first; only when properties lack expressiveness use TomcatConnectorCustomizer or a protocol handler customizer.

## 14. Pre-Production Checklist

- [ ] Confirmed the application uses Servlet and embedded Tomcat, not an external container.
- [ ] Verified dependency tree, Spring Boot/Tomcat versions, and actual factory.
- [ ] Preferred server.* / server.tomcat.* / server.ssl.* for available options.
- [ ] Added WebServerFactoryCustomizer only when Tomcat-specific APIs are required.
- [ ] Explicitly defined port/bind address/protocol/timeout/SSL for every extra Connector.
- [ ] Did not assume primary connector's addConnectorCustomizers apply to extra connectors.
- [ ] Checked port conflicts and network exposure across Docker/Kubernetes/firewalls.
- [ ] Verified reverse proxy, trusted forwarded headers, HTTPS, redirects, and security.
- [ ] Separated HTTP listener, Servlet Filter, Spring Security, and MVC controller concerns in design.
- [ ] Did not conflate maxConnections, maxThreads, acceptCount, and DB pool size.
- [ ] Load tested and checked p95/p99 latency, CPU, GC, threads, connection counts, and downstream.
- [ ] Tested readiness/liveness, graceful shutdown, and startup failure handling.
- [ ] Maintained configuration rollback capability and measured before/after every change.
- [ ] Documented the final owner when multiple customizers affect the same parameter.

## 15. Principles to Remember

TomcatServletWebServerFactory is **the configuration and creation point for embedded Tomcat** in Spring Boot Servlet apps. A Connector is Tomcat's **network entry point**. A Spring MVC controller is the **business HTTP handling layer**. These three concepts serve distinct purposes, so apply changes at the right layer.

For common settings, application.yml is clearest and easiest to operate. For settings lacking a Boot property, WebServerFactoryCustomizer<TomcatServletWebServerFactory> is the supported extension point. When adding another listener, use addAdditionalTomcatConnectors and configure the additional Connector directly; customizers for the default connector are not applied automatically to it.

Any change to ports, threads, connections, timeouts, HTTP/HTTPS, or proxies must be verified with actual runtime results, not just startup logs. Measuring at the right layer, setting sensible resource limits, and enforcing security before deployment will keep application behavior clear and maintainable.

## 16. References

- Spring Boot 3.3 — Servlet Web Applications (Embedded Servlet Container Support and Programmatic Customization sections): https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Embedded Web Servers, Enable Multiple Connectors with Tomcat: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — TomcatServletWebServerFactory API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/tomcat/TomcatServletWebServerFactory.html
- Apache Tomcat 10.1 — HTTP Connector Configuration: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html