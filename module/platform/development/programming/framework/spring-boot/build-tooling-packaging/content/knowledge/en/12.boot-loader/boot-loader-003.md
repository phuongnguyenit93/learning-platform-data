# Relationship Between Manifest, Launcher Class, and Application Classpath

In a Spring Boot application packaged as an **executable JAR**, running `java -jar app.jar` looks as if only a single file is needed. Yet to find the application's `main()` and classes belonging to Spring, Jackson, Tomcat…, Java must know **where the entry point is** and **what the actual classpath consists of**. Spring Boot solves this with three tightly coordinated components:

1. **Manifest (`META-INF/MANIFEST.MF`):** contains `Main-Class` — the class the Java launcher invokes first — and usually `Start-Class` — the main class of *the application*.
2. **Boot Loader (`JarLauncher`, `WarLauncher`, or `PropertiesLauncher`):** launches before the application, understands Spring Boot's archive structure, sets up the appropriate classloader/classpath, and hands control over to `Start-Class`.
3. **Application classpath:** consists of the project's own classes/resources and runtime JARs that the loader finds from locations inside the archive or validly configured additional locations.

**Key takeaway right away:** In Spring Boot 3.3.13, a standard executable JAR has `Main-Class: org.springframework.boot.loader.launch.JarLauncher`, while `Start-Class: dev.example.bootloader.BootLoaderDemoApplication` is an example developer-written class. **`Main-Class` and `Start-Class` are not the same.** The loader is not the Spring `ApplicationContext`; it handles finding and loading classes *before* `SpringApplication.run(...)` can execute.

This lesson pins the examples to **Java 17, Spring Boot 3.3.13**, and the corresponding Maven/Gradle packaging. Paths and package names are chosen for reproducibility and do not represent the latest versions of all tools.

## 1. Two Startup Layers: JVM Launcher and Spring Boot Loader

First, clearly distinguish two very similar-sounding names:

- **Java launcher** is the JDK/JRE `java` executable. When running `java -jar ...`, it opens the archive and reads `Main-Class` per the Java JAR standard.
- **Spring Boot Loader** consists of Java classes inserted by Spring Boot into the executable archive, such as `org.springframework.boot.loader.launch.JarLauncher`. It is the `Main-Class` that the Java launcher runs, which then invokes the application class.

Flow for a Spring Boot 3.3 executable JAR:

```text
Terminal command
java -jar target/bootloader-demo-1.0.0.jar --spring.profiles.active=dev
     |
     v
[1] JVM / Java launcher
    Opens JAR -> reads META-INF/MANIFEST.MF
    Main-Class = org.springframework.boot.loader.launch.JarLauncher
     |
     v
[2] Spring Boot JarLauncher
    Recognizes BOOT-INF/classes and BOOT-INF/lib/*.jar
    Sets up classloader and classpath with nested JARs
    Reads Start-Class = dev.example.bootloader.BootLoaderDemoApplication
     |
     v
[3] BootLoaderDemoApplication.main(String[] args)
    SpringApplication.run(BootLoaderDemoApplication.class, args)
     |
     v
[4] Spring Boot application startup
    Loads configuration/profiles, auto-configuration, beans, web server
     |
     v
[5] HTTP endpoint ready to serve requests
```

Stage **[2]** is precisely why an executable Boot JAR can keep libraries as nested JARs inside it. `Main-Class` gets Java into the right *bootstrap loader*; `Start-Class` helps the bootstrap loader find the right *application main method*; the **classpath** enables the main method and framework to load the classes they use.

If one link in the chain is wrong:

- Missing `Main-Class`: `java -jar` cannot find an entry point.
- `Main-Class` points to a class name missing from the JAR/root classpath: Java reports it could not load the main class.
- Loader is present but `Start-Class` is wrong: the loader starts up but fails to find the application main class.
- Both manifest attributes are right but the classpath lacks `spring-web`, `jackson-databind`, or another module: the application can still fail with `ClassNotFoundException`/`NoClassDefFoundError` at runtime.

## 2. What Does the Manifest Provide, and What Does It Not?

`META-INF/MANIFEST.MF` is the standard metadata file in a JAR. An illustrative manifest snippet for Boot 3.3:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
Spring-Boot-Version: 3.3.13
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
```

These lines are **representative attributes**; plugins may add `Build-Jdk-Spec`, layer/classpath index metadata, implementation version... Do not rely on the real manifest matching byte-for-byte or in line order. The JAR manifest also has long-line wrapping rules; use a proper manifest parser when analyzing it.

| Attribute | Who consumes it? | Role |
| --- | --- | --- |
| `Manifest-Version` | Standard JAR format tools | Manifest format version, **not the Spring Boot version** |
| `Main-Class` | JVM Java launcher when using `-jar` | Class invoked **first**; for a default Boot JAR this is `JarLauncher` |
| `Start-Class` | Spring Boot Loader | Developer-written application main class |
| `Spring-Boot-Version` | Metadata added by Boot packaging tool | Indicates the Boot version used during packaging |
| `Spring-Boot-Classes`/`Spring-Boot-Lib` | Packaging layout metadata | Respective locations of classes and nested libraries, not Java's manifest `Class-Path` |
| `Class-Path` (if present in regular JAR) | Java launcher/standard manifest classpath | References **external** libraries per Java manifest rules; does not automatically turn nested BOOT-INF/lib into a Java classpath |

**Important:** `Start-Class` is **not** an attribute used by the standard Java launcher to select `main()`. Without Spring Boot Loader or a bootstrap loader that understands `Start-Class`, adding that line to a manifest will not make Java automatically locate the application class.

### The Manifest Does Not Replace the Dependency Graph or Runtime Configuration

The manifest does not download Maven dependencies, decide which Spring beans get created, or replace `application.yml` or a secret manager. It only provides part of the **startup contract**. Files like `application-dev.yml`, environment variables, and `--spring.profiles.active` are processed by Spring Boot **after entering the application**, not used to locate `JarLauncher`.

If a user passes:

```bash
java -jar target/bootloader-demo-1.0.0.jar --spring.profiles.active=prod
```

`--spring.profiles.active=prod` is an **application argument** passed to `main(args)`; it does not alter `Main-Class`, `Start-Class`, `BOOT-INF/lib`, or how the JVM reads the manifest.

## 3. How Does a Spring Boot Executable JAR Organize Classes and Dependencies?

A regular JAR may contain compiled application classes at the package path directly from the root:

```text
plain.jar
├── META-INF/MANIFEST.MF
└── dev/example/bootloader/BootLoaderDemoApplication.class
```

Meanwhile, a Spring Boot **executable JAR** has a specific layout:

```text
bootloader-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   ├── launch/JarLauncher.class
│   └── ... other Boot Loader classes
└── BOOT-INF/
    ├── classes/
    │   ├── dev/example/bootloader/
    │   │   ├── BootLoaderDemoApplication.class
    │   │   └── ProbeController.class
    │   └── message.txt
    ├── lib/
    │   ├── spring-boot-3.3.13.jar
    │   ├── spring-boot-autoconfigure-3.3.13.jar
    │   ├── spring-web-*.jar
    │   ├── jackson-databind-*.jar
    │   └── ... other runtime dependencies
    ├── classpath.idx       (may be present)
    └── layers.idx          (may be present)
```

Notable points:

1. **Boot Loader classes** sit where the Java launcher can find them when invoking `Main-Class` in the archive.
2. **Application classes/resources** live in `BOOT-INF/classes/`, not at Java's classpath root when running `-cp myboot.jar`.
3. **Runtime dependencies** are separate JAR archives nested inside `BOOT-INF/lib/`. An outer JAR in standard ZIP format does not automatically make inner JARs Java classpath entries.
4. **JarLauncher** understands the Boot structure, creates a classloader that supports nested JARs, and brings app classes/dependencies into the resource lookup path.
5. `classpath.idx` and `layers.idx` are metadata for other purposes; they are not alternate names for `Main-Class`/`Start-Class`.

This is why **you cannot rename a plain JAR to a boot JAR** or merely insert `Main-Class: ...JarLauncher` into an existing file expecting it to have the full Boot Loader and nested layout.

### Why Keep Dependencies as Nested JARs?

Suppose `spring-web-6.x.jar` sits in `BOOT-INF/lib/`. Instead of extracting all Spring Web `.class` files to the root, Boot keeps it as a separate JAR. This helps identify libraries, manage resources/class loaders according to Spring Boot's layout, and support image layering.

Execution relies on Boot's nested archive resolver; regular ZIP readers only see it as an **entry inside a ZIP**, without adding it to the classpath. Spring Boot Loader uses archive reading utilities and classloaders to resolve them at runtime.

**Do not modify nested JAR ZIPs arbitrarily.** Per Spring Boot's executable archive restrictions, the entry holding a nested JAR inside the outer archive must use the `STORED` ZIP method so the loader can access internal data properly; the nested JAR's own contents may be compressed independently. An ad-hoc ZIP repacking tool can break this requirement even though `jar tf` still lists the filenames.

## 4. Where Is the Application's Classpath Created?

The **Classpath** is the set of places where Java/classloaders look for classes and resources: directories, JARs, modules, or special sources supported by a classloader. For a typical Java app, developers pass those locations via `-cp`. For a Spring Boot executable JAR, the launcher itself builds the required classpath.

### 4.1. Traditional Java Classpath

```bash
java -cp "app.jar:lib/*" dev.example.bootloader.BootLoaderDemoApplication
```

The command above is Linux/macOS style. On Windows, the classpath entry separator is `;`:

```powershell
java -cp "app.jar;lib/*" dev.example.bootloader.BootLoaderDemoApplication
```

Java looks for application classes at the root of `app.jar` and library classes from `.jar` files directly inside `lib/`. This suits a **plain JAR + external dependencies**, provided `app.jar` actually has classes at the package root and all required libraries are supplied.

### 4.2. Spring Boot Executable JAR Classpath

```bash
java -jar target/bootloader-demo-1.0.0.jar
```

Here you **do not** list each dependency on `-cp`. The Java launcher finds `JarLauncher` from the manifest; the launcher adds `BOOT-INF/classes/` and the nested libraries in `BOOT-INF/lib/` into the Boot-managed classpath, then calls `Start-Class`.

**In Java's `-jar` mode, `-cp`/`CLASSPATH` parameters are not used the way `-cp` launches work.** Thus the command:

```bash
java -cp "external/*" -jar target/bootloader-demo-1.0.0.jar
```

does not make `external/*` appear in the Boot application classpath. If libraries outside the archive are needed, you must use an appropriate mechanism like `PropertiesLauncher`, or intentionally change how the application is packaged/run.

### 4.3. Loader Classpath Differs from Dependency Management

BOM/Maven/Gradle **decides versions and the set of build artifacts to resolve**. The build plugin **decides which artifacts actually get packaged**. `JarLauncher` **decides how packaged artifacts are found and loaded**. These are three independent but sequential steps:

```text
pom.xml / build.gradle
    |
    | dependency resolution: determines runtime dependencies
    v
spring-boot:repackage / bootJar
    |
    | places runtime jars into BOOT-INF/lib
    | places compiled app into BOOT-INF/classes
    | inserts loader and manifest
    v
executable JAR
    |
    | java -jar -> JarLauncher -> creates runtime classpath
    v
SpringApplication.run -> application
```

If `BOOT-INF/lib` is missing a dependency due to a wrong scope/configuration, **the loader will not automatically download that dependency over the Internet**. If `BOOT-INF/lib` contains multiple versions of a library, classpath ordering can decide which one is seen; fix dependency resolution/build rather than "hoping the loader picks the newest one".

## 5. JarLauncher, WarLauncher, and PropertiesLauncher: Choosing the Right Bootstrap

Spring Boot 3.3 features three primary launchers:

| Launcher | Main-Class in manifest | Classpath/archive it targets | When to use |
| --- | --- | --- | --- |
| **JarLauncher** | `org.springframework.boot.loader.launch.JarLauncher` | `BOOT-INF/classes/` and nested JARs in `BOOT-INF/lib/` | Default executable **JAR** |
| **WarLauncher** | `org.springframework.boot.loader.launch.WarLauncher` | `WEB-INF/classes/`, `WEB-INF/lib/`, and `WEB-INF/lib-provided/` | Executable **WAR** |
| **PropertiesLauncher** | `org.springframework.boot.loader.launch.PropertiesLauncher` | Boot application paths plus extra paths specified by `loader.path`/`LOADER_PATH` | When extra classpath locations outside the archive are needed |

**`JarLauncher`/`WarLauncher` have relatively fixed classpath layouts.** Do not set `loader.path` expecting `JarLauncher` to start searching for extra external libraries. `loader.path` is a feature of **`PropertiesLauncher`**, requiring the Boot archive to be packaged/configured to launch with that launcher.

### WAR Example

An executable WAR typically contains:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/dev/example/bootloader/BootLoaderDemoApplication.class
WEB-INF/lib/*.jar
WEB-INF/lib-provided/*.jar
```

The manifest may specify:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

`WEB-INF/lib-provided` stores dependencies needed when the WAR runs in executable mode that should not cause conflicts when deployed to an external servlet container. A real WAR application needs proper `war` packaging, server dependency configuration, and the corresponding bootstrap mechanism. Do not turn a Boot JAR into a WAR by renaming the extension.

### `PropertiesLauncher` and External Libraries

When there is a valid requirement for plugins/libraries installed outside the JAR, `PropertiesLauncher` lets you add directories/archives to the classpath:

```bash
java -Dloader.path=external-libs -jar target/bootloader-demo-1.0.0.jar
```

**This only takes effect as intended when the JAR manifest specifies `PropertiesLauncher`**. With the default `JarLauncher`, this is not a "universal add classpath switch". The `external-libs` path is resolved relative to `loader.home`/working directory, and the folder must contain actual JARs. Do not use untrusted external classpath sources: a malicious JAR in the class-loading path can be executed by the JVM inside the application process.

Configuring `PropertiesLauncher` can be done in Maven using layout `ZIP` or `DIR` (alias), and in Gradle via task manifest/Main-Class per plugin docs. Sample fragments appear in Section 9.

## 6. Maven Spring Boot Hands-On: Observing Manifest, Classpath, and Classloader

We will use an application small enough to run on JDK 17, yet containing a real library inside `BOOT-INF/lib` to prove the nested classpath works. The app exposes a `/probe` endpoint:

- Reads resource file `message.txt` in `BOOT-INF/classes` via the **thread context classloader**.
- Asks the classloader to load `com.fasterxml.jackson.databind.ObjectMapper`, a class from the Jackson library pulled in by Spring Boot Web starter.
- Returns the fixed body `message=loader-ready; jackson=true` for verification without depending on classloader names or internal URLs.

### 6.1. Project Structure

```text
bootloader-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/bootloader/
    │   │   ├── BootLoaderDemoApplication.java
    │   │   └── ProbeController.java
    │   └── resources/
    │       └── message.txt
    └── test/
        └── java/dev/example/bootloader/
            └── ProbeControllerTest.java
```

### 6.2. Complete POM

`pom.xml`:

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
    <artifactId>bootloader-demo</artifactId>
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
                <configuration>
                    <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Explanation:

- The parent `spring-boot-starter-parent` provides dependency management and suitable plugin configuration, including the `repackage` execution when the Spring Boot Maven Plugin is declared under `build/plugins`.
- The Maven JAR Plugin creates a normal JAR archive during the `package` lifecycle; the `spring-boot:repackage` goal adds the loader, nested libraries, and appropriate manifest, replacing the default main artifact.
- `<mainClass>...BootLoaderDemoApplication</mainClass>` explicitly tells **the Boot plugin which application main class to use during packaging**, corresponding to `Start-Class`. It **does not** point the executable JAR's `Main-Class` directly to the application class; `Main-Class` is still determined by the layout/launcher.
- If a project **only imports the `spring-boot-dependencies` BOM** instead of using the starter parent, the BOM does not automatically bind plugin goals; you must explicitly declare the version and `repackage` execution.
- Spring Boot version 3.3.13 avoids mixing old `JarLauncher` package names from Spring Boot 2.x with the new `.launch.` name.

### 6.3. Java Main Class

File `src/main/java/dev/example/bootloader/BootLoaderDemoApplication.java`:

```java
package dev.example.bootloader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootLoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootLoaderDemoApplication.class, args);
    }
}
```

File `src/main/java/dev/example/bootloader/ProbeController.java`:

```java
package dev.example.bootloader;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public String probe() throws IOException, ClassNotFoundException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();

        String message;
        try (InputStream input = loader.getResourceAsStream("message.txt")) {
            if (input == null) {
                throw new IllegalStateException("message.txt missing from classpath");
            }
            message = new String(input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }

        Class<?> jackson = Class.forName(
                "com.fasterxml.jackson.databind.ObjectMapper",
                false,
                loader
        );

        return "message=" + message + "; jackson=" + (jackson != null);
    }
}
```

File `src/main/resources/message.txt` has **one line**:

```text
loader-ready
```

The steps in `ProbeController` are purely educational:

1. `Thread.currentThread().getContextClassLoader()` retrieves the classloader set by the framework/loader for the handling thread. This is the right way to locate resources and classes when using nested JARs.
2. `getResourceAsStream("message.txt")` looks up the resource on the **application classpath** — when packaged as a Boot JAR, the resource lives under `BOOT-INF/classes/message.txt` yet is still resolved via the logical name `message.txt`.
3. `Class.forName(..., false, loader)` asks the classloader to locate `ObjectMapper`. In this Boot 3.3 example with `spring-boot-starter-web`, Jackson is in the runtime dependency graph; it usually sits inside a nested JAR under `BOOT-INF/lib`. `false` means do not force class initialization via static initializer merely for the check.
4. The HTTP result is a fixed string that does not expose file path details or the server's entire classpath. In production, do not expose an endpoint letting clients supply arbitrary class names to attempt loading.

**Classloader note:** `ClassLoader.getSystemClassLoader()` is not guaranteed to see classes in nested Boot JARs. Spring Boot documentation emphasizes using the **thread context classloader** when a library needs to load classes dynamically. Do not hard-code concrete classloader names: implementations can change across releases.

### 6.4. Java Test

File `src/test/java/dev/example/bootloader/ProbeControllerTest.java`:

```java
package dev.example.bootloader;

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
class ProbeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void classpathResourceAndJacksonAreAccessible() throws Exception {
        mockMvc.perform(get("/probe"))
                .andExpect(status().isOk())
                .andExpect(content().string("message=loader-ready; jackson=true"));
    }
}
```

**Scope of evidence:** The test confirms the resource and Jackson class can be loaded on the **test runner's classpath**, not that the executable archive was completely and properly repackaged. That is why the next section requires also running `java -jar` and an HTTP smoke test against **the actual release JAR**.

## 7. Maven Build: Generating the Artifact and Observing Both Startup Layers

Inside the `bootloader-demo` directory, with JDK 17 and Maven 3.9.x (or a matching Maven Wrapper):

```bash
mvn -version
mvn clean verify
```

If using Maven Wrapper, you can replace `mvn` with `./mvnw`; on Windows use `mvnw.cmd`.

Per the POM configuration in Section 6, a normal build produces:

```text
target/bootloader-demo-1.0.0.jar
target/bootloader-demo-1.0.0.jar.original
```

- `bootloader-demo-1.0.0.jar` is the **Spring Boot executable JAR** after `repackage`.
- `.jar.original` is the JAR archive before Boot repackaging, typically without the loader and without bundled runtime dependencies. It is the original ZIP-format JAR even though its filename ends in `.original`.
- If a project uses a classifier or custom plugin configuration, names and attached artifacts may differ; always inspect the actual output.

### 7.1. Inspect the Manifest

Linux/macOS, if `unzip` is available:

```bash
unzip -p target/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Important lines to look for:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

The Java `jar` tool can also extract the manifest into an empty working directory if `unzip` is unavailable:

```bash
mkdir -p target/inspect-jar
cd target/inspect-jar
jar xf ../bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

After the `cd` in this example, return to the project root before running `mvn` or `java -jar target/...`.

**Diagnosing the manifest:**

- `Main-Class` is `JarLauncher` and `Start-Class` is your class: standard executable JAR design.
- `Main-Class` points to the app class while classes already reside in `BOOT-INF/classes`: sign that someone edited the manifest or misconfigured the build task.
- `Start-Class` points to a nonexistent class/one without `main(String[])`: fix the Boot plugin's main class configuration.
- Only `Main-Class` is seen at the archive root: it may be a different runnable Java JAR, not proof of a Boot nested classpath.

### 7.2. Inspect Archive Classpath Entries

```bash
jar tf target/bootloader-demo-1.0.0.jar
```

In the actual output, look for at least:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/bootloader/BootLoaderDemoApplication.class
BOOT-INF/classes/dev/example/bootloader/ProbeController.class
BOOT-INF/classes/message.txt
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
```

Other dependency names may vary with the Spring Boot version, BOM, and resolved graph. `jar tf` lists **file entries** and does not by itself prove every dependency is compatible or will load successfully; a smoke test must be run.

Verify the rule "application classes are not at the root" by comparing:

```bash
jar tf target/bootloader-demo-1.0.0.jar.original
```

The plain JAR may contain:

```text
dev/example/bootloader/BootLoaderDemoApplication.class
dev/example/bootloader/ProbeController.class
message.txt
```

However, it **does not** have `BOOT-INF/lib` containing Spring runtime JARs in the Boot executable structure.

### 7.3. Start Up and Confirm the Real Classpath Works

Use `java -jar` with the repackaged JAR:

```bash
java -jar target/bootloader-demo-1.0.0.jar
```

Once the server has started, in another terminal:

```bash
curl -s http://localhost:8080/probe
```

Returned body from the example code:

```text
message=loader-ready; jackson=true
```

Both data pieces in the body prove the classloader sees both the **application resource** and **a class inside a runtime dependency**. You still need to inspect the final JAR itself with `jar tf` and check the manifest as above; the endpoint does not prove the startup classpath of every other library in the system is valid.

If port 8080 is already in use, pick another port:

```bash
java -jar target/bootloader-demo-1.0.0.jar --server.port=8081
curl -s http://localhost:8081/probe
```

Run `curl` in a second terminal while the application is serving; do not run two applications on the same port simultaneously. `--server.port=8081` is a Spring Boot argument and does not modify the classpath or manifest.

## 8. Maven: Configuring the Main Class and the Meaning of `spring-boot:repackage`

In the sample POM, the fragment:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
    </configuration>
</plugin>
```

ensures the Boot plugin knows the **application main class**. With the default JAR layout:

- The executable archive's `Main-Class` is chosen by the Boot plugin based on the **JAR layout**: `org.springframework.boot.loader.launch.JarLauncher`.
- The executable archive's `Start-Class` points to `BootLoaderDemoApplication` per `mainClass`.
- `BOOT-INF/classes` and `BOOT-INF/lib` are built from compiled outputs and dependencies per plugin configuration.
- If there are no multiple main classes, the plugin can auto-detect a suitable main class; with multiple main classes, configure it explicitly to avoid ambiguity.

**Do not set `Main-Class` via `maven-jar-plugin` expecting the Boot plugin to leave it intact.** The Spring Boot Maven Plugin rewrites the manifest during `repackage`. To change the application main class, configure `mainClass` on the **Boot plugin**; to use a different launcher, configure a Boot-supported **layout/launcher**.

### BOM Import Does Not Create Boot Loader

Having only:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

only manages dependency versions. It does not automatically attach the `spring-boot:repackage` goal, does not add `JarLauncher`, and does not place runtime JARs under `BOOT-INF/lib`. When using a corporate parent with BOM import, the project must explicitly configure the Spring Boot Maven Plugin/version/execution to get an executable archive.

**Distinguish three steps:** Maven dependency resolution chooses *which JARs*; `repackage` decides *where to package JARs*; `JarLauncher` decides *how to load packaged JARs*.

## 9. Configuring `PropertiesLauncher` When an External Classpath Is Truly Needed

`JarLauncher` suffices for most Spring Boot services. When an application needs a classpath from a directory outside the JAR (such as separately distributed plugin JARs), you can switch launchers using supported configuration.

### 9.1. Maven: ZIP/DIR Layout

Replace the Spring Boot Maven Plugin configuration in the sample POM with:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

This is a **fragment** inside `<build><plugins>` of a full POM, not a standalone POM. With `layout=ZIP` (alias `DIR`), the Spring Boot Maven Plugin uses **`PropertiesLauncher`** per the documentation; the output is still an executable archive, but `Main-Class` changes.

After rebuilding:

```bash
mvn clean package
unzip -p target/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

The key lines must become:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

Only then can you add an external library path via `loader.path`:

```bash
java -Dloader.path=external-libs -jar target/bootloader-demo-1.0.0.jar
```

The learning example has no external libraries yet, so the app still only uses packaged nested dependencies. If you create `external-libs` containing JARs, `PropertiesLauncher` can add them to the classpath according to its rules and ordering. **Do not place libraries from untrusted sources on the application load path**, as this loads executable code into the JVM.

Another option is setting the `LOADER_PATH` environment variable or a `loader.properties` file; the official configuration syntax also supports `loader.home`, `loader.main`, and dedicated launcher properties. Do not mix up `loader.path` with `spring.config.location`: the former relates to the **Java classpath**, while the latter relates to **Spring Boot configuration files**.

### 9.2. Gradle: Selecting the Launcher via Manifest

In `build.gradle` with the Spring Boot Gradle Plugin, you can configure `bootJar` to use a different launcher when needed:

```groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Main-Class': 'org.springframework.boot.loader.launch.PropertiesLauncher'
    }
}
```

This is an **optional fragment** and should not be added to the default Gradle JAR example in Section 10 if you are studying `JarLauncher`. After changing it, always inspect the manifest and test running it. Do not set `Main-Class` to the application main class in a Boot JAR with nested `BOOT-INF`; doing so bypasses Boot Loader's responsibilities.

### 9.3. What `loader.path` Does Not Automatically Solve

- Does not automatically download dependencies from Maven Central.
- Does not verify compatibility/security of external JARs.
- Does not completely eliminate version conflicts if a class exists in both the nested archive and the external directory; classpath precedence becomes something you must manage.
- Does not fix a broken archive structure or missing `Start-Class`.
- Does not turn `JarLauncher` into `PropertiesLauncher` if the manifest was not changed.
- Should not be used to load arbitrary code from a location writable by unauthorized users.

Usually you should **package dependencies properly via the build tool** rather than using an external library path. Only use `PropertiesLauncher` when there is a suitable plugin/extensibility design.

## 10. Gradle: `bootJar` Generates the Manifest and Boot Classpath

In a Gradle project, the same Java and resource sources from Section 6 can use `settings.gradle`:

```groovy
rootProject.name = 'bootloader-demo'
```

and `build.gradle` (Groovy DSL):

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

springBoot {
    mainClass = 'dev.example.bootloader.BootLoaderDemoApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This configuration uses the Spring Boot Gradle Plugin + Dependency Management Plugin to pull the corresponding BOM; versions on starter dependencies can be omitted. `springBoot.mainClass` specifies the app main class; `bootJar` generates the executable archive with the appropriate `Start-Class` manifest entry.

**Choose one build tool per source project**. If you want to practice Gradle, use the two `settings.gradle`/`build.gradle` files instead of the POM, keeping the same `src/main`/`src/test` from Section 6.

With a compatible Gradle Wrapper already present:

```bash
./gradlew clean test bootJar jar
jar tf build/libs/bootloader-demo-1.0.0.jar
jar tf build/libs/bootloader-demo-1.0.0-plain.jar
java -jar build/libs/bootloader-demo-1.0.0.jar
```

Windows uses `gradlew.bat`. If there is no wrapper yet, you must generate/install a compatible Gradle version; do not assume `gradlew` exists in every project.

By convention when using Spring Boot Gradle Plugin 3.3:

- `bootJar` generates `build/libs/bootloader-demo-1.0.0.jar` containing the Boot loader, `BOOT-INF/classes`, and `BOOT-INF/lib`.
- `jar` generates the regular `build/libs/bootloader-demo-1.0.0-plain.jar` with application classes at the root and no nested runtime libraries.
- `bootRun` runs the app from the source-set runtime classpath, **without needing to open the executable JAR and read its manifest**. Hence succeeding with `./gradlew bootRun` does not prove the final JAR has the right manifest/layout.

If the project sets a custom classifier/name or uses a custom packaging task, names and layouts may differ. Inspect the contents and manifest of **the exact file intended for deployment**.

### Gradle Startup Manifest Check

You can extract the `bootJar` manifest just like with Maven:

```bash
unzip -p build/libs/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

The values to verify remain:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

If `Start-Class` is wrong, fix `springBoot.mainClass`/`bootJar.mainClass` in the Gradle configuration. Do not confuse `Main-Class` with the application class name when the archive still uses the nested JAR layout.

## 11. `classpath.idx` and `layers.idx`: How Do They Differ from the Manifest?

Spring Boot has two index files that may appear inside an executable archive. Distinguish them to avoid editing the wrong thing when a class is not found.

### 11.1. `BOOT-INF/classpath.idx`

This is the **classpath index**, representing the order of nested libraries for the loader to use in the manner supported by executable archives. Example illustrative index file:

```yaml
- "BOOT-INF/lib/spring-boot-3.3.13.jar"
- "BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar"
- "BOOT-INF/lib/spring-web-6.x.y.jar"
```

The `6.x.y` part merely denotes an illustrative version, **not a literal filename to copy into a real artifact**. The build plugin writes entries matching actual dependencies.

Spring Boot documentation states that the classpath index is used by the loader when the archive runs via **`java -jar`**, and does not apply the same way in an IDE, `mvn spring-boot:run`, or `./gradlew bootRun`. That is why resource/class lookup order when running from an IDE versus running the JAR can differ in edge-case dependency conflicts.

**Do not manually edit `classpath.idx` to "fix" a missing library**. First check whether `BOOT-INF/lib` actually contains the JAR, inspect the dependency graph, and check how the build plugin packages it. Editing the list without packaging the dependency into the archive will not conjure the library into existence.

### 11.2. `BOOT-INF/layers.idx`

This is the **layer index** that organizes components into container image layers, such as application, Boot Loader, dependencies, and snapshot-dependencies. It **does not decide `Start-Class`** and is not a Java `Class-Path` manifest attribute.

Conceptual example:

```text
dependencies layer      -> BOOT-INF/lib/...
spring-boot-loader      -> org/springframework/boot/loader/...
application layer       -> BOOT-INF/classes/...
```

When layers are used for OCI image caching, the actual classes/loading paths understood by Boot Loader must still be preserved. Do not change the manifest to point to a layer class.

## 12. ClassLoader Types and Limitations When Loading Nested JARs

Spring Boot Loader needs a classloader capable of resolving URLs/resources inside nested JARs. This is especially important for code/frameworks using reflection, `ServiceLoader`, or name-based resource loading.

### 12.1. Prefer the Thread Context Classloader

Illustrative Java snippet:

```java
ClassLoader appLoader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.fasterxml.jackson.databind.ObjectMapper",
                             false, appLoader);
```

**This is a fragment**, requiring appropriate context/source file and dependencies to run. `ProbeController` in Section 6 is the full version.

Do not blindly replace it with:

```java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
```

assuming the system classloader always sees every class in `BOOT-INF/lib`. With executable nested JARs, classes there are typically found through the classloader established by Boot. A third-party library hard-coding the system classloader might run fine in an IDE yet fail under `java -jar`.

If a specialized technology strictly requires the system classloader and cannot adapt, you may have to change the distribution/classpath model (exploded archive, external libraries, shaded JAR) or apply specialized configuration; do not pass `BOOT-INF/lib/...jar` paths to `java -cp` without understanding nested archive semantics.

### 12.2. ZIP Entry Rules and Building with Standard Tools

To access nested JARs directly without extracting every library to disk, Boot imposes requirements on how inner JAR entries are stored in the outer archive. Specifically, **nested JAR entries must use the `ZipEntry.STORED` method**; data *inside* the inner JAR may still be compressed.

Therefore, a standard ZIP tool might still list `BOOT-INF/lib/foo.jar` while inadvertently recompressing the outer entry with a different method, making Boot Loader unable to access it as designed. Use `spring-boot:repackage` or `bootJar` and avoid manually "re-zipping to shrink" the release JAR.

### 12.3. Duplicate Classes and Resources

If two nested libraries contain the same class name or service file, the outcome depends on dependency resolution, classpath order, and resource loading mechanisms. Boot does not guarantee that the newest version always wins or that two identically named classes can safely coexist.

**Check the actual source of conflicts:**

```bash
mvn dependency:tree
# Or Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

After fixing dependency versions/exclusions, do a clean build and inspect `BOOT-INF/lib`. If an issue only appears in the executable archive, examine classloader assumptions alongside the classpath index and differences between packaged runs and IDE runs.

## 13. Right Way to Pass JVM Options, Spring Arguments, and External Paths

A single `java` command has multiple option "zones", and not all of them alter the classpath:

```bash
java -Xmx512m -Duser.timezone=UTC \
     -jar target/bootloader-demo-1.0.0.jar \
     --server.port=8081 --spring.profiles.active=dev
```

Breakdown:

- `-Xmx512m` and `-Duser.timezone=UTC`: **JVM options**, placed before `-jar`.
- `-jar target/...jar`: Java reads `Main-Class`, invokes Boot Loader.
- `--server.port=8081` and `--spring.profiles.active=dev`: **application args** forwarded by the loader to Spring Boot's main, then processed by Spring.
- None of the above automatically modifies `BOOT-INF/lib` or adds an external JAR to the classpath.

Classification table:

| Action | Primary handling layer | Effect |
| --- | --- | --- |
| `java -jar app.jar` | Java launcher → Boot Loader | Picks bootstrap entry from manifest, builds classpath, invokes app main |
| `java -cp "app.jar:lib/*" app.Main` | Traditional Java launcher | Runs class directly from user-specified classpath |
| `java -Dfoo=bar -jar app.jar` | JVM system properties | Passes system property to JVM/application, does not alter manifest |
| `java -jar app.jar --spring.profiles.active=dev` | Spring Boot application args | Selects Spring profile after entering application |
| `java -Dloader.path=extra -jar app.jar` | `PropertiesLauncher` (if used in manifest) | Adds external library paths when supported by the launcher |
| `mvn -Pci package` | Maven | Activates a **Maven profile**; does not automatically alter active Spring profile |
| `mvn spring-boot:run` | Boot Maven Plugin | Runs from project classpath, not equivalent to `java -jar` |
| `./gradlew bootRun` | Boot Gradle Plugin | Runs from source set runtime classpath, does not need bootJar manifest |

**Warning:** `java -jar app.jar -Dfoo=bar` puts `-Dfoo=bar` after `app.jar`, making it an **application argument string**, not a JVM `-D` property. JVM options must come before `-jar`.

## 14. Diagnosing Errors at the Right Link in the Chain

| Symptom | Where it may be broken | How to verify/fix |
| --- | --- | --- |
| `no main manifest attribute` | Manifest missing `Main-Class` | Read `META-INF/MANIFEST.MF`; verify whether file is a Boot JAR from repackage/bootJar |
| `Could not find or load main class ...JarLauncher` | `Main-Class` name right, but Boot loader classes missing/misplaced at root | `jar tf` looking for `org/springframework/boot/loader/launch/JarLauncher.class`; rebuild with Boot plugin |
| Boot loader runs but cannot find `Start-Class` | Wrong `Start-Class`, app main renamed or not compiled/packaged | Compare manifest with `BOOT-INF/classes/...class` and mainClass configuration |
| `java -cp app.jar app.Main` cannot find app class | App resides under `BOOT-INF/classes`, not root | Use `java -jar` on Boot JAR; if `-cp` is desired, use plain JAR with external dependencies |
| `NoClassDefFoundError: org/springframework/...` after packaging | `BOOT-INF/lib` missing dependency or excluded by scope | Check `jar tf` and Maven/Gradle runtime graph; fix build model |
| Jackson/Web dependency loads in IDE but not in JAR | Source run and packaged run have different classpaths | Compare `spring-boot:run`/`bootRun` against `BOOT-INF/lib`; rebuild/re-inspect |
| Set `-Dloader.path=external-libs` yet class does not appear | Using `JarLauncher` instead of `PropertiesLauncher`, or wrong library path | Inspect `Main-Class`, check location and actual JARs |
| Fails when using `ClassLoader.getSystemClassLoader()` | System loader cannot see nested libraries | Try thread context classloader per Spring Boot loader contract |
| `jar tf` still shows nested JAR yet startup fails after re-zipping | Wrong compression method/metadata on outer JAR | Do not re-zip manually; rebuild with `repackage`/`bootJar` |
| `Start-Class` changed unexpectedly | Multiple main classes or differing plugin config between local/CI | Pin mainClass in Boot Maven/Gradle plugin; inspect release artifact manifest |
| `java -jar` runs yet app does not bind `application-prod.yml` | Wrong Spring profile/config, not a launcher error | Check Spring config sources/`spring.profiles.active` after main starts |
| `UnsupportedClassVersionError` | Runtime JDK lower than bytecode version | Check `java -version`, Maven Compiler/Gradle Java toolchain |
| `ClassNotFoundException` due to duplicate dependency versions | Wrong dependency graph or classpath order | `dependency:tree`/`dependencyInsight`, check `BOOT-INF/lib` and `classpath.idx` |
| Internal library published as a Boot JAR and consuming module cannot see classes | Library classes sit under `BOOT-INF/classes` | Publish a plain JAR or split library module; executable Boot JAR does not replace normal library JAR |
| Container build alters JAR contents after QA | Artifact identity not preserved | Publish/deploy the exact tested checksum/digest; scan artifact inside image |

### Priority Investigation Workflow

1. **Get the exact command executed** (`java -jar`, `java -cp`, `bootRun`, or `spring-boot:run`).
2. **Identify the exact artifact**: module, version, classifier, and actual deployed file path.
3. **Inspect the manifest**: does `Main-Class` have the right launcher? Does `Start-Class` have the right app main?
4. **Inspect archive entries**: are Boot loader classes, `BOOT-INF/classes`, and `BOOT-INF/lib` intact?
5. **Inspect the dependency graph**: were required artifacts resolved and packaged?
6. **Run a smoke test on the executable JAR itself**: use `java -jar`, hit an endpoint; read the first root cause in the stack trace.
7. **Handle classloader-specific issues**: check `Thread.currentThread().getContextClassLoader()`, classpath index, and external paths if any.
8. **Rebuild, test, and re-verify**: fix the build config/POM rather than manually patching the manifest or release ZIP file.

## 15. Reinforcement Exercises

**Exercise 1.** A Spring Boot JAR manifest has `Main-Class: org.springframework.boot.loader.launch.JarLauncher` and `Start-Class: dev.example.bootloader.BootLoaderDemoApplication`. Which class's main method does the JVM invoke directly?

*Answer:* The JVM uses `Main-Class` to invoke `JarLauncher` first. After setting up the appropriate classpath, Boot Loader invokes `BootLoaderDemoApplication`'s main per `Start-Class`.

**Exercise 2.** A JAR contains app classes in `BOOT-INF/classes` and Spring libs in `BOOT-INF/lib`. Will running `java -cp app.jar dev.example.bootloader.BootLoaderDemoApplication` work automatically?

*Answer:* Not under standard classpath rules. Java treats the JAR as a classpath root, does not automatically treat `BOOT-INF/classes` as a root, and does not automatically load nested JARs. Use `java -jar` with Boot Loader, or construct a valid classpath/exploded distribution.

**Exercise 3.** Someone edits only the manifest to `Main-Class: dev.example.bootloader.BootLoaderDemoApplication` on a Boot JAR that already has `BOOT-INF`. Why will this likely fail?

*Answer:* They bypassed `JarLauncher`, the component that sets up the classpath for app classes and nested dependencies. Update `mainClass` in the Spring Boot plugin if you want to change the application entry point, instead of replacing the Boot launcher with the app class.

**Exercise 4.** Why doesn't adding `Class-Path: BOOT-INF/lib/spring-web.jar` to the manifest normally replace `JarLauncher`?

*Answer:* Java's standard manifest `Class-Path` does not automatically resolve nested archive entries inside a Boot JAR in Boot's format. A loader that understands the layout/nested JARs is needed; real JAR names also include versions, and there are usually more than one lib.

**Exercise 5.** The app runs fine in the IDE, yet the packaged JAR is missing `ObjectMapper`. Where do you check first?

*Answer:* Inspect `BOOT-INF/lib` of the exact post-build JAR and the dependency graph/runtime scope. IDE tests use a different classpath than the release archive, so they cannot substitute for archive inspection.

**Exercise 6.** Does `LOADER_PATH` always work with `JarLauncher`?

*Answer:* No. That is a capability of `PropertiesLauncher`. You must configure the manifest/layout to use that launcher and verify the external library path.

**Exercise 7.** Can `BOOT-INF/layers.idx` replace `Start-Class` to change the main method?

*Answer:* No. `layers.idx` describes archive layering for container caching; `Start-Class` lives in the manifest and is used by Boot Loader to identify the application main class.

**Exercise 8.** An outer JAR has nested `BOOT-INF/lib/foo.jar`, yet a ZIP tool recompressed the outer entry with the wrong method. Could Boot Loader still fail even if `jar tf` lists the file?

*Answer:* Yes. Spring Boot Loader has requirements on the ZIP entry method of nested JARs; rebuild with the official plugin instead of re-zipping manually.

**Exercise 9.** Does reading `Start-Class` in the manifest guarantee the application will start successfully?

*Answer:* No. It only states which main class the application intends to call. You also need the loader class, compiled app, all runtime dependencies, Java runtime, and valid configuration; run `java -jar` and smoke test it.

**Exercise 10.** Why is `ProbeControllerTest` in Section 6 insufficient to prove `JarLauncher` ran properly?

*Answer:* The test runner uses Maven/Gradle's test classpath rather than opening the executable archive like `java -jar`. You must inspect the artifact's manifest/`BOOT-INF` and actually run it.

## 16. Pre-Release Checklist for Spring Boot Executable JARs

- **Right artifact:** the deployed file is the output of `spring-boot:repackage` or `bootJar`, not a plain/library JAR, `.jar.original`, or `-plain.jar`.
- **Right manifest:** `Main-Class` is the launcher matching the layout, and `Start-Class` points to the application class with `public static void main(String[])`.
- **Complete loader:** `JarLauncher`/`WarLauncher`/`PropertiesLauncher` classes are present where the Java launcher can load them.
- **Right app classes/resources:** `BOOT-INF/classes` contains compiled application classes and resources, including those read by code via the classpath.
- **Right runtime libs:** `BOOT-INF/lib` contains the exact set of dependencies from the runtime graph; no accidental duplicates/conflicts.
- **No re-zipping breaking nested archives:** build with the appropriate plugin and preserve ZIP entry semantics.
- **Right classpath strategy:** use `JarLauncher` for standard Boot JARs; only use `PropertiesLauncher` and `loader.path` when controlled external jars are needed.
- **Arguments in right positions:** JVM `-D` before `-jar`; Spring `--...` after the JAR; `-cp` does not replace the nested launcher.
- **Compatible JDK:** target runtime supports the project's bytecode (examples use Java 17).
- **Smoke test the actual artifact:** run `java -jar` on the release output, verify endpoints/health, and inspect startup classpath errors.
- **CI publishes the verified artifact:** record checksum/digest and do not rebuild with different rules at deployment time.

**Conclusion:** A Spring Boot executable JAR works because **the manifest points to Boot Loader, Boot Loader builds the classpath from application classes and nested dependencies, and only then invokes the application's `Start-Class`**. Confusing these three roles is a common root cause of "JAR built fine but `java -jar` won't run". Always verify **manifest + loader class + archive layout + runtime classpath + smoke test**, rather than relying solely on the filename or a green build status.

### Official Documentation for Reference

- Spring Boot 3.3 — Executable JAR, Launching Executable Jars: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html
- Spring Boot 3.3 — Executable JAR, Nested JARs: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — PropertiesLauncher Features: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/property-launcher.html
- Spring Boot 3.3 — Executable JAR Restrictions: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — JarLauncher API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/JarLauncher.html
- Oracle Java 17 — Java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
