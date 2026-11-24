# Configuring Additional Manifest Attributes While Preserving the Spring Boot Entry Point

## 1. Problem: adding metadata without breaking the executable JAR

A Spring Boot application packaged with Maven or Gradle is typically launched with **java -jar**. The JAR contains **META-INF/MANIFEST.MF**, a metadata file describing the archive and startup details. A team may want to add:

- **Implementation-Title**: service or product name.
- **Implementation-Version**: application release version.
- **Build-Revision**: commit/build revision ID for traceability.
- **Build-Channel**: e.g. **training**, **staging**, or **release**.
- **Built-By-Team**: name of the team responsible for building the artifact.

That need is valid, yet a Spring Boot executable JAR **differs from a standard Java JAR**. If you misconfigure **Main-Class** or **Start-Class**, the file still ends in **.jar**, still has a manifest, and may even contain all classes, yet **java -jar may fail to start**.

Safety rules for this lesson:

1. Let the **Spring Boot packaging plugin manage the launcher section** of the executable archive.
2. Add only manifest attributes that **do not conflict** with headers required by the Spring Boot loader.
3. When specifying an entry point, use **Spring Boot Maven Plugin `mainClass`** or **Gradle `springBoot.mainClass` / `bootJar.mainClass`**.
4. **Build, read the final manifest, and run the actual JAR** after adding metadata; never conclude it works just because `pom.xml`/`build.gradle` contains the desired configuration.

This lesson uses **Spring Boot 3.3.5**, Java **17**, Maven, and Gradle Groovy DSL (**Gradle 8.5**) for illustration. These versions are a deliberate practical baseline, not a claim that they are the latest. For Spring Boot 4 or another loader version, verify the launcher class name for your exact version.

## 2. What is META-INF/MANIFEST.MF?

A JAR is a structured ZIP file. The manifest normally resides at:

~~~text
META-INF/MANIFEST.MF
~~~

A simple manifest snippet:

~~~text
Manifest-Version: 1.0
Implementation-Title: manifest-demo
Implementation-Version: 1.0.0
Build-Channel: training
Build-Revision: lesson-149
~~~

The snippet above only shows a few metadata attributes. It is **not enough** to form an executable Spring Boot archive. Startup headers are covered in the next section.

The manifest format has specific rules: each attribute has a **name**, a colon, a space, and a **value**, with sections separated by blank lines. Overly long lines can be **wrapped across multiple physical lines** with a leading space on continuation lines. Therefore, when inspecting long values, using **java.util.jar.Manifest** is far more reliable than trying to match the whole value on one line with grep.

Key points:

- **Manifest-Version** is normally generated automatically by JAR tooling.
- **Manifest attributes are not `application.properties` properties**. Putting `Build-Channel` in the manifest does not automatically set `spring.profiles.active` or expose an `app.build-channel` property.
- **The manifest is not a place for secrets**: anyone who obtains the JAR file can usually read its attributes.
- Modifying manifest contents changes the archive's bytes and checksum; signed artifacts may need to be rebuilt and re-signed per policy.
- If the application only needs version/build metadata exposed via Actuator, there is a separate **`build-info.properties`** mechanism; manifest and build-info are two distinct metadata sources.

## 3. Main-Class and Start-Class: the core of Spring Boot

### 3.1. For a plain Java JAR

In a simple JAR where all required dependencies are on the classpath, the manifest can point directly to the class containing:

~~~java
public static void main(String[] args)
~~~

For example:

~~~text
Main-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

With a plain Java JAR, the JVM can invoke this class directly on **java -jar**, provided it is packaged in the right location and all required dependencies can be loaded.

### 3.2. For a Spring Boot 3.3 executable JAR

Spring Boot organizes application classes and runtime dependencies inside the archive using a dedicated layout:

~~~text
manifest-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/launch/
│   └── JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/manifestdemo/ManifestDemoApplication.class
    └── lib/
        ├── spring-boot-*.jar
        └── ...
~~~

In Spring Boot **3.3.x**, the manifest of an executable JAR with the standard layout must look effectively like:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

- **Main-Class** is the **Spring Boot launcher**, invoked first by the JVM on **java -jar**. The launcher sets up a classloader that understands nested dependency JARs in **BOOT-INF/lib** and application classes in **BOOT-INF/classes**.
- **Start-Class** is the **actual application entry-point class** containing **public static void main(String[] args)**. The launcher reads this header and invokes that entry point.
- The Spring Boot Maven/Gradle Plugin may add additional headers, such as **Spring-Boot-Version**, **Spring-Boot-Classes**, **Spring-Boot-Lib**, **Spring-Boot-Classpath-Index**, and **Spring-Boot-Layers-Index**. Exact values depend on plugin/version/layout; **do not alter them manually just to add business metadata**.

In Spring Boot 3.3, **changing `Main-Class` to `ManifestDemoApplication` is wrong for a default Boot JAR**, because application classes live under `BOOT-INF/classes` and dependencies live inside nested JARs. A standard JVM does not assemble that classpath the way the Spring Boot launcher does.

**Similarly, pointing `Start-Class` to a nonexistent class or one without a valid `main` method causes the launcher to fail to find the entry point.** The class name must be a **fully qualified name** including package and class name, case-sensitive.

### 3.3. Startup sequence when running `java -jar`

~~~text
java -jar manifest-demo-1.0.0.jar
                 |
                 v
JVM reads META-INF/MANIFEST.MF
                 |
                 v
Main-Class = org.springframework.boot.loader.launch.JarLauncher
                 |
                 v
Boot loader loads BOOT-INF/classes + BOOT-INF/lib
                 |
                 v
Start-Class = com.example.manifestdemo.ManifestDemoApplication
                 |
                 v
ManifestDemoApplication.main(String[])
                 |
                 v
SpringApplication.run(...)
~~~

If startup fails, inspect the stack trace to distinguish a **launcher/entry-point error**, a **missing class/dependency**, or an **application configuration error**; not every startup failure comes from the manifest.

## 4. Which attributes are safe to add, and which should be avoided?

| Attribute category | Examples | How to handle |
| --- | --- | --- |
| **Identification metadata** | Implementation-Title, Implementation-Version | Usually safe to add. |
| **Build pipeline metadata** | Build-Revision, Build-Channel, Built-By-Team | Can be added if values are non-sensitive and properly managed. |
| **Launcher entry point** | Main-Class | Let the Boot plugin manage it for default executable JARs. |
| **Application class** | Start-Class | Use Spring Boot `mainClass` configuration; avoid conflicting config sources. |
| **Spring Boot layout** | Spring-Boot-Classes, Spring-Boot-Lib | Do not edit arbitrarily; tied to how the loader locates classes/dependencies. |
| **Standard JAR classpath** | Class-Path | Usually unnecessary for Boot JARs with nested dependencies; do not use to replace `BOOT-INF/lib`. |
| **Java module metadata** | Automatic-Module-Name | Add only when you understand JPMS/consumer effects; unnecessary for this example. |
| **Package sealing / Multi-release** | Sealed, Multi-Release | Configure only when the archive actually matches that structure/behavior. |

**Version identification:** `Implementation-Version` should come from the project version rather than a hardcoded number that drifts from the POM or Gradle project version. **Build-Revision** should reflect the real built commit; this demo uses **lesson-149** so test outputs stay reproducible. Do not assign an arbitrary string and call it a real Git SHA.

## 5. One Java 17 program shared by Maven and Gradle

To keep the comparison fair, both tools build the exact same Spring Boot application. Create the source file:

**src/main/java/com/example/manifestdemo/ManifestDemoApplication.java**

~~~java
package com.example.manifestdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManifestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManifestDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner startupProof() {
        return args -> System.out.println("MANIFEST_BOOT_OK");
    }
}
~~~

This is **one complete Java file**, whose package matches its folder path. The project uses **spring-boot-starter**, so it does not start an HTTP server, requires no database, and needs no `application.properties`. When the executable JAR runs successfully, **CommandLineRunner** prints exactly one line from our code:

~~~text
MANIFEST_BOOT_OK
~~~

Spring Boot may print startup logs in addition to that line; this is **deterministic stdout produced by our program**, not the entire terminal output.

Minimal structure when choosing Maven:

~~~text
manifest-demo/
├── pom.xml
└── src/main/java/com/example/manifestdemo/ManifestDemoApplication.java
~~~

When choosing Gradle:

~~~text
manifest-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/com/example/manifestdemo/ManifestDemoApplication.java
~~~

**Choose only one build approach per exercise setup.** The Maven Wrapper or Gradle Wrapper must be generated or already present in the repository; listing wrapper filenames in a directory tree does not create working wrapper scripts by itself.

## 6. Maven: add `manifestEntries` and let Spring Boot `repackage` manage the entry point

### 6.1. Roles of the two Maven plugins

Maven involves two packaging steps:

1. **maven-jar-plugin** builds the plain JAR from classes/resources and can write additional **manifestEntries** into the input JAR's manifest.
2. **spring-boot-maven-plugin** with the **repackage** goal transforms the generated JAR into a **Spring Boot executable JAR**, rewriting loader-managed manifest sections—especially **Main-Class** and **Start-Class**—while preserving compatible extra metadata.

**Very important:** To change the entry point, use **`mainClass` in `spring-boot-maven-plugin`**. Do **not** try setting `Main-Class` or `Start-Class` in `maven-jar-plugin` to force Spring Boot to boot differently; Spring Boot `repackage` is meant to rewrite them.

When using **spring-boot-starter-parent**, the **repackage** execution is preconfigured. You only need to declare the Spring Boot plugin under `build/plugins`; you do not need to add a duplicate `repackage` execution.

### 6.2. Complete `pom.xml`

Save the following **pom.xml** at the application root:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>manifest-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <build.revision>lesson-149</build.revision>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Build the base JAR and add non-conflicting metadata. -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifestEntries>
                            <Implementation-Title>manifest-demo</Implementation-Title>
                            <Implementation-Version>${project.version}</Implementation-Version>
                            <Build-Channel>training</Build-Channel>
                            <Build-Revision>${build.revision}</Build-Revision>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>

            <!-- Repackage and manage Main-Class/Start-Class per Boot standards. -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.manifestdemo.ManifestDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**This is the complete POM** for the demo application. Breakdown of key lines:

- **project.version = 1.0.0**: application release version. **Implementation-Version** reads from this property so you do not have to maintain it in two places.
- **build.revision = lesson-149**: non-sensitive demo value. Later you can pass a real CI commit revision.
- **maven-jar-plugin > archive > manifestEntries**: adds **Implementation-Title**, **Implementation-Version**, **Build-Channel**, **Build-Revision**. These four attributes do not replace `Main-Class` or `Start-Class`.
- **spring-boot-maven-plugin > mainClass**: explicitly specifies **com.example.manifestdemo.ManifestDemoApplication** as the application entry point; the Boot plugin writes the required headers into the executable JAR manifest.
- **Plugin order in `build/plugins`**: Maven JAR Plugin is declared before the Spring Boot Plugin. Within the same `package` phase, the base JAR must be built first and then repackaged. `spring-boot-starter-parent` handles the standard `repackage` execution wiring.
- **packaging = jar**: no other layout configured, since we want the standard Spring Boot 3.3 executable JAR.

You do **not** need to add **Main-Class: org.springframework.boot.loader.launch.JarLauncher** manually in `manifestEntries`. The launcher is chosen by the Boot plugin based on the layout and version being built.

### 6.3. Maven build and artifact path

If the repository has a Maven Wrapper:

~~~bash
./mvnw clean package
~~~

If there is no wrapper but Maven is installed locally:

~~~bash
mvn clean package
~~~

On Windows, use **mvnw.cmd** instead of **./mvnw**. After a successful `package` with the sample POM, the executable archive is expected at:

~~~text
target/manifest-demo-1.0.0.jar
~~~

When no classifier is configured for `repackage`, the executable Boot JAR **replaces the main artifact**; the original JAR may remain as a **.original** file in `target`, which is not the primary deployable file. Every verification check must target **manifest-demo-1.0.0.jar** after `repackage`, never inspecting the `.original` manifest and mistaking it for the final manifest.

### 6.4. Run the Maven artifact

~~~bash
java -jar target/manifest-demo-1.0.0.jar
~~~

Stdout printed by our code:

~~~text
MANIFEST_BOOT_OK
~~~

If the launcher is missing or `Start-Class` is wrong, the app may never reach `CommandLineRunner`. Hence **java -jar** is an essential behavioral check alongside reading manifest attributes.

## 7. Gradle: `bootJar` manifest and `springBoot.mainClass` configuration

### 7.1. Distinguishing `jar` from `bootJar`

When an app applies the Java plugin and Spring Boot Gradle Plugin:

- The **jar** task creates a **plain JAR** containing regular classes/resources; with the Spring Boot Gradle plugin, `jar` usually carries the **plain** classifier to prevent filename collisions.
- The **bootJar** task creates the **executable Spring Boot JAR** with the Boot loader and nested dependencies in `BOOT-INF/lib`.
- **mainClass** in the Spring Boot Gradle Plugin can be auto-detected from source code, but if multiple `main` methods exist, specify it explicitly.
- **Extra manifest attributes must be configured on the task producing the distributed artifact**—in this case, **bootJar**.

Do not write only:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes 'Build-Channel': 'training'
    }
}
~~~

...and assume the same metadata automatically appears in the Boot JAR. **`jar` and `bootJar` are two separate tasks**, each with its own manifest and output. If metadata belongs in the executable archive, configure **`tasks.named('bootJar')`**.

### 7.2. Complete `settings.gradle`

~~~groovy
rootProject.name = 'manifest-demo'
~~~

### 7.3. Complete `build.gradle` (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}

tasks.named('bootJar') {
    manifest {
        attributes(
            'Implementation-Title': 'manifest-demo',
            'Implementation-Version': project.version.toString(),
            'Build-Channel': 'training',
            'Build-Revision': 'lesson-149'
        )
    }
}
~~~

This is a **complete Groovy DSL `build.gradle`** when paired with `settings.gradle` and the Java file in section 5. Explanation:

1. **springBoot.mainClass** provides the actual application class name, matching the Java source package/class. The Spring Boot Gradle Plugin uses this when building the executable JAR.
2. **tasks.named('bootJar')** targets the task that builds the executable archive; the **manifest** block comes from Gradle's `Jar` task API.
3. **attributes(...)** adds the four custom headers, **without setting `Main-Class`** or **`Start-Class`**.
4. **project.version.toString()** links `Implementation-Version` to the project version.
5. **gradlePlugin version 3.3.5** is the Spring Boot build plugin version; **project.version 1.0.0** is the application version; they are two different things.
6. Java toolchain 17 targets the relevant Java tasks; the JVM running Gradle itself must still be compatible with your Gradle and plugin versions.

With Boot 3.3 and standard JAR layout, the plugin automatically sets **Main-Class** to Boot's `JarLauncher` and **Start-Class** to the chosen `mainClass`.

### 7.4. Alternative: set `mainClass` directly on `bootJar`

In some builds you only want to set the entry point for the `bootJar` task rather than project-wide; you can use this block **instead of the `springBoot` block above**:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}
~~~

If you also need metadata, place **mainClass** together with **manifest attributes** inside **one** `bootJar` block:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
    manifest {
        attributes(
            'Implementation-Title': 'manifest-demo',
            'Implementation-Version': project.version.toString(),
            'Build-Channel': 'training',
            'Build-Revision': 'lesson-149'
        )
    }
}
~~~

This is an **alternative snippet**, not a standalone file. Do not set **springBoot.mainClass** to a different value from **bootJar.mainClass**, as that creates two conflicting sources of truth. In Gradle 8.5 / Spring Boot 3.3, the DSL also lets you set **Start-Class** inside `bootJar`'s manifest, but **using the `mainClass` property is clearer and less error-prone**.

### 7.5. Build and run the Gradle artifact

From the root containing the Gradle Wrapper:

~~~bash
./gradlew clean bootJar
~~~

Or to run standard verification tasks as well:

~~~bash
./gradlew clean build
~~~

On Windows use **gradlew.bat**. With `settings.gradle` and the version from section 7, the expected default executable file is:

~~~text
build/libs/manifest-demo-1.0.0.jar
~~~

When running **build**, a plain JAR may also be produced:

~~~text
build/libs/manifest-demo-1.0.0-plain.jar
~~~

**Do not inspect `-plain.jar` to evaluate the Boot JAR manifest**. The `-plain` file serves a different purpose and lacks the Boot loader layout. Run the executable:

~~~bash
java -jar build/libs/manifest-demo-1.0.0.jar
~~~

Stdout printed by Java code:

~~~text
MANIFEST_BOOT_OK
~~~

## 8. Expected final manifest contents

Whether you choose Maven or Gradle, in a **standard Spring Boot 3.3 executable JAR**, the key attributes are expected to look like this (actual line order may vary):

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.manifestdemo.ManifestDemoApplication
Implementation-Title: manifest-demo
Implementation-Version: 1.0.0
Build-Channel: training
Build-Revision: lesson-149
~~~

This is an **illustrative excerpt of fields to verify**, not the entire raw manifest. The Spring Boot Plugin may add `Spring-Boot-Version`, `Spring-Boot-Classes`, `Spring-Boot-Lib`, and other headers; the JAR archiver may also wrap long lines per the manifest specification.

**PASS criteria mean more than just "`Build-Channel` was added."** At minimum verify:

- `Main-Class` is the Boot launcher matching the Boot version and layout.
- `Start-Class` is the exact fully qualified application main class.
- `Implementation-Title`/`Version` and `Build-Channel`/`Revision` match expected values.
- **BOOT-INF/classes/** actually contains the application class and **BOOT-INF/lib/** contains runtime dependencies.
- **java -jar** launches the application cleanly, not merely printing metadata.

## 9. Hands-on manifest verification in Java 17

Because manifests can undergo **line wrapping**, we use the standard Java APIs **java.util.jar.JarFile**, **Manifest**, and **Attributes**. This test reads the **final archive file** without relying on line order or a specific Unix utility.

Place **ManifestVerifier.java** at the **project root** (next to `pom.xml` or `build.gradle`); do **not** put it inside `src/main/java`, so you do not turn a verification tool into part of the application.

~~~java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ManifestVerifier {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ManifestVerifier.java <executable.jar>");
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing manifest");
            }

            Attributes attrs = manifest.getMainAttributes();
            expect(attrs, "Main-Class",
                    "org.springframework.boot.loader.launch.JarLauncher");
            expect(attrs, "Start-Class",
                    "com.example.manifestdemo.ManifestDemoApplication");
            expect(attrs, "Implementation-Title", "manifest-demo");
            expect(attrs, "Implementation-Version", "1.0.0");
            expect(attrs, "Build-Channel", "training");
            expect(attrs, "Build-Revision", "lesson-149");

            String appClass =
                    "BOOT-INF/classes/com/example/manifestdemo/"
                    + "ManifestDemoApplication.class";
            if (jar.getEntry(appClass) == null) {
                throw new IllegalStateException(
                        "App class missing: " + appClass);
            }
        }

        System.out.println("MANIFEST_OK");
    }

    private static void expect(
            Attributes attrs, String key, String expected) {
        String actual = attrs.getValue(key);
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    key + ": expected " + expected + " but was " + actual);
        }
    }
}
~~~

**This is a complete Java file** compatible with Java 17. It checks manifest metadata and verifies the application class sits properly inside the Boot layout. When an attribute is wrong or the class is missing, the program throws an exception and exits non-zero—ideal as a CI gate.

### 9.1. Verify the Maven executable JAR

~~~bash
./mvnw clean package
java ManifestVerifier.java target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar
~~~

**java ManifestVerifier.java** uses the **Java single-file source-code launcher** introduced in Java 11, requiring no prior `javac` step. A sufficiently recent JDK/JVM is required.

If manifest and layout are valid, **stdout from the verifier program alone** is:

~~~text
MANIFEST_OK
~~~

**The `java -jar` command on the next line** is a separate check; when startup succeeds, the application prints:

~~~text
MANIFEST_BOOT_OK
~~~

Do not claim the entire terminal displays only those two lines, since Maven and Spring Boot emit additional logs.

### 9.2. Verify the Gradle executable JAR

~~~bash
./gradlew clean bootJar
java ManifestVerifier.java build/libs/manifest-demo-1.0.0.jar
java -jar build/libs/manifest-demo-1.0.0.jar
~~~

The verifier must likewise print **MANIFEST_OK**, and the application prints **MANIFEST_BOOT_OK**. Only the build tool and artifact path differ; expected attributes are intentionally identical.

### 9.3. Manually reading the manifest with JDK tools

The command:

~~~bash
jar tf target/manifest-demo-1.0.0.jar
~~~

lists entries of the Maven archive. For Gradle, switch the path to **build/libs/manifest-demo-1.0.0.jar**. The list must contain **META-INF/MANIFEST.MF** and **BOOT-INF/classes/com/example/manifestdemo/ManifestDemoApplication.class**.

If you need to open the manifest manually, move into an **empty temporary directory** and run **`jar xf <absolute-path-to-JAR> META-INF/MANIFEST.MF`**, then read the extracted file. **Do not run `jar xf` directly in the project root if you do not want a `META-INF` folder created there.** On Unix environments with `unzip`, you can view it without extracting to disk via `unzip -p` with the entry path.

**Why still use `ManifestVerifier`?** A long value can span multiple physical lines in `MANIFEST.MF`, whereas **`Attributes.getValue`** returns the logical value unfolded per specification.

## 10. Injecting a real build revision during CI runs

In the example, `Build-Revision` is fixed to **lesson-149** for deterministic output. In production projects, the revision should come from the CI checkout commit rather than a manually typed SHA.

### 10.1. Maven: use a project property

The POM in section 6 already has:

~~~xml
<properties>
    <build.revision>lesson-149</build.revision>
</properties>
~~~

and `manifestEntries`:

~~~xml
<Build-Revision>${build.revision}</Build-Revision>
~~~

These are **two fragments inside the POM**, not two new POMs. In CI, pass the property at build time:

~~~bash
./mvnw -Dbuild.revision=abc123 clean package
~~~

Here **abc123 is purely an illustrative value**. Changing `build.revision` updates **Build-Revision** in the manifest accordingly. **ManifestVerifier.java** in section 9 currently expects **lesson-149**, so if you intentionally build with `abc123`, **update the expected revision in the verifier or pass the expected revision into the check tool**. Never conclude a build is broken just because hardcoded test expectations were not updated for new inputs.

Keep version/revision policies consistent across artifacts, CI logs, and deployment metadata. Never inject credentials, secrets, or tokens into the manifest through properties.

### 10.2. Gradle: use `gradle.properties` or `-P`

In the Gradle approach, replace:

~~~groovy
'Build-Revision': 'lesson-149'
~~~

with:

~~~groovy
'Build-Revision': providers.gradleProperty('buildRevision')
        .orElse('lesson-149').get()
~~~

This is a **fragment inside `attributes(...)`** of the `bootJar` block. Using **providers.gradleProperty** allows Gradle to read the property from **gradle.properties** or **`-P`** on the command line. For example:

~~~bash
./gradlew -PbuildRevision=abc123 clean bootJar
~~~

When no property is passed, the revision defaults to **lesson-149**, matching the verifier in section 9. When `abc123` is passed, the verifier must compare against `abc123`.

**You do not need to shell out to `git` directly during Gradle configuration** just to obtain a revision if CI already provides the SHA. Avoid depending on current wall-clock time or local usernames that hurt build reproducibility unnecessarily.

## 11. Differences when an application has multiple `main` classes

A Java project may contain multiple **main** methods, such as **ManifestDemoApplication** and **DataMigrationCli**. The build tool may not know which class to pick, or auto-detection may pick the unintended one.

For **Maven Spring Boot**, specify explicitly:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.manifestdemo.ManifestDemoApplication</mainClass>
    </configuration>
</plugin>
~~~

For **Gradle Spring Boot**:

~~~groovy
springBoot {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}
~~~

Both examples are **fragments**, not complete POM/`build.gradle` files. They ensure the archive's entry point is configured in a way the Boot plugin understands, rather than forcing an arbitrary:

~~~text
Main-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

expecting the JVM to invoke the app class directly from a Boot archive. If a build must produce **multiple executable JARs with different entry points**, configure **multiple archive tasks/executions**, distinct classifiers, and separate `mainClass` settings so two tasks never overwrite the same file; do not simply edit one header on an already-repackaged artifact.

### 11.1. Spring Boot Kotlin application

If a Kotlin file `ExampleApplication.kt` defines a top-level **main** function, the JVM typically generates class **ExampleApplicationKt**. To configure `mainClass` accurately, use the **actual JVM class name**, not just the Kotlin source filename. This is a cross-language note; our main example uses Java 17, so **ManifestDemoApplication** matches directly.

### 11.2. `PropertiesLauncher` and non-JAR layouts

Spring Boot also offers **PropertiesLauncher** and other layouts (e.g., Maven `ZIP`/`DIR`). When switching layouts, **Main-Class may differ from `JarLauncher`**. Because this lesson covers Boot 3.3's **default JAR layout**, we keep the default layout and launcher unchanged.

**If you have special requirements for an external loader path**, use the launcher/layout features supported by the Boot plugin and test them specifically. Never "tweak `Main-Class` blindly" in the manifest until the JAR happens to start, as doing so can break nested library loading or bypass required loader rules.

## 12. Manifest differences between a plain JAR and a Boot JAR

A Spring Boot build can emit two outputs that both contain `META-INF/MANIFEST.MF`:

| Attribute | Plain JAR | Executable Boot JAR |
| --- | --- | --- |
| Application class location | Normally directly under package paths | `BOOT-INF/classes` |
| Runtime dependencies | Normally lacks nested runtime libraries | `BOOT-INF/lib` |
| `Main-Class` | May be absent or point to app if configured | Boot `JarLauncher` for default layout |
| `Start-Class` | Not required | Points to actual application main class |
| `Implementation-Title`/`Version` | Present if configured | Present if configured |
| Run with `java -jar` as standalone Boot app | Not guaranteed | Yes, when packaged with valid entry point |

**Maven:** Spring Boot `repackage` without a classifier typically replaces the main JAR with the executable archive and leaves **.original** locally. Never inspect **.original** mistaking it for the Boot artifact.

**Gradle:** the Spring Boot plugin may produce **manifest-demo-1.0.0-plain.jar** from `jar` and **manifest-demo-1.0.0.jar** from `bootJar`. This lesson adds custom attributes only to **`bootJar`'s manifest**; do not assume the plain JAR receives them.

If both artifacts need identical metadata, configure both **`jar` and `bootJar`** appropriately and inspect both files. However, **never force a plain JAR to set `Main-Class` to `JarLauncher`** when it lacks the Boot loader layout.

**Selecting the right file in CI/CD:** Avoid globs like **`build/libs/*.jar`** when both plain and Boot JARs exist, or you risk picking the wrong file. Use a known path or Gradle's **`bootJar.archiveFile`** provider. When renaming or changing versions, update the pipeline and inspect the actual artifact.

## 13. Manifest vs. `build-info.properties` and other metadata sources

When version/revision data is needed for diagnostics, several options exist:

1. **JAR manifest**: metadata in `META-INF/MANIFEST.MF`, readable via **JarFile**. Suited for inspecting an archive offline or auditing release packages.
2. **Spring Boot build-info**: build details in **META-INF/build-info.properties** when enabling Maven goal **spring-boot:build-info** or Gradle task **bootBuildInfo**. This is a separate file, not the manifest.
3. **Environment variables / Spring properties**: runtime configuration varying per environment, such as profiles or external endpoints.
4. **Container image labels / CI metadata**: commit/build info at the image or pipeline level, aiding source traceability.

**Do not confuse them:** Adding **Implementation-Version** to the manifest **does not automatically make** **`/actuator/info`** expose the build version. Actuator has its own `InfoContributor` and build-info mechanisms; exposing metadata over HTTP requires proper endpoint configuration while guarding against leaking internal details publicly.

For this lesson's goals, we use **`manifestEntries` / `bootJar.manifest`** and inspect directly via `JarFile`; there is no need to add Actuator merely to read a JAR.

## 14. Notes on manifest formatting and build reproducibility

### 14.1. Headers and line length

Manifest attribute names follow naming and length rules in the JAR specification. Choose short, readable headers like **Build-Revision**, **Build-Channel**, and **Implementation-Title**. Long values can be wrapped onto continuation lines starting with a single space. Do not edit `MANIFEST.MF` with naive string concatenation that breaks section boundaries, line breaks, or encoding.

**The proper check** reads logical values via **`Manifest.getMainAttributes().getValue(...)`** as in this lesson's Java verifier. Notably, manifests can contain **named sections** for individual entries: archive-wide build metadata belongs in **main attributes**, not accidentally placed under a file-specific section.

### 14.2. Archive integrity and signed builds

When a JAR is signed, the manifest and signatures are tied to archive contents. Altering the manifest **after signing** can invalidate signature verification. The safe workflow is **configure metadata in the build script → build JAR → verify → sign/publish in the pipeline**. Never open a production JAR in a ZIP tool to edit the manifest manually as a "quick fix."

### 14.3. Avoid unnecessary dynamic timestamps

Writing a real-time `Build-Time` on every build changes the JAR checksum even when code has not changed. If reproducible builds are required, use the archive timestamp/ordering settings supported by Maven/Gradle/Spring Boot and store build timestamps in separate CI metadata. With fixed **Build-Revision** and version, this lesson produces stable metadata across repeated runs on the same inputs.

### 14.4. Security scope

**Never store passwords, access tokens, private URLs with credentials, or customer data** in the manifest. Anyone holding the artifact can extract `META-INF/MANIFEST.MF` without running the application. Build agent hostnames or local user paths may also be unnecessary metadata to expose; choose only fields that genuinely aid traceability.

## 15. Common errors and troubleshooting

**Error 1 — `Main-Class` points directly to the application class in a Boot JAR.** Under Boot 3.3's default JAR layout, the JVM needs Boot's `JarLauncher` to handle `BOOT-INF/lib`. Remove manual `Main-Class` overrides from `maven-jar-plugin` or `bootJar.manifest` and let the Boot plugin configure the launcher.

**Error 2 — `Start-Class` has the wrong package/class name.** Check the package in the Java file and the fully qualified name in **`spring-boot-maven-plugin.mainClass`** or **`springBoot.mainClass`**; run **`jar tf`** to confirm `BOOT-INF/classes` holds the `.class` file.

**Error 3 — Maven `manifestEntries` has `Build-Revision` yet the final artifact lacks it.** Check whether **`repackage`** ran, verify you are inspecting the target JAR (not `.original`), and verify plugin configuration under **`build/plugins`**. If custom executions exist, check the order of JAR creation vs. repackage in the build log.

**Error 4 — Gradle added metadata to `jar` while you inspected `bootJar`.** They are separate tasks. Move metadata configuration to **`tasks.named('bootJar')`** if it belongs in the executable archive; rebuild and re-read the right file.

**Error 5 — Set `Main-Class` via Maven JAR Plugin and saw Spring Boot replace it.** That is intentional behavior of Boot `repackage`. To change the application main class, set **`spring-boot-maven-plugin.mainClass`** instead of trying to stop the plugin from setting `Main-Class`.

**Error 6 — Multiple `main` methods exist and the plugin picked the wrong one.** Declare `mainClass` explicitly in the build rather than relying on auto-detection.

**Error 7 — Running Java throws `ClassNotFoundException` or `NoClassDefFoundError`.** It is not always the manifest: distinguish classloader issues, `Start-Class`, nested dependencies, dependency scopes, and the JDK runtime. Inspect `BOOT-INF/classes`, `BOOT-INF/lib`, Java version, and the stack trace.

**Error 8 — Read `META-INF/MANIFEST.MF` and failed to find a long value via `grep`.** Manifests can wrap lines; use **`java.util.jar.Manifest`** to read logical values.

**Error 9 — Added `Class-Path` listing nested JARs.** Boot `JarLauncher` handles nested libraries automatically. Standard manifest `Class-Path` usually does not replace `BOOT-INF/lib`. Let Spring Boot manage the loader classpath.

**Error 10 — `Implementation-Version` differs from `project.version`.** Avoid wrong hardcoded values; in Maven use **`project.version`**, in Gradle use **`project.version.toString()`** or an explicit `Provider`.

**Error 11 — CI changes `Build-Revision` while the verifier still expects `lesson-149`.** Keep expected values aligned with build inputs; pass the expected revision into the gate when it changes per commit.

**Error 12 — Gradle produces two JARs and CI picks `-plain.jar`.** Never assume every `.jar` file is executable. Select `bootJar` output, check `Main-Class`/`Start-Class`, and test with `java -jar`.

**Error 13 — Set `Start-Class` in the manifest and `mainClass` property to two different classes.** A plugin or task may prioritize one or overwrite the other; keep **a single source of truth for the entry point** and inspect the final manifest.

**Error 14 — Repackaged with `ZIP`/`PropertiesLauncher` layout while the verifier expects `JarLauncher`.** This lesson's example targets the standard JAR layout. When changing layouts, update the expected `Main-Class` accordingly instead of hardcoding `JarLauncher` for every Boot archive.

**Error 15 — Edited the manifest with `unzip`/`zip` post-build without re-testing.** You can invalidate signatures, checksums, Boot archive alignment, or metadata. Edit Maven/Gradle configuration and rebuild cleanly.

**Error 16 — Assumed `Implementation-Title` in the manifest automatically becomes a Spring property.** Spring `Environment` does not auto-import JAR manifest entries as `application.properties`. If code needs to read it, use the appropriate API or configure `build-info`.

**Error 17 — JAR runs on a laptop yet fails in a container.** Check container Java runtime, source compatibility, paths, environment variables, runtime dependencies, and ensure the Dockerfile copies the Boot JAR. A valid manifest is only one startup requirement.

**Error 18 — Spring Boot plugin never runs `repackage`.** In Maven without the starter parent, bind the **`repackage`** execution to the lifecycle; in Gradle without the Boot plugin applied, `bootJar` does not exist. Verify which tasks/goals actually execute.

**Error 19 — Custom header contains secret data.** The manifest is readable metadata. Remove secrets and use a secret manager or runtime configuration.

**Error 20 — Changed Spring Boot version while keeping the old launcher name in custom scripts.** Loader implementation and package paths can change across versions. In this lesson, **`org.springframework.boot.loader.launch.JarLauncher`** is specific to Boot 3.3; do not assume it holds for all older or newer Spring Boot versions.

## 16. Pre-release checklist

- [ ] Clearly confirmed the distributed artifact is the **Spring Boot executable JAR**, not a plain JAR.
- [ ] Selected extra manifest attributes that do not conflict with loader metadata.
- [ ] Maven: placed metadata in **`maven-jar-plugin.archive.manifestEntries`**.
- [ ] Maven: set entry point via **`spring-boot-maven-plugin.mainClass`**; ensured `repackage` runs after the base JAR is built.
- [ ] Gradle: added metadata in **`bootJar.manifest`**, not only `jar.manifest`.
- [ ] Gradle: set entry point via **`springBoot.mainClass`** or **`bootJar.mainClass`**.
- [ ] Verified final `Main-Class` and `Start-Class` match the Boot **version and layout**.
- [ ] Built cleanly with `clean package`/`bootJar`; read the actual final artifact.
- [ ] Ran **`ManifestVerifier.java`** (or equivalent tool) to verify exact metadata and Boot layout.
- [ ] Executed **`java -jar`** and confirmed the application actually runs.
- [ ] Stored no secrets in the manifest; linked version/revision to CI metadata.
- [ ] If manifest changes after JAR signing, rebuilt/re-signed via the proper pipeline.
- [ ] In CI/CD, configured the pipeline to fail if the verifier or `java -jar` smoke test fails.
- [ ] Did not declare a build valid solely from spotting `Main-Class` in a raw manifest dump.

## 17. Official references

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Specification, Launching: https://docs.spring.io/spring-boot/3.3/reference/executable-jar/launching.html
- Apache Maven JAR Plugin — Manifest Customization: https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html
- Apache Maven Archiver — Manifest Configuration: https://maven.apache.org/shared/maven-archiver/examples/manifest.html
- Gradle — Jar Task API: https://docs.gradle.org/8.5/dsl/org.gradle.jvm.tasks.Jar.html
- Java SE — `java.util.jar.Manifest` / `Attributes` / `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html

**Conclusion:** In a Spring Boot 3.3 executable JAR, **`Main-Class` is the Boot launcher** and **`Start-Class` is the application entry point**. Maven lets you add metadata via **`maven-jar-plugin.manifestEntries`** and let **`spring-boot:repackage`** manage startup headers; Gradle adds metadata to **`bootJar.manifest`** and sets the application main class via **`springBoot.mainClass`/`bootJar.mainClass`**. Always verify **the final JAR's manifest + `BOOT-INF` structure + `java -jar`** before publishing an artifact.