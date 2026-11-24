# Running an Executable JAR and Distinguishing It from WAR Deployment in Spring Boot

## 1. Objectives and Context

Spring Boot helps package a Java application into a deployable file. For web applications, the two common formats are **executable JAR** and **WAR**. The file extension alone does not tell the whole story of how it runs: a Spring Boot **executable WAR** can run with `java -jar` **and** be deployed into an external Servlet container, whereas a traditional WAR is typically only deployed into a container.

Questions this lesson must answer:

1. What does `./gradlew bootJar` create, and why can `java -jar application.jar` start an HTTP server without installing Tomcat separately?
2. How does `./gradlew bootWar` differ from `war`/plain WAR? When do you use `java -jar application.war`?
3. When deploying a WAR to an external Tomcat, who starts Spring, who owns the HTTP port, the URL context path, and the lifecycle?
4. Why are `SpringBootServletInitializer`, the `war` plugin, and `providedRuntime` needed?
5. Which files/directories, configurations, Java/Jakarta Servlet versions, and tests must you choose to avoid “runs in the IDE but fails on deploy” errors?

The exercises use **Java 17+, Spring Boot 3.3.13, Gradle 8.x**, and Spring MVC on Tomcat. The versions are only to keep the examples reproducible; production environments should choose a Spring Boot line that is still supported and receives security updates per organizational policy.

### Quick Decision Table

| Format | Command/where it runs | Who provides the web server? | Common use cases |
| --- | --- | --- | --- |
| Spring Boot **executable JAR** | `java -jar app.jar` | Embedded Tomcat/Jetty/Undertow or Netty inside the application | Standalone services, containers/VMs, CI/CD |
| Spring Boot **executable WAR** running standalone | `java -jar app.war` | Embedded Servlet container packaged in `WEB-INF/lib-provided` | Keeping a deployment path for both standalone and external WAR |
| Spring Boot **deployable WAR** | Copy/deploy WAR to a compatible external Tomcat/Jetty | **External** Servlet container | Centralized container-managed infrastructure, legacy platforms |
| Plain JAR from Gradle `jar` | Does not run by default with `java -jar` | Does not include an HTTP server/dependencies by default | Library or Java class archive |
| Plain WAR from Gradle `war` | External container | External container | Traditional WAR; not guaranteed to execute via `java -jar` |

**First conclusion:** JAR vs WAR is about *packaging and ownership of the web runtime*, not “JAR is backend, WAR is frontend”, nor “WAR is necessarily slower”. Startup cost, memory, and scalability also depend on server configuration, service count, dependencies, and workload.

## 2. What Is a Spring Boot Executable JAR?

A JAR is a standard Java ZIP archive. A **plain JAR** may contain classes/resources, but usually does not bundle runtime dependencies and has no Boot launcher. The Spring Boot Gradle plugin has a `bootJar` task that produces a **repackaged executable JAR** with dependencies inside in a specialized layout.

Structure of `packaging-demo.jar`:

~~~text
packaging-demo.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...   (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/
    │   ├── demo/packaging/PackagingApplication.class
    │   ├── demo/packaging/HelloController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   ├── tomcat-embed-*.jar
    │   └── ... other runtime dependencies
    ├── classpath.idx                   (if present)
    └── layers.idx                      (if layered)
~~~

The Spring Boot launcher knows how to read nested JARs in `BOOT-INF/lib` and app classes in `BOOT-INF/classes`, sets up a classloader, and then invokes the application's `main(String[])`.

In **Spring Boot 3.3**, the manifest typically contains:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

`Main-Class` is Spring Boot's launcher; `Start-Class` is your application class annotated with `@SpringBootApplication`. Do not confuse the two fields. The launcher package structure and name have changed between older and newer Boot versions; with Boot 3.3 use `org.springframework.boot.loader.launch.JarLauncher`, and do not copy the old name `org.springframework.boot.loader.JarLauncher` into a custom manifest.

### Why Can It Run with java -jar?

~~~text
java -jar packaging-demo.jar
    |
    v
JVM reads META-INF/MANIFEST.MF
    |
    v
Spring Boot JarLauncher
    |
    v
BOOT-INF/classes + BOOT-INF/lib/*.jar
    |
    v
PackagingApplication.main()
    |
    v
SpringApplication.run(...)
    |
    v
ApplicationContext + embedded Tomcat
    |
    v
HTTP listener, e.g. localhost:8080
~~~

Because the `spring-boot-starter-web` dependency brings embedded Tomcat by default, there is no need to install a separate Tomcat system service on the host. This is a **standalone JVM process** execution model, different from loading a WAR into an already-running container.

**Fat JAR/uber JAR does not mean all dependency classes are “shaded” together into a single directory.** A Boot executable JAR keeps many libraries as **nested JARs**, with a dedicated loader. Some tools using traditional classpath/ZIP handling do not understand the nested format; you should build/test the real artifact.

## 3. WAR and Web Application Archive

A WAR is also a ZIP-based archive, standardized for Servlet containers to accept web applications. For a Spring MVC Servlet application, a deployable WAR typically looks like:

~~~text
packaging-demo.war
├── META-INF/
├── org/springframework/boot/loader/...   (if bootWar)
└── WEB-INF/
    ├── classes/
    │   ├── demo/packaging/PackagingApplication.class
    │   └── ...
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   ├── spring-context-*.jar
    │   └── ... app runtime dependencies
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... embedded container runtime used for java -jar
~~~

In Spring Boot `bootWar`, `WEB-INF/lib-provided` is the special feature:

- When running `java -jar packaging-demo.war`, `WarLauncher` adds **`WEB-INF/lib` and `WEB-INF/lib-provided`** to the classpath → embedded Tomcat is available.
- When an external Tomcat deploys the WAR, the Servlet container **does not load** libraries from `WEB-INF/lib-provided` as runtime webapp libraries → it uses the Servlet engine provided by the external Tomcat, avoiding two colliding servlet containers.
- Regular dependencies in `WEB-INF/lib` are still loaded by the container for the application.

The manifest of an executable WAR in Boot 3.3 typically uses:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

**Not every `.war` file has `WarLauncher`.** A plain WAR built by the `war` task can be deployed to a container, but `java -jar plain.war` will not run as a standalone Boot app. Check the task that builds the file and its manifest.

## 4. Differences in Operational Responsibilities

| Aspect | Executable JAR | WAR in an external Servlet container |
| --- | --- | --- |
| Process | Each app is typically one JVM/process | One Tomcat JVM can host multiple WAR web contexts |
| HTTP port | App embedded server reads `server.port` | External container controls the connector port |
| Base context | App `server.servlet.context-path` for embedded Servlet server | WAR filename/context config of external Tomcat |
| Startup entry | `main` → `SpringApplication.run` | Container → `SpringBootServletInitializer.onStartup` |
| Shutdown | Signal/JVM process → Spring lifecycle | Context undeploy/redeploy/container lifecycle |
| Tomcat upgrade | Change dependency, rebuild/redeploy app | Upgrade external Tomcat + compatibility with all webapps |
| Classpath | Boot launcher and nested JARs | Container classloader + `WEB-INF/classes/lib` |
| Config | Env, args, config files, image settings | Env/app external config + container server config |
| Isolation | Separate instance, still shares host/kernel/network | WARs share JVM/container, separate classloaders but shared process risks |
| Scale | Add JVMs/pods/VMs | Replicate container or deploy multiple app contexts |
| Debug port clash | Duplicate `server.port` on the same host | Duplicate connector port, context path, or WAR deployment |
| JSP | Executable JAR does not support JSP per Boot docs | WAR with Tomcat/Jetty can support JSP |
| WebFlux Reactor Netty | JAR is appropriate | Traditional WAR deployment is **not supported by Boot** for WebFlux apps |

A WAR does not automatically guarantee complete classloader isolation: container/shared JVM/logging/temp dirs/JNDI/container libraries can create coupling. A JAR is not automatically secure either: secrets, file permissions, proxy, graceful shutdown, and CVE updates still must be managed.

## 5. Runnable Project A: Executable JAR with Spring MVC

### 5.1. File Structure

~~~text
packaging-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/demo/packaging/
│   │   │   ├── PackagingApplication.java
│   │   │   └── HelloController.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/demo/packaging/PackagingHttpTest.java
└── build/libs/                   (created after build)
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'packaging-demo'
~~~

`build.gradle` (complete file to build an executable JAR):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Set deterministic name so lab commands match the artifact.
tasks.named('bootJar') {
    archiveFileName = 'packaging-demo.jar'
}
~~~

Explanation:

- `java` plugin provides Java compilation and the `jar` task.
- `org.springframework.boot` plugin provides the `bootJar` task, adding the Boot loader + dependencies into the executable archive.
- `io.spring.dependency-management` uses dependency versions managed by Spring Boot; no need to declare every Tomcat/Spring/Jackson version individually.
- `spring-boot-starter-web` pulls in Spring MVC/Jackson + embedded Tomcat.
- `spring-boot-starter-actuator` provides the health endpoint for operational checks.
- `archiveFileName` sets the main artifact name to `packaging-demo.jar` (if omitted, the name usually includes the project name/version).
- `testImplementation` is only used during tests, not packaged into the production runtime.

### 5.2. Main Class

`src/main/java/demo/packaging/PackagingApplication.java`:

~~~java
package demo.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables component scanning from package `demo.packaging` and auto-configuration. Starter Web includes the Servlet web stack, so Spring Boot initializes embedded Tomcat when running `main`.

### 5.3. Controller

`src/main/java/demo/packaging/HelloController.java`:

~~~java
package demo.packaging;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping(value = "/hello",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "Hello from Spring Boot!";
    }

    @GetMapping("/hello/{name}")
    public Map<String, String> helloName(
            @PathVariable String name) {

        return Map.of(
                "greeting", "Hello, " + name,
                "packaging", "same-business-code");
    }
}
~~~

The same controller code works in an embedded JAR, executable WAR, and external Tomcat WAR. Business logic does not need to know the artifact extension, though **URL base context and lifecycle** will differ.

### 5.4. Properties

`src/main/resources/application.properties`:

~~~properties
# Used for embedded server when running java -jar / bootRun.
server.port=8080

# Embedded mode defaults to root context (/).
# Do not set context-path so you can see the difference when deploying an external WAR.

management.endpoint.health.probes.enabled=true
~~~

Port 8080 is the common Boot/Tomcat embedded default, declared explicitly for the lab. An external WAR is managed by the Tomcat connector port; `server.port=8080` in the app **does not open a second Tomcat** when loaded by an external container.

### 5.5. Build, Run, and Test with cURL

Requires Java 17+ and a suitable Gradle wrapper or compatible Gradle installation.

Linux/macOS:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/packaging-demo.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\packaging-demo.jar
~~~

If you do not have the `gradlew` wrapper yet, install a compatible Gradle version and generate the wrapper or run `gradle clean test bootJar`. Once the JAR is built, it does not depend on an open IDE.

Another terminal:

~~~bash
curl -i http://localhost:8080/hello
~~~

Expected response (headers vary by environment):

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

Hello from Spring Boot!
~~~

Spring may output Content-Type with a different charset/format; what is required here is HTTP 200 and the body `Hello from Spring Boot!`.

~~~bash
curl -i http://localhost:8080/hello/Linh
~~~

Equivalent JSON body:

~~~json
{
  "greeting": "Hello, Linh",
  "packaging": "same-business-code"
}
~~~

JSON key ordering and whitespace are not a contract unless explicit serialization is required. For Actuator:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Expected normal status is HTTP 200 and JSON containing `"status":"UP"` when the system is healthy; when dependencies are unhealthy the status may differ.

### 5.6. Changing the Port at Runtime Without Rebuilding the JAR

~~~bash
java -jar build/libs/packaging-demo.jar --server.port=9090
curl -i http://localhost:9090/hello
~~~

Or via environment variable:

~~~bash
SERVER_PORT=9090 java -jar build/libs/packaging-demo.jar
~~~

PowerShell:

~~~powershell
$env:SERVER_PORT = "9090"
java -jar .\build\libs\packaging-demo.jar
~~~

**Command argument ordering to remember:**

- `-Xmx512m` and `-Duser.timezone=UTC` are JVM options → place **before** `-jar`.
- `--server.port=9090` is a Spring application argument → place **after** the JAR name.
- `--spring.profiles.active=prod` is an application argument. In production, avoid passing raw passwords/secrets in command-line args because they can be exposed in process listings/diagnostics.

Example:

~~~bash
java -Xms128m -Xmx512m -Duser.timezone=UTC \
  -jar build/libs/packaging-demo.jar \
  --server.port=9090 --spring.profiles.active=prod
~~~

Only use the `prod` profile when the corresponding config/properties exist and have been tested; this example does not require creating an additional profile file.

## 6. Inspecting the Built JAR with JDK Tools

To avoid confusing a **plain JAR** with an executable Boot JAR, use:

~~~bash
jar tf build/libs/packaging-demo.jar
~~~

You should see `BOOT-INF/classes/`, `BOOT-INF/lib/`, the Spring Boot launcher, and `META-INF/MANIFEST.MF`. You can filter the output if `grep` is available:

~~~bash
jar tf build/libs/packaging-demo.jar | grep -E 'BOOT-INF|MANIFEST|JarLauncher'
~~~

On PowerShell:

~~~powershell
jar tf .\build\libs\packaging-demo.jar |
    Select-String "BOOT-INF|MANIFEST|JarLauncher"
~~~

Read the manifest with `unzip -p` on Linux/macOS if `unzip` is installed:

~~~bash
unzip -p build/libs/packaging-demo.jar META-INF/MANIFEST.MF
~~~

You will typically see two lines equivalent to:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

Meanwhile, a plain JAR may appear as `packaging-demo-1.0.0-plain.jar` if the `jar` task is invoked. It does not bundle `BOOT-INF/lib` and does not have the Boot launcher. If you run:

~~~bash
java -jar build/libs/packaging-demo-1.0.0-plain.jar
~~~

you may get `no main manifest attribute` or missing runtime dependencies depending on how the plugin/task is configured. **Do not assume every `.jar` is self-contained.** When CI produces multiple artifacts, select the exact file from the `bootJar` task and inspect its manifest.

### Why Is java -cp Not Equivalent?

~~~bash
# NOT the standard way to launch a Boot repackaged nested JAR:
java -cp build/libs/packaging-demo.jar demo.packaging.PackagingApplication
~~~

The standard classpath does not automatically load nested JARs in `BOOT-INF/lib`/classes. Use `java -jar` with the Boot launcher or a properly designed unpack/explicit classpath mechanism; do not “fix” it by manually extracting nested libraries into the JRE lib directory.

## 7. Running the Same Code as a WAR: Which Changes Matter?

To convert **project A** into a **deployable + executable WAR**, keep `HelloController.java`, `application.properties`, and the tests unchanged. Make **two changes**:

1. Have the main class extend `SpringBootServletInitializer` so an external container can initialize the application.
2. Have the build use the `war` plugin, `providedRuntime` for the embedded servlet runtime, and the `bootWar` task to create an executable WAR.

### 7.1. Complete WAR Main Class

**Replace the contents of** `src/main/java/demo/packaging/PackagingApplication.java` with:

~~~java
package demo.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class PackagingApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {

        return application.sources(PackagingApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

Exact explanation:

- **Running the executable WAR with `java -jar`**: the JVM calls `WarLauncher` and then the `main` method; `SpringApplication.run` starts embedded Tomcat.
- **Deploying the WAR to an external Tomcat**: Tomcat creates the web application context, the Jakarta Servlet startup mechanism calls `SpringBootServletInitializer.onStartup` (via Spring's `WebApplicationInitializer`), and `configure` declares the application sources; **the JVM does not need to execute the application's `main`**.
- `configure(...)` returns `application.sources(PackagingApplication.class)`, ensuring the root configuration is registered properly.
- Extending `SpringBootServletInitializer` does not mean every controller has to change. It is an adapter for traditional Servlet WAR deployment.
- If you only run an embedded JAR, you **do not need** to extend this initializer; Spring Boot Starter Web creates the embedded server via `SpringApplication.run`.

**Correct package in Boot 3.3:** `org.springframework.boot.web.servlet.support.SpringBootServletInitializer`. Do not copy `org.springframework.boot.web.support.SpringBootServletInitializer` from Boot 1.x examples.

### 7.2. Replacement Gradle build.gradle, Complete WAR Version

Replace the entire `build.gradle` with:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Important: servlet engine is included when running standalone,
    // while external Tomcat will provide its own runtime.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootWar') {
    archiveFileName = 'packaging-demo.war'
}
~~~

This is the `providedRuntime` syntax for **Spring Boot Gradle 3.3**. Some articles on Boot 4.x use a different artifact `spring-boot-starter-tomcat-runtime`; **do not mix dependency coordinates across major versions**.

**Common point of confusion:** `spring-boot-starter-web` remains the dependency for Spring MVC; you do not need to exclude `spring-boot-starter-tomcat` from `starter-web` in the Gradle 3.3 snippet above. Declaring the Tomcat dependency directly in the `providedRuntime` configuration per Boot documentation places the container runtime libraries into `WEB-INF/lib-provided`.

Why not use `compileOnly`? Per Spring Boot documentation, `providedRuntime` is present on the test runtime classpath so integration tests can run the web server; `compileOnly` alone does not provide the runtime dependency for tests and does not guarantee `lib-provided` packaging.

### 7.3. Build and Inspect Artifacts

~~~bash
./gradlew clean test bootWar
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test bootWar
~~~

Because the artifact filename was configured:

~~~text
build/libs/packaging-demo.war
~~~

The `bootWar` task produces the executable WAR. The Gradle `war` task may also produce a plain archive (usually with the `-plain` classifier). The Spring Boot Gradle plugin uses the `plain` suffix for the `war` task when distinguishing it from `bootWar`. **Do not mistakenly select `packaging-demo-1.0.0-plain.war` to test `java -jar`.**

Inspect:

~~~bash
jar tf build/libs/packaging-demo.war
~~~

Expected contents include `WEB-INF/classes/`, `WEB-INF/lib/`, `WEB-INF/lib-provided/`, Boot loader classes, and the manifest. `WarLauncher` reads the appropriate nested libraries when running standalone.

## 8. WAR Mode A: Running an Executable WAR with java -jar

Even though the artifact ends in `.war`, it can run standalone:

~~~bash
java -jar build/libs/packaging-demo.war
curl -i http://localhost:8080/hello
~~~

Expected HTTP 200 and body:

~~~text
Hello from Spring Boot!
~~~

**Explanation:** `WarLauncher` uses embedded Tomcat from `WEB-INF/lib-provided` when running standalone; Spring Boot accepts application arguments just like a JAR:

~~~bash
java -jar build/libs/packaging-demo.war --server.port=9090
curl -i http://localhost:9090/hello
~~~

In this mode, the web container is part of the application, and `server.port` takes effect. You do not have to install a separate Tomcat or copy the WAR into `webapps`. This is why “a WAR must always run in an external Tomcat” is a **false** conclusion for a Spring Boot executable WAR.

### Proper Boundaries

- Only a WAR with the proper manifest/Boot loader and packaged dependencies runs this way. A plain WAR does not have this behavior by itself.
- Do not run `java -jar` on the WAR and simultaneously deploy **the same WAR to an external Tomcat** on the same port 8080 thinking the two modes do not conflict; they are two separate processes/listeners.
- Do not assume a standalone WAR is a native image or container image; it is still a JVM application using a Java runtime on the host/container.
- If using JSP, an executable WAR on Tomcat or Jetty may be more suitable than a JAR (due to Spring Boot JSP limitations). However, you must test the specific resolver/JSP dependencies/context path.

## 9. WAR Mode B: Deploying to an External Tomcat 10.1

### 9.1. Prerequisites

Spring Boot 3.3 requires **Java 17 or higher**. The external Servlet container must be **Jakarta Servlet** compatible (Boot 3.3 docs specify Servlet 5.0+; embedded Tomcat 10.1 uses Servlet 6.0). For the lab, use an external **Tomcat 10.1** running on Java 17.

**Avoid Tomcat 9 with a Boot 3.3 Servlet WAR:** Tomcat 9 uses `javax.servlet.*`, whereas Spring Framework 6/Spring Boot 3 uses `jakarta.servlet.*`. Simply changing the extension from JAR to WAR does not fix namespace incompatibility; you may encounter class-not-found errors, failed context startup, or HTTP 404. Other enterprise app server containers must be checked for supported Jakarta Servlet API levels, classloaders, and versions.

### 9.2. Typical Deployment Process

Assume Tomcat 10.1 is installed with a valid `CATALINA_BASE`/`CATALINA_HOME`:

~~~text
<tomcat-home>/
├── bin/
│   ├── catalina.sh / catalina.bat
│   └── ...
├── conf/
├── logs/
└── webapps/
    └── packaging-demo.war
~~~

Stop the standalone process running on port 8080. Copy `build/libs/packaging-demo.war` into the external Tomcat `webapps` deployment directory:

~~~bash
cp build/libs/packaging-demo.war /opt/tomcat/webapps/packaging-demo.war
~~~

This is an **illustrative path**. Tomcat may be installed elsewhere; corporate environments may manage deployments via a manager, service/container orchestration, or a read-only image. Do not copy directly onto a production server without authorization and a rollback plan.

Start Tomcat appropriately for your environment (e.g., `bin/catalina.sh run` or service manager). With Tomcat's default connector on port 8080 and the context name derived from `packaging-demo.war`:

~~~bash
curl -i http://localhost:8080/packaging-demo/hello
~~~

The body is still:

~~~text
Hello from Spring Boot!
~~~

**The different URL path is critical:**

- `java -jar packaging-demo.war` with embedded Tomcat root context → `/hello`.
- `packaging-demo.war` deployed to external Tomcat by default → `/packaging-demo/hello`.
- If deployed as `ROOT.war`/appropriate root context path → `/hello`.
- If the container is configured with a different context, you must use the actual context URL rather than guessing from the filename.

This is a frequent cause of “JAR works OK but WAR returns 404”: the tester calls `/hello` instead of `/packaging-demo/hello`. Do not rush to change `@GetMapping` on the controller.

### 9.3. Who Owns the Port and Context Path?

In a **standalone JAR/executable WAR**, the application owns the embedded server, so:

~~~properties
server.port=8080
server.servlet.context-path=/shop
~~~

typically yields the endpoint `/shop/hello`.

In a **WAR on external Tomcat**, the external Tomcat owns the connector port and webapp context. `server.port` in Spring Boot **is not where you change the external Tomcat port**; the port is configured in the server/container, such as Tomcat's `conf/server.xml` or the corresponding management system. The base context path is determined by the deployment name/context descriptor, not by `server.servlet.context-path` meant for the embedded server.

To change the external Tomcat port, edit the container configuration properly (or map it at a reverse proxy); to use a root URL, deploy as the root context; do not change `server.port` expecting external Tomcat to open a second socket.

### 9.4. Illustrative External Tomcat Docker Image

To practice with an isolated Tomcat without installing the server directly on the host, you can use a supported and verified Tomcat 10.1/JRE17 image. Reference Dockerfile:

~~~dockerfile
FROM tomcat:10.1-jre17-temurin

# Dedicated container for the lab; do not use for shared enterprise Tomcat.
RUN rm -rf /usr/local/tomcat/webapps/*

COPY build/libs/packaging-demo.war \
     /usr/local/tomcat/webapps/packaging-demo.war

EXPOSE 8080
~~~

Build/run example (name the Dockerfile above `Dockerfile.tomcat`):

~~~bash
docker build -f Dockerfile.tomcat -t packaging-demo:external-war .
docker run --rm -p 8080:8080 packaging-demo:external-war
curl -i http://localhost:8080/packaging-demo/hello
~~~

You must **stop the standalone JAR/WAR process on port 8080 first**. Registry tags, base digests, security patches, and JDK/runtime must be verified in the deployment environment; production typically pins an image digest rather than a floating tag. Do not delete webapps directories on a shared enterprise Tomcat like the `RUN` line in this lab.

A context deployed as `ROOT.war` will sit at the root path; session cookie, proxy, TLS, and routing policies still need to be configured on the container.

## 10. Maven Case: Same Principles, Different Syntax

The examples above use Gradle. With Maven, `pom.xml` specifies:

~~~xml
<packaging>jar</packaging>
~~~

for an executable JAR, combined with the Spring Boot Maven plugin `repackage` goal; typically `mvn clean package` produces a JAR runnable with `java -jar target/....jar` when the plugin is configured via the Boot parent or explicit execution.

To build a WAR deployable to an external container:

~~~xml
<packaging>war</packaging>
~~~

When using `spring-boot-starter-web` with Tomcat, declare Tomcat in `provided` scope:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

And provide `SpringBootServletInitializer` as in section 7. Depending on plugin configuration, an executable WAR can also be repackaged and run with `java -jar`.

**These are Maven configuration snippets, not a complete `pom.xml`**; use a consistent Spring Boot parent/BOM, Maven plugin, and project coordinates. Do not conclude that setting `<packaging>war</packaging>` alone is enough: missing the initializer or provided server scope can still fail when an external container loads the webapp.

## 11. Plain WAR, Executable WAR, and Library JAR: Distinguishing by Task

The Spring Boot Gradle plugin defines:

| Task | Typical output | Purpose |
| --- | --- | --- |
| `bootJar` | `app.jar` | Executable Boot JAR |
| `jar` | `app-...-plain.jar` | Plain classes/resources JAR |
| `bootWar` | `app.war` | Executable Boot WAR; deployable when properly configured |
| `war` | `app-...-plain.war` | Plain WAR for Servlet containers |
| `bootRun` | Does not require creating an archive | Run app from classes/dependencies during dev |
| `build` | May run tests + assemble artifacts | CI build; verify which artifact is produced |
| `test` | Test reports/classes | Unit/integration tests on build classpath; does not automatically test artifact deployment |

`bootWar` is only available when the Gradle `war` plugin is applied. `bootJar` is available when the `java` plugin is applied alongside the Spring Boot plugin; in a project that has the `war` plugin, how Gradle picks default archives/tasks can differ from the initial JAR project. For this lesson, **explicitly invoke `bootJar` or `bootWar`** and pick the exact artifact file to avoid mix-ups.

A `-plain.jar` file does not run standalone because it lacks the Boot launcher/nested dependencies; a `-plain.war` file can be deployed to Tomcat but does not run as an executable WAR. This is why CI/CD should not use wildcards like `build/libs/*` to deploy when multiple files exist.

### CI Artifact Rules

- JAR CI job: primary artifact `build/libs/packaging-demo.jar` produced by `bootJar`.
- WAR CI job: primary artifact `build/libs/packaging-demo.war` produced by `bootWar`.
- Run checksums/signatures/SBOMs on **the exact file that will be deployed**, do not scan `-plain` and deploy the boot archive.
- Test running `java -jar` from the built artifact rather than only testing `bootRun` from classes.
- If deploying to an external Tomcat, test `packaging-demo.war` on a real external container.

## 12. Verifying with a Spring Boot Integration Test

The following test works for both project A (JAR) and project B (WAR) if Servlet Tomcat test dependencies are configured properly.

`src/test/java/demo/packaging/PackagingHttpTest.java`:

~~~java
package demo.packaging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class PackagingHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void helloEndpointWorks() {
        ResponseEntity<String> r =
                http.getForEntity("/hello", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo(
                "Hello from Spring Boot!");
    }

    @Test
    void greetingEndpointHasExpectedField() {
        ResponseEntity<String> r =
                http.getForEntity("/hello/Linh", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody())
                .contains("Hello, Linh");
    }

    @Test
    void unknownRouteReturns404() {
        ResponseEntity<String> r =
                http.getForEntity("/not-found", String.class);

        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
~~~

### What Does This Test Prove?

- The Boot context loads.
- The embedded Servlet server opens a real HTTP port (random port) and controller routing works.
- Two endpoints return the expected contract, and an unknown path returns 404.

**It does not prove** that the WAR deploys on an external Tomcat: JUnit `@SpringBootTest(RANDOM_PORT)` starts an embedded server using the test runtime classpath, not an external Tomcat. You must have a **second integration test** that deploys the WAR into an external container or Dockerized Tomcat, calls `/packaging-demo/hello`, and inspects logs/health.

Because `providedRuntime` remains on the test runtime classpath, Boot WAR tests can start embedded Tomcat normally. This is a practical advantage over `compileOnly`.

## 13. Automated Deployment: A Minimum Test Matrix

| Case | How to run | Request to try | What it verifies |
| --- | --- | --- | --- |
| Dev classes | `./gradlew bootRun` | `GET /hello` | Logic works, but does not prove the archive |
| Executable JAR | `java -jar packaging-demo.jar` | `GET /hello` | Boot launcher, nested libs, embedded port |
| Executable WAR standalone | `java -jar packaging-demo.war` | `GET /hello` | WarLauncher and `lib-provided` work |
| External Tomcat WAR | Deploy `packaging-demo.war` | `GET /packaging-demo/hello` | Servlet initializer, container classloader, and context |
| External WAR root | Deploy `ROOT.war`/root context | `GET /hello` | Proper context path |
| Port override | `--server.port=9090` after `java -jar` | `GET :9090/hello` | Spring embedded port property |
| External port override | Change external Tomcat connector | `GET :customPort/packaging-demo/hello` | Container owns port, not Boot property |
| Missing resource | Wrong context path | `GET /hello` on non-root external | Expected 404; do not rush to change controller |
| Graceful stop | SIGTERM to standalone JVM | In-flight request, new request | Stop lifecycle and LB/proxy behavior |
| Security | Real auth contract | Authorized/unauthorized paths | Filters/servlet mappings equivalent across both modes |

When testing an external WAR, check startup logs for context deployment errors; HTTP 404 does not always mean a missing business controller route—the application may have failed startup completely.

### Checking Only “200” Is Not Enough

For real APIs, also verify:
- Authentication/authorization, CSRF, CORS.
- `@ControllerAdvice` error responses and static resources.
- Session persistence/cookies.
- Large uploads, streaming/SSE, and WebSocket (when used).
- Database connectivity/transactions and migrations.
- Proxy forwarded headers/HTTPS redirects.
- Health readiness/liveness, graceful shutdown.
- Classpath/resource loading from a nested archive.

These layers can behave differently between an app-owned embedded server and a shared external Tomcat.

## 14. When Should You Prefer an Executable JAR?

An executable JAR is usually a good fit if:
- You want to release a single artifact bundling runtime dependencies, run on Java 17+, and manage ports via configuration.
- Each service is independent with its own lifecycle/rolling deployment.
- You want to package containers following the **one Java process per application** principle.
- Kubernetes/VM infrastructure already provides reverse proxies/LBs and does not require a centralized WAR container.
- You want easy management of Spring Boot + embedded Tomcat versions alongside the artifact.
- You use Spring WebFlux running on embedded Reactor Netty.
- You have no legacy JSP requirement tied to Servlet WAR deployment.

The benefit is that the application owns its embedded server: container version upgrades happen via your dependency/build pipeline; instrumentation/Actuator are easy to set up and test close to production runtime. However, you must still properly manage vulnerability scanning, TLS/proxies, process signals, memory, logs, health, and autoscaling.

JAR does not mean **no server is needed**: embedded Tomcat/Jetty/Undertow/Netty is still an HTTP server; only where it is instantiated and who manages its version differ.

## 15. When Should You Deploy a WAR to an External Container?

External WAR deployment makes sense if:
- The enterprise has shared, centrally managed Tomcat/Jakarta Servlet container infrastructure.
- Policy requires deploying WARs to servers operated/updated/patched centrally.
- Legacy JSP/Servlet/JNDI applications are designed around the app server's context/classloader.
- You need a single WAR artifact that supports gradual migration to standalone alongside legacy deployment.
- The organization already has processes for WAR/version/context management and safe rollouts.

Trade-offs:
- The web container runtime and JVM are often updated **separately** from the application, requiring a compatibility matrix.
- Multiple webapps in the same JVM share memory/GC/process risks; a failure or container update can affect multiple apps.
- Root/context paths differ, and there may be global filters, JNDI, and external JVM properties.
- Managing secrets, configuration, and classloaders can be more complex.
- Not a suitable default for Spring WebFlux apps running on Netty; Boot 3.3 traditional WAR deployment does not support WebFlux apps.

**Do not choose WAR just because it is called “enterprise”.** Choose based on the runtime contract and real operational requirements.

## 16. Spring WebFlux and the Important WAR Exception

Spring WebFlux typically runs on Reactor Netty with the dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

It can be packaged as an executable JAR and run:

~~~bash
./gradlew bootJar
java -jar build/libs/your-reactive-app.jar
~~~

The example filename depends on the project's `archiveFileName`; the path is illustrative.

**Per the Spring Boot 3.3 Traditional Deployment guide**, WAR deployment is **not supported for WebFlux applications** because WebFlux does not depend directly on the Servlet API and deploys by default via embedded Reactor Netty.

Key distinctions:
- Spring MVC servlet controllers can use reactive return types (`Mono`/`Flux`) while still running on the Servlet stack; such an app can have a valid WAR path if designed around MVC.
- A pure Spring WebFlux application with Reactor Netty cannot be “turned into a deployable external WAR” merely by adding the `war` plugin and `SpringBootServletInitializer`.
- If both `starter-web` and `starter-webflux` are present, Boot 3.3 usually selects the MVC Servlet application (unless overridden). Verify the actual runtime with tests/context type.

## 17. JSP and View Rendering: Distinct Limitations

Spring Boot 3.3 docs state:

- **JSP is not supported when using an executable JAR.**
- With Tomcat or Jetty, using WAR packaging can support JSP; an executable WAR run with `java -jar` can also be suitable.
- Undertow does not support JSP per Boot guidance.

If a project uses JSP under `WEB-INF/jsp`, switching to an executable JAR can break the view resolver even while REST endpoints continue working. Migrate to a template engine (Thymeleaf, FreeMarker, etc.) or use WAR and test JSP compilation/resolution.

Do not assume every `.html` file requires a WAR: Spring MVC REST APIs, static HTML/CSS/JS, and popular template engines still work in a Boot executable JAR when resources are structured properly.

## 18. Classpath and Resources When Running from an Archive

In the IDE, resources may sit on the filesystem under `src/main/resources`. After building, they go into `BOOT-INF/classes` (JAR) or `WEB-INF/classes` (WAR).

**Portable pattern:**

~~~java
package demo.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ResourceReader {

    public String readClasspathResource() throws IOException {
        try (InputStream in = getClass().getResourceAsStream(
                "/example-data.txt")) {

            if (in == null) {
                throw new IOException("Classpath resource not found");
            }
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

This file is a standalone Java utility; **it only yields results if** you add `src/main/resources/example-data.txt` to the project and call the method from code. It is not a runnable endpoint automatically exposed by the snippet.

Use `getResourceAsStream` or `ClassPathResource.getInputStream()`. Avoid:

~~~java
// Wrong when treating a packaged resource like a file in the source tree:
new java.io.File("src/main/resources/example-data.txt");

// Unsafe with nested JAR URLs if requiring a regular File:
new org.springframework.core.io.ClassPathResource(
        "example-data.txt").getFile();
~~~

`ClassPathResource.getFile()` requires the resource to be a filesystem file; inside an executable JAR it may reside inside a ZIP/nested JAR with no regular filesystem path. `new File(...)` also depends on the working directory rather than the classpath. Read via streams to stay portable across `bootRun`, JAR, and WAR.

### Some Nested JAR Limitations

Libraries that use `File`, scan the classpath, or use custom classloaders may assume classes live on the filesystem. The Spring Boot launcher supports nested JARs, but applications must test components like Jersey package scanning, reflection, template/resource loading, and JAXB/services when packaged.

Do not “fix” this by extracting the entire JAR into a system directory and modifying the JVM classpath unless required. Check `requiresUnpack`/layertools or official resource loading mechanisms when a real library does not support nested archives.

## 19. Dockerizing an Executable JAR

`Dockerfile` for the built JAR project:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /opt/app
COPY build/libs/packaging-demo.jar /opt/app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Build/run:

~~~bash
./gradlew clean test bootJar
docker build -t packaging-demo:jar .
docker run --rm -p 8080:8080 packaging-demo:jar
~~~

HTTP:

~~~bash
curl -i http://localhost:8080/hello
~~~

**A container image is not synonymous with an executable JAR:** an image is just a way to distribute a runtime, and can contain an executable JAR, a standalone executable WAR, or an external Tomcat deploying a WAR.

In production:
- Pin the base image digest and apply CVE updates.
- Run non-root when possible, and set appropriate JVM memory/container limits.
- Supply secrets via a dedicated management mechanism; never hardcode them in the JAR/Dockerfile.
- Use exec-form `ENTRYPOINT` so Java receives SIGTERM, and configure graceful shutdown and Pod readiness.
- Collect stdout/stderr logs with a collector; keep external state in appropriate DBs/volumes.
- Use layered JARs/buildpacks if you want to optimize Docker caching/startup/size; not required for the JAR vs WAR lesson.

### Layered JAR

Spring Boot Gradle `bootJar` can generate `BOOT-INF/layers.idx` to describe application/dependency layers. Docker buildpacks or layer extraction leverage caching when code changes while dependencies stay unchanged. Layering **does not change** HTTP semantics or JVM runtime requirements. Do not assume a layered JAR is already a deployed Docker image; it is still an archive.

## 20. Java Processes and Production Operations

A command:

~~~bash
java -Xms256m -Xmx768m -jar packaging-demo.jar \
  --spring.profiles.active=prod --server.port=8080
~~~

still requires:
1. A service manager/systemd or container runtime to restart on crash.
2. Reverse proxy/TLS termination or properly configured SSL/TLS listener.
3. Appropriate health endpoints/readiness and timeouts.
4. Environment configuration/secrets separated from the immutable artifact.
5. Log aggregation/metrics/tracing, thread/connection pools.
6. Graceful shutdown so in-flight requests drain.
7. File descriptor/CPU/memory limits, autoscaling, and network firewalling.
8. Rollback and schema/data compatibility.

With an external WAR, most **process-level** concerns are managed by the Tomcat/container operator, while the app remains responsible for business state, HTTP security, resilience, and data correctness.

### Graceful Shutdown in an Embedded App

Example:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

When the Java process receives SIGTERM, Boot gets a chance to stop accepting new requests and wait for in-flight requests. With a WAR in an external container, shutdown follows the lifecycle of the webapp context/external Servlet container, so do not assume the embedded server's process-level graceful setting controls an external Tomcat connector.

In Kubernetes, `terminationGracePeriodSeconds` must cover `preStop` and application shutdown. Standalone JAR/WAR uses process signals, whereas an external WAR must drain at the corresponding container/LB, and may share a server process with other applications.

## 21. Common Errors and How to Identify the Root Cause

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| `no main manifest attribute` | Running a plain JAR/WAR, not a boot archive | `jar tf`/manifest; `bootJar`/`bootWar` tasks |
| `ClassNotFoundException` JarLauncher | Archive/manifest built incorrectly, old Boot version path | Boot 3.3 `Main-Class` is `org.springframework.boot.loader.launch.JarLauncher` |
| `ClassNotFoundException` Spring class | Used plain JAR without dependencies | Deploy `bootJar`/`bootWar` instead of `jar` |
| `Address already in use: bind` | Two standalone processes on the same port | `server.port`, run each app on a different port, stop old instance |
| `GET /hello` is 404 on external Tomcat | URL missing `/packaging-demo` context | Call `/packaging-demo/hello` or configure root context properly |
| `server.port` does not change external WAR port | Port is managed by external container | Edit Tomcat connector/proxy, not app property |
| WAR deploys but fails to start | Missing `SpringBootServletInitializer` | Extend it and configure sources properly |
| `NoClassDefFoundError: jakarta/servlet/...` | Container not Jakarta Servlet compatible, missing libs | Tomcat 10.1/Servlet 5.0+, Boot 3.3, Java 17 |
| `javax.servlet` error running Boot 3 | Legacy Java EE dependencies/container | Remove incompatibility, upgrade/migrate to Jakarta |
| Embedded Tomcat conflicts with external | `provided` scope not configured properly | `providedRuntime`, inspect `WEB-INF/lib-provided` |
| WAR runs standalone OK, fails externally | Only embedded tests run, different classloader/context | Test on a real external container |
| WAR `@SpringBootTest` missing server | Used `compileOnly` instead of `providedRuntime` | `providedRuntime` keeps runtime on test classpath |
| JSP view fails in executable JAR | JSP not supported in this packaging | WAR on Tomcat/Jetty or switch template engine |
| WebFlux WAR deployment fails | Boot 3.3 does not support traditional WebFlux WAR | Executable JAR with Reactor Netty |
| `FileNotFoundException` for resource after build | Using `src/main/resources` path or `getFile()` | Classpath stream, `jar tf` to check resource |
| Container 8080 running but unreachable from host | Port not published/mapped, firewall | `docker run -p`, network/port config |
| Wrong HTTPS redirect URL | Forwarded headers/context path/proxy trust | Test proxy setup and trusted headers |
| Two similarly named JARs in `build/libs` | Boot archive vs `-plain` artifact | Pick explicit artifact from task |
| WAR redeploys context and loses sessions | Container redeploy, in-memory sessions | Spring Session/shared store or stateless |
| Upgrading external Tomcat breaks other apps | Multiple WARs share one JVM/runtime | Compatibility matrix, staging test, rollback |
| Health UP but HTTP endpoint fails | Health check does not test full request path | Curl/integration tests through public routing |

Do not edit the controller immediately when you see a 404. First verify **which process is actually running, which packaged file was deployed, the context path, the port, and Tomcat logs**.

## 22. Choosing JAR/WAR in Interviews and System Design

**Scenario A — Small REST microservice deployed on Kubernetes.** Choose an executable JAR or a container image from the JAR. The service owns its HTTP listener and rolls out independently; test `bootJar`, `java -jar`, health, graceful stop, and retry/idempotency.

**Scenario B — Enterprise system with shared enterprise Tomcat requiring WAR.** Choose a deployable WAR, extend `SpringBootServletInitializer`, use `providedRuntime` on a Jakarta-compatible container, test the context path and servlet filters/JNDI/classloading. If you also want standalone runs in CI, use the executable WAR from `bootWar`.

**Scenario C — Legacy JSP.** WAR is more appropriate than JAR due to Boot JSP limitations; consider migrating to a modern template engine. Do not assume Undertow supports JSP.

**Scenario D — Reactive API on Netty.** Choose an executable JAR; do not force external WAR deployment for Boot 3.3 WebFlux.

**Scenario E — Starting from an old Spring MVC WAR.** Migrate incrementally to a compatible Spring Boot WAR first to minimize operational changes, then move to standalone JAR and containerization when ready. Test sessions, classloaders, static files, external config, and URLs.

### A Concise Memorable Summary

> An executable JAR bundles the Boot launcher + dependencies + embedded web server and runs with `java -jar`. A Spring Boot executable WAR adds the Servlet webapp layout and can run with `java -jar` or deploy into an external container when configured with `SpringBootServletInitializer` and `providedRuntime`. External Tomcat owns the port/context/lifecycle, while a standalone executable JAR/WAR lets Spring Boot manage the server itself.

## 23. Pre-Handoff Artifact Checklist

- [ ] Java runtime is at least Java 17 and Spring Boot/Gradle versions are compatible.
- [ ] Identified the artifact from `bootJar` or `bootWar`, without accidentally deploying a plain archive.
- [ ] Verified manifest `Main-Class` and `Start-Class` match Boot 3.3.
- [ ] JAR contains `BOOT-INF/classes` + `BOOT-INF/lib` and Boot launcher.
- [ ] WAR contains `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` when using `providedRuntime`.
- [ ] Main class has `public static void main` for standalone execution.
- [ ] External WAR has `SpringBootServletInitializer.configure` and a Jakarta-compatible Servlet container.
- [ ] Tested `java -jar` on the real built artifact.
- [ ] Tested WAR on a real external Tomcat, not only embedded `@SpringBootTest`.
- [ ] URLs match root context vs WAR context name.
- [ ] Port config/SSL/proxy match the owner: embedded server or external Tomcat.
- [ ] Static resources/templates/JSP and classpath resource loading work from the packaged artifact.
- [ ] No legacy `javax.servlet` artifacts conflict with Boot 3 `jakarta.servlet`.
- [ ] Sessions, security filters, CORS/CSRF, headers/redirects verified in both modes.
- [ ] Tested restart, graceful shutdown, and in-flight requests.
- [ ] Artifact is signed/scanned/versioned with checksums and a rollback plan.
- [ ] Container/VM has managed logs, metrics, health, network, CPU/memory, and secrets.
- [ ] CI artifact path is explicit, without wildcards that could pick `-plain`.
- [ ] Read the documentation for the exact Spring Boot version of the project.

## 24. Self-Check Exercises

**1.** Which Gradle task builds a Spring Boot executable JAR?

**Answer:** `bootJar`, provided by the Spring Boot Gradle plugin when using the Java plugin. `jar` is the plain JAR task and does not include the Boot loader/dependencies by default.

**2.** Can a Spring Boot executable WAR run with `java -jar`?

**Answer:** Yes, if built with `bootWar` and the embedded server runtime is in `WEB-INF/lib-provided`. A plain WAR usually cannot run standalone.

**3.** Who decides the HTTP port of a WAR deployed to an external Tomcat?

**Answer:** The external Tomcat connector/container config, not the embedded server's `server.port`.

**4.** Is `packaging-demo.war` in Tomcat `webapps` at the root? What is the URL for `@GetMapping("/hello")`?

**Answer:** Typically `/packaging-demo/hello`, because the WAR name defines the context. A root URL requires `ROOT.war` or explicit root context configuration.

**5.** Why is `SpringBootServletInitializer` needed?

**Answer:** So an external Servlet container initializes the Spring application context when the WAR is deployed, rather than the JVM calling the `main` method directly.

**6.** What is the role of `providedRuntime` in a Boot Gradle WAR?

**Answer:** It places the embedded servlet container runtime in `WEB-INF/lib-provided` for standalone execution without conflicting with an external container, while keeping the dependency on the test runtime classpath.

**7.** `spring-boot-starter-web` includes embedded Tomcat—so to deploy an external WAR, must you delete `starter-web`?

**Answer:** No. Keep `starter-web` and declare `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` per the Boot 3.3 guide.

**8.** Can a Spring Boot 3.3 WAR be deployed directly to Tomcat 9?

**Answer:** Not compatible: Tomcat 9 still uses Java EE `javax.servlet`, while Boot 3 uses Jakarta. Use a compatible Jakarta Servlet container, such as Tomcat 10.1 in the lab, and Java 17+.

**9.** Should WebFlux Reactor Netty be switched to an external WAR when deploying?

**Answer:** No; Boot 3.3 does not support traditional WAR deployment for WebFlux apps. Use an executable JAR and embedded Reactor Netty.

**10.** Is a Boot executable JAR a single “shaded” JAR of all classes?

**Answer:** No. Spring Boot typically uses nested JARs in `BOOT-INF/lib` and the `JarLauncher` classloader.

**11.** Why does `new File("src/main/resources/data.txt")` work in the IDE but fail after packaging?

**Answer:** That is a filesystem path in the source tree, not a classpath resource inside the ZIP archive. Use `getResourceAsStream` or `ClassPathResource`'s input stream.

**12.** If `@SpringBootTest(RANDOM_PORT)` passes for a WAR, do you still need to test on external Tomcat?

**Answer:** Yes. Embedded integration tests do not verify external Servlet container startup, classloaders, context paths, or deployment-specific filters.

**13.** Does JSP work in a Spring Boot 3.3 executable JAR?

**Answer:** Not supported per Boot docs; a WAR on Tomcat/Jetty is the appropriate choice if JSP is required.

**14.** What should you check first on a `no main manifest attribute` error?

**Answer:** Check whether you are running `-plain.jar` or `-plain.war`; inspect the manifest and build using `bootJar`/`bootWar`.

## 25. Official Documentation

- [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer`, WAR plugin, `providedRuntime`, WebFlux limitations.
- [Spring Boot 3.3 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootJar`/`bootWar`, plain archives, `providedRuntime`, and `lib-provided`.
- [Spring Boot 3.3 — Executable Jar Format / Nested JARs](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib`, `WEB-INF/lib-provided`.
- [Spring Boot 3.3 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html): `JarLauncher`, `WarLauncher`, `Main-Class`/`Start-Class`.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+, Servlet 5.0+, Tomcat 10.1/Jetty 12/Undertow 2.3.
- [Spring Boot 3.3 — SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): `onStartup`/`configure` contract.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): embedded Servlet servers, JSP restrictions, and Servlet initializer behavior.
- [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): `bootRun`/`java -jar` workflows.
- [Spring Boot 3.3 — Dockerfiles](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html): executable archives in containers, layers.
- [Apache Tomcat 10.1 — Deployment](https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html): context path and deploying WARs into `webapps`.

**Final note:** Both JAR and WAR can be Spring Boot executable archives. `bootJar` gives a self-running app with an embedded server; `bootWar` can produce a **dual-mode** artifact: `java -jar` (`WarLauncher` + `lib-provided`) or deployment to an external Tomcat (`SpringBootServletInitializer` + container-owned port/context). The right artifact, the right Java/Jakarta versions, the right URL/context path, and testing on the real runtime determine a successful deployment.
