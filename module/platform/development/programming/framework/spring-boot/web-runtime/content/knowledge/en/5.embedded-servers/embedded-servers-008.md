# Customizing JettyServletWebServerFactory or UndertowServletWebServerFactory

In a **Spring Boot Servlet** application, the embedded HTTP server is created alongside the ApplicationContext when the application starts. With \`spring-boot-starter-web\`, the default choice is usually **Tomcat**. If the application needs to run **Jetty** or **Undertow**, we change dependencies so Spring Boot selects the right server type, and then customize the corresponding factory when built-in configuration properties do not cover the requirement.

Two classes to distinguish:

- **JettyServletWebServerFactory** creates and configures a Jetty-based Servlet web server.
- **UndertowServletWebServerFactory** creates and configures an Undertow-based Servlet web server.

Both implement Spring Boot's Servlet web server mechanism. They are **not** controllers, custom application servlets, or a switch that turns Spring MVC into WebFlux. The safe integration pattern is usually creating a **WebServerFactoryCustomizer<T>** bean with the specific factory type and letting Spring Boot continue managing the web server lifecycle.

## 1. When Do You Need to Customize a Web Server Factory?

First, identify the actual goal:

| Requirement | First option to consider |
|---|---|
| Change HTTP port | \`server.port\` |
| Change Servlet application context path | \`server.servlet.context-path\` |
| Enable SSL/TLS, HTTP/2, or timeouts with standard properties | Matching \`server.*\` properties and infrastructure config |
| Limit Jetty's thread pool | \`server.jetty.threads.*\` when sufficient |
| Set Undertow I/O and worker thread counts | \`server.undertow.threads.*\` when sufficient |
| Adjust Jetty internal \`Server\`, connector, or thread pool APIs | \`JettyServletWebServerFactory.addServerCustomizers(...)\` |
| Adjust \`Undertow.Builder\` directly | \`UndertowServletWebServerFactory.addBuilderCustomizers(...)\` |
| Adjust Undertow Servlet deployment details | DeploymentInfo customizer when truly necessary |
| Configure ServletContext, filters, listeners, or servlets | Spring Boot Servlet mechanisms, e.g., ServletContextInitializer, FilterRegistrationBean |

**Selection rule:** prefer \`application.yml\` for common settings that vary easily across environments. Use \`WebServerFactoryCustomizer\` when you must access server-specific APIs. Only define a full factory bean if you truly need to alter how the factory is built; that requires understanding the default customizations Spring Boot normally applies.

## 2. Selecting Jetty or Undertow Properly

Customizers are meaningful only when the classpath contains the matching server libraries and Spring Boot is actually creating that Servlet web server type.

### 2.1. Using Jetty Instead of Tomcat

With Gradle Groovy DSL, in a project that already has the Spring Boot plugin and dependency management:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Spring MVC remains the framework processing HTTP requests; only the embedded Servlet server changes from Tomcat to Jetty. The configuration support class name is:

~~~java
org.springframework.boot.web.embedded.jetty.JettyServletWebServerFactory
~~~

### 2.2. Using Undertow Instead of Tomcat

Equivalent configuration for Undertow:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'
}
~~~

Factory used:

~~~java
org.springframework.boot.web.embedded.undertow.UndertowServletWebServerFactory
~~~

**The two Gradle blocks above are alternatives**, not dependencies to declare simultaneously. Avoid keeping Tomcat, Jetty, and Undertow together on the classpath without a clear reason; having multiple server factories can make it difficult to determine which server gets selected. Do not assume that merely adding \`spring-boot-starter-jetty\` is enough to remove Tomcat pulled in by \`spring-boot-starter-web\`.

This lesson covers the **Servlet stack**. If the application uses \`spring.main.web-application-type=reactive\` and WebFlux, the factory mechanism is a reactive web server factory—do not use the two Servlet factory classes above to configure a reactive server.

## 3. How Does WebServerFactoryCustomizer Work?

Spring Boot typically auto-configures a \`ServletWebServerFactory\` bean matching the classpath. During web server creation, \`WebServerFactoryCustomizer\` beans can adjust the factory **before the web server actually starts**.

Diagram representing the main flow:

~~~text
Dependencies on classpath
        |
        v
Spring Boot selects matching ServletWebServerFactory
        |
        v
Apply WebServerFactoryCustomizers with matching types
        |
        v
Factory builds Jetty Server or Undertow server
        |
        v
Embedded server starts listening for HTTP
~~~

A bean declared as \`WebServerFactoryCustomizer<JettyServletWebServerFactory>\` targets only the matching Jetty factory; it does not turn an Undertow factory into Jetty. Likewise, an Undertow-specific customizer only takes effect when the Undertow factory is active.

Spring Boot also has customizers to apply \`server.*\` properties. If you set a value in properties and also assign the same setting in customizer code, the two can overwrite each other. When multiple customizers exist, execution order can affect the result; specify order explicitly via \`@Order\` or \`Ordered\` when needed and verify the final configuration. The simplest rule is **one single owner per setting**.

The examples below use Spring Boot 3.x with Java 17 or higher and represent **separate implementation options**. They belong inside a Spring Boot project configured with the right server starter.

## 4. Example Customizing JettyServletWebServerFactory

Jetty manages HTTP connectors, connections, and a thread pool. A common requirement is adjusting the maximum thread pool size after load testing.

Create file \`src/main/java/demo/web/JettyServerConfiguration.java\`:

~~~java
package demo.web;

import org.eclipse.jetty.util.thread.QueuedThreadPool;
import org.springframework.boot.web.embedded.jetty.JettyServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JettyServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<JettyServletWebServerFactory>
            jettyThreadPoolCustomizer() {

        return factory -> factory.addServerCustomizers(server -> {
            if (server.getThreadPool() instanceof QueuedThreadPool pool) {
                pool.setMaxThreads(160);
            }
        });
    }
}
~~~

Explanation:

1. \`@Configuration\` registers the configuration class in the Spring ApplicationContext.
2. \`@Bean\` registers a customizer specific to \`JettyServletWebServerFactory\`.
3. \`addServerCustomizers(...)\` provides a hook receiving the \`org.eclipse.jetty.server.Server\` instance when Jetty is created.
4. \`server.getThreadPool()\` returns Jetty's actual thread pool.
5. \`instanceof QueuedThreadPool\` checks the type before calling \`setMaxThreads(160)\`, avoiding an unsafe cast when the application uses another thread pool.

**160 is an illustrative value**, not an optimal threshold. Jetty can use a different thread pool setup depending on version or custom code; if the thread pool is not a \`QueuedThreadPool\`, the example branch makes no change. In systems that strictly require a specific thread pool type, validate and fail configuration loudly rather than silently assuming a cast will succeed.

Keep \`maxThreads\` reasonable relative to \`minThreads\`, CPU, stack memory, and downstream dependency capacity. Adding threads does not speed up overloaded SQL queries or HTTP services.

### 4.1. Equivalent Property Configuration When Sufficient

If you only need to adjust Jetty's thread limits and your Spring Boot version supports it, configure it in \`application.yml\`:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
  jetty:
    threads:
      min: 8
      max: 160
~~~

These values illustrate thread limits and path settings. For the same goal, use **only one** of the two approaches for max threads: properties or a Java customizer. Do not declare both without defining application order.

Port and context path apply to Servlet web servers generally. Context path \`/demo\` makes an endpoint mapped to \`/ping\` reachable at \`/demo/ping\`, assuming no other URL configuration intervenes.

### 4.2. When Deeper Jetty Customization Is Required

Jetty also has its own connectors, connection factories, TLS/ALPN, thread pools, and handlers. You can use \`addServerCustomizers\` to access Jetty's \`Server\`, though connector/handler APIs change across Jetty versions. Therefore:

- Check the Jetty version managed by your Spring Boot starter.
- Use APIs for that exact version; do not copy Jetty 9/10/11 code for Jetty 12 without verification.
- Do not accidentally replace handlers or connectors configured by Spring Boot, breaking servlet mappings, HTTPS, or HTTP/2.
- For parameters already having \`server.*\` properties, prefer properties over tuning connectors manually.
- Run integration tests with real HTTP/TLS after changing configuration.

Thread pool tuning is a simple example for learning the Jetty hook; production connector or TLS changes require further compatibility verification and integration testing.

## 5. Example Customizing UndertowServletWebServerFactory

Undertow uses a pool of **I/O threads** to handle I/O events and **worker threads** to handle work dispatched to workers. The two thread counts are separate limits. Do not run long blocking tasks directly on I/O threads; standard Servlet code is dispatched by Undertow according to the server's model.

Create file \`src/main/java/demo/web/UndertowServerConfiguration.java\` in the **Undertow option**:

~~~java
package demo.web;

import org.springframework.boot.web.embedded.undertow.UndertowServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UndertowServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<UndertowServletWebServerFactory>
            undertowThreadCustomizer() {

        return factory -> factory.addBuilderCustomizers(builder -> {
            builder.setIoThreads(4);
            builder.setWorkerThreads(64);
        });
    }
}
~~~

Explanation:

1. Spring Boot registers a customizer for \`UndertowServletWebServerFactory\`.
2. \`addBuilderCustomizers(...)\` receives a callback on \`Undertow.Builder\`.
3. \`setIoThreads(4)\` configures four I/O threads in this example.
4. \`setWorkerThreads(64)\` configures the illustrative worker thread count.
5. Spring Boot proceeds to create and start Undertow from the customized builder.

Numbers must be benchmarked on real hardware and workloads. Setting I/O threads too low can hurt network throughput; setting worker threads too high can cause the JVM to waste stack memory and CPU on context switching while overloading the DB.

### 5.1. Prefer Properties When Only Adjusting Thread Counts

Example \`application.yml\` for Undertow:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
  undertow:
    threads:
      io: 4
      worker: 64
~~~

If you only need these two settings, properties are clear enough and easy to vary by environment. When using a customizer for deeper tuning, avoid setting similar values in two places without verifying the actual outcome.

### 5.2. Other Undertow Extension Points

The Undertow factory also provides specialized hooks:

- **addBuilderCustomizers**: customizes \`Undertow.Builder\`, such as I/O or network options supported by Undertow's API.
- **addDeploymentInfoCustomizers**: adjusts the Servlet deployment's \`DeploymentInfo\` when integrating specialized capabilities.
- Common Servlet factory settings: port, context path, sessions, SSL, and Spring Boot's default customizers.

Do not modify \`DeploymentInfo\` just to register a regular \`Filter\` or \`Servlet\`: Spring Boot already provides \`FilterRegistrationBean\`, \`ServletRegistrationBean\`, and \`ServletContextInitializer\` for those needs.

## 6. Example Application for Testing the Web Server

To verify the server serving requests, you can add a shared Spring Boot entry point and controller for **either** the Jetty or Undertow option.

File \`src/main/java/demo/web/DemoWebApplication.java\`:

~~~java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoWebApplication.class, args);
    }
}
~~~

File \`src/main/java/demo/web/PingController.java\`:

~~~java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

With \`server.port=8080\` and \`server.servlet.context-path=/demo\`, run the application from a Gradle project that already has the Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

On Windows you can use \`gradlew.bat bootRun\`. In another terminal:

~~~bash
curl -i http://localhost:8080/demo/ping
~~~

With an application containing only the sample endpoint and no Spring Security or response-modifying filters, the expected result is **HTTP 200** and response body:

~~~text
pong
~~~

HTTP headers can vary by server and environment; do not assert a fixed header set. If port 8080 is already occupied or another configuration overrides \`server.port\`, the application needs a different suitable port.

**Code organization note:** choose **one** server dependency and **one** configuration class dedicated to the chosen server. If the build only includes the Jetty starter while source code still imports \`UndertowServletWebServerFactory\`, Java will fail to compile due to missing Undertow libraries on the classpath. The two examples are independent implementation options.

## 7. When to Create a Factory Bean Directly?

Besides creating a \`WebServerFactoryCustomizer\`, Spring Boot allows developers to define a \`JettyServletWebServerFactory\` or \`UndertowServletWebServerFactory\` bean:

~~~java
// Illustrative fragment: place inside @Configuration only when you truly want
// to own the entire Jetty factory creation.
@Bean
JettyServletWebServerFactory customJettyFactory() {
    return new JettyServletWebServerFactory();
}
~~~

This is a **fragment**; it compiles only with appropriate imports, a configuration class, and Jetty dependencies. When defining a factory directly, Spring Boot may skip creating the default factory. Customizers can still apply, though the author must understand the provided factory's constructor and configuration.

There is no need to create a factory bean just to change the port or thread pool. Creating a custom factory can cause:

- Accidentally bypassing default factory selection or altering auto-configuration handling.
- Creating multiple beans of type \`ServletWebServerFactory\`, causing non-unique bean errors or conflicts.
- Missing connector or resource configuration steps when making deep changes.
- Tests using random ports or SSL configurations behaving differently than expected.

Therefore, in most applications keep Boot's factory and register customizers only. If you must supply a factory manually, thoroughly test HTTP, HTTPS, context path, Servlet registration, filters, lifecycle, and server shutdown.

## 8. Customization Order and Scope of Each Property

Values are configured across multiple layers:

1. **Environment/ConfigData:** \`application.yml\`, profiles, environment variables, command-line args.
2. **Spring Boot server properties:** maps \`server.*\` values onto the factory.
3. **WebServerFactoryCustomizer:** adjusts the factory conditionally or via server-specific APIs.
4. **Server-specific customizers:** callbacks for Jetty \`Server\` or Undertow \`Builder\` when the actual server is constructed.
5. **External infrastructure:** reverse proxy, load balancer, service mesh, ingress, firewall, and port/network limits.

You cannot guarantee a later layer always "wins" over an earlier layer across all setups if customizer ordering is unmanaged. When multiple sources modify the same parameter, the outcome can depend on application order. Document the single owner, use \`@Order\` when needed, and verify actual values/behavior with integration tests.

### Common Configuration for Jetty and Undertow

Some Spring Boot properties remain shared across Servlet web servers:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
    session:
      timeout: 30m
  shutdown: graceful
~~~

However, properties prefixed with \`server.jetty.*\` target Jetty only, while \`server.undertow.*\` target Undertow only. A \`server.tomcat.*\` property will not modify Undertow simply because the application used to run Tomcat.

Session timeout in the example must be chosen per business needs. Graceful shutdown helps the application finish in-flight requests where permitted; the actual stop deadline is also affected by \`spring.lifecycle.timeout-per-shutdown-phase\` and the runtime environment.

## 9. Differences Between Jetty and Undertow When Tuning Resources

Thread counts in the examples are **execution limits**, not targets to maximize blindly.

| Aspect | Jetty | Undertow |
|---|---|---|
| Servlet factory | JettyServletWebServerFactory | UndertowServletWebServerFactory |
| Common server-specific customization APIs | Jetty Server, connectors, thread pool | Undertow.Builder, DeploymentInfo |
| Thread tuning | Jetty thread pool, min/max limits | I/O threads and worker threads |
| Common configuration | \`server.jetty.threads.*\` | \`server.undertow.threads.*\` |
| What to measure | Busy threads, queues, connectors, CPU, and latency | I/O/worker saturation, CPU, latency, and downstream resources |

Increasing threads can improve throughput for some workloads yet increase lock contention, stack memory consumption, and push DB connection pools to their limits. In particular, do not treat 200 worker threads as 200 concurrent DB queries if the Hikari pool only has 10 connections.

To tune systematically:

1. Determine expected load, requests/second, concurrency, p95/p99 latency, and error rate.
2. Measure CPU, heap, threads, connection pools, GC time, and DB/external API latency.
3. Change one parameter at a time with evidence of a bottleneck.
4. Ramp load gradually and compare before/after; monitor timeouts, queues, and dependency capacity simultaneously.
5. Always maintain container-level resource limits and proper shutdown settings.

Do not copy 4 I/O threads, 64 workers, or 160 Jetty threads verbatim into production without measuring.

## 10. Impact on TLS, HTTP/2, Proxies, and the Servlet Pipeline

Switching the embedded server usually preserves Spring MVC controllers/services because they operate via the Servlet abstraction, yet server-specific configuration can change:

**TLS/HTTPS:** prefer \`server.ssl.*\` or infrastructure certificate/secret mechanisms. When creating connectors manually, keep complete TLS, timeout, and protocol configuration; do not put private keys/keystore passwords in source code.

**HTTP/2:** verify support across Jetty/Undertow version, JDK, TLS/ALPN, and starters. Do not assume every server/connector supports the same HTTP/2 configuration; test with a real HTTP client.

**Reverse proxies:** proxies may pool connections, enforce header/body limits, add \`Forwarded\`/\`X-Forwarded-*\`, and have different timeouts than the backend. When changing web servers, test forwarding headers, HTTPS scheme, redirects, client IP, cookies, and request URIs in your actual deployment setup.

**Servlet pipeline:** filters, listeners, Spring Security, servlet mappings, and sessions still require testing. If a customizer alters context path or connectors, endpoints may change paths or ports even though controllers did not change.

**WebSocket, streaming, and uploads:** do not assume two servers always behave identically on buffers, timeouts, request limits, and protocol support. Test long-lived connections, large uploads, streaming responses, and abnormal connection closes.

## 11. Testing and Verifying Which Server Is Active

### 11.1. Check Dependencies First

In a Gradle project, inspect resolved runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for the Jetty/Undertow starter and confirm Tomcat is no longer pulled in unexpectedly. If using the Spring Boot plugin in a multi-module build, target the corresponding subproject; do not assume running the command at root inspects the right module.

### 11.2. Observe Logs and Endpoints

Start the application and inspect web server startup logs and configuration errors. Jetty and Undertow generally print distinct details in logs; do not rely solely on imported class names to conclude which server is running.

Call real endpoints with \`curl -i\`, verify status/body, context path, and port. When HTTPS or HTTP/2 is enabled, test with the matching client protocol. For timeouts and concurrency, use reproducible load tests.

### 11.3. Real Integration Testing

A \`@WebMvcTest\` unit test focuses only on the MVC slice and typically does not start a real embedded server; it cannot prove Jetty connectors or Undertow worker threads were applied. Use \`@SpringBootTest(webEnvironment = RANDOM_PORT)\` or run the actual JAR to test network behavior and lifecycle.

**Note:** if a Java customizer forces a specific port via \`factory.setPort(8080)\`, it can defeat random-port testing depending on customizer order. For shared values like port, prefer \`server.port\` and avoid overriding it inside specialized customizers.

Verify final results with real configuration and runtime metrics, not merely by asserting that the customizer bean exists.

## 12. Common Mistakes

### Mistake 1: Adding the Jetty Starter Without Excluding Tomcat

Multiple Servlet web servers end up on the classpath. The application may boot with the wrong server or fail configuration depending on how dependencies assemble.

**Fix:** inspect \`runtimeClasspath\`, exclude \`spring-boot-starter-tomcat\` from \`starter-web\`, and add only the chosen server.

### Mistake 2: Confusing a Servlet Factory with a Reactive Server

A WebFlux project tries adding JettyServletWebServerFactory to replace Reactor Netty while running a reactive ApplicationContext.

**Fix:** verify \`WebApplicationType\` and use the factory/server matching the web stack. Both factories in this lesson are for Servlet.

### Mistake 3: Customizer Bean Does Not Run

Could be due to a different active web server type, configuration class outside component scan, bean skipped by conditions, or missing dependencies.

**Fix:** check component scan, ApplicationContext, effective classpath, and logs; if needed, log cleanly when the customizer runs. Do not assume bean existence means the server used that factory.

### Mistake 4: Configuring the Same Attribute in Two Places

Both \`server.jetty.threads.max\` and \`setMaxThreads(...)\` exist with different values, or two customizers both set the port.

**Fix:** assign a single owner, remove duplicates, or manage \`@Order\` intentionally; verify the running server reflects the desired value.

### Mistake 5: Over-Tuning the Thread Pool

Too many threads increase memory footprint and context switching; too few cause requests to queue excessively.

**Fix:** analyze load, thread dumps, pool saturation, and DB limits; measure p95/p99 latency before and after changes.

### Mistake 6: Creating a Factory Bean Manually When Only a Customizer Is Needed

Creating a custom factory can replace auto-configuration, lose expected defaults, or create bean conflicts.

**Fix:** use \`WebServerFactoryCustomizer<JettyServletWebServerFactory>\` or \`WebServerFactoryCustomizer<UndertowServletWebServerFactory>\` to adjust the Spring Boot-managed factory.

### Mistake 7: Copying API Examples from the Wrong Jetty Version

Jetty changes noticeably across major versions. Methods or connector APIs used previously may no longer be compatible.

**Fix:** check the Jetty version managed by the Spring Boot BOM, consult matching API docs, and run compile/integration tests.

### Mistake 8: Tests Check Only Controllers

Endpoint unit tests pass while connectors are misconfigured, HTTPS fails, or the customizer never ran at all.

**Fix:** run integration tests against a real embedded server, test port/path/TLS, and smoke test in the deployment environment.

### Mistake 9: Overlooking Limits Outside the Application

Ports, timeouts, request sizes, and TLS can be blocked or altered by ingress, proxies, firewalls, or containers.

**Fix:** inspect both external infrastructure and the application, especially forwarding headers, idle timeouts, and readiness/liveness probes.

## 13. Deployment Checklist

- Choose the **Servlet stack** and only one primary embedded server: Jetty or Undertow.
- Exclude Tomcat from starter-web and add the right replacement starter.
- Configure port, context path, SSL, and common settings in \`application.yml\` when sufficient.
- Create a customizer with the exact generic type for **JettyServletWebServerFactory** or **UndertowServletWebServerFactory** when server-specific APIs are needed.
- Use Jetty Server customizers or Undertow Builder/DeploymentInfo customizers appropriately; avoid replacing the entire factory.
- Verify customizer beans/configurations are scanned and ordered if multiple sources touch the same value.
- Preserve Servlet mappings, Spring Security, filters, sessions, TLS, HTTP/2, and forwarding when swapping servers.
- Inspect the dependency tree, startup logs, HTTP endpoints, port/context path, and runtime metrics.
- Run bounded load tests, observing p95/p99 latency, CPU, thread pools, DB pools, and timeouts.
- Verify graceful shutdown, probe configuration, and resource limits in the deployment environment.

**Conclusion:** \`JettyServletWebServerFactory\` and \`UndertowServletWebServerFactory\` are the extension points for configuring an embedded **Servlet** server according to the chosen server type. Use properties for supported settings, use **WebServerFactoryCustomizer** when server-specific APIs are required, verify dependencies accurately, and test against the real web server.