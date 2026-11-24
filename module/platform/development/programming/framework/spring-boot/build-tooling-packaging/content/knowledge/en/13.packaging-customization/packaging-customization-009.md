# Compatibility Limits of Launch Scripts with JAR Inspection Tools and Extraction Modes

## 1. Objectives

Spring Boot can package an application into an **executable JAR** run via `java -jar` without installing Gradle or Maven on the deployment host. In addition, Spring Boot's packaging plugins support **fully executable archives**: a shell launch script is prepended to the **very beginning of the JAR/WAR file**. On compatible Unix/Linux hosts, the file can be executed directly as a script or used in service setups.

This convenience comes with a trade-off: the file contains **script bytes ahead of the ZIP/JAR archive**, causing some ZIP/JAR tools to reject the format. Spring Boot 3.3 warns that `jar -xf` may **fail silently** when extracting a fully executable archive. Meanwhile, Spring Boot 3.3 documentation confirms that **`-Djarmode=tools` cannot be used on archives containing a launch script**. Whenever a pipeline needs to extract a JAR to build container images or inspect contents, **do not enable a launch script** on the artifact fed into extraction.

After this lesson, you will:

- Distinguish a regular/"plain" JAR, a standard Spring Boot executable JAR, and a fully executable JAR with a shell prefix.
- Explain why `jar -tf`/`jar -xf`, ZIP readers, tools extraction, and container image pipelines face limitations.
- Configure launch scripts properly in Gradle Groovy/Kotlin DSL and Spring Boot Maven Plugin, and know how to disable them for compatibility.
- Build, run, and preserve two JAR variants of the same Java 17 app, probe byte prefixes yourself, and verify extraction results.
- Choose the right format for direct Unix execution, `java -jar`, WAR deployment, layered JAR extraction, and CI/CD.
- Distinguish packaging/extraction errors from Java application or dependency errors.

**Scope:** examples use Spring Boot 3.3.13, Java 17, and Spring Boot's Gradle/Maven plugins. This version serves as a consistent baseline, not the newest Spring Boot release. In real projects, consult documentation for your exact plugin/loader version and test with the exact JDK and tools used in your pipeline.

## 2. Three concepts that must not be conflated

### 2.1. Plain JAR

The Gradle Java plugin provides the `jar` task. It packages the module's classes and resources without automatically bundling all runtime dependencies. In Spring Boot Gradle Plugin 3.3, when both `jar` and `bootJar` are present, the regular JAR from `jar` normally carries the suffix:

~~~text
build/libs/launch-demo-0.1.0-plain.jar
~~~

A plain JAR is not necessarily an executable application. `java -jar` may fail due to a missing main manifest attribute or missing libraries. Passing `jar -tf` on a plain JAR does not prove the file is valid for releasing a Spring Boot service.

### 2.2. Standard Spring Boot executable JAR, without script

The `bootJar` task or `spring-boot:repackage` goal produces a JAR containing:

~~~text
launch-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/com/example/demo/LaunchApplication.class
    ├── lib/spring-boot-3.3.13.jar
    └── lib/... runtime dependencies ...
~~~

This layout is an abbreviated illustration; the library list depends on the build. The Boot Loader loads nested JARs from `BOOT-INF/lib` and invokes the application via manifest headers such as:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.LaunchApplication
~~~

This file is already **executable via `java -jar`**, even without a shell launch script. Standard ZIP contents normally start with bytes `50 4B 03 04` (ZIP local file header).

### 2.3. Fully executable JAR with launch script

When Gradle invokes `launchScript()` or Maven sets `<executable>true</executable>`, the plugin prepends a script **ahead of** the ZIP payload:

~~~text
app.jar
+--------------------------------+
| #!/bin/bash                     |
| ... Spring Boot launch script ... |  ← prefix
+--------------------------------+
| PK... ZIP/JAR bytes             |
| META-INF/MANIFEST.MF           |
| BOOT-INF/classes               |
| BOOT-INF/lib                   |
| Boot Loader                    |
+--------------------------------+
~~~

This diagram illustrates the concept, not byte-for-byte output. The prefix lets Unix systems run the file directly via a shell launcher, which means **the file no longer starts at byte 0 with a normal ZIP header**.

**Key point:** fully executable merely **adds another startup method**—it does not mean "truly executable JAR" vs. "non-executable" for the unprefixed version. Both variants can hold the exact same Spring Boot app and runtime dependencies; they differ in their contract with the OS and archive tools.

## 3. Compatibility matrix — which option is right?

| Tool / goal | Boot JAR without script | Fully executable with launch script |
| --- | --- | --- |
| `java -jar app.jar` | Standard startup method | Not recommended by Spring Boot when `java -jar` is all you need |
| `./app.jar` on Unix | No default shebang/script | Primary target; requires execute bit, shell, and compatible OS |
| `jar -tf app.jar` | Standard archive reading | Outcome may vary by tool/JDK; must be tested |
| `jar -xf app.jar` | Works cleanly on valid standard archives | Spring Boot warns it **may fail silently** |
| `unzip`/`zipinfo` or ZIP libraries | Usually compatible | Prefix support varies by parser |
| `-Djarmode=tools -jar app.jar extract`, Boot 3.3 | Supported when JAR tools are present | **Not supported** with script-prefixed files |
| `extract --layers` in container builders | Suitable when tools/layers are present | Do not use script-prefixed archives |
| Deploy WAR to servlet container | Use standard container-compatible WAR | Discouraged; container must parse archive |
| Direct Unix service/script | Use external service wrapper | Suitable when explicitly required |
| Scanner/checksum/signing pipelines | Checks follow ZIP/JAR contract | Must verify tools tolerate the prefix |

These represent **format limits and official support boundaries**, not a guarantee that every utility behaves identically. One `unzip` implementation might accept a prefixed file while another rejects it. Never assume "because `unzip` works, Spring Boot `jarmode` will work too."

**Selection rule:** if the application is run via `java -jar`, placed inside a Docker image, parsed as ZIP/JAR, or deployed as a WAR, prefer a **Spring Boot archive without a launch script**. Enable the script only when direct Unix file execution is genuinely required.

## 4. Why do some JAR inspection tools fail?

JARs are built on the ZIP archive format. Many tools scan signatures, offsets, and central directories to locate entries. Prepending a script shifts the start offset of the ZIP payload. Not every parser handles ZIP files with a leading preamble.

- A simple ZIP parser may insist the first two bytes be `PK`.
- Another parser may scan the central directory from the end, adjust offsets, and succeed.
- Some `jar` versions may list or extract entries, yet that is **not a universal guarantee** for fully executable archives.
- Per Spring Boot's own docs, `jar -xf` sometimes **produces no expected files without throwing a clear error**.

Example of a flawed pipeline verification:

~~~bash
mkdir -p extracted
(cd extracted && jar -xf ../app.jar)
echo "Extract complete"
~~~

That `echo` does not verify extraction. If the command exits quietly or does not fail loudly, the pipeline reports a false success. At minimum, assert that **specific expected files** exist and fail clearly otherwise:

~~~bash
test -f extracted/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

`test -f` only checks what matches your app's actual class path and extraction structure. Never "repair" an incompatible archive by stripping the script with `tail`/`dd`: doing so depends on exact offsets/script lengths and easily corrupts checksums and ZIP metadata. The reliable fix is **rebuilding a JAR without the script**.

## 5. Sample Java 17 app for verification

We create a Spring Boot command-line application that prints one line itself:

~~~text
LAUNCH_DEMO_OK
~~~

The code below requires `spring-boot-starter` without needing an HTTP server. File `src/main/java/com/example/demo/LaunchApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LaunchApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchApplication.class, args);
    }

    @Bean
    CommandLineRunner reportStart() {
        return args -> System.out.println("LAUNCH_DEMO_OK");
    }
}
~~~

This is a complete Java file. Spring Boot creates the context and invokes `CommandLineRunner`; with no web starter or background worker, the process exits after startup. Spring Boot log lines may appear alongside that stdout line. Ensure the file path matches `package com.example.demo;`.

## 6. Gradle Groovy DSL: standard build without launch script

Create `settings.gradle`:

~~~groovy
rootProject.name = 'launch-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

With an appropriate Gradle wrapper:

~~~bash
./gradlew --version
./gradlew clean bootJar
java -jar build/libs/launch-demo-0.1.0.jar
~~~

On Windows PowerShell use `.\gradlew.bat`; if the repository has no wrapper yet, generate one or use a compatible installed Gradle. `build.gradle` does not create `gradlew` by itself. The line printed by the app is `LAUNCH_DEMO_OK`.

This configuration **omits `launchScript()`**. `bootJar` still builds an executable Boot JAR. If the build also emits `-plain.jar`, use the `bootJar` output rather than `jar`.

## 7. Gradle Kotlin DSL: equivalent build

Create `settings.gradle.kts`:

~~~kotlin
rootProject.name = "launch-demo"
~~~

Create `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Reuse `LaunchApplication.java` from section 5 and the same Gradle commands. **Pick only one DSL** for the root project; never put both `build.gradle` and `build.gradle.kts` in the same folder trying to configure two variants at once.

## 8. Enabling the launch script in Gradle

### 8.1. Groovy DSL

When direct execution on Unix is desired, **add this fragment** to `build.gradle` from section 6:

~~~groovy
tasks.named("bootJar") {
    launchScript()
}
~~~

Re-run `./gradlew clean bootJar`. The output filename remains `build/libs/launch-demo-0.1.0.jar`, now carrying the script prefix. On Unix with proper permissions:

~~~bash
chmod +x build/libs/launch-demo-0.1.0.jar
./build/libs/launch-demo-0.1.0.jar
~~~

Do not assume the script always prints logs to the terminal: script/service modes can redirect logs or change process lifecycle. For our sample Java app, `LAUNCH_DEMO_OK` is printed when the code actually executes.

### 8.2. Kotlin DSL

In `build.gradle.kts`, place the import at the top of the file:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
~~~

Then add:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

`BootJar` is the task type provided by the Spring Boot plugin, not the plain Java `Jar` task API. If a module lacks `bootJar` because the Spring Boot/Java plugin is missing, fix the plugin setup in the right module rather than renaming tasks randomly.

### 8.3. Setting launch script properties

Spring Boot 3.3 lets you configure default script properties, such as log filename:

**Groovy fragment:**

~~~groovy
tasks.named("bootJar") {
    launchScript {
        properties 'logFilename': 'launch-demo.log'
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript {
        properties(mapOf("logFilename" to "launch-demo.log"))
    }
}
~~~

These fragments are **alternatives replacing** an empty `launchScript()` call; do not include both. Setting `logFilename` does not guarantee filesystem writability; verify service context, UID/GID, and folder permissions.

For a custom script, the plugin provides APIs like:

~~~groovy
tasks.named("bootJar") {
    launchScript {
        script = file('src/custom-launch.sh')
    }
}
~~~

**This is an illustrative fragment, not standalone**: it requires `src/custom-launch.sh` to actually exist with valid, tested shell logic and no secrets. Do not paste this fragment before creating that file.

## 9. Maven: the `executable` option on `repackage`

Maven's Spring Boot Plugin has no `bootJar` task. Maven uses `spring-boot:repackage` in the lifecycle to build the executable archive. With Spring Boot starter parent, the `repackage` goal is preconfigured once the plugin is declared.

### 9.1. Complete Maven POM for the non-script version

An **alternative** Maven project can reuse the Java source from section 5 with the following `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>launch-demo</artifactId>
    <version>0.1.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <executable>false</executable>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`<executable>false</executable>` is the default; written explicitly here so learners see the option. With compatible Maven/JDK:

~~~bash
mvn clean package
java -jar target/launch-demo-0.1.0.jar
~~~

If using a Maven wrapper, run `./mvnw` on Linux/macOS or `.\mvnw.cmd` on Windows. `mvn package` builds the base JAR and the Spring Boot parent's `repackage` execution converts it to an executable Boot JAR. Never pick `.original` by mistake.

### 9.2. Creating a fully executable Maven archive

In the POM above, **change only**:

~~~xml
<executable>true</executable>
~~~

Then run `mvn clean package`. On Unix you can run:

~~~bash
chmod +x target/launch-demo-0.1.0.jar
./target/launch-demo-0.1.0.jar
~~~

Maven Plugin docs warn that `jar -xf` may fail silently on this format; do not enable it if you primarily want `java -jar` or external servlet container deployment.

### 9.3. Maven custom launch script

Spring Boot Maven Plugin provides `embeddedLaunchScript` and `embeddedLaunchScriptProperties`, e.g., as a plugin configuration fragment:

~~~xml
<configuration>
    <executable>true</executable>
    <embeddedLaunchScript>src/custom-launch.sh</embeddedLaunchScript>
    <embeddedLaunchScriptProperties>
        <logFilename>launch-demo.log</logFilename>
    </embeddedLaunchScriptProperties>
</configuration>
~~~

**This is a fragment** replacing `<configuration>` in the complete POM; do not duplicate into two separate `<build>` blocks. The script file must exist, log write permissions must be valid, and it must be tested on the real deployment OS.

## 10. Saving the standard and script-prefixed builds as two separate artifacts

Do not let `clean` wipe the first artifact before comparing. Use a `samples` directory **outside `build`**:

**On Linux/macOS, while Gradle still has `launchScript` disabled:**

~~~bash
mkdir -p samples
./gradlew clean bootJar
cp build/libs/launch-demo-0.1.0.jar samples/standard-boot.jar
~~~

**After adding `launchScript()` in your chosen DSL and rebuilding:**

~~~bash
./gradlew clean bootJar
cp build/libs/launch-demo-0.1.0.jar samples/script-prefixed-boot.jar
~~~

Now:

- `samples/standard-boot.jar` is the Boot executable JAR **without** a shell prefix.
- `samples/script-prefixed-boot.jar` is the Boot executable JAR **with** a shell prefix.
- These two are **not** a plain vs. Boot pair; a plain JAR is a different artifact.
- This is a local demo technique; in CI, use explicit artifact names/variants per your publishing flow.

Run the standard build:

~~~bash
java -jar samples/standard-boot.jar
~~~

Run the script-prefixed build on compatible Unix:

~~~bash
chmod +x samples/script-prefixed-boot.jar
./samples/script-prefixed-boot.jar
~~~

The Java app prints `LAUNCH_DEMO_OK` when running properly. You do not need the script enabled on the standard build just to make `java -jar` work.

## 11. Checking byte prefixes in Java 17 without external ZIP libraries

Alongside the Spring Boot app, create a **standalone Java SE program** at project root (not inside `src/main/java`):

File `ArchivePrefixProbe.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ArchivePrefixProbe {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ArchivePrefixProbe <jar-file>");
            System.exit(2);
        }

        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            byte[] first = in.readNBytes(4);

            if (first.length < 2) {
                throw new IOException("File is too short");
            }

            boolean zip = first.length >= 4
                    && first[0] == 0x50
                    && first[1] == 0x4B
                    && first[2] == 0x03
                    && first[3] == 0x04;

            boolean script = first[0] == '#'
                    && first[1] == '!';

            if (zip) {
                System.out.println("ZIP_HEADER");
            } else if (script) {
                System.out.println("SCRIPT_PREFIX");
            } else {
                System.out.println("OTHER_PREFIX");
            }
        }
    }
}
~~~

Compile with JDK 17:

~~~bash
javac ArchivePrefixProbe.java
java ArchivePrefixProbe samples/standard-boot.jar
java ArchivePrefixProbe samples/script-prefixed-boot.jar
~~~

For the two files built by the plugin in our example (where the default script has a shebang), the two outputs **corresponding to each command** are:

~~~text
ZIP_HEADER
SCRIPT_PREFIX
~~~

Explanation: the standard Boot file starts with a ZIP local header; the fully executable file starts with the script's `#!`. If using a **custom launch script without a shebang** or another format, the probe prints `OTHER_PREFIX`.

**Limitations:** this program reads only the first four bytes; it does not check the central directory, manifest, class loading, dependency graph, checksums, security signatures, or actual `jar -xf` compatibility. It is a prefix diagnostic probe, not a ZIP validator. It runs on plain Java SE without starting Spring Boot.

## 12. Inspecting contents and extracting with JDK `jar`

For the file **without a launch script**:

~~~bash
jar -tf samples/standard-boot.jar
~~~

Look for entries such as:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/demo/LaunchApplication.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
~~~

To test extraction, use a dedicated directory instead of extracting into the project root:

~~~bash
mkdir -p inspect-standard
(cd inspect-standard && jar -xf ../samples/standard-boot.jar)
test -f inspect-standard/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

`test -f` succeeding proves the **expected target file** appeared. If your project uses a different package/class, adjust the path. When unpacking untrusted archives, guard the target directory and write permissions against path traversal overwrites.

To observe the failure mode on the script-prefixed file, use another separate directory:

~~~bash
mkdir -p inspect-prefixed
(cd inspect-prefixed && jar -xf ../samples/script-prefixed-boot.jar)
test -f inspect-prefixed/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

The second test's outcome is **not guaranteed**; Spring Boot warns `jar -xf` may fail silently on fully executable archives. Never treat a zero exit code or lack of exceptions as proof extraction succeeded. Rely only on verified output files.

Some `unzip`/`zipinfo` builds handle script-prefixed ZIPs while others fail or warn. There is **no universal guarantee** across all ZIP readers and runtime environments. Whenever pipelines must extract or parse an archive with varied tools, shipping a standard Boot archive is much safer.

## 13. Spring Boot 3.3 `jarmode=tools` extraction mode

This is the most important limitation in this topic.

### 13.1. What do JAR tools do?

Spring Boot 3.3 includes `spring-boot-jarmode-tools`, which can be packaged into layered executable archives. When this special mode is enabled, the JVM **does not run business code**; instead, the Boot loader invokes tooling to inspect or extract archive contents, e.g.:

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar
~~~

Per Spring Boot 3.3 docs, commands include `extract`, `list-layers`, and `help`. To view options:

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar help extract
~~~

### 13.2. Standard extract layout

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar extract
~~~

In Spring Boot 3.3's default model, this produces a layout with libraries in `lib/` and an application JAR containing app classes and a manifest referencing those libraries. It is **not identical** to raw ZIP extraction via `jar -xf`.

Run `help extract` to see exact output directories and flags for your version instead of guessing a folder name and hardcoding it in CI.

### 13.3. Layered extraction for container images

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar extract --layers --destination extracted
~~~

With default layers, common groups include:

~~~text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
~~~

This layout lets container builders copy each layer separately. If a team customizes layers, folder names and contents change accordingly. `layers.idx` is metadata, while `jarmode=tools` performs the actual extraction.

### 13.4. Why can't you use a file with a launch script?

**Official Spring Boot 3.3 rule: `tools` mode cannot be used with fully executable Spring Boot archives containing a launch script.** Disable the launch script when building JARs intended for `extract`.

Do not try running `jar -xf` first assuming `jarmode=tools` will automatically work on the same file; these are two distinct mechanisms, and both struggle with script prefixes in affected environments/versions.

### 13.5. Two conditions must both hold

To use extract mode:

1. **No launch script prefix.**
2. **Matching JAR tools present** inside the artifact.

Spring Boot 3.3 normally includes `spring-boot-jarmode-tools` when creating layered JAR/WARs; if the build explicitly disables it via `includeTools=false`, extract mode will also be unavailable.

Gradle Groovy snippet illustrating a **configuration to avoid if you still need `extract`**:

~~~groovy
tasks.named("bootJar") {
    includeTools = false
}
~~~

Kotlin:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
~~~

Maven fragment:

~~~xml
<configuration>
    <includeTools>false</includeTools>
</configuration>
~~~

These snippets explain why `tools` can go missing—they are **not** recommended settings. Older Spring Boot lines used `layertools` instead of `tools` or different flags; always verify docs for your exact version before copying CI scripts.

## 14. Container images: keep a standard JAR for extraction

Many Docker/OCI workflows use:

~~~text
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

or run `jarmode=tools extract --layers` in a builder stage. Neither **needs** a Unix launch script inside the JAR.

Example Dockerfile for Spring Boot 3.3, assuming `build/libs/launch-demo-0.1.0.jar` is a **scriptless Boot JAR** with JAR tools and layers:

~~~dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder
COPY build/libs/launch-demo-0.1.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**This is a standalone Dockerfile pattern**, working only when Docker/container runtime is available, the base image/tag is permitted by policy, the JAR was already built in the Docker context, and layer folder names match Spring Boot 3.3. For Maven, adjust the `COPY` source from `target`; if renamed or classified, pick the exact file.

Never use `COPY build/libs/*.jar` when the directory holds both `-plain.jar` and the executable JAR. Avoid copying the wrong artifact into Docker; and if built with `launchScript()`, the `extract` command in the Dockerfile above **is unsupported in Spring Boot 3.3**. Remove the script and rebuild.

If layered extraction is unnecessary, build a simple image with a standard Boot JAR and `java -jar`. Even there, a launch script brings no meaningful benefit.

## 15. Servlet containers, executable WARs, and launch scripts

Spring Boot Gradle plugin offers `bootWar` when the War plugin is applied, and Maven offers `repackage` for WARs. Normal WARs are read/unpacked by servlet containers according to their own rules. Prepending a shell script can prevent containers or archive readers from accepting the file.

Gradle fragment example (shown to understand the feature, **not recommended for externally deployed WARs**):

**Groovy:**

~~~groovy
tasks.named("bootWar") {
    launchScript()
}
~~~

**Kotlin:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    launchScript()
}
~~~

Both snippets are valid only in modules **applying both the Spring Boot plugin and War plugin**. Never add them to a `bootJar`-only project or you will get a task-not-found error.

Distinguish:

- Executable WAR run via `java -jar` through the Boot Loader.
- WAR deployed into an external servlet container via the container's deployment mechanism.
- Fully executable WAR with a shell prefix; Spring Boot warns archive tools may reject it and recommends **against enabling the script when targeting servlet container deployment**.

If a team supports both `java -jar` and external WAR deployment, test each deployment mode and pick appropriate artifacts rather than forcing both through a script-prefixed file.

## 16. When is a fully executable script genuinely worthwhile?

A valid case is a Unix/Linux environment deploying **a single file runnable directly as a script/service**, where operations already defined how processes, logs, and lifecycles are managed.

Before enabling:

- Verify OS and shell compatibility; a JAR with a Unix script does not become a Windows `.exe`.
- Verify execute bits, ownership, whether mounts use `noexec`, and working directory.
- Verify log files, service managers, signal handling, and restart policies.
- Verify custom launch scripts do not hardcode credentials/secrets into the artifact or logs.
- Test on the actual target environment; a passing `bootJar`/`repackage` never proves the script runs in production.
- Document clearly that this variant **must not be used with JAR tools extraction**.

Running `chmod +x` on a standard Boot JAR **does not add a shell script**. Calling `./standard-boot.jar` when byte 0 is a ZIP header makes the OS fail with an execution format error; run it with `java -jar` instead. Conversely, a script-prefixed file missing execute permissions still fails direct execution even with valid Java inside.

## 17. CI/CD verification workflow

A repeatable pipeline should define its **artifact contract** first:

1. **Fetch the exact output:** specify `bootJar` or Maven `repackage`, version, classifier, and output filename. Avoid arbitrary globs.
2. **Identify consumers:** JVM `java -jar`, Unix script, `jar -xf`, `jarmode=tools`, or servlet container.
3. **Choose format:** standard Boot archive in most cases; script-prefixed only when direct Unix execution is required.
4. **Verify prefix:** use a probe like `ArchivePrefixProbe` to catch surprises before ZIP processing.
5. **Verify contents:** run `jar -tf`, inspect `BOOT-INF`/manifest and required entries.
6. **Verify extraction:** for `jar -xf`, assert extracted files exist; for JAR tools, verify actual layer directories exist.
7. **Verify startup:** run `java -jar` on standard artifacts or run the script on real Unix hosts as intended.
8. **Verify release integrity:** hashing, signing, attestation, and scanning must apply to **the exact final file**, never reusing checksums from before the script was prepended.

Prepending a script changes bytes, so checksums differ even with identical classes and dependencies. In signing/verification pipelines, sign and verify each variant individually. Never edit archive bytes after signing without re-verifying.

### 17.1. Avoiding false positives when extracting

Wrong:

~~~bash
jar -xf app.jar
echo "OK"
~~~

Better (inside a controlled extraction directory):

~~~bash
jar -xf ../app.jar
test -f BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

Better still: **never put a shell prefix on a JAR whose contract requires extraction by ZIP/JAR tools**.

## 18. Common symptoms

| Symptom | Possible cause | Right way to investigate |
| --- | --- | --- |
| `jar -xf` prints no error yet extracts no files | Fully executable JAR has a script prefix | Check first 4 bytes, use standard archive, assert extracted files |
| `jar -tf`/ZIP parser fails in CI while local `unzip` works | Different prefix/offset tolerance | Use non-prefixed archive and test with CI's actual tooling |
| `-Djarmode=tools` extraction fails | Script prefix, tools excluded, or wrong mode for Boot version | Disable `launchScript`, check `includeTools` / Boot 3.3 docs |
| Docker builder stops at `extract --layers` | Artifact is script-prefixed, lacks tools, or wrong path | Rebuild standard Boot JAR, verify layer output |
| `./app.jar` reports permission denied | Missing execute bit, owner/mount restriction | Check permissions and OS runtime setup |
| `./app.jar` reports exec format error | No shell script/shebang or incompatible shell | Use `java -jar` for standard archive or build script variant |
| `java -jar` works while `jar -xf` fails | Startup and ZIP extraction follow different contracts | Pick the format matching the tool's contract |
| `BOOT-INF/layers.idx` exists yet `tools` mode fails | `includeTools=false` or incompatible archive format | Inspect packaged dependencies and plugin version |
| `jar -xf` yields a JAR missing Boot classes | Picked plain JAR or stale output by mistake | Inspect task outputs, manifest, and `BOOT-INF` |
| Maven `executable` option has no effect | `repackage` didn't run or wrong plugin configured | Check effective POM and `mvn package` log |
| External WAR container refuses to deploy | WAR format or prefix incompatible with parser | Use scriptless WAR; check container logs |
| Fully executable runs as service with no stdout | Script redirects logs or enters service mode | Check script properties, log files, process status |
| Hash changed compared to previous build | Script prefix, version, or reproducibility shifted | Compare actual artifacts; re-hash/re-sign |
| A ZIP reader rejects `PK` not at offset 0 | Library expects ZIP header at byte 0 | Supply standard archive instead of relying on workarounds |

Never try fixing file-format errors by tweaking `@SpringBootApplication`, shuffling dependency versions, or disabling tests. Identify whether the failure lies in the **archive parser**, **jarmode tools**, **shell runtime**, or **Java application startup** before changing anything.

## 19. Misconceptions to avoid

**"Any executable JAR needs `launchScript`."** False. A scriptless Boot JAR already runs via `java -jar`.

**"`launchScript()` just `chmod`s the file."** False. It **prepends shell script bytes** to the artifact, affecting ZIP/JAR parsers.

**"`jar -xf` printing no exception means extraction worked."** Not guaranteed; Spring Boot warns of silent failures on fully executable archives. Assert extracted files exist.

**"If `unzip` opens it, `jarmode=tools` will too."** False. They are different mechanisms; Boot 3.3 officially does not support `tools` mode on script-prefixed archives.

**"Layered JARs always include `tools`."** Not necessarily if `includeTools` is disabled or plugin/versions differ. Inspect the actual archive and plugin config.

**"`requiresUnpack` fixes `jar -xf` failing due to the launch script."** False. `requiresUnpack` marks a nested dependency to be unpacked at **runtime** by the Boot Loader; it never strips the outer JAR's shell prefix.

**"Changing the shell script makes the Boot JAR smaller or start faster."** That is not the goal. The script adds bytes; startup speed and image layering are separate topics.

**"One artifact works everywhere if you rename `.jar`/`.war`."** False. File format and launch/deployment model dictate compatibility; external servlet containers and container builders have different requirements from direct Unix execution.

## 20. Self-practice exercises

### Exercise 1. Distinguish Boot JAR from plain JAR

**Prompt:** Gradle produces `launch-demo-0.1.0.jar` and `launch-demo-0.1.0-plain.jar`. Which file is `bootJar`'s default output in this lesson, and is `launchScript` needed to run with `java -jar`?

**Answer:** `launch-demo-0.1.0.jar` is `bootJar`'s standard output; `-plain.jar` comes from `jar`. A script is not needed for `java -jar` to run a Boot executable JAR.

### Exercise 2. Container decision

**Prompt:** A Dockerfile runs `java -Djarmode=tools -jar application.jar extract --layers`, and someone wants to enable `launchScript()` "for convenience."

**Answer:** Do not enable it. In Spring Boot 3.3, `tools` mode does not support fully executable archives with a launch script. Use a standard scriptless Boot JAR with tools/layers included.

### Exercise 3. Java byte probe

**Prompt:** Two builds of the same app print `ZIP_HEADER` and `SCRIPT_PREFIX` respectively with `ArchivePrefixProbe`.

**Answer:** Their byte prefixes differ: the first begins with a ZIP local header, the second with a shebang. This alone does not prove the entire ZIP archive is valid or that extraction tools succeed.

### Exercise 4. Silent extraction failure

**Prompt:** `jar -xf` on a fully executable JAR exits without any error message, yet the extraction directory remains empty.

**Answer:** This is the exact failure Spring Boot warns about. Assert post-conditions of extraction and **rebuild a scriptless JAR** as input to the extraction pipeline.

### Exercise 5. Maven

**Prompt:** The POM sets `<executable>true</executable>`, yet a new pipeline stage needs `jar -xf`.

**Answer:** Set `executable` back to `false` or remove it to use the default, re-run `mvn clean package`, verify the Boot archive, and then extract.

### Exercise 6. Unix execution

**Prompt:** A standard JAR had `chmod +x` applied, yet running `./app.jar` fails.

**Answer:** File permissions do not create a shell prefix. Run it with `java -jar`, or enable `launchScript()`/Maven `executable` if direct Unix execution is truly required.

### Exercise 7. WAR

**Prompt:** A WAR will be deployed to an external servlet container. Should the launch script be enabled to make it "fully executable"?

**Answer:** Not recommended; external containers process WARs as archives and a script prefix can break compatibility. Build a scriptless WAR and test on the target container.

**Completion criteria:** you can run the standard JAR with `java -jar`, build the script-prefixed variant and test direct Unix execution where appropriate, observe different byte prefixes with the Java probe, verify `jar -xf` through actual extracted files, and explain why JAR tools extraction requires the scriptless variant.

## 21. Release checklist

- [ ] Clearly identified the artifact consumer: Java runtime, Unix shell, ZIP reader, `jarmode` tools, or external container.
- [ ] Selected the true `bootJar` or `repackage` output, never confusing plain JARs or stale artifacts.
- [ ] For `java -jar`/ZIP extraction/Docker layered extraction, **did not enable `launchScript`**.
- [ ] For direct Unix execution, script was configured/tested, and target filesystem has execute bit and compatible shell.
- [ ] For JAR tools, `includeTools` was not disabled, and version/mode/`extract` flags match your Spring Boot version.
- [ ] `jar -xf`/tools extraction asserts output post-conditions instead of trusting exit codes or log lines.
- [ ] Docker builds avoid globs that could copy `-plain.jar` or a script-prefixed variant by mistake.
- [ ] Externally deployed WARs carry no prefix that breaks archive readers.
- [ ] Variants are named, tested, checksummed, and signed individually; no byte edits after signing without re-verification.
- [ ] Team documented why a launch script is required and which tools must not be used on that file.

**Conclusion:** The launch script exists to support **direct execution on Unix**, not to enable a Spring Boot JAR to run via `java -jar`. Because it prepends bytes ahead of the ZIP structure, some JAR inspection tools lose compatibility; `jar -xf` can fail silently. **In Spring Boot 3.3, `-Djarmode=tools` extraction must not be used on fully executable archives containing a launch script.** Whenever tooling needs to read or extract a JAR, distribute a **scriptless Spring Boot executable archive**.

## 22. Official references

- Spring Boot 3.3.13 — Gradle Plugin, *Packaging Executable Archives / Making an Archive Fully Executable*: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — Maven Plugin, `repackage`, `executable`, and `embeddedLaunchScript`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3.13 — *Dockerfiles*, warning on `tools` mode and fully executable archives: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3.13 — *Efficient Deployments*, extracting JARs and layout: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot 3.3 — Executable JAR specification: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Java SE 17, JAR API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/package-summary.html

When upgrading Spring Boot or changing launchers/build tools, re-read the documentation **for your exact version** and run compatibility checks using the exact tools used post-release. Never pick "fully executable" merely because the name contains the word "fully."