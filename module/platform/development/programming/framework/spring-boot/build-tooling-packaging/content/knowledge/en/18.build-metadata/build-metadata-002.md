# Generating META-INF/build-info.properties with Maven spring-boot:build-info

## 1. What problem does build metadata solve?

When a Spring Boot application is released to a server, container, or Kubernetes, the file actually running may differ from the source code a developer has open in their IDE. For example, a service might return HTTP 500, and the on-call engineer does not yet know whether it is a `0.0.1-SNAPSHOT` artifact or a release, which module it was built from, or when it was packaged. **Build metadata** embeds identifying information about the Maven project into the artifact itself.

The Spring Boot Maven Plugin provides the goal:

```bash
./mvnw spring-boot:build-info
```

The `build-info` goal generates a resource with the standard name:

```text
META-INF/build-info.properties
```

By default, Maven places that resource at:

```text
target/classes/META-INF/build-info.properties
```

When the Spring Boot application is packaged as an executable JAR using `spring-boot:repackage`, this resource typically resides at:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

The path **on the Maven filesystem** and the **path inside the Boot JAR** differ because the Boot Loader places application classes/resources under `BOOT-INF/classes`. At runtime, the logical classpath path remains `META-INF/build-info.properties`.

**Key takeaway:** Goal `spring-boot:build-info` *generates metadata*, while `spring-boot:repackage` *packages the application*. The two goals serve different roles, can be configured together in the same plugin, and do not replace each other.

### Lesson objectives

After this lesson, you will:

- Configure `spring-boot-maven-plugin` to invoke the `build-info` goal on every build.
- Understand the standard keys `build.group`, `build.artifact`, `build.name`, `build.version`, and `build.time`.
- Add custom metadata using `additionalProperties` without confusing it with `application.properties`.
- Know when the file appears in `target/classes` and how to verify it inside the executable JAR.
- Read metadata from Java/Spring Boot via `BuildProperties` or `ClassLoader#getResourceAsStream`.
- Expose build info at Actuator `/actuator/info` **when the dependency is present and endpoint exposure is enabled**.
- Handle `time` to balance build information accuracy against reproducible artifact requirements.
- Distinguish build metadata, Git metadata, and runtime information; avoid embedding secrets.

## 2. Commonly confused concepts and files

| Name | Created or managed by | Purpose |
|---|---|---|
| `pom.xml` | Developer/Maven model | Declares project, dependencies, plugins, profiles, `groupId:artifactId:version` coordinates |
| `spring-boot-dependencies` BOM | Maven `dependencyManagement` | Manages dependency versions, not metadata for a specific build |
| `META-INF/build-info.properties` | `spring-boot:build-info` | Build information embedded into the artifact |
| `application.properties`/`application.yaml` | Spring Boot configuration | Runtime configuration: HTTP port, profiles, datasource, features... |
| `git.properties` | Git Commit Id Plugin or equivalent tool | Commit, branch, commit time, and SCM metadata if configured |
| `META-INF/MANIFEST.MF` | Maven JAR Plugin/Spring Boot Repackage | Main class, launcher, select manifest entries; not equivalent to build-info |
| `BOOT-INF/classpath.idx` | Boot packaging plugin where applicable | Nested JAR order used by Boot Loader; contains no release info |
| `META-INF/sbom/...` (when present) | SBOM generation tool | Software components/dependencies; does not replace `build-info.properties` |

`build-info.properties` is a **Java properties resource**, not a JSON file and not YAML. Spring Boot provides an API to read it into `BuildProperties` when the resource is on the classpath.

An artifact can carry `build-info.properties`, `git.properties`, and a manifest simultaneously; each answers a different question:

- **Build info:** which artifact and version was the app packaged as, and when?
- **Git info:** which source revision was used (when the Git plugin is configured)?
- **Manifest:** which class does the Java launcher run?
- **Actuator info:** which build/git/runtime details are **allowed to be exposed via the endpoint**?

**Do not treat `build-info.properties` as a trusted certificate of origin.** Anyone who can modify the artifact can alter the contents of that file; supply-chain trust also depends on signing, checksums, provenance, and CI/CD controls.

## 3. How spring-boot:build-info works in Maven

The Spring Boot Maven Plugin reads the effective **MavenProject** (after parent inheritance, profiles, and property interpolation) and generates metadata from the module's coordinates/name/time. This goal can be invoked **directly** or **bound to the lifecycle** via `<executions>`.

### 3.1. Invoking the goal manually

```bash
# Run the build-info goal on the Maven module in the current directory.
./mvnw spring-boot:build-info
```

If Maven Wrapper is absent on the machine but Maven is on `PATH`:

```bash
mvn spring-boot:build-info
```

This command **is not equivalent to `package` or `repackage`**. It may generate `target/classes/META-INF/build-info.properties`, but it **does not automatically update a JAR packaged in a previous build**. To include the resource in a new artifact, run a lifecycle with the `package` phase and the corresponding goal configured.

### 3.2. Binding the goal to the build lifecycle

Add an execution for the `build-info` goal:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>generate-build-info</id>
                    <goals>
                        <goal>build-info</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

This is a **configuration snippet to insert into `pom.xml`**, not a complete POM. The plugin binds `build-info` to the resource-generation phase of the lifecycle; therefore, when running `mvn package`, it generates the resource **before the JAR is packaged**. The Maven Spring Boot Starter Parent also manages version/plugin executions for `repackage` when you declare the plugin as shown in the complete example below.

### 3.3. Standard keys

A typical file contains:

```properties
build.artifact=build-info-lab
build.group=com.example
build.name=Build Info Lab
build.version=0.0.1-SNAPSHOT
build.time=2025-01-01T00:00:00Z
```

This is **illustrative content with fixed values from the Section 5 example**, not identical output across all projects. Real files may order lines differently, contain Java properties escaping, and include custom keys.

| Key in file | Default source | Meaning |
|---|---|---|
| `build.group` | `project.groupId` | Maven group coordinate |
| `build.artifact` | `project.artifactId` | Module artifact ID |
| `build.name` | `project.name` | Project display name |
| `build.version` | `project.version` | Artifact version |
| `build.time` | `project.build.outputTimestamp` or Maven session start time when no timestamp is set | Build timestamp in a format parseable by `Instant.parse` |
| `build.<custom-key>` | Plugin `additionalProperties` | Project-defined metadata |

Important details:

1. `build.version` is the **project version**, not the JDK or Spring Boot version.
2. `build.artifact` is the **artifactId**, not the JAR file path.
3. `build.time` reflects the timestamp policy configured at build time. If you intentionally pin `project.build.outputTimestamp`, it does **not** mean the production deployment time.
4. `build.name` may contain spaces; Java properties stores it as a string value.
5. Keys have the `build.` prefix in the file; when read through `BuildProperties`, the standard API uses `getGroup()`, `getVersion()`, etc., and `get("team")` for custom keys **without the prefix**.

### 3.4. The file is a runtime input, not a place to edit runtime config

Once the plugin generates metadata, the application uses it to log "which build is running" or display a release identifier. Never put passwords, API tokens, private keys, connection strings, or confidential CI details in `additionalProperties`. The resource is packaged into the artifact and can be read by anyone with the JAR file, even when the Actuator endpoint is not public.

## 4. Official configuration parameters of the build-info goal

In Spring Boot Maven Plugin 3.5, the most useful parameters are:

| Parameter | Type | Effect |
|---|---|---|
| `additionalProperties` | `Map` | Adds custom metadata keys; the plugin automatically prepends `build.` |
| `excludeInfoProperties` | `List` | Excludes one or more standard or custom keys from the output file |
| `outputFile` | `File` | Changes the generated file path; default `${project.build.outputDirectory}/META-INF/build-info.properties` |
| `skip` | `boolean` | Skips executing the goal; default `false` |
| `time` | `String` | Controls `build.time`; must be parseable by Java `Instant.parse`, or use `off` to omit it |

### 4.1. additionalProperties

Example:

```xml
<additionalProperties>
    <team>platform</team>
    <release.channel>demo</release.channel>
    <java.version>${java.version}</java.version>
</additionalProperties>
```

If the POM has `<java.version>17</java.version>`, the added keys will be:

```properties
build.team=platform
build.release.channel=demo
build.java.version=17
```

For custom keys, do not write the `build.` prefix again inside `additionalProperties` unless you intentionally want the generated key to have an extra prefix; the normal approach is `<team>`, not `<build.team>`.

Values like `${java.version}` are **Maven property interpolation**; Maven interpolates them from the active model. If values come from environment variables, verify availability and ensure no secrets are leaked accidentally. Release metadata should come from controlled CI variables rather than ad hoc developer machine settings.

### 4.2. excludeInfoProperties

You can exclude standard fields `group`, `artifact`, `name`, `version`, `time`, or a custom key. **Snippet illustrating insertion into an execution**:

```xml
<configuration>
    <excludeInfoProperties>
        <excludeInfoProperty>time</excludeInfoProperty>
    </excludeInfoProperties>
</configuration>
```

As a result, the file omits `build.time`. When the only goal is to omit the timestamp, a shorter option is `<time>off</time>`; choose one clear approach. If `version` is excluded, `BuildProperties.getVersion()` can return `null`; do not write Java code assuming every field is always present.

### 4.3. outputFile

Default:

```text
${project.build.outputDirectory}/META-INF/build-info.properties
                ↓
target/classes/META-INF/build-info.properties
```

Only change `outputFile` when you **also understand how to place the resource on the classpath**. For example:

```xml
<configuration>
    <outputFile>${project.build.directory}/generated/build-info.properties</outputFile>
</configuration>
```

Here the goal writes the file to `target/generated/build-info.properties`, but `spring-boot:repackage` and the Spring Boot runtime **no longer recognize** it automatically as `classpath:META-INF/build-info.properties`. You would have to configure resource copying and/or `spring.info.build.location` accordingly. **Recommendation for learning:** keep the default path, as that is what Spring Boot auto-configuration detects.

### 4.4. time, outputTimestamp, and reproducibility

The goal defaults to `project.build.outputTimestamp` if set, otherwise the start time of the Maven session. `time` must be a string compatible with `Instant.parse`, for example:

```xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

To configure it explicitly on the goal:

```xml
<configuration>
    <time>2025-01-01T00:00:00Z</time>
</configuration>
```

These are **two different mechanisms**: `project.build.outputTimestamp` also affects plugins that support reproducible archive timestamps, whereas `time` only controls the goal's build-info. Do not hardcode an arbitrary timestamp in a production build and present it as the "actual build time." In CI, you can use a **stable timestamp defined by the release process** or omit the time field if reproducibility rules prioritize byte-for-byte equality.

To omit `build.time` without fabricating a fake value:

```xml
<configuration>
    <time>off</time>
</configuration>
```

If you genuinely need to record the **actual build time**, you can keep the default taken from the Maven session, accepting that the timestamp metadata changes the artifact bytes on every build. When comparing hashes across two environments, you must also control the JDK, archive timestamps, dependency versions, plugin outputs, file ordering, and all other non-deterministic sources; adjusting `build.time` alone does not guarantee the entire JAR is reproducible.

### 4.5. skip

The following CLI command skips the goal when invoked in a lifecycle that has the execution:

```bash
./mvnw clean package -Dspring-boot.build-info.skip=true
```

Although the build succeeds, in a **clean build** `build-info.properties` will not be generated by that goal. **Without `clean`**, an old file can linger in `target/classes` and still get packaged — a major debugging trap. Therefore, when verifying that `skip` truly took effect, use `clean` and inspect the archive again.

**Do not confuse `spring-boot.build-info.skip` with `-DskipTests` or `-Dmaven.test.skip=true`**: they control different tasks. Skipping the build-info goal does not prove tests were skipped, and vice versa.

## 5. Hands-on Java 17 + Spring Boot lab: complete Maven POM

We will create a small web application named `build-info-lab`, produce an executable JAR, and inspect build metadata via both the Java API and Actuator.

**Environment:** JDK 17+, Maven 3.6.3+ or a properly configured Maven Wrapper, and network access or a Maven cache to download dependencies if not already present. The example uses Spring Boot **3.5.16**, pinned for illustration rather than claimed to be the latest version. The metadata timestamp is **intentionally fixed** to produce easily verifiable stdout.

### 5.1. Directory structure

```text
build-info-lab/
├── pom.xml
├── mvnw                                  (if the project has Maven Wrapper)
├── mvnw.cmd                              (if the project has Maven Wrapper)
├── .mvn/wrapper/...                      (if Maven Wrapper is present)
└── src/
    ├── main/
    │   ├── java/com/example/buildinfo/
    │   │   ├── BuildInfoLabApplication.java
    │   │   └── BuildVersionController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/buildinfo/BuildInfoLabApplicationTests.java
```

Do not fabricate a fake `mvnw`. If Maven is already installed on your machine, every `./mvnw` command can be replaced with `mvn`. If you need a Wrapper, generate it using the official Maven Wrapper procedure and commit its files to the repository.

### 5.2. Complete pom.xml

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
    <artifactId>build-info-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>Build Info Lab</name>
    <description>Build metadata example with Spring Boot Maven Plugin</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Fixed timestamp to illustrate output; real products need a CI policy -->
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                        <configuration>
                            <additionalProperties>
                                <team>platform</team>
                                <release.channel>demo</release.channel>
                                <java.version>${java.version}</java.version>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

With `spring-boot-starter-parent`:

- Spring Boot manages compatible versions for `starter-web`, `starter-actuator`, `starter-test`, and the Spring Boot plugin.
- `spring-boot-maven-plugin` is declared **only once** inside `<plugins>`.
- Execution `generate-build-info` invokes the `build-info` goal; the parent supplies the standard `repackage` configuration when the plugin is used. **Do not add `repackage` to this same execution**.
- `target/classes/META-INF/build-info.properties` is created during the build lifecycle, and `repackage` produces an executable JAR containing that resource file.
- `<project.build.outputTimestamp>` is fixed for the lesson. In real projects, use a timestamp matching your release/reproducibility policy.

### 5.3. Main Java class: reading BuildProperties after startup

Create `src/main/java/com/example/buildinfo/BuildInfoLabApplication.java`:

```java
package com.example.buildinfo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BuildInfoLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildInfoLabApplication.class, args);
    }

    @Bean
    CommandLineRunner printBuildInfo(BuildProperties build) {
        return args -> {
            System.out.println("Group: " + build.getGroup());
            System.out.println("Artifact: " + build.getArtifact());
            System.out.println("Name: " + build.getName());
            System.out.println("Version: " + build.getVersion());
            System.out.println("Time: " + build.getTime());
            System.out.println("Team: " + build.get("team"));
            System.out.println("Channel: " + build.get("release.channel"));
            System.out.println("Java target: " + build.get("java.version"));
        };
    }
}
```

Key things to understand:

1. `BuildProperties` is a bean auto-configured by Spring Boot when `classpath:META-INF/build-info.properties` exists, not a runtime Maven object passed in.
2. `getGroup()`, `getArtifact()`, `getName()`, and `getVersion()` read the standard fields.
3. `getTime()` returns an `Instant`, or `null` if missing/unparseable; in this example the fixed timestamp is valid so it returns `2025-01-01T00:00:00Z`.
4. `get("team")`, `get("release.channel")`, and `get("java.version")` read the **custom keys without the `build.` prefix**.
5. The bean is injected into `CommandLineRunner`; if the resource is not generated or missing from the classpath, this application may **fail to start** due to a missing `BuildProperties` bean. This failure is intentional to surface configuration errors.

### 5.4. Controller to check version over HTTP

`src/main/java/com/example/buildinfo/BuildVersionController.java`:

```java
package com.example.buildinfo;

import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildVersionController {
    private final BuildProperties build;

    public BuildVersionController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/build-version")
    public String version() {
        return build.getArtifact() + ":" + build.getVersion();
    }
}
```

The controller returns only the **artifact name and version**, not secrets or the entire Environment. The custom `/build-version` endpoint is application-defined, **not** an Actuator endpoint. In real applications, appropriate authentication/visibility policies are needed even for seemingly harmless metadata.

### 5.5. application.properties: intentionally enabling Actuator info

Create `src/main/resources/application.properties`:

```properties
spring.application.name=build-info-lab
spring.main.banner-mode=off
server.port=8080

# By default web only exposes health; also allow info for this hands-on lab.
management.endpoints.web.exposure.include=health,info
```

With the `spring-boot-starter-actuator` dependency, Spring Boot provides `BuildInfoContributor` when the `BuildProperties` bean exists. Because `/actuator/info` is **not exposed over HTTP by default**, `management.endpoints.web.exposure.include=health,info` is needed to call it from a browser or curl in the lesson.

If Spring Security or other policies are added to the application, `/actuator/info` may require authentication or be blocked by configuration. Do not open `management.endpoints.web.exposure.include=*` in production.

### 5.6. Small unit/integration test verifying BuildProperties

`src/test/java/com/example/buildinfo/BuildInfoLabApplicationTests.java`:

```java
package com.example.buildinfo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BuildInfoLabApplicationTests {

    @Autowired
    BuildProperties build;

    @Test
    void buildInfoIsAvailableInApplicationContext() {
        assertEquals("com.example", build.getGroup());
        assertEquals("build-info-lab", build.getArtifact());
        assertEquals("0.0.1-SNAPSHOT", build.getVersion());
        assertEquals("platform", build.get("team"));
        assertNotNull(build.getTime());
    }
}
```

Here the test simply confirms the bean and the module's metadata. `webEnvironment = NONE` speeds up verification without starting an HTTP server. The test still boots the Spring ApplicationContext, so the resource must be generated **before the test phase** when running `mvn test` or `mvn package` in a lifecycle with the execution.

**IDE pitfall:** If an IDE runs the Java test standalone via a JUnit launcher without triggering the Maven lifecycle and the generated output folder is not yet populated, the `BuildProperties` bean may be missing. How to troubleshoot: run `./mvnw clean test` and check `target/classes/META-INF/build-info.properties`, then configure the IDE to recognize generated resources or run via the appropriate Maven task.

## 6. Running the build, checking files, and verifying stdout

From the root directory containing `pom.xml`, on Linux/macOS:

```bash
# With Maven Wrapper:
./mvnw clean package

# Without wrapper, using installed Maven:
mvn clean package
```

Choose **one** way to build; there is no need to run both. On Windows PowerShell with the Wrapper, use `.\mvnw.cmd clean package`.

With the exact POM/source in Section 5, when Maven succeeds, the file is generated at:

```text
target/classes/META-INF/build-info.properties
```

and the executable JAR at:

```text
target/build-info-lab-0.0.1-SNAPSHOT.jar
```

### 6.1. Viewing the file in the output directory

Linux/macOS:

```bash
cat target/classes/META-INF/build-info.properties
```

Windows PowerShell:

```powershell
Get-Content target/classes/META-INF/build-info.properties
```

The content will have these **keys and values**:

```properties
build.artifact=build-info-lab
build.group=com.example
build.name=Build Info Lab
build.version=0.0.1-SNAPSHOT
build.time=2025-01-01T00:00:00Z
build.team=platform
build.release.channel=demo
build.java.version=17
```

**Line order does not need to match the example**: Java properties provides no ordering contract for applications. Some special characters may be escaped/reformatted when written. What matters is checking the **keys and values**, not the byte order of the illustrative snippet.

### 6.2. Confirming the resource is packaged in the executable JAR

```bash
# List archive entries; verify the exact JAR name created by Maven:
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar

# Linux/macOS with grep:
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    grep 'BOOT-INF/classes/META-INF/build-info.properties'
```

On PowerShell:

```powershell
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/classes/META-INF/build-info.properties'
```

For a Spring Boot executable JAR, the **path inside the archive** is:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Do not confuse it with `META-INF/build-info.properties` at the root of a plain JAR. Spring Boot Loader puts `BOOT-INF/classes` onto the application classpath, so ResourceLoader/ClassLoader can still locate the resource via `classpath:META-INF/build-info.properties`.

To extract that specific file from the JAR without modifying the archive:

```bash
mkdir -p inspect
cd inspect
jar xf ../target/build-info-lab-0.0.1-SNAPSHOT.jar \
  BOOT-INF/classes/META-INF/build-info.properties
cat BOOT-INF/classes/META-INF/build-info.properties
cd ..
```

In PowerShell, replace `cat` with `Get-Content` and use `Push-Location`/`Pop-Location` if needed. `jar xf` extracts the file into the inspection directory; it **does not modify the original executable JAR**.

### 6.3. Running the executable JAR and reading BuildProperties

```bash
java -jar target/build-info-lab-0.0.1-SNAPSHOT.jar
```

On successful startup, the console **will contain these exact lines printed by CommandLineRunner**:

```text
Group: com.example
Artifact: build-info-lab
Name: Build Info Lab
Version: 0.0.1-SNAPSHOT
Time: 2025-01-01T00:00:00Z
Team: platform
Channel: demo
Java target: 17
```

Because the app includes `spring-boot-starter-web`, the embedded server will keep running and listening for HTTP requests; other Spring Boot logs may appear. Do not assume the entire stdout consists solely of those 8 lines.

### 6.4. Checking HTTP and Actuator endpoints

In another terminal, once the server is ready:

```bash
curl -fsS http://localhost:8080/build-version
curl -fsS http://localhost:8080/actuator/info
```

For the custom endpoint, the expected HTTP body (without a newline added by the controller):

```text
build-info-lab:0.0.1-SNAPSHOT
```

Meanwhile, Actuator `/actuator/info` will contain the **`build` group** with artifact/name/version/group/time and custom keys according to default visibility and appropriate configuration. The JSON shape may look like this (abbreviated; key order not guaranteed):

```json
{
  "build": {
    "artifact": "build-info-lab",
    "name": "Build Info Lab",
    "version": "0.0.1-SNAPSHOT",
    "group": "com.example",
    "time": "2025-01-01T00:00:00Z",
    "team": "platform"
  }
}
```

The JSON above is a **structural example**, not a guarantee of the entire response: contents and custom property formatting depend on version/contributors, and additional fields may be present. To verify **each exact value**, reading the file or the `BuildProperties` bean is the direct source.

### 6.5. When you do not want to run a web server

If you only use `spring-boot-starter` (without `starter-web`) and have no web stack, the app can still read `BuildProperties` in Java and print to the console when the resource exists. However, `curl localhost:8080/actuator/info` **will not work** without an HTTP server; having the metadata file does not create an HTTP endpoint by itself.

## 7. Reading the file with plain Java 17: no Spring required

To understand why the resource is a real Java properties file, try a standalone Java 17 program named `ReadBuildInfo.java`. Run it from the example root directory so `target/classes` is present.

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ReadBuildInfo {
    public static void main(String[] args) throws IOException {
        String path = "META-INF/build-info.properties";

        try (InputStream input = ReadBuildInfo.class
                .getClassLoader().getResourceAsStream(path)) {
            if (input == null) {
                throw new IOException("Missing resource: " + path);
            }

            Properties properties = new Properties();
            properties.load(input);
            System.out.println("Artifact = "
                    + properties.getProperty("build.artifact"));
            System.out.println("Version = "
                    + properties.getProperty("build.version"));
            System.out.println("Team = "
                    + properties.getProperty("build.team"));
        }
    }
}
```

Compile and run with a classpath containing only the **Java class and the Maven output directory**:

```bash
javac ReadBuildInfo.java
java -cp ".:target/classes" ReadBuildInfo
```

On Windows, the classpath separator is a **semicolon**:

```powershell
javac ReadBuildInfo.java
java -cp ".;target/classes" ReadBuildInfo
```

With `build-info.properties` properly generated from the example POM, the stdout of this Java program is **exact**:

```text
Artifact = build-info-lab
Version = 0.0.1-SNAPSHOT
Team = platform
```

The program uses neither the `BuildProperties` bean, nor Spring, nor the Maven plugin on the runtime Java classpath; it simply reads **an existing resource file**. This helps separate "Maven didn't generate the file" from "Spring couldn't find the bean":

- If `ReadBuildInfo` reports `Missing resource`, check whether `target/classes` has the file and whether `-cp` is correct.
- If plain Java can read it but Spring lacks the bean, check the Spring process's actual classpath, auto-configuration, and resource location.
- If `java -jar` runs an old build, check when the JAR was last built and the actual artifact path.

## 8. Understanding the BuildProperties bean and ProjectInfoAutoConfiguration

Spring Boot creates `BuildProperties` from `META-INF/build-info.properties` when the resource is on the application classpath and no replacement bean is defined. This belongs to `ProjectInfoAutoConfiguration` and does not depend on whether the app has Actuator HTTP endpoints.

### 8.1. BuildProperties API

| API | Returns | Notes |
|---|---|---|
| `getGroup()` | `com.example` | May be `null` if the key is excluded |
| `getArtifact()` | `build-info-lab` | Artifact ID, not the full JAR path |
| `getName()` | `Build Info Lab` | `<name>` from the effective POM |
| `getVersion()` | `0.0.1-SNAPSHOT` | Maven version of the module |
| `getTime()` | `Instant` | May be `null` if `build.time` is absent or unparseable |
| `get("team")` | `platform` | Custom key **without** the `build.` prefix |
| `get("release.channel")` | `demo` | Returned as a string rather than a nested object |
| `toPropertySource()` | Spring PropertySource | Useful for exposing metadata as a PropertySource |

**Distinction:** `BuildProperties.getVersion()` is the **built artifact's version**, whereas `SpringBootVersion.getVersion()` or the Spring environment can report the **framework version**. They are not necessarily the same.

### 8.2. Changing the resource location intentionally

Spring Boot looks for `classpath:META-INF/build-info.properties` by default. If an application has a **genuine reason** to read a different location, you can use the Spring property:

```properties
spring.info.build.location=classpath:custom/build-info.properties
```

However, you must also ensure `custom/build-info.properties` is actually on the runtime classpath. Do not change `outputFile` in Maven and expect auto-configuration to guess the new path automatically.

### 8.3. Starting up even when the file is missing

The main example intentionally uses required injection to catch broken builds. In real products, some IDE setups may launch the app before Maven generates resources. When missing metadata is acceptable, you can use an optional bean, for example this **illustrative constructor replacement snippet**:

```java
private final org.springframework.beans.factory.ObjectProvider<BuildProperties>
        buildPropertiesProvider;

public BuildVersionController(
        org.springframework.beans.factory.ObjectProvider<BuildProperties> provider) {
    this.buildPropertiesProvider = provider;
}
```

This is a **class fragment**, not complete to run standalone. `ObjectProvider#getIfAvailable()` handles cases where metadata has not yet been generated. Still, fallbacks like `"unknown"` should be logged/monitored; if production requires release metadata, it is better to check the file in CI and fail the build rather than silently continuing.

## 9. Reproducible builds and build.time policy

A common issue is two people building the same commit/dependencies/POM yet producing JARs with different hashes. `build.time` is one source of difference if it varies with each Maven session. Maven 3.5+ and Spring Boot plugins provide ways to control timestamps to support reproducible builds.

### 9.1. Three common policies

| Policy | Example | Pros | Trade-off |
|---|---|---|---|
| Record Maven session time | No fixed timestamp set | Easy to see when the build ran | Rebuilds may change bytes |
| Pin build time from CI/release | `project.build.outputTimestamp` supplied by pipeline | Aids reproducibility if all other inputs are stable | Requires a process to determine a reliable timestamp |
| Omit build time from file | `<time>off</time>` or exclude `time` | Eliminates one source of non-determinism | No build timestamp left in metadata |

**Do not use a fake fixed timestamp as a substitute for tracking release time.** The `2025-01-01T00:00:00Z` example in this lesson is only to give stdout predictable values. At deploy time, **deployment time** can be measured by the CD system, distinct from **build time** and **commit time**.

### 9.2. SOURCE_DATE_EPOCH and timestamps

Some pipelines use `SOURCE_DATE_EPOCH` as a reproducible timestamp source. This is an industry convention, but **do not assume every Maven/Boot plugin version uses that variable automatically**. If a build needs a timestamp from an environment variable, configure it into `project.build.outputTimestamp` or the `time` parameter per actual policy and verify it in the generated file.

### 9.3. Checking consistency

With identical source, dependencies, and tool versions:

```bash
./mvnw clean package
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar
```

Then extract `build-info.properties` to inspect `build.time`. To verify byte-for-byte reproducibility, compare the SHA-256 hashes of artifacts from two equivalent clean builds; matching version/time alone is not enough.

If `build.time` has a format not parseable by `Instant.parse`, Java `BuildProperties.getTime()` may return `null` even though the raw key remains. Use ISO-8601 with an explicit timezone like `2025-01-01T00:00:00Z` to avoid ambiguity.

## 10. Relationship with Actuator info and security

`spring-boot-starter-actuator` provides the `info` endpoint, but **the build-info file does not depend on Actuator to exist**. There are several cases:

- **File present, no Actuator:** Spring Boot can still create the `BuildProperties` bean and the application can use it in code.
- **File and Actuator present:** `BuildInfoContributor` can add the `build` section to `/actuator/info` when the endpoint is enabled and exposed per configuration.
- **Actuator present, no file:** typically no `build` section is added by `BuildInfoContributor`; the endpoint may return `{}` if no other contributors exist.
- **File present, info missing over HTTP:** `info` may not be exposed, the endpoint may be blocked by security/policy, or `management.info.build.enabled=false`.

### 10.1. info is not public by default

By default Spring Boot only exposes HTTP health, not every endpoint. For local testing:

```properties
management.endpoints.web.exposure.include=health,info
```

In production, define which users and networks may access it. If using Spring Security, configure an appropriate `SecurityFilterChain`/Actuator authorization. Do not enable all `*` endpoints just to read the build version.

### 10.2. Do not put sensitive data in additionalProperties

**Unsafe** example:

```xml
<additionalProperties>
    <database.password>super-secret-value</database.password>
    <ci.token>some-private-token</ci.token>
</additionalProperties>
```

The snippet above **only illustrates what to avoid**, not a configuration to use. Secrets can end up inside the distributed JAR, logs, and Actuator info responses. Do not rely on `/actuator/info` not being exposed as a safeguard for secrets; the artifact can still be inspected by anyone permitted to download the file.

Relatively safe information includes: `team`, `release.channel`, `source.encoding`, `artifact`/`version`, or non-sensitive release identifiers. Still, in high-security environments, even internal names/branches/build servers might be unsuitable for public exposure.

### 10.3. BuildInfoContributor vs GitInfoContributor

| Source | Condition | Contents |
|---|---|---|
| `BuildInfoContributor` | `META-INF/build-info.properties` present, bean/feature enabled | Build coordinates/time/custom metadata |
| `GitInfoContributor` | `git.properties` present and suitably configured | Commit ID, branch, commit time |
| `EnvironmentInfoContributor` | Enabled accordingly | `info.*` properties from Spring Environment |
| Custom `InfoContributor` | Application-defined bean | Additional information computed by code |

The `build-info` goal **does not automatically generate a Git commit hash**. For Git metadata, configure a dedicated plugin and test the `git.properties` output separately. **Do not confuse `build.time` with `git.commit.time`**: packaging time and commit time can be far apart.

## 11. Multi-module Maven: generating build info in the right module

Suppose a Maven reactor has:

```text
multi-service/
├── pom.xml               (parent/aggregator)
├── shared-lib/pom.xml     (library JAR)
└── service-app/pom.xml    (Spring Boot executable app)
```

Each MavenProject has its own `groupId`/`artifactId`/`version` and `build.outputDirectory`. If you put the `build-info` goal in the parent's `<build><plugins>` and let all modules inherit it, you may generate `META-INF/build-info.properties` for **every module**, including the root `pom` packaging or libraries that do not need metadata in published artifacts.

### 11.1. Recommended configuration

- The root parent keeps the **plugin version** in `<build><pluginManagement>` so child modules stay consistent.
- Only `service-app` declares `spring-boot-maven-plugin` and the `build-info` execution (along with an appropriate `repackage` policy).
- `shared-lib` uses `maven-jar-plugin` or the standard JAR lifecycle, without needing the Boot executable plugin just to use dependency management.
- If multiple apps share a metadata policy, you can create a controlled parent/convention configuration; ensure each app writes to **its own target directory**.

Example **parent POM snippet** managing the plugin version without executing it:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.5.16</version>
        </plugin>
    </plugins>
</pluginManagement>
```

If the parent is `spring-boot-starter-parent`, the plugin version is already managed; no extra declaration is needed. The snippet above is only for custom-built parents.

### 11.2. Inspecting individual modules

```bash
# Build the app and its dependent projects in the reactor:
./mvnw -pl :service-app -am clean package

# Inspect only the app's effective POM:
./mvnw -pl :service-app help:effective-pom

# Inspect the resource and archive of the exact module:
jar tf service-app/target/service-app-1.0.0.jar
```

These module/version names are **hypothetical**; they only work verbatim if your Maven reactor actually has `service-app`, version `1.0.0`, and the wrapper. The goal is to inspect the **app artifact's metadata**, not mistake a root file or a library module's metadata for it.

**Note:** When running `-pl :service-app -am`, required upstream projects in the reactor are also built. If they are configured to generate build-info, their metadata does not automatically become the app's "primary" metadata; read the exact resource inside the deployed artifact. When multiple dependency JARs carry `META-INF/build-info.properties`, classloader resource lookup can encounter multiple copies; avoid duplicate configurations with unclear metadata ownership.

## 12. Comparison with Gradle: equivalent purpose, different syntax

The Spring Boot Gradle Plugin also provides build information generation, e.g. in Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

springBoot {
    buildInfo()
}
```

The Gradle plugin creates the `bootBuildInfo` task, whereas Maven uses the `spring-boot:build-info` goal. **Do not run the Gradle `bootBuildInfo` command in Maven**, and do not use `-Dspring-boot.build-info.skip` expecting to control a Gradle task.

This lesson focuses on Maven: the goal reads `MavenProject`, uses XML configuration in the POM, and outputs to `target/classes`. If a monorepo contains both Maven and Gradle projects, determine the build tool **of the final artifact** before looking in `target` or `build`.

## 13. Common issues and troubleshooting

| Symptom | Likely hypothesis | Check / resolution |
|---|---|---|
| `target/classes/META-INF/build-info.properties` missing | Goal not run or execution not bound to lifecycle | Check `pom.xml`, `help:effective-pom`, run `mvn spring-boot:build-info` |
| Plugin declared but file missing after `mvn package` | Only declared `spring-boot-maven-plugin`, missing `build-info` execution | Add `<executions><execution><goals><goal>build-info</goal>...` |
| File generated but missing from executable JAR | Goal ran after package, custom `outputFile`, or stale artifact | Run `mvn clean package`, inspect `target/classes` and `jar tf` |
| Java reports missing `BuildProperties` bean | Resource not on application classpath or auto-config overridden | Check `BOOT-INF/classes/META-INF/build-info.properties`, `spring.info.build.location`, and bean config |
| `BuildProperties.getVersion()` returns `null` | `version` excluded or key missing from file | Check `build.version`, `excludeInfoProperties` |
| `getTime()` returns `null` | `build.time` absent or unparseable | Check `<time>off</time>` and ISO-8601 UTC format |
| `/actuator/info` returns 404 | Missing Actuator, `info` not exposed, endpoint disabled, or wrong URL | Add starter-actuator and `management.endpoints.web.exposure.include=health,info`, check security |
| `/actuator/info` returns `{}` | No contributor/build file or contributors disabled | Check `BuildInfoContributor` and resource |
| `/actuator/info` returns 401/403 | Spring Security/authorization | Use valid credentials/roles; do not open publicly without care |
| File has stale values after skipping goal | `target/classes` holds output from a prior build | Run `mvn clean package` and re-check |
| Build time changes on every build | Timestamp taken from Maven session | Pin `project.build.outputTimestamp` or disable `build.time` per policy |
| Fixed build time shows wrong release date | Hardcoded illustrative timestamp copied into production | Have CI supply the timestamp or record release time in CD |
| `additionalProperties` produces wrong key | Included `build.` in key name or broken Maven interpolation | Inspect generated properties and call `build.get("key")` properly |
| App metadata comes from a library module | Multiple JARs contain `META-INF/build-info.properties` | Limit generation to the app; inspect classpath/resource resolution |
| Maven runs goal directly but POM plugin version unclear | Plugin version unpinned; effective POM/parent differs from expectation | Pin plugin version; use `mvn help:effective-pom` |
| Spring app has no HTTP server so curl fails | Using non-web starter only | Add web starter or verify via Java `BuildProperties` |
| IDE test fails while Maven test passes | IDE did not generate `build-info.properties` resource | Run Maven lifecycle first and check generated resource folder |
| Resource contains secret from build pipeline | `additionalProperties` pulled password/token | Remove from config, rotate secret if published, protect artifact |

### Five-step diagnostic workflow

1. **Identify the module and POM:** does it have the right application `artifactId`? Are the plugin version and `build-info` execution in the effective POM?
2. **Regenerate cleanly:** `./mvnw clean package`; read logs to see if `spring-boot:build-info` ran or was skipped.
3. **Read the output file:** `target/classes/META-INF/build-info.properties`, inspecting keys and post-interpolation values.
4. **Read the final artifact:** `jar tf ...jar`, extract `BOOT-INF/classes/META-INF/build-info.properties`, and compare with `target/classes`.
5. **Read at runtime:** verify the `BuildProperties` bean, startup logs, and `/actuator/info` per security policy; compare version with the actual running artifact.

Do not edit files in `target/classes` manually and treat that as a lasting fix. Fix the source POM, CI variables, or resource generation and rebuild.

## 14. Quality checks and CI/CD integration

A release build pipeline may require:

- The `build-info` goal executes in the lifecycle without being skipped.
- Standard keys `group`, `artifact`, and `version` have the expected values.
- Additional properties belong to an approved allowlist and contain no passwords/tokens.
- `build.time` follows timestamp policy and does not unexpectedly break reproducibility.
- The resource exists inside the **uploaded/deployed JAR**, not only in `target/classes`.
- When running the artifact, `BuildProperties` reports the right coordinates/version.
- Actuator `info` is exposed **only per access policy**, not widened indiscriminately.
- Multi-module CI verifies the right app artifact; library modules do not have to carry identical metadata.

### Example artifact check in CI (Linux/macOS)

Assuming the exact POM and artifact from Section 5:

```bash
set -e

./mvnw clean verify

# Ensure the Maven-generated file exists.
test -f target/classes/META-INF/build-info.properties

# Ensure the executable JAR contains the resource in BOOT-INF/classes.
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    grep -Fx 'BOOT-INF/classes/META-INF/build-info.properties'

# Ensure no wrong version was built.
grep -F 'build.version=0.0.1-SNAPSHOT' \
    target/classes/META-INF/build-info.properties
```

This is a **verification script tailored to the example's files/names**, not a ready-made CI workflow for every system. For multi-module POMs, adjust paths, artifactId, and expected version using pipeline policy variables. On Windows PowerShell, use `Test-Path`/`Select-String` with appropriate exit status checks.

### Distinguishing build time from release provenance

A build-info file helps debug "which version is running," but does not prove:

- **Which commit** the JAR was built from without Git metadata or attestation.
- That the artifact was not modified after the build.
- That the signer/releaser had valid authority.
- That dependencies are free of vulnerabilities.
- That deployment succeeded to the right environment and time.

For strong audit requirements, use build-info alongside Git metadata, checksums/signatures, SBOMs, CI provenance, and deployment records — **never rely on a single properties file as the sole source of truth**.

## 15. End-of-lesson checklist

- [ ] Understand that `spring-boot:build-info` differs from `spring-boot:repackage`.
- [ ] Have a `build-info` execution in the POM of the **application module**.
- [ ] Know the default file `target/classes/META-INF/build-info.properties`.
- [ ] Know the file location inside an executable JAR at `BOOT-INF/classes/META-INF/build-info.properties`.
- [ ] Understand `build.group`, `build.artifact`, `build.name`, `build.version`, and `build.time`.
- [ ] Know that `additionalProperties` automatically prepends `build.`.
- [ ] Know what `excludeInfoProperties`, `time=off`, and `skip` do.
- [ ] Distinguish `build.time`, Git commit time, and deployment time.
- [ ] Read metadata from Java using `BuildProperties` or Java `Properties`.
- [ ] Know when the `BuildProperties` bean is auto-configured.
- [ ] Know that `/actuator/info` requires Actuator and appropriate HTTP exposure/authorization.
- [ ] Never embed secrets in resource files or public endpoints.
- [ ] Know how to configure `project.build.outputTimestamp` to control timestamps.
- [ ] Confirmed the file is **packaged into the actual deployed artifact**.
- [ ] Checked multi-module scope and avoided mistaking a library's build metadata.
- [ ] Ran tests and verified stdout/HTTP of the Java 17 example.
- [ ] Have a CI check for build-info and the release version.

**Conclusion:** The Maven goal `spring-boot:build-info` produces **structured metadata in `META-INF/build-info.properties`** from `MavenProject`. The file is added to the application when Maven packaging/repackage runs in the proper lifecycle, and Spring Boot can read it via `BuildProperties` or expose it via Actuator info. The practical value of this feature lies in **knowing precisely which artifact is running**; to be trustworthy in production, pair it with a timestamp policy, CI verification, and protection of sensitive information.

### Official references

- [Spring Boot 3.5 — Maven Plugin: Integrating with Actuator / build-info Goal](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html)
- [Spring Boot 3.5 — How-to: Generate Build Information](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Spring Boot 3.5 — Actuator Endpoints and Application Information](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — BuildProperties Java API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/info/BuildProperties.html)
- [Spring Boot 3.5 — ProjectInfoAutoConfiguration Java API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/info/ProjectInfoAutoConfiguration.html)
- [Spring Boot 3.5 — Maven Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
