# Understanding the WAR Boundaries for Reactive Applications Using WebFlux

## 1. Conclusion Before Designing the System

**With Spring Boot, do not deploy WebFlux applications using traditional WAR packaging into an external Servlet container.** This limitation is stated explicitly in Spring Boot's Traditional Deployment and Reactive Web Applications documentation, including the Spring Boot 3.3 branch used in the examples below.

That **does not mean WebFlux can only run on Netty or cannot run on Tomcat**. Distinguish three scenarios:

1. **Spring Boot WebFlux + executable JAR + embedded Reactor Netty**: the default, supported model.
2. **Spring Boot WebFlux + executable JAR + embedded Tomcat/Jetty**: can be supported when swapping the embedded server per official configuration. WebFlux uses an adapter for non-blocking Servlet I/O; this is still a **self-starting server** application.
3. **Spring Boot WebFlux + WAR deployed into external Tomcat/Jetty**: **not supported by Spring Boot** like Spring MVC's traditional deployment path. Simply adding the `war` plugin, setting `packaging=war`, or extending `SpringBootServletInitializer` does not make it a supported WebFlux deployment option.

In addition, **pure Spring Framework WebFlux** provides a low-level mechanism to package a WAR for a compatible Servlet container via **`AbstractReactiveWebInitializer`** and **`ServletHttpHandlerAdapter`**. That is a Spring Framework-level capability, **not** a guarantee that **Spring Boot WebFlux auto-configuration + traditional WAR** will work. Do not cite manual Spring Framework examples to deny Spring Boot's deployment boundary.

**Decision rule:** If the hard requirement is **deploying a WAR into an enterprise application server**, choose an appropriate **Servlet/Spring MVC application** or evaluate an architecture that does not use Boot WebFlux WAR. If the key requirement is the **WebFlux reactive server stack**, prefer an **executable JAR** or a container image running that JAR.

This lab uses **Spring Boot 3.3.5**, **Java 17**, Maven, and **Gradle 8.5**. This is an illustrative version set, not a claim of latest. Check release notes when upgrading Spring Boot, Spring Framework, or the servlet container.

## 2. What Is a WAR and What Startup Mechanism Does It Rely On?

### 2.1. Traditional WAR

**WAR (Web Application Archive)** is a web archive handed to an **already-running Servlet container**, such as Tomcat in an enterprise environment. The container unpacks or reads the WAR, creates the web application context, and triggers application initialization per the Servlet API. For **Spring Boot MVC** apps, **`SpringBootServletInitializer`** can initialize the Spring application context in this environment.

Typical WAR layout:

~~~text
mvc-war-demo.war
├── META-INF/
└── WEB-INF/
    ├── classes/                 # application classes and resources
    ├── lib/                     # libraries needed by web app
    └── lib-provided/            # for executable Boot WAR, embedded server marked provided
~~~

**`WEB-INF/lib-provided`** is a special layout used by Spring Boot build plugins in executable WARs so container-provided libraries do not interfere on external deployment, yet remain available when running **`java -jar`**. A traditional WAR does not have to contain `lib-provided`; do not judge the web stack solely by directory names.

### 2.2. Spring Boot WebFlux Executable JAR

A Spring Boot executable JAR is run directly by the JVM. It carries application code and runtime dependencies while starting its own embedded HTTP server:

~~~text
reactive-war-boundary-1.0.0.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/reactive/ReactiveJarApplication.class
    └── lib/
        ├── spring-boot-*.jar
        ├── reactor-netty-*.jar
        └── ...
~~~

In this model, **`java -jar`** launches Spring Boot, Boot creates a reactive application context and embedded Reactor Netty (by default). No external Tomcat is needed to drop files into a `webapps` directory.

### 2.3. Same `.war` Extension, Not the Same Contract

A build tool **can generate a file ending in `.war`**, yet that only proves an archive exists. It **does not prove** that an external container will register handlers properly, start the application context, or serve WebFlux endpoints cleanly. Filename, archive layout, and supported deployability are three separate things.

Conversely, a **Spring Boot MVC executable WAR** with the right build configuration can **both deploy to a servlet container and run via `java -jar`**. That dual-mode capability belongs to the Servlet/Spring MVC path and does **not** automatically carry over to WebFlux.

## 3. WebFlux Is a Reactive HTTP Programming Model, Not a WAR Format

Spring WebFlux is built around a **non-blocking** model, types such as **`Mono`** and **`Flux`**, and an HTTP processing layer without a strict dependency on the Servlet API.

Related components:

- **`DispatcherHandler`**: Spring WebFlux's request-dispatching mechanism.
- **`HttpHandler`**: low-level abstraction representing asynchronous HTTP request/response handling.
- **`Reactor Netty`**: the server runtime typically used by default alongside `spring-boot-starter-webflux`.
- **`ServletHttpHandlerAdapter`**: adapter when running WebFlux over non-blocking Servlet I/O.
- **`DispatcherServlet`**: Spring MVC's request-dispatching mechanism, distinct from `DispatcherHandler`.

Do not equate **WebFlux** with **`WebClient`**. `WebClient` is a **reactive HTTP client**; a Spring MVC application can use `WebClient` to call downstream services while remaining a Servlet/MVC application.

Likewise, Spring MVC supports several reactive return types such as `Mono`/`Flux`. A controller returning **`Mono<String>`** is **not sufficient proof** that the whole application is powered by WebFlux `DispatcherHandler`. You must examine the starters, auto-configuration, and web application type.

### 3.1. Decision Matrix

| Application | Server/Stack | Artifact/Deployment | Status |
| --- | --- | --- | --- |
| Spring Boot WebFlux, `spring-boot-starter-webflux` | Embedded Reactor Netty | **Executable JAR** | **Supported; appropriate default** |
| Spring Boot WebFlux, swapping Netty for embedded Tomcat/Jetty | WebFlux on non-blocking Servlet I/O adapter | **Executable JAR** | **Can be supported** via embedded server configuration |
| Spring Boot WebFlux | Pre-running external Tomcat/Jetty | **Traditional WAR** | **Not supported by Spring Boot** |
| Spring Boot MVC, `spring-boot-starter-web` | Servlet / `DispatcherServlet` | **Externally deployed WAR** | **Supported** when initializer and dependency scopes are right |
| Spring Boot MVC using `WebClient` | Servlet/MVC + reactive client | **Externally deployed WAR** | **Supported** under MVC WAR rules |
| Spring Framework WebFlux without Boot's traditional model | WebFlux + manually configured `ServletHttpHandlerAdapter` | **Manual WAR** | **Spring Framework capability**; requires custom design/testing, not Boot WebFlux WAR |

Do not treat a WebFlux config running on embedded Tomcat as proof that Spring Boot WebFlux will bootstrap from a WAR on external Tomcat. **Embedded server integration** and the **Servlet container deployment lifecycle** are two different mechanisms.

## 4. Why Does Spring Boot Not Support WebFlux Traditional WAR?

### 4.1. Two Different Startup Models

With a default WebFlux application:

~~~text
java -jar app.jar
    |
    v
SpringApplication.run(...)
    |
    v
ReactiveWebServerApplicationContext
    |
    v
ReactiveWebServerFactory
    |
    v
Reactor Netty (or embedded reactive server adapter)
    |
    v
DispatcherHandler / WebFlux routes
~~~

In a Servlet/Spring MVC WAR:

~~~text
Already-running External Tomcat/Jetty
    |
    v
Servlet container looks up Servlet initializer
    |
    v
SpringBootServletInitializer / Spring WebApplicationInitializer
    |
    v
Servlet web application context
    |
    v
DispatcherServlet and MVC mappings
~~~

**`SpringBootServletInitializer`** belongs to the bootstrap mechanism of **Servlet web applications**. WebFlux's application context and server factory follow a different lifecycle. Adding a subclass of `SpringBootServletInitializer` does not make Boot WebFlux automatically wire a reactive `HttpHandler` adapter into an external container along Boot's supported traditional deployment path.

### 4.2. Reactor Netty Is Not a Servlet Container

By default **`spring-boot-starter-webflux`** pulls in **`spring-boot-starter-reactor-netty`**. Reactor Netty is an HTTP server using Netty APIs, not a Servlet container. It does not accept WAR files or process **`WEB-INF/web.xml`** or Servlet initialization the way external Tomcat does.

**This cannot be fixed by renaming `.jar` to `.war`.** Runtime semantics and bootstrapping do not change with the filename.

### 4.3. A Servlet Adapter Does Not Remove Boot's Limitation

Spring Framework includes an adapter for running WebFlux with non-blocking Servlet I/O. Spring Framework also provides **`AbstractReactiveWebInitializer`** for manual deployment to compatible containers. That **does not create a supported traditional Spring Boot guide**; going down that road means taking ownership of custom bootstrap code, handler/filter/security wiring, dependency scopes, and container compatibility rather than relying on Boot WebFlux WAR defaults.

**Article scope:** We explain the boundary and how to pick a safe architecture. We do not provide a recipe to "change a few lines of `build.gradle` into a Boot WebFlux WAR," because that path is not supported by Spring Boot.

## 5. Choosing Based on Deployment Requirements

Start from **hard environmental constraints**, not from the archive extension:

**Scenario A — The system needs a WebFlux non-blocking HTTP server:**

- Choose **`spring-boot-starter-webflux`**.
- Package an **executable JAR** using the Spring Boot Maven/Gradle Plugin.
- Run via **`java -jar`**, systemd, container image, Kubernetes, or another suitable platform.
- Use the default embedded Reactor Netty, or evaluate embedded Tomcat/Jetty when specifically required.
- Test HTTP ports, backpressure/blocking points, throughput, and resource usage under realistic workloads.

**Scenario B — The organization accepts only WARs into existing Tomcat/Jetty:**

- Choose the **Spring MVC / Servlet stack**, unless an alternative architecture is approved.
- Configure **`packaging war`** (Maven) or the **`war`** plugin (Gradle).
- Extend **`SpringBootServletInitializer`** and mark the embedded servlet container **`provided`**.
- Verify Servlet/Jakarta versions compatible with Spring Boot and the external server.
- You can still use **`WebClient`** for reactive outbound API calls without switching the whole server to WebFlux.

**Scenario C — Want to keep WebFlux, yet infrastructure only allows WAR uploads:**

- Call this out clearly as an **architectural conflict**, not merely a missing build plugin setting.
- Propose allowing an executable JAR/container image, or changing the server stack to MVC.
- If considering manual **Spring Framework WebFlux + `AbstractReactiveWebInitializer`**, treat it as a custom integration effort with dedicated ownership, testing/maintenance, and support scope. Do not label it standard Spring Boot WAR deployment.

**Core point:** A WAR is **a distribution and bootstrap mechanism**, not a "reactive endpoint feature." The WAR vs. JAR decision must be validated against runtime architecture from day one.

## 6. Hands-On Lab: A Working Spring Boot WebFlux Executable JAR

This lab demonstrates the right choice for WebFlux: a **self-running JAR**. The same Java 17 source code builds with Maven **or** Gradle.

### 6.1. Directory Tree

~~~text
reactive-war-boundary/
├── pom.xml                     # only use if choosing Maven
├── settings.gradle             # only use if choosing Gradle
├── build.gradle                # only use if choosing Gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactive/
    │   │   ├── ReactiveJarApplication.java
    │   │   └── GreetingController.java
    │   └── resources/static/index.html
    └── test/java/com/example/reactive/
        └── ReactiveJarApplicationTest.java
~~~

This tree shows **two alternative build setups**. A real repository picks either POM or Gradle files, not both simultaneously.

For WebFlux, place static content in **`src/main/resources/static`** (or other Boot-supported resource locations), **not `src/main/webapp`** as used in older WAR web apps. That also avoids misleading readers into thinking WebFlux requires a servlet webapp root.

### 6.2. Complete Main Class

File **`src/main/java/com/example/reactive/ReactiveJarApplication.java`**:

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveJarApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveJarApplication.class, args);
    }
}
~~~

Boot uses this class as the application entry point. We **do not** extend `SpringBootServletInitializer`, because our target is a Spring Boot WebFlux executable JAR rather than an external Servlet WAR.

### 6.3. WebFlux Controller Returning `Mono<String>`

File **`src/main/java/com/example/reactive/GreetingController.java`**:

~~~java
package com.example.reactive;

import reactor.core.publisher.Mono;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> hello() {
        return Mono.just("WEBFLUX_JAR_OK");
    }
}
~~~

This is a complete Java file. **`Mono<String>`** is a reactive publisher holding at most one item. In an application configured for **WebFlux**, this request is handled by the reactive WebFlux HTTP stack.

**Do not assume Spring MVC disappears merely because `Mono` is used.** We intentionally declare **`spring-boot-starter-webflux`** and **omit `spring-boot-starter-web`** so the chosen web application type is reactive. That distinction is crucial when explaining the WAR boundary.

When the server runs on default port 8080 without a proxy or override, call:

~~~bash
curl --silent http://localhost:8080/hello
~~~

**Exact HTTP response body:**

~~~text
WEBFLUX_JAR_OK
~~~

The returned string has no JSON wrapper because the controller produces **`text/plain`**. `curl` may not print a trailing newline, so the shell prompt may appear immediately after the body; do not mistake that for an error. Spring Boot/Gradle/Maven logs are not part of the response body.

### 6.4. A WebFlux Static Resource

File **`src/main/resources/static/index.html`**:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>WebFlux JAR</title>
</head>
<body>
    <h1>Reactive application in executable JAR</h1>
</body>
</html>
~~~

With Spring Boot WebFlux's default resource configuration, the app serves this welcome page from **`GET /`**. It is a classpath resource inside the executable JAR, not **`src/main/webapp`** in an externally deployed WAR.

### 6.5. JUnit Integration Test on Random Port

File **`src/test/java/com/example/reactive/ReactiveJarApplicationTest.java`**:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveJarApplicationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void respondsOverHttp() {
        client.get().uri("/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("WEBFLUX_JAR_OK");
    }
}
~~~

The test uses **`RANDOM_PORT`**, avoiding port 8080 collisions in CI. It tests the endpoint over HTTP while Spring Boot starts the embedded server inside the test context.

**`WebTestClient`** is a testing tool; it does not turn an application into WebFlux if production dependencies/auto-configuration use MVC. Because this lesson uses the WebFlux starter, this environment tests an actual WebFlux app. If the test fails to start, inspect the classpath, test dependencies, and reports before blaming WAR/JAR packaging.

## 7. Maven: Complete POM for WebFlux Executable JAR

Create **`pom.xml`** (if choosing Maven, pair this file with the Java code in section 6):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-war-boundary</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

**What to observe:**

- **`packaging=jar`**: the deliverable is an executable Spring Boot JAR, not a WAR.
- **`spring-boot-starter-webflux`**: brings WebFlux and the default embedded Reactor Netty server into runtime.
- **`spring-boot-starter-test`**, `test` scope: JUnit/Boot test support is excluded from application runtime dependencies.
- **`spring-boot-maven-plugin`** with Spring Boot parent: **repackages** the JAR into an executable artifact.
- No **`spring-boot-starter-web`**; avoids Spring MVC taking precedence if both frameworks accidentally appear on the classpath.

### 7.1. Build and Run with Maven

When the repository has Maven Wrapper:

~~~bash
./mvnw clean verify
java -jar target/reactive-war-boundary-1.0.0.jar
~~~

If there is no wrapper, run **`mvn clean verify`** with a compatible installed Maven. On Windows use **`mvnw.cmd`**.

**`verify`** compiles, runs tests, and passes through `package`/`repackage` in the standard lifecycle. With this POM, the expected artifact is:

~~~text
target/reactive-war-boundary-1.0.0.jar
~~~

Once the application starts cleanly, open a second terminal:

~~~bash
curl --silent http://localhost:8080/hello
~~~

Expected response body:

~~~text
WEBFLUX_JAR_OK
~~~

**Conditions:** compatible Java runtime, port 8080 free, dependencies downloaded, and tests passing. Do not assume CI environments allow binding port 8080 in every job; when running tests alone, the example already uses `RANDOM_PORT`.

### 7.2. Verify the Artifact by Structure, Not Filename

~~~bash
jar tf target/reactive-war-boundary-1.0.0.jar
~~~

In the entry listing, expect:

~~~text
BOOT-INF/classes/com/example/reactive/ReactiveJarApplication.class
BOOT-INF/classes/com/example/reactive/GreetingController.class
BOOT-INF/classes/static/index.html
BOOT-INF/lib/...
~~~

You will also see the Boot launcher under the Spring Boot loader package. **Having `BOOT-INF` and running via `java -jar`** confirms this is a Boot executable JAR, not a WAR for an external Tomcat. `BOOT-INF/lib` lists many more entries depending on resolved versions.

## 8. Gradle: Complete `build.gradle` for WebFlux Executable JAR

If choosing Gradle, file **`settings.gradle`**:

~~~groovy
rootProject.name = 'reactive-war-boundary'
~~~

File **`build.gradle`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the complete configuration for a **WebFlux executable JAR** with the section 6 source code. We do not apply **`id 'war'`**, because we are not targeting traditional WAR deployment. The Spring Boot Gradle Plugin creates **`bootJar`** when the Java plugin is present; `bootJar` packages the main source set and runtime dependencies into an executable archive.

### 8.1. Gradle Commands

The project needs a compatible Gradle Wrapper (e.g., 8.5) created or provided beforehand. Run at root:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/reactive-war-boundary-1.0.0.jar
~~~

On Windows use **`gradlew.bat`**. Once the server is running, in a second terminal:

~~~bash
curl --silent http://localhost:8080/hello
~~~

Response body:

~~~text
WEBFLUX_JAR_OK
~~~

From identical Java sources and starter dependencies, Maven and Gradle produce the same business behavior. The difference is the artifact folder: **`target/`** vs. **`build/libs/`**.

### 8.2. Inspecting the Gradle Dependency Graph

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Expect to see **`spring-boot-starter-webflux`** and **`spring-boot-starter-reactor-netty`**, not a Spring MVC server starter declared in the sample project. If `spring-boot-starter-web` shows up transitively via another dependency, trace the path bringing it in and verify the web application type.

Do not use dependency graph output alone to prove "WAR supported": the graph explains libraries, whereas external deployability is a **lifecycle contract** between the framework and container.

## 9. What Happens When Trying to Switch a WebFlux Build to WAR?

A common suggestion:

~~~xml
<packaging>war</packaging>
~~~

or in Gradle:

~~~groovy
plugins {
    id 'war'
}
~~~

These are **illustrative fragments**; they are not enough to form a working system. They only change the build tool's artifact type or add WAR tasks; they do **not** create a supported Servlet initializer for Boot WebFlux, swap Reactor Netty for external Tomcat, or turn a reactive application context into a Servlet/MVC context.

**Distinguish the outcomes:**

1. **Build succeeds**: means only that the compiler, packaging task, and build-time checks finished.
2. **Valid WAR structure**: means only that the ZIP/JAR layout meets basic archive criteria.
3. **External container deployment succeeds**: also requires proper bootstrap/lifecycle, a compatible Servlet container, matching dependencies, a live application context, and endpoints actually serving requests.
4. **Supported by Spring Boot**: is a matter of the framework's support contract stated in the docs. For **Boot WebFlux traditional WAR**, the documentation confirms it is **not supported** even if you can generate a `.war` file.

**Do not write a guide claiming "just add `SpringBootServletInitializer` to run a WebFlux WAR."** `SpringBootServletInitializer` serves the bootstrap path for **Servlet web applications**. For WebFlux, manually targeting a WAR means moving to a **custom Spring Framework adapter** setup, not standard Boot WebFlux WAR.

### 9.1. Do Not Copy MVC's `providedRuntime` Recipe into WebFlux

In a Spring MVC WAR guide, learners often see:

~~~text
Maven: spring-boot-starter-tomcat scope provided
Gradle: providedRuntime spring-boot-starter-tomcat
~~~

Those lines make sense for an MVC **external Servlet container WAR**. Putting them into a WebFlux POM/`build.gradle` without redesigning the web runtime **does not overcome** the Boot WebFlux WAR limitation. Netty and Tomcat are HTTP servers with different APIs; a dependency scope does not transform the dispatch model, Servlet bootstrap, or lifecycle.

## 10. If a WAR Is Mandatory: Contrasting with Proper Spring Boot MVC

To make the boundary concrete, here is a **non-WebFlux** alternative: a Spring MVC application deployable as a WAR per Spring Boot traditional deployment. It uses **`spring-boot-starter-web`**, the Servlet API, and **`SpringBootServletInitializer`**.

### 10.1. Java Main Class for MVC WAR

File **`src/main/java/com/example/mvc/MvcWarApplication.java`**:

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcWarApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(MvcWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(MvcWarApplication.class, args);
    }

    @RestController
    static class HelloController {
        @GetMapping("/hello")
        String hello() {
            return "MVC_WAR_OK";
        }
    }
}
~~~

This is a complete Java file for **a separate MVC WAR application**. The controller uses **`DispatcherServlet`**, not WebFlux `DispatcherHandler`. **`configure()`** lets the Servlet container start the Boot app from an external WAR; **`main()`** also supports the executable WAR path when Boot packaging is configured properly.

**This project structure is independent of `reactive-war-boundary`** above; do not put both main classes into the same project expecting the compiler to pick the right architecture automatically.

### 10.2. Complete Maven POM for MVC WAR

File **`pom.xml`** of project **`mvc-war-demo`**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-war-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

With **Spring Boot starter parent**, Maven configures the appropriate Maven WAR Plugin defaults and the Spring Boot Plugin's `repackage` goal. This WAR is a **Servlet/MVC WAR**, not a WebFlux WAR.

- **`packaging=war`**: sets the artifact type.
- **`spring-boot-starter-web`**: uses Spring MVC and embedded Tomcat by default.
- **`spring-boot-starter-tomcat`** with **`scope provided`**: lets the external servlet container supply the server rather than baking an embedded server into external deployment's classpath.
- **`SpringBootServletInitializer`**: bootstraps the app from the external container's servlet lifecycle.
- **`spring-boot-maven-plugin`**: can produce an executable WAR also runnable via **`java -jar`** when properly configured.

### 10.3. Equivalent Gradle `build.gradle` for MVC WAR

File **`settings.gradle`**:

~~~groovy
rootProject.name = 'mvc-war-demo'
~~~

File **`build.gradle`**:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

The Gradle **`war`** plugin supplies the **`providedRuntime`** configuration and WAR tasks; the Spring Boot plugin supports **`bootWar`** for an executable WAR when paired with the War plugin. **`providedRuntime`** is better than **`compileOnly`** for the embedded servlet server in the Servlet WAR model, because `compileOnly` is not placed on the test runtime classpath automatically.

This is a **completely different model** from the WebFlux JAR in sections 6–8, so you cannot simply take all of the MVC WAR's `build.gradle`, replace `starter-web` with `starter-webflux`, and assume it is valid.

### 10.4. Build and Inspect the MVC WAR

Maven:

~~~bash
./mvnw clean package
~~~

Expected artifact:

~~~text
target/mvc-war-demo-1.0.0.war
~~~

Gradle:

~~~bash
./gradlew clean bootWar
~~~

Expected artifact:

~~~text
build/libs/mvc-war-demo-1.0.0.war
~~~

You can use JDK **`jar tf`** to inspect the structure:

~~~bash
jar tf target/mvc-war-demo-1.0.0.war
~~~

or the corresponding Gradle path. In a Servlet app WAR, classes/resources normally live in **`WEB-INF/classes/`** and libraries in **`WEB-INF/lib/`**; an executable Boot WAR can also contain **`WEB-INF/lib-provided/`**.

**When running in external Tomcat:** the Tomcat/Servlet API version must be compatible with Spring Boot 3.3, and the URL may carry a **context path from the WAR name or container config**. Do not assume `GET /hello` sits at root: if deployed as **`mvc-war-demo`**, the URL may be **`/mvc-war-demo/hello`** depending on container config.

**When running via `java -jar`:** if the WAR was properly Boot-repackaged and the Java environment is compatible, it can run via **`java -jar target/mvc-war-demo-1.0.0.war`**, or the corresponding Gradle path. That does **not** make WebFlux traditional WAR supported.

## 11. Spring MVC + `WebClient`: A Middle Ground Worth Considering

A common need: the enterprise mandates deploying to an external Tomcat, yet the app wants to call downstream REST APIs non-blockingly or use Reactor. In that scenario, you can keep an **MVC/Servlet web server** and use **`WebClient`** as the HTTP client.

Example Maven dependency fragment inside an MVC WAR project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**This is not a complete POM.** Spring Boot selects **Spring MVC** when both Spring MVC and WebFlux are on the classpath in the standard case, because many teams add the WebFlux starter solely to use `WebClient`. Do not infer that an application runs WebFlux just because the WebFlux starter is present.

With Gradle, a corresponding fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

You still need proper WAR Servlet configuration like section 10 when actually deploying to an external container. **Do not confuse** adding a reactive client with switching the entire server stack to WebFlux. Spring MVC has a different request processing model, even when return types or HTTP clients use Reactor.

**Performance note:** Using `WebClient` does not automatically make all end-to-end processing non-blocking. If a controller calls **`.block()`** or servlet threads wait on results, measure actual concurrency and resource usage. Never pick WebFlux or MVC just because a library mentions the word reactive.

## 12. Embedded Tomcat for WebFlux Does Not Mean Tomcat WAR

Spring Boot WebFlux can use an embedded servlet-based web server instead of Reactor Netty when configured per Spring Boot docs. Example **illustrative Gradle fragment**:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
    implementation 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

This is a **fragment replacing the WebFlux starter line** in section 8's `build.gradle`, **not** a standalone `build.gradle`. The goal is to run **Spring Boot WebFlux on embedded Tomcat** via the non-blocking servlet adapter. In this setup you **keep the `java` plugin and `bootJar` task**; do not add the `war` plugin, do not build a traditional deployable WAR, and do not put Tomcat in `providedRuntime`.

For Maven, the equivalent idea is excluding **`spring-boot-starter-reactor-netty`** from **`spring-boot-starter-webflux`** and adding **`spring-boot-starter-tomcat`** to dependencies. When taking this route, inspect the dependency graph, web application type, and run HTTP integration tests because server interactions and versions can differ.

**When should you choose embedded Tomcat?** When operations or an integrated library has a valid Tomcat-related requirement while the Boot app still starts itself via a JAR. **Do not choose it** as a way to "work around" the WebFlux traditional WAR limitation.

## 13. Gradle/Maven Can Build a WAR, So What Should You Understand?

Build tools execute the tasks you ask them to run. If you use Maven `war` packaging or the Gradle `war` plugin in a project with WebFlux, it can produce a **format-valid WAR archive**. That does not automatically create:

- A Servlet initializer suited to Spring Boot WebFlux.
- Boot-supported mapping of `HttpHandler` to Servlet in traditional deployment mode.
- A mechanism to start Netty from an external WAR.
- External lifecycle startup/shutdown scope for a reactive server.
- A deployment environment tested and supported by the framework maintainers.

**Build success is not deployment support.** CI may pass the build while external Tomcat fails at startup or drops routes. That is an architectural risk; do not wait until staging to discover it.

Specifically, setting:

~~~properties
spring.main.web-application-type=reactive
~~~

can force Boot to choose the reactive application type when both MVC and WebFlux exist on the classpath. However, this property does **not** make WebFlux a supported Spring Boot WAR. The right verification is reading the support matrix and testing the **exact intended deployment method**.

## 14. Verification Table After Selecting an Architecture

| Item to Confirm | WebFlux JAR | MVC WAR |
| --- | --- | --- |
| HTTP server dependency | WebFlux starter; embedded Netty or compatible adapter server | Spring MVC starter; Servlet container |
| Primary packaging | JAR | WAR |
| Entry point | `SpringApplication.main`; Boot JAR launcher | `SpringBootServletInitializer` when external WAR |
| External Servlet WAR supported by Spring Boot? | **No** | **Yes**, when compatible |
| Static resources | `src/main/resources/static` | `src/main/resources/static` and Servlet webapp rules per config |
| Artifact check | `BOOT-INF/classes`, `BOOT-INF/lib` | `WEB-INF/classes`, `WEB-INF/lib` |
| HTTP testing | `RANDOM_PORT` `WebTestClient` | MockMvc / HTTP integration test / container deployment test |
| Run command | `java -jar ...jar` | Deploy `.war` externally or run executable `.war` when configured |
| Production pattern | Service/container image running JAR | Enterprise Servlet server when required by contract |

### Checklist for WebFlux JAR

1. Choose **`spring-boot-starter-webflux`**, without accidentally pulling **`spring-boot-starter-web`** onto the server classpath if the goal is a reactive application type.
2. Keep Maven **`packaging jar`** or Gradle **`bootJar`**; do not add WAR packaging just because deployment needs an environment.
3. Place static resources in **`src/main/resources/static`**, not `src/main/webapp`.
4. Run unit/integration tests with `RANDOM_PORT`.
5. Build the executable JAR and check **`BOOT-INF/classes`** and **`BOOT-INF/lib`**.
6. Run **`java -jar`** and hit the real endpoint.
7. For Docker/Kubernetes, use an image containing the proper Boot JAR and configure port, health check, graceful shutdown, and resource limits.
8. In architectures requiring an external WAR, document this support limitation clearly and make an explicit architectural decision.

### Checklist for MVC WAR

1. Choose **`spring-boot-starter-web`** and verify the app is genuinely a Servlet/MVC web application.
2. Extend **`SpringBootServletInitializer`** and configure **`configure()`** with the exact source class.
3. Choose **`packaging war`** or Gradle **`war`** + **`bootWar`**.
4. Mark the embedded servlet container as **`provided`** per plugin documentation.
5. Verify Java/Jakarta Servlet/Tomcat versions align with your chosen Spring Boot version.
6. Build the WAR and inspect `WEB-INF` and runtime dependencies.
7. Test deploying to an external container of the exact version and check context path and endpoints.
8. Do not treat having `WebClient` inside MVC as evidence that the server switched to WebFlux.

## 15. Common Errors and How to Handle Them

**Error 1 — Only changing packaging from `jar` to `war` in a WebFlux POM.** This changes the archive format without changing the bootstrap model. **Fix:** return to an executable JAR for Boot WebFlux, or switch to a supported Servlet/MVC WAR architecture.

**Error 2 — Adding `SpringBootServletInitializer` to a WebFlux main class.** The initializer is Boot's traditional mechanism for Servlet apps and does not register a supported WebFlux adapter inside an external container. **Fix:** do not treat the initializer as a supported Boot WebFlux WAR path.

**Error 3 — Seeing WebFlux run on embedded Tomcat and inferring external WAR deployment works.** Embedded Tomcat whose lifecycle Boot drives differs from external Tomcat bootstrapping a WAR. **Fix:** separate the two deployment models in architectural documentation.

**Error 4 — Thinking Reactor Netty can accept a WAR.** Netty is not a Servlet WAR container. **Fix:** use a Boot JAR artifact and start Netty from the application.

**Error 5 — Thinking every REST controller returning `Mono` is WebFlux.** Spring MVC can also handle several reactive return types. **Fix:** determine the stack from starters, context type, and auto-configuration, not method signatures alone.

**Error 6 — Both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, yet WebFlux tests do not start as expected.** With both on the classpath, Spring Boot normally prefers Spring MVC. **Fix:** remove the extra starter or explicitly set the reactive type when testing WebFlux; note that this property still does not make WAR supported.

**Error 7 — Adding `providedRuntime`/`provided` Tomcat in WebFlux assuming external WAR will run.** Dependency scope is only one part of Servlet WAR packaging and does not solve Boot reactive bootstrapping. **Fix:** choose the proper runtime approach.

**Error 8 — Placing static resources in `src/main/webapp` for WebFlux.** Boot WebFlux does not use that folder the way traditional WAR servlet apps do. **Fix:** use `src/main/resources/static` or resource locations supported by Boot WebFlux.

**Error 9 — Applying the Gradle `war` plugin, seeing the `war` task succeed, and recording "WebFlux WAR supported."** A valid archive does not guarantee framework runtime/deployment support. **Fix:** consult Spring Boot documentation and test the right startup mode.

**Error 10 — Picking `plain.jar` instead of `bootJar` when deploying a reactive app.** A plain JAR does not include the Boot loader or nested dependencies. **Fix:** select the exact executable Boot JAR and test `java -jar`.

**Error 11 — MVC WAR fails on deploy due to `javax.servlet` with Boot 3.x.** Spring Boot 3 uses the Jakarta namespace; older Servlet containers may be incompatible. **Fix:** choose a Jakarta Servlet container compatible with the Boot version, not just the Java version.

**Error 12 — MVC WAR returns 404 at `/hello` even though the app started.** External containers normally add a context path from the WAR filename. **Fix:** check the server deployment path, e.g. `/mvc-war-demo/hello` instead of `/hello`.

**Error 13 — Using `WebClient` and expecting every request to become non-blocking automatically.** A reactive client does not convert Spring MVC `DispatcherServlet` into WebFlux `DispatcherHandler`. **Fix:** benchmark real performance, avoid unintended blocking, and distinguish client from server stacks.

**Error 14 — Integration tests run only with `bootRun` without testing external WAR.** With MVC WARs, external Tomcat introduces more variables: classloaders, Servlet version, context path, provided libs. **Fix:** add a smoke test on the real target container.

**Error 15 — Masking the WAR limit by manually configuring `AbstractReactiveWebInitializer` and calling it standard Spring Boot WebFlux.** That is a Spring Framework API for custom setups, not Boot-supported traditional WAR deployment. **Fix:** explicitly document the architecture/framework, owner, and compatibility tests.

**Error 16 — Switching from MVC to WebFlux just to avoid thread blocking without checking JDBC libraries.** If code still uses JDBC or blocking APIs on the event loop, scalability may fall short of expectations. **Fix:** evaluate end-to-end reactivity, blocking work, and framework fit for the workload.

**Error 17 — Using an external WAR with unmanaged Netty lifecycle dependencies.** A Servlet container does not manage Reactor Netty inside an arbitrary WebFlux JAR/ZIP. **Fix:** use the Boot JAR embedded server model or a compatible Servlet architecture.

**Error 18 — Setting test property `spring.main.web-application-type=reactive` and treating that as production proof.** A running test context does not validate archive packaging or the traditional deployment lifecycle. **Fix:** verify the final artifact and real startup method in CI/staging.

## 16. Example Decision Based on Business Requirements

**Context:** A data-lookup service needs to handle many asynchronous HTTP calls, while operations traditionally deploys WARs onto a shared Tomcat.

**Option 1 — Keep WebFlux:** the organization allows running the app as an **executable JAR or container image**. The service embeds Netty (or another embedded server) and manages its own lifecycle. Appropriate release and monitoring processes must be added. This fits if the reactive server stack is an essential technical requirement.

**Option 2 — Keep external WAR:** the application switches to **Spring MVC** with the external Servlet container. It can still use `WebClient` for asynchronous client-side API calls, though request processing is not a WebFlux server. This fits if external WAR deployment is an unchangeable constraint.

**Option 3 — Manually use Spring Framework WebFlux on Servlet:** this is deep customization controlling `HttpHandler` adapters and bootstrap, outside the Boot WebFlux WAR contract. Choose it only with strong justification, thorough testing, and acceptance of maintenance cost.

**Decision question:** Does the system truly need a **reactive server stack**, or merely a **reactive HTTP client**? The answer shapes the architecture far more than renaming an artifact from `.jar` to `.war`.

## 17. Official References

- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html) — explicitly states Spring Boot WebFlux's WAR limitation and static resource rules.
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html) — WAR guide for Servlet-based applications and warning that WAR is unsupported for WebFlux.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html) — Spring MVC architecture, Servlet, and configuration.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html) — Netty/Tomcat/Jetty/Undertow as embedded runtimes.
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — `HttpHandler`, `ServletHttpHandlerAdapter`, and Framework-level WAR options.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — WebFlux/MVC detection and testing Boot web apps.
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html) — packaging executable archives.
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html) — `bootJar` and `bootWar` tasks.

**Final takeaway:** **Spring Boot WebFlux does not support traditional WAR deployment into an external Servlet container.** Use an **executable JAR/container image** for a WebFlux server, even when opting for embedded Tomcat instead of Netty. If external WAR deployment is mandatory, use the **Spring MVC/Servlet stack** and configure **`SpringBootServletInitializer` + `provided` servlet container** properly. **Custom Spring Framework WebFlux WARs** are a separate topic, not a support guarantee for Boot WebFlux WARs.