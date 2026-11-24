# Reading `META-INF/MANIFEST.MF` and Distinguishing `Main-Class` from `Start-Class`

**Core question:** When running `java -jar app.jar`, which class does the JVM invoke first? In an **executable Spring Boot JAR**, why does the manifest contain both `Main-Class` and `Start-Class`, and which class name is the one annotated with `@SpringBootApplication`?

**Short answer:**

- **`Main-Class`** is a standard attribute of the Java JAR format. The Java launcher reads this value when running `java -jar` and invokes the `public static void main(String[] args)` method of the specified class. In a typical executable Spring Boot JAR, its value is the **Spring Boot launcher**, such as `org.springframework.boot.loader.launch.JarLauncher` in Spring Boot 3.3.
- **`Start-Class`** is an attribute **specifically used by the Spring Boot launcher** to locate the actual application class, such as `com.example.demo.ManifestDemoApplication`. The JVM does not interpret `Start-Class` as a standard entry point; the **Boot launcher** reads it after being invoked.
- **`META-INF/MANIFEST.MF`** is a metadata file inside the JAR archive. It helps identify the entry point and may contain additional attributes. Reading the manifest alone is **not enough** to guarantee the archive contains all classes and dependencies required to run; you must also inspect its contents and run the artifact.

This lesson sits in the context of Spring Boot **executable JARs**, focusing on reading manifests, understanding class loading, and diagnosing entry-point errors. Examples use **Java 17+**, Spring Boot **3.3.5**, and a compatible Gradle version pinned for reproducibility; this is **not** a claim about the latest Spring Boot release.

## 1. What Is a JAR Manifest?

A JAR (*Java ARchive*) is a ZIP-format archive containing classes, resources, and metadata. A JAR can contain a `META-INF/MANIFEST.MF` file. This file follows attribute-pair syntax:

~~~text
Attribute-Name: Attribute value
Another-Attribute: Another value

~~~

The header section of the manifest contains **main attributes** scoped to the archive. Additional per-entry sections may follow. `Manifest-Version` describes the manifest format version; `Main-Class` is the attribute understood by the Java launcher for standard executable JARs.

### Example of a Plain Java JAR Manifest

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Hello

~~~

With this structure, if `com.example.Hello` exists in the archive and has a valid main method, Java can run:

~~~bash
java -jar hello.jar
~~~

`Main-Class` points **directly** to the application class. A plain JAR does not require `Start-Class`, and the Java launcher does not need that attribute.

### Example of a Spring Boot Executable JAR Manifest

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
Spring-Boot-Version: 3.3.5
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/

~~~

This is a **sample of key attributes that may appear**, not a verbatim copy of every Boot JAR. Extra attributes and ordering can vary by Spring Boot plugin, Gradle/Maven, archive layout, or build configuration. The crux lies in two lines:

- `Main-Class` → Spring Boot's bootstrap/launcher class;
- `Start-Class` → the developer-written class containing the `main` method.

Do not append `.class` or use path slashes in class names for these two attributes: both use the **fully qualified Java class name**, such as `com.example.demo.ManifestDemoApplication`.

### Be Careful When Reading Manifest Text

A manifest is a text file with specific formatting rules:

1. Attribute names and values are separated by a colon and a space.
2. Long lines may be **folded (wrapped)** onto the next physical line starting with **a single space**; that still belongs to the same logical value.
3. Sections can be separated by blank lines, and line endings may not match how a text editor displays them.
4. Unfamiliar names/values may be attributes defined by frameworks or build tools, which does not mean the Java launcher supports them.
5. To read them accurately across any OS, use the Java APIs `java.util.jar.JarFile` and `java.util.jar.Manifest` rather than splitting lines manually.

**Do not** write a custom parser assuming "each line is one complete attribute"; wrapped values can cause such parsing to return incorrect results.

## 2. `Main-Class` Is the Standard Java Entry Point

When running:

~~~bash
java -jar my-application.jar
~~~

the Java launcher opens the JAR, looks up the main section in `META-INF/MANIFEST.MF`, reads `Main-Class`, and attempts to run the corresponding class's method:

~~~java
public static void main(String[] args)
~~~

This is the Java process entry point under the `-jar` mechanism. If `Main-Class` is absent, the Java launcher typically reports an error similar to:

~~~text
no main manifest attribute, in my-application.jar
~~~

If the specified class does not exist on the classpath visible to the launcher, or lacks a valid main method, the application also fails to start normally. Exact messages vary by Java version and root cause.

### `Main-Class` Is Not a Spring Boot Annotation Concept

Putting `@SpringBootApplication` on a class **does not by itself make the Java launcher choose that class**. The annotation enables Spring Boot configuration and auto-configuration; entry-point selection for `java -jar` is governed primarily by the manifest and the Boot launcher mechanism. Therefore:

- A plain JAR can have `Main-Class: com.example.Hello` without using Spring.
- A Boot JAR can have `Main-Class: ...JarLauncher` while the `@SpringBootApplication`-annotated class is recorded in `Start-Class`.
- Putting only `Start-Class` in a plain JAR without `Main-Class` **will not** make `java -jar` work.

### Can `java -cp` Replace `java -jar`?

The syntax:

~~~bash
java -cp path/to/classes com.example.Hello
~~~

passes the **class directly** for the JVM to run instead of asking the JVM to look up `Main-Class` in a JAR. With `java -jar`, `-cp` does not act like the arbitrary classpath composition of `java -cp`; the Java launcher uses the `-jar` archive and its associated rules. A Spring Boot executable JAR also uses nested dependencies and a dedicated loader, so you cannot simply replace `java -jar boot.jar` with `java -cp boot.jar com.example.demo.ManifestDemoApplication` and expect equivalent behavior.

## 3. `Start-Class` Is the Spring Boot Launcher's Instruction

In an **executable Spring Boot JAR** with the default layout, the Spring Boot launcher performs work the plain Java launcher does not do on its own: opening the archive's internal structure, creating a classloader that sees **both application classes and nested dependency JARs**, and then invoking the actual application class.

Control flow:

~~~text
User
  |
  v
java -jar manifest-demo.jar
  |
  v
JVM reads META-INF/MANIFEST.MF
  |
  +-- Main-Class = org.springframework.boot.loader.launch.JarLauncher
  |       |
  |       v
  |   JVM runs JarLauncher.main()
  |       |
  |       +-- Boot launcher establishes classpath:
  |       |      BOOT-INF/classes/
  |       |      BOOT-INF/lib/*.jar (nested JARs)
  |       |
  |       +-- Reads Start-Class from manifest
  |       |      com.example.demo.ManifestDemoApplication
  |       |
  |       v
  |   Loader calls application's main(String[] args)
  |       |
  |       v
  |   SpringApplication.run(...) initializes Spring context
  |
  v
Application starts running
~~~

Key takeaway: **the JVM uses `Main-Class` to know what runs first; the Spring Boot loader uses `Start-Class` to know which class is the application main class.**

`Start-Class` is a valid custom manifest attribute: Java does not treat it as a standard entry point, yet frameworks can read it. Spring Boot build plugins normally determine the application main class, write `Start-Class`, and set `Main-Class` to the appropriate Boot launcher.

### Why Is an Intermediate Launcher Needed?

An executable Boot JAR usually does not "unpack" every dependency into one single class directory. It uses nested JARs to keep dependencies separated by artifact. A regular Java launcher does not natively treat nested JARs inside `BOOT-INF/lib` as standalone classpath entries passed via `-cp`. The Spring Boot launcher performs specialized loading so the archive can execute directly.

Therefore, **`Main-Class` pointing to `JarLauncher` is not a bug**: it is the design of an executable Spring Boot JAR. If you change it to the application class while keeping the default `BOOT-INF/...` layout, the plain JVM may fail to find classes or dependencies. Manually editing the manifest does not change the archive layout or class loading.

## 4. Reading the Archive Structure Alongside the Manifest

A typical executable Spring Boot JAR:

~~~text
manifest-demo.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/demo/ManifestDemoApplication.class
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── spring-context-<version>.jar
    │   └── other runtime libraries
    └── classpath.idx                    (may be present)
~~~

The tree above is a **diagram**, not an exhaustive or literal listing. Actual file names in `BOOT-INF/lib` contain concrete versions rather than literal `<version>`. Index files, layering metadata, and loader details may vary by plugin/version.

Cross-check:

| Check | Attribute/Path | Meaning |
| --- | --- | --- |
| Which class is the JVM told to run? | `Main-Class` | Entry point per the Java launcher |
| Which application class is the Boot loader told to run? | `Start-Class` | Application entry point under the Boot loader |
| Is the loader bytecode in the JAR? | `org/springframework/boot/loader/...` | Are the launcher components matching the manifest present? |
| Are application classes packaged? | `BOOT-INF/classes/...` | Is the application class present in the executable archive? |
| Are runtime libraries packaged? | `BOOT-INF/lib/...` | Are the needed nested dependency JARs present? |
| Which Boot version built it? | `Spring-Boot-Version` if present | Reference metadata; verify via plugin and actual JAR |
| Is classpath order/layering info present? | Index files/manifest attributes when present | Metadata depending on layout/build; does not decide application main class |

`Main-Class` and `Start-Class` **are only metadata**. They do not prove the class file exists or contains valid bytecode. Inspect the entry listing too whenever startup errors occur.

### `JarLauncher`, `WarLauncher`, and `PropertiesLauncher`

In Spring Boot 3.3:

- `org.springframework.boot.loader.launch.JarLauncher`: launcher for executable JARs, finding the app in `BOOT-INF/classes` and dependencies in `BOOT-INF/lib`.
- `org.springframework.boot.loader.launch.WarLauncher`: launcher for executable WARs, using `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` as appropriate.
- `org.springframework.boot.loader.launch.PropertiesLauncher`: a more flexible launcher supporting external library locations configured via options such as `loader.path` and related metadata when used.

Do not assume every Boot archive shares the exact same `Main-Class` value. To know which launcher is active, **read the manifest of that specific artifact**. For a WAR deployed to an **external servlet container**, startup may not go through `java -jar` directly, so the roles of the launcher and Servlet initializer must be distinguished per scenario.

### Watch Out for Spring Boot Versions

In Spring Boot 3.3, the typical launcher name is `org.springframework.boot.loader.launch.JarLauncher`. Older versions (such as Spring Boot 2.x and 3.0) used paths like `org.springframework.boot.loader.JarLauncher`. **Both names can be correct in artifacts belonging to their respective versions.**

Do not manually "fix" a Boot 2.x manifest to use Boot 3.3's launcher class name when the loader bytecode inside the JAR does not contain that class. After an upgrade, compare **plugin version, manifest, and archive contents**; do not treat one Internet example as a rigid standard across all releases.

## 5. Three Ways to Read `META-INF/MANIFEST.MF`

### 5.1. Check If the JAR Has a Manifest Entry Using the JDK

The JDK ships with the `jar` tool:

~~~bash
jar tf build/libs/manifest-demo.jar
~~~

`jar tf` only **lists entries** in the archive; it does not print manifest contents. In the output, look for:

~~~text
META-INF/MANIFEST.MF
~~~

If this line is missing, verify which file you opened (executable Boot JAR, plain JAR, or another file). Presence of the entry proves the manifest file exists, **not that the values of the two attributes are right**.

### 5.2. View Directly with `unzip -p` When Available

On Linux/macOS or systems with `unzip` installed:

~~~bash
unzip -p build/libs/manifest-demo.jar META-INF/MANIFEST.MF
~~~

`-p` writes the entry's contents to stdout without extracting the archive to the filesystem. This is a quick way to inspect the text. If comparing `Main-Class` and `Start-Class`, look for those two lines in the output; if a value is wrapped, join continuation lines properly. On Windows, `unzip` is not available in every environment, so you can use the Java inspector in the next section.

### 5.3. Extract Only One Entry with JDK `jar xf`

Example on Linux/macOS:

~~~bash
mkdir -p inspect-manifest
cd inspect-manifest
jar xf ../build/libs/manifest-demo.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Here `inspect-manifest/` is created from the project root and the JAR resides in `../build/libs/`. Use a separate directory to avoid accidentally **overwriting an existing `META-INF/MANIFEST.MF`** in the project. `jar xf` writes files to the filesystem, whereas `unzip -p` only prints contents. Do not extract the entire archive just to inspect two attributes.

Windows can use `jar xf` similarly, followed by `Get-Content .\META-INF\MANIFEST.MF` in PowerShell, though the most portable and shell-independent approach remains the Java API.

## 6. Writing a Working Java 17 Manifest Inspector

The Java API lets you read logical attributes from a manifest, including values folded across multiple lines, without writing custom text parsing.

Create **`ManifestInspector.java`** in any directory:

~~~java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ManifestInspector {
    private ManifestInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ManifestInspector <path-to-jar>");
            System.exit(2);
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                System.out.println("MANIFEST_MISSING");
                return;
            }

            Attributes attributes = manifest.getMainAttributes();

            System.out.println("Main-Class=" +
                    show(attributes.getValue(Attributes.Name.MAIN_CLASS)));
            System.out.println("Start-Class=" +
                    show(attributes.getValue("Start-Class")));
        }
    }

    private static String show(String value) {
        return value == null ? "(absent)" : value;
    }
}
~~~

This is a **standalone Java program**, needing no Spring Boot dependencies. It does two things:

1. Uses `JarFile#getManifest()` to read the manifest from the archive passed on the command line.
2. Uses `Attributes#getValue(Attributes.Name.MAIN_CLASS)` and `getValue("Start-Class")` to retrieve both fields. For a JAR lacking `Start-Class`, the program prints `(absent)`.

Compile with JDK 17+:

~~~bash
javac ManifestInspector.java
~~~

Once you have built an executable Spring Boot JAR like the example in the next section:

~~~bash
java ManifestInspector build/libs/manifest-demo.jar
~~~

Two expected lines of output **for the Spring Boot 3.3.5 example below**:

~~~text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.demo.ManifestDemoApplication
~~~

The program prints the **actual values** inside whichever artifact you pass in, without hardcoding either class name. If you pass a plain Java JAR built with `jar --main-class`, it typically prints `Start-Class=(absent)`. If the JAR does not exist or is invalid, `JarFile` throws an error; do not confuse that with a missing manifest.

**Why use `JarFile`?** It understands ZIP/JAR structure and standard manifest parsing (including continuation lines). You can extend the inspector to print `Spring-Boot-Version` or `Spring-Boot-Classes` as well, though those are custom attributes and may not exist in every archive.

## 7. Experiment 1 — Plain Java JAR: Only `Main-Class` Is Needed

Before looking at Spring Boot, build a Java 17+ JAR with no external library dependencies. Create **`Hello.java`**:

~~~java
public final class Hello {
    public static void main(String[] args) {
        System.out.println("HELLO_FROM_PLAIN_JAR");
    }
}
~~~

In the directory containing `Hello.java`, on Linux/macOS:

~~~bash
mkdir -p classes
javac -d classes Hello.java
jar --create --file hello.jar --main-class Hello -C classes .
java -jar hello.jar
~~~

Stdout printed by the application:

~~~text
HELLO_FROM_PLAIN_JAR
~~~

If you run the compiled inspector in the same directory:

~~~bash
java ManifestInspector hello.jar
~~~

Result:

~~~text
Main-Class=Hello
Start-Class=(absent)
~~~

Explanation: `jar --main-class Hello` writes the standard entry point to the manifest. `Hello.class` is placed at the root of the JAR because this class sits in the **default package**; this example is intentionally minimal. In real Java projects, use named packages clearly.

You can inspect the manifest via `unzip -p hello.jar META-INF/MANIFEST.MF` or the methods in Section 5. **Do not add `Start-Class` to a plain JAR to "imitate Spring Boot"** — the standard JVM does not read that attribute.

## 8. Experiment 2 — Spring Boot 3.3: `Main-Class` Points to Loader, `Start-Class` Points to Application

This example uses Gradle **Groovy DSL**, Java 17, and Spring Boot 3.3.5. It builds a real executable JAR and prints a line confirming the `main` class was invoked by the Boot launcher.

Directory layout:

~~~text
manifest-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/example/demo/ManifestDemoApplication.java
~~~

### 8.1. `settings.gradle` File

~~~groovy
rootProject.name = 'manifest-demo'
~~~

### 8.2. `build.gradle` File — Complete Configuration

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
    mainClass = 'com.example.demo.ManifestDemoApplication'
}

tasks.named('bootJar') {
    archiveFileName.set('manifest-demo.jar')
}
~~~

Purpose:

- The `java` and `org.springframework.boot` plugins set up build tasks, including `bootJar`.
- `io.spring.dependency-management` manages Boot dependency versions in this project.
- `spring-boot-starter` provides the basic Spring Boot runtime **without** adding a web server since the web starter is not used.
- `springBoot { mainClass = ... }` specifies the application main class by fully qualified name, avoiding reliance on auto-detection when a project has multiple main methods.
- `tasks.named('bootJar')` only changes the output file name; the **Spring Boot plugin** handles the manifest, launcher, and layout for the executable JAR.
- Do not set `Main-Class` to the application class yourself. The goal is for the plugin to write `Main-Class=JarLauncher` and `Start-Class=ManifestDemoApplication` properly.

This example pins version 3.3.5 so learners can compare results; production projects must use a Gradle/Spring Boot/JDK combination matching current support policy.

### 8.3. `src/main/java/com/example/demo/ManifestDemoApplication.java` File

~~~java
package com.example.demo;

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
    CommandLineRunner marker() {
        return args -> System.out.println("BOOT_MAIN_CALLED");
    }
}
~~~

Valid Java 17+ code, with the `public class` name matching the file name. `main` is called via the launcher when running from the executable Boot JAR. After initializing the Spring context, `CommandLineRunner` prints a marker line.

### 8.4. Building and Reading the Manifest

Assuming a Gradle Wrapper compatible with Spring Boot 3.3.5 (e.g., Gradle 8.7) is present. On Linux/macOS:

~~~bash
./gradlew clean bootJar
jar tf build/libs/manifest-demo.jar
unzip -p build/libs/manifest-demo.jar META-INF/MANIFEST.MF
~~~

`jar tf` lists archive entries; `unzip -p` prints the manifest when the `unzip` utility is available. The lines **you should see in this example artifact's manifest**:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
~~~

The manifest may include additional fields such as `Manifest-Version`, `Spring-Boot-Version`, `Spring-Boot-Classes`, `Spring-Boot-Lib`, build metadata, and index attributes. Do not validate manifests by requiring an exact line count, line order, or exact set of secondary metadata fields.

If you saved `ManifestInspector.java` from Section 6 in the project directory (or in a separate tools directory), you can compile and inspect:

~~~bash
javac ManifestInspector.java
java ManifestInspector build/libs/manifest-demo.jar
~~~

Stdout prints the exact two lines shown in Section 6.

### 8.5. Running the Executable Boot JAR

~~~bash
java -jar build/libs/manifest-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the **application** upon successful startup:

~~~text
BOOT_MAIN_CALLED
~~~

Additional lines printed by Gradle, Spring Boot, or the JVM may vary by environment; the output above is only the marker printed by `CommandLineRunner`, not a guarantee that total stdout consists solely of one line. Because only basic `spring-boot-starter` is used without a web server, the application exits after the runner finishes.

**Actual sequence of events:**

1. The JVM reads `Main-Class` and runs `JarLauncher.main(...)`.
2. The Boot loader prepares a classloader for `BOOT-INF/classes` and the nested JARs in `BOOT-INF/lib`.
3. The loader reads `Start-Class` to identify `ManifestDemoApplication`.
4. The loader invokes `ManifestDemoApplication.main(...)`.
5. The application calls `SpringApplication.run(...)`, initializing the Spring context.
6. `CommandLineRunner` prints `BOOT_MAIN_CALLED`.

Running `./gradlew bootRun` takes a different path: Gradle launches the application from the development runtime classpath without necessarily going through the manifest or executable JAR. To genuinely test `Main-Class`/`Start-Class` on the artifact, you must **build and run the JAR itself**.

### 8.6. Checking Bytecode to Prove Classes Are Actually in the Archive

~~~bash
jar tf build/libs/manifest-demo.jar
~~~

In the long listing, find the meaningful entries:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/demo/ManifestDemoApplication.class
BOOT-INF/lib/...
~~~

The line `BOOT-INF/lib/...` is **illustrative notation** for nested JARs, not a literal entry from `jar tf`. If `Start-Class` lists the application class yet the corresponding class is missing from `BOOT-INF/classes` or any location loaded by the launcher, check whether `bootJar` is packaging the right module/source set.

### 8.7. Windows PowerShell

Use `.\gradlew.bat` instead of `./gradlew`. `java`, `javac`, and `jar` come with the JDK; `unzip` may not be installed. Running the compiled Java inspector via `java ManifestInspector build\libs\manifest-demo.jar` works without depending on `unzip`. Pass application arguments to `java -jar` on a single line to avoid shell line-continuation differences.

## 9. Maven: Inspecting `spring-boot:repackage` Output

Maven uses `spring-boot-maven-plugin` to build an executable Boot archive via the `repackage` goal. When combined with `spring-boot-starter-parent`, the plugin typically inherits its version and default execution from the parent, yet you still must **activate the plugin** under `<build><plugins>` in the application configuration (or use an equivalent inheritance/activation mechanism).

Complete `pom.xml` example for the exact same Java application from Section 8:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
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
                    <mainClass>com.example.demo.ManifestDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Note that this is the **Maven alternative** to `build.gradle`; do not keep both build systems for the same example unless intended. The Java file at `src/main/java/com/example/demo/ManifestDemoApplication.java` stays identical.

Run:

~~~bash
mvn clean package
jar tf target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the application:

~~~text
BOOT_MAIN_CALLED
~~~

With the starter parent and plugin configured above, `repackage` creates a Boot executable JAR whose manifest carries the same semantics as in Gradle: **`Main-Class` is the launcher, and `Start-Class` is the application class**. The JAR file name depends on `artifactId`/`version`, `finalName`, and any classifier; this example expects `target/manifest-demo-1.0.0.jar`.

### BOM vs. Packaging Plugin

If a Maven project **only imports the `spring-boot-dependencies` BOM** without using the starter parent, the BOM primarily manages **dependency versions**. It **does not automatically bind the `repackage` execution** to the lifecycle; you must configure `spring-boot-maven-plugin`, its version, and the appropriate execution to get an executable JAR.

If you run `mvn package` without `repackage`, the file produced by `maven-jar-plugin` may be a **plain JAR**, whose manifest lacks `Start-Class` and cannot run via `java -jar` as an executable Boot JAR. Do not manually patch the manifest to compensate for a missing build plugin: fix the packaging pipeline first.

## 10. Properly Configuring the Application Main Class

### Gradle Groovy DSL

In a project with the Spring Boot plugin applied:

~~~groovy
springBoot {
    mainClass = 'com.example.demo.ManifestDemoApplication'
}
~~~

Or configure the `bootJar` task individually:

~~~groovy
tasks.named('bootJar') {
    mainClass.set('com.example.demo.ManifestDemoApplication')
}
~~~

These are **two selectable configuration locations**; avoid setting different values in both without good reason. The value is the application class written to `Start-Class` for the executable Boot JAR. The Spring Boot plugin usually detects a class with `public static void main(String[])` if the project has only one matching class; explicit configuration prevents ambiguity.

### Gradle Kotlin DSL

If using `build.gradle.kts` instead of `build.gradle`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.demo.ManifestDemoApplication")
}
~~~

This is a Kotlin DSL snippet for a project with the Boot/Java plugins applied. Do not copy generic `named<BootJar>` syntax into Groovy DSL.

### Maven

Inside `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <mainClass>com.example.demo.ManifestDemoApplication</mainClass>
</configuration>
~~~

When the `repackage` goal runs, the plugin uses the configured application main class to generate the appropriate `Start-Class`. Do not confuse the plugin's `mainClass` parameter with the standard `Main-Class` manifest attribute. Despite sharing "main class" in plugin configuration naming, **the plugin still generates the launcher entry point** so the executable archive can run.

### When There Are Multiple `main()` Methods in One Module

If the code has `Application.java`, `ImportTool.java`, and `MigrationTool.java`, each containing `public static void main(String[])`, auto-detection may fail to pick a single class or pick an unintended one (depending on build plugin/version). Explicitly set the right class for **the distributed archive**:

~~~text
Spring Boot executable JAR used for deployment:
Start-Class: com.example.demo.ManifestDemoApplication

Standalone import tool:
com.example.tools.ImportTool
~~~

Do not try to craft a manifest with multiple `Start-Class` lines to choose applications arbitrarily. One executable Boot JAR is packaged with one specific main application class; if multiple entry points are needed, consider separate tasks/artifacts with clear names and launchers.

### A Note for Kotlin Applications

In Kotlin, a top-level `fun main` is typically compiled into a JVM class with a `Kt` suffix (unless overridden with `@JvmName`). Therefore, the main class value for the Spring Boot Gradle/Maven plugin must be the **actual JVM class name**, not necessarily the source file name without the suffix. Inspect the archive bytecode when configuring Kotlin.

## 11. Common Errors When Reading or Editing Manifests

| Symptom | Cause to Investigate | How to Verify / Fix |
| --- | --- | --- |
| `no main manifest attribute` | JAR lacks a valid `Main-Class` | Run the inspector; check if running a plain JAR by mistake or missing `bootJar`/`repackage` |
| `Could not find or load main class ...JarLauncher` | `Main-Class` points to a launcher absent from the archive, wrong Boot version, or corrupted JAR | Read manifest, run `jar tf` to find the real launcher class path |
| Failure loading the application class named in `Start-Class` | Wrong FQCN, class missing from archive, or wrong `mainClass` config | Compare `Start-Class` against `BOOT-INF/classes/<package-path>.class` |
| `Start-Class` missing in a Boot JAR | Wrong packaging type, custom manifest override, or inspecting wrong artifact | Verify `bootJar`/`repackage`, output file, and `mainClass` config |
| `Main-Class` points directly to application in Boot nested layout | Custom manifest overwrote launcher | Let the Boot plugin generate the launcher; fix plugin config rather than manual manifest edits |
| `Main-Class` is `org.springframework.boot.loader.JarLauncher` while examples show `...loader.launch.JarLauncher` | Artifact built with an older Spring Boot release | Check Spring Boot version and actual launcher class |
| `Start-Class` is right yet app fails with `NoClassDefFoundError` | Another dependency is missing or incompatible | Inspect `BOOT-INF/lib` and dependency graph, read `Caused by` |
| `UnsupportedClassVersionError` | Runtime JVM is older than application/loader/dependency bytecode | Compare `java --version` with Java toolchain/target |
| Edited `build.gradle` yet manifest did not change | Running a JAR from a previous build, up-to-date task, wrong output, or multi-module | Clean build the right module, check exact file path/classifier |
| `META-INF/MANIFEST.MF` not visible in `jar tf` | Wrong file opened or invalid archive | Verify the exact artifact and file type |
| Long manifest line wrapped oddly | Manifest continuation lines per spec | Parse via `JarFile#getManifest()` rather than simple regex |
| WAR deployed to external Tomcat starts differently from `java -jar` | External servlet container scenarios have their own startup path | Check WAR packaging, Servlet initializer, and container runtime |

**Important distinction:** a startup failure after `JarLauncher` does not necessarily mean `Start-Class` is wrong. For example, if the loader invokes the right main class and `SpringApplication.run` fails to initialize a datasource due to credentials or network issues, both manifest attributes may be completely accurate. Always inspect the **root exception**.

### Missing Classes Due to Confusing Plain JARs with Boot JARs

The Spring Boot Gradle plugin can allow both `jar` and `bootJar` tasks to produce outputs, usually under different naming conventions (such as the `plain` classifier for plain JARs in recent Boot versions). If someone accidentally runs `*-plain.jar`, symptoms include `no main manifest attribute` or missing runtime dependencies. The fix is to check the exact output of the intended task and **never** assume every `.jar` in `build/libs` is an executable Boot JAR.

### Do Not Edit Manifests by Dragging and Dropping in a ZIP Tool

The manifest is toolchain-generated metadata and can relate to signatures, reproducible builds, and classloaders. Modifying the manifest inside an already-built archive can break artifact consistency, invalidate signatures, or cause mismatches with remaining entries. To change the main class, **update build plugin configuration, rebuild, and re-verify**. To create a plain JAR without the Boot launcher, use the appropriate Java packaging task/plugin instead of randomly editing `Main-Class`.

### Does the Manifest `Class-Path` Replace `BOOT-INF/lib`?

In an ordinary Java JAR, the manifest can include a standard `Class-Path` attribute pointing to external JARs per Java rules. In an executable Spring Boot JAR using `JarLauncher`, the classpath for nested dependencies is established by the launcher from the archive layout; **you do not need to list each nested JAR manually in `Class-Path`**. Manually adding `Class-Path` entries like `BOOT-INF/lib/x.jar` does not replace the Spring Boot loader mechanism.

## 12. Pre-Deployment Artifact Verification Workflow

When receiving a JAR from CI/CD, do not rely on file name alone. Follow this checklist:

1. **Identify the exact artifact.** It could be a Boot executable JAR, plain JAR, executable WAR, or another file. Record its name and hash/version if supported by your release process.
2. **Inspect the manifest.** Use `JarFile` or `unzip -p`; record `Main-Class` and `Start-Class`. For a standard Spring Boot 3.3 executable JAR, those values are Boot `JarLauncher` and the application class, respectively.
3. **Verify the launcher exists.** `jar tf` must contain the class matching `Main-Class`. Do not expect loader names from newer releases inside older archives.
4. **Verify the application class exists.** In a default Boot JAR, the path must match `BOOT-INF/classes/com/example/.../Application.class`.
5. **Check runtime libraries.** Inspect `BOOT-INF/lib`; a valid manifest still fails at runtime if required dependencies are missing.
6. **Run the right artifact.** Execute `java -jar file.jar` in a compatible test environment, pass needed arguments/profiles, and read the full exception chain.
7. **To change the entry point, change the build.** Gradle `springBoot.mainClass` or `bootJar.mainClass`; Maven `spring-boot-maven-plugin.mainClass`. Rebuild, re-read the manifest, and re-run.
8. **Separate manifest errors from runtime errors.** Wrong `Main-Class`, wrong `Start-Class`, missing classes, Java version mismatches, and environment configuration are distinct failure layers.

A short Gradle workflow:

~~~bash
./gradlew clean bootJar
jar tf build/libs/manifest-demo.jar
java ManifestInspector build/libs/manifest-demo.jar
java -jar build/libs/manifest-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

With Maven:

~~~bash
mvn clean package
jar tf target/manifest-demo-1.0.0.jar
java ManifestInspector target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Note that the inspector commands assume you compiled `ManifestInspector.java` into the current classpath. If its `.class` file lives in another directory, run `java -cp <directory-containing-inspector> ManifestInspector ...`. It is a standalone archive inspection tool and **does not** need to launch the application just to read the manifest.

## 13. Self-Check Questions

**Question 1.** In the manifest:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.ManifestDemoApplication
~~~

Which class does the JVM run first?

**Answer:** `JarLauncher`, because the JVM reads `Main-Class`. The Spring Boot loader then reads `Start-Class` and calls `ManifestDemoApplication.main`.

**Question 2.** A plain Java JAR has `Main-Class: Hello` and no `Start-Class`. Can it run with `java -jar`?

**Answer:** Yes, if the `Hello` class, a valid main method, and any needed dependencies can be loaded. `Start-Class` is not a required attribute for the Java launcher.

**Question 3.** Is placing only `Start-Class: com.example.App` in a plain JAR enough for `java -jar`?

**Answer:** No. The standard JVM Java launcher requires `Main-Class`; it does not use `Start-Class` on its own.

**Question 4.** Why can a Boot JAR with `Main-Class=JarLauncher` still run `ManifestDemoApplication` even though it sits deep inside `BOOT-INF/classes`?

**Answer:** The Boot launcher understands the executable JAR layout, creates a classloader for `BOOT-INF/classes` and nested dependencies in `BOOT-INF/lib`, and then invokes the application main.

**Question 5.** When can `org.springframework.boot.loader.JarLauncher` (without `.launch.`) be a valid value?

**Answer:** In older Spring Boot generations whose loader classes lived in that package. Always verify against the version and bytecode inside the actual artifact instead of rigidly forcing Boot 3.3 examples.

**Question 6.** Does `jar tf app.jar` reveal the contents of `META-INF/MANIFEST.MF`?

**Answer:** No. It only lists entry names. Use `unzip -p`, extract the manifest separately, or use Java `JarFile#getManifest()` to read the values.

**Question 7.** Does a `ClassNotFoundException` thrown after the loader invokes the right `Start-Class` always mean the manifest is wrong?

**Answer:** No. A library or transitive class could be missing, the wrong version, or excluded from the archive. Check the exception chain, `BOOT-INF/lib`, and the dependency graph.

**Question 8.** In the Spring Boot Gradle plugin, what should you configure to change the application class name without breaking `Main-Class`?

**Answer:** Set `springBoot.mainClass` or `bootJar.mainClass` to a valid class, then rebuild. The Boot plugin is responsible for generating the manifest and launcher entry point matching the executable layout.

## References

- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/launching.html): `JarLauncher`/`WarLauncher`/`PropertiesLauncher`, `Main-Class`, and `Start-Class`.
- [Spring Boot 3.3 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootJar`, main class, archive, and manifest.
- [Spring Boot 3.3 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html): `repackage` and main class.
- [Oracle Java 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifest syntax, `Main-Class`, line folding, and `Class-Path`.
- [Spring Boot 3.2 — The Executable Jar Format](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/executable-jar.html): nested JAR layout and launchers in the Boot 3.2 line.

**Conclusion:** `Main-Class` is **the standard entry point invoked by the Java launcher**; `Start-Class` is **the application entry point used by the Spring Boot launcher**. In a default executable Spring Boot JAR, these two attributes are **intentionally different**. Inspect the manifest with proper tools, verify the classes actually packaged, and run the exact artifact before diagnosing startup failures.