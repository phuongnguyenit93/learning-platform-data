# Distinguishing JDK, Build Tools, Spring Boot Plugins, and Runtime Environment

A Spring Boot application might be written on a machine using JDK 21, built with Gradle, packaged by the Spring Boot Gradle plugin, and then run on a server that only has Java Runtime 21. These four pieces collaborate in the same pipeline, yet perform four different jobs. Understanding their boundaries helps you pick the right tool, produce the right artifact, and troubleshoot issues when moving an app from a developer workstation to CI/CD or deployment environments.

## 1. Overview Map: Who Does What?

| Component | Question It Answers | Primary Responsibility | Examples |
| --- | --- | --- | --- |
| **JDK (Java Development Kit)** | What compiles Java code? | Provides `javac`, `java`, `jar`, and development libraries/tools; generates bytecode from source code. | Temurin JDK 21, Oracle JDK 21 |
| **Build tool** | In what order should libraries be downloaded, compiled, tested, and packaged? | Orchestrates tasks, dependencies, caching, build lifecycles, and automation. | Gradle, Maven |
| **Spring Boot plugin for build tool** | How do we build/run/package the app following Spring Boot conventions? | Integrates specialized tasks or goals such as `bootJar`, `bootRun`, and `repackage`. | `org.springframework.boot` Gradle plugin, `spring-boot-maven-plugin` |
| **Runtime environment** | Where does the built artifact run, and with which JVM and configuration? | Loads classes, executes bytecode, provides OS/resources/network/config and dependent services. | Java 21 runtime on server, container, VM |

Typical flow:

~~~text
Java source code + build.gradle / pom.xml
                    |
                    v
        Gradle / Maven (orchestration)
             |               |
             v               v
   JDK + javac (compile)   Resolve dependencies, test
             \               /
              \             /
               v           v
         Spring Boot build plugin
        (bootJar / bootWar / repackage)
                    |
                    v
           Deployment artifact
        (e.g., executable app.jar)
                    |
                    v
       JVM + OS + configuration
       + database / network / secrets
                    |
                    v
            Running application
~~~

**Key point:** the JDK can compile a simple Java program without Gradle/Maven; Gradle/Maven can manage many kinds of projects beyond Spring Boot; a Spring Boot plugin requires a build tool to operate; and a built artifact usually only needs a compatible Java runtime to execute.

## 2. JDK: Providing the Compiler and Java Tools

The JDK contains the `javac` compiler (turning `.java` into `.class`), the `java` command to launch the JVM, and the `jar` tool to create/inspect Java archives. Java bytecode in `.class` files is executed by the JVM, not directly "run" by Gradle or Maven.

Minimal example, saved as **Hello.java**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from JVM");
    }
}
~~~

On a machine with JDK 17 or newer:

~~~bash
javac Hello.java
java Hello
~~~

Exact output:

~~~text
Hello from JVM
~~~

You can package it manually using the JDK's `jar` tool:

~~~bash
jar --create --file hello.jar --main-class Hello Hello.class
java -jar hello.jar
~~~

The output is still `Hello from JVM`. This example **does not use** Gradle, Maven, or Spring Boot: it proves `javac`/`jar` belong to the JDK, while `java -jar` is the JVM executing an artifact. For applications with many libraries, managing the classpath and packaging manually quickly becomes complex—which is one reason to use a build tool.

### How Does the JDK Differ from the Java Runtime?

- **JDK** serves development and generally includes execution tools too. Build machines need a compiler and appropriate development tools.
- **Java runtime/JRE** is what is needed to run already-compiled applications; it does not necessarily include `javac`. Modern Java distributions may provide a full JDK or a stripped-down runtime image; not every version distributes a standalone JRE.
- **JVM** is the virtual machine that executes bytecode; the JVM is a component of the Java runtime environment, not synonymous with the entire JDK.
- The **JDK version** used to build and the **Java runtime version** used at deploy time may differ, but bytecode and used APIs must be compatible. Classes compiled for Java 21 will not by default run on a Java 17 runtime.

Check each tool individually:

~~~bash
java --version
javac --version
jar --version
~~~

If `java` works but `javac` is missing, the environment likely provides only a runtime, or `PATH`/`JAVA_HOME` does not point to the right JDK. `java --version` shows the Java invoked by the current shell, which is not necessarily the JDK used by your IDE, Gradle toolchain, or CI for compilation.

## 3. Gradle and Maven: Orchestrating the Build Process

A real-world project must resolve dependencies, compile, process resources, run tests, package, optionally run quality checks, and publish artifacts. The **build tool** describes the relationships between these jobs and executes them in the required order.

| Aspect | Gradle | Maven |
| --- | --- | --- |
| Common config files | `build.gradle` or `build.gradle.kts`; `settings.gradle` | `pom.xml` |
| Unit of organization | Tasks and task dependency graph | Lifecycle phases and plugin goals |
| Common Java compile/test | `compileJava`, `test`, `build` | `compile`, `test`, `package` |
| Library management | Dependency configurations, repositories, constraints/platforms | Dependencies, repositories, dependency management/BOM |
| Common Boot tasks/goals | `bootRun`, `bootJar`, `bootWar` | `spring-boot:run`, `spring-boot:repackage` |

For example, `./gradlew build` triggers tasks appropriate for the applied plugins; `mvn package` runs lifecycle phases up to `package`. These are **orchestration commands**, not compiler names. Underneath, the Java compiler is still supplied by the JDK/toolchain.

### Distinguishing Three Easily Confused Java Versions

1. **JVM running the build tool:** the Java version used to start the Gradle daemon or Maven process. Check via `./gradlew --version` or `mvn --version`.
2. **JDK/toolchain compiling the project:** the JDK Gradle/Maven selects to perform compile/test according to configuration. This can differ from the Java running the build tool.
3. **JVM running the deployed app:** the Java inside the server/container when executing `java -jar`. This is independent of the JDK on the build machine.

Conceptually valid example: Gradle runs on JDK 21, compiles the app using a JDK 21 toolchain, and the production runtime is Java 21. If you want to run on Java 17, you must choose a Java 17-compatible target/API and verify the Spring Boot version also supports Java 17.

In Gradle, toolchain configuration can look like:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

This configuration requests JDK 21 for the corresponding Java tasks. It does not automatically install Java 21 onto the production server, nor does it guarantee your Gradle version can run on any arbitrary Java version. If you want to produce Java 17-compatible bytecode with a newer compiler, you may need `options.release = 17`; using `--release` also restricts which standard Java APIs may be called. Framework and dependency compatibility must still be checked separately.

### Dependency Management vs. Packaging Plugin

The `spring-boot-starter-web` dependency brings web and embedded server libraries onto the classpath when properly configured. A BOM (Bill of Materials), `spring-boot-starter-parent`, or dependency management plugin helps pick **aligned library versions**. Meanwhile, the Spring Boot build plugin provides **tasks/goals** to build, run, and package. Having the Boot plugin does not automatically add every starter; adding a starter does not replace executable archive packaging tasks.

## 4. Spring Boot Build Plugin: Connecting the Build Workflow to a Boot App

Spring Boot provides dedicated integration for Gradle/Maven:

- **Gradle `org.springframework.boot` plugin:** adds/configures tasks such as `bootRun` (run from classpath during development), `bootJar` (create executable JAR), `bootWar` when WAR packaging is configured, and `bootBuildImage` for OCI images via buildpacks when environment prerequisites are met.
- **Maven `spring-boot-maven-plugin`:** provides `run`, `repackage`, and supporting goals. The `repackage` goal transforms a standard Java archive into a package with Boot layout and launcher; it can be bound to the `package` lifecycle depending on configuration.
- **Spring Boot framework and starters:** runtime dependencies inside the application. **The build plugin is neither the Spring Boot runtime itself nor a web server.**

In a standard executable Boot JAR, the artifact has a distinct layout such as `BOOT-INF/classes` (application classes/resources), `BOOT-INF/lib` (libraries), and a manifest pointing to the Boot launcher. When invoking `java -jar app.jar`, the launcher sets up the classpath to launch the entry point. Do not assume every `.jar` file is self-executable: a **plain JAR** may lack a startup manifest or runtime dependencies.

Comparison:

| Command / Artifact | Meaning | When to Use |
| --- | --- | --- |
| Gradle Java plugin's `jar` task | Creates a standard Java JAR; does not bundle enough dependencies to run Boot directly | Publishing a library or standard archive |
| `bootJar` | Creates an executable Spring Boot JAR with the proper structure/launcher | Packaging a Boot app as a JAR for deployment |
| `bootRun` | Runs the app via Gradle using the project classpath | Development/smoke runs; does not replace creating a distributable artifact |
| `bootWar` | Creates an executable WAR when the project configures WAR | WAR deployment scenarios or compatible container requirements |
| Maven `package` + `repackage` | Maven packages the archive, Boot plugin repackages it when configured | Maven's way of producing an executable Boot archive |

`bootBuildImage` can create a container image without writing a Dockerfile, yet it is still a **build step**; when the container runs, the Java runtime inside the image executes the application.

## 5. Complete Example: A Spring Boot App Using Gradle

This example pins Spring Boot **3.3.5** and Java **21** to illustrate the tool layers; these are sample versions, not a claim that they are the latest. The build machine needs JDK 21, a Gradle version compatible with the JDK/Boot plugin, and repository access to download dependencies. For new projects, pick supported plugin/framework versions and consult their compatibility matrix.

Create three files:

**settings.gradle**

~~~groovy
rootProject.name = 'boot-packaging-demo'
~~~

**build.gradle**

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
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

tasks.named('bootJar') {
    archiveFileName = 'boot-packaging-demo.jar'
}
~~~

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
~~~

Run in the directory containing `build.gradle`:

~~~bash
gradle clean bootJar
java -jar build/libs/boot-packaging-demo.jar
~~~

The command above assumes a compatible Gradle installation is present. In projects with a Gradle Wrapper, prefer `./gradlew clean bootJar` on Linux/macOS or `gradlew.bat clean bootJar` on Windows to use the exact Gradle version pinned by the project. The JAR filename in this example is explicitly set by `archiveFileName`, so you do not have to guess it from the version.

While the application is running, call from another terminal:

~~~bash
curl -s http://localhost:8080/hello
~~~

Exact HTTP response body:

~~~text
Hello from Spring Boot
~~~

Startup log lines, timestamps, PIDs, and ports can vary by environment; do not treat them as fixed stdout. The default port in a standard web configuration is 8080 unless changed by configuration or occupied.

**Who does what in this example?**

1. Gradle reads `settings.gradle` and `build.gradle`, downloads plugins/dependencies, builds the task graph, and invokes the `bootJar` task.
2. JDK 21/toolchain compiles `DemoApplication.java` into bytecode; Gradle also processes resources and dependent task steps.
3. The Boot Gradle plugin assembles the classes and runtime dependencies into runnable `build/libs/boot-packaging-demo.jar`.
4. `java -jar` uses the JVM on the runtime machine to load the executable JAR; the Spring Boot framework initializes the application context and embedded web server from the web starter.
5. The HTTP `/hello` request is handled by the running application, returning the string above. Gradle and the compiler play no part in handling individual HTTP requests.

On deployment machines, you do not need to copy Gradle, Java source files, or a compiler if you already have the right artifact and a compatible Java runtime. Conversely, having only the JDK and Gradle without the Boot plugin or proper packaging config will not ensure an executable Boot JAR is produced.

### What If the Project Uses Maven?

The mental model does not change. `pom.xml` declares dependencies, dependency management, and plugins. Projects using `spring-boot-starter-parent` usually declare `spring-boot-maven-plugin` so the `repackage` goal integrates into the packaging lifecycle. Typical commands:

~~~bash
mvn clean package
java -jar target/my-app.jar
~~~

The actual filename depends on `artifactId`/`version`/plugin configuration. If you do not use the starter parent, you must configure the plugin version, goal/execution, and dependency management accordingly; **do not assume every `mvn package` automatically produces an executable Boot JAR**. When learning Maven, check `mvn help:effective-pom` and phase/goal logs to confirm what actually runs.

## 6. Runtime: What Happens After the Build Finishes

An artifact can build successfully on a laptop yet fail on a server because the **runtime environment** governs:

- **Java runtime version and architecture:** bytecode and native libraries must match the JVM/OS/CPU.
- **Application configuration:** `application.yml`, environment variables, active profiles, system properties, command-line arguments; runtime values can differ from the build machine.
- **External infrastructure:** databases, message brokers, DNS, TLS certificates, credentials, network, and firewalls.
- **Resources and permissions:** memory/CPU, port binding, file permissions, mounted volumes, configuration paths.
- **Deployment mode:** bare-metal server, VM, container, or orchestration; `java -jar` still runs via the JVM inside that environment.

Example **runtime-only Dockerfile** after `bootJar` has generated the artifact:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/boot-packaging-demo.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This image uses a Java 21 **runtime**, without bringing Gradle or a compiler into the container. The `COPY` instruction requires the artifact to be built already and located inside the Docker build context. This is an example of a runtime image, not a multi-stage Dockerfile that compiles from source.

`gradle bootRun` and `java -jar ...` can both run the same application logic, but through different paths: `bootRun` uses the current classpath/build environment, whereas `java -jar` verifies the actual artifact to be distributed. Therefore, before deploying, test the executable artifact with a runtime and configuration as close to the target environment as possible.

## 7. Version Compatibility: Three Distinct Checks

**Check 1 — Can the build tool run on the JVM driving it?** Your Gradle/Maven version must support the JVM used to launch the build tool itself. Failures right when invoking `gradle`/`mvn` may fall into this category, before any application code is compiled.

**Check 2 — Is the Spring Boot plugin compatible with the project's build tool and Java version?** Versions of the Boot Gradle/Maven plugin, Spring Boot framework, Gradle/Maven, and JDK must align with the official compatibility matrix for that specific version. Spring Boot 3.x requires at least Java 17; other Spring Boot lines may change requirements. Do not pick versions simply because one component is "the latest".

**Check 3 — Can the target runtime execute the artifact?** Java class-file version depends on the compile target. For example, Java 17 uses class-file major version 61, and Java 21 uses 65. An artifact compiled for Java 21 and run on Java 17 can fail with `UnsupportedClassVersionError`, even though the build PASSED. Use `--release`/toolchains properly and test on the real runtime to avoid environment drift.

Common inspection commands:

~~~bash
java --version
javac --version
gradle --version
mvn --version
~~~

Run commands only for tools installed on the machine. When using a Gradle Wrapper, `./gradlew --version` is more informative than `gradle --version` because it reflects the project's Gradle version. `gradle --version` reports the JVM running Gradle, not necessarily the compiler toolchain or production JVM.

## 8. Diagnosing Failures by Isolating the Right Layer

| Symptom | Layer to Check First | How to Find the Root Cause |
| --- | --- | --- |
| `javac: command not found` or `javac` unrecognized | JDK / PATH | Check installed JDK, `JAVA_HOME`, `PATH`; distinguish runtime-only images |
| `invalid source release: 21` | Compiler / toolchain | Check which compiler is actually invoked and the configured Java target |
| Gradle fails to start or reports unsupported JVM | Build tool and the JVM running it | Check `./gradlew --version`, Gradle wrapper version, and compatibility |
| Cannot resolve Boot plugin or dependency | Plugin / repository / network | Check plugin version, plugin repositories, Maven Central, proxy, offline mode |
| `bootJar` task does not exist | Plugin / build configuration | Verify the Boot plugin is applied and this is a properly configured Boot app |
| `no main manifest attribute` when running JAR | Artifact type / packaging | You may be running a plain JAR instead of an executable Boot JAR; check task/goal and manifest |
| `Unable to access jarfile` | Artifact path | Check build output, filename, working directory, and read permissions |
| `UnsupportedClassVersionError` | Runtime JVM vs. bytecode | Compare target Java runtime, toolchain, and compile target |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath / dependency / packaging | Check dependency scope, JAR contents, launcher, and missing libraries |
| Boot starts but DB connection fails | Runtime / config / infrastructure | Check URL, credentials, networking, database readiness, and profiles |
| `Port 8080 was already in use` | Runtime / port | Change `server.port` or free the port per environment procedures |

Multi-layer errors can look similar. Read the **stack trace and the actual failing command**, then determine whether it occurred during plugin resolution, compilation, packaging, or startup; do not assume every Boot failure is caused by "Gradle" or "JDK".

## 9. How to Self-Verify and Remember

Use this hands-on exercise to separate the four roles:

1. Compile and run **Hello.java** using only `javac` and `java`. Takeaway: JDK and JVM are sufficient for a minimal Java program.
2. Run `gradle clean bootJar` in the Boot example. Observe Gradle orchestrating tasks, the JDK compiling, and the Boot plugin creating the executable JAR.
3. Inspect the archive with `jar tf build/libs/boot-packaging-demo.jar` (`jar` belongs to the JDK), looking for `BOOT-INF/classes` and `BOOT-INF/lib`.
4. Run `java -jar build/libs/boot-packaging-demo.jar` and call `/hello`. Takeaway: the artifact is executed by the JVM along with its packaged libraries.
5. When deploying, verify the Java runtime, profiles, environment variables, and external services. A PASSING build only verifies the build stage; it does not replace checking real runtime conditions.

Answer three questions for yourself: **"Who compiles the source code?" → JDK/toolchain. "Who decides the build order and packages according to Boot conventions?" → Gradle/Maven and the Spring Boot build plugin. "Who actually runs the application after deploy?" → The JVM in the runtime environment together with the required dependencies/configuration/infrastructure.**

Once you separate these three steps, you will know whether to fix `JAVA_HOME`, the build script, Boot plugin config, or deployment environment config—instead of randomly changing multiple pieces at once.