# Reproducing Common Packaging Errors and Finding Root Causes via Logs and Archive Contents

## Objective

A Spring Boot application can compile and pass unit tests yet still fail when the deployed artifact is executed. Common causes include selecting a plain JAR by mistake, missing a runtime dependency, misconfiguring the main class, excluding resources from the archive, skipping Maven's repackage step, or having Docker copy an old build file.

This lab creates a small application with HTTP endpoints, intentionally introduces each error, and then uses logs, the manifest, entry listings, and dependency archives to diagnose the root cause. Every lab has three parts: reproduce, gather evidence, and fix.

Lab environment:

- Java 17 or later.
- Spring Boot Gradle plugin 3.3.13.
- Gradle Wrapper 8.x or Gradle 7.5 or later compatible with Boot 3.3.13.
- JDK tools: java, javac, and jar.
- Windows PowerShell or Linux/macOS shell.
- Maven 3.6.3 or later can be used for the Maven section.

These versions are the lab baseline, not a recommendation to run older releases in production. When applying this to real projects, check system requirements and migration guides for your supported release.

After this lesson, you will be able to distinguish plain JAR, executable Boot JAR, and WAR; reproduce failures from wrong archives, missing runtime dependencies, wrong Start-Class, and missing resources; use jar tf, manifest inspection, BOOT-INF/lib, BOOT-INF/classes, and class-loading logs to locate issues; and verify Maven repackage and Docker copying the exact right artifact.

---

## 1. Packaging Model to Understand First

### 1.1 From source code to runnable artifact

~~~text
src/main/java + src/main/resources
                |
                v
         Compile / processResources
                |
                v
       classes + processed resources
                |
                v
       Resolve runtime dependencies
                |
                v
         Packaging task
          /           \
         v             v
     plain JAR     Boot executable JAR
         |             |
         v             v
  classes/resources  Boot loader
  at archive root    BOOT-INF/classes
  no nested libs     BOOT-INF/lib/*.jar
         |             |
         v             v
  java -cp with     java -jar app.jar
  dependencies
~~~

Compilation success only proves the compiler found required types on the compile classpath. It does not prove dependencies are present in the runtime package. Likewise, a task succeeding in producing a JAR file does not prove it is the executable JAR required by the deployment environment.

### 1.2 Plain JAR vs. Boot executable JAR

With the Spring Boot Gradle plugin and Java plugin:

- The jar task builds a regular Java JAR from the project's classes and resources.
- The bootJar task builds an executable Spring Boot JAR, including the Boot loader and runtime dependencies as nested JARs.
- When both tasks are configured, the Gradle Boot plugin sets the plain classifier on the archive created by the jar task by default to distinguish the two files.
- The assemble task is configured to depend on bootJar; therefore, a normal build also creates the executable archive.

A plain JAR is useful when publishing a library or when another runtime supplies dependencies. It is not an equivalent substitute for an executable Boot JAR.

### 1.3 Internal structure of an executable JAR

~~~text
packaging-lab.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/packaging/PackagingLabApplication.class
    │   ├── com/example/packaging/GreetingService.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-web-*.jar
    │   ├── spring-core-*.jar
    │   └── commons-lang3-*.jar
    ├── classpath.idx
    └── layers.idx
~~~

Two key locations:

- BOOT-INF/classes holds application classes and resources.
- BOOT-INF/lib holds runtime dependency JARs.

META-INF/MANIFEST.MF specifies the launcher and application main class. classpath.idx may record the ordering of nested libraries; layers.idx describes archive layers for image/layer tooling.

### 1.4 Why doesn't Java load nested JARs automatically?

The standard Java classpath searches for classes in directories or JARs listed directly. It does not automatically open JAR files nested inside another JAR. Spring Boot uses a dedicated launcher to set up a classloader that understands nested archive layouts.

Therefore, this is how to run an executable Boot JAR:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

The command below is not equivalent:

~~~bash
java -cp build/libs/packaging-lab-1.0.0.jar com.example.packaging.PackagingLabApplication
~~~

It does not automatically add JARs inside BOOT-INF/lib to the classpath. Running it the second way causes the application to miss Spring classes or other dependencies.

---

## 2. Creating a Runnable Lab Project

### 2.1 Directory structure

Create project packaging-lab:

~~~text
packaging-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/
    └── main/
        ├── java/com/example/packaging/
        │   ├── PackagingLabApplication.java
        │   ├── GreetingService.java
        │   └── GreetingController.java
        └── resources/
            ├── application.properties
            └── lab/build-info.txt
~~~

Use the project's Gradle Wrapper. If initializing fresh with Gradle, generate the wrapper once using an installed Gradle and commit the wrapper files per repository guidelines.

### 2.2 settings.gradle

~~~groovy
rootProject.name = 'packaging-lab'
~~~

The project name contributes to the default archive filename.

### 2.3 Complete build.gradle

Example using Gradle's native BOM support:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.packaging.PackagingLabApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The BOM manages versions of dependencies in the Spring Boot release train. Commons Lang has an explicit version in the example. implementation places the dependency on both compile and runtime classpaths because source code uses classes from this library.

The Boot Gradle plugin creates the bootJar task when the Java plugin is applied. If your project already has a dependency management strategy, keep consistent with it; the lab simply needs a clear, working way to manage versions.

### 2.4 Main application

File src/main/java/com/example/packaging/PackagingLabApplication.java:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingLabApplication.class, args);
    }
}
~~~

This is the application entry point. The fully-qualified class name must match the actual package and class name.

### 2.5 Service using a runtime dependency

File src/main/java/com/example/packaging/GreetingService.java:

~~~java
package com.example.packaging;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        String normalized = StringUtils.trimToNull(name);
        if (normalized == null) {
            normalized = "guest";
        }
        return "Hello, " + normalized + "!";
    }
}
~~~

StringUtils belongs to Commons Lang. The lab will intentionally change this dependency from implementation to compileOnly to reproduce a runtime failure.

### 2.6 REST controller and resource

File src/main/java/com/example/packaging/GreetingController.java:

~~~java
package com.example.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Linh") String name) {
        return greetingService.greet(name);
    }

    @GetMapping("/build-info")
    public String buildInfo() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("lab/build-info.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).trim();
        }
    }
}
~~~

File src/main/resources/application.properties:

~~~properties
server.port=8080
spring.application.name=packaging-lab
~~~

File src/main/resources/lab/build-info.txt:

~~~text
artifact=packaging-lab
~~~

The /api/build-info endpoint verifies whether the resource was actually packaged into the artifact.

### 2.7 Building and running the baseline version

Linux/macOS:

~~~bash
./gradlew clean check bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean check bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

When the application starts successfully, Spring Boot logs lines similar to:

~~~text
:: Spring Boot :: (v3.3.13)
Started PackagingLabApplication in ... seconds
~~~

Startup duration and logs depend on the environment and are not fixed.

Open another terminal and call the endpoint:

~~~bash
curl "http://localhost:8080/api/greeting?name=Linh"
~~~

Response body:

~~~text
Hello, Linh!
~~~

Check the resource:

~~~bash
curl http://localhost:8080/api/build-info
~~~

Response body:

~~~text
artifact=packaging-lab
~~~

PowerShell can use:

~~~powershell
Invoke-RestMethod "http://localhost:8080/api/greeting?name=Linh"
Invoke-RestMethod "http://localhost:8080/api/build-info"
~~~

Stop the application with Ctrl+C before running subsequent labs on the same port.

---

## 3. Archive Inspection Toolkit

### 3.1 Listing entries

jar tf reads the entry list inside a JAR without extracting it:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar
~~~

Filter key entries on Linux/macOS:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep -E 'META-INF/MANIFEST.MF|BOOT-INF/classes|BOOT-INF/lib'
~~~

Windows PowerShell:

~~~powershell
jar tf build/libs/packaging-lab-1.0.0.jar |
    Select-String 'META-INF/MANIFEST.MF|BOOT-INF/classes|BOOT-INF/lib'
~~~

Find the application class:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'PackagingLabApplication.class'
~~~

An executable Boot JAR has its entry under BOOT-INF/classes/com/example/packaging. A plain JAR typically places classes at the root by package path, e.g., com/example/packaging/PackagingLabApplication.class.

### 3.2 Reading the manifest

The manifest lives at META-INF/MANIFEST.MF. On Linux/macOS you can use:

~~~bash
unzip -p build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Portable JDK approach:

~~~bash
mkdir manifest-check
cd manifest-check
jar xf ../build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Read the extracted file in PowerShell:

~~~powershell
Get-Content META-INF/MANIFEST.MF
~~~

The manifest of an executable Boot JAR typically serves two roles:

- Main-Class points to the Spring Boot launcher.
- Start-Class points to the application class with public static void main(String[]).

Launcher names can change across Spring Boot lines. Inspect the manifest of the exact artifact rather than copying a launcher class from another tutorial.

### 3.3 Checking packaged dependencies

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/'
~~~

Find Commons Lang:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/commons-lang3'
~~~

If the outer JAR contains the nested entry BOOT-INF/lib/commons-lang3-3.14.0.jar, that proves the dependency file was packaged. To inspect classes inside a nested JAR, extract the nested JAR and run jar tf on it; running jar tf on the outer archive does not list contents inside each nested JAR.

### 3.4 Checking checksums and deployed files

Linux/macOS:

~~~bash
sha256sum build/libs/packaging-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build/libs/packaging-lab-1.0.0.jar -Algorithm SHA256
~~~

Record the checksum of the tested artifact. After copying to a Docker context, staging, or release folder, recompute the hash to confirm the file was not replaced by an older artifact or a different file.

---

## 4. Lab 1 — Choosing the Plain JAR Instead of bootJar

### 4.1 Reproduce

Run both tasks:

~~~bash
./gradlew clean bootJar jar
~~~

Inside build/libs there are usually two files:

~~~text
packaging-lab-1.0.0.jar
packaging-lab-1.0.0-plain.jar
~~~

Actual filenames depend on project name, version, and configured classifiers. Under the Spring Boot Gradle plugin's default convention, the executable archive is created by bootJar; the archive created by jar receives the plain classifier.

Intentionally run the plain JAR:

~~~bash
java -jar build/libs/packaging-lab-1.0.0-plain.jar
~~~

Java typically reports no main manifest attribute or fails to launch the archive as an executable. The plain JAR also lacks the Boot loader and runtime dependencies.

### 4.2 Gather evidence

Compare both archives:

~~~bash
jar tf build/libs/packaging-lab-1.0.0-plain.jar
jar tf build/libs/packaging-lab-1.0.0.jar
~~~

In the plain JAR, application classes sit at the root package path. In the Boot JAR, application classes sit under BOOT-INF/classes and nested dependencies sit under BOOT-INF/lib.

Read both manifests. The Boot JAR's manifest has the proper launcher and Start-Class. The plain JAR may lack the Main-Class needed to run with java -jar.

### 4.3 Fix

Run the right file:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

If the pipeline requires a stable filename, configure explicit output/copy paths rather than using wildcards that can match both plain and executable archives.

For example, a Docker build stage should copy the exact artifact:

~~~dockerfile
COPY --from=build /workspace/build/libs/packaging-lab-1.0.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Do not use wildcards on a directory that may hold both plain and executable JARs. Matching multiple files can also cause Docker copy to fail or pick the wrong source depending on usage.

### 4.4 Conclusion

The error is not in source code or dependency resolution. The pipeline picked the wrong artifact type. The evidence is the classifier, archive layout, manifest, and absence of the Boot loader/nested libraries.

---

## 5. Lab 2 — Missing Runtime Dependency Due to compileOnly

### 5.1 Reproduce

In build.gradle, change:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
~~~

to:

~~~groovy
compileOnly 'org.apache.commons:commons-lang3:3.14.0'
~~~

compileOnly makes Commons Lang visible to the compiler, but the dependency does not appear on the application's standard runtime classpath. Code still compiles because GreetingService can resolve StringUtils at compile time.

Rebuild:

~~~bash
./gradlew clean bootJar
~~~

Inspect the archive:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/commons-lang3'
~~~

Not seeing the nested Commons Lang JAR is evidence that the dependency was excluded from the executable package.

The app may still start up because the class referenced inside the service method is only resolved when the endpoint invokes that method. Call:

~~~bash
curl "http://localhost:8080/api/greeting?name=Linh"
~~~

When the request enters GreetingService.greet, the JVM needs org.apache.commons.lang3.StringUtils and may throw NoClassDefFoundError. Logs usually contain a cause or message mentioning this class.

### 5.2 Find root cause via the dependency graph

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Compare the two graphs. Commons Lang appears in compileClasspath but is absent from runtimeClasspath.

You can query specifically:

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

If a module does not appear in the runtime graph, check the dependency's configuration and exclusions.

### 5.3 Fix

Because the source code directly imports and calls Commons Lang at runtime, use:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
~~~

If the dependency is part of an API that a Java library module needs to expose to consumers' compile classpath, consider api in the java-library plugin. For standard applications, implementation is the right choice.

runtimeOnly is appropriate only when the application does not need the types to compile but requires the library at runtime, such as a JDBC driver loaded by a framework. Do not replace compileOnly with runtimeOnly if source code imports that class.

### 5.4 Maven variant

Maven dependency scopes provided or test can keep a dependency out of an executable JAR's runtime packaging. Check dependency:tree -Dscope=runtime and plugin packaging configuration.

### 5.5 Conclusion

Compile success does not prove the runtime package contains all dependencies. Required evidence is comparing compile/runtime graphs and confirming whether the corresponding nested JAR exists in BOOT-INF/lib.

---

## 6. Lab 3 — Wrong Start-Class in Manifest

### 6.1 Reproduce

In build.gradle, add an intentionally wrong configuration:

~~~groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Start-Class': 'com.example.missing.BrokenApplication'
    }
}
~~~

Build:

~~~bash
./gradlew clean bootJar
~~~

The Boot JAR can still be created because Start-Class is user-configured metadata. When running:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

the launcher attempts to load the nonexistent class. Logs may report ClassNotFoundException or failure to find the main class, depending on launcher and version.

### 6.2 Find the error in manifest and archive

Read the manifest:

~~~bash
unzip -p build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Find the application class:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'PackagingLabApplication.class'
~~~

Evidence will show:

- Start-Class points to com.example.missing.BrokenApplication.
- The archive actually contains com/example/packaging/PackagingLabApplication.class under BOOT-INF/classes.

Thus the application class was compiled and packaged; the manifest simply points to the wrong entry point.

### 6.3 Fix

Remove the wrong override or configure correctly:

~~~groovy
springBoot {
    mainClass = 'com.example.packaging.PackagingLabApplication'
}
~~~

Do not configure multiple places with different values unnecessarily. When using Kotlin, the JVM main class name may have a Kt suffix, such as ApplicationKt; inspect the actual class file generated by the compiler.

Clean build and re-verify:

~~~bash
./gradlew clean bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

### 6.4 Maven equivalent

The Spring Boot Maven plugin manages Main-Class and Start-Class during the repackage goal. If you need to change the main class, configure mainClass on the Spring Boot Maven plugin instead of editing the manifest via the plain JAR plugin.

### 6.5 Conclusion

When the application class is present in the archive yet the launcher reports not finding the main class, check Start-Class before changing source sets or adding dependencies.

---

## 7. Lab 4 — Resource Excluded from Archive

### 7.1 Reproduce

In build.gradle, add a configuration that intentionally excludes the resource:

~~~groovy
tasks.named('processResources') {
    exclude 'lab/**'
}
~~~

Rebuild:

~~~bash
./gradlew clean bootJar
~~~

Inspect:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/classes/lab/build-info.txt'
~~~

The entry is gone from the archive. The app may still start, but requests to /api/build-info will fail because ClassPathResource cannot find the file.

### 7.2 Read error and find root cause

Logs may show FileNotFoundException or an exception wrapped from opening the resource. Do not rush to add libraries; this resource belongs to the application's source set, not a dependency JAR.

Check the source file:

~~~text
src/main/resources/lab/build-info.txt
~~~

Check processResources configuration, sourceSets.main.resources, and exclude/include patterns. A broad pattern can exclude essential resources without failing compilation.

### 7.3 Fix

Remove the unnecessary exclude:

~~~groovy
tasks.named('processResources') {
    // Keep the default configuration so processResources copies src/main/resources.
}
~~~

Or narrow the exclude to the exact files that should not be packaged, avoiding excluding an entire directory.

Rebuild and verify:

~~~bash
./gradlew clean bootJar
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/classes/lab/build-info.txt'
~~~

Run the app and call the endpoint. Expected body:

~~~text
artifact=packaging-lab
~~~

### 7.4 Commonly missed resources

- application.properties or application.yml.
- Template files, schemas, SQL migrations, and static assets.
- META-INF/services/* for ServiceLoader.
- Certificates/truststores packaged by design.
- Configuration files read via the classpath.
- Resources created by a separate code-generation task not wired into processResources.

When resources are produced by code generation, declare explicit output directories and task dependencies so they appear in processed resources.

---

## 8. Lab 5 — Maven Builds a JAR but Forgets Repackage

### 8.1 BOM does not create an executable archive automatically

A project may import spring-boot-dependencies to manage dependency versions without configuring spring-boot-maven-plugin. When running:

~~~bash
./mvnw clean package
~~~

Maven still creates a regular Java JAR. The archive lacks the Boot loader and nested dependencies; java -jar may report no main manifest attribute or fail to run as an executable Boot JAR.

### 8.2 Configuring the plugin and repackage goal

If using a corporate parent and only importing the BOM, configure the plugin explicitly:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.3.13</spring-boot.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

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
            <version>3.3.13</version>
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

If the project inherits from spring-boot-starter-parent, the parent already configures the repackage execution; in that case, simply declaring the plugin typically enables it with the parent's configuration.

### 8.3 Running the right lifecycle

~~~bash
./mvnw clean package
~~~

Or if invoking the goal directly, include the package phase:

~~~bash
./mvnw package spring-boot:repackage
~~~

The repackage goal operates on the JAR/WAR created by the package phase; calling the goal alone without first producing a source archive is not the right workflow.

### 8.4 Verifying the result

~~~bash
jar tf target/orders-service-1.0.0.jar
~~~

The executable archive must have the Boot loader, BOOT-INF/classes, and BOOT-INF/lib. Inspect the manifest and run:

~~~bash
java -jar target/orders-service-1.0.0.jar
~~~

### 8.5 Conclusion

The Maven BOM manages dependency versions. The Spring Boot Maven plugin with repackage creates the executable archive. A project with a correct BOM but missing plugin execution can still output a plain JAR.

---

## 9. Lab 6 — Docker Copies the Wrong Artifact or Stale Build File

### 9.1 Broken Dockerfile caused by wildcards

Error-prone example:

~~~dockerfile
COPY --from=build /workspace/build/libs/*.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If the output directory contains both executable and plain JARs, a wildcard does not specify which file is selected. When multiple files match, Docker may refuse the copy or behave unexpectedly.

### 9.2 Copying the exact artifact

Multi-stage example:

~~~dockerfile
FROM gradle:8-jdk17 AS build
WORKDIR /workspace
COPY . .
RUN gradle clean bootJar --no-daemon

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/packaging-lab-1.0.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is a lab pattern. In real projects, the filename may depend on project name/version; a dedicated Gradle task can copy the executable artifact to a fixed path so Docker copies that exact file.

Never copy a file with the plain classifier for a standalone container.

### 9.3 Stale artifacts in the deployment directory

A pipeline may build the right JAR while a Docker stage or release step copies an artifact from an old cache folder. How to investigate:

1. Record build number, commit SHA, and version in build metadata.
2. Run clean before building release artifacts.
3. List the output directory and check timestamps.
4. Compute SHA-256 before and after copying.
5. Check the Docker build context and COPY path.
6. Record the image digest after building.
7. Promote the exact image digest that passed smoke tests.

Identical filenames do not prove identical contents. Checksums and build metadata confirm the right artifact.

### 9.4 Inspecting inside the image

After building the image, you can run a container to inspect the copied file:

~~~bash
docker run --rm --entrypoint sh packaging-lab:local -c "ls -l /app && sha256sum /app/app.jar"
~~~

Shell commands inside an image depend on the base image; minimal images may lack sh or sha256sum. If unavailable, inspect files in the build stage or use a suitable diagnostic image.

---

## 10. Reading Logs to Narrow Down Packaging Failures

### 10.1 Logs when Java cannot run the archive

| Log/message | First thing to check |
| --- | --- |
| no main manifest attribute | Running plain JAR or manifest missing Main-Class |
| ClassNotFoundException for application main class | Wrong Start-Class or class missing from archive |
| NoClassDefFoundError for library | Missing runtime dependency or classloader cannot see JAR |
| FileNotFoundException for resource | Resource not processed/packaged or wrong path name |
| UnsupportedClassVersionError | Runtime JRE is older than bytecode target |
| App starts but API returns 404 | Controller not scanned, different route, different profile/config, or stale artifact |
| App starts with wrong config | Missing application.properties/yml, wrong profile, or resource precedence |

The message is only the starting point. Cross-check against the actual archive to isolate the cause.

### 10.2 Enabling Spring Boot logs

You can run with debug mode:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar --debug
~~~

--debug prints the condition evaluation report to show which auto-configurations applied or did not apply. It does not fix missing classes, missing resources, or wrong manifests by itself.

Targeted log level increase:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar --logging.level.org.springframework=DEBUG
~~~

Do not leave DEBUG enabled across all packages in production long-term if log volume and sensitive data are not controlled.

### 10.3 Gradle build logs

When a task produces no file or the wrong file:

~~~bash
./gradlew clean bootJar --info --stacktrace
~~~

Check whether bootJar executed, whether processResources ran, whether the runtime configuration resolved dependencies, whether tasks were skipped/up-to-date due to misconfigured inputs/outputs, and what the actual output path/classifier is.

--info and --stacktrace help pinpoint build causes. They do not replace inspecting archive contents.

### 10.4 JVM class-loading logs

When suspecting a class was loaded from a different JAR/version:

~~~bash
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar
~~~

Filter one class on Linux/macOS:

~~~bash
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar 2>&1 |
  grep 'org.apache.commons.lang3.StringUtils'
~~~

PowerShell:

~~~powershell
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar 2>&1 |
    Select-String 'org.apache.commons.lang3.StringUtils'
~~~

Class-loading logs show which class was loaded and the source/location recorded by the JVM. This is helpful when duplicate JARs or classpath ordering cause runtime to load an unintended copy.

### 10.5 Protecting sensitive data in logs

Do not include passwords, tokens, secrets, private repository credentials, or full environment dumps in incident reports. When using Maven debug or Gradle diagnostics, review logs before sharing outside authorized teams.

---

## 11. Advanced Archive Errors

### 11.1 Custom JAR task omits runtime dependencies

A custom Gradle task of type Jar usually packages only source set outputs unless runtime dependencies are explicitly configured. Do not rename a regular JAR task to bootJar and assume it contains the Boot loader.

If the goal is an executable Spring Boot archive, use the BootJar task provided by the plugin. If the goal is an uber JAR in a different format, configure and test the appropriate packaging tool, including merging service descriptors and metadata.

### 11.2 Shaded/uber JAR loses service descriptors

Some libraries use Java SPI via META-INF/services files. When using a shading plugin to merge classes from multiple JARs into one archive, service descriptor files can overwrite one another instead of merging.

Symptoms include providers not being found or ServiceConfigurationError. Check:

~~~bash
jar tf app.jar | grep 'META-INF/services'
~~~

If using Shadow/Shade, configure service file transformers/mergers per plugin documentation. Spring Boot executable JARs preserve dependencies as nested JARs, so their mechanism differs from flattening all classes into an uber JAR.

### 11.3 Duplicate classes across multiple dependencies

Two artifacts with different coordinates can contain the same fully-qualified class. Dependency resolution does not always flag a conflict because their GAV coordinates differ.

Use dependencies or dependency:tree to understand the graph; jar tf on suspect JARs to locate duplicate classes; -Xlog:class+load=info to see where runtime loads the class from; and dependencyInsight to trace module version selection.

Do not conclude a clean dependency graph means zero duplicate classes.

### 11.4 Nested JARs corrupted by external tools

The Spring Boot launcher must access nested JARs in a supported archive format. If a script unzips and re-zips an executable JAR, or a signing/repack tool recompresses entries incompatibly, nested libraries may become unreadable.

For Boot executable JARs, nested JAR entries in the outer archive must be stored using ZIP STORED so the launcher can seek contents by offset. Contents inside the nested JARs themselves can still be compressed normally.

Do not run arbitrary zip/repack tools after bootJar. If signing or transforming the archive is needed, use a compatible tool and run smoke tests on the final transformed file.

### 11.5 Classpath index and differences between bootRun and java -jar

BOOT-INF/classpath.idx can specify nested JAR ordering. Spring Boot uses this index when running the archive via java -jar; it is not used when running from an IDE or via Gradle bootRun.

If identical source behaves differently between bootRun and java -jar, compare the runtime dependency graph, BOOT-INF/classpath.idx, duplicate classes/versions, JAR load order, manifest, and launcher.

Do not delete the classpath index before understanding the dependency order it describes.

### 11.6 developmentOnly is excluded from production archives by default

The Spring Boot Gradle plugin excludes dependencies in the developmentOnly configuration from the executable archive by default. This is intentional so development tools such as DevTools do not ship to production.

If an application genuinely needs a library in production, do not place it in developmentOnly by mistake. Pick the right configuration and verify nested libraries.

### 11.7 WAR and provided dependencies

An executable WAR has a different layout:

~~~text
app.war
├── META-INF/MANIFEST.MF
└── WEB-INF/
    ├── classes/
    ├── lib/
    └── lib-provided/
~~~

Dependencies needed for an embedded container yet provided when deploying to an external servlet container can be placed in WEB-INF/lib-provided depending on Spring Boot configuration. Carefully understand the difference between providedRuntime and compileOnly; the two configurations are not equivalent in all cases.

---

## 12. Investigation Process from Symptom to Root Cause

Follow this workflow when given an artifact that fails to run:

1. **Record the exact file being executed.** Capture full path, name, size, timestamp, and SHA-256.
2. **Identify the archive type.** Plain JAR, executable Boot JAR, executable WAR, or custom archive.
3. **Read the manifest.** Inspect Main-Class, Start-Class, and related attributes.
4. **List archive entries.** Check application classes, resources, Boot loader, BOOT-INF/lib, or WEB-INF/lib.
5. **Cross-check the dependency graph.** Compare compile/runtime graphs and inspect scopes/exclusions.
6. **Read the first exception.** Distinguish launcher failure, missing class, missing resource, class version, or application configuration.
7. **Enable targeted logs.** Gradle --info/--stacktrace, Spring Boot --debug, or JVM class-loading logs.
8. **Reproduce with the exact command.** Match Java version, artifact, environment, and launch command used in deployment.
9. **Fix the smallest root cause.** Adjust task, scope, mainClass, resource includes, or pipeline path based on evidence.
10. **Clean build and verify the final file.** Re-run smoke tests on the artifact/container after any copy, signing, or repacking step.

~~~text
java -jar fails
      |
      v
Read first error + manifest
      |
      +-- no Main-Class / wrong launcher --> wrong archive or manifest
      |
      +-- wrong Start-Class -------------> mainClass configuration
      |
      +-- NoClassDefFoundError ----------> runtime dependency / nested JAR
      |
      +-- FileNotFoundException ---------> resource processing / archive entry
      |
      +-- UnsupportedClassVersionError --> JDK runtime vs bytecode target
      |
      +-- app starts, wrong behavior ----> config/profile/stale artifact
      |
      v
Inspect archive + resolved graph + exact deployed file
      |
      v
Fix, clean build, verify final artifact
~~~

---

## 13. Symptom and Evidence Matrix

| Symptom | Evidence in archive/log | Common cause | Fix |
| --- | --- | --- | --- |
| no main manifest attribute | Manifest missing entry point | Plain JAR or repackage not run | Pick bootJar or configure Maven repackage |
| Boot launcher cannot find app class | Start-Class does not match entry class | Wrong mainClass/manifest | Configure correct FQCN |
| NoClassDefFoundError | Dependency missing from BOOT-INF/lib | compileOnly, provided, or exclusion | Fix runtime scope |
| FileNotFoundException | Resource missing from BOOT-INF/classes | Wrong processResources exclude/sourceSet | Fix resource processing |
| App starts but endpoint returns 404 | Controller/class or route missing from artifact | Source set, component scan, stale JAR | Check class, package scan, and checksum |
| App works locally, fails in container | Archive or JRE in image differs from local | Wrong file copied, different base image | Compare hashes, inspect image and launch command |
| ServiceConfigurationError | META-INF/services missing provider | Shading overwrote service descriptor | Merge service files |
| Unexpected class/version | Class-load log points to unexpected JAR | Duplicate class or classpath ordering | Remove duplicate and align dependencies |
| Nested JAR cannot open | Archive was repacked/recompressed | Incompatible ZIP entry method | Rebuild with Boot plugin and avoid arbitrary repacking |
| UnsupportedClassVersionError | Class file version higher than JRE | Built with newer JDK, run on older JRE | Align Java toolchain and runtime |
| WAR missing embedded server | Wrong WEB-INF/lib-provided or provided scope | Misconfigured WAR/container setup | Choose proper providedRuntime/deployment model |

---

## 14. Pre-Release Artifact Verification Checklist

### 14.1 Build

- [ ] Using reviewed Gradle/Maven Wrapper.
- [ ] Built from clean source state.
- [ ] Unit/integration tests pass.
- [ ] Right task producing executable archive ran.
- [ ] No custom task unexpectedly overwrote the output archive.

### 14.2 Archive

- [ ] Clearly distinguished plain vs. executable archive.
- [ ] Manifest has right launcher and Start-Class.
- [ ] Application classes reside in BOOT-INF/classes or WEB-INF/classes appropriately.
- [ ] Runtime dependencies present in BOOT-INF/lib or WEB-INF/lib.
- [ ] Important resources present in the archive.
- [ ] Service descriptors and metadata intact.
- [ ] Archive not corrupted by external tools after build.

### 14.3 Runtime

- [ ] Ran the right file via java -jar.
- [ ] Used the right Java runtime version.
- [ ] Smoke-test endpoints/health checks succeed.
- [ ] Verified config/profiles and resource loading.
- [ ] Did not rely solely on bootRun or IDE run configurations.

### 14.4 Release pipeline

- [ ] Docker copies exact artifact path without ambiguous wildcards.
- [ ] SHA-256 compared before/after copying when needed.
- [ ] Container smoke test ran on final image.
- [ ] Image digest recorded.
- [ ] Promoted the exact tested image.
- [ ] Release log records commit, version, artifact, and checksum.

---

## 15. Integrated Practice Lab

### A. Plain JAR and executable JAR

1. Run ./gradlew clean bootJar jar.
2. List files in build/libs.
3. Run the plain JAR with java -jar and record the error.
4. Run the executable Boot JAR.
5. Compare manifests and entry layouts.
6. Explain why plain JAR remains useful when publishing libraries.

### B. Missing runtime dependency

1. Change Commons Lang from implementation to compileOnly.
2. Run clean bootJar.
3. Confirm Commons Lang is missing from BOOT-INF/lib.
4. Start the app and call the greeting endpoint.
5. Record the first exception and missing class.
6. Compare compileClasspath with runtimeClasspath.
7. Change back to implementation, rebuild, and confirm the endpoint succeeds.

### C. Wrong main class

1. Override Start-Class to a nonexistent class.
2. Build the executable JAR.
3. Read the manifest.
4. Locate the real application class in the archive.
5. Fix mainClass/Start-Class.
6. Rebuild and run java -jar.

### D. Excluded resource

1. Add exclude lab/** to processResources.
2. Build the JAR.
3. Check the resource entry.
4. Call /api/build-info.
5. Inspect the stack trace and locate the root cause.
6. Remove the exclude, rebuild, and confirm the response body.

### E. Maven repackage

1. Create a Maven project using BOM import alone.
2. Build the JAR without plugin execution.
3. Inspect the archive and test java -jar.
4. Add spring-boot-maven-plugin with the repackage goal.
5. Run clean package.
6. Inspect Boot loader, BOOT-INF, and manifest.
7. Explain the difference when using starter parent.

### F. Docker artifact selection

1. Build both plain and Boot JARs.
2. Write a Dockerfile intentionally using a wildcard.
3. Identify which file was copied and check its hash.
4. Fix the Dockerfile to copy the exact executable artifact.
5. Build the image and run container smoke tests.
6. Record the image digest and artifact checksum.

### G. Incident report

Use template:

~~~text
Project:
Commit/build number:
JDK build:
JDK runtime:
Gradle/Maven version:
Packaging task:
Expected artifact:
Actual artifact path:
Artifact size:
SHA-256:
Archive type:
Main-Class:
Start-Class:
Application class entry:
Required resource entries:
Runtime dependency entries:
Launch command:
First exception/message:
Relevant build log:
Root cause:
Code/build/pipeline change:
Clean build result:
java -jar result:
Container smoke-test result:
Image digest:
Remaining issue:
~~~

Distinguish hypotheses from evidence. Do not mark "fixed" solely because the build task passes; run the actual final artifact and verify expected behavior.

---

## 16. Official References

- Spring Boot 3.3.13 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot 3.3 — Developing Your First Application, Creating an Executable JAR: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot — Nested JARs and archive layout: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — Efficient Deployments and extracting executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot — Maven Plugin, Packaging Executable Archives and repackage: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Gradle — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Oracle JDK 17 — jar command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle JDK 17 — java launcher and options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Docker — Dockerfile COPY reference: https://docs.docker.com/reference/dockerfile/#copy

**Remember:** Successful packaging is not just having a JAR file. Identify the right archive type, read the manifest, verify application classes/resources and runtime dependencies inside, and run the right file with the right Java command. When errors occur, combine stack traces with jar tf, dependency graphs, class-loading logs, and checksums to pinpoint the root cause before making fixes.