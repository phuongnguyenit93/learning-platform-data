# Boundary Between Spring Boot Properties and Server-Specific APIs

A web-enabled Spring Boot application usually runs an **embedded server**: Tomcat, Jetty, or Undertow for the Servlet model; and corresponding options for the reactive model. There are two main ways to configure an embedded server:

1. **Spring Boot-provided properties**: placed in application.yml, application.properties, environment variables, or startup arguments. Spring Boot reads, type-checks, and translates supported values into server settings.
2. **Server-specific APIs**: Java code directly interacting with factories, connectors, handlers, contexts, thread pools, listeners, or configuration objects provided by Tomcat/Jetty/Undertow.

The boundary is not whether a setting is simple or complex. It lies in **who owns the configuration contract**. With Spring Boot properties, the application depends on Boot's configuration contract. With server APIs, the application depends directly on the APIs and lifecycle of a specific server.

Usage principle: **look for a Spring Boot property first; if it cannot meet the need, use WebServerFactoryCustomizer and the server's API; declaring an entire WebServerFactory bean yourself is a last resort.**

## 1. Responsibility Diagram

~~~text
application.yml / environment / CLI
              |
              v
Spring Environment + property binding
              |
              v
Spring Boot ServerProperties and customizers
              |
              v
ServletWebServerFactory
  |             |             |
  v             v             v
Tomcat         Jetty        Undertow
  |             |             |
  v             v             v
Connector /   Server /      Builder /
Context       Handler       Listener
              |
              v
       HTTP request runtime
~~~

The path above explains why some properties work across multiple containers while others apply only when the matching container is running. Spring Boot does not necessarily expose every setter, listener, and hook of every server as properties.

Further distinctions:

- **Spring MVC** owns controller mappings, argument resolvers, converters, exception handlers, and framework-level request processing.
- **The Servlet container** owns HTTP connectors, connection acceptance, queues, worker threads, many TLS settings, and container lifecycle.
- **Spring Boot** wires the components together and passes supported properties down to the right layer.
- **The application** decides per-environment configuration values, extra customizers, and security/performance constraints.

Do not use Tomcat APIs to alter behavior owned by Spring MVC—such as JSON response mapping—simply because the application runs on Tomcat.

## 2. Three Configuration Layers and Examples

| Layer | Examples | Portability | When to use |
|---|---|---|---|
| Common Boot properties | server.port, server.compression.enabled, server.ssl.*, server.shutdown | Relatively high across supported containers, though implementation details may vary | Common needs with official properties |
| Container-scoped Boot properties | server.tomcat.threads.max, server.jetty.threads.max, server.undertow.threads.io | Tied to a specific server | Tuning container features already exposed by Boot |
| Server APIs | TomcatServletWebServerFactory.addAdditionalTomcatConnectors, Jetty server customizers, Undertow builder customizers | Low; depends on server and version | Hooks or structures that Boot properties cannot express |

A key starting with server.tomcat.* is still a **Spring Boot property**, even though its effect is Tomcat-specific. Conversely, calling org.apache.catalina.connector.Connector is a **Tomcat API**, even when executed inside a Spring Boot bean.

This distinction matters during upgrades: properties follow Spring Boot's support lifecycle and metadata, whereas server APIs are directly affected by the Tomcat, Jetty, or Undertow version managed by Boot.

## 3. Common Boot Properties: First Priority

Common settings in a Spring MVC application using an embedded server:

~~~yaml
server:
  port: 8080
  address: 127.0.0.1
  servlet:
    context-path: /demo
    session:
      timeout: 30m
      cookie:
        http-only: true
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Meaning:

- server.port selects the primary HTTP port; commonly defaults to 8080.
- server.address restricts which interface address the server binds to. For example, 127.0.0.1 serves only on the host's loopback.
- server.servlet.context-path adds a URL prefix for the Servlet application. When set to /demo, endpoint /ping is reached at /demo/ping.
- server.servlet.session.timeout sets session inactivity timeout.
- server.servlet.session.cookie.http-only configures container-managed session cookies.
- server.compression.enabled enables response compression per applicable thresholds and rules. It does not mean every response is compressed.
- server.shutdown=graceful asks the server to support graceful shutdown; actual stop time still depends on the server, in-flight requests, and lifecycle timeout.
- spring.lifecycle.timeout-per-shutdown-phase bounds how long a single lifecycle shutdown phase waits.

These examples belong to Boot 3.5.x. When using another version, check Common Application Properties for that exact version. Do not assume every property name exists or shares identical defaults across all versions.

### 3.1. Support Conditions Still Matter

Having a property does not mean every environment executes the exact same physical mechanism. For example:

- server.http2.enabled enables HTTP/2 support when server, TLS, and environment satisfy corresponding requirements.
- server.max-http-request-header-size defines a Boot-level limit, yet each HTTP server may interpret request-line and header sizes differently.
- server.ssl.* configures TLS for the primary connector within Boot's supported scope; TLS termination at a reverse proxy is a different architecture.
- Some pool or thread properties may no longer behave as expected when virtual threads are enabled or the runtime changes.

After configuring, test real server behavior and verify via operational telemetry. Do not see a property get read and assume the connector is running with the expected config.

## 4. Per-Server Boot Properties

Boot provides dedicated namespaces to expose server-specific capabilities many applications need.

### 4.1. Tomcat

~~~yaml
server:
  tomcat:
    threads:
      max: 200
      min-spare: 10
    accept-count: 100
    max-connections: 8192
    connection-timeout: 10s
    accesslog:
      enabled: true
~~~

This example uses properties under server.tomcat.*. They apply when Tomcat is the active embedded servlet server. Sample values are not optimal recommendations for every system; weigh CPU, memory, concurrent requests, I/O wait times, and load tests.

Common points of confusion:

- threads.max caps worker threads under the corresponding execution model; Spring Boot 3.5 explicitly notes this property has no normal effect when virtual threads are enabled.
- accept-count relates to the connection queue when processing limits are reached, not the total requests the system can tolerate.
- max-connections does not equal the number of request-processing threads.
- connection-timeout is not the total execution timeout of a controller.
- accesslog records requests at the container level; manage sensitive data, rotation, and disk capacity.

### 4.2. Jetty

~~~yaml
server:
  jetty:
    threads:
      max: 200
      min: 8
    connection-idle-timeout: 30s
~~~

These are Jetty properties exposed by Spring Boot under server.jetty.*. Swapping Tomcat for Jetty while keeping server.tomcat.threads.max will not give Jetty the same limit. Pool names and semantics differ, so consult Jetty documentation instead of mechanically copying numbers.

### 4.3. Undertow

~~~yaml
server:
  undertow:
    threads:
      io: 4
      worker: 32
~~~

server.undertow.threads.io and server.undertow.threads.worker tune Undertow's distinct thread groups. Separating I/O threads and worker threads matters greatly for blocking operations. Sample values must be benchmarked before applying in production.

An application should retain only settings relevant to its actual server. Unused properties for another container can be ignored silently or create a false impression that the system is tuned.

## 5. Boundary of Boot Properties: Scope and Contract

Boot properties form an **intentional configuration surface**. When Boot publishes server.tomcat.threads.max, it accepts responsibility for binding, validating as supported, and applying that setting via the proper factory/customizer.

Boot does not promise that:

1. Every Tomcat/Jetty/Undertow feature has a corresponding property.
2. A common property is implemented identically across every server.
3. Properties can update live without a restart.
4. A Tomcat property matches a Jetty property in name or value.
5. Every container-specific API stays stable across major version upgrades.

Do not invent keys like server.tomcat.some-advanced-switch expecting Boot to pick them up automatically. Keys outside Boot-supported metadata do not automatically invoke Tomcat setters. If you want application-owned config keys, declare your own namespace like app.server.* and write a `@ConfigurationProperties` class plus a customizer to apply it.

### 5.1. When Might Properties Not Suffice?

Examples of requirements that commonly lead to lower-level APIs:

- Adding a second HTTP connector to the same embedded Tomcat, with its own port and policies.
- Attaching a specialized Valve, handler, lifecycle listener, or hook for which Boot has no matching property.
- Configuring a new feature of the underlying server before Boot introduces an abstraction for it.
- Applying different settings across multiple connectors rather than one global value.
- Needing a customizer with complex conditional logic that a single property cannot describe.

Before picking an API, verify that **no higher-level property or abstraction** solves the requirement. For instance, to change the primary port, use server.port; do not edit Connector directly.

## 6. WebServerFactoryCustomizer: The Boot-Supported Low-Level Entry Point

Spring Boot provides the WebServerFactoryCustomizer interface so applications can customize the **factory before the embedded server starts**.

A simple Tomcat customizer:

~~~java
package com.example.boundary;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class TomcatBoundaryCustomizer
        implements WebServerFactoryCustomizer<TomcatServletWebServerFactory> {

    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        // You can add connectors, context customizers, or valves here.
    }
}
~~~

This is a structural example; it intentionally does not alter runtime behavior yet. The generic parameter is TomcatServletWebServerFactory, so this customizer targets embedded Tomcat on the **Servlet stack**.

Corresponding factories:

| Web stack | Tomcat | Jetty | Undertow | Reactor Netty |
|---|---|---|---|---|
| Servlet | TomcatServletWebServerFactory | JettyServletWebServerFactory | UndertowServletWebServerFactory | Not used for Servlet stack |
| Reactive | TomcatReactiveWebServerFactory | JettyReactiveWebServerFactory | UndertowReactiveWebServerFactory | NettyReactiveWebServerFactory |

Factory names and import packages can change across Boot major versions. Java snippets in this lesson use **Spring Boot 3.5.x** APIs; do not copy imports straight into Spring Boot 4.x without checking version documentation.

### 6.1. Which Part of the Factory to Configure?

- Common factories manage features like port, bind address, and SSL provided through abstractions.
- TomcatServletWebServerFactory allows adding Tomcat connectors, context customizers, and Tomcat extensions.
- JettyServletWebServerFactory allows Jetty-specific server customization.
- UndertowServletWebServerFactory allows configuring Undertow's builder or deployment.
- Deeper APIs like Tomcat Connector, Jetty ServerConnector, or Undertow Builder belong to each server's own dependency.

Using a customizer does not switch Spring MVC to WebFlux. Conversely, picking a reactive-stack factory is a different web server choice and requires understanding the active application model.

### 6.2. Do Not Recreate the Factory Unless Needed

If you declare your own ServletWebServerFactory or TomcatServletWebServerFactory bean, Spring Boot may back off from creating the default factory. Boot's auto-configured customizers can still run against the application-provided factory, so this is not a reliable way to "disable all defaults".

Creating your own factory brings responsibility for keeping desired integrations such as SSL, compression, sessions, access logs, and related setup. **Prefer WebServerFactoryCustomizer** to add only what you need while retaining default configuration.

## 7. Runnable Example: Primary Port via Property, Secondary Port via Tomcat API

Problem: a Spring MVC application running on Tomcat has its primary HTTP connector on port **8080** and needs an experimental HTTP connector on **8081** to demonstrate the configuration boundary. The primary port uses server.port. The second port is added through TomcatServletWebServerFactory because multiple connectors are a Tomcat-specific capability.

**Example scope:** Spring Boot 3.5.16, Java 17+, Maven, Spring MVC, embedded Tomcat. Two plain HTTP ports in this example are only for local/learning environments; real deployments need TLS, firewalls, bind addresses, and access policies planned.

Project structure:

~~~text
server-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/boundary/
    │   ├── BoundaryApplication.java
    │   ├── PingController.java
    │   └── AdditionalConnectorConfiguration.java
    └── resources/application.yml
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>server-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>server-boundary-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Starter Web uses embedded Tomcat by default. The Maven parent manages compatible dependency versions, avoiding unnecessary standalone Tomcat version pins.

### 7.2. BoundaryApplication.java

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

Place the startup class in the same root package as controllers/configurations so component scan discovers them.

### 7.3. PingController.java

~~~java
package com.example.boundary;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

The endpoint returns a fixed string to verify both connectors serve the same MVC application.

### 7.4. application.yml: The Spring Boot Part

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 64
~~~

server.port sets the primary port under Boot's contract. server.tomcat.threads.max is a Boot-provided property specific to Tomcat; it still belongs to the **Spring Boot configuration layer**, not a direct application call to Tomcat APIs.

### 7.5. AdditionalConnectorConfiguration.java: The Tomcat API Part

~~~java
package com.example.boundary;

import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("extra-connector")
public class AdditionalConnectorConfiguration {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            extraTomcatConnector() {

        return factory -> {
            Connector connector =
                    new Connector("org.apache.coyote.http11.Http11NioProtocol");
            connector.setPort(8081);
            factory.addAdditionalTomcatConnectors(connector);
        };
    }
}
~~~

Explanation:

1. @Profile("extra-connector") activates this configuration only when the extra-connector profile is enabled, avoiding accidentally opening an experimental port.
2. WebServerFactoryCustomizer receives the Boot-created TomcatServletWebServerFactory.
3. org.apache.catalina.connector.Connector is a Tomcat API, not a generic Spring Boot abstraction.
4. Http11NioProtocol creates an HTTP/1.1 NIO connector.
5. addAdditionalTomcatConnectors adds connector 8081 alongside primary connector 8080.
6. Spring MVC controllers continue to be served by the same application, without duplicating the ApplicationContext or manually building a second server.

This is the observable boundary: YAML describes the primary HTTP port; Java code describes an additional Tomcat-specific capability.

### 7.6. Build and Run

From the project root directory, requiring JDK 17+ and Maven:

~~~bash
mvn -q -DskipTests package
java -jar target/server-boundary-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=extra-connector
~~~

In another terminal:

~~~bash
curl -sS http://localhost:8080/ping
curl -sS http://localhost:8081/ping
~~~

The body of each response is:

~~~text
pong
~~~

When running **without** the extra-connector profile, the application creates only the Boot-managed primary connector; the customizer adding connector 8081 is not registered.

~~~bash
java -jar target/server-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

If port 8080 or 8081 is occupied by another process, the application may fail to start. Free the port or adjust the example ports in your learning environment. In production, never open an extra HTTP port without assessing TLS transport and network exposure.

## 8. What Happens When Switching Tomcat to Jetty or Undertow?

**server.port** remains a common Boot property, whereas configuration using TomcatServletWebServerFactory and Connector no longer applies to tuning Jetty or Undertow.

Switching the embedded server generally requires changing starter dependencies; for example with Maven for MVC, excluding spring-boot-starter-tomcat from spring-boot-starter-web and adding spring-boot-starter-jetty or spring-boot-starter-undertow. Versions and support depend on your active Spring Boot BOM.

Update configuration in three steps:

1. **Keep common properties** supported by the new server, such as server.port, server.servlet.context-path, or server.compression.enabled.
2. **Migrate server-specific property groups**: do not use server.tomcat.threads.max to tune Jetty's thread pool. Check corresponding server.jetty.* or server.undertow.* properties.
3. **Audit all server-specific imports and beans**: a customizer typed against TomcatServletWebServerFactory cannot simply be reused as-is for Jetty/Undertow; APIs and connector creation differ. In particular, once Tomcat dependencies are removed, code referencing Tomcat classes directly will no longer compile or load.

Place server-bound customizers in dedicated packages/modules, activate them only when the matching container is chosen, and keep integration tests for every supported configuration. Use conditional configuration or profiles only when they correspond directly to real application environments.

## 9. How Spring Boot Applies Properties and Customizers

In Spring Boot 3.5, Boot's auto-configured WebServerFactoryCustomizers typically have order **0**. Application-declared customizers may run later by default unless another order is specified. This means code modifications can overwrite values already set by Boot from properties.

Do not simultaneously:

- Set server.port=8080 in YAML.
- Write another customizer calling factory.setPort(9000).
- Expect both to be true.

Depending on execution order, one value ends up overridden. When an official property meets the need, keep that property as the single configuration source for that behavior.

If the application needs multiple customizers:

- Use @Order or Ordered when ordering is an explicit part of the design.
- Keep customizers independent and avoid mutating the same property in multiple places.
- Document which customizer creates connectors, configures TLS, adds listeners, or enforces policies.
- Check runtime after startup since proxy and environment settings can affect the outcome.

A WebServerFactoryCustomizer typically runs during startup before the server begins serving requests. Editing application.yml after the server is already running does not cause a new Connector to appear automatically; a supported restart/reconfiguration mechanism is required.

## 10. Do Not Confuse Server APIs with Servlet and Spring MVC APIs

Some needs should be handled at the framework or Servlet layer rather than modifying connectors:

| Need | Layer to check first |
|---|---|
| Change endpoint paths | Spring MVC's @RequestMapping, @GetMapping |
| Add interceptors | WebMvcConfigurer |
| Add a request Filter | FilterRegistrationBean or Servlet Filter |
| Add a custom Servlet | ServletRegistrationBean |
| Customize exception handling | @ControllerAdvice |
| Change JSON serialization | Jackson configuration or HTTP message converters |
| Upload size limits | spring.servlet.multipart.* and appropriate validation |
| Change port, session timeout, SSL | Boot's server.* properties |
| Add a Tomcat connector | TomcatServletWebServerFactory/Connector API |

For example, to log MVC request handling duration, an interceptor or filter is usually clearer than adding a Tomcat Valve. Only use a Valve when you truly need container-pipeline hooks and accept Tomcat coupling.

Also distinguish **server-side configuration** from **HTTP client configuration**. RestClient, RestTemplate, or WebClient for outbound upstream calls use their own connections and timeouts. Changing server.tomcat.connection-timeout does not adjust outbound WebClient timeouts.

## 11. TLS, Proxies, and Multiple Connectors

### 11.1. Primary Connector SSL/TLS

Spring Boot provides server.ssl.* and SSL bundle configuration in supported versions. Use properties/SSL bundles for standard TLS requirements.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
~~~

This snippet illustrates **configuration keys only**; to run, it requires a real keystore and appropriate secret/trust configuration. Never commit secret passwords into Git.

Important point: the second connector created directly via Tomcat API in section 7 is a **separate HTTP connector**. It does not automatically inherit all SSL/TLS policies from the primary connector. To add an HTTPS connector, configure connector/TLS via the corresponding API or terminate TLS at a proxy by design. Include secondary ports in security reviews.

### 11.2. Reverse Proxies and Forwarded Headers

When the application sits behind Nginx, ingress, or a load balancer, configure server.forward-headers-strategy to match the architecture. For Tomcat, Boot also offers server.tomcat.remoteip.* properties to tune trust and interpretation of proxy-sent headers.

Only trust forwarded headers arriving from proxies you control. If any external client can send X-Forwarded-For or X-Forwarded-Proto and the application blindly trusts them, URLs, schemes, or IP addresses used for auth/logging can be spoofed.

If built-in properties suffice, do not manually add a duplicate Tomcat RemoteIpValve. Misconfigured proxy header handling can cause redirect loops, missing Secure flags on cookies, or inaccurate audit logs.

### 11.3. Management Port Is Not a Second Application Port

When using Spring Boot Actuator, management.server.port can expose management endpoints on a separate port in supported configurations. This is Boot's management mechanism, not equivalent to adding another application connector to serve all controllers.

If the requirement is merely isolating health/metrics for operations, consider Actuator properties. Do not create an extra Tomcat connector just to simulate a management port.

## 12. Embedded JAR vs. External WAR Deployment Differences

**Executable JAR with embedded server:** the application owns factory lifecycle, connectors, and port binding. server.* properties and WebServerFactoryCustomizers apply per Boot's embedded server mechanism.

**WAR deployed to external Tomcat/Jetty:** the external container is usually configured by operators. The application does not create the host's connectors as in an embedded JAR. Settings like HTTP port, thread pool, and TLS of standalone Tomcat are governed by the external server. Do not expect a WAR app's TomcatServletWebServerFactory bean to change the port of the entire external Tomcat.

Spring MVC layers, Servlet Filters, controllers, and certain Servlet application settings can still operate appropriately for a WAR environment. However, the server operational boundary shifts to the external platform/container.

## 13. Testing to Verify the Boundary

### 13.1. Testing Property Values

Use Spring Boot integration tests with WebEnvironment.RANDOM_PORT to confirm the application starts an embedded server successfully and endpoints return expected content. Here Boot asks the OS for an ephemeral port; the actual port does not have to match the fixed value in application.yml.

Example test in a project with spring-boot-starter-test:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingHttpTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void ping() {
        String body = rest.getForObject("/ping", String.class);
        assertThat(body).isEqualTo("pong");
    }
}
~~~

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Do not enable the extra-connector profile in this test to avoid hardcoding port 8081 when multiple tests run concurrently.

### 13.2. Testing Tomcat-Specific Customizers

When enabling the extra-connector profile in a dedicated integration environment:

1. Start the application and confirm primary port 8080 answers /ping.
2. Confirm secondary port 8081 also answers /ping.
3. Disable the profile or remove the customizer and confirm this same app no longer creates the extra connector.
4. When swapping Tomcat for Jetty, remove/replace Tomcat-specific config and re-run startup tests.
5. Use an out-of-process socket/HTTP client to verify real ports; do not merely assert the bean exists.

End-to-end tests must run against the exact server and dependency versions planned for deployment. Unit tests calling customize(factory) directly cannot fully replace initializing and binding real connectors.

### 13.3. Observing Runtime

Useful checks:

- Read Spring Boot startup logs to see which server is running and its primary port.
- Enable --debug when analyzing the Condition Evaluation Report to see which auto-configurations matched or backed off.
- If monitoring Tomcat via MBeans, check server.tomcat.mbeanregistry.enabled instead of enabling it manually via API when Boot already provides a property.
- Use HTTP requests or port-inspection tools to verify actual listeners.
- For performance tuning, measure thread pools, connections, p95/p99 latency, and error rates under load rather than relying on static config.

With server.port=0, the real port is allocated at server startup; retrieve it from runtime info or WebServerInitializedEvent instead of re-reading server.port assuming it is the bound port.

## 14. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Set server.tomcat.threads.max yet Jetty still uses defaults | Running Jetty; property belongs to Tomcat | Switch to matching server.jetty.* properties and test behavior |
| Invented a server.* key yet nothing happens | Boot does not support that key or no code binds it | Check version's properties reference; for custom options use app.* + @ConfigurationProperties and customizer |
| server.port and customizer specify different ports | Two sources configuring the same setting | Use the property as the single source of truth if Boot supports it |
| App fails to start with port in use | Primary or secondary port already occupied | Check both 8080 and 8081, change ports, or stop conflicting process |
| Build fails after swapping Tomcat to Jetty | Code still imports TomcatServletWebServerFactory or Connector | Swap modules/customizers for the active server |
| Custom WebServerFactory bean loses defaults | Replaced auto-configured factory and missed related integrations | Prefer WebServerFactoryCustomizer; compare before and after configs |
| TLS works on primary port yet secondary port stays HTTP | Manually created extra connector does not inherit SSL settings | Configure TLS explicitly or place behind a proxy by design |
| server.max-http-request-header-size behaves differently across servers | Servers enforce limits differently | Read server docs and test real requests |
| Tuning Tomcat thread pool does not improve speed | Bottleneck is in database, I/O, or virtual-thread config | Measure real load and inspect non-server limits |
| Setting server.port in WAR does not change external Tomcat port | External container owns connectors | Configure the external server |
| Spoofed X-Forwarded-* headers falsify scheme/IP | Proxy trust config is too permissive | Trust only verified proxies; check server.forward-headers-strategy |
| Added management.server.port yet app endpoints do not appear there | Management port is for management endpoints | Use a separate app connector only when genuinely needed, with proper security |

## 15. Decision Process

Before adding Tomcat/Jetty/Undertow-dependent code:

1. **State the desired behavior clearly:** port, timeouts, TLS, thread pool, Valve, listener, or multiple connectors?
2. **Check official Boot properties:** look up Common Application Properties for your exact version.
3. **Confirm web stack and server:** Servlet or reactive; Tomcat, Jetty, Undertow, or Reactor Netty?
4. **Prefer matching properties:** common server.* or specific server.tomcat.*, server.jetty.*, server.undertow.*.
5. **If properties are insufficient, find the extension point:** WebServerFactoryCustomizer with the matching factory type; cross-check actual server APIs.
6. **Keep scope minimal:** avoid recreating the factory, avoid changing the same value in two places, and use profiles when features target only specific environments.
7. **Test against the real server:** ports, TLS, forwarded headers, concurrency, shutdown, and startup failures.
8. **Document migration cost:** note which libraries and APIs will require changes when upgrading Boot or switching containers.

A helpful self-check: if removing the Tomcat dependency still leaves the configuration meaningful, it is likely a Boot-level property/abstraction. If code must import org.apache.catalina.* and needs Connector/Valve internals, that belongs to Tomcat's API.

## 16. Key Takeaways

**Spring Boot properties** are a configuration contract published, bound, and applied at runtime by Boot. The server.* group is the first-choice surface; server.tomcat.*, server.jetty.*, and server.undertow.*, though server-specific, still belong to Boot's contract.

**Server APIs** directly control underlying objects like Tomcat Connector, Jetty ServerConnector, or Undertow Builder. When capabilities lack properties, WebServerFactoryCustomizer lets you add adjustments within the embedded server lifecycle. In return, the application takes responsibility for version compatibility, security, configuration ordering, extra ports, and deployment testing.

In day-to-day work: **properties first, customizer second, replacing the factory last**. Maintaining this boundary keeps systems easy to operate and upgrade while still enabling deep capabilities when genuinely required.

## Official Documentation for Version Cross-Checking

- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html)