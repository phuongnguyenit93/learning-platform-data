# The Spring Boot Build Plugin and the Role of Repackaging

A Spring Boot project can compile cleanly yet still produce a JAR file that fails to run with `java -jar`. The cause usually lies in the difference between a **standard Java JAR** and the **executable archive** Spring Boot creates using its build plugin.

Spring Boot provides plugins for Maven and Gradle to assist with running, testing, or packaging applications. Among these, the most prominent role at release time is **repackaging**: organizing application classes, resources, dependent libraries, and the Spring Boot loader into a self-contained runnable archive.

Understanding the boundary between compile, package, and repackage helps prevent confusion over artifact files, classpaths, manifests, dependency scopes, and how applications run on servers or in containers.

## 1. What problem does the build plugin solve?

A Spring Boot application contains more than just the project's own classes. It typically needs many libraries: Spring Framework, an embedded server, a JSON mapper, database drivers, logging, and other dependencies.

When creating a standard Java JAR, packaging only puts the project's classes and resources into the archive. Dependent JARs remain outside and must be supplied on the classpath at runtime.

The Spring Boot build plugin helps produce a more convenient archive:

- Packages the application's classes and resources.
- Includes the appropriate runtime dependencies inside the archive.
- Adds the **Spring Boot loader** to load nested JARs inside.
- Generates a manifest describing the launcher and the application's main class.
- Supports executable JARs or executable WARs depending on the application type.
- Can add layer metadata to build container images more efficiently.

The overall build is still orchestrated by Maven or Gradle. The plugin does not replace the compiler, test runner, or dependency resolution; it consumes their outputs to produce a runnable Spring Boot artifact.

## 2. Distinguishing a standard JAR from an executable Spring Boot JAR

A standard Java JAR might look like this:

~~~text
catalog-service.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        ├── CatalogApplication.class
        └── service/
            └── CatalogService.class
~~~

If Spring libraries sit outside the JAR, `java -jar catalog-service.jar` will not automatically find them. Depending on how the manifest and classpath are set up, the application may report a missing main class, missing dependencies, or no entry point.

An executable JAR repackaged by Spring Boot typically has this structure:

~~~text
catalog-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/CatalogApplication.class
    │   └── application.yml
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   └── other-runtime-dependencies.jar
    ├── classpath.idx                (if generated)
    └── layers.idx                   (if generated)
~~~

From this layout:

- `BOOT-INF/classes/` holds the application's code and resources.
- `BOOT-INF/lib/` holds required dependency JARs.
- `org/springframework/boot/loader/` holds the launcher classes and nested-JAR loading support.
- `META-INF/MANIFEST.MF` tells Java the archive's entry point.

Filenames depend on versions and the actual dependency list; the structure above illustrates the component groups.

An executable JAR is not simply "extracting all dependency contents into the same package directory". Spring Boot normally keeps dependencies as **nested JARs** and uses a loader to load them.

## 3. How do the Spring Boot loader and manifest work?

The standard Java launcher reads `Main-Class` in the manifest to find the program's starting point. In an executable Spring Boot JAR, `Main-Class` usually points to the **Spring Boot launcher**, while the application's main class is recorded in `Start-Class`.

Illustrative manifest for a modern Spring Boot version:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.CatalogApplication
Spring-Boot-Version: <spring-boot-version>
~~~

`Start-Class` is the application class containing `public static void main(String[] args)`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

When running:

~~~bash
java -jar catalog-service.jar
~~~

the high-level sequence is:

~~~text
java -jar catalog-service.jar
            |
            v
JVM reads META-INF/MANIFEST.MF
            |
            v
Runs Spring Boot JarLauncher
            |
            v
Sets up classpath from BOOT-INF/classes and BOOT-INF/lib
            |
            v
Loads Start-Class
            |
            v
CatalogApplication.main(args)
            |
            v
SpringApplication.run(...)
~~~

The exact launcher name may vary across Spring Boot generations. For example, some older versions use `org.springframework.boot.loader.JarLauncher`, while newer versions place launchers under `org.springframework.boot.loader.launch`. Do not edit the manifest manually based on this example; the build plugin selects the launcher compatible with your Spring Boot version.

### Why is the Spring Boot launcher needed?

The standard Java classpath does not automatically treat `.jar` files located **inside** another JAR as classpath entries. The Boot loader enables reading nested dependencies according to Spring Boot's defined layout.

If you omit the loader while keeping dependencies in `BOOT-INF/lib`, a standard JVM may fail to find Spring classes. Conversely, if you run a JAR not repackaged with Boot's launcher, you cannot assume it follows the same layout.

Therefore, **the Spring Boot loader is a functional part of an executable archive**, not merely decorative metadata.

## 4. Maven: spring-boot-maven-plugin and repackage

For Maven, Spring Boot provides:

~~~text
org.springframework.boot:spring-boot-maven-plugin
~~~

The primary goal for producing an executable archive is:

~~~text
spring-boot:repackage
~~~

Maven runs phases such as `compile`, `test`, and `package`. The plugin's `repackage` goal is used **after** Maven has built the standard JAR/WAR, then repackages that artifact into Spring Boot's layout.

Example POM using the Spring Boot parent:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version><!-- Project Spring Boot version --></version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-service</artifactId>
    <version>1.0.0</version>

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
~~~

In this example, the parent `version` field must be replaced with a real version consistent with the project. Most Maven projects using the starter parent get appropriate plugin management and the `repackage` execution automatically.

Build:

~~~bash
mvn clean package
~~~

When the `repackage` execution is bound to the lifecycle, Maven creates the JAR and the plugin turns it into an executable Spring Boot JAR. Outputs typically appear under `target/`:

~~~text
target/
├── catalog-service-1.0.0.jar
└── catalog-service-1.0.0.jar.original
~~~

The `.jar` file is the repackaged executable archive. The `.jar.original` file is the initial JAR built by Maven before repackaging, when the plugin replaces the main artifact under its default configuration.

Filenames and retention of the original artifact may differ if the project configures `classifier`, `attach`, or custom packaging. Do not treat the `.original` suffix as a universal rule across all projects.

### Maven without the Spring Boot parent

If a project uses a custom parent POM, merely declaring the plugin **does not guarantee** the `repackage` goal is automatically bound to `package`. You may need an explicit execution declaration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version><!-- Version matching Spring Boot --></version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

In this example, version comments are placeholders to be replaced in a real POM. The `repackage` goal execution binds to the `package` phase by default; if customized, verify the actual phase/execution.

You can invoke the goal manually:

~~~bash
mvn package spring-boot:repackage
~~~

However, for pipelines that build frequently, configuring the execution consistently in the POM is far easier to maintain than relying on the caller to remember appending the goal every time.

## 5. Role of repackage in the Maven lifecycle

Distinguish two steps:

~~~text
mvn package
      |
      v
Maven compiler/test/resource processing
      |
      v
maven-jar-plugin or maven-war-plugin
      |
      v
Standard JAR/WAR artifact
      |
      v
spring-boot:repackage (if bound)
      |
      v
Executable Spring Boot JAR/WAR
~~~

`repackage` **does not replace compilation**. It takes the packaged output and reorganizes the archive, adding the loader, nested dependencies, and manifest.

If the build fails saying no main class was found, locate the class containing `main()` and configure the main class for the plugin. If the build has not yet produced the base artifact, repackage cannot synthesize uncompiled classes on its own.

### Specifying the main class when needed

In projects with multiple main classes, you can declare:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.CatalogApplication</mainClass>
    </configuration>
</plugin>
~~~

If there is only one unambiguous main class, the plugin can usually infer it. With multiple entry points or complex multi-module layouts, explicit declaration prevents picking the wrong class.

### Can repackage be skipped?

The Maven plugin has a `skip` option for situations where you do not want `repackage` to run. Then the artifact remains the standard archive created by Maven.

Do not disable repackage and still distribute the file as an executable Spring Boot JAR unless the build uses another purposefully designed packaging and classpath mechanism.

## 6. Gradle: spring-boot-gradle-plugin and bootJar

With Gradle, the Spring Boot plugin is declared with plugin ID:

~~~text
org.springframework.boot
~~~

Gradle Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Replace `<spring-boot-version>` with your project's version. If you do not use the plugin's dependency management or a BOM, configure dependency version management accordingly.

When a project applies both the Java plugin and the Spring Boot plugin, the `bootJar` task is typically created to package an **executable JAR**.

~~~bash
./gradlew bootJar
~~~

Unlike Maven's `repackage` which transforms a JAR/WAR already built by Maven, Gradle's `bootJar` is an archive task configured directly to build an executable Spring Boot archive.

Mental flow:

~~~text
Gradle compileJava + processResources
           |
           v
      class/resource output
           |
           v
         bootJar
           |
           v
   Executable Spring Boot JAR
~~~

### How do bootJar and jar differ?

In a Gradle project using the Spring Boot plugin, both tasks may exist:

- `jar`: builds a standard Java JAR from project outputs.
- `bootJar`: builds an executable Spring Boot JAR including the loader and runtime dependencies.

In many Spring Boot plugin versions, the `jar` task receives the `plain` classifier to avoid colliding with the executable JAR's name:

~~~text
build/libs/
├── catalog-service-1.0.0.jar
└── catalog-service-1.0.0-plain.jar
~~~

Typically, the file without a classifier is the executable artifact from `bootJar`, while the `-plain.jar` file is the standard JAR.

Nevertheless, **names and classifiers can be customized**; identify files by the task that produced them and their actual manifest, not merely by file size or suffix.

An example of explicit naming:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'catalog-service-exec.jar'
}
~~~

With Kotlin DSL:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("catalog-service-exec.jar")
}
~~~

This changes the output filename of the `bootJar` task, not the main class inside the archive.

### bootRun vs. bootJar

`bootRun` runs the application via Gradle from the project classpath, which is handy during development:

~~~bash
./gradlew bootRun
~~~

`bootJar` builds an archive for deployment:

~~~bash
./gradlew bootJar
java -jar build/libs/catalog-service-exec.jar
~~~

`bootRun` is not a repackage operation. It can use Spring Boot DevTools and a development-oriented classpath, whereas the executable JAR is built for standalone execution via `java -jar`.

## 7. Spring Boot Gradle plugin and dependency classpath

The `bootJar` task needs the right runtime dependencies so the application can start. In Gradle, how you declare dependencies affects what ends up in the archive:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Meaning:

| Gradle configuration | Typical role | Inside executable JAR |
|---|---|---|
| `implementation` | Application compile and runtime libraries | Usually included |
| `runtimeOnly` | Libraries needed only at runtime | Usually included |
| `compileOnly` | Needed only for compilation | Usually excluded |
| `annotationProcessor` | Runs during annotation processing | Not a default runtime dependency |
| `developmentOnly` | Dependencies for dev workflows when supported by plugin | Not packaged in standard `bootJar` |
| `testImplementation` | Dependencies for tests | Not an application runtime dependency |

The snippet above is illustrative; each project must manage specific dependency versions via a BOM or dependency-management strategy.

If a database driver is declared as `compileOnly` yet the application actually needs it at runtime, the executable JAR may lack the driver and throw `ClassNotFoundException` or datasource errors. That is a **dependency scope** issue, not a bug in the Spring Boot loader.

Conversely, do not put test-only or annotation-processing libraries on the runtime classpath just to silence a build error; doing so inflates artifact size and alters startup behavior.

## 8. How do Maven dependency scopes affect the artifact?

Maven distinguishes scopes such as `compile`, `runtime`, `provided`, and `test`.

Example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

In an executable archive, the plugin selects dependencies according to Spring Boot's packaging rules and plugin configuration. Do not equate those rules directly with the contents of a plain Maven JAR.

In particular, `provided` plays a distinct role when building an executable WAR for an external servlet container. How Spring Boot packages provided dependencies supports running the archive as executable while avoiding conflicts with an external container.

For DevTools, the Spring Boot Maven Plugin excludes DevTools from the executable archive by default in normal setups. This can be reconfigured, though production should generally not ship development restart tooling.

## 9. Executable WAR and bootWar

Beyond executable JARs, Spring Boot supports executable WARs. A WAR is normally used when an application must be deployable to an **external servlet container**, while optionally supporting `java -jar` execution when packaged in Boot's layout.

With Gradle, when applying the `war` plugin as well, Spring Boot provides the `bootWar` task:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

In a real WAR application, the main class typically extends `SpringBootServletInitializer` so an external servlet container can initialize the `ApplicationContext`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class CatalogApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(CatalogApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Build the WAR with Gradle:

~~~bash
./gradlew bootWar
~~~

A Spring Boot WAR may contain:

~~~text
catalog-service.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   └── lib-provided/
└── org/springframework/boot/loader/...
~~~

Key meanings:

- `WEB-INF/classes/`: application classes and resources.
- `WEB-INF/lib/`: libraries needed when deploying to a servlet container.
- `WEB-INF/lib-provided/`: dependencies used only to support running the WAR as executable without exposing them on the normal classpath of an external container.

When running the WAR with `java -jar`, the Boot launcher can use the needed components. When deploying the WAR to an external servlet container, the container provides its own servlet runtime.

If the application only runs in container images with Spring Boot's embedded server, an executable JAR is usually simpler than an executable WAR. WAR fits cases that require deployment to an external servlet container.

### Maven WAR packaging

A Maven project can set:

~~~xml
<packaging>war</packaging>
~~~

When the servlet container is provided externally, the container dependency typically gets scope `provided` as required. `spring-boot:repackage` can process the WAR packaged by Maven and add the loader to support executable runs.

Crucially, choosing JAR vs. WAR comes from the **deployment model**, not because WAR is inherently better than JAR or vice versa.

## 10. Repackage is not the same as traditional shading or uber-JARs

There are multiple ways to build a Java artifact containing dependencies:

| Approach | Mechanism | Characteristics |
|---|---|---|
| Standard JAR | Contains project classes/resources | Dependencies must be supplied externally |
| Maven Shade/Gradle Shadow | Usually unpacks and merges dependency classes into the archive | May require duplicate resource handling and package relocation |
| Spring Boot executable JAR | Keeps dependencies as nested JARs under `BOOT-INF/lib` | Boot loader sets up classpath and launches application |

Shading and repackaging serve different purposes. Applying both to the same artifact without understanding their layouts can cause duplicate classes, broken resources, or invalid manifests/launchers.

For a typical Spring Boot application, prefer `bootJar` or `spring-boot:repackage` rather than manually building an uber-JAR by unpacking all dependencies.

When publishing a **library** for other projects to import, a standard JAR fits better than an executable Boot JAR. That is because application classes in an executable Boot archive sit under `BOOT-INF/classes`, not at the classpath position a standard library JAR expects.

## 11. Library modules and application modules should be packaged differently

A multi-module project might contain:

~~~text
workspace/
├── common-domain/
├── catalog-data/
└── catalog-app/
~~~

Here:

- `common-domain` provides APIs and domain objects for other modules.
- `catalog-data` contains shared data-access logic.
- `catalog-app` has `@SpringBootApplication` and `main()` to run the server.

In this setup, library modules normally produce **plain JARs**. Only the application module needs an **executable Spring Boot JAR**.

In Gradle, for instance, the Boot plugin can be applied only to the application module. If build conventions apply the plugin to every module, you may need to disable `bootJar` on library modules and keep `jar`, though you should not alter the task graph without clarity on packaging intent.

An executable Boot JAR is a poor choice as a direct dependency for another module: the `BOOT-INF` layout is designed for the Boot launcher, not for the Java compiler to look up classes like a normal library JAR.

### Maven classifiers for distinct artifacts

In Maven, `repackage` can configure a `classifier` to produce an additional executable artifact instead of replacing the main JAR.

Illustrative example:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

With appropriate configuration, output may include:

~~~text
catalog-service-1.0.0.jar
catalog-service-1.0.0-exec.jar
~~~

That way, one artifact can serve as a library while the other runs the application. This is a special-case setup; when you do not need to publish both artifact types, avoid adding build complexity.

## 12. Layered JAR: improving cache reuse when building container images

Spring Boot can include *layers* metadata in an executable archive. The goal is to split contents by change frequency so container image builds reuse caches more effectively.

Common layer groups:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

General meaning:

- `dependencies`: rarely changing dependencies.
- `spring-boot-loader`: Spring Boot's loader components.
- `snapshot-dependencies`: snapshot dependencies that may change frequently.
- `application`: the project's classes and resources.

Metadata may reside in:

~~~text
BOOT-INF/layers.idx
~~~

This file records layer assignments, yet **a JAR does not automatically become a container image** merely because it contains `layers.idx`.

Spring Boot versions provide tools to inspect or extract layers; launch mode mechanisms and syntax may change across versions. If a pipeline relies on layer metadata, use the tooling and documentation matching your plugin version.

Layering helps in Docker images or buildpacks because stable dependency layers stay cached across builds while the application layer updates when code changes. It does not alter the nature of `ApplicationContext` or Spring profiles.

## 13. bootBuildImage vs. bootJar

Alongside executable archives, the Spring Boot Gradle plugin also provides tasks like `bootBuildImage` to create OCI container images via Cloud Native Buildpacks when the build environment meets requirements.

~~~bash
./gradlew bootBuildImage
~~~

Correspondingly, the Spring Boot Maven Plugin provides an image-building goal, for example:

~~~bash
mvn spring-boot:build-image
~~~

Distinguish the two steps:

~~~text
bootJar / repackage
        |
        v
Executable Spring Boot archive
        |
        v
bootBuildImage / build-image (if selected)
        |
        v
OCI container image
~~~

Image creation also depends on the container environment, builder, registry, and required permissions. Building an image **is not** an inherent job of `repackage`, and a JAR runnable via `java -jar` does not automatically generate a Docker image.

If you use a custom Dockerfile, the executable JAR can be copied into the image without needing `bootBuildImage`; the choice depends on your deployment workflow.

## 14. Externalized configuration still works with executable archives

Repackaging does not mean all environment settings must be baked into the JAR. Spring Boot continues to support externalized configuration.

For example, build once:

~~~bash
./gradlew bootJar
~~~

Then the same executable JAR can run in two environments:

~~~bash
java -jar build/libs/catalog-service.jar --spring.profiles.active=staging
~~~

~~~bash
java -jar build/libs/catalog-service.jar --spring.profiles.active=prod
~~~

The actual JAR filename depends on build configuration. These two commands illustrate that **Spring profiles determine runtime configuration**, not how the build plugin structures the archive.

You can supply external config files via `./config/application.yml`, environment variables, command-line properties, or appropriate Config Data locations/imports. Do not build different executable JARs solely to swap database URLs, tokens, or logging levels when code and dependencies are identical.

Avoid embedding real secrets in classpath resources packaged with the application. Archives can be copied or downloaded; using a secrets manager or the deployment platform's configuration mechanism is safer and easier to govern.

## 15. Common packaging errors

### no main manifest attribute

If you run:

~~~bash
java -jar catalog-service.jar
~~~

and get an error like:

~~~text
no main manifest attribute, in catalog-service.jar
~~~

the JAR may be a plain JAR lacking an appropriate `Main-Class`. Verify whether `bootJar` or Maven's `repackage` execution ran, and check that you did not accidentally select `-plain.jar` or `.jar.original`.

### Could not find or load main class

This can happen if the manifest selects the wrong main class, the entry point moved packages, or the archive lacks the class where the launcher expects it.

In projects with multiple `main()` methods, configure the main class explicitly for the build plugin.

Gradle example:

~~~groovy
springBoot {
    mainClass = 'com.example.CatalogApplication'
}
~~~

With Maven, use `<mainClass>com.example.CatalogApplication</mainClass>` in the plugin configuration.

### ClassNotFoundException or NoClassDefFoundError at runtime

Do not assume nested JARs guarantee every dependency is present. A library may be declared with the wrong scope, excluded, or have a version conflict.

Inspect actual runtime dependencies and `BOOT-INF/lib` contents. For example, a JDBC driver declared as `compileOnly` in Gradle will not enter the runtime classpath as intended.

### Maven package produces a JAR that is not a Spring Boot archive

If you do not use `spring-boot-starter-parent` or executions were modified, `repackage` may not be bound to the lifecycle. Verify the Spring Boot Maven Plugin configuration and `repackage` goal.

Merely declaring a `spring-boot-starter-web` dependency **does not automatically turn** a standard Maven JAR into an executable Boot JAR.

### Plugin reports no main class found

A library project without an entry point is likely not suitable for `bootJar` or `repackage`. Decide whether the module needs a plain JAR or an executable archive. If it is genuinely an application, verify the `@SpringBootApplication` class has `main()` and declare `mainClass` when needed.

### JAR packages cleanly yet the web server does not start

Successful packaging does not guarantee valid runtime infrastructure. The application might be missing a server starter, have a bad datasource, wrong profile config, or a bean startup failure.

Separate archive/launcher errors from errors occurring after `SpringApplication.run()` begins creating the `ApplicationContext`.

### Too many dependencies packaged

An executable JAR can grow large because it bundles all runtime libraries. Do not strip dependencies blindly just to shrink size: removing the wrong one causes classpath errors. Inspect the runtime dependency graph, scopes, and genuinely needed libraries.

For containers, layering and image caching usually speed up deployment far better than manually unpacking and trimming JARs.

### Running the JAR with -cp is not like java -jar

`java -jar app.jar` gives Spring Boot's launcher the opportunity to configure the nested-JAR classpath per the manifest.

Do not assume `java -cp app.jar com.example.CatalogApplication` behaves identically, because application classes sit under `BOOT-INF/classes` and dependencies under `BOOT-INF/lib`. If you need a custom launcher or custom classpath, you must understand Spring Boot's archive layout.

## 16. Verifying the artifact before release

A useful technical verification checklist for release pipelines:

1. Identify the task/goal producing the artifact: `bootJar`, `bootWar`, or `spring-boot:repackage`.
2. Confirm the right module has the main class and right archive type.
3. Inspect the output file and avoid confusing the executable archive with a plain JAR.
4. Check the manifest, especially the loader entry point and `Start-Class`.
5. Verify critical runtime dependencies are present inside the archive.
6. Run the artifact with `java -jar` in an appropriate test environment.
7. Verify active profiles and externalized configuration load properly.
8. Observe startup logs, health endpoints, and shutdown behavior.
9. If using containers, confirm the image uses the right artifact and layers.
10. Release only verified artifacts instead of repackaging differently per environment without reason.

Example inspecting JAR contents using the JDK `jar` tool:

~~~bash
jar tf build/libs/catalog-service.jar
~~~

The command lists paths such as `BOOT-INF/classes/`, `BOOT-INF/lib/`, and Spring Boot loader classes. It only confirms archive structure; it does not prove the application will connect to a database or handle requests successfully.

In real environments, combining archive inspection with a startup smoke test is far more valuable than merely comparing file sizes.

## 17. Choosing between the Maven and Gradle plugins

Both plugins solve the goal of creating executable Spring Boot artifacts, but integrate with their build tools differently:

| Criterion | Maven | Gradle |
|---|---|---|
| Plugin | `spring-boot-maven-plugin` | `org.springframework.boot` |
| Build lifecycle | Maven phases/goals | Gradle task graph |
| Package executable JAR | `spring-boot:repackage` after package step | `bootJar` task |
| Package executable WAR | Repackage WAR | `bootWar` task |
| Run from project | `spring-boot:run` | `bootRun` |
| Plain artifact | Original JAR/WAR | `jar` / `war` task |
| Container image | `build-image` goal | `bootBuildImage` task |

You do not need both Maven and Gradle in the same module. Choose the build tool based on project standards, CI systems, multi-module structure, and what the team already uses.

Whichever build tool you use, keep the Spring Boot version of the plugin, framework, and dependencies consistent; avoid mixing incompatible versions via manual declarations.

## 18. Conclusion: repackaging draws the boundary between code and runnable artifact

The Spring Boot build plugin does not merely "zip the project into a JAR file". It transforms compilation and dependency-resolution outputs into an **executable archive** with the appropriate layout, loader, and manifest.

Key points to remember:

- A **plain JAR** contains the module's classes/resources and does not bundle all runtime dependencies by default.
- A **Spring Boot executable JAR** contains `BOOT-INF/classes`, `BOOT-INF/lib`, the loader, and the manifest to run via `java -jar`.
- With **Maven**, `spring-boot:repackage` processes the already-packaged JAR/WAR.
- With **Gradle**, `bootJar`/`bootWar` directly produces the executable archive via the task model.
- **Dependency scope** determines which libraries serve runtime; packaging tasks do not fix missing or mis-scoped dependencies.
- **Spring profiles** and externalized configuration remain runtime decisions, not repackaging responsibilities.
- **Layered JARs** can help optimize container images, though they do not equal having built an image.
- Application modules need executable archives; library modules usually need plain JARs.

When you clearly separate **compilation → plain packaging → Spring Boot repackaging → running/deploying**, you can diagnose artifact errors accurately and build consistent, operable Spring Boot release pipelines.
