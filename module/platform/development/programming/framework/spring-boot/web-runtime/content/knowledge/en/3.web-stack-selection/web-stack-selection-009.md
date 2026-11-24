# Relationship Between Web Stacks and Supported Servers by Spring Boot Version

## 1. Purpose and scope

In Spring Boot, choosing a **web stack** and choosing an **HTTP server** are two related yet distinct decisions. The web stack determines the request-processing model, APIs, and programming style; the HTTP server accepts network connections and provides the runtime environment. Meanwhile, the list of servers officially configured, tested, and supported by Spring Boot **depends on the Spring Boot version**.

This lesson focuses on Spring MVC (Servlet) and Spring WebFlux (reactive), Tomcat, Jetty, Undertow, Reactor Netty, starter dependencies, the Servlet API, and changes when upgrading from Spring Boot 2.7 through 3.x to 4.x. The tables represent **compatibility matrices published by Spring Boot for specific version milestones**, not a guarantee that any arbitrary version of a server works with any Boot release.

## 2. Three layers to distinguish

1. **Web stack:** Spring MVC uses the Servlet model; Spring WebFlux is built on reactive APIs such as Mono, Flux, and asynchronous HTTP adapters. This is a choice of application development model.
2. **Embedded server:** Tomcat, Jetty, Undertow, or Reactor Netty is the HTTP runtime bundled with the application when running as an executable jar. The server handles sockets, TLS, and HTTP, forwarding data to the framework.
3. **Spring Boot version:** defines starters, auto-configuration, factories/adapters, dependency versions managed by the BOM, and the set of servers supported/tested at that point in time.

Server–stack pairings can vary:

| Server | Is a Servlet container? | Can run MVC in a Boot-supported way? | Can act as a WebFlux server? |
|---|---|---|---|
| Tomcat | Yes | Yes | Yes, via reactive adapter |
| Jetty | Yes | Yes | Yes, via reactive adapter |
| Undertow | Yes | Yes in Boot 2.7–3.5 | Yes in Boot 2.7–3.5 |
| Reactor Netty | No | Not a Servlet server for Spring MVC | Yes; default choice for WebFlux |

**Important:** every "Yes" in this table must always be read together with a specific Boot version; starting from Boot 4.x, Undertow is no longer listed among the embedded servers officially supported by Spring Boot. Spring WebFlux running on Tomcat/Jetty does not turn into Spring MVC. Reactor Netty is a reactive HTTP server, while Netty can also appear in HTTP client dependencies; having Netty on the classpath does not by itself prove Netty is accepting incoming requests.

By default, Spring MVC pairs with Tomcat, and WebFlux pairs with Reactor Netty. If both MVC and WebFlux dependencies are present, Spring Boot typically chooses a Servlet/MVC application type under its automatic web application type deduction rules. Many MVC projects intentionally use WebClient to call external services while keeping MVC as the web stack. To truly deploy WebFlux, check the application type and active starters rather than inferring from Mono/Flux in a controller.

## 3. Servlet server support matrix by version

The table below is based on the **System Requirements / Servlet Containers** section of the official documentation for each version, showing the server lines supported by Spring Boot **at the release milestone listed in the first column**.

| Spring Boot | Minimum Java | Tomcat | Jetty | Undertow | Corresponding Servlet API level |
|---|---:|---|---|---|---|
| 2.7.18 | 8 | 9.0 | 9.4 or 10.0 | 2.0 | Tomcat 4.0; Jetty 9.4: 3.1, Jetty 10: 4.0; Undertow 4.0 |
| 3.0.13 | 17 | 10.1 | 11.0 | 2.3 | Tomcat 6.0; Jetty 5.0; Undertow 6.0 |
| 3.1.12 | 17 | 10.1 | 11.0 | 2.3 | Tomcat 6.0; Jetty 5.0; Undertow 6.0 |
| 3.2.10 | 17 | 10.1 | 12.0 | 2.3 | Servlet 6.0 for all three options |
| 3.3.x–3.5.x (e.g., 3.5.16) | 17 | 10.1 | 12.0 | 2.3 | Servlet 6.0 for all three options |
| 4.0.x–4.1.x (e.g., 4.1.2) | 17 | 11.0.x | 12.1.x | Not listed as supported | Servlet 6.1 for Tomcat and Jetty |

Notes when reading the matrix:

- **2.7.x:** Boot uses Spring Framework 5 and the Servlet API in the javax.servlet namespace. Jetty 9.4 only supports Servlet 3.1 while Jetty 10 supports Servlet 4.0; thus a single Boot release can span multiple Servlet API levels depending on container.
- **3.0–3.1:** Boot moves to Spring Framework 6 and the jakarta.servlet namespace. Even though Tomcat 10.1 and Undertow 2.3 are on Servlet 6.0, Jetty 11 is only on Servlet 5.0. Do not equate "Boot 3" with "every container is Servlet 6."
- **3.2–3.5:** Jetty moves to the 12.0 line and supports Servlet 6.0 in Boot-supported configurations.
- **4.0–4.1:** Boot uses Spring Framework 7, Servlet API 6.1, and only lists Tomcat 11.0.x and Jetty 12.1.x as embedded Servlet containers. Undertow 2.3 from Boot 3.x is not a default upgrade option to Boot 4.
- **Patch details can change:** the Boot BOM pins specific dependency versions for bug and security fixes. "Tomcat 10.1" is a **version branch**, not a fixed pointer to one patch. To know the exact patch version, inspect the dependency tree or runtime.
- **3.0.0 differs from 3.0.13:** very early releases in the 3.0 line had different container combinations; when exact details matter, consult the documentation for the **exact version** you operate. Do not rely on one table for the entire history of a major line if patches introduced changes.

"Supported embedded server" does not mean "deploy a WAR onto any server of the same name." External WAR deployment also depends on Servlet API level, javax/jakarta packages, Java runtime, classpath, and version-specific Boot compatibility guidance. For instance, Boot 4 requires considering Servlet 6.1, whereas Boot 2.7 uses javax.servlet; you cannot simply drop an old WAR onto Tomcat 11.

## 4. WebFlux server matrix by version

WebFlux is **not required** to run on Reactor Netty. Spring Boot provides adapters to run WebFlux over other supported servers depending on the version.

| Spring Boot line | WebFlux default | Embedded WebFlux servers supported by Boot |
|---|---|---|
| 2.7.x | Reactor Netty | Reactor Netty, Tomcat, Jetty, Undertow |
| 3.0.x–3.5.x | Reactor Netty | Reactor Netty, Tomcat, Jetty, Undertow |
| 4.0.x–4.1.x | Reactor Netty | Reactor Netty, Tomcat, Jetty |

Read both tables together: **Servlet container version** only describes Tomcat/Jetty/Undertow in a Servlet environment; Reactor Netty itself does not implement the Servlet API and therefore has no row in the Servlet containers table of the System Requirements documentation.

In Boot 4.x, the Servlet stack supports Tomcat or Jetty, and WebFlux can use Reactor Netty or Tomcat/Jetty. The difference between Servlet and reactive lies in the processing pipeline, backpressure, and programming model; you cannot judge which model is "faster" from the web server name alone. When using JDBC or blocking libraries in a reactive flow, you must properly handle blocking characteristics regardless of whether the server supports reactive.

## 5. Relationship with starter dependencies and auto-configuration

Spring Boot provides starters to select stacks and servers without manually assembling dozens of libraries.

| Boot version | Starter for Spring MVC | Starter for WebFlux | Default server |
|---|---|---|---|
| 2.7.x–3.5.x | spring-boot-starter-web | spring-boot-starter-webflux | MVC: Tomcat; WebFlux: Reactor Netty |
| 4.0.x–4.1.x | spring-boot-starter-webmvc (recommended) | spring-boot-starter-webflux | MVC: Tomcat; WebFlux: Reactor Netty |

In Boot 4.x, the older **spring-boot-starter-web** starter still exists but is marked deprecated, with **spring-boot-starter-webmvc** preferred for new projects. Therefore, a Maven example using starter-web for Boot 3.5 should not be copied mechanically to Boot 4.1 when a clearer new starter is available.

Typical configuration flow:

~~~text
Maven/Gradle dependencies
    -> Spring Boot auto-configuration and BOM
        -> choose web application type: SERVLET or REACTIVE
            -> create WebServerFactory matching the chosen server
                -> create and start embedded HTTP server
                    -> MVC DispatcherServlet or WebFlux HTTP handler
~~~

With Spring MVC, Spring Boot creates ServletWebServerApplicationContext and the appropriate ServletWebServerFactory. With WebFlux, Spring Boot uses ReactiveWebServerApplicationContext and the matching ReactiveWebServerFactory. Seeing Netty or Tomcat classes in a project's dependency tree is not enough to conclude which server is created: examine dependencies, auto-configurations, application type, and actual logs/runtime.

When swapping servers, you must **exclude the default server from the starter dependency** and add the matching new starter. Merely adding Jetty alongside Tomcat can leave multiple server factories on the classpath, causing unpredictable behavior or startup failures.

## 6. Illustrative configuration: Spring MVC on Spring Boot 3.5

Suppose a Maven project already uses Spring Boot 3.5.x via parent/BOM. To run MVC on **Jetty 12.0** instead of Tomcat, the dependencies section can be written as follows:

~~~xml
<dependencies>
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
</dependencies>
~~~

The Spring Boot BOM picks the compatible Jetty version, so you do not need to fill in a Jetty version manually. Switching to Undertow in Boot 3.5 simply means replacing the Jetty dependency in the example with **spring-boot-starter-undertow** (while still excluding Tomcat); verify the Undertow version managed by the BOM.

In Gradle Groovy DSL for Boot 3.5, the equivalent pattern is:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

This is an excerpt from a build file that already has the Spring Boot plugin and dependency management configured. Do not execute an isolated XML/Groovy snippet as a complete program.

## 7. Illustrative configuration: Spring MVC on Spring Boot 4.1

With Spring Boot 4.1.x, use **spring-boot-starter-webmvc** and Jetty 12.1:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
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
</dependencies>
~~~

Gradle Groovy DSL example, also for a project already configured with the Spring Boot 4.1 plugin and BOM:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webmvc') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Do not copy spring-boot-starter-undertow from a 3.5 configuration to 4.1: Undertow is no longer listed as a supported embedded server in Boot 4.1. If an application relies on Undertow-specific features, review supported alternatives, API compatibility, and library lifecycles before upgrading.

## 8. Changing the HTTP server in WebFlux

With WebFlux, the default starter is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

In Boot 3.5 and 4.1, it typically brings **spring-boot-starter-reactor-netty** onto the runtime. To run WebFlux on Jetty (Maven snippet for a project with the matching Spring Boot BOM):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-reactor-netty</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
~~~

This example changes the **request-accepting server** of WebFlux. If the application also uses WebClient or client libraries powered by Reactor Netty, check the HTTP client connector and dependencies; changing the server does not require changing the HTTP client. You may still need Netty on the classpath for the client while the web server is Jetty. Similarly, to switch WebFlux to Tomcat, use the matching starter-tomcat and exclude the default starter-reactor-netty. In Boot 4.x, the official options for WebFlux are strictly Reactor Netty, Tomcat, and Jetty.

## 9. Java example to verify the stack and server

The Java 17+ example below is a minimal Spring Boot application. Place it at **src/main/java/com/example/demo/WebServerDemo.java** in a Maven/Gradle project with exactly one appropriate MVC or WebFlux starter; the controller APIs are recognized by both stacks. The server is determined by the configured starter, not the controller code.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebServerDemo {
    public static void main(String[] args) {
        SpringApplication.run(WebServerDemo.class, args);
    }
}

@RestController
class ProbeController {
    @GetMapping("/probe")
    String probe() {
        return "ok";
    }
}
~~~

The program requires the Spring Boot classpath, so it cannot be run with javac WebServerDemo.java alone. With the Maven Wrapper of a Spring Boot project configured with the proper parent and starter:

~~~bash
./mvnw spring-boot:run
~~~

Verify in another terminal (default server port 8080):

~~~bash
curl -sS http://localhost:8080/probe
~~~

The expected response body is exactly **ok** (without a trailing newline since the controller returns a String). Response headers, port, and startup messages may vary by version and configuration; do not infer whether the runtime is Jetty or Tomcat solely from the response body. To explicitly change the port, set in **src/main/resources/application.properties**:

~~~properties
server.port=9090
~~~

Then call http://localhost:9090/probe. The curl command on port 8080 will no longer work unless a proxy or another service is listening there.

## 10. Verifying the actual versions at build and runtime

Verify at least four things: **Boot version, web stack, selected server, and server version**. Follow this order:

1. Check spring-boot-starter-parent/BOM, the Spring Boot Gradle plugin version, or dependency management output to identify which Boot version is managed.
2. Inspect the dependency graph: starter-web or webmvc for MVC, starter-webflux for WebFlux; detect duplicate Tomcat/Jetty/Undertow/Reactor Netty entries.
3. Cross-check the System Requirements table for that **exact Boot version**: server major version and Servlet API level.
4. Start the application and observe actual logs/context/runtime; send HTTP requests to test endpoints. If needed, use integration tests to verify the full connection environment.

With Maven Wrapper:

~~~bash
./mvnw dependency:tree
~~~

With Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

In the output, look for spring-boot-starter-web, spring-boot-starter-webmvc, spring-boot-starter-webflux, spring-boot-starter-tomcat, spring-boot-starter-jetty, spring-boot-starter-undertow, and spring-boot-starter-reactor-netty. With Gradle, the commands above apply to the Unix/macOS wrapper; on Windows, use gradlew.bat. Excluded dependencies or conflict resolutions should be checked on the runtimeClasspath configuration rather than only reading initial declarations.

During startup, logs typically indicate the embedded server and listening port. However, exact log strings vary by Boot version, logger, and log level, so check the server/factory name in runtime details rather than relying on a fixed log string.

## 11. Real-world scenarios

### Scenario A: On Boot 3.5 and want to use Undertow

You can use Spring MVC or WebFlux with Undertow 2.3 because both combinations are in Boot 3.5's supported server list. Exclude the default Tomcat for MVC, or the default Reactor Netty for WebFlux. Ensure multiple server factories are not loaded simultaneously.

### Scenario B: Upgrading an Undertow application from Boot 3.5 to Boot 4.1

This is a **runtime environment** change, not just bumping a dependency version number. Boot 4.1 only lists embedded Tomcat 11.0.x and Jetty 12.1.x for the Servlet stack. Choose a replacement server, audit Undertow-specific configuration code, check Jakarta Servlet packages and Servlet 6.1 compliance, swap starters, and re-run integration tests for request routing, filters, cookies/sessions, HTTPS, timeouts, and graceful shutdown.

### Scenario C: Project uses WebClient but wants to keep Spring MVC

You can keep the MVC starter and add the appropriate client library/dependencies to use WebClient for outbound HTTP calls. Do not automatically conclude the server became Reactor Netty just because Netty appears in dependencies. Boot typically prioritizes the Servlet web application type when both MVC and WebFlux are present.

### Scenario D: Migrating a Boot 2.7 WAR to Boot 3.x or 4.x

You must migrate relevant javax.servlet.* APIs to jakarta.servlet.* when upgrading to Spring Boot 3+, and review Java version, Spring Framework, security/filters, and target Servlet container. Boot 4.x requires checking Servlet API 6.1 when deploying to an external container, along with corresponding dependency/auto-configuration changes. Embedded jar and external WAR are two distinct packaging models; do not apply the embedded matrix directly to external servers.

## 12. Misconceptions to avoid

- **"WebFlux = Netty":** False. Reactor Netty is the default, yet WebFlux can also run on Tomcat/Jetty in Boot 4.x, and also Undertow in Boot 3.x.
- **"Tomcat present means MVC":** False. Tomcat can also serve WebFlux via a reactive adapter.
- **"Boot 3 uses a single Jetty version":** False. Boot 3.0/3.1 uses Jetty 11 (Servlet 5.0), while from Boot 3.2 onward it uses Jetty 12 (Servlet 6.0).
- **"Just adding the Jetty starter swaps the server":** False. You must exclude the default server starter and inspect the dependency graph.
- **"Reactor Netty in dependencies means it is the actual server":** Not necessarily. It may only serve WebClient, while the actual embedded server is Tomcat or Jetty.
- **"Seeing the same major server means Boot supports it":** False. Only combinations published in the exact Boot version's documentation are officially supported. Patch versions, Servlet API, Java, and BOM still matter.
- **"Undertow worked in Boot 3 so it works in Boot 4 too":** False. Current 4.x documentation only lists Tomcat and Jetty for Servlet, plus Reactor Netty for reactive.
- **"Upgrading from 2.7 only requires changing Tomcat":** False. The Servlet namespace changes from javax to jakarta, the minimum Java version changes, and the Spring Framework ecosystem upgrades as well.

## 13. Practical selection process

1. **Lock in the Spring Boot version** based on lifecycle, compatibility requirements, and the project's upgrade policy.
2. **Choose the stack:** MVC for standard Servlet models; WebFlux when the architecture genuinely needs reactive pipelines and non-blocking dependencies are properly designed.
3. **Consult the server list allowed by that exact version's docs:** Boot 3.5 has Tomcat/Jetty/Undertow for Servlet, with Reactor Netty added for WebFlux; Boot 4.1 has Tomcat/Jetty for Servlet, with Reactor Netty added for WebFlux.
4. **Pick a default or supported server:** prefer official starters and the BOM, avoiding manual server version overrides unless backed by testing.
5. **Check Servlet API/Jakarta/Java:** especially for WAR applications and major upgrades.
6. **Inspect the dependency graph, run the application, test HTTP/TLS/session/filters, and check logs** before concluding that the configuration runs the intended server.

## Official reference documentation

- Spring Boot 2.7.18 — System Requirements: https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html
- Spring Boot 3.0.13 — System Requirements: https://docs.spring.io/spring-boot/docs/3.0.13/reference/html/getting-started.html
- Spring Boot 3.1.12 — System Requirements: https://docs.spring.io/spring-boot/docs/3.1.12/reference/html/getting-started.html
- Spring Boot 3.2.10 — System Requirements: https://docs.spring.io/spring-boot/docs/3.2.10/reference/html/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/4.1/system-requirements.html
- Spring Boot 4.1 — Embedded Web Servers: https://docs.spring.io/spring-boot/4.1/how-to/webserver.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/servlet.html
- Spring Boot 4.1 — Reactive Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
- Spring Boot 4.1 — Build Systems / Starters: https://docs.spring.io/spring-boot/4.1/reference/using/build-systems.html
