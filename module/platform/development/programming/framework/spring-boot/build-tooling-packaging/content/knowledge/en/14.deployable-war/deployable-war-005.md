# Distinguishing Traditional Deployable WARs from Executable `java -jar` WARs in Spring Boot

## 1. The Problem: Same `.war` Extension, Two Startup Modes

In the Java ecosystem, a **WAR (Web Application Archive)** is an archive format for packaging web applications to deploy into a **servlet container/application server**. Traditionally, a `.war` file is deployed by an **external container** (such as Apache Tomcat), which loads servlets, manages HTTP ports, and controls the application lifecycle. Spring Boot, however, also supports an **executable WAR**: still a WAR deployable in the traditional way, while also packaging the **Spring Boot Loader** and appropriate dependencies so it can run directly:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war
```

Therefore, the question is not "Can every WAR run with `java -jar`?", but rather **"Which WAR was built, by which plugin, and does it have the launcher and standalone dependencies?"**

| Criterion | Traditional Deployable WAR | Spring Boot Executable WAR |
|---|---|---|
| Primary launch method | Copy/deploy onto a servlet container | `java -jar app.war`; can also deploy to a compatible container |
| Who opens the HTTP port? | External container | Embedded servlet container when running `java -jar` |
| Who creates the Spring application context? | Servlet initialization path (`SpringBootServletInitializer` or equivalent) | `main` invoked by Boot Launcher, then `SpringApplication.run` |
| Can the Java launcher run it directly just from `.war`? | No | Yes, when properly repackaged |
| `META-INF/MANIFEST.MF` | May lack a `Main-Class` suitable for the Java launcher | `Main-Class` is typically `org.springframework.boot.loader.launch.WarLauncher`; `Start-Class` is the app |
| Servlet container libraries | Supplied by the external container | `WEB-INF/lib-provided` used by Boot Loader when running standalone |
| Classes and runtime libraries | `WEB-INF/classes` and `WEB-INF/lib` | Also has `WEB-INF/classes` and `WEB-INF/lib`; usually adds `WEB-INF/lib-provided` and loader |
| Port and context path config | Decided by container per deployment config | Embedded server takes Spring Boot config |
| Typical use case | Organization infrastructure mandates WAR on Tomcat/WebLogic/... | Want **one artifact** that both deploys traditionally and runs standalone |

**Common misconception:** an executable WAR is **not** a "non-standard WAR," nor is it a Docker-only format. It is a WAR compatible with standard deployment mechanisms, validly extended to carry Spring Boot's bootstrap capability. Actual compatibility still depends on the **container, Servlet/Jakarta API, classloader, app config, and Java version**.

## 2. Archive Structure and Each Party's Responsibilities

### 2.1. Traditional WAR

A typical Java web WAR:

```text
traditional.war
├── META-INF/
│   └── MANIFEST.MF
├── index.html                        (depends on application)
└── WEB-INF/
    ├── classes/
    │   └── com/example/war/...
    ├── lib/
    │   ├── spring-webmvc-....jar
    │   └── other application dependencies
    └── web.xml                       (if using a descriptor)
```

When deployed to a compatible Tomcat, **Tomcat** sets the context path, manages connectors/threads/ports, uses its own Servlet container API, and builds the application classloader. `web.xml` is **not required** if the application uses appropriate Servlet annotations/initialization; Spring Boot typically uses `SpringBootServletInitializer` instead of requiring a `web.xml` for new apps.

`java -jar traditional.war` **does not magically turn a WAR into a web server**. If the manifest lacks `Main-Class`, the Java launcher may report:

```text
no main manifest attribute, in traditional.war
```

This is **one error form you may see** (exact wording is not guaranteed across every JDK/archive). Merely adding a `main` method to source code is **not enough**: you need the packaging layout, manifest, and suitable runtime container for the Java launcher to run it.

### 2.2. Spring Boot Executable WAR

A Spring Boot Loader-compatible WAR typically has this layout:

```text
war-lab-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── org/
│   └── springframework/boot/loader/...
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/WarLabApplication.class
    │   └── com/example/war/HelloController.class
    ├── lib/
    │   └── application runtime libraries
    ├── lib-provided/
    │   └── dependencies needed when running embedded
    └── ... (depends on config)
```

Two important library directories:

- **`WEB-INF/lib/`**: application runtime dependencies placed where an external container can also load them on deployment.
- **`WEB-INF/lib-provided/`**: where the Spring Boot plugin puts dependencies marked `provided`/`providedRuntime` inside the executable WAR. **`WarLauncher` uses them during `java -jar`**, while external containers do not treat this as a standard `WEB-INF/lib` location to load as app-bundled libraries.

For example, embedded Tomcat accompanying `spring-boot-starter-web` can be marked **provided**: when deploying to external Tomcat, the container already has a servlet engine; when running `java -jar`, Boot Launcher still needs embedded Tomcat to start an HTTP server itself. Splitting `lib`/`lib-provided` avoids bundling a duplicate Tomcat alongside the external server.

**Not every WAR contains `lib-provided` or the Boot Loader.** If there are no provided dependencies or repackaging did not run, those entries may not appear. Always inspect the actual archive.

### 2.3. Executable WAR Manifest

In Spring Boot 3.x, the manifest typically looks like:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarLabApplication
```

`Main-Class` specifies the **bootstrap loader**, not a controller or servlet class. `Start-Class` specifies the class with the `main` entry point. When running `java -jar`:

```text
java -jar app.war
      |
      v
Spring Boot WarLauncher
      |
      +-- WEB-INF/classes/
      +-- WEB-INF/lib/*.jar
      +-- WEB-INF/lib-provided/*.jar
      |
      v
Start-Class: WarLabApplication.main(...)
      |
      v
SpringApplication.run(...)
      |
      v
Embedded Tomcat listening on HTTP
```

When **deploying to an external container**, the server does not use `WarLauncher` as its primary startup path. It uses its own **servlet initialization**, and Spring Boot provides `SpringBootServletInitializer` as the bridge.

## 3. The Two Application Initialization Paths Are Different

### 3.1. WAR Deployed to an External Container

```text
External Tomcat starts
       |
       v
Scans/deploys WAR (e.g., webapps/war-lab.war)
       |
       v
ServletContainerInitializer / Spring WebApplicationInitializer
       |
       v
SpringBootServletInitializer.configure(...)
       |
       v
Spring ApplicationContext + DispatcherServlet
       |
       v
HTTP endpoint runs under container-assigned context path
```

This execution path **does not begin with the application's `public static void main`**. You must configure proper servlet initialization; for typical Spring Boot servlet apps, extending `SpringBootServletInitializer` and overriding `configure` is the documented approach.

### 3.2. WAR Run Directly with `java -jar`

```text
java -jar app.war
      |
      v
META-INF/MANIFEST.MF -> WarLauncher
      |
      v
ClassLoader with WEB-INF/classes + lib + lib-provided
      |
      v
WarLabApplication.main(...)
      |
      v
SpringApplication.run(...)
      |
      v
Embedded Tomcat and HTTP endpoint
```

**Both mechanisms can coexist in the same Java class.** That explains why an executable WAR can run in both ways, as well as why writing only `main` or only `configure` is insufficient for a complete dual-mode WAR.

### 3.3. `SpringBootServletInitializer` vs. Servlet Container

`SpringBootServletInitializer` is a Spring Boot class that helps **bootstrap the application when an external servlet container deploys the WAR**. It is not Tomcat itself, not `WarLauncher`, and not required for applications that only run as executable JARs.

The complete Java example in the next section shows both `configure` and `main`. If an app only uses an embedded server such as `java -jar app.jar`, the main class does not need to extend `SpringBootServletInitializer`. If the app needs to run as a WAR on external Tomcat, an appropriate servlet bootstrap path must be provided.

For some specialized containers such as WebLogic, Spring Boot documentation also lists additional requirements around implementing `WebApplicationInitializer` directly; **do not treat the Tomcat example below as the only configuration valid for every application server**.

## 4. Hands-On Java 17 Example: One WAR Run Both Ways

The lab below uses **Spring Boot 3.5.16** (pinned for the example, not a claim of latest), **Java 17+**, a Maven version supporting it or a configured Maven Wrapper, and a compatible Tomcat 10.1 to test external deployment.

Objectives:

1. Build a `.war` containing the Boot Loader.
2. Run `java -jar ...war` and call the `/hello` endpoint.
3. Stop the embedded run and deploy the **same WAR** to an external Tomcat.
4. Call `/war-lab/hello` (per the assumed context name) and receive an equivalent body.

### 4.1. Directory Structure

```text
war-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/war/
        │   ├── WarLabApplication.java
        │   └── HelloController.java
        └── resources/
            └── application.properties
```

If the project uses Maven Wrapper, the root also has `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/...`. Wrapper files **do not appear automatically** when writing `pom.xml`; if absent, use an installed `mvn`.

### 4.2. Complete `pom.xml`

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
    <artifactId>war-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <!-- WAR instead of JAR; Maven WAR plugin will package WEB-INF -->
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring MVC, DispatcherServlet, and auto-configuration -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Tomcat is provided by the external container on WAR deployment -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- spring-boot-starter-parent configures repackage during package -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Mechanics:

- `<packaging>war</packaging>` tells Maven to produce a WAR.
- `spring-boot-starter-web` provides Spring MVC and required dependencies.
- Declaring `spring-boot-starter-tomcat` with `<scope>provided</scope>` keeps the servlet engine out of the standard runtime webapp directory on deploy.
- Spring Boot Maven Plugin `repackage` turns the archive created by the Maven WAR plugin into an **executable WAR**, including loader and manifest. Because the example uses `spring-boot-starter-parent`, the `repackage` goal is already bound to the lifecycle when declaring the plugin.
- Inside the executable WAR, appropriate provided dependencies are placed in `WEB-INF/lib-provided` so `WarLauncher` can use them during `java -jar`.

**Do not replace `provided` with `test`**: test scope does not ensure the dependency is available when running an embedded WAR. Nor should you completely exclude Tomcat from the dependency graph if you still want `java -jar` support and have no other embedded server.

### 4.3. Application Class with Both `configure` and `main`

`src/main/java/com/example/war/WarLabApplication.java`:

```java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarLabApplication extends SpringBootServletInitializer {

    // Used when the WAR is deployed by an external servlet container.
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarLabApplication.class);
    }

    // Used when Spring Boot Loader runs the WAR via java -jar.
    public static void main(String[] args) {
        SpringApplication.run(WarLabApplication.class, args);
    }
}
```

This is a **valid Java 17+ class** when compiled with the dependencies in the POM. Because it sits in `com.example.war` with `@SpringBootApplication`, default component scanning finds controllers in the same package.

Why are both methods needed?

- When started by **external Tomcat**, Spring Servlet initialization invokes the `configure` path; the external container manages the servlet lifecycle.
- When started via **`java -jar`**, `WarLauncher` invokes `main`, and Spring Boot starts the embedded web server.
- Configuration flags/profiles may differ between the two launch modes; if you need unified custom `SpringApplicationBuilder` configuration, use **a single shared helper method** called by both `configure` and `main` rather than customizing only one path.

### 4.4. REST Controller with Deterministic Output

`src/main/java/com/example/war/HelloController.java`:

```java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "WAR OK\n";
    }
}
```

A successful HTTP body contains the exact text **`WAR OK` followed by a newline**. With `curl`, the console prints:

```text
WAR OK
```

This controller depends only on Spring Web, not on the launch mode. Thus the same logic can serve HTTP under embedded Tomcat or external Tomcat when their respective configurations are valid.

`src/main/resources/application.properties`:

```properties
spring.application.name=war-lab
spring.main.banner-mode=off
```

We omit `server.servlet.context-path` in the example to make the difference between the embedded server's context and the external container's assigned context easy to observe.

## 5. Maven Build and Running the Executable WAR

From the `war-lab` directory:

```bash
# If the project has Maven Wrapper:
./mvnw clean package

# Or pre-installed Maven, when the project has no Wrapper:
mvn clean package
```

Choose **one** of the two commands; repository access is required if dependencies/plugins are not yet cached. In Windows PowerShell with the Wrapper, use `.\mvnw.cmd clean package`.

When the build succeeds, the example produces:

```text
target/war-lab-0.0.1-SNAPSHOT.war
```

Run directly:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war
```

In another terminal, once startup completes, call:

```bash
curl -fsS http://localhost:8080/hello
```

Expected HTTP body:

```text
WAR OK
```

This is the **output of the controller endpoint** when the app and port are working normally, not the full stdout of `java -jar`. If port 8080 is already used by another process, switch ports for the executable run:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war --server.port=8081
curl -fsS http://localhost:8081/hello
```

**`--server.port`** controls embedded Tomcat in the `java -jar` branch. It does **not** change the connector port of an already-running external Tomcat, because that server's port is configured in Tomcat itself.

### 5.1. Inspect the Actual WAR Rather Than Relying on the Extension

Use the JDK's `jar` tool:

```bash
jar tf target/war-lab-0.0.1-SNAPSHOT.war

# Show only the directories and Boot loader (Unix shell with grep):
jar tf target/war-lab-0.0.1-SNAPSHOT.war | grep -E '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

Windows PowerShell:

```powershell
jar tf target/war-lab-0.0.1-SNAPSHOT.war |
    Select-String '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

Inspect the manifest by extracting it into a separate inspection directory:

```bash
mkdir -p inspect-war
cd inspect-war
jar xf ../target/war-lab-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
```

In Windows PowerShell, use `New-Item -ItemType Directory -Force inspect-war`, `Push-Location inspect-war`, `jar xf ../target/...war META-INF/MANIFEST.MF`, `Get-Content META-INF/MANIFEST.MF`, `Pop-Location`. **Extracting** does not modify the original archive.

In the example, look for:

- `WEB-INF/classes/com/example/war/WarLabApplication.class`.
- `WEB-INF/classes/com/example/war/HelloController.class`.
- Spring MVC dependencies inside `WEB-INF/lib/`.
- Embedded Tomcat JARs inside `WEB-INF/lib-provided/`.
- `Main-Class: org.springframework.boot.loader.launch.WarLauncher`.
- `Start-Class: com.example.war.WarLabApplication`.

**Do not assert exact individual JAR versions/names** before checking the resolved graph and archive. Nor does `jar tf` guarantee that classpath loading order equals ZIP entry order.

## 6. Deploying the Same Executable WAR to External Tomcat

The example assumes **Tomcat 10.1** is installed, runs on **Java 17+**, and is compatible with Spring Boot 3.5 and the application's Jakarta Servlet API. Tomcat 9 uses the old `javax.servlet` namespace and is **not suitable for directly deploying a `jakarta.servlet`-based Spring Boot 3.x app**.

### 6.1. Copy and Determine Context Path

Stop the `java -jar` WAR process if it is occupying **port 8080**, then copy the built artifact into Tomcat's `webapps` directory:

```bash
# Linux/macOS: CATALINA_HOME points to the installed Tomcat directory.
cp target/war-lab-0.0.1-SNAPSHOT.war "$CATALINA_HOME/webapps/war-lab.war"
```

Windows PowerShell with the `CATALINA_HOME` environment variable set:

```powershell
Copy-Item target/war-lab-0.0.1-SNAPSHOT.war "$env:CATALINA_HOME/webapps/war-lab.war"
```

Tomcat must actually exist and be configured to deploy WARs from that folder; this is **not** a Tomcat installation command. When Tomcat has suitable `autoDeploy` enabled, it deploys `war-lab.war` under context path **`/war-lab`** by WAR-filename convention. If the container uses another `Context` configuration or deploys via an admin UI, the context path may differ.

After Tomcat starts up and the WAR deploys successfully:

```bash
curl -fsS http://localhost:8080/war-lab/hello
```

Expected HTTP body is also:

```text
WAR OK
```

**Observed difference:** same `HelloController` class and same WAR artifact, yet when run directly the endpoint is `/hello`, while when deployed under the `war-lab` context it is `/war-lab/hello`. This difference comes from the **context path**, not a missing controller.

If the external server does not run on port 8080, use the container configuration's actual host/port. Do not assume from the WAR's `application.properties` that an external Tomcat listens on `server.port`.

### 6.2. Why Is There No Embedded Tomcat Conflict?

In **external deployment** mode:

- External Tomcat supplies the Servlet/Jakarta API and container-managed engine components.
- Application libraries in `WEB-INF/lib` are loaded per webapp configuration.
- Embedded container dependencies in `WEB-INF/lib-provided` are **not treated as regular webapp libraries** by the external container.
- Spring initializes the application via `SpringBootServletInitializer` in the Servlet startup lifecycle.

In **`java -jar`** mode:

- Spring Boot's `WarLauncher` can access both `WEB-INF/lib` and `WEB-INF/lib-provided`.
- Embedded Tomcat is loaded from the packaged provided dependencies.
- Spring Boot invokes `main`; the embedded server opens the port and serves requests.

That is why **`provided` in an executable WAR does not mean "absent at runtime during `java -jar`."** Standard Maven `provided` is excluded from Maven's ordinary runtime classpath, yet Spring Boot Maven Plugin has **its own executable WAR packaging rules**. You must inspect the final artifact, not just read the scope.

## 7. Telling Plain WARs Apart from Plugin-Built Executable WARs

### 7.1. Maven WAR Plugin and Spring Boot Maven Plugin Do Two Different Jobs

Maven `maven-war-plugin` packages a web application in WAR structure. `spring-boot-maven-plugin:repackage` **adds the executable structure**, loader, and updated manifest for standalone execution.

```text
Maven compile/resources
        |
        v
maven-war-plugin -> Standard webapp WAR
        |
        v
spring-boot-maven-plugin:repackage
        |
        v
Executable WAR with WarLauncher + matching provided deps
```

An un-repackaged WAR can still deploy normally onto Tomcat if the webapp is properly configured, yet `java -jar` will not work out of the box.

Having only:

```xml
<packaging>war</packaging>
```

is **not enough** to assert the WAR is executable. You must check the effective POM and how `spring-boot-maven-plugin` is bound to the lifecycle. With `spring-boot-starter-parent`, declaring the plugin as in section 4 hooks into the normal repackage flow. With another parent/BOM, you may need to declare the `repackage` execution explicitly.

Example plugin snippet for a project **not inheriting Spring Boot parent** that already manages Java/plugin versions separately:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

This is a **snippet inside `<build><plugins>`**, not a standalone POM; the project still needs compiler, dependency versions, WAR plugin, and Java version managed appropriately. Avoid declaring a duplicate `repackage` execution when the parent already binds it.

### 7.2. If You Only Need a Traditional WAR

Do not need or want `java -jar` support? You can use a WAR packaged to servlet container standards **without repackaging via the Spring Boot Loader**. A Servlet-based Spring Boot app should still have `SpringBootServletInitializer` (or suitable servlet bootstrap) and mark container dependencies with the proper scope.

However, **do not remove the Spring Boot plugin completely without inspecting the build**: in an existing project, the plugin may manage other goals or settings. Check tools, parent, and tasks before changing anything, then re-inspect the archive. A traditional WAR only needs to deploy onto a compatible container; do not treat `java -jar` failing as a sign that the WAR is "invalid."

## 8. Gradle: `war`, `bootWar`, and `providedRuntime`

With Gradle, apply the `war` plugin for WAR packaging. When `org.springframework.boot` is applied alongside the `war` plugin, Spring Boot creates the `bootWar` task to package an **executable WAR**, while the `war` task creates a standard Gradle WAR.

### 8.1. Complete Groovy DSL Example

Keep the two Java classes `WarLabApplication` and `HelloController` from section 4. Create `settings.gradle`:

```groovy
rootProject.name = 'war-lab'
```

Create `build.gradle`:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'war'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Servlet engine used when running embedded, excluded from WEB-INF/lib
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

This is a **Gradle Groovy DSL** configuration; do not mix it directly with `build.gradle.kts` Kotlin DSL syntax. The Spring Boot plugin alone does not add starters or manage all dependency versions without dependency management; `platform(...)` here imports constraints from the Spring Boot BOM for the `implementation` configuration.

`providedRuntime` is a configuration from the Gradle WAR plugin and is Spring Boot's documented approach for external servlet container deployment. It is preferred over `compileOnly` for the embedded servlet container because `compileOnly` **is not on the test runtime classpath**, which can leave web integration tests without a runtime container.

### 8.2. Running Tasks and Inspecting Output Files

If the project already has a Gradle Wrapper using a Gradle version compatible with Spring Boot 3.5:

```bash
./gradlew tasks --all

# Build plain WAR and Boot executable WAR:
./gradlew clean war bootWar

# Check actual output:
jar tf build/libs/war-lab-0.0.1-SNAPSHOT.war

# Run executable WAR:
java -jar build/libs/war-lab-0.0.1-SNAPSHOT.war
```

In Windows PowerShell use `.\gradlew.bat`. If the Gradle Wrapper is missing, generate it with a valid installed Gradle; `gradlew` and `gradlew.bat` do not appear automatically when writing build scripts.

By default convention with the Boot plugin, outputs typically include:

```text
build/libs/war-lab-0.0.1-SNAPSHOT.war         # bootWar
build/libs/war-lab-0.0.1-SNAPSHOT-plain.war   # war
```

These names are a **convention**, not a guarantee if the project alters `archiveClassifier`, `archiveBaseName`, or `version`. If the `war` task has a custom classifier, check actual files in `build/libs`. **Do not run `java -jar` on `*-plain.war` and conclude no WAR is executable.**

### 8.3. A Published WAR Is Not Necessarily the WAR You Want to Deploy

Gradle `maven-publish` or other publication setups **do not automatically guarantee** that the published artifact is `bootWar` rather than `war`. If the pipeline needs an **executable WAR**, select the exact artifact/task or `.war` file in the build directory. If you only need external Tomcat deployment, either a plain WAR or a deployable executable WAR (with properly layered dependencies) can work.

Before pushing an artifact to a repository or registry:

1. Inspect the output files of both `war` and `bootWar`.
2. Check `META-INF/MANIFEST.MF` and `WEB-INF/lib-provided`.
3. Test `java -jar` if the artifact advertises executable support.
4. Test deploying to the target Tomcat version if the artifact advertises traditional deployment.

A `.war` suffix or a green build task **does not replace** testing both execution paths.

## 9. Context Path, Ports, and Deployment Lifecycle

The two modes divide configuration ownership differently.

| Question | WAR deployed to external Tomcat | `java -jar` executable WAR |
|---|---|---|
| Where is the HTTP port configured? | Tomcat connector (`server.xml` or operations system) | Embedded server, configurable via `--server.port=8081` |
| Default context path? | From WAR filename or container `Context` config (e.g., `/war-lab`) | Usually `/` unless Spring sets a context path |
| Who starts the server? | Tomcat process/manager | Boot application inside the Java process |
| Who restarts the app? | Servlet container / deployment manager | Process manager, service, or app container runtime |
| Can the server/container run multiple webapps? | One Tomcat can deploy multiple WARs | Each executable WAR is typically its own process with an embedded server |
| Where do Servlet API and embedded engine come from? | External container | `WEB-INF/lib-provided` inside the executable WAR |
| Is `SpringBootServletInitializer` needed? | Yes for traditional Spring Boot servlet WARs | `main` is the executable path; initializer still enables dual-mode |

For example, when external Tomcat listens on port 8080 and deploys `war-lab.war`, the test URL is `http://localhost:8080/war-lab/hello`. If the same executable WAR runs on port 8081 via:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war --server.port=8081
```

then the corresponding request is `http://localhost:8081/hello`. Custom configured context paths must be verified against actual settings.

**Do not run two servers on port 8080 at the same time** unless each binds to a distinct interface or has explicit configuration. A "Port 8080 was already in use" error is a socket bind conflict; it says nothing about whether the artifact is executable.

### Nature of a Servlet Web Application

This pattern applies to the **Spring MVC/Servlet stack**. Spring Boot documentation notes that **WAR deployment is not supported for Spring WebFlux applications using the default reactive server**, because WebFlux does not depend directly on the Servlet API and runs on Reactor Netty by default. Do not convert a `spring-boot-starter-webflux` project into a traditional WAR merely by changing `<packaging>` or enabling Gradle `war`.

## 10. Java Version, Servlet/Jakarta API, and Compatibility

Spring Boot 3.x uses the **Jakarta EE namespace** `jakarta.servlet.*` instead of the older `javax.servlet.*`. Tomcat 10.1 (with Servlet 6.0) is a standard compatible container choice for Spring Boot 3.5; Tomcat 9, tied to legacy `javax.servlet`, is not a compatible target for this application.

Items to verify on deployment:

- **External server JDK** meets requirements for both Spring Boot and the servlet container.
- **Servlet API version/namespace** matches the Spring Framework/Boot release in use.
- **Container vendor/version** is approved by the application and infrastructure; do not assume "Tomcat exists" is enough.
- Container-managed dependencies (Servlet/JSP/WebSocket APIs, engine) are not duplicated in the wrong place inside `WEB-INF/lib`.
- Container classloader policies may differ from Boot Launcher, affecting resources, logging providers, and pre-installed libraries.
- Datasource/JNDI, SSL, session, security, logging, and context path configuration may differ between embedded and external containers.

Errors like `NoClassDefFoundError: javax/servlet/...` or `jakarta/servlet/...` are signals to check the **namespace/Servlet API and classpath**, not just mechanically rename packages. When migrating from legacy Java EE, verify whether all libraries and source code are Jakarta-compatible.

**An executable WAR is not completely container-agnostic.** An application may run embedded yet fail to deploy onto an external container that is too old or enforces special policies/classloaders.

## 11. Proving It with Tests: Two Modes, One Artifact

A reliable testing strategy checks the **exact built WAR file** in both target environments.

### Testing the Executable Branch

1. `mvn clean package` or `./gradlew clean bootWar`.
2. `jar tf ...war` to confirm loader, manifest, and `WEB-INF/lib-provided` when using provided Tomcat.
3. `java -jar ...war --server.port=8081`.
4. Call `curl -fsS http://localhost:8081/hello`.
5. Confirm HTTP 200 and body `WAR OK` with newline; stop the process.
6. Inspect startup logs/exceptions; ensure no classloading or binding errors occurred.

### Testing the External Container Branch

1. Take the **exact same verified WAR file** (do not rebuild with different settings).
2. Deploy to a compatible Tomcat 10.1/JDK; name the file `war-lab.war`.
3. Wait for the server to finish deployment; inspect Tomcat logs.
4. Call `curl -fsS http://localhost:8080/war-lab/hello` (or the actual context/port).
5. Confirm HTTP 200 and body `WAR OK` with newline.
6. Undeploy the WAR and verify the server releases resources/threads cleanly per container lifecycle.

**Fair comparison:** business HTTP responses match; URL paths, ports, and classloader logs may differ. A green `mvn test` alone does not prove the WAR deploys onto real Tomcat. A green `java -jar` alone does not prove the servlet initializer and container compatibility.

### Inspecting the Archive with Pure Java 17 (Optional)

If you prefer not to rely on `grep` or `Select-String`, you can write a small Java CLI to verify selected archive entries. File `WarEntries.java` at root:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.zip.ZipFile;

public class WarEntries {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java WarEntries <path-to-war>");
            return;
        }
        try (ZipFile war = new ZipFile(Path.of(args[0]).toFile())) {
            System.out.println("Has manifest: "
                    + (war.getEntry("META-INF/MANIFEST.MF") != null));
            System.out.println("Has app class: "
                    + (war.getEntry(
                      "WEB-INF/classes/com/example/war/WarLabApplication.class")
                        != null));
            System.out.println("Has Boot launcher: "
                    + (war.getEntry(
                      "org/springframework/boot/loader/launch/WarLauncher.class")
                        != null));
        }
    }
}
```

With Java 17+ at the root containing `WarEntries.java`:

```bash
javac WarEntries.java
java WarEntries target/war-lab-0.0.1-SNAPSHOT.war
```

With an **executable WAR built exactly as in the example** and Spring Boot 3.5 having `WarLauncher` at that path, stdout of this custom program is:

```text
Has manifest: true
Has app class: true
Has Boot launcher: true
```

If run against an **un-repackaged** traditional WAR, the launcher check typically prints `false`. This program checks only **entry presence**; it does not check `Main-Class` in the manifest, dependency completeness, or actual startup. Therefore live testing in both modes is still required.

## 12. Common Errors and How to Diagnose Them

| Symptom | Cause / Hypothesis | Check and Resolution |
|---|---|---|
| `java -jar app.war` reports `no main manifest attribute` | Plain WAR lacking launcher manifest | Check `spring-boot-maven-plugin:repackage`/`bootWar`; inspect manifest |
| `main` exists in Java yet `java -jar` fails | JAR/WAR was not repackaged or manifest is wrong | Check `Main-Class`/`Start-Class`, build plugin, and actual artifact |
| `WarLauncher` missing from archive | Using plain WAR or misconfigured packaging | `jar tf`; pick the `bootWar` or repackaged output |
| `java -jar` fails with missing Tomcat classes | Provided dependencies not placed in `lib-provided` or wrong runtime deps | Check `WEB-INF/lib-provided` and POM/Gradle config |
| External Tomcat deploy hits servlet engine conflicts | Embedded container wrongly packaged in `WEB-INF/lib` | Use Maven `provided`/Gradle `providedRuntime` and rebuild |
| WAR runs standalone yet external Tomcat returns 404 | Wrong context path, undeployed, inactive initializer, or wrong mapping | Inspect server logs, `/war-lab/hello`, and `SpringBootServletInitializer` config |
| External Tomcat startup throws `ClassNotFoundException` | Missing runtime dependency in `WEB-INF/lib` or container classloader difference | Read `Caused by`, JAR list, server libraries, and scopes |
| `NoClassDefFoundError javax.servlet` / `jakarta.servlet` | Incompatible API namespace or container | Match Spring Boot 3.x with Tomcat 10.1; check migrated libraries |
| `server.port=8081` does not change external Tomcat's port | External container port is server-managed | Edit Tomcat connector config instead of Spring embedded property |
| Wrong `-plain.war` artifact distributed | Pipeline picked the wrong artifact | Check manifest, `war` vs. `bootWar`, and deployed file |
| `java -jar` port 8080 already in use | Two servers binding the same port | Stop one server or pass `--server.port` |
| WAR deploys slowly or fails to initialize beans | Differing profiles, JNDI, datasource, migrations, or container init | Check config and logs for that exact mode |
| Controller works embedded yet isn't scanned externally | `configure` returns wrong source/context config | Use `application.sources(WarLabApplication.class)` as shown |
| `WEB-INF/lib-provided` has JARs ignored by external container | Intended behavior of dual-mode layout | Distinguish `WarLauncher`'s classpath from external container's |
| Docker image expects Boot JAR while pipeline deploys WAR | Inconsistent release path | Align artifact/lifecycle and check startup command |
| WebFlux WAR fails traditional deployment | Reactivity/Netty differs from Servlet WAR | Choose the proper deployment style rather than only changing packaging |

### Ordered Troubleshooting Path

1. **Locate the exact artifact** being run or deployed; record version/checksum.
2. **Extract the manifest** and check whether `WarLauncher` and `Start-Class` are present.
3. **List the archive** and distinguish `WEB-INF/classes`, `lib`, `lib-provided`, and embedded libraries.
4. **Inspect the build configuration**: Maven `packaging=war`, `provided`, `repackage`; Gradle `war`, `providedRuntime`, `bootWar`.
5. **Read the right process logs**: stdout of the executable WAR or external Tomcat logs.
6. **Check port and context path** before suspecting a missing controller.
7. **Verify JDK/Jakarta Servlet compatibility** and container version.
8. **Test both modes** in matching environments if dual-mode is required.
9. **Fix in source/build** and rebuild; never hand-edit released WARs.
10. **Add smoke/integration tests** for the mode used in production.

## 13. When to Choose Executable JAR, Traditional WAR, or Executable WAR?

| Real-World Need | Option to Consider | Reason |
|---|---|---|
| Self-running microservice, Dockerized, no external servlet container required | **Spring Boot executable JAR** | Simplest packaging and embedded server operation |
| Organization mandates deploying multiple webapps into one centrally managed Tomcat/app server | **Traditional deployable WAR** | External infrastructure owns server, ports, contexts, and shared services |
| Need one artifact usable on both external Tomcat and `java -jar` | **Spring Boot executable WAR** with proper provided dependencies | Combines servlet deployment and Boot Launcher |
| Spring WebFlux project using default Reactor Netty | **Executable JAR/image**, not traditional WAR | Traditional WAR is not supported for WebFlux per Boot docs |
| Custom application server with JNDI, shared classloader, or complex policies | Container-compatible WAR tested on the real server | Runtime compatibility matters more than file extension |

**Do not choose WAR just because "Spring Boot web must be a WAR."** Spring Boot very commonly uses executable JARs. Use a WAR only when infrastructure requirements, container integration, or a specific dual-mode policy call for it.

## 14. End-of-Lesson Checklist

- [ ] Clearly distinguish an **external Servlet container** from an **embedded server**.
- [ ] Know that a traditional WAR does not automatically run via `java -jar` merely from its `.war` extension.
- [ ] Know that `SpringBootServletInitializer.configure` serves the external servlet container bootstrap path.
- [ ] Know that `main` and `SpringApplication.run` serve the executable WAR startup path.
- [ ] Understand that `WarLauncher` loads classes from `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.
- [ ] With Maven, configure `<packaging>war</packaging>`, Tomcat `provided`, and Boot `repackage` properly.
- [ ] With Gradle, configure the `war` plugin, `providedRuntime`, and `bootWar` properly.
- [ ] Know that `WEB-INF/lib-provided` keeps embedded Tomcat available for direct execution without conflicting with an external server.
- [ ] Know the difference between manifest `Main-Class` and `Start-Class`.
- [ ] Do not confuse **external Tomcat port/context** with embedded Boot `server.port`/context.
- [ ] Verified JDK, Jakarta Servlet API, and container compatibility.
- [ ] Ran an HTTP endpoint smoke test on the **exact artifact and exact deployment mode**.

**In summary:** a traditional deployable WAR is initialized by an **external servlet container**. A Spring Boot executable WAR shares the same WAR foundation while adding the **Boot Loader + manifest + suitable runtime dependencies**, enabling it to both deploy onto a compatible container and run standalone via `java -jar`. The decisive difference lies in the **bootstrap path and packaging**, not in the `.war` extension.

### Official References

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.5 — Launching Executable Jars/Wars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Nested JARs and WAR layout](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Maven Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Gradle — The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)