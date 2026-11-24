# When You Need requiresUnpack or Plugin Unpack Configuration in Spring Boot Loader

## 1. Lesson Objectives

A Spring Boot executable JAR typically places dependency JARs inside the application JAR itself: `BOOT-INF/lib/library.jar`. Spring Boot Loader can load classes and resources directly from the **nested JAR** structure without extracting every dependency to disk. This is the default capability and works well for most Java libraries.

However, some third-party libraries do not rely solely on Java class loading. They open their own JAR file using a `java.io.File` path, use their own ZIP reader, require a JAR with a physical path, or perform internal operations that do not understand nested JAR URLs. In those **verified** cases, Spring Boot packaging plugins provide the `requiresUnpack` mechanism to mark dependencies that must be **extracted to a temporary directory when launched via Spring Boot Loader**.

After this lesson, you will be able to:

- Explain how Spring Boot Loader loads nested JARs and why unpacking is **not needed** by default.
- Recognize real symptoms showing a library **must have an actual JAR file on the filesystem**.
- Distinguish `requiresUnpack` from `exclude`, unpacking the entire executable archive, ZIP compression, and Maven/Gradle dependency resolution.
- Configure `requiresUnpack` accurately in **Gradle Groovy DSL**, **Gradle Kotlin DSL**, and **Spring Boot Maven Plugin**.
- Know that the Gradle pattern matches **the absolute path of the source dependency JAR**, not a Java package or an arbitrary runtime name.
- Verify effectiveness via the final artifact, running `java -jar`, and appropriate tests; avoiding false positives from running only `bootRun` or an IDE.
- Troubleshoot temp directory permissions, container environments, and dependency paths without unnecessarily unpacking everything.

**Scope:** Spring Boot executable JARs/WARs, Spring Boot Loader, and packaging configuration. Examples use Spring Boot 3.3.13 and Java 17 as a consistent baseline; these are illustrative versions, not claims about the latest Spring Boot release.

## 2. Background Mechanism: Boot Loader Reading Nested JARs

### 2.1. Why Does an Executable Spring Boot JAR Differ in Structure from a Plain JAR?

With Spring Boot Gradle `bootJar` or Maven `spring-boot:repackage`, a typical executable JAR structure is:

~~~text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/demo/DemoApplication.class
    └── lib/
        ├── spring-boot-3.3.13.jar
        ├── spring-context-....jar
        └── some-library-1.2.3.jar
~~~

This is a general structure; library names and counts depend on the dependency graph, plugin configuration, and versions. A regular JAR built by the Java plugin's `jar` task may contain only the module's classes/resources, without the `BOOT-INF` layout or Boot Loader.

Typical manifest of a Spring Boot 3.3 executable JAR:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

`Main-Class` is Spring Boot's launcher; `Start-Class` is the application. When running:

~~~bash
java -jar app.jar
~~~

the JVM invokes the Boot launcher; the loader prepares a class loader able to read nested dependency JARs from `BOOT-INF/lib` and then calls the application. Standard Java class loaders do not automatically understand every nested JAR URL form, so Spring Boot supplies its own loader mechanism.

### 2.2. Normally There Is No Bulk Extraction Step

Spring Boot Loader supports reading nested JAR contents by seeking within the outer archive. Dependency JARs sit inside the outer JAR in a loader-supported layout; normally there is no need to create separate external files for each dependency.

Two-flow diagram:

~~~text
Normal case:
app.jar
  └─ BOOT-INF/lib/library.jar
      └─ Spring Boot Loader reads nested JAR directly
          └─ classes/resources loaded into application

Library marked requiresUnpack:
app.jar
  └─ BOOT-INF/lib/problem-library.jar
      └─ Spring Boot Loader extracts that JAR to a temp location
          └─ runtime can use the JAR copy on the filesystem
~~~

Distinguish two points in time:

- **Build time:** the Gradle/Maven plugin packages the executable archive and records that certain nested dependencies need unpacking.
- **Runtime:** when the executable archive is launched via Spring Boot Loader, the loader processes the marked dependencies.

Thus `requiresUnpack` **does not mean Gradle/Maven extracts source JARs into `build/libs` or `target` at build time**. Nor does it mean it creates a permanent `lib` directory next to `app.jar`.

### 2.3. Nested JARs Require Proper ZIP Formatting

Per the Spring Boot executable JAR specification, the ZIP entry holding a **nested JAR** must be stored using `STORED` in the outer archive so the loader can seek directly. Inside the nested JAR, individual entries can remain normally compressed.

This is an **archive format** requirement, distinct from `requiresUnpack`:

- `STORED`: how the nested JAR entry is stored in the outer ZIP, enabling direct reading by the loader.
- `requiresUnpack`: decides whether a specific dependency needs **a real file on disk at runtime**.

If an archive is improperly repacked so nested JAR entries no longer conform to Boot's format, setting `requiresUnpack` is not the right fix. Use the proper Spring Boot packaging plugin and avoid manually altering the ZIP with tools that strip metadata/layout.

## 3. When Is `requiresUnpack` Actually Needed?

A normal Java library that only consumes classes/resources via the context class loader, `getResourceAsStream`, or compatible JAR URL APIs generally **does not need** unpacking.

Consider `requiresUnpack` when there is **evidence** the library needs to operate directly on a JAR file on the filesystem, such as:

1. The library opens its own JAR using `File` or `Path` and expects `File.exists()` to be true for a standalone JAR.
2. The library has its own class loader, ZIP/JAR parser, or native bridge that **does not understand Boot nested URLs**.
3. An internal component of the library requires opening a JAR file via an API that only accepts a filesystem path.
4. Official documentation of the library or Spring Boot recommends marking that exact dependency to unpack when run inside an executable Boot archive.
5. You can reproduce the failure only under `java -jar` on the executable archive, while running via an IDE/Gradle `bootRun` succeeds because dependencies are physical JAR files on disk.

**Example from Spring Boot documentation:** `JRuby`/`jruby-complete` has its own nested-archive handling and assumes `jruby-complete.jar` exists directly on the filesystem. Spring Boot cites this case as an example for `requiresUnpack`. Do not generalize that *every* JRuby version or *every* app using JRuby will definitely fail; check your actual dependency and version.

### 3.1. Indicators Are Only Hints

The table below helps narrow down causes, not as a set of automatic rules:

| Indicator | Possibly related to unpack? | Check before concluding |
| --- | --- | --- |
| `ClassNotFoundException` on `java -jar` | Possibly, among many other causes | Confirm dependency is in `BOOT-INF/lib`/`WEB-INF/lib` and runtime scope |
| `FileNotFoundException` with path containing `jar:nested:...` | Possibly | Check whether the library is converting JAR URLs to `File` |
| Library reports "JAR must be on filesystem" | Likely relevant | Identify the exact artifact and whether the library supports nested URLs |
| `UnsatisfiedLinkError` | Insufficient by itself | Check native library packaging, OS/ABI, `java.library.path`, filesystem permissions |
| `bootRun` succeeds, `java -jar` fails | Requires investigating nested-JAR behavior | Compare classpath, JVM, profiles, external config, and executable artifact |
| Dependency fails to download from repository | No | This is a dependency resolution/repository error, not unpack |
| Missing `Main-Class`/`Start-Class` | No | This is an executable packaging/entry point error |
| Want to shrink JAR size | No | Runtime unpacking does not remove dependencies from the archive |
| Just want smaller Docker images | No | Look at layers, image builds, and dependency trimming |
| App needs external config file | Usually no | Use Spring externalized configuration, not dependency JAR unpacking |
| Library needs to write files inside the JAR | Not necessarily solved | The JAR artifact remains a read-only archive; a separate writable directory is needed |

Rule: **mark only the exact library exhibiting the limitation**, based on reproduction or vendor documentation. Do not enable unpacking for all of `BOOT-INF/lib` "just to be safe".

### 3.2. Why Can Running in an IDE Mask the Bug?

When running from an IDE, Gradle `bootRun`, or Maven `spring-boot:run`, dependencies are usually already physical files in the Gradle/Maven cache, such as `.../caches/modules-2/files-2.1/.../library.jar` or `.../.m2/repository/.../library.jar`.

When packaged as a Boot executable JAR, the same dependency is nested inside `BOOT-INF/lib`. If a library extracts its location as a `File`, it may work in the IDE yet fail on a nested URL.

Hence **the decisive test** is running the executable archive itself via Boot Loader:

~~~bash
java -jar path/to/app.jar
~~~

You cannot fully verify `requiresUnpack` with `bootRun` alone; that task does not fully mirror the nested archive behavior of the released artifact.

## 4. What `requiresUnpack` Is Not

| Mechanism | Effect | Does it replace `requiresUnpack`? |
| --- | --- | --- |
| Gradle/Maven dependency declaration | Adds library to dependency graph and runtime classpath | No: having the library present does not tell the loader to unpack it |
| `requiresUnpack` | Marks nested dependency to be extracted when Boot Loader starts | Right mechanism for "requires physical JAR file" errors |
| Plugin `exclude`/`excludes` | Drops dependencies from the executable archive by rule | No: dropping the library can leave the app missing classes |
| Gradle `zipTree`/Maven Shade | Can extract/merge JAR contents at build time | Not equivalent and risks class/resource collisions |
| `jar -xf app.jar` | Manually extracts the archive where you choose | Does not mark libraries for Boot Loader to unpack |
| `java -Djarmode=tools -jar app.jar extract` | Extracts executable JAR in a Spring Boot supported layout for deployment | Different: extracts the whole application rather than selecting individual libraries |
| Layered JAR / `layers.idx` | Describes layers to aid caching in image builds | No |
| `launchScript()` / fully executable JAR | Prepends a shell launch script to run the archive directly on supported platforms | No |
| PropertiesLauncher `loader.path` | Customizes library/classpath locations when using that launcher | Does not automatically solve every library needing a physical JAR file |

**The keyword "unpack" has multiple meanings.** In this lesson, `requiresUnpack` means **an exception config telling Spring Boot Loader to unpack a specific dependency at launch**, not extracting the entire post-build artifact.

## 5. Gradle Groovy DSL: Configuring `bootJar.requiresUnpack`

### 5.1. Complete Build Without Special Dependencies

Create a single-module Java/Spring Boot project; file `settings.gradle`:

~~~groovy
rootProject.name = 'unpack-demo'
~~~

File `build.gradle`:

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This is a **standalone build script** for the baseline example. It includes the Spring Boot plugin, Java plugin, Java toolchain, and dependency management aligned with Spring Boot 3.3.13. No library in the baseline example needs unpacking, so **not declaring `requiresUnpack` is the right choice**.

The Gradle wrapper (`gradlew`, `gradle/wrapper`) must be generated/present from the project setup; `build.gradle` does not generate the wrapper by itself.

### 5.2. Official `requiresUnpack` Fragment

When a specific dependency is confirmed to need a physical JAR file, Spring Boot 3.3 uses this syntax for Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

This is an **additional fragment for `build.gradle`**, not a standalone build script. It only affects dependency JARs that actually appear in the packaged classpath and match the pattern.

To illustrate combining it with a real JRuby dependency if the project **uses JRuby**, you can declare:

~~~groovy
dependencies {
    implementation 'org.jruby:jruby-complete:9.4.6.0'
}

tasks.named("bootJar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

These two blocks are **situational fragments**, not a requirement to add JRuby to the baseline example. The JRuby version here merely represents dependency coordinates, not an upgrade/downgrade recommendation; real projects must verify compatible versions, repositories, CVEs, and actual usage needs.

`requiresUnpack '**/jruby-complete-*.jar'` uses an **Ant-style path pattern**. Per Spring Boot 3.3 documentation, the matcher applies to **the absolute path of the source dependency JAR file** at packaging time. `**/` matches directory levels, and `*` matches variable parts like version in the filename. A name like `jruby-complete-9.4.6.0.jar` can match if the actual file has a matching name and path.

### 5.3. Do Not Use a Java Package as the Pattern

The following patterns are erroneous or risky examples:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack 'org/jruby/**'  // Wrong intent: this is a package/classes name
    requiresUnpack '*.jar'         // Too broad, may capture many libraries
}
~~~

The target is not finding `org/jruby` **inside** the nested archive; the matcher targets **the source JAR file** resolved from the Gradle dependency graph. Use a sufficiently narrow JAR name pattern, such as `**/jruby-complete-*.jar`, and verify the exact file selected. A broad pattern can cause runtime extraction of batches of dependencies, adding unnecessary I/O and temporary filesystem reliance.

**Note:** the "wrong" snippet above is only for recognizing design mistakes; **do not copy it into a project you are learning with**.

### 5.4. Using a Closure When Advanced Conditions Are Needed

The Spring Boot Gradle Plugin supports an overload taking a closure as a predicate. The closure receives a `FileTreeElement` and returns a `boolean`, letting you select dependencies by file path/filename.

Illustrative Groovy fragment:

~~~groovy
tasks.named("bootJar") {
    requiresUnpack { element ->
        element.file.name.startsWith('jruby-complete-') &&
            element.file.name.endsWith('.jar')
    }
}
~~~

This helps when the matcher requires more precise logic than an Ant pattern. In return, it complicates build logic. In most cases, an explicit pattern is easier to read and maintain. Never write closures relying on a single developer's specific cache folder name, since Gradle cache paths vary across machines.

**Distinction:** the closure/predicate is evaluated when the plugin decides which files to mark in the artifact; it does not mean the Java/Groovy closure is packaged to run at runtime.

## 6. Gradle Kotlin DSL: Equivalent Configuration

### 6.1. Working Kotlin Build

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "unpack-demo"
~~~

File `build.gradle.kts`:

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
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

This matches the Groovy setup in Section 5.1: builds a Boot executable JAR, requiring no unpacking for any library in the baseline example. Kotlin DSL is the **build script language** and does not force you to write the application in Kotlin; the Java class in Section 8 works identically.

### 6.2. Exact `requiresUnpack` Fragment

At the **top of `build.gradle.kts`**, add the import (outside all blocks):

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
~~~

Then configure the task:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

This is the syntax documented for Spring Boot 3.3: `BootJar` is the task type, and `requiresUnpack(...)` is the method taking a pattern string.

If the project actually uses JRuby, the matching dependency goes into `dependencies`:

~~~kotlin
dependencies {
    implementation("org.jruby:jruby-complete:9.4.6.0")
}
~~~

Do not drop sample dependency versions into a real system without checking version/resolution/compatibility. Add `requiresUnpack` only for identified dependencies without altering the rest of the classpath.

In Kotlin DSL, `tasks.named("bootJar")` does not always give you `BootJar`'s typed API when referencing a generic task. `tasks.named<BootJar>("bootJar")` informs the compiler of the task type so it recognizes the method.

### 6.3. Configuring Multiple Dependencies

If **two libraries genuinely require physical files**, you can add two specific patterns:

**Groovy:**

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/legacy-engine-*.jar'
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/legacy-engine-*.jar")
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

`legacy-engine` here is an **illustrative placeholder name** and does not represent a real library; keep it only when your project has an actual artifact and evidence. Do not add both by template if only one dependency is problematic.

## 7. Maven: How Does `spring-boot-maven-plugin` Configure Unpacking?

Maven has no Gradle task named `bootJar`. In Maven, the Spring Boot Maven Plugin uses the `repackage` goal, which has a `requiresUnpack` parameter accepting a **list of dependencies** to extract at runtime.

Unlike Gradle:

- Gradle selects dependency files via an **Ant-style pattern** matching the absolute source JAR path.
- Maven selects dependencies by **`groupId` and `artifactId`** coordinates inside the `requiresUnpack` configuration.

### 7.1. Maven Fragment for JRuby

In `pom.xml` of a Maven application that already has the Spring Boot parent/plugin, configure:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <requiresUnpack>
                    <dependency>
                        <groupId>org.jruby</groupId>
                        <artifactId>jruby-complete</artifactId>
                    </dependency>
                </requiresUnpack>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is an **XML fragment** to merge into the existing `<build><plugins>`; do not create duplicate `<build>` blocks. `requiresUnpack` targets **the dependency with the declared group/artifact**, not `BOOT-INF/lib` paths or Java package names.

An illustrative JRuby Maven dependency (add only when the project genuinely needs it):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.jruby</groupId>
        <artifactId>jruby-complete</artifactId>
        <version>9.4.6.0</version>
    </dependency>
</dependencies>
~~~

Maven's `requiresUnpack` does not require specifying a version in each `<dependency>` item inside `requiresUnpack`; the actual dependency and version are resolved from the POM/`dependencyManagement`/transitive graph. You must verify the artifact actually makes it into the executable archive.

### 7.2. Maven `repackage` Must Have an Execution

If using `spring-boot-starter-parent` for the application, the parent already defines the standard `repackage` execution; declaring the plugin in `build/plugins` is usually enough for `mvn package` to build an executable archive.

If **not using** the starter parent, e.g., only importing the Spring Boot BOM, you may need to declare the plugin version and execution in the right phase so `repackage` runs. Example fragment in a Maven module with another parent:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <configuration>
        <requiresUnpack>
            <dependency>
                <groupId>org.jruby</groupId>
                <artifactId>jruby-complete</artifactId>
            </dependency>
        </requiresUnpack>
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

This is a **plugin fragment**, not a full POM. If the parent already defines the execution, do not copy a second execution causing the goal to run multiple times. Use `mvn help:effective-pom` and `package` logs to verify.

### 7.3. Maven Commands to Verify

~~~bash
mvn dependency:tree
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn clean package
java -jar target/actual-application.jar
~~~

The last line is a **descriptive placeholder path** to replace with the actual executable artifact present under `target`; it is not a fixed filename pre-created by the example. If the project has a Maven wrapper, use `./mvnw` on Linux/macOS or `.\mvnw.cmd` on Windows.

Check in the effective POM: are the `spring-boot-maven-plugin` version, `repackage` execution, and `requiresUnpack` configuration right? Check `mvn dependency:tree` to see whether `org.jruby:jruby-complete` is actually in resolved dependencies. Runtime unpack testing only makes sense once the executable file is built and launched via Boot Loader.

## 8. Java 17: Minimal Runnable Program Before Unpacking Is Needed

Create `src/main/java/com/example/demo/DemoApplication.java` in one of the two complete Gradle projects from Section 5.1 or 6.1:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner reportStart() {
        return args -> System.out.println("APP_STARTED nested-ok");
    }
}
~~~

The application uses `spring-boot-starter` (no embedded web server needed), creates the Spring context, runs `CommandLineRunner`, and can exit after startup if there are no background non-daemon processes. With no special dependencies, **`requiresUnpack` is not needed**.

From a project with a valid Gradle wrapper:

~~~bash
./gradlew clean bootJar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

Startup logs also include Spring Boot lines. The **stdout line printed by the program itself** is:

~~~text
APP_STARTED nested-ok
~~~

**What this line proves:** the basic executable JAR runs through Boot Loader. It **does not prove** that JRuby (if you only added the fragment without using JRuby APIs) failed or used an unpacked JAR path. Do not treat a minimal program's success as sufficient testing for a legacy library.

### 8.1. Using the Same Source to Compare `bootRun` and `java -jar`

~~~bash
./gradlew bootRun
./gradlew clean bootJar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

In the baseline example, both run modes print `APP_STARTED nested-ok`. However:

- `bootRun` runs the app with the main runtime classpath outside a Boot archive.
- `java -jar` runs the artifact with nested JARs and Boot Loader.
- If a library needs physical files, the difference may only surface under `java -jar`.

**Do not intentionally introduce an old library into production just to create a failing example.** The safe way to learn is understanding the configuration and reproducing on a project with a real issue or an organization-approved integration test.

## 9. Checking Whether the Pattern Matches the Right Dependency

Syntactically valid `requiresUnpack` **is not enough**. You must ensure:

1. That dependency is in the resolved runtime graph of **the application module**.
2. The Spring Boot plugin actually packages the dependency into the executable JAR/WAR.
3. The Gradle pattern matches **the absolute path of the source JAR** as Gradle sees it at build time.
4. Runtime actually runs the newly built executable Boot artifact via Boot Loader.

### 9.1. Identify the Dependency First

In a single-module Gradle project:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jruby-complete --configuration runtimeClasspath
~~~

If using a multi-project build, target the specific project, e.g., `:app:dependencies` and `:app:dependencyInsight` with matching arguments (`app` is illustrative).

`dependencyInsight` shows the source/version of the dependency when present in the configuration. If the module does not use JRuby, the command may find no match; that is not a Boot Loader bug. With Maven:

~~~bash
mvn dependency:tree
~~~

If the library is only in test scope or was excluded, it may not enter the executable production archive; `requiresUnpack` does not make an absent dependency appear.

### 9.2. Confirm the JAR Is Present in Output

Use the exact post-build executable file:

~~~bash
./gradlew clean bootJar
jar tf build/libs/unpack-demo-0.1.0.jar
~~~

If the sample JRuby dependency was declared and resolved, look for an entry like:

~~~text
BOOT-INF/lib/jruby-complete-9.4.6.0.jar
~~~

**Note:** `jar tf` only tells you the entry is in the archive. It does not by itself prove the entry was marked `requiresUnpack`, nor that Boot Loader will successfully create temp files at runtime. Do not treat "file sits in `BOOT-INF/lib`" as a complete unpack test.

For a Maven executable JAR, run `jar tf target/<actual-artifact>.jar` after determining the filename. If the actual build output is an executable WAR, the library may reside in `WEB-INF/lib` or `WEB-INF/lib-provided` per packaging, rather than `BOOT-INF/lib`.

### 9.3. Gradle Pattern Matches the Source File, Not JAR Contents

For example, a resolved file in the Gradle cache has a path like:

~~~text
.../caches/modules-2/files-2.1/org.jruby/jruby-complete/9.4.6.0/.../jruby-complete-9.4.6.0.jar
~~~

The pattern:

~~~text
**/jruby-complete-*.jar
~~~

targets that absolute path. `**/` represents the preceding directories and `*` represents the version in the filename. Do not use `BOOT-INF/lib/jruby-complete-*.jar` merely because the output archive contains an entry there; the documented matched path is **the source JAR file**, not the post-packaging path.

If the artifact has a different filename (classifier, repackaging, custom file dependencies), adjust the pattern to the actual file. Rely on build logs/Gradle diagnostics and runtime tests rather than guessing filenames from Maven coordinates.

## 10. Runtime Verification: The Decisive Step

### 10.1. Test the Exact Executable Archive on the Exact JVM

With Gradle:

~~~bash
./gradlew clean bootJar
java -version
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

With Maven:

~~~bash
mvn clean package
java -version
java -jar target/<actual-artifact>.jar
~~~

In the Maven commands, `<actual-artifact>` is an explanatory placeholder to replace with the listed filename; do not type angle brackets as part of a literal filename.

Match **the same JDK version, OS, runtime config, and dependency versions** across runs. If you change the build configuration while simultaneously changing profiles, ports, JVM arguments, network, or libraries, attributing the fix to `requiresUnpack` becomes unreliable.

### 10.2. Distinguish Three Levels of Evidence

| Level | Evidence | What does it NOT prove? |
| --- | --- | --- |
| A — Build | `bootJar`/`repackage` succeeds | Not sure app runs; not sure the unpack dependency was selected properly |
| B — Archive | Library present in `BOOT-INF/lib`/`WEB-INF/lib` | Insufficient to prove library is marked/unpacked at runtime |
| C — Runtime | App launched **via Boot Loader** and the problematic library use case succeeds | Does not automatically prove all scenarios/OSes/JVMs work |

For a library failing because it opens a JAR file directly, the most valuable test is **exercising the exact failing operation** inside the packaged app. A program that merely prints a startup line will not cover errors occurring when the library scans plugins on the first request.

### 10.3. Temporary Directories and Container Environments

When a dependency is marked for unpack, the runtime needs a temporary location to create files. In Java, temp directory handling typically relates to `java.io.tmpdir`; Spring Boot Loader has version-specific naming/path management details. **Do not assume** the file will always appear at a fixed path like `/tmp/library.jar` or survive after the process exits.

In containers or restricted environments:

- Verify the temp directory location is writable, with sufficient disk space and inodes.
- With a read-only root filesystem, provide a writable temp mount per deployment policy.
- Confirm the process UID/GID has permission to use the temp location.
- With concurrent processes starting, avoid hardcoding a custom shared temp name that could collide.
- Avoid global `chmod 777` or disabling all security limits just to fix temp write errors.
- If using `-Djava.io.tmpdir=/path`, verify that directory **already exists and is writable** by the runtime/JDK, and do not turn it into long-lived storage holding secrets.

If runtime errors show `AccessDeniedException`/`No space left on device` when the loader must unpack, investigate temp storage/permissions rather than randomly changing dependency versions.

### 10.4. Other Run Paths Can Mask Bugs

- `bootRun`: dependencies are usually standalone JAR files in the Gradle cache; does not fully test nested loading.
- `spring-boot:run`: similar, using Maven runtime classpath.
- IDE Application run configuration: depends on IDE module/dependency classpath, not necessarily using Boot Loader.
- Exploded artifact: libraries may already be extracted externally, so behavior differs from a one-file Boot JAR.
- `java -cp ... DemoApplication`: invokes the main class directly, bypassing the manifest/Boot launcher; not equivalent to `java -jar executable.jar`.

**QA conclusion:** to prove the distribution works, run **the final distribution artifact** using the exact startup method used on the server.

## 11. Unpacking in Executable WARs and Scope of Applicability

The Spring Boot Gradle Plugin provides `bootWar` when the War plugin is applied. An executable WAR uses a loader tailored to the WAR layout:

~~~text
app.war
├── WEB-INF/classes/
├── WEB-INF/lib/
│   └── dependency.jar
├── WEB-INF/lib-provided/
│   └── embedded-server-related.jar
└── org/springframework/boot/loader/
~~~

`requiresUnpack` is configured on **the relevant task that builds the executable archive**. With Gradle WAR, for example:

**Groovy fragment:**

~~~groovy
tasks.named("bootWar") {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

**Kotlin fragment (must import `BootWar`):**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

This is a fragment for a module **that already applies the War plugin and Spring Boot plugin**, not runnable in a Java-only JAR project lacking `bootWar`. When an app only builds an executable JAR, configuring `bootJar` suffices; **do not** add `bootWar` configuration if that task does not exist.

If the WAR is deployed to an **external servlet container**, the container may have its own WAR unpacking and class-loading mechanisms. Container deployment behavior is not necessarily identical to launching an executable WAR via `java -jar`. Only expect `requiresUnpack` to exercise Boot Loader's mechanism when starting via Boot Loader; test both deployment paths if the project supports both.

The Maven Spring Boot Plugin uses `repackage` for both JAR/WAR and declares `requiresUnpack` by dependency coordinates; it does not create a separate `bootWar` configuration like Gradle.

## 12. Before-and-After Example with a Real Bug

Suppose project `payment-app` uses library `com.example:legacy-loader`. When run from the IDE, the app works. Once packaged into an executable JAR, a specific library feature reports it cannot open the JAR path because it requires `java.io.File`.

**Before state (illustrative):**

~~~text
IDE / Gradle bootRun: library receives filesystem path → runs
java -jar app.jar: library receives nested JAR URL → internal processing fails
~~~

Proper resolution workflow:

1. Reproduce the failure using the exact executable JAR and save the stack trace.
2. Inspect the code/library converting a JAR URL to `File`; confirm the error is not a missing dependency.
3. Identify the exact resolved artifact corresponding to `com.example:legacy-loader`.
4. Check library docs on nested JAR compatibility/unpacking; consider upgrading or switching to a compatible API if possible.
5. If needed, add **one** `requiresUnpack` rule targeting that exact library.
6. Clean-build and re-run the failing use case with `java -jar`.
7. Verify the production runtime environment has suitable temp storage.

**Conditional Gradle Groovy fragment example:**

~~~groovy
tasks.named("bootJar") {
    requiresUnpack '**/legacy-loader-*.jar'
}
~~~

**Conditional Kotlin fragment example:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/legacy-loader-*.jar")
}
~~~

**Conditional Maven plugin fragment example:**

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>legacy-loader</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

`payment-app` and `legacy-loader` are **illustrative** names, not claiming such artifacts exist on Maven Central. These snippets cannot build/run standalone without a matching project and dependency. The goal is illustrating an evidence-driven configuration decision.

**After fixing successfully**, expect the use case that previously failed from the Boot JAR to succeed. Do not assume a specific stdout message since it depends on the library and app; define project tests/assertions accordingly.

## 13. Cases `requiresUnpack` Cannot Solve

Although useful, unpacking is not a "compatibility mode for every library".

### 13.1. Library Uses the System Class Loader

A Spring Boot executable JAR uses a loader/classloader designed for nested JARs. A library attempting to use `ClassLoader.getSystemClassLoader()` to locate classes from nested dependencies may encounter limitations. Unpacking a JAR does not automatically put every class onto the system class loader.

Remedies usually involve using `Thread.currentThread().getContextClassLoader()`/appropriate resource APIs or replacing the library; if the library cannot support Boot's loader architecture, evaluate an appropriate packaging/launch method. Never jump to "ClassNotFound means add requiresUnpack".

### 13.2. Native Library Incompatible with OS/Architecture

A dependency JAR may contain `.so`, `.dll`, or `.dylib` files. Java native loading requires physical files in a suitable environment, yet **unpacking the whole dependency JAR does not guarantee inner native resources are extracted/loaded properly**. Native libraries may require dedicated extraction logic, matching architecture/ABI, and proper `java.library.path`/JNI setup.

Therefore, consult the native library's documentation. If the error is `UnsatisfiedLinkError` due to a different CPU architecture or missing binary, changing `requiresUnpack` will not fix the root cause.

### 13.3. Library Requires Writing into the JAR

A packaged JAR file is normally an immutable artifact. Unpacking to temp does not mean changes can be written back to the original JAR or persisted durably. If a library needs writable state, provide a dedicated data directory with appropriate permissions/storage.

### 13.4. Duplicate Classes or Version Conflicts

If the application has two versions of a library on the runtime classpath, classpath order/version conflicts can trigger linkage errors or wrong behavior. `requiresUnpack` does not change dependency resolution and will not solve `NoSuchMethodError` from mismatched API versions. Inspect `dependencyInsight`/`dependency:tree`, BOMs, and exclusions.

### 13.5. Wrong Executable JAR Layout

If manual re-zipping misplaced `BOOT-INF`, put the wrong launcher in the manifest, broke ZIP entry compression, or corrupted signatures/metadata, the problem is **packaging**. Build with the right version of the Spring Boot Gradle/Maven Plugin rather than treating unpack as a cure-all.

## 14. Practical Troubleshooting

| Symptom | First check | Appropriate action |
| --- | --- | --- |
| `bootRun` works, `java -jar` fails in a custom JAR parser | Check stack trace; is the library opening the JAR via File/Path? | If confirmed, `requiresUnpack` that single dependency and retest |
| `requiresUnpack` has no effect | Pattern didn't match source path or configured on wrong task/module | Check `runtimeClasspath`, `bootJar`/`bootWar`, and task configuration |
| Final JAR lacks the dependency needing unpack | Dependency excluded, wrong scope, or unresolved | Fix dependency graph; unpack will not bring a library back |
| `Task 'bootJar' not found` | Java + Spring Boot plugins not applied in module | Check `plugins`, `./gradlew tasks --all`, project path |
| `Task 'bootWar' not found` | War plugin not applied | Only configure `bootWar` if the project actually builds a WAR |
| Maven `package` does not run `repackage` | Missing plugin execution when not using starter parent | Inspect effective POM and plugin executions |
| One pattern captures too many JARs | `**/*.jar` or overly broad matcher | Narrow by filename/version; retest |
| Runtime hits `AccessDeniedException` in temp | Read-only temp volume, permissions, or wrong UID/GID | Provide writable temp mount/path while maintaining security policy |
| Runtime hits `No space left on device` | Temp filesystem/inodes exhausted | Adjust temp storage/quota after measuring need |
| `ClassNotFoundException` or `NoSuchMethodError` | Possible missing dependency or version conflict | Inspect `BOOT-INF/lib`, dependency tree, classpath, and versions |
| `UnsatisfiedLinkError` with native binary | Native resources, OS/ABI, library path | Consult native loading docs; unpacking JAR is not guaranteed to fix |
| IDE runs, container fails | Different classpath, JVM, temp filesystem, profile, OS | Reproduce with exact Boot artifact in a production-like container |
| `jar tf` shows JAR yet feature still fails | Inclusion differs from runtime unpack/library usage | Exercise failing path; verify plugin rule and temp access |
| Extracting whole JAR via jarmode works for app | Exploded startup differs from one-file nested startup | Verify using the target packaging/runtime model |
| `requiresUnpack` configured yet library unused | Redundant rule or "cargo cult" | Remove rule if tests prove unnecessary, avoiding pointless I/O/temp files |

### 14.1. Concise yet Evidence-Based Investigation Flow

**Step A — Identify the exact artifact:** which file is the executable from `bootJar`/`repackage`, in which module, with which version? Do not pick `-plain.jar` expecting Boot Loader.

**Step B — Identify the error:** does a stack trace point to the library's API; how does the message reference `jar:nested:`, `File`, `ZipFile`, or `JarFile` paths? Do not guess from generic symptoms.

**Step C — Identify the dependency:** in Gradle inspect `runtimeClasspath`; in Maven inspect `dependency:tree`. If the dependency is absent, fix resolution/scope first.

**Step D — Choose the smallest configuration:** Gradle pattern selects only the real JAR artifact; Maven uses exact group/artifact. If the dependency comes from another source or local file dependency, check the path matcher against the actual file.

**Step E — Clean-build and run the release artifact:** re-run the **exact failing case** with `java -jar` in an environment with writable temp storage.

**Step F — Document the rationale:** in the build script or technical docs, briefly note why the dependency must unpack and link the issue/version. That way, on future library upgrades, the team knows whether the rule is still needed.

## 15. Comparing Related Options

### 15.1. `bootJar` and `bootWar` Are Packaging Tasks, Not Startup

Gradle `bootJar` and `bootWar` write markers/config into the executable archive. Actual unpacking happens at launch via Boot Loader; thus `./gradlew bootJar` succeeding does not guarantee runtime has permission to unpack.

### 15.2. Maven `repackage` and `spring-boot:run` Are Different Mechanisms

`spring-boot:repackage` produces the executable artifact; `spring-boot:run` runs the development app with the Maven runtime classpath. If a bug only surfaces after repackage, run `java -jar` to verify. Adding `requiresUnpack` to the Maven packaging plugin does not mean `spring-boot:run` creates temp files identically to Boot Loader.

### 15.3. `java -Djarmode=tools -jar app.jar extract` Is a Different Kind of Unpack

Spring Boot 3.3 supports extracting an executable JAR for certain deployment/caching and startup models. Documentation example:

~~~bash
java -Djarmode=tools -jar my-app.jar extract
~~~

The command above aims at **extracting the application** (in a layout supported by Boot tools). It differs from "unpack only `jruby-complete` at runtime inside a one-file executable JAR". If choosing an exploded deployment model, verify the corresponding publish and startup process; do not conflate it with `requiresUnpack`.

### 15.4. Relationship to Container Images

With OCI containers, a Spring Boot JAR can run directly or be extracted into layers/files depending on how the image is built. If starting via Boot Loader and a dependency is marked for unpack, the container must have a writable temp filesystem. If runtime uses an exploded classpath, filesystem behavior may differ. Hence tests should closely mirror actual production execution.

Do not change Docker image layer caching, disable `layers.idx`, or weaken container security merely to accommodate one library that lacks nested JAR support; first isolate the cause and apply the narrowest exception.

## 16. Practice: From Dependency to Unpack Configuration

### Exercise 1 — Reading Executable JAR Structure

Use the Gradle setup in Section 5 or 6 with the Java code in Section 8:

~~~bash
./gradlew clean bootJar
jar tf build/libs/unpack-demo-0.1.0.jar
java -jar build/libs/unpack-demo-0.1.0.jar
~~~

**Task:** locate `BOOT-INF/classes` and `BOOT-INF/lib`. The app prints `APP_STARTED nested-ok` to stdout (alongside Spring Boot log lines).

**Answer:** since there are no special libraries, this is an example requiring no `requiresUnpack`; Boot Loader loads nested JARs using its default mechanism.

### Exercise 2 — Recognizing the Right Pattern

Suppose Gradle resolves a dependency with path:

~~~text
.../org.jruby/jruby-complete/9.4.6.0/.../jruby-complete-9.4.6.0.jar
~~~

Choose between the two patterns:

~~~text
A. BOOT-INF/lib/jruby-complete-*.jar
B. **/jruby-complete-*.jar
~~~

**Answer:** B. Per Spring Boot Gradle Plugin 3.3, `requiresUnpack` uses an Ant pattern matching the absolute source JAR path. A is a path inside the output archive, not the documented matcher target.

### Exercise 3 — Writing Kotlin DSL Configuration

**Task:** select `jruby-complete` for the `bootJar` task.

**Answer:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

This is a fragment; the Gradle plugin must be applied and the real dependency must exist in `runtimeClasspath`.

### Exercise 4 — Writing Maven Configuration

**Task:** select `org.jruby:jruby-complete` during Maven `repackage`.

**Answer:**

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

This snippet belongs in the `spring-boot-maven-plugin` section of the POM, not the main `dependencies` section. The dependency still must be declared/resolved and the repackage goal configured to run.

### Exercise 5 — Why Is `jar tf` Insufficient?

**Question:** `jar tf app.jar` shows `BOOT-INF/lib/jruby-complete-9.4.6.0.jar`. Does that prove `requiresUnpack` is right and runs successfully?

**Answer:** Not yet. It only shows the dependency is included in the archive. You must verify the packaging rule and launch via Boot Loader in an appropriate environment while exercising the JRuby use case that needs a physical file.

### Exercise 6 — Diagnosing Permissions

**Scenario:** the app runs from the IDE, the JAR marks unpack, yet the production container reports it cannot create temp files.

**Answer:** inspect writable temp paths, UID/GID, disk/inode quotas, and volume mounts. If `java.io.tmpdir` is customized, confirm the directory exists and is writable. Do not delete the rule or grant overly broad permissions before confirming the cause.

### Exercise 7 — Picking the Right Fix

**Question:** `NoSuchMethodError` occurs because `library-a` resolved to an overly old version; should we enable `requiresUnpack` for `library-a`?

**Answer:** No. `NoSuchMethodError` from binary incompatibility/version conflict requires fixing dependency versions and resolution. Unpacking does not change class APIs.

## 17. Decision Checklist

Before merging a `requiresUnpack` configuration, verify:

- [ ] You have a stack trace/documentation proving **that specific dependency needs a physical JAR file**.
- [ ] You distinguished nested-JAR limitations from missing dependencies, wrong main class, profiles, Java version, and native ABI.
- [ ] You evaluated fixing/upgrading the library or using classpath-friendly APIs; avoid adding a workaround if upstream already fixed it.
- [ ] The dependency sits in the runtime graph of **the right application module**.
- [ ] With Gradle, the pattern is narrow and matches **the absolute source JAR path**.
- [ ] With Maven, `requiresUnpack` contains the exact `groupId`/`artifactId` inside `spring-boot-maven-plugin`.
- [ ] `bootJar`/`bootWar` or `repackage` actually ran and produced the executable artifact.
- [ ] `jar tf`/manifest confirm the right output, without stopping at inclusion checks.
- [ ] Tested `java -jar` on the newly built archive itself, exercised the library's use case, and confirmed the error disappeared.
- [ ] The container/server environment has a writable temp filesystem with reasonable space/quotas.
- [ ] Not accidentally unpacking all runtime dependencies, leaking secrets into temp, or relying on fixed temp filenames.
- [ ] Added a regression test and a brief note explaining why the rule exists so future library upgrades can re-evaluate it.

**Conclusion:** With Spring Boot Loader, **the default is keeping and reading nested JARs directly**. Only use `requiresUnpack` when there is **a genuine exception requiring a JAR file on the filesystem at runtime**, configure that exact dependency, and verify with the final executable artifact in a production-like environment.

## 18. Official References

- Spring Boot 3.3.13 Gradle Plugin — Packaging Executable Archives, **Configuring Libraries that Require Unpacking**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 Maven Plugin — Packaging Executable Archives, `repackage` goal and `requiresUnpack` parameter: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Executable Jar Format / Nested JARs: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — Spring Boot Loader and NestedJarFile: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/jarfile-class.html
- Spring Boot 3.3 — Executable Jar Restrictions: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Packaging Efficient Deployments / unpacking executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Gradle Java Plugin and Java source sets: https://docs.gradle.org/current/userguide/java_plugin.html

Always check the documentation for the exact plugin/loader version you use: launcher package paths, configuration APIs, and unpack features can change across Spring Boot releases. **Do not treat requiresUnpack as a better default; it is an intentional exception for a specific library.**
