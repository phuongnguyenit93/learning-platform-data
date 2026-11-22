# Choosing How to Package a Java Application

## Objectives

After this lesson, you can choose an artifact format suited to the product type and deployment environment; distinguish between a library JAR, executable JAR, fat/uber JAR, WAR, EAR, application distribution, container image, runtime image, and native executable; understand Maven packaging and the corresponding Gradle plugins; configure examples for each packaging approach; evaluate dependency, runtime, platform, update, operational, and security considerations; inspect package contents; and design a pipeline that produces the right deliverable for the consumer.

## 1. Where does packaging fit in the build?

Packaging is the step of bundling bytecode, resources, dependencies, metadata, and sometimes the runtime or launcher into a distributable or deployable unit.

~~~text
Source code + resources
          |
          v
       Compile
          |
          v
        Test
          |
          v
   Package / Archive
          |
          +----> Library JAR
          +----> Executable JAR
          +----> WAR / EAR
          +----> ZIP / TAR distribution
          +----> Container image
          +----> Runtime image / installer
          +----> Native executable
~~~

These formats serve different consumers and environments. A library placed on another project's compile classpath has a different contract from a web application deployed to a servlet container or a desktop application installed on Windows/macOS.

Do not choose a format simply because the build tool produces it by default. First determine who will receive the artifact, how they will run it, and what the target environment already provides.

### Distinguishing artifact, archive, and deployment unit

- **Artifact:** an identified and distributed output file, for example a JAR or WAR.
- **Archive:** a container file such as a JAR, ZIP, or TAR with an entry structure.
- **Deployment unit:** a package understood by the deployment platform, for example a WAR on a servlet container, an EAR on a Jakarta EE server, or an OCI image on a container platform.
- **Runtime image:** a directory/package containing a customized Java runtime together with the application.
- **Installer:** an OS-specific installation package, for example MSI, DMG, DEB, or RPM.

A JAR can be a library artifact, an executable application, or a component inside a WAR/EAR. The file extension alone does not fully describe how the application is launched.

## 2. Packaging selection matrix

| Need | Typically suitable packaging | Consumer / environment |
|---|---|---|
| Library used in other Java projects | Library JAR | Maven/Gradle repository, classpath, or module path |
| Small CLI with few dependencies | Executable JAR | User running `java -jar` |
| Standalone application with many dependencies | Application distribution or fat JAR | Server/VM with a Java runtime |
| Self-contained Spring Boot service | Executable Boot JAR | JVM running `java -jar`, container |
| Web app deployed to a servlet container | WAR | Tomcat, Jetty, or a compatible container |
| Enterprise application with multiple modules | EAR | Jakarta EE application server |
| CLI/service needing `bin`, `lib`, config, and script directories | ZIP/TAR distribution | Server or user with Java installed |
| Desktop app needing an installer and dedicated runtime | `jpackage` package | Windows, macOS, Linux |
| Service running on Kubernetes/container platform | OCI container image | Docker/container runtime/orchestrator |
| Application needing a native binary without requiring a JVM installation | GraalVM Native Image | Target OS/architecture built for |

These are common choices, not rigid rules. A Spring Boot application can be released as an executable JAR, a WAR, or a container image. A Java CLI can be released as a ZIP distribution, an installer, or a native executable.

### Decision questions

1. Is the consumer a developer, an application server, an end user, or a container platform?
2. Does the consumer already have a Java runtime?
3. Does the application need to run standalone with a single command?
4. Does it need to be deployed to a servlet container/Jakarta EE server?
5. Do dependencies, the runtime, native libraries, or configuration need to be bundled?
6. Do dependencies need to be updated separately, or is a single file desired?
7. Which OSes and CPU architectures must be supported?
8. Is an installer, service script, container orchestration, or just a library needed?
9. Does it use reflection, JNI, dynamic loading, or frameworks that make native images complex?

Answer these questions before choosing plugins or editing POM/build.gradle.

## 3. Library JAR — the choice for Java libraries

If a module provides classes, interfaces, APIs, or resources for other projects to use, normally create a **library JAR**.

Examples:

~~~text
domain-1.0.0.jar
validation-2.1.0.jar
client-sdk-3.0.0.jar
~~~

A library JAR typically contains:

~~~text
domain-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/acme/domain/
    ├── Customer.class
    └── CustomerService.class
~~~

Dependencies are usually managed separately via POM or Gradle Module Metadata. Consumers declare the library coordinates, and the build tool downloads transitive dependencies according to the metadata.

### Why should you not bundle all dependencies into a library JAR by default?

- Consumers may want to use a different dependency version.
- Bundling dependencies can cause class collisions with other libraries.
- It makes it harder to identify the original dependency when debugging.
- It can strip dependency metadata and license notices.
- Updating a dependency forces re-releasing a large file even when the library API has not changed.

Only shade/relocate dependencies in a library when it is an intentional part of the distribution contract, for example when isolating an implementation dependency to avoid namespace conflicts.

### Maven

Maven defaults to `jar` packaging if the POM does not declare another packaging type. You can state it explicitly:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
~~~

Build:

~~~bash
./mvnw clean package
~~~

The artifact is typically created at:

~~~text
target/domain-1.0.0.jar
~~~

### Gradle

For a Java library, use the Java Library plugin:

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme.platform'
version = '1.0.0'
~~~

Build JAR:

~~~bash
./gradlew clean jar
~~~

The artifact is typically at `build/libs/domain-1.0.0.jar`.

When publishing a library, configure Maven Publish to publish the component together with its POM/metadata. A Sources JAR and Javadoc JAR can also be generated if consumers need IDE navigation or API documentation.

## 4. Executable JAR — running with java -jar

An executable JAR has an entry point specified in its manifest. The Java launcher reads the `Main-Class` field to find the class with the `public static void main(String[] args)` method.

Java 17 program example:

~~~java
package com.example;

public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java application");
    }
}
~~~

Save the file at `src/main/java/com/example/HelloApp.java`.

Compile and create the JAR:

~~~bash
mkdir -p out build
javac -d out src/main/java/com/example/HelloApp.java
jar --create --file build/hello-app.jar \
    --main-class com.example.HelloApp -C out .
~~~

Run:

~~~bash
java -jar build/hello-app.jar
~~~

Exact stdout:

~~~text
Hello from packaged Java application
~~~

The `jar --main-class` command creates the `Main-Class` manifest entry. You can inspect it:

~~~bash
unzip -p build/hello-app.jar META-INF/MANIFEST.MF
~~~

### Executable JARs do not automatically include dependencies

The example above only has the application's own class and needs no external libraries. If the program uses external dependencies, a regular JAR does not automatically embed them.

When running `java -jar`, the Java launcher loads the application's classes from the specified JAR and ignores any external classpath passed with `-cp`/`-classpath`. Therefore, the command:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

is not a way to add dependencies to an executable JAR.

Options to handle this:

- Use the manifest `Class-Path` attribute pointing to sibling dependency JARs.
- Distribute an application distribution with a `lib` directory and a launcher script.
- Create a fat/uber JAR.
- Use a framework that supports nested dependencies, such as a Spring Boot executable JAR.

### When to choose a simple executable JAR?

- Small application.
- Dependencies consist only of the JDK or have a clearly managed classpath.
- Consumer has a compatible Java runtime.
- A simple single launch command is needed.
- No need to integrate with an application server's deployment contract.

## 5. Thin JAR, fat JAR, and uber JAR

| Type | Contents | How it runs |
|---|---|---|
| Thin JAR | Project classes/resources; dependencies are external | Classpath/manifest Class-Path or launcher |
| Fat/Uber JAR | Project classes/resources and dependencies merged into one archive | Usually `java -jar` if it has a suitable launcher manifest |
| Nested executable JAR | Dependency JARs placed inside the archive in a format understood by a loader | Uses the framework's launcher, e.g. Spring Boot |

### Thin JAR

Pros:

- Keeps dependencies separate.
- Allows swapping dependencies without rebuilding the application archive if the contract permits.
- Easy to inspect dependencies and metadata.
- Avoids merging duplicate classes/resources.

Cons:

- All dependencies must be distributed.
- Consumer needs the right launcher/classpath.
- Requires managing versions and the lib directory.

### Fat/Uber JAR

Pros:

- A single primary file to copy/deploy.
- Easy to launch with `java -jar`.
- Fewer classpath setup steps for the consumer.

Cons:

- Merged dependencies can have class or resource conflicts.
- Difficult to update a single dependency independently.
- Larger archive that may contain a lot of unused code.
- Dependency signatures are no longer meaningful after contents are repackaged; licenses, notices, and provenance must be managed properly.

If multiple dependencies share the same package/class, consider relocation (renaming the package namespace) or choosing compatible dependency versions.

### Duplicate resources and ServiceLoader

When merging JARs, you cannot simply overwrite every file at the same path:

- `META-INF/services/*` may contain multiple provider declarations; they must be merged properly.
- The manifest must be regenerated for the final artifact.
- License/NOTICE resources must be preserved according to policy.
- Old signature files such as `.SF`, `.RSA`, and `.DSA` are no longer valid after the archive is modified.
- Configuration files may require resource transformers or custom merge rules.

Test features that use ServiceLoader, logging providers, JDBC drivers, framework auto-configuration, and resource lookups after building an uber JAR.

### Maven Shade Plugin

The Maven Shade Plugin builds an uber JAR and supports package relocation. Example configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.Main</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Build:

~~~bash
./mvnw clean package
~~~

Inspect the generated JAR in `target/`, its manifest, service descriptors, and runtime behavior. For projects with many duplicate resources, configure transformers appropriate for each resource type.

### Gradle

The Gradle Java plugin creates a regular JAR and does not automatically merge all dependencies into a fat JAR. You can use a dedicated plugin or configure an archive task depending on your requirements. Before choosing a plugin, determine how resource merging, service descriptors, signatures, and package relocation will be handled.

## 6. Spring Boot executable JAR and WAR

Spring Boot supports executable archives containing application classes and dependencies so they can be run with `java -jar`.

### Executable Boot JAR

A Boot JAR typically has this structure:

~~~text
application.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    └── lib/
        ├── dependency-a.jar
        └── dependency-b.jar
~~~

Dependencies remain separate JARs inside the archive. The Spring Boot loader knows how to load them when running the application.

This is not the same as merging all classes into a single namespace like a shaded JAR.

Run:

~~~bash
java -jar application.jar
~~~

### Maven

The Spring Boot Maven Plugin uses the `repackage` goal to create an executable archive from the packaged JAR/WAR:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

If the project uses the Spring Boot parent, the execution may already be configured. Run the `package` lifecycle to produce the source archive and the executable archive.

### Gradle

The Spring Boot Gradle Plugin creates the `bootJar` task when configured alongside the Java plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
}

tasks.bootJar {
    archiveFileName = 'application.jar'
}
~~~

The plugin version is just an example; choose a version compatible with your project's Spring Boot line and Gradle wrapper.

Build:

~~~bash
./gradlew clean bootJar
~~~

`bootJar` produces the executable archive; the `jar` task may produce a separate plain JAR. If both exist, check the classifier and file name to avoid publishing the wrong artifact.

### When to choose a Boot JAR?

- The service is deployed as a standalone JVM process.
- The runtime platform supports running a Java command or container.
- You want to bundle an embedded server and dependencies.
- There is no need to deploy a WAR to an external servlet container.

If the deployment platform standardizes on WARs or requires an organization-managed servlet container, consider an executable/deployable WAR.

## 7. WAR — Web Application Archive

WAR is the deployment format for Java web applications, typically for Servlet-based applications.

Common structure:

~~~text
web-app.war
├── index.html
├── assets/
└── WEB-INF/
    ├── classes/
    ├── lib/
    │   ├── application-library.jar
    │   └── another-library.jar
    └── web.xml
~~~

A WAR contains web resources such as HTML/CSS/JavaScript, production classes in `WEB-INF/classes`, runtime dependencies in `WEB-INF/lib`, and platform-appropriate deployment descriptors/metadata.

The servlet container reads the WAR and deploys the web application. Depending on the Jakarta Servlet/Jakarta EE version, the container provides the required APIs and runtime.

### When to choose a WAR?

- The web application runs on a servlet container managed by the target environment.
- The organization needs to deploy multiple web applications onto the same container.
- Runtime lifecycle, thread pools, connectors, TLS, or monitoring are managed by the container.
- The application server's deployment conventions must be used.

Do not choose a WAR just because the application has HTTP endpoints. A Spring Boot service can use an executable JAR and an embedded server without needing a WAR.

### Container-provided dependencies

Do not package the servlet API or libraries that the container requires the application server to provide by policy. In Maven, such dependencies typically have `provided` scope; with the Gradle War plugin, use the appropriate provided configuration.

Mistakenly packaging container/API libraries can cause classloader conflicts, `ClassCastException`, `NoSuchMethodError`, or servlet initialization failures.

### Maven WAR

POM:

~~~xml
<packaging>war</packaging>
~~~

The Maven WAR Plugin collects web application dependencies, classes, and resources during the `package` phase.

Build:

~~~bash
./mvnw clean package
~~~

The artifact is typically located at `target/<artifactId>-<version>.war`.

### Gradle WAR

~~~groovy
plugins {
    id 'war'
}
~~~

The War plugin collects static resources from `src/main/webapp`, production classes into `WEB-INF/classes`, and runtime dependencies into `WEB-INF/lib`.

Build:

~~~bash
./gradlew clean war
~~~

The artifact is typically in `build/libs/`.

### Spring Boot WAR

Spring Boot can produce a WAR that can both be deployed to an external servlet container and run with `java -jar`. For traditional deployment, configure the embedded servlet container as provided/providedRuntime and integrate the application with a servlet initializer according to the Spring Boot guide.

Inspect `WEB-INF/lib` and `WEB-INF/lib-provided` to verify that container dependencies are not packaged incorrectly.

## 8. EAR — Enterprise Archive

EAR is an enterprise application package for Jakarta EE application servers. It can bundle multiple components such as:

- Web modules (WAR).
- Enterprise bean modules (EJB JAR).
- Java library modules.
- Resource adapters (RAR).
- Application deployment descriptors and metadata.

Example structure:

~~~text
enterprise-app.ear
├── META-INF/
│   └── application.xml
├── web-portal.war
├── business-ejb.jar
└── lib/
    └── shared-library.jar
~~~

An EAR allows deploying a set of enterprise modules as a single application unit. The application server manages module lifecycle, classloaders, transactions, security, and platform enterprise services.

### When to choose an EAR?

- The organization uses a Jakarta EE application server that supports EAR.
- The application has multiple enterprise modules that must be deployed together.
- Web modules, EJB modules, and shared libraries need to be separated according to a deployment contract.
- Application configuration needs to be managed at the enterprise level.

Do not choose an EAR for a standalone Spring Boot microservice or a simple web app if there is no application server requirement.

### Maven EAR

POM of the EAR project:

~~~xml
<packaging>ear</packaging>
~~~

The Maven EAR Plugin bundles the declared modules and can generate deployment descriptors such as `application.xml`.

Build:

~~~bash
./mvnw clean package
~~~

### Gradle EAR

~~~groovy
plugins {
    id 'ear'
}
~~~

The Gradle Ear plugin provides the `ear` task to assemble the enterprise archive. Deployable modules can be declared in the `deploy` configuration; shared libraries can be placed in `earlib`.

Build:

~~~bash
./gradlew clean ear
~~~

An EAR must be tested on the exact target Jakarta EE/application server version. A successfully packaged EAR does not prove that descriptors, module versions, or server-specific deployment configurations are compatible.

## 9. Application distribution — ZIP/TAR with bin and lib

If you need to distribute an application with many dependencies, configs, scripts, and documentation, an **application distribution** is often easier to operate than merging everything into a single JAR.

Example:

~~~text
my-app-1.0.0/
├── bin/
│   ├── my-app
│   └── my-app.bat
├── lib/
│   ├── my-app.jar
│   ├── dependency-a.jar
│   └── dependency-b.jar
├── conf/
│   └── application.properties
├── README.txt
└── LICENSE
~~~

Pros:

- Keeps dependencies separate, easy to inspect and replace.
- Includes launcher scripts for Linux/macOS and Windows.
- Can include sample configs, licenses, documentation, and migration notes.
- No need to modify classes/resources to merge dependencies.
- Easy to ship with a dedicated Java runtime if needed.

Cons:

- Multiple files must be kept in sync.
- Requires a proper launcher and classpath.
- If the runtime is not bundled, the target machine must have a suitable Java installation.

### Gradle Application plugin

The Application plugin supports JVM applications and requires declaring the main class:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.Main'
}
~~~

Main tasks:

~~~bash
./gradlew run
./gradlew installDist
./gradlew distZip
./gradlew distTar
./gradlew assembleDist
~~~

- `run`: runs the application in the build environment.
- `installDist`: creates an installation directory with launchers and runtime dependencies.
- `distZip`: creates a ZIP distribution.
- `distTar`: creates a TAR distribution.
- `assembleDist`: assembles the configured distribution formats.

Gradle generates Unix and Windows scripts in the `bin` directory; runtime dependencies are placed in `lib`.

### Maven Assembly Plugin

The Maven Assembly Plugin can bundle project outputs, dependencies, modules, documentation, and custom files into a ZIP/TAR distribution.

You can use a built-in assembly descriptor or a custom descriptor to decide which files are included in the package, which dependencies are copied, the directory structure, accompanying scripts/configs, and the ZIP/TAR format.

The Assembly Plugin is well suited for multi-file distributions. If the goal is an uber JAR that needs class/resource merging and manifest handling, use the Shade Plugin or a tool suited to that requirement.

## 10. Runtime image and installer with jlink/jpackage

If you want users to run the application without installing Java themselves, you can package the runtime together with the application.

Two JDK tools serve different roles:

| Tool | Output | Purpose |
|---|---|---|
| `jlink` | Custom runtime image | Creates a Java runtime containing only the required modules |
| `jpackage` | Application image or native installer | Packages the app and runtime into an OS-specific deliverable |

### jlink

`jlink` assembles Java modules and their transitive dependencies into a custom runtime image.

Example with a modular application:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/mods" \
  --add-modules com.example.app \
  --output build/runtime
~~~

List modules in the runtime:

~~~bash
build/runtime/bin/java --list-modules
~~~

The runtime image contains only the linked modules and their dependencies. This can reduce size compared to shipping the full JDK.

Notes:

- `jlink` works with the module path and observable modules.
- The application must have a valid module graph.
- If using service providers, consider `--bind-services`.
- The team is responsible for updating the custom runtime image when Java patches are released.
- A runtime image does not by itself create a full installer or desktop launcher.

### jpackage

`jpackage` packages an application into an application image or OS-native package.

Example creating an application image:

~~~bash
jpackage \
  --type app-image \
  --name HelloApp \
  --input build/input \
  --main-jar hello-app.jar \
  --main-class com.example.Main \
  --dest build/packages
~~~

The `build/input` directory must contain the main JAR and required dependencies. If no custom runtime image is passed, `jpackage` can use `jlink` to create a runtime for the application.

Package types can include:

- Windows: EXE, MSI.
- macOS: PKG, DMG.
- Linux: DEB, RPM.

Each native format must be built on its corresponding platform; `jpackage` does not provide cross-platform packaging for all OSes from a single host.

### When to choose jlink/jpackage?

- Desktop applications needing a native installer and launcher.
- CLIs/applications distributed to end users who should not be required to install a JDK.
- When you want control over the Java runtime shipped with the application.
- When separate build and test pipelines exist for each OS/architecture.

If the deployment target is a container platform, an OCI image may be more suitable than a desktop installer. If users already manage Java runtimes centrally, a ZIP distribution may be simpler.

## 11. Container image — packaging for container platforms

A container image is a deployment unit containing the application, runtime/base filesystem, and metadata for the container runtime to start the process.

A Java service can be packaged by:

1. Building a JAR or application distribution.
2. Choosing a runtime base image.
3. Copying the artifact and required files into the image.
4. Declaring the user, working directory, environment, and entrypoint.
5. Building the image and publishing it to a container registry.

Minimal Dockerfile example using a built distribution:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/install/my-app/ ./

ENTRYPOINT ["bin/my-app"]
~~~

This is an illustrative example. In production, pin the base image by an approved version/digest, configure a non-privileged user, add appropriate health checks, and restrict permissions/secrets per environment.

### Multi-stage build

A multi-stage build separates the compile environment from the final runtime image:

~~~dockerfile
FROM gradle:9.0-jdk21 AS build
WORKDIR /workspace
COPY . .
RUN gradle --no-daemon clean installDist

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/build/install/my-app/ ./
ENTRYPOINT ["bin/my-app"]
~~~

Image versions in examples should be pinned according to project policy. The final stage receives only the distribution needed to run; there is no need to carry over the Gradle cache, source tree, and JDK compiler if the runtime does not need them.

### When to choose a container image?

- The deployment platform uses Docker/Kubernetes or an OCI-compatible runtime.
- The team wants to package the runtime and app as a single unit.
- Deployments/rollbacks by image digest are needed.
- Registry, orchestration, logging, networking, and secret management exist at the platform level.

A container image does not replace the JAR artifact. Usually the JAR remains the build output, while the image is the deployment package built from that JAR/distribution.

## 12. Native executable with GraalVM Native Image

GraalVM Native Image compiles Java bytecode ahead-of-time into a native executable for a specific OS/architecture.

Advantages can include fast startup, no separate JVM needed to run the executable, and potentially a smaller footprint for suitable workloads.

In return, Native Image has a different build model from the traditional JVM. It statically analyzes reachable code paths at build time; reflection, JNI, resource loading, serialization, or dynamic proxies may require reachability metadata.

Basic example:

~~~bash
native-image -jar application.jar
~~~

The command above assumes Native Image is installed in the environment and the JAR has an appropriate entry point configured. For real applications, configure dependencies and metadata properly according to the framework.

### When should you consider a native image?

- Startup latency and memory footprint are critical requirements.
- Short-lived or scale-to-zero workloads.
- Frameworks and dependencies support Native Image.
- You can maintain a separate native build pipeline, metadata, and tests.

### When should you not rush into it?

- The application relies on complex reflection/dynamic class loading.
- Some libraries do not yet support Native Image.
- Native builds take too long or require dedicated toolchains/platforms.
- You need the same artifact to run across multiple OSes/architectures without building separately.

A native executable is not simply a smaller JAR. It is a different deliverable with its own compatibility, debugging, and build requirements.

## 13. Maven packaging and Gradle plugin mapping

### Maven packaging

The Maven packaging type determines which lifecycle goals are bound to phases. Common values:

| Packaging | Primary output | Plugin/lifecycle |
|---|---|---|
| `jar` | Java library/application JAR | Maven JAR Plugin |
| `war` | Web application archive | Maven WAR Plugin |
| `ear` | Enterprise application archive | Maven EAR Plugin |
| `pom` | POM metadata/parent/aggregator | Does not produce a runtime JAR |

If packaging is not declared, Maven defaults to `jar`.

Some plugins can add other package types or deliverables. For example, Shade creates an uber JAR, Assembly creates a ZIP/TAR distribution, and Spring Boot `repackage` creates an executable archive. Do not confuse a plugin goal with Maven's core packaging type.

### Gradle plugin mapping

| Gradle plugin | Deliverable/task |
|---|---|
| `java` | JAR, `jar` |
| `java-library` | Library JAR and API/implementation model |
| `application` | JVM application distribution, `installDist`, `distZip`, `distTar` |
| `war` | WAR archive, `war` |
| `ear` | EAR archive, `ear` |
| `distribution` | Custom ZIP/TAR distribution |
| `maven-publish` | Publish artifacts/metadata to a Maven repository |
| Spring Boot plugin | `bootJar`, `bootWar` |

The Gradle plugin determines how the archive is built; Maven Publish or a repository publisher determines how it is published. Creating a file in the build directory and publishing it to a repository are two separate actions.

## 14. Choosing by product type

### Java library

Choose a library JAR and publish POM/Gradle metadata. Add sources/Javadoc if needed. Avoid bundling dependencies if consumers should manage dependencies separately.

### CLI tool

If it only uses the JDK, an executable JAR may suffice. If it has many dependencies, choose a ZIP/TAR distribution with a launcher script, or a fat JAR if a single file is desired.

If the tool is for end users and needs a dedicated runtime, consider jpackage or a native executable.

### Backend service

If using Spring Boot and running on a JVM/container platform, an executable Boot JAR is the simplest choice. If the organization requires an external servlet container, choose a WAR. If the deployment platform standardizes on containers, build an OCI image from the verified artifact.

### Traditional Java web application

Choose a WAR when the target runtime is a servlet container. Choose an EAR when the application server must manage multiple enterprise modules in a single application unit.

### Desktop application

Choose a distribution or jpackage to generate an OS-specific launcher, runtime, and installer. If a native startup/resource profile is required, evaluate Native Image.

### Enterprise platform

Choose an EAR when you have matching modules and server contracts. Do not create an EAR just to bundle multiple JARs if the deployment runtime does not understand EAR.

## 15. Factors to check before finalizing

### Runtime compatibility

- Minimum Java version of the consumer.
- JDK/JRE or bundled runtime image.
- Class file version and module path.
- Servlet/Jakarta EE version if using WAR/EAR.
- OS, CPU architecture, and native libraries.

### Dependency model

- Are dependencies external, inside the archive, or nested?
- Who is responsible for updating dependencies?
- Are there duplicate classes/resources?
- Is there ServiceLoader, reflection, or framework scanning?
- Are licenses/NOTICE files preserved when merging dependencies?

### Operations

- Launched via `java -jar`, script, service manager, or container entrypoint?
- Is config placed inside the archive or mounted externally?
- Are logs written to stdout/stderr or files?
- How are stop/graceful shutdown and health checks handled?
- Is a native installer or service registration required?

### Release and security

- Does the artifact have clear coordinates/version?
- Are there checksums, signatures, and provenance?
- Is the runtime/base image patched periodically?
- Is the release archive reproducible or at least equipped with an input manifest?
- Are SBOM and license notices included when distributing dependencies?

## 16. Inspecting the package after building

Do not just check the build exit code. Open the archive and verify the actual deliverable.

### Check names and sizes

Linux/macOS:

~~~bash
ls -lh target/*.jar target/*.war target/*.ear
~~~

Gradle:

~~~bash
ls -lh build/libs/
~~~

PowerShell:

~~~powershell
Get-ChildItem target -File
Get-ChildItem build\libs -File
~~~

### List JAR/WAR/EAR contents

~~~bash
jar --list --file application.jar
jar --list --file application.war
jar --list --file enterprise-app.ear
~~~

Or verify the ZIP archive:

~~~bash
unzip -t application.jar
unzip -t application.war
unzip -t enterprise-app.ear
~~~

Confirm that required classes/resources are present; manifest and Main-Class/launcher metadata are correct; dependencies are placed in the right location; WAR has the appropriate `WEB-INF/classes` and `WEB-INF/lib`; EAR has the required modules and deployment descriptors; distribution has launchers, sample configs, and licenses; container image has the right entrypoint, runtime, and user; runtime image runs on the target platform.

### Verify from the consumer's environment

For JAR:

~~~bash
java -jar application.jar
~~~

For distribution:

~~~bash
./bin/my-app
~~~

For WAR/EAR, deploy to the exact target container/server version and run smoke tests. For containers, run the image in a production-equivalent environment. For jpackage/native images, test on every supported OS/architecture.

## 17. Common issues and how to fix them

### JAR runs on the developer's machine but fails on another machine

**Cause:** the developer's machine has dependencies in CLASSPATH, the local repository, or a lib directory that was not distributed.

**Fix:** inspect package contents; use a clean environment; choose a distribution/fat JAR or configure the manifest classpath properly.

### java -jar reports Main-Class not found

**Cause:** the manifest is missing Main-Class, has the wrong class name, or a plain JAR was built by mistake.

**Fix:** inspect META-INF/MANIFEST.MF; configure the entry point in Maven/Gradle or use jar --main-class; rebuild and run a smoke test.

### java -jar cannot find dependencies

**Cause:** the JAR is a thin JAR, but dependencies are not in the manifest Class-Path or an external launcher.

**Fix:** ship a distribution with lib/launcher, configure manifest Class-Path, or use a suitable fat/nested executable JAR.

### Fat JAR breaks ServiceLoader or framework auto-configuration

**Cause:** resources in META-INF/services or framework metadata were overwritten during merging.

**Fix:** configure resource transformers/merge strategies; inspect service descriptors in the final archive; run integration tests against the packaged JAR.

### Fat JAR hits duplicate class or NoSuchMethodError

**Cause:** two dependencies contain duplicate classes or incompatible versions.

**Fix:** inspect the dependency tree; align on a single version; exclude unneeded dependencies; use controlled relocation if namespace isolation is required.

### WAR deployment fails due to servlet API or classloader issues

**Cause:** libraries already provided by the container were packaged, or an API version incompatible with the server was used.

**Fix:** move container dependencies to provided/providedRuntime; verify the Servlet/Jakarta EE version; inspect WEB-INF/lib.

### WAR runs locally but fails to deploy to the server

**Cause:** the app relies on an embedded container, descriptor, or framework-specific API incompatible with the server.

**Fix:** verify the deployment target; configure WAR mode properly; run integration tests on the same container type/version.

### EAR deploys but modules are not recognized

**Cause:** modules are not declared properly, descriptors are wrong, or the server does not support the spec/version required by the package.

**Fix:** check application.xml, EAR structure, module URIs, and the Jakarta EE/application server version.

### Distribution is missing config files or launchers

**Cause:** the assembly descriptor/CopySpec did not include the files, or the task generating them was not declared as an input.

**Fix:** inspect the archive listing; declare files/task outputs explicitly; run assembleDist/package and test from the extracted directory.

### jpackage fails to create an installer

**Cause:** built on the wrong OS, missing native tools, incompatible runtime image, or unsupported package format.

**Fix:** build on the target OS; check jpackage --help, toolchain, and signing/notarization permissions; build an app-image first to separate packaging errors from app errors.

### jlink reports module not found

**Cause:** the module path is missing a module, or the application does not have a valid module descriptor yet.

**Fix:** check module-info.class, module path, and module name; run java --list-modules; add missing modules/dependencies.

### Native Image is missing reflection/resources

**Cause:** static analysis could not detect dynamic access at runtime.

**Fix:** add appropriate reachability metadata, use the tracing agent when needed, and test the native executable with real execution paths.

### Container image is too large

**Cause:** the final image contains the JDK/compiler, build cache, source tree, or files not needed at runtime.

**Fix:** use a multi-stage build; copy only the distribution needed to run; choose an appropriate runtime base image; inspect layers and dependencies.

### Packaging changed, but consumers still resolve the old artifact

**Cause:** the artifact name, classifier, version, or publication mapping did not change as expected.

**Fix:** check output filenames and publication metadata; verify coordinates in the repository; use a new version or separate classifier per release policy.

## 18. Process for choosing and verifying packaging

1. Identify the consumer and deployment target.
2. Determine whether the Java runtime is pre-installed or must be bundled.
3. Determine the application/library and API/dependency contract.
4. Choose JAR, WAR, EAR, distribution, container, runtime image, or native executable.
5. Choose the appropriate Maven packaging/plugin or Gradle plugin.
6. Configure dependencies, manifest, resource merging, and launcher.
7. Build the package cleanly.
8. Inspect archive contents and metadata.
9. Run the artifact in a production-like environment.
10. Verify checksums/signatures/provenance according to release policy.
11. Publish the right deliverable and document how to install/run it.

There is no need to produce every format at once. Multiple deliverables can be released when there are multiple consumer groups, but each deliverable must have a clear purpose, version, tests, and release record.

## 19. Pre-release checklist

### Choosing the right format

- [ ] Consumer and deployment platform identified.
- [ ] Library JAR distinguished from application package.
- [ ] Confirmed whether the Java runtime is pre-installed or bundled.
- [ ] WAR/EAR chosen only when the target server supports the right specification.
- [ ] Container/native/installer matches the OS and architecture.

### Package contents

- [ ] Classes, resources, and manifest are correct.
- [ ] Main-Class or launcher script is correct.
- [ ] Dependencies are complete and free of duplicates/conflicts.
- [ ] ServiceLoader/resource metadata is merged properly.
- [ ] Configs, licenses, NOTICE, and required documentation are present.
- [ ] No secrets, local configs, or build caches are packaged.

### Runtime and operations

- [ ] Runs from the extracted/downloaded package.
- [ ] Runtime version is compatible.
- [ ] Config externalization and logging are correct.
- [ ] Smoke/integration tests exist on the target environment.
- [ ] Native/installer tested on every supported platform.

### Release

- [ ] Artifact identity/version is clear.
- [ ] Checksums/signatures/provenance generated per policy.
- [ ] SBOM/license review performed if needed.
- [ ] Target repository/registry is correct.
- [ ] Installation, running, upgrade, and rollback instructions are documented.

## 20. Official references

- [Maven Build Lifecycle — Packaging](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — packaging types jar, war, ear, pom and lifecycle goal binding.
- [Maven Shade Plugin](https://maven.apache.org/components/plugins/maven-shade-plugin/) — building uber JARs, relocating dependencies, and transformers.
- [Maven Shade Plugin: Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html) — configuring Main-Class and executable uber JARs.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/) — packaging web application archives.
- [Maven EAR Plugin](https://maven.apache.org/plugins/maven-ear-plugin/) — bundling enterprise modules into an EAR.
- [Maven Assembly Plugin](https://maven.apache.org/plugins/maven-assembly-plugin/) — creating ZIP/TAR distributions with dependencies and custom files.
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — main class, start scripts, installDist, distZip, distTar.
- [Gradle WAR Plugin Reference](https://docs.gradle.org/current/userguide/war_plugin.html) — WAR layout and dependency placement.
- [Gradle EAR Plugin](https://docs.gradle.org/current/userguide/ear_plugin.html) — EAR modules, shared libraries, and deployment descriptors.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — library component and API/implementation separation.
- [Spring Boot Executable Archives — Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html) — bootJar, bootWar, nested dependencies, and layered archives.
- [Spring Boot Executable Archives — Maven](https://docs.spring.io/spring-boot/maven-plugin/packaging.html) — repackage, executable JAR/WAR, and archive layout.
- [Java Launcher — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — java -jar, Main-Class, and classpath behavior.
- [jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — creating custom runtime images from a module graph.
- [jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — application images and platform-specific native installers.
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/) — compiling Java into native executables.
- [GraalVM Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/) — reflection, JNI, resources, and metadata for Native Image.
- [Docker Multi-stage Builds](https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/) — separating the build stage from the runtime image.

Choosing how to package starts with the consumer and the runtime environment. Libraries usually need a JAR with dependency metadata; standalone applications can use an executable JAR or ZIP/TAR distribution; web applications use a WAR when deployed on a servlet container; enterprise applications use an EAR when required by an application server; desktop apps can use jpackage; container platforms use an OCI image; Native Image is for cases that need a native executable and accept its specific compatibility requirements. Test the final package itself in the environment where the consumer will use it.
