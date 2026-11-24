# Creating an Executable JAR and Verifying Execution on a JRE-Only Machine

## 1. Objective and Boundary Between Build Machine and Runtime Machine

A Spring Boot application can be packaged into an **executable JAR** for deployment on a machine that only has a Java Runtime Environment (JRE) or an equivalent runtime image installed. The machine running the application does not need source code, Maven, Gradle, or a Java compiler. It needs a compatible Java runtime, the executable JAR file, and any external resources the application actually uses.

Distinguish the two machines:

| Machine | Required components | Responsibilities |
|---|---|---|
| **Build machine** | Compatible JDK, Maven or Gradle, source code, and dependency repositories | Compile, run tests, package executable JAR, inspect manifest and archive |
| **Runtime machine** | Compatible JRE/Java runtime, executable JAR, required configuration and connections | Run application with java -jar, monitor logs, and verify endpoints |

**An executable JAR does not mean a JAR containing the JVM itself.** Spring Boot packages application classes, the Spring Boot Loader, and required Java dependencies into the archive. The JVM/JRE is still provided by the target machine. Therefore, a JAR running on a JDK on a development laptop is not sufficient proof that it runs on the target machine's runtime; you must verify the exact Java version and deployment operating system.

In this lab, we use Java 17 and Spring Boot 3.5.16. According to Spring Boot 3.5.16 system requirements, Java 17 is the minimum; Maven requires 3.6.3 or later, and Gradle requires 7.6.4 or later in the 7.x branch or 8.4 or later in the 8.x branch. Check the requirements of the exact Spring Boot release your project uses: [Spring Boot 3.5.16 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).

## 2. How Do JDK, JRE, and Executable JAR Differ?

### 2.1. JDK and JRE

- **JDK (Java Development Kit)** includes the javac compiler, jar packaging tool, javadoc, jdeps, jcmd, jstack, and the runtime to execute Java.
- **JRE/runtime image** provides the JVM and the Java modules required to run applications. It does not necessarily include the compiler or development tools.
- **Executable Spring Boot JAR** contains the packaged application, loader, and application libraries. It does not bundle the JRE.

Some Java vendors now distribute runtimes as runtime-only packages or custom runtime images rather than a separate installer named JRE. In this guide, "JRE-only machine" means a machine with a compatible Java runtime but without the JDK development toolkit.

### 2.2. What is inside an executable JAR?

A Spring Boot executable JAR typically has this structure:

```text
runtime-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/runtimejardemo/...
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        ├── spring-web-*.jar
        └── ... other runtime dependencies
```

| Component | Present in executable JAR? | Source |
|---|---|---|
| Application classes/resources | Yes | Project build output |
| Spring Boot Loader | Yes | Spring Boot packaging plugin |
| Packaged Java runtime dependencies | Yes, if on the packaging classpath | Maven/Gradle dependency configuration |
| JVM/JRE | No | Runtime machine |
| OS packages, operating system native libraries | Not included by default | Runtime machine or deployment environment |
| Database, message broker, external config files | Not included by default | External infrastructure |

BOOT-INF/classes/ holds application classes and resources; BOOT-INF/lib/ holds nested dependency JARs. The Spring Boot Loader reads this structure at startup. Official documentation: [Spring Boot Executable JAR](https://docs.spring.io/spring-boot/specification/executable-jar/index.html).

**Consequence:** there is no need to copy individual dependency JARs to the runtime machine if they are properly packaged inside the executable JAR. However, dependencies excluded from runtime packaging, dependencies with provided scope, native libraries, or external configuration files still must be handled separately.

## 3. Choosing the Right Java Runtime for the Target Machine

### 3.1. Matching the Java feature version

If an application is built with Java 17, the most predictable option is running it on a Java 17 runtime. A newer Java runtime can run older bytecode in most cases, though you still need to verify APIs, dependencies, and actual behavior.

Example error when a class is compiled for Java 21 while the machine only has Java 17:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime
only recognizes class file versions up to 61.0
```

Common class file major versions:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

If the runtime reports major version 65 while only supporting up to 61, the application or a dependency was built with Java 21 while the runtime is only Java 17. Upgrade the JRE to a compatible version or build the entire application and dependencies against the baseline supported by the runtime.

### 3.2. Using compiler release to pin the baseline

With Maven, the Spring Boot parent lets you set:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

With standalone Maven Compiler Plugin, you can configure maven.compiler.release as 17. The release option restricts language features, bytecode, and Java platform APIs that source code is allowed to use according to the chosen release.

With Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

The toolchain helps the build select the exact JDK compiler. However, compiler configuration does not downgrade bytecode of third-party dependencies. Confirm that all runtime libraries support Java 17.

**Recommendation:** if production only has a Java 17 runtime, build and test with JDK 17, then test-run that exact artifact on a runtime-only Java 17 matching the target OS/architecture.

### 3.3. Checking the runtime on the target machine

Linux/macOS:

```bash
java -version
java -XshowSettings:properties -version 2>&1 |
  grep -E 'java.version|java.home|os.arch'
```

Windows PowerShell:

```powershell
java -version
java -XshowSettings:properties -version 2>&1 |
  Select-String 'java.version|java.home|os.arch'
```

Check these details:

- java.version: feature/patch version currently running.
- java.vendor: runtime vendor.
- java.home: runtime directory currently in use.
- os.arch: CPU architecture recognized by the JVM.

Runtimes from multiple vendors can be used, but production should standardize vendor, patch level, OS, and architecture for easier issue reproduction.

## 4. Creating a Spring Boot Executable JAR with Maven

### 4.1. Project structure

We create a small web application with an endpoint /runtime-check. When running successfully on a JRE-only machine, the endpoint returns a fixed string for smoke testing.

```text
runtime-jar-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/runtimejardemo/
    │   ├── RuntimeJarDemoApplication.java
    │   └── RuntimeCheckController.java
    └── test/java/com/example/runtimejardemo/
        └── RuntimeCheckControllerTest.java
```

### 4.2. POM

File pom.xml:

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
    <artifactId>runtime-jar-demo</artifactId>
    <version>1.0.0</version>
    <name>Runtime JAR Demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Because the project uses spring-boot-starter-parent, the Spring Boot Maven Plugin already has its repackage execution configured by the parent. This goal runs in the package phase, converting the archive created by Maven into an executable Boot JAR. If not using the parent, declare an appropriate repackage execution in the plugin. See [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html).

### 4.3. Main class

File src/main/java/com/example/runtimejardemo/RuntimeJarDemoApplication.java:

```java
package com.example.runtimejardemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeJarDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeJarDemoApplication.class, args);
    }
}
```

### 4.4. Controller

File src/main/java/com/example/runtimejardemo/RuntimeCheckController.java:

```java
package com.example.runtimejardemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeCheckController {

    @GetMapping("/runtime-check")
    public String runtimeCheck() {
        return "runtime-jar-demo: OK";
    }
}
```

The endpoint returns a fixed string for smoke testing. The actual Java version must still be confirmed separately with java -version on the target machine.

### 4.5. Integration test

File src/test/java/com/example/runtimejardemo/RuntimeCheckControllerTest.java:

```java
package com.example.runtimejardemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RuntimeCheckControllerTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void runtimeCheckEndpointReturnsOk() {
        String response = http.getForObject(
            "/runtime-check",
            String.class
        );

        assertThat(response).isEqualTo("runtime-jar-demo: OK");
    }
}
```

The test boots Spring Boot on a random port and sends an HTTP request to the controller. It confirms the application context and endpoint work in the build machine's test environment; the step to run on a JRE-only machine in the next section still needs to be executed separately.

### 4.6. Building the executable JAR

On a build machine with JDK 17 and Maven:

```bash
java -version
mvn -version
mvn clean verify
```

After a successful build, the main artifact is:

```text
target/runtime-jar-demo-1.0.0.jar
```

mvn verify runs preceding phases, including compile, test, and package, then runs checks bound to verify. If tests fail, do not release the artifact from that build.

## 5. Inspecting the JAR Before Transferring to the Target Machine

### 5.1. Confirming the archive has executable structure

On a build machine with a JDK:

```bash
jar tf target/runtime-jar-demo-1.0.0.jar |
  grep -E '^(META-INF/MANIFEST.MF|org/springframework/boot/loader/|BOOT-INF/classes/|BOOT-INF/lib/)'
```

An executable Boot JAR needs a manifest, the Boot Loader, application classes in BOOT-INF/classes/, and dependency JARs in BOOT-INF/lib/.

If you only see the application's package classes without the Boot Loader/nested dependencies, you may be viewing a plain JAR or the repackage plugin did not run.

### 5.2. Inspecting the manifest

Linux/macOS if unzip is available:

```bash
unzip -p target/runtime-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Or extract the manifest using the JDK:

```bash
mkdir -p target/manifest-check
cd target/manifest-check
jar xf ../runtime-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

A Spring Boot executable manifest typically contains:

- Main-Class: launcher class of Spring Boot Loader.
- Start-Class: main class of the application.
- Classpath/index attributes if configured for the archive.

Cross-check Start-Class against RuntimeJarDemoApplication. Main-Class usually points to the Boot Loader, not necessarily the application's main class.

### 5.3. Distinguishing executable JAR from plain JAR

| Indicator | Executable Boot JAR | Plain JAR |
|---|---|---|
| Boot Loader | Yes | Usually no |
| Application classes | BOOT-INF/classes/ | Usually at root package path |
| Dependency JARs | BOOT-INF/lib/ | Does not automatically bundle dependencies in Boot layout |
| Manifest launcher | Configured to run with java -jar | May lack an appropriate Main-Class |
| How to run | java -jar app.jar | Depends on manifest/classpath and packaging setup |

Do not pick an artifact based solely on filename or size. Inspect the manifest and archive layout.

### 5.4. Checking the checksum before transferring the file

Linux/macOS:

```bash
sha256sum target/runtime-jar-demo-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash ./target/runtime-jar-demo-1.0.0.jar -Algorithm SHA256
```

Record the SHA-256 alongside the build ID/commit. After copying to the runtime machine, recompute the hash and compare. If they differ, check the upload/download process, truncated files, or whether the wrong artifact was copied.

## 6. Transferring the Artifact to a JRE-Only Machine

Only transfer the verified executable JAR along with any external configuration files the application needs. There is no need to transfer source code, Maven repository folders, Gradle caches, the compiler, or the entire build directory.

Linux example:

```bash
sudo mkdir -p /opt/runtime-jar-demo
sudo cp target/runtime-jar-demo-1.0.0.jar /opt/runtime-jar-demo/app.jar
sudo chown -R appuser:appuser /opt/runtime-jar-demo
```

Windows PowerShell example:

```powershell
New-Item -ItemType Directory -Force ./runtime-jar-demo
Copy-Item ./target/runtime-jar-demo-1.0.0.jar ./runtime-jar-demo/app.jar
```

Names and paths are examples only. Use deployment directories according to the target machine's policy; the account running the application needs read permission on the JAR and appropriate permissions for log/data directories.

### 6.1. The runtime machine does not need JDK tools

The target machine only needs the java command. The following tools belong to the JDK and may not exist:

- javac: compiles source code.
- jar: lists/extracts archives.
- javap: reads bytecode/class metadata.
- jdeps: analyzes dependencies/modules.
- javadoc: generates API documentation.

If javac or jar is not found on the target machine, that is not an error for running an executable JAR. Perform archive inspection on the build machine; the runtime machine only needs to run the application with java -jar.

### 6.2. Verifying the right Java runtime after copying

Linux/macOS:

```bash
java -version
sha256sum /opt/runtime-jar-demo/app.jar
```

Windows PowerShell:

```powershell
java -version
Get-FileHash ./runtime-jar-demo/app.jar -Algorithm SHA256
```

Compare the checksum with the build machine. If the runtime machine has multiple Java installations, verify which java is resolved on PATH; on Windows use Get-Command java, on Linux/macOS use command -v java.

## 7. Running the Application with JRE

### 7.1. Running in foreground to observe startup logs

Linux/macOS:

```bash
cd /opt/runtime-jar-demo
java -jar app.jar --server.port=8080
```

Windows PowerShell:

```powershell
java -jar ./runtime-jar-demo/app.jar --server.port=8080
```

Spring Boot starts the embedded web server and writes logs to the console. Keep the terminal open on the first check to watch for startup failures, port binding, configuration, and server status.

With a Java 17 runtime, the sample application should run without requiring javac, Maven, or Gradle.

### 7.2. Testing the endpoint

Open another terminal on the target machine.

Linux/macOS:

```bash
curl -fsS http://127.0.0.1:8080/runtime-check
```

Windows PowerShell:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/runtime-check).Content
```

Exact HTTP body:

```text
runtime-jar-demo: OK
```

If the endpoint returns this content, the request reached the application running on the runtime machine. Combine this with java -version and the checksum to confirm the right runtime and right artifact.

### 7.3. Passing JVM options and Spring Boot arguments

JVM options must precede -jar; application arguments follow the JAR name.

```bash
java -Xms256m -Xmx512m -Dspring.profiles.active=prod \
  -jar app.jar --server.port=8080
```

- -Xms256m: initial heap.
- -Xmx512m: maximum heap limit.
- -Dspring.profiles.active=prod: JVM system property.
- --server.port=8080: Spring Boot command-line property.

Heap values are examples only; choose based on machine memory limits, containers, and actual load. Never set -Xmx higher than the environment's available memory.

### 7.4. External configuration outside the JAR

An executable JAR can contain default application.properties or application.yml. For deployment environments, machine-specific settings such as profile, port, database URL, and secrets should be passed via environment variables, a secret manager, or external configuration files.

Example:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

An external config directory can be added:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/runtime-jar-demo/
```

Ensure configuration files exist with proper permissions, and do not package secrets inside the JAR or print secrets in logs.

## 8. Verifying in a Runtime-Only Environment

### 8.1. Testing on the right kind of machine

A run using the JDK on a laptop only proves the application runs with the runtime bundled with that JDK. To verify the "JRE-only" requirement, run the artifact on:

- A machine/VM with the corresponding runtime-only package installed.
- Or a runtime-only container image with the same Java feature version and architecture.
- Or a staging environment configured like the production runtime.

Do not install Maven/Gradle/JDK onto a runtime-only host just to test-run a JAR. Verify java -version, run java -jar, and test the endpoint.

### 8.2. A runtime-only container is a repeatable test option

If the organization uses Docker, you can run the JAR on an image that only provides a Java runtime. Illustrative example using an organization-approved Java 17 runtime-only image:

```bash
docker run --rm --name runtime-jar-check \
  -p 8080:8080 \
  -v "$PWD/target/runtime-jar-demo-1.0.0.jar:/app/app.jar:ro" \
  eclipse-temurin:17-jre \
  java -jar /app/app.jar --server.port=8080
```

Then test the endpoint from the host machine:

```bash
curl -fsS http://127.0.0.1:8080/runtime-check
```

Select the exact image tag, digest, OS, and architecture per organizational policy; the tag in the example only illustrates how to test. A runtime-only container test reproduces a clean runtime, but does not replace testing on the real OS/host if the application uses native libraries, mounts, certificate stores, or host-specific integrations.

### 8.3. Checking whether the application depends on external resources

An executable JAR does not package the following services and resources:

- External databases, Redis, Kafka, message brokers, or HTTP services.
- Host-mounted upload/data directories.
- Certificates, truststores/keystores, and secrets.
- Operating system native libraries or executables.
- Fonts, locale data, or external configuration files if needed by the application.

Identify these dependencies in the deployment checklist. If the application starts up but business endpoints fail because the database is unavailable, that is a runtime configuration/connectivity issue, not necessarily a JAR packaging error.

## 9. Common Errors When Running on a JRE-Only Machine

| Symptom | Common cause | Fix |
|---|---|---|
| java: command not found or java is not recognized | Runtime not installed or PATH does not point to runtime | Install compatible runtime, check PATH and JAVA_HOME |
| UnsupportedClassVersionError | JRE is older than bytecode of app or dependency | Use compatible JRE or build for a lower Java baseline |
| no main manifest attribute | Plain JAR or executable repackage did not run | Rebuild with Spring Boot plugin, inspect manifest |
| Invalid or corrupt jarfile | File truncated during copy, corrupted, or wrong file | Compare SHA-256, re-copy artifact |
| ClassNotFoundException | Missing class/dependency on runtime classpath | Verify correct executable JAR and nested libraries |
| NoClassDefFoundError | Runtime dependency excluded, provided scope, or exclusion | Check dependency graph and BOOT-INF/lib |
| Address already in use | Another process already occupies the port | Choose another port or free the port |
| Connection refused to database/API | Service not running or wrong endpoint/firewall | Check URL, DNS, network, credentials, and service health |
| UnsatisfiedLinkError | Native library missing or wrong OS/architecture | Install matching native library and check architecture |
| Permission denied | App user cannot read JAR or write to required directory | Fix owner/permissions with minimal scope |
| App starts then exits | Error in config, profile, context, or runtime dependency | Read the first exception in the startup log |
| Works on laptop but fails on server | Different Java vendor/version, OS, architecture, env, or config | Compare runtime properties, checksum, and deployment config |

### 9.1. Analyzing UnsupportedClassVersionError

This is the most critical error when deploying to an older runtime.

For example, Java 21 class files have major version 65; a Java 17 runtime only understands up to major version 61. There are two ways to resolve this:

1. Upgrade the runtime machine to Java 21 if supported by the Spring Boot release and policy.
2. Keep the Java 17 runtime, build the application with release 17, and use dependencies with Java 17-compatible bytecode/APIs.

Do not check only the application's own classes. A single dependency newly upgraded to Java 21 can trigger this error even if application classes were compiled with Java 17.

### 9.2. Analyzing no main manifest attribute

If running the JAR returns no main manifest attribute, you are usually running a plain JAR or an artifact that was not repackaged by Spring Boot.

With Maven, confirm the Spring Boot Maven Plugin is declared and the repackage goal runs during package. For projects using spring-boot-starter-parent, the execution is usually preconfigured.

With Gradle, select the artifact produced by the bootJar task rather than the jar task that produces the plain archive. Verify the exact filename in target/ or build/libs/.

### 9.3. Analyzing missing dependencies

A normal executable Boot JAR contains runtime dependencies inside BOOT-INF/lib/. If a class is missing:

1. Identify which class causes ClassNotFoundException or NoClassDefFoundError.
2. Inspect the dependency graph using Maven dependency:tree or Gradle dependencies.
3. Check scopes/exclusions and packaging configuration.
4. Inspect nested JARs inside the executable archive on the build machine.
5. Rebuild and verify the new artifact.

Do not solve this by randomly copying JARs onto the target machine. Doing so easily creates version conflicts and makes the artifact non-reproducible.

## 10. Maven and Gradle: Equivalent Build Commands

### 10.1. Maven

| Goal | Command |
|---|---|
| Check environment | java -version, mvn -version |
| Run tests and package | mvn clean verify |
| Package only | mvn clean package |
| View runtime dependencies | mvn dependency:tree -Dscope=runtime |
| Inspect repackage plugin | mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 -Dgoal=repackage -Ddetail |

If not using the Spring Boot parent, declare the repackage execution:

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

The repackage goal operates on the JAR/WAR created in the package phase; do not invoke this goal alone on a project that has not yet built the source archive. You can invoke:

```bash
mvn package spring-boot:repackage
```

### 10.2. Gradle

Groovy DSL example in build.gradle:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Build and inspect:

```bash
./gradlew clean test bootJar
./gradlew tasks --all
```

The executable JAR is created by the bootJar task, typically located in build/libs/. The Spring Boot Gradle Plugin automatically creates this task when the Java plugin is applied; assemble and build are configured to depend on bootJar. See [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html).

If the project produces both a plain JAR and an executable Boot JAR, choose the output of bootJar. Do not take the file with the plain classifier to run as an executable archive.

## 11. Checklist for Releasing a JAR for a JRE-Only Machine

### 11.1. On the build machine

- [ ] Confirmed JDK/toolchain matches target Java baseline.
- [ ] Pinned Spring Boot plugin/dependency versions.
- [ ] Ran mvn clean verify or ./gradlew clean test bootJar.
- [ ] Confirmed tests pass.
- [ ] Built the correct executable JAR.
- [ ] Inspected manifest and main class.
- [ ] Inspected Boot Loader and nested dependencies.
- [ ] Verified runtime dependencies were not unintentionally excluded.
- [ ] Computed SHA-256 and saved alongside build ID/commit.
- [ ] Test-ran the artifact on a matching runtime-only environment.

### 11.2. On the runtime machine

- [ ] Installed Java runtime matching feature version, vendor policy, and architecture.
- [ ] java -version displays the expected runtime.
- [ ] JAR SHA-256 matches the release artifact.
- [ ] Copied the correct executable JAR, not the plain JAR.
- [ ] Granted file read permissions and needed directory permissions to service user.
- [ ] Configured port, profile, environment variables, secrets, and external config.
- [ ] java -jar app.jar starts up successfully.
- [ ] Smoke-test endpoint returns expected content.
- [ ] External database/API/native dependencies checked.
- [ ] Logs and service restart/stop procedures defined.

### 11.3. Evidence to archive per release

```text
release/
├── runtime-jar-demo-1.0.0.jar
├── runtime-jar-demo-1.0.0.sha256
├── build-info.txt
├── runtime-version.txt
└── deployment-config-example/
```

build-info.txt should record the commit SHA, build command, JDK version, Maven/Gradle Wrapper version, and Spring Boot version. runtime-version.txt records the Java vendor, feature version, OS, and architecture used for verification.

Do not store secrets or credentials in release evidence. If sample configs need to be saved, keep only non-sensitive values and document where secrets are supplied during deployment.

## 12. Conclusion

To run Spring Boot on a machine with only a compatible JRE, build the executable JAR using the JDK on the build machine, package application classes together with runtime dependencies and the Spring Boot Loader into the archive, then transfer the correct JAR to the runtime machine. The target machine only needs a compatible Java runtime and the external resources the application uses; it does not need Maven, Gradle, source code, or a compiler.

Verification requires three pieces of evidence: **a properly structured executable JAR**, **a compatible runtime version**, and **the application actually starting and serving requests in a runtime-only environment**. Check the manifest/BOOT-INF on the build machine, compare checksums after transferring the file, run java -jar on the JRE-only host, and smoke-test the endpoint. This approach validates both the artifact and the deployment environment.

### Official Documentation

- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot — Executable JAR](https://docs.spring.io/spring-boot/specification/executable-jar/index.html)
- [Spring Boot Maven Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Building Applications](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Oracle Java — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle Java — JDK Tools and Utilities](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html)
