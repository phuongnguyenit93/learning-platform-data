# Inspecting the Classpath and Avoiding Web Stack Conflicts in Spring Cloud Gateway

When initializing **SPRING_CLOUD_GATEWAY**, a common error is having all dependencies declared yet finding that the Gateway fails to start or does not pick up routes. The root cause often lies in the **classpath**: the project intends to run the Gateway in reactive mode but accidentally pulls in Spring MVC, or conversely selects Gateway Server MVC while applying WebFlux-specific configuration and APIs.

This lesson belongs to the **Setup** chapter. The goal is to independently identify which web stack the application is using, detect conflicting dependencies, and verify that the Gateway can actually receive, process, and forward requests before building out route predicates, filter chains, path/header modifications, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

## 1. What Does the Classpath Determine at Startup?

The **classpath** is the set of classes and libraries present when the JVM loads the application. With Spring Boot, the classpath affects **auto-configuration** and web application type detection. Two key stacks to note:

- **Servlet stack**: typically uses Spring MVC, `DispatcherServlet`, and a servlet container such as Tomcat or Jetty. The corresponding Gateway is **Spring Cloud Gateway Server MVC**.
- **Reactive stack**: typically uses Spring WebFlux, `DispatcherHandler`, Reactive Streams, and an appropriate HTTP server, commonly Reactor Netty. The corresponding Gateway is **Spring Cloud Gateway Server WebFlux**.

Spring Boot can infer the web application type from the classes present:

| Classpath Signal | Common Default Result | Meaning |
|---|---|---|
| WebFlux present, no Spring MVC | `REACTIVE` | Boot can create a reactive web application context |
| Spring MVC present (even if WebFlux is also present) | `SERVLET` | Boot usually prioritizes Spring MVC when both frameworks are present |
| Required web server components missing | `NONE` or error due to missing dependencies | The application has no functioning HTTP gateway as expected |
| `spring.main.web-application-type` configured | Follows the forced value if startup conditions are met | Must verify at runtime; forcing the property does not fix wrong dependencies |

In real applications, auto-configuration, exclusions, and custom configuration also affect the outcome. Therefore, **the mere presence of a JAR is not enough to conclude which stack the Gateway is running on**. Combine the dependency tree, startup logs, and the actual application context class.

For example, a Spring MVC application can use `WebClient` from Spring WebFlux to make outbound HTTP calls; that **does not automatically turn a Servlet server into a Reactive server**. Conversely, the presence of Reactor Netty because of an HTTP client does not prove the Gateway server itself is running on Reactor Netty.

## 2. Choosing the Right Gateway Variant from the Start

Spring Cloud Gateway has two common server deployment options; exact starter names and configuration namespaces depend on the **Gateway/Spring Cloud version line**.

| Question | Gateway Server WebFlux | Gateway Server MVC |
|---|---|---|
| Web stack | Reactive, built on Spring WebFlux | Servlet, built on Spring Web MVC |
| Processing model | Reactive chain, non-blocking when supporting components allow | Servlet/WebMvc.fn and the Servlet processing model |
| HTTP receiver | Reactive web server, typically Reactor Netty | Servlet container, typically Tomcat |
| Starter in newer release lines | `spring-cloud-starter-gateway-server-webflux` | `spring-cloud-starter-gateway-server-webmvc` |
| Starter name seen in older lines | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-mvc` |
| What to avoid | Letting Spring MVC accidentally change the web application type | Copying WebFlux-specific DSLs, filters, or configuration |
| Usually suitable when | The project intentionally operates a reactive Gateway with compatible integrations | The project needs to deploy the Gateway on the Servlet stack |

**Choose one server variant as the foundation for a Gateway application.** Do not declare both Gateway server starters at the same time just to "support both." Mixing WebFlux and MVC causes confusion over routing mechanisms, filters, security, and auto-configuration.

### Maven Dependency Examples

For a **release line that supports the new starter names**, a WebFlux Gateway application can declare:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
~~~

If the intent is Gateway Server MVC, **replace** the dependency above with:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

These are **mutually exclusive alternatives**, not two blocks to combine. For older release trains, use the corresponding starter name specified in the documentation **for that exact version**. The Gateway starter version is typically managed by the **Spring Cloud BOM** compatible with Spring Boot; do not arbitrarily assign independent versions to multiple Spring Cloud artifacts.

In Gradle Kotlin DSL, also pick **one** of the two:

~~~kotlin
dependencies {
    // Gateway Server WebFlux on a release line supporting this starter
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")

    // If choosing Server MVC, remove the WebFlux line above
    // and use the corresponding MVC starter instead:
    // implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webmvc")
}
~~~

The blocks above only illustrate the **Gateway dependency portion**, not a complete Spring Boot project. When creating a real project, configure the Spring Boot plugin/parent, dependency management or BOM, and a compatible JDK; cross-check versions against the official documentation for your release train.

## 3. Why Adding `spring-boot-starter-web` Can Break a WebFlux Gateway

Consider a project that initially has only Gateway Server WebFlux. Later, a team member adds `spring-boot-starter-web` thinking every REST API needs this starter:

~~~xml
<!-- Do not add to a WebFlux Gateway application merely out of habit -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

This starter typically brings **Spring MVC** (`spring-webmvc`) and Servlet libraries onto the classpath. If Boot detects both Spring MVC and WebFlux, it **usually selects `SERVLET` by default**. Meanwhile, Gateway Server WebFlux requires a reactive environment. Depending on the version, the application may display a message like "Spring MVC found on classpath; incompatible with Spring Cloud Gateway," or other bean/auto-configuration errors related to the web stack.

The origin of `spring-webmvc` is not necessarily a directly declared dependency. It can enter via a shared library starter, an internal module, an API docs generator, or a transitive dependency.

~~~mermaid
flowchart TD
    A["Gateway Server WebFlux Application"] --> B["Add direct or transitive dependency"]
    B --> C{"Does classpath contain Spring MVC?"}
    C -->|No| D["Boot can select REACTIVE"]
    C -->|Yes| E["Boot usually prioritizes SERVLET"]
    D --> F["Verify reactive context and real route"]
    E --> G["Gateway WebFlux risks failing to initialize"]
    G --> H["Find dependency branch pulling spring-webmvc"]
    H --> I["Remove or replace the dependency"]
    I --> F
~~~

**Having both `spring-webflux` and `spring-webmvc` in the JVM is not always wrong.** This combination can be valid when the application is intentionally Servlet-based and uses a reactive HTTP client. Conflicts arise when **the actual selected stack does not match the requirements of the Gateway server in use**, or when a team applies configuration/APIs from the wrong variant.

## 4. Inspecting the Classpath with Maven

First, run the command in **the module that actually builds the Gateway application**, not just at the root of a multi-module project.

~~~bash
# Show the dependency tree and paths pulling libraries into the application
./mvnw dependency:tree

# Optionally focus on core Spring artifacts
./mvnw dependency:tree -Dincludes=org.springframework:*
~~~

On Windows, use `mvnw.cmd` instead of `./mvnw` if the project has the Maven Wrapper. If there is no Wrapper, use the installed Maven (`mvn`).

From the output, look for these components:

- `spring-cloud-starter-gateway...`: which Gateway starter is selected, WebFlux or MVC?
- `spring-webmvc`, `spring-boot-starter-web`: signs that Spring MVC is present.
- `spring-webflux`, `spring-boot-starter-webflux`: WebFlux components.
- `spring-boot-starter-tomcat` or another servlet container: check whether a Servlet server dependency is present.
- `reactor-netty-http` or another server library: inspect reactive components; do not draw conclusions from a single JAR alone.
- `spring-cloud-dependencies` and resolved dependencies: cross-check the release train, Boot, and Gateway to avoid version mismatches.

**Tree reading tip:** if you see `spring-webmvc`, trace upward along parent branches to see which dependency pulled it in. For example, in an illustrative layout:

~~~text
gateway-app
+-- spring-cloud-starter-gateway-server-webflux
\-- shared-web-starter
    \-- spring-boot-starter-web
        \-- spring-webmvc
~~~

In this case, the point to address is `shared-web-starter` or its dependency relationship, not blindly deleting the `spring-webmvc` JAR from the cache.

### Checking Maven Dependency Management

If `pom.xml` declares the dependency yet Gateway still resolves to the wrong version, read the **effective POM** or dependency tree to see the resolved version. The Spring Cloud BOM manages artifacts within the same release train; cross-check against the Spring Boot–Spring Cloud compatibility table for the **version line you are running**. Do not force an individual starter version to fix a web stack error when the root cause is mixing Servlet and Reactive.

## 5. Inspecting the Classpath with Gradle

With Gradle, inspect the **runtimeClasspath** of the module running the Gateway; `compileClasspath` may not reflect all runtime dependencies.

~~~bash
# View all dependencies selected for runtime
./gradlew dependencies --configuration runtimeClasspath

# Find why spring-webmvc is present and which version is selected
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath

# Trace back the web starter if present
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath

# Identify the Gateway starter and its resolved versions
./gradlew dependencyInsight --dependency spring-cloud-starter-gateway --configuration runtimeClasspath
~~~

On Windows, you can use `gradlew.bat`. For multi-module Gradle builds, target the specific module task, such as `:gateway-app:dependencyInsight`. For builds with custom configurations, select the configuration matching the artifact that will run. A dependency in `testRuntimeClasspath` **does not automatically mean** a production runtime conflict.

When Gradle reports a version chosen by conflict resolution or a constraint, verify which BOM/plugin is managing which dependency. Do not remove constraints or add `force` before checking release train compatibility.

## 6. Resolving Conflicts: Fix the Root Cause

### Case A — The Project Needs Gateway Server WebFlux

1. Confirm that the Gateway dependency actually belongs to the **Server WebFlux** variant for your current version.
2. Find where `spring-boot-starter-web`/`spring-webmvc` is declared directly or pulled in by another dependency.
3. Remove the unnecessary Servlet starter or **replace** the shared library with a variant that does not force MVC.
4. If the library is still needed for business logic, add an exclusion **on the exact offending branch** and verify that it still works without MVC.
5. Re-run the dependency tree and start the Gateway; confirm the reactive context and working routes.

**Illustrative** Maven example: library `com.example:legacy-client` is confirmed to only use the HTTP client part, yet it mistakenly pulls in `spring-boot-starter-web`.

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

In Gradle Kotlin DSL, the corresponding exclusion is:

~~~kotlin
implementation("com.example:legacy-client:1.0.0") {
    exclude(group = "org.springframework.boot", module = "spring-boot-starter-web")
}
~~~

**This is not a default fix for every library.** If `legacy-client` genuinely requires `DispatcherServlet` or Servlet APIs, excluding it can cause runtime failures; you must change the design or split modules. In particular, an exclusion on one branch will not remove `spring-webmvc` if it is also pulled in from another branch. Always re-inspect the dependency tree **after** making changes.

### Case B — The Project Needs Gateway Server MVC

Keep the **Server MVC** starter matching your release train and Servlet web stack. Do not replace the MVC starter with WebFlux just because online documentation shows similar routes/filters. Consult the APIs, route predicates, and filters of **Gateway Server MVC**; a filter written for reactive exchanges cannot automatically be used in a Servlet filter chain.

You can use `WebClient` for outbound HTTP from a Servlet application when truly needed, while still confirming that Boot creates a **Servlet web context** and initializes Gateway MVC routes properly.

### Case C — Wanting to Force `spring.main.web-application-type=reactive`

In some versions, you can use:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

This property **only forces Boot to pick the web application type**; it does not remove `spring-webmvc` from the classpath and does not turn Servlet-based controllers or libraries into reactive components. Nor does it turn Gateway MVC into Gateway WebFlux.

Use this option only when you have confirmed the deployment intent is reactive, fully understand the dependency sources, and have verified all integrated components. For new projects, **removing the dependency that causes the stack mismatch** is usually clearer and easier to maintain.

Similarly, `web-application-type: none` is not a fix for an HTTP Gateway because Boot will not start a web server to receive requests as expected.

## 7. Verifying the Actual Web Stack at Runtime

The dependency tree shows which libraries are present; the next step is proving **the application created the right server**.

### Step 1 — Inspect Startup Logs and the Application Context

At startup, observe the web server, application context type, and auto-configuration messages. Commonly:

- **Server WebFlux**: a reactive web server context class, such as `ReactiveWebServerApplicationContext`; the default HTTP server is usually Reactor Netty.
- **Server MVC**: a servlet web server context class, such as `ServletWebServerApplicationContext`; the HTTP server is usually Tomcat, Jetty, or an appropriate servlet container.

Do not rely solely on the name `Netty` or `Tomcat`: depending on configuration, WebFlux can run on another server; the context type and registered routes are more reliable indicators.

You can temporarily print the application context class for diagnostics:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebStackDiagnostics {

    @Bean
    ApplicationRunner showWebContext(ApplicationContext context) {
        return args -> System.out.println(
            "Gateway ApplicationContext: " + context.getClass().getName()
        );
    }
}
~~~

This snippet is for **observation**, not for deciding the stack by matching class name strings. Remove temporary logging after troubleshooting, or replace it with automated checks suited to your project.

### Step 2 — Test a Real Route Against a Mock Downstream

The example below illustrates a route configuration commonly used in **some Gateway Server WebFlux 4.x lines**. Namespace names and route formats may differ in other lines/variants; check the documentation for the exact version you are using:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: http://localhost:9090
          predicates:
            - Path=/api/inventory/**
          filters:
            - StripPrefix=1
~~~

Assume a downstream service is running on port **9090** and returns HTTP 200 for `GET /inventory/items`. After starting the Gateway on port **8080**, call:

~~~bash
curl -i http://localhost:8080/api/inventory/items
~~~

Expected outcome: the Gateway matches the `Path` predicate, `StripPrefix=1` removes the `api` segment, and the downstream receives `GET /inventory/items`. If the Gateway has no route, you may get **404**; if the route exists but the downstream is unreachable, you may see **5xx**. Exact status codes also depend on filters, exception handlers, and versions, so check logs rather than guessing from the status code alone.

With **Gateway Server MVC**, use the MVC route configuration/DSL and perform the same input/output test. Do not copy WebFlux's YAML namespace into an MVC application and assume routes will load.

### Step 3 — Test Error Cases Too

A valid Gateway also needs to handle mismatched paths, stopped downstreams, and rejected security checks. Depending on enabled features, verify:

| Behavior | What to Observe |
|---|---|
| Route predicate does not match | Request is not forwarded to the wrong service; 404 behavior is handled properly |
| Path/header-modifying filters | Downstream receives the right path/headers; sensitive headers are not leaked accidentally |
| Authentication | Requests with missing/invalid tokens are blocked at the appropriate layer |
| Rate limiting | Requests exceeding the threshold are handled per policy, typically HTTP 429 |
| Circuit breaker and retry | No infinite retries are created; fallback/error handling behaves as expected |
| Service discovery | Service names resolve through the configured discovery/load balancer mechanism |
| TLS | Verify HTTPS, trust/certificates, and downstream connection setup |
| Logs/metrics/tracing | Observability data is emitted for routes, latency, errors, and request flow for your version |

These checks apply only once the corresponding features are configured. This lesson focuses on getting the **web stack foundation right**, which is a prerequisite before implementing those integrations.

## 8. Common Errors and How to Isolate Them

| Symptom | Possibilities to Check | How to Fix |
|---|---|---|
| Startup reports MVC is incompatible with Gateway | Using **WebFlux Gateway** while Spring MVC is on the classpath | Trace `spring-webmvc`, remove/replace unnecessary Servlet dependencies |
| `spring-webflux` is present yet Boot still creates a servlet context | `spring-webmvc` is also on the classpath | Clarify MVC vs. WebFlux intent; a WebFlux HTTP client does not mean a reactive server |
| Application runs but registers no routes | Wrong Gateway variant or config namespace; auto-configuration not activated | Check starter, route config, and logs for your exact version |
| `ClassNotFoundException`, `NoSuchMethodError`, missing Gateway beans | Incompatible Spring Boot/Spring Cloud/Gateway versions or missing classpath dependencies | Check the BOM and resolved dependencies; restore a compatible version set |
| Gateway MVC starts up, but copied WebFlux filters fail | APIs/filters differ between the two variants | Rewrite using Gateway Server MVC APIs |
| Gateway WebFlux runs but errors when handling requests | A component requires Servlet APIs or performs blocking operations on the event loop | Identify the dependency/stack and locate blocking I/O; switch to an appropriate API |
| Runs locally, fails in packaged artifact | Runtime classpath, profiles, scopes, or packaged dependencies differ from IDE environment | Inspect dependencies and logs of **the actual deployed artifact** |

**Do not immediately blame every HTTP 404/5xx on a stack conflict.** Conclude that only when you find evidence from the dependency tree, context, route config, and logs. Route errors, service discovery issues, or security rules can produce similar symptoms.

## 9. End-to-End Diagnostic Workflow

Practical scenario: a team creates a reactive API Gateway to route `/api/orders/**`, then integrates a shared starter and the application starts failing at startup.

1. **State the intent clearly:** this is **Gateway Server WebFlux**, requiring a reactive server, with no need to run Spring MVC controllers.
2. **Read the build file:** confirm the selected Gateway starter and Spring Boot/Spring Cloud BOM versions. Do not mix in the Gateway MVC starter.
3. **Inspect runtime dependencies:** run `dependency:tree` or `dependencyInsight`, locate `spring-webmvc`, and trace the transitive branch coming from the shared starter.
4. **Fix the dependency relationship:** remove or replace the starter introducing Servlet APIs if it does not serve the Gateway; avoid exclusions if the library genuinely depends on MVC.
5. **Verify after fixing:** re-run the dependency tree; build and start the application following project procedures, observing the reactive context and registered routes.
6. **Test a request:** call the route to a mock downstream, verifying paths/headers, success codes, and error codes per scenario.
7. **Document the decision:** record the Gateway artifact, resolved versions, variant, conflict cause, adjusted dependencies, and smoke test evidence.

If the team intentionally deploys the Gateway on Servlet, start the workflow above with **Gateway Server MVC**, confirm the servlet context, and replace reactive examples/DSLs with the corresponding MVC documentation.

~~~mermaid
flowchart TD
    A["Gateway fails to start or route does not work"] --> B["Confirm whether WebFlux or MVC was chosen"]
    B --> C["Inspect Maven/Gradle runtime classpath"]
    C --> D{"Do starter and stack match?"}
    D -->|No| E["Find direct/transitive dependency causing mismatch"]
    E --> F["Remove, replace, or exclude with verification"]
    D -->|Yes| G["Verify Boot/Cloud BOM and route configuration"]
    F --> G
    G --> H["Start up and inspect application context"]
    H --> I["Smoke test route with downstream"]
    I --> J{"Does the result meet requirements?"}
    J -->|Not yet| C
    J -->|Passed| K["Record versions, dependencies, and results"]
~~~

## 10. Pre-Development Checklist for Gateway

- [ ] Selected **Server WebFlux** or **Server MVC** for the application.
- [ ] Confirmed the **Gateway starter matches the name for the release train in use**.
- [ ] Cross-checked **JDK, Spring Boot, Spring Cloud BOM, and Gateway** versions.
- [ ] Checked **runtimeClasspath** or the Maven dependency tree of the runnable module.
- [ ] Traced any `spring-webmvc`/`spring-boot-starter-web` source if the project requires Gateway WebFlux.
- [ ] Confirmed both Gateway server starters are not accidentally included together.
- [ ] Accounted for why `spring-webflux` is present if the project intentionally targets Servlet.
- [ ] Inspected startup logs and confirmed the matching **application context** type.
- [ ] Verified route predicates, path/header filters, and downstream with real requests.
- [ ] Tested at least one error case; checked security/TLS/rate limiting/discovery configs if enabled.
- [ ] Documented any dependency exclusions or web stack choices for the maintenance team.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — choose the right **version** and the **Server WebFlux** or **Server MVC** section.
- [Spring Cloud project](https://spring.io/projects/spring-cloud) — release trains and Spring Boot compatibility information.
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/) — web applications, auto-configuration, and dependency management.
- [Spring Framework — Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux mechanics and relationship with the Servlet stack.

**Remember:** a Gateway operates reliably only when the **Gateway variant, runtime dependencies, Spring Boot web application type, and route configuration** align. Verify the classpath and request flow right at setup, before adding filters and microservice resilience mechanisms.
