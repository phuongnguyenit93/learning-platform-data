# SpringBootServletInitializer and Servlet Applications in External Containers

## 1. Purpose and Context

Spring Boot can run under two different web runtime models:

- **Executable JAR/WAR packaging:** the `java -jar` command invokes `main()`, and Spring Boot creates an embedded Tomcat, Jetty, or Undertow server and manages the HTTP port itself.
- **Deploying a WAR into an external Servlet container:** an already-running Tomcat or application server receives a `.war` file, creates a `ServletContext` for the webapp, and then boots Spring Boot through the Servlet initialization lifecycle. In this mode, the external container **does not call the `main()` method**.

`SpringBootServletInitializer` is Spring Boot's support class for **traditional WAR deployment**. It bridges the `ServletContext` initialization lifecycle with `SpringApplication` to create the `WebApplicationContext`, `DispatcherServlet`, and registered Servlets/Filters in the application.

This lesson belongs to the **Application Deployment** topic of the **Spring Boot - web-runtime** module, using Java 17+, Spring Boot 3.5.16, Spring MVC, and Tomcat 10.1. The example allows the same source code to run both via `java -jar ...war` and deployed as `catalog.war` in an external Tomcat, comparing HTTP paths/headers/runtime behavior.

**An initializer class alone is not enough to turn a JAR into a WAR:** you need WAR packaging, appropriate dependency scopes, Jakarta Servlet compatibility, the right entrypoint, and testing on a real external server.

### Learning Outcomes

After this lesson, you can explain:

1. Why the Servlet container does not call `main()` and what calls `SpringBootServletInitializer.configure(...)`.
2. Why `spring-boot-starter-tomcat` requires `provided` in a Maven WAR and `providedRuntime` in Gradle.
3. The differences between `WEB-INF/lib`, `WEB-INF/lib-provided`, and an executable WAR.
4. Why the context path comes from the WAR name/container, and why `server.port` does not change the external Tomcat port.
5. How to register `ServletRegistrationBean` and `FilterRegistrationBean`, avoiding duplicates with `web.xml`/annotations.
6. Java/Jakarta Servlet versions, Spring Boot BOM, Spring MVC vs WebFlux, and vendor exceptions.
7. A testing strategy from JUnit/MockMvc to real embedded HTTP and **external WAR smoke tests**.
8. Security, TLS, sessions, secrets, classloaders, redeploy, and health checks when one JVM runs multiple WARs.

## 2. Three Artifact Types and Entrypoints

| Attribute | Executable JAR | Executable WAR via `java -jar` | WAR on external container |
| --- | --- | --- | --- |
| File | `.jar` | Spring Boot-repackaged `.war` | Deployable `.war` |
| Entrypoint | `main()` | `main()` | Servlet initializer `onStartup` |
| HTTP server | Boot creates embedded server | Boot creates embedded server | Pre-existing Tomcat/application server |
| Port | `server.port` | `server.port` | External connector (`server.xml`, platform) |
| Context path | `server.servlet.context-path` | Same as embedded JAR | Deployment context of the WAR |
| Server dependencies | Inside JAR | Boot launcher can use `lib-provided` | Container provides Servlet engine |
| Servlet API | Application runtime | Launcher/provided dependencies | Container's Jakarta Servlet |
| JVM | Usually one process per app | Usually one process per app | Multiple WARs may share one JVM |
| Startup failure | Process may fail | Process may fail | WAR fails while container keeps running |
| Testing needed | Functional + HTTP + E2E | Artifact/executable HTTP | **Container-specific WAR deployment** |

An executable WAR is useful when you need the same artifact to run both standalone and externally. With the Spring Boot build plugin and Tomcat marked `provided`, the embedded servlet container dependencies are placed in `WEB-INF/lib-provided`. When running `java -jar`, the Boot launcher loads them; when external Tomcat deploys the WAR, the webapp uses application libraries in `WEB-INF/lib` and the Servlet engine provided by the server.

**Do not conclude external deployment works solely because `java -jar` succeeded.** The launcher, classloader, and Servlet startup paths differ.

### When to Choose an Executable JAR

- Each service deploys as its own process/container image.
- The app owner wants to control the embedded server version, flags, and runtime.
- Simpler per-app blue/green, rolling updates, and rollbacks.
- No operational requirement for WAR or an existing Servlet application server.

### When Traditional WAR Fits

- A platform team centrally manages Tomcat/application servers.
- Operational or compliance processes only accept WARs.
- Need to integrate with legacy Servlet/JSP/JNDI or existing Java EE/Jakarta EE apps.
- Multiple webapps are deployed under shared container policies.

A WAR does not automatically provide strong security isolation: separate classloaders can still share the JVM heap, GC, process state, and server resources.

## 3. Where Does SpringBootServletInitializer Sit in the Servlet Lifecycle?

Exact class name in Spring Boot 3.5:

```java
org.springframework.boot.web.servlet.support.SpringBootServletInitializer
```

`SpringBootServletInitializer` implements `org.springframework.web.WebApplicationInitializer`. Spring Framework integrates with `ServletContainerInitializer` via `SpringServletContainerInitializer`. When a Servlet container handles WAR startup, it discovers and invokes matching `WebApplicationInitializer`s. The Boot initializer builds the `SpringApplication`/`WebApplicationContext` via `SpringApplicationBuilder`.

### Diagram of the Two Startup Paths

```text
EXECUTABLE MODE
java -jar target/servlet-war-demo-1.0.0.war
       |
       v
public static void main(String[] args)
       |
       v
SpringApplication.run(...)
       |
       v
Boot-managed embedded Tomcat
       |
       v
DispatcherServlet, Filters, application beans
       |
       v
http://localhost:8088/api/hello/Ada


EXTERNAL WAR MODE
Existing Tomcat -> deploy webapps/catalog.war
       |
       v
ServletContainerInitializer / SpringServletContainerInitializer
       |
       v
SpringBootServletInitializer.onStartup(ServletContext)
       |
       v
configure(SpringApplicationBuilder) -> SpringApplication
       |
       v
WebApplicationContext / Servlet registrations
       |
       v
http://localhost:8080/catalog/api/hello/Ada
```

This is a conceptual flow; the Servlet spec, container, and Spring coordinate the actual callback order. **`main()` does not run when an external container deploys a WAR in the standard way.**

### Minimal Java Template

```java
package com.example.wardeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class ServletWarApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ServletWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ServletWarApplication.class, args);
    }
}
```

The class above is valid Java, though running it requires the dependencies and `pom.xml` in section 9. Both entrypoints select the same `ServletWarApplication.class`.

**Do not do the following:** inside `configure`, call `SpringApplication.run(...)` and then return the builder. `configure` is responsible for **preparing** the builder while Boot manages startup timing; starting the app manually inside the callback can create duplicate contexts and Servlet registrations.

### Overriding `configure` Is Not Always Mandatory

Boot 3.5 JavaDoc notes you can either override `configure` or have the initializer itself act as the configuration source. The explicit `builder.sources(MyApplication.class)` form remains clearer, easier to inspect, and widely documented. If you need customizations shared by both modes, you can extract a common helper method:

```java
@SpringBootApplication
public class AlternateWarApp extends SpringBootServletInitializer {

    private static SpringApplicationBuilder customize(
            SpringApplicationBuilder b) {
        return b.sources(AlternateWarApp.class)
                .bannerMode(org.springframework.boot.Banner.Mode.OFF);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return customize(builder);
    }

    public static void main(String[] args) {
        customize(new SpringApplicationBuilder()).run(args);
    }
}
```

This is an **alternative snippet**—do not add it alongside the demo at the same time. For environment-specific settings (profiles, credentials, URLs), prefer externalized configuration and test each launch path; do not hardcode production secrets into classes.

## 4. Compatibility Requirements of Spring Boot 3.5.16

Spring Boot 3.5.16 requires **Java 17 or higher** and Spring Framework **6.2.19 or higher** per the official matrix. Supported embedded Servlet runtimes at the Servlet 6.0 generation include Tomcat 10.1, Jetty 12.0, and Undertow 2.3. The docs also note you can deploy a Boot WAR to a **Servlet 5.0+ compatible container**; however, vendor-specific configuration must still be verified.

| Factor | Requirement/choice |
| --- | --- |
| JDK for lab | Java 17 |
| Spring Boot | 3.5.16 via BOM/parent |
| Servlet namespace | `jakarta.servlet.*` |
| External lab container | Tomcat 10.1 / Jakarta Servlet 6.0 |
| Minimum Servlet per Boot 3.5 | Servlet 5.0+ compatible external container |
| Web runtime in lab | Spring MVC, Servlet |
| WAR startup | `SpringBootServletInitializer` |
| Platform testing | Must use the real target external server/version |

Correct namespace in Boot 3.5 code:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Legacy imports `javax.servlet.Filter` or `javax.servlet.http.HttpServlet` belong to older Java EE and cannot be used directly with Tomcat 10.1/Boot 3.5. **Tomcat 9 uses javax Servlet 4.0** and is not a compatible container for a Boot 3.5 WAR. When migrating from Boot 2 to Boot 3, upgrade all Servlet/JSP/JSTL/JAX-RS dependencies, Spring Security, and the server.

**Meeting the Servlet API version alone does not guarantee that all JSP, JNDI, WebSocket, logging, security realm, or classloader configurations are compatible.** Vendor documentation and smoke tests on the exact server are mandatory for complex applications.

### WebFlux Is Not the Default Use Case for This WAR

The Spring Boot 3.5 traditional deployment guide states that **Spring WebFlux servers do not support traditional WAR deployment**. An MVC WAR can use `WebClient` for outbound HTTP calls; that does not turn the inbound runtime into a WebFlux server. If you want a reactive server, choose an appropriate Reactor Netty deployment model rather than using the Servlet initializer as a universal workaround.

## 5. Maven WAR Packaging: Three Core Points

### (1) Set `<packaging>war</packaging>`

```xml
<packaging>war</packaging>
```

When omitted, Maven usually packages a JAR. A WAR has the layout expected by Servlet containers (`WEB-INF/classes`, `WEB-INF/lib`, and descriptors if needed).

### (2) Keep the Spring MVC Starter as an Application Dependency

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

External Tomcat provides the **Servlet engine**, not Spring MVC/Jackson/Boot application libraries. Do not mark all of `starter-web` as `provided`.

### (3) Mark the Tomcat Starter as Provided

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

This is the Maven configuration documented by Boot 3.5 for external WAR deployment. The Spring Boot Maven plugin supports repackaged executable WARs and keeps provided dependencies in `WEB-INF/lib-provided`, allowing the artifact to run via `java -jar` if `main()` is present.

Typical WAR layout:

```text
META-INF/
org/springframework/boot/loader/...       (Boot launcher)
WEB-INF/
  classes/
    application.properties
    com/example/wardeploy/...
  lib/
    spring-boot-...
    spring-webmvc-...
    jackson-...
  lib-provided/
    tomcat-embed-...
```

This is a **diagram**, not an exhaustive list of every JAR. Do not add embedded Tomcat in both `provided` and `compile` scopes with different versions.

Verify:

```bash
mvn clean package
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:*
jar tf target/servlet-war-demo-1.0.0.war
```

Confirm classes and libraries are in the right layers. If you hit `NoSuchMethodError`, `ClassCastException`, or `NoClassDefFoundError` at deploy time, check the BOM, dependency tree, container shared libs, and duplicate modules.

## 6. Gradle: war Plugin and providedRuntime

A Gradle Groovy DSL alternative to Maven:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

```bash
./gradlew clean test bootWar
```

This is a **standalone `build.gradle` fragment for dependency configuration**, used with a Gradle Wrapper compatible with Boot 3.5. `providedRuntime` is recommended over `compileOnly` because `compileOnly` does not provide runtime dependencies for web integration tests. For other projects, apply the organization's exact versions, plugins, and Java toolchain.

## 7. HTTP Paths: Who Owns the Port and Context?

### When Running the Executable WAR

For example, `application.properties` has:

```properties
server.port=8088
```

Run:

```bash
java -jar target/servlet-war-demo-1.0.0.war
```

Boot manages embedded Tomcat on **8088**. With no embedded context path set, the controller URL is:

```text
http://localhost:8088/api/hello/Ada
```

### When External Tomcat Deploys the WAR

External Tomcat has connector **8080**. If you copy the WAR as `catalog.war` into `webapps` and use deployment defaults, the application gets context path **`/catalog`**:

```text
http://localhost:8080/catalog/api/hello/Ada
```

`server.port=8088` inside the WAR **does not change the port** of external Tomcat. Here Tomcat owns the connector, socket, TLS, base thread pool, and deployed `ServletContext`.

`server.servlet.context-path` is useful for the **embedded Servlet container**, not for changing a context root already determined by external Tomcat. Deploying `ROOT.war` normally uses the root context by default. With a platform-specific context descriptor, the path can differ from the WAR filename.

### Observing Real Paths

```java
String contextPath = request.getContextPath();
String servletPath = request.getServletPath();
```

For `GET /api/where` in the project:

| Mode | `contextPath` | `servletPath` |
| --- | --- | --- |
| Embedded, root | `""` | `/api/where` |
| External `catalog.war` | `/catalog` | `/api/where` |

Filter/Servlet URL patterns are matched **relative to the `ServletContext`**. If a Filter needs to protect `/api/*`, do not prepend `/catalog` to the pattern, because the container has already resolved the context first.

### Behind a Reverse Proxy

```text
Browser: https://example.test/shop/api/hello/Ada
Proxy:   rewrite /shop -> /catalog
Tomcat:  http://tomcat.internal:8080/catalog/api/hello/Ada
MVC:     /api/hello/Ada
```

This is only an example. Proxies strip or retain prefixes differently; test directly against Tomcat and through the proxy, including cookie `Path`, redirect `Location`, scheme/host forwarding, and TLS.

## 8. Servlet, Filter, web.xml, and Initializer

A traditional Boot WAR **does not require `web.xml`** when using Java/Servlet initializers properly. Custom Servlets/Filters can be registered via:

- `@Bean Servlet` or `ServletRegistrationBean`
- `@Bean Filter` or `FilterRegistrationBean`
- `@ImportResource` if legacy Spring XML configuration must be kept
- `@SpringBootApplication` and Boot auto-configuration for MVC

Servlet snippet:

```java
@Bean
ServletRegistrationBean<LegacyPingServlet> legacy() {
    return new ServletRegistrationBean<>(
            new LegacyPingServlet(), "/legacy/*");
}
```

Filter snippet:

```java
@Bean
FilterRegistrationBean<RequestMarkerFilter> marker() {
    FilterRegistrationBean<RequestMarkerFilter> bean =
            new FilterRegistrationBean<>(
                    new RequestMarkerFilter());
    bean.addUrlPatterns("/api/*");
    return bean;
}
```

Both snippets rely on the demo classes in section 9. The container registers them into the webapp `ServletContext` without creating a second server.

**Do not double-register** the same class/name/mapping via `web.xml`, `@WebServlet`, `@WebFilter`, `@Component`, `@Bean`, and registration beans unless intentionally designed. Doing so can cause startup failures, double filter execution, or shadowed routes.

### Migrating Legacy Spring MVC

If an application has `AbstractDispatcherServletInitializer`, Spring XML, Servlet filters, and a context hierarchy:

1. Document the existing mappings and responsibilities in `web.xml`.
2. Create `@SpringBootApplication` in a root package that can scan controllers/services.
3. Add `SpringBootServletInitializer` with the proper source.
4. Move Servlets/Filters/Listeners incrementally to registration beans where appropriate.
5. Keep `@ImportResource` for XML not yet migrated, and check parent/child contexts.
6. Pay attention to Spring Security `DelegatingFilterProxy`, Session, CSRF/CORS, and JSP/view resolvers.
7. Remove duplicate registrations and run regression tests on the external container.

Do not delete vendor descriptors if the server still relies on JNDI, role mappings, or deployment metadata.

## 9. Complete Maven WAR Project

Lab goal: a Spring Boot MVC application with a business controller, service, Actuator, a Filter, and a non-MVC Servlet. The same WAR must run in embedded mode and on external Tomcat.

### 9.1. Structure

```text
servlet-war-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/wardeploy/
    │   │   ├── ServletWarApplication.java
    │   │   ├── GreetingService.java
    │   │   ├── GreetingController.java
    │   │   └── WebRuntimeConfiguration.java
    │   └── resources/application.properties
    └── test/java/com/example/wardeploy/
        ├── GreetingServiceTest.java
        ├── GreetingMvcSliceTest.java
        └── EmbeddedWarHttpTest.java
```

Endpoints:

- `GET /api/hello/{name}`: JSON greeting, handled by MVC.
- `GET /api/where`: returns actual context/servlet path.
- `GET /legacy/ping`: text from custom Servlet.
- `GET /actuator/health`: Actuator health.
- Filter sets header `X-Demo-Filter: active` on `/api/*`.

### 9.2. `pom.xml`

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
    <artifactId>servlet-war-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

No JSP, WebFlux, JPA, or database is needed for this example. `provided` Tomcat and the Spring Boot plugin produce a WAR capable of running in both modes.

### 9.3. `ServletWarApplication.java`

```java
package com.example.wardeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class ServletWarApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ServletWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ServletWarApplication.class, args);
    }
}
```

This class's sole responsibility is bootstrapping. External containers use `configure`; executable WAR mode uses `main`.

### 9.4. `GreetingService.java`

```java
package com.example.wardeploy;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public record Greeting(String message) {
    }

    public Greeting greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return new Greeting("Hello, " + name + "!");
    }
}
```

`Greeting` is a nested public Java record so Jackson can serialize it to JSON. Business logic does not depend on the Servlet container or HTTP port.

### 9.5. `GreetingController.java`

```java
package com.example.wardeploy;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
            value = "/hello/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingService.Greeting hello(
            @PathVariable String name) {
        return service.greet(name);
    }

    @GetMapping(
            value = "/where",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> where(
            HttpServletRequest request) {
        return Map.of(
                "contextPath", request.getContextPath(),
                "servletPath", request.getServletPath());
    }
}
```

`/api/where` shows where the app is actually mounted. Do not hardcode `/catalog` in the controller; the WAR context is chosen by the container.

### 9.6. `WebRuntimeConfiguration.java`

```java
package com.example.wardeploy;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class WebRuntimeConfiguration {

    @Bean
    ServletRegistrationBean<LegacyPingServlet>
    legacyServletRegistration() {
        ServletRegistrationBean<LegacyPingServlet> bean =
                new ServletRegistrationBean<>(
                        new LegacyPingServlet(), "/legacy/*");
        bean.setName("legacyPingServlet");
        return bean;
    }

    @Bean
    FilterRegistrationBean<RequestMarkerFilter>
    markerFilterRegistration() {
        FilterRegistrationBean<RequestMarkerFilter> bean =
                new FilterRegistrationBean<>(
                        new RequestMarkerFilter());
        bean.addUrlPatterns("/api/*");
        bean.setName("requestMarkerFilter");
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return bean;
    }
}

class LegacyPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(
                    HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("legacy-ok\n");
    }
}

class RequestMarkerFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        ((HttpServletResponse) response)
                .setHeader("X-Demo-Filter", "active");
        chain.doFilter(request, response);
    }
}
```

The file is valid because only `WebRuntimeConfiguration` is a public class. The other two classes are package-private. Do not add `@Component` or `@WebServlet` to them: `ServletRegistrationBean`/`FilterRegistrationBean` already own the registration.

A request `GET /catalog/legacy/ping` is routed by external Tomcat to Servlet mapping `/legacy/*`, after stripping context `/catalog`. Meanwhile the `/api/*` Filter applies to MVC API routes.

### 9.7. `application.properties`

```properties
spring.application.name=servlet-war-demo

# Only used for embedded Tomcat when running java -jar.
server.port=8088

# External Tomcat determines context path per deployment.
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
```

In production, do not use this artifact as a security template: the POM does not include Spring Security. Only expose Actuator health for verification; do not enable `env`/`beans`/`heapdump`/`shutdown`.

## 10. Java 17+ Test Suite

### 10.1. `GreetingServiceTest.java`

```java
package com.example.wardeploy;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service =
            new GreetingService();

    @Test
    void greetingIsCorrect() {
        assertEquals(
                new GreetingService.Greeting("Hello, Ada!"),
                service.greet("Ada"));
    }

    @Test
    void blankNameIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

Pure Java unit tests, requiring no Spring context or Tomcat.

### 10.2. `GreetingMvcSliceTest.java`

```java
package com.example.wardeploy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void mvcRoutesAndSerializes() throws Exception {
        given(service.greet("Ada")).willReturn(
                new GreetingService.Greeting("Hello, Ada!"));

        mvc.perform(get("/api/hello/Ada"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Ada!"));
    }
}
```

`@MockitoBean` uses the Spring Framework 6.2 namespace. `MockMvc` tests MVC handler mapping/JSON **without opening a socket**; it does not prove external WAR deployment.

### 10.3. `EmbeddedWarHttpTest.java`

```java
package com.example.wardeploy;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedWarHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void embeddedServerAndFilterWork() {
        assertTrue(port > 0);
        ResponseEntity<Map> response = http.getForEntity(
                url("/api/hello/Ada"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada!",
                response.getBody().get("message"));
        assertEquals("active",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void embeddedRootContextIsEmpty() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/api/where"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("",
                response.getBody().get("contextPath"));
        assertEquals("/api/where",
                response.getBody().get("servletPath"));
    }

    @Test
    void customServletIsRouted() {
        ResponseEntity<String> response = http.getForEntity(
                url("/legacy/ping"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("legacy-ok\n", response.getBody());
    }

    @Test
    void healthIsReachable() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/actuator/health"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP",
                response.getBody().get("status"));
    }
}
```

This is an **embedded** live HTTP test, not an external WAR test. Provided Tomcat libraries are on the test classpath, allowing `RANDOM_PORT` to work. You must run a separate external deployment smoke test.

### 10.4. Build Commands

```bash
java -version
mvn -version
mvn clean test
mvn clean package
```

`mvn package` runs tests per the default lifecycle and produces `target/servlet-war-demo-1.0.0.war`. If dependencies are not cached locally, Maven needs repository access. Do not assume fixed Surefire stdout because plugins/logging vary.

## 11. Try the Executable WAR First

```bash
java -jar target/servlet-war-demo-1.0.0.war
```

The app uses embedded Tomcat on port 8088 from properties. In another terminal:

```bash
curl -i http://127.0.0.1:8088/api/hello/Ada
curl -i http://127.0.0.1:8088/api/where
curl -i http://127.0.0.1:8088/legacy/ping
curl -i http://127.0.0.1:8088/actuator/health
```

Expected when healthy:

- `/api/hello/Ada`: HTTP 200, `X-Demo-Filter: active`, body `{"message":"Hello, Ada!"}`.
- `/api/where`: HTTP 200, JSON:

```json
{"contextPath":"","servletPath":"/api/where"}
```

- `/legacy/ping`: HTTP 200, text `legacy-ok` **with trailing newline**.
- `/actuator/health`: HTTP 200 and `{"status":"UP"}` when health contributors are UP.

This is executable mode. It proves the WAR can start embedded Tomcat via the Boot launcher, **not** Servlet startup on external Tomcat.

## 12. Deploying to External Tomcat 10.1

### 12.1. Rename Artifact for the Context

```bash
cp target/servlet-war-demo-1.0.0.war target/catalog.war
```

PowerShell:

```powershell
Copy-Item target/servlet-war-demo-1.0.0.war target/catalog.war
```

Under Tomcat defaults, `catalog.war` deploys at context path `/catalog`. `ROOT.war` usually uses the root context. Custom Context descriptors or platform config can override this.

### 12.2. Tomcat 10.1 on Docker for Local Lab

```bash
docker run --rm -d \
  --name war-demo-tomcat \
  -p 127.0.0.1:8080:8080 \
  tomcat:10.1-jdk17-temurin

docker cp target/catalog.war \
  war-demo-tomcat:/usr/local/tomcat/webapps/catalog.war

docker logs war-demo-tomcat --tail=80
```

PowerShell one-liner:

```powershell
docker run --rm -d --name war-demo-tomcat -p 127.0.0.1:8080:8080 tomcat:10.1-jdk17-temurin
docker cp target/catalog.war war-demo-tomcat:/usr/local/tomcat/webapps/catalog.war
docker logs war-demo-tomcat --tail=80
```

Bind the demo port only to host loopback. The image tag is illustrative; production should pin digests, scan for CVEs, and apply patches. Wait for Tomcat logs to report successful WAR deployment before sending requests.

### 12.3. Verify the WAR at the Correct Context

```bash
curl -i http://127.0.0.1:8080/catalog/api/hello/Ada
curl -i http://127.0.0.1:8080/catalog/api/where
curl -i http://127.0.0.1:8080/catalog/legacy/ping
curl -i http://127.0.0.1:8080/catalog/actuator/health
```

| External URL | HTTP when healthy | Expected content |
| --- | --- | --- |
| `/catalog/api/hello/Ada` | 200 | `{"message":"Hello, Ada!"}`, filter header |
| `/catalog/api/where` | 200 | Context `/catalog`, Servlet path `/api/where` |
| `/catalog/legacy/ping` | 200 | `legacy-ok` + newline |
| `/catalog/actuator/health` | 200 | `{"status":"UP"}` |
| `/api/hello/Ada` (missing context) | Usually 404 | Not a route of the catalog WAR |

Detailed JSON of external `/catalog/api/where`:

```json
{"contextPath":"/catalog","servletPath":"/api/where"}
```

This is the core difference from an embedded WAR. A URL without `/catalog` hits a different Tomcat path. If Tomcat has a ROOT webapp, it may return its own content; do not infer from an arbitrary 200 that the catalog route works.

### 12.4. Stop the Lab

```bash
docker stop war-demo-tomcat
```

Because `--rm` was used, the container is removed when stopped. **Do not stop a shared organizational external Tomcat** just to finish a lab.

## 13. Security and Operations for External WARs

### 13.1. HTTP/TLS Connectors

In embedded mode, Boot manages `server.port`, `server.ssl.*`, and embedded Tomcat. In external mode, the Tomcat platform owns HTTP connectors, TLS certificates, and listener settings; WAR application properties **do not automatically change external connectors**.

Review certificate trust/renewal, HTTPS redirects, `Forwarded`/`X-Forwarded-*` headers, request sizes/timeouts, compression, WebSocket, HTTP/2, Tomcat valves, and ingress rewrites.

### 13.2. Cookies/Session

Multiple WARs on the same hostname can issue `JSESSIONID` cookies, with `Path` typically scoped to the Servlet context. Check:

- Whether `/catalog` path works for login/redirects.
- `Secure` when behind an HTTPS reverse proxy.
- `HttpOnly`, `SameSite`, session timeout, and cookie domain.
- Session persistence during redeploy or multi-node load balancing.
- Spring Session namespace/Redis if intentionally sharing state.

Do not assume WARs sharing a JVM automatically share HTTP sessions or user authentication.

### 13.3. SecurityFilterChain and Actuator

The application has Spring Security and the container may also apply its own realms/constraints. Filter order, CORS, CSRF, and authorization must be verified through the actual URL. Actuator health sits under `/catalog/actuator/health` in the example; do not publicly expose `env`, `beans`, `heapdump`, `loggers`, or `shutdown`.

If you need a management listener on a different port, determine **which platform owns the connector** and how security/network policies apply. Do not assume standalone Boot `management.server.*` settings will open a new port on a shared external Tomcat the same way as in executable mode.

### 13.4. Secrets and Shared JVM

In a Tomcat running multiple WARs, process-level system properties and OS environment variables can apply to **every WAR**. Do not set global `SPRING_PROFILES_ACTIVE`, credentials, JNDI, or secret paths that other webapps might misuse. Prefer platform-approved per-app configuration, secret managers, file ACLs, and auditing.

### 13.5. Classloader, Memory, and Redeploy

Each webapp has its own `ServletContext`/classloader but shares the JVM heap/GC/system resources. When multiple WARs run together:

- Combined Hikari `maximumPoolSize` values can exceed DB connection limits.
- Long-lived Threads, `ThreadLocal`, and custom executors can pin old classloaders after undeploy.
- JDBC drivers, schedulers, file watchers, HTTP clients, and logging appenders need proper shutdown.
- Memory leaks in one WAR affect other WARs.
- Server restarts have a wider blast radius than restarting a single app process.

Use bean lifecycle hooks (`@PreDestroy`, `DisposableBean`) and monitor heap/metaspace/thread counts across multiple redeploys. Do not treat WAR webapp classloaders as process-level security isolation.

## 14. Testing Strategy Matching the Three Boundaries

| Test type | Question answered | What it does not prove |
| --- | --- | --- |
| JUnit unit | Is Java service logic right? | MVC/Servlet routing |
| `@WebMvcTest` + MockMvc | Are handler mappings/JSON right? | Real socket/container |
| `@SpringBootTest(RANDOM_PORT)` | Does embedded servlet HTTP work? | External WAR classloader/startup |
| `java -jar ...war` smoke | Does the repackaged executable WAR work? | External Tomcat deployment |
| Deploy WAR to Tomcat 10.1 + curl | Do external initializer/context/routing work? | Real ingress/TLS if unused |
| Staging proxy test | Are public route, cert, forwarded headers right? | Capacity without load testing |
| Repeated redeploy/soak | Are there long-term leaks/session issues? | Every production failure mode |

**A real external smoke test is essential.** Simply changing `@SpringBootTest` to `RANDOM_PORT` still tests embedded Tomcat. If the external container fails to deploy the WAR, Tomcat's HTTP server can still open port 8080 and serve another app; health checks must target `/catalog/actuator/health`.

Recommended negative checks: URL without `/catalog`, `/catalog/legacy/missing`, disallowed POST methods, filters/security not overly permissive, HTTPS/cookie behavior behind proxy, and corresponding startup failure logs.

## 15. Common Error Analysis

| Symptom | Possible cause | How to verify and fix |
| --- | --- | --- |
| Executable WAR runs, external 404 | Missing initializer or wrong context path | Check `SpringBootServletInitializer`, deploy logs |
| Tomcat port 8080 open but WAR fails | Container hosts multiple webapps | Check exact `/catalog/actuator/health` |
| Boot controller 404 | Wrong component scan root | Place `@SpringBootApplication` in common root package |
| `javax.servlet.*` ClassNotFound | Legacy Servlet API | Migrate to `jakarta.*` |
| `jakarta.servlet.*` NoClassDefFound | Container Servlet generation too old | Tomcat 10.1/Servlet 5+ |
| Boot 3.5 WAR on Tomcat 9 | Incompatible namespace/generation | Upgrade Servlet container |
| `NoSuchMethodError` | Spring/Tomcat/Jackson version mismatch | Boot BOM, dependency tree, shared server libs |
| Build outputs a JAR | Missing `<packaging>war</packaging>` | Fix Maven packaging |
| Executable WAR fails to run | Wrong plugin repackage/main class | Check Boot Maven plugin |
| Embedded Tomcat jars in `WEB-INF/lib` | Wrong `provided` scope | Use `spring-boot-starter-tomcat` `provided` |
| `server.port=8088` but external still 8080 | Container owns connector | Edit Tomcat/server config |
| `/api/...` 404, `/catalog/api/...` 200 | Missing context path | Compute URL from WAR deployment |
| Filter does not run | Registered `/catalog/api/*` instead of `/api/*` | Use `ServletContext`-relative pattern |
| Duplicate Servlet on startup | Duplicate XML/annotations/Bean registrations | Pick a single registration mechanism |
| Boot 2→3 JSP/JSTL fails | Incomplete Jakarta migration | Upgrade APIs/libs matching container |
| Local health passes, public proxy 404 | Wrong rewrite/forwarded path | Test both direct and via proxy |
| Redeploy increases heap/metaspace | Classloader/thread/resource leak | Shutdown hooks, heap/thread dumps |
| Spring Security 403 | Auth/CSRF/filter/realm differs at runtime | Inspect chain and headers, do not blindly disable |
| Secret/profile leaks to wrong WAR | Shared OS process vars | Per-webapp config |
| WebFlux server WAR deploy fails | Traditional WAR WebFlux server not supported | Choose reactive deployment |
| Different Servlet container vendor | Different vendor classloading/startup | Test exact version/vendor |

### A Notable Exception: WebLogic

The Boot 3.5 traditional deployment guide requires the initializer for **WebLogic** to implement `WebApplicationInitializer` **directly**, even though its superclass `SpringBootServletInitializer` already implements it. Vendor-specific snippet:

```java
@SpringBootApplication
public class WebLogicWarApp extends SpringBootServletInitializer
        implements org.springframework.web.WebApplicationInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(WebLogicWarApp.class);
    }
}
```

This snippet needs imports and vendor-specific dependencies/config; **do not** add it alongside the demo main class. WebLogic may require `WEB-INF/weblogic.xml` configuring package preferences (e.g. `org.slf4j`); verify version compatibility and official docs before deploying.

## 16. Hands-On Exercises

**A. Remove the initializer.** Remove `extends SpringBootServletInitializer` while keeping `main`. Predict: embedded executable still runs, external WAR does not bootstrap as before. Restore after testing.

**B. Do not rename the WAR.** Deploy `servlet-war-demo-1.0.0.war` under its original name and call `/catalog/...`: likely 404. Under Tomcat naming conventions, the default path follows the WAR name; adjust the URL to the actual context.

**C. Change `server.servlet.context-path`.** Set `/embedded` and compare running `java -jar` with external `catalog.war`. Embedded routes get `/embedded` prefix, while external remains controlled by the container.

**D. Remove `provided` scope.** Compare `jar tf` before/after; find Tomcat JARs pulled into normal WAR dependencies. Restore `provided`.

**E. Change Servlet mapping.** `/legacy/*` → `/compat/*`; MVC slice tests may still pass, while embedded/external HTTP `/legacy/ping` fails.

**F. Wrong Filter mapping.** Use `/catalog/api/*` instead of `/api/*`; the Filter fails to match as expected under context `/catalog`. Fix back to the `ServletContext`-relative mapping.

**G. Add a second WAR.** Run `/catalog` and `/orders` on the same Tomcat. Assess combined JDBC pools, heap, log paths, and rollout blast radius.

**H. Proxy rewrite.** Map public `/shop` to upstream `/catalog`. Check redirects, sessions, `Location`, HTTPS, and actual HTTP responses.

**I. WAR startup fails, Tomcat stays alive.** Omit a required property and inspect logs and `/catalog/actuator/health`; why is `curl localhost:8080` not a deployment health check?

**J. Compare Gradle/Maven.** Build `bootWar` with `providedRuntime`, inspect `lib-provided` and runtime behavior compared to Maven WAR. Do not mix dependencies from different BOM generations.

## 17. Self-Assessment Questions

1. What is `SpringBootServletInitializer` used for? — Bootstrapping a Boot web app from an external Servlet container.
2. Does external Tomcat run `main()`? — No.
3. What does `configure` return? — `SpringApplicationBuilder` with sources/customizations added.
4. Does a WAR only need renaming the extension from `.jar`? — No.
5. What does Maven packaging need? — `<packaging>war</packaging>`.
6. What scope for the Tomcat starter? — `provided`.
7. What is the Gradle equivalent? — `war` and `providedRuntime`.
8. Why does `WEB-INF/lib-provided` exist? — So Boot's executable WAR can still use provided libraries.
9. What is Boot 3.5's Java baseline? — 17+.
10. Which external Tomcat is suitable? — Tomcat 10.1/Jakarta Servlet.
11. Is Tomcat 9 suitable for a Boot 3.5 WAR? — No, due to Servlet namespace/generation.
12. Does `server.port` change the external connector? — No.
13. Where does the `/catalog` context come from? — WAR deployment/context configuration.
14. Does a Filter pattern need `/catalog`? — No.
15. Is `web.xml` required? — No, in a typical Java initializer setup.
16. Should you double-register a Servlet? — No.
17. Does `@SpringBootTest(RANDOM_PORT)` test external Tomcat? — No, it tests embedded.
18. What should you smoke test? — Proper context/health/business/Servlet/filter endpoints.
19. Do WARs sharing a JVM have process-level isolation? — No.
20. Can a WebFlux server be deployed as a traditional WAR? — Not supported per the Boot 3.5 guide.

## 18. Production Checklist

- [ ] Main class extends `SpringBootServletInitializer`, with clear sources/package scan.
- [ ] `configure` does not start the app twice; `main()` supports executable mode when needed.
- [ ] Maven WAR/Boot plugin or Gradle `war`/`bootWar` versions match.
- [ ] Tomcat is `provided`/`providedRuntime` with no duplicate servlet engine JARs.
- [ ] Java/Jakarta/Servlet/Spring/Server versions are compatible, with no legacy `javax` remaining.
- [ ] Inspected WAR `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`.
- [ ] WAR name/context path, public ingress path, and Tomcat connector are clearly documented.
- [ ] Servlet/Filter registrations do not duplicate `web.xml`/annotations.
- [ ] Actuator health matches the WAR context, and sensitive endpoints are not public.
- [ ] TLS/mTLS, security chain, CORS/CSRF, session cookie flags, and proxy config are tested.
- [ ] Secrets/profiles are scoped per app, not leaked through shared JVM config.
- [ ] Combined DB pools, threads, and heap/GC of all WARs fit within the capacity budget.
- [ ] Unit, MVC slice, embedded HTTP, executable WAR, and **external WAR smoke** tests all run for their respective targets.
- [ ] Backup/rollback, traffic draining, redeploy, and classloader leak checks are in place.
- [ ] An open Tomcat port is not treated as proof of successful WAR deployment.
- [ ] Track server patch versions, CVEs, deployment logs, and startup failure alerts.

## 19. Official References

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer`, WAR packaging, `provided` Tomcat, and WebLogic.
- [Spring Boot 3.5 — SpringBootServletInitializer JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): `WebApplicationInitializer` interface, `configure`, and lifecycle.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Spring Framework/Servlet compatibility.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.port` and embedded runtime.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC, Servlet/Filter registration.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc/RANDOM_PORT/TestRestTemplate.
- [Spring Boot 3.5 — Actuator Monitoring](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html): health URL/exposure.
- [Spring Framework — WebApplicationInitializer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/WebApplicationInitializer.html): Servlet startup integration.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): `ServletContext`, filters, and URL matching.
- [Apache Tomcat 10.1 — Deployer HOW-TO](https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html): WAR deployment/context behavior.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): Maven WAR packaging.
- [Spring Boot Gradle Plugin 3.5 — Packaging](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html): `bootWar`/`providedRuntime`.

**Conclusion:** `SpringBootServletInitializer` enables an **external Servlet container** to boot a Spring Boot WAR via the Servlet lifecycle, while `main()` is for executable mode. A proper WAR requires the right packaging, provided dependencies, a Jakarta-compatible container, verified Servlet/Filter registrations, and the right URL context. Build and inspect the WAR, run tests, and then **deploy and send real HTTP traffic through the actual external container** before declaring production readiness.