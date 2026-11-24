# Plain JARs and Executable JARs Differ in Contents and Startup Mechanism

When building Java applications, especially with Spring Boot, you may see two files with the same `.jar` extension that behave very differently. One file contains only the project's compiled classes and resources; the other packages all required dependencies as well and can be launched directly with `java -jar`. Properly distinguishing the two helps prevent `no main manifest attribute`, `ClassNotFoundException`, or `NoClassDefFoundError` errors during deployment.

In this lesson, a **plain JAR** (plain/ordinary JAR) refers to a standard JAR archive that primarily contains a module's classes and resources and has not been repackaged by Spring Boot to carry runtime dependencies. A **Spring Boot executable JAR** (also called a repackaged/boot JAR) is an archive with a dedicated structure and launcher for running a Spring Boot application from a single file. This classification is **based on structure and actual runnability**, not two different file extensions.

**Learning objectives:** (1) explain `META-INF/MANIFEST.MF`, `Main-Class`, and `Start-Class`; (2) read the `BOOT-INF/classes`, `BOOT-INF/lib`, and Spring Boot loader structure; (3) understand when to use `java -cp` and when to use `java -jar`; (4) build and inspect both types of JARs with Maven or Gradle; (5) distinguish between a plain JAR, an executable Boot JAR, a shaded/uber JAR, and a traditional runnable Java JAR.

## 1. The `.jar` Extension Does Not Indicate Runnability

A JAR (*Java ARchive*) is based on the ZIP format; it can contain `.class` files, resources, `META-INF/MANIFEST.MF`, and other metadata. A JAR can serve as a library, a command-line tool, or an application. **Simply having a `.jar` extension does not mean it can be run with `java -jar`.**

A JAR that merely contains a class with `public static void main(String[] args)` is still **not enough** for `java -jar` to know which class to select if the manifest does not declare an entry point. Conversely, a simple Java JAR with no external dependencies can still be run with `java -jar` with just `Main-Class` in the manifest; it does not necessarily have to be a "fat JAR".

Three common cases:

| Case | Main Contents | Typical Execution |
| --- | --- | --- |
| Plain/library JAR | `.class` files and resources of a module; does not bundle external dependencies | Placed on the **classpath** of another application; or run via `java -cp` with the main class and full classpath |
| Traditional runnable Java JAR | Plain JAR with `Main-Class` in the manifest; dependencies may have to reside externally | `java -jar app.jar` if the entry point and required libraries can be found |
| Spring Boot executable JAR | Boot loader + `BOOT-INF/classes` + runtime JARs inside `BOOT-INF/lib` | `java -jar app.jar`; Boot loader sets up the classpath from nested JARs |

Therefore, **"executable JAR" in the Boot context does not mean Java only supports Boot JARs**. What sets Boot apart is its ability to carry and load **nested dependency JARs** according to the Boot layout, rather than some magic that turns a `.jar` into an OS-native executable independent of the JVM.

## 2. Inspecting the Structure of Both Archives Directly

### 2.1. A Typical Plain JAR

Suppose an application has the main class `dev.example.jar.BootJarDemoApplication`:

```text
boot-jar-demo-1.0.0-plain.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/                     (may be present when built with Maven)
└── dev/
    └── example/
        └── jar/
            └── BootJarDemoApplication.class
```

The application's Java class sits **at the root following the package path**: `dev/example/jar/BootJarDemoApplication.class`. If the application also uses Spring Framework, Jackson, Tomcat, logging, and so on, those libraries **are not automatically bundled into the plain JAR**. They must be supplied via an external classpath, appropriate manifest configuration, or another packaging mechanism.

A plain JAR can be used as a **library** in a larger application or as input to another packaging/distribution pipeline. The word "plain" describes not being repackaged with the Spring Boot loader; it **does not assert** that the JAR lacks an entry point or cannot run in all cases.

### 2.2. Spring Boot Executable JAR

```text
boot-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
├── BOOT-INF/
│   ├── classes/
│   │   └── dev/example/jar/
│   │       └── BootJarDemoApplication.class
│   └── lib/
│       ├── spring-boot-*.jar
│       ├── spring-web-*.jar
│       ├── jackson-*.jar
│       └── other runtime dependencies
└── [layer metadata, if present]
```

Here, `BOOT-INF/classes` holds **the application's classes and resources**; `BOOT-INF/lib` holds **the dependency JARs**. The JARs in `BOOT-INF/lib` are preserved as **JARs nested inside a JAR**, rather than unpacking all library `.class` files into a single directory as some shaded JAR approaches do.

`org.springframework.boot.loader.launch.JarLauncher` is the launcher class in Spring Boot 3.3. It understands `BOOT-INF/classes` and `BOOT-INF/lib`, prepares the appropriate classloader, and then invokes the application's real main method. A standard Java classpath loader does not automatically load all JARs residing inside another JAR using this layout.

**Important consequence:** Two JARs can contain **the same application code** yet have different internal paths and dependency-loading strategies. Consequently, running them is not a matter of simply renaming the file while keeping all `java` arguments unchanged.

## 3. The Manifest Determines the Entry Point

The `META-INF/MANIFEST.MF` file is standard JAR metadata. Two attributes to distinguish in this lesson:

- **`Main-Class`**: used by the Java launcher to identify the class containing the `public static void main(String[] args)` method when running `java -jar`.
- **`Start-Class`**: the attribute used by the Spring Boot loader to identify **the application's main class**. This is not a standard Java launcher attribute name for selecting an entry point.

Example of a plain runnable Java JAR:

```text
Manifest-Version: 1.0
Main-Class: dev.example.cli.Hello
```

Example of a Spring Boot 3.3 executable JAR:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.jar.BootJarDemoApplication
Spring-Boot-Version: 3.3.13
```

These are **illustrative manifest lines**; build tools may add other attributes such as classpath/layer indices or build metadata. Do not expect manifest contents to match byte-for-byte across projects.

Boot startup sequence:

```text
java -jar boot-jar-demo-1.0.0.jar
        |
        v
JVM reads META-INF/MANIFEST.MF
        |
        v
Main-Class = org.springframework.boot.loader.launch.JarLauncher
        |
        v
Boot loader opens BOOT-INF/classes and BOOT-INF/lib/*.jar
        |
        v
Start-Class = dev.example.jar.BootJarDemoApplication
        |
        v
BootJarDemoApplication.main(args)
        |
        v
SpringApplication.run(...) -> Spring context -> web server
```

**Do not change `Main-Class` to the application class in a Boot JAR** while keeping the `BOOT-INF` structure: the application will lose the launcher responsible for resolving the nested classpath. Conversely, a plain JAR without the Boot loader will have no idea what the `JarLauncher` class is. The packaging plugin sets the corresponding attributes; configure the main class in the **Spring Boot plugin** or appropriate project metadata instead of manually editing the manifest inside an already-built JAR.

## 4. How Do `java -cp` and `java -jar` Actually Differ?

### 4.1. `java -cp`: You Supply the Classpath and Main Class Yourself

Example:

```bash
java -cp "app.jar:lib/*" dev.example.jar.BootJarDemoApplication
```

This example is for Linux/macOS; Windows uses `;` to separate classpath entries:

```powershell
java -cp "app.jar;lib/*" dev.example.jar.BootJarDemoApplication
```

Java looks for `dev/example/jar/BootJarDemoApplication.class` inside `app.jar`, while libraries reside in the JARs inside `lib/`. The `*` after a directory in the classpath is the Java launcher's classpath wildcard mechanism, not a mechanism for recognizing Boot's nested JARs. `java -cp` is especially useful when you want to run a **plain JAR** with dependency JARs placed separately.

If a class is in the JAR but the libraries it imports at startup are not on the classpath, class-loading errors can occur. For a Spring Boot application using `spring-boot-starter-web`, adding only the plain application JAR to `-cp` is **not enough**.

### 4.2. `java -jar`: The JVM Reads the Entry Point from the Manifest

```bash
java -jar boot-jar-demo-1.0.0.jar
```

The Java launcher reads the JAR's manifest, invokes `Main-Class`, and passes application arguments to the main method. For a Boot JAR, `Main-Class` is `JarLauncher`, and Boot's launcher builds the internal classpath from `BOOT-INF`.

When using `-jar`, classpath settings via `-cp`/`CLASSPATH` **do not take effect the way `-cp` execution does**, so do not expect:

```bash
java -cp "lib/*" -jar plain.jar
```

to automatically resolve external libraries via `-cp`. For a plain runnable JAR that needs external libraries, you can declare `Class-Path` in the manifest for JARs at appropriate paths, or use `java -cp "plain.jar:lib/*" package.Main` directly. For a Spring Boot executable JAR, use the launcher via `java -jar` as designed.

### 4.3. Common Errors When Choosing the Wrong Launch Mode

| Command/Action | Possible Outcome | Why |
| --- | --- | --- |
| `java -jar plain.jar` without `Main-Class` | `no main manifest attribute` | The Java launcher does not know the main class |
| `java -jar plain.jar` with `Main-Class` but missing Spring runtime libs | `ClassNotFoundException` or `NoClassDefFoundError` | Dependencies are missing from the classpath |
| `java -cp plain.jar package.Main` without required libs | Runtime class-loading failure | The plain JAR does not bundle dependencies |
| `java -cp boot.jar package.Main` | Cannot find application main class | Boot JAR classes reside under `BOOT-INF/classes`, not at the classpath root |
| `java -jar boot.jar` with valid manifest and complete Boot loader | Starts up if application/config are valid | The loader opens nested dependency JARs |
| Renaming `plain.jar` to `boot.jar` | Does not automatically change runnability | File name does not restructure the archive or add the loader |

## 5. A Plain Java Experiment to Separate `Main-Class` from "Fat JAR"

Before using Spring Boot, verify the Java launcher rules with a class that needs no external libraries.

Create `src/example/Hello.java`:

```java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello JAR");
    }
}
```

On a system with JDK 17+, in the directory containing `src/`:

```bash
mkdir -p out
javac -d out src/example/Hello.java

# Plain JAR without declaring Main-Class
jar --create --file hello-plain.jar -C out .

# Java knows the main class via -cp and the class name
java -cp hello-plain.jar example.Hello

# Add Main-Class when creating a JAR with an entry point
jar --create --file hello-runnable.jar --main-class example.Hello -C out .

java -jar hello-runnable.jar
```

Both commands print to stdout:

```text
Hello JAR
```

Running `java -jar hello-plain.jar` (without declaring an entry point) reports a missing `Main-Class` error similar to:

```text
no main manifest attribute, in hello-plain.jar
```

This example proves that an **ordinary Java JAR can be run with `java -jar`** if it has `Main-Class` in the manifest and all dependent classes can be found. It has no `BOOT-INF` or Spring Boot loader because it needs no external dependencies. The core problem Spring Boot solves is **packaging an application with many dependency JARs** into a single executable archive that Java can launch.

If practicing on Windows PowerShell, create the directory with `New-Item -ItemType Directory out -Force` instead of `mkdir -p out`. The `javac`, `jar`, and `java` commands remain the same; the package directory structure must exist.

## 6. Complete Spring Boot Maven Example: Same Source, Two JARs with Different Layouts

Use Maven 3.9.x and JDK 17. Create the project:

```text
boot-jar-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/jar/BootJarDemoApplication.java
    └── test/java/dev/example/jar/BootJarDemoApplicationTests.java
```

### 6.1. `pom.xml`

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

    <groupId>dev.example</groupId>
    <artifactId>boot-jar-demo</artifactId>
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

**Why are there two packaging steps?** With `<packaging>jar</packaging>`, the Maven JAR Plugin creates a plain JAR during the `package` phase. `spring-boot-starter-parent` already provides an execution for the `spring-boot:repackage` goal, and declaring `spring-boot-maven-plugin` under `<plugins>` triggers that goal. It reads the original JAR, adds the launcher, changes the layout, embeds runtime dependencies, and produces the Boot executable JAR replacing the main artifact. The original plain file is typically kept with the `.jar.original` extension.

The Spring Boot BOM selects dependency versions; **importing the BOM alone does not automatically bind the `repackage` goal**. If you do not use the starter parent and only import the BOM, you must explicitly configure the Spring Boot Maven Plugin with the appropriate version and `repackage` goal execution.

### 6.2. Application Class

File `src/main/java/dev/example/jar/BootJarDemoApplication.java`:

```java
package dev.example.jar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootJarDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootJarDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello executable JAR";
    }
}
```

File `src/test/java/dev/example/jar/BootJarDemoApplicationTests.java`:

```java
package dev.example.jar;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BootJarDemoApplicationTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void endpointResponds() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello executable JAR"));
    }
}
```

No `application.yml` is required for the example to run on the default HTTP port 8080 unless the environment overrides `server.port`. The test uses MockMvc, so it does not need to start a separate HTTP server on port 8080.

### 6.3. Build and Verify Both Files

```bash
mvn -version
mvn clean verify
ls -lh target/boot-jar-demo-1.0.0.jar*
```

Under the default configuration:

```text
target/boot-jar-demo-1.0.0.jar
target/boot-jar-demo-1.0.0.jar.original
```

- The `.jar` file is the **Spring Boot executable JAR** after `repackage`.
- The `.jar.original` file is the **plain JAR before `repackage`**. Even though the extension ends with `.original`, its content is still a valid JAR/ZIP archive; it is simply the plugin's backup output.

Inspect the entries:

```bash
jar tf target/boot-jar-demo-1.0.0.jar
jar tf target/boot-jar-demo-1.0.0.jar.original
```

In the Boot JAR, look for entries:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/jar/BootJarDemoApplication.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
```

In the plain JAR, look for:

```text
dev/example/jar/BootJarDemoApplication.class
```

The plain JAR does not contain the entire `BOOT-INF/lib` directory as the Boot JAR does. The list above only excerpts notable entries; an actual JAR contains many more classes/resources/libraries and the listing order is not fixed.

### 6.4. Running the Boot JAR Directly

```bash
java -jar target/boot-jar-demo-1.0.0.jar
```

After startup succeeds, in another terminal:

```bash
curl -s http://localhost:8080/hello
```

Body:

```text
Hello executable JAR
```

This is the standard model for containers, VMs, or deployment pipelines. The JAR already contains application classes, runtime dependencies, and the Boot loader; the host machine still needs a **compatible JVM**, and may still need databases, networking, environment variables, or external services depending on application configuration. The term "self-contained" here does not mean a single JAR file carries the OS/JDK and every external service.

## 7. Running the Spring Boot Plain JAR: Supplying an External Classpath

The plain JAR still contains `BootJarDemoApplication.class` and can execute the main method, but it **does not carry the required Spring runtime JARs**. Therefore, if you run:

```bash
java -cp target/boot-jar-demo-1.0.0.jar.original dev.example.jar.BootJarDemoApplication
```

the application usually fails to start because Spring Boot/Spring Framework is missing from the classpath. Supply all runtime dependencies.

First, use the Maven Dependency Plugin to copy them into a separate directory:

```bash
mvn dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
```

To have a `.jar` file extension that is easy to use on the Java classpath, copy the original JAR:

```bash
cp target/boot-jar-demo-1.0.0.jar.original target/plain.jar
```

Then run on Linux/macOS:

```bash
java -cp "target/plain.jar:target/dependency/*" dev.example.jar.BootJarDemoApplication
```

On PowerShell/Windows, replace the last two commands with:

```powershell
Copy-Item target/boot-jar-demo-1.0.0.jar.original target/plain.jar
java -cp "target/plain.jar;target/dependency/*" dev.example.jar.BootJarDemoApplication
```

If the system has all dependencies and the port is not overridden, the `/hello` endpoint still returns `Hello executable JAR`. That is **the same application logic**, except the classpath is supplied externally via `-cp`.

**This is a hands-on exercise to understand the mechanism**, not necessarily the preferred deployment approach. In production, pick one clear packaging strategy: an executable Boot JAR, a container image, an appropriate WAR, or a controlled external classpath distribution. Avoid mixing approaches in ways that cause missing or duplicate library versions.

**Do not use `java -jar target/plain.jar -cp ...` to resolve the classpath**. When `-jar` is used, remember that the Java launcher prioritizes the main entry from the JAR's manifest and does not take the classpath the way `java -cp` does. For a plain archive lacking `Main-Class`, the reliable way is to invoke the class containing the main method as shown above along with all required dependencies.

## 8. Gradle: `jar` and `bootJar` Are Two Different Tasks

With Spring Boot Gradle Plugin 3.3, when the Java plugin is applied:

- **`jar`**: creates a regular plain JAR, with the `plain` classifier by default, for example `boot-jar-demo-1.0.0-plain.jar`.
- **`bootJar`**: creates a Spring Boot executable JAR, by default e.g. `boot-jar-demo-1.0.0.jar`.
- **`build`** may produce outputs according to lifecycle/task dependencies; the example below explicitly invokes `bootJar` and `jar` for easy inspection.

### 8.1. `settings.gradle` and `build.gradle`

Create `settings.gradle`:

```groovy
rootProject.name = 'boot-jar-demo'
```

Create `build.gradle` (Groovy DSL), using the same two Java files from Section 6:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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

tasks.register('copyRuntimeLibs', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('external-libs')
}
```

For a standalone Gradle project, place the two Java source files at `src/main/java/dev/example/jar/BootJarDemoApplication.java` and `src/test/java/dev/example/jar/BootJarDemoApplicationTests.java`; **do not keep `pom.xml` alongside it unless intentionally maintaining two build definitions**.

The Gradle build uses the `org.springframework.boot` plugin to create the `bootJar` task. The Dependency Management Plugin works alongside the Boot plugin to import the corresponding BOM versions. The `copyRuntimeLibs` task is **added solely to demonstrate running the plain JAR**: it copies JARs from `runtimeClasspath` into a directory and is not needed for the Boot executable JAR.

### 8.2. Building and Inspecting Both Files

If a Gradle Wrapper compatible with the Spring Boot plugin is available, run (on Windows use `gradlew.bat`):

```bash
./gradlew clean test bootJar jar copyRuntimeLibs
ls -lh build/libs/
jar tf build/libs/boot-jar-demo-1.0.0.jar
jar tf build/libs/boot-jar-demo-1.0.0-plain.jar
```

File names in this example configuration:

```text
build/libs/boot-jar-demo-1.0.0.jar        -> executable Boot JAR
build/libs/boot-jar-demo-1.0.0-plain.jar  -> plain JAR
```

In practice, archive names can differ when a project changes `archiveBaseName`, `archiveVersion`, `archiveClassifier`, or uses a custom task. Do not infer from the `.jar` extension; verify via the manifest and contents.

Start the Boot JAR:

```bash
java -jar build/libs/boot-jar-demo-1.0.0.jar
```

Or run the plain JAR with the external dependencies copied by the demonstration task:

```bash
java -cp "build/libs/boot-jar-demo-1.0.0-plain.jar:build/external-libs/*" dev.example.jar.BootJarDemoApplication
```

Windows:

```powershell
java -cp "build/libs/boot-jar-demo-1.0.0-plain.jar;build/external-libs/*" dev.example.jar.BootJarDemoApplication
```

Run only **one instance at a time** if both use port 8080. Both approaches can serve the same `/hello` endpoint if the runtime classpath and configuration are correct.

### 8.3. Changing the Classifier and Avoiding Accidental Publishing

The Spring Boot Gradle Plugin normally assigns `plain` as the classifier for `jar` so its output does not overwrite `bootJar`. If a team wants to change the convention, it must adjust the corresponding tasks and check everywhere the artifact is consumed:

```groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}
tasks.named('jar') {
    archiveClassifier = ''
}
```

This is an **illustrative fragment for changing output names**, not needed for the example above. After configuring it this way, the plain JAR has no classifier, while the executable JAR carries the `-boot.jar` suffix. Therefore, CI must not hard-code "the file without a suffix is always the executable JAR" if the project allows changing classifiers.

In a library project, you often only want the plain JAR so other modules can depend on it via a standard classpath. In a Spring Boot service deployment project, you usually need `bootJar`. When publishing to a Maven repository, you must check which artifact the task/publication selects; seeing two files in `build/libs` does not confirm which file was published.

## 9. Why Not Just Unpack All Dependencies into One JAR?

There are multiple ways to put a Java application with many dependencies into a single artifact. A Spring Boot executable JAR is **one specific approach**:

| Packaging Type | Organization | Startup Mechanism | Pros / Considerations |
| --- | --- | --- | --- |
| Plain JAR + external libs | App JAR and `lib/*.jar` directory kept separate | `java -cp ... package.Main`, or valid manifest `Class-Path` | Separate JARs are explicit; must distribute and manage classpath |
| Plain runnable JAR without external dependencies | Application classes + `Main-Class` | `java -jar file.jar` | Lightweight and simple; only suitable when all needed classes are already present |
| Shaded/uber JAR | Usually **unpacks** dependency classes/resources into a single archive | `java -jar file.jar` if main manifest is set | May require handling duplicate resources/service descriptors and class conflicts |
| Spring Boot executable JAR | App classes in `BOOT-INF/classes`; library JARs **nested in `BOOT-INF/lib`**; Boot loader | `java -jar file.jar` | Easy to track nested libraries; requires a launcher that understands the Boot layout |
| Spring Boot executable WAR | App in `WEB-INF/classes`, libs in `WEB-INF/lib`/`lib-provided` per packaging | `java -jar file.war` if executable; or deploy to a web container depending on config | Serves WAR/container use cases, unlike the JAR layout |

Do not call every fat JAR "packaged identically to Spring Boot". A **shaded JAR** typically unpacks dependency classes into the root; a Spring Boot **nested JAR** keeps each dependency as a separate JAR. These formats affect resource lookup, classloaders, dependency security scanning, and debugging.

An application with many libraries can still sometimes run with a plain JAR and an external `lib` directory, provided the classpath matches. Thus, the difference does not lie in "a plain JAR can never run", but in **self-containment and how Java/Boot locates the required classes**.

## 10. Inspect Manifest and Contents Instead of Guessing from File Names

A technical checklist you can run on a built JAR:

**Step 1: confirm the actual artifact.**

```bash
ls target/*.jar*
# Or with Gradle:
ls build/libs/*.jar
```

**Step 2: list contents and look for Boot layout indicators.**

```bash
jar tf target/boot-jar-demo-1.0.0.jar
```

Indicators of a Boot executable JAR:

```text
BOOT-INF/classes/dev/example/jar/BootJarDemoApplication.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
```

The corresponding plain build typically has only `dev/example/jar/BootJarDemoApplication.class` at the root, without any of the structure above.

**Step 3: read the manifest.**

If `unzip` is available, use:

```bash
unzip -p target/boot-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Or use JDK `jar` in a separate working directory:

```bash
mkdir -p target/manifest-inspect
cd target/manifest-inspect
jar xf ../boot-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

A Boot 3.3 build needs `Main-Class` pointing to the appropriate Boot launcher and `Start-Class` pointing to the application main class. Even if both attributes are set correctly, if libraries/the loader have been deleted or the archive structure was altered, the JAR still may not run; **a valid manifest is a necessary condition, not sufficient proof**.

**Step 4: launch it for real.**

```bash
java -version
java -jar target/boot-jar-demo-1.0.0.jar
```

Check the startup logs and HTTP endpoint, not just `BUILD SUCCESS`. With Spring Boot 3.3, the project in this lesson uses Java 17, so a JVM older than the target Java version may throw `UnsupportedClassVersionError` even if the JAR is packaged completely correctly.

**Step 5: compare sizes meaningfully.**

A Boot executable JAR is usually larger than a plain JAR because it contains runtime libraries, but **do not use file size as the sole criterion**. A plain/shaded JAR, embedded resources, or compression settings can cause size not to reflect runnability. Concluding based on manifest + layout + actual execution is the reliable approach.

## 11. Which JAR Should Be Used for Libraries, Applications, and CI/CD?

### Library Modules

A library providing Java types, helpers, or APIs for other modules normally publishes a **plain JAR** so the dependency resolver (Maven/Gradle) can resolve related libraries itself. If a Spring Boot executable JAR is published as an ordinary dependency, consumers may fail to find classes because they reside under `BOOT-INF/classes` instead of the root.

**Rule:** do not add a Spring Boot executable JAR into `<dependencies>` and expect Maven to treat it like a standard library JAR.

In a multi-module project, a `common` module can produce a plain JAR while a `web-app` module produces a Boot executable JAR. The application module uses `common` as a dependency and packages it into `BOOT-INF/lib` or according to valid packaging configuration.

### Spring Boot Service Modules

A Spring Boot service deployed on the JVM typically prefers an executable Boot JAR. Pipeline:

```text
source + pinned build config
            |
            v
compile -> test -> package/bootJar
            |
            v
verify archive structure and runtime dependencies
            |
            v
smoke test: java -jar ...
            |
            v
publish EXACT checked artifact
            |
            v
deploy on target JVM/container
```

Do not build one JAR for testing and then rebuild another JAR with different profile/dependency settings right before deployment without inspecting it. Use artifact identity (version, checksum, or digest) to verify that production runs **the exact output that passed the gate**.

### Container Images

You can use an executable JAR as input for a container image or Spring Boot build-image workflows. **A JAR does not include a JDK**, so the container base image must have a compatible Java runtime, or the image-building tool must supply an appropriate runtime. A command like `java -jar /app/app.jar` still relies on the Boot loader and classpath inside the JAR.

### Layered JARs

Spring Boot supports **layers** and metadata such as `BOOT-INF/layers.idx` to facilitate creating container layers. Layers do not turn a Boot JAR into a plain JAR: classes remain in `BOOT-INF/classes`, and dependencies remain in `BOOT-INF/lib`. The layer index can be added by the build plugin when the appropriate layered archive mechanism is enabled; do not try to pass `layers.idx` to `java -cp`.

## 12. Real-World Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `java -jar ...jar` → `no main manifest attribute` | Plain JAR without `Main-Class` | Run with `java -cp ... Main` or package an executable JAR properly |
| `java -jar ...jar` → `ClassNotFoundException` | Manifest points to wrong main/loader or classes are not in expected location | Inspect `META-INF/MANIFEST.MF` and `jar tf` |
| `NoClassDefFoundError: org/springframework/...` when running plain JAR | Spring libraries missing from classpath | Supply runtime JARs via dependency resolver, use `-cp`, or use Boot JAR |
| `java -cp boot.jar app.Main` cannot find main class | Boot places app classes in `BOOT-INF/classes` | Use `java -jar` with the Boot launcher |
| `java -jar` finds Main-Class but embedded server is missing | Dependency/packaging missing web starter or wrong scope | Inspect `BOOT-INF/lib`, POM/Gradle runtime graph, and Spring configuration |
| Maven only produces plain `.jar` despite BOM import | Spring Boot Maven Plugin not applied/repackaged | Declare plugin/execution appropriately, check effective POM |
| Maven `.jar.original` is much smaller than `.jar` | Expected because it is the plain archive before repackage | Keep them distinct; do not accidentally deploy `.original` |
| Gradle produces both `-plain.jar` and unclassified JAR | Both `jar` and `bootJar` exist | Pick the right output; do not upload based solely on a glob |
| `UnsupportedClassVersionError` | Target JVM is too old for compiled bytecode | Use a Java runtime compatible with `java.version`/toolchain |
| App runs locally but misses classes in production | Local IDE classpath includes dependencies not packaged in the artifact | Check dependency scopes, `BOOT-INF/lib`, final artifact, and deploy environment |
| Servlet app starts then reports port 8080 in use | Another process is occupying the port | Stop the other process or pass `--server.port=8081` for the new instance |
| JAR reported as "not a valid jar" after manual editing | Truncated/corrupted ZIP/archive or malformed edits | Rebuild from source; verify hash and `jar tf` |
| Using a plain JAR as a dependency that went through Spring Boot repackage | Consumer cannot see classes under classpath root | Publish a plain classifier/JAR for the library or split modules |
| Shaded JAR loses service providers/resources | `META-INF/services` or resource collisions when unpacking archives | Configure shade transformers or choose Boot nested-JAR packaging |

### Ordered Troubleshooting Workflow

1. **Inspect the exact command executed**: `java -jar` or `java -cp`? Did the command pass a main class?
2. **Check the JDK:** `java -version` and `mvn -version`/Gradle toolchain.
3. **Identify the artifact:** right module, right version, right classifier, newly built file?
4. **Read the archive:** does `jar tf` show `BOOT-INF` and the loader? Are application classes at the root or in `BOOT-INF/classes`?
5. **Read the manifest:** are `Main-Class` and, if it is a Boot JAR, `Start-Class` sensible?
6. **Inspect the runtime dependency graph:** Maven `dependency:tree` or Gradle `dependencies --configuration runtimeClasspath`. Compare against the packaged JAR.
7. **Try starting it and run a smoke test:** do not draw conclusions from a successful build alone.
8. **Fix the build script/POM, do not manually patch a published archive**, then rebuild and inspect the new artifact.

## 13. Self-Check Exercises

**Scenario A.** A JAR contains `example/Hello.class` with a main method but no `Main-Class`. Can it be run with `java -jar`?

*Answer:* Not via the standard `java -jar` mechanism. Run `java -cp hello.jar example.Hello` or recreate the JAR with a manifest containing `Main-Class: example.Hello`.

**Scenario B.** A Spring Boot Maven build outputs two files: `demo.jar` and `demo.jar.original`. Which file runs directly as a standard Boot executable?

*Answer:* `demo.jar` is the main executable archive after `repackage`; `.jar.original` is the original plain JAR that typically lacks runtime dependencies. Check the manifest and `jar tf` to confirm the actual output.

**Scenario C.** Gradle outputs `demo-1.0.0.jar` and `demo-1.0.0-plain.jar`. Which file should be published as an application run via `java -jar`?

*Answer:* Under the default Spring Boot Gradle Plugin convention, the file **without `-plain`** is the executable Boot JAR. If task classifiers have been customized, inspect the `bootJar` output instead of relying on the name.

**Scenario D.** A colleague sets `Main-Class: dev.example.jar.BootJarDemoApplication` in a Spring Boot nested JAR and deletes the Boot launcher to "simplify" it. What is wrong?

*Answer:* The application class sits under `BOOT-INF/classes` and dependencies sit under `BOOT-INF/lib`; the standard Java launcher does not automatically load nested JARs in the Boot layout. Keep the Boot loader and proper manifest instead of editing it manually.

**Scenario E.** A plain JAR has `Main-Class` in its manifest, but startup fails saying `org.springframework.boot.SpringApplication` cannot be found. Is `Main-Class` wrong?

*Answer:* Not necessarily. The main method may be right, while Spring Boot runtime dependencies are missing from the classpath. Add the libraries or package a Boot executable JAR.

**Scenario F.** For the same application, running `java -cp "plain.jar:lib/*" dev.example.jar.BootJarDemoApplication` and `java -jar boot.jar` both return `Hello executable JAR`. Do the two files have the "same contents"?

*Answer:* No. They may contain the same app code/behavior, but the Boot JAR carries nested dependencies and the loader; the plain JAR requires external JARs on the classpath. "Producing the same output" does not prove identical layout or dependency contents.

**Scenario G.** Someone claims an "executable JAR" must run when double-clicked on any OS without installing Java. Conclusion?

*Answer:* False. `java -jar` requires a compatible JVM; double-click execution or distributing a native launcher is a separate topic. You can use a container runtime or native image in a separate workflow, but a JAR does not turn into a native machine binary on its own.

**Scenario H.** Building with `mvn clean package` succeeds; why do you still need to check `jar tf` and run a smoke test?

*Answer:* A successful build only confirms the configured goals ran; it could still package the wrong classifier, miss a runtime dependency, or have a broken runtime configuration. Inspecting the archive and running it verifies the exact output intended for deployment.

## 14. Checklist for Choosing the JAR Type for a Project

- **Module type:** library consumed via Maven/Gradle or standalone deployed Spring Boot application?
- **Packaging goal/task:** Maven `jar:jar` or `spring-boot:repackage`? Gradle `jar` or `bootJar`?
- **Main class:** is there a `main`, and does manifest `Main-Class` point to the application or Boot `JarLauncher`?
- **Layout:** application classes at the package root or `BOOT-INF/classes`? Runtime dependencies external or in `BOOT-INF/lib`?
- **Execution method:** `java -cp ... Main` requiring external libs or `java -jar ...` using the Boot launcher?
- **JDK:** is the target runtime compatible with Java 17 or the chosen toolchain?
- **Smoke test:** does the application start up and serve endpoints according to expected configuration?
- **Traceability:** have artifact version/checksum been verified and is the right file being deployed?
- **Publishing:** library modules publish plain JARs; application modules publish executable Boot JARs if that is the target.
- **No blind guessing:** do not rely solely on `.jar`, `-plain`, or size; verify **manifest + archive layout + runtime behavior**.

**Rule to remember:** A **Plain JAR** typically carries only the module's compiled classes/resources and requires an accurate classpath if the application has external dependencies. A **Spring Boot executable JAR** carries application classes in `BOOT-INF/classes`, dependency JARs in `BOOT-INF/lib`, and the Boot `JarLauncher` so `java -jar` can run. A simple Java JAR with `Main-Class` can also be "executable" without being Spring Boot; therefore, always specify **the exact archive type**.

### Official Documentation

- Spring Boot 3.3 — Developing Your First Spring Boot Application (Creating an Executable Jar): https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot 3.3.13 API — JarLauncher: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/JarLauncher.html
- Spring Boot — Executable Jar Specification, Launching Executable Jars: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Spring Boot — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Gradle Plugin, Packaging Executable and Plain Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Oracle JDK 17 — Java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17 — JAR tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html