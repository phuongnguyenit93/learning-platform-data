# Choosing Plain JAR, Executable JAR, WAR, or OCI Image in Spring Boot

## 1. Choose Based on How the Application Is Consumed and Deployed

In Spring Boot, "packaging" raises two distinct questions: **what is inside the artifact** (classes, resources, libraries, launcher) and **which environment will run that artifact** (Java classpath, standalone JVM, external servlet container, or container runtime). A `.jar` or `.war` extension alone does not prove an artifact is self-runnable. Nor is an OCI image simply another type of JAR: an image typically **contains** the packaged Java application together with a Java runtime and required operating system components.

Four options to distinguish:

1. **Plain/regular JAR:** mainly contains a module's classes and resources; dependencies usually must be supplied separately. Suitable when a module is **consumed by other modules as a library** or when the host system explicitly manages the classpath.
2. **Executable JAR (Spring Boot executable JAR):** contains classes/resources, nested dependencies, and the Spring Boot launcher; ideal for running standalone services via `java -jar` on a JVM.
3. **WAR:** supports the model of **deploying a web application to a servlet container** such as an external Tomcat. A WAR produced by Spring Boot plugins can simultaneously be an **executable WAR** runnable via `java -jar` if properly configured.
4. **OCI image:** a standard container image deployment unit; suited for Docker, Kubernetes, and container platforms. Can be built from an executable JAR/WAR via Cloud Native Buildpacks or a Dockerfile.

| Criterion | Plain JAR | Spring Boot Executable JAR | Deployable WAR | OCI Image |
| --- | --- | --- | --- | --- |
| Primary purpose | Distribute libraries/classes | Run standalone application | Run web app inside a servlet container | Distribute and run app as a container |
| Bundled dependencies? | Usually not | Yes, typically in `BOOT-INF/lib` | Yes in `WEB-INF/lib`; provided container dependencies are separated when Boot repackages | Includes runtime/dependency/app layers per image build |
| Common way to run | Consumed as dependency by another module or custom classpath | `java -jar app.jar` | Deploy to compatible Tomcat; executable WAR can also run `java -jar app.war` | `docker run ... image:tag` or Kubernetes |
| Target environment needs | JVM, dependencies, and startup mechanism | Compatible JVM | Compatible servlet container/JVM; or JVM if executable WAR | Container runtime / OCI platform; Java runtime is usually inside the image |
| When to choose | Shared libraries, SDKs, reusable modules | Standalone services, VMs, JAR-based runners | Infrastructure mandating WAR management on an app server | CI/CD pipelines, orchestration, container platforms |
| Common misconception | Having `.jar` does not mean `java -jar` works | Should not be used as a regular library | WAR is not automatically appropriate for every Spring app | An image can contain a JAR/WAR; the two concepts are not mutually exclusive |

## 2. What Is Inside Each Package?

### 2.1. Plain JAR

A JAR is a standard Java-structured ZIP archive, typically containing `.class` files, resources, and a `META-INF/` directory. Example:

```text
com/example/library/Formatter.class
application.properties
META-INF/MANIFEST.MF
```

A plain JAR **does not bundle all dependencies**. When used as a library, Maven/Gradle resolves its dependencies from metadata when another project declares it. To run it directly, you need a `main` class, an appropriate manifest/classpath, and every runtime dependency. Do not treat having a `main` method as enough to guarantee `java -jar` will work.

**Choose a plain JAR when** building domain, utility, SDK, or API modules shared across applications. If you consume an executable Boot JAR as a dependency, application classes sit under `BOOT-INF/classes`, so standard classpath consumers cannot find them via regular JAR layout. For library modules, keep the plain JAR as the main artifact; if you also need to run the app, produce an additional executable JAR with a distinct classifier.

### 2.2. Spring Boot Executable JAR

Spring Boot Maven `repackage` or Gradle `bootJar` transforms an application artifact into an executable package. Typical layout:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/<dependency-1>.jar
BOOT-INF/lib/<dependency-2>.jar
```

Spring Boot's launcher sets up the classpath for libraries nested in `BOOT-INF/lib` and invokes the application class. The manifest is managed by the plugin: `Main-Class` typically points to the launcher, while `Start-Class` points to the application class. Do not manually edit `Main-Class` in the Maven JAR plugin hoping it replaces the `repackage` mechanism.

For Spring MVC apps using an embedded servlet server, an executable JAR usually starts the HTTP server in the same JVM process; you can run `java -jar app.jar --server.port=9090`. This is a sensible default for a Spring Boot service running directly on a server or VM.

**Limitations:** the target image/JVM still needs a compatible Java runtime; a JAR also does not supply environment config, secrets, databases, or logging/monitoring systems on its own.

### 2.3. WAR and Executable WAR

WAR is the packaging format for servlet-based web applications. Typical layout:

```text
WEB-INF/classes/com/example/packaging/PackagingApplication.class
WEB-INF/lib/<application-dependency>.jar
WEB-INF/lib-provided/<embedded-container-dependency>.jar
META-INF/MANIFEST.MF
```

`WEB-INF/lib-provided` is characteristic of a **Spring Boot repackaged executable WAR** when servlet container dependencies are marked `provided`. An external servlet container supplies container libraries when deploying the WAR; Spring Boot's launcher can still use `lib-provided` libraries when running via `java -jar`. A regular WAR created by standard Java tooling is not necessarily an executable WAR.

To deploy a Spring Boot MVC app to an external servlet container, the application usually needs:
- `war` packaging, `SpringBootServletInitializer`, and an overridden `configure` method;
- the embedded servlet container marked `provided` / `providedRuntime`;
- verification that the container supports the exact Jakarta Servlet, Java, and Spring Boot versions in use;
- checking the WAR's context path on the application server.

Traditional WAR packaging **is not an option for Spring WebFlux applications using Reactor Netty** under the default model. Choose WAR only if the deployment platform truly requires an external servlet container or has specific infrastructure/integration constraints.

### 2.4. OCI Image

An OCI image is a set of layers and a manifest following the container image standard. A Spring Boot application image typically contains a Java runtime, minimal Linux components, and application code/dependencies. At runtime, the container runtime creates a container from the image; the application is still typically a JVM process running code from the executable JAR/WAR.

Two common paths exist:
- **Cloud Native Buildpacks:** `mvn spring-boot:build-image` or `gradle bootBuildImage`; no manual Dockerfile needed, selects builder/runtime images and structures layers.
- **Dockerfile:** explicit control over base image, JAR copying, entrypoint, user, and filesystem.

OCI images are convenient for registries, digest-based deployments, Kubernetes, and environment consistency. However, images must be updated when Java/base images receive patches; you must manage CPU architectures, registries, permissions, vulnerability scanning, and container resource limits. OCI **does not replace** deciding whether a module should be a plain JAR or an executable app.

## 3. Runnable Example with Spring Boot and Java 17

The example below **pins Spring Boot 3.5.0** so dependencies and commands remain consistent. This is an illustrative version, not a claim that it is the latest. Spring Boot 4.x changes some starter/runtime artifacts; when upgrading, cross-check documentation for that release line. You need JDK 17+, Maven, and network access to download dependencies. Create the following two Java files.

**`src/main/java/com/example/packaging/PackagingApplication.java`:**

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
```

**`src/main/java/com/example/packaging/HelloController.java`:**

```java
package com.example.packaging;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

**Minimal `pom.xml` to build an executable JAR:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Because the project inherits from `spring-boot-starter-parent` and declares the Boot Maven plugin, the `repackage` goal is configured in the lifecycle. Run in the directory containing `pom.xml`:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Open another terminal to test:

```bash
curl -fsS http://localhost:8080/hello
```

**Exact response body:** `Hello from Spring Boot` (curl may not print a trailing newline). The server uses port 8080 unless overridden or already bound. Stop the process with Ctrl+C. If using the Maven Wrapper, replace `mvn` with `./mvnw` (Windows: `mvnw.cmd`).

You can inspect the archive layout with `jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar`; this command lists JAR entries without starting the application.

## 4. Building Each Format with Maven

### 4.1. When You Want a Plain JAR

With the example above, you can temporarily skip Spring Boot repackaging for a build:

```bash
mvn clean package -Dspring-boot.repackage.skip=true
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
```

The resulting JAR is a standard Java artifact without nested runtime dependencies or the Boot launcher. Do not run it with `java -jar` like the service deployment in section 3; a plain JAR is suited for publishing as a library or feeding into a workflow with an external classpath. In a dedicated library project, you typically do not declare the Spring Boot Maven plugin at all.

**If you need both a plain JAR and an executable JAR:** keep the `pom.xml` from section 3, but configure the `exec` classifier on the `repackage` execution:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

This `<build>` snippet **replaces** the `<build>` block in the sample POM—do not paste it as a second block. After `mvn clean package`, Maven creates the plain `target/packaging-demo-0.0.1-SNAPSHOT.jar` and the runnable `target/packaging-demo-0.0.1-SNAPSHOT-exec.jar`. In projects with a different parent, ensure the `repackage` goal is actually bound to the `package` phase.

### 4.2. When You Want an Executable JAR

Use the POM from section 3 and run `mvn clean package`. If the project does not use `spring-boot-starter-parent`, configure an execution of `spring-boot-maven-plugin` with the `repackage` goal on the lifecycle. When invoking manually, a source JAR must already have been produced by `package`:

```bash
mvn package spring-boot:repackage
```

Do not run `mvn spring-boot:repackage` alone expecting the plugin to compile and package the project from scratch. The plugin may preserve the original JAR with a `.original` suffix when replacing the main artifact (when no classifier is used).

### 4.3. When You Want a WAR to Deploy to a Servlet Container

For **Spring MVC** in the sample POM, change the default `<packaging>jar</packaging>` to `<packaging>war</packaging>` right below the version declaration, and add the servlet container dependency with `provided`:

```xml
<packaging>war</packaging>
<!-- Add to existing <dependencies> section: -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Update `PackagingApplication.java` to:

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class PackagingApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(PackagingApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
```

Keep `HelloController.java` and the Maven plugin unchanged, then run:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.war
```

With the Spring Boot Maven plugin, this is an executable WAR. At the same time, the `.war` artifact can be deployed to a Tomcat **compatible** with the Spring Boot/Jakarta Servlet version in use. The URL on an external Tomcat usually depends on the WAR filename/context; for example, it may carry a `/packaging-demo-0.0.1-SNAPSHOT` prefix, whereas running standalone via `java -jar` serves the sample endpoint at `/hello`.

**Important:** `provided` is for container dependencies—do not mark all application dependencies as `provided`. Check classloaders/versions, Jakarta `jakarta.*` (Spring Boot 3+), context path configuration, and resources supplied by the external server. Do not deploy a Spring Boot 3/4 WAR onto an older servlet container that only supports the `javax.*` namespace.

### 4.4. When You Want an OCI Image from a Maven Project

With the JAR app from section 3 and a running Docker daemon:

```bash
mvn spring-boot:build-image -Dspring-boot.build-image.imageName=packaging-demo:0.0.1
docker run --rm -p 8080:8080 packaging-demo:0.0.1
```

Open another terminal and run `curl -fsS http://localhost:8080/hello`; the response body is `Hello from Spring Boot`. The plugin uses Cloud Native Buildpacks and can ensure an appropriate archive is built before creating the image. A Docker daemon must be running; builder/runtime images may need to be pulled over the network. This command creates the image in the local container environment—**it does not push it to a registry**. Naming and tagging conventions should align with your deployment team's standards.

## 5. Equivalents in Gradle

With Gradle using the Java plugin and Spring Boot Gradle plugin:

| Target | Task |
| --- | --- |
| Plain JAR | `./gradlew jar` (usually carries classifier `plain` when Boot plugin is enabled) |
| Executable JAR | `./gradlew bootJar` |
| Plain WAR | `./gradlew war` (when the `war` plugin is applied) |
| Executable WAR | `./gradlew bootWar` (when the `war` plugin is applied) |
| OCI image via Buildpacks | `./gradlew bootBuildImage --imageName=packaging-demo:0.0.1` |

Sample `build.gradle` (Groovy DSL) using the Java code from section 3:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Running `./gradlew clean bootJar jar` produces both the executable and plain JARs under `build/libs/` (actual filenames depend on project/version/classifier). To switch to WAR, add `id 'war'` to `plugins`, add `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` to `dependencies`, apply `SpringBootServletInitializer` as in section 4.3, and run `./gradlew clean bootWar`. This `providedRuntime` example uses a Boot 3.5.x dependency; for Spring Boot 4.x, check the container runtime artifact of that release line.

`./gradlew bootBuildImage --imageName=packaging-demo:0.0.1` creates an OCI image with Buildpacks and requires connectivity to a Docker daemon (or configured compatible runtime). On Windows, use `gradlew.bat`; if no Gradle Wrapper is present yet, generate the wrapper or invoke `gradle` accordingly.

**Distinction:** `bootJar`/`bootWar` are Spring Boot plugin tasks, while `jar`/`war` are standard Java/WAR packaging tasks. The `*-plain.jar` name is only a common convention; do not infer artifact type from filename alone—inspect its contents and task configuration.

## 6. OCI Image with a Dockerfile: When Do You Need More Control?

If you need custom image setup, after building the executable JAR you can use a minimal Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/packaging-demo-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

```bash
mvn clean package
docker build -t packaging-demo:dockerfile .
docker run --rm -p 8080:8080 packaging-demo:dockerfile
```

This is a **Dockerfile for an already-built JAR**, not a Dockerfile that compiles Java itself. `EXPOSE 8080` only declares metadata, whereas `-p 8080:8080` publishes the port from the container to the host. In production, pin base image tags/digests, monitor patches and CPU architecture compatibility, run as a non-root user, manage config/secrets at runtime, scan for vulnerabilities, and consider layering for cache efficiency. Cloud Native Buildpacks often reduce Dockerfile maintenance effort, but do not eliminate image updates and security checks.

## 7. Selection Rules by Scenario

- **Module `billing-core` imported by three other applications:** publish a **plain JAR** as a dependency. Do not make an executable Boot JAR its primary library artifact.
- **API `order-service` running on a VM with systemd, no Docker requirement:** use an **executable JAR** and a compatible Java runtime; deploy as a single process with health checks, logging, and restart policies.
- **Enterprise with centrally operated Tomcat requiring WAR deployment:** use a **WAR**, `SpringBootServletInitializer`, and `provided` servlet container dependencies; verify servlet/JDK compatibility prior to deployment.
- **Service running on Kubernetes:** prefer an **OCI image**; inside it is usually an executable JAR, built with Buildpacks or a Dockerfile, with tags and digests managed in CI/CD.
- **Same service running both standalone and on external Tomcat:** an **executable WAR** can satisfy both modes, though both startup paths must be tested separately; do not pick it by default unless WAR deployment is genuinely needed.
- **Having both reusable libraries and a directly runnable service:** separate library modules from application modules, or publish both a plain JAR and an executable JAR with **different classifiers**; avoid letting a library dependency accidentally point to the Boot repackaged artifact.

A simple decision flow:

```text
Is the artifact imported by another project as a library?
  Yes -> plain JAR (or separate library module).
  No  ->
    Does the platform mandate an external servlet container?
      Yes -> deployable WAR; consider executable WAR if standalone execution is also needed.
      No  ->
        Does the deployment platform use Docker/Kubernetes?
          Yes -> OCI image, typically built from an executable JAR.
          No  -> executable JAR run via java -jar.
```

Do not pick WAR just because the application exposes an HTTP API; embedded Tomcat in an executable JAR already serves HTTP. And do not call an OCI image a "new JAR": images and JARs address two different packaging layers.

## 8. Pre-Release Checks and Common Pitfalls

### Verification Checklist

1. **Artifact type:** verify Maven/Gradle commands, `pom.xml`/`build.gradle`, and `jar tf` or `unzip -l` output. For a Boot JAR, expect `BOOT-INF/classes`, `BOOT-INF/lib`, and the launcher; for a WAR, inspect `WEB-INF`.
2. **Execution:** test the actual deployment mechanism: plain JAR as a consumer dependency; executable JAR via `java -jar`; WAR on the app server; OCI image in a container.
3. **Live run:** invoke `/hello` or a business endpoint, checking exit codes, logs, and HTTP status. Seeing `BUILD SUCCESS` alone is not enough.
4. **Compatibility:** verify Java versions at build and runtime, Spring Boot, servlet container, image architecture, and runtime dependencies.
5. **Deployment readiness:** externalize config/secrets, expose/publish ports, configure health/readiness checks, set RAM/CPU limits, capture stdout/stderr logs, run vulnerability scans, and plan base image updates.
6. **Reproducibility:** pin dependencies/plugins, establish clear versions/tags, and in container environments prefer deploying by verified image digest rather than relying solely on `latest`.

| Symptom | Likely Cause | How to Check / Fix |
| --- | --- | --- |
| `no main manifest attribute` on `java -jar` | Running a plain JAR or build wasn't repackaged | Use `bootJar`/`spring-boot:repackage`; inspect manifest and JAR layout |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing dependency or using a Boot repackaged JAR as a regular classpath library | Inspect `BOOT-INF/lib`, dependency tree, and right artifact/classifier |
| `UnsupportedClassVersionError` | Runtime Java is older than compiled bytecode | Check `java -version` and toolchain/`java.version`; upgrade runtime or compile to a supported target |
| WAR fails to start on external Tomcat | Missing initializer, wrong `provided`, or incompatible servlet/Jakarta/Java versions | Check `SpringBootServletInitializer`, deployment logs, and versions |
| WAR deploys cleanly but `/hello` returns 404 | WAR context path differs from expectation or mapping wasn't registered | Check WAR filename/context path and mapping logs; hit the exact URL |
| `bootBuildImage`/`build-image` cannot connect to Docker | Docker daemon/context isn't running or reachable | Check `docker info`, Docker context, and plugin configuration |
| Image runs but HTTP is unreachable | Port not published, app listens on another port, wrong bind address, or probe issue | Inspect `docker logs`, `server.port` config, and `docker run -p` |
| Container exits out of memory | Memory limit too low for JVM/application | Check exit code, container logs, JVM memory settings, and runtime limits |

**Do not confuse "packaged successfully" with "deployed successfully."** Packaging only proves an artifact exists; only testing in a production-like environment confirms Java runtime, dependencies, ports, configuration, and startup behavior.

## 9. Official Documentation for Version-Specific Reference

- Spring Boot Maven Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html).
- Spring Boot Gradle Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html).
- Spring Boot – [Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html).
- Spring Boot Maven Plugin – [Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).
- Spring Boot Gradle Plugin – [Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html).

**Rule of thumb:** module to import → plain JAR; JVM app running directly → executable JAR; managed servlet container environment → deployable WAR; container platform → OCI image (usually packaging an executable JAR inside).