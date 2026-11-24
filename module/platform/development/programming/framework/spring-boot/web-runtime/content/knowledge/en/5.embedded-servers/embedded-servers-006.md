# WebServerFactoryCustomizer Ordering and Its Relationship with `server.*` Configuration in Spring Boot

## 1. Problem to Understand

Spring Boot supports configuring the embedded HTTP server in two common ways: declaring `server.*` properties in application configuration, and writing `WebServerFactoryCustomizer` beans to modify the web server factory programmatically in Java. When both change the same setting—such as the listening port—the outcome depends on **the order in which customizers are applied to the factory**.

Questions to answer:
- At what stage are `server.port`, `server.address`, `server.servlet.context-path`, and `server.tomcat.*` applied?
- How do `@Order` and `Ordered` govern customizer execution order?
- Does `server.port` from `application.properties`, environment variables, or the command line take absolute precedence over Java code?
- If multiple customizers call `setPort`, what is the final configuration?
- How do you verify the configured value, the value on the factory, and the actual HTTP port?
- How do customizers differ across Servlet MVC, WebFlux, and the Tomcat, Jetty, Undertow, and Reactor Netty engines?

Java examples in this lesson target **Spring Boot 3.5.x + Java 17+ + `spring-boot-starter-web`**. In Spring Boot 4, several package and module names changed; verify APIs for your exact version rather than copying 3.x imports verbatim into 4.x.

## 2. First: `server.*` and `WebServerFactoryCustomizer` Do Not Operate at the Same Precedence Layer

A configuration value passes through two logical stages:

1. **Property resolution:** Spring Boot collects multiple `PropertySource`s into `Environment`. Property-source precedence rules pick the active value for a key like `server.port`.
2. **Applying to the web server factory:** Auto-configuration components use values bound into `ServerProperties` to configure the factory. Other `WebServerFactoryCustomizer` beans can also mutate the same factory before it creates the real server.

You can visualize this as:

~~~text
application.properties, application.yaml
environment variables, system properties, CLI arguments
                      |
                      v
        Spring Environment / PropertySources
                      |
           @ConfigurationProperties
                      |
                      v
          ServerProperties (server.*)
                      |
                      v
   Auto-configured WebServerFactoryCustomizer (order 0)
                      |
                      v
   Application-provided WebServerFactoryCustomizers
          (may run earlier or later)
                      |
                      v
            Final WebServerFactory
                      |
                 getWebServer()
                      |
                      v
     Tomcat / Jetty / Undertow / Reactor Netty runs
~~~

This is a conceptual diagram, not a guarantee that every bean is created at a fixed instant. Server configuration also involves container-specific customizers and steps executed during connector creation or server startup.

**Distinguish two questions:** "Which value does the key `server.port` resolve to in `Environment`?" is a `PropertySource` precedence question; "Which port does the server ultimately listen on?" also depends on programmatic modifications to the factory.

## 3. `server.*` Configuration from Environment and ServerProperties

Spring Boot uses `@ConfigurationProperties` to bind server-related properties from `Environment` into configuration objects such as `ServerProperties`. Commonly used keys:

| Property | Meaning | Notes |
|---|---|---|
| `server.port` | Primary HTTP port, typically defaults to 8080 | `0` requests a random available port; `-1` disables HTTP endpoints while keeping the web context in some setups |
| `server.address` | Network address the server binds to | Consider when running in containers, on localhost, or behind a reverse proxy |
| `server.servlet.context-path` | Context path for Servlet applications | Servlet-specific property; do not assume it applies mechanically to WebFlux |
| `server.ssl.*` | Certificates, keys, protocols, and HTTPS settings | SSL changes must consider connector creation and version docs |
| `server.http2.enabled` | Enables HTTP/2 if engine and environment support it | Effective behavior depends on engine/TLS support |
| `server.compression.*` | Response compression settings | Do not assume every response is compressed |
| `server.tomcat.*` | Tomcat-specific options | Only meaningful for Tomcat and matching version |
| `server.jetty.*` | Jetty-specific options | Does not configure Tomcat |
| `server.netty.*` | Options applicable to Reactor Netty when supported | Check configuration metadata for the running version |

Example `src/main/resources/application.properties`:

~~~properties
server.port=8085
server.servlet.context-path=/demo
server.compression.enabled=true
~~~

When no other customizer changes the port, the Servlet application normally serves at `http://localhost:8085/demo`.

Spring Boot supports relaxed binding: `server.port` can come from the `SERVER_PORT` environment variable. Command-line `--server.port=9090` normally takes precedence over file configuration. Even so, after `Environment` selects a value, Java code running later against the factory can still replace the value applied to **the actual server** if it mutates the same setting.

### 3.1. Example Distinguishing the Two Precedence Layers

Suppose:
- `application.properties` declares `server.port=8085`.
- Startup passes `--server.port=9090`.
- `Environment.getProperty("server.port")` returns `9090` per property precedence.
- A late-ordered customizer calls `factory.setPort(9191)`.

Typical result: `ServerProperties` holds configured port 9090, yet the server runs on **9191**. This is not a binding bug. Java customizer code deliberately changed the factory after configuration properties were applied.

## 4. How WebServerFactoryCustomizer Is Applied

`WebServerFactoryCustomizer<T extends WebServerFactory>` has one method: `customize(T factory)`. Spring Boot's bean post-processor collects customizers matching the factory type being created, sorts them according to order rules, and invokes `customize` before the factory creates the web server.

### 4.1. Ascending Order: Smaller Numbers Run First

In the Spring ecosystem, common rules are:

- `Ordered.HIGHEST_PRECEDENCE` or smaller negative values: very high priority, runs early.
- `@Order(-100)`: typically runs before `@Order(0)`.
- `@Order(0)`: runs between negative and positive values.
- `@Order(100)`: runs after `@Order(0)`.
- `Ordered.LOWEST_PRECEDENCE`: low priority, typically runs late.

**A smaller order value means executed earlier**, not stronger override authority. If two customizers call the same setter on the same factory, the one executed **later** generally determines the value left on that property, unless a later container step alters the outcome.

### 4.2. Order of Spring Boot's Built-In Customizers

Official Spring Boot documentation on embedded servers states that Boot's auto-configured `WebServerFactoryCustomizer` beans have **order `0`** and are processed before user customizers that do not declare an explicit order. Thus:

| Bean | Order | Expectation for `server.port` |
|---|---:|---|
| Application customizer with `@Order(-100)` | -100 | Runs early; its setting can be overwritten by Boot's order-0 customizer |
| Boot-created server configuration customizer | 0 | Applies parameters bound from `ServerProperties` |
| Application customizer with `@Order(100)` | 100 | Runs later than order 0; can change `setPort` |
| Customizer without `@Order` / `Ordered` | Typically equivalent to low priority | Boot docs guarantee Boot's order-0 customizers run before unordered application beans |

If multiple customizers share **the same order**, do not rely on whichever bean happens to be listed or instantiated first. Assign distinct orders to customizers that depend on one another or remove conflicting setters.

### 4.3. Ways to Declare Order

Depending on the bean definition, you can use:

~~~java
@Component
@Order(100)
class LatePortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {
    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
    }
}
~~~

This is an example class placed in a Spring Boot 3.x project with matching imports; the complete version is in the next section.

Or implement `Ordered` directly:

~~~java
class OrderedPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>,
                   Ordered {
    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
    }
}
~~~

The second form participates only when the class is registered as a Spring bean. Do not confuse factory customizer order with `FilterRegistrationBean.setOrder`, Spring Security filter chain order, advice `@Order`, or `ApplicationRunner` order: those are separate mechanisms.

## 5. Runnable Java 17+ Example: Early Customizer, Auto-Config, Late Customizer

Create a **Spring Boot 3.5.x** project using Java 17+ and the `spring-boot-starter-web` dependency (default embedded Tomcat). Set `application.properties` as follows:

~~~properties
server.port=8085
server.servlet.context-path=/demo
~~~

Create `src/main/java/example/web/CustomizerOrderApplication.java`:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomizerOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomizerOrderApplication.class, args);
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> portObserver(Environment env) {
        return event -> System.out.printf(
                "CHECK configured=%s actual=%d%n",
                env.getProperty("server.port"),
                event.getWebServer().getPort());
    }
}

@Component
@Order(-100)
class EarlyPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(7001);
        System.out.println("EARLY: setPort(7001)");
    }
}

@Component
@Order(100)
class LatePortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
        System.out.println("LATE: setPort(9191)");
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Launch with your build tool wrapper:

~~~bash
./mvnw spring-boot:run
# or:
./gradlew bootRun
~~~

The three lines printed by the illustrative code are expected in this order (normal Spring Boot log lines may appear in between):

~~~text
EARLY: setPort(7001)
LATE: setPort(9191)
CHECK configured=8085 actual=9191
~~~

Test HTTP:

~~~bash
curl -s http://localhost:9191/demo/ping
~~~

Body:

~~~text
pong
~~~

**Exact explanation:**

1. `EarlyPortCustomizer` has order -100, so it calls `setPort(7001)` before Boot's order-0 customizer.
2. Boot's configuration customizer applies `server.port=8085`, replacing the early 7001 value on the factory.
3. `LatePortCustomizer` at order 100 then calls `setPort(9191)`, so the final factory carries port 9191.
4. `Environment` still sees `server.port=8085`; Java customizers do not rewrite `Environment`.
5. `server.servlet.context-path=/demo` remains active since these customizers only changed the port. Requests to `/demo/ping` return `pong`.

To observe behavior without the late customizer, **remove the `LatePortCustomizer` bean from the test project and restart**. Boot's auto-configured customizer then applies `server.port=8085` after early order -100, so the server typically listens on 8085. This is a learning exercise edit; do not alter real production configuration.

### 5.1. Trying with the Command Line

Run:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8099
~~~

If the argument syntax is supported by the project's Maven wrapper/plugin as shown, `Environment.getProperty("server.port")` becomes 8099. However, `LatePortCustomizer` still calls `setPort(9191)`, so the server still uses 9191. Verify via the `CHECK` line and a real HTTP request.

The equivalent plain Java command after building an executable JAR:

~~~bash
java -jar target/my-app.jar --server.port=8099
~~~

In the final command, `target/my-app.jar` represents **the actual built JAR filename**; substitute your real filename. The goal is illustrating that `PropertySource` precedence differs from customizer ordering.

## 6. Outcome Matrix When Multiple Customizers Conflict

Assuming `server.port=8085` is present and no other customizers follow the listed steps:

| Operations on the same factory | Typical resulting port | Explanation |
|---|---:|---|
| Only `server.port` configured | 8085 | Boot customizer uses ServerProperties |
| `@Order(-100)` setPort(7001), then Boot order 0 | 8085 | Boot writes port later |
| Boot order 0, then `@Order(100)` setPort(9191) | 9191 | Application customizer writes later |
| Early -100, Boot 0, Late 100 | 9191 | Last setter execution determines value |
| Two customizers both `@Order(100)` setting different ports | Should not be predicted | Assign explicit order or remove conflict |
| One customizer sets port, another only adds a connector | Depends on server-specific API | Different connectors can listen on different ports |

This table only illustrates conflicts for **one setter on one factory**. For SSL, HTTP/2, context path, thread pools, or connector customizers, "last setter wins" may not fully describe behavior because APIs may accumulate callbacks, replace objects, or apply transformations when building the server.

## 7. Distinguishing Factory-Level and Container-Level Customizers

A project can simultaneously use:
- `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>`: changes common Servlet factory parameters like port, address, and context path within supported APIs.
- `WebServerFactoryCustomizer<TomcatServletWebServerFactory>`: modifies Tomcat's specific factory; does not run with a Jetty factory.
- `TomcatConnectorCustomizer` or container-specific callbacks: modify connector objects when Tomcat is built from the factory.
- `WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory>`: for reactive factories, distinct from Servlet.
- `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>`: specific to Reactor Netty.

A Servlet-typed generic customizer applies only to matching factory types; it is **not** a universal interceptor for both MVC and WebFlux. Likewise, having `spring-boot-starter-webflux` on the classpath does not guarantee requests are served by WebFlux when starter-web is also present; check the actual `WebApplicationType`.

Factory-level `@Order` governs the call order of matching **factory customizer beans**. It does not directly determine the order of Tomcat callbacks executed by the factory while creating connectors, nor filter ordering in the request pipeline. For `add*Customizer`-style customizers, outcomes can depend on the insertion order of callbacks and server engine mechanics.

## 8. When to Prefer `server.*`, and When to Write a Customizer?

**Prefer declarative `server.*` configuration** when official keys exist:
- Port, address, compression, SSL, HTTP/2.
- Servlet or container-specific parameters already published by Boot.
- Separating dev/staging/prod via profiles, environment variables, ConfigMaps, or deployment charts.

**Only use a Java customizer** when official properties cannot express the requirement:
- Adding connectors or adjusting native Tomcat/Jetty/Netty settings.
- Applying dynamic rules that depend on a specialized configuration bean.
- Integrating a server engine extension without a corresponding key.

When a Java customizer needs a dynamic configuration value, define a dedicated application property and bind it into a `@ConfigurationProperties` bean, then pass it explicitly to the customizer. Avoid hardcoding ports that disable `server.port` configurability unless overriding is explicitly required and tested.

Illustrative snippet in a class holding `Environment` (fragment; requires imports and bean registration):

~~~java
@Override
public void customize(ConfigurableServletWebServerFactory factory) {
    Integer override = environment.getProperty(
            "demo.embedded-server.override-port", Integer.class);
    if (override != null) {
        factory.setPort(override);
    }
}
~~~

In this snippet `environment` is a constructor-injected field. Without `demo.embedded-server.override-port`, the customizer leaves the port untouched and `server.port` remains in effect. In larger apps, use type-safe configuration rather than scattered `Environment` lookups.

## 9. Cases Requiring Special Caution

### 9.1. Ephemeral Port `server.port=0`

`server.port=0` asks the OS for an available port; the actual port is only known after server creation/startup. If a late customizer hardcodes `setPort(9191)`, the random-port request is overridden, which can cause parallel tests to collide on ports.

To obtain the real port at runtime, use `WebServerInitializedEvent` and `event.getWebServer().getPort()`. In Spring Boot integration tests, use `@LocalServerPort` with `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Do not read `server.port` from `Environment` assuming it always reflects the listening port.

### 9.2. `management.server.port` and Multiple Web Contexts

If the Actuator management server runs on a separate port, the system can have an additional context or web server. Identify which customizer beans apply to each context, and distinguish `server.port` from `management.server.port`. An `ApplicationListener<WebServerInitializedEvent>` may receive more than one event in multi-server setups; inspect which context emitted the event. Do not read a single port from the first event and ignore the management server.

### 9.3. SSL, HTTP/2, and Multiple Connectors

`server.ssl.*` and `server.http2.enabled` can involve native settings and callbacks during server creation. Adding an extra HTTP connector when HTTPS is enabled cannot be achieved simply by declaring two `server.port` values; it requires server-specific APIs and testing. Do not try to swap `setPort` as a substitute for multi-connector configuration.

### 9.4. Replacing the WebServerFactory Bean

Declaring your own `ServletWebServerFactory` or `ReactiveWebServerFactory` bean causes Boot's auto-configured factory to back off. However, **Boot's customizers can still be applied to your custom factory**. Therefore, do not assume a custom factory bean automatically ignores all `server.*` properties. Test this scenario on your exact Boot version and engine.

### 9.5. Changing Configuration at Runtime

Changing `server.port` in a property source after the server has started does not make the listening socket switch ports automatically. Factory customizers typically run during factory creation/startup, not as a continuous server controller. Changing ports, TLS, or connectors normally requires a safe reconfiguration/restart mechanism supported by the server engine.

## 10. How to Verify and Debug Configuration Differences

Start with three **fundamentally distinct** values:

1. **Value in Environment:** `environment.getProperty("server.port")`.
2. **Value applied to the factory:** observe inside matching customizers, log setters in a test environment, or debug the bean post-processor.
3. **Actual server value:** `WebServerInitializedEvent.getWebServer().getPort()` or a real HTTP request to the active port.

To trace root causes:
- Check `application.properties`, profile-specific configs, the `SERVER_PORT` env var, JVM system properties, and CLI arguments.
- Confirm which web stack and container the process uses; check whether the customizer's generic type matches.
- List active `WebServerFactoryCustomizer` beans (only in debug tooling with authorized context access).
- Check `@Order` / `Ordered` on each bean and where setters for the same property are called.
- Search for `setPort`, `setAddress`, `setContextPath`, `addConnectorCustomizer`, `addServerCustomizers`.
- Read container startup logs, inspect OS ports, or send real HTTP requests.
- Remember Docker/Kubernetes environments: the port bound inside the process differs from the published host port or external service port.

Actuator `/actuator/env` and `/actuator/configprops` (if enabled and authorized) help locate property sources and bound values. **They do not by themselves prove what port customizers applied to the final server**. Do not expose administrative endpoints or config secrets publicly just for debugging.

### 10.1. A Useful Integration Test

With the example in section 5, run the app and send a request:

~~~bash
curl -i http://localhost:9191/demo/ping
~~~

Expected result: HTTP 200 with body `pong` if there is no proxy/port collision and configuration matches the example. Also verify:
- Port 8085 is not the primary listening port in the final example.
- The `CHECK` line shows configured 8085 yet actual port 9191.
- Removing the late customizer restores the expected port to 8085.
- When running random-port tests, disable or remove hardcoded port customizers before expecting ephemeral port allocation.

For automated integration tests, prefer gating overrides behind a test-disabled flag or designing customizers not to hardcode ports in tests; obtain the real port via `@LocalServerPort` and send HTTP requests there. Tests asserting only `Environment.getProperty("server.port")` can miss customizer overrides.

## 11. Common Mistakes

1. **Mistaking `@Order(-100)` for "highest override priority".** Smaller numbers run earlier, so the value can be reset by an order-0 bean.
2. **Believing `server.port` always beats every Java setter.** Property binding and factory customization are two separate phases.
3. **Assuming bean listing order in source determines execution order.** Explicit `Ordered` or `@Order` is needed.
4. **Two customizers sharing the same order and mutating the same property.** Never rely on equal-order tie-breaking.
5. **Targeting the wrong factory type.** A Servlet customizer does not control a Reactor Netty reactive factory.
6. **Confusing factory customizer order with Servlet Filter order or Tomcat connector callback order.** Execution mechanisms differ.
7. **Overriding `server.port=0` in tests.** Breaks random ports, causing flaky CI tests.
8. **Treating `Environment` as proof the server listens on that port.** Check `WebServerInitializedEvent` or real HTTP.
9. **Hardcoding a port inside a shared library.** Can silently break deployment config and cause port conflicts on hosts.
10. **Replacing the factory bean and assuming auto-customizers stop running.** Customizers apply to matching factories, including user-defined ones.
11. **Trying to configure two connectors with one `server.port`.** Must use server-specific APIs and verify.
12. **Changing a property at runtime and expecting the server to rebind ports.** Startup binding is not socket hot-reload.

## 12. Checklist Before Using a Customizer in a Project

- [ ] Checked Spring Boot configuration metadata to see if `server.*` already covers the requirement.
- [ ] Distinguished values resolved from `PropertySource` vs. factory values after customizers.
- [ ] Identified the exact web stack and matching factory generic type.
- [ ] Checked auto-configured order-0 customizers on the active version.
- [ ] Declared distinct numeric orders on application customizers when ordering matters.
- [ ] Avoided conflicting setters on the same parameter or documented its single owner.
- [ ] Tested `server.port=0`, test profiles, management port, and multi-connector scenarios.
- [ ] Verified actual port via `WebServerInitializedEvent` or HTTP request.
- [ ] Tested `server.ssl.*`, `server.tomcat.*`, or `server.netty.*` keys against the matching engine.
- [ ] Documented scope and behavior across Spring Boot version upgrades.

## 13. Conclusion

In Spring Boot, `server.*` provides declarative configuration resolved from `Environment` and applied to the factory via auto-configuration. **Boot's `WebServerFactoryCustomizer`s run at order 0; application customizers running afterward can override factory properties without modifying the original value in Environment.** Smaller order values execute earlier; when the same setter is called multiple times, check execution order and server creation steps. Prefer `server.*` for supported options, use Java customizers for unsupported capabilities, and always confirm effective configuration on the real web server.

## References

- Spring Boot 3.5, Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, Servlet Web Applications (Programmatic Customization): https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html