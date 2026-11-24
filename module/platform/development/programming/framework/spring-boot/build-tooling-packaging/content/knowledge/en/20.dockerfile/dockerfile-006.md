# Using an Extracted Layout Suitable for Java CDS and Understanding Version Limits

When deploying Spring Boot with a Dockerfile, you can run `java -jar app.jar` directly, extract the JAR to optimize class loading, or generate a **CDS archive** so the JVM shares class metadata and can reduce startup time and memory footprint. However, not every JAR extraction layout, `jarmode` command, or Java version supports CDS identically. A reasonable-looking Dockerfile can still produce an unusable `application.jsa` due to missing libraries, a different runtime classpath, a swapped image/JDK, or commands meant for another Spring Boot generation.

This lesson focuses on **Spring Boot 3.3.13 + Java 17**, explaining how to use `java -Djarmode=tools -jar ... extract` to create a CDS-friendly layout, distinguishing **default extraction** from `extract --layers` for preserving Docker caches, training CDS via `-XX:ArchiveClassesAtExit`, running with `-XX:SharedArchiveFile`, verifying that the archive is actually used, and identifying **JDK/Spring Boot version, classpath, and deployment limits**. It includes a complete Java 17 project, Maven/Gradle configs, two sample Dockerfiles, verification commands, and a CI/CD checklist.

**Version scope:** Spring Boot 3.3.13 is chosen as a baseline for consistent syntax, not claimed to be the newest or still-supported release. For real applications, use your organization's approved version and read documentation for **that exact branch**. Java 24+ and **AOT Cache** follow a different workflow noted in the limits section; **do not mix them with Java 17 CDS syntax**.

## 1. What Is CDS and How Does It Help Spring Boot?

**Class Data Sharing (CDS)** is a HotSpot JVM feature that saves processed class metadata into a `.jsa` archive. On subsequent runs, the JVM can reuse matching class metadata rather than repeating the full loading and processing work from scratch.

Distinguish two capabilities:

- **Default JDK CDS:** many JVM distributions ship with a default archive for core platform classes. You may see some benefit even without building an application-specific archive.
- **Application CDS (AppCDS) / dynamic CDS archive:** also stores application and library classes loaded by the JVM during a "training" run. On **Java 17**, `-XX:ArchiveClassesAtExit=application.jsa` writes a dynamic archive when the JVM exits cleanly, and `-XX:SharedArchiveFile=application.jsa` tells the JVM to use it on subsequent runs.

CDS can improve **startup and footprint**; it **does not** automatically speed up business algorithms, is not a database cache, does not store the application's live object graph, and does not guarantee a fixed percentage speedup. Gains vary with loaded class counts, classloaders, JVM, image, cold/warm startup, filesystem, and container resources.

A valid workflow:

```text
Spring Boot executable JAR
          |
          | jarmode=tools extract
          v
CDS-friendly layout: small application JAR + lib/*.jar
          |
          | Java 17 training JVM, exits cleanly
          | -XX:ArchiveClassesAtExit=application.jsa
          v
application.jsa
          |
          | Same compatible runtime layout/JDK
          | -XX:SharedArchiveFile=application.jsa
          v
Application starts with CDS archive available
```

**Flipping a single JVM flag is not enough.** The archive must be generated cleanly, reside at the right path with a matching classpath, and be accepted by the JVM at production startup.

## 2. Why Does the Spring Boot Executable JAR Layout Matter?

A standard Spring Boot executable JAR typically contains:

```text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...       # Boot launcher classes
└── BOOT-INF/
    ├── classes/...                           # Application classes/resources
    ├── lib/*.jar                             # Nested runtime dependency JARs
    └── layers.idx                            # Optional archive layer index
```

Running:

```bash
java -jar app.jar
```

works functionally. However, inside the JAR there are **nested JARs**, meaning the classpath does not look like regular JAR files sitting directly on the filesystem. JVM/CDS mechanics impose constraints on classpaths and JAR files; a nested-archive layout is not the easiest layout for building a reusable CDS archive.

Starting in **Spring Boot 3.3**, `jarmode=tools extract` creates a layout where:
- Runtime dependencies are extracted into a **`lib/`** directory.
- A **smaller application JAR** holds classes/resources/manifest and references the split library files.
- You run the application via `java -jar` on the **extracted application JAR**, without manually assembling a classpath.

Spring Boot 3.3 documentation calls this **default extraction layout** an efficient and **CDS-friendly** deployment approach. This is not merely `jar xf` dumping entries back where they were; Boot tools construct an execution-ready layout suited for caching.

**Do not equate:**
- `java -jar original-fat.jar`: runs the outer executable JAR with nested archives on its classpath.
- `java -jar extracted/app.jar`: runs the thin JAR after extraction with `lib/` libraries placed appropriately.
- `java -cp lib/*:...`: hand-assembled classpath. If path order or entries differ from training, CDS may not be reused as expected.

## 3. Two Extraction Modes in Spring Boot 3.3

Spring Boot 3.3 exposes `spring-boot-jarmode-tools` through a special mode:

```bash
java -Djarmode=tools -jar app.jar
```

This prints help for supported commands, including `extract`, `list-layers`, and `help`.

### 3.1. Default Layout: `extract --destination`

```bash
java -Djarmode=tools -jar app.jar extract --destination unpacked
```

This is the **simplest option for AppCDS**. If the source is `app.jar`, the conceptual output structure is:

```text
unpacked/
├── app.jar                        # Application JAR generated by Boot to run
└── lib/
    ├── spring-boot-*.jar
    ├── spring-context-*.jar
    └── ...                        # Other runtime dependencies
```

The thin JAR carries **the input application's name**, not necessarily `application.jar` by default. Per Boot 3.3 docs, default extraction creates `<app-name>/<app-name>.jar` and dependency JARs under `lib/`. Exact paths may include additional metadata/files depending on the build; inspect the actual output.

With `target/cds-layout-demo-1.0.0.jar` and destination `unpacked`, launch it with:

```bash
java -jar unpacked/cds-layout-demo-1.0.0.jar
```

You can also `cd` into `unpacked` and run `java -jar cds-layout-demo-1.0.0.jar`. Keep the directory tree intact because the extracted JAR's manifest/classpath references the libraries in `lib/`.

### 3.2. Docker-Layer-Preserving Layout: `extract --layers --destination`

```bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
```

Output is grouped by layer index:

```text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
```

When you **COPY the contents** of all four folders into **the same runtime target directory** in order, you reconstruct the layout runnable via:

```bash
java -jar application.jar
```

This is the layout used in Spring Boot 3.3 Dockerfile documentation to combine **OCI caching** with **CDS**. The `application.jar` in the final image is the tool-generated launcher/application artifact, **not necessarily the original uber JAR**.

### 3.3. Which Mode Should You Pick?

| Need | Extraction Command | Output to Use |
| --- | --- | --- |
| Run CDS on a local machine/VM with minimal steps | `extract --destination unpacked` | `unpacked/<app>.jar` and `unpacked/lib/` |
| Dockerfile needs cache reuse across dependencies/loader/app | `extract --layers --destination extracted` | Four folders with separate `COPY`s into `/application` |
| Only inspect archive entries | `jar tf` or `unzip -l` | Entry listing, **not** a substitute for Boot extraction |
| Run outer JAR without extracting | `java -jar original.jar` | Valid at runtime, yet misses Boot 3.3's CDS-friendly layout |
| Use Buildpacks | `bootBuildImage` or Maven `build-image` | Buildpack manages image layout/training per its capabilities |

**Key takeaway:** `--layers` does not mean "only this mode supports CDS"; **both the default layout and the layout reassembled from layers are CDS-friendly** when the final classpath and layout match. The `--layers` flag specifically helps build stable Docker/OCI layers.

## 4. Spring Boot Version Limits: `tools` Differs from `layertools`

Documentation across years shows similar-looking commands that **are not interchangeable**:

| Branch / Mechanism | Common Command | Notes |
| --- | --- | --- |
| Spring Boot 2.x and pre-3.3 with layered JAR support | `-Djarmode=layertools` | Legacy command and layout; check docs for your running branch |
| **Spring Boot 3.3** | `-Djarmode=tools`, commands `extract`, `list-layers`, `help` | Provides CDS-friendly `lib/` extraction; 3.3 syntax used in this lesson |
| Spring Boot 3.3 when Docker layers are needed | `extract --layers --destination ...` | Rebuilds runtime layout by copying four groups |
| Newer Spring Boot/JDK branches | Check matching features, possibly **JVM AOT Cache** | Do not assume newer flags work on Boot 3.3 + Java 17 |

In Spring Boot 3.3, `-Djarmode=tools extract` **replaces the older** `-Djarmode=layertools extract`; likewise `list-layers` replaces the legacy list command. Do not copy an old blog's Dockerfile and merely bump the Maven/Gradle version numbers.

One limitation noted explicitly in Boot 3.3 docs: **tools mode cannot be used on a fully executable JAR with an embedded shell launch script**. If a project enabled the launch script to run the file directly like a Unix program, **disable the launch script** on artifacts meant for `jarmode=tools extract`.

### 4.1. Boot Tools Can Be Excluded from the Archive

Boot 3.3's Gradle `bootJar` task and Maven `spring-boot-maven-plugin` expose an **`includeTools`** property. If `includeTools=false` is configured, the artifact still runs via `java -jar` normally, yet **lacks the tools required for `jarmode=tools`**.

Do not confuse the presence/absence of `BOOT-INF/layers.idx` with the presence/absence of `spring-boot-jarmode-tools`. Spring Boot 3.3 separated tools inclusion control from some older layering settings. When debugging, check all five:
1. Actual Spring Boot plugin version in use.
2. Whether tools exist in the packaged JAR.
3. Whether an embedded launch script is present.
4. Whether the `tools extract` command matches the branch/version.
5. When using `--layers`, whether the layer index is generated and readable.

## 5. JVM Limits: Java 17 CDS, Java 24+, and AOT Cache

This lesson uses **Java 17** because Spring Boot 3.3 supports it and HotSpot Java 17 offers **dynamic CDS archives** via `ArchiveClassesAtExit`. Run:

```bash
java -version
java -XX:+PrintFlagsFinal -version
```

The second command prints many flags and is quite verbose; check `java -version` and JVM docs for flag names/semantics rather than printing all flags in CI. If an image uses a non-HotSpot runtime or a JDK build lacking the option, the JVM reports an unrecognized `-XX:...` option; **never silently assume CDS is active**.

Version distinctions:

- **Java 17 (HotSpot):** supports `-XX:ArchiveClassesAtExit=...`, `-XX:SharedArchiveFile=...`, `-Xshare:off/on/auto`. AppCDS creates a dynamic archive from loaded classes.
- **Java 21 (HotSpot):** also supports CDS, yet **never reuse a `.jsa` trained on Java 17**. Generate the archive with the exact runtime/JVM matching deployment.
- **Java 24 and later:** the JVM added **AOT Cache** under newer JEPs. Recent Spring Boot docs recommend AOT Cache over CDS where the JVM supports it; syntax can differ across Java/Boot releases. **Do not use `-XX:AOTCache` or `-XX:AOTMode` on Java 17 with this lesson's sample**.
- **GraalVM native executable:** a different deployment model; does not use a HotSpot `.jsa` CDS archive in the native binary.
- **Spring AOT (`processAot`) / native-image:** serves a different purpose from CDS. Spring AOT generates code/hints for reflection/bean wiring, whereas CDS shares class metadata in the JVM.

**Do not conclude Spring Boot 3.3 supports every future Java release** merely because newer JVMs introduce AOT Cache; check the **Boot/JDK compatibility matrix for your exact version**. Whenever upgrading the JDK major version or Spring Boot plugin, retrain the archive and verify runtime flags.

## 6. Conditions That Make `application.jsa` Unusable

Java CDS enforces constraints on **classpath, module path, JAR bytes, JDK build, and VM options**:

1. **Compatible JDK runtime:** recommended to use the exact same vendor, version/build, CPU architecture, and base image for training and production. An archive may fail to load across different JDKs.
2. **Final classpath:** JAR paths and entry sets seen by the JVM must match those at archive creation; do not train in `/tmp` and later move `lib/` elsewhere or alter `-cp`.
3. **JARs untouched after training:** updating dependencies, classes/resources, plugin-generated manifests, or libraries in `lib/` can invalidate or degrade the archive.
4. **VM flags can affect CDS:** certain flags touching module paths, patched modules, class loading, or advanced options disable or reduce archive usability.
5. **Classes loaded during training** enter the archive within JVM rules. Classes loaded only when hitting a rare endpoint may miss out if never touched during training.
6. **Classloader/application topology** can affect archived classes; using Boot's generated layout minimizes risk.
7. **Filesystem and permissions:** the container must have read access to `application.jsa`, the thin JAR, and `lib/` files; never abuse root privileges to mask bad permissions.

For Java 17, JVM documentation on Application CDS also notes that classpaths cannot arbitrarily contain **non-empty directories** in certain archive modes. The thin **JAR + lib JARs** layout works far better than unpacking `.class` files into folders and putting raw folders onto `-cp`.

**Takeaway:** *a CDS archive is tied to one build and one JVM environment*, not an asset shared permanently across releases. Whenever **application, JAR, JDK, or runtime layout** changes, treat the old archive as **invalid for the new release** and regenerate it.

## 7. Hands-On Java 17 + Spring Boot 3.3 Project

To test real commands, let's build a simple REST application. You can use either Maven or Gradle with the **exact same Java code**.

```text
cds-layout-demo/
├── pom.xml                              # Maven option
├── settings.gradle                       # Gradle option
├── build.gradle                          # Gradle option
├── Dockerfile.cds                       # Docker multi-stage layered CDS
├── Dockerfile.extracted                 # Docker non-layered extracted CDS
└── src/
    ├── main/java/com/example/cds/
    │   ├── CdsLayoutApplication.java
    │   └── PingController.java
    └── test/java/com/example/cds/
        └── PingControllerTest.java
```

This tree shows **available choices**, not a requirement for a real project to maintain both Maven and Gradle simultaneously. When using Maven, use `pom.xml`; when using Gradle, use `settings.gradle` + `build.gradle`. Each Dockerfile copies from the corresponding output.

### 7.1. Main class

Create `src/main/java/com/example/cds/CdsLayoutApplication.java`:

```java
package com.example.cds;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CdsLayoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CdsLayoutApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning under `com.example.cds`. With the web starter, the app runs an embedded server and **does not exit on its own**, unlike one-shot console demos.

### 7.2. REST endpoint

Create `src/main/java/com/example/cds/PingController.java`:

```java
package com.example.cds;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "cds-ready";
    }
}
```

When running on default port 8080, the command:

```bash
curl -fsS http://localhost:8080/ping
```

returns body:

```text
cds-ready
```

This is the **HTTP body** output, not the Java startup log. Use `Ctrl+C` to stop the app when testing locally.

### 7.3. Plain Java JUnit test

Create `src/test/java/com/example/cds/PingControllerTest.java`:

```java
package com.example.cds;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PingControllerTest {

    @Test
    void pingReturnsExpectedText() {
        assertEquals("cds-ready", new PingController().ping());
    }
}
```

This test verifies controller behavior without booting a Spring context, so it runs in simple CI setups too. It **does not** test the CDS archive or Docker image; those are tested separately after building the artifact.

## 8. Complete Maven POM to Build an Executable Boot JAR

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cds-layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
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

The Spring Boot parent manages plugin versions and `repackage` execution by convention. Maven writes the executable JAR to `target/cds-layout-demo-1.0.0.jar` and, under standard settings, includes `spring-boot-jarmode-tools`.

Build and test from the project root:

```bash
./mvnw clean verify
```

If the project has no Maven Wrapper, run `mvn clean verify` with a compatible Maven/JDK. On Windows PowerShell use `.\mvnw.cmd clean verify`.

Then:

```bash
jar tf target/cds-layout-demo-1.0.0.jar
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar
```

If `java -Djarmode=tools` does not recognize the command, check the plugin version/execution and `includeTools` instead of assuming any `.jar` contains tools.

**Do not use `target/*.jar.original`** as extraction input. That is the pre-`repackage` JAR lacking the Boot launcher and nested libraries.

## 9. Equivalent Gradle Groovy DSL

Create `settings.gradle`:

```groovy
rootProject.name = 'cds-layout-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.cds.CdsLayoutApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`bootJar` builds the **executable JAR**, whereas the `jar` task may produce `*-plain.jar` per conventions. When running `extract`, pick **the exact `bootJar` output**, never a plain file via wildcard. `springBoot.mainClass` is set explicitly to avoid ambiguity if a module gains multiple `main` classes.

Build:

```bash
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/cds-layout-demo-1.0.0.jar
```

On Windows PowerShell use `.\gradlew.bat`; if no Gradle Wrapper is present, use a compatible installed Gradle.

If using `build.gradle.kts`, the equivalent Gradle Kotlin DSL snippet for main class and tests is:

```kotlin
springBoot {
    mainClass.set("com.example.cds.CdsLayoutApplication")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

This is a **snippet added to a `build.gradle.kts` that already applies the Java and Spring Boot plugins**, not a standalone Kotlin DSL file. Keep Kotlin DSL `mainClass.set(...)` and typed task syntax; do not paste raw Groovy DSL into `build.gradle.kts`.

## 10. Pre-Extraction Check: Verify It Is a Proper Boot JAR

For Maven:

```bash
JAR=target/cds-layout-demo-1.0.0.jar
jar tf "$JAR" | grep '^BOOT-INF/'
jar tf "$JAR" | grep 'META-INF/MANIFEST.MF'
```

For Gradle, substitute `JAR=build/libs/cds-layout-demo-1.0.0.jar`. In the listing, expect:
- `BOOT-INF/classes/com/example/cds/CdsLayoutApplication.class`.
- `BOOT-INF/classes/com/example/cds/PingController.class`.
- `BOOT-INF/lib/spring-boot-3.3.13.jar` and runtime dependencies.
- `META-INF/MANIFEST.MF` with Boot launcher/`Start-Class` attributes.
- `BOOT-INF/layers.idx` if the layered index is enabled.

**`jar tf` only lists entries**; it does not prove CDS works. It helps distinguish an executable JAR from a plain JAR. If `unzip` is available, inspect the manifest:

```bash
unzip -p "$JAR" META-INF/MANIFEST.MF
```

For Spring Boot 3.3, typical fields are:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.cds.CdsLayoutApplication
```

This is an excerpt; the manifest can include extra metadata. If using a fully executable JAR with an embedded launch script, `tools` mode does not support it: build a separate artifact **without the script**.

## 11. Practicing CDS with the Default Layout Locally

We use the Maven artifact to keep commands concise; for Gradle, simply adjust the path. From the project root:

```bash
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar \
  extract --destination unpacked
```

Once tools finishes successfully, inspect:

```bash
ls -l unpacked
ls -l unpacked/lib
```

Expect **`unpacked/cds-layout-demo-1.0.0.jar`** and runtime JARs under **`unpacked/lib/`**; some additional metadata may appear depending on the archive. Now enter the output folder:

```bash
cd unpacked
java -jar cds-layout-demo-1.0.0.jar
```

Test from another terminal:

```bash
curl -fsS http://localhost:8080/ping
```

Output:

```text
cds-ready
```

Stop the app with Ctrl+C. Running the thin JAR **verifies the layout has a working classpath to boot**, though it does not prove an AppCDS archive exists yet. The training step below generates the `.jsa` file.

**Do not rename the JAR or move `lib/` after extraction** unless you understand the manifest/classpath layout. If the image needs `/application` as its root, extract directly there or copy the entire tree **before training**, then run from that exact location in production.

## 12. Training CDS on Java 17 with `ArchiveClassesAtExit`

Inside `unpacked/` sit the thin executable application JAR and `lib/`. Run:

```bash
java -XX:ArchiveClassesAtExit=application.jsa \
  -Dspring.context.exit=onRefresh \
  -jar cds-layout-demo-1.0.0.jar
```

Meaning:
- `-XX:ArchiveClassesAtExit=application.jsa`: instructs the JVM to write a **dynamic CDS archive** on process exit.
- `-Dspring.context.exit=onRefresh`: via Spring Framework integration, requests **exiting right after refreshing the application context**, enabling training without leaving the web server serving requests indefinitely.
- `-jar cds-layout-demo-1.0.0.jar`: runs the **extracted JAR**, not the outer JAR in `target/`.

In Docker/CI, training must **exit with a successful exit code** and produce the archive file before the image build proceeds. If the app has startup listeners connecting to a DB, Kafka, internal services, or requiring secrets in `@PostConstruct`, `onRefresh` does not magically eliminate those side effects. Design an appropriate training profile/config or skip CDS if safe build-time training is impossible.

Verify:

```bash
test -s application.jsa
ls -lh application.jsa
```

`test -s` checks "file exists and is non-empty" in Unix shells; this **does not yet prove the JVM will accept** the archive. There is no fixed stdout during training: Spring Boot and HotSpot logs vary by version and log settings.

### 12.1. If Training Fails to Exit

Real applications may spawn threads or background services. Tune the training configuration rather than running `ArchiveClassesAtExit` and hanging indefinitely. You can guard init conditions, avoid accidentally starting schedulers/consumers during build, and enforce a CI timeout.

**Never pass `-Dspring.context.exit=onRefresh` in production**: that property exits training early; if present in production, the web server will not stay up as a long-running service.

## 13. Running the Application with the CDS Archive

Once the archive is generated, stay **inside `unpacked`** and run:

```bash
java -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

Another terminal:

```bash
curl -fsS http://localhost:8080/ping
```

Body remains:

```text
cds-ready
```

Endpoint correctness proves the **application did not break** with CDS enabled. To verify the JVM actually loaded `.jsa`, inspect logs as shown next; do not guess from the HTTP body.

If the JDK or cache is incompatible, the JVM may warn and fall back without fully using the archive, or fail if you forced `-Xshare:on`. Per Java 17 recommendations, **`-Xshare:auto`** suits production by letting the JVM decide whether CDS is usable, while `-Xshare:on` is reserved for fail-fast diagnostics.

## 14. Verifying That CDS Is Actually Used by the JVM

In Java 17 HotSpot, enable unified logging:

```bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

CDS logs reveal:
- Which archive was mapped/opened successfully.
- Whether classpath or JDK compatibility issues occurred.
- Whether the shared archive was accepted or ignored by the JVM.
- The distinction between the default JDK CDS archive and **`application.jsa`**.

Do not match hardcoded log lines across all JVM minor versions and vendors; exact phrasing varies. For more verbose logs, use:

```bash
java -Xlog:cds=debug \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

`-Xlog:cds=debug` can emit a lot of output; enable only for diagnostics, not by default in production.

To **fail fast in a verification environment** if the archive cannot be used:

```bash
java -Xshare:on \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

**Do not enable `-Xshare:on` blindly across all production workloads**: Java 17 docs warn that forced mode can cause the JVM to exit if a shared archive is invalid. In production, use normal mode and monitor logs/metrics appropriately.

### 14.1. Comparing Startup With and Without AppCDS

When benchmarking, hold **JDK, CPU/memory limits, filesystem, config, and app JAR** constant, varying only flags. Example without CDS:

```bash
java -Xshare:off -jar cds-layout-demo-1.0.0.jar
```

Versus:

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

`-Xshare:off` disables even the default JDK CDS, making this an **extreme comparison**. To also isolate the gain of *application CDS over default JDK CDS*, run a baseline JVM with default CDS enabled while **not specifying `application.jsa`**. Run multiple iterations with controlled warm/cold caches, measure startup, RSS, and throughput, and observe real behavior. Never promise "50% faster startup" without measuring your own app.

## 15. Baseline Dockerfile: Single Uber JAR, No CDS

To see layout differences, create `Dockerfile.basic`:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/cds-layout-demo-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

Build after `./mvnw clean package`:

```bash
docker build -f Dockerfile.basic -t cds-demo:basic .
docker run --rm -p 8080:8080 cds-demo:basic
```

In another terminal run `curl -fsS http://localhost:8080/ping`. Body `cds-ready`. This Dockerfile is **simple and runnable**, yet:
- Does not use Boot tools extraction.
- Does not generate `application.jsa`.
- Copies the whole outer JAR, so any app code change re-copies the entire JAR.
- Does not split dependencies into OCI layers via `layers.idx`.

Therefore `Dockerfile.basic` serves as a sensible baseline when weighing the complexity cost of CDS and multi-stage extraction. **Not every project needs CDS.**

## 16. CDS Dockerfile Using Default Extraction Without Four OCI Layers

When focusing solely on a CDS-friendly layout with an easy-to-follow example, create `Dockerfile.extracted` (Maven demo):

```dockerfile
# Use the same runtime family and Java 17 for training / serving.
FROM bellsoft/liberica-openjre-debian:17-cds AS extractor
WORKDIR /workspace
COPY target/cds-layout-demo-1.0.0.jar input.jar
RUN java -Djarmode=tools -jar input.jar extract --destination /unpacked

FROM bellsoft/liberica-openjre-debian:17-cds
WORKDIR /application
COPY --from=extractor /unpacked/ ./

# Training runs inside the exact final layout.
RUN java -XX:ArchiveClassesAtExit=application.jsa \
    -Dspring.context.exit=onRefresh \
    -jar cds-layout-demo-1.0.0.jar

EXPOSE 8080
ENTRYPOINT ["java", "-XX:SharedArchiveFile=application.jsa", \
            "-jar", "cds-layout-demo-1.0.0.jar"]
```

Sequence:
1. Builder copies the **exact packaged Boot JAR**.
2. Boot tools create `/unpacked/<jar-name>` and `/unpacked/lib/`.
3. Runtime stage copies the whole layout into `/application`.
4. `RUN` trains CDS in **`/application`**, at the exact path and on the exact JVM image family used when the container serves traffic.
5. `ENTRYPOINT` loads `application.jsa` and launches the thin JAR.
6. The final Docker image **does not retain the original input uber JAR** at `/workspace/input.jar`.

Build:

```bash
./mvnw clean package
docker build -f Dockerfile.extracted -t cds-demo:extracted .
```

Run:

```bash
docker run --rm -p 8080:8080 cds-demo:extracted
```

`GET /ping` still returns `cds-ready`. If using Gradle, change `COPY target/...` to `COPY build/libs/cds-layout-demo-1.0.0.jar input.jar` after running `./gradlew clean test bootJar`.

**Limitation of this Dockerfile:** copying the whole extracted layout in one step does not maximize layer caching when only app code changes. It is a **CDS-first, Docker-cache-second** example. To get both, use Section 17's Dockerfile.

## 17. Dockerfile Combining Four Spring Boot Layers with CDS

Create `Dockerfile.cds` for the Maven demo:

```dockerfile
# Spring Boot 3.3 + Java 17 CDS: extract in builder.
FROM bellsoft/liberica-openjre-debian:17-cds AS extractor
WORKDIR /workspace

# Avoid wildcards when target contains multiple artifacts.
COPY target/cds-layout-demo-1.0.0.jar input.jar
RUN java -Djarmode=tools -jar input.jar extract --layers --destination extracted

# Use the same runtime image for training and serving.
FROM bellsoft/liberica-openjre-debian:17-cds
WORKDIR /application

# Each COPY is a separate OCI layer, in cache-friendly order.
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

# Generate application CDS after assembling the full classpath.
RUN java -XX:ArchiveClassesAtExit=application.jsa \
    -Dspring.context.exit=onRefresh \
    -jar application.jar

EXPOSE 8080
ENTRYPOINT ["java", "-XX:SharedArchiveFile=application.jsa", \
            "-jar", "application.jar"]
```

**This Dockerfile follows the Spring Boot 3.3 layout**, where `extract --layers` creates folders matching the four layers:
- `dependencies`: external release libraries.
- `spring-boot-loader`: Boot launcher code.
- `snapshot-dependencies`: external SNAPSHOT dependencies.
- `application`: app classes/resources and local project module dependencies.

These folders are **merged into the same `/application` root**. The structure contains **`application.jar`** and `lib/` ready to run Boot in extracted mode. The training `RUN` must come **after all four `COPY`s**; training earlier and modifying classpath files afterward can break or invalidate the archive.

### 17.1. Build and Run Commands

```bash
./mvnw clean package
docker build -f Dockerfile.cds -t cds-demo:layered .
docker run --rm -p 8080:8080 cds-demo:layered
```

In another terminal:

```bash
curl -fsS http://localhost:8080/ping
```

HTTP body:

```text
cds-ready
```

For Gradle: run `./gradlew clean test bootJar` and change one Dockerfile line to `COPY build/libs/cds-layout-demo-1.0.0.jar input.jar`.

### 17.2. Why Do Four `COPY`s Help Caching?

When editing only `PingController.java`, the `application` layer changes while `dependencies` and `spring-boot-loader` can be reused. If a SNAPSHOT dependency changes, `snapshot-dependencies` may differ. However, **the layer containing `application.jsa` must also be regenerated** whenever relevant code or classpath changes.

**Do not promise Docker will always rebuild only one layer**: BuildKit caching depends on base image digests, entry timestamps, file bytes, metadata, and Dockerfile instruction order. If the base image/JDK changes, `application.jsa` must be retrained; if the build task produces a non-deterministic JAR, Docker cache can miss even when source barely changed.

### 17.3. Docker Images in Production

Beyond this lab:
- **Pin base images by digest** in release pipelines when reproducibility is required.
- Use a non-root user when policy allows, ensuring `application.jsa`/JAR/`lib` are readable.
- Never pass DB passwords or production secrets into `docker build` just for training.
- Keep `WORKDIR /application` and the final layout/entrypoint aligned.
- When `target` or `build/libs` holds multiple artifacts, select **the exact Boot JAR by explicit path**, never an ambiguous `*.jar`.
- The Docker `ENTRYPOINT` must **omit `-Dspring.context.exit=onRefresh`**, otherwise the app exits instead of serving HTTP.

## 18. Verifying `application.jsa` Inside the Image, Not Just Build Success

A Dockerfile build with `RUN ... ArchiveClassesAtExit` usually fails if training fails, yet even when the build succeeds you should verify the file and JVM acceptance.

Check file size inside the built image:

```bash
docker run --rm --entrypoint /bin/sh cds-demo:layered \
  -c 'test -s /application/application.jsa && ls -lh /application/application.jsa'
```

Inspect HotSpot logging:

```bash
docker run --rm -p 8080:8080 \
  --entrypoint java cds-demo:layered \
  -Xlog:cds=info -XX:SharedArchiveFile=application.jsa \
  -jar application.jar
```

Log lines vary across vendors and JDK patch versions. Look for messages confirming the JVM loaded the **application CDS archive** with no mismatch warnings; do not treat `cds-ready` as proof, because the endpoint returns the exact same response **even without CDS**.

To fail fast in a **CI test**, you can use `-Xshare:on` in a dedicated verification command, yet **never** switch the production `ENTRYPOINT` to forced mode untested. `-Xshare:on` will abort app startup if the archive is invalid.

## 19. Situations That Make an Archive Unusable

| Change | Risk to `application.jsa` | Handling |
| --- | --- | --- |
| Edit app class/resource and rebuild JAR | Application classes/JAR bytes differ | **Retrain** archive with new artifact |
| Upgrade Spring Boot/Framework/dependency version | Classpath and class metadata change | Retrain after upgrade, run smoke tests |
| Replace release library in `lib/` | New JAR file / different bytes | Retrain; do not keep old `.jsa` |
| Update SNAPSHOT library under same version | Bytes change despite identical coordinates | Never reuse old archive; use immutable dependencies for releases |
| Switch JDK 17 image from vendor A to vendor B | JVM/archive compatibility can differ | Train and run on the exact same runtime distribution/build |
| Change CPU architecture AMD64 ↔ ARM64 | CDS binary layout may be incompatible | Build and train separately per platform |
| Change Java 17 patch version or flags | JVM may reject archive | Retrain against production runtime |
| Change `WORKDIR` or move `lib/` after training | Classpath/JAR paths differ | Finalize layout before training; do not move files |
| Swap JAR launcher/shell script | Tools mode can break | Use Boot JAR without embedded launch script |
| Save archive outside final image | Runtime cannot find `application.jsa` | Ensure `RUN` generates inside final stage or `COPY` properly |
| Run JAR from different directory than training | Relative paths may break | Keep `WORKDIR` consistent, verify classpath |
| Add Java agent or module patch flags | Classloader/flags change; some CDS optimizations disabled | Test with exact production startup JVM options |
| Change Spring profile and loaded bean set | Classes loaded during training differ from runtime | Evaluate training coverage and measure actual gains |
| Use native image instead of HotSpot JVM | No equivalent `.jsa` mechanism | Use dedicated native-image workflow |

**Remember:** Docker layer caching and CDS archives have **different lifecycles**. Docker can reuse dependency image layers while still having to regenerate `application.jsa` because app code changed. Or image layers remain cached yet a swapped JDK runtime invalidates CDS. A Docker cache hit **does not prove a CDS hit**.

## 20. Special Note on `spring.context.exit=onRefresh` Training

Spring Framework supports `spring.context.exit=onRefresh` for the training workflow documented by Spring Boot 3.3. Its flow is:

1. The JVM loads the classes needed to initialize the context.
2. The application context refreshes.
3. The training process exits so the JVM writes `.jsa`.
4. Subsequent runtime invocations **omit** this property so the app runs normally.

However, not every application is "side-effect free" during refresh. Things like:
- `@PostConstruct`, bean init, or custom `BeanFactoryPostProcessor`;
- datasource connection checks or DB migrations;
- custom beans connecting to Kafka/RabbitMQ/Redis during init;
- reading secrets/config from Vault, DNS, or service discovery;
- early-starting schedulers or listeners

can still fail if run inside a Docker build environment lacking infrastructure.

**Safe solutions:**
- Use a minimal **training profile** that skips production systems; note that a different class set/profile can reduce CDS coverage.
- Defer or disable unneeded side effects during training without arbitrarily changing the classpath.
- Never inject real secrets into image build layers because secrets can linger in logs/history.
- Enforce timeouts and resource limits on CI training runs.
- If safe training is not feasible, **running the extracted layout without CDS is far better than forcing training that breaks the pipeline**.

Some apps require bean init to read runtime config; when architecture permits, cleanly separate bean wiring/initialization from external network calls during context refresh.

## 21. Boot Tools and CDS Support in Maven vs Gradle

### 21.1. Maven

With the Spring Boot 3.3 parent, `spring-boot-maven-plugin` in Section 8's POM handles `repackage`. If a company **does not inherit** the Spring Boot parent and imports only the BOM, explicitly declare the plugin version and `repackage` execution.

If plugin customization excluded tools, check:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>true</includeTools>
    </configuration>
</plugin>
```

This is a **plugin configuration snippet inside the POM**; if the POM already declares `spring-boot-maven-plugin`, add `<includeTools>true</includeTools>` inside that declaration. In Boot 3.3 tools are normally included already; **you do not need to add this block** unless overriding defaults.

To use `--layers`, do not disable the layered index with `<layers><enabled>false</enabled></layers>`. If layering is not needed, default `extract` still works with tools when supported by the artifact. Parameter names and layer/tools relationships have changed across versions; always read the Maven Plugin reference for your exact branch.

### 21.2. Gradle

`bootJar` is registered by the Spring Boot Gradle plugin; to guarantee tools explicitly:

```groovy
tasks.named('bootJar') {
    includeTools = true
}
```

This is a **snippet added to Groovy `build.gradle`**, not a standalone file. Use only when overriding or making configuration explicit; Boot 3.3 includes tools by default. If the project enables a launch script on `bootJar`, disable the script setting when using tools mode.

**Do not configure `includeTools` on the plain `jar` task**; tools mode belongs to **Spring Boot executable archives**, not ordinary library JARs.

### 21.3. If the JAR Lacks `layers.idx`

`jar tf app.jar` missing `BOOT-INF/layers.idx` can happen because:
- You are inspecting a plain JAR instead of `bootJar`/`repackage` output.
- Layering was disabled.
- The plugin version does not support it or is misconfigured.
- You are inspecting a stale artifact.

If you only want default `extract --destination` and valid tools exist, you do not need four Docker layers. When a Dockerfile uses `extract --layers`, however, **layer metadata must exist** to create the directories `COPY` expects.

## 22. Docker CDS vs Buildpacks vs AOT: Picking the Right Tool

| Approach | Responsibility | Who Controls Image/Runtime Creation? |
| --- | --- | --- |
| Dockerfile copying whole JAR | Simple, few steps | Dockerfile author |
| Dockerfile Boot `tools extract` + thin JAR/lib | Efficient, CDS-friendly layout | Dockerfile author |
| Dockerfile Boot `tools extract --layers` + CDS | Separate OCI layers + CDS archive | Dockerfile author, JVM, and Boot tools |
| Spring Boot `bootBuildImage` / Maven `build-image` | Buildpacks build OCI image with own caching/layering | Builder/buildpacks |
| Spring AOT processing | Optimizes framework work and generated code/hints | Spring AOT tooling |
| JVM AOT Cache (Java 24+ and compatible runtime/Boot) | Newer JVM technique differing from Java 17 CDS | Newer JVM/runtime/tooling |
| GraalVM native image | Compiles to native executable, not run via HotSpot `-jar` | Native-image toolchain |

**Do not paste an arbitrary builder's Buildpacks CDS syntax into a Dockerfile**, or mix newer Java JVM AOT Cache flags into Java 17 AppCDS commands. `bootBuildImage` handles layering and caching according to its builder version rather than emitting four manual `COPY` lines like a custom Dockerfile.

If your goal is solely **faster image pulls** via Docker caching, `--layers` alone may suffice without CDS. If your goal is cutting startup/memory, evaluate CDS training. If the app has no strict latency requirements, a simple baseline image is easier to operate.

## 23. Layered Testing: Build, Layout, Archive, and Endpoint

A solid pipeline verifies each step independently:

### 23.1. Right Artifact

```bash
./mvnw -B clean verify
test -s target/cds-layout-demo-1.0.0.jar
jar tf target/cds-layout-demo-1.0.0.jar |
  grep -Fx 'BOOT-INF/classes/com/example/cds/CdsLayoutApplication.class'
```

### 23.2. Tools Mode and Extraction Succeed

```bash
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar help extract
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar \
  extract --destination unpacked
test -s unpacked/cds-layout-demo-1.0.0.jar
test -d unpacked/lib
```

### 23.3. CDS Training Produces Non-Empty Archive

```bash
cd unpacked
java -XX:ArchiveClassesAtExit=application.jsa \
  -Dspring.context.exit=onRefresh \
  -jar cds-layout-demo-1.0.0.jar
test -s application.jsa
```

### 23.4. Runtime Verifies Both CDS and Business Endpoint

```bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

Another terminal runs `curl -fsS http://localhost:8080/ping` and checks body `cds-ready`. **Automated CI** must manage process lifecycle, poll readiness with a timeout, check exit codes, and stop the process; never start a long-running web server synchronously and assume the pipeline will finish on its own.

When validating a `--layers` Dockerfile, also check:
- Layer list from `java -Djarmode=tools -jar ... list-layers`.
- That `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application` extracted cleanly.
- That `application.jar` and `lib` exist after copying into the runtime image.
- That `application.jsa` exists **inside the final image**.
- Smoke-test the image via `docker run`, startup logs, and the endpoint.

**Remember:** `test -s` works in Bash/POSIX shells. In PowerShell use `Test-Path`/`Get-Item`, or run validation in Linux CI.

## 24. Controlled Performance Comparison

Do not see "archive generated" in logs and declare startup faster. A realistic evaluation:

1. Define the **target metric**: time-to-first-request, application ready time, RSS/PSS memory, or image pull/build time.
2. Keep **source commit, dependency graph, Java image, CPU/memory/cgroup limits, and config** constant.
3. Build **baseline 1**: outer uber JAR without AppCDS.
4. Build **baseline 2**: extracted layout without AppCDS, isolating the gain from extraction alone.
5. Build **variant 3**: extracted layout with AppCDS. Enable `-Xlog:cds` on the first verification pass to prove the archive actually loads.
6. Run multiple iterations, distinguishing cold vs warm filesystem and container/image caches.
7. Measure the **build-time cost of generating `application.jsa`** and the extra archive/image size.
8. Observe behavior when the **classpath changes**, a JDK patch releases, or the base image digest updates.
9. Record measured results and caveats in the pipeline; do not claim a universal "X% faster" across all apps.

If startup is dominated by database migrations, remote secrets, network warm-up, or schedulers, CDS may affect only a small fraction of total startup. If multiple JVMs share a host/memory context, memory sharing benefits also depend on how the OS/container shares memory pages.

**CDS does not replace performance profiling.** It is a measurable, controlled optimization, not a mandatory requirement of every Spring Boot Dockerfile.

## 25. Common Failures When Extracting and Using CDS

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `-Djarmode=layertools` worked in old guides but fails on Boot 3.3 | Wrong jarmode version | Use `-Djarmode=tools` and matching commands |
| `tools extract` fails on archive with shell launch script | Fully executable JAR does not support tools mode | Build Boot JAR without embedded script |
| `java -Djarmode=tools` prints no help | Tools excluded or inspecting plain JAR | Check `includeTools`, `bootJar`/`repackage` |
| `--layers` does not extract four folders | Layer index missing, wrong version/tool config | Check `BOOT-INF/layers.idx` and `help extract` |
| `unpacked/lib` empty/missing | Wrong artifact or wrong extract layout | Extract exact executable JAR, check `BOOT-INF/lib` |
| `java -jar` on extracted JAR reports missing classes | Moved JAR or `lib`; manifest/classpath broken | Copy full extracted tree intact, run from right location |
| `application.jsa` missing | Training did not exit cleanly, wrong path/permissions, flag rejected | Check exit code/logs, `test -s`, and JDK version |
| Training Docker `RUN` hangs | Web server/worker/service init never exits | Use `spring.context.exit=onRefresh`, design safe training config |
| Training needs real DB/secrets | Bean init triggers production side effects | Isolate safe training config or skip CDS |
| `.jsa` exists yet JVM warns it is unused | Classpath/JDK/flags changed or incompatible archive | `-Xlog:cds=info`, retrain on final layout |
| Changed JDK patch, runtime vendor, or CPU arch | Binary archive tied to VM/platform | Rebuild and retrain per runtime target |
| App JAR replaced after training | Archived classes/paths/bytes mismatch | Retrain on exact release artifact |
| CDN/Docker cache hits while CDS misses | OCI layer cache differs from JVM CDS class archive | Check CDS logs separately |
| Archive built while source still changing | Modified artifact breaks stale archive | Generate `.jsa` inside each release's image build |
| `-Dspring.context.exit=onRefresh` left in production ENTRYPOINT | App exits right after refresh instead of serving HTTP | Use property only in training `RUN` |
| Unchecked `-Xshare:on` in production | JVM fails to start on archive mismatch | Use normal mode in prod, guard in CI |
| Request-only classes missing from archive | Training exited before those paths executed | Design suitable training workload, re-measure startup |
| Gradle Docker `COPY` picked `*-plain.jar` | Wildcard picked wrong artifact | Select explicit `build/libs/cds-layout-demo-1.0.0.jar` |
| Docker image has `application.jsa` yet runtime path differs | Wrong `WORKDIR`, `lib`, or `ENTRYPOINT` | Fix layout before training and keep identical at runtime |
| Java 17 reports `Unrecognized VM option 'AOTCache'` | Flag belongs to newer JVM | Use `ArchiveClassesAtExit`/`SharedArchiveFile` on Java 17 |
| CDS shows little gain | Startup bottleneck is network/DB or few classes archived | Compare baselines and logs, optimize real bottleneck |
| Container running as non-root cannot read `.jsa` | File permissions and ownership in image | Make file readable by runtime user; do not run as root to bypass |
| JVM loads default archive instead of app archive | App CDS file missing/invalid, misread log | Check `-Xlog:cds` and `SharedArchiveFile` path |

## 26. Lab Completion Checklist

- [ ] Understand how **CDS/AppCDS** differs from Docker layer caching, Spring AOT, and GraalVM native images.
- [ ] Select **Spring Boot 3.3.13 / Java 17** for the example; do not mix commands from other branches.
- [ ] Produce a **Spring Boot executable JAR**, avoiding Maven `*.jar.original` or Gradle `*-plain.jar`.
- [ ] Do not embed a **fully executable launch script** when using `jarmode=tools`.
- [ ] JAR includes `spring-boot-jarmode-tools` / proper `includeTools` config.
- [ ] Understand `extract --destination` creates **a thin application JAR + `lib/`** for CDS.
- [ ] Understand `extract --layers --destination` creates four directories for Dockerfiles to merge under one runtime root.
- [ ] When using `--layers`, verify `BOOT-INF/layers.idx` and all layers copied by the Dockerfile exist.
- [ ] Java 17 REST app builds/tests cleanly and `/ping` returns body `cds-ready`.
- [ ] Training runs on the **finalized layout** with `-XX:ArchiveClassesAtExit=application.jsa` and `-Dspring.context.exit=onRefresh`.
- [ ] `application.jsa` is generated **after clean training exit** and is non-empty.
- [ ] Production runs `-XX:SharedArchiveFile=application.jsa` **without** `spring.context.exit=onRefresh`.
- [ ] `-Xlog:cds` confirms the JVM accepts the archive, not merely that a `.jsa` file exists.
- [ ] Training and production use **compatible JVMs** with unchanged classpath/JARs and paths.
- [ ] On code/dependency/JDK/image updates, **retrain** the archive for the new version.
- [ ] Use an appropriate runtime Docker image and verify non-root user, permissions, and secret safety.
- [ ] CI checks build, layout, archive, endpoint, logs, and image digests.
- [ ] Evaluate startup/memory across multiple runs with clear baselines; never claim unmeasured improvements.
- [ ] For Java 24+ or newer Spring Boot branches, consult **AOT Cache** docs instead of copying Java 17 flags.

**Conclusion:** To use Java CDS with Spring Boot 3.3, **extract the right layout** using `-Djarmode=tools extract`, **train on the extracted application JAR** with `-XX:ArchiveClassesAtExit`, and **reuse the exact same runtime tree and JDK** with `-XX:SharedArchiveFile`. When writing a cache-optimized Dockerfile, use `extract --layers`, `COPY` layers in order, and **train only after assembling the full classpath**. Verify **JVM logs, endpoints, and version constraints** before treating CDS as active in production.

## Official References

- [Spring Boot 3.3 — Class Data Sharing](https://docs.spring.io/spring-boot/3.3/reference/packaging/class-data-sharing.html)
- [Spring Boot 3.3 — Efficient Deployments / Extracted Layout](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 — Dockerfiles and CDS](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Release Notes — CDS and `jarmode=tools`](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Oracle Java 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html)
- [Oracle Java 17 — The `java` Command, CDS Restrictions](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading and Linking](https://openjdk.org/jeps/483)