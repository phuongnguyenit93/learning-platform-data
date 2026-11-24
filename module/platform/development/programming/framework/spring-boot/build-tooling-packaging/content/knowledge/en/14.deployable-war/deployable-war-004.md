# Creating a WAR with Gradle `war` and `bootWar` in Spring Boot

When deploying a Spring Boot application in the **WAR** model, you often encounter two similarly named tasks:

- **`war`** provided by the **Gradle War plugin**: builds a traditional WAR suitable for deploying to an external servlet container such as Apache Tomcat.
- **`bootWar`** provided by the **Spring Boot Gradle plugin** when the War plugin is applied: builds an **executable Spring Boot WAR**, complete with launcher and nested dependencies so it can run with `java -jar`; when the servlet container dependency is configured properly, that very same WAR can also be deployed into an external servlet container.

**Not every task that creates a `.war` file produces the same kind of artifact.** To know whether to use `war` or `bootWar`, identify the **deployment path**: an environment-provided servlet container or a JVM running the archive directly.

This article walks through the dependency model, Gradle Groovy/Kotlin DSL configuration, a Java 17+ application capable of building both WARs, how to inspect the archive structure, testing, Tomcat deployment, and common pitfalls.

The examples pin **Spring Boot 3.3.5**, **Java 17**, and **Gradle 8.7** for concrete inputs; this is not a claim of the latest versions. With Spring Boot 3.x, note the **`jakarta.servlet.*`** API in place of the older `javax.servlet.*` generation.

## 1. How Does a WAR Differ from a JAR?

**JAR (Java ARchive)** typically contains classes, resources, and metadata for distributing a Java module. **WAR (Web Application Archive)** is an archive format for **web applications** with a layout recognized by servlet containers.

A typical WAR has the layout:

~~~text
sample.war
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/war/WarDemoApplication.class
│   │   └── application.properties        (if present)
│   ├── lib/
│   │   ├── spring-webmvc-*.jar
│   │   └── application libraries
│   └── web.xml                          (optional with modern Servlet)
└── contents from src/main/webapp/         (if present)
~~~

This is a diagram: actual library names carry version numbers, and `web.xml` may not exist at all. In a modern Spring Boot project using `SpringBootServletInitializer` and programmatic initialization, **`web.xml` is not strictly necessary**.

An executable Spring Boot WAR adds **Spring Boot loader classes**, entry-point metadata, and may contain:

~~~text
WEB-INF/lib-provided/
    tomcat-embed-core-*.jar
    tomcat-embed-websocket-*.jar
    ...
~~~

Libraries in `WEB-INF/lib-provided` are for the **executable** `java -jar` path, while remaining outside `WEB-INF/lib` loaded by an external servlet container under standard WAR conventions. That is the key mechanism allowing one archive to both **run standalone** and **deploy** to an external Tomcat.

### Quick Comparison

| Property | Gradle `war` | Spring Boot `bootWar` |
| --- | --- | --- |
| Plugin registering task | `id 'war'` | `id 'org.springframework.boot'` when War plugin is applied |
| Task type | `War` | `BootWar` (extends `War`) |
| Output | Traditional WAR | Executable Spring Boot WAR |
| `WEB-INF/classes` | Yes | Yes |
| `WEB-INF/lib` | Runtime dependencies, excluding provided dependencies | Appropriate application runtime libraries |
| `WEB-INF/lib-provided` | Typically absent | Present if `providedRuntime` dependencies need packaging |
| Boot launcher / `Start-Class` | Not default on a plain WAR | Present in a standard executable archive |
| `java -jar file.war` | Not the default target | Can run |
| Deploy to external servlet container | Yes, if application is validly configured | Yes, with proper servlet configuration and server dependency handling |

**`bootWar` does not mean "embedded server only."** A properly configured executable Boot WAR can be deployed to an external container; the key difference is where the servlet server libraries sit inside the archive.

## 2. How the Gradle `war` Plugin Works

Simply declare:

~~~groovy
plugins {
    id 'war'
}
~~~

The Gradle War plugin **applies the Java plugin**, adding the `war` task and web-application configurations. In the standard case:

- `src/main/java` holds primary sources.
- `src/main/resources` holds classpath resources.
- `src/main/webapp` holds web application root files, copied to the **root of the WAR**.
- Compiled Java classes go into `WEB-INF/classes`.
- Appropriate runtime dependencies are copied into `WEB-INF/lib`.
- Dependencies in `providedCompile`/`providedRuntime` are treated as provided by the deployment environment and excluded from packaged libraries under War plugin semantics.

Build a plain WAR:

~~~bash
./gradlew war
~~~

`war` is also wired into Gradle's `assemble` lifecycle task unless customized or disabled by the project. If you want to ensure you run the **exact** task under inspection, invoke `war` by name directly rather than inferring from running `build`.

### Configuring Output Path and Filename

~~~groovy
import org.gradle.api.tasks.bundling.War

tasks.named('war', War) {
    archiveFileName.set('portal-plain.war')
}
~~~

`archiveFileName` is a Property provided by Gradle; the output name does not have to match `project.name`. By default the target directory is usually `build/libs/`, unless `destinationDirectory` is customized.

If you need traditional web application files such as JSPs, HTML, or assets at the archive root, place them under `src/main/webapp`. For a pure Spring Boot-managed REST API, that directory is **not required**.

## 3. Spring Boot Gradle Plugin Adds `bootWar` When the War Plugin Is Present

When a project applies both the **Spring Boot Gradle plugin** and the **Gradle War plugin**, the Boot plugin registers `bootWar` of type `BootWar`. It is wired into `assemble` while using executable-archive packaging logic.

~~~groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

`io.spring.dependency-management` in this example manages dependency versions via the Spring Boot BOM. Another project may use a **Gradle native platform/BOM** instead; you do not have to use both at once.

Build an executable WAR:

~~~bash
./gradlew bootWar
~~~

To configure the task directly:

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named('bootWar', BootWar) {
    archiveFileName.set('portal.war')
}
~~~

**`tasks.named` does not create a new task**; it retrieves an already-registered task, so it only makes sense when the plugins that register `bootWar` are applied in the same project. Do not re-register `bootWar` with `tasks.register`.

### Why Are There Two WAR Files?

By Spring Boot Gradle plugin default, when `bootWar` and `war` both operate, the plain `war` task typically uses the **`plain` archive classifier** to avoid overwriting the executable archive:

~~~text
build/libs/portal-1.0.0.war
build/libs/portal-1.0.0-plain.war
~~~

This is an **illustrative default convention**, subject to `project.name`, `version`, `archiveBaseName`, `archiveClassifier`, and actual configuration. Do not guess which WAR to deploy from the filename alone. Verify with `jar tf` and the manifest.

To eliminate ambiguity in this hands-on exercise, we will explicitly set **two distinct filenames**: `war-demo.war` and `war-demo-plain.war`.

## 4. `providedRuntime` Is Key to Running Standalone and Deploying Externally

A Servlet-based Spring Boot web starter normally brings in **embedded Tomcat** transitively. If deploying to an **external Tomcat**, the external container **already supplies** the servlet engine. Putting embedded Tomcat inside `WEB-INF/lib` as well can cause duplicate classes, conflicts, or unexpected startup behavior.

With Spring Boot 3.3, the recommended configuration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Here `spring-boot-starter-web` is the application dependency; `spring-boot-starter-tomcat` is marked as **provided at runtime by the container**. That is the published Spring Boot 3.3 pattern for an **executable and deployable WAR**.

**What happens during the build?**

1. With **plain `war`**, the Gradle War plugin excludes provided dependencies and their transitive closure from the WAR runtime libraries. The external container must supply a compatible servlet engine.
2. With **`bootWar`**, the Spring Boot plugin places supported provided runtime libraries into `WEB-INF/lib-provided`. When running `java -jar`, `WarLauncher` loads them to start embedded Tomcat. When deployed externally, the servlet container does not automatically add `WEB-INF/lib-provided` to the standard web application classpath.
3. Dependencies **truly belonging to the application** still go into `WEB-INF/lib` so both modes see them per WAR semantics.

~~~text
providedRuntime: spring-boot-starter-tomcat
          |
          +-- plain war:
          |    WEB-INF/lib/          (excludes provided Tomcat)
          |
          +-- bootWar:
               WEB-INF/lib/          (application libraries)
               WEB-INF/lib-provided/ (provided Tomcat)
                  |
                  +-- java -jar: WarLauncher loads lib-provided
                  +-- external Tomcat: does not load lib-provided as WEB-INF/lib
~~~

### Why Not Use `compileOnly`?

The Gradle War plugin defines `providedCompile` and `providedRuntime` with specific semantics. `compileOnly` serves compilation only and does **not** supply the dependency at runtime or test runtime. If the servlet container dependency is mechanically switched to `compileOnly`, web tests needing a servlet engine may fail. `providedRuntime` keeps the dependency available on the build's appropriate runtime/test classpaths while excluding it from the traditional WAR and letting `bootWar` handle it specially.

**Caution on transitivity:** Gradle War plugin's `providedRuntime` can also exclude transitive dependencies from the plain WAR. If a library is pulled in by a provided dependency while also being independently needed by the application at runtime, inspect the resolved graph and actual archive rather than assuming every module is preserved.

### What If You Are Not Using Tomcat?

If the application uses Jetty or another container, pick the right starter and runtime dependency; do not copy `spring-boot-starter-tomcat` into a project that excludes Tomcat. For Servlet WARs targeting an external container, API/container versions and provided dependency management still need to match.

**Version context note:** Spring Boot 3.3 uses Jakarta Servlet; Tomcat 10.1 with Servlet 6.0 is a suitable illustrative choice. A Spring Boot 3.x WAR generally cannot be deployed straight onto Tomcat 9 based on `javax.servlet.*`.

## 5. Two Startup Paths and `SpringBootServletInitializer`

### Path A — Running the Executable WAR

~~~bash
java -jar build/libs/war-demo.war
~~~

The JVM reads `META-INF/MANIFEST.MF` and invokes Spring Boot's `WarLauncher`; the launcher builds the classpath from `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` per the standard layout. It then invokes the application main class, typically recorded under `Start-Class`.

An executable WAR manifest in Spring Boot 3.3 includes two lines like:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

These are **representative lines**; the manifest can contain other metadata as well. The Java launcher understands only `Main-Class`, while the Boot launcher uses `Start-Class`.

### Path B — Deploying the WAR to an External Servlet Container

An external servlet container like Tomcat **does not start via the application's `java -jar` command**. It loads the WAR within the container's web application context, sets up the classpath/web resources, and uses Servlet initialization to bootstrap the Spring context.

With Spring Boot, the application class should extend `SpringBootServletInitializer` and override `configure`:

~~~java
@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

This is an **illustrative snippet**; the required imports appear in the hands-on exercise below. Both paths are supported in the same class:

- `main` serves `java -jar` or direct application execution.
- `configure` serves external servlet container initialization.

If the application has special customizations when creating the Spring context, make sure both paths share the corresponding configuration; do not customize only `main` and expect an external container to pick it up automatically.

**`SpringBootServletInitializer` does not build a WAR.** It prepares the entry point for servlet deployment. The `war`/`bootWar` tasks perform the **packaging**. Both code and build script must work together for external deployment to succeed.

## 6. Complete Hands-On Lab: Same Project Building `war` and `bootWar`

The example is a small Spring MVC REST application. After building, one WAR is for running `java -jar` and the other is suited for traditional deployment. The Java 17+ code runs if files, toolchain, and dependencies are set up exactly as below.

### 6.1. Directory Structure

~~~text
war-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/example/war/
                ├── WarDemoApplication.java
                └── HelloController.java
~~~

Neither `src/main/webapp` nor `web.xml` is needed for a simple REST API. If you have static webapp resources, the Gradle War plugin copies `src/main/webapp` into the archive root.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'war-demo'
~~~

### 6.3. `build.gradle` — Complete, Groovy DSL

~~~groovy
import org.gradle.api.tasks.bundling.War
import org.springframework.boot.gradle.tasks.bundling.BootWar

plugins {
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.war.WarDemoApplication'
}

// Executable Spring Boot WAR: can run with java -jar.
tasks.named('bootWar', BootWar) {
    archiveFileName.set('war-demo.war')
}

// Plain WAR: deploy to an external servlet container.
tasks.named('war', War) {
    archiveFileName.set('war-demo-plain.war')
}
~~~

**Notes:**

- `id 'war'` applies the Java plugin and registers the `war` task; combined with the Spring Boot plugin, it provides `bootWar`.
- `spring-boot-starter-web` provides Spring MVC and web libraries.
- `providedRuntime '...starter-tomcat'` separates the servlet server from the standard WAR runtime library set and lets `bootWar` handle it for executable mode.
- `testImplementation` is for testing and does not put JUnit/Mockito into `WEB-INF/lib` in production packaging.
- `springBoot.mainClass` sets the main application class explicitly, avoiding main-class discovery errors when a project has multiple `main()` classes.
- `archiveFileName.set(...)` is used instead of relying on default classifiers so both artifacts are clearly identified during verification.
- Note that keeping build comments ASCII-safe improves compatibility if learners have inconsistent toolchain encodings; actual code names and logic do not depend on the comments.

### 6.4. `src/main/java/com/example/war/WarDemoApplication.java`

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

This Java class has a package matching its directory path. `SpringBootServletInitializer` serves **external deployment**, while `main` serves direct execution with the Boot launcher.

### 6.5. `src/main/java/com/example/war/HelloController.java`

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "HELLO_FROM_WAR";
    }
}
~~~

The class lives under package `com.example.war`, discovered by component scanning from `WarDemoApplication`. It is an HTTP GET endpoint requiring no database, secrets, or external network. The response body is plain text:

~~~text
HELLO_FROM_WAR
~~~

Do not switch to `@Controller` or return a view name; `@RestController` ensures the `String` is written directly to the HTTP response body.

## 7. Building Both WARs with Gradle

At the project root with a compatible Gradle Wrapper, on Linux/macOS:

~~~bash
./gradlew clean war bootWar
~~~

This command explicitly requests both tasks instead of relying on how `build` might be customized in another project. On success, per the configured `archiveFileName`:

~~~text
build/libs/war-demo.war
build/libs/war-demo-plain.war
~~~

If the build fails, do not mistake a file from an older build for a new artifact. `clean` prevents stale interference, though it deletes previous task outputs in `build/`, so use it in the practice project directory.

Run each task separately if needed:

~~~bash
./gradlew bootWar
./gradlew war
~~~

To see which tasks are actually registered:

~~~bash
./gradlew tasks --all
./gradlew help --task war
./gradlew help --task bootWar
~~~

`tasks --all` may list many more tasks added by plugins; exact output depends on the project and Gradle version. Do not confuse **a task named `war`** with **a WAR file having been successfully built**.

### `build`, `assemble`, and `bootWar`

In standard Spring Boot Gradle plugin integration, `bootWar` is wired into `assemble`. The Gradle War plugin likewise wires `war` into `assemble`. Therefore `./gradlew build` normally builds the relevant archives along with verification steps, though real pipelines may disable or alter task dependencies. When a lesson needs to inspect both artifacts individually, invoking `war bootWar` explicitly is more reliable.

## 8. Comparing Both Archives Using JDK Tools

The `jar` tool included in JDK 17:

~~~bash
jar tf build/libs/war-demo-plain.war
jar tf build/libs/war-demo.war
~~~

In the plain WAR, look for representative entries:

~~~text
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-<version>.jar
~~~

This is an **abbreviated listing diagram**, not full stdout: `<version>` represents the actual JAR version. The Boot plugin's `WEB-INF/lib-provided` is not a structure generated by plain `war`.

In the executable Boot WAR, look additionally for:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-<version>.jar
WEB-INF/lib-provided/tomcat-embed-core-<version>.jar
~~~

The actual list has many more entries, and nested dependency names include specific version numbers. What matters is the **location of the servlet container JAR**: in `lib-provided` for the executable WAR, and absent from `lib` in the plain WAR under standard configuration.

### Why Doesn't `jar tf` Print Classes Inside Nested JARs?

`jar tf file.war` lists entries of the **outer archive**, rather than recursively scanning every class inside each `WEB-INF/lib/*.jar`. A nested JAR is a single entry inside the WAR. To inspect classes inside a dependency JAR, use the dependency graph or extract the nested JAR separately with an appropriate tool.

### Reading the Right File's Manifest

On Linux/macOS with `unzip`:

~~~bash
unzip -p build/libs/war-demo.war META-INF/MANIFEST.MF
~~~

In the example's executable WAR, two main lines are expected:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Do not require the manifest to contain only two lines, because version metadata, indexes, build info, and other archive attributes may be present. `jar tf` only lists the `META-INF/MANIFEST.MF` entry; it **does not print the file contents itself**.

Plain WARs typically **lack** a launcher `Main-Class` like an executable WAR. If both manifests look identical, verify you are reading two distinct files, that another task did not overwrite one, and that the archive configuration was actually applied.

## 9. Standalone Java 17 Inspector: Distinguishing Real Archives

Instead of relying on filenames or writing shell-dependent code, you can use the Java standard library to open a WAR as a JAR/ZIP. Create **`WarInspector.java`** in a separate directory:

~~~java
import java.io.IOException;
import java.util.Enumeration;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class WarInspector {
    private WarInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java WarInspector <path-to-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            Attributes attrs = manifest == null
                    ? null : manifest.getMainAttributes();

            String mainClass = attrs == null
                    ? null : attrs.getValue(Attributes.Name.MAIN_CLASS);
            String startClass = attrs == null
                    ? null : attrs.getValue("Start-Class");

            boolean classes = false;
            boolean provided = false;
            boolean loader = false;

            Enumeration<JarEntry> entries = archive.entries();
            while (entries.hasMoreElements()) {
                String path = entries.nextElement().getName();
                if (path.equals(
                        "WEB-INF/classes/com/example/war/WarDemoApplication.class")) {
                    classes = true;
                }
                if (path.startsWith("WEB-INF/lib-provided/")
                        && path.endsWith(".jar")) {
                    provided = true;
                }
                if (path.equals(
                        "org/springframework/boot/loader/launch/WarLauncher.class")) {
                    loader = true;
                }
            }

            System.out.println("MAIN_CLASS=" + show(mainClass));
            System.out.println("START_CLASS=" + show(startClass));
            System.out.println("APP_CLASS=" + classes);
            System.out.println("HAS_LIB_PROVIDED=" + provided);
            System.out.println("HAS_BOOT_WAR_LAUNCHER=" + loader);
        }
    }

    private static String show(String value) {
        return value == null ? "(absent)" : value;
    }
}
~~~

This is a standalone Java 17 program; it only inspects the artifact and needs no Spring Boot dependencies.

Compile:

~~~bash
javac WarInspector.java
~~~

Run against the **lab's executable WAR**:

~~~bash
java WarInspector build/libs/war-demo.war
~~~

Expected output with the Spring Boot 3.3.5 setup above:

~~~text
MAIN_CLASS=org.springframework.boot.loader.launch.WarLauncher
START_CLASS=com.example.war.WarDemoApplication
APP_CLASS=true
HAS_LIB_PROVIDED=true
HAS_BOOT_WAR_LAUNCHER=true
~~~

Run against the plain WAR:

~~~bash
java WarInspector build/libs/war-demo-plain.war
~~~

Typical output for a standard Gradle War plugin archive:

~~~text
MAIN_CLASS=(absent)
START_CLASS=(absent)
APP_CLASS=true
HAS_LIB_PROVIDED=false
HAS_BOOT_WAR_LAUNCHER=false
~~~

The `MAIN_CLASS`/`START_CLASS` lines for a plain WAR may differ if you configure the manifest yourself; thus the inspector reports **actual values** rather than hardcoding that every plain WAR on earth lacks a manifest. The count and placement of dependency JARs also depend on resolved configurations and packaging options.

The program uses `JarFile` to inspect the **outer WAR**; it does not recurse into every nested JAR. For this exercise, verifying the entry layout is sufficient.

## 10. Running the Executable WAR with `java -jar`

After building `build/libs/war-demo.war`:

~~~bash
java -jar build/libs/war-demo.war --server.port=8081
~~~

Spring Boot's `WarLauncher` builds the classpath from the application, libraries in `WEB-INF/lib`, and provided runtime libraries in `WEB-INF/lib-provided`, enabling embedded Tomcat to start. `WarDemoApplication.main` is invoked, and the embedded server runs on port 8081 if the port is free.

Use another terminal to test:

~~~bash
curl -fsS http://localhost:8081/api/hello
~~~

HTTP response body:

~~~text
HELLO_FROM_WAR
~~~

Do not treat Spring Boot startup log lines as fixed stdout. Startup timing, PID, and banner/log messages depend on the environment. `curl -fsS` may not append a newline in the terminal; the logical body is the string above.

Stop the application with Ctrl+C. If port 8081 is already used by another app, choose a different port with `--server.port` and adjust the test URL accordingly.

**Do not pass the plain WAR to this command as if it were an executable archive:**

~~~bash
java -jar build/libs/war-demo-plain.war
~~~

With a default plain WAR, the Java launcher typically reports a missing main manifest attribute or lacks an entry point runnable via `-jar`. That **does not mean** the plain WAR is broken: its purpose is deployment to an external servlet container.

## 11. Deploying the WAR to an External Tomcat

With Spring Boot 3.3, use a Jakarta Servlet compatible external servlet container, such as **Apache Tomcat 10.1**. Tomcat 9 uses the `javax.servlet.*` family and is not a suitable direct deployment target for Spring Boot 3.x.

A typical manual workflow in a lab environment:

1. Install JDK 17+ and a compatible Tomcat 10.1.
2. Identify the Tomcat instance in use (exact `CATALINA_BASE`, deployment directory, and port).
3. Copy the built plain WAR into the deploy directory, typically `webapps/` of that Tomcat instance.
4. Start Tomcat or instruct it to deploy the application per server procedures.
5. Read Tomcat logs to confirm the WAR deployed successfully and check the actual context path.

Example on Linux/macOS with a local Tomcat having no conflicting deployment name:

~~~bash
cp build/libs/war-demo-plain.war /opt/tomcat/webapps/war-demo.war
~~~

**The `/opt/tomcat/webapps` path is illustrative**; replace it with your real Tomcat deployment directory. Never copy directly onto a production server without authorization or an approved deployment pipeline; on systems with Tomcat Manager or CI/CD, use the organization's supported deployment mechanism.

If Tomcat deploys the WAR under context path `/war-demo`, the endpoint can be reached at:

~~~bash
curl -fsS http://localhost:8080/war-demo/api/hello
~~~

Expected response body:

~~~text
HELLO_FROM_WAR
~~~

**Context path is a common source of confusion:**

- When running an executable WAR via `java -jar`, the Boot app usually sits at root context `/`, so the route is `/api/hello` unless `server.servlet.context-path` is changed.
- When deploying a WAR named `war-demo.war` into Tomcat, the context is usually `/war-demo`, so the route becomes `/war-demo/api/hello`.
- If Tomcat is configured with another context, hostname, port, or reverse proxy, the real URL also differs. Do not jump to a dependency-error conclusion simply because an HTTP 404 came back on the wrong context URL.

For external deployment, **`war-demo.war` produced by `bootWar`** can also be deployed into a compatible container if `SpringBootServletInitializer` and provided dependency semantics are preserved. This article uses plain `war-demo-plain.war` to clearly distinguish the two tasks, not because an executable WAR can only run in embedded mode.

### Why Does `SpringBootServletInitializer` Matter?

In an external container, there is no invocation of the application's `public static void main` like in the `java -jar` path. `SpringBootServletInitializer` hooks into servlet startup and configures the source for the Spring application context.

If a project has `main` without an appropriate servlet initializer, a WAR—even with all classes and dependencies—may fail to initialize the Spring web application when deployed externally. When hitting this issue, fix the entry point/initializer before tweaking archive classifiers.

## 12. Managing `war` and `bootWar` in Real Projects

### Use Explicit Artifact Names Instead of Relying on the Default `plain`

Example:

~~~groovy
tasks.named('bootWar') {
    archiveFileName.set('myapp-executable.war')
}

tasks.named('war') {
    archiveFileName.set('myapp-servlet.war')
}
~~~

Both tasks emit separate files. Explicit `archiveFileName` values help when CI/CD needs to know exactly which file is launched via `java -jar` and which file goes to an external container.

If only one artifact is needed, you can run only the required task instead of always running both. **Disabling the other task is not strictly necessary**; disabling it can affect publishing, `assemble`, or other plugins.

### Multi-Module Projects

In a multi-project Gradle build, the `bootWar` task exists in the subproject where the relevant plugins are applied:

~~~bash
./gradlew :webapp:bootWar
./gradlew :webapp:war
~~~

`:webapp` is a sample subproject name; substitute your real module. Do not call `rootProject.tasks.named('bootWar')` when the task exists only in a child project. Shared library modules typically build JARs only and need neither `war` nor `bootWar`.

### Equivalent Kotlin DSL

In a `build.gradle.kts` with `war` and the Spring Boot plugin applied:

~~~kotlin
import org.gradle.api.tasks.bundling.War
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    archiveFileName.set("myapp-executable.war")
}

tasks.named<War>("war") {
    archiveFileName.set("myapp-servlet.war")
}
~~~

This is a **Kotlin DSL configuration snippet**, not a standalone file. Do not copy generic `named<BootWar>` syntax into a Groovy `build.gradle`. In Kotlin DSL, the dependency can be written as `providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")` once the War plugin is applied.

### Renaming Is Not Changing the Classpath

Configuring `archiveFileName` only changes the output filename. It **does not** alter dependency scopes, `WEB-INF/lib`, `WEB-INF/lib-provided`, main class, or deployability. You must configure `dependencies`, `springBoot.mainClass`, `SpringBootServletInitializer`, and the corresponding plugins/tasks to change runtime behavior.

### Customizing WAR Contents

Gradle's `War`/`BootWar` tasks provide archive properties such as `webAppDirectory`, `from(...)`, `webInf { ... }`, `archiveFileName`, and `destinationDirectory`. Example when static web files are present:

~~~groovy
tasks.named('war') {
    webAppDirectory.set(layout.projectDirectory.dir('src/main/webapp'))
}
~~~

This illustrates **plain WAR** configuration, assuming the directory exists; the `war` plugin already defaults to `src/main/webapp`, so there is no need to repeat it unless customizing. If you want the same static resources inside the executable WAR, verify that `bootWar` receives the desired content and then **inspect the actual archive**. Never assume that customizing one task automatically applies to the other.

## 13. Common Errors and How to Fix Them

| Symptom | Common Cause | Verification and Resolution |
| --- | --- | --- |
| `Task 'bootWar' not found` | Both Spring Boot plugin and War plugin not applied in the right project | Check `plugins`, subproject, and `./gradlew tasks --all` |
| `Task 'war' not found` | `id 'war'` not applied in the right project | Add War plugin; do not confuse with `bootJar` |
| `java -jar file.war` reports `no main manifest attribute` | Running a plain WAR | Read manifest; pick the `bootWar` output |
| `bootWar` runs yet `Start-Class` is wrong/unknown | Plugin cannot locate the application main class | Configure `springBoot.mainClass`; verify fully qualified name |
| Plain WAR deploys to Tomcat, startup reports missing initializer | Application lacks a proper servlet initializer | Extend `SpringBootServletInitializer` and override `configure` |
| Deploying to Tomcat 9 fails with `javax`/`jakarta` errors | Spring Boot 3.x uses Jakarta Servlet; Tomcat 9 uses older API generation | Use a compatible container such as Tomcat 10.1 |
| Duplicate Tomcat/servlet classes error | Embedded servlet server packaged in `WEB-INF/lib` instead of provided | Use `providedRuntime` on the right dependency; inspect archive |
| `java -jar` lacks embedded servlet classes | Provided dependencies were not placed in `WEB-INF/lib-provided` by `bootWar` | Check `providedRuntime`, `bootWar` config, and `jar tf` |
| Web integration tests missing server | Tomcat placed in `compileOnly` with wrong semantics | Use `providedRuntime` in a Gradle War project |
| HTTP 404 on external Tomcat | Wrong context path or endpoint | Try `/war-demo/api/hello` instead of `/api/hello`; check logs |
| `build/libs` has multiple WARs, CI deploys wrong one | Plain and executable WARs with different classifiers exist | Use explicit filenames and check manifest/layout |
| Build succeeds yet archive misses a dependency | Exclusions, transitive provided configs, or another publish task | Inspect `runtimeClasspath`, provided scopes, and `jar tf` |
| `war` contains stale files not in current output | Leftover old artifacts or misconfigured copy specs | Run `clean` when needed; inspect the freshly built output |
| `java -jar` works, external deploy fails on DB/profile | Container environment differs from direct runtime | Check config, credentials, classloader, env, and server logs |
| WAR contains `WEB-INF/lib-provided` yet Tomcat ignores nested Tomcat there | Intentional conflict-avoidance mechanism | External container provides its own server; do not move `lib-provided` into `lib` |

**Read the root cause:** if the application boots but returns HTTP 500 due to a database or network issue, that is not necessarily a `war` or `bootWar` error. Change packaging only when there is evidence of class, resource, loader, initializer, or container compatibility differences.

### Diagnostic Commands Worth Remembering

~~~bash
./gradlew tasks --all
./gradlew help --task war
./gradlew help --task bootWar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
./gradlew clean war bootWar
jar tf build/libs/war-demo.war
jar tf build/libs/war-demo-plain.war
~~~

`dependencies`/`dependencyInsight` show the dependency graph and why a version was selected. **Do not** treat the graph as the sole proof of archive contents: `providedRuntime` and packaging tasks affect where each final JAR lands. `jar tf` inspects the actual artifact.

When using `--info`, Gradle logs more task-execution details, though you should not assert fixed stdout since logs vary by version and environment.

## 14. Deployment Limitations to Keep in Mind

### Pure WebFlux and Servlet WAR

**Spring WebFlux** applications running on a reactive model with Reactor Netty by default are not a standard supported target for **external Servlet container WAR deployment** as shown here. This lesson is for **Spring MVC/Servlet**. Do not turn a pure WebFlux application into a `war` merely by adding the Gradle War plugin and expecting external servlet startup to work.

### Container Must Be API- and JVM-Compatible

Spring Boot 3.3 requires Java 17+ and uses Jakarta Servlet. Tomcat 10.1 is a common example for Servlet 6.0. When choosing another external servlet container, verify Servlet API constraints, Jakarta namespaces, Java version, native libraries, and container features the application relies on.

### Runtime Configuration Does Not Magically Travel with the WAR

`java -jar` can take configuration from the command line, environment variables, and external config files; an external Tomcat has its own startup, filesystem, logging, and environment. Do not equate **same source code** with **same environment**. If a WAR runs directly yet fails when deployed externally, check the initializer, servlet container dependencies, and container logs before blaming a Gradle task.

### Do Not Copy a WAR to a Server Before Knowing the Context Path

The WAR name typically affects the context path chosen by the container, yet the container may use context XML, manager settings, or a reverse proxy to override it. An endpoint `/api/hello` in code may appear as `/app/api/hello` when deployed under `/app`. Check the actual context path instead of blindly adding or stripping `/` segments.

### Do Not Hand-Edit the ZIP Manifest After Building

`bootWar` generates the loader and manifest for an executable WAR; `war` generates a traditional WAR. Manually editing `Main-Class` does not make a plain WAR executable, because the launcher and classpath layout are still missing. If you must change the main class, update the Spring Boot plugin configuration and rebuild.

## 15. Quick Decision Workflow

1. **Determine where it runs:** direct JVM or external servlet container.
2. **Ensure the application belongs to the Servlet stack** if external WAR deployment is needed.
3. **Apply the Gradle `war` plugin** for the `war` task, and the Spring Boot Gradle plugin if `bootWar` is needed.
4. **Add `SpringBootServletInitializer` and `configure`** for external deployment; keep `main` for executable mode if direct execution is needed.
5. **Declare the web starter and `providedRuntime`** for the appropriate embedded servlet container.
6. **Build the desired task** with `./gradlew war`, `./gradlew bootWar`, or both.
7. **Inspect the artifact**: `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, loader, and manifest.
8. **Test the right execution path**: `java -jar` for executable WAR; deploy on a compatible Tomcat for traditional WAR.
9. **Check the endpoint and context path**, then verify logs and tests in the target environment.
10. **Document which release artifact goes where**, preventing pipelines from mixing up plain and executable WARs.

## 16. Self-Check Questions

**Q1:** Which task does `id 'war'` create, and does it automatically create `bootWar`?

**Answer:** The War plugin creates `war`; `bootWar` appears when the Spring Boot Gradle plugin works alongside the War plugin in the same project.

**Q2:** Why does `war-demo-plain.war` typically not run with `java -jar`?

**Answer:** A plain WAR targets external servlet deployment and does not include a Boot loader or main manifest entry point by default. To run directly, use the executable WAR produced by `bootWar`.

**Q3:** Why put `spring-boot-starter-tomcat` in `providedRuntime`?

**Answer:** The external servlet container provides Tomcat itself; a plain WAR should not bundle a duplicate embedded server in `WEB-INF/lib`, while `bootWar` can place provided dependencies under `WEB-INF/lib-provided` for executable mode.

**Q4:** Does `SpringBootServletInitializer` replace the work of `war`/`bootWar`?

**Answer:** No. The initializer lets an external servlet container bootstrap the Spring context; the build tasks determine which archive is created and what it contains.

**Q5:** For the same `/api/hello` endpoint, why does running the WAR directly on port 8081 have a different URL than deploying to Tomcat?

**Answer:** A direct WAR usually uses the root context, so `http://localhost:8081/api/hello`. External Tomcat uses a context path from the WAR/deployment name, such as `http://localhost:8080/war-demo/api/hello`.

**Q6:** If two files both have a `.war` extension, how do you tell which one is executable?

**Answer:** Inspect `META-INF/MANIFEST.MF`, `Main-Class=WarLauncher`, `Start-Class`, and Boot loader entries; also check `WEB-INF/lib-provided`, the originating task, and run the artifact properly.

**Q7:** Can `providedRuntime` be replaced arbitrarily with `compileOnly`?

**Answer:** No. `compileOnly` does not provide the dependency on the test/runtime classpath, easily causing web tests or runtime paths to behave differently than expected. `providedRuntime` has WAR-specific semantics.

**Q8:** Can a Spring Boot 3.3 WAR be deployed directly onto Tomcat 9?

**Answer:** Not as a standard compatible deployment configuration: Boot 3.x uses Jakarta Servlet while Tomcat 9 uses `javax.servlet.*`. Pick a compatible container, such as Tomcat 10.1.

## 17. Official Documentation

- Spring Boot 3.3 — [Packaging Executable Archives with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootWar`, `providedRuntime`, executable and deployable WAR, plain classifier.
- Gradle — [The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html): `war`, `WEB-INF/classes`/`WEB-INF/lib`, `providedCompile`, `providedRuntime`, and webapp root.
- Spring Boot — [Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer` and preparing a WAR for an external servlet container.
- Spring Boot 3.3 — [SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): `configure` callback.
- Spring Boot 3.3 — [System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java, Gradle, and Servlet container compatibility.
- Spring Boot — [Launching Executable Archives](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/launching.html): `WarLauncher` and manifest `Main-Class`/`Start-Class`.

**Key takeaway:** **`war` creates a traditional WAR**, while **`bootWar` creates an executable Spring Boot WAR**; `providedRuntime` and `SpringBootServletInitializer` are the two essential pieces if you want **the same application** to work with an embedded servlet server on `java -jar` and with an external servlet container on WAR deployment. To tell the two artifacts apart, **inspect the WAR contents and test the right execution path** rather than looking only at the file extension.
