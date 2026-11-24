# Running `java -jar` from an Isolated Directory and Verifying Loaded Resources

## 1. Goal and Significance of This Test

During Spring Boot development, applications often run cleanly inside an IDE or via `mvn spring-boot:run` / `./gradlew bootRun`. However, a release build must be able to run as **a standalone executable JAR**, without `src/main/resources`, `target/classes`, source code, Maven, or Gradle present in the deployment environment.

This hands-on test verifies that by **packaging the JAR, moving or invoking it from a completely separate directory, and running `java -jar`**. In addition to confirming startup succeeds, we verify that resource files are read **from the classpath inside the JAR**, rather than accidentally reading a file sitting in the project directory.

After this lesson, you will be able to:

1. Distinguish the **process working directory** (current working directory / CWD), **JAR file location**, **classpath**, and **path to a resource inside the archive**.
2. Inspect `BOOT-INF/classes`, `BOOT-INF/lib`, the Boot launcher, and the manifest of an executable Spring Boot JAR.
3. Read packaged resources with `ClassPathResource#getInputStream()` or `ClassLoader#getResourceAsStream()`, rather than assuming a resource is always a `java.io.File`.
4. Build and run a Spring Boot 4.1.2 example with Java 17 and Maven; verify with a unit test and an isolated JAR run in an empty directory on Linux/macOS or Windows PowerShell.
5. Perform the equivalent workflow with Gradle `bootJar`.
6. Distinguish **resources packaged inside the JAR** from **external configuration** that Spring Boot looks up in the working directory; diagnose `FileNotFoundException`, missing `BOOT-INF/classes`, wrong artifacts, wrong Java runtimes, and wrong working directories.
7. Know what evidence suffices for a packaging smoke test and where the test's limits lie.

**Example versions:** Spring Boot **4.1.2**, Java **17+**, Maven **3.6.3+** or Gradle **8.14+ (8.x line) / 9.x** per Spring Boot 4.1.2 compatibility requirements. Build tools are needed on the **build machine**; the host running the artifact only needs a compatible Java runtime.

## 2. Three Locations You Must Distinguish

Suppose after building we have:

~~~text
/home/developer/resource-jar-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── samples/payload.txt
└── target/
    └── resource-jar-demo-1.0.0.jar
~~~

We create an isolated directory:

~~~text
/tmp/boot-jar-run-abc123/
└── app.jar
~~~

And run:

~~~bash
cd /tmp/boot-jar-run-abc123
java -jar app.jar
~~~

At that point, three distinct paths exist:

| Type | Value in Scenario Above | Used For |
| --- | --- | --- |
| **CWD / `user.dir`** | `/tmp/boot-jar-run-abc123` | Resolving `Path.of("relative.txt")`, `new File("relative.txt")`, and external config files outside the JAR |
| **JAR file location** | `/tmp/boot-jar-run-abc123/app.jar` | Java locating and opening the archive file; does not necessarily match CWD when using an absolute path |
| **Classpath resource** | `samples/payload.txt`, inside the JAR at `BOOT-INF/classes/samples/payload.txt` | ClassLoader / Spring Resource API locating packaged resources |

**Key point:** `java -jar /some/path/app.jar` **does not automatically change the current working directory to `/some/path`**. The JVM runs with whatever CWD the shell, IDE, service manager, or container assigned to the process. You can run a JAR from CWD A even while the JAR sits in B.

Example:

~~~bash
cd /tmp
java -jar /opt/apps/app.jar
~~~

With this command, `Path.of("data/input.txt")` looks for `/tmp/data/input.txt`, **not** `/opt/apps/data/input.txt`. Meanwhile, classpath resource `samples/payload.txt` can still be loaded from the archive.

### Two Separate Verification Checks

- **Running the JAR from an isolated directory:** proves the launcher, dependencies, entry point, and runtime suffice to boot without the build directory.
- **Loading a resource inside the JAR:** proves the resource was copied into the archive and the code reads it in a JAR-compatible way. To be sure, you must read the **contents** of the resource, not merely check that the resource exists in the source tree.

An application may launch fine via `java -jar` yet fail to read a template, JSON file, or custom data file because the code hardcoded `src/main/resources/...`. Running from an isolated directory exposes that bug immediately.

## 3. What Is Inside an Executable Spring Boot JAR?

A JAR produced by the Spring Boot Maven Plugin's `repackage` goal or Gradle's `bootJar` task has a structure like:

~~~text
resource-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── dev/example/ResourceJarApplication.class
│   │   ├── application.properties
│   │   └── samples/payload.txt
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...
└── org/springframework/boot/loader/
    └── ...
~~~

- `BOOT-INF/classes` holds the **application's own** classes and resources.
- `BOOT-INF/lib` holds dependency JARs required at runtime under the executable archive design.
- `META-INF/MANIFEST.MF` holds launcher and entry-point metadata.
- The Spring Boot loader sets up the classpath for `BOOT-INF/classes` and nested dependencies. The ClassLoader sees `samples/payload.txt` by its **logical classpath path** without needing a `BOOT-INF/classes/` prefix in Java code.

Typical manifest for the JAR layout:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.ResourceJarApplication
~~~

`Main-Class` is the Spring Boot launcher; `Start-Class` is the application class containing `public static void main(String[] args)`. Never set `Main-Class` to the application class while overlooking how the Boot loader handles nested dependency JARs.

**Note:** running only `maven-jar-plugin:jar` without `repackage` may output a **plain JAR**. A plain JAR lacks the Boot layout and full runtime dependencies, so testing from an isolated directory may fail with `NoClassDefFoundError` or `no main manifest attribute`. The `.jar` extension does not prove an archive is an executable Spring Boot archive.

## 4. Proper Ways to Read Resources in an Executable JAR

### 4.1. `ClassPathResource#getInputStream()`

Spring Framework provides `ClassPathResource` to read resources from the classpath, whether they live in an external folder or inside a JAR:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
        new ClassPathResource("samples/payload.txt");

try (InputStream input = resource.getInputStream()) {
    String content = new String(input.readAllBytes(),
            StandardCharsets.UTF_8).strip();
    System.out.println(content);
}
~~~

This is an **illustrative snippet placed inside a method permitted to throw `IOException`**. The complete example in Section 6 includes the class, method, and all imports. Given `samples/payload.txt` containing `IN_JAR_RESOURCE_OK`, the exact line printed by this snippet is:

~~~text
IN_JAR_RESOURCE_OK
~~~

Using `InputStream` reads the resource through the executable JAR's classloader mechanism regardless of whether it exists as a physical file on disk. Use try-with-resources to close the stream after reading.

### 4.2. Plain Java `ClassLoader#getResourceAsStream()`

A plain Java API option without depending on Spring's `Resource` abstraction:

~~~java
try (InputStream input =
        ResourceJarApplication.class.getClassLoader()
                .getResourceAsStream("samples/payload.txt")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found on classpath");
    }
    String value = new String(input.readAllBytes(),
            StandardCharsets.UTF_8).strip();
    System.out.println(value);
}
~~~

This snippet also belongs inside an appropriate method because `readAllBytes()` can throw `IOException`. The name passed to `ClassLoader` is **`samples/payload.txt`**, with no leading `/`. With `ResourceJarApplication.class.getResourceAsStream("/samples/payload.txt")`, the leading `/` means "from classpath root", whereas `Class#getResourceAsStream("payload.txt")` without `/` resolves relative to the class's package. Distinguish the two APIs to avoid path errors.

### 4.3. Why Do `getFile()` and `Path.of(...)` Fail Easily?

The following is **not a recommended way to read a resource inside a JAR**:

~~~java
new ClassPathResource("samples/payload.txt").getFile();
~~~

When an IDE runs from an exploded classes directory, `getFile()` can return a real file and appear to work. However, when the resource lives **inside a JAR**, it is not an individual filesystem file reachable as `java.io.File`; `getFile()` may throw `FileNotFoundException`. Use `getInputStream()` to read it.

Similarly:

~~~java
Path path = Path.of("src/main/resources/samples/payload.txt");
~~~

reads the **source tree relative to CWD**, not the classpath. When moving the JAR to a host with only Java and no source tree, that path does not exist. `Path.of("samples/payload.txt")` is also a **CWD-relative** path; it does not magically look inside `BOOT-INF/classes`.

If a library genuinely requires a `java.io.File`, you may need to **copy the resource to a temporary file** via `getInputStream()`, pass the temp file to the library, and clean it up per application lifecycle. Never attempt to turn a `jar:`/nested-JAR URL into a regular `Path` and assume it exists standalone.

### 4.4. Reading Packaged Resources vs. Writing Runtime Files

Resources inside the JAR are **part of the artifact** and must not be modified directly to store user data. If an application needs to write uploads, logs, caches, reports, or output files, use a writable **external path**, such as a configured `app.storage-dir` value resolved via `Path.of(...)`.

| Need | Appropriate API | Example |
| --- | --- | --- |
| Read static templates/JSON/TXT shipped with the app | `ClassPathResource#getInputStream()` | `classpath:samples/payload.txt` |
| Read a classpath resource in plain Java | `ClassLoader#getResourceAsStream()` | `samples/payload.txt` |
| Read a configured external file | `Files.newInputStream(Path.of(configuredPath))` | `/srv/app/config/data.json` |
| Write runtime-generated data | `Files.write(Path, bytes)` in a writable directory | `/var/lib/myapp/outputs` |
| Read `application.properties` via Spring | Spring Boot Config Data / `Environment` | `app.setting` |

**Short rule:** files "shipped with the build" → classpath; files "provided or modified at deployment/runtime" → external filesystem/config outside the JAR.

## 5. Inputs, Outputs, and PASS Criteria

| Stage | Input | Output | Passing Evidence |
| --- | --- | --- | --- |
| Prepare source | Java 17 code, `pom.xml`/`build.gradle`, `src/main/resources/...` | Buildable workspace | Verify exact resource path and toolchain version |
| Process resources | `samples/payload.txt`, `application.properties` | `target/classes` or `build/resources/main` | Files present and contents not corrupted by filtering |
| Compile | Java source + classpath | `.class` | No compile errors; classes match target Java release |
| Unit test | Test source + processed resources | JUnit report | Classpath resource test passes, zero test failures |
| Package | Compiled classes + resources + runtime deps | Boot executable JAR | Contains `BOOT-INF/classes/samples/payload.txt` and nested libs |
| Isolated run | Only JAR + Java runtime, CWD outside project | Process runs/exits with status 0 | Prints valid resource-load markers, no source-tree dependency |
| Runtime configuration | `application.properties` in JAR + external config if any | Spring `Environment` | Know whether value came from package or external override |
| Release gate | Reports, artifact, checksum | Release-ready artifact | Both archive inspection and live execution pass |

**Do not equate them:** a passing unit test reading resources from `target/classes` does not prove the JAR contains the resource; `jar tf` showing the resource in the JAR does not prove the code reads it after changing CWD. This lab must satisfy **both layers of evidence**.

## 6. Complete Maven Example with Spring Boot 4.1.2 and Java 17

We build a **Spring Boot command-line application** without starting a web server. That lets `java -jar` print its results and exit cleanly, making it easy to verify in CI without managing ports or background processes. The example intentionally prints three markers:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-packaged-config
CWD_RESOURCE_EXISTS=false
~~~

These three lines are **the output printed by our code**, assuming it runs in an empty directory without `samples/payload.txt` and without external configuration overriding `app.setting`. JVM or tool logs/behavior may also appear depending on the environment.

### 6.1. Project Structure

~~~text
resource-jar-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/ResourceJarApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── samples/
    │           └── payload.txt
    └── test/
        └── java/dev/example/ResourceJarApplicationTest.java
~~~

All source files sit in **standard Maven locations**. Note that `samples/payload.txt` is not placed next to `pom.xml` or next to `resource-jar-demo-1.0.0.jar`; it belongs to the application's classpath resources.

### 6.2. Standalone POM — `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>resource-jar-demo</artifactId>
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
~~~

Explanation:

- **Starter parent** manages dependency and plugin defaults; declaring `spring-boot-maven-plugin` activates the parent-provided `repackage` execution to build the Boot executable JAR at `package`.
- `spring-boot-starter` provides core Spring Boot components without Web MVC since this example opens no HTTP server.
- `spring-boot-starter-test` provides JUnit Jupiter and test libraries; the parent selects compatible plugin versions.
- `<java.version>17</java.version>` sets Java 17 as the compile target under the parent configuration.
- `<packaging>jar</packaging>` tells Maven to produce the source JAR for the Boot plugin to repackage.
- Expected artifact path is `target/resource-jar-demo-1.0.0.jar`. If you customize `finalName` or `classifier`, update commands to match.

**If not using the starter parent:** importing the `spring-boot-dependencies` BOM does not bind the `repackage` execution automatically. You must explicitly configure the Boot Maven Plugin, its version, and the `repackage` execution in `package` to produce a runnable archive. Do not substitute a plain JAR and conclude resource loading is broken.

### 6.3. Resource to Verify — `src/main/resources/samples/payload.txt`

File contents (single line, optional trailing newline):

~~~text
IN_JAR_RESOURCE_OK
~~~

We intentionally use a short ASCII string independent of special encodings. Our Java code uses `UTF-8` and `strip()` to trim surrounding newlines/whitespace, so a trailing newline in the file does not alter the output marker.

### 6.4. Spring Configuration — `src/main/resources/application.properties`

~~~properties
spring.application.name=resource-jar-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
app.setting=from-packaged-config
~~~

- `web-application-type=none`: runs the app as a command-line program without starting a web server.
- `banner-mode=off`, `log-startup-info=false`, and `logging.level.root=OFF`: reduces background noise in this demo. That does not mean libraries or the JVM will never write anything to stderr.
- `app.setting`: a Spring property read from `Environment` at runtime. It verifies that **packaged `application.properties` was loaded by Spring Boot**.
- Never place secrets in packaged files. Real applications should load passwords/tokens from appropriate external configuration sources.

### 6.5. Main Class — `src/main/java/dev/example/ResourceJarApplication.java`

~~~java
package dev.example;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;

@SpringBootApplication
public class ResourceJarApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceJarApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyResources(Environment environment) {
        return args -> {
            ClassPathResource resource =
                    new ClassPathResource("samples/payload.txt");

            String content;
            try (InputStream input = resource.getInputStream()) {
                content = new String(input.readAllBytes(),
                        StandardCharsets.UTF_8).strip();
            }

            System.out.println("CLASSPATH_RESOURCE=" + content);
            System.out.println("APP_SETTING="
                    + environment.getProperty("app.setting"));
            System.out.println("CWD_RESOURCE_EXISTS="
                    + Files.exists(Path.of("samples/payload.txt")));
        };
    }
}
~~~

**Why does this code work on Java 17?**

- `InputStream#readAllBytes()` was added in Java 9, `String#strip()` in Java 11, and `Path.of()` in Java 11: all are present in Java 17.
- `CommandLineRunner` is a Spring Boot functional interface. The `@Bean` runs once the application context starts; since the app has no web server or background daemon keeping the JVM alive, it normally exits after the runner finishes.
- `ClassPathResource("samples/payload.txt")` resolves the file on the classpath. Under `java -jar`, the Spring Boot loader exposes `BOOT-INF/classes` as the classpath root.
- `Environment#getProperty("app.setting")` reads loaded Spring configuration without directly opening `src/main/resources/application.properties`.
- `Files.exists(Path.of("samples/payload.txt"))` **intentionally checks the wrong location type** to prove the CWD filesystem does not hold that file. It evaluates to `false` when run in an isolated directory containing only the JAR.
- Because `CommandLineRunner#run` declares checked exceptions, reading `InputStream` can throw `IOException` directly inside the lambda.

**No source file is accessed via `Path.of("src/main/resources/...")`.** This is crucial: the JAR can run on hosts that do not have the Maven project at all.

### 6.6. Unit Test — `src/test/java/dev/example/ResourceJarApplicationTest.java`

~~~java
package dev.example;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ResourceJarApplicationTest {

    @Test
    void canReadResourceFromTestClasspath() throws Exception {
        ClassPathResource resource =
                new ClassPathResource("samples/payload.txt");

        assertTrue(resource.exists());

        try (InputStream input = resource.getInputStream()) {
            String value = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
            assertEquals("IN_JAR_RESOURCE_OK", value);
        }
    }
}
~~~

This test verifies the resource can be read from the **test classpath**. During Maven execution, files in `src/main/resources` have already been copied into `target/classes` and normally sit on the test classpath. This is a **unit-level check**, not a packaging test of the archive. To guarantee portability, still run the actual JAR from a separate directory as shown in Section 8.

The unit test avoids `@SpringBootTest` because it only tests Spring's `ClassPathResource` (without starting an application context) and Java streams; this keeps the test fast and focused.

## 7. Building and Inspecting the JAR Before Moving Directories

In the project directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

`mvn clean verify` clears previous build outputs and runs through the `verify` phase, covering compilation, unit tests, and packaging. With the Boot starter parent and Boot Maven Plugin declared as above, the `repackage` goal produces the executable archive in `target`. Do not stop at `BUILD SUCCESS`; check the actual artifact and reports.

### 7.1. Viewing Build Outputs

~~~text
target/
├── classes/
│   ├── application.properties
│   ├── dev/example/ResourceJarApplication.class
│   └── samples/payload.txt
├── surefire-reports/
│   └── ...
├── resource-jar-demo-1.0.0.jar
└── resource-jar-demo-1.0.0.jar.original
~~~

`.jar.original` is the original JAR normally retained when the Boot plugin repackages the default main artifact; **do not** treat `.jar.original` as the release file. Projects may configure things differently (`classifier` or `attach`), so always use the exact executable file confirmed by build logs.

### 7.2. Listing Archive Contents

~~~bash
jar tf target/resource-jar-demo-1.0.0.jar
~~~

The listing must include:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/dev/example/ResourceJarApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/samples/payload.txt
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

If `BOOT-INF/classes/samples/payload.txt` is missing, check:

- Whether the file actually exists at `src/main/resources/samples/payload.txt` (exact case).
- Whether `target/classes/samples/payload.txt` was copied by `maven-resources-plugin`.
- Any `<resources>`, `<includes>`, `<excludes>`, filtering, or profile excluding the file.
- Which file was inspected; you might be looking at a plain JAR, stale artifact, or library module.

### 7.3. Reading Packaged File Contents Directly (Optional Tooling)

On Linux/macOS when `unzip` is available:

~~~bash
unzip -p target/resource-jar-demo-1.0.0.jar \
    BOOT-INF/classes/samples/payload.txt
~~~

Expected output:

~~~text
IN_JAR_RESOURCE_OK
~~~

For the config file:

~~~bash
unzip -p target/resource-jar-demo-1.0.0.jar \
    BOOT-INF/classes/application.properties
~~~

You should see `app.setting=from-packaged-config`. This is **packaged content evidence**, independent of whether IDE or source files looked right. You do not need to extract the whole JAR to verify it.

If `unzip` is absent, use `jar tf` to check entries; you can use `jar xf` inside a separate temporary folder to read contents, avoiding extracting into the workspace and overwriting files.

## 8. Required Practice: Running from an Isolated Directory

### 8.1. Linux/macOS: Copy the JAR to a New Directory

From the **project root** after `mvn clean verify` PASSES:

~~~bash
RUN_DIR="$(mktemp -d)"
cp target/resource-jar-demo-1.0.0.jar "$RUN_DIR/app.jar"

# The new directory has no src/, target/, pom.xml, or samples/
(cd "$RUN_DIR" && pwd && java -jar app.jar)
~~~

`mktemp -d` creates a fresh directory; because only the single JAR file was copied, no external `samples/payload.txt` exists under the process CWD. `(...)` spawns a subshell so changing directory applies **only to this run**, leaving your main terminal in its original location.

The three lines printed by the application (excluding the `pwd` line and any environment-dependent logs/diagnostics) must match:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-packaged-config
CWD_RESOURCE_EXISTS=false
~~~

**Condition for `APP_SETTING`:** no `--app.setting` argument is passed and no higher-precedence environment variable, system property, or external config source overrides it. If CI sets `APP_SETTING`, see Section 10 to distinguish intended override behavior from packaging bugs.

Explanation of the three lines:

1. `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK`: the file contents **were genuinely read** via `ClassPathResource` without a source tree present.
2. `APP_SETTING=from-packaged-config`: Spring Boot loaded a property from `application.properties` packaged inside the JAR.
3. `CWD_RESOURCE_EXISTS=false`: the relative filesystem path `samples/payload.txt` **does not exist on disk** in the new directory. This confirms line 1 did not rely on CWD paths.

Even if the output looks right, check the exit code if anything failed. Use a separate check on `$?` right after `java -jar` if needed; in POSIX shells, `$?` holds the exit status of the immediately preceding command, so check it before running another command.

### 8.2. Linux/macOS: Running the JAR by Absolute Path Without Copying

Another variant that also tests a CWD outside the project:

~~~bash
PROJECT_ROOT="$(pwd)"
RUN_DIR="$(mktemp -d)"
(
    cd "$RUN_DIR"
    java -jar "$PROJECT_ROOT/target/resource-jar-demo-1.0.0.jar"
)
~~~

In this variant, **the JAR remains in the project directory**, while the process runs with the temporary directory as its CWD. It demonstrates that `java -jar` does not require CWD to match the directory containing the artifact. To test **self-contained portability of dependencies/resources** most strictly, the copied-JAR variant in Section 8.1 remains clearer.

### 8.3. Windows PowerShell: Create a New Directory and Run

From the project root in PowerShell:

~~~powershell
$runDir = Join-Path $env:TEMP ("boot-jar-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runDir | Out-Null
Copy-Item .\target\resource-jar-demo-1.0.0.jar (Join-Path $runDir "app.jar")

Push-Location $runDir
try {
    java -jar .\app.jar
    if ($LASTEXITCODE -ne 0) {
        throw "java -jar failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

- `[guid]::NewGuid()` generates a unique folder name, avoiding stale build folders.
- `Push-Location`/`Pop-Location` restores your working directory.
- `$LASTEXITCODE` checks the Java process exit code instead of assuming PowerShell script execution implies JVM success.
- The three lines `CLASSPATH_RESOURCE`, `APP_SETTING`, and `CWD_RESOURCE_EXISTS` behave just like on Linux/macOS if no external overrides exist.
- In PowerShell, relative `.\app.jar` is the JAR file **on the filesystem**, while `samples/payload.txt` is located by ClassLoader **inside the archive**.

Never hardcode Linux paths like `/tmp/...` inside Java source code. The application relies solely on relative classpath resources and Spring `Environment`, so the exact same JAR runs across different filesystems.

### 8.4. Verifying the Test Directory Is Truly Isolated

Minimum criteria:

- The run directory **does not contain** `src/main/resources`.
- No `samples/payload.txt` file exists externally on the filesystem.
- Neither an IDE nor Maven is used to launch the class directly.
- Neither `target/classes` nor the build machine's classpath is added via `-cp`.
- Only `app.jar` and a valid Java runtime are needed; required dependencies reside inside the executable Boot JAR.
- The Java process exits cleanly and shows expected resource-reading markers.
- To verify the release artifact stayed intact, compare hashes of the project JAR and the copied JAR.

Optional example when `sha256sum` is available:

~~~bash
sha256sum target/resource-jar-demo-1.0.0.jar
sha256sum "$RUN_DIR/app.jar"
~~~

Both hashes must match because the file was only copied, not modified. On macOS use `shasum -a 256`; on PowerShell use `Get-FileHash`. Hashes verify the copied file wasn't altered, though they **do not replace** startup/resource verification.

## 9. Gradle: Running the Same Test with `bootJar`

Use **the exact same Java code** and files under `src/main/resources` from Section 6. Do not alter application code just because the build tool changed. To use Gradle instead of Maven, add these two files:

**`settings.gradle`**:

~~~groovy
rootProject.name = 'resource-jar-demo'
~~~

**`build.gradle`** (Groovy DSL, Java 17):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Explanation:

- The Gradle Java plugin adds source sets and `processResources`, `compileJava`, and `test` tasks.
- The Spring Boot Gradle plugin adds the `bootJar` task to package the **executable JAR**, distinct from `jar` which creates the plain JAR.
- Uses Gradle native `platform` to import the Boot BOM for runtime and test dependencies, since the Boot Gradle plugin alone does not imply all dependencies get versions automatically.
- `java.toolchain.languageVersion=17` requests JDK 17 for relevant Java tasks; the Gradle daemon JVM may differ, provided it is compatible with the active Gradle version.
- `useJUnitPlatform()` enables JUnit Jupiter test discovery.
- `src/main/resources/samples/payload.txt` is copied by `processResources` to `build/resources/main/samples/payload.txt`, and `bootJar` places it into `BOOT-INF/classes/samples/payload.txt`.

When a compatible Gradle Wrapper is present:

~~~bash
./gradlew clean build
jar tf build/libs/resource-jar-demo-1.0.0.jar
~~~

`./gradlew clean build` runs the project's build/verification lifecycle tasks; `./gradlew bootJar` creates the executable archive yet **does not by itself prove unit tests ran**. If a quality gate is needed, use `build` or invoke required verification tasks.

Isolated execution on Linux/macOS:

~~~bash
RUN_DIR="$(mktemp -d)"
cp build/libs/resource-jar-demo-1.0.0.jar "$RUN_DIR/app.jar"
(cd "$RUN_DIR" && java -jar app.jar)
~~~

The three verification lines match Section 8.1. On Windows, change the copy source to `.\build\libs\resource-jar-demo-1.0.0.jar` and use the PowerShell script from Section 8.3.

**Avoid grabbing the plain JAR by mistake:** a Gradle project may also output `*-plain.jar` or other archives. Use the output of the `bootJar` task and verify `BOOT-INF/classes`, `BOOT-INF/lib`, and the manifest before running.

## 10. Packaged Resources in the JAR vs. External Spring Configuration

Spring Boot features **externalized configuration**. For default application configuration files, Boot checks multiple locations, including:

- Classpath root and `classpath:/config/` — which can reside inside the executable JAR.
- Current working directory `./`.
- `./config/` and certain subdirectories beneath it.
- Environment variables, system properties, command-line arguments, and other property sources in Spring's precedence order.

This means `APP_SETTING=from-packaged-config` is **not a fixed runtime constant**. If the deployment environment intentionally supplies external configuration for the same `app.setting` key, Spring uses the external value even though `BOOT-INF/classes/application.properties` stays unchanged.

### 10.1. Testing with a Command-Line Argument

In the directory containing only `app.jar`:

~~~bash
java -jar app.jar --app.setting=from-command-line
~~~

The three lines printed by our code are now:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-command-line
CWD_RESOURCE_EXISTS=false
~~~

This is valid because command-line properties have higher precedence than `app.setting` inside the packaged application config file. **Resource `samples/payload.txt` stays unchanged** because the code reads it from the classpath. That proves runtime configuration is decoupled from the artifact's contents.

### 10.2. Testing with an External `application.properties`

Create `application.properties` **directly in the CWD where the JAR runs** containing:

~~~properties
app.setting=from-external-file
~~~

When running:

~~~bash
java -jar app.jar
~~~

the expected output, assuming no higher-precedence config source exists, is:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-external-file
CWD_RESOURCE_EXISTS=false
~~~

An external config file in CWD overrides the same key inside `BOOT-INF/classes/application.properties`. This is **by design**, not Spring Boot misreading a resource. This pair of checks helps you see that the JAR loaded its packaged resource properly while Spring `Environment` applied external configuration per precedence rules.

**Be careful when creating test files:** if a test requires an "entirely empty directory containing only `app.jar`", run the baseline test first; only afterward create external `application.properties` for the override experiment. Do not accidentally leave a config file from an earlier run polluting the baseline.

### 10.3. Environment Variables

Spring applies relaxed binding to property names. An environment variable `APP_SETTING` can normally override `app.setting`. On Linux/macOS, to test cleanly without environment interference, inspect `printenv APP_SETTING` before running; in PowerShell inspect `$env:APP_SETTING`. Never dump the entire environment to CI logs because it may contain secrets.

To verify **exact packaged contents**, read `BOOT-INF/classes/application.properties` directly from the JAR; to verify **runtime values**, use `Environment`/`@ConfigurationProperties` and document valid override sources.

### 10.4. `spring.config.location` and `spring.config.additional-location`

Spring Boot lets you specify external configuration locations:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

The `optional:` prefix allows missing paths without failing startup. `spring.config.additional-location` **adds** locations alongside default ones; `spring.config.location` can **replace** the default location set when configured. Pick the right one for your goal; if replacing default locations and forgetting classpath sources, you may lose packaged defaults you meant to keep.

For applications launched from unpredictable CWDs (service managers, Kubernetes, scheduled tasks), specify explicit external configuration paths rather than relying on `./config/` if the deployment setup does not guarantee the CWD.

## 11. Verifying Resources Across Multiple Layers

Whenever `CLASSPATH_RESOURCE` is wrong or fails, trace from top to bottom:

~~~text
src/main/resources/samples/payload.txt
          |
          | Maven resources:resources
          | or Gradle processResources
          v
target/classes/samples/payload.txt
or build/resources/main/samples/payload.txt
          |
          | Spring Boot repackage / bootJar
          v
BOOT-INF/classes/samples/payload.txt inside JAR
          |
          | Spring Boot launcher + class loader
          v
ClassPathResource("samples/payload.txt").getInputStream()
          |
          v
"IN_JAR_RESOURCE_OK"
~~~

Isolation table:

| First Point Where It Looks Wrong | Primary Hypothesis | Check |
| --- | --- | --- |
| Missing in source | Wrong path, forgot to commit | Check `src/main/resources/samples/payload.txt` |
| Missing in processed resources | Resource include/exclude, profile, plugin task | `target/classes` / `build/resources/main` |
| Missing entry in JAR | Wrong artifact/task/plugin, packaging rules | `jar tf`, Boot plugin `repackage`, `bootJar` |
| Entry exists in JAR yet code fails to load it | Wrong resource name, filesystem path used, wrong classloader | `ClassPathResource#getInputStream`, exact path |
| Resource loads yet app config is wrong | External config override, profile, `spring.config.location` | `Environment`, packaged config contents, CWD |
| Works in IDE yet fails with `java -jar` | Hidden source-tree dependency; code uses `getFile` or `Path.of("src/...")` | Run JAR in an empty CWD, inspect stack trace |
| Fails only on Linux at runtime | Path case sensitivity | Compare `Samples` vs. `samples`, `Payload.txt` vs. `payload.txt` |
| JAR runs on dev machine yet fails in CI | Missing/incompatible JDK runtime | `java -version`, `UnsupportedClassVersionError` |
| `ClassNotFoundException` on `java -jar` | Plain JAR, wrong manifest, or missing runtime dependency | `BOOT-INF/lib`, `Main-Class`, `Start-Class` |

**Never fix this by copying `src/main/resources` into the release directory** just to make the app run; that merely hides a packaging bug or bad resource-reading code, defeating the purpose of a standalone JAR.

## 12. Common Coding Mistakes

### Mistake 1: Assuming the Project Root Always Exists

~~~java
Files.readString(Path.of("src/main/resources/samples/payload.txt"));
~~~

Only works if the process runs from the project root **and** the source tree is still present. This is no way to test a packaged resource. Fix it with `ClassPathResource#getInputStream()`.

### Mistake 2: Calling `getFile()` on a Resource Inside a JAR

~~~java
new ClassPathResource("samples/payload.txt").getFile();
~~~

When running from an IDE's classpath directory, it may succeed; when the resource sits inside an archive, `getFile()` can fail because it is not a physical filesystem file. Fix it with `getInputStream()`; if a library requires `File`, copy the resource temporarily to disk.

### Mistake 3: Confusing Resource Path with Archive Entry Name

In the JAR it is `BOOT-INF/classes/samples/payload.txt`, yet when accessing it:

~~~java
new ClassPathResource("samples/payload.txt");
~~~

**Do not** write `new ClassPathResource("BOOT-INF/classes/samples/payload.txt")` because the launcher already treats `BOOT-INF/classes` as the classpath root. The wrong prefix causes the resource not to be found.

### Mistake 4: Misusing Leading `/` with `ClassLoader`

~~~java
ResourceJarApplication.class.getClassLoader()
        .getResourceAsStream("/samples/payload.txt");
~~~

The `ClassLoader` API expects resource names relative to the classpath root, **with no leading `/`**. Fix it to `"samples/payload.txt"`. With `SomeClass.class.getResourceAsStream("/samples/payload.txt")`, a leading `/` means "resolve from classpath root"; the two APIs are inconsistent.

### Mistake 5: Checking Only One Place

`mvn test` is green while `bootJar` or `repackage` drops the resource; conversely, `jar tf` shows the file while runtime code reads a relative filesystem path. Both **artifact inspection and isolated execution** are required; never skip either one.

### Mistake 6: Packaging Secrets and Writable Files

Classpath files inside a JAR are no place for runtime passwords, tokens, uploaded data, or log files. Packaging them forces rebuilds to change data, increases secret exposure risks, and breaks write expectations. Use external configuration/file storage with appropriate permissions.

### Mistake 7: Running the Wrong JAR File

- Maven may leave `*.jar.original` after `repackage`.
- Gradle may produce `*-plain.jar`.
- Multi-module builds produce many library/application JARs.
- Custom `classifier` or `finalName` alters filenames.

Select the artifact created by the Spring Boot packaging goal/task. Verify the manifest and `BOOT-INF` before running.

## 13. When Using Containers, Service Managers, or Docker

CWD still matters when applications are started by containers or system services. **Illustrative Dockerfile**, only used after building the JAR locally/in CI:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY target/resource-jar-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

In this example, `WORKDIR /opt/app` sets CWD; the application still loads `samples/payload.txt` from the classpath inside `app.jar`. Even if `WORKDIR` changes or an orchestrator alters the working directory, classpath resources remain unaffected, whereas `Path.of("relative.txt")` changes meaning.

The Dockerfile above assumes you **already built the JAR in the build context** and has no custom container policies. It is a minimal example omitting non-root users, provenance, image scanning, read-only filesystems, and multi-stage builds. In real systems, follow your organization's security policies and build reproducibility practices.

With `systemd` or Windows services, the working directory can also be configured independently. Never infer CWD from the folder holding the executable JAR. Specify external configuration paths explicitly.

## 14. CI Checklist for Verifying a Portable Executable JAR

A solid quality gate should verify:

1. **Source present:** the resource exists at `src/main/resources/...` in the commit being built.
2. **Resources task works:** the file is copied into the build's classes/resources output.
3. **Tests pass:** unit tests locate the resource with zero failures/errors.
4. **Right artifact:** the Boot executable JAR exists with a valid manifest, `BOOT-INF/classes/samples/payload.txt`, and required dependencies in `BOOT-INF/lib`.
5. **Unambiguous artifact:** CI grabs the exact app JAR, not `.jar.original`, `*-plain.jar`, library JARs, or stale outputs from an earlier run.
6. **Isolated CWD:** runs inside a fresh temporary directory with no source/resources directories.
7. **No build tool required:** uses only the Java runtime to execute `java -jar` after copying the JAR.
8. **Exit code 0:** the application completes with no stack traces.
9. **Resource-load marker:** `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK`.
10. **Spring config marker:** `APP_SETTING=from-packaged-config` in an un-overridden environment; test external overrides separately if needed.
11. **No external file dependency:** `CWD_RESOURCE_EXISTS=false` in the fresh CWD.
12. **Artifact integrity:** copied JAR hash matches built artifact if needed; store artifact checksum.
13. **Cross-platform:** if developing on Windows and deploying on Linux, verify path case sensitivity and separators.
14. **No secret leaks:** never print env vars or sensitive config contents into smoke-test logs.
15. **Clean up temp space:** clean up directories created by the job without deleting paths outside CI scope.

### Minimal Verification Script on Linux/macOS

From the project root after building:

~~~bash
set -eu
mvn clean verify

JAR="$(pwd)/target/resource-jar-demo-1.0.0.jar"
RUN_DIR="$(mktemp -d)"
cp "$JAR" "$RUN_DIR/app.jar"

output="$(cd "$RUN_DIR" && java -jar app.jar)"
printf '%s\n' "$output"

printf '%s\n' "$output" |
    grep -Fx 'CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK'
printf '%s\n' "$output" |
    grep -Fx 'APP_SETTING=from-packaged-config'
printf '%s\n' "$output" |
    grep -Fx 'CWD_RESOURCE_EXISTS=false'
~~~

This is an **illustrative smoke-test script**: with `set -e`, a failing `java -jar` or `grep` causes the script to stop with a non-zero exit code. In production add `trap` cleanup and CI-specific artifact/runner handling, and clear any external overrides like `APP_SETTING` if testing a clean baseline. The script does not run Maven inside the temporary directory; Maven runs only at the project root during the build step.

## 15. Before-and-After Scenarios Easy to Confuse

### Scenario A — Green in IDE, Fails in Deployment

**Before:** Java code uses `Path.of("src/main/resources/samples/payload.txt")`. The IDE runs at the project root so it finds the file. After copying the JAR to `/opt/app`, `NoSuchFileException` occurs.

**After:** switch to `new ClassPathResource("samples/payload.txt").getInputStream()`, verify the file exists at `BOOT-INF/classes/samples/payload.txt`, and test from an empty CWD to confirm proper loading.

### Scenario B — JAR Runs, Yet Config Differs

**Before:** a test expects `APP_SETTING=from-packaged-config`, while the host has `./application.properties` containing `app.setting=from-external-file`. The JAR runs and reads the resource fine, yet the config assertion fails.

**After:** separate packaged config from externalized config and check CWD/property precedence. Run baseline tests in a directory free of external configs, and test overrides in a separate test case.

### Scenario C — Copying Source Resources as a "Fix"

**Before:** the build forgot to copy `payload.txt` into the JAR; an operator copied the whole `src/main/resources` folder onto the production server so relative paths worked.

**After:** fix `<resources>`/`processResources` and classpath loading so production requires no source tree. Configure CI to fail releases if `jar tf` shows missing resources.

### Scenario D — Picking the Gradle Plain JAR by Mistake

**Before:** running `java -jar build/libs/resource-jar-demo-1.0.0-plain.jar`, hitting missing launcher/dependencies.

**After:** select the `bootJar` output, verify `BOOT-INF/lib`, and run from an isolated directory. Plain JARs are suited for libraries and do not carry Boot executable semantics.

## 16. Self-Check Questions

**Question 1.** Running `java -jar /opt/app/app.jar` when CWD is `/tmp/run`. Where does `Path.of("data.txt")` look?

**Answer:** `/tmp/run/data.txt`. It uses CWD, not `/opt/app`.

**Question 2.** A resource sits inside the JAR at `BOOT-INF/classes/samples/payload.txt`. What path should you pass to `ClassPathResource`?

**Answer:** `samples/payload.txt`. The Boot loader already maps `BOOT-INF/classes` as the classpath root.

**Question 3.** Why can `ClassPathResource#getFile()` work in an IDE yet fail when running the JAR?

**Answer:** IDEs typically run against exploded classes on the filesystem; inside an executable JAR, the resource is not an individual physical file. Read it with `getInputStream()`.

**Question 4.** Is a passing unit test that reads the resource from the test classpath enough to prove the JAR is portable?

**Answer:** No. You must verify the entry inside the JAR and run `java -jar` from a directory without the source tree.

**Question 5.** Do `CWD_RESOURCE_EXISTS=false` and `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK` contradict each other?

**Answer:** No. One checks the CWD filesystem; the other reads the classpath resource inside the JAR. This is the exact expected result.

**Question 6.** Adding an external `application.properties` with `app.setting=override` makes the output differ from packaged config. Is the resource inside the JAR broken?

**Answer:** Not necessarily. Spring Boot prioritizes runtime configuration sources per externalized configuration rules; verify the packaged resource in the JAR and the `Environment` value separately.

**Question 7.** When using the Maven starter parent and declaring `spring-boot-maven-plugin`, which goal builds the executable JAR?

**Answer:** The `repackage` goal, bound to the `package` phase by the starter parent configuration.

**Question 8.** In Gradle, which task packages the executable Spring Boot JAR?

**Answer:** `bootJar`. Ordinary `jar` serves a different purpose and is not equivalent to `bootJar`.

**Question 9.** Should you reference `src/main/resources` inside a Docker image to read a resource already packaged in the JAR?

**Answer:** No. Read resources from the classpath; a Docker image does not need the source tree copied just for the application to run.

**Question 10.** Why is `jar tf` alone not enough?

**Answer:** It proves the file exists in the archive, not that the JVM Boot launcher starts, the code uses the right path, Spring config loads properly, or the process exits 0.

## 17. Key Takeaways and Final Checklist

- [ ] Build the **Boot executable JAR**, never a plain JAR or `.jar.original`.
- [ ] Place resources in `src/main/resources/...`, landing at `BOOT-INF/classes/...` in the artifact.
- [ ] Code reads classpath resources as streams, without relying on `src/main/resources` or `Resource#getFile()`.
- [ ] Run `java -jar` from a fresh CWD with no `src`, `target`, `build`, or `classes` directory.
- [ ] Verify exact read contents and the Java process exit code.
- [ ] Understand that CWD, JAR location, and classpath resource are three distinct concepts.
- [ ] Distinguish packaged `application.properties` from external configuration that can override it.
- [ ] Inspect manifest launcher, nested dependency JARs, source resources, and processed resources when errors occur.
- [ ] Never write runtime data into resources packaged inside the JAR.
- [ ] Run an automated smoke test on the artifact before release.

**Conclusion:** A truly portable application does not need to sit next to its source tree. When a JAR is properly packaged, `ClassPathResource("samples/payload.txt")` reads the data from `BOOT-INF/classes/samples/payload.txt`, even when `Path.of("samples/payload.txt")` reports the file does not exist in the working directory. That is the single most important proof in this lesson.

## 18. Official Documentation

1. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
3. [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
4. [Spring Boot — NestedJarFile and Class Loading](https://docs.spring.io/spring-boot/specification/executable-jar/jarfile-class.html)
5. [Spring Framework — Resources / ClassPathResource](https://docs.spring.io/spring-framework/reference/core/resources.html)
6. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
7. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
8. [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
10. [Oracle Java — ClassLoader#getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)