# Checking Boot Loader, jarmode, and Packaging Structure Changes Across Versions

## 1. Purpose and Scope

A Spring Boot executable JAR/WAR is more than an archive containing classes and dependencies. The packaging plugin also creates the manifest, places application classes in the right directory, embeds the Spring Boot Loader, writes classpath/layers indexes, and may include tools for running in jarmode. Dockerfiles, shell scripts, systemd units, deployment pipelines, and artifact analysis steps often depend on these details.

When upgrading Spring Boot, the build may still succeed while the artifact or image no longer runs properly if:

- Scripts still invoke `-Djarmode=layertools` after that jarmode was removed.
- Dockerfiles hard-code an old launcher class or loader path.
- The build still configures `LoaderImplementation.CLASSIC` even though Boot 4 removed that option.
- The pipeline expects an embedded launch script inside the executable JAR.
- Optional runtime dependencies are no longer included in the executable archive by default.
- The Dockerfile accidentally copies `*-plain.jar`, `.original`, or an artifact with a different classifier.
- Layer indexing or jarmode tools are disabled while the image build still relies on them.

This guide explains the executable archive structure, the role of the Boot Loader, manifests, nested JARs, `classpath.idx`, `layers.idx`, jarmode, and how they change across Boot 3.3, 3.5, 4.0, and 4.1. It focuses on Maven/Gradle packaging and verifying real artifacts before release.

After this guide, you will be able to:

- Read JAR/WAR structures and distinguish the launcher from the application's main class.
- Verify `Main-Class`, `Start-Class`, loader classes, and `BOOT-INF`/`WEB-INF` directories.
- Understand the transition from `layertools` to `tools` and replacement commands.
- Remove classic loader and embedded launch script configurations when upgrading to Boot 4.
- Inspect the default change for optional dependencies in Maven executable archives.
- Configure `includeTools`, layers, and `includeOptional` appropriately.
- Update Dockerfiles, scripts, service units, and CI artifact selection.
- Run archive, extraction, `java -jar`, and container smoke tests.

## 2. Version-by-Version Change Map

Key milestones to remember:

| Version | Packaging-Related Changes |
| --- | --- |
| Spring Boot 3.2 and earlier | Projects may still use `-Djarmode=layertools`, `layers.includeLayerTools` configuration, or classic loader implementation. |
| Spring Boot 3.3 | Introduced jarmode `tools`; `extract` replaces `layertools extract`, `list-layers` replaces `layertools list-layers`. `layertools` and old configuration are deprecated. |
| Spring Boot 3.5 | Continues supporting `tools`, layered archives, `includeTools`, and launchers in the `org.springframework.boot.loader.launch` package. Maven Plugin 3.5.7+ adds `includeOptional`. |
| Spring Boot 4.0 | Removes classic uber-JAR loader option; removes embedded launch scripts for fully executable JARs; optional Maven dependencies are no longer included in the uber JAR by default. |
| Spring Boot 4.1 | Removes jarmode `layertools`; use `tools`. Standard executable JAR/WAR layout and launcher manifest continue using `BOOT-INF`/`WEB-INF` paths and `org.springframework.boot.loader.launch`. |

Official sources to read together: [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes), [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide), [Spring Boot 4.1 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes).

**Key point:** do not treat this as a single launcher package rename. The standard manifest launcher `org.springframework.boot.loader.launch.JarLauncher` is used by both Boot 3.5 and Boot 4.1 documentation. The main breaking changes are the loader implementation option, launch scripts, jarmode, and dependency inclusion. Inspect the manifest of the generated artifact instead of guessing class names.

## 3. How an Executable JAR Differs from a Plain JAR

A plain JAR typically contains only the module's classes and resources. It does not package all runtime dependencies in a structure that the Spring Boot Loader can load directly with `java -jar`.

An executable JAR produced by the Spring Boot Maven/Gradle Plugin adds:

- Spring Boot Loader classes at the root of the archive.
- Application classes inside `BOOT-INF/classes/`.
- Runtime dependencies as nested JARs inside `BOOT-INF/lib/`.
- `META-INF/MANIFEST.MF` with the launcher class and application main class.
- Optionally `BOOT-INF/classpath.idx` and `BOOT-INF/layers.idx`.
- Optionally `spring-boot-jarmode-tools` to support extraction/layer operations.

Illustrative structure:

~~~text
application.jar
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- ... Boot Loader classes ...
|
+-- BOOT-INF/
    +-- classes/
    |   +-- com/example/Application.class
    |   +-- application.yml
    |
    +-- lib/
    |   +-- spring-boot-*.jar
    |   +-- spring-context-*.jar
    |   +-- application-dependency-*.jar
    |
    +-- classpath.idx     (optional)
    +-- layers.idx        (optional)
~~~

The Java launcher reads the manifest to invoke the Boot Loader. The loader sets up an appropriate classloader, reads nested JARs, and then calls the application's main class. This allows users to run:

~~~bash
java -jar application.jar
~~~

This model differs from traditional shaded/fat JARs. A shaded JAR usually unpacks and merges classes from dependencies into one archive; a Boot executable JAR keeps dependencies as separate nested JARs. This avoids many conflicts when libraries share resource or file names and keeps packaged dependencies visible.

Documentation: [Executable Jar Format](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html).

## 4. Executable WAR and WEB-INF/lib-provided

An executable WAR has a different layout from a JAR because it can be run using an embedded server or deployed to an external Servlet container.

~~~text
application.war
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- ... Boot Loader classes ...
|
+-- WEB-INF/
    +-- classes/
    |   +-- com/example/Application.class
    |
    +-- lib/
    |   +-- application dependencies
    |
    +-- lib-provided/
        +-- embedded-container dependencies
        +-- dependencies needed for executable WAR
~~~

- `WEB-INF/classes/` holds application classes and resources.
- `WEB-INF/lib/` holds regular dependencies.
- `WEB-INF/lib-provided/` holds dependencies needed when running the WAR standalone, marked `provided` in the build model to avoid conflicts when deployed to a traditional container.

An executable WAR has the appropriate launcher manifest and can be run with `java -jar application.war`. When deploying to an external Tomcat/Servlet container, check the container version and provided dependencies separately; a WAR running via the embedded launcher does not automatically prove the external container has the same classpath or Servlet API.

Do not copy JAR `BOOT-INF/lib` rules into a Dockerfile handling a WAR. Paths and the semantics of provided dependencies are different.

## 5. Manifest: Launcher vs. Application Main Class

The manifest serves two distinct roles:

- `Main-Class` is the class that starts the Spring Boot Loader.
- `Start-Class` is the application's class with `public static void main(String[] args)`.

Executable JAR example:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.Application
~~~

Executable WAR example:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.Application
~~~

Do not confuse `Main-Class` with `Start-Class`. If `Main-Class` is set to `com.example.Application` while the archive still contains nested dependencies, the JVM does not natively know how to load nested JARs. When using the Spring Boot Maven Plugin, the plugin manages the manifest; if you need to change `mainClass` or layout, configure the Spring Boot Plugin rather than trying to alter the manifest with another JAR plugin.

### 5.1. JarLauncher, WarLauncher, and PropertiesLauncher

- `JarLauncher` reads nested libraries in `BOOT-INF/lib/`.
- `WarLauncher` reads libraries in `WEB-INF/lib/` and `WEB-INF/lib-provided/`.
- `PropertiesLauncher` allows adding external dependency locations outside the archive; by default it still searches `BOOT-INF/lib/`, and can also read `LOADER_PATH`, `loader.path`, or configuration in `loader.properties`.

`PropertiesLauncher` is useful when a deployment environment needs to mount an external plugin/library directory outside the archive. However, you must control the versions, permissions, and immutability of that directory; external dependencies can cause the same JAR to behave differently across environments.

Example of setting the launcher via manifest in Gradle:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    manifest {
        attributes(
            "Main-Class" to "org.springframework.boot.loader.launch.PropertiesLauncher",
            "Start-Class" to "com.example.Application"
        )
    }
}
~~~

Only choose `PropertiesLauncher` when you genuinely need a dynamic loader path. For typical applications, let the plugin pick the default launcher for the layout.

Documentation: [Launching Executable Jars](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/launching.html).

## 6. Boot Loader Package and Classic Loader Removal

The Spring Boot Loader is bootstrap code inside the executable archive. The standard launcher package in Boot 3.5 and Boot 4.1 is:

~~~text
org.springframework.boot.loader.launch.JarLauncher
org.springframework.boot.loader.launch.WarLauncher
org.springframework.boot.loader.launch.PropertiesLauncher
~~~

Loader classes are placed in the archive under the root path `org/springframework/boot/loader/`. Do not confuse the Java package of the launcher with the archive path of the loader classes.

### 6.1. Classic Uber-JAR Loader Removed in Boot 4.0

Some Boot 3.x builds could select the classic loader implementation via plugin configuration. Spring Boot 4.0 removed the classic uber-JAR loader. If your build has the configurations below, you must remove them when upgrading to Boot 4:

Maven:

~~~xml
<configuration>
    <loaderImplementation>CLASSIC</loaderImplementation>
</configuration>
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    loaderImplementation = org.springframework.boot.loader.tools.LoaderImplementation.CLASSIC
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    loaderImplementation =
        org.springframework.boot.loader.tools.LoaderImplementation.CLASSIC
}
~~~

This is legacy configuration specifying the classic implementation. Boot 4 no longer has this option; remove the setting from the POM/build script and let the Boot 4 plugin generate the default loader.

Do not work around this by manually adding `spring-boot-loader` as a dependency or copying launcher classes into the JAR. The Spring Boot Plugin must generate the archive and manifest in sync with the loader implementation for that exact version.

### 6.2. Do Not Hard-Code Legacy Launcher Classes

Very old Dockerfiles or scripts may directly invoke `org.springframework.boot.loader.JarLauncher`. For archives packaged per Boot 3.5/4.1 documentation, the standard manifest launcher uses the `org.springframework.boot.loader.launch` package.

Check places that may hard-code it:

- `Main-Class` in custom manifests.
- `ENTRYPOINT`/`CMD` in Dockerfiles.
- Java commands in shell scripts or service units.
- `-Dloader.main`, manually assembled classpaths, or custom launchers.
- Scripts that unpack the archive and invoke the launcher class directly.

Prefer `java -jar application.jar`. If invoking the launcher class directly is unavoidable, verify the actual manifest, classpath, and loader version.

## 7. Embedded Launch Scripts Removed in Boot 4.0

Boot 3.x could build fully executable JARs with an embedded launch script. The script was prepended to the archive so Unix-like OSes could run the file like a shell script; the Maven plugin had `executable` and `embeddedLaunchScript` properties, and Gradle had `launchScript()`.

Old Maven example:

~~~xml
<configuration>
    <executable>true</executable>
</configuration>
~~~

Old Gradle example:

~~~groovy
tasks.named("bootJar") {
    launchScript()
}
~~~

Boot 4.0 removed embedded launch scripts. Remove these configurations when upgrading. Standard executable JARs still run using:

~~~bash
java -jar application.jar
~~~

If you need to run the application as a service, move the startup command to the service manager, container runtime, or deployment platform:

- systemd unit on Linux.
- Docker/OCI `ENTRYPOINT`.
- Kubernetes container command.
- Gradle Application Plugin if separate distribution scripts are needed.
- Process manager/Windows service wrapper supported by the organization.

Do not use embedded launch scripts in new JARs, and do not assume `java -Djarmode=tools -jar` can process an archive with an embedded launch script. Boot 3.5 docs state that tools mode cannot be used with fully executable archives containing a launch script.

Documentation: [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).

## 8. Jarmode: From layertools to tools

Jarmode allows Boot's bootstrap code to run a utility instead of starting the application. It is commonly used in Docker builds to inspect an archive, list layers, or extract the archive into directories.

### 8.1. Before Boot 3.3: layertools

Older Dockerfiles may contain:

~~~bash
java -Djarmode=layertools -jar application.jar list
java -Djarmode=layertools -jar application.jar extract
~~~

Jarmode `layertools` was deprecated in Spring Boot 3.3.

### 8.2. From Boot 3.3 Onward: Use tools

Boot 3.3 introduced `tools` and replaced the legacy commands:

| Old Command | New Command |
| --- | --- |
| `java -Djarmode=layertools -jar app.jar extract` | `java -Djarmode=tools -jar app.jar extract --layers` |
| `java -Djarmode=layertools -jar app.jar list-layers` | `java -Djarmode=tools -jar app.jar list-layers` |

Common commands:

~~~bash
java -Djarmode=tools -jar application.jar
java -Djarmode=tools -jar application.jar help
java -Djarmode=tools -jar application.jar list-layers
java -Djarmode=tools -jar application.jar help extract
java -Djarmode=tools -jar application.jar extract
java -Djarmode=tools -jar application.jar extract --layers --destination extracted
~~~

- `extract` without `--layers` creates an efficient layout: an application JAR and extracted libraries in a `lib/` directory. This layout is useful for startup, CDS, and AOT cache.
- `extract --layers` splits contents according to `layers.idx` so Docker/OCI can create separate image layers.
- `list-layers` displays the extractable layers.
- `help` and `help extract` display commands/options supported by the archive itself.

### 8.3. Boot 4.1 Removes layertools

Spring Boot 4.1 removes jarmode `layertools`. If a script still calls `-Djarmode=layertools`, it is no longer a valid execution path. Switch to `-Djarmode=tools`, then test the command against an actual Boot 4.1 archive.

**Recommendation:** migrate Boot 3.x projects to `tools` during upgrade preparation. That way Dockerfiles and scripts no longer depend on a deprecated command before switching Boot major versions.

Sources: [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes) and [Spring Boot 4.1 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes).

## 9. includeTools and Embedding Jarmode Tools into the Archive

When building a layered archive, the plugin adds `spring-boot-jarmode-tools` so `java -Djarmode=tools -jar ...` works. Depending on the plugin version, disabling layer creation does not necessarily disable the tools JAR.

Since Boot 3.3, the old `layers.includeLayerTools` configuration was replaced by `includeTools`. Use the new property:

Maven:

~~~xml
<configuration>
    <includeTools>true</includeTools>
</configuration>
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    includeTools = true
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    includeTools.set(true)
}
~~~

If the archive does not need extraction/layer commands, you can set `includeTools=false`. However, if the Dockerfile uses jarmode tools, the tools dependency must remain in the archive.

Do not confuse these two settings:

- `layers.enabled=false` disables creating layer index/metadata per plugin configuration.
- `includeTools=false` excludes the tools JAR from the archive.

If a build script sets `layers.enabled=false` while the Dockerfile still runs `list-layers` or `extract --layers`, the image build can fail because layer metadata or the appropriate tools dependency is missing. Check both settings together.

## 10. layers.idx, Layer Order, and Docker Cache

A layered JAR still uses the standard executable JAR layout while adding `BOOT-INF/layers.idx`. By default, layers are ordered from least frequently changing to most frequently changing:

1. `dependencies`: release dependencies not containing `SNAPSHOT`.
2. `spring-boot-loader`: loader classes.
3. `snapshot-dependencies`: dependencies whose version contains `SNAPSHOT`.
4. `application`: project/module dependencies, application classes, and resources.

Example index contents:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/library-a.jar"
  - "BOOT-INF/lib/library-b.jar"
- "spring-boot-loader":
  - "org/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/library-snapshot.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
~~~

Layer order matters. Stable dependencies should come first; frequently changing application code should come last. When only source code changes, Docker can reuse dependency layers from the previous image and rebuild only the application layer.

`layers.idx` is used for splitting the archive into OCI/Docker layers. It is not a classpath list. `classpath.idx` serves a different purpose: recording the order of nested dependency JARs to place on the classpath.

### 10.1. Customizing Layers

Customize layers only when there is a clear reason, such as a group of internal dependencies changing on its own cycle. When customizing:

- Ensure every required archive entry is assigned to the right layer.
- Avoid having a file unintentionally claimed by multiple rules.
- Document the layer order clearly.
- Check `list-layers` and extraction output after changing rules.
- Verify the Dockerfile copies all generated layer directories.

If layer order changes, Docker image cache behavior changes too. Re-measure image size and how many layers rebuild after a sample source/dependency change.

## 11. classpath.idx and Dependency Ordering

`BOOT-INF/classpath.idx` can be generated automatically by the plugin. It lists nested JARs in the classpath order used by the build system when running the application.

Example:

~~~text
- "BOOT-INF/lib/dependency-a.jar"
- "BOOT-INF/lib/dependency-b.jar"
~~~

Notes:

- The plugin can generate the index automatically.
- The index is used when running the archive with `java -jar`.
- It is not used when running the application from an IDE, `mvn spring-boot:run`, or Gradle `bootRun`.
- When reproducible builds are enabled, entries in the classpath index may be sorted alphabetically according to plugin rules.
- Do not hand-craft `classpath.idx` arbitrarily without understanding dependency order and how the launcher reads it.

If the application behaves differently between the IDE and `java -jar`, check the classpath index, dependency order, duplicate classes/resources, and how the plugin creates the archive.

## 12. Optional Dependencies Change in Maven Executable JARs

This is a packaging change that can let an application start locally yet fail with missing classes when running the artifact.

In Spring Boot Maven Plugin 3.5.16, `includeOptional` defaults to `true`. In Spring Boot 4.0, optional dependencies are no longer included in the uber JAR by default. Maven Plugin 4.1 also documents `includeOptional=false` as the default.

If the application truly needs a Maven dependency declared with `<optional>true</optional>` in the executable archive, make a clear decision:

1. Is that dependency a mandatory runtime requirement for the application?
2. Should it be a direct non-optional dependency of the application module?
3. If keeping it declared as optional, should `includeOptional=true` be set for the executable archive?

Maven example:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeOptional>true</includeOptional>
    </configuration>
</plugin>
~~~

If optional dependencies are only meant for consumer modules or conditionally enabled features, do not mechanically pull all of them into the production JAR. Enable `includeOptional` only after understanding the dependency graph and the purpose of each optional dependency.

**Scope:** `includeOptional` is a Maven Plugin setting. Gradle manages dependencies/variants using its own model; inspect `runtimeClasspath` and `bootJar` output rather than assuming Gradle shares Maven's default.

Documentation: [Boot 3.5 Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html), [Boot 4.1 Maven Plugin Packaging](https://docs.spring.io/spring-boot/4.1/maven-plugin/packaging.html), [Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).

## 13. Maven: repackage, Layout, and Original Artifact

The Spring Boot Maven Plugin produces an executable archive via the `repackage` goal. This goal processes the JAR/WAR created in the `package` phase; invoking the goal alone without running `package` may have no source archive to repackage.

Common commands:

~~~bash
./mvnw clean package
~~~

Or when invoking the goal explicitly:

~~~bash
./mvnw package spring-boot:repackage
~~~

If the project inherits from `spring-boot-starter-parent`, the `repackage` execution is usually already configured; simply declare the plugin per the guide.

### 13.1. Maven Archive Layouts

The plugin supports these layouts:

| Layout | Meaning |
| --- | --- |
| `JAR` | Standard executable JAR. |
| `WAR` | Executable WAR; provided dependencies are placed in `WEB-INF/lib-provided`. |
| `ZIP` or `DIR` | Layout similar to JAR but using `PropertiesLauncher`. |
| `NONE` | Bundles dependencies/resources without embedding the bootstrap loader. |

Example:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <layout>JAR</layout>
    </configuration>
</plugin>
~~~

`Main-Class` is managed by the plugin according to the layout. If using the `ZIP` layout, the launcher may be `PropertiesLauncher`; do not copy a `JAR` layout manifest into a `ZIP` layout.

### 13.2. Original Artifact and .original

By default, Maven `repackage` renames the original non-executable artifact to `.original`. You can configure a classifier to keep the plain archive and executable archive side by side.

For example, a project might produce:

~~~text
target/
  application.jar
  application.jar.original
~~~

Do not let a Dockerfile use a wildcard `target/*.jar` and accidentally copy an unwanted archive. Specify the exact verified executable artifact, classifier, and filename.

### 13.3. Sample Maven Configuration for Boot 4

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <includeTools>true</includeTools>
        <includeOptional>false</includeOptional>
        <layers>
            <enabled>true</enabled>
        </layers>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This is an illustrative Boot 4 configuration when you want a layered JAR with tools and without optional dependencies included in the archive. If the application requires optional runtime dependencies, set `includeOptional=true` after verification. If the project uses a parent that already configures `repackage`, avoid creating duplicate executions.

## 14. Gradle: bootJar, bootWar, and Plain Archives

The Gradle plugin provides these tasks:

- `bootJar`: builds the executable JAR.
- `bootWar`: builds the executable WAR.
- `jar`/`war`: builds the plain archive per the Java/War plugin.

When the Spring Boot plugin configures `bootJar`, the `jar` task typically uses the `plain` classifier so both archives can coexist.

Example:

~~~text
build/libs/
  application-1.0.0.jar
  application-1.0.0-plain.jar
~~~

Build:

~~~bash
./gradlew clean bootJar
./gradlew clean bootWar
./gradlew clean build
~~~

`build`/`assemble` is configured to depend on `bootJar` when using the Java plugin. Check task output instead of guessing artifact names.

### 14.1. Configuring a Layered bootJar

Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
    mainClass.set("com.example.Application")
}
~~~

Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    layered {
        enabled = true
    }
    includeTools = true
    mainClass = 'com.example.Application'
}
~~~

If not using jarmode tools:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
~~~

Once `includeTools=false` is set, the Dockerfile can no longer call `java -Djarmode=tools -jar ...` on that archive. Keep the configuration aligned with the image build.

### 14.2. Setting Classifiers Explicitly

If the pipeline expects an executable JAR with classifier `boot` and a plain JAR without a classifier:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("boot")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
~~~

If the plain JAR is unnecessary, the `jar` task can be disabled in some typical applications. Do not disable the `jar` task if native image builds or other plugins rely on it; check consumer tasks before changing it.

## 15. Docker Multi-Stage Builds with Jarmode Tools

Layered JARs let you separate stable dependencies from application code into distinct Docker layers. Each `COPY` can create a new layer; when code changes while dependencies stay unchanged, Docker can reuse the dependency layers.

Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS builder
WORKDIR /builder

COPY target/application.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:21-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Replace the base image with a JDK/JRE image approved by your organization, pin the tag/digest per policy, and ensure the Java runtime matches the application's bytecode.

### 15.1. Do Not Copy the Wrong Artifact

Maven can create `.original`; Gradle can create `-plain.jar`; a project may use a `boot` classifier. Use an explicit artifact path:

~~~dockerfile
COPY target/application.jar application.jar
~~~

If using Gradle:

~~~dockerfile
ARG JAR_FILE=build/libs/application-1.0.0.jar
COPY ${JAR_FILE} application.jar
~~~

Do not rely on `COPY target/*.jar` or `COPY build/libs/*.jar` if the directory contains multiple archives. A Docker build might succeed yet copy the plain archive and fail only at runtime.

### 15.2. Do Not Use Jarmode If the Archive Lacks Tools

Verify before calling `extract`:

- Does the plugin enable layers and include the tools JAR in the archive?
- Does `BOOT-INF/layers.idx` exist when using `extract --layers`?
- Is the archive an executable JAR created by the Spring Boot Plugin?
- Is there an embedded launch script from an older build?
- Is `includeTools` set to false?

If extraction is unnecessary, you can copy the executable JAR directly into the runtime image and run `java -jar`. Layering is an image-build cache optimization, not a requirement for an executable JAR to run.

## 16. Archive Indexes and Reproducible Builds

The two index files have distinct purposes:

| File | Location | Purpose |
| --- | --- | --- |
| `classpath.idx` | `BOOT-INF/classpath.idx` | Order of nested dependency JARs when the launcher builds the classpath. |
| `layers.idx` | `BOOT-INF/layers.idx` | Grouping of archive entries for creating Docker/OCI layers. |

`classpath.idx` can be generated for both JARs and WARs. `layers.idx` is used for JARs. The index files use YAML-compatible syntax, though Spring Boot does not parse them as general YAML; the exact documented format must be preserved.

When reproducible builds are enabled, the plugin can normalize entry order and timestamps. Manually modifying indexes or the zip archive after repackaging can break reproducibility or alter checksums. Let the build plugin manage these files and inspect the artifact produced by a clean build.

## 17. Nested JAR Restrictions and Libraries Requiring Unpack

The Spring Boot Loader needs to read nested JAR contents directly from the executable archive. There are several technical constraints:

- Zip entries representing nested JARs must be written as `ZipEntry.STORED`, uncompressed in the outer archive, so the loader can seek directly to nested content.
- The nested JAR file itself can still contain compressed entries.
- Code loading classes from nested JARs should use `Thread.getContextClassLoader()`; `ClassLoader.getSystemClassLoader()` does not see nested JARs in the standard way.
- Some libraries assume a JAR always exists as a standalone file on the filesystem. For those libraries, configure `requiresUnpack` so the Boot Loader unpacks the dependency to a temporary directory at startup.

Maven example:

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>org.jruby</groupId>
            <artifactId>jruby-complete</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

Gradle example:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

Only use `requiresUnpack` for dependencies confirmed to have issues running nested. Unpacking all dependencies increases startup time, I/O, and temp directory usage.

Documentation: [Executable Jar Restrictions](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/restrictions.html).

## 18. Inspecting Artifacts with Command-Line Tools

After building, inspect the actual archive instead of only trusting build logs.

### 18.1. Listing Archive Entries

Maven:

~~~bash
./mvnw clean package
jar tf target/application.jar
~~~

Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/application-1.0.0.jar
~~~

Look for entries:

- `META-INF/MANIFEST.MF`
- `org/springframework/boot/loader/`
- `BOOT-INF/classes/`
- `BOOT-INF/lib/`
- `BOOT-INF/classpath.idx`
- `BOOT-INF/layers.idx`

For a WAR, check `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.

### 18.2. Reading the Manifest

On Linux/macOS with `unzip`:

~~~bash
unzip -p target/application.jar META-INF/MANIFEST.MF
~~~

On Windows or environments without `unzip`, use `jar xf` in a temporary directory:

~~~powershell
New-Item -ItemType Directory -Force manifest-check
Set-Location manifest-check
jar xf ..\target\application.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
~~~

Verify:

- `Main-Class` points to the right launcher for the layout.
- `Start-Class` points to the application's main class.
- No legacy launcher class is hard-coded.
- Custom attributes such as `Class-Path`, `Loader-Path`, or build metadata have the right values.

### 18.3. Checking Jarmode and Layers

~~~bash
java -Djarmode=tools -jar target/application.jar list-layers
java -Djarmode=tools -jar target/application.jar help extract
java -Djarmode=tools -jar target/application.jar extract --layers --destination target/extracted
~~~

Verify the generated directories:

~~~text
target/extracted/
  dependencies/
  spring-boot-loader/
  snapshot-dependencies/
  application/
~~~

Do not just verify exit code 0; verify all required layers and files are present, then run the extracted executable layout if that is how production deploys.

### 18.4. Checking Checksums and Contents

Record the checksum of the release artifact:

~~~bash
sha256sum target/application.jar
~~~

On PowerShell:

~~~powershell
Get-FileHash .\target\application.jar -Algorithm SHA256
~~~

Compare the checksum between the CI artifact, the published artifact, and the artifact used by the Docker build. If the Docker build uses a different filename/classifier or rebuilds the artifact in a later stage, record evidence of the exact artifact placed into the image.

## 19. Migration Workflow from Boot 3.x to Boot 4.x

Follow a verifiable order:

1. **Lock baseline:** clean build, save checksum, manifest, `jar tf`, Dockerfile, and CI output for the current version.
2. **Scan repo:** search for `jarmode=layertools`, `LoaderImplementation.CLASSIC`, `loaderImplementation`, `launchScript()`, `executable=true`, `embeddedLaunchScript`, `includeLayerTools`, `includeOptional`, and any hard-coded launcher classes.
3. **Upgrade jarmode early:** from Boot 3.3 onward switch to `tools`; test `extract` and `list-layers` on the Boot 3.5 artifact.
4. **Handle loader config:** remove `loaderImplementation=CLASSIC` when upgrading to Boot 4.0.
5. **Handle launch scripts:** remove fully executable JAR configuration; move startup commands to the service/container manager or Gradle Application Plugin.
6. **Review optional dependencies:** check Maven `includeOptional` because Boot 4 flips the default to false.
7. **Review layers/tools:** confirm `layers.enabled`, `includeTools`, `layers.idx`, and the Dockerfile are aligned.
8. **Upgrade plugin with Boot:** ensure the Spring Boot Maven/Gradle Plugin matches the Spring Boot runtime generation.
9. **Build archive:** run clean `package`/`bootJar`/`bootWar` and verify manifest, layout, indexes, and classifier.
10. **Build container:** run extraction, `COPY` layers, and startup in the runtime image.
11. **Smoke test:** run `java -jar`, health endpoint, and a critical functional flow.
12. **Publish test:** verify the published artifact and Docker image digest match the QA-tested content.
13. **Rollback:** keep the old image/artifact and know clearly how to revert if the new archive lacks a dependency or loader.

### 19.1. Scanning Legacy Configurations in the Repository

Use ripgrep:

~~~bash
rg -n "jarmode=layertools|LoaderImplementation\\.CLASSIC|loaderImplementation|launchScript\\(|embeddedLaunchScript|executable>true|includeLayerTools|includeOptional|org\\.springframework\\.boot\\.loader\\.JarLauncher" .
~~~

Inspect deployment and pipeline directories as well, not just POM/`build.gradle`:

- Dockerfiles and Dockerfile templates.
- Shell scripts, Makefiles, build scripts.
- Helm charts, Kubernetes manifests.
- systemd units or service wrappers.
- CI workflows, release scripts, and artifact publishing.
- Internal build plugins/convention plugins.
- Operational READMEs/runbooks.

If the repo lacks `rg`, use `grep -R` or an equivalent search. Read the context of each match before editing; do not bulk-replace strings without confirming which version/build path they belong to.

## 20. Troubleshooting

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `no main manifest attribute` | Plain JAR or manifest lacks launcher | Check `Main-Class`; build via `repackage`/`bootJar`. |
| `ClassNotFoundException` for `JarLauncher` | Manifest references wrong package/class or loader classes missing | Read manifest and check `org/springframework/boot/loader/`. |
| `ClassNotFoundException` for application main class | Wrong `Start-Class` or application classes missing from `BOOT-INF/classes` | Check build output and `Start-Class`. |
| `NoClassDefFoundError` only in production | Dependency excluded from archive, often optional/provided/excluded | Check `BOOT-INF/lib`, Maven `includeOptional`, dependency scope, and `runtimeClasspath`. |
| `jarmode=layertools` does not work | Boot 4.1 removed `layertools` | Use `-Djarmode=tools`. |
| `jarmode=tools` not recognized | Tools JAR not packaged or archive is not a Boot executable JAR | Check `includeTools`, `spring-boot-jarmode-tools`, and manifest. |
| `list-layers` gives no matching output | No `layers.idx` or layers disabled | Check `layers.enabled`, archive index, and `extract --layers`. |
| Docker extraction fails | Dockerfile uses archive with launch script, missing tools JAR, or wrong artifact | Use normal executable archive, `includeTools=true`, pick the right file. |
| `LoaderImplementation.CLASSIC` fails to resolve | Boot 4 removed classic loader implementation | Remove CLASSIC configuration from Maven/Gradle. |
| JAR does not run as a shell script after Boot 4 upgrade | Embedded launch script was removed | Use `java -jar` in service/container or Application Plugin. |
| Docker image cannot find libraries | Wrong layer copied or layer index/custom layer rules changed | Run `list-layers`, inspect extracted tree, and `COPY` every layer. |
| App runs in IDE but fails with `java -jar` | Classpath index, dependency order, or archive contents differ | Check `classpath.idx`, manifest, and dependency graph. |
| JAR build passes yet startup is slow | Nested JAR loading, unpacking, or oversized archive | Measure startup; consider tools `extract` efficient layout and CDS/AOT. |
| Dependency present locally yet missing from artifact | Scope/optional/default inclusion changed or running plain vs. executable archive | Check effective POM and `jar tf`. |
| Pipeline publishes wrong file | Wildcard picks `.original` or `-plain.jar` | Pin artifact path/classifier; verify manifest before publishing. |
| `PropertiesLauncher` fails to load external libs | Wrong `LOADER_PATH`/`loader.path` or file permissions | Check environment, `loader.properties`, and archive layout. |
| Library fails running from nested JAR | Library requires JAR file on filesystem | Configure `requiresUnpack` for that dependency. |

### Quick Diagnostic Sequence

1. Identify the exact running file via checksum and artifact name.
2. Run `jar tf` to check the archive layout.
3. Read `META-INF/MANIFEST.MF`.
4. Inspect `BOOT-INF/classes`, `BOOT-INF/lib`, `classpath.idx`, `layers.idx`.
5. Run `java -Djarmode=tools -jar app.jar list-layers`.
6. Compare Maven/Gradle configs between old and new versions.
7. Run `java -jar` with the same runtime JDK as production.
8. Build and smoke test the final Docker image, not just the builder stage.

## 21. Hands-On Exercise and Completion Criteria

Practice on a Maven or Gradle Spring Boot application:

1. Build the Boot 3.5 artifact and record its checksum.
2. Run `jar tf`; note the `BOOT-INF`/`WEB-INF` directories.
3. Read the manifest, confirming `Main-Class` and `Start-Class`.
4. Inspect `classpath.idx` and `layers.idx` if present.
5. Run `java -Djarmode=tools -jar app.jar list-layers`.
6. Run `extract --layers --destination extracted`; verify the four default layers.
7. Find and migrate all `layertools` invocations to `tools`.
8. Find `LoaderImplementation.CLASSIC` configuration and note places to remove when upgrading to Boot 4.
9. Find embedded launch script configs and replace them with service/container commands.
10. Check Maven `includeOptional`; determine which runtime dependencies must be kept when switching to Boot 4.
11. Upgrade the Spring Boot Plugin along with the Boot version; build the new JAR/WAR.
12. Compare manifest and archive entries between Boot 3.5 and Boot 4.
13. Build a Docker image using multi-stage `tools extract`; confirm each layer is copied.
14. Run the container, verify startup/health and one critical request.
15. Verify the published artifact and checksum; confirm no plain/original archive was picked by mistake.
16. Write a migration note listing changed configurations and verification commands.

**Completion criteria:** you can read the manifest and JAR/WAR structure; explain the roles of Boot Loader and `jarmode`; replace `layertools` with `tools`; handle classic loader, embedded launch script, and optional dependency changes; have the Docker image use the proper layers; and pass `java -jar`/container smoke tests on the Boot 4 artifact.

## Official References

- [Spring Boot 3.3 Release Notes – tools jarmode and layertools deprecation](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Spring Boot 3.5 – Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 – Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 – Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 – Dockerfiles](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 4.0 Migration Guide – classic loader and launch scripts](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot 4.1 Release Notes – layertools removal](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes)
- [Spring Boot 4.1 – Launching Executable Jars](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/launching.html)
- [Spring Boot 4.1 – Executable Jar Restrictions](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/restrictions.html)
- [Spring Boot 4.1 – Maven Plugin Packaging](https://docs.spring.io/spring-boot/4.1/maven-plugin/packaging.html)
- [Spring Boot 4.1 – Gradle Plugin Packaging](https://docs.spring.io/spring-boot/4.1/gradle-plugin/packaging.html)
- [Spring Boot 4.1 – Dockerfiles](https://docs.spring.io/spring-boot/4.1/reference/packaging/container-images/dockerfiles.html)
