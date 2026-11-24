# Choosing JAR, WAR, ZIP, or NONE Layout in the Spring Boot Maven Plugin

## 1. What problem does this lesson solve?

A Spring Boot application can be built with Maven into several archive formats. When reading `pom.xml`, learners often encounter `<packaging>jar</packaging>`, `<packaging>war</packaging>`, or `spring-boot-maven-plugin` configurations with `<layout>JAR</layout>`, `<layout>WAR</layout>`, `<layout>ZIP</layout>`, and `<layout>NONE</layout>`. Similar names easily lead to a misconception: **"`packaging` and `layout` are the same setting."**

In reality, they handle two different layers of responsibility:

- **Maven `packaging`** determines the artifact type and lifecycle producing the initial archive (for example, JAR or WAR).
- **Spring Boot Maven Plugin `layout`** determines **how classes, dependencies, and the launcher are arranged inside the archive** when the `spring-boot:repackage` goal processes the artifact.

Therefore, changing `layout` is not a general way to change a file extension, turn a JAR into a Tomcat-deployable WAR, or produce an unpacked `.zip` folder on the filesystem.

After this lesson, you will:

1. Distinguish `packaging`, `layout`, `classifier`, `finalName`, and Spring Boot layers.
2. Choose between `JAR`, `WAR`, `ZIP`/`DIR`, and `NONE` based on **how the application will be launched or consumed**.
3. Understand the roles of `JarLauncher`, `WarLauncher`, `PropertiesLauncher`, and why `NONE` has no bootstrap loader.
4. Write POMs and Java 17+ code for a `JAR` app, a `ZIP` variant, a `WAR` app, and a `NONE` configuration for comparison.
5. Inspect repackaged archives via `jar tf`, manifests, and a standard Java `JarFile` utility.
6. Avoid mistakes like picking the wrong artifact, targeting the wrong servlet container, missing runtime dependencies, or assuming `ZIP` means a `.zip` file extension.

**Example version convention:** Java `17`, Spring Boot `3.3.5`, compatible Maven 3.x. These values form a reproducible example set, not a promise that they are the latest releases. When practicing on Spring Boot 4.x or different Maven/plugin versions, check the docs for your actual version—especially launcher names and servlet container requirements.

## 2. Distinguishing five easily confused concepts

| Concept | Where is it configured? | What does it actually control? |
| --- | --- | --- |
| `packaging` | `<project><packaging>jar/war</packaging>` | Maven lifecycle and the **source archive type** packaged by plugins |
| `layout` | `spring-boot-maven-plugin <configuration>` | Arrangement of classes, dependencies, and bootstrap loader after `repackage` |
| `mainClass` | Spring Boot Maven Plugin | Application main class, typically written to `Start-Class` in the executable archive |
| `finalName` | `<build><finalName>...` | Local archive filename; does not change Maven GAV (`groupId:artifactId:version`) |
| `classifier` | `repackage` goal configuration | Creates/attaches an archive variant, e.g., main artifact and `-exec.jar` |

Another set of concepts also needs separation:

- **Spring Boot `layers`**: metadata and layer partitioning for OCI image optimization; **not** a value of `layout`.
- **Spring Boot Maven Plugin `<executable>true</executable>`**: mechanism that prepends a launch script to the archive for shell-like execution on supported systems; **not** equivalent to `layout=ZIP`.
- **`outputDirectory`** or `project.build.directory`: path where build outputs are written; **does not** choose which loader is embedded.
- **`ZIP`** (layout enum) differs from an **ordinary ZIP file**: a Java JAR already uses the ZIP file format; Spring Boot's `ZIP` layout specifically refers to using `PropertiesLauncher`.
- **`NONE`** is not synonymous with `skip repackage`: it can still bundle dependencies into the archive while **not embedding a bootstrap loader**; `<skip>true</skip>` skips the repackage goal entirely.

## 3. Quick selection table: JAR, WAR, ZIP/DIR, or NONE?

| Layout | Typical intent | Internal paths | Spring Boot launcher | `java -jar`? |
| --- | --- | --- | --- | --- |
| `JAR` | Standard standalone app, CLI, web service with embedded server | `BOOT-INF/classes`, `BOOT-INF/lib` | `JarLauncher` | Yes, when configured properly |
| `WAR` | Executable WAR, optionally also targeting an external servlet container | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | `WarLauncher` | Yes for properly built executable WARs |
| `ZIP` | Needs flexible classpath managed by `PropertiesLauncher`, e.g., adding external libraries | Similar to JAR layout, including `BOOT-INF` | `PropertiesLauncher` | Yes, when configured properly |
| `DIR` | Alias for `ZIP` per Spring Boot Maven Plugin docs | Same as `ZIP` | `PropertiesLauncher` | Same as `ZIP` |
| `NONE` | Bundles dependencies and resources for another system to consume/launch on its own | Layout without Boot bootstrap loader | **No Boot launcher** | **Not** a default Boot executable archive |

For **most standalone Spring Boot applications**, **keeping the default layout** is the simplest and best-supported choice: Maven `jar` normally defaults to `JAR`, and Maven `war` normally defaults to `WAR`. Switch to `ZIP` only when you genuinely need launcher classpath flexibility; use `NONE` when you **intentionally do not want** a Boot bootstrap loader and know how the consumer loads dependencies.

**WAR note:** `layout` sets the archive structure, yet running a WAR in **external Tomcat** also requires matching Servlet/Jakarta APIs, Spring Boot servlet initialization, and proper dependency scopes. You cannot simply change `layout` from `JAR` to `WAR` and expect the archive to deploy to any servlet container.

### 3.1. What does "Executable" mean here?

A Spring Boot **executable** archive contains the launcher and manifest needed for `java -jar` to load both application classes and nested dependencies without assembling a manual classpath. This differs completely from an ordinary JAR that only sets `Main-Class` while missing runtime dependencies.

In Spring Boot 3.3, under the standard JAR layout, the manifest typically contains:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

`Main-Class` is the bootstrap class called first by the JVM; `Start-Class` is the application's entry point. With `WAR` and `ZIP`, `Main-Class` changes to the corresponding launcher. `NONE` includes no bootstrap loader, so **do not expect to test it with `java -jar`** the way you test `JAR`/`WAR`/`ZIP`.

## 4. What does Spring Boot `repackage` do in Maven?

For a standard Maven jar project, the typical build flow is:

~~~text
pom.xml + src/main/java + src/main/resources
                    |
                    v
               mvn package
                    |
                    v
            Maven jar:jar / war:war
                    |
                    v
             Standard archive
                    |
                    v
     spring-boot-maven-plugin:repackage
                    |
                    v
          Archive with Boot layout
                    |
                    v
           Inspect + smoke test
~~~

The `spring-boot:repackage` goal operates on the **already-built archive** (JAR or WAR) and arranges application classes, dependencies, and the matching loader according to `layout`. When inheriting `spring-boot-starter-parent` and declaring `spring-boot-maven-plugin` in `<build><plugins>`, the `repackage` execution is managed by the parent and typically runs during `package`.

In a POM **not using the Boot parent**, you must specify the plugin version and bind the `repackage` goal execution, or run the goal explicitly **after** `package`. Example snippet:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <layout>JAR</layout>
        <mainClass>demo.Application</mainClass>
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

This snippet is **not** a standalone runnable POM; you still need Spring Boot dependencies, compatible compiler/JDK settings, and the application main class. If the goal is not bound, you can run `mvn package spring-boot:repackage` so the archive exists before repackaging; never run `mvn spring-boot:repackage` alone right after `clean` expecting it to compile and package from scratch.

**Why does the plugin need a nested JAR layout?** Standard JVM `java -jar` reads an archive's manifest/classpath, but cannot automatically load JARs stored as ZIP entries inside another JAR. The Spring Boot launcher implements nested-archive class loading so an application can run as a single executable JAR. `JarLauncher` and `WarLauncher` use fixed library lookup paths, whereas `PropertiesLauncher` supports broader classpath configuration.

## 5. `JAR` layout: standard choice for self-contained apps

### 5.1. Structure and manifest

A Spring Boot 3.3 executable JAR typically has this layout:

~~~text
app.jar
  META-INF/MANIFEST.MF
  org/springframework/boot/loader/...   (bootstrap classes)
  BOOT-INF/classes/...                  (application classes/resources)
  BOOT-INF/lib/*.jar                    (runtime dependencies)
~~~

`JarLauncher` looks for classes and libraries in `BOOT-INF/classes` and `BOOT-INF/lib`. The app's Java main class lives in `BOOT-INF/classes`, while the manifest `Main-Class` points to the Boot launcher rather than the app class.

### 5.2. Complete `JAR` hands-on exercise (Java 17 + Maven)

Structure:

~~~text
layout-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          Application.java
~~~

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>example.learning</groupId>
    <artifactId>layout-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.Application</mainClass>
                    <layout>JAR</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`<packaging>jar</packaging>` instructs Maven to build a JAR; `<layout>JAR</layout>` specifies how to repackage it. In standard projects, you can **omit `<layout>JAR</layout>`** so the plugin infers it from `packaging`, avoiding redundant config. It is written explicitly here to highlight the distinction.

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("layout-demo:ok");
    }
}
~~~

This is a command-line Spring Boot program without `spring-boot-starter-web`, so it opens no HTTP server and normally exits once the runner finishes.

Build and run from the directory containing `pom.xml`:

~~~bash
mvn clean package
java -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If Maven is not installed globally but the project includes a Maven Wrapper, run `./mvnw clean package` on Linux/macOS or `.\mvnw.cmd clean package` in PowerShell. For output from **the `System.out.println` inside our application**, the result line is:

~~~text
layout-demo:ok
~~~

Maven emits its own build logs; this command passes flags disabling the Spring Boot banner/logs to focus on program stdout. JVM or external environment messages are not part of that line.

Inspect ZIP entries:

~~~bash
jar tf target/layout-demo-1.0.0.jar
~~~

You should see `META-INF/MANIFEST.MF`, `BOOT-INF/classes/demo/Application.class`, `BOOT-INF/lib/*.jar` entries, and Boot loader classes. This verifies the JAR was actually **repackaged**, rather than just seeing a file named `layout-demo-1.0.0.jar`.

### 5.3. When to choose `JAR`?

Choose the `JAR` layout when:

- Deploying a Java process run via `java -jar` or packaging an executable JAR inside a Docker/OCI image.
- You do not need to modify the classpath outside the archive via `PropertiesLauncher`.
- You want minimal configuration, convention over configuration, and smooth tooling support across Maven, CI, and Spring Boot.
- Building CLIs, workers, or web services carrying an embedded server.

**Do not change `layout` just because "the JAR filename must be fixed."** Archive filenames belong to `<build><finalName>`; `layout` does not control the filename.

## 6. `ZIP`/`DIR` layout: using `PropertiesLauncher` for a flexible classpath

### 6.1. `ZIP` does not mean changing the extension to `.zip`

In the Spring Boot Maven Plugin, `ZIP` is a `layout` name; documentation confirms **`DIR` is an alias for `ZIP`**. This layout organizes application classes and dependencies similarly to `JAR`, but uses `PropertiesLauncher` as the bootstrapper.

If the Maven project keeps `<packaging>jar</packaging>`, the output file is **still `.jar`**, e.g. `target/layout-demo-1.0.0.jar`. `ZIP` **does not** produce `layout-demo.zip` or extract into a directory. `DIR` likewise does not turn output from a file into an on-disk directory.

In Spring Boot 3.3, `Main-Class` for the `ZIP` layout is typically:

~~~text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: demo.Application
~~~

To verify, read the manifest **of the actual file**. Do not guess from `pom.xml`, as `layout` could be overridden in effective plugin configuration.

### 6.2. Switching the `JAR` example to `ZIP`

Keep `pom.xml` and `Application.java` from section 5 intact, **modifying only** `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <layout>ZIP</layout>
</configuration>
~~~

Re-run:

~~~bash
mvn clean package
java -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

The line printed by the application remains:

~~~text
layout-demo:ok
~~~

What changed is the **embedded launcher** and the ability to configure the loader classpath—not the `CommandLineRunner` logic. Using `<layout>DIR</layout>` instead of `ZIP` produces the equivalent layout per documentation.

### 6.3. `loader.path` and external libraries outside the archive

`PropertiesLauncher` can load extra directories or archives via the `loader.path` property or `LOADER_PATH` environment variable. For instance, in an environment where you **explicitly create an `external-libs` directory containing approved JARs**:

~~~bash
java -Dloader.path=external-libs -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

`-Dloader.path=...` is a **JVM system property** and must appear **before `-jar`**. Spring arguments like `--spring.main.banner-mode=off` go after the JAR path so the application receives them. `loader.path` can hold multiple comma-separated entries per launcher syntax. It is not `spring.config.location` and not equivalent to the shell `-cp` flag.

**The example above only illustrates how to pass a loader path; it does not automatically populate `external-libs`**. If the directory is empty, that does not prove the launcher actually loaded a new library; to test an extension, you need an extra JAR and real code using it. Never treat an external classpath as a place to "drop random newer JAR versions" into production: it can alter classloading order, break binary compatibility, undermine reproducibility, and introduce security risks.

In Spring Boot documentation, `PropertiesLauncher` supports additional settings such as `loader.home`, `loader.config.name`/`loader.config.location`, `loader.main`, and `loader.path`. How `loader.properties` is discovered and precedence across system properties, environment variables, and manifest headers depend on the version; consult docs for your Boot version, especially when automating deployments.

### 6.4. When is `ZIP`/`DIR` useful, and when is it not?

**Useful** when you have a legitimate need for an extensible classpath: an organized runtime plugin mechanism, externally managed libraries governed by versions/checksums, or operations tooling built around `PropertiesLauncher`. Even then, this choice **does not automatically create a safe plugin architecture**; you still need API contracts, isolation, versioning, and compatibility tests.

**Unnecessary** if your application just bundles its dependencies and runs as a standalone process. The default `JAR` layout is simpler, has fewer misinterpretable knobs, and keeps deployment pipelines clear.

## 7. `WAR` layout: executable WAR and external servlet containers

### 7.1. Why is `WAR` different from `JAR`?

A Spring Boot executable `WAR` typically has this layout:

~~~text
app.war
  META-INF/MANIFEST.MF
  org/springframework/boot/loader/...
  WEB-INF/classes/...             (application classes/resources)
  WEB-INF/lib/*.jar               (runtime dependencies)
  WEB-INF/lib-provided/*.jar      (provided dependencies)
~~~

`WarLauncher` knows to load `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` when running the executable WAR via `java -jar`. `provided` dependencies are separated so they do not clash with libraries supplied by an **external servlet container** during traditional WAR deployment.

However, **Maven `packaging` and Spring Boot `layout` must match the format**: to build a WAR, set `<packaging>war</packaging>`, ensure the Maven WAR Plugin participates in the lifecycle, and let Spring Boot `repackage` apply the WAR layout. Never change only `<layout>WAR</layout>` in a JAR project and claim you have a valid deployable WAR.

### 7.2. Complete illustrative `WAR` POM

Create a **separate** project `war-layout-demo` (do not overwrite the previous JAR POM). `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>example.learning</groupId>
    <artifactId>war-layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.WarApplication</mainClass>
                    <layout>WAR</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Here `spring-boot-starter-web` pulls in Tomcat transitively; **explicitly declaring** `spring-boot-starter-tomcat` with `scope=provided` tells Maven/Spring Boot that the container dependency should not sit on the regular WAR runtime classpath when deployed to an external servlet container. In the executable WAR, it can still reside in `WEB-INF/lib-provided` for `WarLauncher` when running via `java -jar`.

Boot 3.3 uses Jakarta Servlet APIs; to deploy to an external servlet container, pick a container **compatible with the exact Boot/Jakarta version**—do not pick Tomcat 9 (`javax.servlet`) for Boot 3.x. With an external container, container classloading, dependency policies, and server config can still affect execution.

### 7.3. WAR application with `SpringBootServletInitializer`

Structure:

~~~text
war-layout-demo/
  pom.xml
  src/main/java/demo/WarApplication.java
~~~

Create `src/main/java/demo/WarApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WarApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(WarApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarApplication.class);
    }

    @GetMapping(value = "/probe", produces = "text/plain")
    public String probe() {
        return "war-layout-ok";
    }
}
~~~

`main` serves the **executable WAR** when run via `java -jar`, while `SpringBootServletInitializer` configures the entry point for an **external servlet container**. Never rely on `<layout>WAR</layout>` alone as a substitute for the initializer class when targeting a traditional servlet container deployment.

### 7.4. Build, run, and verify the WAR

From the `war-layout-demo` project:

~~~bash
mvn clean package
jar tf target/war-layout-demo-1.0.0.war
~~~

You will see paths like `WEB-INF/classes/demo/WarApplication.class`, `WEB-INF/lib/`, and `WEB-INF/lib-provided/`, plus loader classes. If `unzip` is available, inspect the manifest:

~~~bash
unzip -p target/war-layout-demo-1.0.0.war META-INF/MANIFEST.MF
~~~

With Boot 3.3's WAR layout, `Main-Class` is normally `org.springframework.boot.loader.launch.WarLauncher` and `Start-Class` is `demo.WarApplication`.

In terminal one, run the executable WAR with the embedded server:

~~~bash
java -jar target/war-layout-demo-1.0.0.war --server.address=127.0.0.1 --server.port=8087
~~~

In terminal two, once startup completes:

~~~bash
curl -fsS http://127.0.0.1:8087/probe
~~~

Exact **HTTP body**:

~~~text
war-layout-ok
~~~

`curl` may omit a trailing newline after the body. When finished, stop the Java process in terminal one (e.g., `Ctrl+C`) to free the port. In CI, manage process lifecycle, timeouts, and cleanup automatically instead of relying on two terminals waiting indefinitely.

**External container deployment is a separate test:** deploy the WAR to a compatible container; its context path may come from the WAR filename or container config, so `/probe` might not live at root. Verify inside the real container rather than assuming `java -jar` PASS implies external deploy PASS.

### 7.5. When to choose `WAR`?

Choose `WAR` when operations truly require **WAR deployment into an external Servlet container**, or when bound by a specific WAR release contract. If running Spring Boot as a standalone service with no external container, `JAR` is usually simpler.

Do not pick `WAR` just to "have nested dependencies"; an executable JAR also has `BOOT-INF/lib`. Nor should you rename `.jar` to `.war` via `finalName` to fake a WAR: both archive format and Maven lifecycle must match.

## 8. `NONE` layout: bundle dependencies without embedding a launcher

### 8.1. `NONE` is not `skip`

`NONE` is a special layout of `spring-boot:repackage`. Per Spring Boot docs, it **packages dependencies and project resources** while **omitting the bootstrap loader**. Lacking the loader required for nested dependencies, it **is not considered a standard Spring Boot executable archive for `java -jar`**.

Comparison:

| Configuration | Does `repackage` run? | Boot bootstrap loader embedded? | Meaning |
| --- | --- | --- | --- |
| `layout=JAR` | Yes | Yes | Boot executable JAR |
| `layout=WAR` | Yes | Yes | Boot executable WAR |
| `layout=ZIP` | Yes | Yes (`PropertiesLauncher`) | Boot executable with flexible classpath |
| `layout=NONE` | Yes | **No** | Archive holding project/dependencies for a specialized consumer |
| `skip=true` | No | Not added by this goal | Keeps artifact from the preceding Maven packaging step |

If you manually set `Main-Class` via another plugin, a `NONE` archive **may** still have a different manifest entry, yet that does not turn it into an executable Boot archive: Java still needs an appropriate classpath or launcher to locate dependencies. Do not claim as an absolute rule that "every `NONE` file has no manifest"; the guaranteed rule is that **Spring Boot adds no bootstrap loader for `NONE`**.

### 8.2. Configuration variant on the `JAR` example

Starting from `layout-demo` in section 5, change only the plugin configuration to:

~~~xml
<configuration>
    <layout>NONE</layout>
</configuration>
~~~

You may omit `mainClass` because the goal now is **not** building an executable archive with a Boot launcher. Run:

~~~bash
mvn clean package
jar tf target/layout-demo-1.0.0.jar
~~~

Inspect actual contents: project classes/resources and repackaged dependencies follow the structure generated by your current plugin and version. **Do not assume** a fixed layout like `BOOT-INF/lib` for `NONE` without inspecting it; the defining trait is that the file **has no bootstrap loader**.

**Do not treat `java -jar target/layout-demo-1.0.0.jar` as a required PASS check for `NONE`.** Failing to self-boot matches `NONE`'s design. If a downstream system needs to run code inside, that system must know how to load classes/libraries or provide its own bootstrap mechanism.

### 8.3. When does `NONE` make sense?

- A custom distribution platform wants an archive holding dependencies **without** the Spring Boot launcher.
- An external tool parses, extracts, or repackages classes and libraries under an established protocol.
- The runtime architecture already manages bootstrapping and classpath resolution outside the archive.

**Do not use `NONE` to "make the JAR lighter" on intuition.** Nested dependencies can still be bundled in the archive; `NONE` does not mean a thin JAR containing only application classes. If you want a standard library JAR for other projects to depend on, revisit **whether that module should be repackaged at all**, and check Maven main artifact/classifier/attach settings so dependency consumers get the proper format.

## 9. Verifying layout via manifest and file entries

Never read `<layout>` alone and declare the archive valid. A reliable verification procedure:

1. `mvn clean package` from the **exact module**.
2. Inspect the generated artifact filename and actual extension.
3. Run `jar tf` to check class/library paths matching the layout.
4. Read `META-INF/MANIFEST.MF`, specifically `Main-Class` and `Start-Class`.
5. If the layout includes a loader, **run the actual archive** with `java -jar` and verify output or endpoints.
6. If the layout is `NONE`, **verify the absence of a loader** rather than expecting `java -jar` to boot.
7. If the final deliverable is an externally deployed WAR or Docker image, also verify that final runtime artifact directly.

### 9.1. Inspect with the JDK without unzipping

Java 17 includes `java.util.jar.JarFile`, which reads both `.jar` and `.war` files as ZIP-compatible archives. Create a standalone file `InspectLayout.java`:

~~~java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectLayout {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java InspectLayout.java <archive-path>");
        }

        Path archive = Path.of(args[0]);
        try (JarFile file = new JarFile(archive.toFile())) {
            Manifest manifest = file.getManifest();
            Attributes attrs = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            String main = attrs.getValue("Main-Class");
            String start = attrs.getValue("Start-Class");

            boolean bootClasses = file.stream().anyMatch(
                    e -> e.getName().startsWith("BOOT-INF/classes/"));
            boolean bootLibs = file.stream().anyMatch(
                    e -> e.getName().startsWith("BOOT-INF/lib/"));
            boolean warClasses = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/classes/"));
            boolean warLibs = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib/"));
            boolean warProvided = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib-provided/"));
            boolean bootLoader = file.stream().anyMatch(
                    e -> e.getName().startsWith(
                            "org/springframework/boot/loader/"));

            System.out.println("main=" + main);
            System.out.println("start=" + start);
            System.out.println("boot.classes=" + bootClasses);
            System.out.println("boot.libs=" + bootLibs);
            System.out.println("war.classes=" + warClasses);
            System.out.println("war.libs=" + warLibs);
            System.out.println("war.provided=" + warProvided);
            System.out.println("boot.loader=" + bootLoader);
        }
    }
}
~~~

This is a **standalone** Java source-file launcher program requiring no Maven dependencies. Run from the directory containing the file:

~~~bash
java InspectLayout.java target/layout-demo-1.0.0.jar
~~~

For the **`JAR` layout of section 5's example**, program output will report key values such as:

~~~text
main=org.springframework.boot.loader.launch.JarLauncher
start=demo.Application
boot.classes=true
boot.libs=true
war.classes=false
war.libs=false
war.provided=false
boot.loader=true
~~~

These values are **expected specifically for this Spring Boot 3.3.5 example after repackage**, not defaults for every JAR in existence. Switching to `ZIP` primarily changes `main` to `org.springframework.boot.loader.launch.PropertiesLauncher`. Inspecting the WAR typically gives `war.classes=true` and `war.libs=true`, plus `war.provided=true` when `provided` dependencies exist. For `NONE`, `boot.loader` is expected to be `false`.

**Do not infer layout from a single boolean.** This code reports structure and manifest headers only. Testing with `java -jar` or deploying to an external servlet container is still required to confirm actual execution.

### 9.2. Inspecting the manifest via CLI when `unzip` is available

Linux/macOS with `unzip`:

~~~bash
unzip -p target/layout-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Windows PowerShell can use `jar xf` inside a temporary folder or Java `InspectLayout.java` as above. Never assume `unzip` is preinstalled on every Windows machine.

If the manifest shows:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

that indicates the `JAR` layout with Spring Boot 3.3's launcher. If it shows:

~~~text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: demo.Application
~~~

that indicates the `ZIP`/`DIR` layout. For `WAR`, the launcher is typically `WarLauncher`. **Never manually edit `Main-Class` with `maven-jar-plugin` to "switch layouts"**; the Spring Boot plugin manages the manifest according to the loader and archive layout, so the proper way is configuring `layout` and `mainClass` when genuinely needed.

## 10. Classifier, attach, and the risk of deploying the wrong JAR

A proper layout can still be tested incorrectly if a pipeline picks the wrong artifact. For example, when the Maven plugin configures:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <layout>JAR</layout>
    <classifier>exec</classifier>
</configuration>
~~~

Spring Boot can create and attach an executable artifact with classifier `exec` alongside the ordinary main archive. Local filenames in the example project become:

~~~text
target/layout-demo-1.0.0.jar
target/layout-demo-1.0.0-exec.jar
~~~

Here `-exec.jar` is the repackaged archive, whereas the unclassified JAR may be the plain archive. Smoke tests must target the **exact executable file**:

~~~bash
java -jar target/layout-demo-1.0.0-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

The line printed by `Application` remains:

~~~text
layout-demo:ok
~~~

**Do not hardcode assumptions that every build produces both files.** Without a classifier, `repackage` replaces the main artifact and keeps the original with `.original`. If `attach=false`, the repackaged artifact is not automatically installed/deployed to Maven repositories. Inspect actual plugin config and outputs.

**Do not use `finalName` to replace Maven coordinates.** For example, setting `<finalName>service</finalName>` yields `target/service.jar` locally, while the module's Maven identity remains `example.learning:layout-demo:1.0.0` upon install/deploy. Changing a filename never determines `JAR`/`WAR`/`ZIP`/`NONE`.

## 11. Layered JARs are distinct from `layout`

Spring Boot supports **layered archives** for Docker/OCI images, separating components such as dependencies, loader, snapshot dependencies, and application classes per layer policy. Layering optimizes image build caching; the archive still retains the layout structure required by the launcher to find classes/libs.

Do not confuse:

- `layout=JAR`: controls the **structure and bootstrap** of the executable archive.
- `layers`: describes **layers** inside supported archives; there is no layout named `LAYERS`.
- `spring-boot:build-image`: a separate goal that builds an OCI image, not merely renaming a JAR extension.
- `<executable>true</executable>`: prepends a launch script to supported archives; it does not convert `JAR` to `ZIP` or `WAR`.

Thus, when the goal is "optimize Docker layer caching," examine `layers` and `build-image`; when the goal is "load libraries from an external directory," consider `ZIP`/`PropertiesLauncher`; when the goal is "deploy to a servlet container," look at `WAR`. A single `layout` option does not solve every packaging problem.

## 12. Advanced options and compatibility limits

### 12.1. Custom `layoutFactory`

The Spring Boot Maven Plugin provides a `layoutFactory` parameter for specialized layout needs. It requires an implementation of Boot's `LayoutFactory` and appropriate plugin classpath configuration. When **`<layout>...` is explicitly specified**, plugin documentation states custom layout factories are ignored. Do not expect a custom `layoutFactory` to take effect while a fixed `layout` is configured.

Use a custom layout only with a clear requirement and a team ready to maintain and test it; for standard cases, `JAR`/`WAR`/`ZIP`/`NONE` are far more predictable.

### 12.2. You cannot turn an embedded server into an external WAR via `layout` alone

A web app targeting external Tomcat deployment normally needs:

- Maven `<packaging>war</packaging>` and proper dependency scopes.
- `SpringBootServletInitializer` or equivalent servlet bootstrap mechanism.
- A Servlet container compatible with `jakarta.servlet` and Boot's Java version.
- Appropriate context path, logging, JNDI/security, and deployment setup.
- Smoke testing **inside the actual external container**.

Changing only `<layout>WAR</layout>` inside a JAR project without adjusting these pieces creates mismatches or fails on the target server.

### 12.3. Do not treat `PropertiesLauncher` as a "free JAR upgrade"

`ZIP` is valuable when a configurable classpath is needed. Yet an external classpath expands what you must test: classloading order, library version conflicts, deployment file existence/permissions, and supply chain risks if an untrusted party modifies that directory. Using `ZIP` must pair with strict management of external JARs, checksums, and regression testing.

### 12.4. Do not expect `NONE` layout to run with `java -jar`

Any Java archive can declare `Main-Class` via another plugin, yet **Spring Boot `NONE` layout embeds no Boot bootstrap loader**. Nested library entries do not automatically become part of the JVM classpath. Consumers must supply their own classpath/launcher; if standalone execution is required, choose `JAR` or another executable layout.

### 12.5. Watch Spring Boot versions

Spring Boot loader packages change across versions. For instance, in Spring Boot 3.3 launcher classes live under `org.springframework.boot.loader.launch`; documentation for Boot 3.1 and earlier showed `org.springframework.boot.loader.JarLauncher`. Never copy class names from older articles and hardcode them into manifests manually. For another Boot version, inspect the manifest **actually generated** by the plugin and consult that version's docs.

## 13. Common errors and diagnostic guide

| Symptom | Possible cause | Action to take |
| --- | --- | --- |
| `no main manifest attribute` when running JAR | Plain archive, `NONE` layout, `repackage` didn't run, or wrong file | Check `Main-Class`, plugin execution, classifier |
| `ClassNotFoundException` for `JarLauncher` | Loader missing from archive or manifest points to wrong version's launcher | `jar tf`, inspect manifest, rebuild with right Boot plugin |
| `ClassNotFoundException` for application class | Wrong `Start-Class` package, or compiled class misplaced | Verify FQCN, `BOOT-INF/classes`/`WEB-INF/classes` |
| `NoClassDefFoundError` when running executable archive | Runtime dependency excluded or wrong scope | Check `BOOT-INF/lib` or `WEB-INF/lib`, dependency tree |
| `UnsupportedClassVersionError` | Runtime JRE/JDK too old for compiled bytecode | Check `java -version` on host, compiler/toolchain settings |
| File remains `.jar` after setting `layout=ZIP` | Normal behavior due to Maven `packaging=jar` | Distinguish layout from extension; inspect `PropertiesLauncher` |
| `loader.path` seems ignored | App still uses `JarLauncher`, wrong property name, or missing external dir | Inspect manifest, place `-Dloader.path` before `-jar`, check logs |
| `.war` fails to deploy on Tomcat 9 | Spring Boot 3.x uses Jakarta Servlet; Tomcat 9 uses `javax` | Use a compatible container and proper WAR/initializer config |
| WAR runs via `java -jar` yet external deploy fails | Wrong servlet initializer/container config/scope/context path | Check external container logs, container version, and URL |
| `WEB-INF/lib-provided` differs from expectations | `provided` scope wrong or WAR not repackaged | Inspect effective dependencies and archive entries |
| `NONE` fails to run with `java -jar` | No Boot bootstrap loader, by design | Use consumer-specific launcher or an executable layout |
| Build OK yet pipeline uploads wrong JAR | Multiple classifiers, plain, or `.original` JARs present | Pin exact path, manifest, and checksum checks |
| `mvn spring-boot:repackage` says no archive found | `package` phase hasn't run yet | Run `package` lifecycle before `repackage` |
| Layout right yet Docker container fails to start | Image entrypoint, JRE, permissions, or env issue | Test the OCI image and runtime directly |
| Custom `layoutFactory` has no effect | Explicit `layout` takes precedence | Check plugin configuration; remove override if factory is intended |
| Changed layout to "shrink size" yet JAR stays big | `layout` is not a dependency-exclusion mechanism | Check exclusions, packaging, layering, and actual archive entries |

**How to read errors:** an exception name is only a clue, not a conclusion. When errors occur post-deploy, check in order: **correct artifact → manifest → entries → JVM/version → dependencies → logs/runtime**. Never try to cure `ClassNotFoundException` by randomly switching `layout` without knowing where the missing library belongs.

## 14. Real-world selection scenarios

### A. Spring Boot web service running as one process in a container

Requirement: CI builds an executable archive, Dockerfile runs `java -jar`, no external servlet container, no runtime plugin loading.

**Choice:** Maven `packaging=jar`, Boot `layout=JAR` or leave default. Build with `mvn clean package`, verify `BOOT-INF`, smoke test `java -jar` and the image.

**Avoid:** `WAR` since no external servlet container is used; `ZIP` since no external classpath is needed; `NONE` since it lacks a Boot bootstrap launcher.

### B. Enterprise requirement to deploy a WAR into external Tomcat

Requirement: package as a WAR, run in a compatible servlet container, and optionally allow `java -jar` for debugging when properly configured.

**Choice:** Maven `packaging=war`, layout `WAR`, `SpringBootServletInitializer`, container dependency `provided`, test both executable WAR and external deployment.

**Avoid:** changing only `<layout>WAR</layout>` on a JAR project and assuming it is deploy-ready.

### C. A launcher needs to pick up plugin JARs from an external directory

Requirement: controlled classpath configuration, operations tooling managing versions/checksums for external libraries.

**Consider:** Maven `packaging=jar`, layout `ZIP` or `DIR`, using `PropertiesLauncher` with `loader.path`. Write explicit tests proving runtime loads the expected plugin; manage directory permissions and versions tightly.

**Do not assume:** `layout=ZIP` creates the plugin folder, emits a `.zip` file, or manages external JAR compatibility automatically.

### D. Artifact is unpacked and launched by another platform's runtime

Requirement: release platform provides its own loader/classpath management; do not embed the Spring Boot bootstrap loader.

**Consider:** layout `NONE` once the downstream consumer understands the output format and has been tested. Clearly define the archive contract, paths, dependency handling, and metadata.

**Avoid:** `NONE` for any service whose pipeline only knows `java -jar` and has no external launcher.

### E. Separating a plain JAR and executable JAR in a Maven repository

Requirement: another module consumes the classes as a library, while deployment needs an executable artifact.

**Mechanism to choose:** explicit `exec` classifier/`attach` or splitting into separate modules; do not accidentally try to solve this with `layout=ZIP` or `layout=NONE`. Verify `groupId:artifactId:version:classifier` coordinates and which file downstream consumers resolve.

## 15. Checklist when changing Spring Boot Maven Plugin layout

1. **Identify the final deliverable:** `java -jar` process, external Tomcat WAR, external classpath, or consumer-specific archive?
2. **Choose the right Maven `packaging`:** `jar` or `war`; do not confuse with `layout`.
3. **Choose `layout` or keep default:** `JAR` for standalone, `WAR` for WARs, `ZIP`/`DIR` for `PropertiesLauncher`, `NONE` for loaderless archives.
4. **Confirm Java main and servlet initializer:** `mainClass` for the launcher; external WAR deployment needs initializer and container compatibility.
5. **Check `dependency scopes`:** especially WAR `provided` and runtime dependencies; avoid stripping `BOOT-INF/lib` or `WEB-INF/lib`.
6. **Verify plugin execution:** `repackage` must run after initial archive creation; parent vs. non-parent POMs differ.
7. **Clean build:** `mvn clean package` in the right module; never test stale files.
8. **Inspect output file:** name/extension, manifest, `Main-Class`, `Start-Class`, `BOOT-INF`/`WEB-INF` entries, presence of loader.
9. **Test the matching launch mode:** `java -jar` for executable `JAR`/`WAR`/`ZIP`; external container deploy test for `WAR`; consumer-specific test for `NONE`.
10. **Preserve artifact identity:** classifier, `attach`, and `finalName` must not mislead pipelines into selecting the wrong file.
11. **For `ZIP`:** verify `loader.path` and external library governance if actually used.
12. **For containers:** test the final image/runtime rather than treating host JAR execution as sufficient.
13. **Across Boot versions:** verify Spring Boot loader classes and docs for your exact version instead of hardcoding manifests from another article.
14. **Document the decision:** why a non-default layout was chosen, its benefits, QA criteria, and rollback plan.

### Self-check

**Q1.** Maven `packaging=jar`, Boot `layout=ZIP`. Will the output file definitely have a `.zip` extension?

**Answer:** No. Maven still builds a JAR-typed artifact; `ZIP` layout governs internal structure and `PropertiesLauncher`, not the filename extension.

**Q2.** Why is `layout=NONE` not equivalent to `skip=true`?

**Answer:** `NONE` still runs `repackage` to bundle project/dependencies without embedding a loader; `skip=true` skips the `repackage` goal entirely.

**Q3.** Where do `JAR` and `WAR` typically place application classes?

**Answer:** `JAR` puts them in `BOOT-INF/classes`, `WAR` puts them in `WEB-INF/classes`. `WAR` also uses `WEB-INF/lib-provided` for `provided` dependencies.

**Q4.** When should `PropertiesLauncher` be used?

**Answer:** When there is a clear requirement for a customized classpath outside the archive via `loader.path` or loader configuration, backed by governance and testing of external JARs.

**Q5.** If a WAR runs via `java -jar` on Spring Boot 3.3, is it guaranteed to deploy to Tomcat 9?

**Answer:** No. Boot 3.x is built on Jakarta Servlet; Tomcat 9 uses the older `javax` namespace. A compatible container and matching WAR/initializer setup are required.

**Q6.** Can `maven-jar-plugin` set `Main-Class=demo.Application` as a substitute for `layout=JAR`?

**Answer:** No. A Spring Boot executable JAR needs the loader for nested runtime libraries, and the Boot plugin manages the manifest. Configure `mainClass`/`layout` in the Spring Boot Maven Plugin instead of manually setting `Main-Class`.

## 16. Official documentation

- Spring Boot Maven Plugin — Packaging Executable Archives (`JAR`/`WAR`/`ZIP`/`DIR`/`NONE` layouts): https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot Maven Plugin — Repackage goal parameters: https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot-repackage
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Launching Executable Jars / `PropertiesLauncher`: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Spring Boot — Traditional Deployment (WAR): https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — POM Reference (`packaging`, `finalName`, and plugins): https://maven.apache.org/pom.html
- Java 17 — `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Conclusion:** `packaging` determines the **Maven artifact type**, while `layout` determines the **structure and bootstrap mechanism of the Spring Boot archive**. `JAR` is the sensible default for standalone apps, `WAR` fits WAR/container requirements, `ZIP`/`DIR` uses `PropertiesLauncher` for flexible classpaths, and `NONE` bundles dependencies **without embedding a Boot bootstrap loader**. Every choice must be proven with **the real artifact, real manifest, and the target environment's actual launch method**, not just a `<layout>` tag in the POM.