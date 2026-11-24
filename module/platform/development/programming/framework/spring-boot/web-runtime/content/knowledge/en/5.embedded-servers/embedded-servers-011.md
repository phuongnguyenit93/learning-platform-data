# Consequences of Replacing the Entire WebServerFactory Bean Instead of Adding a WebServerFactoryCustomizer

## 1. Context: How Does Spring Boot Create an Embedded Server?

In a Spring Boot application using an embedded HTTP server, the framework does not launch Tomcat, Jetty, or Reactor Netty via an ad-hoc call inside a controller. Spring Boot creates a **web server factory bean**, applies configuration to the factory, and then asks the factory to build and start the server. Therefore, distinguish between:

- **Factory bean**: the object responsible for creating the web server, e.g., `TomcatServletWebServerFactory` for Spring MVC on Tomcat.
- **`WebServerFactoryCustomizer<T>`**: a callback that modifies an **already-existing** factory before the server starts. The callback is not a web server and normally does not create a new factory.
- **Auto-configuration**: Spring Boot inspects the classpath, web application type, and existing beans to create an appropriate default factory, then registers customizers for common settings.
- **Web server**: the actual Tomcat/Jetty/Netty instance accepting HTTP connections after initialization.

For the Servlet stack, `ServletWebServerApplicationContext` needs an appropriate `ServletWebServerFactory`. For the reactive stack, `ReactiveWebServerApplicationContext` uses `ReactiveWebServerFactory`. Factories of these two types are not interchangeable.

The standard choice is letting Boot create the factory and configuring it via `application.properties`/`application.yaml`. When container-specific APIs without properties are needed, add a `WebServerFactoryCustomizer`. **Only create a factory bean yourself if you genuinely need to control how the server is constructed**, such as swapping the factory implementation or overriding extension points that customizers cannot reach.

## 2. How the Two Extension Approaches Differ

### Approach A: Keep the Default Factory and Add a Customizer

~~~text
Classpath + WebApplicationType
          |
          v
Spring Boot auto-configures matching factory
          |
          v
BeanPostProcessor applies Boot's customizers
          |
          v
Apply application customizers (in order)
          |
          v
Create embedded server and start
~~~

The application adds **one configuration step**. Boot retains ownership of choosing the default factory. Built-in Spring Boot features and other customizers continue participating normally.

### Approach B: Declare Your Own Factory Bean

~~~text
Application declares @Bean ServletWebServerFactory
          |
          v
Boot's factory auto-configuration backs off
          |
          v
Application-created factory becomes the initialization candidate
          |
          v
Matching WebServerFactoryCustomizers are still applied
          |
          v
Create embedded server and start
~~~

**Very common technical misconception:** according to official documentation, when you declare your own `WebServerFactory`, the factory Spring Boot would normally create is replaced, **yet Spring Boot's auto-configured customizers are still applied to the custom factory where applicable**. It is incorrect to claim that "replacing the factory disables all `server.*` settings". The outcome depends on the factory type, the interfaces it implements, matching customizers, and the order of configuration mutations.

| Aspect | Adding `WebServerFactoryCustomizer` | Declaring your own `WebServerFactory` |
|---|---|---|
| Who creates the factory? | Boot creates it | Application creates it |
| Boot's default factory? | Retained | Auto-configuration backs off when a matching bean exists |
| Boot's default customizers? | Still run | **Still run** if applicable to the new factory |
| Risk of wrong factory type | Low when generic matches server/stack | Higher: may create a factory mismatched with the running stack |
| Version upgrade compatibility | Generally easier | Must audit constructors, packages, hooks, container APIs |
| Degree of control | Setters/hooks exposed by the factory | Can swap the entire implementation or subclass |
| Lifecycle ownership | Primarily configuration | Also assumes responsibility that the factory honors the contract |
| Best suited for | Changing a few server behaviors | Special cases unsolvable via properties/customizers |

## 3. Consequence One: Default Auto-Configuration Backs Off

Spring Boot uses conditions like `@ConditionalOnMissingBean` to decide whether to create the default server factory bean. When a valid `ServletWebServerFactory` bean is declared by the application, the default factory creation branch is typically skipped. Likewise, inspect the `ReactiveWebServerFactory` branch for WebFlux.

This **does not mean all other auto-configuration disappears**. For example, Spring MVC mappings, message converters, filter/servlet registrations, and other auto-configured capabilities have their own conditions. Spring Boot can still create those beans, yet they only work properly if the custom factory supports the startup model and contract.

Practical consequences of using a custom-written factory:

1. Certain initialization behaviors tied to Boot's usual default implementation may no longer be inherited if the application changes factory types outright.
2. The application must ensure the factory is constructed with compatible dependencies, server APIs, and versions.
3. If a subclass or implementation fails to implement `getWebServer(...)` properly or fails to apply `ServletContextInitializer` instances, registration of DispatcherServlet, filters, session listeners, or endpoints may be incomplete.
4. If multiple beans qualify as the web server factory, the application may fail to resolve a unique factory and fail to start.

**Point to verify:** behavior differs between `new TomcatServletWebServerFactory()` (still Boot's standard factory, accepting matching customizers) and a completely custom `ServletWebServerFactory` implementation (which may lack configuration interfaces required by certain customizers). Never lump both scenarios into the same risk level.

## 4. Consequence Two: Customizers Still Run, Yet Outcomes Can Surprise You

Spring Boot applies `WebServerFactoryCustomizer` beans via `WebServerFactoryCustomizerBeanPostProcessor` **before the server starts**. Application-declared factories still pass through this mechanism. Boot's customizers typically carry order 0 and run before application-defined customizers, unless the application sets a different explicit order.

Ordering consequences:

- If Boot reads `server.port=9090` and sets the port on the factory, and an application customizer then calls `factory.setPort(9191)`, the final port can become 9191. When inspecting configuration, examine **all customizers** rather than looking only at `application.properties`.
- If one customizer adds a `TomcatConnectorCustomizer` while another calls a setter that replaces the entire collection instead of appending, previously registered callbacks can be lost. Prefer `add...` APIs when you intend to append.
- A generic `WebServerFactoryCustomizer<TomcatServletWebServerFactory>` targets only matching Tomcat Servlet factories. It does not automatically apply to Jetty, Netty, or Tomcat Reactive factories.
- Customizers execute very early in the ApplicationContext lifecycle, so eagerly injecting heavy business bean graphs into a customizer can trigger unexpected early initialization. The API documentation recommends lazy lookup if dependencies are needed.

Thus, "auto-configured customizers still run" **does not guarantee the final result is automatically right**. It requires customizers to be compatible and not overwrite one another out of order.

## 5. Consequence Three: Higher Risk of Configuration Drift and Runtime Differences

Settings typically handled by Spring Boot include:

| Group | Example properties | What to check when replacing the factory |
|---|---|---|
| Port and address | `server.port`, `server.address` | Is the new factory configurable and does it receive common customizers? |
| HTTPS/TLS | `server.ssl.*` | Does it support SSL bundles/certificates and matching connectors? |
| HTTP/2 | `server.http2.enabled` | Do the container and connector construction meet requirements? |
| Compression | `server.compression.*` | Does the custom factory apply settings accurately? |
| Session | `server.servlet.session.*` | Applies properly if on the Servlet stack with matching factory support |
| Context path | `server.servlet.context-path` | Applies to Servlet web servers, not every reactive server |
| Forward headers | `server.forward-headers-strategy` | Verify when placed behind a proxy/load balancer |
| Graceful shutdown | `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase` | Verify server lifecycle/shutdown integration |
| Container-specific | `server.tomcat.*`, `server.jetty.*` | Meaningful only for the matching container |
| Observability | Actuator, metrics, access logs | Depends on server implementation, registry registration, and matching config |

Many of these properties can still work with a standard custom factory because Boot retains auto-configured customizers. Risk arises when the application creates an **incompatible** factory, overwrites values again after Boot processes them, or alters server creation in ways that bypass extension hooks. The right approach is **testing functionality at runtime**, not drawing conclusions from the presence or absence of a property line in a file.

For example, the server starting on the new port only verifies basic networking; it **does not prove** TLS, proxy headers, access logs, graceful shutdown, or actuator metrics are right. Security-related changes must be verified with real request paths and active SSL/proxy configuration.

## 6. Consequence Four: Coupling to Spring Boot and Server Versions

Factories are Spring Boot APIs, and factory class package names can change across major versions.

| Component | Spring Boot 3.5 | Spring Boot 4.1 |
|---|---|---|
| Tomcat Servlet factory | `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory` | `org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory` |
| Customizer interface | `org.springframework.boot.web.server.WebServerFactoryCustomizer` | `org.springframework.boot.web.server.WebServerFactoryCustomizer` |
| Servlet factory interface | `org.springframework.boot.web.servlet.server.ServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ServletWebServerFactory` |
| Servlet/Tomcat | Tomcat 10.1 and Jakarta Servlet 6.0 | Tomcat 11.0.x and Jakarta Servlet 6.1 |

An example written for Boot 3.5 keeping the old `TomcatServletWebServerFactory` import may fail to compile on Boot 4.1. Writing a custom factory—especially subclassing and overriding protected hooks—couples the application even more tightly to internal or breaking container APIs. On major upgrades, cross-check exact API Javadocs and the dependency BOM rather than just bumping version numbers in Maven/Gradle.

The same rule applies to WebFlux: `ReactiveWebServerFactory` and server-specific factories (Reactor Netty, Tomcat Reactive, Jetty Reactive) are distinct types. Configuring a Servlet factory in a REACTIVE application is not how you replace WebFlux's factory. In Boot 3.5, Undertow remained a supported embedded server; in Boot 4.x the official list retains only Tomcat/Jetty and Reactor Netty for reactive. Do not carry Undertow factory creation code from 3.x to 4.x without verifying support scope.

## 7. Recommended Approach: Properties First, Customizer When Needed

If you only need to change port, timeouts, sessions, or supported settings, use properties to keep code simple. Example `src/main/resources/application.properties`:

~~~properties
server.port=9090
server.compression.enabled=true
server.shutdown=graceful
~~~

If programmatic changes via Tomcat API are required, add a **customizer bean** without declaring a factory bean. The example below targets Spring Boot 3.5, Java 17+, Servlet stack using `spring-boot-starter-web`, and default embedded Tomcat.

Save at `src/main/java/com/example/factorydemo/FactoryDemoApplication.java`:

~~~java
package com.example.factorydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FactoryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FactoryDemoApplication.class, args);
    }
}

@RestController
class ProbeController {
    @GetMapping("/probe")
    String probe() {
        return "factory-ok";
    }
}

@Configuration(proxyBeanMethods = false)
class TomcatTuningConfiguration {
    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> tomcatCustomizer() {
        return factory -> factory.addConnectorCustomizers(
                connector -> connector.setMaxPostSize(1_048_576));
    }
}
~~~

Example explanation:

- `@SpringBootApplication` enables component scan and auto-configuration from the current package. Spring Boot detects a Servlet web application and creates the Tomcat Servlet factory.
- `@Bean` returns a `WebServerFactoryCustomizer`, **without creating a ServletWebServerFactory bean**. Boot's factory remains in place.
- `addConnectorCustomizers(...)` appends a callback configuring the Tomcat Connector; `setMaxPostSize(1_048_576)` limits POST body size **when Tomcat parses the body for form parameters**. This is not a universal limit for all JSON request bodies; do not use it in place of required validation or upload limits.
- In real projects, if `server.tomcat.max-http-form-post-size` meets the requirement, the property remains simpler than code.
- The HTTP port is configured via `server.port=9090`; the callback does not touch the port.

Run inside a Maven project directory with Spring Boot 3.5.x parent/BOM, starter-web, and Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

In Windows PowerShell, you can use `mvnw.cmd spring-boot:run`. Call:

~~~bash
curl -sS http://localhost:9090/probe
~~~

Exact response body returned by the controller:

~~~text
factory-ok
~~~

Startup log lines depend on the environment, so do not treat them as fixed stdout. If `server.port=9090` is omitted, the usual default port is 8080.

## 8. Replacing the Factory Bean: Use Only When Truly Necessary

In the same Boot 3.5 project, **replace** `TomcatTuningConfiguration` above with the following configuration to illustrate declaring a factory. Do not run both examples simultaneously as independent configs while comparing their effects.

~~~java
package com.example.factorydemo;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ManualTomcatFactoryConfiguration {
    @Bean
    ServletWebServerFactory servletWebServerFactory() {
        return new TomcatServletWebServerFactory();
    }
}
~~~

This is an additional configuration class, saved in `ManualTomcatFactoryConfiguration.java` in the same package as the previous application; it is not a standalone runnable Java program.

When this `ServletWebServerFactory` bean exists:

1. Spring Boot **no longer needs to create another default Tomcat factory** along the normal auto-configuration branch.
2. `WebServerFactoryCustomizerBeanPostProcessor` **still applies** customizers compatible with the `TomcatServletWebServerFactory` your application just created.
3. Consequently, `server.port=9090`, SSL, or compression **can still be applied properly** by Boot's customizers. Do not treat the mere creation of the bean as proof that all properties are disabled.
4. The application has assumed ownership of creating and maintaining the factory: if you switch to another implementation or override hooks, you must re-verify the entire integration pipeline.
5. If you only needed `setMaxPostSize` or adding a Tomcat connector customizer, creating the factory like this is overly broad; go back to `WebServerFactoryCustomizer`.

Example showing why you must not duplicate factories in the same context:

~~~java
// Design error illustration: two beans both implementing ServletWebServerFactory.
@Bean
ServletWebServerFactory firstFactory() {
    return new TomcatServletWebServerFactory();
}

@Bean
ServletWebServerFactory secondFactory() {
    return new TomcatServletWebServerFactory();
}
~~~

This snippet is an **error illustration**, not a complete application. The Servlet web application context expects to locate a single matching server factory; if multiple `ServletWebServerFactory` candidates exist, startup can fail due to ambiguity.

Another case is declaring `ServletWebServerFactory` while creating a `NettyReactiveWebServerFactory` bean for WebFlux, or vice versa. The two stacks have separate contracts; to switch HTTP servers, swap the stack-appropriate starter/dependencies and let Boot select the factory unless there is a special requirement.

## 9. How to Verify Changes Safely

Do not stop testing after seeing "Started" in the logs. Minimal checks:

1. **Single factory:** ApplicationContext has exactly one `ServletWebServerFactory` for Servlet apps, or exactly one `ReactiveWebServerFactory` for reactive apps.
2. **Expected container type:** actual factory is Tomcat/Jetty/Netty as intended. Check the dependency tree and runtime logs.
3. **Properties still effective:** test port, context path, HTTP/2, compression, and TLS per real needs; check whether customizers override properties.
4. **Web component registration:** controllers, `Filter`s, `ServletContextInitializer`s, and session listeners still work.
5. **Lifecycle:** startup, shutdown, graceful shutdown, and resource cleanup.
6. **Observability:** Actuator health, server metrics, access logs/trace headers if used by the system.
7. **Version alignment:** Java runtime, Boot BOM, Tomcat/Jetty versions, javax/jakarta, and major-version API imports.

JUnit Jupiter example for **the same Boot 3.5 project from section 7**. File `src/test/java/com/example/factorydemo/FactoryRuntimeTest.java`:

~~~java
package com.example.factorydemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FactoryRuntimeTest {
    @Autowired
    ApplicationContext context;

    @LocalServerPort
    int port;

    @Test
    void factoryAndHttpEndpointWork() throws Exception {
        Map<String, ServletWebServerFactory> factories =
                context.getBeansOfType(ServletWebServerFactory.class);
        assertEquals(1, factories.size());
        assertInstanceOf(TomcatServletWebServerFactory.class,
                factories.values().iterator().next());
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + "/probe"))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("factory-ok", response.body());
    }
}
~~~

To run the test, the project needs `spring-boot-starter-test` and JUnit Jupiter from the Boot BOM:

~~~bash
./mvnw test
~~~

`RANDOM_PORT` allocates a real port for the test; inspecting `@LocalServerPort` is more reliable than assuming the app listens on 9090. When a non-empty context path is configured, the test URL must include that context path. When testing SSL/TLS, compression, or filters, write dedicated tests sending requests that satisfy the required conditions.

To inspect why Boot stopped creating the default factory, set `debug=true` or run the application with `--debug` to view the Condition Evaluation Report; look for auto-configurations related to `ServletWebServerFactory`/`ReactiveWebServerFactory` and why conditions matched or did not match. You can also inspect Actuator conditions when enabled and properly secured. Do not rely on a single log string because class names and messages vary across Boot versions.

## 10. Common Misconceptions

- **"Creating a custom factory bean makes Boot stop running all customizers."** False. Spring Boot documentation states auto-configured customizers still apply to custom factories. Distinguish *factory auto-configuration back-off* from the *customizer mechanism*.
- **"Simply calling new TomcatServletWebServerFactory is identical in every way to the default factory."** Do not assume so. If the app changes implementations, adds subclasses/hooks, or alters order, behavior can differ; test under real configuration.
- **"Using a `@Bean` with a different name lets Boot still create the default factory."** Conditions typically match by **bean type** rather than just name; providing a matching `ServletWebServerFactory` causes the default factory to back off.
- **"Setting `server.port` always yields the final value."** Not guaranteed. A customizer ordered later can change the port; check the actual listener.
- **"A Tomcat-typed customizer will run on Jetty."** False. Generic type and concrete factory determine whether the callback is invoked.
- **"Create multiple factories so Boot picks one randomly."** False. The web application context needs a single matching factory; multiple candidates can fail startup.
- **"Losing metrics/TLS is guaranteed when declaring a custom factory."** Inaccurate. With a standard implementation and matching auto-customizers, these features can keep working. Test rather than assume.
- **"`WebServerFactoryCustomizer` is equivalent to `WebMvcConfigurer`."** False. `WebServerFactoryCustomizer` configures the embedded HTTP server; `WebMvcConfigurer` configures Spring MVC, such as interceptors, formatters, and CORS mappings. They operate at different layers.
- **"The same Tomcat factory class uses identical imports in Boot 3 and 4."** False. Package names change across major versions; APIs depend on the exact BOM.

## 11. Decision and PR Review Process

To customize an embedded server, follow this order:

1. **State the requirement clearly:** port, TLS, connector, thread pool, graceful shutdown, lifecycle, or factory implementation?
2. **Try properties:** look up `server.*` and container-specific properties first.
3. **Use a customizer if code is needed:** pick the generic matching the factory, prefer `add...` APIs, avoid early-initialized business bean dependencies, and control ordering.
4. **Create a factory bean only when you must alter server creation:** demonstrate why properties and customizers are insufficient; verify single factory, contract, classpath, and web app type.
5. **Test behavior thoroughly:** HTTP, TLS, proxies, request bodies, filters/sessions, logging, metrics, and startup/shutdown matching the change scope.
6. **Review on Boot upgrades:** check packages, Javadocs, supported servers, Java/Servlet APIs, and BOM.

A PR replacing the factory should specify what the old factory lacked, which customizers still run, the test suite confirming zero lost behavior, and the rollback plan. If only one Tomcat parameter is needed, `WebServerFactoryCustomizer` is easier to control and maintain.

## Official References

- Spring Boot 3.5 — Embedded Web Servers, Configure the Web Server: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 4.1 — Embedded Web Servers: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot 3.5 — Servlet Web Applications, Programmatic Customization: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot 4.1 — `WebServerFactoryCustomizer` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- Spring Boot 3.5 — `TomcatServletWebServerFactory` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/tomcat/TomcatServletWebServerFactory.html
- Spring Boot 4.1 — `TomcatServletWebServerFactory` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/tomcat/servlet/TomcatServletWebServerFactory.html