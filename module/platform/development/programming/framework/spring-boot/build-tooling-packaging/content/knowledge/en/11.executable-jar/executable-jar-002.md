# Creating an Executable JAR with Maven package and repackage in Spring Boot

## 1. Goal: From Java Code to a Single File Runnable with `java -jar`

A Spring Boot application typically needs to be turned into an artifact ready for deployment to a server or container. With Maven, the common commands are:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Behind those two lines lie **two distinct packaging jobs**:

1. The `jar:jar` goal of the Maven JAR Plugin creates an **ordinary JAR** from compiled classes and resources. This JAR usually **does not contain** all bundled dependencies; if you simply run `java -jar`, the application may lack its classpath or lack a suitable main manifest.
2. The `spring-boot:repackage` goal of the **Spring Boot Maven Plugin** takes that source JAR, adds the loader and selected dependencies into Spring Boot's dedicated structure, configures the appropriate manifest, and produces an **executable/fat JAR** runnable with `java -jar`.

For a project using `spring-boot-starter-parent` with `spring-boot-maven-plugin` declared, the `repackage` goal is preconfigured in the lifecycle at `package`. Thus, `mvn clean package` alone is sufficient—there is no need to invoke the `repackage` goal manually.

**Important:** "Executable JAR" in Spring Boot normally means a **Java executable archive** runnable with `java -jar`. It is not inherently a native machine program; the target environment still needs a compatible Java runtime. It also differs from a "fully executable JAR" with a shell launch script (explained in Section 11).

### When Should You Create an Executable JAR?

- A Spring Boot application needs to be deployed as a standalone JVM service on a VM/server.
- An API with embedded Tomcat/Jetty/Undertow, or an application without a web server that has a `main` method to launch.
- CI/CD needs a clearly versioned artifact that can be verified and handed off to an image build or deployment tool.
- You want to run the same artifact with different environment configurations (`--server.port`, profiles, credentials outside the JAR).

Do not use an executable JAR as an ordinary library dependency for another project: application classes sit under `BOOT-INF/classes`, which differs from the standard JAR classpath layout. If a shared library is needed, extract a library module or keep a separate plain JAR via a classifier.

## 2. Understanding the Maven Lifecycle Order

Maven has **lifecycle phases**; `package` is a phase, while `jar:jar` and `spring-boot:repackage` are **plugin goals** bound to that phase. Invoking the `package` phase causes Maven to run all preceding phases in the default lifecycle, and then execute the bound goals.

```text
mvn clean package
  |
  +-- clean lifecycle
  |     \-- delete old target/ (maven-clean-plugin)
  |
  +-- default lifecycle up to package
        |
        +-- validate
        +-- process-resources
        +-- compile        --> target/classes
        +-- test-compile   --> target/test-classes (if tests exist)
        +-- test           --> run matching unit tests
        +-- package
              |
              +-- maven-jar-plugin:jar
              |     \-- create plain JAR from classes/resources
              |
              +-- spring-boot-maven-plugin:repackage
                    \-- take source JAR, repackage into executable JAR
```

The diagram above **omits intermediate phases** to highlight the primary sequence; Maven also has `generate-sources`, `process-classes`, `prepare-package`, and other phases. Plugin tasks configured by the project may add goals. With `<packaging>jar</packaging>` (or when packaging is omitted, defaulting to `jar`), the Maven JAR Plugin is bound to `package` by lifecycle mapping. The Spring Boot plugin runs `repackage` **after** the source JAR has been created.

| Command | What Happens? | Typical Outcome |
| --- | --- | --- |
| `mvn compile` | Compiles source code | `target/classes`; no executable JAR created yet |
| `mvn test` | Compiles then runs tests | Verification only, does not reach the `package` phase |
| `mvn package` | Runs up to the package phase, including bound goals | Executable JAR if the repackage plugin is configured |
| `mvn clean package` | Cleans previous build outputs then packages | Artifact from a clean build |
| `mvn install` | Runs through package then installs into local Maven repository | Installs main/attached artifacts into `~/.m2/repository` |
| `mvn deploy` | Runs through package then publishes artifact to remote Maven repository | Requires `distributionManagement` and access permissions |
| `mvn spring-boot:repackage` | Directly invokes a goal that needs a source JAR/WAR | **Should not be invoked standalone** without having run `package` |

**Distinguishing `clean` and `package`:** `clean` belongs to a separate lifecycle, so `mvn package` does not automatically delete `target`. In CI, use `mvn -B -ntp clean verify` or `clean package` depending on testing requirements; `verify` typically runs additional checks/goals bound after `package`. For an executable JAR, the artifact is produced during the `package` phase.

If tests fail, Maven normally stops before `repackage`. `-DskipTests` skips **running** tests while still allowing test compilation; `-Dmaven.test.skip=true` can skip both compiling and running tests. Do not use these flags to mask failing tests in a main release pipeline.

## 3. How Does `spring-boot-starter-parent` Configure `repackage`?

`spring-boot-starter-parent` inherits dependency/plugin version management and preconfigures an execution of `spring-boot-maven-plugin` with the ID **`repackage`**. However, the project must still declare the plugin inside `<build><plugins>` to activate it in the application module.

Typical POM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

These are **two snippets inside `pom.xml`**, not a complete POM. `3.5.0` is pinned for consistent illustration on Java 17; it is not a claim about the latest Spring Boot release.

When using the parent above:
- The plugin version is managed by the parent.
- An execution with ID `repackage` already exists, with goal `repackage` running in the `package` phase.
- There is no need to add another execution with a different ID or repeat `<goals>`.
- You can customize the execution **with the exact ID `repackage`** to specify a classifier, main class, or other relevant options.

A common mistake is using the starter parent while also adding another `<execution>` with the `repackage` goal and a new ID. Maven may execute repackage twice, complicating the build or causing errors because the artifact has already been repackaged. With the parent, simply declare the plugin as shown above.

## 4. Complete Java 17+ Example That Builds and Runs

Let us create a minimal API with an endpoint that answers HTTP requests. This section uses **Spring Boot 3.5.0**, **Java 17+**, and a Maven version compatible with that Boot version. Network access to Maven Central or an internal repository mirror is needed on the first run to download the parent POM, dependencies, and plugins.

Project structure:

```text
packaging-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── packaging/
                        └── PackagingDemoApplication.java
```

### 4.1. Complete `pom.xml` File

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>packaging-demo</name>
    <description>Demo Maven package and Spring Boot repackage</description>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-web` provides Spring MVC and an embedded servlet server according to the Spring Boot 3.5 starter. The Maven plugin turns the application JAR into an archive containing the loader and dependencies. The POM does not need to specify a version for `spring-boot-starter-web` because the parent manages dependency versions.

### 4.2. Java File with Entry Point and HTTP Endpoint

**`src/main/java/com/example/packaging/PackagingDemoApplication.java`:**

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PackagingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "World") String name) {
        return "Hello, " + name + "!";
    }
}
```

The Java file must match `package com.example.packaging` and public class name `PackagingDemoApplication`. `main` is the **real application entry point** invoked by the Spring Boot launcher after setting up the nested JAR classpath. Combining the controller into the application class is fine for small examples; in larger applications, separate controllers and services into their own classes for maintainability.

### 4.3. Creating the Artifact

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn -B -ntp clean package
```

- `-B`: runs Maven in batch mode, suitable for CI.
- `-ntp`: suppresses verbose artifact download progress output (supported by modern Maven).
- `clean package`: removes prior build outputs and performs compilation, tests, and packaging.
- If the repository already includes the Maven Wrapper, use `./mvnw -B -ntp clean package` (Windows: `mvnw.cmd`).

When the build succeeds, you normally see:

```text
target/
├── classes/
│   └── com/example/packaging/PackagingDemoApplication.class
├── packaging-demo-0.0.1-SNAPSHOT.jar
└── packaging-demo-0.0.1-SNAPSHOT.jar.original
```

These are **the primary relevant files**, not an exhaustive listing of the `target` directory: Maven also creates metadata, generated sources, and other directories. `.jar` is the executable archive after `repackage`, and `.jar.original` is the plain JAR prior to repackaging under the default configuration. An `.original` JAR is not always runnable standalone via `java -jar`.

### 4.4. Running the JAR and Checking the Response

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

The Spring Boot application starts its HTTP server; by default it typically listens on port **8080** if no override is configured and the port is free. Open another terminal:

```bash
curl -fsS 'http://localhost:8080/hello'
curl -fsS 'http://localhost:8080/hello?name=Mai'
```

**Corresponding response bodies:**

```text
Hello, World!
Hello, Mai!
```

Each `curl` command makes a separate request, and a Java `String` response does not append a newline automatically; when run consecutively, the terminal may display them adjacent to each other. The output block above separates lines for readability and does not imply the server sends trailing newlines. Stop the server with Ctrl+C.

You can change the port at **runtime** without repackaging:

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Then the endpoint is at `http://localhost:9090/hello`. This is a **Spring Boot application argument** passed into `main(String[] args)`, unrelated to the Maven repackage process. Environment-specific configuration such as database passwords and tokens should be provided from sources external to the artifact upon deployment.

## 5. Verifying the JAR Was Truly Repackaged

Seeing `BUILD SUCCESS` alone is not enough to conclude the archive runs well. Verify **the exact file path**, manifest, layout, and run a smoke test.

### 5.1. Listing Archive Contents

```bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Some expected entries in Spring Boot 3.5:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class
BOOT-INF/lib/spring-boot-3.5.0.jar
BOOT-INF/lib/...
BOOT-INF/layers.idx
```

This is a **representative list of entries**, not full stdout; versions and the set of JARs in `BOOT-INF/lib` depend on the dependency tree/build. The ellipsis `...` is illustrative, not an actual file name. You can filter them:

```bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep -E '^(BOOT-INF/|org/springframework/boot/loader/)'
```

The `grep` command applies to Bash/Linux/macOS with `grep` installed. On Windows PowerShell:

```powershell
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^(BOOT-INF/|org/springframework/boot/loader/)'
```

If the application class sits directly at `com/example/packaging/...` at the root of the JAR and there is no `BOOT-INF/lib`, it is very likely a **plain JAR**, or the build did not execute `repackage`.

### 5.2. Inspecting the Manifest

On Unix systems with `unzip`:

```bash
unzip -p target/packaging-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

The key lines are usually:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingDemoApplication
```

The actual manifest contains other attributes and the line order may differ. In Boot 3.x, `Main-Class` is the **Spring Boot launcher**, whereas `Start-Class` is the **application's main class**. The Spring Boot launcher knows how to load JARs inside `BOOT-INF/lib` and then invoke `Start-Class`. This is why you should not manually set `Main-Class` with the Maven JAR Plugin as a substitute for `repackage`.

Launcher class paths and manifest structures can change across Spring Boot major versions; when upgrading to Boot 4.x or another release, consult the documentation and inspect the artifact for that exact version rather than hardcoding behavior from a 3.5 example.

### 5.3. Minimum Tests Required to Pass

A valid artifact must satisfy these checks:

1. `mvn -B -ntp clean package` returns exit code **0**.
2. `target/packaging-demo-0.0.1-SNAPSHOT.jar` exists and is readable by the `jar` tool.
3. `META-INF/MANIFEST.MF` has the appropriate loader main and `Start-Class`.
4. `BOOT-INF/classes` contains application classes and `BOOT-INF/lib` contains required runtime dependencies.
5. `java -jar ...` starts successfully on a supported Java version.
6. `curl -fsS http://localhost:8080/hello` returns body **`Hello, World!`** and a 2xx HTTP status.
7. No internal secrets/credentials are unintentionally hardcoded in resources or build configurations.

If CI only checks JAR file size or the `mvn package` result without a smoke test, an archive missing runtime configuration or built for the wrong Java version can still be released.

## 6. Distinguishing Plain JARs, Executable Boot JARs, and "Fat JARs"

| Criterion | Plain JAR from `jar:jar` | Executable Boot JAR from `repackage` |
| --- | --- | --- |
| Application classes | Usually at the root by package, e.g., `com/example/...` | Under `BOOT-INF/classes/com/example/...` |
| Runtime dependencies | Usually **not** bundled | Packaged as nested JARs inside `BOOT-INF/lib` |
| Manifest | May lack a runnable `Main-Class` | Boot plugin manages launcher `Main-Class` and `Start-Class` |
| Running with `java -jar` | Only runs if main/classpath and manifest config suffice; usually insufficient for apps with dependencies | Designed to be run via `java -jar` on a compatible Java runtime |
| Use as a library for another project | More suitable | Unsuitable as a standard classpath dependency |
| Example artifact | `...jar.original` or a JAR with `plain` classifier | `...jar` or `...-exec.jar` if using a classifier |

**"Fat JAR/uber JAR"** is a broad term: many tools can bundle classes/dependencies into a single file. A Spring Boot executable JAR is a specific type of fat JAR with **nested dependency JARs**, its own loader, and a specific layout; it is not the same as when the Maven Shade Plugin "flattens" all dependency classes into the root JAR. When an integration system expects a specific layout, verify the loader and runtime; do not rely solely on the word "fat".

`maven-jar-plugin` creates the plain JAR itself, and `spring-boot-maven-plugin` repackages it **afterward**. The two plugins work together; you cannot use the Maven JAR Plugin alone to obtain the Spring Boot nested-loader layout.

## 7. Without the Spring Boot Parent: You Must Bind the `repackage` Goal

Many projects use a corporate parent POM or only import the Spring Boot BOM. In this case, **importing the BOM does not grant you the plugin execution** from `spring-boot-starter-parent`.

Example configuration in a `pom.xml` using another parent; the snippet below shows **the blocks to merge into a valid POM**, not a standalone POM:

```xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.5.0</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
            <executions>
                <execution>
                    <id>repackage</id>
                    <phase>package</phase>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Points to ensure:

- The project has `<modelVersion>4.0.0</modelVersion>`, `groupId/artifactId/version` (or inherited values), and a Java main class.
- `<packaging>jar</packaging>` or default `jar` packaging so Maven produces the plain source archive.
- Plugin versions **are declared explicitly** when not managed by a parent, and the Java compiler targets release 17.
- `repackage` **is bound to `package`**, after the goal that creates the source JAR.
- The BOM only manages dependency versions; other plugins (compiler, surefire, jar, etc.) should have their versions pinned via the project/corporate parent for reproducible builds.

Once merged properly, `mvn clean package` also produces an executable JAR. If a corporate parent already configures the `repackage` goal, check `mvn help:effective-pom` before **adding a second execution**, to avoid running the goal twice. When using multiple executions in the same phase, make sure `maven-jar-plugin` creates the source JAR before `spring-boot-maven-plugin:repackage`.

### Calling `spring-boot:repackage` Directly

The Spring Boot Maven Plugin advises **against calling `repackage` on its own** because the goal needs a source JAR/WAR produced by the `package` phase. If a project declares the plugin but **has not bound `repackage` to `package`**, you can explicitly run:

```bash
mvn package spring-boot:repackage
```

This runs Maven's `package` phase first and then invokes the `repackage` goal. However, **with a POM using `spring-boot-starter-parent` as in Section 4, `mvn package` already runs `repackage`**. There is no need to append the goal again; use `mvn clean package` for the primary example.

## 8. Keeping Both the Plain JAR and Executable JAR via a Classifier

By default, `repackage` **replaces Maven's main artifact** with the executable JAR and preserves the source JAR as `.jar.original` for reference in `target`. When you need to publish a plain JAR for another module while also producing an executable JAR to run, use a `classifier`, such as `exec`.

In the POM with `spring-boot-starter-parent` from Section 4, **replace the existing `<build>` block** with:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

**Very important:** the execution ID must be `repackage` to customize the execution inherited from the parent. Do not add another execution with an arbitrary ID just to set a classifier.

The output of `mvn clean package` is typically:

```text
target/packaging-demo-0.0.1-SNAPSHOT.jar        # Plain JAR (main artifact)
target/packaging-demo-0.0.1-SNAPSHOT-exec.jar   # Executable Boot JAR (classified artifact)
```

Run the correct executable artifact:

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT-exec.jar
```

Do not run the plain JAR on the first line and expect it to execute standalone. With a classifier, the executable artifact can be attached so `mvn install`/`mvn deploy` publishes it alongside the main JAR (depending on plugin and repository configuration). If another project needs reusable code, it is still **better to extract a library module** rather than depending on application classes.

### Renaming the Final File

Maven supports `<finalName>` inside `<build>`:

```xml
<build>
    <finalName>orders-service</finalName>
</build>
```

This is an **optional snippet** to merge into your existing build block; do not create a second build block. With `finalName=orders-service`, the file in `target` may be `orders-service.jar` instead of `artifactId-version.jar`. However, Maven artifact coordinates during install/deploy are still determined by `groupId/artifactId/version/classifier`; **the local file name is not the entirety of the Maven artifact identity**.

## 9. Properly Customizing the Main Class and Manifest

If a project has **multiple** classes containing `public static void main(String[] args)`, auto-detection may fail or pick an unintended class. Configure it directly in the Spring Boot Maven plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.packaging.PackagingDemoApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This is a **block to replace/merge into the existing plugin**, not a duplicate plugin declaration with the same coordinates. The Boot plugin manages `Main-Class` as the loader and `Start-Class` as the application class according to the layout/version. Configuring `<mainClass>` is the explicit way to handle multiple entry points.

Do not manually add:

```xml
<archive>
    <manifest>
        <mainClass>com.example.packaging.PackagingDemoApplication</mainClass>
    </manifest>
</archive>
```

to the Maven JAR Plugin and treat it as a replacement for the Boot loader. That only configures the JAR plugin's manifest; it **does not create `BOOT-INF/lib`** and does not ensure nested dependencies will be loaded. For a Spring Boot executable JAR, loader/main manifest entries must be managed through the Boot plugin.

### Other Layouts

The Spring Boot Maven Plugin supports common layouts:

| `layout` | Meaning |
| --- | --- |
| `JAR` | Standard executable Spring Boot JAR layout |
| `WAR` | Executable WAR, classes in `WEB-INF/classes` |
| `ZIP`/`DIR` | Layout using `PropertiesLauncher` for specialized configuration cases |
| `NONE` | Bundles nested dependencies **without a bootstrap loader**, so it cannot run with `java -jar` out of the box |

Keep the default layout if the goal is a standard executable JAR. Do not select `NONE` to "fix" a `Main-Class` error, since that layout lacks a loader. For applications deployed to an external servlet container, WAR is a different option requiring compatible Spring MVC/servlet container configuration; do not force a JAR into a WAR merely by changing `layout`.

## 10. Which Dependencies Are Packaged into the Executable JAR?

The Spring Boot plugin selects dependencies based on the dependency graph and plugin configuration. A typical JAR contains:

```text
BOOT-INF/classes/    # Application classes + resources
BOOT-INF/lib/        # Runtime dependency JARs needed when running
org/springframework/boot/loader/...  # Spring Boot loader
META-INF/MANIFEST.MF
```

**Not every dependency in the POM belongs in the artifact.** Scopes such as `compile`, `runtime`, `provided`, `test`, and the optional flag affect the dependency graph and repackaging. The Boot Maven Plugin applies its own packaging rules: across common Boot 3.x branches, even `provided`/`optional` dependencies may be included in the executable archive unless explicitly excluded; `test` dependencies are not treated as runtime dependencies. Inspect the actual `BOOT-INF/lib` contents rather than guessing solely from scope.

Some specific details in Spring Boot 3.5:

- `spring-boot-devtools` and `spring-boot-docker-compose` are excluded from the repackaged archive by default via `excludeDevtools`/`excludeDockerCompose` settings.
- `<excludes>` or `<excludeGroupIds>` on the Boot plugin can omit artifacts you do not wish to distribute; specify exact `groupId`/`artifactId` values and avoid excluding required runtime libraries.
- `includeSystemScope` does not include all `system`-scope dependencies in the executable archive by default; avoid relying on absolute local JAR paths on developer machines.
- Certain nested libraries have special requirements and must be unpacked at runtime; the Boot plugin supports `requiresUnpack` for specific cases. Do not enable it broadly.

Example **configuration snippet inside the Spring Boot plugin** to exclude a build/dev-only dependency:

```xml
<configuration>
    <excludes>
        <exclude>
            <groupId>com.example</groupId>
            <artifactId>dev-only-helper</artifactId>
        </exclude>
    </excludes>
</configuration>
```

This snippet is purely illustrative for an internal artifact named `dev-only-helper`. If the real application needs its classes at runtime, excluding it will cause `ClassNotFoundException` or `NoClassDefFoundError`. Check `mvn dependency:tree` and run a smoke test before trimming dependencies.

### Checking the Dependency Tree

```bash
mvn -B -ntp dependency:tree
```

This command displays the **resolved Maven dependency tree**, whereas `jar tf` displays **the files actually inside the JAR**. The two differ: the dependency tree reflects scopes, transitives, and omitted conflicts, while the executable archive reflects the plugin's packaging rules. `dependency:tree` requires the Maven Dependency Plugin, which may need to be downloaded on first use.

## 11. Layered JARs and Fully Executable JARs

These two options are often confused because both relate to "deployment optimization".

### 11.1. Layered JARs for Container Image Build Caching

In Spring Boot 3.5, an executable JAR typically contains `BOOT-INF/layers.idx` describing layers such as:

- `dependencies`: release dependencies that change infrequently;
- `spring-boot-loader`: bootstrap loader;
- `snapshot-dependencies`: snapshot dependencies;
- `application`: application classes/resources and local modules.

Layer metadata helps container image build tools group less frequently changing parts into cacheable layers, yet **the JAR remains an archive run with `java -jar`**. The `layers.idx` file does not turn the JAR into an OCI image on its own, nor does it make Maven automatically publish an image.

To disable layer metadata with the Boot plugin, add **inside the plugin's `<configuration>`**:

```xml
<layers>
    <enabled>false</enabled>
</layers>
```

Customize this only when specifically required; the default is usually appropriate. To build an OCI image, you can use `spring-boot:build-image` or a Dockerfile, which is a **separate deployment step** outside the scope of `mvn package`/`repackage`.

### 11.2. Fully Executable JARs with a Shell Launch Script

The Spring Boot Maven plugin also offers the option:

```xml
<configuration>
    <executable>true</executable>
</configuration>
```

This option prepends a launch script to the JAR file so it can be executed directly like an executable file on Unix systems. This **differs** from a regular executable Boot JAR, which runs smoothly via `java -jar`. Some ZIP/JAR tools do not handle a fully executable archive with a prefixed script as expected; therefore, enable it only if you genuinely need to run the file directly that way. The default `executable=false` is suitable for JAR distribution and inspection with `jar tf`.

**Do not confuse file `+x` permissions with the Java launcher.** `chmod +x app.jar` does not give an unrepackaged plain JAR a loader or dependencies.

## 12. CI/CD-Level Customizations

### 12.1. Do Not Bundle Secrets and Runtime-Specific Config into the Binary

In the example, `src/main/resources/application.properties` (if present) goes into `BOOT-INF/classes`. This file may hold **non-sensitive** defaults, while passwords/tokens, environment-specific database URLs, signing keys, and so on should be supplied via the environment, a secret store, or external configuration outside the artifact.

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

This is a runtime argument and does not modify the JAR. When aiming to keep **a single binary across dev/staging/prod**, externalizing configuration this way prevents rebuilding for every secret.

### 12.2. Ensuring the Java Version

Spring Boot 3.5 requires Java 17 or higher. In the example POM, `<java.version>17</java.version>` is used by the parent to set the compiler release. If building with a newer JDK while targeting Java 17 at runtime, ensure compatible bytecode is emitted and avoid using APIs that only exist in newer versions. On the server:

```bash
java -version
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

`UnsupportedClassVersionError` indicates that the bytecode requires a newer Java version than the runtime provides. The fix is to use a JRE/JDK runtime of sufficient version or compile for the release your project actually supports.

### 12.3. Using the Maven Wrapper and Deterministic Outputs

Use the Maven Wrapper (`./mvnw`/`mvnw.cmd`) when provided by the repository so every machine runs the same Maven distribution; pin Spring Boot/plugin versions in the POM and review dependency updates on a schedule.

A minimal CI job example (shell):

```bash
set -e
./mvnw -B -ntp clean verify
test -f target/packaging-demo-0.0.1-SNAPSHOT.jar
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar |
    grep -q 'BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class'
```

This is a **Bash snippet for a repository that already has the Maven Wrapper**, `grep`, and `test`; it is not a complete pipeline YAML. `verify` runs through `package` so the artifact is created; if a test or check fails, the job aborts. Before deploying, add a real smoke test running in a production-like environment with external dependencies appropriately configured.

You can use checksums to verify an artifact moving across CI/registries was not altered:

```bash
sha256sum target/packaging-demo-0.0.1-SNAPSHOT.jar
```

`sha256sum` is common on Linux; Windows PowerShell provides `Get-FileHash -Algorithm SHA256`. A checksum verifies the integrity of **specific bytes**, not that the artifact functions properly or is free of vulnerabilities.

## 13. Common Errors During `package` and `repackage`

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| `target/app.jar` exists, but `java -jar` says `no main manifest attribute` | Only a plain JAR was created, missing Boot launcher/manifest | Check Spring Boot Maven plugin declaration, parent, and `repackage` execution; read the manifest |
| `ClassNotFoundException` when running the JAR | Dependency missing from archive or wrong layout/classpath | Run `jar tf` to check `BOOT-INF/lib`, review excludes and dependency tree |
| `Could not find main class` / unable to determine main class | Missing `main` or multiple entry-point classes | Check class/package and configure `<mainClass>` in the Boot plugin |
| Calling `mvn spring-boot:repackage` fails because plugin cannot find source JAR | `package` has not run; `repackage` does not compile/package from scratch | Use `mvn clean package` if bound by parent, or `mvn package spring-boot:repackage` if unbound |
| `repackage` goal runs twice | Starter parent already defines the execution and POM adds a redundant execution/CLI goal | Keep a single execution with ID `repackage` when customizing |
| Executable JAR exists but fails on target Java runtime | Runtime Java version is older than compiled bytecode | Check `java -version`, compiler release, and Spring Boot requirements |
| `jar tf` shows neither `BOOT-INF/classes` nor `BOOT-INF/lib` | Inspecting a plain JAR, `repackage` skipped, or different classifier | Check output file name, `<classifier>`, and `spring-boot.repackage.skip` |
| POM imports Boot BOM but produces no executable JAR | BOM only manages dependencies, does not bind plugin goal | Declare the Boot Maven plugin + `repackage` execution in `package` |
| Plugin resolution fails with `Plugin not found` | Repository/proxy/mirror cannot reach the Spring Boot plugin | Check `settings.xml`, `pluginRepositories`, credentials, and mirrors |
| Plugin reports no main class | Library module, invalid app main, or source failed to compile | Check `src/main/java`, packaging, and entry point; library modules should stay plain JARs |
| `.jar.original` accidentally executed | The backup file is the plain source JAR | Run the repackaged `.jar` or `-exec.jar` when a classifier is used |
| Setting `<finalName>` causes CI not to find the artifact | Name in `target` changed from `artifactId-version` | Check actual output and update CI paths |
| Tests fail before JAR is created | Maven runs `test` before `package` | Fix the tests; skip only under explicit policy, do not hide failures |
| Application starts but port 8080 is busy | Runtime config conflict or another process occupies the port | Stop the other process or pass `--server.port=9090` |
| JAR works on dev machine but fails on deploy | Different Java version, secrets/config, DNS, network, or filesystem permissions | Run a smoke test in the actual target deployment environment |
| `maven-jar-plugin` and `repackage` in same phase in wrong order | Source archive not ready when `repackage` runs | Ensure the JAR creation goal runs before `repackage` |
| `<layout>NONE</layout>` set and `java -jar` fails | Layout `NONE` lacks a bootstrap launcher | Use the standard `JAR` layout |
| Maven `install`/`deploy` publishes an unexpected artifact | Misunderstanding of main artifact/classifier/attach | Check `mvn install` output, plugin `classifier`/`attach`, and artifact coordinates |

### Useful Diagnostic Commands

```bash
mvn -version
mvn help:effective-pom
mvn -B -ntp clean package
mvn -B -ntp dependency:tree
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
unzip -p target/packaging-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

`help:effective-pom` shows the plugin configuration after parent inheritance; it is very useful for spotting an unbound or duplicated `repackage` execution. `jar tf` and `unzip -p` inspect the actual archive. If using the `exec` classifier, replace the path with `...-exec.jar`. Maven Help Plugin and Dependency Plugin may also require network access on first download.

Do not wipe the entire `~/.m2/repository` over a single failed build; first determine whether it is a dependency resolution, test, compilation, or archive layout failure. For cached dependency resolution failures, `mvn -U` can refresh metadata after fixing repository settings.

## 14. Common Misconceptions

1. **"`package` is another name for `repackage`."** False: `package` is a lifecycle phase; `repackage` is a Spring Boot plugin goal that runs during that phase when bound.
2. **"Adding `spring-boot-starter-web` alone makes the JAR executable."** False: the starter provides runtime dependencies, whereas the Maven plugin and `repackage` goal create the layout and launcher.
3. **"Running `mvn package spring-boot:repackage` is always better than `mvn package`."** False with the starter parent: `repackage` already runs during `package`, so invoking it again is redundant.
4. **"The BOM completely replaces the Spring Boot starter parent."** The BOM only manages dependency versions; it does not automatically add plugin management/executions to the lifecycle.
5. **"The manifest just needs `Main-Class` pointing to the `@SpringBootApplication` class."** Insufficient for nested dependency JARs; the Boot loader and `Start-Class` handle that part.
6. **"Having a `.jar` file means it can run with `java -jar`."** The file extension only denotes the archive format. It needs a valid main class, manifest, and classpath.
7. **"`.jar.original` is a backup copy identical to the executable JAR."** It is normally the original JAR prior to `repackage`, with a different layout and dependencies.
8. **"`mvn package` skips tests."** By default Maven runs through the `test` phase; tests are bypassed only when skip flags/configs are used or no tests exist.
9. **"`classifier=exec` makes the executable JAR the main artifact."** In the example configuration, the main artifact is the plain JAR, while the executable carries the `exec` classifier.
10. **"`spring-boot:repackage` builds a Docker image."** No: it builds an executable JAR/WAR; images require a separate step such as Buildpacks or a Dockerfile.
11. **"Since the JAR bundles dependencies, it includes secrets and the Java runtime too."** No: sensitive application configuration and the Java runtime typically live outside the archive.
12. **"Upgrading Spring Boot only requires bumping the version number."** You must check Java requirements, plugins, launcher classes, dependency compatibility, and re-run verification/tests for that branch.

## 15. Recommended Practical Workflow

For a new Spring Boot project using Maven:

1. Choose a Java version supported by your Spring Boot version (e.g., **Java 17** for Boot **3.5.0**).
2. Use `spring-boot-starter-parent` or a BOM/corporate parent with equivalent plugin configuration.
3. Ensure there is a Spring Boot main class and the Java file is in the right package.
4. Declare `spring-boot-maven-plugin`; if using the starter parent, **do not add a duplicate execution goal**.
5. Run `mvn -B -ntp clean package` to compile, test, and repackage.
6. Inspect `target/...jar`, `BOOT-INF/classes`, `BOOT-INF/lib`, and `META-INF/MANIFEST.MF`.
7. Run `java -jar target/...jar`; test endpoints/logic with runtime configuration.
8. If both a library and an application are needed, split modules or design an `exec` classifier and confirm which artifact gets installed/deployed.
9. In CI, publish the QA-verified artifact, keep secrets out, verify the Java runtime, and run a smoke test before deployment.
10. When upgrading Spring Boot major versions, consult the **exact version's documentation** since launcher/plugin structure may change.

## 16. Official Documentation for Version-Specific Reference

- Spring Boot 3.5 – [Packaging Executable Archives (Maven Plugin)](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): `repackage`, classifier, mainClass, dependency exclusions, layers, JAR layout.
- Spring Boot 3.5 – [Using the Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent, plugin execution, and non-parent usage.
- Spring Boot 3.5 – [Build](https://docs.spring.io/spring-boot/3.5/how-to/build.html): why executable JARs are unsuitable as dependencies, creating library artifacts.
- Spring Boot 3.5 – [Efficient Deployments](https://docs.spring.io/spring-boot/3.5/reference/packaging/efficient.html): JAR layers and deployment strategies.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `package` phase, plugin goals, and binding.
- Apache Maven – [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): `jar:jar` goal and manifest.

**Rule to remember:** Maven `package` **builds the source artifact** in the lifecycle; Spring Boot Maven Plugin `repackage` **repackages that artifact** into an executable archive with the right loader, dependencies, and manifest to run with `java -jar`. When using `spring-boot-starter-parent`, `mvn clean package` suffices because the `repackage` execution is already configured.