# Inspecting JAR Contents with `jar tf` and Extraction Tools

When packaging a Spring Boot application, Maven or Gradle can report `BUILD SUCCESS` while the resulting JAR still lacks a class, resource, runtime dependency, or valid entry point. Therefore, **inspecting the JAR after building** is a separate step from compiling and running tests. The JDK's `jar` tool together with ZIP utilities such as `unzip`, `zipinfo`, and 7-Zip let you look directly at what went into the artifact rather than guessing from `src` layout or build configuration.

This lesson walks through `jar tf`, `jar tvf`, and `jar xf` all the way to reading `META-INF/MANIFEST.MF`, inspecting a **Spring Boot executable JAR**, classes/resources in `BOOT-INF/classes`, dependency JARs nested in `BOOT-INF/lib`, extraction tools on Linux/macOS/Windows, and automated verification in CI. It includes a runnable Java 17 + Spring Boot 3.3.13 example. That version is solely a consistent baseline for this lesson and must not be interpreted as the latest release; rely on your actual project's tooling and release version.

## 1. What Is a JAR and Why Can ZIP Tools Open It?

A **JAR (Java ARchive)** is an archive format built on ZIP. Inside it can hold:
- `.class` bytecode and resource files (properties, JSON, templates, images, XML, etc.).
- `META-INF/MANIFEST.MF`, metadata describing the archive and, when applicable, how to launch it.
- Java metadata such as `META-INF/services/**` or multi-release entries `META-INF/versions/**`.
- In a Spring Boot executable JAR: the **Boot launcher**, application classes/resources, and **runtime libraries as nested JARs**.

Capabilities of each tool:

| Tool | What It Can Do | What It Cannot Prove |
| --- | --- | --- |
| `jar tf file.jar` | Lists entry names and paths | Entry contents, runtime compatibility |
| `jar tvf file.jar` | Lists entries with sizes and timestamps | Authenticity, whether dependencies are compatible |
| `jar xf file.jar [entry]` | Extracts all or selected entries | That the application runs successfully |
| `unzip -l file.jar` | Lists entries and ZIP metadata | Whether the main class is right or wrong |
| `unzip -p file.jar entry` | Prints **the contents** of an entry to stdout | Security of code inside the archive |
| `unzip -t file.jar` | Checks archive readability/CRC | Cryptographic signature / publisher origin |
| `7z l file.jar` | Browses archive with 7-Zip when installed | That JDK and Spring Boot runtime match |

**`jar tf` does not extract files**; `jar xf` is what writes files to disk. `jar` belongs to the **JDK**, so there is no guarantee every minimal Java-runtime-only environment has this command. Check:

```bash
java -version
jar --version
```

JDK 17 also supports long options:

```bash
jar --list --file path/to/application.jar
jar --extract --file path/to/application.jar META-INF/MANIFEST.MF
```

In short flags, `t` = table/list, `f` = file, `x` = extract, `v` = verbose. Do not confuse `jar tf` with `java -jar`: one **reads the archive**, while the other **executes the program inside the archive**.

## 2. Distinguishing JAR Types Before Inspecting

Not every `.jar` file shares the same layout or can run standalone.

| Type | Typical Class Path | Runtime Dependencies | `java -jar` |
| --- | --- | --- | --- |
| Ordinary library JAR | `com/example/Library.class` at root | External to JAR | Not required |
| Plain application JAR | `com/example/App.class` at root | Usually external and requires proper classpath | Only if entry point and matching classpath exist |
| Spring Boot executable JAR | `BOOT-INF/classes/com/example/App.class` | Nested JARs in `BOOT-INF/lib` | Usually runs when built properly |
| Shaded/uber JAR | App and library classes merged at root per rules | Many dependencies unpacked/merged | Depends on manifest and shade config |
| Spring Boot executable WAR | `WEB-INF/classes` | `WEB-INF/lib`, optionally `WEB-INF/lib-provided` | Can run or deploy to servlet container when properly configured |

**Common mistake:** opening a plain JAR and concluding "Spring Boot is broken because `BOOT-INF/classes` is missing". First verify which artifact type the project intends to produce. With the Gradle Spring Boot plugin, `bootJar` builds the executable JAR, while the `jar` task normally builds `*-plain.jar` if enabled. With Maven and `spring-boot-maven-plugin`, the `repackage` goal repackages the original JAR, potentially leaving a `*.jar.original` file.

For a Boot executable JAR, do not run the app by guessing `java -cp app.jar com.example.App`: application classes reside under `BOOT-INF/classes` and dependencies reside in nested JARs; a standard classpath will not resolve the Boot layout automatically. The standard way to run it is `java -jar app.jar` via the Boot launcher.

## 3. Build the Artifact First, Then Pick the Exact File to Inspect

### 3.1. Gradle

In a project with the Gradle Wrapper:

```bash
./gradlew clean bootJar
```

After building, inspect `build/libs/` and choose the actual executable JAR. If `archiveFileName`, `archiveClassifier`, or a multi-module layout was customized, the path may differ.

### 3.2. Maven

In a project with the Maven Wrapper:

```bash
./mvnw clean package
```

When using the Spring Boot starter parent with `spring-boot-maven-plugin`, the `package` phase invokes `repackage` and produces the executable JAR in `target/`. If only importing the Spring Boot BOM without inheriting the parent, dependency version management **does not automatically bind the `repackage` goal to the lifecycle**; you must configure the plugin and execution separately.

In Windows PowerShell, use `.\gradlew.bat` or `.\mvnw.cmd`. If there is no Wrapper, use a preinstalled `gradle` or `mvn` compatible with the project.

**Do not inspect a stale file built hours ago** or a JAR with a different classifier than what CI deploys. Record the exact artifact path in the pipeline and run inspection immediately after building. Examples below use two illustrative paths:
- Gradle: `build/libs/jar-inspect-demo-1.0.0.jar`.
- Maven: `target/jar-inspect-demo-1.0.0.jar`.

These names will match if you create the sample project in Section 5.

## 4. Listing Contents with `jar tf`

### 4.1. Listing All Entries

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar
```

An excerpt of a Spring Boot 3.3 executable JAR listing typically looks like:

```text
META-INF/
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/
BOOT-INF/classes/
BOOT-INF/classes/com/example/inspect/JarInspectApplication.class
BOOT-INF/classes/demo/marker.txt
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
```

**This is an illustrative excerpt, not full real output.** Index entries may be absent depending on configuration, and `BOOT-INF/lib` lists many more libraries per the dependency graph. Get exact names and versions by running `jar tf` directly on your own artifact.

Key structure:

```text
executable.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...  # Boot loader
└── BOOT-INF/
    ├── classes/                         # app classes/resources
    ├── lib/                             # nested dependency JARs
    ├── classpath.idx                    # optional
    └── layers.idx                       # optional
```

### 4.2. Filtering Only What You Need to See

Linux/macOS with `grep`:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/classes/'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/lib/'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'MANIFEST.MF'
```

Windows PowerShell:

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
jar tf $jar | Select-String '^BOOT-INF/classes/'
jar tf $jar | Select-String '^BOOT-INF/lib/'
jar tf $jar | Select-String 'MANIFEST.MF'
```

These filters **search entry names**, not entry contents. If nothing matches, check whether you opened the right executable JAR, whether resources were copied, and whether path prefixes match the layout. ZIP entry names always use `/` even on Windows hosts.

### 4.3. How Does `jar tvf` Differ?

```bash
jar tvf build/libs/jar-inspect-demo-1.0.0.jar
```

The `v` flag adds metadata such as byte size and timestamps. Do not infer whether a file is "fresh" or "stale" solely from entry timestamps: reproducible builds may normalize timestamps. `jar tvf` also **does not** print the contents of `META-INF/MANIFEST.MF`.

## 5. Spring Boot Java 17 Example to Verify Real Contents

The sample project contains one Spring Boot main class and one resource file carrying an identifier string. We use the **exact same Java code** for either Gradle or Maven; pick one build tool to test.

Structure:

```text
jar-inspect-demo/
├── settings.gradle     (Gradle option)
├── build.gradle        (Gradle option)
├── pom.xml             (Maven option)
└── src/main/
    ├── java/com/example/inspect/JarInspectApplication.java
    └── resources/demo/marker.txt
```

### 5.1. Java Code

`src/main/java/com/example/inspect/JarInspectApplication.java`:

```java
package com.example.inspect;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class JarInspectApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(JarInspectApplication.class, args)) {
            try (InputStream in = JarInspectApplication.class
                    .getClassLoader()
                    .getResourceAsStream("demo/marker.txt")) {
                if (in == null) {
                    throw new IOException("Missing classpath resource: demo/marker.txt");
                }
                String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("archive-resource=" + value.strip());
            }
        }
    }
}
```

In `src/main/resources/demo/marker.txt`, write **one line**:

```text
archive-inspection-ok
```

`getResourceAsStream("demo/marker.txt")` reads the resource from the **classpath** rather than depending on filesystem source paths. The code uses Java 17 and closes `ApplicationContext` so the demo exits after printing the result; do not close the context right after startup in a long-running web server.

### 5.2. Building with Gradle Groovy DSL

`settings.gradle`:

```groovy
rootProject.name = 'jar-inspect-demo'
```

Complete `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.inspect.JarInspectApplication'
}
```

The `bootJar` task packages classes, resources, and runtime dependencies into the executable JAR. `mainClass` sets the entry point even if another `main` class is added later.

```bash
./gradlew clean bootJar
jar tf build/libs/jar-inspect-demo-1.0.0.jar
java -jar build/libs/jar-inspect-demo-1.0.0.jar
```

Line printed by the sample program:

```text
archive-resource=archive-inspection-ok
```

Depending on the environment, Spring Boot logs may also appear. If the resource file is missing from the classpath, the program throws `IOException` instead of printing the expected line.

### 5.3. Building with Maven

`pom.xml`:

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
    <artifactId>jar-inspect-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent configures `repackage` on the plugin, so `./mvnw clean package` creates the executable JAR. Then:

```bash
./mvnw clean package
jar tf target/jar-inspect-demo-1.0.0.jar
java -jar target/jar-inspect-demo-1.0.0.jar
```

The program likewise prints `archive-resource=archive-inspection-ok`. Note that `target/jar-inspect-demo-1.0.0.jar.original` (if present) is the pre-repackage file, **not** the executable artifact you want to inspect.

## 6. Inspecting `META-INF/MANIFEST.MF`

The manifest is a **text file inside the archive**. `jar tf` only shows the entry name. To read `Main-Class` or `Start-Class` values, you must **read its contents**.

When `unzip` is available:

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Typical fields in a Spring Boot 3.3 executable JAR:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.inspect.JarInspectApplication
```

- **`Main-Class`**: Boot loader launcher invoked by `java -jar`, setting up the nested JAR classpath.
- **`Start-Class`**: actual application `main` class.
- Other fields (`Spring-Boot-Version`, `Spring-Boot-Classes`, etc.) may appear; order and contents depend on plugin/version.
- Older Spring Boot versions may use a different launcher package; **never hardcode Boot 3.3's `JarLauncher` name to judge every version**.

If `Start-Class` is wrong, check Gradle's `springBoot.mainClass` / `bootJar.mainClass` or Spring Boot Maven plugin's `mainClass` config. If `Main-Class` is the application class or missing an entry point when expecting a Boot JAR, you may be inspecting a plain JAR or the plugin did not run.

**Manifests can contain continuation lines** for long values (continuation lines start with a space). Automated manifest parsing must obey JAR manifest rules instead of naively splitting each line independently.

## 7. `jar xf` and `unzip -p`: Reading Entry Contents

### 7.1. Extracting with `jar xf`

```bash
jar xf build/libs/jar-inspect-demo-1.0.0.jar
```

Without specifying entries, this extracts the **entire** archive into the **current working directory**. That can dump thousands of files; never run it inside your source directory or anywhere containing files you want to keep clean.

Safer approach:

```bash
mkdir -p jar-inspection
cd jar-inspection
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
cat META-INF/MANIFEST.MF
cat BOOT-INF/classes/demo/marker.txt
```

This extracts only the two files you need to inspect. For Maven, change `../build/libs/...` to `../target/...`; the `jar-inspection` directory is created at the project root. On Windows, create the directory with `New-Item -ItemType Directory` and read text files with `Get-Content`.

### 7.2. No Disk Writes Needed If You Have `unzip -p`

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
```

Expected contents:

```text
archive-inspection-ok
```

`unzip -p` writes contents to stdout, which is very convenient for manifests, properties, or text. **Do not use text redirection pipelines to extract `.jar` libraries or binary images across arbitrary shells**: older PowerShell versions can corrupt bytes/encoding when redirecting. For binaries, prefer `jar xf` or a dedicated ZIP extraction tool.

### 7.3. Other Options

```bash
unzip -l build/libs/jar-inspect-demo-1.0.0.jar
zipinfo -1 build/libs/jar-inspect-demo-1.0.0.jar
unzip -t build/libs/jar-inspect-demo-1.0.0.jar
```

`zipinfo` is not available on every system, and `unzip -t` mainly verifies ZIP readability and CRCs—**it does not verify JVM compatibility or publisher trustworthiness**. When 7-Zip is installed, `7z l file.jar` also lists entries, and the 7-Zip GUI lets you browse/extract it as a ZIP archive.

### 7.4. PowerShell Without `unzip`

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
jar tf $jar | Select-String 'BOOT-INF/classes/demo/marker.txt'
New-Item -ItemType Directory -Path .\jar-inspection -Force | Out-Null
Push-Location .\jar-inspection
try {
    jar xf ..\build\libs\jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
    jar xf ..\build\libs\jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
    Get-Content .\META-INF\MANIFEST.MF
    Get-Content .\BOOT-INF\classes\demo\marker.txt
} finally {
    Pop-Location
}
```

These are **PowerShell commands using an installed JDK**, requiring no Unix tools. `jar xf` must run inside a controlled inspection directory because it creates subdirectories matching the entry paths. Never extract untrusted archives with Administrator privileges.

## 8. Inspecting Application Classes and Resources

In a Spring Boot executable JAR, `src/main/java/com/example/inspect/JarInspectApplication.java` becomes the class entry:

```text
BOOT-INF/classes/com/example/inspect/JarInspectApplication.class
```

And the source resource:

```text
src/main/resources/demo/marker.txt
```

becomes:

```text
BOOT-INF/classes/demo/marker.txt
```

You can verify each entry:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'JarInspectApplication.class'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'BOOT-INF/classes/demo/marker.txt'
```

**Distinguishing the path layers:**

| Place | File Path |
| --- | --- |
| Java source | `src/main/java/com/example/inspect/JarInspectApplication.java` |
| Resource source | `src/main/resources/demo/marker.txt` |
| Gradle resource output | `build/resources/main/demo/marker.txt` |
| Maven resource output | `target/classes/demo/marker.txt` |
| Inside Boot executable JAR | `BOOT-INF/classes/demo/marker.txt` |
| Path passed to `ClassLoader.getResourceAsStream` | `demo/marker.txt` |

If the file exists in `src/main/resources` yet is missing from the JAR, inspect `processResources` (Gradle), `process-resources` (Maven), `include/exclude` rules, and the archive task. If the file is in the JAR yet the classloader cannot read it, check the runtime lookup path: normally pass `demo/marker.txt`, **not** `BOOT-INF/classes/demo/marker.txt`.

**`jar tf` does not prove a Java class has a valid `main` method.** It only confirms the entry name. For deeper inspection, you can run `javap` on extracted bytecode, though for Spring Boot the most effective check is reading the manifest alongside running `java -jar` and observing behavior.

## 9. Nested JARs: Why Are Library Classes Invisible in `jar tf`?

Spring Boot packages runtime dependencies as **JAR files inside another JAR**:

```text
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-context-<version>.jar
BOOT-INF/lib/spring-core-<version>.jar
...
```

`<version>` here is an illustrative placeholder, not a literal string. Running `jar tf outer.jar` sees each nested `*.jar` as **a single entry** and does not recursively list `.class` files inside it.

### 9.1. Listing Nested JARs

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/lib/.*[.]jar$'
```

On PowerShell:

```powershell
jar tf .\build\libs\jar-inspect-demo-1.0.0.jar |
    Select-String '^BOOT-INF/lib/.*[.]jar$'
```

### 9.2. Extracting and Inspecting a Specific Library

After getting the **exact name from the actual listing**, create a separate directory and run `jar xf`. Example with `spring-boot-3.3.13.jar`:

```bash
mkdir -p jar-inspection
cd jar-inspection
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/lib/spring-boot-3.3.13.jar
jar tf BOOT-INF/lib/spring-boot-3.3.13.jar
```

Only the last command lists classes and resources **inside the dependency JAR**. To look for `org/springframework/boot/SpringApplication.class`, search inside the nested `spring-boot-3.3.13.jar`, not inside the application's `BOOT-INF/classes`.

Two different libraries can each contain `META-INF/services/...` without creating duplicate **entry names** in the outer JAR; they remain distinct archives added to the classpath by the Boot loader.

### 9.3. Comparing with the Dependency Graph

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree
```

The dependency graph tells you **which libraries/versions resolved and why**; `jar tf` confirms **which artifacts were actually packaged**. A dependency may be absent from the production JAR due to test/provided scopes, exclusions, classifiers, or custom packaging. Do not pull `junit-jupiter-engine` or `mockito-core` into production `BOOT-INF/lib` just "to be thorough": test dependencies normally do not belong in production archives.

## 10. Inspecting `classpath.idx` and `layers.idx`

Some Spring Boot executable JARs contain:

- `BOOT-INF/classpath.idx`: list/order of nested JARs added to the runtime classpath when running the executable JAR via `java -jar`.
- `BOOT-INF/layers.idx`: describes how contents split into layers for container image building and caching.

Check for them with `jar tf`, then read them when they **actually exist**:

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classpath.idx
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/layers.idx
```

Example `classpath.idx` format:

```text
- "BOOT-INF/lib/spring-boot-3.3.13.jar"
- "BOOT-INF/lib/spring-context-6.1.20.jar"
```

Names and versions here are illustrative. Note that `jar tf` returns **entry order inside the archive**, which is not necessarily runtime classpath order; when `classpath.idx` is present, follow the Boot version's conventions.

Simplified layer example:

```text
- "dependencies":
  - "BOOT-INF/lib/"
- "application":
  - "BOOT-INF/classes/"
```

Do not use `layers.idx` to determine the main class or conclude a resource is missing. **A missing index is not automatically an error**: depending on version, plugin, and configuration, indices may or may not be generated. The core functionality of a JAR must still be verified via manifest, classes/resources, dependencies, and actual execution.

## 11. Checking for Duplicate Entries vs. Classpath Collisions

A ZIP/JAR can hold multiple entries with the same name if a custom packaging step or permissive duplicate strategy allows it. Detect duplicate entry names:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | sort | uniq -d
```

PowerShell:

```powershell
jar tf .\build\libs\jar-inspect-demo-1.0.0.jar |
    Group-Object |
    Where-Object { $_.Count -gt 1 } |
    Select-Object Name, Count
```

Empty output means the **outer archive** listing has no duplicate entry names by this comparison. However, that **does not** rule out identical resource/class names sitting inside **two different nested dependency JARs**. Also, an app might have matching paths in main resources and test resources; `src/test/resources` does not normally enter the production JAR, though both can appear on the test classpath.

If Gradle throws `DuplicateFileCopyingException`, inspect `processResources`, `bootJar`, `DuplicatesStrategy`, and source roots. In Maven, inspect `<resources>`, `includes/excludes`, `targetPath`, and packaging plugins. **Do not manually edit a packaged archive to hide duplicates**; fix the rule in the source/build config, rebuild, and re-verify.

## 12. Inspecting with Java 17 Without External ZIP Tools

Beyond `jar tf`, the JDK provides `java.util.jar.JarFile` to inspect entries by name. Example **standalone Java 17** program with no Spring Boot dependency:

Create `JarEntryCheck.java` in a separate directory:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public class JarEntryCheck {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected path to a JAR file");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile())) {
            System.out.println("manifest=" +
                    (jar.getJarEntry("META-INF/MANIFEST.MF") != null));
            System.out.println("app-class=" +
                    (jar.getJarEntry(
                            "BOOT-INF/classes/com/example/inspect/JarInspectApplication.class"
                    ) != null));
            System.out.println("resource=" +
                    (jar.getJarEntry("BOOT-INF/classes/demo/marker.txt") != null));
        }
    }
}
```

Compile and run with JDK 17 from the directory containing `JarEntryCheck.java`:

```bash
javac JarEntryCheck.java
java JarEntryCheck build/libs/jar-inspect-demo-1.0.0.jar
```

**Adjust the path** in the command if running from another directory, or pass an absolute path to the artifact. With a properly structured sample JAR from Section 5, the exact stdout of **this checker program** is:

```text
manifest=true
app-class=true
resource=true
```

This checks **entry presence** only; it does not read manifest contents, verify runtime dependencies, or execute the application. It is helpful when you want simple assertions without Bash `grep` or `unzip`. For a plain JAR, `BOOT-INF/classes/**` paths do not exist; update expectations to match the artifact type.

You can also call `JarFile.getManifest()` to inspect `Main-Class` and `Start-Class` attributes, handling the case where no manifest exists and verifying the right launch layout. The example above stays intentionally minimal and easy to run standalone.

## 13. Integrity, Checksums, Signatures, and Extraction Safety

### 13.1. ZIP CRCs Do Not Replace Signatures

```bash
unzip -t build/libs/jar-inspect-demo-1.0.0.jar
```

This tests compressed stream readability and entry CRCs. It **does not guarantee the artifact came from a trusted source or is safe to execute**. `jar tf` merely lists entry names without validating every class payload.

### 13.2. Comparing SHA-256 Checksums

Linux/macOS when `sha256sum` is available:

```bash
sha256sum build/libs/jar-inspect-demo-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\build\libs\jar-inspect-demo-1.0.0.jar
```

A checksum is meaningful when **compared against a reference hash obtained over a trusted channel** or when proving the inspected file matches the deployed file. Computing a hash on its own does not authenticate the publisher.

### 13.3. Signed JARs and Nested Libraries

For **genuinely signed library JARs**, the JDK provides:

```bash
jarsigner -verify -verbose -certs path/to/signed-library.jar
```

Do not confuse verifying a signature on the **outer executable JAR** with verifying every nested dependency JAR: they are separate artifacts that may use different signing/trust mechanisms. To verify software provenance, follow your organization's supply-chain workflow and policy rather than seeing `META-INF/*.SF` and assuming trust.

### 13.4. Safety When Handling Untrusted JARs

A JAR from an untrusted source may contain malformed paths, excessive entries, or crafted payloads that exhaust resources during extraction. Always **list entries first**, use an empty temporary directory, never run with elevated/admin privileges, and guard against path traversal. Never run `java -jar` on an untrusted program just to "see what is inside"; **reading entries** and **executing code** are completely different actions.

Never embed private keys, access tokens, or passwords in `src/main/resources`: if the build packages them, anyone holding the JAR can read them with `jar xf`/`unzip -p`. Minifying or renaming files does not protect secrets.

## 14. Automated Artifact Verification in CI

A pipeline can **fail fast** if an executable JAR misses mandatory entries. Bash example run from the **sample project root**:

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR='build/libs/jar-inspect-demo-1.0.0.jar'
test -s "$JAR"

jar tf "$JAR" > jar-entry-list.txt
grep -Fx 'META-INF/MANIFEST.MF' jar-entry-list.txt
grep -Fx 'BOOT-INF/classes/com/example/inspect/JarInspectApplication.class' jar-entry-list.txt
grep -Fx 'BOOT-INF/classes/demo/marker.txt' jar-entry-list.txt
grep -E '^BOOT-INF/lib/.*[.]jar$' jar-entry-list.txt

java -jar "$JAR" > jar-run.log
grep -Fx 'archive-resource=archive-inspection-ok' jar-run.log
```

`grep -Fx` requires **the entire line to equal the exact path**. This works here because the demo program runs and exits; if the JAR is a **long-running web server**, use a health/smoke test with managed process lifecycles and timeouts rather than running `java -jar` synchronously and waiting for it to exit.

A simple PowerShell check:

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
if (-not (Test-Path -LiteralPath $jar)) {
    throw 'Executable JAR not found'
}
$entries = @(jar tf $jar)
if ($LASTEXITCODE -ne 0) {
    throw 'jar tf failed'
}
$required = @(
    'META-INF/MANIFEST.MF',
    'BOOT-INF/classes/com/example/inspect/JarInspectApplication.class',
    'BOOT-INF/classes/demo/marker.txt'
)
foreach ($name in $required) {
    if ($entries -notcontains $name) {
        throw "Missing archive entry: $name"
    }
}
Write-Output 'Required JAR entries found'
```

These scripts are **samples tailored to this lesson's specific JAR layout**; do not apply them verbatim to plain JARs or WARs. You can harden them by checking the manifest, comparing release checksums, scanning for sensitive files, and running the artifact inside a test container. Preserve logs and reports properly in CI.

## 15. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `jar: command not found` | JDK not installed or wrong `PATH` | Check `JAVA_HOME`, `jar --version` |
| `NoSuchFileException` during `jar tf` | Wrong filename/path, not built yet | Inspect `build/libs` or `target` |
| `BOOT-INF/classes` missing | Inspecting plain JAR, shaded JAR, WAR, or other layout | Confirm which artifact type was intended |
| Maven creates `*.jar.original` | Backup before `repackage` | Inspect the executable JAR without this suffix |
| Gradle produces `-plain.jar` | `jar` task built plain JAR alongside `bootJar` | Pick the right classifier for deployment |
| `jar tf` shows manifest yet no contents | `t` only lists entries | Use `unzip -p` or `jar xf` |
| `java -jar` reports missing main | Manifest lacks/mispoints `Main-Class` or build skipped repackage | Read manifest and packaging plugin logs |
| `Start-Class` is right yet startup fails | Missing class/runtime dependency, bad config, or startup bug | `jar tf`, nested JARs, stack trace |
| Spring Framework class missing in outer listing | Classes live inside nested `BOOT-INF/lib/*.jar` | Extract the nested JAR and run `jar tf` on it |
| `getResourceAsStream` returns `null` | Wrong classpath path or resource excluded | Compare source, build output, and `BOOT-INF/classes` |
| Test classes/JUnit appear in production JAR | Wrong scope/configuration/packaging | Check `testImplementation` / Maven `test` scope |
| A library is missing | Excluded or wrong scope/version | Cross-check dependency graph and `BOOT-INF/lib` |
| `jar xf` dumps many files into project | Extracted entire archive in current directory | Use a temporary folder and extract only target entries |
| `unzip -p` writes binary to file and corrupts it | Shell encoding/redirection altered binary stream | Use `jar xf` or ZIP tool for raw byte extraction |
| Resource in JAR is right yet runtime config differs | Spring Boot property precedence/profile/external config | Inspect runtime environment, not just archive |
| JAR file is right yet container runs old version | CI/CD deployed wrong artifact/tag/cached image | Verify paths, checksums, and actual deployed image |
| `unzip -t` PASSES yet app fails | CRC validity differs from runtime compatibility/correctness | Run `java -jar`, check logs and dependencies |
| `layers.idx` missing | Not generated under current configuration | Not automatically an error; check build requirements |
| JAR unusually large | Extra dependencies, large resources, test data bundled | Inspect `BOOT-INF/lib`, resources, and entry sizes |

## 16. Pre-Release Checklist

- [ ] Know **the exact artifact** being deployed: plain/shaded JAR, `bootJar`, Maven `repackage`, or WAR.
- [ ] `jar tf` reads the newly built file, not an old file or wrong classifier.
- [ ] For a Boot executable JAR, `META-INF/MANIFEST.MF`, loader, `BOOT-INF/classes`, and `BOOT-INF/lib` (when runtime dependencies exist) are present.
- [ ] **Read the manifest contents** and confirm `Main-Class` and `Start-Class` are accurate.
- [ ] Key application classes exist inside the archive under the right package path.
- [ ] Required resources/config/templates/static assets sit at the right entry paths.
- [ ] Read at least one resource inside the archive to verify its **contents**, not just its filename.
- [ ] Know how to extract and inspect a nested JAR when checking dependency classes or resources.
- [ ] Compared nested dependencies against `runtimeClasspath` (Gradle) or `dependency:tree` (Maven).
- [ ] No test dependencies, temporary files, secrets, or private data leaked into the production archive.
- [ ] Integrity/checksums verified per policy and any extraction done in a safe directory.
- [ ] `java -jar`/smoke test ran on **the exact artifact to be deployed**, not just IDE sources.
- [ ] Pipeline fails if critical entries are missing and captures enough logs to diagnose failures.

**Remember:** `jar tf` answers "**what entries are inside the JAR?**"; `jar tvf` adds metadata; `jar xf` and `unzip -p` reveal "**what does the file actually contain?**"; the manifest defines launch behavior; `BOOT-INF/classes` holds app classes/resources; `BOOT-INF/lib` holds nested runtime dependencies. Only combining **listing entries → reading manifest/resources → checking libraries → running the real artifact** thoroughly verifies a Spring Boot executable JAR.

## References

- [Oracle JDK 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [Oracle JDK 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Spring Boot 3.3 — Developing Your First Spring Boot Application](https://docs.spring.io/spring-boot/3.3/tutorial/first-application/)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot — Executable JAR Format / Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)