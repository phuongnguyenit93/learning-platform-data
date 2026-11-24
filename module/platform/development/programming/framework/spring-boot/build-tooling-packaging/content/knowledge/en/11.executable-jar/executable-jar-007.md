# Managing Plain Archives, Executable Archives, and the `plain` or `original` Suffixes

## Goal and Problem Statement

In a Spring Boot project, after running `./mvnw package` or `./gradlew build`, the `target/` or `build/libs/` directory often ends up containing **multiple files sharing the same base name**:

```text
# Gradle example
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT-plain.jar

# Maven example with default repackage
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT.jar.original

# Maven example when configuring the "exec" classifier
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT-exec.jar
```

These files are not arbitrary copies. They represent **two distinct artifact types**: an ordinary Java archive and a Spring Boot executable archive. Picking the wrong file can prevent `java -jar` from running, cause missing runtime libraries, prevent another module from importing Java classes, or make a pipeline push the wrong artifact to a repository/deployment target.

After this lesson, you will be able to:

1. Explain **plain JARs/WARs** and **Spring Boot executable JARs/WARs**, their internal structures, and their intended uses.
2. Correctly interpret **Gradle `jar`/`bootJar`, `war`/`bootWar`** conventions and the `-plain.jar`/`-plain.war` suffix.
3. Explain **Maven `spring-boot:repackage`**, why `.jar.original` or `.war.original` exists, and the meaning of `<classifier>exec</classifier>` and `<attach>`.
4. Configure archive names/classifiers safely so two tasks do not overwrite the same path and plain archives are not disabled when still needed.
5. Use `jar tf`, the manifest, and actual execution to **accurately identify** which artifact runs standalone, which serves as a dependency, and which is selected by the deploy stage.
6. Write simple CI checks to avoid confusing `plain`, `original`, JARs from other modules, or stale build files.

**Scope:** Spring Boot applications using Maven or Gradle, primarily executable JARs; WARs are included because the `plain`/`bootWar` and `original` rules apply similarly. Examples use **Spring Boot 3.3.13, Java 17**, and a compatible Gradle Wrapper; these are illustrative versions, not versions every project must use. Consult the exact plugin documentation if using Spring Boot 4.x or a different Gradle/Maven version.

## 1. Two Archive Forms: Similar Outside, Different Purpose

### 1.1 Ordinary Java Archive (Plain)

An ordinary JAR produced by Gradle `jar` or the Maven JAR Plugin mainly contains **the module's classes and resources** laid out by Java package. For example:

```text
demo-0.0.1-SNAPSHOT-plain.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── demo/
│           └── DemoApplication.class
└── application.properties                 (if present)
```

This is an **illustrative structure**, not the only file tree a JAR can have. In a typical plain JAR:

- Classes sit directly by package, e.g., `com/example/demo/DemoApplication.class` at the archive root.
- The JAR **does not automatically carry all runtime dependencies** as nested JARs merely because it was packaged with `jar`. Other plugins may produce fat/shaded JARs in their own way.
- It can be consumed by another Maven/Gradle project as a normal dependency, because a consumer's Java classloader expects classes at the root.
- It is usually **insufficient to run standalone** with `java -jar` in a Spring Boot app with dependencies. However, there is no rule that "a plain JAR can never run": a plain JAR with a properly prepared manifest and classpath, or a JDK-only program, can still run. The word `plain` describes **how it is packaged**, not a mechanical test of every possible execution mode.

A Java library module normally needs this format to share APIs/classes with other modules; not every module in a repository should use Spring Boot executable packaging.

### 1.2 Spring Boot Executable JAR

A Spring Boot executable JAR created by Gradle `bootJar` or Maven `spring-boot:repackage` typically looks like:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── application.properties
│   ├── lib/
│   │   ├── spring-boot-....jar
│   │   └── ...other runtime dependencies...
│   ├── classpath.idx                 (may be present)
│   └── layers.idx                    (when layers are enabled)
└── org/springframework/boot/loader/...
```

- `BOOT-INF/classes` holds the application's classes and resources.
- `BOOT-INF/lib` holds dependency JARs chosen by the packaging tool so the application can run standalone with a nested-JAR classpath.
- `org/springframework/boot/loader/...` is the launcher that supports booting and reading nested JARs in Boot's format.
- Manifests in **Spring Boot 3.3.x** typically contain attributes such as `Main-Class: org.springframework.boot.loader.launch.JarLauncher` and `Start-Class: com.example.demo.DemoApplication`. Actual values depend on version, layout, and main class name.
- Runnable with `java -jar <path-to-boot-file>.jar` given a matching JDK and runtime environment.

**Do not call an executable Boot JAR a shaded JAR in the sense that all JARs are unpacked/merged into the root.** Spring Boot by default **nests** dependency JARs; plugins like Shade/Shadow use different models.

### 1.3 Why Is a Boot JAR Unsuitable as a Regular Java Dependency?

Another module expects to load `com/example/demo/DemoApplication.class` from the root of a dependency JAR. In a Spring Boot executable JAR, however, that class resides under `BOOT-INF/classes/com/example/demo/...`. A regular Maven/Gradle consumer classloader **does not automatically treat `BOOT-INF/classes` as the package root**, making an executable JAR unsuitable as a library dependency.

If a project needs to both **publish a library** and **run an application**, keep the plain artifact as the main dependency and place the executable artifact under a **separate classifier**, or split the design into two modules (`library` and `application`). There is no reason to publish every Boot JAR as a dependency for other modules.

### 1.4 The File Suffix Alone Does Not Prove Structure

A teammate could rename `demo-plain.jar` to `demo.jar`; the file remains a plain archive. Or a Boot JAR could be named `demo-exec.jar`, `demo-boot.jar`, or any custom name. Therefore:

> **The name hints at intent; the packaging task, manifest, layout, and actual execution prove the artifact type.**

Do not guess solely from file size, the `.jar` extension, the presence of `Main-Class`, or a file appearing in `target`/`build/libs`.

## 2. Terminology Table to Avoid Confusing `plain`, `original`, and `classifier`

| Term | Build System / Source | Meaning |
| --- | --- | --- |
| `jar` (regular task/goal) | Gradle `jar` or Maven JAR Plugin in `package` phase | Packages classes/resources into a plain JAR |
| `bootJar` | Spring Boot Gradle plugin + Java plugin | Builds an **executable Boot JAR** |
| `bootWar` | Spring Boot Gradle plugin + War plugin | Builds an **executable Boot WAR** |
| `spring-boot:repackage` | Spring Boot Maven Plugin | Takes the JAR/WAR built during the Maven lifecycle and repackages it in Boot layout |
| `-plain.jar` / `-plain.war` | **Gradle** (default convention classifier on the plain task when a Boot task exists) | A **separate plain artifact** created by the `jar`/`war` task |
| `.jar.original` / `.war.original` | **Maven** when `repackage` replaces the main artifact | **Backup of the archive before repackaging**, kept locally in `target` by default |
| `-exec.jar`, `-boot.jar` | Maven/Gradle when a user configures a different classifier | A configured suffix on the artifact; **not mandatory** in every project |
| `classifier` | Maven artifact coordinates or Gradle `archiveClassifier` | Distinguishes variants sharing the same base name and version |
| `attach` (Maven) | Spring Boot Maven Plugin | Controls whether the repackaged artifact is attached during `install`/`deploy` |
| `layout=NONE` (Maven) | Spring Boot Maven Plugin | Can embed nested libraries without a main launcher: **not a standard executable layout** |

**Key note:** `.jar.original` is not a Maven **classifier** named `original`. It is a backup suffix on the file replaced by `repackage`. By contrast, `-plain.jar` is an actual classifier on Gradle's plain `jar` task. This is a crucial distinction in this lesson.

## 3. Gradle: `jar` and `bootJar` Are Two Separate Tasks

### 3.1 Sample Configuration for a Spring Boot JAR

`settings.gradle` file:

```groovy
rootProject.name = 'demo'
```

`build.gradle` file (Groovy DSL) suitable for this lab:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This example does not need the web starter because it only demonstrates a console Spring Boot JAR. The project needs a Java class with `main` as shown in Section 7. Here `io.spring.dependency-management` provides Boot BOM dependency version management when used alongside the plugin; it does not create the `bootJar` task. It is `org.springframework.boot` combined with `java` that adds the Boot archive task.

### 3.2 Tasks to Distinguish

When applying the Java plugin and Spring Boot Gradle plugin:

| Task | Purpose | Example Default Output |
| --- | --- | --- |
| `compileJava` | Compiles Java code | `build/classes/java/main` |
| `processResources` | Processes resources | `build/resources/main` |
| `jar` | Plain JAR, classes at root | `build/libs/demo-0.0.1-SNAPSHOT-plain.jar` |
| `bootJar` | Spring Boot executable JAR, classes in `BOOT-INF/classes` | `build/libs/demo-0.0.1-SNAPSHOT.jar` |
| `assemble` | Lifecycle assembling artifacts; Boot attaches `bootJar` to `assemble` | Runs archive tasks wired into lifecycle |
| `build` | Lifecycle combining `assemble` and verification steps | Can produce both executable and plain archives depending on task enablement/config |
| `bootRun` | Runs source set / runtime classpath during development | **Not** a JAR-producing task |

With Boot Gradle plugin 3.3, documentation confirms that when `bootJar` is configured, the `jar` task is given the **`plain` convention classifier**. Thus both tasks write to **different paths** without colliding. Similarly, `bootWar` and `war` apply the `plain` classifier to the plain WAR task.

**`-plain` does not mean a failed build, a stale artifact, or "the Spring Boot plugin did not run".** It is a real file produced by Gradle to keep the plain archive separate from the Boot archive.

To explicitly produce both in this lab:

```bash
./gradlew clean jar bootJar
```

After running that command, keeping the sample configuration and no classifier overrides, the expected files are:

```text
build/libs/demo-0.0.1-SNAPSHOT-plain.jar
build/libs/demo-0.0.1-SNAPSHOT.jar
```

These are names derived from the sample `rootProject.name`/`version`, not stdout captured from an actual Gradle run. Real projects may have other archives, custom classifiers, or disabled tasks.

### 3.3 Changing Classifiers: Giving Boot `-boot` and Plain No Suffix

Sometimes CI/publishing wants the **plain JAR to carry the primary name**, while the executable JAR uses `-boot.jar`. Configure **in `build.gradle`**:

```groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}

tasks.named('jar') {
    archiveClassifier = ''
}
```

After `./gradlew clean jar bootJar`, expected names:

```text
build/libs/demo-0.0.1-SNAPSHOT.jar           # plain
build/libs/demo-0.0.1-SNAPSHOT-boot.jar      # executable
```

This is a **classifier change**; it does not swap the logic of the two tasks. `jar` remains plain and `bootJar` remains Boot. If the pipeline previously copied `demo-0.0.1-SNAPSHOT.jar` to run `java -jar`, after this classifier change it would copy the **plain JAR by mistake**. Update the artifact selection stage in the **same commit**.

**Kotlin DSL `build.gradle.kts`**, equivalent explicit task-type syntax (snippet; the file must apply the proper plugins):

```kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveClassifier.set("boot")
}

tasks.named<org.gradle.api.tasks.bundling.Jar>("jar") {
    archiveClassifier.set("")
}
```

Do not paste Groovy's `archiveClassifier = 'boot'` into Kotlin DSL. Kotlin uses double-quoted strings and the property `set(...)` API.

### 3.4 Should You Disable the Plain `jar` Task?

The Spring Boot Gradle Plugin allows:

```groovy
tasks.named('jar') {
    enabled = false
}
```

Equivalent Kotlin DSL:

```kotlin
tasks.named<org.gradle.api.tasks.bundling.Jar>("jar") {
    enabled = false
}
```

This prevents the `jar` task from **producing a plain JAR** when invoked, keeping output cleaner for pure applications that only want an executable archive. However, **do not disable it by default**:

- A Java library or `java-library` module may need the plain JAR as a dependency.
- Some `maven-publish` setups, distribution tasks, or CI steps rely on `jar`'s output.
- **Spring Boot documentation warns against disabling `jar` when building native images** (related to Gradle/GraalVM integration).
- Disabling `jar` does not automatically run `bootJar` nor determine the app's main class; inspect the task graph and rebuild.
- Never set the classifier of both `jar` and `bootJar` to empty string `''` at the same time: both tasks will target the **same file name**, overwriting each other or producing unpredictable results.

If you just want **CI to pick one specific file**, it is usually better to configure the stage to select the **exact task output** rather than disabling a task needed by other workflows.

### 3.5 Renaming the Archive Does Not Change the Archive Type

Gradle properties such as `archiveBaseName`, `archiveVersion`, `archiveClassifier`, and `archiveFileName` control output naming. For example:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'service-app.jar'
}
```

This only renames `bootJar`'s output to `service-app.jar`; it does not turn a plain `jar` into a Boot JAR, nor does it make `service-app.jar` automatically safe to deploy. When using a fixed name, verify other variants and tasks do not write to the same path.

The default directory is `build/libs/`, though it can be changed with `destinationDirectory` or other configuration. Do not hardcode file paths from examples if a project customizes archive properties.

## 4. Maven: A Plain JAR Is Built First, Then `repackage` Turns It into a Boot JAR

### 4.1 Example POM for Default `repackage`

Minimal `pom.xml` for a Spring Boot application without an HTTP server, configured for Java 17:

```xml
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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

When inheriting `spring-boot-starter-parent`, the `repackage` goal is already configured on an execution named `repackage`; declaring the plugin in the POM suffices to activate it in the standard lifecycle. In a project that **only imports the Spring Boot BOM without inheriting the parent**, you do not get this execution by default: you must bind `spring-boot:repackage` to the `package` phase (or invoke the goal properly).

Run from the directory containing `pom.xml` and the Maven Wrapper:

```bash
./mvnw clean package
```

With the config above and the `main` class from Section 7, after `package` you normally see:

```text
target/demo-0.0.1-SNAPSHOT.jar              # Boot executable JAR
target/demo-0.0.1-SNAPSHOT.jar.original     # plain JAR before repackage
```

Maven creates the plain JAR first (typically via the Maven JAR Plugin), and then the Spring Boot Maven Plugin **repackages** it into the executable layout. When the goal has no classifier configured, it **replaces the main artifact** with the repackaged file. The original file is renamed to `.original` inside the build directory to preserve the pre-repackage archive.

**Where confusion happens most:**

- `demo-0.0.1-SNAPSHOT.jar` after default repackaging is the **Boot executable JAR**.
- `demo-0.0.1-SNAPSHOT.jar.original` is a **plain backup file**, not a JAR "given an original classifier by Gradle" and not a container deployment target.
- `.original` is a **local** file name (backup), not a supplemental Maven artifact uploaded alongside the main JAR to repositories by default.
- `mvn install`/`deploy` by default processes the **repackaged main artifact**; it does not turn `.original` into a classified Maven artifact merely because the file sits in `target`.

You can still run `jar tf target/demo-0.0.1-SNAPSHOT.jar.original` to inspect the initial JAR's bytes (a JAR is a ZIP; `jar` accepts any file path), yet `.original` is not the file to `COPY` into a Dockerfile as your runnable JAR without checking.

### 4.2 `mvn package` vs. Calling `spring-boot:repackage` Standalone

`spring-boot:repackage` **requires an existing source JAR/WAR** from the `package` phase. Per the documentation, you should not invoke `./mvnw spring-boot:repackage` on its own in a build lacking a source archive.

With a properly configured plugin, the standard safe command is:

```bash
./mvnw clean package
```

If a project's parent did not bind the `repackage` goal, a properly ordered command is:

```bash
./mvnw package spring-boot:repackage
```

Be careful: **if the `repackage` goal already runs in `package`**, appending it in the same command can trigger unwanted or redundant operations. Do not mix both blindly; check `help:effective-pom` and the execution list first.

### 4.3 `<classifier>exec</classifier>`: Keeping the Plain JAR as the Main Artifact

If a module may be consumed as a dependency by another module, or you want to store both archive forms in a Maven repository, configure a **custom classifier for Boot repackage**.

Keep the POM above and change the Spring Boot plugin block to:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
        <attach>true</attach>
    </configuration>
</plugin>
```

This is a **plugin replacement snippet inside `<build><plugins>`** for a project using `spring-boot-starter-parent`. Because the parent binds the `repackage` execution, plugin-level configuration applies to that execution. `<attach>true</attach>` is the goal's default; it is stated explicitly here to highlight publishing both artifacts. In projects **not using the parent**, you must also declare the `repackage` execution properly.

After `./mvnw clean package`, assuming no other source artifact already carries classifier `exec`, expected files:

```text
target/demo-0.0.1-SNAPSHOT.jar             # plain JAR, main Maven artifact
target/demo-0.0.1-SNAPSHOT-exec.jar        # executable Boot JAR, "exec" classifier artifact
```

Interpretation:

- `demo-0.0.1-SNAPSHOT.jar` is the plain JAR, with Java classes at the root (assuming no other special plugins).
- `demo-0.0.1-SNAPSHOT-exec.jar` contains the Boot loader, `BOOT-INF/classes`, and nested dependencies.
- Run `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar` to launch the application. Use the plain main JAR as a dependency where appropriate.
- With `attach=true`, `mvn install`/`deploy` can register two artifacts: the unclassified main artifact and the `exec`-classified artifact. Consumers must specify the classifier to fetch `exec`.
- `.jar.original` is no longer created by default when **the main artifact is not replaced**, because the two outputs already have distinct names.

**Important advanced detail:** when `classifier` is set, the Maven Repackage Plugin first checks if an artifact **already exists with that classifier** to use as its repackage source. If found, it repackages that classified artifact; otherwise, it uses the main archive and attaches the repackaged archive as a supplemental artifact. Thus, when a custom Maven JAR Plugin builds multiple classifiers, verify execution order and the actual source artifact rather than reading `<classifier>exec</classifier>` in isolation.

### 4.4 `<attach>false</attach>` Does Not Mean "Do Not Create the File"

The `attach` parameter on the Maven Boot Plugin controls **attaching the repackaged artifact for `install`/`deploy`**. When `attach=false`, do not assume the plugin "skips creating the Boot JAR"; per documentation, it still creates the executable archive locally while omitting it as an attached artifact during publishing.

Common case `attach=true` with empty classifier: the repackaged JAR replaces the main artifact. Case `classifier=exec` + `attach=true`: both artifacts are published under distinct coordinates. If setting `attach=false`, test both `package` and `install` against a local test repository or inspect publishing metadata to verify exactly what goes where. **Do not confuse "file exists in `target`" with "file gets published".**

### 4.5 Maven `finalName` Affects File Name, Not Packaging

If the POM has:

```xml
<build>
    <finalName>app-service</finalName>
</build>
```

the main archive will usually be named `target/app-service.jar` (and `target/app-service.jar.original` with default repackage). With classifier `exec`, the file becomes `target/app-service-exec.jar` per plugin behavior.

`<finalName>` **differs from** `<classifier>`:

- `finalName` primarily controls the file name in the build directory.
- `classifier` distinguishes attached/published Maven artifacts; with the Boot plugin, it also governs source/output artifact selection for repackaging.
- Maven dependency coordinates still comprise `groupId`, `artifactId`, `version`, `type`, and `classifier`; changing the local file name with `finalName` does not alter repository coordinates.

Do not change `finalName` just to "get rid of `.original`"; the backup serves its own role and appears when the plugin replaces the main artifact by default.

## 5. Comparing Gradle `-plain.jar` and Maven `.jar.original` Over Time

### Gradle: Two Tasks / Two Independent Outputs

```text
Java/resources source
        |
        +-- jar ------------> build/libs/demo-0.0.1-SNAPSHOT-plain.jar
        |                         (plain archive)
        |
        \-- bootJar --------> build/libs/demo-0.0.1-SNAPSHOT.jar
                                  (Boot executable archive)
```

- `jar`/`bootJar` write separate outputs; the convention classifier prevents collisions.
- There is no default "rename plain to `.original`" step to make room for the executable archive.
- Both files coexist when both tasks run, or only one exists when a pipeline invokes a single task.
- `-plain` is a **filename classifier** on the `jar` task that can be reconfigured.

### Maven: One Main Artifact That Can Be Replaced

```text
Java/resources source
        |
        v
maven-jar-plugin:jar ----> target/demo-0.0.1-SNAPSHOT.jar  (initially plain)
        |
        v
spring-boot:repackage ---> target/demo-0.0.1-SNAPSHOT.jar
                            (replaced with Boot executable)
                             +
                            target/demo-0.0.1-SNAPSHOT.jar.original
                            (pre-repackage backup)
```

- `.original` is only a local backup under the default flow.
- Adding a custom `exec` classifier changes the output path to **a plain main JAR and Boot `-exec.jar`**, avoiding replacing the main archive.
- If `repackage` did not run, `target/demo-...jar` may still be plain and have **no** `.original`. Therefore, looking for file names alone cannot verify whether the goal executed.

### Side-by-Side Comparison Under Default Configuration

| Question | Gradle Boot Plugin | Maven Boot Plugin |
| --- | --- | --- |
| What creates the plain JAR? | `jar` task | Maven JAR Plugin in `package` |
| What creates the Boot executable JAR? | `bootJar` task | `spring-boot:repackage` goal |
| Default Boot JAR name in example | `demo-0.0.1-SNAPSHOT.jar` | `demo-0.0.1-SNAPSHOT.jar` |
| Default plain JAR name in example | `demo-0.0.1-SNAPSHOT-plain.jar` | `demo-0.0.1-SNAPSHOT.jar.original` |
| Is the plain JAR a standalone artifact? | Yes, output of an independent task | Main JAR prior to repackage; after default repackage, kept locally as `.original` |
| How to keep plain as the main artifact | Set `jar` classifier to empty and `bootJar` classifier to `boot` (or configure publications explicitly) | Set `<classifier>exec</classifier>` for Boot repackage |
| Should plain be deployed as an executable? | No, unless specifically engineered to run standalone | No, unless provided with dedicated startup/dependencies |
| Most reliable verification | Check tasks, `jar tf`/manifest, run exact Boot JAR | Check `repackage` execution, `jar tf`/manifest, run exact Boot JAR |

## 6. When Packaging a WAR: `war`, `bootWar`, `-plain.war`, and `.war.original`

This topic focuses on executable JARs, yet the **plain vs. executable** distinction applies equally to WARs in Spring MVC/Servlet applications.

### 6.1 Gradle WAR

When both the Gradle `war` plugin and Boot plugin are applied, `war` creates a plain WAR and `bootWar` creates a Boot executable WAR. When both are created with defaults, illustrative names are:

```text
build/libs/demo-0.0.1-SNAPSHOT-plain.war    # plain war
build/libs/demo-0.0.1-SNAPSHOT.war          # bootWar executable
```

Plugin and servlet dependency **Groovy snippet**:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

This snippet is not a complete `build.gradle`; it needs `repositories`, `group`, `version`, JDK, and an application class. `war` applies `java` implicitly. To deploy a WAR to an external servlet container, the application must implement `SpringBootServletInitializer` and match a compatible container, not just swap `jar` for `war`.

Classifiers can be changed for WARs using the same principle:

```groovy
tasks.named('bootWar') {
    archiveClassifier = 'boot'
}
tasks.named('war') {
    archiveClassifier = ''
}
```

Then the plain WAR takes the primary name `demo-0.0.1-SNAPSHOT.war`, while the Boot WAR uses `demo-0.0.1-SNAPSHOT-boot.war`. **Update the deployment pipeline** to select the right file.

### 6.2 Maven WAR

With Maven `<packaging>war</packaging>` and a properly bound `repackage` goal, the original WAR may be saved as `target/demo-0.0.1-SNAPSHOT.war.original` when the executable WAR replaces the main artifact. Using `<classifier>exec</classifier>` keeps the plain WAR as the main artifact and also produces `...-exec.war`.

A Maven Boot executable WAR normally has `WEB-INF/classes`, `WEB-INF/lib`, and possibly `WEB-INF/lib-provided`. Plain WARs also have `WEB-INF/classes` and `WEB-INF/lib`, so seeing `WEB-INF` alone **is not enough to conclude a WAR is executable**. Check the Boot loader/manifest and test `java -jar` on the Boot WAR. If deploying to an external servlet container, also verify container/initializer/provided-dependency compatibility.

**Do not treat `-plain.war` as an "undeployable file":** a plain WAR may be the exact artifact needed by an external servlet container. However, if the pipeline expects `java -jar`, a plain WAR lacks the Boot launcher. Choose the artifact based on the **target operating model**, not on an assumption that "Boot is always better than plain".

## 7. A Java 17+ Class to Verify the Artifact

To avoid contrived stdout or web environment dependencies, create **a Spring Boot application without an HTTP server**. For either the Maven POM or `build.gradle` given above, create:

```text
src/main/java/com/example/demo/DemoApplication.java
```

Full contents:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println("ARCHIVE_OK");
    }
}
```

This is a valid Java class for a **Spring Boot project with starter dependencies and Java 17+**. It is **not standalone** if compiled with bare `javac DemoApplication.java` because it requires Spring Boot classes on the classpath. Use `./mvnw package` or `./gradlew bootJar` to compile and package it.

When built into an executable Boot JAR and run with a compatible JDK:

```bash
# Maven, without custom classifier
java -jar target/demo-0.0.1-SNAPSHOT.jar

# Gradle, using default Boot task classifier
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

The application prints **its own line**:

```text
ARCHIVE_OK
```

In practice, Spring Boot's banner, startup logs, warnings, or other output may also appear; the snippet above is **not full stdout** from a real run. If you added `<classifier>exec</classifier>` in Maven, run `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar`; if you changed `archiveClassifier='boot'` in Gradle, run `java -jar build/libs/demo-0.0.1-SNAPSHOT-boot.jar`.

### Inspecting with `jar tf`

Maven:

```bash
./mvnw clean package
jar tf target/demo-0.0.1-SNAPSHOT.jar
jar tf target/demo-0.0.1-SNAPSHOT.jar.original
```

Gradle:

```bash
./gradlew clean jar bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
jar tf build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

**Expected indicators from the Maven/Gradle examples:**

| Path inside ZIP | Boot Executable JAR | Plain JAR |
| --- | --- | --- |
| `BOOT-INF/classes/com/example/demo/DemoApplication.class` | Present | Usually absent |
| `com/example/demo/DemoApplication.class` at root | Absent in standard Boot layout | Present |
| `BOOT-INF/lib/` with dependency JARs | Present | Absent in default plain packaging |
| `org/springframework/boot/loader/...` | Present | Usually absent |
| `META-INF/MANIFEST.MF` | Present | Present |
| `Main-Class: ...JarLauncher` in manifest | Usually present in Boot 3.3 JAR layout | Not by default |
| `Start-Class: com.example.demo.DemoApplication` | Usually present | Not by default |

Do not inspect Maven's `.original` file and mistakenly conclude the Boot JAR is missing its launcher: `.original` **intentionally preserves the pre-repackage archive**.

### Reading the Manifest

On macOS/Linux if `unzip` is available:

```bash
unzip -p build/libs/demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

For Maven, adjust the file path. In Boot 3.3, `Main-Class` and `Start-Class` are distinct attributes: the launcher is the class called first by the JVM, and the Spring Boot launcher finds the original application via `Start-Class`.

**Verification warning:** seeing `Main-Class` alone does not prove all dependencies are present; a plain JAR can also declare `Main-Class`. Combine **manifest + layout + actual execution**; adapt criteria if a project uses a custom loader or layout.

## 8. Why Does `java -jar` Fail on `-plain.jar` or `.jar.original`?

Suppose someone runs:

```bash
java -jar build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

One of the following errors may occur, **depending on manifest and classpath configuration**:

- `no main manifest attribute`: the plain JAR does not declare `Main-Class`.
- `ClassNotFoundException` or `NoClassDefFoundError`: a main class exists, yet runtime dependencies are not packaged inside the archive and no valid external classpath is supplied.
- The application starts yet fails missing resources/dependencies at runtime: which is why packaging and runtime tests must accompany file checks.

There is no single fixed stdout/error across **every** plain JAR. The right fix is to **pick the executable Boot JAR** when standalone execution is needed—not renaming the file to `*.jar`, stripping the `plain` suffix, or copying `BOOT-INF` manually.

In Maven, running `java -jar target/demo-...jar.original` also usually fails for a Spring Boot app with dependencies because it is the **pre-repackage archive**. It is not a corrupted file; it simply serves a different purpose.

### When a Plain JAR Is the Right Choice

In a module providing APIs or domain models, a plain JAR with classes at the root is the right format for other modules to import. If a pipeline intends to publish a **Java library**, do not automatically pick the largest file or the Boot JAR. When a module needs to serve as both a library and an app, consider:

1. Splitting into a `library` module using `java-library` and an `application` module using the Boot plugin.
2. Or in Maven, keeping plain as main and using Boot classifier `exec`.
3. Or in Gradle, configuring classifiers and publications so the plain/API artifact and executable artifact have clear coordinates.

The key requirement is that **consuming modules** do not expect to load classes from `BOOT-INF/classes` via a standard classloader.

## 9. Selecting the Right Artifact in CI, Docker, and Publishing

### 9.1 Why You Should Not Use Overly Broad Wildcards

A copy step like:

```bash
cp build/libs/*.jar release/app.jar
```

can fail when multiple files exist, or be poorly patched into "take the first file" and accidentally grab `-plain.jar`. In Maven, `target/*.jar*` can match `.jar.original`, sources/javadoc JARs, or files from other modules.

Rules:

- Build **from a clean checkout** using the exact Wrapper and task/goal intended by the pipeline.
- Reference the exact **task output** or **one fixed, verified artifact path**.
- Verify the file's manifest/layout before publishing or putting it into an image.
- Whenever changing classifiers, `finalName`, or `archiveFileName`, update CI/Dockerfiles in the same change.
- Do not mistake a locally kept `.original` file for an attached/deployed Maven artifact.
- In Gradle, verify publication components/tasks rather than assuming every file in `build/libs` gets published to a Maven repository.

### 9.2 Example Maven Stage Selecting the Right Boot JAR

With the example POM using default repackage:

```bash
./mvnw clean package
artifact="target/demo-0.0.1-SNAPSHOT.jar"
test -f "$artifact"
jar tf "$artifact"
java -jar "$artifact"
```

`java -jar` acts as a smoke test; for this lesson's console app, it prints `ARCHIVE_OK` and exits under normal conditions. In real CI, web applications usually **do not exit on their own**; launch under process control, run a health check, and terminate cleanly rather than calling `java -jar` inline without timeouts/health policies.

With Maven classifier `exec`, change only the verified/deployed path to:

```bash
artifact="target/demo-0.0.1-SNAPSHOT-exec.jar"
```

If a team wants to publish the **plain main artifact** as a library and the Boot classifier for deployment, configure `attach`/execution properly and verify Maven repository metadata rather than only checking local files.

### 9.3 Example Gradle Stage Selecting the Right Boot JAR

```bash
./gradlew clean bootJar
artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"
test -f "$artifact"
jar tf "$artifact"
```

If `archiveClassifier = 'boot'`, update the path to `demo-0.0.1-SNAPSHOT-boot.jar`. Complex builds may alter destination directories or basenames; read the real name from task configuration.

**Illustrative Dockerfile excerpt** for the sample Maven artifact, not a full pipeline solution:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

If Maven is using `classifier=exec`, that Dockerfile would **copy the plain main JAR by mistake**; change it to `target/demo-0.0.1-SNAPSHOT-exec.jar`. With Gradle, change `target/...` to the actual `build/libs/...` file.

### 9.4 Fail-Fast Layout Check with Bash

The snippet below verifies the **executable Boot JAR layout** for the example before adding it to a Docker image; it differs from testing the running application, yet catches accidental plain/original selection:

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$artifact" ]]; then
    echo "FAIL: artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fq 'BOOT-INF/classes/' <<< "$entries"; then
    echo "FAIL: missing BOOT-INF/classes"
    exit 1
fi

if ! grep -Fq 'BOOT-INF/lib/' <<< "$entries"; then
    echo "FAIL: missing BOOT-INF/lib"
    exit 1
fi

if ! grep -Fq 'org/springframework/boot/loader/' <<< "$entries"; then
    echo "FAIL: missing Spring Boot loader"
    exit 1
fi

echo "PASS: Spring Boot executable JAR layout detected"
```

**Applies to:** a Spring Boot 3.3 app with starter dependencies and `bootJar` JAR output. For a valid Boot JAR with nested dependencies and proper loader, the script prints:

```text
PASS: Spring Boot executable JAR layout detected
```

This line is **not output measured on your own project**, but the expected output under the script's conditions. A missing source file or missing layout prints a `FAIL` line and exits 1. The script checks **layout**; it does not prove the JDK is right, runtime config is right, or every library is secure. If a project uses a custom loader/layout or packages a WAR, adjust the conditions.

For a WAR, check `WEB-INF/classes`, `WEB-INF/lib`/`WEB-INF/lib-provided`, and the WAR launcher; do not apply JAR `BOOT-INF/classes` checks to a WAR.

### 9.5 PowerShell for Windows Users

```powershell
$artifact = "build/libs/demo-0.0.1-SNAPSHOT.jar"

if (-not (Test-Path -LiteralPath $artifact)) {
    throw "Artifact missing: $artifact"
}

$entries = & jar tf $artifact
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read jar: $artifact"
}

if (-not ($entries | Select-String -SimpleMatch "BOOT-INF/classes/")) {
    throw "Not a Boot JAR: BOOT-INF/classes missing"
}
if (-not ($entries | Select-String -SimpleMatch "org/springframework/boot/loader/")) {
    throw "Not a Boot JAR: loader missing"
}

Write-Output "PASS: Boot JAR layout detected"
```

This is a **basic layout check**: verifying classes/resources under `BOOT-INF` and the Boot loader; add checks for `BOOT-INF/lib`, the manifest, and smoke tests per pipeline requirements. If using Maven, update `$artifact` to `target/demo-0.0.1-SNAPSHOT.jar` or `-exec.jar` as appropriate.

### 9.6 Publishing: File Existence Does Not Equal Publication

In Maven, `repackage`'s `attach` and `classifier` determine whether the main artifact or a supplemental artifact is installed/deployed. In Gradle, archive-building tasks and `maven-publish`/publication configs are separate concerns: a file appearing in `build/libs` does not automatically mean it is published to a Maven repository.

**One question to answer before deploying/publishing:** "Which task built this file, what are its `group/artifact/version/classifier` coordinates, and how does the consuming stage launch it or import its classes?" Only then choose plain vs. executable.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Evidence and Fix |
| --- | --- | --- |
| `build/libs` has two JARs, one suffixed `-plain` | Gradle Boot task and `jar` task created two archive types | Usually normal; pick the Boot output for `java -jar` |
| `target` contains `.jar.original` | Maven `repackage` replaced main JAR and kept backup | Inspect `target/*.jar` and manifest; never deploy `.original` |
| Gradle plain JAR mistaken for stale build output | Unfamiliarity with `archiveClassifier=plain` | Check `jar` task, root classes layout, and `bootJar` task |
| Maven main JAR won't run after setting `classifier=exec` | Main artifact is now plain; Boot moved to `-exec.jar` | Run `java -jar ...-exec.jar` and update CI/Dockerfile |
| No `.original` file in Maven | Using a classifier, `repackage` didn't run, clean removed backup, or custom plugin | Verify goal execution and actual archive output |
| `mvn package` did not produce a Boot JAR | Not inheriting parent or missing `repackage` execution; skipped or other plugin | Inspect `help:effective-pom`, check phase and plugin logs |
| `bootJar` task not found | Boot plugin and Java plugin not applied together or wrong module | `./gradlew tasks --all`, check `apply false` and module |
| `bootWar` task not found | Gradle `war` plugin not applied or wrong module | Check `plugins` and `tasks --all` |
| `bootJar` reports main class not found | Module lacks a valid `public static void main(String[])` | Add/set `mainClass` or split into a library module |
| `jar tf` shows `BOOT-INF/classes` missing | Inspecting the plain JAR or custom archive layout | Check producing task, manifest, and artifact path |
| `no main manifest attribute` with `java -jar` | Plain JAR lacks entry point, or wrongly packaged archive | Pick the executable Boot JAR instead of renaming files |
| `ClassNotFoundException` using plain JAR | Plain lacks runtime dependencies; classpath incomplete | Use Boot archive for standalone run or set up proper classpath |
| Maven classifier `exec` set yet archive repackaged oddly | A source artifact with that classifier already existed | Inspect `jar`/`repackage` executions, ordering, and classifiers |
| Gradle two tasks write the same `...jar` name | `jar` and `bootJar` given identical classifier/name | Give both tasks **distinct `archiveFileName`s**, clean and rebuild |
| Gradle build creates Boot JAR yet CI copies plain | Wildcard or ambiguous artifact selection script | Pin a single Boot output path, check layout before deploy |
| Disabling `jar` breaks native build | Some native image workflows require the `jar` task | Re-enable `jar`, use classifiers/CI selection instead of disabling |
| Maven consumer cannot load classes from dependency | Boot JAR published at main coordinates; classes sit in `BOOT-INF` | Publish plain main + Boot classifier, or split library module |
| `target/*.jar` contains stale files | Forgot `clean`, incremental output, or multi-module | Identify exact file by name/version; check timestamp/hash and stage |
| WAR builds fine yet fails to deploy | Wrong WAR type, missing Servlet initializer/compatibility | Distinguish `war` vs. `bootWar`, check WAR layout and server logs |
| Build produces new file yet container runs old code | Image copied wrong artifact, stale layer/cache, or unchanged tag | Verify `COPY` path, checked artifact `sha256`, and deployed image |

### Recommended Diagnostic Sequence

1. **Confirm the build system** and module: `pom.xml` or `build.gradle`, Maven Wrapper or Gradle Wrapper?
2. **Note the exact task/goal:** `jar`, `bootJar`, `war`, `bootWar`, `repackage`?
3. **List actual file names:** `target/` or `build/libs/`, including classifiers, `.original`, and plain files.
4. **Inspect the suspect file:** `jar tf`, manifest; check whether classes sit at root or in `BOOT-INF/classes`.
5. **Confirm the goal:** running `java -jar`, deploying to a WAR container, or publishing a library for other modules?
6. **Cross-check CI/Docker/publishing:** which artifact and classifier are actually consumed?
7. **Only with evidence in hand** adjust `archiveClassifier`, `<classifier>`, `attach`, or task enablement; rebuild cleanly from trusted sources and re-verify.

## 11. Hands-On Labs: Inspecting Both Archive Types

### Lab A – Gradle

1. Create a project with `build.gradle` from Section 3 and `DemoApplication` from Section 7, using Java 17+ and a compatible Gradle Wrapper.
2. Run `./gradlew clean jar bootJar`, then list `build/libs`. With defaults unchanged, expect one `-plain.jar` and one unclassified JAR.
3. Inspect both with `jar tf`. Verify whether the application class sits at the **root** or in `BOOT-INF/classes`; check for `BOOT-INF/lib` and the Boot loader.
4. Run `java -jar` on the **Boot JAR** and observe `ARCHIVE_OK` printed by the program. Try the plain JAR in a practice copy and explain any manifest/dependency failure.
5. Add `bootJar.archiveClassifier='boot'` and `jar.archiveClassifier=''`; run a clean build and record the two new names.
6. Assume CI still copies `demo-0.0.1-SNAPSHOT.jar`; explain why after step 5 it would copy the **plain** JAR.
7. Answer: when should you not set `enabled=false` on `jar`? If you have library modules and native images, what must you verify?

### Lab B – Maven Without Classifier

1. Use the POM from Section 4 and `DemoApplication` from Section 7.
2. Run `./mvnw clean package`; list `target`.
3. Inspect `demo-0.0.1-SNAPSHOT.jar` and `demo-0.0.1-SNAPSHOT.jar.original` with `jar tf`. Compare `BOOT-INF/classes` against root classes.
4. Explain why the main `...jar` is now the **Boot JAR** even though Maven built a plain JAR first, and what `.original` is.
5. Run `java -jar` on the **main JAR after repackage**; confirm `ARCHIVE_OK`.
6. Answer: if you remove the repackage plugin yet still run `mvn package`, can you still rely on "the main JAR runs with `java -jar`"?

### Lab C – Maven with Classifier `exec`

1. On a branch or copy of the project, add `<classifier>exec</classifier>` to the Spring Boot Maven Plugin config.
2. Run `./mvnw clean package`; record the main plain `.jar` and Boot `-exec.jar`.
3. Use `jar tf` to prove `-exec.jar` has `BOOT-INF/classes` while the main JAR does not use that layout.
4. Run `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar` and confirm `ARCHIVE_OK`.
5. If testing `mvn install` to a local test repository, verify the `exec`-classified artifact is attached when `attach=true`; avoid installing/deploying to production repositories during practice.
6. Explain why another module may need the plain main artifact while operations needs `-exec.jar`.
7. Summarize the difference between "Gradle `-plain.jar` is a task output name" and "Maven `.jar.original` is a pre-repackage backup".

### Lab D – Auditing a Hypothetical Release Pipeline

Suppose a pipeline uses:

```text
build/libs/demo-0.0.1-SNAPSHOT.jar
build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

A commit changes `bootJar.archiveClassifier` to `boot` and `jar.archiveClassifier` to empty. Rewrite the deployment artifact path, `jar tf`, and `java -jar` commands, and specify the CI step that must fail if the layout no longer matches.

Also consider Maven switching from unclassified repackage to `<classifier>exec</classifier>`: which file **must no longer be `COPY`'d** into the Docker image, which file must be `COPY`'d instead, and why?

**Passing criteria:** do not just memorize file names. You must identify **which task/goal produces the file**, its **internal format**, **intended usage** (dependency vs. standalone execution), **classifier/attach if published**, and verify that the checked artifact path is the exact path deployed.

## 12. Official Reference Documentation

- Spring Boot 3.3 Gradle Plugin – Packaging Executable Archives, section `Packaging Executable and Plain Archives`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 Maven Plugin – Packaging Executable Archives, `repackage`, `.original`, `classifier`, `attach`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot – The Executable Jar Format, nested JARs and launcher: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Gradle – Working with Files, archive name/classifier and reproducible archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Maven – Introduction to the Build Lifecycle, `package`/`install`/`deploy` phases: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

**Remember:** the right file to run is never decided by a suffix alone. Trace **build task/goal → classifier and output name → layout/manifest → execution or consumption mode → real release stage**. Gradle `-plain` and Maven `.original` both refer to plain archives, yet **they do not share the same mechanism or release role**.