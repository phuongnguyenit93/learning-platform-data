# Checking Dependencies, URL Mappings, and Versions When Combining Multiple Web Platforms in Spring Boot

## 1. Objectives and Real-World Scenarios

A Spring Boot application can grow from a simple REST API into a system combining multiple technologies: Spring MVC, WebFlux client, Jersey/JAX-RS, custom servlets, security filters, static assets, WebSocket, template engines, Actuator, and an edge reverse proxy. Each may work well in isolation, yet **combining** them often introduces three hard-to-spot failure categories:

1. **Dependencies / classpath:** two starters pick different web stacks; a library pulls incompatible Spring/Jakarta/Jersey versions; transitive dependencies override Boot's standard libraries; conflicting JSON providers or embedded servers appear.
2. **URL mappings (routing/mapping):** default Jersey servlet covers `/*` and steals requests from `DispatcherServlet`; custom servlets or filters match too broadly; context path is confused with servlet path; proxies rewrite URIs; paths across MVC, JAX-RS, static assets, and Actuator collide.
3. **Versions / contracts:** Boot/Framework/server/Jakarta APIs drift out of sync; legacy `javax.*` namespaces mix with `jakarta.*`; `/v1` and `/v2` URLs overlap ambiguously; routing behavior shifts on Spring Framework upgrades; tests pass in the IDE while the executable JAR fails on classpath or scanning.

**Deployment principle:** establish **one primary web runtime**, select dependencies from the same Spring Boot BOM, assign **each platform its own URL region**, and test real HTTP behavior at every layer. Do not stop at "mvn package succeeded."

This lesson uses **Java 17+ and Spring Boot 3.5.16**; the complete source files demonstrate an application hosting **Spring MVC + Jersey/JAX-RS + a custom Servlet** on the same embedded Tomcat with separated URLs. It also covers MVC + WebFlux, Jakarta APIs, security filters, version alignment, testing, and common pitfalls.

### After This Lesson, You Should Be Able to Answer

- Why does adding `spring-boot-starter-webflux` to MVC **not automatically switch** the application to WebFlux?
- Why can Jersey cause an MVC `@GetMapping` to return 404 even when the method is valid?
- In `/app/api/hello`, which part is the **context path**, **servlet mapping**, and **controller path**?
- How do you use Maven/Gradle to inspect the **runtime dependency tree** and BOM-managed versions?
- Why shouldn't you arbitrarily pin `spring-webmvc`, Jersey, or Jakarta Servlet versions?
- How do you test a route against the **right technology**, rather than merely asserting status 200?
- Behind Nginx/Ingress, how do you trace public URLs, upstream URLs, and the actual receiving handler?

## 2. What Does "Combining Multiple Platforms" Actually Mean?

Having multiple web libraries does not automatically mean multiple HTTP servers are fighting over requests. Classify the combinations:

| Combination | Usable? | Core Point |
| --- | --- | --- |
| Spring MVC + RestClient | Yes, common | MVC handles inbound; `RestClient` makes synchronous outbound HTTP calls |
| Spring MVC + WebClient | Yes | Adds WebFlux library for **outbound client**; inbound usually remains MVC |
| Spring MVC + Jersey/JAX-RS | Yes, with explicit mapping design | Both are Servlet-based frameworks; partition `DispatcherServlet` and Jersey servlet |
| Spring MVC + custom servlet | Yes | Use `ServletRegistrationBean` with narrow path, avoiding `/*` |
| Spring MVC + Thymeleaf + static assets | Yes | Template/view resolvers and static handlers; watch for controller path collisions |
| WebFlux + Reactor Netty | Yes, default reactive starter | Reactor Netty handles inbound; Reactor/WebFlux reactive stack |
| WebFlux + blocking JPA/JDBC | Technically possible with proper handling | Never run blocking JDBC on the event loop |
| MVC + WebFlux server in **one** Boot app | Does not run two dispatchers simultaneously by default | Boot 3.5 **prioritizes MVC** when both starters are present |
| Jersey/JAX-RS + Spring Security Servlet | Yes, requires clear policy/filters | Security filters attach to the Servlet request pipeline, not MVC controllers alone |
| gRPC + HTTP REST + WebSocket | Yes with compatible libraries/servers | May use separate **listeners/ports/protocols**; do not assume shared mappings |
| JSF/Vaadin + Spring MVC | Yes with compatible integration | Separate servlet/filter/view lifecycles; needs aligned versions/mappings |
| Actuator + REST API | Yes | Management endpoints can share or use a separate port/base path |

**Similar words are not equivalent:**

- WebFlux **server** differs from `WebClient` **client**.
- Servlet container (Tomcat/Jetty/Undertow) differs from Spring MVC `DispatcherServlet`.
- A Jersey REST resource differs from a Spring MVC `@RestController`, even when both return JSON.
- JAX-RS `jakarta.ws.rs.Path` is not Spring MVC `@RequestMapping`.
- A public ingress URL is not necessarily the URI seen by the backend.
- A business API version `/v2` differs from **library versions** and Spring Boot versions.

## 3. Step 1: Identify the Actual Web Application Type

### 3.1. Spring MVC (Servlet Stack)

In Spring Boot 3.5, `spring-boot-starter-web` typically brings Spring MVC and embedded Tomcat. Default pipeline:

```text
HTTP connection -> Tomcat
     -> Servlet filters
     -> DispatcherServlet
     -> HandlerMapping
     -> @RestController / @Controller
     -> HTTP response
```

Spring MVC uses Jakarta Servlet APIs and `DispatcherServlet`, suited to imperative apps using JDBC/JPA, synchronous service calls, view templates, or servlet integrations.

### 3.2. Spring WebFlux (Reactive Stack)

`spring-boot-starter-webflux` typically uses Reactor Netty as the embedded server in pure reactive projects:

```text
HTTP connection -> Reactor Netty
     -> HttpHandler/WebFilter
     -> DispatcherHandler/RouterFunction
     -> Mono/Flux handler
     -> HTTP response
```

WebFlux does not require the Servlet API to run and uses reactive streams/backpressure. Still, **WebFlux can also run on certain Servlet containers via adapters**, depending on config; never equate "WebFlux" strictly with "Netty" in every architecture.

### 3.3. When Both Starters Are Present

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

This is a **Maven fragment**, not a complete POM. In Spring Boot 3.5, when both MVC and WebFlux are on the classpath, **MVC is chosen as the default web application type**. This is intentional so MVC apps can still use outbound `WebClient`.

Consequences:

- `@GetMapping` controllers are managed by Spring MVC `RequestMappingHandlerMapping`.
- You can use `WebClient` to call external services; you do not simultaneously run an independent WebFlux `DispatcherHandler` for inbound traffic.
- `WebFluxConfigurer` beans or `spring.webflux.*` properties do not automatically configure MVC.
- If the app must **genuinely** run reactive, pick the right starter/runtime or set `spring.main.web-application-type=reactive` after auditing the entire classpath; doing so **does not** make Servlet-based Jersey integration reactive.

**Do not add both starters just to "boost performance."** Pick one primary runtime; add client libraries only for concrete needs.

### 3.4. Verifying the Runtime via Code and Logs

Once the app starts, a small component can inspect the context type (snippet, not the demo project):

```java
@Component
class RuntimeReporter implements ApplicationRunner {
    private final ApplicationContext context;

    RuntimeReporter(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Context=" +
                context.getClass().getSimpleName());
    }
}
```

This code requires Spring imports for `ApplicationRunner`, `ApplicationArguments`, `ApplicationContext`, and `@Component`. In an embedded MVC app you typically see a Servlet web application context; a reactive server uses a Reactive web context. Do not rely solely on the printed class name when custom contexts exist; verify alongside the dependency tree, startup logs, and HTTP tests.

## 4. Step 2: Inspect the Dependency Graph and Version Alignment

### 4.1. The Spring Boot BOM Is the Primary Version Source

Spring Boot publishes the `spring-boot-dependencies` **Bill of Materials (BOM)** managing compatible versions across Spring Framework, embedded servers, Jackson, validation, logging, and many third-party libraries.

With Maven, the simplest approach is `spring-boot-starter-parent`:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
```

After that, you normally **omit explicit `<version>` tags** for `spring-boot-starter-web`, `spring-boot-starter-jersey`, and other BOM-managed dependencies.

With Gradle, apply matching plugin and dependency management/platform BOM versions. Example with the Spring Dependency Management plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a **Gradle fragment illustrating dependency management**; plugin versions and project layout must fit your real Gradle wrapper. Never combine multiple conflicting BOMs assuming version selection stays conflict-free.

### 4.2. Maven Commands to Inspect Dependencies

Run in the directory containing `pom.xml`:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework:*
mvn dependency:tree -Dincludes=org.glassfish.jersey:*
mvn dependency:tree -Dincludes=jakarta.servlet:*
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:analyze
```

Meaning:

- `dependency:tree`: reveals transitive dependencies, servers, and resolved libraries.
- `-Dincludes`: filters group/artifact patterns to spotlight Spring/Jersey/Jakarta.
- `help:effective-pom`: inspects the merged parent/BOM/plugin/dependency management result.
- `dependency:analyze`: helps spot used/unused/undeclared dependencies (with caveats for reflection/runtime providers).
- The **runtime classpath** is what actually gets packaged and executed. You may also inspect `mvn dependency:build-classpath` and the executable JAR contents.

In PowerShell, if `*` is expanded unexpectedly by the shell, quote the entire argument: `"-Dincludes=org.springframework:*"`. Never assume a dependency is absent just because an improperly quoted filter returned empty output.

### 4.3. Gradle Inspection for Transitive Dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jersey-server --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet-api --configuration runtimeClasspath
```

Gradle's conflict resolution rules differ from Maven's; `dependencyInsight` explains why a particular version won. Inspect both the CLI build and IDE run configurations if an error only reproduces in the IDE.

### 4.4. Version Groups That Must Share the Same Generation

| Component | What to Confirm | Typical Failure if Wrong |
| --- | --- | --- |
| Spring Boot 3.5.x | Consistent parent/BOM and starters | Unexpected auto-configuration behavior |
| Spring Framework | Managed by Boot BOM, never pinned arbitrarily | `NoSuchMethodError`, handler/config incompatibility |
| Tomcat 10.1.x | Matching Servlet/Jakarta generation | Classloading/Servlet API mismatch |
| Jersey 3.x | Jakarta JAX-RS and compatible Jersey modules | `ClassNotFoundException`, provider/servlet init failure |
| Jackson | Synchronized core/databind/module versions | Decode errors, linkage errors, duplicate providers |
| Spring Security | Matches Boot generation and filter chain runtime | Filter/API incompatibility |
| Jakarta Servlet | `jakarta.servlet.*` on Boot 3.x | `javax.servlet.*` incompatible |
| Jakarta REST | `jakarta.ws.rs.*` for Jersey 3.x | Providers or resources fail to register |
| Reactor Netty | BOM-managed version if WebFlux is added | Codec/Netty runtime mismatch |
| JDK | **Java 17+** for Boot 3.5 | `UnsupportedClassVersionError` or build errors |

Boot 3.x moved to the Jakarta EE ecosystem. Older libraries using `javax.servlet.*` and `javax.ws.rs.*` cannot be fixed by mechanically changing imports alone; you must upgrade **the entire compatible API/provider/adapter stack**.

### 4.5. Version Anti-Patterns

- Explicitly declaring `org.springframework:spring-webmvc:5.x` inside Spring Boot 3.5 from an old example.
- Adding `javax.servlet:javax.servlet-api` and implementing `javax.servlet.Filter` on Tomcat 10.x.
- Mixing Jersey 2.x (`javax`) and Jersey 3.x (`jakarta`) through transitive dependencies.
- Pinning one Jackson module to a different generation than the rest without tests.
- Swapping a single Spring Framework jar to patch a CVE while ignoring Boot patches/BOM compatibility.
- Leaving both embedded Tomcat and Jetty starters unexcluded, muddying runtime selection/classpath.
- Adding an HTTP client library that transitively pulls in unexpected server auto-configuration.

**Proper approach:** upgrade **Spring Boot patches** and curated BOM dependencies whenever possible; document any necessary overrides with rationale, security advisory checks, and regression tests. Never rely solely on "mvn compile passed" — linkage errors often surface only at startup or first request.

## 5. Step 3: Multi-Layer URL Mapping Model

The URL seen by the browser rarely matches the pattern in `@GetMapping` one-to-one. In an embedded Servlet app, think in order:

```text
Scheme + Host + Port
    |
    +-- Reverse proxy public prefix / rewrite (if any)
    |
    +-- Servlet context path
    |
    +-- Servlet mapping (DispatcherServlet / Jersey servlet / custom)
    |
    +-- Framework handler path (MVC @GetMapping / JAX-RS @Path)
    |
    +-- HTTP method + headers + params + consumes/produces
```

Example:

```text
http://localhost:8080/demo/mvc/hello
  host:port         /demo   /mvc/hello
                    context   MVC controller mapping
```

When `DispatcherServlet` is mapped at `/` by default, Spring MVC's handler mapping owns `/mvc/hello`. A Jersey servlet mapped at `/jaxrs/*` causes `/demo/jaxrs/hello` to be **dispatched by the Servlet container to Jersey**, not Spring MVC.

### 5.1. Servlet Context Path

```properties
server.servlet.context-path=/demo
```

This property sets the context root for the **Servlet web application**, meaning MVC, Jersey, and custom servlets registered in that context are all accessed beneath `/demo`. It is neither a controller `@RequestMapping` nor a proxy public prefix.

### 5.2. DispatcherServlet Mapping

By default Spring Boot MVC mounts `DispatcherServlet` at the root context; a controller can declare:

```java
@RestController
@RequestMapping("/mvc")
class HelloController {
    @GetMapping("/hello")
    String hello() { return "mvc-ok"; }
}
```

This is a snippet. With context path `/demo`, the URL is `/demo/mvc/hello`.

You can change MVC's Servlet mapping via `spring.mvc.servlet.path`. However, in **Spring Boot 3.5, the default `PathPatternParser` has limitations when using a servlet path prefix**. If you actually configure:

```properties
server.servlet.context-path=/demo
spring.mvc.servlet.path=/spring-api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

then an MVC controller `@GetMapping("/hello")` becomes reachable at `/demo/spring-api/hello`. **Do not assume `spring.mvc.servlet.path` applies to the Jersey servlet or custom servlets.** Before enabling it, verify Boot/Framework version behavior and regression tests; merely to group URLs, `@RequestMapping("/mvc")` is simpler than moving `DispatcherServlet`.

### 5.3. Jersey `@ApplicationPath`

Spring Boot provides starter and auto-configuration support for Jersey/JAX-RS. Without restricting its mapping, **the default Jersey servlet maps to `/*`**, stealing requests you expected MVC to serve.

Clean solution:

```java
@Component
@ApplicationPath("/jaxrs")
class JerseyResources extends ResourceConfig {
    JerseyResources() {
        register(JerseyHelloResource.class);
    }
}
```

This is a snippet. With `@ApplicationPath("/jaxrs")`, Jersey maps under `/jaxrs` inside the servlet context. A resource `@Path("/hello")` resolves to `/demo/jaxrs/hello` when context path is `/demo`.

**Executable JAR packaging note:** Boot 3.5 docs advise **registering each resource class explicitly** via `ResourceConfig.register(...)` instead of relying on `packages(...)` scanning, because Jersey scanning in executable archives has limitations. Resources should be `@Component` for Spring DI alongside JAX-RS annotations like `@GET` and `@Path`.

### 5.4. Custom Servlet Mapping

`ServletRegistrationBean` gives explicit control over servlet names and URL patterns:

```java
@Bean
ServletRegistrationBean<HealthServlet> healthServlet() {
    return new ServletRegistrationBean<>(
            new HealthServlet(), "/legacy/*");
}
```

This is a snippet where `HealthServlet` is an application-defined `HttpServlet`. Map narrowly like `/legacy/*`, avoiding `/*` or `/` unless intentionally altering container-wide dispatch. In the complete project below, the custom servlet serves `/legacy/health` without intercepting MVC or Jersey.

### 5.5. The Servlet Container Picks a Servlet Before Any Framework Picks a Controller

Crucial rule: with Spring MVC + Jersey + custom Servlet, routing has **two stages**:

1. The Servlet container picks a servlet by path mapping (exact, longest path-prefix, extension, default, per the Servlet spec).
2. **Only after** the servlet receives the request do Spring MVC `HandlerMapping` or Jersey resource matching pick an internal handler.

Consequently, two endpoints both written `/hello` inside **two separate servlets** are not necessarily an "ambiguous MVC mapping"; they can be cleanly separated by `/mvc/*` and `/jaxrs/*`. Conversely, if Jersey maps `/*` and MVC maps `/`, Jersey grabs the request before Spring MVC ever runs.

**Do not expect Spring MVC to report "Ambiguous mapping" for a conflict occurring earlier at the Servlet container.** Spring MVC only sees requests that actually reach `DispatcherServlet`.

## 6. Build a URL Ownership Matrix Before Coding

Example with `server.servlet.context-path=/demo`:

| Local Public URL | Expected Owner | Definition | Proper Verification |
| --- | --- | --- | --- |
| `/demo/mvc/hello` | Spring MVC | `@RequestMapping("/mvc")` + `@GetMapping("/hello")` | Body `mvc-ok` |
| `/demo/jaxrs/hello` | Jersey/JAX-RS | `@ApplicationPath("/jaxrs")` + `@Path("/hello")` | Body `jersey-ok` |
| `/demo/legacy/health` | Custom Servlet | `ServletRegistrationBean("/legacy/*")` | Body `legacy-ok` |
| `/demo/mvc/missing` | MVC, no endpoint | MVC mapping miss / static handler fallback | HTTP 404 |
| `/demo/jaxrs/missing` | Jersey, no resource | Jersey resource miss | HTTP 404 |
| `/demo/hello` | Unregistered | Avoid guessing owner | HTTP 404 |
| `/demo/assets/app.js` | Static resource **if present** | MVC resource handler or another servlet | 200 if the file really exists |
| `/actuator/health` | Actuator **if added** | Management base path/port config | Do not infer from app endpoints |

**Never judge success solely by HTTP 200.** For instance, an SPA fallback returning `index.html` with HTTP 200 for `/api/missing` does not mean the API route worked. Verify `Content-Type`, body, response headers, and route owner.

### Paths Mean Different Things by Endpoint Type

- Spring MVC `@RequestMapping` and `@GetMapping`: path relative **inside `DispatcherServlet`**.
- Jersey `@Path`: path relative **inside the Jersey application mapping**.
- Servlet `/legacy/*`: inspects `getServletPath()`/`getPathInfo()` per pattern.
- Static resources: `spring.mvc.static-path-pattern` applies to MVC resource handlers, not Jersey mappings.
- WebFlux: has its own `HandlerMapping` and `spring.webflux.static-path-pattern`, distinct from MVC.
- Actuator management port/base-path: may run on a separate listener/context.
- Reverse proxy public prefix: may be stripped or rewritten before reaching the app.

## 7. Where Else Do URL Conflicts Come From?

### 7.1. Two MVC Controllers Registering the Same Request Mapping

If two MVC methods share identical **method + path + mapping conditions** (headers, params, consumes, produces...), Spring MVC fails startup with an ambiguous mapping error. Never try to "solve" this by tweaking `@Order` arbitrarily; assign distinct paths or disambiguate mapping conditions.

When patterns overlap partially with different specificities, Spring MVC picks by specificity. Always **test the real URLs** rather than just searching source code for matching strings.

### 7.2. Jersey Capturing `/*`

A `/*` Jersey servlet mapping competes with `DispatcherServlet`'s default `/`. Symptom: the MVC controller exists yet `GET /api/users` returns 404, and logs show Jersey handling or rejecting the request. Fix with `@ApplicationPath("/jaxrs")` or explicit `ServletRegistrationBean`/ownership rules.

Do not debug by disabling `@RestController`, adding random `@ComponentScan` annotations, or changing ports before determining which Servlet received the URL.

### 7.3. Overly Broad Servlets or Filters

A Servlet registered at `/*` can intercept every URL, starving MVC, Jersey, and Actuator. A Filter mapped to `/*` affects **every Servlet**, not just MVC. If a filter writes `401`/`403` and returns without calling `chain.doFilter`, downstream framework handlers never execute.

Register filters with `FilterRegistrationBean` and specify explicit URL patterns when a filter targets only one subsystem. Distinguish Spring Security's security filter chain from custom servlet filters.

### 7.4. Static Resources, WebJars, and SPA Fallbacks

Spring MVC usually registers static resource mapping `/**` to serve classpath `/static`, `/public`, and similar folders. A request with no matching controller can reach the resource handler and return 404 via `NoResourceFoundException` instead of `NoHandlerFoundException`. If an SPA fallback catches `/**` and serves `index.html` for every unknown path, API 404s get masked as HTML 200s.

Partition namespaces cleanly:

- `/api/**` for backend APIs.
- `/assets/**` for hashed static assets.
- `/webjars/**` for WebJars if used.
- `/ui/**` or `/` for frontend pages.
- `/jaxrs/**` for Jersey.
- `/legacy/**` for custom servlets.

Never dump all handlers and filters onto `/**` without testing ordering and fallback behavior.

### 7.5. Security, CORS, and CSRF

When MVC and Jersey coexist on the Servlet stack, Spring Security `FilterChainProxy` operates at the **Servlet filter level**. A security policy relying only on `MvcRequestMatcher` for a `DispatcherServlet` path may fail to cover Jersey or custom servlet resources as expected.

Verify:

- Which `SecurityFilterChain` matches `/jaxrs/**` and `/legacy/**`.
- Authentication/authorization applies to non-MVC endpoints as well.
- CSRF protection covers unsafe methods (`POST`/`PUT`/`DELETE`) when using cookies/sessions.
- CORS preflight `OPTIONS` executes at the proper filter order and path.
- Login/logout redirects and error pages do not hijack other namespaces.
- Never treat "403 Forbidden" as proof a controller or Jersey route is missing; a security filter may be blocking it earlier.

**Never set `permitAll("/**")` in production** just to "let all platforms run together." Define explicit authorization per namespace and write negative access tests.

## 8. Versioned API Paths Differ from Library Versions

### 8.1. Two Separate Concepts

- **Library version**: Spring Boot 3.5.x, Spring Framework 6.2.x, Jersey 3.x, Tomcat 10.1.x — determines classpath and runtime APIs.
- **API version**: `/api/v1/orders`, `/api/v2/orders`, `Accept` vendor media types, or version headers — determines the client contract.

Upgrading Spring Boot **does not change** `/api/v1` into `/api/v2`. Conversely, keeping URL `/api/v1` does not mean old libraries remain compatible with a Jakarta runtime.

### 8.2. Designing Consistent URL Versioning

Example partitioning per platform:

```text
/app/mvc/v1/products           Spring MVC v1
/app/mvc/v2/products           Spring MVC v2
/app/jaxrs/v1/report           Jersey JAX-RS legacy v1
/app/jaxrs/v2/report           Jersey JAX-RS v2
/app/legacy/health             Custom Servlet with unversioned public path
```

Never give two API versions the exact same path and HTTP method hoping "the newer version loads first." If using header or media-type versioning, configure resolvers/mappings carefully per your Spring Framework version and **test requests both with and without the version header**.

### 8.3. API Version Is Not Bean Version

One codebase can serve v1 and v2 from the same Java service using different DTOs. Never create two `@RestController` beans with identical mappings expecting bean names like `ProductsV1Controller`/`ProductsV2Controller` to differentiate URLs. When changing JSON contracts, maintain explicit DTOs/mappings and test backward compatibility.

### 8.4. Deprecation and Rollback

When migrating v1 to v2:

1. Identify active v1 clients and compatibility requirements.
2. Publish the new endpoint under an explicit namespace/version.
3. Maintain contract tests for both v1 and v2.
4. Ensure caches/CDNs and proxy routes distinguish versions.
5. Set a monitored migration deadline.
6. Never remove v1 before clients migrate per policy.
7. Document release notes and rollback steps in case framework/server upgrades alter routing behavior.

## 9. Reverse Proxies, Context Paths, and Effective Paths

An application might listen internally at:

```text
http://backend:8080/app/mvc/hello
```

while its public URL is:

```text
https://example.com/service/mvc/hello
```

Nginx/Ingress might strip `/service` and prepend `/app`, or pass paths through unchanged. **Reading `@GetMapping("/mvc/hello")` alone is never enough** to deduce the public URL.

### 9.1. Two Nginx `proxy_pass` Behaviors

Assume the backend expects `/app/mvc/hello`.

Configuration **preserving the URI**:

```nginx
location /app/ {
    proxy_pass http://127.0.0.1:8080;
}
```

A request to `/app/mvc/hello` is forwarded upstream with `/app/mvc/hello` intact.

Configuration **with a trailing URI slash**:

```nginx
location /app/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Nginx replaces the matched `/app/` prefix with `/`, so `/app/mvc/hello` arrives upstream as `/mvc/hello`; a backend expecting context `/app` returns **404**. Fix this at the proxy route/rewrite, not by adding `@CrossOrigin("*")` or changing the Java controller.

This is an **Nginx fragment**, not a complete production proxy config. Inside containers/Kubernetes, `127.0.0.1` inside Nginx points to the Nginx pod itself; point to the proper service DNS/network target instead.

### 9.2. Forwarded Headers

`Forwarded` or `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Prefix` describe the public origin when TLS termination or rewrites happen at the proxy. Spring Boot offers `server.forward-headers-strategy`, yet enabling it **does not repair a broken URI rewrite**.

Only trust forwarded headers from proxies under your control; Internet clients can spoof headers if the gateway fails to strip/overwrite them. Test redirect URLs, absolute links, cookies, and request origins behind the proxy.

### 9.3. Comparing Direct vs. Proxied Requests

```bash
curl -i http://localhost:8080/app/mvc/hello
curl -i https://example.com/service/mvc/hello
```

The second command uses an **illustrative placeholder URL**, not a live reachable host. When debugging, hit your real assigned domain/host and compare request ID, status, `Location`, and paths between proxy and backend rather than drawing conclusions from placeholder hostnames.

## 10. Complete Project: MVC, Jersey, and Custom Servlet in One Boot App

This project uses Spring Boot **3.5.16**, Java **17+**, and Maven to prove:

- Spring MVC keeps `/mvc/**` inside the default `DispatcherServlet`.
- Jersey/JAX-RS uses `@ApplicationPath("/jaxrs")`, without capturing `/*`.
- A legacy servlet is registered narrowly at `/legacy/*`.
- All three share **context path `/app`**.
- An integration test sends real HTTP requests and asserts the distinct body from each owner.

No database, Redis, Docker, frontend, token, or partner API is required. WebFlux starter is omitted since the demo makes no outbound `WebClient` calls; MVC + WebFlux rules were covered in Section 3.

### 10.1. Directory Structure

```text
multi-web-platform-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/multiweb/
    │   │   ├── MultiWebApplication.java
    │   │   ├── MvcHelloController.java
    │   │   ├── JerseyConfiguration.java
    │   │   ├── JerseyHelloResource.java
    │   │   └── LegacyServletConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/multiweb/
            └── MultiPlatformRoutingTest.java
```

Place all classes inside `com.example.multiweb` so `@SpringBootApplication` component scanning discovers them. Public classes must live in files matching their names; package-private helper classes can share a file.

### 10.2. Complete `pom.xml`

```xml
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
    <artifactId>multi-web-platform-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jersey</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

**Why is this POM properly scoped?**

- `spring-boot-starter-web` provides Spring MVC + embedded Tomcat.
- `spring-boot-starter-jersey` provides the Boot-managed Jersey runtime and JAX-RS integration.
- No manual version pins on `jersey-server`, `spring-webmvc`, `jakarta.ws.rs-api`, or `tomcat-embed-core`; everything comes from Boot's BOM.
- `starter-test` provides JUnit and HTTP integration testing tools.
- `java.version=17` aligns with Spring Boot 3.5's baseline.

Do not add `spring-boot-starter-webflux` just to collect "more platforms." Add integrations based on concrete requirements, not dependency counts.

### 10.3. Application Main

File `src/main/java/com/example/multiweb/MultiWebApplication.java`:

```java
package com.example.multiweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiWebApplication.class, args);
    }
}
```

The application boots the embedded Servlet container and registers components automatically. No manual `ServletContext` or `DispatcherServlet` setup is needed.

### 10.4. MVC Controller

File `src/main/java/com/example/multiweb/MvcHelloController.java`:

```java
package com.example.multiweb;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mvc")
public class MvcHelloController {

    @GetMapping(value = "/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "mvc-ok\n";
    }
}
```

`@RestController` is a Spring MVC component. With context path `/app` and default `DispatcherServlet` at root, the full path is **`/app/mvc/hello`**, returning `mvc-ok` with a trailing newline.

### 10.5. Jersey ResourceConfig and `@ApplicationPath`

File `src/main/java/com/example/multiweb/JerseyConfiguration.java`:

```java
package com.example.multiweb;

import jakarta.ws.rs.ApplicationPath;

import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/jaxrs")
public class JerseyConfiguration extends ResourceConfig {

    public JerseyConfiguration() {
        register(JerseyHelloResource.class);
    }
}
```

**Effect:** the Jersey servlet is confined to `/jaxrs/**`, preventing it from keeping default `/*` and eclipsing `/mvc/**`. Resource classes are registered **explicitly** so executable JARs work reliably instead of depending on `packages(...)` scanning.

### 10.6. Jersey Resource

File `src/main/java/com/example/multiweb/JerseyHelloResource.java`:

```java
package com.example.multiweb;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

import org.springframework.stereotype.Component;

@Component
@Path("/hello")
public class JerseyHelloResource {

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "jersey-ok\n";
    }
}
```

`@Path` and `@GET` are **JAX-RS annotations**, not Spring MVC `@GetMapping`. The class uses `@Component` for Spring lifecycle integration and is registered in `ResourceConfig.register(...)` for Jersey HTTP dispatch.

Combining context path `/app` + Jersey mapping `/jaxrs/*` + resource path `/hello`, the endpoint is **`/app/jaxrs/hello`**, returning `jersey-ok` + newline.

### 10.7. Narrowly Registered Custom Servlet

File `src/main/java/com/example/multiweb/LegacyServletConfiguration.java`:

```java
package com.example.multiweb;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyServletConfiguration {

    @Bean
    ServletRegistrationBean<LegacyHealthServlet>
    legacyHealthServletRegistration() {
        ServletRegistrationBean<LegacyHealthServlet> bean =
                new ServletRegistrationBean<>(
                        new LegacyHealthServlet(), "/legacy/*");
        bean.setName("legacyHealthServlet");
        return bean;
    }
}

class LegacyHealthServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        if (!"/health".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("legacy-ok\n");
    }
}
```

This is a **valid single Java file**: `LegacyServletConfiguration` is public matching the filename, and `LegacyHealthServlet` is package-private. Only `ServletRegistrationBean` is a Spring bean; **do not** add `@Component` onto `LegacyHealthServlet` or register a second Servlet bean that duplicates mappings.

`/legacy/*` routes `/app/legacy/health` to the custom servlet with `request.getPathInfo()` equal to `/health`. `/app/legacy/unknown` enters the servlet and receives a 404 from `doGet`.

### 10.8. Application Configuration

File `src/main/resources/application.properties`:

```properties
server.port=8080
server.servlet.context-path=/app
spring.application.name=multi-web-platform-demo

# Do not alter spring.mvc.servlet.path in this demo.
# Jersey mapping is defined via @ApplicationPath("/jaxrs").
```

**Intentional design:** `/app` is the **shared** Servlet context path, while `/mvc`, `/jaxrs`, and `/legacy` belong to distinct frameworks/Servlets. Leaving `DispatcherServlet`'s mapping untouched avoids `spring.mvc.servlet.path` compatibility issues with `PathPatternParser`.

### 10.9. Building and Running

From the folder containing `pom.xml`, with JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn clean package
java -jar target/multi-web-platform-demo-1.0.0.jar
```

Once the app starts (with port 8080 free), open a second terminal:

```bash
curl -i http://localhost:8080/app/mvc/hello
curl -i http://localhost:8080/app/jaxrs/hello
curl -i http://localhost:8080/app/legacy/health
```

All three return HTTP 200 when mappings are registered properly, with bodies:

```text
mvc-ok
```

```text
jersey-ok
```

```text
legacy-ok
```

Each body ends with a trailing newline. `curl -i` also prints HTTP headers, and status-line formatting can vary by environment; **the body value** is what stays fixed in the demo source.

Test negative URLs:

```bash
curl -i http://localhost:8080/app/mvc/missing
curl -i http://localhost:8080/app/jaxrs/missing
curl -i http://localhost:8080/app/legacy/missing
curl -i http://localhost:8080/app/hello
```

These should return HTTP 404 from their respective handlers/containers; error body formats differ across MVC, Jersey, and custom Servlets. Do not equate every 404 with "Spring MVC could not find a controller" — identify the **Servlet owner**.

Calling `http://localhost:8080/mvc/hello` **without `/app`** fails to match the demo's context path, so it will not reach the MVC endpoint.

### 10.10. Testing the Wrong HTTP Method

```bash
curl -i -X POST http://localhost:8080/app/mvc/hello
curl -i -X POST http://localhost:8080/app/jaxrs/hello
```

Both endpoints declare GET only. The result is normally HTTP 405 Method Not Allowed once the request reaches the handler; error bodies and `Allow` headers can differ between MVC and Jersey. If Spring Security/CSRF is present, POST can be blocked earlier with 401/403; debug the filter chain first before blaming controller mappings.

## 11. Real HTTP Integration Tests for Every Platform

File `src/test/java/com/example/multiweb/MultiPlatformRoutingTest.java`:

```java
package com.example.multiweb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MultiPlatformRoutingTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://localhost:" + port + "/app" + path;
    }

    @Test
    void mvcOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/mvc/hello"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("mvc-ok\n", response.getBody());
    }

    @Test
    void jerseyOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/jaxrs/hello"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("jersey-ok\n", response.getBody());
    }

    @Test
    void legacyServletOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/legacy/health"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("legacy-ok\n", response.getBody());
    }

    @Test
    void wrongPrefixIsNotAnAlias() {
        ResponseEntity<String> response =
                http.getForEntity(url("/hello"), String.class);
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }
}
```

Run:

```bash
mvn test
```

**Why write HTTP integration tests instead of only MockMvc?**

- `MockMvc` focuses on the Spring MVC `DispatcherServlet` pipeline; it **does not simulate** Servlet container dispatch to the Jersey servlet and custom servlets.
- `@SpringBootTest(RANDOM_PORT)` boots a real embedded server, testing Servlet registrations, context path, and Jersey auto-configuration.
- `TestRestTemplate` sends real HTTP requests to a random port, avoiding port 8080 conflicts.
- Asserting **each owner's distinct body** rather than just HTTP 200 catches fallback or route-shadowing bugs.
- A bug where `Jersey servlet /*` hijacks MVC routes is immediately caught by `mvcOwnsItsPath`.

These tests exercise the local example configuration without production proxies. To verify TLS, gateways, authentication, and rewrites, add smoke tests against the real deployed environment.

### 11.1. When IDE Tests Differ from Executable JAR Behavior

Jersey can have package-scanning limitations in executable archives. The demo calls `register(JerseyHelloResource.class)` explicitly to avoid classpath scanners. If code changes pass in the IDE yet fail under `java -jar`, compare classpath, packaging layout, and resource registration rather than blaming Java bytecode.

Inspect the packaged JAR:

```bash
jar tf target/multi-web-platform-demo-1.0.0.jar
```

Look for application classes under `BOOT-INF/classes/` and libraries under `BOOT-INF/lib/`. Gradle or WAR packaging uses different layouts; do not assume identical paths across all artifact types.

### 11.2. What Additional Tests Are Needed?

| Test | Purpose | Level |
| --- | --- | --- |
| `GET /app/mvc/hello` returns `mvc-ok` | Verify MVC mapping | HTTP integration |
| `GET /app/jaxrs/hello` returns `jersey-ok` | Verify Jersey resource registration | HTTP integration |
| `GET /app/legacy/health` returns `legacy-ok` | Verify `ServletRegistrationBean` | HTTP integration |
| Wrong URL `/app/hello` returns 404 | Verify no accidental alias | Negative integration |
| Disallowed POST calls | Verify method contracts | Negative integration |
| Unauthenticated `/jaxrs/private` | Verify security beyond MVC | Security integration |
| Versioned paths v1/v2 | Prevent route shadowing | Contract regression |
| CORS preflight per namespace | Verify filters/policy | Browser + HTTP |
| Static assets/WebJars URLs | Ensure not captured by Jersey/SPA | Resource integration |
| Reverse proxy public prefix | Verify URI rewrites/forwarded headers | Deployment smoke tests |

## 12. Inspecting Mappings When Multiple Systems Coexist

### 12.1. Spring MVC Mappings Do Not Represent All Servlets

You can inspect mappings from Spring MVC `RequestMappingHandlerMapping` or Actuator `/actuator/mappings` when enabled. However:

- MVC mappings list handlers **inside `DispatcherServlet`**, not JAX-RS resources as MVC annotations.
- Actuator mappings in a Servlet app can show servlet registrations, filter mappings, and dispatcher mappings depending on version and config.
- Jersey has its own resource registry, so check `ResourceConfig`, `@Path` annotations, and HTTP routes.
- Custom Servlets use `ServletRegistrationBean`, whose URL patterns are not `@GetMapping`.
- Proxy/Ingress routes live **outside Spring Boot** and never appear in MVC `HandlerMapping`.

**Do not just grep for `@GetMapping` to declare "no conflicts."** Build a layer-by-layer inventory.

### 12.2. Actuator Mappings (When Permitted)

For dev inspection, add the Actuator starter to the POM and expose endpoints carefully:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

```properties
management.endpoints.web.exposure.include=health,info,mappings
```

These are **optional fragments, omitted from the runnable demo POM/config**. Never expose `mappings` publicly in production if route, servlet, or filter details are sensitive. With a dedicated management port, URLs change too — do not assume Actuator lives under `/app`.

### 12.3. Filter Ordering Affects Outcomes

Spring Security, CORS filters, custom logging, tracing, request body wrappers, and URL rewrite filters can intercept requests **before** MVC, Jersey, or custom servlets run. At startup in dev, you can enable `web` group logging:

```properties
logging.level.web=debug
```

Boot 3.5 docs note this logging displays registered filter orders and URL patterns. Never turn on full debug logging in production where it might record secrets. For filters requiring explicit ordering, configure `FilterRegistrationBean#setOrder(...)` or implement `Ordered`/`@Order` on the proper registration.

## 13. Common Failures: Symptoms, Causes, and Fixes

| Symptom | Likely Cause | How to Verify/Fix |
| --- | --- | --- |
| MVC `@GetMapping` 404s after adding Jersey | Jersey servlet `/*` hijacks requests | `@ApplicationPath("/jaxrs")`, test MVC body |
| Jersey resource 404s in executable JAR | `packages(...)` scanner misses classes | Explicit `ResourceConfig.register(Resource.class)` |
| Both MVC and Jersey return 200 yet hit wrong handler | Overlapping path ownership or fallback | Assert distinct bodies and filter/servlet mappings |
| Boot picks MVC even after adding WebFlux starter | MVC takes precedence when both starters exist | Default behavior; choose runtime explicitly |
| WebFlux config has no effect | Runtime is Servlet MVC | Check web application type/logs; use `WebMvcConfigurer` |
| Servlet/JAX-RS compile errors with `javax.*` | Old Java EE mixed with Jakarta APIs | Upgrade to Boot 3.5–compatible `jakarta.*` libraries |
| `NoSuchMethodError` after upgrading one library | Version skew against BOM | Check dependency tree/effective POM; drop manual override |
| `ClassNotFoundException` on Jersey provider | Missing transitive dependency or mismatch | Inspect Jersey modules/package versions |
| Both Tomcat and Jetty in dependency tree | Missing starter exclusions | Pick one embedded server and fix dependencies |
| 404 only after adding `server.servlet.context-path` | Client/URL omitted context prefix | Request `/app/...` |
| 404 after setting `spring.mvc.servlet.path` | URL/matching strategy mismatch | Check `PathPatternParser` vs. Ant matcher |
| 404 only behind Nginx/Ingress | Proxy stripped `/app` or trailing slash in `proxy_pass` | Compare backend vs. public URI and proxy logs |
| POST 403 while GET 200 | Spring Security/CSRF/filter | Check security chain, CSRF token, filter order |
| `OPTIONS` preflight fails | CORS not handled before auth or blocked by proxy | Test `Origin` and `Access-Control-Request-*` |
| JSON response has wrong `Content-Type` | MVC converters vs. Jersey providers differ | Check `@Produces`/`produces` and content negotiation |
| Static assets 404 after adding Jersey | Jersey mapping/filter captures resource paths | Separate namespaces, test `/assets/**` |
| `/actuator/health` on different port | Dedicated management server configured | Inspect management port/base-path |
| MVC tests pass yet deployed app fails | MockMvc ignores container/Jersey/proxies | Add `RANDOM_PORT` integration and deploy smoke tests |
| JAR behaves differently from IDE | Different classpath/resources/scanning | Test executable JAR, `jar tf`, explicit registration |
| Security protects MVC yet leaves Jersey public | Matchers target only MVC paths | Write security rules covering all Servlet namespaces |
| v1/v2 endpoints collide | Unclear version mapping | Separate paths/headers and add tests |
| `@GetMapping` handler missing at runtime | Component scan missed its package | Check `@SpringBootApplication` base package |
| 200 HTML returned instead of API JSON | SPA fallback or proxy fallback | Check `Content-Type` and owner body |
| Major Boot upgrade breaks Undertow/starter | Supported server list changed | Read release/docs for the **exact target major** before upgrading |
| New GET API fails with 415/406 | Wrong `consumes`/`produces`/`Accept` | Inspect media types |
| Boot fails startup with ambiguous mappings | Two MVC mappings share identical conditions | Disambiguate path/method/params/headers |

## 14. Ordered Verification Process Without Guessing

When adding a new web platform to an existing Boot app, follow these checks in order:

1. **Identify the exact Spring Boot version** from the parent/BOM or Gradle plugin.
2. Run `java -version` to confirm the Java baseline; Boot 3.5 requires Java 17+.
3. Run `mvn dependency:tree` or Gradle `runtimeClasspath` to verify which of Spring MVC, WebFlux, Jersey, and embedded servers are present.
4. Hunt down manual dependency overrides, legacy `javax.*` jars, duplicate Jackson/Jersey providers, and duplicate server starters.
5. Verify the **web application type** Boot actually selects: MVC or reactive — never guess from controller names.
6. Write out the URL table: public prefix → context path → Servlet mapping → framework handler path.
7. Assign isolated namespaces such as `/mvc/**`, `/jaxrs/**`, `/legacy/**`, `/assets/**`.
8. For Jersey, verify `@ApplicationPath` and explicit `ResourceConfig.register(...)`.
9. For custom Servlets/Filters, verify `ServletRegistrationBean`, `FilterRegistrationBean`, URL patterns, and ordering.
10. Boot the app and test **every namespace** with `curl -i`; check body, status, and `Content-Type`, not just 200.
11. Run random-port HTTP integration tests covering negative URLs and disallowed HTTP methods.
12. Compare direct backend requests against public ingress/proxy requests whenever behavior differs.
13. Verify security/CORS/CSRF across Jersey and legacy areas, not MVC alone.
14. Test the packaged executable JAR, not just IDE runs.
15. Upgrade Spring Boot patches/BOM in a controlled way, re-running tests and SCA/CVE checks.
16. Document URL ownership maps and version contracts in architecture/release docs.

### Pre- and Post-Upgrade Verification Matrix

| Check Item | Before Upgrade | After Upgrade |
| --- | --- | --- |
| Boot/Framework/Jersey/Tomcat versions | Record runtime dependencies | No major-version skew |
| Selected web application type | MVC/Reactive confirmed | Unchanged unless intentional |
| Servlet mappings | `/`, `/jaxrs/*`, `/legacy/*` | No shadowing |
| Context path | `/app` | Public contract preserved |
| MVC GET route | `/app/mvc/hello` → MVC | Still MVC |
| Jersey GET route | `/app/jaxrs/hello` → Jersey | Still Jersey |
| Custom servlet | `/app/legacy/health` → Servlet | Still Servlet |
| Status 404/405/406/415 | Tested | Semantics preserved |
| Security filters/CORS/CSRF | Covered | No newly exposed namespaces |
| Front proxy/rewrites | Stable public URLs | Prefixes intact |
| Executable JAR packaging | Routes active | No lost Jersey resources |
| Response codecs/content types | Match contract | Unchanged unexpectedly |

## 15. Practice Exercises

### Exercise 1: Add WebClient While Keeping MVC

An MVC app using `spring-boot-starter-web` needs to call a partner with `WebClient`. You add `spring-boot-starter-webflux` and observe the context remains Servlet MVC.

**Explanation:** this is Spring Boot 3.5's default behavior. `WebClient` is a reactive HTTP client and does not require switching inbound routing to WebFlux. Keeping MVC when you only need the client is appropriate.

### Exercise 2: Jersey Captures API Routes

MVC had `GET /api/books`, which starts returning 404 after adding Jersey. Jersey's `ResourceConfig` lacks `@ApplicationPath`.

**Solution:** inspect Jersey's servlet registration for `/*`; restrict its mapping to `/jaxrs/*` via `@ApplicationPath("/jaxrs")`; re-run MVC and Jersey smoke tests. Never add random controllers just to work around 404s.

### Exercise 3: Setting Context Path and Forgetting the URL Change

You configure `server.servlet.context-path=/shop`. Controller `@GetMapping("/orders")` now responds only at `/shop/orders`.

**Explanation:** the context prefix precedes framework handler paths; this is not a Java annotation bug.

### Exercise 4: Library Errors Migrating from Boot 2 to Boot 3

A filter imports `javax.servlet.Filter` alongside Jersey 2.x.

**Solution:** upgrade all integrations to Jakarta-compatible versions using `jakarta.servlet.Filter` and compatible Jersey 3.x, verifying Maven dependency tree/BOM. Never try to bridge by adding both `javax` and `jakarta` APIs.

### Exercise 5: MVC Path Prefix Breaks Mappings

You set `spring.mvc.servlet.path=/api` in Boot 3.5 and several endpoints stop matching as before.

**Solution:** check `PathPatternParser` / `spring.mvc.pathmatch.matching-strategy`. If you truly need a servlet prefix, configure a Boot 3.5–supported strategy and add tests; if you only want route grouping, use `@RequestMapping("/api")` instead of moving `DispatcherServlet`.

### Exercise 6: Proxy Strips the Prefix

Nginx defines `location /app/` with `proxy_pass http://backend/;` while Boot uses context path `/app`.

**Solution:** `/app/` is replaced with `/` on forward; the backend receives `/mvc/hello` and returns 404. Fix the proxy rewrite or align the backend context path per contract — do not enable wildcard CORS.

### Exercise 7: Controller Tests Miss Jersey Mapping Bugs

All MockMvc unit tests pass, yet after deployment Jersey fails to register JAX-RS resources inside the executable JAR.

**Solution:** add `@SpringBootTest(RANDOM_PORT)` calling the Jersey endpoint and use explicit `ResourceConfig.register(Resource.class)`. `MockMvc` does not test the full Servlet container.

### Exercise 8: Security Filters Leave Legacy Servlet Unprotected

The app blocks `/mvc/admin`, yet `/legacy/admin` remains accessible without authentication.

**Solution:** review Servlet security filter chains and request matchers across all namespaces, adding negative HTTP tests. `MvcRequestMatcher` does not substitute for policies covering all Servlets.

### Exercise 9: Colliding API Versions

Two MVC controllers both annotate `@GetMapping("/products")`, with the developer expecting class names `ProductsV1Controller`/`ProductsV2Controller` to separate versions.

**Solution:** give them `/v1/products` and `/v2/products` or explicit supported version header conditions, plus contract tests. Class names have no effect on HTTP mapping.

### Exercise 10: Swapping Server Starters Causes Conflicts

A developer adds the Jetty starter without excluding Tomcat from `spring-boot-starter-web`.

**Solution:** follow Boot's exclusion/replacement pattern cleanly, verify the runtime dependency tree and actual running server, and never leave selection up to unpredictable classpath ordering.

## 16. Self-Assessment Questions

1. **Do MVC + WebFlux starters create two inbound HTTP dispatchers by default?** No. Boot 3.5 prioritizes MVC while still supporting `WebClient`.
2. **Which annotation marks a URL resource in Jersey JAX-RS?** `@Path` in `jakarta.ws.rs`, not MVC `@RequestMapping`.
3. **Why does Jersey need `@ApplicationPath` alongside MVC?** To stop the default `/*` Jersey servlet mapping from capturing MVC/static requests.
4. **What is `ServletRegistrationBean` used for?** Registering a custom Servlet with explicit URL patterns, name, and init params.
5. **Are `server.servlet.context-path` and `spring.mvc.servlet.path` the same?** No. Context path applies to the whole Servlet application; MVC servlet path applies only to `DispatcherServlet`.
6. **Does Spring MVC `@GetMapping("/hello")` know the public ingress path?** No; a proxy can rewrite prefixes.
7. **Why use the Spring Boot BOM?** It provides a curated, tested set of compatible library versions.
8. **Which Servlet namespace does Spring Boot 3.5 use?** `jakarta.servlet.*`, not legacy `javax.servlet.*`.
9. **Which REST namespace does Jersey 3.x use?** `jakarta.ws.rs.*`.
10. **Does a passing Maven compile prove routing is right?** No; run HTTP integration tests and executable JAR smoke tests.
11. **Why can't MockMvc replace HTTP integration tests for Jersey?** MockMvc primarily tests Spring MVC `DispatcherServlet`, not container servlet dispatch.
12. **Does every `404` mean a missing MVC controller?** No; Jersey, proxies, static handlers, filters, and custom servlets can all produce 404s.
13. **What is the risk of mapping a custom servlet to `/*`?** It can intercept requests meant for MVC or Jersey.
14. **Does `spring.mvc.static-path-pattern` change Jersey's mapping?** No, it belongs to MVC's static resource handler.
15. **What must you check when changing `spring.mvc.servlet.path` in Boot 3.5?** `PathPatternParser`/`AntPathMatcher` compatibility and test coverage.
16. **Does upgrading the Spring Boot library version change API URL v1 to v2?** No; API versioning is a separate contract.
17. **Does Actuator `mappings` list all ingress routes?** No; proxies sit outside Spring Boot.
18. **Why write negative tests for invalid URLs?** To ensure an SPA/Servlet fallback returning 200 does not mask a broken route.
19. **Can Spring Security filters intercept requests before MVC and Jersey?** Yes, when filter mappings and chains match properly.
20. **What is the ultimate QA bar?** Validated dependency versions, verified web runtime, clear Servlet owners, verified URL/proxy behavior, and passing contract/security tests.

## 17. Production Readiness Checklist

- [ ] Document exact Boot/JDK/Framework/server/Jersey versions and dependency tree.
- [ ] Follow the Boot BOM; avoid unmotivated overrides of transitive Spring/Jakarta dependencies.
- [ ] Never mix legacy `javax.*` jars with Jakarta-native Servlet/JAX-RS integrations.
- [ ] Choose one primary inbound web runtime (MVC or WebFlux) with clear justification.
- [ ] Distinguish HTTP clients from HTTP servers; never pull a server stack just from confusing `WebClient`.
- [ ] Assign distinct URL namespaces for MVC, Jersey, custom Servlets, static assets, and management.
- [ ] Restrict Jersey with `@ApplicationPath`; register resource classes explicitly.
- [ ] Register custom Servlets/Filters with reviewed URL patterns and ordering.
- [ ] Separate context path, servlet path, framework mapping, and proxy rewrite cleanly.
- [ ] Check `spring.mvc.servlet.path` constraints and matching strategy for your Boot version.
- [ ] Assert HTTP 200 with **owner-specific bodies**, negative 404/405 responses, `Content-Type`, and methods.
- [ ] Maintain HTTP integration tests and executable JAR smoke tests.
- [ ] Test CORS, authentication, authorization, and CSRF across every namespace.
- [ ] Verify static assets, WebJars, and SPA fallbacks do not capture API paths.
- [ ] Check Actuator management path/port and avoid exposing sensitive mappings publicly.
- [ ] Test both direct backend access and reverse proxy/ingress to verify path rewrites.
- [ ] Patch Boot/Jersey/Servlet containers cohesively while reviewing CVEs and release notes.
- [ ] Assign clear ownership for dependencies, URL routing, and API version contracts.
- [ ] Prepare rollback plans and regression tests whenever adding a platform, plugin, or starter.

## 18. Official Reference Documentation

- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC, Jersey, `@ApplicationPath`, Servlet/filter registrations, static resources, routing.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux and the behavior selecting MVC when both MVC + WebFlux are present.
- [Spring Boot 3.5 — Spring MVC How-to](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html): `spring.mvc.servlet.path`, `DispatcherServlet` configuration.
- [Spring Boot 3.5 — Build Systems](https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html): starter parent, Maven/Gradle, curated dependency versions/BOM.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Tomcat/Jetty/Undertow/Reactor Netty and version/platform requirements.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): testing web application types, `RANDOM_PORT`, `TestRestTemplate`.
- [Spring Framework 6.2 — Spring Web MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc.html): `DispatcherServlet` and `HandlerMappings`.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): URL/method/params/headers/consumes/produces mapping.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): servlet URL matching and filter pipeline.
- [Jakarta RESTful Web Services (JAX-RS)](https://jakarta.ee/specifications/restful-ws/): `@Path`, `@GET`, and `@ApplicationPath`.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): dependency tree.
- [Nginx ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_pass` URI replacement and upstream routing.

**Conclusion:** When extending Spring Boot with multiple web platforms, keep **BOM/Jakarta-aligned dependencies**, **the primary inbound runtime**, **Servlet/handler URL ownership**, and **API version contracts** cleanly separated. One application can host Spring MVC, Jersey, and custom Servlets without colliding as long as each has its own namespace, aligned dependencies, and HTTP integration tests running **against a real server**. Never sacrifice routing or security correctness by leaving `/*` wildcards open or ignoring version conflicts.