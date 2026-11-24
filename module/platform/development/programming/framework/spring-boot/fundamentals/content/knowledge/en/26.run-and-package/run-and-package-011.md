# Boundaries with Build Images, Containers, and Native Executables

Once a Spring Boot application runs via `mvn spring-boot:run` or the Run button in an IDE, work is only complete at the level of **running in a development environment**. To move the application to servers, CI/CD pipelines, or container platforms, we still have to decide how to package it, which runtime to use, and which components belong in the deployment environment.

Three concepts are very easy to confuse:

- **Build image:** creating a *container image* (typically conforming to the OCI format) containing the application along with everything required to run inside a container.
- **Container:** a running instance of a container image, with its own filesystem, network, and resource limits governed by the container platform.
- **Native executable:** a program compiled to machine code for a specific operating system and architecture, commonly using GraalVM Native Image in the modern Spring Boot ecosystem.

A native executable **can reside inside a container image**, though it does not have to. Conversely, a container image **can contain an executable JAR running on a JVM**, without using Native Image at all. Thus "build image" and "build native" are two **relatively independent** decisions, not interchangeable terms.

This lesson clarifies the boundaries from source code to executable JAR, from JAR to container image, from image to container, and from bytecode to native executable. The final part summarizes how to choose based on startup time, memory footprint, build time, compatibility, and production operations.

## 1. Overview Map: From Source to Running Process

A Spring Boot project can follow several paths:

~~~text
                 Java/Kotlin source + resources
                              |
                              v
                        Compile / test
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
             JVM artifact           Spring AOT processing
           executable JAR                 |
                  |                       v
                  |                Native Image compile
                  |                       |
         +--------+--------+              v
         |                 |         Native executable
         v                 v              |
    java -jar         Build OCI image     +----------+
         |                 |              |          |
         v                 v              v          v
     JVM process     Container image  Run directly  Package in
                           |             on OS     OCI image
                           v                            |
                       Container                        v
                       running JVM                  Container
                                                   running native
~~~

Looking at the diagram, there are at least four distinct execution outcomes:

| Deployment mode | Primary artifact | JVM runtime present at runtime? | Container present? |
|---|---|---|---|
| Run executable JAR directly | `app.jar` | Yes | No |
| Run JAR inside a container | OCI image containing JAR and Java runtime | Yes | Yes |
| Run native executable directly | Native binary | Full JVM runtime not needed | No |
| Run native executable in container | OCI image containing native binary and matching OS runtime | Full JVM runtime not needed | Yes |

These are **four execution forms**, not four different frameworks. Business logic can share the exact same Spring Boot source code, yet toolchains, startup characteristics, and runtime constraints are not identical.

### Three Questions to Separate

Before picking tooling, answer:

1. **What do we package the application into?** A JAR, WAR, native binary, or an intermediate set of artifacts?
2. **Which runtime executes the process?** A JVM or an ahead-of-time compiled native executable?
3. **What deploys and isolates the process?** Running directly on a host, inside a container, or via another mechanism?

For example, "running a Spring Boot app in Docker" only answers the third question. It **does not specify** whether the app runs on a JVM or as a native binary.

## 2. First Boundary: Building vs. Running a Project

Inside an IDE, a developer can run the main class directly:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

The IDE normally constructs a classpath from compiled output classes, resources, and dependency JARs, then launches a JVM with the main class. That is convenient during development, though not the only way to deploy.

When building for release, you normally want an artifact that can be tracked, stored, and run independently of the source tree. In Spring Boot, the most common form is an **executable JAR**.

### Building Is Not Running

- **Compile:** turns source code into bytecode/compiled output.
- **Test:** executes tests according to build configuration.
- **Package:** bundles classes, resources, and dependencies into an artifact.
- **Run:** launches a process from an existing artifact.
- **Deploy:** delivers the artifact and configuration to the target environment, operating its lifecycle and monitoring.

A successful `package` command does not prove the app can connect to the production database, activate the right profile, or pass health checks. It proves one stage in the delivery pipeline succeeded.

### An Executable JAR Is Not a Native Executable

A `.jar` file still holds Java bytecode and metadata. When running:

~~~bash
java -jar store-service.jar
~~~

the operating system launches `java`, and the JVM loads classes and executes the application.

Conversely, a native executable is usually invoked directly:

~~~bash
./store-service
~~~

It is a binary compiled for a target OS/architecture, not a renamed JAR file.

## 3. Spring Boot's Executable JAR

Spring Boot supports building an executable JAR structured to run the application alongside its dependencies.

A typical diagram:

~~~text
store-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/store/...
│   │   └── application.yml
│   └── lib/
│       ├── spring-boot-...
│       ├── spring-context-...
│       └── ...
└── org/springframework/boot/loader/...
~~~

Launcher internals can vary across Spring Boot generations, yet the core idea is providing a launcher that loads application classes and dependency JARs bundled inside the archive.

### Why Not Build a Plain Java JAR Only?

A plain Java JAR does not carry all the libraries an application depends on. If you only package your own classes, deployment requires assembling a lengthy classpath of external JARs.

Spring Boot's executable JAR simplifies running:

~~~bash
java -jar store-service.jar
~~~

This is especially helpful when moving an artifact across machines or placing the JAR inside a container.

### Manifest and Launcher

An executable JAR normally has a manifest pointing to the appropriate launcher along with application main class metadata. Do not assume `Main-Class` in the JAR is always `StoreApplication`; in a Boot executable JAR it may point to the Boot launcher, while the application main class sits in separate metadata.

When inspecting, use tooling to read the actual artifact's manifest. Never hand-edit the manifest after building, as that easily breaks launch behavior or creates drift between build and deployment.

## 4. Creating an Executable JAR with Maven or Gradle

With Maven and an appropriate Spring Boot plugin, you can run:

~~~bash
mvn clean package
~~~

The Spring Boot Maven plugin provides the `repackage` goal to turn a standard built JAR into a Spring Boot executable JAR. Whether this goal binds to the default lifecycle depends on the project's plugin/parent configuration.

Plugin example:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

The output typically resides under:

~~~text
target/store-service-0.0.1-SNAPSHOT.jar
~~~

Run:

~~~bash
java -jar target/store-service-0.0.1-SNAPSHOT.jar
~~~

With Gradle and the Spring Boot plugin, the common task is:

~~~bash
./gradlew bootJar
~~~

The artifact typically resides under:

~~~text
build/libs/
~~~

Run on the JVM:

~~~bash
java -jar build/libs/store-service-0.0.1-SNAPSHOT.jar
~~~

Filenames are examples; actual names depend on `group`, `version`, archive configuration, and build setup.

### Do Not Confuse a Plain JAR with a Boot Executable JAR

In some Gradle/Maven projects, a build may produce both:

- A plain JAR intended for use as a library.
- An executable JAR intended for the Spring Boot application.

These two artifacts serve different purposes. A plain JAR may fail under `java -jar` if its manifest/classpath lacks an entry point or dependencies. Verify which artifact your release pipeline actually publishes.

### WAR Is Another Option

Spring Boot also supports packaging WAR archives for systems deploying into external servlet containers when properly configured. That is a packaging option distinct from an executable JAR and **does not imply** running inside an OCI container or as a native executable.

For microservices and typical container deployments, executable JARs are common because they simplify the process model. Legacy environments mandating WARs may still have valid reasons to use them.

## 5. What Is a Container Image?

A **container image** is an immutable content-addressed artifact at a given digest, typically composed of **layers** plus metadata configuring the process, environment, entrypoint, filesystem, and target architecture.

An image can contain:

~~~text
Container image: example/store-service:1.0
├── Base filesystem / OS runtime components
├── Java runtime (if running on JVM)
├── Dependencies or application layers
├── Spring Boot executable JAR
└── Entrypoint / runtime metadata
~~~

An image is **built** first and then **run** as one or more containers. A container is a live running instance with runtime state, a network namespace, and resources managed by the container engine.

### Image vs. Container

| Concept | Mental model | Common operations |
|---|---|---|
| Image | Packaged blueprint and metadata to start processes | Build, tag, push, scan |
| Container | A specific running instance created from an image | Start, stop, inspect, logs |
| Registry | Store and distribution hub for images | Push, pull, access control |
| Volume | Storage mechanism separated from the container's writable layer | Mount, back up, manage data |
| Host/container engine | Infrastructure that creates and runs containers | CPU, memory, networking, isolation |

One image can spawn many containers. Deleting a container does not delete the image. Likewise, data written into a container's writable layer must not be treated as durable storage.

### Containers Are Not Full Virtual Machines

In Linux container environments, containers normally share the host kernel rather than booting a separate kernel like traditional virtual machines. They isolate processes, filesystems, networking, and resources depending on platform configuration.

Thus a container image is not a universal "runs on every OS" guarantee. The OS, CPU architecture, libc, and native dependencies still matter significantly.

## 6. Must an OCI Image Contain a Spring Boot Executable JAR?

No. An OCI image can hold:

- An executable JAR alongside a compatible JRE/JDK.
- A native executable plus required OS libraries.
- A Node.js, Python, Go, or other-language application.
- Various configuration files, scripts, and runtime components by design.

For Spring Boot, the two main models are:

~~~text
JVM container image:
    Base image + JRE + Spring Boot JAR
                         |
                         v
                 java -jar app.jar

Native container image:
    OS runtime layer + native binary
                         |
                         v
                     ./app
~~~

The word "image" in **container image** refers to the filesystem/layer archive artifact, whereas "Native Image" in **GraalVM Native Image** refers to a machine-code compilation technology. Both share the word *image*, yet they belong to **two completely different layers**.

## 7. Using a Dockerfile to Package a JAR

A simple Dockerfile might look like:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Meaning:

1. `FROM` selects a base image carrying a Java runtime.
2. `WORKDIR` creates/sets the working directory.
3. `COPY` copies the built JAR into the image.
4. `EXPOSE` documents the port the application expects to listen on.
5. `ENTRYPOINT` defines the main command executed when the container starts.

This is a minimal example. Production images should also address non-root users, file permissions, security updates, image digests, memory settings, and shutdown handling.

### Building an Image and Running a Container

Once the JAR is built, build the image:

~~~bash
docker build -t example/store-service:dev .
~~~

This creates a local image from the Dockerfile and build context. It **does not start the application**.

To run it:

~~~bash
docker run --rm -p 8080:8080 example/store-service:dev
~~~

This creates and starts a container from the image.

Access the app if the server listens on the matching port:

~~~text
http://localhost:8080
~~~

Here `-p 8080:8080` maps the host port to the container port. Simply writing `EXPOSE 8080` in a Dockerfile **does not publish ports to the host**.

### Why Copying the Right Artifact Matters

A Dockerfile line like:

~~~dockerfile
COPY target/*.jar /app/app.jar
~~~

can misbehave if `target` contains multiple JARs or an unintended artifact. In real projects, ensure the build produces predictable output or pass an explicit artifact name so CI fails cleanly on packaging errors instead of silently grabbing the wrong JAR.

### `.dockerignore`

The build context can include many unnecessary files. Example:

~~~text
.git
.idea
.vscode
node_modules
target/*
!target/store-service-0.0.1-SNAPSHOT.jar
~~~

This intentionally retains only the specific JAR needed inside the image. Ensure ignore rules match your project's build context structure.

Avoid sending full source history, credentials, IDE files, or caches into the Docker build context unnecessarily. Smaller images and trim contexts make builds faster, cleaner, and less prone to leaking sensitive files.

## 8. A Dockerfile Does Not Compile Java by Itself

In the example above:

~~~dockerfile
COPY target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar
~~~

the Dockerfile assumes the JAR **already exists**. If the build hasn't run yet or produced a different JAR version, image creation either fails or packages an old artifact.

Distinguish two patterns:

**Model A — build outside Docker:**

~~~text
CI runs Maven/Gradle
         |
         v
     Executable JAR
         |
         v
     docker build
         |
         v
     Container image
~~~

**Model B — multi-stage Docker build:**

~~~text
Docker build stage
         |
         v
Maven/Gradle compiles app
         |
         v
Creates executable JAR
         |
         v
Runtime stage copies artifact
         |
         v
Minimal runtime container image
~~~

Multi-stage builds keep build tools out of the runtime image, though you still must manage caching, dependency downloads, toolchain versions, and reproducibility.

### Conceptual Multi-Stage Example

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /workspace
COPY pom.xml .
COPY src ./src

RUN mvn -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This illustrates the **build stage and runtime stage** split. A real Maven project may involve parent POMs, multi-module dependencies, `.mvn`, Maven wrapper, settings, or repository credentials, so never copy this snippet blindly without accounting for project structure.

`-DskipTests` only keeps the image build example brief; a release pipeline still needs to run tests at an appropriate stage per project policy.

## 9. Spring Boot `build-image`: Building Without Writing a Dockerfile

Spring Boot provides goals/tasks capable of creating OCI-compatible container images via **Cloud Native Buildpacks**.

With Maven and an appropriate Spring Boot Maven plugin:

~~~bash
mvn spring-boot:build-image
~~~

With Gradle and an appropriate Spring Boot plugin:

~~~bash
./gradlew bootBuildImage
~~~

These commands use buildpacks/builders to package the app and metadata into a container image. In standard setups, a compatible container runtime/daemon endpoint accessible to the plugin is needed, along with access to fetch builder/run images and dependencies.

### What Are Buildpacks?

Cloud Native Buildpacks detect the application type, select build/runtime components, assemble layers, and produce an OCI image. Rather than authoring every instruction in a Dockerfile, buildpacks apply standardized packaging logic.

Conceptual flow:

~~~text
Spring Boot project
       |
       v
Spring Boot build-image task/goal
       |
       v
Builder + buildpacks
       |
       +--> Detect Java application
       +--> Select runtime/components
       +--> Create application layers
       +--> Configure launch process
       |
       v
OCI container image
       |
       v
docker run / container runtime
~~~

This does not mean buildpacks "avoid containers." The builder may use a container runtime during the build. It simply means developers **do not have to write a custom Dockerfile** to obtain a standard buildpacks-produced image.

### `build-image` Does Not Run the Application

The command:

~~~bash
mvn spring-boot:build-image
~~~

is an **image artifact build** step, not an invocation that starts the server to handle traffic. Once the image is produced, you still run it via a container engine or deploy it to your target environment.

### Selected Benefits of Buildpacks

Depending on the chosen builder and buildpacks, they can offer:

- Separate dependency and application layers for better cache reuse.
- Java runtime selection matched to configuration.
- Launch process and runtime environment setup.
- Support for non-root execution and security defaults.
- Metadata supporting image management and software supply chain visibility.
- Base runtime layer rebasing/updating in supported scenarios.

Do not assume every capability applies universally to every builder. Exact behavior depends on builder/buildpack versions, registries, and operational policies.

## 10. How Do Buildpacks Differ from Dockerfiles?

| Criterion | Buildpacks via Spring Boot | Dockerfile |
|---|---|---|
| Starting point | Project/artifact + builder/buildpacks | Dockerfile and build context |
| Who designs packaging steps | Buildpacks/builder | Developers/platform team |
| System customization | Via builder, env, bindings, supported extensions | Via Dockerfile stages and instructions |
| Base image control | Governed by builder/run image | Explicitly picked via `FROM` |
| Caching/layers | Managed by buildpacks | Managed by Dockerfile/build engine |
| Best suited for | Standard Spring Boot services minimizing Dockerfile upkeep | Cases needing bespoke control |
| Automatically yields native executable? | Not by default in every configuration | No; depends on build stages |
| Output | Container image | Container image |

Do not conclude buildpacks are always better than Dockerfiles or vice versa. Decide based on platform standards, customization needs, security rules, and team operational skills.

### When to Start with Buildpacks?

If your Spring Boot app is a standard service needing no special OS packages and your organization accepts a managed builder, buildpacks are a sensible starting point.

### When Is a Dockerfile More Useful?

For instance:

- Requiring custom OS libraries absent from the builder.
- Needing a non-standard build pipeline.
- Coordinating multiple artifacts or non-Java tooling in one image.
- Requiring granular control over runtime stages, file ownership, or image layout.
- Operating inside CI/CD pipelines standardized on audited Dockerfiles.

Even when authoring Dockerfiles, adhere to image minimalism, vulnerability scanning, reproducible builds, and non-root execution.

## 11. Layered JARs and Image Layers

A Spring Boot executable JAR can carry **layering** metadata. The idea is separating components that change at different rates:

~~~text
Infrequently changing dependencies
           |
Spring Boot loader
           |
Snapshot dependencies
           |
Application classes/resources
~~~

When assembling an OCI image, stable pieces sit in better-cached lower layers. Changing a single Java class no longer forces rebuilding or re-uploading every dependency layer.

### A Layered JAR Is Not Itself a Container Image

A JAR structured for layering is still a **JAR**; layer metadata merely guides image tools on how to split contents when creating an image.

Conversely, an OCI image consists of filesystem layers under the container specification. The two are related yet live at different layers:

~~~text
Spring Boot layered JAR metadata
            |
            v
Image build tool uses metadata
            |
            v
OCI filesystem layers
~~~

### Does a Layered JAR Speed Up Native Images?

Not by the same mechanism. Native Image compiles bytecode and performs reachability analysis to emit a binary rather than merely placing dependency JARs into runtime layers.

Container layer caching can still help CI pipelines, yet **layered executable JAR optimizations do not translate directly into native binary optimizations**.

### Beware of Outdated Guides

CLI syntax for layer extraction and `jarmode` can change across Spring Boot generations. Always follow documentation matching your Spring Boot version rather than copying deprecated `jarmode` commands.

## 12. Native Executable: A Different Kind of Artifact

Spring Boot supports creating a **native executable** via Spring AOT and GraalVM Native Image with a compatible toolchain.

Instead of:

~~~text
Java bytecode -> JVM load/interpret/JIT at runtime
~~~

the high-level model is:

~~~text
Java bytecode + application metadata
                   |
                   v
            Spring AOT processing
                   |
                   v
        GraalVM Native Image analysis
                   |
                   v
      Machine-code native executable
                   |
                   v
           OS executes binary directly
~~~

A native executable is a binary compiled for a **target operating system and CPU architecture**. It is neither a renamed `.jar` nor an OCI image.

### Native Image Still Involves Java

Applications are still written in Java/Kotlin using Spring Framework APIs. The difference is shifting much of the analysis and compilation to **build time**, producing an executable that runs without installing a full JVM runtime as required by JARs.

A native binary still contains runtime support code and may require OS libraries; "no full JVM runtime needed" does not mean "zero runtime components."

### Why Does Native Attract Interest?

Scenarios that often benefit:

- Fast startup, suited for rapidly scaling workloads.
- Potentially lower baseline/idle memory overhead.
- No JRE/JDK installation required directly in the runtime host/image.
- Fewer runtime classloading and JIT warmup steps.

These are **potential gains**, not a guarantee every workload runs faster or uses less memory in every scenario. Always measure on your actual application.

## 13. What Does Spring AOT Do During a Native Build?

Spring's **Ahead-of-Time (AOT) processing** prepares information at build time that traditional Spring applications normally discover dynamically at runtime.

In JVM mode, Spring relies heavily on dynamic mechanisms:

- Component scanning.
- Reflection to locate constructors, methods, and annotations.
- Dynamic proxies.
- Conditional bean registration.
- Classpath resource loading.
- Serialization/deserialization.
- Environment- and classpath-driven configuration.

GraalVM Native Image operates under build-time reachability analysis and a closed-world assumption. Not every piece of code or resource accessed only via runtime reflection or string names can be inferred automatically.

Spring AOT generates code and metadata describing required components for the native runtime so Spring Boot features work inside a native executable.

### Two Layers to Distinguish

| Component | Responsibility |
|---|---|
| Spring AOT | Prepares bean registrations and reachability metadata/hints for native builds |
| GraalVM Native Image | Analyzes and compiles the application plus dependencies into a native binary |

Spring AOT **does not replace** the Native Image compiler; nor can Native Image magically infer Spring's dynamic mechanisms without sufficient metadata.

### AOT Is Not Ordinary JVM Tuning

A JVM application can consume AOT-generated artifacts in supported contexts, yet native builds focus on feeding data to produce a native binary. Do not confuse Spring AOT with the JVM's JIT compiler.

## 14. Building a Native Executable Directly

With Spring Boot 3.x and matching plugins, a typical Maven workflow might look like:

~~~bash
mvn -Pnative native:compile
~~~

This command only works when the project already configures native build support—such as GraalVM Native Build Tools profiles/plugins and Spring Boot AOT integration. Arbitrary `pom.xml` files do not automatically include a `native` profile.

With Gradle and the Native Build Tools plugin configured:

~~~bash
./gradlew nativeCompile
~~~

The build relies on a Native Image-capable toolchain alongside required compilers and system dependencies.

Upon success, the binary may appear in an output directory such as:

~~~text
target/
build/native/nativeCompile/
~~~

Exact paths and executable names vary by plugin, operating system, and build configuration.

### Do Not Run `nativeCompile` When You Only Want a JAR

`nativeCompile` is not an alias for `bootJar`. It can consume substantial CPU, memory, and build duration to emit a platform-specific binary.

If your deployment only expects Java 21 and a JVM container, an executable JAR suffices; native builds are an optimization choice, not a mandatory step.

### Building Requires a Target-Compatible Environment

Native executables tie tightly to OS, CPU architecture, and native library linkage. A binary compiled on Linux x86-64 cannot simply execute on macOS ARM64, and vice versa.

Align build hosts and target platforms or use toolchain-supported cross-build mechanisms. In CI, native builds normally run on runners matching the deployment architecture.

## 15. Native Executables Are Not Automatically Compatible with Every Library

Java on the JVM is highly flexible with reflection, classpath scanning, dynamic class loading, and runtime bytecode generation. Native Image requires far more call paths and metadata to be known at build time.

Cases requiring extra attention:

- `Class.forName(...)` with dynamically computed class names.
- Reflection locating constructors/methods not inferred by the framework.
- Serialization/deserialization of dynamically chosen types.
- Resource files looked up purely by runtime-assembled names.
- JNI or native libraries with special linking/loading needs.
- Dynamic proxies over insufficiently described interfaces.
- Frameworks generating classes/bytecode at runtime.
- `ServiceLoader` or plugin architectures needing reachability metadata.
- Static class initialization with side effects tied to the build environment.

Spring Boot and supported libraries ship built-in runtime hints, yet **there is no guarantee every Java library compiles to native untouched**.

### Dynamic Reflection Example

~~~java
String className = settings.getHandlerClassName();

Class<?> type = Class.forName(className);
Object handler = type.getDeclaredConstructor().newInstance();
~~~

If `className` only appears in runtime configuration, the native compiler may have no way to retain that class and grant reflective access ahead of time.

One fix is replacing dynamic class lookup with an explicit Spring bean registry, or registering exact reachability metadata/runtime hints for the reflectively accessed types.

### Resource Files in Native Images

Example:

~~~java
InputStream stream =
        getClass().getResourceAsStream("/rules/payment.json");
~~~

In a JVM JAR, classpath resources resolve as expected. In a native binary, resources may need explicit registration to be bundled into the native executable.

Never assume "the file sits in `src/main/resources`, so the native executable definitely includes it." Understand resource reachability and build-tool metadata.

## 16. Runtime Hints: When Dynamic Access Must Be Declared

Spring provides runtime hints APIs for native/AOT scenarios. Example registrar:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader
    ) {
        hints.reflection().registerType(
                PartnerPayload.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );

        hints.resources().registerPattern(
                "partner/templates/*.json"
        );
    }
}
~~~

`PartnerPayload` is an illustrative class. `RuntimeHints` declares reflective invocation and resource patterns the native build must preserve.

One way to register it in supported Spring versions:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerRuntimeHints.class)
public class PartnerConfiguration {
}
~~~

Import `org.springframework.context.annotation.ImportRuntimeHints` and related types. This illustrates scenarios with **genuine runtime dynamic requirements**; not every Spring Boot application needs hand-authored runtime hints.

### Do Not Register Every Class Blindly

Overly broad metadata bloats binary size, pulls dead code into the executable, and masks design flaws. When troubleshooting native errors, pinpoint which exact class or resource is missing, which access kind is needed, and whether the library officially supports native mode.

### Do Not Confuse Spring Runtime Hints with a Dockerfile

Runtime hints participate in **native executable analysis and compilation**. A Dockerfile governs **packaging and running the artifact inside a container**. Adding a `COPY` instruction to a Dockerfile will not fix missing reflection metadata inside an already-compiled native binary.

## 17. Building an Image Containing a Native Executable

Two steps can work together:

~~~text
Build native executable
        |
        v
    app binary
        |
        v
Build OCI image containing binary
        |
        v
Run container executing binary
~~~

Simple illustrative runtime Dockerfile:

~~~dockerfile
FROM debian:bookworm-slim

WORKDIR /app

COPY build/native/nativeCompile/store-service /app/store-service

RUN chmod +x /app/store-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/store-service"]
~~~

This assumes the binary was built for Linux and matches system libraries inside the base image. Depending on linkage, the executable may depend on glibc, CA certificates, timezone data, or other native libraries. If the base image is overly stripped down, the binary may fail to launch even though `docker build` succeeded.

### Why Can't You Drop a Linux Binary into Any Arbitrary Image?

Dynamically linked native binaries expect matching OS loaders and shared libraries. A base image using a different `libc` or missing required libraries causes runtime crashes.

Unlike a JVM JAR handled through a suitable JVM runtime, a native binary binds much more tightly to its compilation/linking platform. Always verify image OS/architecture and runtime shared libraries.

### A Smaller Image Does Not Prove Native Runs Faster

Image size measures layer storage/transfer footprint. Startup time measures time until process readiness. RSS memory measures one dimension of RAM consumption. Throughput and latency measure performance under load.

These metrics relate, yet **none substitutes for another**. A tiny image can still boot slowly waiting on a database; a small native binary can still deliver lower steady-state throughput than a warmed-up JVM on certain workloads.

## 18. Buildpacks Can Also Produce Native Images

Certain builders/buildpacks support GraalVM Native Image mode. Spring Boot plugins can configure `build-image` to enable this mode depending on plugin and builder versions.

Illustrative Maven example once native build support is configured in the project:

~~~bash
mvn -Pnative spring-boot:build-image
~~~

In buildpack environments supporting Native Image, a buildpack environment variable may look like:

~~~text
BP_NATIVE_IMAGE=true
~~~

Exact activation depends on the builder, buildpack, and Spring Boot plugin version. Do not assume setting `BP_NATIVE_IMAGE` inside a running application magically converts a JVM image into a native image.

### What Actually Happens?

~~~text
Spring Boot project
          |
          v
Boot build-image + native-capable buildpacks
          |
          +--> Spring AOT processing
          +--> GraalVM Native Image compile
          +--> Native binary
          +--> OCI image assembly
          |
          v
OCI image running native executable
~~~

The output is a **container image holding a native executable**. Never call that output a "native JAR" or "JVM container" if the process actually runs a native binary.

### Native Buildpacks Still Require Heavy Build Resources

Native Image compilation can consume substantially more RAM and CPU than packaging a JAR. In CI, allocate adequate resources to the builder and cap concurrency if several services compile simultaneously.

Running the native build inside a container standardizes the toolchain, yet it does not eliminate compilation cost.

## 19. Comparing JVM JAR and Native Executable

| Aspect | JVM executable JAR | GraalVM native executable |
|---|---|---|
| Format | JAR containing bytecode and dependencies | Machine-code binary for target platform |
| Required runtime | Compatible JVM/JRE | No full JVM needed; matching OS runtime still required |
| Build time | Typically shorter | Typically longer due to analysis and native compilation |
| Startup | Includes JVM and framework initialization cost | Often capable of much faster startup |
| Memory | JVM heap, JIT/code cache, and runtime overhead | Often smaller memory footprint in some workloads |
| Peak throughput | JVM JIT optimizes hot paths well after warmup | Depends on binary, compilation, and workload |
| Dynamic reflection/classloading | More flexible | Requires attention to reachability metadata |
| Portability | JAR runs on any OS with a compatible JVM | Binary tied to target OS/architecture |
| Observability | Familiar JVM profiling, JFR, heap dumps | Tooling and observability options differ |
| Debugging | Standard Java/JVM debugging workflows | Involves native symbols/toolchain concerns |
| Packaging into OCI image | Yes | Yes |
| Best suited for | Standard services, dynamic libraries, fast builds | Cold-start or memory-sensitive workloads with solid native support |

Never turn this table into a blanket claim that "native is better than JVM." A high-throughput, long-lived service with time to warm up can benefit hugely from JVM JIT optimizations. A short-lived job or scale-to-zero service can benefit strongly from rapid native startup.

**Benchmarking on real workloads decides.**

## 20. The Same Codebase Can Support Two Release Strategies

Suppose a system has three services:

~~~text
checkout-service     -> JVM container
billing-worker       -> JVM container
small-scheduled-job  -> native container
~~~

An entire platform does not have to switch to native all at once.

### Why Choose a Mix?

- Long-running web services under sustained load may favor JVM throughput and familiar debugging tools.
- Short-lived scheduled jobs may prioritize startup latency.
- Services relying on heavy reflection/plugin libraries may not yet suit native builds.
- One group of apps may standardize on buildpacks while another requires custom Dockerfiles.

Architecture should keep APIs and integration contracts stable; runtime packaging details should not leak into business logic unnecessarily.

### Never Switch Build Modes Unintentionally Across Environments

If tests run exclusively on the JVM JAR while production deploys a native executable, native-only reflection or resource issues will slip through. Pipelines must test the **actual artifact type being deployed**.

## 21. Configuration Boundaries: Never Bake Environments into Images

A well-designed image is built to be reused across environments with varying configuration:

~~~text
One image by digest
          |
          +--> dev: dev DB + dev credentials
          |
          +--> staging: staging DB + staging credentials
          |
          +--> prod: prod DB + prod credentials
~~~

The same artifact runs with different environment variables, mounted configs, or secret management across stages. This prevents "same source code, different artifact" drift between staging and production.

Example:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=8080 \
  example/store-service:1.0
~~~

Here configuration is injected when **running the container**, not baked into the image at build time.

### `spring.profiles.active` in Containers

Spring Boot reads profiles from `Environment` following precedence rules:

~~~yaml
spring:
  profiles:
    default: local
~~~

When the container sets:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

the `prod` profile activates without modifying the image.

Never embed database passwords, API keys, or production credentials inside a repository-committed `application-prod.yml` or inside image layers. Use platform-managed secrets with strict access controls.

### Build-Time vs. Runtime Configuration Differ

| Data | When is it typically needed? |
|---|---|
| Java source, dependency versions, compiler flags | Build time |
| Native reflection/resource metadata | Native build time |
| Builder/run image and architecture | Build/image assembly |
| Database URL, credentials, active profile | Runtime |
| Service port, logging level | Runtime |
| Feature flags affecting bean registration | Runtime startup |
| Secrets required during image build | Only when strictly needed, using dedicated build-secret mechanisms |

Never smuggle runtime secrets into build arguments or Dockerfile `ENV` lines hoping layer history hides them.

## 22. Native Builds Sharpen the Build-Time vs. Runtime Boundary

In JVM mode, apps discover many things dynamically at startup. With native executables, certain reachability and class-initialization decisions move to build time.

Suppose an app defines two beans:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "app.payment.mode",
            havingValue = "mock"
    )
    PaymentGateway mockGateway() {
        return new MockPaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.payment.mode",
            havingValue = "live"
    )
    PaymentGateway liveGateway() {
        return new LivePaymentGateway();
    }
}
~~~

With native/AOT, keep in mind that **not every runtime property change can materialize a class or bean excluded during build analysis**. Spring AOT handles conditions and reachability in supported ways, yet build-time condition evaluation can constrain runtime combinations.

Therefore, for native applications, explicitly test every profile/property combination production requires. Never assume toggling an environment variable lets a native binary dynamically load brand-new plugins or classes the way a JVM classpath can.

### Avoid Reading Production Environments During Native Builds

Build pipelines must produce reproducible artifacts without connecting to production databases or reading runtime secrets. If static initializers or build-time hooks call external services, native compilation becomes improperly coupled to the build environment.

Keep build-time initialization cleanly separated from side effects permitted only when the live application runs.

## 23. Container Networking: `localhost` Is Not the Host in the Usual Sense

A common pitfall when moving Spring Boot from an IDE into containers is the database URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/store
~~~

Inside a container, `localhost` normally refers to **that container's own network namespace**. If the database runs in a separate container, `localhost` will not reach it.

For example, in a container network with a database service named `postgres`:

~~~properties
spring.datasource.url=jdbc:postgresql://postgres:5432/store
~~~

Actual networking and DNS names depend on your container orchestrator or Docker Compose setup.

### `EXPOSE` and `-p` Differ

In a Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

primarily serves as metadata indicating the intended port.

The command:

~~~bash
docker run -p 8081:8080 example/store-service:dev
~~~

maps host port `8081` to container port `8080`.

Inside the application:

~~~properties
server.port=8080
~~~

sets the port Spring Boot's web server listens on inside the container.

These are three distinct settings; if they disagree, traffic cannot reach the server.

### Bind Address

If an app binds solely to `127.0.0.1` inside a container, host port publishing will fail to reach it. When serving across a container network, verify the server binds to an appropriate interface such as `0.0.0.0` per platform networking policy.

Never "fix" networking bugs by exposing internal ports to the public internet; production requires proper ingress, network policies, TLS, and authentication.

## 24. Container Data and Filesystems

Containers have writable layers, yet those are rarely suitable for durable business data.

Suppose Spring Boot receives an upload:

~~~text
/app/uploads/invoice.pdf
~~~

If saved into the container's writable layer and the container is later replaced, that data vanishes. For durable data, use:

- Databases or appropriate object storage.
- Managed persistent volumes.
- External backed-up filesystems.
- Upload/persistence workflows with retries and integrity checks.

### Native Mode Does Not Solve Persistence

Both JVM and native processes face the exact same ephemeral container filesystem semantics. Switching to a native executable does not make files inside a container durable.

### File Permissions and Users

A container running as a non-root user cannot write to a directory owned by `root` in the image. That is a packaging/runtime permission problem, not Spring dependency injection or native compilation.

If temporary writes are required, provision writable directories with proper permissions or mount a volume. Never run as `root` blindly just to bypass permission errors without assessing risk.

## 25. Process Lifecycle, PID 1, and Graceful Shutdown

In a Dockerfile, **exec-form `ENTRYPOINT`** is a strong default:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

When the Java process runs as the container's main process, stop signals from the container runtime reach it directly.

A shell form like:

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

can spawn a shell as PID 1 and complicate signal forwarding depending on implementation. If an entrypoint wrapper script is necessary, hand off to the app process via `exec`:

~~~sh
#!/bin/sh
exec java -jar /app/app.jar
~~~

### Container Stop and Spring Boot Shutdown

Desired flow:

~~~text
Orchestrator wants to stop container
                |
                v
         Send stop signal
                |
                v
       JVM/native process receives it
                |
                v
       Spring ApplicationContext closes
                |
                +--> Stop accepting new work
                +--> Wait for in-flight work
                +--> Close connection pools
                +--> Run destruction callbacks
                |
                v
          Process exits
~~~

Spring Boot supports graceful web server shutdown in supported versions. Example:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Actual shutdown duration remains bounded by the container orchestrator. If the platform waits only a few seconds before sending a forced kill, setting a longer timeout inside Spring will not guarantee requests finish.

### Native Processes Also Need Proper Shutdown

A native executable does not eliminate cleanup needs. It still manages network connections, thread pools, file handles, and lifecycle callbacks. Test graceful shutdown on the **exact runtime mode you deploy**.

## 26. Health Checks and Readiness

A container in status "running" does not mean the application is ready for traffic. The process might still be:

- Booting the Spring `ApplicationContext`.
- Executing database migrations.
- Unable to reach a mandatory dependency.
- Temporarily overloaded or unable to serve new requests.

Spring Boot Actuator provides health endpoints when added and configured. Example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Typical endpoint:

~~~text
/actuator/health
~~~

In orchestrators like Kubernetes, readiness/liveness probes can target dedicated probe groups when enabled and configured.

### Liveness vs. Readiness

| Probe | Question | Consequence on failure |
|---|---|---|
| Liveness | Is the process in a healthy state that should stay alive? | Platform may restart the container |
| Readiness | Can this instance currently serve traffic? | Platform pauses routing requests to it |
| Startup probe | Has startup finished so other probes can start? | Prevents false restarts on slow starts |

Do not include every external dependency inside liveness checks. If a database blips and every pod restarts simultaneously, the outage worsens. Align health probes with what the orchestrator actually does when each probe fails.

### JVM and Native Have Different Startup Profiles

Because native processes start faster, probe delays/thresholds may differ. Still, never slash timeouts blindly based on one fast local startup. Real startup also includes config loading, DNS, TLS, migrations, cache warmups, and infrastructure connections.

## 27. Logging and Observability Across Container Boundaries

In containers, the standard approach is writing logs to `stdout`/`stderr` for platform collection:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(StoreApplication.class);

log.info("Store service started");
~~~

Inspect development logs via:

~~~bash
docker logs <container-name-or-id>
~~~

In production, log collectors gather, enrich, and ship logs to observability backends.

### Never Treat Docker Logs as Permanent Storage

Retention and searchability depend on log drivers, platform configuration, and collectors. If strict auditing is mandatory, write durable audit records rather than relying solely on a log line.

### JVM and Native Differ in Observability

On the JVM, familiar tools like heap dumps, Java Flight Recorder (JFR), and JVM metrics are readily available. Native executables carry different observability support; Spring/Micrometer APIs and metrics still work in supported configurations, yet low-level runtime tooling differs.

When adopting native, evaluate monitoring and profiling tools upfront—not just startup speed.

## 28. CPU and Memory Configuration in Containers

Containers enforce CPU/memory limits, yet JVM and native runtime tuning differ.

For JVM images, consider adjusting:

- Heap sizing or `MaxRAMPercentage`.
- CPU awareness matching container quotas.
- Thread pools and database connection pools.
- Metaspace, code cache, and native off-heap memory.
- Garbage collector tuning where genuinely warranted.

Example passing JVM options:

~~~bash
docker run --rm \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0" \
  example/store-service:dev
~~~

`JAVA_TOOL_OPTIONS` is a standard JVM mechanism for passing startup flags; evaluate specific percentages against actual heap, non-heap usage, and container limits rather than treating any number as universally optimal.

For native executables, JVM flags like `-XX:MaxRAMPercentage` do not apply the same way as with `java -jar`. Native runtimes expose their own flags depending on GraalVM Native Image version and build configuration.

### Never Compare Memory by Heap Alone

A JVM with a 256 MB heap still allocates thread stacks, class metadata, JIT code cache, and native buffers. Native processes also consume non-heap memory. Always compare total RSS/working set and peak memory under identical workloads and container limits.

### Fast Startup Does Not Guarantee High Throughput

A REST service running continuously for hours can achieve stronger throughput once the JVM JIT optimizes hot code paths. A native executable may win cold starts yet lag under sustained heavy load. Choose based on real SLAs.

## 29. Build-Time Caching and Runtime Performance Are Different Axes

Fast artifact packaging is a pipeline goal; fast startup is a runtime goal. They interact, yet they are not synonymous.

~~~text
Build pipeline
    |
    +--> Compile speed
    +--> Dependency caching
    +--> Docker/buildpack layer cache
    +--> Native compilation cost
    |
    v
Artifact ready
    |
    v
Runtime
    |
    +--> Process startup
    +--> Application readiness
    +--> Memory use
    +--> Throughput
    +--> Latency
~~~

A native build may take longer to produce an artifact in exchange for faster runtime startup. If teams deploy dozens of times daily, build cost matters; if instances constantly scale from zero, startup speed may dominate.

### What Metrics to Measure?

Collect:

- Clean build and incremental build times.
- Artifact and container image sizes.
- Time from process launch to readiness.
- Peak RSS and steady-state memory usage.
- CPU usage during startup and under load.
- P50/P95/P99 latency and throughput.
- Shutdown duration and in-flight request draining.
- Compatibility friction and runtime-hint maintenance overhead.

Never choose native solely off an artificial "Hello World" startup demo unrepresentative of your real application.

## 30. Reproducibility and Image Supply Chain

A tagged image:

~~~text
example/store-service:latest
~~~

is not an immutable identifier. Tags can be reassigned to new image contents.

An image digest pins exact image contents:

~~~text
example/store-service@sha256:<digest>
~~~

In production, deploying by digest or enforcing strict immutable tag policies prevents deploying the wrong artifact.

### Helpful Practices

- Pin dependency versions via BOM/lockfiles where suitable.
- Track base image versions and apply security updates.
- Produce images from repeatable CI pipelines.
- Exclude unnecessary packages from runtime layers.
- Scan both dependencies and container images for vulnerabilities.
- Run as a non-root user whenever possible.
- Restrict runtime filesystem and network privileges.
- Never embed secrets inside image layers.
- Record build metadata and commit SHAs for artifact provenance.
- Sign images and enforce artifact attestation when policy requires it.
- Maintain SBOMs and track dependency licenses.

### Native Images Are Not Immune to Vulnerabilities

A native executable embeds library code compiled at build time. When a vulnerability affects a dependency or runtime component, you normally must **rebuild the binary** and redeploy. Swapping a container base image does not patch vulnerable libraries statically linked or compiled into an existing native binary.

Likewise, in JVM images, updating the Java runtime base image patches the JVM/OS layer yet does not upgrade application libraries inside the JAR.

## 31. Multi-Platform and Multi-Architecture Deployments

When deploying across both x86-64 and ARM64, verify three layers:

1. **Container image platform:** image OS and CPU architecture.
2. **Runtime inside the image:** architecture-matching JRE/JDK or native binary.
3. **External native libraries:** matching JNI drivers and system libraries.

A Java JAR can run across architectures when paired with a matching JVM and compatible native libraries. However, an OCI image containing an x86-64 JRE does not become an ARM64 image merely because the JAR itself is cross-platform.

For native executables, binaries must be compiled for each target platform unless your toolchain supports targeted cross-compilation.

### Multi-Arch Images

A single registry tag can point to an image index/manifest list referencing multiple architecture variants, letting the container runtime pull the variant matching its host.

Building genuine multi-arch images requires building artifacts for every included architecture. Never label a single-architecture binary image as "multiarch."

## 32. Native Builds and Class Initialization

One distinctive aspect of Native Image is **class initialization timing**. Depending on rules and compiler configuration, some classes initialize at build time while others initialize at runtime.

Example of an unsuitable design:

~~~java
public final class ProductionConfig {

    static final String TOKEN =
            System.getenv("PAYMENT_API_TOKEN");

    private ProductionConfig() {
    }
}
~~~

If that class initializes during native compilation instead of runtime, the environment value can be frozen incorrectly or cause secret/config leaks. Never place runtime secret reading, socket opening, or connection creation inside static initializers without understanding Native Image initialization phases.

Prefer reading configuration at runtime startup via Spring `Environment`, `@ConfigurationProperties`, or properly lifecycle-managed services:

~~~java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        String apiToken,
        URI endpoint
) {}
~~~

When using native/AOT, verify Spring supports the bound property types and supply metadata if dynamic types require it. Never treat native builds as an excuse to pull runtime secrets into build time.

## 33. Test Strategy for JVM and Native

A practical testing strategy spans multiple layers:

| Layer | Purpose |
|---|---|
| Unit tests | Verify business logic |
| Spring context tests on JVM | Verify DI, configuration, repositories, HTTP wiring |
| Container smoke tests | Confirm image boots and ports, networking, env, and health work |
| Native smoke tests | Confirm native binary boots and reflection/resources work |
| Native integration tests | Exercise critical use cases inside the native runtime |
| Performance tests | Compare startup, memory, latency, and throughput under realistic load |

If production runs a native executable while tests run solely on the JVM, native-only failures will escape into production.

### What to Watch in Native Smoke Tests

- Does the Spring context register every needed bean?
- Does JSON serialization/deserialization work with real DTOs?
- Are classpath resources discovered properly?
- Do JPA/ORM queries execute with needed metadata?
- Do proxies, transactions, and security behave as expected?
- Are native libraries and TLS certificates available?
- Do runtime profiles and environment variables take effect?
- Do health probes and graceful shutdown behave cleanly?

Verify all of these in native mode rather than assuming a clean native compile guarantees full functional parity.

### Testing Images Properly

After building an OCI image, run **the exact image intended for deployment** in a realistic test environment. Testing the standalone JAR alone misses broken `ENTRYPOINT` definitions, missing CA certificates, wrong user permissions, and misconfigured container ports.

## 34. Real-World Scenario: Deploying a Store Service as a JVM Image

Suppose a team builds an e-commerce service with Spring MVC, Spring Data JPA, and PostgreSQL. Their initial goal is consistent deployment on a container platform with no extreme cold-start demands.

The workflow naturally starts from an executable JAR:

~~~text
Checkout source
      |
      v
Maven/Gradle build + tests
      |
      v
Spring Boot executable JAR
      |
      v
Dockerfile or Buildpacks
      |
      v
OCI image
      |
      v
Registry
      |
      v
Container orchestrator
      |
      +--> Runtime Environment/Secrets
      +--> Service networking
      +--> Health checks
      +--> CPU/memory limits
      +--> Log collection
      |
      v
Spring Boot process running on JVM
~~~

This path is straightforward, easy to debug, and enjoys broad compatibility across Java libraries.

### Runtime Configuration

~~~yaml
spring:
  application:
    name: store-service

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

The deployment environment supplies:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/store
SPRING_DATASOURCE_USERNAME=store_user
~~~

Passwords come from proper secret management—never embedded in Dockerfiles or hard-coded in source.

### When Should You Try Native Here?

Once you have a baseline JVM image with measured startup and memory metrics, experiment with native on the same use cases. If most startup time goes to database migrations, network handshakes, or warming external connections, native startup savings may prove smaller than expected.

## 35. Real-World Scenario: Scheduled Worker Seeking Lower Cold Start

Suppose a scheduled job runs frequently, processing small batches each invocation, where JVM + Spring Boot startup accounts for most of total execution duration.

One option:

~~~text
Source + tests
      |
      v
Spring AOT
      |
      v
GraalVM Native Image build
      |
      v
Native executable
      |
      v
OCI image containing native binary
      |
      v
Scheduler creates container
      |
      v
Job runs and exits
~~~

Here native deserves consideration because execution is brief and startups are frequent.

Still, account for trade-offs:

- Build times may rise substantially.
- Complex reflection/plugin libraries require extra metadata.
- Multi-architecture runners require multi-platform builds.
- Exit codes must propagate cleanly back to the scheduler.
- Database transactions and idempotency remain mandatory.
- Container startup and cold connection overhead still exist.

Do not migrate to native without automated tests on the real native binary or if measured gains fail to justify maintenance effort.

## 36. Boundary Between Spring Boot Packaging and the Deployment Platform

Spring Boot helps you:

- Package executable JARs/WARs.
- Integrate container image builds via buildpacks.
- Prepare AOT/native builds when paired with matching toolchains.
- Expose runtime configuration, health checks, and lifecycle hooks.
- Run embedded web servers or workers inside the process.

However, Spring Boot **does not replace**:

- Container registries.
- IAM and secret managers.
- Kubernetes/Docker networking.
- TLS ingress/load balancers.
- Durable storage and backups.
- CI/CD release governance.
- Autoscaling strategies.
- Image signing and vulnerability scanning.
- Resource quotas and cluster scheduling.

When an image fails to pull due to registry credentials, that belongs to the deployment/platform layer. When a native binary crashes over missing reflection metadata, that belongs to build/native compatibility. When the app fails creating a `DataSource` from a wrong URL, that belongs to runtime configuration. Knowing these boundaries speeds up incident resolution.

## 37. Common Errors and How to Isolate Them

| Symptom | Possible cause | What to check |
|---|---|---|
| `java -jar` complains about missing main manifest | Plain JAR rather than Boot executable JAR | Build plugin, manifest, and artifact |
| Image build cannot find JAR | JAR not built or wrong `COPY` path | Build output and Docker build context |
| `docker build` succeeds yet app fails to start | Broken `ENTRYPOINT` or runtime config | Run container, inspect logs and exit code |
| Containerized app fails reaching DB at `localhost` | `localhost` refers to the container itself | Container DNS and network setup |
| Container runs yet host cannot connect | Wrong port mapping or bind address | `server.port`, `EXPOSE`, and `-p` |
| Buildpacks cannot reach Docker endpoint | Container daemon unavailable or wrong host socket | Builder runtime daemon configuration |
| `build-image` runs very slowly | Cache misses, dependency downloads, builder or native compile | Build stages and caching setup |
| Image contains two Java runtimes | Redundant tools/layers in Dockerfile/base image | Image layers and runtime stage |
| Native build fails on reflection/resource access | Missing reachability metadata | Runtime hints and library compatibility |
| Native binary runs on build host yet fails in container | OS/`libc`/library/architecture mismatch | Target platform and shared library deps |
| Native build captures CI secrets | Unsuitable static init/build-time config | Separate build-time and runtime properties |
| Native app misses template/resource files | Resource excluded from binary | Register matching resource hints |
| Native app runs with lower throughput | Workload differs from JIT optimization | Benchmark after warmup with real metrics |
| Health check fails immediately at startup | Misconfigured probe timing/thresholds | Separate startup/readiness/liveness probes |
| Container fails graceful shutdown | Signal never reached app or short grace period | `ENTRYPOINT` form and orchestrator timeout |
| Uploaded files disappear on container replacement | Written to ephemeral writable layer | Provision volumes or object storage |
| JVM tests pass while native fails | Native artifact untested | Add native smoke/integration tests |
| Image leaks secrets | Unsafe config `COPY` or build args | Audit image layers and secret flow |

### Layer-by-Layer Diagnostic Flow

~~~text
Source/build
      |
      +--> Is the artifact right?
      |
Package/image
      |
      +--> Are runtime and entrypoint right?
      |
Container/platform
      |
      +--> Are network, filesystem, env, and permissions right?
      |
Spring startup
      |
      +--> Are Environment, profiles, beans, and dependencies right?
      |
Application behavior
      |
      +--> Are business logic, database, latency, and health right?
~~~

Do not tweak Spring configuration when the container lacks a Java runtime. Conversely, do not swap Docker base images to solve a `BeanCreationException` caused by a typo in a property before identifying the actual cause.

## 38. Which Option Should You Choose?

A pragmatic decision guide:

| Context | Sensible starting choice |
|---|---|
| Learning Spring Boot or building small projects | Executable JAR + `java -jar` |
| Standard web service on a container platform | JVM OCI image via buildpacks or Dockerfile |
| Team wants minimal custom Dockerfiles | Spring Boot `build-image` / Cloud Native Buildpacks |
| Need full control over runtime filesystem and OS packages | Multi-stage Dockerfile |
| Short-lived jobs where startup and memory are critical | Trial native executable and measure gains |
| App relies heavily on dynamic native-unfriendly libraries | JVM runtime is usually simpler to operate |
| Need a native process directly on a host | Native executable for target OS/arch |
| Need native binaries managed by container orchestrators | Native executable inside an OCI image |
| CI standardized on JVM images with no real bottleneck | Stay on JVM; avoid premature optimization |

### A Decision Tree

~~~text
Should app be deployed as container?
           |
      +----+----+
      |         |
     No        Yes
      |         |
      v         v
JAR/native    Need detailed Dockerfile control?
 on host        |
            +---+---+
            |       |
           Yes     No
            |       |
            v       v
       Dockerfile  Buildpacks
            |       |
            +---+---+
                |
                v
     Is cold start/memory a real bottleneck?
                |
          +-----+-----+
          |           |
         No          Yes
          |           |
          v           v
      JVM image    Try native build
                      |
                      v
           Compatibility + benchmark
                      |
                      v
          Pick JVM/native by metrics
~~~

This is a guide for thinking, not a rigid rule. An organization may choose Dockerfiles for compliance even when buildpacks are handier, or adopt native to meet a strict product constraint.

## 39. A Predictable Release Pipeline

For a production Spring Boot project, a pipeline might flow like:

~~~text
Source commit
     |
     v
Static checks + unit tests
     |
     v
Build artifact (JAR or native)
     |
     v
Integration tests
     |
     v
Build OCI image
     |
     v
Image scan / SBOM / metadata
     |
     v
Push registry
     |
     v
Deploy staging by image digest
     |
     v
Smoke tests + health + load checks
     |
     v
Promote the exact same artifact to production
     |
     v
Observe / rollback if needed
~~~

If adopting native, include native compatibility/smoke tests in the appropriate stages. If using JVM, verify the Java runtime and tune memory limits to fit the container.

### Limits of "Build Once, Deploy Many"

The same OCI image digest promotes cleanly across environments when platforms, architectures, and runtime configs align. Yet when supporting multiple target architectures or separate native binaries, you must build matching variants and manage manifest/digest lists accordingly.

Avoid saying "build once, run anywhere" once an artifact binds tightly to a specific OS, CPU, or system library set.

## 40. Misconceptions to Avoid

### "Build image means build a Native Image"

False. Spring Boot `build-image` normally builds an **OCI container image**. It can hold a JAR plus a Java runtime. GraalVM Native Image is a separate compilation step requiring its own toolchain and configuration.

### "A container is a native executable"

False. A container is a runtime environment/instance created from an image. Containers can execute JVM processes, native binaries, or other programs.

### "Native executables don't need Docker"

True in the sense that they can run directly on a matching host OS. Yet organizations running Kubernetes or container runtimes still commonly package native binaries inside OCI images.

### "Having a Dockerfile means you don't need a Java runtime"

False when the image runs an executable JAR. In that case, the image must include a compatible Java runtime.

### "Packaging a JAR means the app is deployed"

False. A JAR is just an artifact. You still need a runtime, configuration, secrets, networking, storage, and process supervision.

### "Going native fixes database bottlenecks automatically"

False. Native mode changes compilation and runtime startup; it does not alter transaction semantics, consistency, network round-trips, or credentials.

### "Native builds are always smaller and faster"

Never assume so. Startup and idle memory may improve, yet build duration, binary size, and steady-state throughput depend on the application. Measure first.

### "One native binary runs on every operating system"

False. Native binaries target specific OS/CPU combinations and linking requirements.

### "The container image should bake in all production config"

Bad design. Supply secrets and environment-specific runtime configuration at deploy/run time rather than embedding them inside the image.

### "If the image starts cleanly, it's ready for production"

Insufficient. Verify readiness probes, graceful shutdown, resource limits, security hardening, observability, and data/backup lifecycles.

## 41. Pre-Packaging Checklist for Spring Boot

1. **Identify the target artifact.** Executable JAR, WAR, or native binary?
2. **Identify the runtime.** JVM/JRE or native process?
3. **Decide if a container is needed.** OCI images and containers are simply one deployment layer.
4. **Pick Dockerfile or buildpacks** based on required customization and operational standards.
5. **Verify the artifact inside the image** matches the intended version and startup command.
6. **Verify OS/CPU architecture** and target OS libraries, especially for native binaries.
7. **Keep Java/runtime versions aligned** with build targets.
8. **Keep runtime config and secrets outside the image** using secure mechanisms.
9. **Never misuse `localhost`** when connecting to services in other containers.
10. **Verify published ports** and server bind addresses.
11. **Design readiness/liveness probes** without equating "container running" with "app ready."
12. **Use exec-form `ENTRYPOINT` and test signal forwarding.**
13. **Configure graceful shutdown** aligned with orchestrator grace periods.
14. **Never store durable data in container writable layers.**
15. **Run non-root wherever feasible**, limiting file and network permissions.
16. **Collect logs, metrics, and traces** without leaking secrets into logs.
17. **Scan and patch dependencies and base images**, recording build metadata.
18. **If using native, verify reflection/resources/proxies** and run native integration tests.
19. **Benchmark with realistic workloads**, separating build time from runtime performance.
20. **Deploy traceable artifacts pinned by digest/version**, rather than uncontrolled mutable tags.

## Conclusion

Spring Boot offers multiple packaging and deployment options, yet you must keep the layers distinct: an **executable JAR** is a Java artifact executed by a JVM; an **OCI container image** is a bundle of filesystem layers and launch metadata; a **container** is a running instance of an image; and a **native executable** is a platform-specific binary built via Spring AOT and GraalVM Native Image.

`spring-boot:build-image` and `bootBuildImage` primarily build OCI images using buildpacks—they do not automatically imply native compilation. Dockerfiles offer another way to build OCI images. Both approaches can package either a JVM-hosted JAR or, when configured and built properly, a native binary.

Native executables can cut startup latency and memory usage in certain scenarios at the expense of build time, reachability metadata constraints, and platform coupling. Containers standardize packaging and rollout yet do not replace configuration management, data persistence, security, or observability.

When designing a release architecture, explicitly separate **build artifact → image assembly → container runtime → Spring application lifecycle**, and pick JVM or native based on real measurements and application compatibility. Understanding these boundaries leads to cleaner pipelines, faster layer-accurate troubleshooting, and avoiding premature or misplaced optimizations.
