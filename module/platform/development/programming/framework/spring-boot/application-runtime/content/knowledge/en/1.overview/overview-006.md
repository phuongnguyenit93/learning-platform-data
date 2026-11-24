# Relationship Between Externalized Configuration, Auto-Configuration, Web Server, and Actuator in Spring Boot

## 1. The big picture

A Spring Boot application does not operate via four isolated mechanisms. They connect in a chain: **externalized configuration** supplies environment-specific values; **auto-configuration** inspects the classpath, existing beans, and configuration values to decide which components to create; the **embedded web server** receives and handles HTTP traffic if the application is a web app; and **Actuator** provides observability and management endpoints, usually registered on that same web infrastructure or on a separate management port.

For example, the exact same application package can run on a developer machine on port 8080, in a test environment on port 9080, and in production on port 8080 while allowing access to `/actuator/health` only from an internal network. Business code does not necessarily need to change: configuration values and deployment infrastructure determine these differences.

~~~mermaid
flowchart TD
  A["Classpath: Spring Web, Actuator, other libraries"] --> C["Auto-configuration conditions"]
  B["YAML/properties, environment variables, JVM, CLI"] --> D["Spring Environment"]
  D --> C
  C --> E["ApplicationContext and beans"]
  E --> F["DispatcherServlet / WebFlux and embedded HTTP server"]
  D --> F
  E --> G["Actuator endpoints and Micrometer"]
  D --> G
  F --> H["Application HTTP API"]
  G --> I["HTTP/JMX management, health, metrics"]
  F --> I
~~~

The diagram shows logical relationships; the actual initialization sequence has multiple phases, and a separate management port may use a distinct management context/server.

| Component | Question it answers | Primary inputs | Visible effects |
| --- | --- | --- | --- |
| Externalized configuration | With which parameters should the application run? | `application.yaml`, profiles, environment variables, JVM/CLI args | Port, bind address, features, logging, management settings |
| Auto-configuration | Given available libraries, beans, and configuration, which beans should Boot create? | Classpath, `Environment`, `@Conditional...` conditions, application-declared beans | MVC/WebFlux, web server factory, JSON converters, actuator infrastructure... |
| Embedded web server | Where do HTTP requests arrive and get handled? | Web stack, web server implementation, `server.*` | HTTP listener, routing, request/response, port, and context path |
| Actuator | How is the system living, ready, and operating? | Actuator starter, beans, health indicators, `management.*`, Micrometer | `health`, `info`, `metrics`, and permitted management endpoints |

**Important distinction:** configuration values do not automatically create every feature; having a starter does not mean every endpoint will be publicly exposed. Auto-configuration requires matching conditions, and Actuator is additionally governed by endpoint access, HTTP exposure, and security rules.

## 2. Externalized configuration is the starting point

Spring Boot merges multiple `PropertySource`s into `Environment`. As a result, the same key can be read in Java code, in `@ConfigurationProperties` binding, or by built-in auto-configuration. Common sources:

- `application.yaml`/`application.properties` packaged inside the JAR: default values shipped with the application.
- External config files outside the JAR and profile-specific files: differ across dev, test, and production without rebuilding.
- Environment variables: well-suited for containers and CI/CD; for example `SERVER_PORT=9090` maps to `server.port`.
- Java system properties and application launch arguments: for example `-Dserver.port=9090` or `--server.port=9090`.
- Additional sources (config import/config tree, secret stores via appropriate integrations): keep operational configuration and secrets out of source code.

Among **common sources under default configuration**, command-line arguments take precedence over Java system properties, Java system properties over environment variables, and environment variables over config data; within config data, files outside the JAR and profile-specific files typically override packaged defaults. This is a conditional description, not an exhaustive precedence table: test properties, `SPRING_APPLICATION_JSON`, `@PropertySource`, and config location groups have their own rules. When an exact conclusion is needed, consult the *Externalized Configuration* section of the documentation for the version in use.

Example:

~~~yaml
# src/main/resources/application.yaml
spring:
  application:
    name: runtime-demo

server:
  port: 8080

demo:
  message: "Hello from YAML"

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- `server.port` is used to configure the web application's HTTP port.
- `spring.application.name` provides the application name metadata; it does not automatically create an HTTP route.
- `demo.message` is project-defined configuration; the application itself must read or bind that value.
- `management.endpoints.web.exposure.include` specifies which Actuator endpoints are permitted to be **exposed over the web**, provided the endpoint is supplied, access is allowed, and security does not block it.

When running with `--server.port=9091`, the CLI argument normally overrides `server.port: 8080` in YAML. This mechanism allows one artifact to be deployed across multiple environments.

### Profiles and when they take effect

`application-dev.yaml` or `application-prod.yaml` can carry environment-specific settings; select profiles via `spring.profiles.active` from a valid source or `--spring.profiles.active=prod`. Profile selection and config data loading occur early so beans are created with the right values. Do not assume that editing a YAML file on disk after the application has started will immediately change beans, the HTTP port, or auto-configuration: Boot by default does not hot-reload runtime configuration like that; a dedicated refresh mechanism or a restart is required.

## 3. Auto-configuration turns classpath + configuration into infrastructure

`@SpringBootApplication` includes enabling auto-configuration. Boot reads auto-configuration classes registered by matching dependencies, then evaluates conditions before creating beans. Common conditions:

- `@ConditionalOnClass`: the required library is on the classpath.
- `@ConditionalOnWebApplication`: the context matches a web application type.
- `@ConditionalOnMissingBean`: the application has not already supplied a bean playing that role, so Boot creates the default.
- `@ConditionalOnProperty`: configuration enables a feature branch.

For example, adding the **Spring Web** dependency for a servlet application typically results in configuring Spring MVC, `DispatcherServlet`, HTTP mappings, and an appropriate embedded web server. Adding **Spring Boot Actuator** lets Boot configure endpoints, health indicators, and metrics integrations when the corresponding conditions are met.

Several key consequences:

1. **Classpath creates capability:** without a matching web dependency, setting `server.port=8080` alone is not enough to create an HTTP server.
2. **Configuration steers decisions:** setting `spring.main.web-application-type=none` can prevent the application from running as a web app even if web libraries are on the classpath; many management branches also depend on `management.*` values.
3. **Custom beans can cause auto-configuration to "back off":** Boot frequently uses `@ConditionalOnMissingBean` to avoid creating defaults that collide with application-defined beans. Do not assume every custom bean replaces an entire auto-configuration class.
4. **Auto-configuration does not replace business code:** Controllers, services, and domain rules must still be provided by the application.

To see why an auto-configuration was applied or excluded, start with the `--debug` flag and inspect the condition evaluation report in the logs. Actuator has a `conditions` endpoint for deep investigation, though that endpoint is not publicly exposed over HTTP by default; enable and protect it only when needed.

## 4. The web server is the infrastructure executing those decisions

A standalone Spring Boot application typically embeds an HTTP server inside the Java process itself:

- **Servlet stack:** Spring MVC pairs with an embedded servlet server such as Tomcat or Jetty depending on chosen dependencies. `DispatcherServlet` dispatches requests to controllers.
- **Reactive stack:** Spring WebFlux can run with Reactor Netty or a compatible HTTP server. The reactive processing model differs from the Servlet API even though both receive HTTP.
- **Non-web:** a batch process, consumer, or CLI may not open an HTTP port. Using Spring Boot does not always mean running a web server.

When Boot starts a web context, server configuration affects the listener and paths. Common keys are `server.port`, `server.address`, and for Servlet apps `server.servlet.context-path`. For example, if a Servlet app sets `server.servlet.context-path=/shop`, a business route `/api/hello` appears at `/shop/api/hello`; when there is no separate management port, default Actuator paths are also affected by the context path.

**Ports and paths are not the same thing:**

- `server.port=9090` changes the primary HTTP listening port.
- `server.servlet.context-path=/shop` changes the Servlet application's path prefix.
- `management.endpoints.web.base-path=/manage` changes the management endpoint prefix from `/actuator` to `/manage`.
- `management.server.port=9091` can open management HTTP on a separate port; in that case the management base path is resolved within the management server's context rather than simply appending to the application context path.

Port 8080 is only a common default; the actual port can be overridden by other configuration or assigned by the OS when `server.port=0` is set. If the port is already in use and no alternative is configured, the web application may fail to start.

## 5. Actuator uses the same configuration and web infrastructure

`spring-boot-starter-actuator` integrates endpoints for monitoring and diagnostics; information comes from beans in the `ApplicationContext` and from the running system. Typical endpoints:

| Endpoint | Meaning | Things to note |
| --- | --- | --- |
| `health` | Aggregates application health and health indicators | Status can be UP/DOWN/OUT_OF_SERVICE; do not equate HTTP 200 with every dependency always being healthy |
| `info` | Application, build, Git info when configured/contributed | May have very little data if no contributors are declared |
| `metrics` | Inspect Micrometer metrics currently recorded | Used for diagnostics; long-term retention requires an appropriate monitoring backend/registry |
| `env`, `configprops` | Inspect configuration/binding sources and values | Sensitive; has value sanitization mechanisms and requires restricted access |
| `conditions` | View matched/unmatched auto-configuration conditions | Useful when an expected bean does not appear |

If the application has a web server and does not customize the base path, the health endpoint is normally at `/actuator/health`. If a separate management port is set, the URL uses that port. Actuator also has non-HTTP exposure methods (such as JMX, depending on configuration), so "an endpoint exists" does not automatically mean "the endpoint is exposed over HTTP".

Three separate layers of control to understand:

1. **Endpoint exists:** whether the starter, auto-configuration, and endpoint creation conditions are met.
2. **Access/exposure:** whether the endpoint is permitted for access and exposed over HTTP/JMX. In modern default configurations, only health is exposed over HTTP; `include: health,info,metrics` widens web exposure, not a substitute for security.
3. **Security/network:** whether Spring Security, firewalls, ingress, network policies, and caller permissions allow access. When an application defines its own `SecurityFilterChain`, that configuration must also cover the relevant Actuator URLs.

**Production recommendation:** do not expose `env`, `configprops`, `beans`, `conditions`, `heapdump`, or all endpoints over the public Internet merely for debugging convenience. Keep the endpoint set minimal, protect metrics as needed, restrict health details, and consider a separate management port/private network. Configuring `management.server.port` alone does not replace firewalls or authentication.

### Management port and application health

When management runs on the same port as the application, endpoints are handled by the primary HTTP infrastructure. When `management.server.port` differs from `server.port`, Boot may create a separate management context and web server: this isolates management traffic, which also has implications for health checking. A management port that still responds does not always prove the business port listener or all business dependencies are working properly. Test readiness/liveness and actual routes according to deployment requirements; do not treat a single response from `/actuator/health` as absolute proof for every functional flow.

## 6. Runnable example: one application, two endpoint groups, multiple config sources

Create a Maven project from Spring Initializr with group `com.example`, artifact `runtime-demo`, Java 17+, and the **Spring Web** and **Spring Boot Actuator** dependencies matching the selected Boot version. Below are two Java files and one YAML file; the classes are in the same package so component scanning picks up the controller properly.

**File `src/main/java/com/example/runtime/RuntimeDemoApplication.java`:**

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/runtime/HelloController.java`:**

~~~java
package com.example.runtime;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private final Environment environment;

    public HelloController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/api/hello")
    public String hello() {
        String name = environment.getProperty("spring.application.name", "app");
        String message = environment.getProperty("demo.message", "Hello");
        return name + ": " + message;
    }
}
~~~

**File `src/main/resources/application.yaml`:** use the exact YAML content from section 2.

Run from the Maven project directory with the Spring Boot plugin configured:

~~~bash
mvn spring-boot:run
~~~

In a second terminal, call:

~~~bash
curl -s http://localhost:8080/api/hello
curl -s http://localhost:8080/actuator/health
~~~

Provided the application starts and health indicators are healthy, the returned bodies are respectively:

~~~text
runtime-demo: Hello from YAML
~~~

~~~json
{"status":"UP"}
~~~

The two URLs are created through two different paths: `/api/hello` comes from the application's `@RestController`; `/actuator/health` comes from Actuator's auto-configuration. They can share the same web server even though their purposes differ.

To observe overriding without editing Java or YAML, stop the previous run, package, and run the JAR (using the example project's default artifact and version):

~~~bash
mvn -q -DskipTests package
java -jar target/runtime-demo-0.0.1-SNAPSHOT.jar --server.port=9091 --demo.message="Hello from CLI"
~~~

Calling `curl -s http://localhost:9091/api/hello` returns the body:

~~~text
runtime-demo: Hello from CLI
~~~

At the same time, health moves to `http://localhost:9091/actuator/health` because no separate management port is configured. Port 8080 is no longer the new instance's business port. If the actual machine's config files or CLI have other overrides, inspect the final values Boot receives.

**Extending one step further:** add to `application.yaml`:

~~~yaml
management:
  server:
    port: 9092
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

On the next run with business port 9091, the business endpoint remains at `http://localhost:9091/api/hello` while management health is at `http://localhost:9092/actuator/health`. Do not assume the health endpoint also exists on the business port. In a real system, configure protection for access on port 9092 and verify firewall/network policies.

### When strongly typed business configuration is needed

`Environment.getProperty(...)` is fine for illustration, but in larger applications group configuration into `@ConfigurationProperties` with validation and strongly typed binding. For example, `demo.message`, `demo.retry-count`, and `demo.timeout` can be grouped into a configuration class. This is **application** configuration, distinct from `server.*` or `management.*` keys already read by built-in auto-configuration.

## 7. Tracking the impact of changing an input

| Change | Affected configuration/condition | Expected result |
| --- | --- | --- |
| Change `--server.port=9091` | Environment → web server factory | Business HTTP changes port; Actuator on the same port moves too unless management is separated |
| Add Spring Web to a previously non-web app | Classpath → web auto-configuration | Spring MVC, DispatcherServlet, and embedded HTTP server can appear |
| Remove Actuator dependency | Classpath → actuator auto-configuration | Corresponding Actuator endpoints are not created, even if `management.*` remains in the file |
| Set `management.server.port=9092` | Management context/server config | Management HTTP can run on a separate port |
| Only add `metrics` to web exposure | Endpoint exposure rules | `/actuator/metrics` can be accessed via HTTP if the endpoint exists and access/security allow; does not automatically add a monitoring backend |
| Declare your own bean that Boot only creates when missing | `@ConditionalOnMissingBean` | The corresponding default branch may back off in favor of the application bean |
| Set `spring.main.web-application-type=none` | ApplicationContext type | No normal application HTTP listener; `server.port` does not create a server by itself |
| Edit config file after startup | Bound values and running infrastructure | Usually requires a restart or purposefully designed refresh for changes to take effect |

Do not confuse correlation with causation: changing a YAML value **only** affects a component if application code or auto-configuration reads that key and applies it at the appropriate time.

## 8. Diagnosing common errors

**Application runs, yet requests to the right path return 404.** Check the effective `server.port`, `server.servlet.context-path` (for servlets), `management.endpoints.web.base-path`, and whether `management.server.port` is set. Test business and Actuator routes using two separate URLs. 404 generally differs from 401/403 caused by security.

**Set `management.endpoints.web.exposure.include=health,metrics`, yet `/actuator/metrics` is missing.** Check the Actuator dependency, endpoint state/conditions, access, port, and base path; next check authentication and Spring Security. Exposure is not an unconditional authorization grant. Do not enable `*` in public environments as a "quick fix".

**`server.port` is set, yet HTTP does not open.** Check `spring.main.web-application-type`, Web/WebFlux starters, and startup logs. Spring Boot supports non-web applications; configuring a port alone does not create a web stack.

**Expected an auto-configured bean, yet it is missing.** Check dependencies, profiles, property conditions, self-defined beans, and the condition evaluation report via `--debug`. Do not guess "Boot is broken" simply because an auto-configuration did not activate.

**Health returns DOWN or HTTP 503.** Check health details according to granted permissions, specific health indicators (DB, disk, dependencies...), logs, and readiness state. Changing `server.port` or exposing more endpoints does not fix a dependency outage.

**Configuration in YAML does not "take effect".** Check whether CLI args, JVM system properties, environment variables, or external config data override it; verify active profiles and key binding. Note that differently formatted keys may be normalized by relaxed binding, and configuration only takes effect after the right initialization phase.

**Opened a separate management port and assumed it is secure.** Two different ports do not mean two isolated networks. Check endpoint access/exposure, security rules, and network-level access separately.

## 9. Principles to remember

1. **Externalized configuration is operational input data**, not a web server or a mechanism that builds beans by itself.
2. **Auto-configuration decides which components are created** from conditions on libraries, beans, and properties; the application still owns business logic.
3. **The embedded web server executes HTTP**, receiving parameters via configuration and beans created by Boot.
4. **Actuator observes infrastructure and the application**, while using the same condition system, configuration, and typically the web stack; endpoints must be exposed and secured properly.
5. **One artifact can behave differently across environments** by changing external config sources, but only when the relevant component supports that key and has a suitable mechanism to apply it.

**Self-check:** If you add Actuator without adding a web starter to a non-web application, will `/actuator/health` automatically exist over HTTP? No: an appropriate web HTTP runtime is required. If you already have a web runtime and set a separate management port, do `/api/hello` and `/actuator/health` necessarily share the same port? No. If you change `server.port` via CLI and want to understand why the YAML value was overridden, what should you inspect? Inspect `PropertySource` precedence and the effective `Environment` values.

## Official reference documentation by version

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)