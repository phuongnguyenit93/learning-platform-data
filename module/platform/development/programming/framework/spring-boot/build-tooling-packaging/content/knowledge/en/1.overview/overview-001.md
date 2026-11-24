# What Problems Do Build and Packaging Tools Solve in a Spring Boot Application?

## 1. The Practical Problem: From Source Code to a Runnable Application

A Spring Boot application is not just Java files. It also depends on Spring Framework, Spring Boot, web libraries, JSON, JDBC, database drivers, configuration files, and resources. When developing on a personal machine, the IDE usually compiles and assembles the classpath automatically, so the application runs. However, when moving to a test machine, server, or CI/CD environment, questions arise:

- Where do we get the **exact right version** of each library? How do we resolve transitive dependencies and version conflicts?
- In what order do we compile dozens or hundreds of Java files, process resources, and run tests?
- How do we hand off **a deterministic deliverable** containing compiled code and required libraries to the deployment environment?
- How do we run the same application version in another environment without opening an IDE, manually constructing a classpath, or recompiling?
- How can a CI machine produce the artifact, run quality checks, and hand it off to the release step through a repeatable process?

A **build tool** such as Maven or Gradle solves automating the process from source to artifact. The **Spring Boot build plugin** adds packaging capabilities tailored to Spring Boot's execution model, especially executable JAR/WAR files and, when needed, OCI container images.

> Key takeaway: building creates a software deliverable in a controlled way; packaging puts that deliverable into a format suitable for the target runtime environment. Together, they bridge development with testing and deployment.

## 2. Distinguishing Build, Package, Run, and Deploy

| Activity | Input → Output | Question Solved |
| --- | --- | --- |
| **Dependency resolution** | Dependency declarations → resolved set of versioned libraries | Which libraries does the application need to compile, test, and run? |
| **Compile / process resources** | Java and resources → compiled classes and processed resources | How do we turn source files into content the JVM can use? |
| **Test / verify** | Compiled code → test and verification results | Is it qualified to move to the next step? |
| **Package** | Classes, resources, runtime dependencies → JAR/WAR or image | How should a single artifact be handed off? |
| **Run** | Artifact and runtime configuration → application process | How does the JVM/container start the program? |
| **Deploy** | Selected artifact/image → an operational environment | How do we deliver that version onto a server, platform, or cluster? |

Building and packaging are artifact preparation steps. Running the application starts a process from that artifact; deploying also requires infrastructure, configuration, networking, data, and a release strategy. Therefore, **a successful build does not guarantee the application will start or serve requests in production**.

## 3. What Challenges Do Maven and Gradle Solve?

### 3.1. Dependency Management Instead of Copying JARs by Hand

Instead of downloading individual JARs, placing them manually in a folder, and maintaining the classpath yourself, a project declares dependencies by group, name, and version—or lets a dependency management mechanism choose versions. Maven/Gradle downloads artifacts from repositories, resolves transitive dependencies, and builds separate classpaths for compile, test, and runtime.

Spring Boot provides a curated set of compatible library versions through the **Spring Boot BOM / dependency management**. This reduces the risk of team members choosing conflicting versions of Spring, Jackson, logging, or servers. However, a BOM does not automatically guarantee that every dependency or upgrade is bug-free; the team must still test and review security.

### 3.2. Automating Repetitive Steps

A single build command can trigger a chain of tasks: processing resources → compiling → testing → creating an archive. The build tool tracks dependencies between tasks/phases and reports failures at the failing step. Every developer no longer needs to remember long sequences of `javac` commands or copy libraries manually.

Maven uses **lifecycles/phases** such as `compile`, `test`, `package`, and `verify`; Gradle uses a **task and dependency graph** such as `compileJava`, `test`, `bootJar`, and `build`. The names and invocation mechanisms differ, but the common goal is to describe the workflow as repeatable configuration.

### 3.3. Standardizing Between Developer Machines and CI

The **pom.xml** or **build.gradle(.kts)** file is the build definition stored alongside source code. Maven Wrapper (**mvnw**) or Gradle Wrapper (**gradlew**) ensures machines use the exact build tool version chosen by the project. Pipelines can run the same commands as a developer's local machine to run tests, produce artifacts, and store results.

Repeatability also depends on the JDK version, dependency repositories, plugin versions, environment variables, and build configuration. Wrappers/BOMs are a useful foundation; when strict reproducibility is required, you also need version pinning, dependency locking/verification, and stable build inputs.

### 3.4. Supporting Large Projects

Build tools model modules, inter-module dependencies, shared tasks, caching, and incremental builds. As a result, as a project grows, the team still has a centralized workflow for compiling and testing instead of fragmented, inconsistent scripts.

## 4. Why Does Spring Boot Need Its Own Packaging Mechanism?

A standard Java JAR contains the project's classes/resources, but **does not by default include all dependent JARs**. If you run it with `java -jar` while dependencies are missing from the classpath, the application can fail with class-not-found errors. Shipping a thin JAR alongside dozens of library JARs and a startup script is possible, but hard to hand off and error-prone.

The Spring Boot Maven Plugin and Gradle Plugin can create an **executable archive**: a JAR/WAR containing application code, resources, runtime dependencies, and the required launcher component. When using an executable JAR, you can start it with a single command:

~~~bash
java -jar my-app.jar
~~~

For a typical executable JAR, the internal structure looks like:

~~~text
my-app.jar
├── META-INF/
├── BOOT-INF/
│   ├── classes/   # application classes and resources
│   └── lib/       # runtime dependency JARs
└── org/springframework/boot/loader/...  # Spring Boot launcher
~~~

Spring Boot's launcher knows how to load classes from nested JARs inside the archive. This differs from simply zipping all files into a ZIP or standard JAR. Launcher class names and format details can vary across Spring Boot versions; the purpose of `BOOT-INF/classes` and `BOOT-INF/lib` remains separating application code from dependency libraries.

**Benefit:** the team can store, test, hand off, and deploy a single deterministic artifact, avoiding having the target environment re-resolve all dependencies or manually construct a classpath. The target machine still needs a compatible Java version and the external services/configuration the application uses.

## 5. Artifact Types and When to Use Them

| Output | Characteristics | Use Case |
| --- | --- | --- |
| **Executable JAR** | Packages the Boot app with runtime dependencies and launcher; usually run with `java -jar` | Standalone Spring Boot services deployed on a VM, server, or container |
| **Executable WAR** | A WAR archive that can also run directly when properly configured | Servlet applications that need to support WAR-style deployment |
| **WAR deployed to an external servlet container** | Requires configuration compatible with the container, dependencies, and app initialization | Systems required to use a separately managed Tomcat/servlet container |
| **Plain JAR** | Standard JAR, usually without full dependencies or the Boot launcher | Libraries or modules meant to be consumed as a dependency by other projects |
| **OCI container image** | Packages the application together with the runtime/container filesystem into an image | Deploying via Docker, Kubernetes, or container platforms |

Not all artifacts are interchangeable. An **application executable JAR** should not by default be used as a **library JAR** for another module: its code resides in `BOOT-INF/classes` and has a different layout from a plain JAR. For typical Boot applications, an executable JAR is the standard choice; a WAR is only needed when external servlet container compatibility is required.

Spring Boot plugins also support **layered archives**: separating dependencies, loader, snapshot dependencies, and application code into layers so container image builders can reuse layers that change infrequently. Layering mainly improves image build/distribution efficiency; it does not replace testing or runtime configuration.

## 6. Specific Roles of the Spring Boot Plugins

Maven/Gradle handles the general build system. The Spring Boot plugin provides tasks tailored to Boot applications:

| Need | Maven + Spring Boot Maven Plugin | Gradle + Spring Boot Gradle Plugin |
| --- | --- | --- |
| Run during development | `spring-boot:run` | `bootRun` |
| Create executable JAR/WAR | `package` combined with configured `repackage` goal | `bootJar` or `bootWar` |
| Run tests | `test` / `verify` via lifecycle and test plugins | `test` / `check` / `build` via task graph |
| Build OCI image with Cloud Native Buildpacks | `spring-boot:build-image` | `bootBuildImage` |

With Maven, **repackage** processes the archive produced by the `package` phase. If you use `spring-boot-starter-parent` and declare the Spring Boot Maven Plugin in the standard way, the `repackage` execution is preconfigured; if you do not use the parent, you must configure the corresponding execution. You should not assume `package` in **every** Maven project automatically produces an executable Boot JAR.

With Gradle, applying the Spring Boot plugin alongside the Java plugin registers the **bootJar** task; `bootJar` is distinct from the **jar** task that creates a plain JAR. Similarly, `bootWar` requires the appropriate WAR setup. When checking the output directory, choose the executable archive rather than assuming every JAR can be run with `java -jar`.

**bootRun / spring-boot:run** is for running the application from the project during development. **bootJar / repackage** is for creating a deliverable artifact. The two are related but not identical: running successfully from an IDE or `bootRun` does not prove the final JAR is packaged properly.

## 7. End-to-End Example: From Source to a Runnable JAR

Suppose you create a project named **demo-build** with Spring Initializr, using Java 17+, adding the Web dependency matching your chosen Spring Boot version, and keeping the generated Maven Wrapper or Gradle Wrapper. Place the following class at **src/main/java/com/example/demo/DemoApplication.java**:

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

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

This class has a `main` method to boot Spring Boot and an HTTP endpoint **GET /ping** returning the string **pong**. It requires Spring Boot and Spring Web dependencies; you cannot run plain `javac` on this file alone without the Spring classpath.

**If the project uses Gradle (Linux/macOS):**

~~~bash
./gradlew clean test bootJar
java -jar build/libs/demo-build-0.0.1-SNAPSHOT.jar
~~~

**If the project uses Maven (Linux/macOS) with the Spring Boot Maven Plugin configured for repackage:**

~~~bash
./mvnw clean verify
java -jar target/demo-build-0.0.1-SNAPSHOT.jar
~~~

On Windows, use **gradlew.bat** or **mvnw.cmd** respectively. The JAR names above illustrate a project/artifact **demo-build** with version **0.0.1-SNAPSHOT**; check the actual filename in **build/libs** or **target** because it depends on your build configuration.

Once the application has started on port 8080 (unless another port is configured), open a second terminal:

~~~bash
curl http://localhost:8080/ping
~~~

Expected HTTP response body:

~~~text
pong
~~~

In this example, the build tool fetched dependencies, compiled, ran tests, and produced the JAR; the Spring Boot plugin packaged the JAR into a runnable structure; and `java -jar` started the process directly from the artifact. You can then move that exact verified JAR to another environment, provided Java, configuration, and dependent services are compatible.

To verify the often-confused steps, compare:

- **./gradlew bootRun**: runs from the build/dev environment; does not prove the executable JAR was created.
- **./gradlew bootJar**: builds the executable JAR; this command itself does not start the server.
- **java -jar ...**: runs the packaged JAR; does not require an IDE, Gradle, or Maven on the target machine.
- **./mvnw package**: builds the artifact via the lifecycle; only produces an executable Boot JAR when the Spring Boot plugin/`repackage` is configured properly.

## 8. From JAR to Container Image and CI/CD

For OCI images, the Spring Boot plugin can use **Cloud Native Buildpacks** to build an image from your application without having to write a Dockerfile by hand:

~~~bash
./gradlew bootBuildImage
~~~

Or in a Maven project with the corresponding plugin:

~~~bash
./mvnw spring-boot:build-image
~~~

This process requires an environment/build service that satisfies the plugin's requirements, typically including a compatible Docker daemon and the ability to pull builder/run images. After creation, the image still needs to be tagged, pushed to a registry, and deployed through its own workflow to run in another environment. **Building an image does not automatically mean it is deployed to production**.

A basic CI/CD pipeline might look like:

1. Check out the exact commit; select the JDK and build tool version via the wrapper.
2. Resolve dependencies; run compilation, tests, and configured checks.
3. Build the executable JAR or OCI image and verify the output.
4. Associate the artifact with the commit/version and store it in an artifact repository or image registry.
5. Deploy **that exact artifact** across environments; supply the required configuration, secrets, and services at runtime.
6. Check health, logs, dependency connectivity, and serving readiness after startup.

The strength of this approach is producing a single traceable release unit. Each server does not have to rebuild from source under differing conditions. However, to ensure the same artifact works across environments, environment-specific configuration must be cleanly externalized from code and build outputs.

## 9. What Build and Packaging Do Not Solve on Their Own

- **Environment-specific configuration:** database addresses, credentials, profiles, downstream endpoints, or feature flags still must be provided appropriately at runtime; avoid embedding secrets directly in a JAR or image.
- **Program correctness:** a successful build only proves the requested build steps completed; it does not replace integration tests, performance tests, or business-logic verification.
- **Runtime compatibility:** a JAR compiled for a newer Java version may not run on an older JVM; the environment must also have the right ports, resources, and external services.
- **Security:** dependency management helps control versions, but does not automatically detect or remove all vulnerabilities; you must monitor CVEs, update libraries/base images, and apply appropriate scans.
- **Operations:** build tools do not automatically provide monitoring, data backups, scaling, rollbacks, or zero-downtime deployment.

A classic example: the JAR build PASSES, but running on the server fails with a missing datasource configuration or database connection error. That is a runtime configuration/environment issue, not proof that Gradle or Maven packaged the app incorrectly.

## 10. Common Errors and How to Diagnose Them

| Symptom | What to Check | How to Fix |
| --- | --- | --- |
| Running JAR fails with **no main manifest attribute** or does not start | Running a plain JAR instead of an executable Boot JAR; missing plugin configuration | Select the `bootJar`/`repackage` output and check main class/plugin configuration |
| **ClassNotFoundException / NoClassDefFoundError** | Missing runtime dependency, wrong scope configuration, or improperly packaged artifact | Inspect the dependency tree/runtime classpath and artifact contents |
| Runs in IDE but fails with **java -jar** | IDE and archive use different classpaths/configurations | Test the final packaged artifact directly in a production-like environment |
| **UnsupportedClassVersionError** | Runtime JDK/JVM is older than the compiled bytecode level | Align Java toolchain and runtime compatibility |
| Local build PASSES but CI FAILS | Differences in JDK, wrapper, plugins, repositories, env vars, or machine-dependent tests | Pin inputs, keep wrapper in VCS, eliminate machine-state dependencies |
| JAR exists but HTTP endpoint is unreachable | App hasn't finished starting, wrong port/profile, failing downstream service, or network block | Check logs/health, bound port, configuration, and environment |
| Image builds successfully but fails when deployed | Mismatched registry/architecture/runtime config, secrets, or dependent services | Inspect image, logs, runtime configuration, environment, and readiness |

Do not treat every startup error by blindly adding dependencies to the build. Identify which step in **resolve → compile → test → package → run → deploy** failed, and inspect the inputs and logs of that exact step.

## 11. Choosing a Tool and Checking Your Understanding

**Maven or Gradle?** Both solve dependency management and build automation. Maven uses clear lifecycles and convention-driven configuration; Gradle offers a programmable task model and flexible build/caching mechanisms. The choice also depends on organizational standards, project structure, and operational capability. With Spring Boot, the core requirement is configuring the plugin properly and producing the right artifact, not the tool's name.

**Three self-check questions:**

1. Why can a JAR containing project classes run in an IDE yet fail with missing-class errors on a server? → The IDE can supply the full runtime classpath; a regular JAR usually does not bundle dependencies. An executable Boot JAR solves this common execution path.
2. Why should you still test `java -jar` before release even if `bootRun` succeeds? → The two execution paths build classpaths and consume artifacts differently; you need to verify the actual deliverable being handed off.
3. Why should the exact same artifact be preserved between testing and production? → It removes variables introduced by rebuilding; if behavior differs, you can isolate the cause to configuration, environment dependencies, or operations.

**Conclusion:** Maven/Gradle turns the build process into repeatable, verifiable steps; Spring Boot build plugins produce artifacts with a clear execution model; and release pipelines receive a traceable JAR/WAR/image. Together, teams reduce dependency errors, cut manual steps, and deliver applications from developer machines to runtime environments more consistently.

### Official References

- Spring Boot — Executable Jar Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html
