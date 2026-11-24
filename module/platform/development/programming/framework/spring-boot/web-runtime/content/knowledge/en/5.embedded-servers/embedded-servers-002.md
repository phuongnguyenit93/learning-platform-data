# Default Servers by Starter and Inspecting the Dependency Tree

In Spring Boot, the question "which web server is the application using?" requires distinguishing three things: **the declared starter**, **the dependencies actually resolved by Gradle/Maven**, and **the server initialized by Spring Boot at runtime**. In a typical Spring Boot 3.3.x setup, `spring-boot-starter-web` leads to **embedded Tomcat**, while `spring-boot-starter-webflux` leads to **Reactor Netty**. However, dependencies can be excluded, replaced, pulled in transitively from another starter, or used solely as an HTTP client. Therefore, you should not guess the actual server from a single line in `build.gradle`.

This lesson belongs to the **Embedded Servers** group: focusing on starters, default servers, why dependencies appear, how to inspect the dependency tree, and how to confirm at runtime. Examples use Spring Boot 3.3.x, Java 21, and Gradle; for other major versions of Spring Boot, check the documentation and dependency graph for the version you are using.

## 1. How Do Starter, Stack, Server, and Classpath Differ?

| Concept | Nature | Example |
| --- | --- | --- |
| **Starter** | A dependency aggregating libraries typically needed for a capability | `spring-boot-starter-web` |
| **Web stack** | The framework model for handling HTTP requests | Spring MVC/Servlet or Spring WebFlux |
| **Web server** | The component opening sockets, accepting connections, and exchanging HTTP | Tomcat, Jetty, Undertow, Reactor Netty |
| **Servlet container** | The runtime executing the Jakarta Servlet API (Servlet, Filter, Listener...) | Tomcat, Jetty, Undertow |
| **Classpath** | The list of classes/JARs effective at compile or runtime | `runtimeClasspath` |
| **Auto-configuration** | Spring Boot creating beans matching classpath conditions, properties, and existing beans | `ServletWebServerFactoryAutoConfiguration` |
| **Running server** | The server actually created by the context and listening for HTTP | `TomcatWebServer` or `NettyWebServer` |

A starter can bring a server onto the classpath **as a transitive dependency**. However, Spring Boot only creates one web server matching the application type and runtime configuration. The presence of a JAR does not mean that JAR is chosen as the server.

For example, a Spring MVC application that also uses `spring-boot-starter-webflux` to call external services with `WebClient` may contain both Tomcat and Reactor Netty libraries in its dependency tree, yet the default selected server remains MVC's Tomcat. Reactor Netty may only be used as an HTTP client.

## 2. Default Server Table for Key Starters

The table below describes **typical Spring Boot 3.3.x configuration**, without exclusions, replacements, or custom factory beans:

| Starter or dependency group | Web stack / purpose | Default server or meaning |
| --- | --- | --- |
| `spring-boot-starter-web` | Spring MVC on Servlet | **Tomcat** via `spring-boot-starter-tomcat` |
| `spring-boot-starter-webflux` | Reactive WebFlux | **Reactor Netty** via `spring-boot-starter-reactor-netty` |
| `spring-boot-starter-jersey` | JAX-RS/Jersey on Servlet | **Tomcat** in the 3.3.x starter's default dependencies |
| `spring-boot-starter-tomcat` | Starter for the Tomcat Servlet container | Provides Tomcat; the starter alone does not determine whether the app runs a web stack |
| `spring-boot-starter-jetty` | Starter for replacing/declaring the Jetty server | Provides Jetty; requires an appropriate stack and configuration |
| `spring-boot-starter-undertow` | Starter for replacing/declaring the Undertow server in Boot 3.3.x | Provides Undertow; requires an appropriate stack and configuration |
| `spring-boot-starter-reactor-netty` | Reactor Netty HTTP runtime | Can serve WebFlux or be used by an HTTP client; does not turn Spring MVC into WebFlux by default |
| `spring-boot-starter-data-jpa`, `spring-boot-starter-security`, `spring-boot-starter-validation`, `spring-boot-starter-actuator` | Database, security, validation, monitoring | **Does not determine a default web server** merely by being declared |

Specialized starters such as WebSocket, Spring Web Services, Spring Data REST, or third-party starters should be checked on the **actual dependency tree**. They may add web libraries or bring in a web starter along another dependency path; do not equate the word "starter" with having its own embedded server.

Two choices stated directly in the Spring Boot documentation:

- **Servlet:** `spring-boot-starter-web → spring-boot-starter-tomcat → Tomcat`.
- **Reactive:** `spring-boot-starter-webflux → spring-boot-starter-reactor-netty → Reactor Netty`.

Tomcat, Jetty, and Undertow provide a Servlet environment; Reactor Netty is an HTTP server/reactive runtime, not a Servlet container for running Spring MVC's `DispatcherServlet`.

## 3. Why Does starter-web Choose Tomcat?

When declaring:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle resolves the dependencies required by the starter. A representative portion of the tree (abbreviated and without version numbers since they depend on the Boot BOM) is:

~~~text
runtimeClasspath
\--- org.springframework.boot:spring-boot-starter-web
     +--- org.springframework.boot:spring-boot-starter
     +--- org.springframework.boot:spring-boot-starter-json
     +--- org.springframework:spring-web
     +--- org.springframework:spring-webmvc
     \--- org.springframework.boot:spring-boot-starter-tomcat
          +--- org.apache.tomcat.embed:tomcat-embed-core
          +--- org.apache.tomcat.embed:tomcat-embed-el
          \--- org.apache.tomcat.embed:tomcat-embed-websocket
~~~

This is an **illustrative** tree, not verbatim output from a specific Gradle run. Depending on the version, the report will include additional constraints, versions, shorthand markers, and other dependency branches.

Role of each group:

- `spring-webmvc` provides `DispatcherServlet`, handler mapping, and Spring MVC HTTP processing.
- `spring-boot-starter-tomcat` provides the integrated server/container.
- `tomcat-embed-core` contains the core of embedded Tomcat.
- `spring-boot-starter-json` brings the appropriate JSON libraries into the application.

When Spring Boot detects a Servlet application, auto-configuration creates an appropriate `ServletWebServerFactory` (by default usually `TomcatServletWebServerFactory`) and uses that factory to start the server. Controllers and services are Spring beans, while Tomcat is responsible for accepting requests and running Servlets/Filters.

**Signs to look for on the dependency graph:** `spring-boot-starter-tomcat` and `org.apache.tomcat.embed:tomcat-embed-core`. However, final confirmation must be the runtime web server, because a dependency can still be present without being selected, or the application may run under a different deployment model.

## 4. Why Does starter-webflux Choose Reactor Netty?

With:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

An important branch in the tree is:

~~~text
runtimeClasspath
\--- org.springframework.boot:spring-boot-starter-webflux
     +--- org.springframework:spring-webflux
     +--- org.springframework.boot:spring-boot-starter-json
     \--- org.springframework.boot:spring-boot-starter-reactor-netty
          \--- io.projectreactor.netty:reactor-netty-http
~~~

Reactor Netty provides an HTTP server suited to WebFlux's reactive and non-blocking processing model. Spring Boot typically creates `ReactiveWebServerApplicationContext` and `NettyReactiveWebServerFactory` (when Netty is selected).

Distinguish between:

- `spring-webflux` is the web framework.
- Reactor is the Reactive Streams foundation used across the Spring ecosystem.
- `reactor-netty-http` is the library implementing the Netty-based HTTP client/server.
- `NettyWebServer` is the server wrapper Spring Boot uses at runtime.

WebFlux can also be deployed on other servers supported by the corresponding Boot version. Do not equate "WebFlux" with "must be Netty", just as you should not equate "Spring MVC" with "must be Tomcat".

## 5. Multiple Web Starters Present: "Having a Dependency" vs. "Running a Server"

Suppose a project declares both:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

When both Spring MVC and WebFlux are on the classpath, standard Spring Boot 3.3 **prefers Servlet/MVC** when auto-detecting `WebApplicationType`. Common consequences:

- The application boots with a `ServletWebServerApplicationContext`.
- Embedded Tomcat remains the default server from starter-web.
- Reactive APIs such as `WebClient` can be used to call external services.
- The presence of `spring-boot-starter-reactor-netty` in the graph **does not prove that Reactor Netty is listening for incoming client HTTP requests**.

Analysis table:

| Dependencies present | Default app type (if not overridden) | Server typically started |
| --- | --- | --- |
| Only starter-web | SERVLET | Tomcat |
| Only starter-webflux | REACTIVE | Reactor Netty |
| Both starter-web and starter-webflux | SERVLET | Tomcat |
| Only non-web starters | NONE (if no other web framework) | No embedded web server |
| Starter-web with Tomcat properly replaced by Jetty | SERVLET | Jetty |

You can configure `spring.main.web-application-type` or call `SpringApplication.setWebApplicationType(...)` to select the application type when needed, but **do not** force REACTIVE just to see Netty run: controllers, Servlet filters, Spring Security, and related dependencies must be compatible with the chosen stack.

## 6. Why Inspect runtimeClasspath First?

Gradle manages several different configurations:

- `implementation`: dependencies used to compile and run the application.
- `compileClasspath`: set of classes/JARs used during compilation.
- `runtimeClasspath`: set of resolved dependencies for running the application (including appropriate runtime dependencies).
- `testRuntimeClasspath`: dependencies used when running tests; may include test servers or other libraries.
- `annotationProcessor`: classpath for annotation processors, not the runtime server.

To find the actual server carried along to run the application, **runtimeClasspath** is usually a better starting point than compileClasspath or testRuntimeClasspath. For a WAR deployed to an external container or an application with custom packaging, you must also inspect the container-provided scope and the final deployed artifact.

Run in the project directory containing the Gradle wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

In a multi-project Gradle build, target the specific subproject:

~~~bash
./gradlew :my-web-app:dependencies --configuration runtimeClasspath
~~~

Replace `:my-web-app` with the actual Gradle path of the module containing the application. Do not assume the root project's dependency tree is the tree for every subproject.

**How to read the report:** a line at the top of a branch is a direct or parent dependency; indented lines below represent dependencies brought through it. Trace the branch backward from `spring-boot-starter-tomcat` to the starter or library that pulled it in.

## 7. dependencyInsight: Finding Exactly Who Pulled the Server In

The `dependencies` command shows the big picture; `dependencyInsight` answers "where does this dependency come from and why was this version selected?".

Example with Tomcat:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
~~~

With Tomcat's core library:

~~~bash
./gradlew dependencyInsight \
  --dependency tomcat-embed-core \
  --configuration runtimeClasspath
~~~

With Reactor Netty:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-reactor-netty \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency reactor-netty-http \
  --configuration runtimeClasspath
~~~

The Bash commands use backslashes for line continuation. In PowerShell, write them on a single line:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

With a subproject:

~~~bash
./gradlew :my-web-app:dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
~~~

`dependencyInsight` helps detect:

1. Whether the dependency is declared directly or pulled through a starter.
2. Whether there are multiple dependency paths leading to the same module.
3. Whether the selected version was upgraded/downgraded by dependency constraints or conflict resolution.
4. Whether a dependency you intended to exclude is still brought in by another branch.
5. When switching Tomcat to Jetty, whether Tomcat remains on runtimeClasspath via another dependency.

To avoid misidentifying results, search by full `group:name` when multiple modules share similar names, such as `org.springframework.boot:spring-boot-starter-tomcat`.

### 7.1. Common Symbols in Gradle Trees

| Symbol in output | Meaning |
| --- | --- |
| `+---` or `\---` | A dependency branch |
| `(*)` | This dependency branch was already displayed elsewhere; Gradle omits repeated subtrees |
| `(c)` | Dependency constraint, **not** necessarily an artifact actually placed on the classpath |
| `a:1.0 -> 2.0` | Requested version and version selected after resolution differ |
| `(n)` or unresolved message | Dependency could not be resolved in that report |
| `FAILED` | Resolution error that requires specific investigation |

Illustrative example:

~~~text
+--- org.springframework.boot:spring-boot-starter-web
|    \--- org.springframework.boot:spring-boot-starter-tomcat
|         \--- org.apache.tomcat.embed:tomcat-embed-core
\--- some-other-library
     \--- org.apache.tomcat.embed:tomcat-embed-core (*)
~~~

The second branch with `(*)` still shows the dependency is used via another path. Do not treat `(*)` as an error, and do not treat `(c)` as proof that a server is actually present.

### 7.2. If the Report Shows "No dependencies matching..."

That result may mean the searched module does not exist in that specific configuration, or the search name did not match. Check in order:

1. Did you run against the right Gradle subproject?
2. Did you select the application's `runtimeClasspath` instead of a test configuration?
3. Is the searched module name spelled correctly?
4. Was the dependency excluded, module-substituted, or was the starter changed?
5. Are you looking at a build variant, artifact, or packaged application different from what actually runs?

Do not automatically conclude the application uses Jetty merely because Tomcat is not found. You must determine which server is actually selected.

## 8. From Dependency Graph to Runtime Confirmation

The dependency graph answers **which implementations could be present**. Runtime must answer **which implementation was selected**.

With Spring Boot 3.3, several classes help identify this:

| Application type | Typical ApplicationContext | Common factory | Runtime WebServer |
| --- | --- | --- | --- |
| Servlet + Tomcat | `ServletWebServerApplicationContext` | `TomcatServletWebServerFactory` | `TomcatWebServer` |
| Servlet + Jetty | `ServletWebServerApplicationContext` | `JettyServletWebServerFactory` | `JettyWebServer` |
| Servlet + Undertow | `ServletWebServerApplicationContext` | `UndertowServletWebServerFactory` | `UndertowWebServer` |
| Reactive + Reactor Netty | `ReactiveWebServerApplicationContext` | `NettyReactiveWebServerFactory` | `NettyWebServer` |

These names are implementation classes from the Boot 3.x version. They are useful for diagnostics, though business logic should not depend on them unless specifically required.

At runtime, you can check server startup logs (Tomcat/Netty/Jetty), actual address and port, the process/JVM, and the ApplicationContext. Automatic logs can vary with log levels or startup configuration, so a direct check on `WebServer` is more reliable if programmatic evidence is needed.

## 9. Complete Example: Servlet Application and Confirming Real Tomcat

The example creates a Spring Boot 3.3.x, Java 21, Gradle application. It prints the WebServer implementation started by Spring Boot and exposes an HTTP endpoint for verification.

Structure:

~~~text
server-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/serverselection/
    ├── ServerSelectionApplication.java
    └── HelloController.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'server-selection-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**src/main/java/com/example/serverselection/ServerSelectionApplication.java**

~~~java
package com.example.serverselection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ServerSelectionApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(ServerSelectionApplication.class, args);

        if (context instanceof ServletWebServerApplicationContext servlet) {
            WebServer server = servlet.getWebServer();
            System.out.println("STACK=SERVLET");
            System.out.println("SERVER=" + server.getClass().getSimpleName());
            System.out.println("PORT=" + server.getPort());
        } else {
            System.out.println("STACK=OTHER");
        }
    }
}
~~~

**src/main/java/com/example/serverselection/HelloController.java**

~~~java
package com.example.serverselection;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

Run note: the project needs a compatible Gradle wrapper and JDK 21; with Gradle installed, you can generate the wrapper and then run:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

If the project already has a wrapper, just run `./gradlew bootRun`. On Windows PowerShell use `.\gradlew.bat bootRun`.

In the default configuration with no port/server overrides, after startup logs the following output is expected:

~~~text
STACK=SERVLET
SERVER=TomcatWebServer
PORT=8080
~~~

These are the three lines printed by the sample code, **not Spring Boot's entire stdout**. If a different `server.port` or `server.port=0` is configured, PORT will reflect the actual port. If Tomcat is properly replaced with Jetty, the SERVER name changes accordingly.

Test HTTP from another terminal:

~~~bash
curl -i http://localhost:8080/hello
~~~

Expected result has status `200 OK` and JSON response:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Check the sample project's dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

Compare all three sources of evidence: build.gradle declares starter-web; the dependency graph contains Tomcat; runtime prints `TomcatWebServer`. When all three align, concluding the server is far more solid than just looking at the starter name.

## 10. Switching Tomcat to Jetty in the Servlet Stack

If a Spring MVC application needs to use Jetty, you must **exclude default Tomcat and add the appropriate Jetty starter**, replacing the existing starter-web dependency with the following configuration:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Points to remember:

1. This is a replacement for the previous web dependency block, not adding a second starter-web.
2. Exclusion applies per dependency branch. If another library still pulls Tomcat in, trace the source with `dependencyInsight` and handle it in the appropriate place.
3. Jetty must be compatible with Spring Boot and the Jakarta Servlet version in use; avoid forcing versions manually unless necessary.
4. After editing, re-run the dependency report and the application to confirm `JettyWebServer`.

Verification commands:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-starter-jetty \
  --configuration runtimeClasspath
~~~

If Jetty was swapped properly and no other branch pulls in Tomcat, starter-tomcat should no longer appear on runtimeClasspath. Observing runtime remains the final confirmation step.

Similarly, within Spring Boot 3.3.x you can substitute `spring-boot-starter-undertow` when compatible with the project. Do not assume server options and starter names in future major versions will stay the same as 3.3.x.

## 11. Switching Reactor Netty to Another HTTP Server for WebFlux

Spring WebFlux supports multiple HTTP runtimes within the corresponding Boot version's scope; `spring-boot-starter-webflux` pulls in Reactor Netty by default. When switching to another server, evaluate both dependencies and how WebFlux is deployed on that server.

Example approach with Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

This snippet only illustrates dependency structure for Boot 3.3.x. Check version-specific documentation, compatibility, and WebFlux/runtime integration before using it in a real application.

In particular, do not exclude Reactor Netty simply because you see it in the graph when the application uses `WebClient`: Reactor Netty may be the active HTTP client connector. If you want to separate the client connector and server runtime, configure both sides explicitly and test outbound/inbound requests.

## 12. Tricky Situations When Reading the Dependency Tree

### 12.1. A Dependency Has Multiple Incoming Paths

`dependencyInsight` may show Tomcat being pulled in via a web starter and also via an internal library. Excluding it on one branch may not remove every path. Do not use a global exclusion without understanding why it was required.

### 12.2. Both Tomcat and Reactor Netty Are Present

This is not always an error. A Spring MVC application using WebClient can use Tomcat for the server and Reactor Netty for the client. Use the runtime context to confirm; do not infer that two HTTP servers are opening ports merely because both appear in the graph.

### 12.3. Server JAR Present Without Opening an HTTP Port

The application may set `spring.main.web-application-type=none`, fail during startup, run inside an external servlet container, or declare a different WebServerFactory. Having the JAR on runtimeClasspath does not prove an HTTP port is listening.

### 12.4. Tomcat Found on testRuntimeClasspath

Test dependencies can bring in libraries absent from the production application runtime. Inspect `runtimeClasspath` and the final artifact rather than looking only at the test classpath.

### 12.5. Deploying a WAR to an External Server

With external Tomcat/Jetty, the deployment environment manages the server and its lifecycle. Analyze `providedRuntime`, WAR packaging, `WEB-INF/lib`, and the operating container as well. Do not blindly apply executable JAR assumptions.

### 12.6. Parent/BOM Changes Versions While Starter Names Stay Identical

Dependency management can select a different Tomcat or Reactor Netty version without changing the starter name. `dependencyInsight` shows the selected version and selection reason, helping spot conflicts or unintended version overrides. Avoid pinning standalone versions for server artifacts when the Boot BOM manages them consistently.

### 12.7. Running the Gradle Report on the Wrong Subproject

In a multi-project build, `./gradlew dependencies` at the root returns dependencies of the root project, which may not be those of the runnable module. Target the exact `:module:dependencies` path and inspect that module's runtimeClasspath configuration.

### 12.8. Confusing Port with Server Type

Both Tomcat and Reactor Netty can use default port 8080. Merely seeing port 8080 open **does not prove** Tomcat is used. Check logs, factories, and the WebServer implementation.

## 13. Maven Has Equivalent Inspection Commands

For Maven projects, use `mvn dependency:tree` to view the dependency tree:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-reactor-netty
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
~~~

Filter options depend on the maven-dependency-plugin version; when filtering yields nothing, inspect the full tree and verify the dependency is being resolved.

Maven `dependency:tree` and Gradle `dependencies` both answer "which JARs are present and via which dependency paths?". Gradle `dependencyInsight` digs deeper into the selected version and resolution path on a specific configuration. Neither tool **replaces** confirming the web server actually running.

## 14. Server Verification Checklist for an Application

When preparing to deploy or swap an embedded server, check in order:

1. **Read direct dependencies:** does the application declare starter-web, starter-webflux, starter-jersey, or only non-web starters?
2. **Pick the right module:** in multi-project Gradle builds, specify the project path of the runnable application.
3. **Inspect resolved runtimeClasspath:** which of starter-tomcat, starter-reactor-netty, starter-jetty, or starter-undertow is present?
4. **Trace origin with dependencyInsight:** which starter or library brought in the server dependency? Are there multiple paths?
5. **Check application type:** SERVLET, REACTIVE, or NONE; if both MVC and WebFlux are present, have you confirmed which stack Boot chooses?
6. **Check overrides:** exclusions, dependency substitutions, version constraints, custom WebServerFactory, WAR packaging, or external containers.
7. **Inspect logs and runtime WebServer:** which implementation is initialized, listening port, bind address, and startup status.
8. **Send a real HTTP request:** confirm the application accepts requests and returns responses; check port/context path.
9. **Re-test after changing the server:** Servlet Filters, WebSocket if used, HTTPS/TLS, sessions, timeouts, headers, uploads, and monitoring—do they behave as required?
10. **Keep dependencies consistent:** prefer versions managed by the Spring Boot BOM and consult documentation for your actual version.

You can remember the method in three layers:

~~~text
Declared dependencies (build.gradle / pom.xml)
               |
               v
Actual resolved dependencies (runtimeClasspath / dependency:tree)
               |
               v
Initialized ApplicationContext + WebServer
               |
               v
Real HTTP requests, logs, and metrics
~~~

**Conclusion:** `spring-boot-starter-web` typically pulls in Tomcat and boots Spring MVC on Servlet, while `spring-boot-starter-webflux` pulls in Reactor Netty for WebFlux. Other starters do not necessarily bring a server of their own, and a server library appearing in the tree is not enough to know it is listening for HTTP. Use `dependencies` for the big picture, `dependencyInsight` to trace origin and version, and then confirm `WebServer` along with real requests before concluding or changing an embedded server.

## References

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html